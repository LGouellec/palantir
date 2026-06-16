"""
Kafka publisher for Longbridge real-time market data.

Uses the Confluent Kafka producer, like the other scrapers/fetchers in this
repo. Supports loading the full producer config from a properties file via the
KAFKA_CONFIG_PATH environment variable (Confluent Cloud SASL_SSL settings).
"""
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class KafkaPublisher:
    """Thin wrapper around confluent_kafka.Producer with JSON serialization."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        client_id: str = "longbridge-fetcher",
        compression_type: Optional[str] = "lz4",
        acks: str = "1",
        config_path: Optional[str] = None,
        **additional_config: Any,
    ):
        self.producer = None
        self._initialized = False

        self.producer_config: Dict[str, Any] = {
            "bootstrap.servers": bootstrap_servers,
            "compression.type": compression_type or "none",
            "acks": acks,
            "client.id": client_id,
            # Real-time quotes are high-throughput; small linger batches well.
            "linger.ms": 20,
            "queue.buffering.max.messages": 1_000_000,
        }
        self.producer_config.update(additional_config)

        config_path = config_path or os.environ.get("KAFKA_CONFIG_PATH")
        if config_path:
            self._load_config_from_file(config_path)

        self._message_count = 0
        self._error_count = 0
        self._delivery_success_count = 0
        self._delivery_error_count = 0

    def _load_config_from_file(self, config_path: str) -> None:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Kafka config file not found: {config_path}")

        logger.info("📄 Loading Kafka config from: %s", config_path)
        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    self.producer_config[key.strip()] = value.strip()
        logger.info("✅ Loaded Kafka config (%d properties)", len(self.producer_config))

    def initialize(self) -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "confluent-kafka is required. Install with: pip install confluent-kafka"
            ) from exc

        self.producer = Producer(self.producer_config)
        self._initialized = True
        logger.info("✅ Kafka producer initialized")
        logger.info("   Brokers: %s", self.producer_config.get("bootstrap.servers"))
        for key, value in  self.producer_config.items():
            print(f"{key}: {value}")

    def _delivery_callback(self, err, msg) -> None:
        if err:
            self._delivery_error_count += 1
            if self._delivery_error_count <= 10 or self._delivery_error_count % 100 == 0:
                logger.error("❌ Delivery failed: %s", err)
        else:
            self._delivery_success_count += 1

    def publish(self, topic: str, key: str, value: Dict[str, Any]) -> None:
        """Produce a JSON message keyed by `key` (non-blocking)."""
        if not self._initialized:
            logger.warning("⚠️  Kafka producer not initialized; dropping message")
            return

        try:
            self.producer.produce(
                topic=topic,
                value=json.dumps(value, separators=(",", ":")).encode("utf-8"),
                key=key.encode("utf-8"),
                callback=self._delivery_callback,
            )
            self.producer.poll(0)
            self._message_count += 1
        except BufferError:
            # Local queue full: block briefly to drain, then retry once.
            self._error_count += 1
            self.producer.poll(0.5)
            try:
                self.producer.produce(
                    topic=topic,
                    value=json.dumps(value, separators=(",", ":")).encode("utf-8"),
                    key=key.encode("utf-8"),
                    callback=self._delivery_callback,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("❌ Dropping message for %s after buffer retry: %s", key, exc)
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            logger.error("❌ Failed to publish %s: %s", key, exc)

    def poll(self, timeout: float = 0) -> None:
        if self._initialized:
            self.producer.poll(timeout)

    def flush(self, timeout: float = 30) -> None:
        if self._initialized and self.producer:
            self.producer.flush(timeout)

    def close(self) -> None:
        if self._initialized and self.producer:
            logger.info("🔄 Flushing pending messages...")
            self.producer.flush(timeout=30)
            self._initialized = False
            logger.info("🛑 Kafka producer stopped")
            self.log_stats()

    def log_stats(self) -> None:
        logger.info(
            "📊 produced=%d delivered=%d delivery_errors=%d publish_errors=%d",
            self._message_count,
            self._delivery_success_count,
            self._delivery_error_count,
            self._error_count,
        )
