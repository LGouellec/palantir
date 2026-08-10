---
SET 'sql.local-time-zone' = 'UTC';
SET 'sql.state-ttl'= '10 d';
SET 'sql.tables.scan.idle-timeout'= '30 s';
SET 'sql.tables.scan.startup.mode' ='earliest-offset';

INSERT INTO `news`

WITH stock_news_analyzed AS (
  SELECT
    CAST(sn.`id` AS STRING) AS news_id,
    sn.`summary` AS content,
    sn.`content` AS full_content,
    sn.`url` AS url,
    sn.`headline` AS title,
    TO_TIMESTAMP_LTZ(sn.`created_at`, 'yyyy-MM-dd''T''HH:mm:ss.SSSSSSXXX') AS published_date,
    sn.`symbols` AS category,
    sn.`source` AS source,
    AI_SENTIMENT(
      SUBSTR(sn.`headline` || CHR(10) || sn.`content`, 1, 600),
      ARRAY[
        'oil','positive','negative','neutral','finance','interest rates','economy','technology',
        'artificial-intelligence','security','stock market','stock crash','earnings',
        'merge and acquisition','layoffs','product launches','regulatory actions',
        'future expectations','past performance','SEC investigation','minor product update',
        'revenue miss','expectation miss','volatility','geopolitics',
        'losses, warnings, downgrades','growth, upgrades, expansion','fear','panic',
        'profit warning','beat expectations'
      ]
    ) AS r
  FROM `stock_news` sn
),
stock_news_analyzed_filtered AS (
  SELECT
    a.news_id,
    a.content,
    a.full_content,
    a.url,
    a.title,
    a.published_date,
    a.category,
    a.source,
    aspect,
    label,
    score
  FROM stock_news_analyzed a
  CROSS JOIN UNNEST(a.r.sentiment) AS s(aspect, label, score)
  WHERE UPPER(label) <> 'UNKNOWN'
)

SELECT
  af.news_id,
  af.content,
  SUBSTR(af.full_content, 1, 6000) AS full_content,
  CAST(
    ROW(
      ARRAY_AGG(
        CAST(
          ROW(af.aspect, af.label, af.score)
          AS ROW<aspect STRING, label STRING, score DOUBLE>
        )
      )
    )
    AS ROW<analysis ARRAY<ROW<aspect STRING, label STRING, score DOUBLE>>>
  ) AS sentiment,
  af.url,
  af.title,
  af.published_date,
  af.category,
  af.source
FROM stock_news_analyzed_filtered af
GROUP BY af.news_id, af.content, af.full_content, af.url, af.title, af.published_date, af.category, af.source;
