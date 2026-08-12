"""
Kafka consumer for `stock_quotes.trade_signal`.

The topic is produced by Flink with key.format/value.format = json-registry
(Confluent wire-format JSON Schema via Schema Registry), so consuming it for
real (Confluent Cloud) needs registry-aware decoding. When SCHEMA_REGISTRY_URL
is unset we fall back to plain `json.loads`, which lets the local smoke test
(agent/docker-compose.yml, no registry) publish the example payload from
agent/spec.md directly.

Offset handling mirrors scrapers/wsj/wsj_scraper_distributed.py: auto-commit
is on a timer, but the offset store itself is only advanced manually (after
runner.py has fully executed the decision for a message), giving an
at-least-once guarantee instead of losing a signal on a mid-processing crash.
"""
import json
import logging
import os
from typing import Optional

from confluent_kafka import DeserializingConsumer, KafkaError

logger = logging.getLogger(__name__)


def _plain_json_deserializer(data: Optional[bytes], _ctx) -> Optional[dict]:
    if data is None:
        return None
    return json.loads(data)


def _load_kafka_config_file(config_path: str) -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Kafka config file not found: {config_path}")

    conf = {}
    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                conf[key.strip()] = value.strip()
    return conf


def _build_value_deserializer(cfg):
    if not cfg.schema_registry_url:
        logger.info("📄 SCHEMA_REGISTRY_URL unset; decoding trade signals as plain JSON")
        return _plain_json_deserializer

    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.json_schema import JSONDeserializer

    sr_conf = {"url": cfg.schema_registry_url}
    if cfg.schema_registry_api_key:
        sr_conf["basic.auth.user.info"] = (
            f"{cfg.schema_registry_api_key}:{cfg.schema_registry_api_secret}"
        )

    logger.info("📄 Decoding trade signals via Schema Registry at %s", cfg.schema_registry_url)
    schema_registry_client = SchemaRegistryClient(sr_conf)
    # schema_str=None -> resolve the writer schema per-message from the id
    # embedded in the Confluent wire-format header; from_dict=None -> return
    # the plain dict (no need for a generated model class here).
    return JSONDeserializer(schema_str=None, schema_registry_client=schema_registry_client)


class TradeSignalConsumer:
    def __init__(self, cfg):
        self._cfg = cfg
        value_deserializer = _build_value_deserializer(cfg)

        conf = {
            "bootstrap.servers": cfg.kafka_bootstrap_servers,
            "group.id": cfg.consumer_group_id,
            "client.id": "trading-agent",
            "value.deserializer": value_deserializer,
            "auto.offset.reset": "latest", # start at the end of the topic
            "enable.auto.commit": False,
            "auto.commit.interval.ms": 5000,
            "enable.auto.offset.store": False,
        }
        if cfg.kafka_config_path:
            conf.update(_load_kafka_config_file(cfg.kafka_config_path))

        self._consumer = DeserializingConsumer(conf)
        self._consumer.subscribe([cfg.trade_signal_topic])
        logger.info(
            "📡 Subscribed to %s as group %s", cfg.trade_signal_topic, cfg.consumer_group_id
        )

    def poll(self, timeout: float):
        msg = self._consumer.poll(timeout)
        if msg is None:
            return None

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                return None
            logger.error("❌ Kafka error: %s", msg.error())
            return None

        return msg

    def mark_processed(self, msg) -> None:
        self._consumer.store_offsets(msg)

    def close(self) -> None:
        self._consumer.close()
