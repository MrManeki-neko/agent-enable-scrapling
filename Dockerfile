FROM python:3.10-slim

# Minimal system dependencies — curl for the health check only.
# Playwright / Chromium are NOT installed because the service uses
# Scrapling's HTTP-only FetcherSession, which needs no browser binary.
# Removing the browser installation saves ~400 MB and cuts cold-start
# time significantly.
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd --create-home --shell /bin/bash app
ENV HOME=/home/app

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

RUN chown -R app:app /app
USER app

# Production server: gunicorn with gthread workers (see gunicorn.conf.py).
# PORT env var is set automatically by Railway.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
