# Dockerfile for YFinance Analytics Engine
# Multi-stage build for smaller final image

# Stage 1: Builder
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY yfinance/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Install optional dependencies
RUN pip install --no-cache-dir --user \
    confluent-kafka \
    openai

# Stage 2: Runtime
FROM python:3.11-slim

# Set metadata
LABEL maintainer="YFinance Analytics Engine"
LABEL description="Async analytics engine for Yahoo Finance stock data with real-time monitoring"
LABEL version="1.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser yfinance/ /app/
COPY --chown=appuser:appuser common/ /app/common/

# Copy entrypoint script
COPY yfinance/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Create required directories
RUN mkdir -p /app/.nasdaq_cache && \
    chown -R appuser:appuser /app/.nasdaq_cache

# Switch to non-root user
USER appuser

# Add local binaries to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Environment variables with defaults
ENV KAFKA_ENABLED=false \
    KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
    KAFKA_TOPIC=stock-updates \
    BATCH_SIZE=50 \
    INTERVAL_MS=30000 \
    INCLUDE_NEWS=true \
    ANALYZE_SENTIMENT=true \
    NEWS_DAYS=20 \
    SENTIMENT_ANALYZER=keyword \
    COOLDOWN_PERIOD=60

# Expose port (if needed for future HTTP endpoints)
# EXPOSE 8000

# Health check (checks if the app can import successfully)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from analytics_engine import AsyncAnalyticsEngine" || exit 1

# Use entrypoint script
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default command: run with environment-based configuration
CMD []
