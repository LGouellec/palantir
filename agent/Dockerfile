# Trading agent
# Build context: agent
# Multi-stage build for a smaller final image.

# Stage 1: Builder
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
LABEL maintainer="Palantir Trading Engine"
LABEL description="stock_quotes.trade_signal -> Alpaca order execution"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

RUN useradd -m -u 1000 -s /bin/bash appuser
WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
# Only the runtime files - not the Dockerfile/README/Makefile/docker-compose.yml/spec.md
# that also live at this level now that the agent isn't nested under worker/.
COPY --chown=appuser:appuser *.py entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH

# Defaults (overridden by the Deployment / ConfigMap in Kubernetes).
ENV TRADE_SIGNAL_TOPIC=stock_quotes.trade_signal \
    CONSUMER_GROUP_ID=trading-agent \
    KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
    TRADING_LIVE=false \
    DRY_RUN=false \
    ALPACA_CREDENTIALS_FILE=/secrets/credentials.json

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import config, credentials, trade_signal, risk, rules, alpaca_trading, kafka_consumer" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
