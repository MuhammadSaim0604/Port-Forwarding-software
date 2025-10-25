from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import secrets

Base = declarative_base()

class Tunnel(Base):
    __tablename__ = 'tunnels'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    token = Column(String(64), unique=True, nullable=False)
    local_port = Column(Integer, nullable=False)
    public_port = Column(Integer, unique=True, nullable=True)
    protocol = Column(String(10), default='TCP')
    status = Column(String(20), default='inactive')
    verification_code = Column(String(32), unique=True, nullable=True)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_connected = Column(DateTime, nullable=True)
    
    def __init__(self, name, local_port, protocol='TCP'):
        self.name = name
        self.local_port = local_port
        self.protocol = protocol
        self.token = secrets.token_hex(32)
        self.verification_code = secrets.token_hex(16)

class TunnelSession(Base):
    __tablename__ = 'tunnel_sessions'
    
    id = Column(Integer, primary_key=True)
    tunnel_id = Column(Integer, nullable=False)
    client_id = Column(String(100), nullable=False)
    connected_at = Column(DateTime, default=datetime.utcnow)
    disconnected_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

engine = create_engine('sqlite:///tunnels.db', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()
