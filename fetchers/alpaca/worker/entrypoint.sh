#!/bin/bash
set -e

# Allow overriding the command (e.g. for debugging): `docker run ... python -c ...`
if [ "$#" -gt 0 ]; then
    exec python "$@"
fi

echo "Starting Alpaca news fetcher"
echo "  NEWS_SYMBOLS=${NEWS_SYMBOLS:-*} NEWS_TOPIC=${NEWS_TOPIC}"

exec python runner.py
