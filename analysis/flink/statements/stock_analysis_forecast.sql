-- =============================================================================
-- Stage 2/2 of the forecasting pipeline.
--
-- `stock_quotes.analysis` (stock_analysis_aggregate.sql) already computes
-- technical indicators + order-book depth from `stock_quotes.candles_15m`,
-- filtered down to rows with a BULLISH/BEARISH signal. Rather than
-- recomputing indicators/depth a second time here, this statement just joins
-- that already-curated table against the forecast produced in stage 1
-- (stock_candle_15m_forecast_base.sql) on (symbol, window_start) - no UDF
-- call, no depth aggregation, no windowed operator: just a keyed join.
-- =============================================================================

CREATE TABLE `stock_quotes.analysis_forecast` (
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
  forecast_result ROW<
    forecast ARRAY<ROW<`timestamp` TIMESTAMP(3), mean DOUBLE, q10 DOUBLE, q50 DOUBLE, q90 DOUBLE>>,
    metadata STRING
  >,
  PRIMARY KEY (symbol, window_start) NOT ENFORCED
)
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'delete',
  'kafka.retention.time' = '7d',
  -- upsert: a regular stream-stream join re-emits/retracts as either side
  -- updates. Upsert keyed by the PK keeps exactly one final row per
  -- (symbol, window_start).
  'changelog.mode' = 'upsert',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry',
  'value.fields-include' = 'all'
);
---
SET 'sql.local-time-zone' = 'UTC';
SET 'sql.state-ttl' = '3 d';
SET 'sql.tables.scan.startup.mode' = 'earliest-offset';

INSERT INTO `stock_quotes.analysis_forecast`
SELECT
  a.symbol,
  a.window_start,
  a.window_end,
  a.`open`,
  a.high,
  a.low,
  a.`close`,
  a.volume,
  a.volume_ticks,
  a.sma,
  a.ema,
  a.rsi,
  a.macd,
  a.macd_signal,
  a.macd_hist,
  a.bb_lower,
  a.bb_mid,
  a.bb_upper,
  a.atr,
  a.obv,
  a.adx,
  a.di_plus,
  a.di_minus,
  a.sharpe,
  a.signal_score,
  a.signal_strength,
  a.signal,
  a.best_bid,
  a.best_ask,
  a.spread,
  f.forecast_result
FROM `stock_quotes.analysis` a
INNER JOIN `stock_quotes.candles_15m_forecast_base` f
  ON a.symbol = f.symbol
 AND a.window_start = f.window_start
WHERE f.forecast_result.metadata IS NOT NULL;
