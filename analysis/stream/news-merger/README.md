# news-merger

Kafka Streams application that merges the scraper topics described in
[`../messages-input.md`](../messages-input.md) into a single `financial-news` topic
whose value follows [`../message-output.md`](../message-output.md).

```
investing-news ─────┐
seeking-alpha-news ─┤  map each source to the common shape
wsj-articles ───────┤ ──────────────────────────────────────► financial-news (key = id)
twitter-tweets ─────┘
```

The topology is stateless (no state store, no repartition topic). Inputs and output are
plain JSON (no Schema Registry), like the scrapers produce them.

## Field mapping

| output           | investing-news   | seeking-alpha-news             | wsj-articles                     | twitter-tweets          |
|------------------|------------------|--------------------------------|----------------------------------|-------------------------|
| `id` (also key)  | `id`             | `/news/<n>` from `url`         | 8-hex suffix of `url`            | `id`                    |
| `author`         | `author`         | `author`                       | `author`                         | `username`              |
| `category`       | `category`       | `category`                     | first path segment of `url`      | `source` (search query) |
| `content`        | `content`        | `content`                      | `content`                        | `text`                  |
| `content_md`     | `content_md`     | `content_md`                   | `content_md`                     | `content_md`            |
| `published_date` | `published_date` | `published_date`               | `published_date`                 | `timeIso` / `timestamp` |
| `scraped_at`     | `scraped_at`     | `scraped_at`                   | `scraped_at`                     | `scrapedAt`             |
| `title`          | `title`          | `title`                        | `title`                          | `""`                    |
| `url`            | `url`            | `url`                          | `url`                            | `permanentUrl`          |
| `source`         | `"investing"`    | `"seeking-alpha"`              | `"wsj"`                          | `"twitter"`             |

- Id extraction is the same as in `analysis/flink/statements/news_sentiment.sql`; if the
  pattern does not match, the `url` is used as id.
- `published_date` / `scraped_at` are normalized to ISO-8601 UTC (`2025-10-01T13:30:00Z`).
  Values without an offset (e.g. investing's `10/01/2025, 09:30 AM`) are read as
  `America/New_York`. Unparseable values are passed through unchanged.
- Malformed JSON, tombstones and records without any id/url are logged and skipped.

## Configuration

| env var                     | default              |
|-----------------------------|----------------------|
| `KAFKA_BOOTSTRAP_SERVERS`   | `localhost:9092`     |
| `KAFKA_CONFIG_PATH`         | _(none)_ — properties file with credentials. The librdkafka format used by the other services (`sasl.mechanisms`, `sasl.username`, `sasl.password`) is translated automatically. |
| `APPLICATION_ID`            | `news-merger`        |
| `OUTPUT_TOPIC`              | `financial-news`     |
| `INPUT_TOPIC_INVESTING`     | `investing-news`     |
| `INPUT_TOPIC_SEEKING_ALPHA` | `seeking-alpha-news` |
| `INPUT_TOPIC_WSJ`           | `wsj-articles`       |
| `INPUT_TOPIC_TWITTER`       | `twitter-tweets`     |
| `PROCESSING_GUARANTEE`      | `at_least_once`      |
| `AUTO_OFFSET_RESET`         | `earliest`           |
| `NUM_STREAM_THREADS`        | `1`                  |
| `JAVA_OPTS`                 | `-XX:MaxRAMPercentage=75` |

## Build & run

```bash
mvn verify                                   # unit tests (TopologyTestDriver) + fat jar
docker build -t news-merger .
docker run --rm \
  -e KAFKA_CONFIG_PATH=/config/kafka_config.properties \
  -v $PWD/kafka_config.properties:/config/kafka_config.properties:ro \
  news-merger
```

The image is built and pushed to ACR as `palantir/news-merger` by
`.github/workflows/news-merger-docker-push-azure.yml` on `v*.*.*` tags or manual dispatch.
