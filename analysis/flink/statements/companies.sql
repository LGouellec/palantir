---
CREATE TABLE `companies` (
  `ticker` STRING,
  `name` STRING,
  `timestamp` TIMESTAMP_LTZ(3),
  `current_price` FLOAT,
  `previous_close` FLOAT,
  `open` FLOAT,
  `day_high` FLOAT,
  `day_low` FLOAT,
  `market_cap` FLOAT,
  `volume` BIGINT,
  `avg_volume_10d` BIGINT,
  `avg_50d` FLOAT,
  `recommendation_key` STRING,
  `shares_outstanding` BIGINT,
  `ratios` ROW<
        `pe` STRING,
        `eps`  STRING,
        `dividend_yield`  STRING,
        `beta` STRING
        >,
  `week_52` ROW<
        `high` FLOAT,
        `low` FLOAT
        >,
  `news` ARRAY<ROW<
    `category` STRING, 
    `confidence` DOUBLE,
    `content` STRING,  
    `impact_score` DOUBLE,
    `keywords` ARRAY<STRING>,
    `publish_date` STRING,
    `sentiment` STRING,
    `source` STRING,
    `title` STRING,
    `url` STRING
    >>,
  `sentiment` ROW<
    `sentiment_score` FLOAT,
    `confidence` FLOAT,
    `analyzer_type` STRING,
    `news_count_7d` INT,
    `news_count_30d` INT,
    `positive_count` INT,
    `neutral_count` INT,
    `negative_count` INT,
    `key_themes` ARRAY<STRING>,
    `risks` ARRAY<STRING>,
    `catalysts` ARRAY<STRING>,
    `sentiment_trend` STRING,
    `growth_sentiment` STRING,
    `dividend_safety` STRING
    >,
  `analyst_guidance` ARRAY<ROW<
    `analyst_count` DOUBLE,
    `eps_estimate` DOUBLE,
    `eps_high` DOUBLE,
    `eps_low` DOUBLE,
    `fiscal_year` DOUBLE,
    `quarter` DOUBLE,
    `rating` STRING,
    `rating_distribution` MAP<STRING, DOUBLE>,
    `revenue_estimate` DOUBLE,
    `revenue_high` DOUBLE,
    `revenue_low` DOUBLE,
    `updated_date` STRING>>,
  PRIMARY KEY (ticker) NOT ENFORCED
)
DISTRIBUTED BY HASH(ticker) INTO 3 BUCKETS
WITH (
  'kafka.consumer.isolation-level' = 'read-uncommitted',
  'kafka.cleanup-policy' = 'delete',
  'kafka.retention.time' = '7d',
  'changelog.mode' = 'append',
  'key.format' = 'json-registry',
  'value.format' = 'json-registry'
);
---
SET 'sql.local-time-zone' = 'UTC';
SET 'sql.tables.scan.startup.mode' ='earliest-offset';

INSERT INTO `companies`
  SELECT
  `ticker`,
  `company`.`name` AS `name`,
  TO_TIMESTAMP_LTZ(
    `timestamp`,
    'yyyy-MM-dd''T''HH:mm:ss.SSSSSS'
   ) AS `timestamp`,
  CAST(`price`.`current` AS FLOAT) AS `current_price`,
  CAST(`price`.`previous_close` AS FLOAT) AS `previous_close`,
  CAST(`price`.`open` AS FLOAT) AS `open`,
  CAST(`price`.`day_high` AS FLOAT) AS `day_high`,
  CAST(`price`.`day_low` AS FLOAT) AS `day_low`,
  CAST(`price`.`market_cap` AS BIGINT) AS `market_cap`,
  CAST(`price`.`volume` AS INT) `volume`,
  CAST(`price`.`avg_volume_10d` AS INT) AS `avg_volume_10d`,
  CAST(`price`.`avg_50d` AS FLOAT) AS `avg_50d`,
  `price`.`recommendation_key` `recommendation_key`,
  CAST(`company`.`shares_outstanding` AS BIGINT) AS `shares_outstanding`,
  CAST(
    ROW(
      CAST(`ratios`.`pe` AS STRING),
      CAST(`ratios`.`eps` AS STRING),
      CAST(`ratios`.`dividend_yield` AS STRING),
      CAST(`ratios`.`beta` AS STRING)
    )
    AS ROW<
      `pe` STRING,
      `eps` STRING,
      `dividend_yield` STRING,
      `beta` STRING
    >
  ) AS `ratios`,
  CAST(
    ROW(
      CAST(`week_52`.`high` AS FLOAT),
      CAST(`week_52`.`low` AS FLOAT)
    )
    AS ROW<
      `high` FLOAT,
      `low` FLOAT
    >
  ) AS `week_52`,
  `news`,
  CAST(
    ROW(
      CAST(`sentiment`.`sentiment_score` AS FLOAT),
      CAST(`sentiment`.`confidence` AS FLOAT),
      `sentiment`.`analyzer_type`,
      CAST(`sentiment`.`news_count_7d` AS INT),
      CAST(`sentiment`.`news_count_30d` AS INT),
      CAST(`sentiment`.`positive_count` AS INT),
      CAST(`sentiment`.`neutral_count` AS INT),
      CAST(`sentiment`.`negative_count` AS INT),
      CAST(`sentiment`.`key_themes` AS ARRAY<STRING>),
      CAST(`sentiment`.`risks` AS ARRAY<STRING>),
      CAST(`sentiment`.`catalysts` AS ARRAY<STRING>),
      `sentiment`.`sentiment_trend`,
      `sentiment`.`growth_sentiment`,
      `sentiment`.`dividend_safety`
    )
    AS ROW<
      `sentiment_score` FLOAT,
      `confidence` FLOAT,
      `analyzer_type` STRING,
      `news_count_7d` INT,
      `news_count_30d` INT,
      `positive_count` INT,
      `neutral_count` INT,
      `negative_count` INT,
      `key_themes` ARRAY<STRING>,
      `risks` ARRAY<STRING>,
      `catalysts` ARRAY<STRING>,
      `sentiment_trend` STRING,
      `growth_sentiment` STRING,
      `dividend_safety` STRING
    >
  ) AS `sentiment`,
  `analyst_guidance`

FROM `yahoo-news`;