"""
Shard worker entrypoint.

  1. Resolve this pod's shard index (from SHARD_INDEX or the StatefulSet ordinal)
  2. Load the full ordered symbol list (written by the operator into a ConfigMap)
  3. Compute this shard's contiguous slice of <= MAX_PER_SHARD symbols
  4. Resolve this shard's Longbridge credentials
  5. Open one Longbridge WebSocket and stream quotes + depth into Kafka
"""
import logging
import signal
import sys
import threading

from config import WorkerConfig, load_symbols
from credentials import resolve_credentials
from kafka_publisher import KafkaPublisher
from longbridge_client import LongbridgeShardClient
from sharding import shard_count, shard_slice

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("longbridge.worker")

_shutdown = threading.Event()


def _handle_signal(signum, _frame):
    logger.info("📨 Received signal %s; shutting down", signum)
    _shutdown.set()


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cfg = WorkerConfig.from_env()
    logger.info(
        "🚀 Longbridge shard worker starting (shard_index=%d, shard_count=%d, max_per_shard=%d)",
        cfg.shard_index,
        cfg.shard_count,
        cfg.max_per_shard,
    )

    all_symbols = load_symbols(cfg.symbols_path)
    expected_shards = shard_count(len(all_symbols), cfg.max_per_shard)
    logger.info("📋 Loaded %d symbols -> %d shards expected", len(all_symbols), expected_shards)

    if cfg.shard_index >= expected_shards:
        # Over-provisioned replica (e.g. mid-rollout): nothing to do, stay healthy.
        logger.warning(
            "Shard %d has no work (only %d shards needed); idling until shutdown",
            cfg.shard_index,
            expected_shards,
        )
        _shutdown.wait()
        return 0

    my_symbols = shard_slice(all_symbols, cfg.shard_index, cfg.max_per_shard)
    logger.info("🎯 This shard owns %d symbols: %s …", len(my_symbols), my_symbols[:5])

    creds = resolve_credentials(cfg.shard_index)
    logger.info("🔑 Credentials resolved (%s)", creds.masked())

    publisher = KafkaPublisher(
        bootstrap_servers=cfg.kafka_bootstrap_servers,
        client_id=f"longbridge-shard-{cfg.shard_index}",
        config_path=cfg.kafka_config_path or None,
    )
    publisher.initialize()

    client = LongbridgeShardClient(
        app_key=creds.app_key,
        app_secret=creds.app_secret,
        access_token=creds.access_token,
        publish=publisher.publish,
        quote_topic=cfg.quote_topic,
        depth_topic=cfg.depth_topic,
        subscribe_quote=cfg.subscribe_quote,
        subscribe_depth=cfg.subscribe_depth,
        subscribe_batch_size=cfg.subscribe_batch_size,
    )

    try:
        client.start(my_symbols)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start Longbridge subscription")
        publisher.close()
        return 1

    # The SDK pushes events from its own thread; here we periodically drain
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
