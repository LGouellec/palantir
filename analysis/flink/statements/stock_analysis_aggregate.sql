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
SET 'sql.state-ttl' = '3 d';
SET 'sql.tables.scan.startup.mode' ='earliest-offset';
-- SET 'sql.tables.scan.startup.mode' ='timestamp';
-- SET 'sql.tables.scan.startup.timestamp-millis' = '1782345600000';

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
  FROM `stock_quotes.candles_15m`
  WINDOW w AS (
    PARTITION BY symbol
    ORDER BY `$rowtime`
    ROWS BETWEEN 200 PRECEDING AND CURRENT ROW
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
),
-- Top-of-book depth aggregated to the same 1-minute tumbling windows as the
-- candles. spread = best_ask - best_bid (positive); averaged over the minute.
-- Position 1 of each array is the best level. (For the closing spread instead,
-- swap AVG(...) for LAST_VALUE(...) ordered by $rowtime.)
depth_1m AS (
  SELECT
    symbol,
    window_start,
    AVG(bids[1].price)                  AS best_bid,
    AVG(asks[1].price)                  AS best_ask,
    AVG(asks[1].price - bids[1].price)  AS spread
  FROM TABLE(
    TUMBLE(TABLE `stock_quotes.depth`, DESCRIPTOR($rowtime), INTERVAL '1' MINUTE)
  )
  WHERE symbol IS NOT NULL
    AND CARDINALITY(asks) > 0
    AND CARDINALITY(bids) > 0
  GROUP BY symbol, window_start, window_end
)
SELECT
  e.symbol,
  e.window_start,
  e.window_end,
  e.`open`,
  e.high,
  e.low,
  e.`close`,
  e.volume,
  e.volume_ticks,
  e.ind.sma,
  e.ind.ema,
  e.ind.rsi,
  e.ind.macd,
  e.ind.macd_signal,
  e.ind.macd_hist,
  e.ind.bb_lower,
  e.ind.bb_mid,
  e.ind.bb_upper,
  e.ind.atr,
  e.ind.obv,
  e.ind.adx,
  e.ind.di_plus,
  e.ind.di_minus,
  e.ind.sharpe,
  e.ind.signal_score,
  e.ind.signal_strength,
  e.ind.signal,
  d.best_bid,
  d.best_ask,
  d.spread
FROM enriched e
LEFT JOIN depth_1m d
  ON e.symbol = d.symbol
 AND e.window_start = d.window_start
WHERE 1=1
AND e.ind.ema IS NOT NULL
AND e.volume > 1000000
AND (e.ind.signal = 'BULLISH' OR e.ind.signal = 'BEARISH')
AND ((d.spread * 100) / e.`close`) < 0.25;