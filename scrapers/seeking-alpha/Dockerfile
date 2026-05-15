FROM python:3.11-slim

# Install system dependencies including Playwright browser dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    wget \
    gnupg \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY seeking-alpha/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and browsers for stealth mode
RUN pip install playwright && \
    playwright install chromium && \
    playwright install-deps chromium

# Copy common utilities (shared across scrapers)
COPY common/ /app/common/

# Copy scraper files
COPY seeking-alpha/seeking_scraper_base.py .
COPY seeking-alpha/seeking_scraper.py .
COPY seeking-alpha/seeking_scraper_stealth.py .
COPY seeking-alpha/kafka_config.py .

# Verify all required files are present
RUN ls -la /app/ && \
    test -f /app/seeking_scraper_base.py || (echo "ERROR: seeking_scraper_base.py not found" && exit 1) && \
    test -f /app/seeking_scraper.py || (echo "ERROR: seeking_scraper.py not found" && exit 1) && \
    test -f /app/seeking_scraper_stealth.py || (echo "ERROR: seeking_scraper_stealth.py not found" && exit 1) && \
    test -f /app/kafka_config.py || (echo "ERROR: kafka_config.py not found" && exit 1) && \
    test -d /app/common || (echo "ERROR: common directory not found" && exit 1) && \
    test -d /app/common/mouvement || (echo "ERROR: common/mouvement directory not found" && exit 1) && \
    echo "✓ All required files verified"

# Create output directory
RUN mkdir -p /data/articles /app/history

# Copy entrypoint script
COPY seeking-alpha/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Environment variables with defaults
ENV CATEGORY=market-news::all
ENV LIMIT=100
ENV DELAY=2.0
ENV CONTINUOUS=false
ENV CONTINUOUS_INTERVAL=300
ENV KAFKA_ENABLED=false
ENV KAFKA_TOPIC=seeking-news

# Stealth mode and login configuration
ENV STEALTH_MODE=false
ENV HEADLESS=true
ENV SEEKING_ALPHA_EMAIL=""
ENV SEEKING_ALPHA_PASSWORD=""
ENV HISTORY_TTL_DAYS=30

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
