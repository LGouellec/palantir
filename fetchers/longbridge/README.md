# Longbridge Fetcher → Kafka

Real-time NASDAQ + NYSE quotes streamed from the Longbridge WebSocket API into
Kafka, sharded across Kubernetes pods and driven by a Kopf operator.

See [`spec.md`](./spec.md) for the original design. This README documents the
implementation.

## Why sharding

Longbridge allows **one long-lived WebSocket per account** and **500 tickers per
WebSocket**. The full US universe (NASDAQ + NYSE, incl. ETFs) is ~8000 tickers, so we need
~17 shards, each with **its own Longbridge account**. A Kubernetes operator computes the shard
count daily and scales a StatefulSet accordingly.

```
 CronJob (06:00 ET)            Operator (Kopf)                 StatefulSet
 ─────────────────             ───────────────                 ───────────
 fetch NASDAQ+NYSE   ──patch──▶ MarketShardConfig  ──reconcile─▶ market-shard-0..N
 via Nasdaq FTP                 (CRD)                            each: 500 tickers
 patch spec.symbols             • shardCount = ⌈n/500⌉            • 1 WebSocket
                                • write ConfigMap                • → Kafka
                                • scale StatefulSet
                                • stamp hash → rollout
```

## Components

| Path | What |
|------|------|
| `worker/` | The shard worker: reads its ticker slice, opens one Longbridge WebSocket, publishes quotes + depth to Kafka. |
| `operator/` | Kopf operator (`shard_operator.py`) + daily ticker refresh (`refresh.py`) + Nasdaq FTP fetch (`tickers.py`). |
| `crd/` | The `MarketShardConfig` CustomResourceDefinition. |
| `../../infra/fetchers/longbridge-k8s/` | Deployment manifests (namespace, RBAC, operator, StatefulSet, ConfigMaps, Secret example, CronJob). |

## Sharding model

The operator writes the full **ordered** symbol list into a ConfigMap
(`market-shard-symbols → us-equities.json`). Shard `i` owns
`symbols[i*500 : (i+1)*500]`. Because the list is sorted deterministically and
both sides share `maxPerShard`, the shard → ticker mapping is stable. A changed
list changes the `symbolsHash`, which the operator stamps on the pod template
annotation to trigger a rolling restart so pods re-read their slice.

The shard index comes from the StatefulSet pod ordinal (`market-shard-7` → 7).

## Credentials (one account per shard)

Each shard reads its own Longbridge credentials, resolved in this order:

1. **Per-shard file** in `LONGPORT_CREDENTIALS_DIR` (default `/secrets`):
   `shard-<index>.json` → `{"app_key","app_secret","access_token"}`. This is
   how the K8s `longbridge-credentials` Secret is consumed.
2. **Indexed env vars**: `LONGPORT_APP_KEY_<index>` / `_SECRET_<index>` / `_ACCESS_TOKEN_<index>`.
3. **Shared env vars**: `LONGPORT_APP_KEY` / `LONGPORT_APP_SECRET` / `LONGPORT_ACCESS_TOKEN`
   (local/dev with a single account only — does not respect the 500-ticker limit).

## Kafka output

Two topics, keyed by the plain ticker (`AAPL`):

**`quotes.realtime`** (`SubType.Quote`)
```json
{
  "symbol": "AAPL", "longbridge_symbol": "AAPL.US",
  "source": "longbridge", "event_type": "quote",
  "event_time": "2026-06-10T13:30:00.123+00:00",
  "ingest_time": "2026-06-10T13:30:00.456+00:00",
  "last_done": 201.34, "open": 200.1, "high": 202.0, "low": 199.8,
  "volume": 1234567, "turnover": 248000000.0,
  "trade_status": "Normal", "trade_session": "Intraday"
}
```

**`quotes.depth`** (`SubType.Depth`)
```json
{
  "symbol": "AAPL", "longbridge_symbol": "AAPL.US",
  "source": "longbridge", "event_type": "depth",
  "ingest_time": "2026-06-10T13:30:00.456+00:00",
  "asks": [{"position": 1, "price": 201.35, "volume": 300, "order_num": 4}],
  "bids": [{"position": 1, "price": 201.33, "volume": 500, "order_num": 6}]
}
```

Prices are emitted as JSON numbers (floats), volumes as integers. (Note the
Flink `json-registry` int/number ambiguity if you later wire these into a Flink
table — declare price columns as `DOUBLE`.)

## Build

```bash
make build           # builds longbridge-worker and longbridge-operator images
make push TAG=0.0.1
```

## Deploy

```bash
# 1. Create the real Longbridge credentials Secret (one entry per shard).
cp ../../infra/fetchers/longbridge-k8s/05-longbridge-secret.example.yaml my-secret.yaml
# ...edit my-secret.yaml... then:
kubectl apply -f my-secret.yaml

# 2. Edit 04-kafka-configmap.yaml with your Confluent Cloud API key/secret.

# 3. Apply everything else (CRD, operator, StatefulSet, CronJob, CR).
make deploy

# 4. Bootstrap the symbol list now instead of waiting for 06:00 ET.
make bootstrap

# 5. Watch it come up.
kubectl -n longbridge get marketshardconfig us-equities   # SHARDS / SYMBOLS columns
make logs-operator
make logs-shard
```

Order matters only in that the operator scales the StatefulSet from 0 once the
symbols ConfigMap exists — so pods never start without their ticker slice.

## Local smoke test (no Kubernetes)

```bash
mkdir -p local
echo '["AAPL.US","MSFT.US","TSLA.US"]' > local/us-equities.json
export LONGPORT_APP_KEY=... LONGPORT_APP_SECRET=... LONGPORT_ACCESS_TOKEN=...
export KAFKA_BOOTSTRAP_SERVERS=host.docker.internal:9092
make local
```

## Operational notes

- **Daily refresh**: the CronJob runs at 06:00 ET on weekdays. If the universe
  is unchanged (same hash) it skips the patch, so no needless rollout.
- **Self-heal**: the operator re-reconciles every `SELF_HEAL_INTERVAL_S` (300s)
  to correct manual drift in replicas.
- **Over-provisioned shards**: a pod whose index exceeds the needed shard count
  idles healthily (e.g. transiently during scale-down).
- **Scaling**: don't `kubectl scale` the StatefulSet by hand — the operator owns
  `replicas`. Change `maxPerShard` on the CR instead.
