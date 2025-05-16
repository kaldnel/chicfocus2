import multiprocessing
import os

# Gunicorn configuration file for Render deployment
bind = "0.0.0.0:" + os.environ.get("PORT", "5000")
workers = 1  # For WebSockets, one worker is better
worker_class = "eventlet"  # Use eventlet worker for WebSocket support
worker_connections = 1000
timeout = 300  # Longer timeout for WebSocket connections
keepalive = 120
threads = 3
max_requests = 1000  # Restart workers to avoid memory leaks
max_requests_jitter = 50  # Add jitter to prevent all workers restarting at once
preload_app = True
forwarded_allow_ips = '*'
proxy_allow_ips = '*'
graceful_timeout = 60
websockets_ping_interval = 5  # More frequent pings
websockets_ping_timeout = 180  # Longer timeout 