"""
Longbridge WebSocket client for one shard.

Opens a single QuoteContext (one long-lived WebSocket per account), subscribes
to this shard's symbols for real-time quotes and order-book depth, and forwards
every push event to Kafka. The QuoteContext runs its own background thread and
auto-reconnects / re-subscribes, so the caller only needs to keep the process
alive.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Longbridge market suffix for US equities (e.g. "AAPL.US").
US_SUFFIX = ".US"


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _enum_name(value) -> Optional[str]:
    """Render an SDK enum (e.g. TradeStatus.Normal) as its bare name."""
    if value is None:
        return None
    return str(value).rsplit(".", 1)[-1]


def _plain_symbol(longbridge_symbol: str) -> str:
    """Strip the market suffix: 'AAPL.US' -> 'AAPL'."""
    return longbridge_symbol.rsplit(".", 1)[0]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Type of the publish sink: (topic, key, value_dict) -> None
PublishFn = Callable[[str, str, dict], None]


class LongbridgeShardClient:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        access_token: str,
        publish: PublishFn,
        quote_topic: str,
        depth_topic: str,
        subscribe_quote: bool = True,
        subscribe_depth: bool = True,
        subscribe_batch_size: int = 100,
    ):
        self._app_key = app_key
        self._app_secret = app_secret
        self._access_token = access_token
        self._publish = publish
        self._quote_topic = quote_topic
        self._depth_topic = depth_topic
        self._subscribe_quote = subscribe_quote
        self._subscribe_depth = subscribe_depth
        self._batch_size = max(1, subscribe_batch_size)
        self._ctx = None

    # ------------------------------------------------------------------ #
    # Event handlers (invoked from the SDK background thread)
    # ------------------------------------------------------------------ #
    def _on_quote(self, symbol: str, event) -> None:
        try:
            ts = event.timestamp
            message = {
                "symbol": _plain_symbol(symbol),
                "longbridge_symbol": symbol,
                "source": "longbridge",
                "event_type": "quote",
                "event_time": ts.isoformat() if isinstance(ts, datetime) else None,
                "ingest_time": _now_iso(),
                "last_done": _to_float(event.last_done),
                "open": _to_float(event.open),
                "high": _to_float(event.high),
                "low": _to_float(event.low),
                "volume": event.volume,
                "turnover": _to_float(event.turnover),
                "trade_status": _enum_name(getattr(event, "trade_status", None)),
                "trade_session": _enum_name(getattr(event, "trade_session", None)),
            }
            self._publish(self._quote_topic, message["symbol"], message)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to handle quote push for %s", symbol)

    def _on_depth(self, symbol: str, event) -> None:
        try:
            message = {
                "symbol": _plain_symbol(symbol),
                "longbridge_symbol": symbol,
                "source": "longbridge",
                "event_type": "depth",
                "ingest_time": _now_iso(),
                "asks": [self._depth_level(d) for d in event.asks],
                "bids": [self._depth_level(d) for d in event.bids],
            }
            self._publish(self._depth_topic, message["symbol"], message)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to handle depth push for %s", symbol)

    @staticmethod
    def _depth_level(depth) -> dict:
        return {
            "position": depth.position,
            "price": _to_float(depth.price),
            "volume": depth.volume,
            "order_num": depth.order_num,
        }

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self, symbols: List[str]) -> None:
        from longport.openapi import Config, QuoteContext, SubType

        if not symbols:
            logger.warning("⚠️  Shard has no symbols to subscribe to; idling")
            return

        sub_types = []
        if self._subscribe_quote:
            sub_types.append(SubType.Quote)
        if self._subscribe_depth:
            sub_types.append(SubType.Depth)
        if not sub_types:
            raise ValueError("At least one of SUBSCRIBE_QUOTE / SUBSCRIBE_DEPTH must be enabled")

        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            access_token=self._access_token,
        )
        self._ctx = QuoteContext(config)

        if self._subscribe_quote:
            self._ctx.set_on_quote(self._on_quote)
        if self._subscribe_depth:
            self._ctx.set_on_depth(self._on_depth)

        logger.info(
            "📡 Subscribing %d symbols (quote=%s, depth=%s) in batches of %d",
            len(symbols),
            self._subscribe_quote,
            self._subscribe_depth,
            self._batch_size,
        )
        # The Longbridge API caps the number of symbols per subscribe call, so
        # we batch. is_first_push=True delivers an initial snapshot per symbol.
        for i in range(0, len(symbols), self._batch_size):
            batch = symbols[i : i + self._batch_size]
            self._ctx.subscribe(batch, sub_types)
            logger.info("   subscribed %d/%d", min(i + self._batch_size, len(symbols)), len(symbols))

        logger.info("✅ Subscription complete; streaming quotes")

    def close(self) -> None:
        # QuoteContext closes its WebSocket when garbage collected; drop the ref.
        self._ctx = None
