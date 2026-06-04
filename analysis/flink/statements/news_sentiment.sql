---
CREATE TABLE news (
  news_id STRING,
  content STRING,
  full_content STRING,
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
  PRIMARY KEY (news_id) NOT ENFORCED
)
DISTRIBUTED BY HASH(news_id) INTO 6 BUCKETS
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'compact',
  'changelog.mode' = 'upsert',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry'
);
---

SET 'sql.local-time-zone' = 'UTC';
SET 'sql.state-ttl'= '10 d';
SET 'sql.tables.scan.idle-timeout'= '30 s';
SET 'sql.tables.scan.startup.mode' ='earliest-offset';

INSERT INTO `news`

WITH reddit_exploded AS (
  SELECT
    t.`post_id` AS post_id,
    t.`post_val`.`title` AS title,
    t.`post_val`.`url` AS url,
    t.`post_val`.`created_utc` AS published_date, 
    body AS comment_body
  FROM `reddit_posts_with_comments` AS t
  CROSS JOIN UNNEST(t.comments) AS u (
    post_permalink,
    comment_id,
    parent_id,
    author,
    body,
    score,
    created_utc,
    depth,
    is_submitter,
    sentiment_score,
    sentiment_label
  )
),
reddit_grouped AS (
  SELECT
    post_id,
    title,
    url,
    published_date,
    ARRAY_AGG(comment_body) AS comment_bodies
  FROM reddit_exploded
  GROUP BY post_id, title, url, published_date
),
reddit_final AS (
  SELECT
    post_id,
    title,
    url,
    published_date,
    SPLIT(REGEXP_EXTRACT(url, 'https:\/\/www.reddit.com\/r\/([a-zA-Z0-9]+)\/', 1), ',') as category,
    title || CHR(10) || CHR(10) || ARRAY_JOIN(comment_bodies, CHR(10) || CHR(10)) AS full_content
  FROM reddit_grouped
  WHERE CARDINALITY(comment_bodies) > 0
),
merged_streams AS (
  SELECT 
  * 
  FROM (
    -- INVESTING
    SELECT
        JSON_VALUE(DECODE(i.`val`, 'UTF-8') , '$.id')  as news_id,
        JSON_VALUE(DECODE(i.`val`, 'UTF-8'), '$.content') as content,
        JSON_VALUE(DECODE(i.`val`, 'UTF-8'), '$.content_md') as full_content,
        JSON_VALUE(DECODE(i.`val`, 'UTF-8'), '$.url') as url,
        JSON_VALUE(DECODE(i.`val`, 'UTF-8'), '$.title') as title,
        TO_TIMESTAMP_LTZ(
          JSON_VALUE(DECODE(i.`val`, 'UTF-8'), '$.published_date'),
          'MM/dd/yyyy, hh:mm a',
          'UTC-04:00'
        ) AS published_date,
        SPLIT(JSON_VALUE(DECODE(i.`val`, 'UTF-8'), '$.category'), ',') as category,
        'investing' as source
      FROM `investing-news` i 
    UNION ALL 
    -- SEEKING ALPHA
    SELECT 
        REGEXP_EXTRACT(JSON_VALUE(DECODE(s.`val`, 'UTF-8'), '$.url'), '/news/([0-9]+)', 1) AS news_id,
        JSON_VALUE(DECODE(s.`val`, 'UTF-8'), '$.content') as content,
        JSON_VALUE(DECODE(s.`val`, 'UTF-8'), '$.content_md') as full_content,
        JSON_VALUE(DECODE(s.`val`, 'UTF-8'), '$.url') as url,
        JSON_VALUE(DECODE(s.`val`, 'UTF-8'), '$.title') as title,
        TO_TIMESTAMP_LTZ(
          REGEXP_REPLACE(
            JSON_VALUE(DECODE(s.`val`, 'UTF-8'), '$.published_date'),
            '([+-][0-9]{2}:[0-9]{2}|Z)$',
            ''
          ),
          'yyyy-MM-dd''T''HH:mm:ss',
          'UTC-04:00'
        ) as published_date,
        SPLIT(JSON_VALUE(DECODE(s.`val`, 'UTF-8'), '$.category'), ',') as category,
        'seeking-alpha' as source
      FROM `seeking-alpha-news` s
    UNION ALL
    -- WSJ
    SELECT
        REGEXP_EXTRACT(JSON_VALUE(DECODE(w.`val`, 'UTF-8'), '$.url'), '-([0-9a-f]{8})(?:[/?]|$)', 1) AS news_id,
        JSON_VALUE(DECODE(w.`val`, 'UTF-8'), '$.content') as content,
        JSON_VALUE(DECODE(w.`val`, 'UTF-8'), '$.content_md') as full_content,
        JSON_VALUE(DECODE(w.`val`, 'UTF-8'), '$.url') as url,
        JSON_VALUE(DECODE(w.`val`, 'UTF-8'), '$.title') as title,
        TO_TIMESTAMP_LTZ(
          JSON_VALUE(DECODE(w.`val`, 'UTF-8'), '$.published_date'),
          'yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''
        ) as published_date,
        SPLIT(REGEXP_EXTRACT(
          JSON_VALUE(DECODE(w.`val`, 'UTF-8'), '$.url'),
          'https://www\.wsj\.com/([^/]+)',
          1
        ), ',') as category,
        'wsj' as source
      FROM `wsj-articles` w
    UNION ALL
    -- REDDIT
    SELECT 
        r.post_id as news_id,
        r.full_content as content,
        r.full_content as full_content,
        r.url as url,
        r.title as title,
        r.published_date,
        r.category,
        'reddit' as source
      FROM reddit_final r
    UNION ALL
    -- TWITTER
    SELECT
        JSON_VALUE(DECODE(t.`val`, 'UTF-8') , '$.id')  as news_id,
        JSON_VALUE(DECODE(t.`val`, 'UTF-8'), '$.text') as content,
        JSON_VALUE(DECODE(t.`val`, 'UTF-8'), '$.content_md') as full_content,
        JSON_VALUE(DECODE(t.`val`, 'UTF-8'), '$.permanentUrl') as url,
        '' as title,
        TO_TIMESTAMP_LTZ(
          JSON_VALUE(DECODE(t.`val`, 'UTF-8'), '$.timeIso'),
          'yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''
        ) as published_date,
        SPLIT(JSON_VALUE(DECODE(t.`val`, 'UTF-8'), '$.source'), ',') as category,
        'twitter' as source
      FROM `twitter-tweets` t
  )
),
analyzed AS (
  SELECT
    m.news_id,
    m.content,
    m.full_content,
    m.url,
    m.title,
    m.published_date,
    m.category,
    m.source,
    AI_SENTIMENT(
      SUBSTR(m.title || CHR(10) || m.content, 1, 600),
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
  FROM merged_streams m
),
analyzed_filtered AS (
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
  FROM analyzed a
  CROSS JOIN UNNEST(a.r.sentiment) AS s(aspect, label, score)
  WHERE UPPER(label) <> 'UNKNOWN'
)

SELECT
  af.news_id,
  af.content,
  af.full_content,
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
FROM analyzed_filtered af
GROUP BY af.news_id, af.content, af.full_content, af.url, af.title, af.published_date, af.category, af.source;