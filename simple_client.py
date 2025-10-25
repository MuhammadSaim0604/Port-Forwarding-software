#!/usr/bin/env python3
import socketio
import sys
import socket
import time
import logging
import base64
import threading

logging.basicConfig(level=logging.WARNING)

if len(sys.argv) < 5:
    print("Usage: python simple_client.py <server_url> <token> <tunnel_id> <local_port>")
    sys.exit(1)

server_url = sys.argv[1]
token = sys.argv[2]
tunnel_id = int(sys.argv[3])
local_port = int(sys.argv[4])

sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=10,
    reconnection_delay=2,
    reconnection_delay_max=10,
    logger=False,
    engineio_logger=False
)

tunnel_protocol = 'TCP'
heartbeat_running = False
active_local_connections = {}
local_connections_lock = threading.Lock()

def send_heartbeat():
    global heartbeat_running
    heartbeat_running = True
    while heartbeat_running and sio.connected:
        try:
            time.sleep(30)
        except:
            break

@sio.on("connect")
def on_connect():
    print("[+] Connected to tunnel server")
    print("[*] Authenticating...")
    sio.emit("tunnel_auth", {
        "token": token,
        "tunnel_id": tunnel_id,
        "local_port": local_port
    })

@sio.on("auth_response")
def on_auth_response(data):
    global tunnel_protocol, heartbeat_running
    print("\n" + "="*60)
    if data.get("success"):
        tunnel_protocol = data.get('protocol', 'TCP')
        print("[SUCCESS] Tunnel authenticated and active!")
        print("="*60)
        print(f"Protocol: {tunnel_protocol}")
        print(f"Public Port: {data.get('public_port')}")
        print(f"Local Port: {local_port}")
        print(f"\n{data.get('message')}")
        print("\nTunnel is running. Press Ctrl+C to stop.")
        
        if not heartbeat_running:
            heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
            heartbeat_thread.start()
    else:
        print("[ERROR] Authentication failed!")
        print("="*60)
        print(f"Error: {data.get('error')}")
        if "verification_url" in data:
            print(f"\nPlease verify at: {server_url}{data.get('verification_url')}")
        sys.exit(1)
    print("="*60)

@sio.on("new_connection")
def on_new_connection(data):
    conn_id = data.get('conn_id')
    protocol = data.get('protocol', 'TCP')
    
    print(f"[+] New {protocol} connection: {conn_id}")
    
    try:
        local_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        local_socket.settimeout(10)
        
        try:
            local_socket.connect(('127.0.0.1', local_port))
            local_socket.settimeout(300.0)
        except ConnectionRefusedError:
            print(f"[!] Cannot connect to localhost:{local_port} - Is your service running?")
            sio.emit("close_connection", {'conn_id': conn_id})
            return
        
        with local_connections_lock:
            active_local_connections[conn_id] = {
                'socket': local_socket,
                'active': True
            }
        
        def read_from_local():
            try:
                while True:
                    with local_connections_lock:
                        if conn_id not in active_local_connections or not active_local_connections[conn_id]['active']:
                            break
                    
                    try:
                        data = local_socket.recv(8192)
                        if not data:
                            print(f"[*] Local service closed connection {conn_id}")
                            break
                        
                        data_b64 = base64.b64encode(data).decode('ascii')
                        sio.emit("stream_response", {
                            'conn_id': conn_id,
                            'data': data_b64
                        })
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"[!] Error reading from local: {e}")
                        break
                
                sio.emit("close_connection", {'conn_id': conn_id})
            except Exception as e:
                print(f"[!] Error in read_from_local: {e}")
            finally:
                with local_connections_lock:
                    if conn_id in active_local_connections:
                        active_local_connections[conn_id]['active'] = False
        
        read_thread = threading.Thread(target=read_from_local, daemon=True)
        read_thread.start()
        
    except Exception as e:
        print(f"[!] Error handling new connection {conn_id}: {e}")
        sio.emit("close_connection", {'conn_id': conn_id})

@sio.on("stream_data")
def on_stream_data(data):
    conn_id = data.get('conn_id')
    stream_data = data.get('data', '')
    
    try:
        if isinstance(stream_data, str):
            stream_data = base64.b64decode(stream_data)
        
        with local_connections_lock:
            if conn_id in active_local_connections and active_local_connections[conn_id]['active']:
                local_socket = active_local_connections[conn_id]['socket']
                local_socket.sendall(stream_data)
            else:
                print(f"[!] Connection {conn_id} not found or inactive")
    except Exception as e:
        print(f"[!] Error forwarding stream data: {e}")
        sio.emit("close_connection", {'conn_id': conn_id})

@sio.on("close_connection")
def on_close_connection(data):
    conn_id = data.get('conn_id')
    
    with local_connections_lock:
        if conn_id in active_local_connections:
            active_local_connections[conn_id]['active'] = False
            try:
                active_local_connections[conn_id]['socket'].close()
            except:
                pass
            del active_local_connections[conn_id]
            print(f"[-] Connection {conn_id} closed")

@sio.on("udp_packet")
def on_udp_packet(data):
    session_id = data.get('session_id')
    packet_data = data.get('data', '')
    
    try:
        if isinstance(packet_data, str):
            packet_data = base64.b64decode(packet_data)
        
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(5)
        
        udp_socket.sendto(packet_data, ('127.0.0.1', local_port))
        
        def wait_for_response():
            try:
                response, _ = udp_socket.recvfrom(65535)
                response_b64 = base64.b64encode(response).decode('ascii')
                sio.emit("udp_response", {
                    'session_id': session_id,
                    'data': response_b64
                })
            except socket.timeout:
                pass
            except Exception as e:
                print(f"[!] UDP response error: {e}")
            finally:
                udp_socket.close()
        
        response_thread = threading.Thread(target=wait_for_response, daemon=True)
        response_thread.start()
        
    except Exception as e:
        print(f"[!] Error handling UDP packet: {e}")

@sio.on("disconnect")
def on_disconnect():
    global heartbeat_running
    heartbeat_running = False
    
    with local_connections_lock:
        for conn_id in list(active_local_connections.keys()):
            try:
                active_local_connections[conn_id]['socket'].close()
            except:
                pass
        active_local_connections.clear()
    
    print("[-] Disconnected from tunnel server")

try:
    print("[*] Starting tunnel client...")
    print(f"[*] Server: {server_url}")
    print(f"[*] Tunnel ID: {tunnel_id}")
    print(f"[*] Local Port: {local_port}")
    print("[*] Connecting...\n")
    sio.connect(server_url, transports=['websocket', 'polling'])
    sio.wait()
except KeyboardInterrupt:
    print("\n[*] Shutting down...")
    heartbeat_running = False
    
    with local_connections_lock:
        for conn_id in list(active_local_connections.keys()):
            try:
                active_local_connections[conn_id]['socket'].close()
            except:
                pass
        active_local_connections.clear()
    
    sio.disconnect()
except Exception as e:
    print(f"\n[!] Connection error: {e}")
    print("[!] Make sure the server is reachable and try again.")
    import traceback
    traceback.print_exc()
    sys.exit(1)
