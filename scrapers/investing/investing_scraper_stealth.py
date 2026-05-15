#!/usr/bin/env python3
"""
Investing.com News Scraper - Stealth Mode
Uses Scrapling's StealthyFetcher for enhanced anti-bot avoidance
Adapted from SeekingScraperStealth
"""

import time
import os
import sys
import shutil
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Union

# Add parent directory to path for common module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scrapling.fetchers import StealthyFetcher
from investing_scraper_base import InvestingScraperBase


class InvestingScraperStealth(InvestingScraperBase):
    """
    Investing.com Scraper using Scrapling's StealthyFetcher for anti-bot avoidance

    Features:
    - Automatic browser context cleanup after consecutive 403 errors
    - Graceful Playwright process shutdown (SIGTERM → SIGKILL fallback)
    - Persistent browser session management via user_data_dir
    - Multi-category support
    - Human-like mouse interactions for captcha solving
    """

    def __init__(
        self,
        output_dir: str = "news",
        headless: bool = True,
        verbose: bool = False,
        category: str = "latest-news",
        analysis: bool = False,
        history_file: str = "history/scraped_history.json",
        kafka_enabled: bool = False,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "investing-articles",
        kafka_config_file: Optional[str] = None,
        history_ttl_days: Optional[int] = None
    ):
        # Set category-specific attributes before calling parent
        self.category = category
        self.analysis = analysis

        # Build URL based on analysis flag
        url_type = "analysis" if analysis else "news"
        self.category_url = f"https://www.investing.com/{url_type}/{category}"
        self.solve_cloudflare = False

        # Call parent constructor
        super().__init__(
            output_dir=output_dir,
            verbose=verbose,
            history_file=history_file,
            kafka_enabled=kafka_enabled,
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            kafka_topic=kafka_topic,
            kafka_config_file=kafka_config_file,
            history_ttl_days=history_ttl_days
        )

        # Stealth-specific attributes
        self.headless = headless
        self.user_data_dir = "./chrome_investing"  # Persistent browser context

        # Track consecutive 403 errors for browser context reset
        self.consecutive_403_count = 0
        self.max_consecutive_403 = 3

        # Enable Scrapling's adaptive mode for future-proofing
        StealthyFetcher.adaptive = True

    def _cleanup_browser_context(self) -> None:
        """
        Clean up persistent browser context and cookies after consecutive 403 errors.

        Uses process-level cleanup (SIGTERM → SIGKILL) to terminate Playwright instances
        managed internally by StealthyFetcher, then deletes the browser context directory
        to force a fresh start.
        """
        self.logger.warning(f"🧹 Cleaning up browser context after {self.consecutive_403_count} consecutive 403 errors")
        print(f"⚠️  Detected {self.consecutive_403_count} consecutive 403 errors - resetting browser context...")

        try:
            # StealthyFetcher manages Playwright instances internally, so we use
            # process-level cleanup since we don't have direct access to browser objects
            try:
                # Check if pgrep/pkill are available (may not be in Docker containers)
                pgrep_available = subprocess.run(
                    ['which', 'pgrep'],
                    capture_output=True,
                    timeout=2
                ).returncode == 0

                if pgrep_available:
                    self.logger.debug("Attempting graceful Playwright shutdown with SIGTERM...")
                    result = subprocess.run(
                        ['pgrep', '-f', 'playwright'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        # Playwright processes found
                        pids = result.stdout.strip().split('\n')
                        self.logger.debug(f"Found {len(pids)} Playwright process(es), sending SIGTERM...")

                        # Send SIGTERM for graceful shutdown
                        subprocess.run(['pkill', '-15', '-f', 'playwright'], stderr=subprocess.DEVNULL, timeout=5)

                        # Wait up to 5 seconds for graceful shutdown
                        for _ in range(10):
                            time.sleep(0.5)
                            check = subprocess.run(
                                ['pgrep', '-f', 'playwright'],
                                capture_output=True,
                                timeout=5
                            )
                            if check.returncode != 0:
                                self.logger.debug("Playwright processes shut down gracefully")
                                break
                        else:
                            # If still running after 5 seconds, force kill
                            self.logger.warning("Graceful shutdown timeout, forcing SIGKILL...")
                            subprocess.run(['pkill', '-9', '-f', 'playwright'], stderr=subprocess.DEVNULL, timeout=5)
                            time.sleep(1)
                            self.logger.debug("Forced Playwright process termination")
                    else:
                        self.logger.debug("No Playwright processes found")
                else:
                    self.logger.debug("pgrep/pkill not available (common in Docker), relying on context cleanup")
                    # In Docker without process tools, just wait a bit for processes to settle
                    time.sleep(2)

            except subprocess.TimeoutExpired:
                self.logger.warning("Process check timed out")
            except FileNotFoundError:
                self.logger.debug("Process management tools not found (Docker environment), skipping process cleanup")
                time.sleep(2)
            except Exception as e:
                self.logger.debug(f"Process cleanup note: {e}")
                time.sleep(2)

            # Additional wait for full cleanup
            time.sleep(1)

            # Delete persistent browser context directory
            user_data_path = Path(self.user_data_dir)
            if user_data_path.exists():
                self.logger.info(f"Deleting browser context directory: {user_data_path}")
                shutil.rmtree(user_data_path, ignore_errors=True)
                self.logger.info("✓ Browser context directory deleted")

            # Reset consecutive error counter
            self.consecutive_403_count = 0

            # Give the system time to fully clean up
            time.sleep(3)

            self.logger.info("✅ Browser context cleanup complete - starting fresh")
            print("✅ Browser context reset complete - will retry with fresh session")

        except Exception as e:
            self.logger.error(f"Error during browser context cleanup: {e}", exc_info=True)
            print(f"❌ Warning: Cleanup had issues but continuing: {e}")
            # Reset counter anyway to avoid infinite loop
            self.consecutive_403_count = 0

    def fetch(self, url: str):
        """Fetch page with StealthyFetcher and 403 handling with retry after cleanup"""
        while True:
            try:
                self.logger.debug(f"Fetching: {url}")
                proxy = os.getenv('HTTP_PROXY', None)
                if proxy:
                    self.logger.info(f"Using HTTP Proxy: {proxy}")

                response = StealthyFetcher.fetch(
                    url,
                    headless=self.headless,
                    user_data_dir=self.user_data_dir,
                    network_idle=False,
                    load_dom=False,
                    disable_resources=True,
                    solve_cloudflare=self.solve_cloudflare,
                    allow_webgl=True,
                    hide_canvas=False,
                    google_search=False,
                    proxy=proxy,
                    retries=5,
                    timeout=20000
                )

                if response.status == 403 or response.status == 401:
                    self.solve_cloudflare = True
                    self.consecutive_403_count += 1
                    self.logger.warning(f"403 Forbidden ({self.consecutive_403_count}/{self.max_consecutive_403})")
                    if self.consecutive_403_count >= self.max_consecutive_403:
                        self.logger.info(f"Max consecutive 403s reached, cleaning up browser context and retrying...")
                        self._cleanup_browser_context()
                        # Continue loop to retry
                        continue
                    else:
                        # Haven't hit max yet, raise to let caller handle
                        raise Exception(f"403 Forbidden ({self.consecutive_403_count}/{self.max_consecutive_403})")
                else:
                    self.solve_cloudflare = False

                # Reset counter on success
                self.consecutive_403_count = 0
                return response

            except Exception as e:
                # Only re-raise if it's not a 403 that we're retrying
                if "403 Forbidden" not in str(e) or self.consecutive_403_count < self.max_consecutive_403:
                    self.logger.error(f"Fetch failed for {url}: {e}")
                    raise

    def _extract_article_id(self, url: str) -> Optional[str]:
        """Extract article ID from URL (trailing number after last dash)"""
        match = re.search(r'-(\d+)$', url)
        return match.group(1) if match else None

    def _is_article_url(self, url: str) -> bool:
        """Validate if URL is an article (pattern: /news/{category}/{slug}-{id})"""
        pattern = r'^https?://(?:www\.)?investing\.com/news/[^/]+/.+-\d+/?(?:\?.*)?$'
        return bool(re.match(pattern, url))

    def _extract_article_links(self, page) -> List[str]:
        """Extract article links from listing page"""
        links = set()

        # Investing.com uses data-test="article-title-link" attribute - use this first!
        selector_strategies = [
            # Strategy 1: data-test attribute (most reliable and fast)
            'a[data-test="article-title-link"]',

            # Strategy 2: Specific article card selectors (fallback)
            'a[href*="/news/"][class*="hover:underline"]',
            'article a[href*="/news/"]',

            # Strategy 3: Generic news link pattern
            'a[href*="/news/"][href*="-"]',
        ]

        for selector in selector_strategies:
            try:
                potential_links = page.css(f'{selector}::attr(href)').getall()

                for href in potential_links:
                    # Construct full URL
                    if href.startswith('http'):
                        full_url = href
                    elif href.startswith('/'):
                        full_url = 'https://www.investing.com' + href
                    else:
                        continue

                    # Clean URL (remove query params and fragments)
                    full_url = full_url.split('?')[0].split('#')[0]

                    # Validate article URL pattern
                    if self._is_article_url(full_url):
                        links.add(full_url)

                if links:
                    self.logger.info(f"Found {len(links)} article links with selector: {selector}")
                    break

            except Exception as e:
                self.logger.debug(f"Selector '{selector}' failed: {e}")
                continue

        return list(links)

    def get_articles_with_metadata(self, limit: int = 20, filter_scraped: bool = True) -> List[Dict]:
        """
        Discover articles from listing pages with pagination

        Args:
            limit: Maximum number of articles to collect
            filter_scraped: If True, filter out already-scraped articles

        Returns:
            List of article metadata dicts (id, url)

        Note:
            Pagination stops at page 15 to avoid excessive scraping,
            even if the limit hasn't been reached.
        """
        articles = []
        page_num = 1
        max_pages = 15  # Maximum pages to scrape to avoid excessive pagination

        print(f"\n🔍 Discovering articles from {self.category}...")

        while len(articles) < limit and page_num <= max_pages:
            # Build page URL (investing.com uses path-based pagination)
            if page_num == 1:
                page_url = self.category_url
            else:
                page_url = f"{self.category_url}/{page_num}"

            self.logger.info(f"Fetching page {page_num}: {page_url}")
            print(f"  📄 Page {page_num}: {page_url}")

            try:
                page = self.fetch(page_url)

                # Extract article links using discovered selectors
                article_urls = self._extract_article_links(page)

                if not article_urls:
                    self.logger.info(f"No articles found on page {page_num}, stopping")
                    print(f"  ⚠️  No articles found on page {page_num}")
                    break

                for url in article_urls:
                    if filter_scraped and self._is_already_scraped(url):
                        self.logger.debug(f"Skipping already scraped: {url}")
                        continue

                    articles.append({
                        'id': self._extract_article_id(url),
                        'url': url
                    })

                    if len(articles) >= limit:
                        break

                print(f"    ✓ Found {len(article_urls)} articles ({len(articles)} new)")

                page_num += 1

                # Check if we've hit the page limit
                if page_num > max_pages:
                    self.logger.info(f"Reached maximum page limit ({max_pages}), stopping pagination")
                    print(f"  ⚠️  Reached maximum page limit ({max_pages})")
                    break

                time.sleep(1.0)  # Delay between pages

            except Exception as e:
                self.logger.error(f"Error fetching page {page_num}: {e}")
                print(f"  ❌ Error on page {page_num}: {e}")
                break

        print(f"\n📊 Discovered {len(articles)} articles total")
        return articles[:limit]

    def _try_selectors(self, page, selectors: List[str]) -> Optional[str]:
        """Try multiple selectors and return first match"""
        for selector in selectors:
            try:
                # Check if selector targets attribute
                if '::attr(' in selector:
                    result = page.css(selector).get()
                else:
                    result = page.css(selector + '::text').get()

                if result and result.strip():
                    return result.strip()
            except Exception as e:
                self.logger.debug(f"Selector '{selector}' failed: {e}")
                continue
        return None

    def _extract_title(self, page) -> Optional[str]:
        """Extract article title"""
        selectors = [
            'h1.article-title',
            'h1.articleHeader',
            'h1[class*="article"]',
            'h1',
            'meta[property="og:title"]::attr(content)',
            'meta[name="title"]::attr(content)',
        ]
        return self._try_selectors(page, selectors)

    def _extract_author(self, page) -> Union[str, List[str]]:
        """Extract article author(s) - may be multiple"""
        # Updated selectors based on actual investing.com HTML structure
        selectors = [
            # Investing.com specific: <span class="flex flex-row text-xs"><a href="/members/contributors/..."><span class="text-link">Author Name</span></a></span>
            'span.flex.flex-row.text-xs a span.text-link',
            'a[href*="/members/contributors/"] span.text-link',
            'a[href*="/members/contributors/"] span',
            # Generic fallbacks
            'span.author-name',
            'a[rel="author"]',
            'span[class*="author"]',
            '[class*="byline"]',
            'meta[name="author"]::attr(content)',
        ]

        authors = []
        for selector in selectors:
            try:
                if '::attr(' in selector:
                    results = page.css(selector).getall()
                else:
                    results = page.css(selector + '::text').getall()

                if results:
                    for result in results:
                        cleaned = result.strip()
                        # Remove "By " prefix
                        cleaned = re.sub(r'^By\s+', '', cleaned, flags=re.IGNORECASE)
                        if cleaned and len(cleaned) > 1:  # Filter out single characters
                            authors.append(cleaned)
                    break
            except Exception as e:
                self.logger.debug(f"Author selector '{selector}' failed: {e}")
                continue

        # Return list if multiple, single string if one, 'Unknown' if none
        if len(authors) > 1:
            return authors
        elif len(authors) == 1:
            return authors[0]
        return 'Unknown'

    def _extract_published_date(self, page) -> Optional[str]:
        """Extract published date"""
        # Investing.com specific: <div class="flex flex-row items-center"><span>Published 05/14/2026, 08:22 PM</span>
        # We need to extract all spans and filter by content since :has-text() is not standard CSS

        # Try to find spans within flex containers
        try:
            all_spans = page.css('div.flex.flex-row.items-center span::text').getall()
            for span_text in all_spans:
                if span_text and 'Published' in span_text:
                    # Clean up "Published " prefix
                    date_str = re.sub(r'^Published\s+', '', span_text, flags=re.IGNORECASE).strip()
                    if date_str:
                        self.logger.debug(f"Found published date: {date_str}")
                        return date_str
        except Exception as e:
            self.logger.debug(f"Flex container search failed: {e}")

        # Generic fallback selectors
        selectors = [
            'time[datetime]::attr(datetime)',
            'meta[property="article:published_time"]::attr(content)',
            'span[class*="publish-date"]::attr(data-time)',
        ]

        date_str = self._try_selectors(page, selectors)

        # Clean up "Published " prefix if present
        if date_str:
            date_str = re.sub(r'^Published\s+', '', date_str, flags=re.IGNORECASE).strip()

        return date_str

    def _extract_modified_date(self, page) -> Optional[str]:
        """Extract modified/updated date"""
        selectors = [
            'time.modified::attr(datetime)',
            'time[class*="update"]::attr(datetime)',
            'meta[property="article:modified_time"]::attr(content)',
            'span[class*="update-date"]::attr(data-time)',
            '[class*="modified"]',
            '[class*="updated"]',
        ]
        return self._try_selectors(page, selectors)

    def _extract_excerpt(self, page) -> Optional[str]:
        """Extract article excerpt/summary"""
        selectors = [
            'meta[property="og:description"]::attr(content)',
            'meta[name="description"]::attr(content)',
            'div.article-excerpt',
            'div[class*="summary"]',
            'p.lead',
        ]

        excerpt = self._try_selectors(page, selectors)

        # Clean up excerpt
        if excerpt:
            # Remove common prefixes
            excerpt = re.sub(r'^(--\s+|[\)\]-]\s*)', '', excerpt).strip()
            # Require minimum length
            if len(excerpt) > 20:
                return excerpt

        return None

    def _extract_content(self, page) -> List[str]:
        """Extract article content paragraphs"""
        paragraphs = []

        # Try specific article containers first
        article_selectors = [
            'article.article-content',
            'div.article-body',
            'div.articlePage',
            '[class*="article-content"]',
            '[id*="article"]',
            'article',
        ]

        # Try to find article body container
        for selector in article_selectors:
            try:
                p_elements = page.css(f'{selector} p::text').getall()

                for text in p_elements:
                    text = text.strip()
                    if text and len(text) > 30:  # Filter short/empty paragraphs
                        paragraphs.append(text)

                if paragraphs:
                    self.logger.debug(f"Found content with selector: {selector}")
                    break
            except Exception as e:
                self.logger.debug(f"Content selector '{selector}' failed: {e}")
                continue

        # Fallback: get all paragraphs
        if not paragraphs:
            try:
                all_p = page.css('p::text').getall()
                for text in all_p:
                    text = text.strip()
                    if text and len(text) > 50:
                        paragraphs.append(text)
                self.logger.debug("Used fallback paragraph extraction")
            except Exception as e:
                self.logger.error(f"Fallback extraction failed: {e}")

        return paragraphs

    def _extract_tags(self, page) -> List[str]:
        """Extract article tags/keywords"""
        tags = []
        selectors = [
            'a[rel="tag"]',
            '[class*="tag"]',
            'meta[property="article:tag"]::attr(content)',
            'meta[name="keywords"]::attr(content)',
        ]

        for selector in selectors:
            try:
                if '::attr(' in selector:
                    results = page.css(selector).getall()
                else:
                    results = page.css(selector + '::text').getall()

                if results:
                    for result in results:
                        # If comma-separated string, split it
                        if ',' in result:
                            tags.extend([t.strip() for t in result.split(',') if t.strip()])
                        else:
                            cleaned = result.strip()
                            if cleaned:
                                tags.append(cleaned)
            except Exception as e:
                self.logger.debug(f"Tag selector '{selector}' failed: {e}")
                continue

        return list(set(tags))  # Deduplicate

    def _extract_images(self, page) -> List[str]:
        """Extract article images"""
        images = []

        selectors = [
            'article img::attr(src)',
            '[class*="article-body"] img::attr(src)',
            'figure img::attr(src)',
            'div[class*="article-content"] img::attr(src)',
            'img::attr(src)',  # Fallback: all images
        ]

        for selector in selectors:
            try:
                imgs = page.css(selector).getall()
                for img in imgs:
                    # Make absolute URL
                    if img.startswith('//'):
                        img = 'https:' + img
                    elif img.startswith('/'):
                        img = 'https://www.investing.com' + img
                    elif not img.startswith('http'):
                        continue

                    # Filter out icons, ads, tracking pixels (small images)
                    if any(keyword in img.lower() for keyword in ['icon', 'logo', 'pixel', 'avatar', '1x1']):
                        continue

                    images.append(img)

                if images:
                    break
            except Exception as e:
                self.logger.debug(f"Image selector '{selector}' failed: {e}")
                continue

        return list(set(images))  # Deduplicate

    def _extract_comment_count(self, page) -> int:
        """Extract number of comments (optional)"""
        selectors = [
            '[class*="comment-count"]',
            '[class*="comments"]',
            '[id*="comment-count"]',
        ]

        for selector in selectors:
            try:
                text = page.css(selector + '::text').get()
                if text:
                    # Extract number from text
                    match = re.search(r'(\d+)', text)
                    if match:
                        return int(match.group(1))
            except:
                continue

        return 0

    def scrape_article(self, url: str, article_metadata: Optional[Dict] = None) -> Optional[Dict]:
        """
        Scrape individual article

        Args:
            url: Article URL
            article_metadata: Optional pre-fetched metadata

        Returns:
            Article data dictionary or None if should be skipped
        """
        try:
            self.logger.info(f"Scraping article: {url}")
            page = self.fetch(url)

            # Extract all fields
            title = self._extract_title(page)
            author = self._extract_author(page)
            published_date = self._extract_published_date(page)
            modified_date = self._extract_modified_date(page)
            content_paragraphs = self._extract_content(page)
            excerpt = self._extract_excerpt(page)
            tags = self._extract_tags(page)
            images = self._extract_images(page)
            comment_count = self._extract_comment_count(page)

            # Build content string
            content = '\n\n'.join(content_paragraphs)
            content = self.remove_copyright(content)

            # Extract article ID
            article_id = article_metadata.get('id') if article_metadata else self._extract_article_id(url)

            article_data = {
                'id': article_id,
                'url': url,
                'scraped_at': datetime.now().isoformat(),
                'title': title,
                'author': author,
                'published_date': published_date,
                'modified_date': modified_date,
                'excerpt': excerpt,
                'content': content,
                'word_count': len(content.split()) if content else 0,
                'category': self.category,
                'tags': tags,
                'images': images,
                'comment_count': comment_count
            }

            self.logger.debug(f"Extracted article: {title} ({article_data['word_count']} words)")
            return article_data

        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}", exc_info=self.verbose)
            return None


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Scrape Investing.com articles using Scrapling',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Investing.com specific
    parser.add_argument('--category', default='latest-news',
        choices=[
                # News category
                'latest-news', 'stock-market-news', 'earnings', 'analyst-ratings', 'transcripts',
                 'forex-news', 'commodities-news', 'cryptocurrency-news', 'economy', 'economic-indicators', 'headlines',
                # Analysis category
                 'market-overview', 'forex', 'stock-markets', 'commodities', 'bonds', 'cryptocurrency', 'etfs'],
        help='Category to scrape (default: latest-news)')
    parser.add_argument('--analysis', action='store_true',
        help='Scrape from /analysis/ instead of /news/ (default: False)')

    # Standard options
    parser.add_argument('--output-dir', '-o', default='news',
        help='Output directory (default: news)')
    parser.add_argument('--limit', '-l', type=int, default=20,
        help='Number of articles to scrape (default: 20)')
    parser.add_argument('--format', '-f', choices=['json', 'markdown', 'both'],
        default='both', help='Output format (default: both)')
    parser.add_argument('--no-headless', action='store_true',
        help='Show browser (default: headless)')
    parser.add_argument('--delay', '-d', type=float, default=2.0,
        help='Delay between articles in seconds (default: 2.0)')
    parser.add_argument('--verbose', '-v', action='store_true',
        help='Verbose logging')
    parser.add_argument('--history-file', default='history/scraped_history.json',
        help='History file path (default: history/scraped_history.json)')
    parser.add_argument('--force', action='store_true',
        help='Force re-scraping of already scraped articles')
    parser.add_argument('--save-local', action='store_true',
        help='Save locally even when Kafka is enabled')
    parser.add_argument('--continuous', action='store_true',
        help='Run continuously (infinite loop)')
    parser.add_argument('--continuous-interval', type=int, default=300,
        help='Seconds between iterations in continuous mode (default: 300)')

    # Kafka options
    parser.add_argument('--kafka', action='store_true', dest='kafka_enabled',
        help='Enable Kafka publishing')
    parser.add_argument('--kafka-config', default='kafka_config.properties',
        help='Kafka configuration file (default: kafka_config.properties)')
    parser.add_argument('--kafka-bootstrap-servers', default='localhost:9092',
        help='Kafka bootstrap servers (default: localhost:9092)')
    parser.add_argument('--kafka-topic', default='investing-articles',
        help='Kafka topic name (default: investing-articles)')

    args = parser.parse_args()

    if args.verbose:
        print("🔍 Verbose logging enabled\n")

    if args.kafka_enabled:
        print(f"📡 Kafka enabled → {args.kafka_topic}\n")

    # Create scraper
    scraper = InvestingScraperStealth(
        output_dir=args.output_dir,
        headless=not args.no_headless,
        verbose=args.verbose,
        category=args.category,
        analysis=args.analysis,
        history_file=args.history_file,
        kafka_enabled=args.kafka_enabled,
        kafka_bootstrap_servers=args.kafka_bootstrap_servers,
        kafka_topic=args.kafka_topic,
        kafka_config_file=args.kafka_config if Path(args.kafka_config).exists() else None
    )

    # Run scraper
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
