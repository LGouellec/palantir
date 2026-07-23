---
-- Merge vector_search + Company news from HTTP Endpoint + Current news + stock_analysis with a specific criteria (force du signal)
-- Appeler un modele IA avec un Agent (Determiner le prix + stop loss + exit)
-- plus Forecast
---

CREATE CONNECTION companies_rest_connection WITH (
  'type'     = 'rest',
  'endpoint' = 'https://YYYYY',
  'token' = 'XXXX'
);

CREATE TABLE companies_report (
  `ticker` STRING,
  `name` STRING,
  `report` STRING,
  PRIMARY KEY (ticker) NOT ENFORCED          
) WITH (
  'connector' = 'rest',
  'rest.connection' = 'companies_rest_connection',
  'rest.method' = 'POST',
  'rest.path' = 'companies/report'
);

-- For testing purpose
SELECT * FROM LATERAL TABLE (KEY_SEARCH_AGG(companies_report, DESCRIPTOR(ticker), 'STM'));

SELECT b.name, b.report FROM (
  SELECT CAST(report[1] as ROW<name STRING, report STRING>)
  FROM LATERAL TABLE (
    KEY_SEARCH_AGG(companies_report, DESCRIPTOR(ticker), 'NVDA')
  ) AS r(report)
) b