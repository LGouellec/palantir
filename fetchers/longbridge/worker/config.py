"""
Worker configuration, resolved from environment variables.

In Kubernetes the worker runs as a StatefulSet pod, so the shard index is
derived from the pod ordinal (e.g. `market-shard-7` -> 7) unless SHARD_INDEX
is set explicitly.
"""
import json
import logging
import os
import re
import socket
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return int(val)


def resolve_shard_index() -> int:
    """Shard index from SHARD_INDEX, or parsed from the StatefulSet pod name."""
    val = os.environ.get("SHARD_INDEX")
    if val is not None and val != "":
        return int(val)

    hostname = os.environ.get("HOSTNAME") or socket.gethostname()
    match = re.search(r"-(\d+)$", hostname)
    if not match:
        raise RuntimeError(
            f"Cannot derive SHARD_INDEX from hostname '{hostname}'. "
            "Set SHARD_INDEX explicitly or run as a StatefulSet pod."
        )
    return int(match.group(1))


@dataclass
class WorkerConfig:
    shard_index: int
    shard_count: int
    max_per_shard: int
    symbols_path: str

    subscribe_quote: bool
    subscribe_depth: bool

    quote_topic: str
    depth_topic: str

    kafka_bootstrap_servers: str
    kafka_config_path: str = ""

    flush_interval_s: int = 30
    subscribe_batch_size: int = 100

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls(
            shard_index=resolve_shard_index(),
            shard_count=_env_int("SHARD_COUNT", 1),
            max_per_shard=_env_int("MAX_PER_SHARD", 500),
            symbols_path=os.environ.get("SYMBOLS_PATH", "/config/us-equities.json"),
            subscribe_quote=_env_bool("SUBSCRIBE_QUOTE", True),
            subscribe_depth=_env_bool("SUBSCRIBE_DEPTH", True),
            quote_topic=os.environ.get("QUOTE_TOPIC", "quotes.realtime"),
            depth_topic=os.environ.get("DEPTH_TOPIC", "quotes.depth"),
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            kafka_config_path=os.environ.get("KAFKA_CONFIG_PATH", ""),
            flush_interval_s=_env_int("FLUSH_INTERVAL_S", 30),
            subscribe_batch_size=_env_int("SUBSCRIBE_BATCH_SIZE", 100),
        )


def load_symbols(symbols_path: str) -> List[str]:
    """Load the full ordered symbol list written by the operator.

    Accepts either a JSON array of symbols, or an object with a "symbols" key.
    """
    if not os.path.isfile(symbols_path):
        raise FileNotFoundError(f"symbols file not found: {symbols_path}")

    with open(symbols_path, "r") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = data.get("symbols", [])
    if not isinstance(data, list):
        raise ValueError(f"{symbols_path} must contain a JSON array of symbols")

    return [str(s) for s in data]
