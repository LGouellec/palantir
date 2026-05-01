#!/usr/bin/env python3
"""
Wall Street Journal Article Scraper
Uses Scrapling - adaptive web scraping framework with built-in stealth mode
"""

import json
import re
import time
import logging
import random
from time import sleep
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from stt.audio_transcriber import AudioTranscriber
from mouvement.human import HumanMouseSimulator
from playwright.sync_api import Page
from scrapling.fetchers import StealthyFetcher
from kafka_config import load_kafka_config, KafkaConfig
from scrapling.engines.toolbelt.custom import Response


class WSJScraper:
    """WSJ Article Scraper using Scrapling's StealthyFetcher for anti-bot avoidance"""

    def __init__(
        self,
        output_dir: str = "articles",
        headless: bool = True,
        verbose: bool = False,
        base_url: str = "https://www.wsj.com",
        history_file: str = "scraped_history.json",
        kafka_enabled: bool = False,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "wsj-articles",
        kafka_config_file: Optional[str] = None
    ):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.verbose = verbose
        self.history_file = Path(history_file)

        # Load Kafka configuration from file
        self.kafka_config: Optional[KafkaConfig] = None
        if kafka_config_file or Path("kafka_config.properties").exists():
            try:
                self.kafka_config = load_kafka_config(kafka_config_file)
            except Exception as e:
                print(f"⚠️  Failed to load Kafka config: {e}")
                self.kafka_config = None

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

        # Configure logging
        if verbose:
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self.logger = logging.getLogger('WSJScraper')
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger = logging.getLogger('WSJScraper')
            self.logger.setLevel(logging.WARNING)

        self.audio_transcribe = AudioTranscriber(self.logger)
        
        # Initialize Kafka producer if enabled
        if kafka_enabled:
            self._init_kafka()

        # Enable Scrapling's adaptive mode for future-proofing
        StealthyFetcher.adaptive = True

    def _load_history(self) -> Dict[str, str]:
        """Load scraping history from JSON file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    print(f"📚 Loaded {len(history)} previously scraped articles from {self.history_file}")
                    return history
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

    def _mark_as_scraped(self, url: str) -> None:
        """Mark URL as scraped in history"""
        self.scraped_history[url] = datetime.now().isoformat()
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

            self.logger.debug(conf);
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
                'base_url': self.base_url,
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

    def to_markdown(self, article_data: Dict) -> str :
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

    def load_tracking_mouse(self, page:Page):
        self.simulator = HumanMouseSimulator(page, self.logger)
        self.simulator.enable_mouse_tracking()

    def by_pass_captcha(self, page:Page):

        status = page.evaluate("() => navigator.webdriver");
        self.logger.info(f"Webdriver used : {status}")

        page.wait_for_load_state("domcontentloaded")

        if page.locator('div.css-jzm21u-MastHeadContainer.e1mkna771').count() > 0:
            self.logger.info("Skip captcha bypass ...")
            return

        self.logger.info("Captcha is triggered. Try to disable it automatically ...")
        page.screenshot(path=f'./data/images/screenshot-init.png', full_page=True)

        framelocator = page.locator('iframe').content_frame

        if HumanMouseSimulator.wait_for_frame_selector(framelocator, '#ddv1-captcha-container'):
            page.screenshot(path=f'./data/images/screenshot-iframe.png', full_page=True)
            n = random.random()
            # 80% audio, 20% slider resolver
            if n < 0.80: # Try resolving audio captcha
                self.logger.info(f'Trying resolving audio captcha')

                def fill_func(index:int, value:int, typing_speed:float):
                    selector = f'#captcha__audio > div.audio-captcha-input-container > input:nth-child({index+1})'
                    locator = framelocator.locator(selector)
                    self.simulator.move_and_type(locator, str(value), delay=int(typing_speed * 1000))

                self.simulator.click(framelocator.locator('#captcha__audio__button'))

                audioSrc = framelocator.locator('#captcha__audio > audio').get_attribute('src');
                self.logger.info(f"Downloading audio captcha from : {audioSrc}")
                transcription_result = self.audio_transcribe.transcribe_audio(audioSrc)

                # click on play audio
                framelocator.locator('#captcha__audio > div.audio-captcha-play-container > button').click()
                self.logger.info(f'Transcription captcha detected : {transcription_result.full_text}')
                self.simulator.simulate_human_typing(transcription_result.sequences, fill_func)

                self.simulator.click(framelocator.locator('#captcha__audio > div.audio-captcha-submit-container > button'))
            else:
                self.logger.info(f'Trying resolving slider captcha')
                self.simulator.click(framelocator.locator('#captcha__puzzle__button'))

                start = framelocator.locator('#captcha__frame__bottom > div.sliderContainer > div.slider');
                end = framelocator.locator('#captcha__frame__bottom > div.sliderContainer > div.sliderTarget');

                self.simulator.drag_slider(start, end)

        page.screenshot(path=f'./data/images/screenshot-iframe-after.png', full_page=True)
        sleep(2)    
        page.screenshot(path=f'./data/images/screenshot-iframe-after2.png', full_page=True)

        page.wait_for_selector('div.css-jzm21u-MastHeadContainer.e1mkna771')
        page.screenshot(path=f'./data/images/screenshot-final.png', full_page=True)        
        self.simulator.reset_position()

    def get_article_links(self, url: str = None, limit: int = 20, enable_pagination: bool = True) -> List[str]:
        """
        Get article links from WSJ homepage or specific section

        Args:
            url: URL to scrape from
            limit: Maximum number of article links to collect (across all pages)
            enable_pagination: If True and URL has ?page= param, continue to next pages until 404

        Returns:
            List of unique article URLs
        """
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        url = url or self.base_url
        all_links = set()

        # Check if URL has pagination parameter
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        has_page_param = 'page' in query_params

        if has_page_param and enable_pagination:
            # Pagination mode: iterate through pages until 404
            current_page = int(query_params.get('page', ['1'])[0])
            self.logger.info(f"Pagination detected, starting from page {current_page}")
            print(f"📄 Pagination mode enabled, starting from page {current_page}")

            while len(all_links) < limit:
                # Build URL for current page
                query_params['page'] = [str(current_page)]
                new_query = urlencode(query_params, doseq=True)
                page_url = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    new_query,
                    parsed.fragment
                ))

                self.logger.info(f"Fetching page {current_page}: {page_url}")
                print(f"📄 Fetching page {current_page}...")

                try:
                    # Fetch page
                    page = self.fetch(page_url)

                    if page.status == 404:
                        self.logger.info(f"Page {current_page} does not exist, stopping pagination")
                        print(f"Page {current_page} does not exist, stopping pagination")
                        break
                    
                    # Extract links from this page
                    page_links = self._extract_article_links_from_page(page)

                    if not page_links:
                        # No articles found, might be end of pagination
                        self.logger.info(f"No articles found on page {current_page}, stopping pagination")
                        print(f"📄 Page {current_page}: No articles found, stopping")
                        break

                    # Add to collection
                    before_count = len(all_links)
                    all_links.update(page_links)
                    new_count = len(all_links) - before_count

                    self.logger.info(f"Page {current_page}: Found {new_count} new articles ({len(all_links)} total)")
                    print(f"📄 Page {current_page}: +{new_count} articles (total: {len(all_links)})")

                    # Check if we've reached limit
                    if len(all_links) >= limit:
                        self.logger.info(f"Reached limit of {limit} articles")
                        print(f"✓ Reached limit of {limit} articles")
                        break

                    # Move to next page
                    current_page += 1

                    # Small delay between pages
                    time.sleep(1.0)

                except Exception as e:
                    # Check if it's a 404 or similar error
                    error_msg = str(e).lower()
                    if '404' in error_msg or 'not found' in error_msg:
                        self.logger.info(f"Page {current_page} returned 404, end of pagination")
                        print(f"📄 Page {current_page}: 404 Not Found, stopping pagination")
                        break
                    else:
                        self.logger.error(f"Error fetching page {current_page}: {e}")
                        print(f"❌ Error on page {current_page}: {e}")
                        break

        else:
            # Single page mode (original behavior)
            self.logger.info(f"Fetching article links from {url}")

            try:
                page = self.fetch(url)

                all_links = self._extract_article_links_from_page(page)

            except Exception as e:
                self.logger.error(f"Error fetching article links: {e}", exc_info=self.verbose)
                print(f"❌ Error: {e}")

        # Limit to requested number
        result = list(all_links)[:limit]

        self.logger.info(f"Extracted {len(result)} unique article links")
        print(f"✓ Found {len(result)} article links total")

        return result

    def _extract_article_links_from_page(self, page) -> set:
        """Extract article links from a scraped page"""
        links = set()

        # Find all article links using CSS selector
        article_links = page.css('a[class*="css-1rznr30-CardLink"]')
        #self.logger.debug(page.body.decode("utf-8"))
        #self.logger.debug(page.request_headers)
        #self.logger.debug(page.meta)
        self.logger.debug(f"Found {len(article_links)} potential article links")

        for link_elem in article_links:
            href = link_elem.attrib.get('href', '')
            # Construct full URL
            if href.startswith('http'):
                full_url = href
            elif href.startswith('/'):
                full_url = 'https://www.wsj.com' + href
            else:
                continue

            # Clean URL (remove query params from article URLs)
            full_url = full_url.split('?')[0]
            links.add(full_url)
            self.logger.debug(f"Added article link: {full_url}")

        return links

    def scrape_article(self, url: str) -> Optional[Dict]:
        """Scrape a single WSJ article"""
        self.logger.info(f"Scraping article: {url}")

        article_data = {
            'url': url,
            'scraped_at': datetime.now().isoformat(),
        }

        try:
            # Fetch the article page with stealth mode
            self.logger.debug(f"Fetching article page: {url}")
            page = self.fetch(url)
            
            self.logger.debug("Page fetched, extracting article data...")

            # Extract title
            title = self._extract_title(page)
            article_data['title'] = title or 'No Title'
            self.logger.info(f"Title: {article_data['title']}")

            # Extract author
            author = self._extract_author(page)
            article_data['author'] = author or 'Unknown'
            self.logger.debug(f"Author: {article_data['author']}")

            # Extract publish date
            published_date = self._extract_date(page)
            article_data['published_date'] = published_date or 'Unknown'
            self.logger.debug(f"Published: {article_data['published_date']}")

            # Extract excerpt/summary
            excerpt = self._extract_excerpt(page)
            if excerpt:
                article_data['excerpt'] = excerpt
                self.logger.debug(f"Excerpt: {excerpt[:100]}...")

            # Extract article content
            paragraphs = self._extract_content(page)
            article_data['content'] = '\n\n'.join(paragraphs)
            article_data['word_count'] = len(' '.join(paragraphs).split())
            self.logger.info(f"Extracted {len(paragraphs)} paragraphs, {article_data['word_count']} words")

            return article_data

        except Exception as e:
            self.logger.error(f"Error scraping article {url}: {e}", exc_info=self.verbose)
            print(f"  ❌ Error: {e}")
            return None

    def _extract_title(self, page) -> Optional[str]:
        """Extract article title using multiple selectors"""
        selectors = [
            'h1.wsj-article-headline',
            'h1[class*="headline"]',
            'h1',
            'meta[property="og:title"]::attr(content)',
            'meta[name="title"]::attr(content)',
        ]

        for selector in selectors:
            self.logger.debug(f"Trying title selector: {selector}")
            try:
                if '::attr' in selector:
                    title = page.css(selector).get()
                else:
                    title = page.css(f'{selector}::text').get()

                if title and title.strip():
                    self.logger.debug(f"Title found with selector: {selector}")
                    return title.strip()
            except Exception as e:
                self.logger.debug(f"Selector {selector} failed: {e}")
                continue

        self.logger.warning("No title found with any selector")
        return None

    def _extract_author(self, page) -> Optional[str]:
        """Extract article author"""
        selectors = [
            'a[rel="author"]::text',
            '[class*="author"]::text',
            '[class*="byline"]::text',
            'meta[name="author"]::attr(content)',
            'meta[property="article:author"]::attr(content)',
        ]

        for selector in selectors:
            self.logger.debug(f"Trying author selector: {selector}")
            try:
                author = page.css(selector).get()
                if author and author.strip():
                    self.logger.debug(f"Author found with selector: {selector}")
                    return author.strip()
            except:
                continue

        return None

    def _extract_date(self, page) -> Optional[str]:
        """Extract publish date"""
        selectors = [
            'time::attr(datetime)',
            'time::text',
            'meta[property="article:published_time"]::attr(content)',
            'meta[name="article.published"]::attr(content)',
            'meta[name="publishedDate"]::attr(content)',
        ]

        for selector in selectors:
            self.logger.debug(f"Trying date selector: {selector}")
            try:
                date = page.css(selector).get()
                if date and date.strip():
                    self.logger.debug(f"Date found with selector: {selector}")
                    return date.strip()
            except:
                continue

        return None

    def _extract_excerpt(self, page) -> Optional[str]:
        """Extract article excerpt/summary"""
        selectors = [
            'meta[property="og:description"]::attr(content)',
            'meta[name="description"]::attr(content)',
            '[class*="dek"]::text',
            '[class*="excerpt"]::text',
            '[class*="summary"]::text',
        ]

        for selector in selectors:
            try:
                excerpt = page.css(selector).get()
                if excerpt and len(excerpt.strip()) > 20:
                    return excerpt.strip()
            except:
                continue

        return None

    def _extract_content(self, page) -> List[str]:
        """Extract article content paragraphs"""
        paragraphs = []

        # Try to find article body container
        article_selectors = [
            'article',
            '[class*="article-content"]',
            '[class*="article-body"]',
            '[class*="article__body"]',
            '[id*="article"]',
            '[id*="content"]',
        ]

        article_body = None
        for selector in article_selectors:
            self.logger.debug(f"Trying content container selector: {selector}")
            try:
                article_body = page.css(selector).get()
                if article_body:
                    self.logger.debug(f"Content container found: {selector}")
                    # Get all paragraphs within this container
                    p_elements = page.css(f'{selector} p::text').getall()
                    self.logger.debug(f"Found {len(p_elements)} <p> tags in container")

                    for text in p_elements:
                        text = text.strip()
                        if text and len(text) > 30:
                            paragraphs.append(text)
                            self.logger.debug(f"Added paragraph ({len(text)} chars)")

                    if paragraphs:
                        break
            except Exception as e:
                self.logger.debug(f"Selector {selector} failed: {e}")
                continue

        # Fallback: get all paragraphs from page
        if not paragraphs:
            self.logger.warning("No article container found, using fallback")
            try:
                all_p = page.css('p::text').getall()
                self.logger.debug(f"Fallback: found {len(all_p)} <p> tags total")

                for text in all_p:
                    text = text.strip()
                    if text and len(text) > 50:
                        paragraphs.append(text)
            except Exception as e:
                self.logger.error(f"Fallback extraction failed: {e}")

        self.logger.info(f"Extracted {len(paragraphs)} paragraphs total")
        return paragraphs

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

    def scrape_and_save(
        self,
        article_urls: List[str] = None,
        limit: int = 20,
        format: str = 'both',
        delay: float = 2.0,
        force: bool = False,
        save_local: bool = False,
        enable_pagination: bool = True,
        auto_discovery: bool = True
    ) -> None:
        """
        Main method to scrape and save articles

        Args:
            article_urls: Optional list of article URLs to scrape
            limit: Number of articles to discover (if article_urls not provided)
            format: Output format (json, markdown, both)
            delay: Delay between requests in seconds
            force: Force re-scraping of already scraped articles
            save_local: Force local file save even if Kafka is enabled
            enable_pagination: Enable automatic pagination (follow ?page= parameter)
            auto_discovery: Automatically discover articles from base_url (default: True)
        """

        self.logger.info("Starting scrape_and_save operation")

        # Notify about save behavior
        if self.kafka_enabled and not save_local:
            print(f"\n📡 Kafka mode: Articles will be published to Kafka only (no local files)")
            print(f"   Use --save-local to also save files locally")
        elif self.kafka_enabled and save_local:
            print(f"\n📡 Kafka mode + local save: Articles will be published to Kafka AND saved locally")

        # Auto-discovery of articles (if enabled)
        if auto_discovery:
            print(f"\n🔍 Discovering articles from {self.base_url}...")
            self.logger.info(f"Discovering articles from {self.base_url}")
            discovered_urls = self.get_article_links(limit=limit, enable_pagination=enable_pagination)

            # Combine discovered URLs with provided URLs (if any)
            if article_urls:
                for url in article_urls:
                    all_section_urls = self.get_article_links(url, limit, enable_pagination=enable_pagination)
                    print(f"📝 Combining {len(discovered_urls)} discovered + {len(all_section_urls)} provided URLs")
                    self.logger.info(f"Combining discovered URLs with {len(all_section_urls)} provided URLs")
                    discovered_urls = list(set(discovered_urls + all_section_urls))
                article_urls = discovered_urls
                print(f"📊 Total unique URLs: {len(article_urls)}")
            else:
                article_urls = discovered_urls
        else:
            # No auto-discovery, use only provided URLs
            if not article_urls:
                print("❌ No URLs provided and auto-discovery is disabled")
                print("   Provide URLs via --urls-file or enable auto-discovery")
                self.logger.warning("No URLs to scrape (auto-discovery disabled)")
                return

            print(f"\n📝 Using {len(article_urls)} provided URLs (auto-discovery disabled)")
            self.logger.info(f"Auto-discovery disabled, using {len(article_urls)} provided URLs")

        if not article_urls:
            print("❌ No articles found to scrape")
            self.logger.warning("No articles found")
            return

        # Filter out already scraped articles (unless force is True)
        if not force:
            original_count = len(article_urls)
            article_urls = [url for url in article_urls if not self._is_already_scraped(url)]
            skipped_count = original_count - len(article_urls)

            if skipped_count > 0:
                print(f"⏭️  Skipping {skipped_count} already scraped article(s)")
                self.logger.info(f"Skipped {skipped_count} already scraped articles")

            if not article_urls:
                print("✅ All articles have already been scraped!")
                print(f"   Use --force to re-scrape them")
                return

        print(f"\n📰 Scraping {len(article_urls)} {'new ' if not force else ''}article(s)...")
        print("=" * 60)
        self.logger.info(f"Scraping {len(article_urls)} articles with format={format}, delay={delay}, force={force}")

        success_count = 0
        paywall_count = 0
        error_count = 0

        for i, url in enumerate(article_urls, 1):
            print(f"\n[{i}/{len(article_urls)}] {url}")

            # Check if already scraped (info only, filtering done above)
            if not force and self._is_already_scraped(url):
                scraped_date = self.scraped_history.get(url)
                print(f"  ⏭️  Already scraped on {scraped_date[:10]} - skipping")
                continue

            try:
                article_data = self.scrape_article(url)

                if article_data and article_data.get('content'):
                    word_count = article_data.get('word_count', 0)
                    if word_count > 50:
                        # Publish to Kafka immediately after successful scrape
                        if self.kafka_enabled:
                            self._publish_to_kafka(article_data)

                        # Save to file (skipped if Kafka enabled unless save_local=True)
                        self.save_article(article_data, format=format, force_save=save_local)

                        # Mark as scraped after successful save/publish
                        self._mark_as_scraped(url)
                        success_count += 1
                    else:
                        print(f"  ⚠️  Only {word_count} words (likely paywalled)")
                        paywall_count += 1
                else:
                    print(f"  ⚠️  No content found (paywalled or blocked)")
                    paywall_count += 1

            except Exception as e:
                print(f"  ❌ Error: {e}")
                self.logger.error(f"Error processing {url}: {e}", exc_info=self.verbose)
                error_count += 1

            # Delay between requests
            if i < len(article_urls) and delay > 0:
                time.sleep(delay)

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
        print(f"   Total in history: {len(self.scraped_history)}")
        print(f"   History file: {self.history_file.absolute()}")

    def fetch(self, url: str = None) -> Response:
        retry = True
        proxy = os.getenv('HTTP_PROXY', None)
        self.logger.info(f"Using HTTP Proxy {proxy}")
        while retry == True:
            response = StealthyFetcher.fetch(
                        url,
                        timeout=30000,
                        proxy=proxy,
                        user_data_dir="./chrome",
                        headless=self.headless,
                        network_idle=True,
                        google_search=False,
                        load_dom=True,
                        allow_webgl=True,
                        hide_canvas=True,
                        disable_resources=False,
                        page_action=self.by_pass_captcha,
                        page_setup=self.load_tracking_mouse)
            if response.status == 401:
                # captcha enabled, need to retry
                print(f"Retry fetching {url} due captcha enabled")
            elif response.status == 200 or response.status == 404:
                return response
            else:
                print(f"Retry fetching {url} due to a bad status code (HTTP:{response.status})")
        

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Scrape Wall Street Journal articles using Scrapling',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --limit 10
  %(prog)s --urls-file articles.txt --format markdown
  %(prog)s --output-dir ./wsj_articles --delay 3.0
  %(prog)s --verbose --limit 5
  %(prog)s --no-headless --verbose  # Debug mode
        """
    )

    parser.add_argument('--output-dir', '-o', default='articles',
                       help='Output directory for articles (default: articles)')
    parser.add_argument('--limit', '-l', type=int, default=10000,
                       help='Number of articles to scrape (default: 10000)')
    parser.add_argument('--format', '-f', choices=['json', 'markdown', 'both'],
                       default='both', help='Output format (default: both)')
    parser.add_argument('--urls-file',
                       help='File containing article URLs (one per line)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Show browser window (for debugging)')
    parser.add_argument('--delay', '-d', type=float, default=2.0,
                       help='Delay between requests in seconds (default: 2.0)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--base-url', default=os.getenv('BASE_URL', 'https://www.wsj.com/world'),
                       help='Base URL to scrape from (default: https://www.wsj.com/world)')
    parser.add_argument('--history-file', default='scraped_history.json',
                       help='History file to track scraped articles (default: scraped_history.json)')
    parser.add_argument('--force', action='store_true',
                       help='Force re-scraping of articles already in history')
    parser.add_argument('--save-local', action='store_true',
                       help='Save articles locally even when Kafka is enabled')
    parser.add_argument('--no-pagination', action='store_true',
                       help='Disable automatic pagination (if URL has ?page= parameter)')
    parser.add_argument('--no-auto-discovery', action='store_true',
                       help='Disable automatic article discovery (only use provided URLs)')

    # Kafka options
    parser.add_argument('--kafka', '--enable-kafka', action='store_true', dest='kafka_enabled',
                        default=os.getenv('KAFKA_ENABLED', False),
                       help='Enable Kafka publishing (requires confluent-kafka)')
    parser.add_argument('--kafka-config',
                       default=os.getenv('KAFKA_CONFIG_FILE', 'kafka_config.properties'),
                       help='Kafka configuration file (default: kafka_config.properties)')
    parser.add_argument('--kafka-bootstrap-servers',
                       default=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
                       help='Kafka bootstrap servers (default: KAFKA_BOOTSTRAP_SERVERS env or localhost:9092)')
    parser.add_argument('--kafka-topic',
                       default=os.getenv('KAFKA_TOPIC', 'wsj-articles'),
                       help='Kafka topic name (default: KAFKA_TOPIC env or wsj-articles)')

    args = parser.parse_args()

    # Load URLs from file if provided
    article_urls = None
    if args.urls_file:
        urls_file = Path(args.urls_file)
        if urls_file.exists():
            with open(urls_file, 'r') as f:
                article_urls = [line.strip() for line in f
                              if line.strip() and not line.startswith('#')]
            print(f"Loaded {len(article_urls)} URLs from {args.urls_file}")
        else:
            print(f"Error: File not found: {args.urls_file}")
            return

    if args.verbose:
        print("🔍 Verbose logging enabled\n")

    if args.kafka_enabled:
        print(f"📡 Kafka enabled → {args.kafka_topic}\n")

    # Create scraper and run
    scraper = WSJScraper(
        output_dir=args.output_dir,
        headless=not args.no_headless,
        verbose=args.verbose,
        base_url=args.base_url,
        history_file=args.history_file,
        kafka_enabled=args.kafka_enabled,
        kafka_bootstrap_servers=args.kafka_bootstrap_servers,
        kafka_topic=args.kafka_topic,
        kafka_config_file=args.kafka_config
    )

    scraper.scrape_and_save(
        article_urls=article_urls,
        limit=args.limit,
        format=args.format,
        delay=args.delay,
        force=args.force,
        save_local=args.save_local,
        enable_pagination=not args.no_pagination,
        auto_discovery=not args.no_auto_discovery
    )


if __name__ == '__main__':
    main()
