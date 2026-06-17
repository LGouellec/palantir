# Alpaca news fetcher
# Build context: fetchers/alpaca
# Multi-stage build for a smaller final image.

# Stage 1: Builder
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*
COPY worker/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
LABEL maintainer="Palantir Trading Engine"
LABEL description="Alpaca WebSocket -> Kafka real-time news fetcher"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

RUN useradd -m -u 1000 -s /bin/bash appuser
WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser worker/ /app/
RUN chmod +x /app/entrypoint.sh

USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH

# Defaults (overridden by the Deployment / ConfigMap in Kubernetes).
ENV NEWS_SYMBOLS=* \
    NEWS_TOPIC=news.realtime \
    INCLUDE_CONTENT=true \
    KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
    ALPACA_CREDENTIALS_FILE=/secrets/credentials.json

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import config, alpaca_client, kafka_publisher" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
