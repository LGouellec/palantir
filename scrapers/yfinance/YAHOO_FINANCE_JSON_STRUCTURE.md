# Yahoo Finance JSON Structure

This document explains the JSON data structure returned by Yahoo Finance API and how the yfinance fetcher handles it.

## Overview

The Yahoo Finance API returns comprehensive company data through the `info` property of `yfinance.Ticker`. The yfinance fetcher **preserves the complete Yahoo Finance JSON response** while also adding normalized field names for backward compatibility.

## Data Fetching

```python
import yfinance as yf

# Get ticker
stock = yf.Ticker("MSFT")

# Get all company info (returns dict with Yahoo Finance JSON structure)
info = stock.info
```

## JSON Structure

The `info` dictionary contains 100+ fields organized into the following categories:

### 1. Company Information

```json
{
    "symbol": "MSFT",
    "shortName": "Microsoft Corporation",
    "longName": "Microsoft Corporation",
    "displayName": "Microsoft",
    
    "address1": "One Microsoft Way",
    "city": "Redmond",
    "state": "WA",
    "zip": "98052-6399",
    "country": "United States",
    "phone": "425 882 8080",
    "website": "https://www.microsoft.com",
    
    "industry": "Software - Infrastructure",
    "industryKey": "software-infrastructure",
    "industryDisp": "Software - Infrastructure",
    "sector": "Technology",
    "sectorKey": "technology",
    "sectorDisp": "Technology",
    
    "longBusinessSummary": "Microsoft Corporation develops...",
    "fullTimeEmployees": 228000
}
```

### 2. Company Officers (Executives)

Nested array of executive data:

```json
{
    "companyOfficers": [
        {
            "maxAge": 1,
            "name": "Mr. Satya Nadella",
            "age": 58,
            "title": "Chairman & CEO",
            "yearBorn": 1967,
            "fiscalYear": 2025,
            "totalPay": 12251294,
            "exercisedValue": 0,
            "unexercisedValue": 0
        },
        {
            "name": "Ms. Amy E. Hood",
            "title": "Executive VP & CFO",
            "totalPay": 4444191
        }
        // ... more officers
    ]
}
```

### 3. Price Data

```json
{
    "currentPrice": 418.57,
    "regularMarketPrice": 418.57,
    "previousClose": 419.09,
    "open": 419.48,
    "dayLow": 416.34,
    "dayHigh": 424.4,
    "bid": 418.41,
    "ask": 418.61,
    "bidSize": 2,
    "askSize": 1
}
```

### 4. Volume and Market Metrics

```json
{
    "volume": 22390344,
    "regularMarketVolume": 22390344,
    "averageVolume": 33775124,
    "averageVolume10days": 32895010,
    "averageDailyVolume10Day": 32895010,
    "averageDailyVolume3Month": 33775124
}
```

### 5. Market Cap and Shares

```json
{
    "marketCap": 3109320130560,
    "sharesOutstanding": 7428434704,
    "impliedSharesOutstanding": 7428434704,
    "floatShares": 7417440621,
    "sharesShort": 79107882,
    "sharesShortPriorMonth": 80991357,
    "sharesPercentSharesOut": 0.0106,
    "heldPercentInsiders": 0.0008,
    "heldPercentInstitutions": 0.75764,
    "shortRatio": 2.26,
    "shortPercentOfFloat": 0.0107
}
```

### 6. Valuation Ratios

```json
{
    "trailingPE": 24.944576,
    "forwardPE": 21.64525,
    "priceToBook": 7.504348,
    "priceToSalesTrailing12Months": 9.769349,
    "pegRatio": 1.29,
    "enterpriseValue": 3156523876352,
    "enterpriseToRevenue": 9.918,
    "enterpriseToEbitda": 17.113
}
```

### 7. Financial Metrics

```json
{
    "totalRevenue": 318272995328,
    "revenuePerShare": 42.836,
    "revenueGrowth": 0.183,
    "grossProfits": 217409994752,
    "grossMargins": 0.68309,
    "ebitda": 184457003008,
    "ebitdaMargins": 0.57956004,
    "operatingMargins": 0.46326,
    "profitMargins": 0.39341998,
    "earningsGrowth": 0.234,
    "netIncomeToCommon": 125215997952,
    "trailingEps": 16.78,
    "forwardEps": 19.33773,
    "epsCurrentYear": 16.81245
}
```

### 8. Balance Sheet Metrics

```json
{
    "bookValue": 55.777,
    "totalCash": 78227996672,
    "totalCashPerShare": 10.531,
    "totalDebt": 125431996416,
    "debtToEquity": 30.271,
    "quickRatio": 1.142,
    "currentRatio": 1.283
}
```

### 9. Cash Flow Metrics

```json
{
    "freeCashflow": 37011251200,
    "operatingCashflow": 170141007872
}
```

### 10. Returns and Efficiency

```json
{
    "returnOnAssets": 0.14814,
    "returnOnEquity": 0.34013999
}
```

### 11. Dividends

```json
{
    "dividendRate": 3.64,
    "dividendYield": 0.87,
    "exDividendDate": 1779321600,
    "payoutRatio": 0.20729999,
    "fiveYearAvgDividendYield": 0.79,
    "trailingAnnualDividendRate": 3.56,
    "trailingAnnualDividendYield": 0.008494595,
    "lastDividendValue": 0.91,
    "lastDividendDate": 1779321600,
    "dividendDate": 1781136000
}
```

### 12. 52-Week Range

```json
{
    "fiftyTwoWeekLow": 356.28,
    "fiftyTwoWeekHigh": 555.45,
    "fiftyTwoWeekLowChange": 62.29001,
    "fiftyTwoWeekLowChangePercent": 0.17483443,
    "fiftyTwoWeekRange": "356.28 - 555.45",
    "fiftyTwoWeekHighChange": -136.88,
    "fiftyTwoWeekHighChangePercent": -0.24643083,
    "fiftyTwoWeekChangePercent": -9.14281,
    "52WeekChange": -0.0914281,
    "SandP52WeekChange": 0.26208222
}
```

### 13. Moving Averages

```json
{
    "fiftyDayAverage": 400.441,
    "fiftyDayAverageChange": 18.128998,
    "fiftyDayAverageChangePercent": 0.04527258,
    "twoHundredDayAverage": 460.40125,
    "twoHundredDayAverageChange": -41.831238,
    "twoHundredDayAverageChangePercent": -0.09085822
}
```

### 14. All-Time Metrics

```json
{
    "allTimeHigh": 555.45,
    "allTimeLow": 0.088542
}
```

### 15. Analyst Metrics

```json
{
    "targetHighPrice": 870.0,
    "targetLowPrice": 400.0,
    "targetMeanPrice": 560.6302,
    "targetMedianPrice": 557.5,
    "recommendationMean": 1.30909,
    "recommendationKey": "strong_buy",
    "averageAnalystRating": "1.3 - Strong Buy",
    "numberOfAnalystOpinions": 54
}
```

### 16. Governance & Risk Metrics

```json
{
    "auditRisk": 9,
    "boardRisk": 7,
    "compensationRisk": 5,
    "shareHolderRightsRisk": 2,
    "overallRisk": 4,
    "governanceEpochDate": 1777593600,
    "compensationAsOfEpochDate": 1767139200
}
```

### 17. Earnings Dates

```json
{
    "earningsTimestamp": 1777492800,
    "earningsTimestampStart": 1785355200,
    "earningsTimestampEnd": 1785355200,
    "earningsCallTimestampStart": 1777498200,
    "earningsCallTimestampEnd": 1777498200,
    "isEarningsDateEstimate": true,
    "earningsQuarterlyGrowth": 0.231,
    "mostRecentQuarter": 1774915200
}
```

### 18. Fiscal Year Info

```json
{
    "lastFiscalYearEnd": 1751241600,
    "nextFiscalYearEnd": 1782777600
}
```

### 19. Exchange and Trading Info

```json
{
    "exchange": "NMS",
    "quoteType": "EQUITY",
    "fullExchangeName": "NasdaqGS",
    "messageBoardId": "finmb_21835",
    "market": "us_market",
    "marketState": "CLOSED",
    "exchangeTimezoneName": "America/New_York",
    "exchangeTimezoneShortName": "EDT",
    "gmtOffSetMilliseconds": -14400000,
    "tradeable": false,
    "cryptoTradeable": false,
    "hasPrePostMarketData": true,
    "firstTradeDateMilliseconds": 511108200000
}
```

### 20. Pre/Post Market Data

```json
{
    "postMarketTime": 1779494389,
    "postMarketPrice": 417.7939,
    "postMarketChange": -0.7760925,
    "postMarketChangePercent": -0.18541522,
    "regularMarketTime": 1779480000,
    "regularMarketChange": -0.519989,
    "regularMarketChangePercent": -0.12407574,
    "regularMarketDayRange": "416.34 - 424.4"
}
```

### 21. Split History

```json
{
    "lastSplitFactor": "2:1",
    "lastSplitDate": 1045526400
}
```

### 22. Metadata

```json
{
    "maxAge": 86400,
    "priceHint": 2,
    "currency": "USD",
    "financialCurrency": "USD",
    "language": "en-US",
    "region": "US",
    "typeDisp": "Equity",
    "quoteSourceName": "Nasdaq Real Time Price",
    "triggerable": true,
    "customPriceAlertConfidence": "HIGH",
    "sourceInterval": 15,
    "exchangeDataDelayedBy": 0,
    "esgPopulated": false,
    "corporateActions": []
}
```

### 23. Additional Fields

```json
{
    "beta": 1.093,
    "irWebsite": "http://www.microsoft.com/investor/default.aspx",
    "executiveTeam": [],
    "trailingPegRatio": 1.2904
}
```

## How the Fetcher Handles This Data

### 1. Complete Preservation

The fetcher **preserves ALL Yahoo Finance fields**:

```python
# yfinance.py line 61 (fetch_quote) and line 123 (fetch_fundamentals)
data = dict(info)  # Copies entire Yahoo Finance JSON
```

This means:
- ✅ `companyOfficers` array is preserved
- ✅ All address fields are preserved
- ✅ All governance metrics are preserved
- ✅ All 100+ Yahoo Finance fields are available

### 2. Normalized Fields

The fetcher **adds** standardized field names for consistency:

```python
data.update({
    "name": info.get("longName", info.get("shortName", "")),
    "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
    "market_cap": info.get("marketCap", 0),
    "pe_ratio": info.get("trailingPE", 0),
    "pb_ratio": info.get("priceToBook", 0),
    "sector": info.get("sector", ""),
    "industry": info.get("industry", ""),
    # ... more normalized fields
})
```

### 3. Field Access

You can access data in two ways:

**Yahoo Finance field names** (original):
```python
data["longName"]  # "Microsoft Corporation"
data["currentPrice"]  # 418.57
data["companyOfficers"]  # List of executives
data["longBusinessSummary"]  # Company description
```

**Normalized field names** (for compatibility):
```python
data["name"]  # "Microsoft Corporation"
data["current_price"]  # 418.57
data["sector"]  # "Technology"
data["industry"]  # "Software - Infrastructure"
```

Both sets of fields are available in the returned data!

## Example Usage

```python
from yfinance.data.fetcher.yfinance import YFinanceFetcher

fetcher = YFinanceFetcher()
result = fetcher.fetch_quote("MSFT")

if result.success:
    data = result.data
    
    # Access Yahoo Finance fields directly
    print(data["longName"])  # Microsoft Corporation
    print(data["currentPrice"])  # 418.57
    print(data["sector"])  # Technology
    
    # Access executive data
    for officer in data.get("companyOfficers", []):
        print(f"{officer['name']}: {officer['title']}")
        print(f"  Total Pay: ${officer.get('totalPay', 0):,.0f}")
    
    # Access governance metrics
    print(f"Overall Risk: {data.get('overallRisk', 'N/A')}")
    print(f"Audit Risk: {data.get('auditRisk', 'N/A')}")
    
    # Access all available fields
    print(f"Total fields: {len(data)}")
```

## Kafka Output

When publishing to Kafka, the **complete Yahoo Finance JSON** is included:

```json
{
    "ticker": "MSFT",
    "longName": "Microsoft Corporation",
    "currentPrice": 418.57,
    "companyOfficers": [
        {
            "name": "Mr. Satya Nadella",
            "title": "Chairman & CEO",
            "totalPay": 12251294
        }
    ],
    "sector": "Technology",
    "industry": "Software - Infrastructure",
    "longBusinessSummary": "Microsoft Corporation develops...",
    
    // ... all 100+ Yahoo Finance fields ...
    
    // Plus normalized fields
    "name": "Microsoft Corporation",
    "current_price": 418.57,
    "market_cap": 3109320130560
}
```

## Benefits

1. **Complete Data Access**: All Yahoo Finance fields are available
2. **Nested Structures Preserved**: `companyOfficers`, `executiveTeam`, etc.
3. **Backward Compatibility**: Normalized field names still work
4. **Future-Proof**: New Yahoo Finance fields automatically included
5. **Rich Executive Data**: Names, titles, ages, compensation details
6. **Governance Metrics**: Risk assessments and compliance data

## Field Mapping Reference

| Yahoo Finance Field | Normalized Field | Type |
|---------------------|------------------|------|
| `longName` | `name` | string |
| `currentPrice` / `regularMarketPrice` | `current_price` | float |
| `sharesOutstanding` / `impliedSharesOutstanding` | `shares_outstanding` | float |
| `marketCap` | `market_cap` | int |
| `trailingPE` | `pe_ratio` | float |
| `forwardPE` | `forward_pe` | float |
| `priceToBook` | `pb_ratio` | float |
| `priceToSalesTrailing12Months` | `ps_ratio` | float |
| `pegRatio` | `peg_ratio` | float |
| `dividendYield` | `dividend_yield` | float |
| `currency` | `currency` | string |
| `exchange` | `exchange` | string |
| `sector` | `sector` | string |
| `industry` | `industry` | string |

## See Also

- `yfinance.py` - Implementation
- [Yahoo Finance API Documentation](https://pypi.org/project/yfinance/)
- [yfinance GitHub](https://github.com/ranaroussi/yfinance)
