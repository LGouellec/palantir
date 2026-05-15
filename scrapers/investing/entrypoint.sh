#!/bin/bash
set -e

# If arguments provided, execute them directly
if [ "$#" -gt 0 ]; then
    exec python "$@"
fi

# Build command from environment variables
CMD="python investing_scraper_stealth.py"

# Required args
CMD="$CMD --category ${CATEGORY}"
CMD="$CMD --limit ${LIMIT}"
CMD="$CMD --delay ${DELAY}"

# Analysis mode
if [ "${ANALYSIS}" = "true" ]; then
    CMD="$CMD --analysis"
fi

# Continuous mode
if [ "${CONTINUOUS}" = "true" ]; then
    CMD="$CMD --continuous"
    CMD="$CMD --continuous-interval ${CONTINUOUS_INTERVAL}"
fi

# Kafka configuration
if [ "${KAFKA_ENABLED}" = "true" ]; then
    CMD="$CMD --kafka"
    CMD="$CMD --kafka-topic ${KAFKA_TOPIC}"

    if [ -n "${KAFKA_BOOTSTRAP_SERVERS}" ]; then
        CMD="$CMD --kafka-bootstrap-servers ${KAFKA_BOOTSTRAP_SERVERS}"
    fi

    if [ -n "${KAFKA_CONFIG_FILE}" ] && [ -f "${KAFKA_CONFIG_FILE}" ]; then
        CMD="$CMD --kafka-config ${KAFKA_CONFIG_FILE}"
    fi
fi

# Optional args
if [ "${VERBOSE}" = "true" ]; then
    CMD="$CMD --verbose"
fi

if [ "${FORCE}" = "true" ]; then
    CMD="$CMD --force"
fi

if [ "${SAVE_LOCAL}" = "true" ]; then
    CMD="$CMD --save-local"
fi

if [ -n "${OUTPUT_DIR}" ]; then
    CMD="$CMD --output-dir ${OUTPUT_DIR}"
fi

if [ -n "${HISTORY_FILE}" ]; then
    CMD="$CMD --history-file ${HISTORY_FILE}"
fi

if [ -n "${FORMAT}" ]; then
    CMD="$CMD --format ${FORMAT}"
fi

# Headless mode configuration
if [ "${HEADLESS}" = "false" ]; then
    CMD="$CMD --no-headless"
fi

# History TTL configuration
if [ -n "${HISTORY_TTL_DAYS}" ]; then
    CMD="$CMD --history-ttl-days ${HISTORY_TTL_DAYS}"
fi

echo "Starting scraper with command: $CMD"
exec $CMD
