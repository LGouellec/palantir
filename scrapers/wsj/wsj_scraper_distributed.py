#!/usr/bin/env python3
"""
Distributed WSJ Scraper for Kubernetes
Supports multiple distribution strategies for multi-pod deployments
"""

import os
from time import sleep
import hashlib
import json
from typing import List, Optional
from pathlib import Path

from wsj_scraper import WSJScraper


class DistributedWSJScraper(WSJScraper):
    """
    Distributed scraper that can work in a Kubernetes cluster

    Distribution strategies:
    1. MODULO: URLs distributed by hash % total_pods
    2. KAFKA: URLs pushed to Kafka topic, pods consume via consumer groups
    3. RANGE: Manual URL range assignment
    """

    def __init__(
        self,
        pod_index: int = 0,
        total_pods: int = 1,
        distribution_mode: str = 'modulo',
        kafka_urls_topic: Optional[str] = None,
        kafka_urls_consumer_group: Optional[str] = None,
        coordinator_pod: int = 0,
        **kwargs
    ):
        """
        Initialize distributed scraper

        Args:
            pod_index: Index of current pod (0-based)
            total_pods: Total number of pods in cluster
            distribution_mode: 'modulo', 'kafka', or 'range'
            kafka_urls_topic: Kafka topic for URL distribution (for kafka mode)
            kafka_urls_consumer_group: Kafka consumer group for workers
            **kwargs: Arguments passed to WSJScraper
        """
        super().__init__(**kwargs)

        self.pod_index = pod_index
        self.coordinator_pod = coordinator_pod
        self.total_pods = total_pods
        self.distribution_mode = distribution_mode.lower()
        self.kafka_urls_topic = kafka_urls_topic or 'wsj-urls'
        self.kafka_urls_consumer_group = kafka_urls_consumer_group or 'wsj-scraper-workers'

        # Kafka URL queue infrastructure
        self.kafka_url_producer = None
        self.kafka_url_consumer = None

        # Initialize Kafka URL queue if needed
        if self.distribution_mode == 'kafka':
            self._init_kafka_url_queue()

        self.logger.info(
            f"Distributed scraper initialized: "
            f"pod={pod_index}/{total_pods}, mode={distribution_mode}"
        )
        print(f"🚀 Pod {pod_index}/{total_pods} ready (mode: {distribution_mode})")

    def _init_kafka_url_queue(self):
        """Initialize Kafka producer and consumer for URL distribution"""
        try:
            from confluent_kafka import Producer, Consumer, KafkaError
            from kafka_config import load_kafka_config

            # Load Kafka configuration
            kafka_config = load_kafka_config()
            base_config = kafka_config.get_producer_config()

            # Initialize producer (for coordinator)
            if self.pod_index == self.coordinator_pod:
                producer_config = base_config.copy()
                self.kafka_url_producer = Producer(producer_config)
            else: # Initialize consumer (for workers)
                consumer_config = base_config.copy()
                consumer_config.update({
                    'group.id': self.kafka_urls_consumer_group,
                    'auto.offset.reset': 'earliest',
                    'enable.auto.commit': True,
                    'auto.commit.interval.ms': 5000,
                })
                self.kafka_url_consumer = Consumer(consumer_config)
                self.kafka_url_consumer.subscribe([self.kafka_urls_topic])
                self.logger.info(
                    f"Kafka URL queue initialized: topic={self.kafka_urls_topic}, "
                    f"group={self.kafka_urls_consumer_group}"
                )
            
            self.logger.info(f"✅ Kafka URL queue connected: {self.kafka_urls_topic}")

        except ImportError:
            raise ImportError(
                "Kafka mode requires 'confluent-kafka' package. "
                "Install with: pip install confluent-kafka"
            )
        except Exception as e:
            self.logger.error(f"Kafka URL queue initialization failed: {e}")
            raise

    def _url_belongs_to_pod(self, url: str) -> bool:
        """
        Check if URL should be processed by this pod (modulo mode)
        Uses consistent hashing to distribute URLs
        """
        url_hash = int(hashlib.md5(url.encode()).hexdigest(), 16)
        assigned_pod = url_hash % self.total_pods
        return assigned_pod == self.pod_index

    def _filter_urls_for_pod(self, urls: List[str]) -> List[str]:
        """Filter URLs assigned to this pod (modulo mode)"""
        if self.distribution_mode == 'modulo':
            filtered = [url for url in urls if self._url_belongs_to_pod(url)]
            self.logger.info(
                f"Pod {self.pod_index}: assigned {len(filtered)}/{len(urls)} URLs"
            )
            print(f"📊 Pod {self.pod_index}: assigned {len(filtered)}/{len(urls)} URLs")
            return filtered
        return urls

    def _push_urls_to_kafka(self, urls: List[str]) -> None:
        """Push URLs to Kafka topic (coordinator pod only)"""
        if not self.kafka_url_producer:
            raise RuntimeError("Kafka URL producer not initialized")

        def delivery_report(err, msg):
            if err:
                self.logger.error(f"URL delivery failed: {err}")
            else:
                self.logger.debug(
                    f"URL delivered: partition={msg.partition()}, offset={msg.offset()}"
                )

        # Push URLs to topic
        for url in urls:
            message = json.dumps({'url': url}).encode('utf-8')
            self.kafka_url_producer.produce(
                topic=self.kafka_urls_topic,
                key=url.encode('utf-8'),
                value=message,
                callback=delivery_report
            )
            self.kafka_url_producer.poll(0)

        # Flush to ensure all messages are sent
        self.kafka_url_producer.flush()

        self.logger.info(f"Pushed {len(urls)} URLs to Kafka topic: {self.kafka_urls_topic}")
        print(f"📤 Pushed {len(urls)} URLs to Kafka topic: {self.kafka_urls_topic}")

    def _get_url_from_kafka(self, timeout: float = 5.0) -> Optional[str]:
        """Get next URL from Kafka topic (using consumer group protocol)"""
        if not self.kafka_url_consumer:
            raise RuntimeError("Kafka URL consumer not initialized")

        try:
            msg = self.kafka_url_consumer.poll(timeout=timeout)

            if msg is None:
                return None

            if msg.error():
                from confluent_kafka import KafkaError
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    self.logger.debug(f"Reached end of partition {msg.partition()}")
                    return None
                else:
                    self.logger.error(f"Consumer error: {msg.error()}")
                    return None

            # Parse message
            data = json.loads(msg.value().decode('utf-8'))
            url = data.get('url')

            self.logger.debug(
                f"Consumed URL from partition {msg.partition()}, offset {msg.offset()}"
            )
            return url

        except Exception as e:
            self.logger.error(f"Error consuming URL from Kafka: {e}")
            return None

    def close(self) -> None:
        """Cleanup resources (Kafka producers/consumers, etc.)"""
        # Close parent resources (article Kafka producer)
        super().close()

        # Close URL queue resources
        if self.kafka_url_producer:
            try:
                remaining = self.kafka_url_producer.flush(timeout=10.0)
                if remaining > 0:
                    self.logger.warning(f"{remaining} URL messages were not delivered")
                self.logger.info("Kafka URL producer closed")
            except Exception as e:
                self.logger.error(f"Error closing Kafka URL producer: {e}")

        if self.kafka_url_consumer:
            try:
                self.kafka_url_consumer.close()
                self.logger.info("Kafka URL consumer closed")
            except Exception as e:
                self.logger.error(f"Error closing Kafka URL consumer: {e}")

    def get_article_links_distributed(
        self,
        url: str = None,
        limit: int = 20,
        enable_pagination: bool = True
    ) -> List[str]:
        """
        Get article links with distribution logic

        Args:
            url: URL to scrape links from
            limit: Max number of links to discover
            enable_pagination: Enable automatic pagination

        Returns:
            List of URLs assigned to this pod
        """

        if self.distribution_mode == 'kafka':
            # Kafka mode: coordinator discovers, others consume from topic
            if self.pod_index == self.coordinator_pod:
                # Coordinator: discover and push to Kafka
                print(f"🔍 Coordinator pod {self.pod_index}: discovering URLs...")
                all_urls = self.get_article_links(url, limit, enable_pagination=enable_pagination)
                self._push_urls_to_kafka(all_urls)
                return []  # Coordinator doesn't scrape
            else:
                # Worker: wait for URLs in topic
                print(f"⏳ Worker pod {self.pod_index}: waiting for URLs from Kafka...")
                return []  # URLs consumed in scrape_and_save_distributed

        elif self.distribution_mode == 'modulo':
            # Modulo mode: all pods discover, each filters its share
            print(f"🔍 Pod {self.pod_index}: discovering URLs...")
            all_urls = self.get_article_links(url, limit, enable_pagination=enable_pagination)
            return self._filter_urls_for_pod(all_urls)

        else:
            # Range mode: manual assignment
            return self.get_article_links(url, limit, enable_pagination=enable_pagination)

    def push_urls_to_kafka_queue(self, urls: List[str]) -> None:
        """Filter and push URLs to Kafka topic"""
        original_count = len(urls)
        all_urls = [url for url in urls if not self._is_already_scraped(url)]
        skipped_count = original_count - len(all_urls)

        if skipped_count > 0:
            print(f"⏭️  Skipping {skipped_count} already scraped article(s)")
            self.logger.info(f"Skipped {skipped_count} already scraped articles")

        # Push all URLs to Kafka
        print(f"📤 Coordinator: pushing {len(all_urls)} unique URLs to Kafka...")
        self._push_urls_to_kafka(all_urls)
        print(f"✅ Coordinator pod {self.pod_index}: URLs pushed.")

        for url in all_urls:
            self._mark_as_scraped(url)
        

    def scrape_and_save_distributed(
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
        Distributed scraping with automatic URL distribution

        Args:
            article_urls: Optional pre-defined URL list
            limit: Number of URLs to discover (if not provided)
            format: Output format
            delay: Delay between requests
            force: Force re-scraping
            save_local: Force local file save even if Kafka is enabled
            enable_pagination: Enable automatic pagination
            auto_discovery: Automatically discover articles from base_url (default: True)
        """

        self.logger.info(
            f"Starting distributed scrape: pod={self.pod_index}, mode={self.distribution_mode}"
        )

        # Kafka mode: special handling for coordinator + workers
        if self.distribution_mode == 'kafka':
            if self.pod_index == self.coordinator_pod:
                while True:
                    # Coordinator: discover URLs (if auto-discovery enabled)
                    if auto_discovery:

                        print(f"🔍 Coordinator pod {self.pod_index}: discovering URLs...")
                        discovered_urls = self.get_article_links(limit=limit, enable_pagination=enable_pagination)
                        self.push_urls_to_kafka_queue(discovered_urls)

                        if article_urls:
                            for url in article_urls:
                                all_section_urls = self.get_article_links(url, limit, enable_pagination=enable_pagination)
                                self.push_urls_to_kafka_queue(all_section_urls)
                    else:
                        # No auto-discovery, use only provided URLs
                        if not article_urls:
                            print("❌ Coordinator: No URLs provided and auto-discovery is disabled")
                            return
                        print(f"📝 Coordinator: Using {len(article_urls)} provided URLs (auto-discovery disabled)")
                        all_urls = article_urls
                        self.push_urls_to_kafka_queue(all_urls)

                    print(f"⏰ Sleeping 10 minutes before restarting the coordinator")
                    sleep(600)
                    continue
            # Workers continue to consume from queue below

        # For non-Redis modes: discover and combine URLs
        else:
            # Discover URLs if auto-discovery is enabled
            if auto_discovery:
                print(f"🔍 Pod {self.pod_index}: discovering URLs...")
                discovered_urls = self.get_article_links_distributed(
                    limit=limit,
                    enable_pagination=enable_pagination
                )

                # Combine discovered URLs with provided URLs (if any)
                if article_urls:
                    print(f"📝 Combining {len(discovered_urls)} discovered + {len(article_urls)} provided URLs")
                    self.logger.info(f"Combining discovered URLs with {len(article_urls)} provided URLs")
                    # Merge and deduplicate
                    all_urls = list(set(discovered_urls + article_urls))
                    # Apply distribution filter for modulo mode
                    if self.distribution_mode == 'modulo':
                        article_urls = self._filter_urls_for_pod(all_urls)
                    else:
                        article_urls = all_urls
                    print(f"📊 Total unique URLs for pod {self.pod_index}: {len(article_urls)}")
                else:
                    article_urls = discovered_urls
            else:
                # No auto-discovery, use only provided URLs
                if not article_urls:
                    print(f"❌ Pod {self.pod_index}: No URLs provided and auto-discovery is disabled")
                    return
                print(f"📝 Pod {self.pod_index}: Using {len(article_urls)} provided URLs (auto-discovery disabled)")
                # Apply distribution filter for modulo mode
                if self.distribution_mode == 'modulo':
                    article_urls = self._filter_urls_for_pod(article_urls)

            original_count = len(article_urls)
            article_urls = [url for url in article_urls if not self._is_already_scraped(url)]
            skipped_count = original_count - len(article_urls)

            if skipped_count > 0:
                print(f"⏭️  Skipping {skipped_count} already scraped article(s)")
                self.logger.info(f"Skipped {skipped_count} already scraped articles")

        # Kafka mode workers: consume from topic
        if self.distribution_mode == 'kafka':
            # Workers only (coordinator already done above)
            print(f"🔄 Worker pod {self.pod_index}: consuming from Kafka topic...")
            scraped_count = 0

            while True:
                url = self._get_url_from_kafka(timeout=5.0)

                if url is None:
                    # No more URLs in topic
                    print(f"📭 No URLs available. Pod {self.pod_index} will sleep 30 seconds and retry.")
                    if self.kafka_enabled:
                        self.kafka_producer.flush()
                    sleep(30)
                    continue

                # Check if already scraped
                if not force and self._is_already_scraped(url):
                    print(f"⏭️  [{self.pod_index}] Already scraped: {url}")
                    continue

                # Scrape the article
                print(f"\n[Pod {self.pod_index}] {url}")
                try:
                    article_data = self.scrape_article(url)

                    if article_data and article_data.get('content'):
                        word_count = article_data.get('word_count', 0)
                        if word_count > 50:
                            # Publish to Kafka if enabled (priority)
                            if self.kafka_enabled:
                                self._publish_to_kafka(article_data)

                            # Save locally only if Kafka disabled or save_local=True
                            self.save_article(article_data, format=format, force_save=save_local)

                            self._mark_as_scraped(url)
                            scraped_count += 1
                        else:
                            print(f"  ⚠️  Only {word_count} words (likely paywalled)")
                    else:
                        print(f"  ⚠️  No content found")

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    self.logger.error(f"Error scraping {url}: {e}")

                # Delay between requests
                if delay > 0:
                    import time
                    time.sleep(delay)

            # Cleanup Kafka producer
            if self.kafka_enabled:
                self.close()

            print(f"\n✅ Pod {self.pod_index} complete: scraped {scraped_count} articles")
            return

        # Modulo/Range mode: use filtered URL list
        if not article_urls:
            print(f"📭 No URLs assigned to pod {self.pod_index}")
            return

        # Use parent class method for actual scraping
        self.scrape_and_save(
            article_urls=article_urls,
            format=format,
            delay=delay,
            force=force,
            save_local=save_local,
            enable_pagination=enable_pagination
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Distributed WSJ Scraper for Kubernetes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Distribution Modes:
  modulo: Each pod gets URLs by hash % total_pods (all pods discover)
  kafka:  Coordinator discovers, workers consume from Kafka topic via consumer groups
  range:  Manual URL range assignment

Environment Variables (for K8s):
  POD_INDEX:             Index of current pod (0-based)
  TOTAL_PODS:            Total number of pods
  DISTRIBUTION:          Distribution mode (modulo/kafka/range)
  KAFKA_URLS_TOPIC:      Kafka topic for URL distribution
  KAFKA_URLS_GROUP:      Kafka consumer group for workers

Examples:
  # Modulo mode (3 pods)
  POD_INDEX=0 TOTAL_PODS=3 python %(prog)s --mode modulo --limit 30
  POD_INDEX=1 TOTAL_PODS=3 python %(prog)s --mode modulo --limit 30
  POD_INDEX=2 TOTAL_PODS=3 python %(prog)s --mode modulo --limit 30

  # Kafka mode (coordinator + 2 workers)
  POD_INDEX=0 TOTAL_PODS=3 python %(prog)s --mode kafka --limit 30  # Coordinator
  POD_INDEX=1 TOTAL_PODS=3 python %(prog)s --mode kafka             # Worker
  POD_INDEX=2 TOTAL_PODS=3 python %(prog)s --mode kafka             # Worker
        """
    )

    # Distributed options
    parser.add_argument('--pod-index', type=int,
                       default=int(os.getenv('POD_INDEX', 0)),
                       help='Pod index (default: POD_INDEX env or 0)')
    parser.add_argument('--total-pods', type=int,
                       default=int(os.getenv('TOTAL_PODS', 1)),
                       help='Total pods (default: TOTAL_PODS env or 1)')
    parser.add_argument('--mode', '--distribution-mode',
                       default=os.getenv('DISTRIBUTION', 'modulo'),
                       choices=['modulo', 'kafka', 'range'],
                       help='Distribution mode (default: modulo)')
    parser.add_argument('--kafka-urls-topic',
                       default=os.getenv('KAFKA_URLS_TOPIC', 'wsj-urls'),
                       help='Kafka topic for URL distribution (default: KAFKA_URLS_TOPIC env or wsj-urls)')
    parser.add_argument('--kafka-urls-consumer-group',
                       default=os.getenv('KAFKA_URLS_GROUP', 'wsj-scraper-workers'),
                       help='Kafka consumer group for workers (default: KAFKA_URLS_GROUP env or wsj-scraper-workers)')
    parser.add_argument('--coordinator-pod', type=int, default=0,
                       help='Coordinator pod index (kafka mode, default: 0)')

    # Standard scraper options
    parser.add_argument('--output-dir', '-o', default='articles',
                       help='Output directory')
    parser.add_argument('--limit', '-l', type=int, default=10000,
                       help='Number of articles to discover')
    parser.add_argument('--format', '-f', choices=['json', 'markdown', 'both'],
                       default='both', help='Output format')
    parser.add_argument('--urls-file', help='File with URLs')
    parser.add_argument('--delay', '-d', type=float, default=2.0,
                       help='Delay between requests')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging')
    parser.add_argument('--base-url',
                        default=os.getenv('BASE_URL', 'https://www.wsj.com/world'),
                       help='Base URL to scrape')
    parser.add_argument('--history-file',
                       default=f'scraped_history_pod_{os.getenv("POD_INDEX", 0)}.json',
                       help='History file (default: per-pod)')
    parser.add_argument('--force', action='store_true',
                       help='Force re-scraping')
    parser.add_argument('--save-local', action='store_true',
                       help='Save articles locally even when Kafka is enabled')
    parser.add_argument('--no-pagination', action='store_true',
                       help='Disable automatic pagination (if URL has ?page= parameter)')
    parser.add_argument('--no-auto-discovery', action='store_true',
                       help='Disable automatic article discovery (only use provided URLs)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Show browser')

    # Kafka options
    parser.add_argument('--kafka', '--enable-kafka', action='store_true',
                        default=os.getenv('KAFKA_ENABLED', False),
                        dest='kafka_enabled',
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

    if args.verbose:
        print("🔍 Verbose logging enabled\n")

    if args.kafka_enabled:
        print(f"📡 Kafka enabled → {args.kafka_topic}\n")

    # Create distributed scraper
    scraper = DistributedWSJScraper(
        pod_index=args.pod_index,
        total_pods=args.total_pods,
        distribution_mode=args.mode,
        kafka_urls_topic=args.kafka_urls_topic if args.mode == 'kafka' else None,
        kafka_urls_consumer_group=args.kafka_urls_consumer_group if args.mode == 'kafka' else None,
        output_dir=args.output_dir,
        headless=not args.no_headless,
        verbose=args.verbose,
        base_url=args.base_url,
        history_file=args.history_file,
        kafka_enabled=args.kafka_enabled,
        kafka_bootstrap_servers=args.kafka_bootstrap_servers,
        kafka_topic=args.kafka_topic,
        kafka_config_file=args.kafka_config,
        coordinator_pod=args.coordinator_pod
    )

    # Run distributed scraping
    scraper.scrape_and_save_distributed(
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
