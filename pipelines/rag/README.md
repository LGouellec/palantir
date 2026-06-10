# RAG — CosmosDB Sink Connector (self-managed Connect on Confluent Cloud)

Kubernetes manifests for a **self-managed Kafka Connect worker**
(`cp-kafka-connect`, Confluent Community License — free, no paid Platform
license) that connects to our **Confluent Cloud** cluster and streams the
`news_embedding` topic into Azure CosmosDB, using Microsoft's
[`kafka-connect-cosmosdb`](https://github.com/microsoft/kafka-connect-cosmosdb)
sink connector (v1.19.0, installed from the GitHub release).

There is no local Kafka broker — the worker uses Confluent Cloud as its broker
(see `infra/confluent-cloud.md`). The Flink job in
`analysis/flink/statements/rag.sql` produces `news_embedding` (JSON_SR); this
sink writes each record into the `news` container of the `palantir-db` CosmosDB
database (the RAG vector store).

## Components

| File | What it deploys |
|------|-----------------|
| `00-namespace.yaml` | `palantir-rag` namespace |
| `01-kafka-connect.yaml` | Confluent Cloud credentials Secret + Kafka Connect StatefulSet (init container fetches the connector jar) + headless REST Service |
| `02-cosmosdb-sink-connector.yaml` | CosmosDB key Secret, connector ConfigMap, and a Job that registers the sink via the Connect REST API |

## Image & licensing notes

- The Connect **runtime** is `confluentinc/cp-kafka-connect:7.7.0`, under the
  Confluent **Community** License — free to use, no paid Platform license
  required. It already bundles the JSON_SR `JsonSchemaConverter`.
- The CosmosDB connector is the **GitHub release fat-jar**, not the deprecated
  Confluent Hub package `microsoftcorporation/kafka-connect-cosmos`.

## Before you deploy

Fill in `01-kafka-connect.yaml` → `confluent-cloud-credentials` Secret:

- `bootstrap-servers`, `kafka-api-key`, `kafka-api-secret` — prefilled with the
  "CosmosDb Sink Connector" key from `infra/cosmos-db-rag.md`.
- `schema-registry-url`, `schema-registry-api-key`, `schema-registry-api-secret`
  — **must be set** (JSON_SR needs Schema Registry). Create an SR API key in the
  same Confluent Cloud environment.

> **GPU:** the Connect container requests `nvidia.com/gpu: 1`. Connect is pure
> JVM I/O and won't actually use a GPU — it's requested per the deployment spec
> to pin the pod to a GPU node (with a matching toleration). Remove the
> `nvidia.com/gpu` requests/limits and the toleration if you don't want that.

## Deploy

```bash
kubectl apply -f pipelines/rag/00-namespace.yaml
kubectl apply -f pipelines/rag/01-kafka-connect.yaml
kubectl -n palantir-rag rollout status deploy/kafka-connect

# Register the sink connector.
kubectl apply -f pipelines/rag/02-cosmosdb-sink-news_embeddings.yaml
kubectl -n palantir-rag logs job/register-cosmosdb-sink -f
```

## Monitor

```bash
# Hit the Connect REST API directly via port-forward.
kubectl -n palantir-rag port-forward svc/kafka-connect 8083:8083
curl -s localhost:8083/connectors/palantir-cosmos-sink-news-embeddings/status | jq
```

## Notes / caveats

1. **Secrets are inlined** to match the repo convention. The CosmosDB key and
   Confluent Cloud key are committed — move them to a sealed secret / Key Vault
   and **rotate** for anything beyond a sandbox.
2. **Connect internal topics** (`connect-cosmos-configs/offsets/status`) are
   created in Confluent Cloud at RF=3 (CC requirement). The worker's API key
   needs permission to create/produce/consume them.
3. **Scale** `replicas` in `01-kafka-connect.yaml` for throughput / HA — workers
   form one Connect group via `CONNECT_GROUP_ID` / `group.id`.

## CosmosDB sink config keys (v1.19.0 connector)

| Key | Value |
|-----|-------|
| `connector.class` | `com.azure.cosmos.kafka.connect.sink.CosmosDBSinkConnector` |
| `connect.cosmos.connection.endpoint` | `https://palantir-rag.documents.azure.com:443/` |
| `connect.cosmos.master.key` | (from `cosmosdb-credentials` Secret) |
| `connect.cosmos.databasename` | `palantir-db` |
| `connect.cosmos.containers.topicmap` | `news_embedding#news` |
