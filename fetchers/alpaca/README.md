# Alpaca real-time news fetcher

Streams [Alpaca real-time company news](https://docs.alpaca.markets/us/docs/streaming-real-time-news)
into a Kafka topic using the official
[`alpaca-py`](https://github.com/alpacahq/alpaca-py) library.

A single `NewsDataStream` WebSocket
(`wss://stream.data.alpaca.markets/v1beta1/news`) covers every symbol via the
`*` wildcard, so — unlike the Longbridge fetcher — there is no sharding: one
process owns the whole stream and forwards each article to Kafka.

## Layout

```
worker/
  runner.py           # entrypoint: wires config + credentials + stream + Kafka
  config.py           # env-driven WorkerConfig
  credentials.py      # resolves Alpaca API key/secret (file or env)
  alpaca_client.py    # NewsDataStream wrapper + News -> JSON normalization
  kafka_publisher.py  # confluent_kafka producer wrapper (JSON)
  Dockerfile
  entrypoint.sh
  requirements.txt
Makefile
```

The local smoke-test Compose file is shared by all fetchers and lives one level
up at [`fetchers/docker-compose.yml`](../docker-compose.yml).

## Message format

Each article is published to `NEWS_TOPIC` (default `news.realtime`), keyed by its
primary symbol (so a company's news stays ordered on one partition), with this
JSON value:

```json
{
  "id": 24843171,
  "headline": "...",
  "summary": "...",
  "author": "...",
  "content": "...",
  "url": "https://...",
  "symbols": ["AAPL"],
  "source": "benzinga",
  "created_at": "2026-06-16T12:34:56+00:00",
  "updated_at": "2026-06-16T12:34:56+00:00",
  "images": [{"size": "large", "url": "https://..."}],
  "fetch_source": "alpaca",
  "event_type": "news",
  "ingest_time": "2026-06-16T12:34:57.123456+00:00"
}
```

Set `INCLUDE_CONTENT=false` to drop the (large) full-article `content` field.

## Configuration

| Env var | Default | Description |
| --- | --- | --- |
| `NEWS_SYMBOLS` | `*` | Comma-separated symbols, or `*` for all news |
| `NEWS_TOPIC` | `news.realtime` | Destination Kafka topic |
| `INCLUDE_CONTENT` | `true` | Include the full article body |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Used when `KAFKA_CONFIG_PATH` is unset |
| `KAFKA_CONFIG_PATH` | – | Path to a Kafka properties file (Confluent Cloud SASL_SSL) |
| `FLUSH_INTERVAL_S` | `30` | How often to poll/flush and log stats |
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | – | Alpaca credentials (env) |
| `ALPACA_CREDENTIALS_FILE` | `/secrets/credentials.json` | Alpaca credentials (file) |

## Local smoke test

Run from the `fetchers/` directory (the Compose file is shared by all fetchers):

```bash
cd ..   # into fetchers/
export APCA_API_KEY_ID=...
export APCA_API_SECRET_KEY=...
# optional: limit to specific tickers (default is all news)
export NEWS_SYMBOLS="AAPL,MSFT,TSLA"
docker compose up --build kafka alpaca-news
```

Consume what lands in Kafka:

```bash
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 --topic news.realtime --from-beginning
```

## Build & push the image

```bash
make build          # docker build -> palantiracr.azurecr.io/palantir/alpaca-news-fetcher:0.0.1
make push
```

CI also builds and pushes this image — see
`.github/workflows/fetchers-docker-push-azure.yml`.

## Deploy to Kubernetes

Manifests live in [`infra/fetchers/alpaca-k8s`](../../infra/fetchers/alpaca-k8s):

```bash
kubectl apply -f infra/fetchers/alpaca-k8s/00-namespace.yaml
# Confluent Cloud: edit 01-kafka-configmap.yaml with your SASL creds
# (or use 01-kafka-configmap-local.yaml for an in-cluster Kafka)
kubectl apply -f infra/fetchers/alpaca-k8s/01-kafka-configmap.yaml
# copy the example secret, fill in your Alpaca creds, then apply it
cp infra/fetchers/alpaca-k8s/02-alpaca-secret.example.yaml infra/fetchers/alpaca-k8s/02-alpaca-secret.yaml
kubectl apply -f infra/fetchers/alpaca-k8s/02-alpaca-secret.yaml
kubectl apply -f infra/fetchers/alpaca-k8s/03-deployment.yaml
```

Keep the Deployment at `replicas: 1`: two connections would produce duplicate
articles.
