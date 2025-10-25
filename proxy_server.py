import socket
import threading
import uuid
import base64
from models import get_session, Tunnel
import time

active_connections = {}
connection_lock = threading.Lock()

class TrafficProxy:
    def __init__(self, socketio_instance, connected_tunnels):
        self.socketio = socketio_instance
        self.connected_tunnels = connected_tunnels
        self.proxy_threads = {}
        self.active_ports = {}
        self.stop_flags = {}
    
    def start_proxy_for_tunnel(self, tunnel_id, public_port, protocol='TCP'):
        if public_port in self.active_ports:
            print(f'[*] Proxy already running on port {public_port}')
            return
        
        self.stop_flags[public_port] = False
        self.active_ports[public_port] = {'tunnel_id': tunnel_id, 'protocol': protocol}
        
        if protocol in ['TCP', 'BOTH']:
            tcp_thread = threading.Thread(
                target=self._tcp_proxy_worker,
                args=(tunnel_id, public_port),
                daemon=True
            )
            tcp_thread.start()
            self.proxy_threads[f'{tunnel_id}_tcp'] = tcp_thread
            print(f'[+] Started TCP proxy on port {public_port} for tunnel {tunnel_id}')
        
        if protocol in ['UDP', 'BOTH']:
            udp_thread = threading.Thread(
                target=self._udp_proxy_worker,
                args=(tunnel_id, public_port),
                daemon=True
            )
            udp_thread.start()
            self.proxy_threads[f'{tunnel_id}_udp'] = udp_thread
            print(f'[+] Started UDP proxy on port {public_port} for tunnel {tunnel_id}')
    
    def stop_proxy_for_tunnel(self, tunnel_id, public_port):
        if public_port in self.stop_flags:
            self.stop_flags[public_port] = True
        if public_port in self.active_ports:
            del self.active_ports[public_port]
        
        with connection_lock:
            for conn_id in list(active_connections.keys()):
                if active_connections[conn_id].get('tunnel_id') == tunnel_id:
                    conn_data = active_connections[conn_id]
                    if 'socket' in conn_data and conn_data['socket']:
                        try:
                            conn_data['socket'].close()
                        except:
                            pass
                    del active_connections[conn_id]
        
        for key in list(self.proxy_threads.keys()):
            if key.startswith(f'{tunnel_id}_'):
                del self.proxy_threads[key]
        
        print(f'[-] Stopped traffic proxy on port {public_port} for tunnel {tunnel_id}')
    
    def _tcp_proxy_worker(self, tunnel_id, public_port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind(('0.0.0.0', public_port))
            server_socket.listen(50)
            server_socket.settimeout(1.0)
            print(f'[*] TCP Proxy listening on 0.0.0.0:{public_port}')
            
            while not self.stop_flags.get(public_port, False):
                try:
                    client_socket, addr = server_socket.accept()
                    print(f'[+] New TCP connection from {addr} on port {public_port}')
                    
                    handler_thread = threading.Thread(
                        target=self._handle_tcp_stream,
                        args=(client_socket, tunnel_id, public_port, addr),
                        daemon=True
                    )
                    handler_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self.stop_flags.get(public_port, False):
                        print(f'[!] Error accepting TCP connection: {e}')
        except Exception as e:
            print(f'[!] Error starting TCP proxy on port {public_port}: {e}')
        finally:
            server_socket.close()
            print(f'[-] TCP Proxy stopped on port {public_port}')
    
    def _udp_proxy_worker(self, tunnel_id, public_port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind(('0.0.0.0', public_port))
            server_socket.settimeout(1.0)
            print(f'[*] UDP Proxy listening on 0.0.0.0:{public_port}')
            
            udp_sessions = {}
            
            while not self.stop_flags.get(public_port, False):
                try:
                    data, addr = server_socket.recvfrom(65535)
                    print(f'[+] UDP packet from {addr} on port {public_port}: {len(data)} bytes')
                    
                    session_key = f"{addr[0]}:{addr[1]}"
                    if session_key not in udp_sessions:
                        session_id = str(uuid.uuid4())
                        udp_sessions[session_key] = {
                            'session_id': session_id,
                            'addr': addr,
                            'last_activity': time.time()
                        }
                        print(f'[*] Created UDP session {session_id} for {addr}')
                    else:
                        udp_sessions[session_key]['last_activity'] = time.time()
                    
                    session_id = udp_sessions[session_key]['session_id']
                    
                    handler_thread = threading.Thread(
                        target=self._handle_udp_packet,
                        args=(server_socket, data, addr, tunnel_id, public_port, session_id),
                        daemon=True
                    )
                    handler_thread.start()
                    
                    current_time = time.time()
                    for key in list(udp_sessions.keys()):
                        if current_time - udp_sessions[key]['last_activity'] > 120:
                            print(f'[*] Expiring UDP session {udp_sessions[key]["session_id"]}')
                            del udp_sessions[key]
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self.stop_flags.get(public_port, False):
                        print(f'[!] Error receiving UDP packet: {e}')
        except Exception as e:
            print(f'[!] Error starting UDP proxy on port {public_port}: {e}')
        finally:
            server_socket.close()
            print(f'[-] UDP Proxy stopped on port {public_port}')
    
    def _handle_tcp_stream(self, client_socket, tunnel_id, public_port, addr):
        conn_id = str(uuid.uuid4())
        
        try:
            client_socket.settimeout(300.0)
            
            if tunnel_id not in self.connected_tunnels:
                print(f'[!] Tunnel {tunnel_id} not connected')
                client_socket.send(b'HTTP/1.1 503 Service Unavailable\r\n\r\nTunnel not connected')
                client_socket.close()
                return
            
            tunnel_info = self.connected_tunnels[tunnel_id]
            client_sid = tunnel_info['sid']
            
            with connection_lock:
                active_connections[conn_id] = {
                    'socket': client_socket,
                    'tunnel_id': tunnel_id,
                    'type': 'TCP',
                    'active': True,
                    'buffer': []
                }
            
            self.socketio.emit('new_connection', {
                'conn_id': conn_id,
                'tunnel_id': tunnel_id,
                'protocol': 'TCP'
            }, to=client_sid)
            
            print(f'[*] TCP stream {conn_id} established for tunnel {tunnel_id}')
            
            while True:
                with connection_lock:
                    if conn_id not in active_connections or not active_connections[conn_id]['active']:
                        break
                
                try:
                    data = client_socket.recv(8192)
                    if not data:
                        print(f'[*] TCP client closed connection {conn_id}')
                        break
                    
                    data_b64 = base64.b64encode(data).decode('ascii')
                    self.socketio.emit('stream_data', {
                        'conn_id': conn_id,
                        'data': data_b64,
                        'protocol': 'TCP'
                    }, to=client_sid)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f'[!] Error reading TCP stream {conn_id}: {e}')
                    break
            
            self.socketio.emit('close_connection', {
                'conn_id': conn_id
            }, to=client_sid)
            
        except Exception as e:
            print(f'[!] Error handling TCP stream {conn_id}: {e}')
        finally:
            with connection_lock:
                if conn_id in active_connections:
                    active_connections[conn_id]['active'] = False
                    try:
                        active_connections[conn_id]['socket'].close()
                    except:
                        pass
                    del active_connections[conn_id]
            print(f'[-] TCP stream {conn_id} closed')
    
    def _handle_udp_packet(self, server_socket, data, addr, tunnel_id, public_port, session_id):
        try:
            if tunnel_id not in self.connected_tunnels:
                print(f'[!] Tunnel {tunnel_id} not connected')
                return
            
            tunnel_info = self.connected_tunnels[tunnel_id]
            client_sid = tunnel_info['sid']
            
            data_b64 = base64.b64encode(data).decode('ascii')
            
            self.socketio.emit('udp_packet', {
                'session_id': session_id,
                'data': data_b64,
                'tunnel_id': tunnel_id,
                'addr': f"{addr[0]}:{addr[1]}"
            }, to=client_sid)
            
            with connection_lock:
                if session_id not in active_connections:
                    active_connections[session_id] = {
                        'socket': server_socket,
                        'tunnel_id': tunnel_id,
                        'type': 'UDP',
                        'addr': addr,
                        'active': True
                    }
            
        except Exception as e:
            print(f'[!] Error handling UDP packet: {e}')

proxy_instance = None

def get_proxy_instance(socketio_instance, connected_tunnels):
    global proxy_instance
    if proxy_instance is None:
        proxy_instance = TrafficProxy(socketio_instance, connected_tunnels)
    return proxy_instance

def handle_stream_response(conn_id, data):
    with connection_lock:
        if conn_id in active_connections and active_connections[conn_id]['active']:
            try:
                if isinstance(data, str):
                    data = base64.b64decode(data)
                active_connections[conn_id]['socket'].send(data)
                return True
            except Exception as e:
                print(f'[!] Error sending to connection {conn_id}: {e}')
                active_connections[conn_id]['active'] = False
                return False
    return False

def handle_udp_response(session_id, data):
    with connection_lock:
        if session_id in active_connections and active_connections[session_id]['type'] == 'UDP':
            try:
                if isinstance(data, str):
                    data = base64.b64decode(data)
                server_socket = active_connections[session_id]['socket']
                addr = active_connections[session_id]['addr']
                server_socket.sendto(data, addr)
                return True
            except Exception as e:
                print(f'[!] Error sending UDP to session {session_id}: {e}')
                return False
    return False

def close_connection(conn_id):
    with connection_lock:
        if conn_id in active_connections:
            active_connections[conn_id]['active'] = False
            try:
                active_connections[conn_id]['socket'].close()
            except:
                pass
            del active_connections[conn_id]
