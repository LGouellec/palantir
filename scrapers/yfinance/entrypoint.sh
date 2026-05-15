#!/bin/bash
set -e

# If arguments provided, execute them directly
if [ "$#" -gt 0 ]; then
    exec python "$@"
fi

# Build command from environment variables
CMD="python runner.py"

# Kafka configuration
if [ "${KAFKA_ENABLED}" = "true" ]; then
    CMD="$CMD --kafka"
fi

# Batch size
if [ -n "${BATCH_SIZE}" ]; then
    CMD="$CMD --batch-size ${BATCH_SIZE}"
fi

# Interval in milliseconds
if [ -n "${INTERVAL_MS}" ]; then
    CMD="$CMD --interval-ms ${INTERVAL_MS}"
fi

# News configuration
if [ "${INCLUDE_NEWS}" = "false" ]; then
    CMD="$CMD --no-news"
fi

if [ -n "${NEWS_DAYS}" ]; then
    CMD="$CMD --news-days ${NEWS_DAYS}"
fi

# Sentiment analysis
if [ "${ANALYZE_SENTIMENT}" = "false" ]; then
    CMD="$CMD --no-sentiment"
fi

if [ -n "${SENTIMENT_ANALYZER}" ]; then
    CMD="$CMD --sentiment-analyzer ${SENTIMENT_ANALYZER}"
fi

echo "Starting YFinance Analytics Engine with command: $CMD"
exec $CMD
