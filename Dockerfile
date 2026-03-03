FROM python:3.10-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Scrapling browsers and Playwright browsers (MUST run as root)
# Cache bust: 2026-03-03-17:10
RUN scrapling install && \
    playwright install chromium && \
    playwright install-deps chromium

# Copy Playwright browsers to be accessible by non-root user
RUN mkdir -p /home/app/.cache && \
    cp -r /root/.cache/ms-playwright /home/app/.cache/ && \
    chown -R app:app /home/app/.cache

# Set HOME environment variable for the app user
ENV HOME=/home/app

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Start the application
CMD ["python", "scrapling-service.py"]
