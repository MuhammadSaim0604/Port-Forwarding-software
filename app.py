from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from models import get_session, Tunnel, TunnelSession
from proxy_server import get_proxy_instance
from datetime import datetime
import os
import random
import io
import threading
from proxy_server import close_connection
import socket
    
app = Flask(__name__)
app.config['SECRET_KEY'] = 'tunnel-management-secret-key-change-in-production'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=120, ping_interval=25)

connected_tunnels = {}
traffic_proxy = None

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/tunnels', methods=['GET'])
def get_tunnels():
    session = get_session()
    try:
        domain = os.getenv('REPLIT_DEV_DOMAIN', 'localhost')
        public_ip = domain.split('.')[0] if 'replit' in domain else 'localhost'
        
        tunnels = session.query(Tunnel).all()
        result = []
        for tunnel in tunnels:
            result.append({
                'id': tunnel.id,
                'name': tunnel.name,
                'local_port': tunnel.local_port,
                'public_port': tunnel.public_port,
                'protocol': getattr(tunnel, 'protocol', 'TCP'),
                'public_ip': domain,
                'status': tunnel.status,
                'verified': tunnel.verified,
                'created_at': tunnel.created_at.isoformat() if tunnel.created_at else None,
                'last_connected': tunnel.last_connected.isoformat() if tunnel.last_connected else None,
                'verification_url': f"/verify/{tunnel.verification_code}" if not tunnel.verified else None
            })
        return jsonify(result)
    finally:
        session.close()

@app.route('/api/tunnels', methods=['POST'])
def create_tunnel():
    session = get_session()
    try:
        data = request.json
        name = data.get('name')
        local_port = data.get('local_port')
        protocol = data.get('protocol', 'TCP')
        
        if not name or not local_port:
            return jsonify({'error': 'Name and local_port are required'}), 400
        
        if protocol not in ['TCP', 'UDP', 'BOTH']:
            return jsonify({'error': 'Protocol must be TCP, UDP, or BOTH'}), 400
        
        public_port = random.randint(10000, 60000)
        while session.query(Tunnel).filter_by(public_port=public_port).first():
            public_port = random.randint(10000, 60000)
        
        tunnel = Tunnel(name=name, local_port=local_port, protocol=protocol)
        tunnel.public_port = public_port
        session.add(tunnel)
        session.commit()
        
        return jsonify({
            'id': tunnel.id,
            'name': tunnel.name,
            'token': tunnel.token,
            'local_port': tunnel.local_port,
            'public_port': tunnel.public_port,
            'protocol': tunnel.protocol,
            'verification_code': tunnel.verification_code,
            'verification_url': f"/verify/{tunnel.verification_code}"
        }), 201
    finally:
        session.close()

@app.route('/api/tunnels/<int:tunnel_id>', methods=['DELETE'])
def delete_tunnel(tunnel_id):
    session = get_session()
    try:
        tunnel = session.query(Tunnel).filter_by(id=tunnel_id).first()
        if not tunnel:
            return jsonify({'error': 'Tunnel not found'}), 404
        
        if tunnel_id in connected_tunnels:
            del connected_tunnels[tunnel_id]
        
        session.delete(tunnel)
        session.commit()
        return jsonify({'message': 'Tunnel deleted successfully'})
    finally:
        session.close()

@app.route('/client/<int:tunnel_id>')
def download_client(tunnel_id):
    session = get_session()
    try:
        tunnel = session.query(Tunnel).filter_by(id=tunnel_id).first()
        if not tunnel:
            return jsonify({'error': 'Tunnel not found'}), 404
        
        with open('simple_client.py', 'r') as f:
            client_code = f.read()
        
        return send_file(
            io.BytesIO(client_code.encode('utf-8')),
            mimetype='text/x-python',
            as_attachment=True,
            download_name=f'tunnel_client_{tunnel.id}.py'
        )
    finally:
        session.close()

@app.route('/download/<int:tunnel_id>')
def download_bat(tunnel_id):
    session = get_session()
    try:
        tunnel = session.query(Tunnel).filter_by(id=tunnel_id).first()
        if not tunnel:
            return jsonify({'error': 'Tunnel not found'}), 404
        
        env_domain = os.getenv('REPLIT_DEV_DOMAIN')
        if env_domain:
            domain = env_domain
        else:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                local_ip = '127.0.0.1'
                
            domain = f"{local_ip}:5000"
        server_url = f"https://{domain}" if 'replit' in domain.lower() else f"http://{domain}"
        
        verification_msg = ""
        if not tunnel.verified:
            verification_msg = f"""echo.
echo ========================================
echo IMPORTANT: First-time setup required!
echo ========================================
echo Please verify your tunnel by opening this URL in your browser:
echo {server_url}/verify/{tunnel.verification_code}
echo.
echo After verification, run this file again to connect.
echo ========================================
pause
exit /b 0
"""
        
        bat_content = f"""@echo off
title Tunnel Client - {tunnel.name}
echo ========================================
echo Tunnel Client for {tunnel.name}
echo ========================================
echo.
echo Server: {server_url}
echo Local Port: {tunnel.local_port}
echo Public Port: {tunnel.public_port}
echo.
{verification_msg}
echo Installing Python packages...
pip install --quiet python-socketio requests websocket-client >nul 2>&1

if errorlevel 1 (
    echo [ERROR] Python is not installed or pip failed
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Downloading client script...
curl -s -o tunnel_client.py {server_url}/client/{tunnel.id}

if not exist tunnel_client.py (
    echo [ERROR] Failed to download client
    pause
    exit /b 1
)

echo Starting tunnel...
echo.
python tunnel_client.py {server_url} {tunnel.token} {tunnel.id} {tunnel.local_port}

pause
"""
        
        file_obj = io.BytesIO(bat_content.encode('utf-8'))
        file_obj.seek(0)
        
        return send_file(
            file_obj,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f'tunnel_{tunnel.name}_{tunnel.id}.bat'
        )
    finally:
        session.close()

@app.route('/verify/<verification_code>')
def verify_tunnel(verification_code):
    session = get_session()
    try:
        tunnel = session.query(Tunnel).filter_by(verification_code=verification_code).first()
        if not tunnel:
            return render_template('verify.html', success=False, message='Invalid verification code')
        
        if tunnel.verified:
            return render_template('verify.html', success=True, message='Tunnel already verified', tunnel=tunnel)
        
        tunnel.verified = True
        session.commit()
        
        return render_template('verify.html', success=True, message='Tunnel verified successfully!', tunnel=tunnel)
    finally:
        session.close()

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    emit('connected', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    global traffic_proxy
    print(f'Client disconnected: {request.sid}')
    for tunnel_id, data in list(connected_tunnels.items()):
        if data.get('sid') == request.sid:
            session = get_session()
            try:
                tunnel = session.query(Tunnel).filter_by(id=tunnel_id).first()
                if tunnel:
                    tunnel.status = 'inactive'
                    session.commit()
                    
                    if traffic_proxy:
                        traffic_proxy.stop_proxy_for_tunnel(tunnel_id, tunnel.public_port)
            finally:
                session.close()
            del connected_tunnels[tunnel_id]
            break

@socketio.on('tunnel_auth')
def handle_tunnel_auth(data):
    global traffic_proxy
    token = data.get('token')
    tunnel_id = data.get('tunnel_id')
    local_port = data.get('local_port')
    
    session = get_session()
    try:
        tunnel = session.query(Tunnel).filter_by(id=tunnel_id, token=token).first()
        
        if not tunnel:
            emit('auth_response', {'success': False, 'error': 'Invalid tunnel credentials'})
            return
        
        if not tunnel.verified:
            emit('auth_response', {
                'success': False, 
                'error': 'Tunnel not verified',
                'verification_url': f'/verify/{tunnel.verification_code}'
            })
            return
        
        tunnel.status = 'active'
        tunnel.last_connected = datetime.utcnow()
        session.commit()
        
        connected_tunnels[tunnel_id] = {
            'sid': request.sid,
            'local_port': local_port,
            'public_port': tunnel.public_port,
            'tunnel': tunnel
        }
        
        tunnel_session = TunnelSession(
            tunnel_id=tunnel_id,
            client_id=request.sid
        )
        session.add(tunnel_session)
        session.commit()
        
        if traffic_proxy is None:
            traffic_proxy = get_proxy_instance(socketio, connected_tunnels)
        
        protocol = getattr(tunnel, 'protocol', 'TCP')
        traffic_proxy.start_proxy_for_tunnel(tunnel_id, tunnel.public_port, protocol)
        
        emit('auth_response', {
            'success': True,
            'public_port': tunnel.public_port,
            'protocol': protocol,
            'message': f'Tunnel active! {protocol} traffic on port {tunnel.public_port} will forward to your local port {local_port}'
        })
        
        print(f'Tunnel {tunnel.name} (ID: {tunnel_id}) connected. Public port: {tunnel.public_port} -> Local port: {local_port}')
        
    finally:
        session.close()

@socketio.on('stream_response')
def handle_stream_response(data):
    from proxy_server import handle_stream_response as proxy_handle_stream_response
    conn_id = data.get('conn_id')
    response_data = data.get('data')
    
    if conn_id and response_data:
        proxy_handle_stream_response(conn_id, response_data)

@socketio.on('udp_response')
def handle_udp_response(data):
    from proxy_server import handle_udp_response as proxy_handle_udp_response
    session_id = data.get('session_id')
    response_data = data.get('data')
    
    if session_id and response_data:
        proxy_handle_udp_response(session_id, response_data)

@socketio.on('close_connection')
def handle_close_connection_from_client(data):

    conn_id = data.get('conn_id')
    
    if conn_id:
        close_connection(conn_id)
        print(f'[*] Client closed connection {conn_id}')

if __name__ == '__main__':
    # ensure folders exist when running in container
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    # Use PORT from environment (Render provides $PORT). Default to 5000 for local dev.
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('1', 'true', 'yes')

    socketio.run(app, host='0.0.0.0', port=port, debug=debug)
