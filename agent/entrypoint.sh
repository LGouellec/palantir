#!/bin/bash
set -e

# Allow overriding the command (e.g. for debugging): `docker run ... python -c ...`
if [ "$#" -gt 0 ]; then
    exec python "$@"
fi

echo "Starting trading agent"
echo "  TRADE_SIGNAL_TOPIC=${TRADE_SIGNAL_TOPIC:-stock_quotes.trade_signal} TRADING_LIVE=${TRADING_LIVE:-false} DRY_RUN=${DRY_RUN:-false}"

exec python runner.py
