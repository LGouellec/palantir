---
CREATE TABLE reddit_posts_with_comments (
  post_id STRING,
  post_val ROW<
    id STRING,
    title STRING,
    author STRING,
    created_utc TIMESTAMP_LTZ(3),
    permalink STRING,
    url STRING,
    score BIGINT,
    upvote_ratio BIGINT,
    num_comments BIGINT,
    num_crossposts BIGINT,
    selftext STRING,
    post_type STRING,
    is_nsfw BOOLEAN,
    is_spoiler BOOLEAN,
    flair STRING,
    total_awards BIGINT,
    has_media BOOLEAN,
    media_downloaded BOOLEAN,
    source STRING,
    sentiment_score FLOAT,
    sentiment_label STRING,
    keywords STRING
  >,
  comments ARRAY<
    ROW<
      post_permalink STRING,
      comment_id STRING,
      parent_id STRING,
      author STRING,
      body STRING,
      score BIGINT,
      created_utc TIMESTAMP_LTZ(3),
      depth BIGINT,
      is_submitter BOOLEAN,
      sentiment_score FLOAT,
      sentiment_label STRING
    >
  >,
  PRIMARY KEY (post_id) NOT ENFORCED
)
DISTRIBUTED BY HASH(post_id)
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'compact',
  'changelog.mode' = 'upsert',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry'
);
---

SET 'sql.state-ttl'= '3 d';
SET 'sql.tables.scan.idle-timeout'= '30 s';
SET 'sql.tables.scan.startup.mode' ='earliest-offset';

INSERT INTO reddit_posts_with_comments
WITH comments_dedup AS (
  SELECT
    CAST(`key` AS STRING) AS comment_id,
    CAST(`val` AS STRING) AS comment_val,
    JSON_VALUE(CAST(`val` AS STRING), '$.parent_id' RETURNING STRING) as post_id
  FROM (
    SELECT
      `key`,
      `val`,
      $rowtime,
      ROW_NUMBER() OVER (
        PARTITION BY `key`
        ORDER BY $rowtime ASC
      ) AS rownum
    FROM `reddit-comments-raw`
  )
  WHERE rownum = 1
),

posts_dedup AS (
  SELECT
    CAST(`key` AS STRING) AS post_id,
    CAST(`val` AS STRING) AS post_val
  FROM (
    SELECT
      `key`,
      `val`,
      $rowtime,
      ROW_NUMBER() OVER (
        PARTITION BY `key`
        ORDER BY $rowtime ASC
      ) AS rownum
    FROM `reddit-posts-raw`
  )
  WHERE rownum = 1
)

SELECT
  p.post_id,
  CAST(
    ROW(
      JSON_VALUE(p.post_val, '$.id'),
      JSON_VALUE(p.post_val, '$.title'),
      JSON_VALUE(p.post_val, '$.author'),
      TO_TIMESTAMP_LTZ(
          REPLACE(
            REPLACE(JSON_VALUE(p.post_val, '$.created_utc'), 'T', ' '),
            '+00:00',
            ''
          ),
          'yyyy-MM-dd HH:mm:ss',
          'UTC'
        ),
      JSON_VALUE(p.post_val, '$.permalink'),
      JSON_VALUE(p.post_val, '$.url'),
      JSON_VALUE(p.post_val, '$.score' RETURNING INTEGER),
      JSON_VALUE(p.post_val, '$.upvote_ratio' RETURNING INTEGER),
      JSON_VALUE(p.post_val, '$.num_comments' RETURNING INTEGER),
      JSON_VALUE(p.post_val, '$.num_crossposts' RETURNING INTEGER),
      JSON_VALUE(p.post_val, '$.selftext'),
      JSON_VALUE(p.post_val, '$.post_type'),
      JSON_VALUE(p.post_val, '$.is_nsfw' RETURNING BOOLEAN),
      JSON_VALUE(p.post_val, '$.is_spoiler' RETURNING BOOLEAN),
      JSON_VALUE(p.post_val, '$.flair'),
      JSON_VALUE(p.post_val, '$.total_awards' RETURNING INTEGER),
      JSON_VALUE(p.post_val, '$.has_media' RETURNING BOOLEAN),
      JSON_VALUE(p.post_val, '$.media_downloaded' RETURNING BOOLEAN),
      JSON_VALUE(p.post_val, '$.source'),
      JSON_VALUE(p.post_val, '$.sentiment_score' RETURNING DOUBLE),
      JSON_VALUE(p.post_val, '$.sentiment_label'),
      JSON_VALUE(p.post_val, '$.keywords')
    )
    AS ROW<
      id STRING,
      title STRING,
      author STRING,
      created_utc TIMESTAMP_LTZ(3),
      permalink STRING,
      url STRING,
      score BIGINT,
      upvote_ratio BIGINT,
      num_comments BIGINT,
      num_crossposts BIGINT,
      selftext STRING,
      post_type STRING,
      is_nsfw BOOLEAN,
      is_spoiler BOOLEAN,
      flair STRING,
      total_awards BIGINT,
      has_media BOOLEAN,
      media_downloaded BOOLEAN,
      source STRING,
      sentiment_score FLOAT,
      sentiment_label STRING,
      keywords STRING
    >
  ) as post_val,
  ARRAY_AGG(
    CAST(
      ROW(
        JSON_VALUE(c.comment_val, '$.post_permalink'),
        JSON_VALUE(c.comment_val, '$.comment_id'),
        JSON_VALUE(c.comment_val, '$.parent_id'),
        JSON_VALUE(c.comment_val, '$.author'),
        JSON_VALUE(c.comment_val, '$.body'),
        JSON_VALUE(c.comment_val, '$.score' RETURNING INTEGER),
        TO_TIMESTAMP_LTZ(
          REPLACE(
            REPLACE(JSON_VALUE(c.comment_val, '$.created_utc'), 'T', ' '),
            '+00:00',
            ''
          ),
          'yyyy-MM-dd HH:mm:ss',
          'UTC'
        ),
        JSON_VALUE(c.comment_val, '$.depth' RETURNING INTEGER),
        JSON_VALUE(c.comment_val, '$.is_submitter' RETURNING BOOLEAN),
        JSON_VALUE(c.comment_val, '$.sentiment_score' RETURNING DOUBLE),
        JSON_VALUE(c.comment_val, '$.sentiment_label')
      )
      AS ROW<
        post_permalink STRING,
        comment_id STRING,
        parent_id STRING,
        author STRING,
        body STRING,
        score BIGINT,
        created_utc TIMESTAMP_LTZ(3),
        depth BIGINT,
        is_submitter BOOLEAN,
        sentiment_score FLOAT,
        sentiment_label STRING
      >
    )
    IGNORE NULLS
  ) AS comments
FROM posts_dedup p
LEFT JOIN comments_dedup c
  ON p.post_id = c.post_id
GROUP BY
  p.post_id,
  p.post_val;