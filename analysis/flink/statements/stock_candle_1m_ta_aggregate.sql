-- =============================================================================
-- Aggregate the trailing 100 candles per symbol and call the ta_indicators UDF.
--
-- Prerequisites (see stock_candle_1m_indicators.sql):
--   1. Sink table `stock_quotes.candles_1m_ta` exists.
--   2. The Python UDF is registered:  CREATE FUNCTION ta_indicators ...
--
-- How it works:
--   * A streaming OVER window keeps the last 100 rows per symbol. This is a
--     per-row SLIDING window: it emits one output row for EVERY candle (from
--     candle #1), not only after 100 have arrived. The "100" is the max frame
--     size, not a warm-up gate. Indicators that need more history (RSI-14,
--     MACD, ...) simply come back NULL from the UDF until enough candles exist.
--   * ARRAY_AGG collects each OHLCV channel into an ARRAY<DOUBLE>, oldest ->
--     newest (the window's ORDER BY direction).
--   * The scalar UDF receives the four arrays and returns a ROW of indicators
--     for the most recent candle; we flatten that ROW into the sink columns.
--
-- Note on ORDER BY: a streaming OVER window must be ordered by a *time
-- attribute*. `window_start` is a plain TIMESTAMP(3), so we order by the
-- `$rowtime` system column (the Kafka record timestamp Confluent Cloud exposes
-- as a watermarked time attribute on every table).
-- =============================================================================

SET 'sql.local-time-zone' = 'UTC';

INSERT INTO `stock_quotes.analysis`
WITH windowed AS (
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
    ARRAY_AGG(`close`) OVER w AS close_window,
    ARRAY_AGG(high)    OVER w AS high_window,
    ARRAY_AGG(low)     OVER w AS low_window,
    ARRAY_AGG(volume)  OVER w AS volume_window
  FROM `stock_quotes.candles_1m`
  WINDOW w AS (
    PARTITION BY symbol
    ORDER BY `$rowtime`
    ROWS BETWEEN 99 PRECEDING AND CURRENT ROW
  )
),
enriched AS (
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
    ta_indicators(close_window, high_window, low_window, volume_window) AS ind
  FROM windowed
)
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
  ind.sma,
  ind.ema,
  ind.rsi,
  ind.macd,
  ind.macd_signal,
  ind.macd_hist,
  ind.bb_lower,
  ind.bb_mid,
  ind.bb_upper,
  ind.atr,
  ind.obv,
  ind.adx,
  ind.di_plus,
  ind.di_minus,
  ind.sharpe,
  ind.signal_score,
  ind.signal_strength,
  ind.signal
FROM enriched
WHERE ind.ema IS NOT NULL;

-- =============================================================================
-- FALLBACK: if your Confluent Cloud Flink version rejects ARRAY_AGG inside an
-- OVER window (it is documented for GROUP BY but not explicitly for OVER), build
-- the trailing arrays with MATCH_RECOGNIZE instead, which is supported for
-- sequence/pattern collection, then feed `ta_indicators` exactly as above:
--
--   FROM `stock_quotes.candles_1m`
--   MATCH_RECOGNIZE (
--     PARTITION BY symbol
--     ORDER BY `$rowtime`
--     MEASURES
--       LAST(C.window_start) AS window_start,
--       LAST(C.window_end)   AS window_end,
--       LAST(C.`open`)       AS `open`,
--       LAST(C.high)         AS high,
--       LAST(C.low)          AS low,
--       LAST(C.`close`)      AS `close`,
--       LAST(C.volume)       AS volume,
--       LAST(C.volume_ticks) AS volume_ticks,
--       ARRAY_AGG(C.`close`) AS close_window,
--       ARRAY_AGG(C.high)    AS high_window,
--       ARRAY_AGG(C.low)     AS low_window,
--       ARRAY_AGG(C.volume)  AS volume_window
--     ONE ROW PER MATCH
--     AFTER MATCH SKIP TO NEXT ROW
--     PATTERN (C{1,100})        -- up to the last 100 candles
--     DEFINE C AS TRUE
--   )
-- The UDF tolerates short windows (returns NULLs until enough history exists).
-- =============================================================================
