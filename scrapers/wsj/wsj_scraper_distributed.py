#!/usr/bin/env python3
"""
Distributed WSJ Scraper for Kubernetes
Supports multiple distribution strategies for multi-pod deployments
"""

import os
from time import sleep
import hashlib
from typing import List, Optional
from pathlib import Path

from wsj_scraper import WSJScraper


class DistributedWSJScraper(WSJScraper):
    """
    Distributed scraper that can work in a Kubernetes cluster

    Distribution strategies:
    1. MODULO: URLs distributed by hash % total_pods
    2. REDIS_QUEUE: URLs pushed to Redis queue, pods consume
    3. RANGE: Manual URL range assignment
    """

    def __init__(
        self,
        pod_index: int = 0,
        total_pods: int = 1,
        distribution_mode: str = 'modulo',
        redis_url: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize distributed scraper

        Args:
            pod_index: Index of current pod (0-based)
            total_pods: Total number of pods in cluster
            distribution_mode: 'modulo', 'redis', or 'range'
            redis_url: Redis connection URL (for redis mode)
            **kwargs: Arguments passed to WSJScraper
        """
        super().__init__(**kwargs)

        self.pod_index = pod_index
        self.total_pods = total_pods
        self.distribution_mode = distribution_mode.lower()
        self.redis_url = redis_url
        self.redis_client = None

        # Initialize Redis if needed
        if self.distribution_mode == 'redis' and redis_url:
            self._init_redis()

        self.logger.info(
            f"Distributed scraper initialized: "
            f"pod={pod_index}/{total_pods}, mode={distribution_mode}"
        )
        print(f"🚀 Pod {pod_index}/{total_pods} ready (mode: {distribution_mode})")

    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            import redis
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            self.logger.info(f"Redis connected: {self.redis_url}")
            print(f"✅ Redis connected")
        except ImportError:
            raise ImportError(
                "Redis mode requires 'redis' package. "
                "Install with: pip install redis"
            )
        except Exception as e:
            self.logger.error(f"Redis connection failed: {e}")
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

    def _push_urls_to_redis(self, urls: List[str], queue_name: str = 'wsj:urls'):
        """Push URLs to Redis queue (coordinator pod only)"""
        if not self.redis_client:
            raise RuntimeError("Redis not initialized")

        # Push URLs to queue
        for url in urls:
            self.redis_client.rpush(queue_name, url)

        self.logger.info(f"Pushed {len(urls)} URLs to Redis queue: {queue_name}")
        print(f"📤 Pushed {len(urls)} URLs to Redis queue")

    def _get_url_from_redis(self, queue_name: str = 'wsj:urls', timeout: int = 5) -> Optional[str]:
        """Get next URL from Redis queue (blocking with timeout)"""
        if not self.redis_client:
            raise RuntimeError("Redis not initialized")

        result = self.redis_client.blpop(queue_name, timeout=timeout)
        if result:
            _, url = result
            return url
        return None

    def get_article_links_distributed(
        self,
        url: str = None,
        limit: int = 20,
        coordinator_pod: int = 0,
        enable_pagination: bool = True
    ) -> List[str]:
        """
        Get article links with distribution logic

        Args:
            url: URL to scrape links from
            limit: Max number of links to discover
            coordinator_pod: Which pod discovers links (others wait for Redis)
            enable_pagination: Enable automatic pagination

        Returns:
            List of URLs assigned to this pod
        """

        if self.distribution_mode == 'redis':
            # Redis mode: coordinator discovers, others consume from queue
            if self.pod_index == coordinator_pod:
                # Coordinator: discover and push to Redis
                print(f"🔍 Coordinator pod {self.pod_index}: discovering URLs...")
                all_urls = self.get_article_links(url, limit, enable_pagination=enable_pagination)
                self._push_urls_to_redis(all_urls)
                return []  # Coordinator doesn't scrape
            else:
                # Worker: wait for URLs in queue
                print(f"⏳ Worker pod {self.pod_index}: waiting for URLs from Redis...")
                return []  # URLs consumed in scrape_and_save_distributed

        elif self.distribution_mode == 'modulo':
            # Modulo mode: all pods discover, each filters its share
            print(f"🔍 Pod {self.pod_index}: discovering URLs...")
            all_urls = self.get_article_links(url, limit, enable_pagination=enable_pagination)
            return self._filter_urls_for_pod(all_urls)

        else:
            # Range mode: manual assignment
            return self.get_article_links(url, limit, enable_pagination=enable_pagination)

    def push_urls_to_redis(self, urls: List[str], redis_queue: str) -> None:
        original_count = len(urls)
        all_urls = [url for url in urls if not self._is_already_scraped(url)]
        skipped_count = original_count - len(all_urls)

        if skipped_count > 0:
            print(f"⏭️  Skipping {skipped_count} already scraped article(s)")
            self.logger.info(f"Skipped {skipped_count} already scraped articles")

        # Push all URLs to Redis
        print(f"📤 Coordinator: pushing {len(all_urls)} unique URLs to Redis...")
        self._push_urls_to_redis(all_urls, redis_queue)
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
        auto_discovery: bool = True,
        coordinator_pod: int = 0,
        redis_queue: str = 'wsj:urls'
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
            coordinator_pod: Pod index that coordinates (for redis mode)
            redis_queue: Redis queue name
        """

        self.logger.info(
            f"Starting distributed scrape: pod={self.pod_index}, mode={self.distribution_mode}"
        )

        # Redis mode: special handling for coordinator + workers
        if self.distribution_mode == 'redis':
            if self.pod_index == coordinator_pod:
                while True:
                    # Coordinator: discover URLs (if auto-discovery enabled)
                    if auto_discovery:

                        print(f"🔍 Coordinator pod {self.pod_index}: discovering URLs...")
                        discovered_urls = self.get_article_links(limit=limit, enable_pagination=enable_pagination)
                        self.push_urls_to_redis(discovered_urls, redis_queue)

                        if article_urls: 
                            for url in article_urls:
                                all_section_urls = self.get_article_links(url, limit, enable_pagination=enable_pagination)
                                self.push_urls_to_redis(all_section_urls, redis_queue)
                    else:
                        # No auto-discovery, use only provided URLs
                        if not article_urls:
                            print("❌ Coordinator: No URLs provided and auto-discovery is disabled")
                            return
                        print(f"📝 Coordinator: Using {len(article_urls)} provided URLs (auto-discovery disabled)")
                        all_urls = article_urls
                        self.push_urls_to_redis(all_urls, redis_queue)

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
                    coordinator_pod=coordinator_pod,
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

        # Redis mode workers: consume from queue
        if self.distribution_mode == 'redis':
            # Workers only (coordinator already exited above)
            print(f"🔄 Worker pod {self.pod_index}: consuming from Redis queue...")
            scraped_count = 0

            while True:
                url = self._get_url_from_redis(redis_queue, timeout=5)

                if url is None:
                    # No more URLs in queue
                    print(f"📭 No more URLs in queue. Pod {self.pod_index} will sleep 30 seconds and retry.")
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
  redis:  Coordinator discovers, workers consume from Redis queue
  range:  Manual URL range assignment

Environment Variables (for K8s):
  POD_INDEX:      Index of current pod (0-based)
  TOTAL_PODS:     Total number of pods
  REDIS_URL:      Redis connection URL
  DISTRIBUTION:   Distribution mode (modulo/redis/range)

Examples:
  # Modulo mode (3 pods)
  POD_INDEX=0 TOTAL_PODS=3 python %(prog)s --mode modulo --limit 30
  POD_INDEX=1 TOTAL_PODS=3 python %(prog)s --mode modulo --limit 30
  POD_INDEX=2 TOTAL_PODS=3 python %(prog)s --mode modulo --limit 30

  # Redis mode (coordinator + 2 workers)
  POD_INDEX=0 TOTAL_PODS=3 python %(prog)s --mode redis --limit 30  # Coordinator
  POD_INDEX=1 TOTAL_PODS=3 python %(prog)s --mode redis             # Worker
  POD_INDEX=2 TOTAL_PODS=3 python %(prog)s --mode redis             # Worker
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
                       choices=['modulo', 'redis', 'range'],
                       help='Distribution mode (default: modulo)')
    parser.add_argument('--redis-url',
                       default=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
                       help='Redis URL (default: REDIS_URL env or localhost)')
    parser.add_argument('--coordinator-pod', type=int, default=0,
                       help='Coordinator pod index (redis mode, default: 0)')
    parser.add_argument('--redis-queue', default='wsj:urls',
                       help='Redis queue name (default: wsj:urls)')

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
        redis_url=args.redis_url if args.mode == 'redis' else None,
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

    # Run distributed scraping
    scraper.scrape_and_save_distributed(
        article_urls=article_urls,
        limit=args.limit,
        format=args.format,
        delay=args.delay,
        force=args.force,
        save_local=args.save_local,
        enable_pagination=not args.no_pagination,
        auto_discovery=not args.no_auto_discovery,
        coordinator_pod=args.coordinator_pod,
        redis_queue=args.redis_queue
    )


if __name__ == '__main__':
    main()
