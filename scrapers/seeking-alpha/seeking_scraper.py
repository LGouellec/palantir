#!/usr/bin/env python3
"""
Seeking Alpha News Scraper
Uses curl_cffi for HTTP requests to SeekingAlpha API
"""

import os
import time
from datetime import datetime
from typing import List, Dict, Optional

from curl_cffi import requests
from bs4 import BeautifulSoup
from seeking_scraper_base import SeekingScraperBase


class SeekingScraper(SeekingScraperBase):
    """Seeking Alpha Scraper using curl_cffi to fetch from SeekingAlpha API"""

    def __init__(
        self,
        output_dir: str = "news",
        verbose: bool = False,
        api_base_url: str = "https://seekingalpha.com/api/v3/news",
        category: str = "market-news::all",
        history_file: str = "scraped_history.json",
        kafka_enabled: bool = False,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "seeking-news",
        kafka_config_file: Optional[str] = None,
        history_ttl_days: Optional[int] = None
    ):
        # Call parent constructor
        super().__init__(
            output_dir=output_dir,
            verbose=verbose,
            api_base_url=api_base_url,
            category=category,
            history_file=history_file,
            kafka_enabled=kafka_enabled,
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            kafka_topic=kafka_topic,
            kafka_config_file=kafka_config_file,
            history_ttl_days=history_ttl_days
        )

    def get_articles_with_metadata(self, limit: int = 20, filter_scraped: bool = True) -> List[Dict]:
        """
        Get articles with metadata from SeekingAlpha API
        Automatically paginates through API pages until limit is reached

        Args:
            limit: Maximum number of articles to collect (across all pages)
            filter_scraped: If True, filter out already-scraped articles

        Returns:
            List of article dictionaries with metadata (not already scraped)
        """
        all_articles = []
        page_number = 1
        page_size = 50  # API max per page
        skipped_count = 0

        self.logger.info(f"Fetching articles from SeekingAlpha API (category: {self.category})")
        print(f"📄 Fetching articles from SeekingAlpha API (category: {self.category})...")

        while len(all_articles) < limit:
            try:
                # Fetch page from API
                articles = self._base_fetch_articles_from_api(page_number, page_size)

                if not articles:
                    self.logger.info(f"No more articles found at page {page_number}, stopping pagination")
                    print(f"📄 Page {page_number}: No articles found, stopping")
                    break

                # Filter out already scraped articles
                if filter_scraped:
                    before_filter = len(articles)
                    articles = [a for a in articles if not self._is_already_scraped(a['url'])]
                    filtered = before_filter - len(articles)
                    if filtered > 0:
                        skipped_count += filtered
                        self.logger.debug(f"Filtered {filtered} already-scraped articles from page {page_number}")

                # Add to collection
                all_articles.extend(articles)
                new_count = len(articles)

                self.logger.info(f"Page {page_number}: Found {new_count} new articles (total: {len(all_articles)}, skipped: {skipped_count})")
                print(f"📄 Page {page_number}: +{new_count} new articles (total: {len(all_articles)})")

                # Check if we've reached limit
                if len(all_articles) >= limit:
                    self.logger.info(f"Reached limit of {limit} articles")
                    print(f"✓ Reached limit of {limit} articles")
                    break

                # Move to next page
                page_number += 1

                # Small delay between pages
                time.sleep(1.0)

            except Exception as e:
                self.logger.error(f"Error fetching page {page_number}: {e}", exc_info=self.verbose)
                print(f"❌ Error on page {page_number}: {e}")
                break

        # Limit to requested number
        result = all_articles[:limit]

        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} already scraped article(s)")

        self.logger.info(f"Fetched {len(result)} new articles with metadata")
        print(f"✓ Found {len(result)} new articles total")

        return result

    def scrape_article(self, url: str, article_metadata: Optional[Dict] = None) -> Optional[Dict]:
        """
        Scrape a single SeekingAlpha article

        Args:
            url: Article URL
            article_metadata: Optional pre-fetched metadata from API

        Returns:
            Article data dictionary
        """
        self.logger.info(f"Scraping article: {url}")

        article_data = {
            'url': url,
            'scraped_at': datetime.now().isoformat(),
        }
        manual_fetching = False

        try:
            # If we have metadata from API, use it
            if article_metadata and article_metadata.get('content'):
                self.logger.debug("Using pre-fetched API data")

                article_data['title'] = article_metadata.get('title', 'No Title')
                article_data['published_date'] = article_metadata.get('date', 'Unknown')
                article_data['author'] = 'Seeking Alpha'  # API doesn't provide author in list

                # Extract content from HTML
                html_content = article_metadata.get('content', '')
                content_text = self._extract_text_from_html(html_content)

                if content_text == '':
                    self.logger.debug("Anti-Bot detected, trying to fetching article page directly")
                    manual_fetching = True
                else:   
                    article_data['content'] = content_text
                    article_data['excerpt'] = content_text[:60]
                    article_data['word_count'] = len(content_text.split())

                    self.logger.info(f"Title: {article_data['title']}")
                    self.logger.info(f"Word count: {article_data['word_count']}")
            else:
                manual_fetching = True
            
            if manual_fetching:
                # Fallback: Fetch article page directly (less efficient)
                self.logger.debug("No API metadata, fetching article page directly")

                # Extract article ID from URL
                article_id = url.split('/')[-1]
                api_url = f"https://seekingalpha.com/api/v3/news/{article_id}"

                headers = {
                    'accept': '*/*',
                    'accept-language': 'en-US,en;q=0.9',
                    'referer': url,
                    'origin': 'https://seekingalpha.com',
                    'sec-ch-ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"macOS"',
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
                }

                response = requests.get(api_url, headers=headers, impersonate="chrome119", timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    attributes = data.get('data', {}).get('attributes', {})

                    article_data['title'] = attributes.get('title', 'No Title')
                    article_data['published_date'] = attributes.get('publishOn', 'Unknown')
                    article_data['author'] = 'Seeking Alpha'
                    article_data['descripton'] = data.get('meta', {}).get('page', {}).get('description', '')

                    html_content = attributes.get('content', '')
                    content_text = self._extract_text_from_html(html_content)
                    article_data['content'] = content_text
                    article_data['excerpt'] = content_text[:60]
                    article_data['word_count'] = len(content_text.split())
                else:
                    self.logger.error(f"Failed to fetch article: HTTP {response.status_code}")
                    return None

            return article_data

        except Exception as e:
            self.logger.error(f"Error scraping article {url}: {e}", exc_info=self.verbose)
            print(f"  ❌ Error: {e}")
            return None

    def _extract_text_from_html(self, html_content: str) -> str:
        """
        Extract clean text from HTML content

        Args:
            html_content: HTML string from API

        Returns:
            Clean text content
        """
        if not html_content:
            return ""

        # Use BeautifulSoup to parse HTML and extract text
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text and clean up whitespace
        text = soup.get_text(separator='\n\n')

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = '\n\n'.join(lines)

        return clean_text

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Scrape Seeking Alpha articles using API with curl_cffi or stealth mode',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single run (scrape once and exit)
  %(prog)s --limit 10
  %(prog)s --category "market-news::consumer" --limit 20

  # Stealth mode (use browser emulation to bypass anti-bot detection)
  %(prog)s --stealth --limit 20
  %(prog)s --stealth --no-headless --verbose  # Debug mode with visible browser

  # Continuous mode (infinite loop with 5-minute pauses)
  %(prog)s --continuous --kafka --limit 50
  %(prog)s --continuous --continuous-interval 600 --limit 100  # 10-minute intervals

  # Production continuous scraping with Kafka
  %(prog)s --continuous --kafka --kafka-topic seeking-news \\
           --category "market-news::all" --limit 100 --verbose
        """
    )

    parser.add_argument('--output-dir', '-o', default='articles',
                       help='Output directory for articles (default: articles)')
    parser.add_argument('--limit', '-l', type=int, default=10000,
                       help='Number of articles to scrape from API (default: 10000)')
    parser.add_argument('--format', '-f', choices=['json', 'markdown', 'both'],
                       default='both', help='Output format (default: both)')
    parser.add_argument('--category', default=os.getenv('CATEGORY', 'market-news::all'),
                       help='Article category to scrape (default: market-news::all)')
    parser.add_argument('--delay', '-d', type=float, default=2.0,
                       help='Delay between requests in seconds (default: 2.0)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--history-file', default='scraped_history.json',
                       help='History file to track scraped articles (default: scraped_history.json)')
    parser.add_argument('--history-ttl-days', type=int, default=None,
                       help='Number of days to keep entries in history before auto-eviction (default: 30 days)')
    parser.add_argument('--force', action='store_true',
                       help='Force re-scraping of articles already in history')
    parser.add_argument('--save-local', action='store_true',
                       help='Save articles locally even when Kafka is enabled')
    parser.add_argument('--continuous', action='store_true',
                       help='Run in continuous mode (infinite loop with pauses between iterations)')
    parser.add_argument('--continuous-interval', type=int, default=300,
                       help='Seconds to wait between scraping iterations in continuous mode (default: 300 = 5 minutes)')

    # Stealth mode options
    parser.add_argument('--stealth', action='store_true',
                       help='Use stealth mode with browser emulation (slower but bypasses anti-bot detection)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Show browser window when using stealth mode (for debugging)')
    parser.add_argument('--login-email',
                       default=os.getenv('SEEKING_ALPHA_EMAIL'),
                       help='Seeking Alpha login email (or set SEEKING_ALPHA_EMAIL env var)')
    parser.add_argument('--login-password',
                       default=os.getenv('SEEKING_ALPHA_PASSWORD'),
                       help='Seeking Alpha login password (or set SEEKING_ALPHA_PASSWORD env var)')

    # Kafka options
    parser.add_argument('--kafka', '--enable-kafka', action='store_true', dest='kafka_enabled',
                        default=str(os.getenv('KAFKA_ENABLED', False)).lower() in ("1", "true", "yes", "on"),
                       help='Enable Kafka publishing (requires confluent-kafka)')
    parser.add_argument('--kafka-config',
                       default=os.getenv('KAFKA_CONFIG_FILE', 'kafka_config.properties'),
                       help='Kafka configuration file (default: kafka_config.properties)')
    parser.add_argument('--kafka-bootstrap-servers',
                       default=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
                       help='Kafka bootstrap servers (default: KAFKA_BOOTSTRAP_SERVERS env or localhost:9092)')
    parser.add_argument('--kafka-topic',
                       default=os.getenv('KAFKA_TOPIC', 'seeking-news'),
                       help='Kafka topic name (default: KAFKA_TOPIC env or seeking-news)')

    args = parser.parse_args()

    if args.verbose:
        print("🔍 Verbose logging enabled\n")

    if args.kafka_enabled:
        print(f"📡 Kafka enabled → {args.kafka_topic}\n")

    if args.stealth:
        print("🛡️  STEALTH MODE enabled - Using browser emulation\n")
        if args.login_email and args.login_password:
            print(f"🔐 Login enabled for: {args.login_email}\n")

    # Create scraper and run
    if args.stealth:
        # Use stealth mode scraper with browser emulation
        from seeking_scraper_stealth import SeekingScraperStealth

        scraper = SeekingScraperStealth(
            output_dir=args.output_dir,
            headless=not args.no_headless,
            verbose=args.verbose,
            category=args.category,
            history_file=args.history_file,
            kafka_enabled=args.kafka_enabled,
            kafka_bootstrap_servers=args.kafka_bootstrap_servers,
            kafka_topic=args.kafka_topic,
            kafka_config_file=args.kafka_config,
            login_email=args.login_email,
            login_password=args.login_password,
            history_ttl_days=args.history_ttl_days
        )
    else:
        # Use standard curl_cffi scraper (faster, but may be detected)
        scraper = SeekingScraper(
            output_dir=args.output_dir,
            verbose=args.verbose,
            category=args.category,
            history_file=args.history_file,
            kafka_enabled=args.kafka_enabled,
            kafka_bootstrap_servers=args.kafka_bootstrap_servers,
            kafka_topic=args.kafka_topic,
            kafka_config_file=args.kafka_config,
            history_ttl_days=args.history_ttl_days
        )

    scraper.scrape_and_save(
        limit=args.limit,
        format=args.format,
        delay=args.delay,
        force=args.force,
        save_local=args.save_local,
        continuous=args.continuous,
        continuous_interval=args.continuous_interval
    )


if __name__ == '__main__':
    main()
