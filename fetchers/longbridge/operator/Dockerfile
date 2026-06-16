# Longbridge Kubernetes operator + daily ticker refresh job
# Build context: fetchers/longbridge
FROM python:3.11-slim

LABEL maintainer="Palantir Trading Engine"
LABEL description="Kopf operator that shards US tickers across Longbridge workers"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

RUN useradd -m -u 1000 -s /bin/bash appuser
WORKDIR /app

COPY operator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser operator/ /app/

USER appuser

# Default: run the operator. The CronJob overrides the command to run the
# refresh job:  ["python", "refresh.py"]
ENTRYPOINT ["kopf", "run", "--standalone", "--all-namespaces", "/app/shard_operator.py"]
