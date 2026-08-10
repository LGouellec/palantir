
CREATE CONNECTION companies_rest_connection WITH (
  'type'     = 'rest',
  'endpoint' = 'https://company-flink-proxy.kafka-gateway.cloud',
  'token' = 'XXXXX'
);

CREATE TABLE companies_report (
  `ticker` STRING,
  `name` STRING,
  `report` STRING,
  PRIMARY KEY (ticker) NOT ENFORCED          
) WITH (
  'connector' = 'rest',
  'rest.connection' = 'companies_rest_connection',
  'rest.method' = 'POST',
  'rest.path' = 'companies/report'
);

-- For testing purpose
SELECT b.name, b.report FROM (
  SELECT CAST(report[1] as ROW<ticker STRING, name STRING, report STRING>)
  FROM LATERAL TABLE (
    KEY_SEARCH_AGG(companies_report, DESCRIPTOR(ticker), 'NVDA',
    MAP['client_timeout', 60, 'async_enabled', false, 'retry_count', 10])
  ) AS r(report)
) b

-- For testing purpose : vector search over palantir_vector_search.
-- Mirrors the query_embedding CTE below - embeds a dated test query, then
-- pulls the top-5 nearest news articles and unnests them into readable rows.
SELECT n.news_id, n.title, n.published_date, n.url
FROM (
  VALUES (CONCAT('Date: ', CAST(CURRENT_TIMESTAMP AS STRING), ' NVDA stock news relevant to trading around a BULLISH technical signal'))
) AS t(query_text),
LATERAL TABLE(AI_EMBEDDING('palantir_embed', t.query_text)) AS e(embedding),
LATERAL TABLE(
  VECTOR_SEARCH_AGG(palantir_vector_search, DESCRIPTOR(embeddings), e.embedding, 5,
    MAP['client_timeout', 60, 'async_enabled', false, 'retry_count', 10])
) AS vs(hits)
CROSS JOIN UNNEST(vs.hits) AS n(news_id, content, sentiment, url, title, published_date, category, source, embeddings, score);

-- For testing purpose : company fundamental-news vector search over palantir_vector_search.
-- Mirrors the company_news_query_embedding/company_news_context CTEs below -
-- embeds a dated, company-specific but signal-agnostic test query (so it
-- surfaces any good or bad news about the company, not just news that
-- happens to echo today's technical signal), over-fetches top-10, filters
-- down to the editorial sources (seeking-alpha, investing, wsj) instead of
-- social media, and drops anything older than 3 weeks.
SELECT n.news_id, n.title, n.source, n.published_date, n.url
FROM (
  VALUES (CONCAT('Date: ', CAST(CURRENT_TIMESTAMP AS STRING),
    ' NVDA NVIDIA recent news and developments about the company, positive or negative. Check only source seeking-alpha, investing or wsj'))
) AS t(query_text),
LATERAL TABLE(AI_EMBEDDING('palantir_embed', t.query_text,
  MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
) AS e(embedding),
LATERAL TABLE(
  VECTOR_SEARCH_AGG(palantir_vector_search, DESCRIPTOR(embeddings), e.embedding, 10,
    MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
) AS vs(hits)
CROSS JOIN UNNEST(vs.hits) AS n(news_id, content, sentiment, url, title, published_date, category, source, embeddings, score)
WHERE --n.source IN ('seeking-alpha', 'investing', 'wsj', 'reddit')
  --AND 
TO_TIMESTAMP_LTZ(n.published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY;


---
-- Chat model used to turn the assembled context into a trade signal.
-- Same Azure OpenAI resource as palantir_embedding_connection (rag.sql), pointed
-- at the chat-completions deployment instead of the embeddings one.
CREATE CONNECTION palantir_chat_connection
WITH (
  'type' = 'azureopenai',
  'endpoint' = 'https://palantir-oai.openai.azure.com/openai/deployments/gpt-5.6-luna/chat/completions?api-version=2024-02-01',
  'api-key' = 'XXXXX'
);

CREATE MODEL palantir_trade_signal_llm
  INPUT (prompt STRING)
  OUTPUT (response STRING)
WITH (
  'azureopenai.connection' = 'palantir_chat_connection',
  'provider' = 'azureopenai',
  'task' = 'text_generation',
  'azureopenai.system_prompt' = 'You are a disciplined trading agent that turns technical indicators, company reports, and recent news into a single trade signal. Use only the evidence given in the user prompt - never invent facts or call external tools. Always respond with ONLY a compact JSON object, no markdown fences and no extra text, matching exactly this shape: {"signal": "BUY|SELL|HOLD", "stop_loss": <number>, "exit_price": <number>, "forecast_5d": [{"day": <1-5>, "outlook": "<one sentence>", "expected_close": <number>}]}.'
);

---
-- Sink: one trade signal per (symbol, window_start) event from analysis_forecast.
-- forecast_5d is stored as the raw JSON array text returned by the model
-- (AI_COMPLETE only returns a STRING, so a nested array can't be typed further
-- without a UDF) - parse it downstream with JSON_QUERY/JSON_VALUE as needed.
CREATE TABLE `stock_quotes.trade_signal` (
  symbol STRING NOT NULL,
  window_start TIMESTAMP(3) NOT NULL,
  window_end TIMESTAMP(3) NOT NULL,
  -- Everything below through forecast_result is carried straight through
  -- from stock_quotes.analysis_forecast (quant_signal is its `signal` column,
  -- renamed to avoid colliding with this table's own LLM-generated `signal`).
  `open` DOUBLE,
  high DOUBLE,
  low DOUBLE,
  `close` DOUBLE,
  volume DOUBLE,
  volume_ticks BIGINT,
  sma DOUBLE,
  ema DOUBLE,
  rsi DOUBLE,
  macd DOUBLE,
  macd_signal DOUBLE,
  macd_hist DOUBLE,
  bb_lower DOUBLE,
  bb_mid DOUBLE,
  bb_upper DOUBLE,
  atr DOUBLE,
  obv DOUBLE,
  adx DOUBLE,
  di_plus DOUBLE,
  di_minus DOUBLE,
  sharpe DOUBLE,
  signal_score INT,
  signal_strength DOUBLE,
  quant_signal STRING,
  best_bid DOUBLE,
  best_ask DOUBLE,
  spread DOUBLE,
  forecast_result ROW<
    forecast ARRAY<ROW<`timestamp` TIMESTAMP(3), mean DOUBLE, q10 DOUBLE, q50 DOUBLE, q90 DOUBLE>>,
    metadata STRING
  >,
  context STRING,
  signal STRING,
  stop_loss DOUBLE,
  exit_price DOUBLE,
  forecast_5d STRING,
  PRIMARY KEY (symbol, window_start) NOT ENFORCED
)
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'delete',
  'kafka.retention.time' = '7d',
  'changelog.mode' = 'upsert',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry',
  'value.fields-include' = 'all'
);
---
-- Intermediate sink: the assembled prompt, one row per (symbol, window_start)
-- event, BEFORE it's handed to AI_COMPLETE.
--
-- Turns out an upsert-mode source is never enough on its own here: reading
-- ANY upsert table back always goes through ChangelogNormalize, which
-- reports changelogMode=[I,UB,UA,D] regardless of how clean the upsert key
-- is - and Flink refuses to run a non-deterministic function (AI_COMPLETE
-- calling the LLM) on a stream carrying any U/D, full stop, not just when the
-- key is untracked. So this table has to be append-mode, which in turn
-- requires the query populating it (below) to be genuinely insert-only from
-- source to `context`:
--   1. stock_quotes.analysis_forecast is itself altered to append (see
--      below) - reading an upsert table always reintroduces update messages
--      via ChangelogNormalize, even with zero joins/aggregates on top.
--   2. news_context/company_news_context build their summaries by indexing
--      straight into the VECTOR_SEARCH_AGG result array (hits[1]..hits[N])
--      instead of CROSS JOIN UNNEST + GROUP BY/ARRAY_AGG - an unbounded
--      GroupAggregate always emits update-before/update-after as rows
--      accumulate into a group, regardless of the source's changelog mode.
-- With both of those, the whole stage-1 pipeline is insert-only, so this
-- table can be append and stage 2 can read it as genuinely changelogMode=[I].
CREATE TABLE `stock_quotes.trade_signal_context` (
  symbol STRING NOT NULL,
  window_start TIMESTAMP(3) NOT NULL,
  window_end TIMESTAMP(3) NOT NULL,
  -- Carried straight through from stock_quotes.analysis_forecast so stage 2
  -- (and stock_quotes.trade_signal) doesn't have to re-join it back in.
  `open` DOUBLE,
  high DOUBLE,
  low DOUBLE,
  `close` DOUBLE,
  volume DOUBLE,
  volume_ticks BIGINT,
  sma DOUBLE,
  ema DOUBLE,
  rsi DOUBLE,
  macd DOUBLE,
  macd_signal DOUBLE,
  macd_hist DOUBLE,
  bb_lower DOUBLE,
  bb_mid DOUBLE,
  bb_upper DOUBLE,
  atr DOUBLE,
  obv DOUBLE,
  adx DOUBLE,
  di_plus DOUBLE,
  di_minus DOUBLE,
  sharpe DOUBLE,
  signal_score INT,
  signal_strength DOUBLE,
  quant_signal STRING,
  best_bid DOUBLE,
  best_ask DOUBLE,
  spread DOUBLE,
  forecast_result ROW<
    forecast ARRAY<ROW<`timestamp` TIMESTAMP(3), mean DOUBLE, q10 DOUBLE, q50 DOUBLE, q90 DOUBLE>>,
    metadata STRING
  >,
  context STRING,
  PRIMARY KEY (symbol, window_start) NOT ENFORCED
)
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'delete',
  'kafka.retention.time' = '7d',
  'changelog.mode' = 'append',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry',
  'value.fields-include' = 'all'
);
---

ALTER TABLE `stock_quotes.analysis_forecast` SET ('changelog.mode' = 'append')

---

SET 'sql.local-time-zone' = 'UTC';
SET 'sql.state-ttl' = '3 d';
SET 'sql.tables.scan.startup.mode' = 'latest-offset';

-- Stage 1/2 : assemble the context and materialize it into
-- stock_quotes.trade_signal_context (see that table's comment for why).
INSERT INTO `stock_quotes.trade_signal_context`
WITH context_base AS (
  -- One synchronous external lookup per event: the company's Markdown report,
  -- keyed by ticker == symbol, via the REST external table (KEY_SEARCH_AGG
  -- always returns a row with an array, empty if there's no match).
  SELECT
    af.*,
    CAST(cr.hits[1] AS ROW<ticker STRING, name STRING, report STRING>) AS company
  FROM `stock_quotes.analysis_forecast` af,
  LATERAL TABLE(
    KEY_SEARCH_AGG(companies_report, DESCRIPTOR(ticker), af.symbol,
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
  ) AS cr(hits)
),
query_embedding AS (
  -- Embed a short query describing what kind of news we want, so the vector
  -- search below returns the news most relevant to this ticker's current signal.
  -- The current date is folded into the query text (same "Date: ..." prefix
  -- convention used when embedding news_embedding in rag.sql) so the query
  -- lands, semantically, next to recently-dated articles instead of matching
  -- purely on topic regardless of how old the news is.
  SELECT
    cb.*,
    e.embedding AS query_embedding
  FROM context_base cb
  CROSS JOIN LATERAL TABLE(
    AI_EMBEDDING('palantir_embed',
      CONCAT(
        'Date: ', CAST(CURRENT_TIMESTAMP AS STRING), ' ',
        cb.symbol, ' ', COALESCE(cb.company.name, ''),
        ' stock news relevant to trading around a ', cb.signal, ' technical signal'
      ),
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10]
    )
  ) AS e(embedding)
),
company_news_query_embedding AS (
  -- Second, separate query: query_embedding's wording ("...technical signal")
  -- pulls back mostly Twitter chatter that already echoes today's quant
  -- signal. This one stays company-specific (ticker + name) but drops any
  -- mention of BULLISH/BEARISH/trading - and deliberately stays generic
  -- (no "earnings"/"layoffs"/etc. keyword list) so it isn't biased toward
  -- any one category of news and can surface whatever is actually out there,
  -- good or bad, even when it doesn't line up with the current technical
  -- signal. Filtered down in company_news_context below to the last 3 weeks
  -- so stale articles don't crowd out fresher ones (the source filter down
  -- to seeking-alpha/investing/wsj is currently disabled there).
  SELECT
    cb.*,
    e.embedding AS company_news_query_embedding
  FROM context_base cb
  CROSS JOIN LATERAL TABLE(
    AI_EMBEDDING('palantir_embed',
      CONCAT('Date: ', CAST(CURRENT_TIMESTAMP AS STRING), ' ',
        cb.symbol, ' ', COALESCE(cb.company.name, ''),
        ' recent news and developments about the company, positive or negative. Check only source seeking-alpha, investing or wsj'),
        MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10]
    )
  ) AS e(embedding)
),
news_context AS (
  -- Top-5 semantically closest news articles, built directly off the
  -- VECTOR_SEARCH_AGG result array by fixed index (hits[1]..hits[5]) instead
  -- of CROSS JOIN UNNEST + GROUP BY/ARRAY_AGG. That older shape put an
  -- unbounded GroupAggregate in the plan, which - regardless of whether the
  -- source is append or upsert - always emits update-before/update-after as
  -- rows accumulate into a group, in turn feeding an updating stream into
  -- AI_COMPLETE further down and tripping Flink's determinism check. Fixed
  -- array indexing keeps this a plain one-row-in/one-row-out Correlate+Calc,
  -- so the pipeline stays genuinely insert-only end to end.
  SELECT
    qe.*,
    CONCAT(
      CASE WHEN vs.hits[1] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[1].published_date, 3) AS STRING), '] ', vs.hits[1].title, CHR(10), SUBSTR(vs.hits[1].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[2] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[2].published_date, 3) AS STRING), '] ', vs.hits[2].title, CHR(10), SUBSTR(vs.hits[2].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[3] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[3].published_date, 3) AS STRING), '] ', vs.hits[3].title, CHR(10), SUBSTR(vs.hits[3].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[4] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[4].published_date, 3) AS STRING), '] ', vs.hits[4].title, CHR(10), SUBSTR(vs.hits[4].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[5] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[5].published_date, 3) AS STRING), '] ', vs.hits[5].title, CHR(10), SUBSTR(vs.hits[5].content, 1, 500), CHR(10), CHR(10)) ELSE '' END
    ) AS news_summary
  FROM query_embedding qe,
  LATERAL TABLE(
    VECTOR_SEARCH_AGG(palantir_vector_search, DESCRIPTOR(embeddings), qe.query_embedding, 5,
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
  ) AS vs(hits)
),
company_news_context AS (
  -- Same fixed-index approach as news_context, over the top-10 company-news
  -- search. The recency filter (was a WHERE after UNNEST) is now inline per
  -- index instead: an item outside the last 3 weeks just contributes ''.
  SELECT
    cne.symbol,
    cne.window_start,
    CONCAT(
      CASE WHEN vs.hits[1] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[1].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[1].published_date, 3) AS STRING), ' / ', vs.hits[1].source, '] ', vs.hits[1].title, CHR(10), SUBSTR(vs.hits[1].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[2] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[2].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[2].published_date, 3) AS STRING), ' / ', vs.hits[2].source, '] ', vs.hits[2].title, CHR(10), SUBSTR(vs.hits[2].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[3] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[3].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[3].published_date, 3) AS STRING), ' / ', vs.hits[3].source, '] ', vs.hits[3].title, CHR(10), SUBSTR(vs.hits[3].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[4] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[4].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[4].published_date, 3) AS STRING), ' / ', vs.hits[4].source, '] ', vs.hits[4].title, CHR(10), SUBSTR(vs.hits[4].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[5] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[5].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[5].published_date, 3) AS STRING), ' / ', vs.hits[5].source, '] ', vs.hits[5].title, CHR(10), SUBSTR(vs.hits[5].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[6] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[6].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[6].published_date, 3) AS STRING), ' / ', vs.hits[6].source, '] ', vs.hits[6].title, CHR(10), SUBSTR(vs.hits[6].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[7] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[7].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[7].published_date, 3) AS STRING), ' / ', vs.hits[7].source, '] ', vs.hits[7].title, CHR(10), SUBSTR(vs.hits[7].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[8] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[8].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[8].published_date, 3) AS STRING), ' / ', vs.hits[8].source, '] ', vs.hits[8].title, CHR(10), SUBSTR(vs.hits[8].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[9] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[9].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[9].published_date, 3) AS STRING), ' / ', vs.hits[9].source, '] ', vs.hits[9].title, CHR(10), SUBSTR(vs.hits[9].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[10] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[10].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[10].published_date, 3) AS STRING), ' / ', vs.hits[10].source, '] ', vs.hits[10].title, CHR(10), SUBSTR(vs.hits[10].content, 1, 500), CHR(10), CHR(10)) ELSE '' END
    ) AS company_news_summary
  FROM company_news_query_embedding cne,
  LATERAL TABLE(
    VECTOR_SEARCH_AGG(palantir_vector_search, DESCRIPTOR(embeddings), cne.company_news_query_embedding, 10,
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
  ) AS vs(hits)
),
prompt AS (
  SELECT
    nc.symbol,
    nc.window_start,
    nc.window_end,
    nc.`open`,
    nc.high,
    nc.low,
    nc.`close`,
    nc.volume,
    nc.volume_ticks,
    nc.sma,
    nc.ema,
    nc.rsi,
    nc.macd,
    nc.macd_signal,
    nc.macd_hist,
    nc.bb_lower,
    nc.bb_mid,
    nc.bb_upper,
    nc.atr,
    nc.obv,
    nc.adx,
    nc.di_plus,
    nc.di_minus,
    nc.sharpe,
    nc.signal_score,
    nc.signal_strength,
    nc.signal AS quant_signal,
    nc.best_bid,
    nc.best_ask,
    nc.spread,
    nc.forecast_result,
    CONCAT(
      -- Role, evidence-only constraint, and required JSON shape now live in
      -- palantir_trade_signal_llm's azureopenai.system_prompt - this just
      -- identifies which company this particular event is about.
      'Company: ', nc.symbol, ' (', COALESCE(nc.company.name, nc.symbol), ')', CHR(10), CHR(10),
      '## Company report', CHR(10), COALESCE(nc.company.report, 'No report available.'), CHR(10), CHR(10),
      '## Most relevant recent news', CHR(10), COALESCE(NULLIF(nc.news_summary, ''), 'No recent news available.'), CHR(10), CHR(10),
      '## Other company news (independent of the current technical signal)', CHR(10),
      COALESCE(NULLIF(cnc.company_news_summary, ''), 'No additional company news available.'), CHR(10), CHR(10),
      '## Technical indicators (15m candle at ', CAST(nc.window_start AS STRING), ')', CHR(10),
      'close=', COALESCE(CAST(nc.`close` AS STRING), 'n/a'),
      ', sma=', COALESCE(CAST(nc.sma AS STRING), 'n/a'),
      ', ema=', COALESCE(CAST(nc.ema AS STRING), 'n/a'),
      ', rsi=', COALESCE(CAST(nc.rsi AS STRING), 'n/a'),
      ', macd=', COALESCE(CAST(nc.macd AS STRING), 'n/a'),
      ', macd_signal=', COALESCE(CAST(nc.macd_signal AS STRING), 'n/a'),
      ', bb_lower=', COALESCE(CAST(nc.bb_lower AS STRING), 'n/a'),
      ', bb_mid=', COALESCE(CAST(nc.bb_mid AS STRING), 'n/a'),
      ', bb_upper=', COALESCE(CAST(nc.bb_upper AS STRING), 'n/a'),
      ', atr=', COALESCE(CAST(nc.atr AS STRING), 'n/a'),
      ', adx=', COALESCE(CAST(nc.adx AS STRING), 'n/a'),
      ', sharpe=', COALESCE(CAST(nc.sharpe AS STRING), 'n/a'),
      ', best_bid=', COALESCE(CAST(nc.best_bid AS STRING), 'n/a'),
      ', best_ask=', COALESCE(CAST(nc.best_ask AS STRING), 'n/a'),
      ', spread=', COALESCE(CAST(nc.spread AS STRING), 'n/a'),
      ', quant_signal=', nc.signal, ' (strength=', COALESCE(CAST(nc.signal_strength AS STRING), 'n/a'), ')',
      CHR(10), CHR(10),
      '## Model forecast (next step)', CHR(10),
      COALESCE(CAST(nc.forecast_result AS STRING), 'No forecast available.')
    ) AS context
  FROM news_context nc
  JOIN company_news_context cnc
    ON nc.symbol = cnc.symbol AND nc.window_start = cnc.window_start
)
SELECT
  p.symbol,
  p.window_start,
  p.window_end,
  p.`open`,
  p.high,
  p.low,
  p.`close`,
  p.volume,
  p.volume_ticks,
  p.sma,
  p.ema,
  p.rsi,
  p.macd,
  p.macd_signal,
  p.macd_hist,
  p.bb_lower,
  p.bb_mid,
  p.bb_upper,
  p.atr,
  p.obv,
  p.adx,
  p.di_plus,
  p.di_minus,
  p.sharpe,
  p.signal_score,
  p.signal_strength,
  p.quant_signal,
  p.best_bid,
  p.best_ask,
  p.spread,
  p.forecast_result,
  p.context
FROM prompt p;

---
-- Stage 2/2 : read the materialized context back and call AI_COMPLETE.
-- stock_quotes.trade_signal_context is append-mode, so this source is
-- genuinely changelogMode=[I] (no ChangelogNormalize at all) - that's what
-- lets AI_COMPLETE's non-deterministic output flow into the sink without
-- tripping the determinism check (an upsert-mode source, even with a clean
-- key, doesn't satisfy this - see that table's comment).
SET 'sql.local-time-zone' = 'UTC';
SET 'sql.tables.scan.startup.mode' = 'earliest-offset';

INSERT INTO `stock_quotes.trade_signal`
SELECT
  p.symbol,
  p.window_start,
  p.window_end,
  p.`open`,
  p.high,
  p.low,
  p.`close`,
  p.volume,
  p.volume_ticks,
  p.sma,
  p.ema,
  p.rsi,
  p.macd,
  p.macd_signal,
  p.macd_hist,
  p.bb_lower,
  p.bb_mid,
  p.bb_upper,
  p.atr,
  p.obv,
  p.adx,
  p.di_plus,
  p.di_minus,
  p.sharpe,
  p.signal_score,
  p.signal_strength,
  p.quant_signal,
  p.best_bid,
  p.best_ask,
  p.spread,
  p.forecast_result,
  p.context,
  JSON_VALUE(g.response, '$.signal') AS signal,
  CAST(JSON_VALUE(g.response, '$.stop_loss') AS DOUBLE) AS stop_loss,
  CAST(JSON_VALUE(g.response, '$.exit_price') AS DOUBLE) AS exit_price,
  JSON_QUERY(g.response, '$.forecast_5d') AS forecast_5d
FROM `stock_quotes.trade_signal_context` p,
LATERAL TABLE(AI_COMPLETE('palantir_trade_signal_llm', p.context,
 MAP['debug', true, 'client_timeout', 90, 'async_enabled', true, 'retry_count', 10])) AS g(response);


---
-- For testing purpose : full context for one company (stage 1 only).
-- Exact same CTE chain as the stage-1 INSERT above, just scoped to a single
-- symbol (WHERE af.symbol = 'NVDA' - swap the ticker to test another company)
-- and capped with LIMIT 1, since `stock_quotes.analysis_forecast` is an
-- unbounded stream. This is a plain SELECT (no AI_COMPLETE), so it's safe to
-- run standalone - read the assembled prompt here before spending a model
-- call on it.
WITH context_base AS (
  SELECT
    af.*,
    CAST(cr.hits[1] AS ROW<ticker STRING, name STRING, report STRING>) AS company
  FROM `stock_quotes.analysis_forecast` af,
  LATERAL TABLE(
    KEY_SEARCH_AGG(companies_report, DESCRIPTOR(ticker), af.symbol,
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
  ) AS cr(hits)
  WHERE af.symbol = 'IBM'
),
query_embedding AS (
  SELECT
    cb.*,
    e.embedding AS query_embedding
  FROM context_base cb
  CROSS JOIN LATERAL TABLE(
    AI_EMBEDDING('palantir_embed',
      CONCAT(
        'Date: ', CAST(CURRENT_TIMESTAMP AS STRING), ' ',
        cb.symbol, ' ', COALESCE(cb.company.name, ''),
        ' stock news relevant to trading around a ', cb.signal, ' technical signal'
      ),
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10]
    )
  ) AS e(embedding)
),
company_news_query_embedding AS (
  SELECT
    cb.*,
    e.embedding AS company_news_query_embedding
  FROM context_base cb
  CROSS JOIN LATERAL TABLE(
    AI_EMBEDDING('palantir_embed',
      CONCAT('Date: ', CAST(CURRENT_TIMESTAMP AS STRING), ' ',
        cb.symbol, ' ', COALESCE(cb.company.name, ''),
        ' recent news and developments about the company, positive or negative. Check only source seeking-alpha, investing or wsj'),
        MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10]
    )
  ) AS e(embedding)
),
news_context AS (
  SELECT
    qe.*,
    CONCAT(
      CASE WHEN vs.hits[1] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[1].published_date, 3) AS STRING), '] ', vs.hits[1].title, CHR(10), SUBSTR(vs.hits[1].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[2] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[2].published_date, 3) AS STRING), '] ', vs.hits[2].title, CHR(10), SUBSTR(vs.hits[2].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[3] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[3].published_date, 3) AS STRING), '] ', vs.hits[3].title, CHR(10), SUBSTR(vs.hits[3].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[4] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[4].published_date, 3) AS STRING), '] ', vs.hits[4].title, CHR(10), SUBSTR(vs.hits[4].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[5] IS NOT NULL THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[5].published_date, 3) AS STRING), '] ', vs.hits[5].title, CHR(10), SUBSTR(vs.hits[5].content, 1, 500), CHR(10), CHR(10)) ELSE '' END
    ) AS news_summary
  FROM query_embedding qe,
  LATERAL TABLE(
    VECTOR_SEARCH_AGG(palantir_vector_search, DESCRIPTOR(embeddings), qe.query_embedding, 5,
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
  ) AS vs(hits)
),
company_news_context AS (
  SELECT
    cne.symbol,
    cne.window_start,
    CONCAT(
      CASE WHEN vs.hits[1] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[1].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[1].published_date, 3) AS STRING), ' / ', vs.hits[1].source, '] ', vs.hits[1].title, CHR(10), SUBSTR(vs.hits[1].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[2] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[2].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[2].published_date, 3) AS STRING), ' / ', vs.hits[2].source, '] ', vs.hits[2].title, CHR(10), SUBSTR(vs.hits[2].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[3] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[3].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[3].published_date, 3) AS STRING), ' / ', vs.hits[3].source, '] ', vs.hits[3].title, CHR(10), SUBSTR(vs.hits[3].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[4] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[4].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[4].published_date, 3) AS STRING), ' / ', vs.hits[4].source, '] ', vs.hits[4].title, CHR(10), SUBSTR(vs.hits[4].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[5] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[5].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[5].published_date, 3) AS STRING), ' / ', vs.hits[5].source, '] ', vs.hits[5].title, CHR(10), SUBSTR(vs.hits[5].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[6] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[6].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[6].published_date, 3) AS STRING), ' / ', vs.hits[6].source, '] ', vs.hits[6].title, CHR(10), SUBSTR(vs.hits[6].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[7] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[7].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[7].published_date, 3) AS STRING), ' / ', vs.hits[7].source, '] ', vs.hits[7].title, CHR(10), SUBSTR(vs.hits[7].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[8] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[8].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[8].published_date, 3) AS STRING), ' / ', vs.hits[8].source, '] ', vs.hits[8].title, CHR(10), SUBSTR(vs.hits[8].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[9] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[9].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[9].published_date, 3) AS STRING), ' / ', vs.hits[9].source, '] ', vs.hits[9].title, CHR(10), SUBSTR(vs.hits[9].content, 1, 500), CHR(10), CHR(10)) ELSE '' END,
      CASE WHEN vs.hits[10] IS NOT NULL AND TO_TIMESTAMP_LTZ(vs.hits[10].published_date, 3) >= CURRENT_TIMESTAMP - INTERVAL '21' DAY THEN CONCAT('- [', CAST(TO_TIMESTAMP_LTZ(vs.hits[10].published_date, 3) AS STRING), ' / ', vs.hits[10].source, '] ', vs.hits[10].title, CHR(10), SUBSTR(vs.hits[10].content, 1, 500), CHR(10), CHR(10)) ELSE '' END
    ) AS company_news_summary
  FROM company_news_query_embedding cne,
  LATERAL TABLE(
    VECTOR_SEARCH_AGG(palantir_vector_search, DESCRIPTOR(embeddings), cne.company_news_query_embedding, 10,
      MAP['client_timeout', 90, 'async_enabled', true, 'retry_count', 10])
  ) AS vs(hits)
),
prompt AS (
  SELECT
    nc.symbol,
    nc.window_start,
    nc.window_end,
    CONCAT(
      -- Role, evidence-only constraint, and required JSON shape now live in
      -- palantir_trade_signal_llm's azureopenai.system_prompt - this just
      -- identifies which company this particular event is about.
      'Company: ', nc.symbol, ' (', COALESCE(nc.company.name, nc.symbol), ')', CHR(10), CHR(10),
      '## Company report', CHR(10), COALESCE(nc.company.report, 'No report available.'), CHR(10), CHR(10),
      '## Most relevant recent news', CHR(10), COALESCE(NULLIF(nc.news_summary, ''), 'No recent news available.'), CHR(10), CHR(10),
      '## Other company news (independent of the current technical signal)', CHR(10),
      COALESCE(NULLIF(cnc.company_news_summary, ''), 'No additional company news available.'), CHR(10), CHR(10),
      '## Technical indicators (15m candle at ', CAST(nc.window_start AS STRING), ')', CHR(10),
      'close=', COALESCE(CAST(nc.`close` AS STRING), 'n/a'),
      ', sma=', COALESCE(CAST(nc.sma AS STRING), 'n/a'),
      ', ema=', COALESCE(CAST(nc.ema AS STRING), 'n/a'),
      ', rsi=', COALESCE(CAST(nc.rsi AS STRING), 'n/a'),
      ', macd=', COALESCE(CAST(nc.macd AS STRING), 'n/a'),
      ', macd_signal=', COALESCE(CAST(nc.macd_signal AS STRING), 'n/a'),
      ', bb_lower=', COALESCE(CAST(nc.bb_lower AS STRING), 'n/a'),
      ', bb_mid=', COALESCE(CAST(nc.bb_mid AS STRING), 'n/a'),
      ', bb_upper=', COALESCE(CAST(nc.bb_upper AS STRING), 'n/a'),
      ', atr=', COALESCE(CAST(nc.atr AS STRING), 'n/a'),
      ', adx=', COALESCE(CAST(nc.adx AS STRING), 'n/a'),
      ', sharpe=', COALESCE(CAST(nc.sharpe AS STRING), 'n/a'),
      ', best_bid=', COALESCE(CAST(nc.best_bid AS STRING), 'n/a'),
      ', best_ask=', COALESCE(CAST(nc.best_ask AS STRING), 'n/a'),
      ', spread=', COALESCE(CAST(nc.spread AS STRING), 'n/a'),
      ', quant_signal=', nc.signal, ' (strength=', COALESCE(CAST(nc.signal_strength AS STRING), 'n/a'), ')',
      CHR(10), CHR(10),
      '## Model forecast (next step)', CHR(10),
      COALESCE(CAST(nc.forecast_result AS STRING), 'No forecast available.')
    ) AS context
  FROM news_context nc
  JOIN company_news_context cnc
    ON nc.symbol = cnc.symbol AND nc.window_start = cnc.window_start
)
SELECT
  p.symbol,
  p.window_start,
  p.window_end,
  p.context
FROM prompt p
LIMIT 1;

-- For testing purpose : generated signal for one company (stage 2 only).
-- Run the stage-1 test above first (or let the real stage-1 INSERT run
-- briefly) so at least one matching row exists in
-- `stock_quotes.trade_signal_context`, then run this.
SELECT
  p.symbol,
  p.window_start,
  p.context,
  JSON_VALUE(g.response, '$.signal') AS signal,
  CAST(JSON_VALUE(g.response, '$.stop_loss') AS DOUBLE) AS stop_loss,
  CAST(JSON_VALUE(g.response, '$.exit_price') AS DOUBLE) AS exit_price,
  JSON_QUERY(g.response, '$.forecast_5d') AS forecast_5d
FROM `stock_quotes.trade_signal_context` p,
LATERAL TABLE(AI_COMPLETE('palantir_trade_signal_llm', p.context)) AS g(response)
LIMIT 5;