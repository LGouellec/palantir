#!/bin/sh
set -e

# If arguments are provided, run them directly (e.g. `node dist/index.js --foo`).
if [ "$#" -gt 0 ]; then
    exec node "$@"
fi

echo "Starting twitter scraper"
echo "  queries=${TWITTER_QUERIES:-<none>} users=${TWITTER_USERS:-<none>}"
echo "  kafka_enabled=${KAFKA_ENABLED:-false} topic=${KAFKA_TOPIC:-twitter-tweets}"
echo "  continuous=${CONTINUOUS:-false} interval=${CONTINUOUS_INTERVAL:-300}s"

exec node dist/index.js
