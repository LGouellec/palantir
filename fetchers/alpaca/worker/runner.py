"""
Alpaca news fetcher entrypoint.

  1. Resolve config (symbols, topic, Kafka) and Alpaca credentials
  2. Open one Alpaca NewsDataStream and forward every article to Kafka
  3. Periodically drain Kafka delivery callbacks and log stats until shutdown
"""
import logging
import signal
import sys
import threading

from alpaca_client import AlpacaNewsClient
from config import WorkerConfig
from credentials import resolve_credentials
from kafka_publisher import KafkaPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("alpaca.news")

_shutdown = threading.Event()


def _handle_signal(signum, _frame):
    logger.info("📨 Received signal %s; shutting down", signum)
    _shutdown.set()


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cfg = WorkerConfig.from_env()
    logger.info(
        "🚀 Alpaca news fetcher starting (symbols=%s, topic=%s)",
        cfg.symbols,
        cfg.news_topic,
    )

    creds = resolve_credentials()
    logger.info("🔑 Credentials resolved (%s)", creds.masked())

    publisher = KafkaPublisher(
        bootstrap_servers=cfg.kafka_bootstrap_servers,
        client_id="alpaca-news-fetcher",
        config_path=cfg.kafka_config_path or None,
    )
    publisher.initialize()

    client = AlpacaNewsClient(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        publish=publisher.publish,
        news_topic=cfg.news_topic,
        symbols=cfg.symbols,
        include_content=cfg.include_content,
    )

    try:
        client.start()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start Alpaca news stream")
        publisher.close()
        return 1

    # The stream pushes events from its own thread; here we periodically drain
    # delivery callbacks and log stats until we're told to stop.
    try:
        while not _shutdown.wait(cfg.flush_interval_s):
            publisher.poll(0)
            publisher.log_stats()
    finally:
        logger.info("🧹 Cleaning up")
        client.close()
        publisher.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
