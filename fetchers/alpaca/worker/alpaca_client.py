"""
Alpaca real-time news WebSocket client.

Opens a single NewsDataStream
(wss://stream.data.alpaca.markets/v1beta1/news), subscribes to the configured
symbols (or "*" for every symbol), and forwards each article to Kafka. The
stream manages its own asyncio loop and auto-reconnects, so we run it on a
background thread and keep the main thread free to flush Kafka.

See https://docs.alpaca.markets/us/docs/streaming-real-time-news and
https://github.com/alpacahq/alpaca-py
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Type of the publish sink: (topic, key, value_dict) -> None
PublishFn = Callable[[str, str, dict], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> Optional[str]:
    """Render a datetime (or already-stringified timestamp) as an ISO string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _clean_html(value: Any) -> Optional[str]:
    """Strip HTML tags from a string, returning plain text.

    Alpaca news content (and sometimes the summary) arrives with HTML markup,
    so we run it through BeautifulSoup to recover readable text.
    """
    if value is None:
        return None
    text = BeautifulSoup(str(value), "html.parser").get_text(separator=" ")
    return " ".join(text.split())


def _get(obj: Any, *names: str) -> Any:
    """Read a field from either a News model (attributes) or a raw dict."""
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        elif hasattr(obj, name):
            return getattr(obj, name)
    return None


class AlpacaNewsClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        publish: PublishFn,
        news_topic: str,
        symbols: List[str],
        include_content: bool = True,
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._publish = publish
        self._news_topic = news_topic
        self._symbols = symbols or ["*"]
        self._include_content = include_content
        self._stream = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Message shaping
    # ------------------------------------------------------------------ #
    def _normalize(self, news: Any) -> dict:
        symbols = list(_get(news, "symbols") or [])
        images = _get(news, "images") or []
        message = {
            "id": _get(news, "id"),
            "headline": _get(news, "headline"),
            "summary": _get(news, "summary"),
            "author": _get(news, "author"),
            "url": _get(news, "url"),
            "symbols": symbols,
            "source": _get(news, "source"),
            "created_at": _iso(_get(news, "created_at")),
            "updated_at": _iso(_get(news, "updated_at")),
            "images": [
                {"size": _get(img, "size"), "url": _get(img, "url")} for img in images
            ],
            # Provenance, mirroring the other fetchers in this repo.
            "fetch_source": "alpaca",
            "event_type": "news",
            "ingest_time": _now_iso(),
        }
        if self._include_content:
            message["content"] = _clean_html(_get(news, "content"))
        return message

    # ------------------------------------------------------------------ #
    # Event handler (invoked from the stream's asyncio loop)
    # ------------------------------------------------------------------ #
    async def _on_news(self, news: Any) -> None:
        try:
            message = self._normalize(news)
            symbols = message.get("symbols") or []
            if not symbols:
                # No symbols on the article: fall back to the news id as key so
                # the event is still published.
                news_id = message.get("id")
                key = str(news_id) if news_id is not None else "unknown"
                self._publish(self._news_topic, key, message)
                return

            # One Kafka message per symbol, keyed by that symbol so a company's
            # news stays ordered on its partition. The payload is identical.
            for symbol in symbols:
                self._publish(self._news_topic, str(symbol), message)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to handle news event")

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        from alpaca.data.live.news import NewsDataStream

        self._stream = NewsDataStream(self._api_key, self._api_secret)
        self._stream.subscribe_news(self._on_news, *self._symbols)

        logger.info("📡 Subscribing to Alpaca news for symbols: %s", self._symbols)

        # stream.run() blocks running its own asyncio loop, so push it to a
        # daemon thread and let the main thread drive Kafka flushing.
        self._thread = threading.Thread(
            target=self._run, name="alpaca-news-stream", daemon=True
        )
        self._thread.start()
        logger.info("✅ Alpaca news stream started")

    def _run(self) -> None:
        try:
            self._stream.run()
        except Exception:  # noqa: BLE001
            logger.exception("Alpaca news stream terminated unexpectedly")

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:  # noqa: BLE001
                logger.debug("Error while stopping Alpaca news stream", exc_info=True)
            self._stream = None
