#!/bin/bash
set -e

# Allow overriding the command (e.g. for debugging): `docker run ... python -c ...`
if [ "$#" -gt 0 ]; then
    exec python "$@"
fi

echo "Starting Longbridge shard worker"
echo "  SHARD_INDEX=${SHARD_INDEX:-<from pod ordinal>} SHARD_COUNT=${SHARD_COUNT} MAX_PER_SHARD=${MAX_PER_SHARD}"
echo "  QUOTE_TOPIC=${QUOTE_TOPIC} DEPTH_TOPIC=${DEPTH_TOPIC}"

exec python runner.py
