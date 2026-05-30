# Twitter / X Scraper

Scrapes tweets from search queries and user timelines using
[`@the-convocation/twitter-scraper`](https://github.com/the-convocation/twitter-scraper)
and publishes normalized records to Kafka — slotting into the same
env-driven / continuous / history-dedup pattern as the other scrapers in this
repo (`../seeking-alpha`, `../investing`).

> ⚠️ This library drives the unofficial X web API. Any account you log into may
> be rate-limited or banned. Prefer **cookie-based auth** over username/password.

## Layout

```
twitter/
├── src/
│   ├── index.ts      # orchestrator: cycle loop, continuous mode, signals
│   ├── config.ts     # env-var config + Confluent properties parsing
│   ├── scraper.ts    # library wrapper: auth, search/timeline, Tweet→record
│   ├── kafka.ts      # kafkajs producer (SASL_SSL Confluent Cloud or plaintext)
│   ├── history.ts    # file-backed tweet-id dedup with TTL
│   └── logger.ts
├── Dockerfile        # multi-stage TS build (context = scrapers/)
├── entrypoint.sh
├── .env.example
└── kafka_config.properties.example
```

## Quick start (local)

```bash
cd scrapers/twitter
npm install
cp .env.example .env        # edit queries/users + auth + kafka
npm run start               # tsx, no build step needed
```

Build & run compiled output:

```bash
npm run build && npm run serve
```

## Configuration

All config is via environment variables (or a `.env` file). See
[`.env.example`](./.env.example) for the full list. Key ones:

| Variable | Description | Default |
| --- | --- | --- |
| `TWITTER_QUERIES` | Comma-separated search queries (supports X operators) | — |
| `TWITTER_USERS` | Comma-separated usernames (no `@`) | — |
| `SEARCH_MODE` | `Top` / `Latest` / `Photos` / `Videos` / `Users` | `Latest` |
| `MAX_TWEETS` | Max tweets per query / user | `50` |
| `DELAY_MS` | Delay between requests (ms) | `1500` |
| `CONTINUOUS` / `CONTINUOUS_INTERVAL` | Loop forever every N seconds | `false` / `300` |
| `KAFKA_ENABLED` / `KAFKA_TOPIC` | Publish to Kafka | `false` / `twitter-tweets` |
| `KAFKA_BOOTSTRAP_SERVERS` | Broker(s); overrides config file | — |
| `KAFKA_CONFIG_FILE` | Confluent Cloud properties file | — |
| `HISTORY_FILE` / `HISTORY_TTL_DAYS` | Dedup store | `history/…` / `30` |
| `SAVE_LOCAL` / `OUTPUT_DIR` | Also write JSONL locally | `false` / `output` |

At least one of `TWITTER_QUERIES` / `TWITTER_USERS` must be set.

## Authentication

> **You must provide both the `auth_token` AND `ct0` cookies.** `ct0` is the
> CSRF token; without it every request returns `401`. The scraper normalizes
> the cookie domain to the host the library targets (`.x.com`), so cookies
> exported straight from **x.com** work fine.

Resolved in this order (first that yields a logged-in session wins):

1. **`TWITTER_COOKIES_FILE`** — a cookies file. Accepts any of:
   - a browser-extension export (JSON array of `{ "name": …, "value": … }`,
     e.g. from **Cookie-Editor**) — the most convenient,
   - a tough-cookie JSON array (`{ "key": … }`),
   - a raw cookie string (`auth_token=…; ct0=…`).

   On a successful credential login, fresh cookies are written back here so
   later runs skip login. Mount this as a volume to persist sessions.
2. **`TWITTER_COOKIES`** — raw cookie string (`auth_token=…; ct0=…`).
3. **`TWITTER_USERNAME` / `TWITTER_PASSWORD` / `TWITTER_EMAIL`** — credential
   login. Last resort; ban risk.

### Getting `auth_token` and `ct0`

1. Log in to **x.com** in your browser.
2. DevTools (F12) → **Application** → Cookies → `https://x.com`.
3. Copy the **`auth_token`** and **`ct0`** values into `cookies.json`, e.g.:
   ```json
   [
     { "name": "auth_token", "value": "PASTE_AUTH_TOKEN" },
     { "name": "ct0", "value": "PASTE_CT0" }
   ]
   ```
   (Or just `auth_token=…; ct0=…` as the file's only line.)

If the file loads but the session isn't logged in, the values are usually
expired — log out/in on x.com and re-copy them.

Unauthenticated runs work for some endpoints but are heavily limited.

## Output schema

Each tweet is published as JSON, keyed by author username:

```jsonc
{
  "id": "1790…",
  "username": "DeItaone",
  "name": "Walter Bloomberg",
  "text": "…",
  "permanentUrl": "https://twitter.com/…/status/…",
  "timestamp": 1716900000,
  "timeIso": "2026-05-28T12:00:00.000Z",
  "likes": 42, "retweets": 7, "replies": 3, "views": 12000,
  "hashtags": [], "mentions": [], "urls": [], "photos": [], "videos": [],
  "isRetweet": false, "isReply": false, "isQuoted": false,
  "source": "search:$TSLA",      // or "user:DeItaone"
  "scrapedAt": "2026-05-28T12:00:01.000Z",
  "content_md": "# Tweet by …\n\n**ID:** …\n…\n\n---\n\n<text>"
}
```

The **`content_md`** field renders every field above as a single markdown
document (heading + `**Key:** value` metadata block + `---` + tweet text).
Downstream sentiment analysis reads `$.content_md`
(`analysis/flink/statements/market_sentiment_analysis.sql`), matching the
WSJ / seeking-alpha scrapers.

## Kafka

- **Local** (docker-compose): set `KAFKA_BOOTSTRAP_SERVERS=kafka:29092`.
- **Confluent Cloud**: copy `kafka_config.properties.example` →
  `kafka_config.properties`, fill in API key/secret, and set
  `KAFKA_CONFIG_FILE=kafka_config.properties` (SASL_SSL / PLAIN auto-detected).

## Docker

Built from the `scrapers/` directory (shared build context):

```bash
cd scrapers
docker build -f twitter/Dockerfile -t twitter-scraper .
docker run --rm --env-file twitter/.env twitter-scraper
```

### docker-compose

Add a service alongside the others in `scrapers/docker-compose.yml`:

```yaml
  twitter-scraper:
    build:
      context: .
      dockerfile: twitter/Dockerfile
    container_name: twitter-scraper
    depends_on:
      kafka:
        condition: service_started
    restart: unless-stopped
    environment:
      - TWITTER_QUERIES=$TSLA,$NVDA,$AAPL
      - TWITTER_USERS=DeItaone,FirstSquawk
      - SEARCH_MODE=Latest
      - MAX_TWEETS=50
      - DELAY_MS=1500
      - CONTINUOUS=true
      - CONTINUOUS_INTERVAL=300
      - VERBOSE=true
      - KAFKA_ENABLED=true
      - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
      - KAFKA_TOPIC=twitter-tweets
      - TWITTER_COOKIES_FILE=/app/history/cookies.json
      - HISTORY_FILE=/app/history/scraped_history.json
      - HISTORY_TTL_DAYS=30
      - TZ=UTC
    volumes:
      - ./twitter/history:/app/history
    networks:
      - scraper-network
```
