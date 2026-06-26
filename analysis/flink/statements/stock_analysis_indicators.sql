---
-- Sink table: 1m candles enriched with technical indicators.
-- One row per (symbol, window_start), same grain as `stock_quotes.candles_1m`.
CREATE TABLE `stock_quotes.analysis` (
  symbol STRING NOT NULL,
  window_start TIMESTAMP(3) NOT NULL,
  window_end TIMESTAMP(3) NOT NULL,
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
  signal STRING,
  best_bid DOUBLE,
  best_ask DOUBLE,
  spread DOUBLE,
  PRIMARY KEY (symbol, window_start) NOT ENFORCED
)
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'delete',
  'kafka.retention.time' = '7d',
  -- upsert (not append): the LEFT JOIN with depth produces an updating stream
  -- (candle row first, enriched with spread when depth arrives). Upsert keyed by
  -- the PK keeps exactly one final row per (symbol, window_start).
  'changelog.mode' = 'upsert',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry',
  'value.fields-include' = 'all'
);
---
-- Register the Python UDF. Replace the artifact id with the one returned by
-- `confluent flink artifact create` (see README.md).
CREATE FUNCTION ta_indicators
  AS 'ta_udf.indicators.ta_indicators'
  LANGUAGE PYTHON
  USING JAR 'confluent-artifact://cfa-1ykjm3';
---
-- The aggregation + UDF call query lives in stock_candle_1m_ta_aggregate.sql.
-- Run it after the sink table and the function above have been created.

---
-- Test the UDF function
---
-- Smoke test: call ta_indicators with dummy OHLCV arrays (oldest -> newest).
-- 16 candles of a clean uptrend.
SELECT ta_indicators(
  CAST(ARRAY[100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115] AS ARRAY<DOUBLE>),       -- close
  CAST(ARRAY[100.5,101.5,102.5,103.5,104.5,105.5,106.5,107.5,108.5,109.5,110.5,111.5,112.5,113.5,114.5,115.5] AS ARRAY<DOUBLE>), -- high
  CAST(ARRAY[99.5,100.5,101.5,102.5,103.5,104.5,105.5,106.5,107.5,108.5,109.5,110.5,111.5,112.5,113.5,114.5] AS ARRAY<DOUBLE>),   -- low
  CAST(ARRAY[1000,1010,1020,1030,1040,1050,1060,1070,1080,1090,1100,1110,1120,1130,1140,1150] AS ARRAY<DOUBLE>)                   -- volume
) AS ind;
