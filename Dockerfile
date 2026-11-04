# Use official Playwright Python image with Chromium pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (chromium)
RUN playwright install chromium

# Copy application source
COPY . .

# Install package in editable mode
RUN pip install -e .

# Create volume mounts for persistent data & exports
VOLUME ["/app/data", "/app/exports"]

# Default entrypoint to the harvest CLI
ENTRYPOINT ["harvest"]
CMD ["stats"]
