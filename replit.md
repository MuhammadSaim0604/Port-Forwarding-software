# Tunnel Management System

## Overview
A Python-based web application for managing secure tunnels that enable port forwarding from Windows machines to public endpoints. This system provides a dashboard for creating and managing tunnels, generating Windows client files, and forwarding traffic through established connections.

## Purpose
This software enables users to:
- Create and manage tunnels through a web dashboard
- Download .bat files for Windows clients
- Establish secure connections between Windows machines and the server
- Forward traffic from public IP/port to Windows machine's local ports

## Project Architecture

### Core Components
1. **Web Dashboard** (`app.py`) - Flask-based web interface
   - Create/manage tunnels
   - View tunnel status
   - Download Windows client files
   - Verification system

2. **Database Layer** (`models.py`) - SQLAlchemy ORM
   - Tunnel configurations
   - Session management
   - SQLite database

3. **Tunnel Client** (`tunnel_client.py`) - Windows client
   - Python-based client
   - WebSocket connection to server
   - Traffic forwarding capabilities

### Features
- **Tunnel Creation**: Web-based tunnel creation with automatic port allocation
- **Verification System**: URL-based verification before tunnel activation
- **.bat File Generation**: Automatic Windows batch file generation
- **Real-time Status**: Live tunnel status monitoring via WebSocket
- **Traffic Forwarding**: Public traffic forwarding to local Windows ports

## Technology Stack
- **Backend**: Python 3.11, Flask, Flask-SocketIO
- **Database**: SQLite with SQLAlchemy ORM
- **Real-time Communication**: WebSocket (Socket.IO)
- **Frontend**: HTML, CSS, JavaScript

## File Structure
```
.
├── app.py                 # Main Flask application
├── models.py              # Database models
├── tunnel_client.py       # Python tunnel client
├── templates/
│   ├── dashboard.html     # Main dashboard UI
│   └── verify.html        # Verification page
├── tunnels.db             # SQLite database (auto-generated)
└── replit.md              # This file
```

## How It Works

### Workflow
1. User creates a tunnel in the web dashboard
2. System assigns a public port and generates verification code
3. User downloads the .bat file for their Windows machine
4. User opens verification URL to activate the tunnel
5. User runs the .bat file on Windows (downloads Python client and connects)
6. Client connects to server via WebSocket
7. After authentication, tunnel becomes active and proxy starts
8. HTTP traffic sent to public IP:port is forwarded to Windows machine's local port

### Current Capabilities
- **Raw TCP/UDP Forwarding**: Full support for ANY protocol (HTTP, HTTPS, SSH, FTP, DNS, Gaming, VoIP, custom)
- **Binary Data Support**: Handles binary data without corruption using base64 encoding
- **Large Payloads**: Supports files and data >10MB
- **Multiple Simultaneous Connections**: Each tunnel can handle multiple concurrent connections
- **Protocol Flexibility**: Support TCP-only, UDP-only, or BOTH protocols on same tunnel
- **Request/Response Model**: Each request gets a unique ID and response is matched back
- **Verification System**: Ensures only verified tunnels can be activated
- **Multi-Tunnel Support**: Multiple tunnels can run simultaneously on different ports
- **Cross-Platform**: Server runs on Windows and Linux

### Technical Details
- **Server Async Mode**: Threading (compatible with Python 3.11-3.12)
- **Data Encoding**: Base64 for binary safety over WebSocket
- **Timeouts**: TCP 60s, UDP 30s configurable
- **Port Range**: 10000-60000 for public ports
- **Max Payload**: 10MB per request (configurable)
- **Heartbeat**: 30s intervals to maintain connection

### Security
- Token-based authentication
- Verification requirement before activation
- Session tracking
- Secure WebSocket connections

## Database Schema

### Tunnels Table
- `id`: Primary key
- `name`: Tunnel name
- `token`: Authentication token (64-char hex)
- `local_port`: Port on Windows machine
- `public_port`: Assigned public port
- `status`: Current status (active/inactive)
- `verification_code`: Unique verification code
- `verified`: Boolean verification status
- `created_at`: Creation timestamp
- `last_connected`: Last connection timestamp

### Tunnel Sessions Table
- `id`: Primary key
- `tunnel_id`: Foreign key to tunnels
- `client_id`: Socket.IO session ID
- `connected_at`: Connection timestamp
- `disconnected_at`: Disconnection timestamp
- `is_active`: Boolean active status

## API Endpoints

### Web Routes
- `GET /` - Dashboard homepage
- `GET /verify/<code>` - Tunnel verification
- `GET /download/<id>` - Download .bat file

### REST API
- `GET /api/tunnels` - List all tunnels
- `POST /api/tunnels` - Create new tunnel
- `DELETE /api/tunnels/<id>` - Delete tunnel

### WebSocket Events
- `connect` - Client connection
- `disconnect` - Client disconnection
- `tunnel_auth` - Tunnel authentication
- `forward_traffic` - Traffic forwarding
- `auth_response` - Authentication response
- `traffic_data` - Forwarded traffic data

## Development Notes

### Dependencies
- Flask: Web framework
- Flask-SocketIO: WebSocket support (threading mode)
- Flask-CORS: Cross-origin resource sharing
- SQLAlchemy: ORM and database management
- python-socketio: Socket.IO client library
- simple-websocket: WebSocket backend for threading mode
- requests: HTTP client library (client-side only)

### Configuration
- Default port: 5000
- Database: SQLite (tunnels.db)
- Public port range: 10000-60000

## Recent Changes
- October 25, 2025: Major Overhaul - Production-Ready Raw Traffic Support
  - **COMPLETE REWRITE**: Changed from HTTP-only to full raw TCP/UDP support
  - **Cross-Platform Server**: Works on both Windows and Linux (threading mode, no eventlet)
  - **Binary Data Handling**: Base64 encoding for WebSocket transmission, supports large payloads (>10MB)
  - **Protocol Support**: TCP, UDP, and BOTH (simultaneous TCP+UDP on same port)
  - **Raw Socket Client**: Replaced HTTP requests with raw socket connections
  - **Traffic Types Supported**: HTTP, HTTPS, SSH, FTP, DNS, Gaming, VoIP, custom protocols
  - **Improved Stability**: Added heartbeat, reconnection logic, proper timeout handling
  - **Enhanced UI**: Protocol selection dropdown in dashboard
  - **Threading Mode**: Compatible with Python 3.11-3.12 on Windows and Linux
  - **Removed Dependencies**: Removed eventlet (incompatible with Python 3.12)

- October 25, 2025: Initial project creation
  - Implemented complete tunnel management system
  - Created web dashboard with real-time updates
  - Built Windows client generation system
  - Added verification workflow
  - Configured WebSocket communication

## User Preferences
- Language: English
- Server Platform: Windows and Linux (cross-platform)
- Client Platform: Windows with Python 3.11+ installed
- Use Case: Port forwarding and tunnel management for ALL traffic types (TCP/UDP/HTTP/HTTPS/etc.)
