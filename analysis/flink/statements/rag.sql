---
    CREATE CONNECTION palantir_embedding_connection
    WITH (
        'type' = 'azureopenai',
        'endpoint' = 'https://palantir-oai.openai.azure.com/openai/deployments/text-embedding-3-large-2/embeddings?api-version=2023-05-15',
        'api-key' = 'XXXX'
    );
---
    CREATE MODEL palantir_embed
        INPUT (text STRING)
        OUTPUT (response ARRAY<FLOAT>)
    WITH (
        'azureopenai.input_format'='OPENAI-EMBED',
        'azureopenai.connection'='palantir_embedding_connection',
        'provider'='azureopenai',
        'task'='embedding'
    );
---
-- FOR A TEST
SELECT *
FROM (
  VALUES
    (1, 'OpenAI and Anthropic are racing toward potentially record-breaking initial public offerings by the end of the year.\n\nAn inside look at the financials of both companies prior to\n\ncompleted earlier this year shows their Achilles heel: the soaring costs needed to train new artificial intelligence models.\n', 10.50)
) AS t(id, name, price),
LATERAL TABLE(AI_EMBEDDING('palantir_embed', t.name)) AS e(embedding);

--
    CREATE CONNECTION palantir_cosmosdb_connection
    WITH (
        'type' = 'cosmosdb',
        'endpoint' = 'https://palantir-rag.documents.azure.com:443/',
        'api-key' = 'XXXXX'
    );
---

CREATE TABLE news_embedding (
  news_id STRING,
  content STRING,
  sentiment ROW<
    analysis ARRAY<
        ROW<
        aspect STRING,
        label  STRING,
        score  DOUBLE
        >
  >>,
  url STRING,
  title STRING,
  published_date TIMESTAMP_LTZ(3),
  category ARRAY<STRING>,
  source STRING,
  embeddings ARRAY<FLOAT>,
  PRIMARY KEY (news_id) NOT ENFORCED
)
DISTRIBUTED BY HASH(news_id) INTO 6 BUCKETS
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'delete',
  'changelog.mode' = 'append',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry'
);

--

SET 'sql.local-time-zone' = 'UTC';
SET 'sql.state-ttl'= '10 d';
SET 'sql.tables.scan.idle-timeout'= '30 s';
SET 'sql.tables.scan.startup.mode' ='earliest-offset';
-- SET 'sql.tables.scan.startup.mode' ='timestamp';
-- SET 'sql.tables.scan.startup.timestamp-millis' = '1782086400000';


INSERT INTO news_embedding
SELECT
    n.news_id,
    n.content,
    n.sentiment,
    n.url,
    n.title,
    n.published_date,
    n.category,
    n.source,
    e.embedding AS embeddings
FROM (
    SELECT *
    FROM news
    WHERE full_content IS NOT NULL
      AND CHARACTER_LENGTH(TRIM(full_content)) > 0
) n
CROSS JOIN LATERAL TABLE(
  AI_EMBEDDING(
    'palantir_embed',
    CONCAT(
      'Date: ',
      COALESCE(CAST(n.published_date AS STRING), ''),
      ' ',
      n.full_content
    ),
  MAP['retry_count', '10', 'client_timeout', '60', 'debug', 'true']
  )) AS e(embedding);

-- 'max_parallelism', '2', 'async_enabled', 'true'

---

CREATE TABLE palantir_vector_search (
  news_id STRING,
  content STRING,
  sentiment ROW<
    analysis ARRAY<
        ROW<
        aspect STRING,
        label  STRING,
        score  DOUBLE
        >
  >>,
  url STRING,
  title STRING,
  published_date BIGINT,
  category ARRAY<STRING>,
  source STRING,
  embeddings ARRAY<FLOAT>
) WITH (
   'connector' = 'cosmosdb',
   'cosmosdb.connection' = 'palantir_cosmosdb_connection',
   'cosmosdb.database' = 'palantir-db',
   'cosmosdb.container' = 'news'
);