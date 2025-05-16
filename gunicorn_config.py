import multiprocessing
import os

# Gunicorn configuration file for Render deployment
bind = "0.0.0.0:" + os.environ.get("PORT", "5000")
workers = 1  # For WebSockets, one worker is better
worker_class = "eventlet"  # Use eventlet worker for WebSocket support
timeout = 120  # Longer timeout for WebSocket connections
keepalive = 5
threads = 3
preload_app = True
forwarded_allow_ips = '*'
proxy_allow_ips = '*' 