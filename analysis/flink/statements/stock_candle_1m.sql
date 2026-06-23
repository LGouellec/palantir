---
CREATE TABLE `stock_quotes.candles_1m` (
  symbol STRING NOT NULL,
  window_start TIMESTAMP(3) NOT NULL,
  window_end TIMESTAMP(3) NOT NULL,
  `open` DOUBLE,
  high DOUBLE,
  low DOUBLE,
  `close` DOUBLE,
  volume DOUBLE,
  volume_ticks BIGINT,
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
SET 'sql.local-time-zone' = 'UTC';

WITH hilo AS (
  SELECT
    symbol,
    window_start,
    window_end,
    MAX(last_done) AS high,
    MIN(last_done) AS low,
    COUNT(*) AS volume_ticks
  FROM TABLE(
    TUMBLE(
      TABLE `stock_quotes.realtime`,
      DESCRIPTOR($rowtime),
      INTERVAL '1' MINUTE
    )
  )
  WHERE symbol IS NOT NULL
    AND last_done IS NOT NULL
  GROUP BY symbol, window_start, window_end
),

open_tick AS (
  SELECT
    symbol,
    window_start,
    window_end,
    last_done AS `open`,
    volume AS open_volume
  FROM (
    SELECT
      symbol,
      last_done,
      volume,
      $rowtime,
      window_start,
      window_end,
      ROW_NUMBER() OVER (
        PARTITION BY symbol, window_start, window_end
        ORDER BY $rowtime ASC
      ) AS rownum
    FROM TABLE(
      TUMBLE(
        TABLE `stock_quotes.realtime`,
        DESCRIPTOR($rowtime),
        INTERVAL '1' MINUTE
      )
    )
    WHERE symbol IS NOT NULL
      AND last_done IS NOT NULL
  )
  WHERE rownum = 1
),

close_tick AS (
  SELECT
    symbol,
    window_start,
    window_end,
    last_done AS `close`,
    volume AS close_volume
  FROM (
    SELECT
      symbol,
      last_done,
      volume,
      $rowtime,
      window_start,
      window_end,
      ROW_NUMBER() OVER (
        PARTITION BY symbol, window_start, window_end
        ORDER BY $rowtime DESC
      ) AS rownum
    FROM TABLE(
      TUMBLE(
        TABLE `stock_quotes.realtime`,
        DESCRIPTOR($rowtime),
        INTERVAL '1' MINUTE
      )
    )
    WHERE symbol IS NOT NULL
      AND last_done IS NOT NULL
  )
  WHERE rownum = 1
)

INSERT INTO `stock_quotes.candles_1m`
SELECT
  h.symbol,
  h.window_start,
  h.window_end,
  o.`open`,
  h.high,
  h.low,
  c.`close`,
  c.close_volume AS volume,
  h.volume_ticks
FROM hilo h
JOIN open_tick o
  ON h.symbol = o.symbol
 AND h.window_start = o.window_start
 AND h.window_end = o.window_end
JOIN close_tick c
  ON h.symbol = c.symbol
 AND h.window_start = c.window_start
 AND h.window_end = c.window_end;
