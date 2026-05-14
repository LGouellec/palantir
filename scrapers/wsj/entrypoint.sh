#!/bin/bash
set -e

# If arguments provided, execute them directly
if [ "$#" -gt 0 ]; then
    exec python "$@"
fi

# Build command from environment variables
CMD="python wsj_scraper_distributed.py"

# Distributed options
CMD="$CMD --pod-index ${POD_INDEX}"
CMD="$CMD --total-pods ${TOTAL_PODS}"
CMD="$CMD --mode ${DISTRIBUTION}"

if [ "${DISTRIBUTION}" = "kafka" ]; then

    if [ -n "${KAFKA_URLS_TOPIC}" ]; then
        CMD="$CMD --kafka-urls-topic ${KAFKA_URLS_TOPIC}"
    fi

    if [ -n "${KAFKA_URLS_GROUP}" ]; then
        CMD="$CMD --kafka-urls-consumer-group ${KAFKA_URLS_GROUP}"
    fi

    if [ -n "${COORDINATOR_POD}" ]; then
        CMD="$CMD --coordinator-pod ${COORDINATOR_POD}"
    fi

fi

# Standard scraper options
CMD="$CMD --base-url ${BASE_URL}"
CMD="$CMD --limit ${LIMIT}"
CMD="$CMD --delay ${DELAY}"

if [ -n "${OUTPUT_DIR}" ]; then
    CMD="$CMD --output-dir ${OUTPUT_DIR}"
fi

if [ -n "${FORMAT}" ]; then
    CMD="$CMD --format ${FORMAT}"
fi

if [ -n "${URLS_FILE}" ] && [ -f "${URLS_FILE}" ]; then
    CMD="$CMD --urls-file ${URLS_FILE}"
fi

if [ -n "${HISTORY_FILE}" ]; then
    CMD="$CMD --history-file ${HISTORY_FILE}"
fi

# Boolean flags
if [ "${VERBOSE}" = "true" ]; then
    CMD="$CMD --verbose"
fi

if [ "${FORCE}" = "true" ]; then
    CMD="$CMD --force"
fi

if [ "${SAVE_LOCAL}" = "true" ]; then
    CMD="$CMD --save-local"
fi

if [ "${NO_PAGINATION}" = "true" ]; then
    CMD="$CMD --no-pagination"
fi

if [ "${NO_AUTO_DISCOVERY}" = "true" ]; then
    CMD="$CMD --no-auto-discovery"
fi

if [ "${HEADLESS}" = "false" ]; then
    CMD="$CMD --no-headless"
fi

# Kafka options (for article publishing)
if [ "${KAFKA_ENABLED}" = "true" ]; then
    CMD="$CMD --kafka"
    CMD="$CMD --kafka-topic ${KAFKA_TOPIC}"

    if [ -n "${KAFKA_BOOTSTRAP_SERVERS}" ]; then
        CMD="$CMD --kafka-bootstrap-servers ${KAFKA_BOOTSTRAP_SERVERS}"
    fi

fi

if [ -n "${KAFKA_CONFIG_FILE}" ] && [ -f "${KAFKA_CONFIG_FILE}" ]; then
    CMD="$CMD --kafka-config ${KAFKA_CONFIG_FILE}"
fi

echo "Starting WSJ scraper with command: $CMD"
exec $CMD
