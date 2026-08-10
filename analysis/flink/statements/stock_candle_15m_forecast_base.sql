-- =============================================================================
-- Stage 1/2 of the forecasting pipeline.
--
-- Splits the heavy work (OHLCV history arrays for ta_indicators + the
-- AI_FORECAST call) out of the final aggregate/indicators/depth statement,
-- so each Flink statement runs its own, lighter compute pool footprint.
-- This table is the source for stock_close_forecast.sql (stage 2), which
-- adds technical indicators, order-book depth, and filters.
--
-- Both window functions below read the same partition/order (symbol,
-- $rowtime), so they're computed in a single pass over `candles_15m` with
-- two named windows - no self-join needed to line the arrays up with the
-- forecast.
--   * w_arr: bounded ROWS window -> the last 200 candles per symbol, fed to
--     ta_indicators downstream.
--   * w_fc:  unbounded RANGE window required by AI_FORECAST, which manages
--     its own rolling context internally (see minContextSize/maxContextSize
--     below); state-ttl bounds how long Flink itself retains history.
-- =============================================================================

CREATE TABLE `stock_quotes.candles_15m_forecast_base` (
  symbol STRING NOT NULL,
  window_start TIMESTAMP(3) NOT NULL,
  window_end TIMESTAMP(3) NOT NULL,
  `open` DOUBLE,
  high DOUBLE,
  low DOUBLE,
  `close` DOUBLE,
  volume DOUBLE,
  volume_ticks BIGINT,
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
  -- Row-preserving window functions only (no aggregation, no join): exactly
  -- one output row per input row, so this can stay append-only like its
  -- source `candles_15m`.
  'changelog.mode' = 'append',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry',
  'value.fields-include' = 'all'
);
---
SET 'sql.local-time-zone' = 'UTC';
-- AI_FORECAST's maxContextSize below is 200 candles; at 15 minutes each
-- that's ~50h of history, so 3 days of state leaves comfortable margin.
SET 'sql.state-ttl' = '3 d';
SET 'sql.tables.scan.startup.mode' = 'earliest-offset';

INSERT INTO `stock_quotes.candles_15m_forecast_base`
SELECT
    symbol,
    window_start,
    window_end,
    `open`,
    high,
    low,
    `close`,
    volume,
    volume_ticks,
    AI_FORECAST(
      CAST(`close` AS DOUBLE),
      `$rowtime`,
      JSON_OBJECT(
        --'model' VALUE 'timesfm-2.5',
        'model' VALUE 'ttm',
        'minContextSize' VALUE 20,
        'maxContextSize' VALUE 200,
        'horizon' VALUE 1,
        'rmseWindowSize' VALUE 5
      )
    ) OVER (
      PARTITION BY symbol
      ORDER BY `$rowtime`
      RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS forecast_result
FROM `stock_quotes.candles_15m`