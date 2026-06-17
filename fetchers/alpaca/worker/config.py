"""
Worker configuration, resolved from environment variables.

The Alpaca news stream is a single WebSocket (one connection covers every
symbol via the "*" wildcard), so unlike the Longbridge fetcher there is no
sharding here — one pod owns the whole stream.
"""
import logging
import os
from dataclasses import dataclass
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


def parse_symbols(raw: str) -> List[str]:
    """Parse the NEWS_SYMBOLS env var into a list for subscribe_news().

    Accepts a comma-separated list (e.g. "AAPL,MSFT,TSLA") or the wildcard "*"
    to stream news for every symbol. Symbols are upper-cased; "*" is preserved.
    """
    if not raw:
        return ["*"]
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    return symbols or ["*"]


@dataclass
class WorkerConfig:
    symbols: List[str]
    news_topic: str
    include_content: bool

    kafka_bootstrap_servers: str
    kafka_config_path: str = ""

    flush_interval_s: int = 30

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls(
            symbols=parse_symbols(os.environ.get("NEWS_SYMBOLS", "*")),
            news_topic=os.environ.get("NEWS_TOPIC", "news.realtime"),
            include_content=_env_bool("INCLUDE_CONTENT", True),
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            kafka_config_path=os.environ.get("KAFKA_CONFIG_PATH", ""),
            flush_interval_s=_env_int("FLUSH_INTERVAL_S", 30),
        )
