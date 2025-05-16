import multiprocessing
import os

# Gunicorn configuration file for Render deployment
bind = "0.0.0.0:" + os.environ.get("PORT", "5000")
workers = 1  # For WebSockets, one worker is better
worker_class = "eventlet"  # Use eventlet worker for WebSocket support
timeout = 300  # Longer timeout for WebSocket connections
keepalive = 65
threads = 3
worker_connections = 1000
preload_app = True
forwarded_allow_ips = '*'
proxy_allow_ips = '*'
graceful_timeout = 60 