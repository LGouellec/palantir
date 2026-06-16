# Longbridge shard worker
# Build context: fetchers/longbridge
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
LABEL description="Longbridge WebSocket -> Kafka real-time quote shard worker"

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

# Defaults (overridden by the StatefulSet / ConfigMap in Kubernetes).
ENV SHARD_COUNT=1 \
    MAX_PER_SHARD=500 \
    SYMBOLS_PATH=/config/us-equities.json \
    SUBSCRIBE_QUOTE=true \
    SUBSCRIBE_DEPTH=true \
    QUOTE_TOPIC=quotes.realtime \
    DEPTH_TOPIC=quotes.depth \
    KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
    LONGPORT_CREDENTIALS_DIR=/secrets

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import config, longbridge_client, kafka_publisher" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
