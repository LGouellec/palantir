# YFinance Async Analytics Engine

A high-performance async analytics fetcher for Yahoo Finance stock data, designed for real-time monitoring of 100+ stocks concurrently.

## Features

### Core Fetching
- **Concurrent fetching**: Fetch 100+ stocks in parallel using asyncio
- **Rate limiting**: Built-in semaphore-based rate limiting (default: 20 concurrent requests)
- **Automatic retry with exponential backoff**: Handles 429 errors, network issues, and transient failures
- **Complete data capture**: Retains ALL yfinance data (100+ fields) including:
  - Real-time quotes (price, market cap, PE/PB ratios)
  - Fundamental data (financials, balance sheet, cash flow)
  - Company news and press releases
  - Analyst guidance and recommendations
  - Historical price data with analytics (CAGR, volatility, max drawdown)
  - Valuation metrics (F-Score components, historical PE/PB)
  - Dividends history, splits, institutional holdings, insider transactions
  - Quarterly statements, options data, and all raw info fields
- **Graceful error handling**: Individual stock failures don't break batch operations
- **NASDAQ ticker list**: Fetch official ticker lists from NASDAQ FTP server (3000+ stocks)

### Real-Time Monitoring
- **Built-in scheduler**: Automatic data refresh at configurable intervals
- **Batch monitoring**: Monitor 1000+ stocks with weighted rotation
- **Preferred tickers**: Priority fetching for your watchlist (3x weight)
- **Callback system**: Real-time notifications when data updates
- **Market hours awareness**: Respects market hours (7:30 AM - 6:00 PM ET, weekdays)

### Proxy & Rate Limiting
- **Proxy rotation**: Distribute requests across multiple SOCKS5 proxies
- **SOCKS5 support**: Works with Yahoo Finance (HTTP proxies are blocked)
- **Health checking**: Automatic failover to healthy proxies
- **Per-proxy rate limiting**: Configurable limits per proxy
- **Retry statistics**: Track and monitor rate limit issues

### News & Sentiment
- **News fetching**: Company news and press releases from Yahoo Finance
- **Sentiment analysis**: Keyword-based or LLM-based sentiment analysis
- **Impact scoring**: Categorize news by impact and confidence
- **Key themes**: Extract themes, catalysts, and risks from news

### Integration & CLI
- **Kafka integration**: Publish stock updates to Kafka topics (optional)
- **Command-line runner**: Full-featured CLI with configurable parameters
- **WebSocket testing**: Test real-time streaming with yfinance WebSocket API
- **Docker support**: Production-ready Docker images and compose files

## Architecture

### Components

```
scrapers/yfinance/
├── runner.py                     # CLI entry point with argparse
├── analytics_engine.py           # Main async orchestrator
├── models.py                     # Data models (StockAnalytics, StockQuote, etc.)
├── proxy_rotator.py              # SOCKS5 proxy rotation with health checking
├── nasdaq_tickers.py             # NASDAQ ticker list fetcher
├── kafka_callback.py             # Kafka integration for real-time publishing
├── test_websocket.py             # WebSocket real-time streaming test
├── data/fetcher/
│   ├── base.py                   # Sync base classes
│   ├── yfinance.py               # Sync YFinance implementation (SOCKS5 proxy support)
│   ├── async_base.py             # Async base classes
│   └── async_yfinance.py         # Async YFinance wrapper
├── news/
│   ├── base.py                   # News data models
│   ├── fetcher/
│   │   ├── base.py               # Sync news fetcher base
│   │   ├── yfinance.py           # Sync news fetcher (news + press releases)
│   │   ├── async_base.py         # Async news fetcher base
│   │   └── async_yfinance.py     # Async news wrapper
│   └── analyzer/
│       ├── base.py               # Sentiment analyzer base
│       ├── keyword.py            # Keyword-based sentiment
│       └── llm.py                # LLM-based sentiment (OpenAI)
```

### Design Decisions

**Why `asyncio.to_thread()` instead of aiohttp?**
- YFinance handles complex scraping and API discovery
- Yahoo Finance endpoints aren't publicly documented
- Reimplementing would be fragile and time-consuming
- `asyncio.to_thread()` provides true concurrency without blocking the event loop

**Rate Limiting**
- **Proactive rate limiting**: Token bucket algorithm prevents 429 errors before they happen
- **Concurrent limiting**: Semaphore limits parallel requests (default: 20)
- **Requests per second**: Smoothly limits request rate (default: 20 req/s)
- Allows bursts up to 2× rate while maintaining average over time
- Configurable via `max_concurrent` and `max_requests_per_second` parameters
- Prevents IP bans and ensures stable performance

## Installation

### Local Installation

```bash
cd scrapers/yfinance
pip install -r requirements.txt
```

**Requirements:**
- Python 3.9+ (for `asyncio.to_thread()`)
- yfinance >= 1.3.0 (for WebSocket support)
- pandas >= 2.0.0
- curl-cffi >= 0.6.0 (for SOCKS5 proxy support)
- certifi >= 2023.0.0 (for SSL certificates)
- confluent-kafka >= 2.0.0 (optional, for Kafka integration)
- openai >= 1.0.0 (optional, for LLM-based sentiment analysis)

### Docker Installation (Recommended)

**Quick Start:**
```bash
make build
make run
make logs
```

**With Kafka:**
```bash

See documentation, see **[README.md](../README.md)**

## Logging

The library uses Python's standard `logging` module. Configure logging in your application:

```python
import logging

# Basic configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Or configure specific loggers
logging.getLogger('analytics_engine').setLevel(logging.DEBUG)
logging.getLogger('nasdaq_tickers').setLevel(logging.INFO)
```

**Log levels:**
- `DEBUG`: Detailed information (cache hits, individual fetches)
- `INFO`: General information (monitoring status, ticker counts)
- `WARNING`: Retry attempts, non-critical issues
- `ERROR`: Critical errors in monitor loop

## Usage

### Quick Start: Command-Line Runner

The easiest way to start monitoring stocks is with the command-line runner:

```bash
# Basic monitoring (50 stocks, 30-second refresh)
python runner.py

# Monitor with news and sentiment
python runner.py --include-news --analyze-sentiment

# Monitor with Kafka publishing
python runner.py --kafka --batch-size 50 --interval-ms 30000

# Full configuration
python runner.py \
  --batch-size 100 \
  --interval-ms 60000 \
  --include-news \
  --news-days 7 \
  --analyze-sentiment \
  --sentiment-analyzer keyword \
  --kafka
```

**Command-line options:**
- `--batch-size N`: Number of stocks to fetch per iteration (default: 50)
- `--interval-ms MS`: Refresh interval in milliseconds (default: 30000 = 30s)
- `--include-news` / `--no-news`: Enable/disable news fetching (default: enabled)
- `--news-days N`: Days of news to fetch (default: 20)
- `--analyze-sentiment` / `--no-sentiment`: Enable/disable sentiment analysis (default: enabled)
- `--sentiment-analyzer {keyword,llm}`: Sentiment analyzer type (default: keyword)
- `--kafka`: Enable Kafka publishing (default: disabled)

**What it does:**
1. Loads prefered ticker list if `PREFERED_TICKERS_PATH` is set
2. Fetches all NASDAQ-listed stocks
3. Randomizes ticker order to avoid patterns
4. Starts batch monitoring with preferred tickers (3x weight)
5. Publishes updates to Kafka (if `--kafka` enabled)
6. Respects market hours (7:30 AM - 6:00 PM ET, weekdays)

**Custom ticker list:**

Edit `top_stocks.txt` to customize your watchlist:
```
AAPL
GOOGL
MSFT
NVDA
...
```

Set the env variable `PREFERED_TICKERS_PATH`

### Programmatic Usage

For custom integrations, use the engine directly:

#### Single Stock Analytics

```python
import asyncio
from analytics_engine import AsyncAnalyticsEngine

async def main():
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    
    result = await engine.fetch_stock_analytics(
        "AAPL",
        include_news=True,
        news_days=7,
        include_history=True,
        history_period="1y",
    )
    
    print(f"Price: ${result['data']['current_price']:.2f}")
    print(f"PE Ratio: {result['data']['pe_ratio']:.2f}")
    print(f"News: {len(result['news'])} articles")

asyncio.run(main())
```

### Batch Analytics (100+ Stocks)

```python
async def main():
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    
    tickers = ["AAPL", "GOOGL", "MSFT", ...]  # 100+ tickers
    
    results = await engine.fetch_batch_analytics(
        tickers,
        include_news=True,
        news_days=30,
    )
    
    for ticker, data in results.items():
        if data.get("errors"):
            print(f"{ticker}: ERROR - {data['errors'][0]}")
        else:
            price = data['data']['current_price']
            pe = data['data']['pe_ratio']
            print(f"{ticker}: ${price:.2f} | PE: {pe:.2f}")

asyncio.run(main())
```

### Batch Summary

```python
async def main():
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    
    tickers = [...]  # List of 100+ tickers
    
    summary = await engine.fetch_batch_summary(tickers)
    
    print(f"Total: {summary['total_stocks']}")
    print(f"Successful: {summary['successful']}")
    print(f"Failed: {summary['failed']}")
    
    # Access individual stock data
    for ticker, stock in summary['stocks'].items():
        print(f"{ticker}: ${stock['current_price']:.2f}")

asyncio.run(main())
```

### Real-time Monitoring (Scheduler)

Monitor stocks with automatic refresh at configurable intervals:

```python
import asyncio
from analytics_engine import AsyncAnalyticsEngine

async def main():
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    
    # Define a callback for price updates
    def on_update(ticker, data):
        price = data['data']['current_price']
        pe = data['data']['pe_ratio']
        print(f"📈 {ticker}: ${price:.2f} | PE: {pe:.2f}")
    
    # Register callback
    engine.add_update_callback(on_update)
    
    # Start monitoring with 30-second refresh
    engine.start_monitoring(
        tickers=["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"],
        interval_ms=30000,  # Refresh every 30 seconds
        include_news=False,
        include_history=False,
    )
    
    print(f"Monitoring {len(engine.monitored_tickers)} stocks...")
    
    try:
        # Run for 5 minutes
        await asyncio.sleep(300)
        
        # Access cached data anytime
        aapl_data = await engine.get_cached_data("AAPL")
        if aapl_data:
            print(f"\nLatest AAPL: ${aapl_data['data']['current_price']:.2f}")
        
    finally:
        await engine.stop_monitoring()

asyncio.run(main())
```

**Portfolio Monitoring Example:**

```python
async def monitor_portfolio():
    # Your portfolio
    portfolio = {
        "AAPL": 10,    # 10 shares
        "GOOGL": 5,    # 5 shares
        "NVDA": 8,     # 8 shares
    }
    
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    
    # Callback to track portfolio value
    def portfolio_update(ticker, data):
        price = data['data']['current_price']
        shares = portfolio[ticker]
        value = price * shares
        print(f"💼 {ticker}: {shares} × ${price:.2f} = ${value:,.2f}")
    
    engine.add_update_callback(portfolio_update)
    
    # Monitor portfolio with 1-minute refresh
    engine.start_monitoring(
        tickers=list(portfolio.keys()),
        interval_ms=60000,  # 1 minute
        include_news=False,
    )
    
    try:
        while True:
            await asyncio.sleep(60)
            
            # Calculate total portfolio value
            all_data = await engine.get_all_cached_data()
            total = sum(
                all_data[ticker]['data']['current_price'] * shares
                for ticker, shares in portfolio.items()
                if ticker in all_data
            )
            print(f"\n💰 Total Portfolio: ${total:,.2f}\n")
            
    except KeyboardInterrupt:
        await engine.stop_monitoring()

asyncio.run(monitor_portfolio())
```

### NASDAQ Ticker List

Fetch the official list of all NASDAQ-listed stocks from the FTP server (ftp.nasdaqtrader.com):

```python
async def main():
    engine = AsyncAnalyticsEngine()
    
    # Fetch all NASDAQ tickers from FTP server
    tickers = await engine.fetch_nasdaq_tickers(
        include_nasdaq=True,  # NASDAQ-listed stocks
        include_nyse=True,    # NYSE-listed stocks
        include_amex=True,    # AMEX-listed stocks
        include_etf=False,    # Exclude ETFs (default: False)
        cache_ttl_hours=24,   # Cache for 24 hours
    )
    
    print(f"Found {len(tickers)} stocks")
    print(f"First 20: {tickers[:20]}")
    
    # Access cached list later
    if engine.nasdaq_tickers:
        print(f"Cached: {len(engine.nasdaq_tickers)} tickers")

asyncio.run(main())
```

**Monitor all NASDAQ stocks with preferred tickers:**

```python
async def main():
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    
    # Fetch complete ticker list
    all_tickers = await engine.fetch_nasdaq_tickers()
    
    # Define your watchlist (will be fetched first)
    my_watchlist = ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA", "META"]
    
    # Start monitoring all stocks (3000+)
    # ⚠️  This will make ~3000 requests every refresh interval
    engine.start_monitoring(
        tickers=all_tickers,
        interval_ms=60000,  # 60 seconds
        include_news=False,
        include_history=False,
        preferred_tickers=my_watchlist,  # Fetch these first
    )
    
    # Add callback to track high-volume stocks
    def volume_alert(ticker, data):
        stock_data = data['data']
        volume = stock_data.get('volume', 0)
        avg_volume = stock_data.get('avg_volume_10d', 1)
        
        # Alert if volume > 2x average
        if volume > avg_volume * 2:
            print(f"🔔 {ticker}: High volume! {volume:,} ({volume/avg_volume:.1f}x avg)")
    
    engine.add_update_callback(volume_alert)
    
    try:
        await asyncio.sleep(3600)  # Monitor for 1 hour
    finally:
        await engine.stop_monitoring()

asyncio.run(main())
```

**Note:** When monitoring large lists (3000+ stocks), use `preferred_tickers` to ensure your watchlist is fetched first before rate limiting throttles requests. This guarantees your most important stocks are always up-to-date.

**Features:**
- Downloads from official NASDAQ FTP server (ftp.nasdaqtrader.com)
- Parses both NASDAQ and other exchanges (NYSE, AMEX)
- Filters test symbols, preferred stocks, and ETFs (configurable)
- Local caching with configurable TTL (default: 24 hours)
- Async-friendly using `asyncio.to_thread()`

**Files:**
- `nasdaqlisted.txt` - NASDAQ-listed stocks
- `otherlisted.txt` - NYSE, AMEX, and other exchanges

## Sentiment Analysis

Analyze sentiment of news articles using keyword-based or LLM-based analyzers.

### Keyword-Based Analyzer

Fast, free, and works offline. Uses predefined word lists to classify sentiment:

```python
result = await engine.fetch_stock_analytics(
    "AAPL",
    include_news=True,
    news_days=7,
    analyze_sentiment=True,
    sentiment_analyzer="keyword",  # Default
)

# Access sentiment data
sa = result['sentiment_analysis']
print(f"Sentiment Score: {sa['sentiment_score']:.3f}")  # -1.0 to 1.0
print(f"Positive: {sa['positive_count']}")
print(f"Negative: {sa['negative_count']}")
print(f"Neutral: {sa['neutral_count']}")
print(f"Key Themes: {sa['key_themes']}")
print(f"Catalysts: {sa['catalysts']}")
print(f"Risks: {sa['risks']}")

# Each news item has sentiment
for news in result['news']:
    print(f"{news['sentiment']}: {news['title']}")
    print(f"  Confidence: {news['confidence']:.2f}")
    print(f"  Impact: {news['impact_score']:.2f}")
    print(f"  Category: {news['category']}")
```

**Pros:**
- ✅ Fast (no API calls)
- ✅ Free (no costs)
- ✅ Works offline
- ✅ Consistent results

**Cons:**
- ❌ Less accurate than LLM
- ❌ Misses context/sarcasm
- ❌ Limited to keyword matching

### LLM-Based Analyzer

High-quality sentiment analysis using OpenAI GPT models:

```python
import os

result = await engine.fetch_stock_analytics(
    "AAPL",
    include_news=True,
    news_days=3,  # Fewer to reduce API costs
    analyze_sentiment=True,
    sentiment_analyzer="llm",
    llm_api_key=os.environ.get("OPENAI_API_KEY"),
    llm_model="gpt-4o-mini",  # Fast and cheap
    # llm_base_url="https://api.openai.com/v1",  # Optional: custom endpoint
)

# LLM provides additional insights
sa = result['sentiment_analysis']
print(f"Sentiment Trend: {sa['sentiment_trend']}")  # improving, deteriorating, stable
print(f"Growth Outlook: {sa['growth_sentiment']}")  # positive, negative, neutral
print(f"Dividend Safety: {sa['dividend_safety']}")  # stable, at_risk, improving
```

**Pros:**
- ✅ Highly accurate
- ✅ Understands context
- ✅ Provides insights (trends, outlook)
- ✅ Better categorization

**Cons:**
- ❌ Requires API key
- ❌ Costs money (per article)
- ❌ Slower (API calls)
- ❌ Requires internet connection

### Batch Sentiment Analysis

Analyze sentiment for multiple stocks:

```python
results = await engine.fetch_batch_analytics(
    ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"],
    include_news=True,
    news_days=7,
    analyze_sentiment=True,
    sentiment_analyzer="keyword",  # or "llm"
    llm_api_key=os.environ.get("OPENAI_API_KEY"),  # if using LLM
)

# Compare sentiment across stocks
for ticker, data in results.items():
    if 'sentiment_analysis' in data:
        sa = data['sentiment_analysis']
        print(f"{ticker}: {sa['sentiment_score']:.3f}")
```

### Monitoring with Sentiment

Real-time sentiment monitoring:

```python
def sentiment_alert(ticker, data):
    if 'sentiment_analysis' in data:
        sa = data['sentiment_analysis']
        if sa['sentiment_score'] < -0.5:
            print(f"⚠️  {ticker}: Negative sentiment detected!")
            print(f"   Risks: {', '.join(sa['risks'])}")

engine.add_update_callback(sentiment_alert)

engine.start_monitoring(
    tickers=["AAPL", "GOOGL", "MSFT"],
    interval_ms=60000,
    include_news=True,
    news_days=7,
    analyze_sentiment=True,
    sentiment_analyzer="keyword",
)
```

### Cost Considerations (LLM)

**Keyword analyzer:** Free, no API costs

**LLM analyzer costs (using gpt-4o-mini):**
- ~$0.000150 per article analyzed
- Example: 100 articles = ~$0.015 (1.5 cents)
- Example: 1000 articles = ~$0.15 (15 cents)

**Tips to reduce LLM costs:**
1. Use `news_days=3` or less (fewer articles)
2. Use `gpt-4o-mini` (cheapest, fastest)
3. Monitor fewer stocks
4. Use keyword analyzer for initial screening, LLM for deep dives


## API Reference

### `AsyncAnalyticsEngine`

#### `__init__(max_concurrent=20, max_requests_per_second=20.0, max_retries=3, base_retry_delay=1.0, max_retry_delay=60.0)`
Initialize the analytics engine.

**Parameters:**
- `max_concurrent`: Maximum concurrent requests (default: 20)
- `max_requests_per_second`: Maximum requests per second (default: 20.0)
  - Uses token bucket algorithm for smooth rate limiting
  - Allows bursts up to 2× rate while maintaining average
  - Set to 0 to disable rate limiting (not recommended)
- `max_retries`: Maximum retry attempts for failed requests (default: 3)
- `base_retry_delay`: Base delay in seconds for exponential backoff (default: 1.0)
- `max_retry_delay`: Maximum retry delay in seconds (default: 60.0)

**Example:**
```python
# Conservative rate limiting for high-volume monitoring
engine = AsyncAnalyticsEngine(
    max_concurrent=15,
    max_requests_per_second=15.0,  # Proactive rate limiting
    max_retries=5,
)

# Aggressive (risk 429 errors)
engine = AsyncAnalyticsEngine(
    max_concurrent=30,
    max_requests_per_second=30.0,
)

# Disable rate limiting (not recommended)
engine = AsyncAnalyticsEngine(
    max_concurrent=20,
    max_requests_per_second=0,  # No rate limiting
)
```

#### `fetch_stock_analytics(ticker, include_news=True, news_days=30, include_history=False, history_period="5y")`
Fetch complete analytics for a single stock.

**Parameters:**
- `ticker`: Stock ticker symbol
- `include_news`: Fetch news and analyst guidance (default: True)
- `news_days`: Days of news to fetch (default: 30)
- `include_history`: Fetch historical price data (default: False)
- `history_period`: Period for history ("1y", "2y", "5y", "10y", "max")

**Returns:** Dictionary with:
- `ticker`: Stock ticker
- `fetch_time`: ISO timestamp
- `data`: Quote and fundamental data
- `news`: List of news items (if `include_news=True`)
- `guidance`: List of analyst guidance (if `include_news=True`)
- `history`: Historical analytics (if `include_history=True`)
- `errors`: List of errors

#### `fetch_batch_analytics(tickers, include_news=True, news_days=30, include_history=False, history_period="5y", preferred_tickers=None)`
Fetch analytics for multiple stocks concurrently.

**Parameters:**
- `tickers`: List of ticker symbols
- `preferred_tickers`: Optional list of tickers to fetch first (default: None)
- Other parameters same as `fetch_stock_analytics()`

**Returns:** Dict mapping ticker → analytics data

**Note:** When `preferred_tickers` is provided, those tickers are fetched first before other tickers. This is useful when monitoring large lists (e.g., all NASDAQ stocks) and you want to ensure important stocks are fetched first.

#### `fetch_batch_summary(tickers)`
Fetch analytics for multiple stocks and return aggregated summary.

**Parameters:**
- `tickers`: List of ticker symbols

**Returns:** Dictionary with:
- `total_stocks`: Total count
- `successful`: Successful fetches
- `failed`: Failed fetches
- `stocks`: Dict of ticker → simplified data (price, PE, market cap)
- `errors`: Dict of ticker → error list

#### `fetch_nasdaq_tickers(include_nasdaq=True, include_nyse=True, include_amex=True, include_etf=False, cache_ttl_hours=24)` (async)
Fetch list of all NASDAQ-listed stocks from FTP server.

Downloads ticker lists from ftp.nasdaqtrader.com and caches them locally.

**Parameters:**
- `include_nasdaq`: Include NASDAQ-listed stocks (default: True)
- `include_nyse`: Include NYSE-listed stocks (default: True)
- `include_amex`: Include AMEX-listed stocks (default: True)
- `include_etf`: Include ETFs in the results (default: False)
- `cache_ttl_hours`: Cache validity in hours (default: 24)

**Returns:** List of ticker symbols (e.g., `["AAPL", "GOOGL", "MSFT", ...]`)

**Example:**
```python
tickers = await engine.fetch_nasdaq_tickers()
print(f"Found {len(tickers)} stocks")

# Start monitoring all NASDAQ stocks
engine.start_monitoring(tickers, interval_ms=60000)
```

#### `nasdaq_tickers` (property)
Get cached NASDAQ ticker list. Returns `None` if `fetch_nasdaq_tickers()` hasn't been called yet.

**Example:**
```python
if engine.nasdaq_tickers:
    print(f"Cached {len(engine.nasdaq_tickers)} tickers")
```

### Scheduler Methods (Real-time Monitoring)

#### `start_monitoring(tickers, interval_ms=60000, include_news=True, news_days=7, include_history=False, preferred_tickers=None, batch_size=None)`
Start automatic refresh of stock data at specified intervals.

**Parameters:**
- `tickers`: List of ticker symbols to monitor
- `interval_ms`: Refresh interval in milliseconds (default: 60000 = 1 minute)
- `include_news`: Fetch news with each refresh (default: True)
- `news_days`: Days of news to fetch (default: 7)
- `include_history`: Fetch historical data (default: False)
- `preferred_tickers`: Optional list of tickers with 3x weight (default: None)
- `batch_size`: Optional batch size per iteration (default: None = fetch all)

**Modes:**

1. **Full Mode** (default, `batch_size=None`): Fetch all tickers on each refresh
2. **Batch Mode** (`batch_size=N`): Fetch N tickers per iteration with rotation

**Batch Mode Benefits:**
- Monitor 1000+ stocks without overwhelming rate limits
- Preferred tickers get 3x weight (fetched 3x more frequently)
- Spreads load over time while keeping watchlist ultra-fresh

**Example:**
```python
# Full mode: fetch all tickers each time
engine.start_monitoring(
    tickers=["AAPL", "GOOGL", "MSFT"],
    interval_ms=30000,  # Refresh every 30 seconds
    include_news=False,  # Skip news for faster refresh
)

# Batch mode: monitor 3000 stocks in batches of 100
# Preferred stocks fetched 3x more often!
engine.start_monitoring(
    tickers=all_nasdaq_tickers,  # ~3000 stocks
    batch_size=100,  # Fetch 100 per iteration
    preferred_tickers=["AAPL", "GOOGL", "MSFT", "NVDA"],  # 3x weight
    interval_ms=60000,  # Every 60 seconds
)
# Result: Preferred stocks updated every ~60s
#         Other stocks updated every ~30 minutes (3000/100 = 30 iterations)
```

#### `stop_monitoring()`
Stop the monitoring scheduler (async method).

**Example:**
```python
await engine.stop_monitoring()
```

#### `add_update_callback(callback)`
Add a callback function that fires when stock data is refreshed.

**Parameters:**
- `callback`: Function with signature `callback(ticker: str, data: Dict[str, Any])`
  - Can be sync or async function

**Example:**
```python
def on_price_update(ticker, data):
    price = data['data']['current_price']
    print(f"{ticker}: ${price:.2f}")

engine.add_update_callback(on_price_update)
```

#### `get_cached_data(ticker)` (async)
Get the latest cached data for a specific ticker.

**Returns:** Analytics data dict or None

**Example:**
```python
data = await engine.get_cached_data("AAPL")
if data:
    print(f"Price: ${data['data']['current_price']:.2f}")
```

#### `get_all_cached_data()` (async)
Get all cached stock data.

**Returns:** Dict mapping ticker → analytics data

**Example:**
```python
all_data = await engine.get_all_cached_data()
for ticker, data in all_data.items():
    print(f"{ticker}: ${data['data']['current_price']:.2f}")
```

#### Properties

- `is_monitoring`: Boolean indicating if monitoring is active
- `monitored_tickers`: List of currently monitored tickers
- `refresh_interval_ms`: Current refresh interval in milliseconds

### Retry & Rate Limit Methods

#### `get_retry_stats()`
Get statistics about retry attempts and rate limit errors.

**Returns:** Dictionary with:
- `total_requests`: Total number of requests made
- `total_retries`: Total number of retry attempts
- `rate_limit_errors`: Number of 429 errors encountered
- `failed_after_retries`: Requests that failed after all retries
- `retry_rate`: Percentage of requests that required retries
- `success_rate`: Percentage of requests that eventually succeeded

**Example:**
```python
stats = engine.get_retry_stats()
print(f"429 errors: {stats['rate_limit_errors']}")
print(f"Retry rate: {stats['retry_rate']:.1f}%")
print(f"Success rate: {stats['success_rate']:.1f}%")
```

#### `reset_retry_stats()`
Reset retry statistics counters to zero.

**Example:**
```python
engine.reset_retry_stats()
# ... run operations ...
stats = engine.get_retry_stats()  # Stats only from recent operations
```

#### `get_rate_limiter_stats()`
Get current rate limiter status and available capacity.

**Returns:** Dictionary with:
- `enabled`: Whether rate limiting is enabled
- `max_requests_per_second`: Configured rate limit
- `available_tokens`: Current tokens available (can make this many requests immediately)
- `capacity`: Maximum tokens (burst capacity)

**Example:**
```python
stats = engine.get_rate_limiter_stats()
if stats['enabled']:
    print(f"Rate limit: {stats['max_requests_per_second']} req/s")
    print(f"Available burst: {stats['available_tokens']:.2f} requests")
    print(f"Max burst: {stats['capacity']:.2f} requests")
else:
    print("Rate limiting disabled")
```

**Use case:** Monitor if rate limiting is actively throttling requests.
- If `available_tokens` is near 0, requests are being throttled
- If `available_tokens` is near `capacity`, no throttling is happening

## Rate Limit Handling

The engine uses a **two-tier rate limiting strategy** to prevent and handle rate limits:

### Tier 1: Proactive Rate Limiting (Prevention)

**Token Bucket Algorithm** prevents 429 errors before they happen:

1. **Smooth rate limiting**: Spaces out requests to maintain average requests/second
2. **Burst tolerance**: Allows short bursts (up to 2× rate) without throttling
3. **Automatic pacing**: Waits for tokens before starting requests
4. **No wasted retries**: Prevents rate limit errors in the first place

**How it works:**
- Bucket starts with tokens (default: 40 tokens = 2× rate)
- Each request consumes 1 token
- Tokens refill at configured rate (default: 20 tokens/second)
- If no tokens available, waits until one is available
- Allows bursts when bucket is full, but maintains average rate

**Example:** With `max_requests_per_second=20.0`:
- Can immediately burst 40 requests (2× capacity)
- Then throttles to 20 requests/second average
- Bucket refills over time when idle

### Tier 2: Reactive Retry Logic (Recovery)

If rate limits still occur (e.g., external throttling), **exponential backoff** handles recovery:

1. **Detection**: Automatically detects retryable errors:
   - HTTP 429 (Too Many Requests)
   - HTTP 503 (Service Unavailable)
   - Network/connection errors
   - Timeout errors

2. **Retry Strategy**: Exponential backoff with jitter
   - First retry: ~1 second
   - Second retry: ~2 seconds
   - Third retry: ~4 seconds
   - Maximum delay: 60 seconds (configurable)
   - Jitter: ±25% randomization to avoid thundering herd

3. **Logging**: Logs retry attempts:
   ```
   WARNING - Data fetch for AAPL failed (attempt 1/4): 429 Too Many Requests
   INFO - Retrying in 1.23s...
   ```

### Configuration Examples

```python
# Conservative (avoid rate limits, high reliability)
engine = AsyncAnalyticsEngine(
    max_concurrent=10,               # Lower concurrency
    max_requests_per_second=10.0,    # Conservative rate limit
    max_retries=5,                   # More retries
    base_retry_delay=2.0,            # Longer initial delay
    max_retry_delay=60.0,            # Higher max delay
)

# Aggressive (faster, may hit limits occasionally)
engine = AsyncAnalyticsEngine(
    max_concurrent=30,               # Higher concurrency
    max_requests_per_second=30.0,    # Aggressive rate limit
    max_retries=3,                   # Standard retries
    base_retry_delay=0.5,            # Shorter delay
    max_retry_delay=30.0,            # Lower max delay
)

# Balanced (recommended, good for most use cases)
engine = AsyncAnalyticsEngine(
    max_concurrent=20,               # Default
    max_requests_per_second=20.0,    # Default (proactive limiting)
    max_retries=3,                   # Default
    base_retry_delay=1.0,            # Default
    max_retry_delay=60.0,            # Default
)
```

### Best Practices

1. **Monitor retry rates**: Check `get_retry_stats()` regularly
   ```python
   stats = engine.get_retry_stats()
   if stats['retry_rate'] > 20:  # More than 20% retries
       print("⚠️  High retry rate - consider reducing max_concurrent")
   ```

2. **Adjust concurrency**: If seeing many 429 errors, reduce `max_concurrent`

3. **Use scheduler wisely**: Don't set refresh intervals too aggressively
   - 30-60 seconds: Good for real-time monitoring
   - < 15 seconds: Risk of rate limits

4. **Handle persistent failures**: If `failed_after_retries` is high, investigate:
   ```python
   stats = engine.get_retry_stats()
   if stats['failed_after_retries'] > 10:
       print("⚠️  Many persistent failures - check network/API status")
   ```

### Example: Monitoring Retry Stats

```python
import asyncio
from analytics_engine import AsyncAnalyticsEngine

async def monitor_with_stats():
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    
    # Fetch 50 stocks
    tickers = [...]  # 50 tickers
    results = await engine.fetch_batch_analytics(tickers)
    
    # Check retry statistics
    stats = engine.get_retry_stats()
    print(f"📊 Retry Statistics:")
    print(f"  Total requests: {stats['total_requests']}")
    print(f"  429 errors: {stats['rate_limit_errors']}")
    print(f"  Retry rate: {stats['retry_rate']:.1f}%")
    
    if stats['rate_limit_errors'] > 0:
        print(f"  ⚠️  Encountered rate limits - consider reducing concurrency")

asyncio.run(monitor_with_stats())
```

## Data Structure

### Quote + Fundamentals Data

```python
{
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "current_price": 175.50,
    "market_cap": 2750000000000,
    "pe_ratio": 28.5,
    "pb_ratio": 45.2,
    "dividend_yield": 0.005,
    "eps": 6.15,
    "bvps": 3.88,
    "revenue": 394328000000,
    "net_income": 96995000000,
    "fcf": 99584000000,
    "roe": 145.5,
    "sector": "Technology",
    "industry": "Consumer Electronics",
    # ... 50+ additional fields
}
```

### News Data

```python
{
    "title": "Apple Announces New Product Line",
    "content": "Apple Inc. today announced...",
    "source": "Reuters",
    "publish_date": "2026-05-06T10:30:00",
    "url": "https://..."
}
```

### Analyst Guidance

```python
{
    "fiscal_year": 2026,
    "quarter": 2,
    "analyst_eps_mean": 1.52,
    "analyst_revenue_mean": 94500000000,
    "analyst_count": 42,
    "analyst_rating": "buy",
    "analyst_rating_distribution": {
        "strong_buy": 15,
        "buy": 20,
        "hold": 5,
        "sell": 2,
        "strong_sell": 0
    }
}
```

### Complete Data Capture

The engine retains **ALL** information from yfinance (100+ fields), not just the subset shown above. This includes:

**Additional data in `additional_data` field:**
- `dividends_history`: Historical dividend payments
- `splits_history`: Stock split history  
- `recommendations`: Analyst recommendations history
- `quarterly_income_stmt`: Quarterly income statements (raw)
- `quarterly_balance_sheet`: Quarterly balance sheets (raw)
- `quarterly_cashflow`: Quarterly cash flow statements (raw)
- `institutional_holders`: Top institutional shareholders
- `insider_transactions`: Recent insider trading activity
- `insider_purchases`: Insider purchase history
- `insider_roster_holders`: Current insider holdings
- `options`: Available option expiration dates
- `info_raw`: All raw fields from yfinance `info` property

**Example: Accessing additional data**

```python
result = await engine.fetch_stock_analytics("AAPL", include_news=True)

# Access standard fields
print(f"Price: ${result['data']['current_price']:.2f}")
print(f"PE Ratio: {result['data']['pe_ratio']:.2f}")

# Access additional data
if 'additional_data' in result:
    additional = result['additional_data']
    
    # Dividend history
    if 'dividends_history' in additional:
        print(f"Latest dividend: {additional['dividends_history']}")
    
    # Institutional holders
    if 'institutional_holders' in additional:
        print(f"Top holders: {additional['institutional_holders']}")
    
    # Insider transactions
    if 'insider_transactions' in additional:
        print(f"Recent insider activity: {additional['insider_transactions']}")
```

**Kafka message includes all data:**

When publishing to Kafka, the `additional_data` field is serialized and included in the message, giving you access to the complete dataset downstream.

## Performance

**Benchmark: 100 stocks**
- Concurrent (max_concurrent=20): ~5-10 seconds
- Sequential: ~100+ seconds
- **Speedup: 10-20x**

**Memory**: Minimal (< 100MB for 100 stocks)

## Error Handling

The engine handles errors gracefully:
- **Individual stock failures** don't break batch operations
- **Network errors** are caught and reported per stock
- **Invalid tickers** return error messages instead of raising exceptions
- **Rate limiting** prevents Yahoo Finance from blocking requests

## Kafka Integration

### Publishing Stock Updates to Kafka

The engine supports custom callbacks for publishing real-time stock updates to Kafka topics using **Confluent Kafka producer**. Perfect for building event-driven trading systems, data pipelines, or alerting systems.

**Features:**
- Confluent Kafka producer (production-ready)
- Config file support via `KAFKA_CONFIG_PATH` environment variable
- Delivery callbacks and statistics
- Automatic flush on close
- JSON serialization

#### Quick Start

```python
import asyncio
from analytics_engine import AsyncAnalyticsEngine
from kafka_callback import create_kafka_callback

async def main():
    # Create Kafka callback
    kafka_callback = create_kafka_callback(
        bootstrap_servers="localhost:9092",
        topic="stock-updates",
    )
    
    # Initialize Kafka producer
    await kafka_callback.initialize()
    
    # Create engine and add callback
    engine = AsyncAnalyticsEngine(max_concurrent=20)
    engine.add_update_callback(kafka_callback)
    
    # Start monitoring (data auto-publishes to Kafka)
    engine.start_monitoring(
        tickers=["AAPL", "GOOGL", "MSFT"],
        interval_ms=30000,  # 30 seconds
        include_news=True,
    )
    
    # Run for 5 minutes
    await asyncio.sleep(300)
    
    # Cleanup
    await engine.stop_monitoring()
    await kafka_callback.close()

asyncio.run(main())
```

#### Message Format

Stock updates are published as JSON with the following structure:

```json
{
  "ticker": "AAPL",
  "timestamp": "2026-05-06T14:30:00",
  "source": "yfinance-analytics-engine",
  "price": {
    "current": 175.50,
    "market_cap": 2750000000000,
    "currency": "USD"
  },
  "ratios": {
    "pe": 28.5,
    "pb": 45.2,
    "dividend_yield": 0.005
  },
  "fundamentals": {
    "eps": 6.15,
    "revenue": 394328000000,
    "fcf": 99584000000,
    "roe": 145.5
  },
  "company": {
    "name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics"
  },
  "news_count": 5,
  "analyst_guidance": {
    "eps_estimate": 1.52,
    "revenue_estimate": 94500000000,
    "analyst_count": 42,
    "rating": "buy"
  }
}
```

#### Custom Message Transformation

Override `_transform_to_message()` to customize the message format:

```python
from kafka_callback import KafkaStockPublisher

class AlertPublisher(KafkaStockPublisher):
    """Custom publisher for price alerts."""
    
    def _transform_to_message(self, ticker, data):
        stock_data = data.get("data", {})
        
        # Simplified alert format
        return {
            "symbol": ticker,
            "price": stock_data.get("current_price"),
            "pe_ratio": stock_data.get("pe_ratio"),
            "alert": stock_data.get("pe_ratio", 0) > 50,
            "timestamp": data.get("fetch_time"),
        }
```

#### Multiple Topics

Publish to different topics based on conditions:

```python
# All stocks
all_publisher = KafkaStockPublisher(topic="all-stocks")

# High-value stocks only
class HighValuePublisher(KafkaStockPublisher):
    async def __call__(self, ticker, data):
        market_cap = data['data'].get('market_cap', 0)
        if market_cap > 100_000_000_000:  # > $100B
            await super().__call__(ticker, data)

high_value_pub = HighValuePublisher(topic="high-value-stocks")

# Add both callbacks
engine.add_update_callback(all_publisher)
engine.add_update_callback(high_value_pub)
```

#### Production Configuration

**Method 1: Using Config File (Recommended)**

```bash
# 1. Create kafka.properties file
cat > kafka.properties <<EOF
bootstrap.servers=broker1:9092,broker2:9092,broker3:9092
compression.type=gzip
acks=all
retries=5
enable.idempotence=true
client.id=yfinance-analytics-engine
EOF

# 2. Set environment variable
export KAFKA_CONFIG_PATH=/path/to/kafka.properties

# 3. Use in code (config auto-loaded)
kafka_publisher = KafkaStockPublisher(topic="stock-updates-prod")
await kafka_publisher.initialize()
```

**Method 2: Programmatic Configuration**

```python
kafka_publisher = KafkaStockPublisher(
    bootstrap_servers="broker1:9092,broker2:9092,broker3:9092",
    topic="stock-updates-prod",
    compression_type="gzip",
    acks="all",
    retries=5,
    # Additional Confluent Kafka configs
    **{
        "enable.idempotence": "true",
        "max.in.flight.requests.per.connection": "5",
        "batch.size": "32768",
        "linger.ms": "100",
    }
)
```

#### Prerequisites

```bash
# Install Confluent Kafka client
pip install confluent-kafka

# Start Kafka (Docker)
docker run -p 9092:9092 apache/kafka

# Optional: Copy example config
cp kafka.properties.example kafka.properties
export KAFKA_CONFIG_PATH=$(pwd)/kafka.properties
```

## Proxy Rotation

Distribute requests across multiple SOCKS5 proxies to avoid rate limiting and IP blocking.

### Why SOCKS5?

**Important:** Yahoo Finance detects and blocks HTTP proxies. Use SOCKS5 proxies instead.

See: [yfinance issue #2518](https://github.com/ranaroussi/yfinance/issues/2518)

- ❌ **HTTP Proxies**: Detected and rejected by Yahoo Finance  
- ✅ **SOCKS5 Proxies**: Works reliably with Yahoo Finance

### Quick Setup

**Method 1: Environment Variable**

```bash
export PROXY_LIST="socks5://proxy1:1080,socks5://proxy2:1080,socks5://user:pass@proxy3:1080"
export PROXY_MAX_RPM=60  # Max requests per minute per proxy
python runner.py
```

**Method 2: Config File**

Create `proxies.txt`:
```
socks5://proxy1.example.com:1080
socks5://proxy2.example.com:1080
socks5://user:pass@proxy3.example.com:1080
```

```bash
export PROXY_CONFIG_PATH=./proxies.txt
python runner.py
```

### How It Works

1. **Round-Robin Rotation**: Distributes requests evenly across healthy proxies
2. **Per-Proxy Rate Limiting**: Respects `max_requests_per_minute` per proxy
3. **Health Checking**: Marks proxies unhealthy after consecutive failures
4. **Auto-Failover**: Skips unhealthy or rate-limited proxies
5. **Browser Impersonation**: Uses curl-cffi with Chrome impersonation to avoid detection

### Recommended Proxy Providers

**SOCKS5 proxy providers:**
- [Bright Data](https://brightdata.com) - Enterprise residential SOCKS5
- [Smartproxy](https://smartproxy.com) - Good balance of price/performance  
- [Oxylabs](https://oxylabs.io) - High-quality residential/datacenter
- [IPRoyal](https://iproyal.com) - Affordable residential SOCKS5

### Testing Proxies

```bash
# Test SOCKS5 connectivity
curl --socks5 your-proxy:1080 https://finance.yahoo.com

# Test proxy IP
curl --socks5 your-proxy:1080 https://api.ipify.org
```

### Configuration

```python
from proxy_rotator import ProxyRotator
from analytics_engine import AsyncAnalyticsEngine

# Initialize proxy rotator
proxy_rotator = ProxyRotator(
    proxies=[
        "socks5://proxy1.example.com:1080",
        "socks5://proxy2.example.com:1080",
    ],
    max_requests_per_minute=60,
    max_consecutive_failures=3,
    enable_health_check=True,
)

# Use with analytics engine
engine = AsyncAnalyticsEngine(proxy_rotator=proxy_rotator)
```

See **[PROXY_SETUP.md](PROXY_SETUP.md)** for complete documentation.

## WebSocket Testing

Test real-time price streaming using yfinance WebSocket API.

### Quick Test

```bash
python test_websocket.py
```

This will:
- Connect to Yahoo Finance WebSocket
- Stream real-time price updates for AAPL, GOOGL, MSFT, NVDA, META
- Show price, change %, volume for ~30 seconds or 50 messages
- Fall back to polling mode if WebSocket unavailable

### Expected Output

```
✅ WebSocket connected!
📡 Listening for real-time updates...

📊 AAPL: $178.45 (+1.23%) Vol: 12,345,678 @ 14:23:45
📊 GOOGL: $142.67 (+0.89%) Vol: 8,901,234 @ 14:23:46
📊 MSFT: $412.34 (+2.11%) Vol: 15,678,901 @ 14:23:47
...
```

### Requirements

- yfinance >= 1.3.0 (WebSocket support)
- Market hours (9:30 AM - 4:00 PM ET, weekdays)
- Outside market hours, falls back to polling mode

### SSL Certificate Issues

If you get SSL certificate errors on macOS:

```bash
# Fix SSL certificates
/Applications/Python\ 3.12/Install\ Certificates.command

# Or use certifi
pip install certifi
```