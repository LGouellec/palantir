# Trading agent

Consumes the Flink-generated `stock_quotes.trade_signal` topic (see
`analysis/flink/statements/trade_signal.sql`, schema and example payload in
[`spec.md`](./spec.md)) and calls the Alpaca trading API to enter, scale into,
adjust, or exit positions per `spec.md`'s BUY/HOLD/SELL and risk-management
rules.

Defaults are safety-first: **paper trading** unless `TRADING_LIVE=true` is set
explicitly, and every entry/exit is an Alpaca **bracket order**
(`order_class=bracket`) so the stop-loss/take-profit protection lives on
Alpaca's servers rather than in this process's memory.

## Layout

```
runner.py           entrypoint: wires config + credentials + Kafka + Alpaca, poll loop
config.py            env-driven WorkerConfig (topics, risk thresholds, kafka)
credentials.py        resolves Alpaca API key/secret (file or env)
trade_signal.py        TradeSignal dataclass: parses/validates the Kafka payload
kafka_consumer.py       DeserializingConsumer (schema-registry, or plain-JSON locally)
alpaca_trading.py        alpaca-py TradingClient wrapper (account/positions/orders)
risk.py                   pure sizing & threshold math (no I/O, easiest to unit test)
rules.py                  BUY/HOLD/SELL decision engine -> Action
Dockerfile
entrypoint.sh
requirements.txt
docker-compose.yml    local smoke test (own Kafka, no Schema Registry)
Makefile
```

## Decision rules

For each incoming signal, a fresh Alpaca account snapshot (equity,
`last_equity`, positions, open orders) is pulled and `rules.decide()`
evaluates, in order:

1. **Circuit breaker**: if today's PnL (`(equity - last_equity) / last_equity`)
   is at or above `DAILY_CIRCUIT_BREAKER_PCT`, no new entries/scale-ins are
   allowed for the rest of the day. Exits (`SELL` on a held position) are
   never blocked.
2. **`SELL`**: close the full position if held; no-op (no margin/shorting) if
   not held.
3. **`BUY`, not held**: size the entry (risk-based, capped by exposure and
   liquidity) and submit a bracket order.
4. **`BUY`, held**: only scale in if `(exit_price - close) / close >=
   SCALE_IN_MIN_UPSIDE_PCT` — the spec asks for "significant" upside without a
   number, so this is set stricter than the plain new-entry bar below.
5. **`HOLD`, held**: adjust the resting stop-loss/take-profit legs only if the
   new levels are strictly more favorable (higher stop, higher target) — never
   loosens.
6. **`HOLD`, not held**: enter only if
   `(exit_price - close) / close > NEW_ENTRY_MIN_UPSIDE_PCT` (spec's explicit
   3% threshold).

Sizing (`risk.py`) risks at most `RISK_PER_TRADE_PCT` of equity on the
distance from `close` to `stop_loss`, then caps the resulting position so it
never exceeds `MAX_POSITION_SIZE_PCT` of equity on its own, and so total
exposure never exceeds `MAX_PORTFOLIO_UTILIZATION_PCT` of equity (plus
`PREFERRED_SYMBOL_EXTRA_UTILIZATION_PCT` extra headroom for symbols in
`PREFERRED_SYMBOLS`) or available buying power. Liquidity is the signal's
`volume` (already a running daily aggregate) times `close`, and must clear
`MIN_DAILY_DOLLAR_VOLUME_USD`.

**Portfolio reorientation**: if sizing comes back at 0 shares because the
portfolio is fully booked (total exposure at `MAX_PORTFOLIO_UTILIZATION_PCT`)
and this signal's potential PnL beats our worst open position's unrealized
P&L by at least `REORIENT_MIN_EDGE_PCT`, the decision is `CLOSE_POSITION` on
that worst position instead of a no-op — freeing up exposure so a
follow-up signal can size the new entry. Disable with
`PORTFOLIO_REORIENT_ENABLED=false`.

Every decision is logged as `<symbol> signal=<BUY|HOLD|SELL> -> <Action>
(<reason>)` — that log line is the audit trail for every order this agent
does or doesn't place.

## Configuration

| Env var | Default | Description |
| --- | --- | --- |
| `TRADE_SIGNAL_TOPIC` | `stock_quotes.trade_signal` | topic to consume |
| `CONSUMER_GROUP_ID` | `trading-agent` | Kafka consumer group |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | used when `KAFKA_CONFIG_PATH` is unset |
| `KAFKA_CONFIG_PATH` | – | path to a Kafka properties file (Confluent Cloud SASL_SSL) |
| `SCHEMA_REGISTRY_URL` | – | Confluent Schema Registry URL; unset -> plain JSON (local smoke test) |
| `SCHEMA_REGISTRY_API_KEY` / `_API_SECRET` | – | Schema Registry basic-auth credentials |
| `TRADING_LIVE` | `false` | must be `true` to trade the live Alpaca account instead of paper |
| `DRY_RUN` | `false` | log the decided action instead of calling Alpaca |
| `RISK_PER_TRADE_PCT` | `0.02` | max equity risked per position (entry + scale-ins combined) |
| `MAX_POSITION_SIZE_PCT` | `0.02` | max market value of a single position as a fraction of equity |
| `MAX_PORTFOLIO_UTILIZATION_PCT` | `0.60` | max total exposure as a fraction of equity |
| `DAILY_CIRCUIT_BREAKER_PCT` | `0.10` | halt new entries for the day above this daily PnL |
| `MIN_DAILY_DOLLAR_VOLUME_USD` | `5000000` | liquidity floor for new entries |
| `NEW_ENTRY_MIN_UPSIDE_PCT` | `0.03` | HOLD + not-held entry threshold |
| `SCALE_IN_MIN_UPSIDE_PCT` | `0.05` | BUY/SELL + held scale-in threshold |
| `SHORT_SELLING_ENABLED` | `false` | if `true`, a SELL signal with no position opens a short instead of no-op'ing |
| `PREFERRED_SYMBOLS` | – | comma-separated symbols allowed extra portfolio-utilization headroom |
| `PREFERRED_SYMBOL_EXTRA_UTILIZATION_PCT` | `0.10` | extra headroom above `MAX_PORTFOLIO_UTILIZATION_PCT` for those symbols |
| `PORTFOLIO_REORIENT_ENABLED` | `true` | when fully booked, sell the worst open position for a meaningfully more profitable signal instead of no-op'ing |
| `REORIENT_MIN_EDGE_PCT` | `0.05` | how much a new signal's potential PnL must beat the worst position's unrealized P&L by to trigger a reorientation sell |
| `POLL_TIMEOUT_S` | `5.0` | Kafka poll timeout |
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | – | Alpaca credentials (env) |
| `ALPACA_CREDENTIALS_FILE` | `/secrets/credentials.json` | Alpaca credentials (file) |

## Local smoke test

```bash
cd agent
export APCA_API_KEY_ID=...      # a paper-trading key pair
export APCA_API_SECRET_KEY=...
docker compose up --build kafka trading-agent
```

This runs with `DRY_RUN=true` and no Schema Registry, so every decision is
logged but no order is ever placed. From another shell, publish the example
payload from `spec.md`:

```bash
cat > /tmp/signal.json <<'EOF'
{"symbol":"MRK","window_start":1786384800000,"window_end":1786385700000,
 "close":130.58,"volume":2384044.0,"signal":"BUY","stop_loss":128.4,"exit_price":133.0}
EOF
docker exec -i kafka kafka-console-producer \
  --bootstrap-server localhost:9092 --topic stock_quotes.trade_signal < /tmp/signal.json
```

Watch the `trading-agent` logs for the resulting decision (`ENTER_LONG` with a
sized quantity, or `NO_OP` with a reason if paper-account state fails a gate).

## Build & push the image

```bash
make build          # docker build -> palantiracr.azurecr.io/palantir/trading-agent:0.0.1
make push
```

CI builds and pushes this image to ACR via
[`agent-docker-push-azure.yml`](../.github/workflows/agent-docker-push-azure.yml)
on every `v*.*.*` tag push (or manually via `workflow_dispatch`), publishing
`palantir/trading-agent` tagged with `latest`, the pushed branch name (on
branch pushes), the release semver (full/major/major.minor, on tag pushes),
and `sha-<short-sha>`.

## Deploy to Kubernetes

Manifests live in [`infra/agent-k8s`](../infra/agent-k8s):

```bash
kubectl apply -f infra/agent-k8s/00-namespace.yaml
# Confluent Cloud: edit 01-kafka-configmap.yaml with your Kafka + Schema Registry settings
kubectl apply -f infra/agent-k8s/01-kafka-configmap.yaml
# copy the example secret, fill in your Alpaca creds, then apply it
cp infra/agent-k8s/02-agent-secret.example.yaml infra/agent-k8s/02-agent-secret.yaml
kubectl apply -f infra/agent-k8s/02-agent-secret.yaml
kubectl apply -f infra/agent-k8s/03-deployment.yaml
```

Keep `replicas: 1`: the exposure cap and circuit breaker are recomputed fresh
from Alpaca's account API on every decision rather than tracked in a shared
store, so two concurrent replicas could both pass the same exposure check and
double-enter a position.
