# Rate Limiting and Cooldown Configuration

## Overview

The YFinance Analytics Engine includes built-in rate limiting and automatic cooldown mechanisms to prevent overwhelming the Yahoo Finance API and handle 429 (Too Many Requests) errors gracefully.

## Cooldown Mechanism

### What is it?

When the scraper detects a high failure rate (>50%), it automatically enters a cooldown period to give the API breathing room. This prevents aggressive retrying that could lead to IP blocking.

### How it works

1. **Monitor Batch Results**: After each batch of stock fetches, the engine calculates the failure rate
2. **Trigger Threshold**: If failure rate exceeds 50%, cooldown is triggered
3. **Cooldown Period**: The engine pauses for the configured cooldown duration
4. **Resume**: After cooldown, normal operation resumes

### Example Log Output

```
⚠️  High failure rate: 65.2% (15/23) - waiting 60 seconds to give API breathing room...
✅ Cooldown complete - resuming normal operation
```

## Configuration

### Default Behavior

By default, the cooldown period is **60 seconds**.

### Method 1: Environment Variable (Recommended for Docker)

Set the `COOLDOWN_PERIOD` environment variable:

```bash
export COOLDOWN_PERIOD=120  # 2 minutes
python runner.py
```

**Docker Compose:**

```yaml
environment:
  - COOLDOWN_PERIOD=180  # 3 minutes
```

### Method 2: Constructor Parameter (Programmatic)

```python
from analytics_engine import AsyncAnalyticsEngine

# Custom cooldown period (120 seconds)
engine = AsyncAnalyticsEngine(
    cooldown_period=120.0
)
```

### Method 3: Dockerfile

Already configured with default value:

```dockerfile
ENV COOLDOWN_PERIOD=60
```

## Configuration Examples

### Conservative (Longer Cooldown)

For APIs with strict rate limits or when you want to be extra cautious:

```bash
export COOLDOWN_PERIOD=300  # 5 minutes
```

### Aggressive (Shorter Cooldown)

For development or when rate limits are less strict:

```bash
export COOLDOWN_PERIOD=30  # 30 seconds
```

### Fractional Values

You can use fractional seconds:

```python
engine = AsyncAnalyticsEngine(cooldown_period=45.5)  # 45.5 seconds
```

## Related Rate Limiting Settings

The engine has several rate limiting mechanisms working together:

### 1. Request Rate Limiting

Controls the maximum requests per second:

```python
engine = AsyncAnalyticsEngine(
    max_requests_per_second=2.0  # Max 2 requests/second
)
```

### 2. Concurrent Request Limit

Controls how many requests run in parallel:

```python
engine = AsyncAnalyticsEngine(
    max_concurrent=20  # Max 20 concurrent requests
)
```

### 3. Retry Configuration

Controls exponential backoff for individual failures:

```python
engine = AsyncAnalyticsEngine(
    max_retries=3,           # Max 3 retry attempts
    base_retry_delay=1.0,    # Start with 1 second delay
    max_retry_delay=60.0     # Cap at 60 seconds delay
)
```

### 4. Cooldown Period (New!)

Controls batch-level cooldown when failure rate is high:

```python
engine = AsyncAnalyticsEngine(
    cooldown_period=60.0  # Wait 60 seconds when >50% failure rate
)
```

## Complete Configuration Example

```python
from analytics_engine import AsyncAnalyticsEngine

engine = AsyncAnalyticsEngine(
    # Rate limiting
    max_concurrent=20,              # 20 parallel requests
    max_requests_per_second=2.0,    # 2 req/s max
    
    # Retry behavior
    max_retries=3,                  # Retry up to 3 times
    base_retry_delay=1.0,           # Start with 1s delay
    max_retry_delay=60.0,           # Cap at 60s delay
    
    # Cooldown (NEW!)
    cooldown_period=60.0,           # 60s cooldown on high failure rate
    
    # Proxy rotation
    enable_proxy_rotation=True      # Use proxy rotation if available
)
```

## Best Practices

### Production

For production deployments scraping 100+ stocks:

```yaml
environment:
  - COOLDOWN_PERIOD=120          # 2 minutes
  - INTERVAL_MS=60000            # 1 minute between batches
  - BATCH_SIZE=50                # 50 stocks per batch
```

### Development

For development and testing:

```yaml
environment:
  - COOLDOWN_PERIOD=30           # 30 seconds
  - INTERVAL_MS=30000            # 30 seconds between batches
  - BATCH_SIZE=20                # Smaller batches
```

### High-Volume Scraping

If you're scraping a large number of stocks and hitting rate limits:

```yaml
environment:
  - COOLDOWN_PERIOD=300          # 5 minutes
  - INTERVAL_MS=120000           # 2 minutes between batches
  - BATCH_SIZE=30                # Smaller batches
  - PROXY_AUTO_FETCH=true        # Enable proxy rotation
  - PROXY_AUTO_FETCH_MAX=50      # Use up to 50 proxies
```

## Monitoring

### Check Failure Rate

The engine logs the failure rate when it exceeds 50%:

```
⚠️  High failure rate: 65.2% (15/23)
```

### Monitor Cooldowns

Watch for cooldown messages in logs:

```bash
docker logs -f yfinance-scraper | grep -i "cooldown"
```

### Statistics

Get retry statistics programmatically:

```python
stats = engine.get_retry_stats()
print(f"429 errors: {stats.rate_limit_errors}")
print(f"Total retries: {stats.total_retries}")
```

## Troubleshooting

### Still Getting Rate Limited?

1. **Increase cooldown period**: Try 180-300 seconds
2. **Reduce batch size**: Lower `BATCH_SIZE` from 50 to 20-30
3. **Increase interval**: Raise `INTERVAL_MS` to 120000 (2 minutes)
4. **Enable proxy rotation**: Set `PROXY_AUTO_FETCH=true`

### Cooldown Too Aggressive?

If you're seeing frequent cooldowns but not hitting rate limits:

1. **Decrease cooldown period**: Try 30-45 seconds
2. **Increase concurrent requests**: Raise `max_concurrent` to 30-40
3. **Check failure threshold**: Cooldown triggers at >50% failure rate

### Example: Tuning for Your Use Case

```bash
# Start conservative
export COOLDOWN_PERIOD=120
export BATCH_SIZE=30
export INTERVAL_MS=90000

# Monitor logs for a few cycles
docker logs -f yfinance-scraper

# If no cooldowns triggered, gradually reduce:
export COOLDOWN_PERIOD=90
export BATCH_SIZE=40
export INTERVAL_MS=60000

# Continue tuning until you find the sweet spot
```

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `COOLDOWN_PERIOD` | 60 | Seconds to wait when failure rate >50% |
| `BATCH_SIZE` | 50 | Stocks per batch |
| `INTERVAL_MS` | 30000 | Milliseconds between batches |
| `PROXY_AUTO_FETCH` | false | Auto-fetch and validate free proxies |
| `PROXY_AUTO_FETCH_MAX` | 50 | Max proxies to validate |

## API Rate Limits

Yahoo Finance has undocumented rate limits that vary:

- **Per IP**: ~2,000 requests/hour (estimated)
- **Burst limit**: ~48 requests/minute (estimated)
- **Cooldown trigger**: Seeing >50% 429 errors

These limits can vary based on IP reputation, time of day, and Yahoo's current policies.

## Summary

The configurable cooldown period helps you:

1. **Prevent IP blocking** by automatically backing off during rate limit situations
2. **Tune aggressiveness** based on your specific use case and rate limit experience
3. **Monitor and adjust** based on real-world behavior

Start with the default (60 seconds) and adjust based on your monitoring data!
