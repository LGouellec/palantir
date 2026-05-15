FROM python:3.11-slim

# Install system dependencies (including procps for process management)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Scrapling browser components
RUN scrapling install

# Copy scraper files
COPY investing_scraper_base.py .
COPY investing_scraper_stealth.py .
COPY kafka_config.py .

# Create directories
RUN mkdir -p /app/news /app/history /app/chrome_investing

# Copy entrypoint script
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Environment variables with defaults
ENV CATEGORY=latest-news
ENV ANALYSIS=false
ENV KAFKA_ENABLED=false
ENV KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ENV KAFKA_TOPIC=investing-articles
ENV HEADLESS=true
ENV LIMIT=20
ENV DELAY=2.0
ENV CONTINUOUS_INTERVAL=300

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default command: run in continuous mode
# CMD ["python", "investing_scraper_stealth.py", "--continuous", "--continuous-interval", "300"]
