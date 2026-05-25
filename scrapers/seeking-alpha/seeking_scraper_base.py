#!/usr/bin/env python3
"""
Base class for Seeking Alpha News Scrapers
Contains common functionality for history management, Kafka publishing, etc.
"""

import json
import os
import re
import sys
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from http.cookiejar import CookieJar, Cookie
from curl_cffi import requests

# Add parent directory to path for common package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import kafka_config as kafka_config_
from common import ProxyRotator

def convert_playwright_cookies_to_cookiejar(playwright_cookies: List[Dict]) -> CookieJar:
    """
    Convert Playwright cookies format to http.cookiejar.CookieJar format
    compatible with curl_cffi's CookieTypes.

    Playwright cookie format (from page.context.cookies()):
        {
            'name': str,
            'value': str,
            'domain': str,
            'path': str,
            'expires': float,  # Unix timestamp, -1 for session cookies
            'httpOnly': bool,
            'secure': bool,
            'sameSite': str  # 'Strict', 'Lax', 'None'
        }

    Args:
        playwright_cookies: List of cookie dictionaries from Playwright

    Returns:
        CookieJar object compatible with curl_cffi requests
    """
    jar = CookieJar()

    for pw_cookie in playwright_cookies:
        # Convert expires from Unix timestamp to None (session) or timestamp
        # Playwright uses -1 for session cookies
        expires = None
        if pw_cookie.get('expires', -1) > 0:
            expires = int(pw_cookie['expires'])

        # Create http.cookiejar.Cookie object
        # Note: Cookie constructor has many required parameters
        cookie = Cookie(
            version=0,
            name=pw_cookie['name'],
            value=pw_cookie['value'],
            port=None,
            port_specified=False,
            domain=pw_cookie['domain'],
            domain_specified=True,
            domain_initial_dot=pw_cookie['domain'].startswith('.'),
            path=pw_cookie['path'],
            path_specified=True,
            secure=pw_cookie.get('secure', False),
            expires=expires,
            discard=expires is None,  # Session cookie if no expiry
            comment=None,
            comment_url=None,
            rest={'HttpOnly': pw_cookie.get('httpOnly', False)},
            rfc2109=False
        )

        jar.set_cookie(cookie)

    return jar


class SeekingScraperBase(ABC):
    """Abstract base class for Seeking Alpha scrapers"""

    # History TTL: entries older than this will be automatically evicted
    HISTORY_TTL_DAYS = 30

    def __init__(
        self,
        output_dir: str = "news",
        verbose: bool = False,
        api_base_url: str = "https://seekingalpha.com/api/v3/news",
        article_base_url: str = "https://seekingalpha.com/news",
        category: str = "market-news::all",
        history_file: str = "scraped_history.json",
        kafka_enabled: bool = False,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "seeking-news",
        kafka_config_file: Optional[str] = None,
        history_ttl_days: Optional[int] = None
    ):
        self.api_base_url = api_base_url
        self.article_base_url = article_base_url
        self.category = category

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self.history_file = Path(history_file)

        # Configure history TTL (default: 30 days)
        if history_ttl_days is not None:
            self.HISTORY_TTL_DAYS = history_ttl_days

        # Load Kafka configuration from file
        self.kafka_config: Optional[kafka_config_.KafkaConfig] = None
        if kafka_config_file or Path("kafka_config.properties").exists():
            try:
                self.kafka_config = kafka_config_.load_kafka_config(kafka_config_file)
            except Exception as e:
                print(f"⚠️  Failed to load Kafka config: {e}")
                self.kafka_config = None

        # Initialize session cookies as empty list (Playwright format)
        # Will be converted to CookieJar when used with curl_cffi
        self.session_cookies = []

        # Kafka configuration (CLI args override config file)
        self.kafka_enabled = kafka_enabled
        if self.kafka_config:
            self.kafka_bootstrap_servers = self.kafka_config.bootstrap_servers
        else:
            self.kafka_bootstrap_servers = kafka_bootstrap_servers

        self.kafka_topic = kafka_topic
        self.kafka_producer = None

        # Load scraping history
        self.scraped_history = self._load_history()

        # Configure logging (subclass should set logger name)
        if verbose:
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self.logger = logging.getLogger(self.__class__.__name__)
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger = logging.getLogger(self.__class__.__name__)
            self.logger.setLevel(logging.WARNING)

        # Initialize Kafka producer if enabled
        if kafka_enabled:
            self._init_kafka()

        self.proxy_rotator = ProxyRotator()
        if self.proxy_rotator.is_enabled():
            self.logger.info(f"🔄 Proxy rotation enabled with {self.proxy_rotator.get_healthy_count()} proxies")
        else:
            self.proxy_rotator = None

    def _cleanup_old_entries(self, history: Dict[str, str]) -> Dict[str, str]:
        """
        Remove entries older than HISTORY_TTL_DAYS from history

        Args:
            history: Dictionary of {url: timestamp_iso}

        Returns:
            Cleaned history with old entries removed
        """
        if not history:
            return {}

        cutoff_date = datetime.now() - timedelta(days=self.HISTORY_TTL_DAYS)
        cleaned = {}
        removed_count = 0

        for url, timestamp_str in history.items():
            try:
                # Parse ISO format timestamp
                scraped_date = datetime.fromisoformat(timestamp_str)

                # Keep only entries within TTL
                if scraped_date >= cutoff_date:
                    cleaned[url] = timestamp_str
                else:
                    removed_count += 1
                    self.logger.debug(f"Evicting old entry: {url} (scraped {timestamp_str})")
            except (ValueError, TypeError) as e:
                # Keep entries with invalid timestamps (shouldn't happen, but be safe)
                self.logger.warning(f"Invalid timestamp for {url}: {timestamp_str}, keeping entry")
                cleaned[url] = timestamp_str

        if removed_count > 0:
            print(f"🧹 Evicted {removed_count} entries older than {self.HISTORY_TTL_DAYS} days from history")
            self.logger.info(f"Evicted {removed_count} old entries from history")

        return cleaned

    def _load_history(self) -> Dict[str, str]:
        """Load scraping history from JSON file and clean up old entries"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    original_count = len(history)
                    print(f"📚 Loaded {original_count} entries from {self.history_file}")

                    # Clean up old entries (older than HISTORY_TTL_DAYS)
                    cleaned_history = self._cleanup_old_entries(history)

                    # Save cleaned history back if any entries were removed
                    if len(cleaned_history) < original_count:
                        # Temporarily set history to cleaned version for saving
                        temp_history = self.scraped_history if hasattr(self, 'scraped_history') else None
                        self.scraped_history = cleaned_history
                        self._save_history()
                        # Restore or keep cleaned version
                        if temp_history is None:
                            pass  # First load, keep cleaned_history
                        else:
                            self.scraped_history = temp_history

                    return cleaned_history
            except Exception as e:
                print(f"⚠️  Could not load history file: {e}")
                return {}
        else:
            print(f"📝 Creating new history file: {self.history_file}")
            return {}

    def _save_history(self) -> None:
        """Save scraping history to JSON file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.scraped_history, f, indent=2, ensure_ascii=False)
            self.logger.debug(f"History saved: {len(self.scraped_history)} articles")
        except Exception as e:
            self.logger.error(f"Could not save history file: {e}")
            print(f"⚠️  Could not save history: {e}")

    def _is_already_scraped(self, url: str) -> bool:
        """Check if URL has already been scraped"""
        return url in self.scraped_history

    def _mark_as_scraped(self, url: str, persist: bool = True) -> None:
        """Mark URL as scraped in history"""
        self.scraped_history[url] = datetime.now().isoformat()
        if persist:
            self._save_history()

    def _init_kafka(self) -> None:
        """Initialize Kafka producer"""
        try:
            from confluent_kafka import Producer

            # Use configuration from file if available, otherwise use defaults
            if self.kafka_config:
                conf = self.kafka_config.get_kafka_config()
                self.logger.info(f"📋 Using Kafka config from {self.kafka_config.config_file}")
            else:
                # Default Confluent Kafka configuration
                conf = {
                    'bootstrap.servers': self.kafka_bootstrap_servers,
                    'acks': 'all',  # Wait for all replicas
                    'retries': 3,
                    'max.in.flight.requests.per.connection': 1,  # Ensure ordering
                    'compression.type': 'snappy',  # Efficient compression
                    'linger.ms': 10,  # Small batching delay
                }

            self.logger.debug(conf)
            self.kafka_producer = Producer(conf)
            self.logger.info(f"Kafka producer initialized and connected to : {conf['bootstrap.servers']}")

        except ImportError:
            raise ImportError(
                "Kafka integration requires 'confluent-kafka' package. "
                "Install with: pip install confluent-kafka"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Kafka producer: {e}")
            print(f"❌ Kafka connection failed: {e}")
            raise

    def _delivery_callback(self, err, msg):
        """Callback for Kafka message delivery reports"""
        if err:
            self.logger.error(f"Message delivery failed: {err}")
        else:
            self.logger.info(
                f"Published to Kafka: topic={msg.topic()}, "
                f"partition={msg.partition()}, "
                f"offset={msg.offset()}"
            )

    def _publish_to_kafka(self, article_data: Dict) -> bool:
        """
        Publish article to Kafka topic

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.kafka_producer:
            return False

        try:
            key = article_data.get('url', '')
            kafka_message = {
                'url': article_data.get('url'),
                'title': article_data.get('title'),
                'author': article_data.get('author'),
                'published_date': article_data.get('published_date'),
                'scraped_at': article_data.get('scraped_at'),
                'word_count': article_data.get('word_count', 0),
                'excerpt': article_data.get('excerpt', ''),
                'content': article_data.get('content'),
                'category': self.category,
                'content_md': self.to_markdown(article_data)
            }

            # Serialize to JSON
            message_value = json.dumps(kafka_message).encode('utf-8')
            message_key = key.encode('utf-8') if key else None

            # Produce message (async)
            self.kafka_producer.produce(
                topic=self.kafka_topic,
                key=message_key,
                value=message_value,
                callback=self._delivery_callback
            )

            # Poll to handle delivery callbacks
            self.kafka_producer.poll(0)

            print(f"  📡 Published to Kafka: {self.kafka_topic}")
            return True

        except BufferError:
            # Producer queue is full, flush and retry
            self.logger.warning("Producer queue full, flushing...")
            self.kafka_producer.flush()
            return self._publish_to_kafka(article_data)
        except Exception as e:
            self.logger.error(f"Failed to publish to Kafka: {e}")
            print(f"  ⚠️  Kafka publish failed: {e}")
            return False

    def _base_fetch_articles_from_api(self, page_number: int, page_size: int) -> List[Dict]:
        """
        Fetch articles from SeekingAlpha API

        Args:
            page_number: Page number to fetch (1-indexed)
            page_size: Number of articles per page

        Returns:
            List of article dictionaries with metadata
        """
        # Build API URL with pagination params
        params = {
            'filter[category]': self.category,
            'filter[since]': '0',
            'filter[until]': str(int(time.time())),
            'page[size]': str(page_size),
            'page[number]': str(page_number),
            'include': 'primaryTickers,secondaryTickers',
            'isMounting': 'true',
            'fields[news]': 'title,date,comment_count,content,disclosure,primaryTickers,secondaryTickers,tag,gettyImageUrl,publishOn',
            'fields[tag]': 'slug,name'
        }

        # More comprehensive headers to mimic real browser
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'accept-encoding': 'gzip, deflate, br',
            'referer': f'https://seekingalpha.com/{self.category.replace("::", "/")}',
            'origin': 'https://seekingalpha.com',
            'sec-ch-ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=1, i'
        }

        try:
            self.logger.debug(f"Fetching API: {self.api_base_url}")
            self.logger.debug(f"Params: {params}")
            self.logger.debug(f"Headers: {headers}")

            # Convert Playwright cookies to CookieJar for curl_cffi compatibility
            curl_cookies = convert_playwright_cookies_to_cookiejar(self.session_cookies) if self.session_cookies else None
            self.logger.info(curl_cookies)

            proxy = None
            if self.proxy_rotator:
                proxy = self.proxy_rotator.get_proxy_sync()

            response = requests.get(
                self.api_base_url,
                params=params,
                cookies=curl_cookies,
                headers=headers,
                proxy=proxy,
                impersonate="chrome_android",
                timeout=30
            )

            self.logger.debug(f"Response status: {response.status_code}")
            if response.status_code != 200:
                self.logger.debug(f"Response content: {response.content}")

            if response.status_code != 200:
                self.logger.error(f"API returned status {response.status_code}")
                self.logger.error(f"Page response : {response.content}")
                return []

            data = response.json()
            articles = []

            # Parse JSON response
            if 'data' in data:
                for item in data['data']:
                    attributes = item.get('attributes', {})
                    article_id = item.get('id', '')

                    # Build article URL
                    article_url = f"https://seekingalpha.com/news/{article_id}"

                    articles.append({
                        'id': article_id,
                        'url': article_url,
                        'title': attributes.get('title', ''),
                        'date': attributes.get('publishOn', ''),
                        'content': attributes.get('content', ''),
                        'raw_data': item  # Store full data for later use
                    })

                self.logger.debug(f"Parsed {len(articles)} articles from API response")

            return articles

        except Exception as e:
            self.logger.error(f"Error fetching from API: {e}", exc_info=self.verbose)
            raise

    def to_markdown(self, article_data: Dict) -> str:
        """Convert article data to markdown format"""
        markdown_content = f"""# {article_data['title']}

**Author:** {article_data['author']}
**Published:** {article_data['published_date']}
**URL:** {article_data['url']}
**Scraped:** {article_data['scraped_at']}
**Word Count:** {article_data.get('word_count', 0)}
"""

        if article_data.get('excerpt'):
            markdown_content += f"\n**Summary:** {article_data['excerpt']}\n"

        markdown_content += f"\n---\n\n{article_data['content']}\n"
        return markdown_content

    def close(self) -> None:
        """Cleanup resources (Kafka producer, etc.)"""
        if self.kafka_producer:
            try:
                # Flush all messages (wait up to 10 seconds)
                remaining = self.kafka_producer.flush(timeout=10.0)
                if remaining > 0:
                    self.logger.warning(f"{remaining} messages were not delivered")
                else:
                    self.logger.info("All messages delivered successfully")
                self.logger.info("Kafka producer closed")
            except Exception as e:
                self.logger.error(f"Error closing Kafka producer: {e}")

    def remove_copyright(self, text: str) -> str:
        """Remove copyright notices from text"""
        # Remove common copyright patterns
        patterns = [
            r'Copyright.*?Inc\.',
            r'©.*?Inc\.',
            r'All rights reserved\.',
        ]

        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()

    def save_article(self, article_data: Dict, format: str = 'both', force_save: bool = False) -> None:
        """
        Save article to file (json, markdown, or both)

        Args:
            article_data: Article data to save
            format: Output format (json, markdown, both)
            force_save: Force local save even if Kafka is enabled
        """
        if not article_data or not article_data.get('content'):
            self.logger.warning("No article data or content to save")
            return

        # Skip local save if Kafka is enabled (unless force_save=True)
        if self.kafka_enabled and not force_save:
            self.logger.debug("Kafka enabled, skipping local file save (use --save-local to force)")
            return

        # Create safe filename
        safe_title = re.sub(r'[^\w\s-]', '', article_data['title'])[:100]
        safe_title = re.sub(r'[-\s]+', '-', safe_title).strip('-')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"{timestamp}_{safe_title}"

        # Save JSON
        if format in ['json', 'both']:
            json_path = self.output_dir / f"{base_filename}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, indent=2, ensure_ascii=False)
            print(f"  ✓ Saved JSON: {json_path.name}")
            self.logger.debug(f"Saved JSON: {json_path}")

        # Save Markdown
        if format in ['markdown', 'both']:
            md_path = self.output_dir / f"{base_filename}.md"
            markdown_content = self.to_markdown(article_data)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            print(f"  ✓ Saved Markdown: {md_path.name}")
            self.logger.debug(f"Saved Markdown: {md_path}")

    # Abstract methods to be implemented by subclasses
    @abstractmethod
    def get_articles_with_metadata(self, limit: int = 20, filter_scraped: bool = True) -> List[Dict]:
        """
        Get articles with metadata from SeekingAlpha
        Must be implemented by subclass

        Args:
            limit: Maximum number of articles to collect
            filter_scraped: If True, filter out already-scraped articles

        Returns:
            List of article dictionaries with metadata
        """
        pass

    @abstractmethod
    def before_scraping(self):
        pass

    @abstractmethod
    def scrape_article(self, url: str, article_metadata: Optional[Dict] = None) -> Optional[Dict]:
        """
        Scrape a single SeekingAlpha article
        Must be implemented by subclass

        Args:
            url: Article URL
            article_metadata: Optional pre-fetched metadata

        Returns:
            Article data dictionary
        """
        pass

    def scrape_and_save(
        self,
        limit: int = 20,
        format: str = 'both',
        delay: float = 2.0,
        force: bool = False,
        save_local: bool = False,
        continuous: bool = False,
        continuous_interval: int = 300
    ) -> None:
        """
        Main method to scrape and save articles
        Publishes to Kafka immediately as articles are discovered

        Args:
            limit: Number of articles to scrape per iteration
            format: Output format (json, markdown, both)
            delay: Delay between article scraping in seconds
            force: Force re-scraping of already scraped articles
            save_local: Force local file save even if Kafka is enabled
            continuous: If True, run in continuous mode (infinite loop)
            continuous_interval: Seconds to wait between scraping iterations (default: 300 = 5 minutes)
        """
        self.logger.info("Call before scraping")
        self.before_scraping()
        
        if continuous:
            self.logger.info(f"Starting continuous scraping mode (interval: {continuous_interval}s)")
            print(f"\n🔄 Continuous mode enabled - will scrape every {continuous_interval // 60} minutes")
            print(f"   Press Ctrl+C to stop\n")

            iteration = 0
            try:
                while True:
                    iteration += 1
                    print(f"\n{'=' * 60}")
                    print(f"🔄 Iteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"{'=' * 60}")

                    # Run one scraping iteration
                    self._scrape_iteration(
                        limit=limit,
                        format=format,
                        delay=delay,
                        force=force,
                        save_local=save_local
                    )

                    # Wait before next iteration
                    print(f"\n⏸️  Waiting {continuous_interval // 60} minutes before next iteration...")
                    print(f"   Next run at: {(datetime.now() + __import__('datetime').timedelta(seconds=continuous_interval)).strftime('%Y-%m-%d %H:%M:%S')}")
                    time.sleep(continuous_interval)

            except KeyboardInterrupt:
                print(f"\n\n⚠️  Continuous mode interrupted by user")
                print(f"   Completed {iteration} iteration(s)")
                if self.kafka_enabled:
                    self.close()
                return
        else:
            # Single run mode
            self._scrape_iteration(
                limit=limit,
                format=format,
                delay=delay,
                force=force,
                save_local=save_local
            )

    def _scrape_iteration(
        self,
        limit: int = 20,
        format: str = 'both',
        delay: float = 2.0,
        force: bool = False,
        save_local: bool = False
    ) -> None:
        """
        Single iteration of scraping - common logic for both scraper types

        Args:
            limit: Number of articles to scrape
            format: Output format (json, markdown, both)
            delay: Delay between article scraping in seconds
            force: Force re-scraping of already scraped articles
            save_local: Force local file save even if Kafka is enabled
        """
        self.logger.info("Starting scrape iteration")

        # Notify about save behavior
        if self.kafka_enabled and not save_local:
            print(f"\n📡 Kafka mode: Articles will be published to Kafka immediately as discovered")
            print(f"   Use --save-local to also save files locally")
        elif self.kafka_enabled and save_local:
            print(f"\n📡 Kafka mode + local save: Articles published to Kafka AND saved locally")

        print(f"\n🔍 Fetching articles from SeekingAlpha (category: {self.category})...")
        self.logger.info(f"Starting scraping (category: {self.category})")
        print("=" * 60)

        success_count = 0
        paywall_count = 0
        error_count = 0
        total_processed = 0

        try:
            # Get articles from subclass implementation
            articles = self.get_articles_with_metadata(limit=limit, filter_scraped=not force)

            # Process each article
            for article_metadata in articles:
                if total_processed >= limit:
                    break

                url = article_metadata['url']
                total_processed += 1

                print(f"\n[{total_processed}/{min(limit, len(articles))}] {article_metadata.get('title', url)}")

                try:
                    # Scrape article with pre-fetched metadata
                    article_data = self.scrape_article(url, article_metadata=article_metadata)

                    if article_data and article_data.get('content'):
                        word_count = article_data.get('word_count', 0)
                        if word_count > 10:
                            # Publish to Kafka immediately
                            if self.kafka_enabled:
                                self._publish_to_kafka(article_data)

                            # Save to file (if enabled)
                            self.save_article(article_data, format=format, force_save=save_local)

                            # Mark as scraped
                            self._mark_as_scraped(url)
                            success_count += 1
                        else:
                            print(f"  ⚠️  Only {word_count} words (likely paywalled)")
                            paywall_count += 1
                    else:
                        print(f"  ⚠️  No content found")
                        paywall_count += 1

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    self.logger.error(f"Error processing {url}: {e}", exc_info=self.verbose)
                    error_count += 1

                # Delay between articles
                if delay > 0 and total_processed < limit:
                    time.sleep(delay)

        except Exception as e:
            self.logger.error(f"Error during scraping: {e}", exc_info=self.verbose)
            print(f"❌ Error: {e}")

        # Cleanup
        if self.kafka_enabled:
            self.close()

        # Print summary
        print("\n" + "=" * 60)
        print(f"✅ Scraping complete!")
        if self.kafka_enabled:
            print(f"   Published to Kafka: {success_count}")
            print(f"   Kafka topic: {self.kafka_topic}")
            if save_local:
                print(f"   Also saved locally: {success_count}")
                print(f"   Output directory: {self.output_dir.absolute()}")
        else:
            print(f"   Successfully saved: {success_count}")
            print(f"   Output directory: {self.output_dir.absolute()}")
        print(f"   Paywalled/Limited: {paywall_count}")
        print(f"   Errors: {error_count}")
        print(f"   Total processed: {total_processed}")
        print(f"   Total in history: {len(self.scraped_history)}")
        print(f"   History file: {self.history_file.absolute()}")
