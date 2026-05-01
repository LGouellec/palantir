SELECT DECODE(a.`key`, 'UTF-8') as url, 
DECODE(a.`val`, 'UTF-8') as val,
AI_SENTIMENT(JSON_VALUE(DECODE(a.`val`, 'UTF-8'), '$.content_md'), 
ARRAY['positive', 'negative', 'neutral', 'finance', 'interest rates', 'economy', 'technology', 'artificial-intelligence', 'security', 'stock market', 'stock crash',
  'earnings', 'merge and acquisition', 'layoffs', 'product launches', 'regulatory actions', 'future expectations', 'past performance', 'SEC investigation', 'minor product update',
  'revenue miss', 'expectation miss', 'volatility', 'geopolitics', 'losses, warnings, downgrades', 'growth, upgrades, expansion', 'fear', 'panic', 'profit warning', 'beat expectations'
  ]) as sentiment 
FROM `wsj-articles` a 
LIMIT 30;