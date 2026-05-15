FROM python:3.11-slim
#FROM pyd4vinci/scrapling:latest

# Install system dependencies
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
COPY wsj/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# Install Scrapling browser components
RUN scrapling install
# Install optional dependencies
RUN pip install --no-cache-dir confluent-kafka # For Kafka integration

# Copy common utilities (shared across scrapers)
COPY common/ /app/common/

# Copy scraper files
COPY wsj/wsj_scraper.py .
COPY wsj/wsj_scraper_distributed.py .
COPY wsj/kafka_config.py .
COPY wsj/stt/audio_transcriber.py stt/audio_transcriber.py

# Create output directory
RUN mkdir -p /data/articles /app/history /app/data/images /app/chrome

# Copy entrypoint script
COPY wsj/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Environment variables with defaults

# Distributed scraping options
ENV POD_INDEX=0
ENV TOTAL_PODS=1
ENV DISTRIBUTION=modulo
ENV KAFKA_URLS_TOPIC=wsj-urls
ENV KAFKA_URLS_GROUP=wsj-scraper-workers
ENV COORDINATOR_POD=0

# Standard scraper options
ENV BASE_URL=https://www.wsj.com
ENV LIMIT=20
ENV DELAY=2.0
ENV OUTPUT_DIR=/data/articles
ENV FORMAT=both
ENV VERBOSE=false
ENV FORCE=false
ENV SAVE_LOCAL=false
ENV NO_PAGINATION=false
ENV NO_AUTO_DISCOVERY=false
ENV HEADLESS=true

# Kafka publishing options (for scraped articles)
ENV KAFKA_ENABLED=false
ENV KAFKA_TOPIC=wsj-articles
ENV KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ENV KAFKA_CONFIG_FILE=kafka_config.properties

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
