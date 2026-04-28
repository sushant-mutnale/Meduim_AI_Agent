FROM python:3.11-slim

WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (useful for playwright/other automation tasks)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright system dependencies and Chromium
RUN playwright install-deps chromium && \
    playwright install chromium

# Copy application code
COPY ./app /code/app
RUN mkdir -p /code/assets

# The command is overridden in docker-compose.yml 
# for API, celery_worker, and celery_beat
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
