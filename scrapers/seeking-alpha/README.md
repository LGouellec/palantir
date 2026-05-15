# Seeking Alpha News Scraper

Professional Seeking Alpha news scraper with **dual-mode support**: fast API-based scraping with curl_cffi, or stealth mode with browser emulation for bypassing anti-bot detection.

## 🚀 Key Features

This scraper leverages the SeekingAlpha API for efficient article collection:
- ✅ **API-based** - Uses SeekingAlpha's public API for reliable data extraction
- ✅ **Advanced Stealth Mode** - Browser emulation with Scrapling + intelligent anti-bot bypass
  - 🤖 **Smart Captcha Bypass** - Dynamic progress monitoring with human-like micro-movements
  - 🧹 **Auto-Recovery** - Automatic browser context cleanup after consecutive 403 errors
  - 🎭 **Human Simulation** - Natural hand tremor, variable timing, realistic mouse paths
  - 🔐 **Authenticated Access** - Login support for full paywall content
- ✅ **Fast & efficient** - Direct API access is much faster than HTML parsing (standard mode)
- ✅ **Single-call content** - API returns full article content in one request (no need for distributed scraping)
- ✅ **Immediate publishing** - Articles published to Kafka as soon as they're discovered (no waiting for pagination)
- ✅ **Early filtering** - Already-scraped articles filtered out immediately (saves processing time)
- ✅ **History TTL** - Auto-evict old entries from history (configurable, default 30 days)
- ✅ **Continuous mode** - Run in infinite loop with configurable pause intervals (perfect for production)
- ✅ **Pagination support** - Automatically fetches multiple pages of articles
- ✅ **Category-based** - Only scrapes from specified category (market-news::all, market-news::consumer, etc.)
- ✅ **Kafka integration** - Real-time streaming to Kafka topics for downstream processing

## 🛡️ Standard vs Stealth Mode

### Standard Mode (Default - curl_cffi)
**When to use:**
- Fast scraping when content is not being cut off
- API responses include full article content
- Lower resource usage

**Pros:**
- ⚡ Very fast (no browser overhead)
- 💰 Low resource consumption
- 🎯 Simple HTTP requests

**Cons:**
- ⚠️ May encounter anti-bot detection (content cutoff)
- ⚠️ Some articles may be truncated

### Stealth Mode (--stealth flag)
**When to use:**
- Content is being cut off or truncated
- Anti-bot detection is blocking full article access
- Website detects non-browser scrapers
- Encountering captcha challenges or 403 errors

**Pros:**
- 🛡️ Full browser emulation bypasses anti-bot detection
- ✅ Gets complete article content
- 🎭 Mimics real user behavior with advanced human simulation
- 🤖 Intelligent captcha bypass with dynamic progress monitoring
- 🧹 Auto-recovery from 403 errors (browser context cleanup)
- 🎯 Hand tremor simulation defeats bot detection

**Cons:**
- 🐌 Slower (browser automation overhead)
- 💾 Higher resource usage (runs real browser)
- 🔧 More complex setup

**Advanced Stealth Features:**

**1. Smart Captcha Bypass**
- Dynamically monitors captcha progress bar completion
- Human-like micro-movements during "Press & Hold" challenges
- Simulates natural hand tremor (1-3px jitter every 0.4-0.7s)
- Waits until progress reaches 98% of target before releasing
- Prevents bot detection from perfectly still mouse position

**2. Automatic 403 Recovery**
- Tracks consecutive 403 errors (max 3 before recovery)
- Gracefully terminates Playwright browser processes (SIGTERM → SIGKILL)
- Deletes persistent browser context and cookies
- Restarts from scratch with fresh session
- Prevents cascading failures and reduces manual intervention

**3. Human Behavior Simulation**
- Natural mouse movement paths with Bézier curves
- Variable timing and acceleration/deceleration
- Micro-movements and hand tremor during interactions
- Realistic click patterns and scroll behavior
- Shared across scrapers via common/mouvement package

**Usage:**
```bash
# Standard mode (fast, may have content cutoff)
python seeking_scraper.py --limit 20

# Stealth mode (slower, bypasses anti-bot detection)
python seeking_scraper.py --stealth --limit 20

# Stealth mode with visible browser (for debugging)
python seeking_scraper.py --stealth --no-headless --limit 5 --verbose
```

## 🏗️ Architecture

### Shared Common Package

The scraper uses a shared `common/` package that is reused across multiple scrapers (seeking-alpha, wsj):

```
scrapers/
├── common/                          # Shared utilities
│   └── mouvement/                   # Human behavior simulation
│       ├── __init__.py
│       └── human.py                 # HumanMouseSimulator class
├── seeking-alpha/
│   ├── seeking_scraper_stealth.py   # Uses common.mouvement.human
│   └── Dockerfile                   # Copies ../common/ to /app/common/
└── wsj/
    ├── wsj_scraper.py               # Uses common.mouvement.human
    └── Dockerfile                   # Copies ../common/ to /app/common/
```

**Benefits:**
- ✅ No code duplication across scrapers
- ✅ Consistent human behavior simulation
- ✅ Single source of truth for mouse movement algorithms
- ✅ Easier maintenance and updates

**HumanMouseSimulator Features:**
- Bézier curve mouse movements (natural acceleration/deceleration)
- Variable timing with jitter (unpredictable but human-like)
- Hand tremor simulation (micro-movements)
- Realistic click patterns
- Scroll behavior with momentum

## 📦 Installation

### Quick Install

```bash
pip install -r requirements.txt

# For stealth mode, also install Playwright browsers
pip install playwright
playwright install chromium
playwright install-deps chromium
```

### Docker Dependencies

The Dockerfile includes all required system packages:
- `curl`, `wget`, `ca-certificates`, `gnupg` - Network utilities
- `procps` - Process management tools (pgrep, pkill) for browser cleanup
- `python:3.11-slim` - Base Python image
- `playwright` - Browser automation (Chromium)

**Note:** The `procps` package is required for graceful Playwright process termination during 403 error recovery.

## 🎯 Usage

### Basic Examples

```bash
# Scrape 10 articles from default category (market-news::all) - Standard mode
python seeking_scraper.py --limit 10

# Scrape from specific category
python seeking_scraper.py --category "market-news::consumer" --limit 20

# Save only markdown files
python seeking_scraper.py --format markdown --limit 15

# Scrape with verbose logging
python seeking_scraper.py --verbose --limit 5

# With Kafka publishing (articles published immediately as found)
python seeking_scraper.py --kafka --kafka-topic seeking-news --limit 100

# Continuous scraping with Kafka (stream processing ready)
python seeking_scraper.py \
  --kafka \
  --category "market-news::all" \
  --limit 1000 \
  --delay 1.0 \
  --verbose
```

### Stealth Mode Examples

```bash
# Basic stealth mode (use when content is cut off)
python seeking_scraper.py --stealth --limit 20

# Stealth mode with specific category
python seeking_scraper.py --stealth --category "market-news::us-economy" --limit 10

# Stealth mode with visible browser (debugging)
python seeking_scraper.py --stealth --no-headless --limit 5 --verbose

# Stealth mode with Kafka publishing
python seeking_scraper.py \
  --stealth \
  --kafka \
  --kafka-topic seeking-news \
  --limit 50 \
  --save-local

# Production stealth mode with continuous scraping
python seeking_scraper.py \
  --stealth \
  --continuous \
  --kafka \
  --category "market-news::all" \
  --limit 100 \
  --delay 3.0

# Stealth mode with authenticated access and history TTL
python seeking_scraper.py \
  --stealth \
  --login-email "${SEEKING_ALPHA_EMAIL}" \
  --login-password "${SEEKING_ALPHA_PASSWORD}" \
  --history-ttl-days 7 \
  --limit 50

# Debug captcha bypass and 403 recovery (visible browser)
python seeking_scraper.py \
  --stealth \
  --no-headless \
  --verbose \
  --limit 5
```

**Stealth Mode Output Example:**
```
🔐 Logging in to Seeking Alpha...
✅ Login successful! Session cookies saved.
📄 Fetching articles from SeekingAlpha API (category: market-news::all)...

[DEBUG] Captcha detected! Attempting bypass...
[DEBUG] Moving to button center: (512.5, 384.2)
[DEBUG] Mouse down on button, holding...
[DEBUG] Progress: 45px / 200px (22.5%)
[DEBUG] Progress: 120px / 200px (60.0%)
[DEBUG] Progress: 196px / 200px (98.0%) - releasing!
[DEBUG] Mouse released, waiting for captcha to clear...
[DEBUG] ✓ Captcha bypassed successfully!

📰 Processing article 15/100: "Tech Stocks Rally Amid..."
⚠️  [DEBUG] HTTP 403 detected (1/3)
⚠️  [DEBUG] HTTP 403 detected (2/3)
⚠️  [DEBUG] HTTP 403 detected (3/3) - triggering cleanup...
[DEBUG] Cleaning browser context after 3 consecutive 403 errors
[DEBUG] Terminating Playwright processes (graceful shutdown)...
[DEBUG] Waiting for processes to exit...
[DEBUG] Sending SIGKILL to remaining processes...
[DEBUG] Deleting persistent browser context...
[DEBUG] Process cleanup completed
✅ Browser context cleaned, restarting with fresh session...
📰 Processing article 16/100: "Tech Stocks Rally Amid..." (retry)
✓ Scraped successfully!
```

### Authenticated Access (Login)

To get **full access to paywalled content**, you can log in to your Seeking Alpha account. The scraper will perform the login once, save session cookies, and reuse them for all subsequent requests.

```bash
# Set credentials via environment variables (recommended)
export SEEKING_ALPHA_EMAIL="your-email@example.com"
export SEEKING_ALPHA_PASSWORD="your-password"

# Run with stealth mode + login
python seeking_scraper.py --stealth --limit 20

# Or pass credentials directly (less secure)
python seeking_scraper.py \
  --stealth \
  --login-email "your-email@example.com" \
  --login-password "your-password" \
  --limit 20

# First run: performs login and saves cookies
# 🔐 Logging in to Seeking Alpha...
# ✅ Login successful! Session cookies saved.
# 💾 Saved session cookies to seeking_cookies.json

# Subsequent runs: reuses saved cookies (no login needed)
# ✅ Using existing session cookies
```

**How it works:**
1. **First run**: Logs in to Seeking Alpha, saves session cookies to `seeking_cookies.json`
2. **Subsequent runs**: Loads cookies from file, no login needed
3. **Cookie verification**: On first article of each session, verifies cookies are still valid
4. **Auto re-login**: If cookies expired, automatically logs in again and saves new cookies
5. **Persistent session**: Uses persistent browser context to maintain login state
6. **Full content access**: Bypasses paywall and gets complete article content

**Auto re-login process:**
```
First article scrape:
  ├─ Load cookies from seeking_cookies.json
  ├─ Verify login status (check if user menu exists)
  ├─ If invalid: ⚠️ Session expired, logging in again...
  ├─ Perform login
  ├─ Save new cookies
  └─ Continue scraping

Subsequent articles in same session:
  └─ Use validated cookies (no re-verification needed)
```

**Security notes:**
- ⚠️ Store credentials in environment variables, not command-line args
- ⚠️ Keep `seeking_cookies.json` secure (contains session tokens)
- ⚠️ Cookies expire after some time, scraper will auto-login when needed
- ✅ Only verifies once per session to minimize overhead
- ✅ Transparent re-authentication if session expires

**How It Works:**
1. Fetches page 1 from API (50 articles with full content)
2. Filters out already-scraped articles immediately
3. Publishes each new article to Kafka right away
4. Moves to page 2 and repeats
5. Continues until limit is reached or no more articles

### Continuous Scraping Mode

For production deployments, use continuous mode to run the scraper in an infinite loop:

```bash
# Basic continuous mode (5-minute intervals by default)
python seeking_scraper.py --continuous --kafka --limit 50

# Custom interval (10 minutes)
python seeking_scraper.py \
  --continuous \
  --continuous-interval 600 \
  --kafka \
  --limit 100

# Production setup with Kafka
python seeking_scraper.py \
  --continuous \
  --kafka \
  --kafka-topic seeking-news \
  --category "market-news::all" \
  --limit 100 \
  --verbose \
  --delay 1.0

# Output:
# 🔄 Continuous mode enabled - will scrape every 5 minutes
#    Press Ctrl+C to stop
#
# ============================================================
# 🔄 Iteration #1 - 2026-05-11 14:30:00
# ============================================================
# 📄 Fetching articles from SeekingAlpha API (category: market-news::all)...
# [... scraping ...]
# ✅ Scraping complete!
#
# ⏸️  Waiting 5 minutes before next iteration...
#    Next run at: 2026-05-11 14:35:00
```

**When to Use Continuous Mode:**
- ✅ Production deployments that need 24/7 monitoring
- ✅ Kubernetes pods that should never exit
- ✅ Real-time news aggregation pipelines
- ✅ Continuous data ingestion to Kafka

**When NOT to Use:**
- ❌ One-time scraping jobs
- ❌ Cron-based scheduled tasks (use single-run mode with cron instead)
- ❌ Testing/development

### Advanced Examples

```bash
# Slower scraping (more polite)
python seeking_scraper.py --delay 3.0 --limit 20

# Custom output directory
python seeking_scraper.py --output-dir ~/Documents/SeekingAlpha --limit 30

# Force re-scrape articles (ignore history)
python seeking_scraper.py --force --limit 10

# Custom history file per category
python seeking_scraper.py --category "market-news::consumer" \
  --history-file consumer_history.json --limit 50

# Continuous scraping with custom interval (10 minutes)
python seeking_scraper.py \
  --continuous \
  --continuous-interval 600 \
  --kafka \
  --kafka-topic seeking-news \
  --category "market-news::all" \
  --limit 100

# Multiple categories in parallel (each pod scrapes different category continuously)
python seeking_scraper.py --continuous --category "market-news::consumer" --kafka &
python seeking_scraper.py --continuous --category "market-news::tech" --kafka &
python seeking_scraper.py --continuous --category "market-news::finance" --kafka &
```

### Automatic Pagination

The scraper automatically paginates through the API to fetch the requested number of articles:

```bash
# Fetch 100 articles (automatically fetches page 1, 2, 3... until 100 articles collected)
python seeking_scraper.py --limit 100

# Output:
# 📄 Fetching articles from SeekingAlpha API...
# 📄 Page 1: +50 articles (total: 50)
# 📄 Page 2: +50 articles (total: 100)
# ✓ Reached limit of 100 articles
# ✓ Found 100 articles total
```

Pagination is always enabled and works transparently with the API.

### Persistent Scraping (Avoid Re-scraping)

The scraper automatically tracks scraped articles in a history file:

```bash
# First run - scrapes 20 articles
python seeking_scraper.py --limit 20

# Second run - only scrapes NEW articles not in history
python seeking_scraper.py --limit 20

# Force re-scraping all articles
python seeking_scraper.py --force --limit 20
```

History file (`scraped_history.json`) stores:
```json
{
  "https://seekingalpha.com/articles/example-1": "2026-04-20T10:30:22.123456",
  "https://seekingalpha.com/articles/example-2": "2026-04-20T10:32:15.654321"
}
```

### History TTL (Auto-Eviction)

Prevent history file from growing indefinitely by auto-evicting old entries:

```bash
# Keep history for 30 days (default)
python seeking_scraper.py --limit 100

# Keep history for 7 days only
python seeking_scraper.py --history-ttl-days 7 --limit 100

# Keep history forever (disable TTL)
python seeking_scraper.py --history-ttl-days 0 --limit 100
```

**How it works:**
- On each scraper run, entries older than TTL are automatically removed
- Timestamp is compared against `datetime.now()`
- Only applies to history file, not downloaded articles
- Useful for long-running production deployments

**Example with 7-day TTL:**
```bash
# Day 1: Scrape 100 articles (all saved to history)
python seeking_scraper.py --history-ttl-days 7 --limit 100

# Day 8: History auto-evicts Day 1 articles
# Scraper may re-scrape those articles if they appear in feed again
python seeking_scraper.py --history-ttl-days 7 --limit 100

# Output:
# [DEBUG] Auto-evicting 100 expired entries (older than 7 days)
# [DEBUG] History now has 200 entries
```

**Docker environment variable:**
```yaml
env:
  - name: HISTORY_TTL_DAYS
    value: "30"  # or "0" to disable
```

## 💻 Programmatic Usage

```python
from seeking_scraper import SeekingScraper

# Create scraper instance
scraper = SeekingScraper(
    output_dir='articles',
    verbose=True,
    category='market-news::consumer',  # Target specific category
    kafka_enabled=True,  # Publishes to Kafka immediately as articles are found
    kafka_topic='seeking-news'
)

# Single run mode - scrape once and exit
scraper.scrape_and_save(
    limit=50,
    format='both',
    delay=2.0
)

# Continuous mode - infinite loop with 5-minute pauses
scraper.scrape_and_save(
    limit=50,
    continuous=True,
    continuous_interval=300  # 5 minutes
)

# Custom interval (10 minutes)
scraper.scrape_and_save(
    limit=100,
    continuous=True,
    continuous_interval=600,  # 10 minutes
    delay=1.0
)

# Force re-scrape (ignore history)
scraper.scrape_and_save(
    limit=10,
    force=True
)

# Get articles with metadata from API (for custom processing)
# This will filter out already-scraped articles automatically
articles = scraper.get_articles_with_metadata(limit=50)
for article in articles:
    print(f"{article['title']} - {article['url']}")
    print(f"  Content preview: {article['content'][:100]}...")

# Process each article individually
for article in articles:
    # Article already has full content from API
    article_data = scraper.scrape_article(
        article['url'], 
        article_metadata=article
    )
    if article_data:
        # Custom processing here
        scraper.save_article(article_data, format='markdown')
```

### Single Article Scraping

```python
from wsj_scraper import SeekingScraper

scraper = SeekingScraper()

# Scrape one article
article = scraper.scrape_article('https://seekingalpha.com/articles/example')

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

### Kubernetes Deployment
- ✅ **Docker Support** - Containerized deployment ready
- ✅ **Stateless Design** - No need for distributed coordination (API returns full content in one call)
- ✅ **Horizontal Scaling** - Run multiple pods with different categories for parallel processing

**Why No Distributed Mode?**
Unlike browser-based scrapers (like WSJ) that require:
1. First call: Fetch article URLs from listing pages
2. Second call: Scrape full article content (expensive with antibot bypass)

SeekingAlpha API returns **everything in one call**:
- Article metadata (title, date, author)
- Full article content (HTML)
- All in a single JSON response

This makes distributed coordination unnecessary - just run multiple pods with different categories!

**Kubernetes Multi-Category Example (Continuous Mode):**
```bash
# Pod 1: Consumer news (continuous scraping every 5 minutes)
kubectl run seeking-consumer \
  --image=palantiracr.azurecr.io/palantir/seeking-scraper:latest \
  --restart=Never \
  --command -- python seeking_scraper.py \
    --continuous \
    --kafka \
    --category "market-news::consumer" \
    --kafka-topic seeking-news \
    --limit 100

# Pod 2: Tech news (continuous scraping every 10 minutes)
kubectl run seeking-tech \
  --image=palantiracr.azurecr.io/palantir/seeking-scraper:latest \
  --restart=Never \
  --command -- python seeking_scraper.py \
    --continuous \
    --continuous-interval 600 \
    --kafka \
    --category "market-news::tech" \
    --kafka-topic seeking-news \
    --limit 100

# Pod 3: All news (continuous scraping every 5 minutes)
kubectl run seeking-all \
  --image=palantiracr.azurecr.io/palantir/seeking-scraper:latest \
  --restart=Never \
  --command -- python seeking_scraper.py \
    --continuous \
    --kafka \
    --category "market-news::all" \
    --kafka-topic seeking-news \
    --limit 100 \
    --verbose
```

**Deployment YAML Example:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: seeking-scraper-consumer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: seeking-scraper
      category: consumer
  template:
    metadata:
      labels:
        app: seeking-scraper
        category: consumer
    spec:
      containers:
      - name: scraper
        image: palantiracr.azurecr.io/palantir/seeking-scraper:latest
        command: ["python", "seeking_scraper.py"]
        args:
          - "--continuous"
          - "--kafka"
          - "--category=market-news::consumer"
          - "--kafka-topic=seeking-news"
          - "--limit=100"
          - "--verbose"
        env:
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka.default.svc.cluster.local:9092"
        - name: CATEGORY
          value: "market-news::consumer"
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

## 🚢 Docker

Image available at:
   - Azure ACR: `docker pull palantiracr.azurecr.io/palantir/seeking-scraper:latest`

**Features:**
- ✅ Multi-platform builds (amd64, arm64)
- ✅ Vulnerability scanning (Trivy/Azure Defender)
- ✅ Automated tagging (latest, semver, sha)
- ✅ Build caching (75-87% faster)
- ✅ Playwright + Chromium included (for stealth mode)
- ✅ Process cleanup utilities (procps package)

**Environment Variables:**
```bash
# Basic configuration
CATEGORY=market-news::all           # Article category
LIMIT=100                           # Max articles per run
DELAY=2.0                           # Delay between articles (seconds)

# Continuous mode
CONTINUOUS=false                    # Enable infinite loop mode
CONTINUOUS_INTERVAL=300             # Seconds between iterations (5 min)

# Kafka integration
KAFKA_ENABLED=false                 # Enable Kafka publishing
KAFKA_TOPIC=seeking-news            # Kafka topic name
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Stealth mode and authentication
STEALTH_MODE=false                  # Enable browser emulation
HEADLESS=true                       # Run browser in headless mode
SEEKING_ALPHA_EMAIL=""              # Login email (for paywall bypass)
SEEKING_ALPHA_PASSWORD=""           # Login password

# History management
HISTORY_TTL_DAYS=30                 # Auto-evict entries older than N days
```

**Docker Compose Example:**
```yaml
version: '3.8'
services:
  seeking-scraper:
    image: palantiracr.azurecr.io/palantir/seeking-scraper:latest
    environment:
      CATEGORY: "market-news::all"
      LIMIT: 100
      DELAY: 2.0
      CONTINUOUS: "true"
      CONTINUOUS_INTERVAL: 300
      KAFKA_ENABLED: "true"
      KAFKA_BOOTSTRAP_SERVERS: "kafka:9092"
      KAFKA_TOPIC: "seeking-news"
      STEALTH_MODE: "true"
      HEADLESS: "true"
      HISTORY_TTL_DAYS: 30
      SEEKING_ALPHA_EMAIL: "${SEEKING_ALPHA_EMAIL}"
      SEEKING_ALPHA_PASSWORD: "${SEEKING_ALPHA_PASSWORD}"
    volumes:
      - ./data:/data/articles
      - ./history:/app/history
    restart: unless-stopped
```


## 🔧 Command Line Options

```
Options:
  -h, --help            show this help message and exit
  --output-dir OUTPUT_DIR, -o OUTPUT_DIR
                        Output directory for articles (default: articles)
  --limit LIMIT, -l LIMIT
                        Number of articles to scrape from API (default: 10000)
  --format {json,markdown,both}, -f {json,markdown,both}
                        Output format (default: both)
  --category CATEGORY   Article category to scrape (default: market-news::all)
                        Examples: market-news::consumer, market-news::tech, etc.
  --delay DELAY, -d DELAY
                        Delay between article processing in seconds (default: 2.0)
  --verbose, -v         Enable verbose logging
  --history-file HISTORY_FILE
                        History file to track scraped articles (default: scraped_history.json)
  --force               Force re-scraping of articles already in history
  --save-local          Save articles locally even when Kafka is enabled
  --continuous          Run in continuous mode (infinite loop with pauses between iterations)
  --continuous-interval INTERVAL
                        Seconds to wait between scraping iterations in continuous mode
                        (default: 300 = 5 minutes)
  
Stealth Mode Options:
  --stealth             Use stealth mode with browser emulation (slower but bypasses anti-bot detection)
  --no-headless         Show browser window when using stealth mode (for debugging)
  --login-email EMAIL   Email for Seeking Alpha login (can also use SEEKING_ALPHA_EMAIL env var)
  --login-password PASS Password for Seeking Alpha login (can also use SEEKING_ALPHA_PASSWORD env var)
  --history-ttl-days DAYS
                        Days to keep articles in history before auto-eviction (default: 30)
                        Set to 0 to disable TTL (keep forever)

Kafka Options:
  --kafka, --enable-kafka
                        Enable Kafka publishing (publishes immediately as articles are found)
  --kafka-config KAFKA_CONFIG
                        Kafka configuration file (default: kafka_config.properties)
  --kafka-bootstrap-servers KAFKA_BOOTSTRAP_SERVERS
                        Kafka bootstrap servers (default: KAFKA_BOOTSTRAP_SERVERS env or localhost:9092)
  --kafka-topic KAFKA_TOPIC
                        Kafka topic name (default: KAFKA_TOPIC env or seeking-news)
```

**Notes:** 
- The scraper only works with categories - no URL file input
- Articles are fetched from the API and published to Kafka immediately (no batching)
- Use `--continuous` for production deployments that need to run 24/7
```

## ⚠️ Important Notes

### When to Use Each Mode

**Standard Mode (Default):**
- ✅ Use first - it's faster and simpler
- ✅ Works for most scraping scenarios
- ✅ Low resource consumption
- ⚠️ May encounter content cutoff or anti-bot detection

**Stealth Mode (`--stealth`):**
- ✅ Use when standard mode hits anti-bot detection
- ✅ Required for bypassing captchas
- ✅ Needed for authenticated access (paywalled content)
- ✅ Auto-recovery from 403 errors with browser cleanup
- ⚠️ Slower and uses more resources (browser overhead)

### API-Based Approach (Standard Mode)
- Uses SeekingAlpha's public API (minimal anti-bot issues)
- Simple HTTP requests with curl_cffi (browser impersonation)
- No browser automation required
- Fast and efficient data extraction

### Browser-Based Approach (Stealth Mode)
- Full Playwright + Chromium browser automation
- Advanced anti-bot bypass with captcha handling
- Human behavior simulation (mouse movements, tremor, timing)
- Automatic 403 error recovery with process cleanup
- Persistent browser context with login state

### Content Access
- Seeking Alpha provides article content through their API
- Content is returned as HTML which is parsed to clean text
- Articles include title, publish date, and full content
- Paywall content requires login (use `--stealth` with credentials)

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
python seeking_scraper.py --verbose --limit 2
```

### "No articles found"

**Cause:** API may be down or category filter is incorrect  
**Solution:** Run with `--verbose` to see API responses:

```bash
python seeking_scraper.py --verbose --limit 1
```

Check the API response and verify the category parameter is valid.

### API Connection Issues

**Symptom:** Connection errors or timeouts  
**Cause:** Network issues or rate limiting  
**Solution:** Increase delay between requests:

```bash
python seeking_scraper.py --delay 3.0 --limit 10
```

### Installation Issues

```bash
# Reinstall dependencies
pip install -r requirements.txt

# Check installation
python -c "from curl_cffi import requests; print('✅ curl_cffi OK')"
python -c "from bs4 import BeautifulSoup; print('✅ BeautifulSoup OK')"

# For stealth mode, verify Playwright
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright OK')"
playwright install chromium
```

### Stealth Mode: 403 Errors / Anti-Bot Detection

**Symptom:** Receiving HTTP 403 errors repeatedly  
**Cause:** Website detected bot behavior or rate limiting  
**Auto-Recovery:** After 3 consecutive 403 errors, the scraper automatically:
1. Terminates all Playwright browser processes (SIGTERM → SIGKILL)
2. Deletes persistent browser context and cookies
3. Restarts with fresh session
4. Logs debug info: `[DEBUG] 403 detected (X/3), cleaning browser context...`

**Manual Recovery:**
```bash
# Force cleanup of stuck Playwright processes
pkill -9 -f playwright

# Delete persistent browser context
rm -rf /app/history/seeking_alpha_context

# Restart scraper
python seeking_scraper.py --stealth --limit 20
```

### Stealth Mode: Captcha Challenges

**Symptom:** Stuck on PerimeterX "Press & Hold" captcha  
**Cause:** Website requires human verification  
**Auto-Bypass:** The scraper automatically:
1. Detects captcha iframe (`style*='display: block'`)
2. Moves mouse to "Press & Hold" button with human-like path
3. Holds down mouse button while monitoring progress bar
4. Applies micro-movements (1-3px jitter) every 0.4-0.7s to simulate hand tremor
5. Waits until progress reaches 98% of target width
6. Releases mouse button
7. Waits for captcha to clear (max 10s)

**Debug Captcha Bypass:**
```bash
# Watch the captcha bypass in action (visible browser)
python seeking_scraper.py --stealth --no-headless --limit 1 --verbose

# Output shows:
# [DEBUG] Captcha detected! Attempting bypass...
# [DEBUG] Moving to button center: (x, y)
# [DEBUG] Mouse down on button, holding...
# [DEBUG] Progress: 45px / 200px (22.5%)
# [DEBUG] Progress: 180px / 200px (90.0%)
# [DEBUG] Progress: 196px / 200px (98.0%) - releasing!
# [DEBUG] Mouse released, waiting for captcha to clear...
# [DEBUG] ✓ Captcha bypassed successfully!
```

**If Captcha Bypass Fails:**
- Increase `--delay` to slow down scraping (reduces captcha frequency)
- Check that Playwright browsers are installed: `playwright install chromium`
- Verify `procps` package installed (Docker): `apt-get install procps`
- Use authenticated login to reduce captcha challenges

### Stealth Mode: Process Cleanup Issues

**Symptom:** `pgrep: command not found` in Docker logs  
**Cause:** `procps` package not installed in container  
**Solution:** Already fixed in Dockerfile (line 9), but if building custom image:
```dockerfile
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    wget \
    gnupg \
    procps \
    && rm -rf /var/lib/apt/lists/*
```

**Symptom:** Zombie Playwright processes after crashes  
**Cause:** Browser not terminated gracefully  
**Solution:** The scraper now uses proper SIGTERM → SIGKILL sequence:
```python
# Graceful shutdown (10s timeout)
subprocess.run(['pkill', '-15', '-f', 'playwright'], ...)
time.sleep(1)
# Force kill if still running
subprocess.run(['pkill', '-9', '-f', 'playwright'], ...)
```

## 🎓 Advanced Usage

### Filter Articles by Keyword

```python
from wsj_scraper import SeekingScraper

scraper = SeekingScraper()

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
from wsj_scraper import SeekingScraper
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
scraper = SeekingScraper()
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

## 📊 API-Based vs Browser-Based Scraping

| Feature | API-Based (This Scraper) | Browser-Based (Selenium/Puppeteer) |
|---------|--------------------------|-------------------------------------|
| **Speed** | ⭐⭐⭐⭐⭐ Very Fast | ⭐⭐ Slow |
| **Resource Usage** | ⭐⭐⭐⭐⭐ Very Low | ⭐⭐ High (browser overhead) |
| **Anti-Bot Issues** | ✅ None (API access) | ⚠️ Requires bypass techniques |
| **Reliability** | ⭐⭐⭐⭐⭐ Stable API | ⭐⭐⭐ DOM changes break selectors |
| **Ease of Use** | ⭐⭐⭐⭐⭐ Simple HTTP | ⭐⭐⭐ Complex setup |
| **Maintenance** | ⭐⭐⭐⭐⭐ Low | ⭐⭐ High (selector updates) |

**Why API-Based is Better:**
- No browser automation overhead
- Structured JSON responses (no HTML parsing complexity)
- No anti-bot detection to bypass
- Much faster and more reliable
- Lower resource consumption (perfect for Kubernetes scaling)

## 📚 Resources

- [Seeking Alpha Official Site](https://seekingalpha.com)
- [curl_cffi GitHub](https://github.com/yifeikong/curl_cffi)
- [BeautifulSoup Documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)

## 📄 License

[TODO]

---

**Built with curl_cffi & BeautifulSoup** - Fast, efficient API-based scraping 🚀
