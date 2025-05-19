import multiprocessing
import os

# Gunicorn configuration file for Render deployment
bind = "0.0.0.0:10000"
backlog = 2048

# Worker processes - reduced for better stability
workers = 2  # Reduced from CPU count to prevent resource exhaustion
worker_class = "eventlet"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "chicfocus"

# SSL
keyfile = None
certfile = None

# WebSocket specific settings
worker_connections = 1000
timeout = 300
keepalive = 120
threads = 2
max_requests = 5000  # Increased to reduce worker restarts
max_requests_jitter = 100
preload_app = True
forwarded_allow_ips = '*'
proxy_allow_ips = '*'
graceful_timeout = 120
websockets_ping_interval = 30  # Reduced ping frequency
websockets_ping_timeout = 300  # Increased timeout 