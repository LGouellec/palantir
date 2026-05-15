#!/usr/bin/env python3
"""
Base class for Investing.com News Scrapers
Contains common functionality for history management, Kafka publishing, etc.
Adapted from SeekingScraperBase
"""

import json
import re
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


class InvestingScraperBase(ABC):
    """Abstract base class for Investing.com scrapers"""

    # History TTL: entries older than this will be automatically evicted
    HISTORY_TTL_DAYS = 30

    def __init__(
        self,
        output_dir: str = "news",
        verbose: bool = False,
        history_file: str = "history/scraped_history.json",
        kafka_enabled: bool = False,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "investing-articles",
        kafka_config_file: Optional[str] = None,
        history_ttl_days: Optional[int] = None
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self.history_file = Path(history_file)

        # Configure history TTL (default: 30 days)
        if history_ttl_days is not None:
            self.HISTORY_TTL_DAYS = history_ttl_days

        # Load Kafka configuration from file if available
        self.kafka_config = None
        kafka_config_path = Path(kafka_config_file) if kafka_config_file else Path("kafka_config.properties")
        if kafka_config_path.exists():
            try:
                # Import here to avoid circular dependency
                import sys
                import os
                sys.path.insert(0, os.path.dirname(__file__))
                from kafka_config import load_kafka_config
                self.kafka_config = load_kafka_config(str(kafka_config_path))
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
            except (ValueError, TypeError):
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
            # Create parent directory if it doesn't exist
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            return {}

    def _save_history(self) -> None:
        """Save scraping history to JSON file"""
        try:
            # Ensure parent directory exists
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
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
                'id': article_data.get('id'),
                'url': article_data.get('url'),
                'title': article_data.get('title'),
                'author': article_data.get('author'),
                'published_date': article_data.get('published_date'),
                'scraped_at': article_data.get('scraped_at'),
                'word_count': article_data.get('word_count', 0),
                'excerpt': article_data.get('excerpt', ''),
                'content': article_data.get('content'),
                'category': article_data.get('category'),
                'images': article_data.get('images', []),
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

    def to_markdown(self, article_data: Dict) -> str:
        """Convert article data to markdown format"""
        markdown_content = f"""# {article_data['title']}

**Author:** {article_data.get('author', 'Unknown')}
**Published:** {article_data.get('published_date', 'Unknown')}
**URL:** {article_data['url']}
**Scraped:** {article_data['scraped_at']}
**Word Count:** {article_data.get('word_count', 0)}
**Category:** {article_data.get('category', 'Unknown')}
"""

        if article_data.get('tags'):
            markdown_content += f"**Tags:** {', '.join(article_data['tags'])}\n"

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
        Get articles with metadata from Investing.com
        Must be implemented by subclass

        Args:
            limit: Maximum number of articles to collect
            filter_scraped: If True, filter out already-scraped articles

        Returns:
            List of article dictionaries with metadata
        """
        pass

    @abstractmethod
    def scrape_article(self, url: str, article_metadata: Optional[Dict] = None) -> Optional[Dict]:
        """
        Scrape a single Investing.com article
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
                    print(f"   Next run at: {(datetime.now() + timedelta(seconds=continuous_interval)).strftime('%Y-%m-%d %H:%M:%S')}")
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

        print(f"\n🔍 Fetching articles from Investing.com...")
        self.logger.info(f"Starting scraping")
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

                print(f"\n[{total_processed}/{min(limit, len(articles))}] {url}")

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
