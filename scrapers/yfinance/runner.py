import argparse
import asyncio
import logging
import os
import signal
from analytics_engine import AsyncAnalyticsEngine
from models import StockAnalytics
from kafka_callback import KafkaStockPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_event = asyncio.Event()


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='YFinance Analytics Engine - Live Monitoring',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of stocks to fetch per iteration'
    )

    parser.add_argument(
        '--interval-ms',
        type=int,
        default=30000,
        help='Monitoring interval in milliseconds'
    )

    parser.add_argument(
        '--include-news',
        action='store_true',
        default=True,
        help='Include news fetching'
    )

    parser.add_argument(
        '--no-news',
        action='store_false',
        dest='include_news',
        help='Disable news fetching'
    )

    parser.add_argument(
        '--analyze-sentiment',
        action='store_true',
        default=True,
        help='Enable sentiment analysis'
    )

    parser.add_argument(
        '--no-sentiment',
        action='store_false',
        dest='analyze_sentiment',
        help='Disable sentiment analysis'
    )

    parser.add_argument(
        '--news-days',
        type=int,
        default=20,
        help='Number of days of news to fetch'
    )

    parser.add_argument(
        '--sentiment-analyzer',
        type=str,
        choices=['keyword', 'llm'],
        default='keyword',
        help='Sentiment analyzer to use (keyword or llm)'
    )

    parser.add_argument(
        '--kafka',
        action='store_true',
        default=False,
        help='Enable Kafka publishing for stock updates'
    )

    return parser.parse_args()


def handle_shutdown(signum, _frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"\n\nReceived signal {signum}. Shutting down gracefully...")
    shutdown_event.set()


async def monitoring_with_kafka(
    batch_size: int = 50,
    interval_ms: int = 30000,
    include_news: bool = True,
    analyze_sentiment: bool = True,
    news_days: int = 20,
    sentiment_analyzer: str = 'keyword',
    enable_kafka: bool = False,
):
    """Monitor all NASDAQ stocks in batches with optional Kafka integration."""
    logger.info("\n" + "=" * 70)
    logger.info("YFinance Analytics Engine - Live Monitoring")
    logger.info("=" * 70)

    engine = AsyncAnalyticsEngine(max_concurrent=20, max_requests_per_second=2, enable_proxy_rotation=True)

    # Kafka integration
    kafka_publisher = None
    if enable_kafka:
        logger.info("Initializing Kafka publisher...")
        kafka_bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        kafka_topic = os.environ.get("KAFKA_TOPIC", "yahoo_news")

        kafka_publisher = KafkaStockPublisher(
            bootstrap_servers=kafka_bootstrap,
            topic=kafka_topic,
        )
        kafka_publisher.initialize()
        engine.add_update_callback(kafka_publisher.publish_stock_update)
        logger.info(f"✅ Kafka publisher enabled (topic: {kafka_topic})")

    # Price alert callback
    def price_alert(ticker: str, data: StockAnalytics) -> None:
        """Alert on significant price changes."""
        # Check if we have quote data
        if not data.quote:
            return

        price = data.quote.current_price
        pe_ratio = data.quote.pe_ratio
        timestamp = data.fetch_time.isoformat()[:19]

        # Simple alert logic
        if price and price > 0:
            pe_str = f"PE: {pe_ratio:.2f}" if pe_ratio else "PE: N/A"
            logger.info(f"📈 {ticker}: ${price:.2f} | {pe_str} | {timestamp}")

            # Alert on high PE ratios
            if pe_ratio and pe_ratio > 50:
                logger.info(f"   ⚠️  High PE ratio: {pe_ratio:.2f}")

    # News alert callback
    def news_alert(ticker: str, data: StockAnalytics) -> None:
        """Alert on new articles."""
        news = data.news
        if news:
            logger.info(f"📰 {ticker}: {len(news)} recent articles")
            for article in news[:1]:  # Show first article
                logger.info(f"   - {article.title[:60]}...")

    engine.add_update_callback(price_alert)
    engine.add_update_callback(news_alert)

    try:
        # NASDAQ + NYSE tickers
        logger.info("\nFetching NASDAQ + NYSE ticker list...")
        tickers = await engine.fetch_nasdaq_tickers(
            include_nasdaq=True,
            include_nyse=True,
            include_etf=False
        )
        logger.info(f"Found {len(tickers)} tickers")

        # Load preferred tickers
        preferred_tickers = []
        tickers_file = os.environ.get("PREFERED_TICKERS_PATH", "top_stocks.txt")

        if os.path.exists(tickers_file):
            with open(tickers_file, 'r') as f:
                preferred_tickers = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                # Remove duplicates
                preferred_tickers = list(dict.fromkeys(preferred_tickers))
            logger.info(f"Loaded {len(preferred_tickers)} preferred tickers from {tickers_file}")
        else:
            logger.warning(f"Preferred tickers file not found: {tickers_file}")

        # Start monitoring in batch mode
        logger.info("\nStarting monitoring...")
        logger.info(f"  Total tickers: {len(tickers)}")
        logger.info(f"  Preferred tickers: {len(preferred_tickers)}")
        logger.info(f"  Batch size: {batch_size} stocks per iteration")
        logger.info(f"  Interval: {interval_ms / 1000:.1f} seconds")
        logger.info(f"  News: {'Enabled' if include_news else 'Disabled'} ({news_days} days)" if include_news else "  News: Disabled")
        logger.info(f"  Sentiment: {'Enabled (' + sentiment_analyzer + '-based)' if analyze_sentiment else 'Disabled'}")
        logger.info(f"  Kafka: {'Enabled' if enable_kafka else 'Disabled'}")
        logger.info("")

        engine.start_monitoring(
            tickers=tickers,
            batch_size=batch_size,
            interval_ms=interval_ms,
            include_news=include_news,
            analyze_sentiment=analyze_sentiment,
            news_days=news_days,
            sentiment_analyzer=sentiment_analyzer,
            preferred_tickers=preferred_tickers,
        )

        logger.info("✅ Monitoring started successfully!")
        logger.info("Press Ctrl+C to stop...\n")

        # Wait until shutdown signal is received
        await shutdown_event.wait()

    except Exception as e:
        logger.error(f"Error during monitoring: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Stop monitoring gracefully
        logger.info("\nStopping monitoring...")
        await engine.stop_monitoring()

        # Flush Kafka if enabled
        if kafka_publisher:
            logger.info("Flushing Kafka messages...")
            kafka_publisher.close()

        logger.info("✅ Monitoring stopped")


async def main():
    """Run YFinance live monitoring."""
    # Parse command-line arguments
    args = parse_arguments()

    logger.info("\n")
    logger.info("╔══════════════════════════════════════════════════════════════════════╗")
    logger.info("║          YFinance AnalyticsEngine - Live Monitoring                  ║")
    logger.info("╚══════════════════════════════════════════════════════════════════════╝")
    logger.info("\n")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    await monitoring_with_kafka(
        batch_size=args.batch_size,
        interval_ms=args.interval_ms,
        include_news=args.include_news,
        analyze_sentiment=args.analyze_sentiment,
        news_days=args.news_days,
        sentiment_analyzer=args.sentiment_analyzer,
        enable_kafka=args.kafka,
    )

    logger.info("\n✅ Engine shutdown complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\nExiting...")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
