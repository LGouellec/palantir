# Wall Street Journal Scraper

Professional WSJ article scraper built with **Scrapling** - an adaptive web scraping framework with built-in stealth mode and anti-bot detection.

## TODO

[ ] Login callback

## 🚀 Why Scrapling?

Scrapling is **784x faster** than BeautifulSoup and includes:
- ✅ **Built-in stealth mode** - bypasses Cloudflare and anti-bot systems
- ✅ **Adaptive scraping** - automatically adjusts when websites change
- ✅ **Multiple fetcher types** - from simple HTTP to full browser automation
- ✅ **Superior performance** - optimized parsing engine
- ✅ **Clean API** - CSS/XPath selectors with full type hints

## 📦 Installation

### Quick Install

```bash
pip install -r requirements.txt
scrapling install
```

## 🎯 Usage

### Basic Examples

```bash
# Scrape 10 articles from WSJ homepage
python wsj_scraper.py --limit 10

# Scrape from specific section (e.g., AI/Tech)
python wsj_scraper.py --base-url "https://www.wsj.com/tech/ai" --limit 20

# Save only markdown files
python wsj_scraper.py --format markdown --limit 15

# Scrape with verbose logging
python wsj_scraper.py --verbose --limit 5

# Debug mode (visible browser + logs)
python wsj_scraper.py --no-headless --verbose --limit 2
```

### Advanced Examples

```bash
# Scrape from URL list
echo "https://www.wsj.com/tech/ai" > sections.txt
echo "https://www.wsj.com/markets" >> sections.txt
python wsj_scraper.py --urls-file sections.txt --limit 50

# Slower scraping (more stealthy)
python wsj_scraper.py --delay 5.0 --limit 20

# Custom output directory
python wsj_scraper.py --output-dir ~/Documents/WSJ --limit 30

# Force re-scrape articles (ignore history)
python wsj_scraper.py --force --limit 10

# Custom history file
python wsj_scraper.py --history-file my_history.json --limit 20
```

### Automatic Pagination

The scraper automatically follows pagination when the URL contains `?page=`:

```bash
# Scrape from page 1, automatically continue to pages 2, 3, 4... until 404
python wsj_scraper.py \
  --base-url "https://www.wsj.com/tech/ai?page=1" \
  --limit 100

# Output:
# 📄 Pagination mode enabled, starting from page 1
# 📄 Fetching page 1...
# 📄 Page 1: +20 articles (total: 20)
# 📄 Fetching page 2...
# 📄 Page 2: +18 articles (total: 38)
# 📄 Page 3: 404 Not Found, stopping pagination
# ✓ Found 38 article links total

# Start from specific page
python wsj_scraper.py --base-url "https://www.wsj.com/markets?page=5" --limit 50

# Disable pagination (scrape only single page)
python wsj_scraper.py \
  --base-url "https://www.wsj.com/tech?page=1" \
  --no-pagination \
  --limit 20
```

See [PAGINATION.md](PAGINATION.md) for detailed pagination guide.

### Persistent Scraping (Avoid Re-scraping)

The scraper automatically tracks scraped articles in a history file:

```bash
# First run - scrapes 20 articles
python wsj_scraper.py --limit 20

# Second run - only scrapes NEW articles not in history
python wsj_scraper.py --limit 20

# Force re-scraping all articles
python wsj_scraper.py --force --limit 20
```

History file (`scraped_history.json`) stores:
```json
{
  "https://www.wsj.com/articles/example-1": "2026-04-20T10:30:22.123456",
  "https://www.wsj.com/articles/example-2": "2026-04-20T10:32:15.654321"
}
```

## 💻 Programmatic Usage

```python
from wsj_scraper import WSJScraper

# Create scraper instance
scraper = WSJScraper(
    output_dir='articles',
    headless=True,
    verbose=True,
    base_url='https://www.wsj.com/tech/ai'
)

# Scrape articles (skips already scraped)
scraper.scrape_and_save(
    limit=10,
    format='both',
    delay=2.0
)

# Force re-scrape (ignore history)
scraper.scrape_and_save(
    limit=10,
    force=True
)

# Or scrape specific URLs
urls = [
    'https://www.wsj.com/articles/example-1',
    'https://www.wsj.com/articles/example-2'
]
scraper.scrape_and_save(article_urls=urls)
```

### Single Article Scraping

```python
from wsj_scraper import WSJScraper

scraper = WSJScraper()

# Scrape one article
article = scraper.scrape_article('https://www.wsj.com/articles/example')

if article:
    print(f"Title: {article['title']}")
    print(f"Author: {article['author']}")
    print(f"Words: {article['word_count']}")
    
    # Save it
    scraper.save_article(article, format='both')
```

## ✨ Features

### Core Features
- ✅ **Stealth Mode** - Built-in anti-bot detection bypass
- ✅ **Smart Extraction** - Multiple fallback selectors for reliability
- ✅ **Dual Output** - Save as JSON and/or Markdown
- ✅ **Adaptive** - Automatically handles website changes
- ✅ **Fast** - 784x faster than BeautifulSoup
- ✅ **Verbose Logging** - Detailed debug information
- ✅ **Configurable** - Custom delays, output formats, base URLs

### Extracted Data
- Article title
- Author name
- Published date
- Article summary/excerpt
- Full article content
- Word count
- Source URL
- Scrape timestamp

### Persistent Scraping
- ✅ **Smart History Tracking** - Automatically skips already scraped articles
- ✅ **JSON History File** - Stores scraped URLs with timestamps
- ✅ **Incremental Scraping** - Only scrapes new articles
- ✅ **Force Re-scrape** - Option to override history and re-scrape all

### Distributed Scraping (Kubernetes)
- ✅ **Multi-pod Deployment** - Scale across multiple Kubernetes pods
- ✅ **3 Distribution Modes** - Modulo (hash-based), Redis (queue-based), Range (manual)
- ✅ **Production Ready** - StatefulSets, Deployments, CronJobs included
- ✅ **Load Balancing** - Automatic URL distribution across pods
- ✅ **Docker Support** - Docker Compose for local testing
- ✅ **Scalable** - From 1 to 100+ pods

## 🚢 Docker

Image available at:
   - Azure ACR: `docker pull palantiracr.azurecr.io/wsj-scraper:latest`

**Features:**
- ✅ Multi-platform builds (amd64, arm64)
- ✅ Vulnerability scanning (Trivy/Azure Defender)
- ✅ Automated tagging (latest, semver, sha)
- ✅ Build caching (75-87% faster)


## 🔧 Command Line Options

```
Options:
  -h, --help            show this help message and exit
  --output-dir OUTPUT_DIR, -o OUTPUT_DIR
                        Output directory for articles (default: articles)
  --limit LIMIT, -l LIMIT
                        Number of articles to scrape (default: 10000)
  --format {json,markdown,both}, -f {json,markdown,both}
                        Output format (default: both)
  --urls-file URLS_FILE
                        File containing article URLs (one per line)
  --no-headless         Show browser window (for debugging)
  --delay DELAY, -d DELAY
                        Delay between requests in seconds (default: 2.0)
  --verbose, -v         Enable verbose logging
  --base-url BASE_URL   Base URL to scrape from (default: https://www.wsj.com)
  --history-file HISTORY_FILE
                        History file to track scraped articles (default: scraped_history.json)
  --force               Force re-scraping of articles already in history
  --save-local          Save articles locally even when Kafka is enabled
  --no-pagination       Disable automatic pagination (if URL has ?page= parameter)
  --no-auto-discovery   Disable automatic article discovery (only use provided URLs)
  --kafka, --enable-kafka
                        Enable Kafka publishing (requires confluent-kafka)
  --kafka-config KAFKA_CONFIG
                        Kafka configuration file (default: kafka_config.properties)
  --kafka-bootstrap-servers KAFKA_BOOTSTRAP_SERVERS
                        Kafka bootstrap servers (default: KAFKA_BOOTSTRAP_SERVERS env or localhost:9092)
  --kafka-topic KAFKA_TOPIC
                        Kafka topic name (default: KAFKA_TOPIC env or wsj-articles)
```

## ⚠️ Important Notes

### Bot Detection
- **Scrapling's StealthyFetcher** handles anti-bot detection automatically
- Uses real browser fingerprints and network idle detection
- Cloudflare bypass built-in
- Much more reliable than basic HTTP requests

### Paywall Limitations
- WSJ has a subscription paywall
- Scraper extracts **free preview content** + **summaries**
- Full articles require WSJ subscription
- See "Subscription Access" section below

### Legal & Ethical
**Acceptable Use:**
- ✅ Personal research and education  
- ✅ Academic analysis
- ✅ News monitoring

**NOT Acceptable:**
- ❌ Commercial redistribution
- ❌ High-volume automated scraping
- ❌ Bypassing paywalls for profit

### Rate Limiting
- Default 2-second delay between requests
- Be respectful of WSJ infrastructure
- Increase delay with `--delay` for more stealth

## 🐛 Troubleshooting

### Enable Verbose Logging

```bash
# See detailed debug information
python wsj_scraper.py --verbose --limit 2

# Debug with visible browser
python wsj_scraper.py --no-headless --verbose --limit 1
```

### "No articles found"

**Cause:** Selectors may need updating or page structure changed  
**Solution:** Run with `--verbose` to see what's happening:

```bash
python wsj_scraper.py --verbose --no-headless --limit 1
```

### "Paywalled content"

**Symptom:** Only getting 50-100 words per article  
**Cause:** Article is behind subscription paywall  
**What you get:** Title, author, date, summary/excerpt

### Installation Issues

```bash
# Reinstall Scrapling
pip uninstall scrapling
pip install "scrapling[fetchers]"
scrapling install

# Check installation
python -c "from scrapling.fetchers import StealthyFetcher; print('✅ OK')"
```

### Browser Not Starting

```bash
# Run Scrapling installer
scrapling install

# Or reinstall browser components
pip install --force-reinstall "scrapling[fetchers]"
scrapling install
```

## 🎓 Advanced Usage

### Scrape Multiple Sections

```python
from wsj_scraper import WSJScraper
import time

sections = {
    'ai': 'https://www.wsj.com/tech/ai',
    'markets': 'https://www.wsj.com/markets',
    'economy': 'https://www.wsj.com/economy'
}

for name, url in sections.items():
    print(f"\n📰 Scraping {name.upper()} section...")
    
    scraper = WSJScraper(
        output_dir=f'articles/{name}',
        base_url=url,
        verbose=False
    )
    
    scraper.scrape_and_save(limit=10, delay=3.0)
    time.sleep(5)  # Delay between sections
```

### Filter Articles by Keyword

```python
from wsj_scraper import WSJScraper

scraper = WSJScraper(base_url='https://www.wsj.com/tech/ai')

# Get article links
urls = scraper.get_article_links(limit=50)

# Filter for AI-related articles
ai_keywords = ['artificial intelligence', 'ChatGPT', 'machine learning', 'LLM']

for url in urls:
    article = scraper.scrape_article(url)
    
    if article:
        text = (article['title'] + ' ' + article.get('content', '')).lower()
        
        if any(keyword.lower() in text for keyword in ai_keywords):
            print(f"✓ AI article: {article['title']}")
            scraper.save_article(article)
```

### Save to Database

```python
from wsj_scraper import WSJScraper
import sqlite3

# Create database
conn = sqlite3.connect('wsj_articles.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE,
    title TEXT,
    author TEXT,
    published_date TEXT,
    content TEXT,
    word_count INTEGER,
    scraped_at TEXT
)
''')

# Scrape and save
scraper = WSJScraper()
urls = scraper.get_article_links(limit=10)

for url in urls:
    article = scraper.scrape_article(url)
    if article and article.get('content'):
        try:
            cursor.execute('''
            INSERT INTO articles (url, title, author, published_date, 
                                 content, word_count, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                article['url'], article['title'], article['author'],
                article['published_date'], article['content'],
                article['word_count'], article['scraped_at']
            ))
            conn.commit()
            print(f"✓ Saved to DB: {article['title']}")
        except sqlite3.IntegrityError:
            print(f"  Skipped (duplicate): {article['title']}")

conn.close()
```

## 📊 Scrapling vs Other Libraries

| Feature | Scrapling | Selenium | BeautifulSoup | Scrapy |
|---------|-----------|----------|---------------|--------|
| **Speed** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| **Anti-Bot** | ✅ Built-in | ⚠️ Manual | ❌ None | ⚠️ Manual |
| **Stealth Mode** | ✅ Yes | ⚠️ Partial | ❌ No | ❌ No |
| **Ease of Use** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Memory** | Low | High | Very Low | Medium |
| **JS Support** | ✅ Yes | ✅ Yes | ❌ No | ⚠️ Plugin |

**Performance Benchmarks:**
- **784x faster** than BeautifulSoup
- **41x faster** than Selectolax
- **12x faster** than PyQuery
- Comparable to Scrapy/Parsel

## 📚 Resources

- [Scrapling GitHub](https://github.com/D4Vinci/Scrapling)
- [Scrapling Documentation](https://scrapling.readthedocs.io/)
- [WSJ Official Site](https://www.wsj.com)

## 📄 License

[TODO]

---

**Built with Scrapling** - The adaptive web scraping framework 🚀
