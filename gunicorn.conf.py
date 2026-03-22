# gunicorn.conf.py — production server configuration
#
# Run with: gunicorn --config gunicorn.conf.py wsgi:app
#
# Worker model: 2 processes × 4 threads = 8 concurrent requests.
# Threads are ideal for this I/O-bound scraping workload because threads
# share memory and don't duplicate the in-process Fetcher instance.
# Processes would duplicate all memory without adding throughput here.

import os

bind = f"0.0.0.0:{os.environ.get('PORT', 8000)}"
workers = 2
threads = 4
worker_class = "gthread"
timeout = 120          # seconds — generous for multi-page crawls
graceful_timeout = 30
keepalive = 5
accesslog = "-"        # stdout
errorlog = "-"         # stdout
loglevel = "info"
