"""
Kafka callback for publishing stock updates to Kafka topics.

Uses Confluent Kafka producer for production-ready publishing.
Supports configuration from properties file via KAFKA_CONFIG_PATH env variable.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from models import StockAnalytics

logger = logging.getLogger(__name__)


def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize an object for JSON serialization.

    Handles pandas DataFrames, Series, Timestamps, and other non-serializable types.

    Args:
        obj: Object to sanitize

    Returns:
        JSON-serializable version of the object
    """
    # Handle None
    if obj is None:
        return None

    # Handle pandas DataFrame
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            # Convert to dict with string keys
            return {
                str(k): _sanitize_for_json(v)
                for k, v in obj.to_dict(orient='index').items()
            }

        # Handle pandas Series
        if isinstance(obj, pd.Series):
            return {
                str(k): _sanitize_for_json(v)
                for k, v in obj.to_dict().items()
            }

        # Handle pandas Timestamp
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
    except ImportError:
        pass

    # Handle datetime
    if isinstance(obj, datetime):
        return obj.isoformat()

    # Handle dict
    if isinstance(obj, dict):
        return {
            str(k): _sanitize_for_json(v)
            for k, v in obj.items()
        }

    # Handle list/tuple
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]

    # Handle primitives (str, int, float, bool)
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # For anything else, convert to string
    return str(obj)


class KafkaStockPublisher:
    """
    Callback handler that publishes stock updates to Kafka using Confluent producer.

    Features:
    - Confluent Kafka producer with async wrapper
    - Config file support via KAFKA_CONFIG_PATH environment variable
    - JSON serialization
    - Error handling and delivery callbacks
    - Message statistics tracking
    - Partition key based on ticker symbol
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "stock-updates",
        compression_type: Optional[str] = "none",
        acks: str = "all",
        retries: int = 100,
        **additional_config,
    ):
        """
        Initialize Kafka publisher.

        Args:
            bootstrap_servers: Kafka broker addresses (comma-separated)
            topic: Kafka topic name for stock updates
            compression_type: Compression (gzip, snappy, lz4, zstd, none)
            acks: Acknowledgment mode (all, 1, 0)
            retries: Number of retries on failure
            **additional_config: Additional Confluent Kafka producer config

        Environment Variables:
            KAFKA_CONFIG_PATH: Path to Kafka properties file (overrides all other config)
        """
        self.topic = topic
        self.producer = None

        # Base configuration
        self.producer_config = {
            "bootstrap.servers": bootstrap_servers,
            "compression.type": compression_type or "none",
            "acks": acks,
            "retries": retries,
            "client.id": "yfinance-analytics-engine",
        }

        # Merge additional config
        self.producer_config.update(additional_config)

        # Check for config file
        config_path = os.environ.get("KAFKA_CONFIG_PATH")
        if config_path:
            self._load_config_from_file(config_path)

        self._message_count = 0
        self._error_count = 0
        self._delivery_success_count = 0
        self._delivery_error_count = 0
        self._initialized = False

    def _load_config_from_file(self, config_path: str) -> None:
        """
        Load Kafka configuration from properties file.

        Args:
            config_path: Path to Kafka properties file

        Format:
            bootstrap.servers=localhost:9092
            compression.type=gzip
            acks=all
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Kafka config file not found: {config_path}")

        logger.info(f"📄 Loading Kafka config from: {config_path}")

        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse key=value
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Override config with file values
                    self.producer_config[key] = value

        logger.info(f"✅ Loaded {len(self.producer_config)} config properties")

    def initialize(self):
        """
        Initialize the Confluent Kafka producer.

        Call this before starting monitoring.
        """
        try:
            from confluent_kafka import Producer

            self.producer = Producer(self.producer_config)
            self._initialized = True

            logger.info(f"✅ Kafka producer initialized (Confluent)")
            logger.info(f"   Topic: {self.topic}")
            logger.info(f"   Brokers: {self.producer_config.get('bootstrap.servers')}")
            logger.info(f"   Compression: {self.producer_config.get('compression.type')}")

        except ImportError:
            raise ImportError(
                "confluent-kafka is required for Kafka integration. "
                "Install with: pip install confluent-kafka"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Kafka producer: {e}")

    def close(self):
        """
        Close the Kafka producer gracefully.

        Flushes all pending messages before closing.
        Call this when stopping monitoring.
        """
        if self.producer and self._initialized:
            logger.info("🔄 Flushing pending messages...")

            # Flush synchronously
            self.producer.flush(timeout=30)

            self._initialized = False

            logger.info(f"🛑 Kafka producer stopped")
            logger.info(f"   Messages sent: {self._message_count}")
            logger.info(f"   Delivery success: {self._delivery_success_count}")
            logger.info(f"   Delivery errors: {self._delivery_error_count}")
            logger.info(f"   Publish errors: {self._error_count}")

    def _delivery_callback(self, err, msg):
        """
        Delivery report callback called once for each message.

        Args:
            err: Error if delivery failed, None if successful
            msg: Message that was delivered
        """
        if err:
            self._delivery_error_count += 1
            logger.info(f"❌ Delivery failed for {msg.key().decode()}: {err}")
        else:
            self._delivery_success_count += 1
            # Log periodically
            if self._delivery_success_count % 100 == 0:
                logger.info(f"✅ Delivered {self._delivery_success_count} messages")

    def publish_stock_update(self, ticker: str, analytics: StockAnalytics) -> None:
        """
        Callback function called when stock data is updated.

        This is the function registered with engine.add_update_callback()

        Args:
            ticker: Stock ticker symbol
            analytics: StockAnalytics dataclass instance
        """
        if not self._initialized:
            logger.warning("⚠️  Kafka producer not initialized. Call initialize() first.")
            return

        try:
            # Transform analytics data to Kafka message
            message = self._transform_to_message(ticker, analytics)

            # Sanitize message for JSON serialization
            # This handles pandas Timestamps, DataFrames, Series, etc.
            sanitized_message = _sanitize_for_json(message)

            # Serialize to JSON
            message_json = json.dumps(sanitized_message).encode("utf-8")
            key = ticker.encode("utf-8")

            # Produce message (synchronous)
            self.producer.produce(
                topic=self.topic,
                value=message_json,
                key=key,
                callback=self._delivery_callback,
            )

            # Poll to trigger delivery callbacks (non-blocking)
            self.producer.poll(0)

            self._message_count += 1

        except BufferError:
            # Queue is full, wait and retry
            self._error_count += 1
            logger.warning(f"⚠️  Queue full, waiting for {ticker}...")
            self.producer.poll(1)
            # Could retry here if needed

        except Exception as e:
            self._error_count += 1
            logger.error(f"❌ Failed to publish {ticker} to Kafka: {e}")

    def _transform_to_message(self, ticker: str, analytics: StockAnalytics) -> Dict[str, Any]:
        """
        Transform analytics data to Kafka message format.

        Override this method to customize message structure.

        Args:
            ticker: Stock ticker symbol
            analytics: StockAnalytics dataclass instance

        Returns:
            Message dictionary to send to Kafka
        """
        # Build message
        message = {
            # Metadata
            "ticker": ticker,
            "timestamp": analytics.fetch_time.isoformat(),
            "source": "yfinance-analytics-engine",
            "has_errors": len(analytics.errors) > 0,
            "errors": analytics.errors,
        }

        # Price data
        if analytics.quote:
            message["price"] = {
                "current": analytics.quote.current_price or 0,
                "previous_close": analytics.quote.previous_close or 0,
                "open": analytics.quote.open_price or 0,
                "day_high": analytics.quote.day_high or 0,
                "day_low": analytics.quote.day_low or 0,
                "market_cap": analytics.quote.market_cap or 0,
                "volume": analytics.quote.volume or 0,
                "avg_volume_10d": analytics.quote.avg_volume_10d or 0,
            }

            # Valuation ratios
            message["ratios"] = {
                "pe": analytics.quote.pe_ratio or 0,
                "eps": analytics.quote.eps or 0,
                "dividend_yield": analytics.quote.dividend_yield or 0,
                "beta": analytics.quote.beta or 0,
            }

            # 52-week range
            message["week_52"] = {
                "high": analytics.quote.week_52_high or 0,
                "low": analytics.quote.week_52_low or 0,
            }

            # Company info
            message["company"] = {
                "name": analytics.quote.name or "",
                "ticker": analytics.quote.ticker,
                "shares_outstanding": analytics.quote.shares_outstanding or 0,
            }

        # Fundamentals
        if analytics.fundamentals:
            message["fundamentals"] = {
                "revenue": analytics.fundamentals.revenue or 0,
                "revenue_growth": analytics.fundamentals.revenue_growth or 0,
                "net_income": analytics.fundamentals.net_income or 0,
                "profit_margin": analytics.fundamentals.profit_margin or 0,
                "operating_margin": analytics.fundamentals.operating_margin or 0,
                "total_debt": analytics.fundamentals.total_debt or 0,
                "total_equity": analytics.fundamentals.total_equity or 0,
                "debt_to_equity": analytics.fundamentals.debt_to_equity or 0,
                "current_ratio": analytics.fundamentals.current_ratio or 0,
                "book_value_per_share": analytics.fundamentals.book_value_per_share or 0,
                "pb_ratio": analytics.fundamentals.pb_ratio or 0,
                "roe": analytics.fundamentals.roe or 0,
                "roa": analytics.fundamentals.roa or 0,
            }

        # Valuation metrics
        if analytics.valuation:
            message["valuation"] = {
                "cagr_1y": analytics.valuation.cagr_1y or 0,
                "cagr_3y": analytics.valuation.cagr_3y or 0,
                "cagr_5y": analytics.valuation.cagr_5y or 0,
                "volatility_1y": analytics.valuation.volatility_1y or 0,
                "volatility_3y": analytics.valuation.volatility_3y or 0,
                "max_drawdown_1y": analytics.valuation.max_drawdown_1y or 0,
                "sharpe_ratio_1y": analytics.valuation.sharpe_ratio_1y or 0,
                "sortino_ratio_1y": analytics.valuation.sortino_ratio_1y or 0,
            }

        # Add news if available
        if analytics.news:
            message["news_count"] = len(analytics.news)
            message["news"] = [
                {
                    "title": article.title,
                    "source": article.source,
                    "publish_date": article.publish_date.isoformat() if article.publish_date else None,
                    "url": article.url,
                    "content": article.content,
                    "sentiment": article.sentiment.value if article.sentiment else None,
                    "confidence": article.confidence,
                    "impact_score": article.impact_score,
                    "category": article.category.value if article.category else None,
                    "keywords": article.keywords,
                }
                for article in analytics.news
            ]

        # Add sentiment analysis if available
        if analytics.sentiment_analysis:
            message["sentiment"] = {
                "sentiment_score": analytics.sentiment_analysis.sentiment_score,
                "confidence": analytics.sentiment_analysis.confidence,
                "analyzer_type": analytics.sentiment_analysis.analyzer_type,
                "news_count_7d": analytics.sentiment_analysis.news_count_7d,
                "news_count_30d": analytics.sentiment_analysis.news_count_30d,
                "positive_count": analytics.sentiment_analysis.positive_count,
                "neutral_count": analytics.sentiment_analysis.neutral_count,
                "negative_count": analytics.sentiment_analysis.negative_count,
                "key_themes": analytics.sentiment_analysis.key_themes,
                "risks": analytics.sentiment_analysis.risks,
                "catalysts": analytics.sentiment_analysis.catalysts,
                "sentiment_trend": analytics.sentiment_analysis.sentiment_trend,
                "growth_sentiment": analytics.sentiment_analysis.growth_sentiment,
                "dividend_safety": analytics.sentiment_analysis.dividend_safety,
            }

        # Add guidance if available
        if analytics.guidance:
            message["analyst_guidance"] = [
                {
                    "fiscal_year": g.fiscal_year,
                    "quarter": g.quarter,
                    "eps_estimate": g.analyst_eps_mean,
                    "eps_low": g.analyst_eps_low,
                    "eps_high": g.analyst_eps_high,
                    "revenue_estimate": g.analyst_revenue_mean,
                    "revenue_low": g.analyst_revenue_low,
                    "revenue_high": g.analyst_revenue_high,
                    "analyst_count": g.analyst_count,
                    "rating": g.analyst_rating.value if g.analyst_rating else None,
                    "rating_distribution": g.analyst_rating_distribution,
                    "updated_date": g.updated_date.isoformat() if g.updated_date else None,
                }
                for g in analytics.guidance
            ]

        # Add all additional data from yfinance
        # This includes: dividends_history, recommendations, quarterly statements,
        # institutional holders, insider transactions, and all other info fields
        if analytics.additional_data:
            message["additional_data"] = analytics.additional_data

        return message

    def get_stats(self) -> Dict[str, int]:
        """
        Get publisher statistics.

        Returns:
            Dictionary with detailed statistics:
            - message_count: Total messages attempted
            - error_count: Publish errors
            - delivery_success_count: Successfully delivered messages
            - delivery_error_count: Delivery failures
        """
        return {
            "message_count": self._message_count,
            "error_count": self._error_count,
            "delivery_success_count": self._delivery_success_count,
            "delivery_error_count": self._delivery_error_count,
        }


# Utility function to create a simple callback
def create_kafka_callback(
    bootstrap_servers: str = "localhost:9092",
    topic: str = "stock-updates",
) -> KafkaStockPublisher:
    """
    Create a Kafka callback with default settings.

    Args:
        bootstrap_servers: Kafka brokers
        topic: Kafka topic

    Returns:
        KafkaStockPublisher instance ready to use

    Example:
        kafka_callback = create_kafka_callback(
            bootstrap_servers="localhost:9092",
            topic="stock-updates"
        )
        kafka_callback.initialize()
        engine.add_update_callback(kafka_callback.publish_stock_update)
    """
    return KafkaStockPublisher(
        bootstrap_servers=bootstrap_servers,
        topic=topic,
    )
