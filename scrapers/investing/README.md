# Investing.com News Scraper

A production-ready web scraper for Investing.com news articles with Kafka integration, de-duplication, and continuous scraping support.

## Features

- **Stealth Mode**: Uses Scrapling's StealthyFetcher for anti-bot evasion
- **De-duplication**: History-based tracking with automatic TTL cleanup (30 days)
- **Kafka Integration**: Publishes articles to Kafka topics in real-time
- **Multi-Category Support**: Scrape from various categories (stock-market-news, crypto-news, etc.)
- **Analysis Mode**: Option to scrape from `/analysis/` instead of `/news/` sections
- **Continuous Mode**: Run indefinitely with configurable intervals
- **403 Recovery**: Automatic browser context cleanup after consecutive 403 errors
- **Pagination Limit**: Stops at page 15 to avoid excessive scraping
- **Docker Support**: Containerized deployment with docker-compose
- **Robust Extraction**: Multiple fallback selectors for reliable data extraction

## Architecture

Based on seeking-alpha scraper pattern with clean separation:

- **`investing_scraper_base.py`**: Abstract base class with common functionality (history, Kafka, de-duplication)
- **`investing_scraper_stealth.py`**: Stealth implementation using Scrapling and browser automation
- **`kafka_config.py`**: Kafka configuration loader

## Installation

### Local Development

```bash
cd /Users/sylvainlegouellec/repos/palantir-trading-engine/scrapers/investing

# Install dependencies
pip install -r requirements.txt

# Install Scrapling browser components
scrapling install
```

### Docker Deployment

```bash
# Build image
cd /Users/sylvainlegouellec/repos/palantir-trading-engine/scrapers
docker build -t investing-scraper ./investing

# Or use docker-compose
docker-compose up investing-scraper
```

## Usage

### Basic Scraping

```bash
# Scrape 10 articles from latest news
python investing_scraper_stealth.py --limit 10

# Scrape from specific category
python investing_scraper_stealth.py --category crypto-news --limit 20

# Scrape analysis articles instead of news
python investing_scraper_stealth.py --analysis --category stock-market-news --limit 20

# Verbose mode
python investing_scraper_stealth.py --verbose --no-headless
```

### Kafka Mode

```bash
# Publish to Kafka
python investing_scraper_stealth.py --kafka --limit 50

# Kafka with custom topic
python investing_scraper_stealth.py --kafka --kafka-topic my-topic

# Kafka with local save
python investing_scraper_stealth.py --kafka --save-local
```

### Continuous Mode

```bash
# Run continuously (scrape every 5 minutes)
python investing_scraper_stealth.py --continuous --continuous-interval 300

# Continuous with Kafka
python investing_scraper_stealth.py --kafka --continuous --continuous-interval 600
```

## Supported Categories

- `latest-news` - Latest news (default)
- `stock-market-news` - Stock market news
- `economy-news` - Economy news
- `forex-news` - Forex news
- `commodities-news` - Commodities news
- `crypto-news` - Cryptocurrency news

## Data Model

Each article includes:

```python
{
    'id': str,                    # Article ID from URL
    'url': str,                   # Full article URL
    'scraped_at': str,           # ISO timestamp
    'title': str,                # Article title
    'author': str | List[str],   # Single author or list
    'published_date': str,       # Publication date
    'modified_date': str,        # Last modified date (if available)
    'excerpt': str,              # Article summary
    'content': str,              # Full article content
    'word_count': int,           # Word count
    'category': str,             # Category (latest-news, etc.)
    'tags': List[str],           # Article tags/keywords
    'images': List[str],         # Image URLs
    'comment_count': int         # Number of comments
}
```

## Configuration

### Environment Variables

- `CATEGORY`: Category to scrape (default: `latest-news`)
- `ANALYSIS`: Scrape from `/analysis/` instead of `/news/` (default: `false`)
- `KAFKA_ENABLED`: Enable Kafka publishing (default: `false`)
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka servers (default: `localhost:9092`)
- `KAFKA_TOPIC`: Kafka topic name (default: `investing-articles`)
- `HEADLESS`: Run browser in headless mode (default: `true`)
- `LIMIT`: Articles per iteration (default: `20`)
- `DELAY`: Delay between articles in seconds (default: `2.0`)
- `CONTINUOUS_INTERVAL`: Seconds between iterations (default: `300`)

### Kafka Configuration

Create `kafka_config.properties`:

```properties
bootstrap.servers=your-kafka-server:9092
security.protocol=SASL_SSL
sasl.mechanisms=PLAIN
sasl.username=your-username
sasl.password=your-password
session.timeout.ms=45000
client.id=ccloud-python-client-investing
```

## Command-Line Options

```
usage: investing_scraper_stealth.py [-h] [--category {latest-news,stock-market-news,economy-news,forex-news,commodities-news,crypto-news}]
                                     [--analysis] [--output-dir OUTPUT_DIR] [--limit LIMIT] [--format {json,markdown,both}]
                                     [--no-headless] [--delay DELAY] [--verbose] [--history-file HISTORY_FILE]
                                     [--force] [--save-local] [--continuous] [--continuous-interval CONTINUOUS_INTERVAL]
                                     [--kafka] [--kafka-config KAFKA_CONFIG] [--kafka-bootstrap-servers KAFKA_BOOTSTRAP_SERVERS]
                                     [--kafka-topic KAFKA_TOPIC]

Options:
  --category              Category to scrape (default: latest-news)
  --analysis              Scrape from /analysis/ instead of /news/ (default: False)
  --output-dir, -o        Output directory (default: news)
  --limit, -l             Number of articles to scrape (default: 20)
  --format, -f            Output format: json, markdown, both (default: both)
  --no-headless           Show browser window (default: headless)
  --delay, -d             Delay between articles in seconds (default: 2.0)
  --verbose, -v           Enable verbose logging
  --history-file          History file path (default: history/scraped_history.json)
  --force                 Force re-scraping of already scraped articles
  --save-local            Save locally even when Kafka is enabled
  --continuous            Run in continuous mode (infinite loop)
  --continuous-interval   Seconds between iterations (default: 300)
  --kafka                 Enable Kafka publishing
  --kafka-config          Kafka config file (default: kafka_config.properties)
  --kafka-bootstrap-servers Kafka bootstrap servers (default: localhost:9092)
  --kafka-topic           Kafka topic name (default: investing-articles)
```

## Docker Compose

Add to your `docker-compose.yml`:

```yaml
investing-scraper:
  build:
    context: ./investing
    dockerfile: Dockerfile
  container_name: investing-scraper
  depends_on:
    kafka:
      condition: service_started
  restart: unless-stopped
  environment:
    - CATEGORY=latest-news
    - ANALYSIS=false  # Set to true for /analysis/ instead of /news/
    - KAFKA_ENABLED=true
    - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
    - KAFKA_TOPIC=investing-articles
    - CONTINUOUS_INTERVAL=300
  volumes:
    - ./investing/history:/app/history
    - ./investing/news:/app/news
  networks:
    - scraper-network
```

## De-duplication

The scraper maintains a history file (`history/scraped_history.json`) to track scraped articles:

- **Automatic Cleanup**: Entries older than 30 days are automatically removed
- **Persistent**: History survives container restarts via volume mounts
- **URL-based**: Uses article URL as unique identifier

## Pagination Limits

To prevent excessive scraping and avoid potential rate limiting:

- **Maximum Pages**: Pagination stops at page 15, even if the article limit hasn't been reached
- **Rationale**: Most relevant articles appear on early pages; deep pagination rarely yields useful content
- **Behavior**: The scraper will log a warning when hitting the page limit and process whatever URLs were collected

## Troubleshooting

### 403 Forbidden Errors

The scraper automatically handles 403 errors:
- After 3 consecutive 403s, it resets the browser context
- Cleans up Playwright processes and browser cache
- Retries with a fresh session

### Selector Issues

If extraction fails:
1. Run with `--verbose` to see detailed logs
2. Check selector patterns in `_extract_*` methods
3. Use `--no-headless` to inspect the page visually

### Kafka Connection Issues

- Verify `kafka_config.properties` exists and has correct credentials
- Check Kafka broker is accessible
- Test with `--verbose` to see connection logs

## Performance

- **Single instance**: ~180-240 articles/hour (with 2s delay)
- **Continuous mode**: Runs 24/7 with configurable intervals
- **Pagination**: Fast path-based navigation
- **History**: Auto-cleanup prevents unbounded growth

## License

Part of the Palantir Trading Engine project.
