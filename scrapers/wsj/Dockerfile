FROM python:3.11-slim
#FROM pyd4vinci/scrapling:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Scrapling browser components
RUN scrapling install

# Install optional dependencies
RUN pip install --no-cache-dir redis           # For distributed mode
RUN pip install --no-cache-dir confluent-kafka # For Kafka integration

# Copy scraper files
COPY wsj_scraper.py .
COPY wsj_scraper_distributed.py .
COPY kafka_config.py .

# Create output directory
RUN mkdir -p /data/articles /app/history

# Environment variables with defaults
ENV POD_INDEX=0
ENV TOTAL_PODS=1
ENV DISTRIBUTION=modulo
ENV BASE_URL=https://www.wsj.com
ENV LIMIT=20
ENV DELAY=2.0
ENV HEADLESS=true


ENTRYPOINT ["python"]

# Default command (can be overridden)
CMD ["wsj_scraper_distributed.py"]
