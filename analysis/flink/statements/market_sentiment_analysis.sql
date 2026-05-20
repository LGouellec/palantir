SELECT DECODE(a.`key`, 'UTF-8') as url, 
DECODE(a.`val`, 'UTF-8') as val,
AI_SENTIMENT(JSON_VALUE(DECODE(a.`val`, 'UTF-8'), '$.content_md'), 
ARRAY['positive', 'negative', 'neutral', 'finance', 'interest rates', 'economy', 'technology', 'artificial-intelligence', 'security', 'stock market', 'stock crash',
  'earnings', 'merge and acquisition', 'layoffs', 'product launches', 'regulatory actions', 'future expectations', 'past performance', 'SEC investigation', 'minor product update',
  'revenue miss', 'expectation miss', 'volatility', 'geopolitics', 'losses, warnings, downgrades', 'growth, upgrades, expansion', 'fear', 'panic', 'profit warning', 'beat expectations'
  ]) as sentiment 
FROM `wsj-articles` a 
LIMIT 30;


SELECT AI_SENTIMENT(content, ARRAY['oil', 'positive', 'negative', 'neutral', 'finance', 'interest rates', 'economy', 'technology', 'artificial-intelligence', 'security', 'stock market', 'stock crash',
  'earnings', 'merge and acquisition', 'layoffs', 'product launches', 'regulatory actions', 'future expectations', 'past performance', 'SEC investigation', 'minor product update',
  'revenue miss', 'expectation miss', 'volatility', 'geopolitics', 'losses, warnings, downgrades', 'growth, upgrades, expansion', 'fear', 'panic', 'profit warning', 'beat expectations'])
FROM (VALUES ('U.S. crude-oil inventories increased, counter to what was expected by surveyed analysts, according to data released Wednesday by the Energy Information Administration.\n\nCommercial crude-oil stockpiles, excluding the Strategic Petroleum Reserve, rose by 6.2 million barrels to 449.3 million barrels in the week ended March 13, and were 1% below the five-year average for the time of year, the EIA said')) AS NameTable(content) 



[
  oil,Negative,0.6381080746650696,
  positive,UNKNOWN,0.0,
  negative,UNKNOWN,0.0,
  neutral,UNKNOWN,0.0,
  finance,UNKNOWN,0.0, 
  interest rates,UNKNOWN,0.0,
  economy,UNKNOWN,0.0,
  technology,UNKNOWN,0.0,
  artificial-intelligence,UNKNOWN,0.0,
  security,UNKNOWN,0.0,
  stock market,UNKNOWN,0.0,
  stock crash,UNKNOWN,0.0,
  earnings,UNKNOWN,0.0,
  merge and acquisition,UNKNOWN,0.0,
  layoffs,UNKNOWN,0.0,
  product launches,UNKNOWN,0.0,
  regulatory actions,UNKNOWN,0.0,
  future expectations,UNKNOWN,0.0,
  past performance,UNKNOWN,0.0,
  SEC investigation,UNKNOWN,0.0,
  minor product update,UNKNOWN,0.0,
  revenue miss,UNKNOWN,0.0,
  expectation miss,UNKNOWN,0.0,
  volatility,UNKNOWN,0.0,
  geopolitics,UNKNOWN,0.0,
  losses,
  warnings,
  downgrades,UNKNOWN,0.0,
  growth, upgrades, expansion,UNKNOWN,0.0,
  fear,UNKNOWN,0.0,
  panic,UNKNOWN,0.0,
  profit warning,UNKNOWN,0.0,
  beat expectations,UNKNOWN,0.0],{num_aspects=30}