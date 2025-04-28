"""
Gunicorn configuration file with increased limits for large file uploads.
"""
import multiprocessing

# Server socket configuration
bind = "0.0.0.0:5000"
backlog = 2048

# Server process configuration
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 300  # 5 minutes timeout for long uploads
keepalive = 2

# Process naming
proc_name = 'pokemon-ocr'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = '/tmp'

# Logging
loglevel = 'info'
accesslog = '-'
errorlog = '-'

# Process management
preload_app = True
reload = True

# SSL configuration
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'

# HTTP settings
limit_request_line = 4094
limit_request_fields = 1000  # Increased number of allowed form fields
limit_request_field_size = 100 * 1024 * 1024  # 100MB for field size