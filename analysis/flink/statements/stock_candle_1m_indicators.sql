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
-- Register the Python UDF. Replace the artifact id with the one returned by
-- `confluent flink artifact create` (see README.md).
CREATE FUNCTION ta_indicators
  AS 'ta_udf.indicators.ta_indicators'
  LANGUAGE PYTHON
  USING JAR 'confluent-artifact://<YOUR_ARTIFACT_ID>';
---
-- The aggregation + UDF call query lives in stock_candle_1m_ta_aggregate.sql.
-- Run it after the sink table and the function above have been created.
