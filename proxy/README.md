# flink-proxy — REST external table for `KEY_SEARCH_AGG`

C#/.NET HTTP proxy (ASP.NET Core, net10.0) that exposes the CosmosDB `companies`
collection (one NASDAQ company per document, key = `ticker`) as a **REST external
table** consumable by the `KEY_SEARCH_AGG` function of Confluent Cloud for Apache
Flink.

Flow: `stream` → `KEY_SEARCH_AGG` → **HTTP POST** to this proxy → **CosmosDB**
→ company JSON document → mapped to the external table columns.

## Endpoints

| Method | Route                        | Usage                                                       |
|--------|------------------------------|-------------------------------------------------------------|
| POST   | `/companies/key-search`      | Called by `KEY_SEARCH_AGG`. JSON body → array of documents. |
| POST   | `/companies/report`          | Like key-search but returns `[{ ticker, name, report }]`, where `report` is a **Markdown summary** of all fields (LLM input). |
| GET    | `/companies/{ticker}`        | Manual test: `curl .../companies/AMD`.                      |
| GET    | `/companies/report/{ticker}` | Raw Markdown (`text/markdown`): `curl .../companies/report/SPCX`. |
| GET    | `/healthz`                   | Liveness.                                                   |

The proxy returns a **JSON array** of the matching documents. Confluent Cloud
accepts either a single node or an array and maps the fields to the external
table columns.

### Request contract — tolerant parsing

The exact body emitted by `KEY_SEARCH_AGG` is not contractually documented and may
vary (bare string, array, or key/value object). The proxy therefore stays
**tolerant**: it walks the whole received JSON, keeps the scalar values that look
like a ticker (`^[A-Z]{1,6}(\.[A-Z]{1,2})?$`), and **logs the raw body**
(`LogLevel Palantir.FlinkProxy = Debug`).

> After a first real test, confirm the body in the logs and tighten
> `KeyExtractor` / `CosmosOptions.KeyField` if needed.

## Configuration

`Cosmos` section of `appsettings.json`, overridable with environment variables
(double underscore):

| Key                | Env var             | Default                                           |
|--------------------|---------------------|---------------------------------------------------|
| `Cosmos:Endpoint`  | `Cosmos__Endpoint`  | `https://palantir-rag.documents.azure.com:443/`   |
| `Cosmos:Key`       | `Cosmos__Key`       | *(required — not committed)*                       |
| `Cosmos:Database`  | `Cosmos__Database`  | `palantir-db`                                      |
| `Cosmos:Container` | `Cosmos__Container` | `companies`                                        |
| `Cosmos:KeyField`  | `Cosmos__KeyField`  | `ticker`                                           |

### Endpoint authentication

`Auth` section, aligned with the `authentication.*` options of the REST
`CREATE CONNECTION`. `/healthz` always stays open. Secrets are compared in
constant time.

| Key                | Env var             | Values / role                                 |
|--------------------|---------------------|-----------------------------------------------|
| `Auth:Type`        | `Auth__Type`        | `None` (default), `Basic`, `Bearer`, `ApiKey` |
| `Auth:Username`    | `Auth__Username`    | Basic — username                              |
| `Auth:Password`    | `Auth__Password`    | Basic — password                              |
| `Auth:Token`       | `Auth__Token`       | Bearer — token                                |
| `Auth:ApiKeyHeader`| `Auth__ApiKeyHeader`| ApiKey — header name (default `X-API-Key`)    |
| `Auth:ApiKey`      | `Auth__ApiKey`      | ApiKey — expected value                       |

- **Basic** → the proxy expects `Authorization: Basic base64(user:pass)`.
- **Bearer** → the proxy expects `Authorization: Bearer <token>`.
- **ApiKey** → the proxy expects the key in the `Auth:ApiKeyHeader` header (e.g. `X-API-Key: <key>`).

Configure the same credentials on the Flink side in the `CREATE CONNECTION` (below).

## Run

```bash
# Local
export Cosmos__Key='***'
dotnet run --project proxy            # listens on http://localhost:8080
curl http://localhost:8080/companies/AMD

# Docker
docker build -t flink-proxy ./proxy
docker run -p 8080:8080 -e Cosmos__Key='***' flink-proxy
```

## CI/CD

`.github/workflows/proxy-docker-push-azure.yml` builds the multi-arch image
(`linux/amd64,linux/arm64`) and pushes it to Azure ACR
(`palantiracr.azurecr.io/palantir/company-flink-proxy`).

- **Triggers:** push of a `v*.*.*` tag (touching `proxy/**`), or manual `workflow_dispatch`.
- **Tags produced:** `latest`, the branch name, semver (`X.Y.Z`, `X.Y`, `X`) on tag pushes, and `sha-<short>`.
- **Required repo config:** variable `REGISTRY_USERNAME` and secret `REGISTRY_TOKEN` (same as the other `*-docker-push-azure` workflows).
- Registry-side build cache (`:buildcache`) speeds up subsequent builds.

Release example:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

## Flink side (Confluent Cloud)

The proxy must be reachable from Confluent Cloud (public HTTPS endpoint,
e.g. via an ingress / tunnel).

```sql
-- 1) REST connection to the proxy
--    Align auth with the proxy `Auth` section:
--    Basic  -> Auth__Type=Basic  + Username/Password
--    Bearer -> Auth__Type=Bearer + Token
CREATE CONNECTION companies_rest_connection WITH (
  'type'     = 'rest',
  'endpoint' = 'https://<public-host>/companies/key-search',
  -- Basic:
  'authentication.type'     = 'basic',
  'authentication.username' = 'flink',
  'authentication.password' = 's3cret'
  -- Bearer (instead of the basic block):
  -- 'authentication.type'         = 'bearer',
  -- 'authentication.bearer.token' = 'tok-abc-123'
  -- ApiKey (key in a custom header — see the connection header options):
  -- e.g. proxy: Auth__Type=ApiKey Auth__ApiKeyHeader=X-API-Key Auth__ApiKey=k-secret-42
);

-- 2) External table: declare only the columns to extract from the response.
--    Names/types must match the CosmosDB document fields.
CREATE TABLE companies_ext (
  `ticker`         STRING,
  `name`           STRING,
  `current_price`  DOUBLE,
  `recommendation_key` STRING,
  `sentiment` ROW<
    `sentiment_score` DOUBLE,
    `sentiment_trend` STRING,
    `confidence`      DOUBLE
  >
) WITH (
  'connector'       = 'rest',
  'rest.connection' = 'companies_rest_connection'
);

-- 3) Enrich a stream by ticker via KEY_SEARCH_AGG
SELECT
  s.ticker,
  c.name,
  c.current_price,
  c.recommendation_key
FROM trade_signals AS s,
  LATERAL TABLE(
    KEY_SEARCH_AGG(
      companies_ext,
      DESCRIPTOR(s.ticker),   -- input column (search key)
      companies_ext.ticker    -- column matched in the external table
    )
  ) AS c;
```

Options tunable via `map[...]` (4th argument): `async_enabled`,
`client_timeout`, `max_parallelism`, `retry_count`, `retry_error_list`, `debug`.

### "report" variant as LLM input

Point a second `CREATE CONNECTION` at `/companies/report`, with an external table
exposing a single `report STRING` column, then feed a model:

```sql
CREATE TABLE companies_report (
  `ticker` STRING,
  `name`   STRING,
  `report` STRING          -- Markdown summary of the whole document
) WITH (
  'connector'       = 'rest',
  'rest.connection' = 'companies_report_connection'  -- endpoint = .../companies/report
);

SELECT s.ticker, r.report
FROM trade_signals AS s,
  LATERAL TABLE(KEY_SEARCH_AGG(companies_report, DESCRIPTOR(s.ticker), companies_report.ticker)) AS r;
-- r.report can then be passed to AI_COMPLETE / ML_PREDICT as a prompt.
```

## Files

| File                             | Role                                             |
|----------------------------------|--------------------------------------------------|
| `Program.cs`                     | Host, DI, `CosmosClient` singleton, routes.      |
| `Controllers/KeySearchController.cs` | Endpoints `key-search`, `report`, `{ticker}`.|
| `CompanyRepository.cs`           | CosmosDB lookup (stream API + System.Text.Json). |
| `ReportBuilder.cs`               | Renders the CosmosDB document into a Markdown summary. |
| `KeyExtractor.cs`                | Tolerant extraction of tickers from the body.    |
| `EndpointAuthMiddleware.cs`      | Basic / Bearer / ApiKey endpoint auth.           |
| `AuthOptions.cs` / `CosmosOptions.cs` | Strongly-typed configuration.               |
