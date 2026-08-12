"""
Alpaca credential resolution.

Same resolution order as fetchers/alpaca/worker/credentials.py (kept as its
own copy rather than a shared import - each worker in this repo already
carries its own credentials module):

  1. A JSON file at ALPACA_CREDENTIALS_FILE (default /secrets/credentials.json):
       {"api_key": "...", "api_secret": "..."}
  2. Environment variables (the standard Alpaca names, with ALPACA_* aliases):
       APCA_API_KEY_ID / APCA_API_SECRET_KEY
       ALPACA_API_KEY  / ALPACA_API_SECRET

The same key pair is used for both market data and trading - Alpaca routes to
paper vs live based on which base URL/`paper` flag the client is built with,
not on the credentials themselves.
"""
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlpacaCredentials:
    api_key: str
    api_secret: str

    def masked(self) -> str:
        return f"api_key={self.api_key[:4]}…({len(self.api_key)} chars)"


def _from_mapping(data: dict) -> Optional[AlpacaCredentials]:
    key = data.get("api_key") or data.get("APCA_API_KEY_ID")
    secret = data.get("api_secret") or data.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        return None
    return AlpacaCredentials(api_key=str(key), api_secret=str(secret))


def _resolve_from_file() -> Optional[AlpacaCredentials]:
    path = os.environ.get("ALPACA_CREDENTIALS_FILE", "/secrets/credentials.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r") as f:
        creds = _from_mapping(json.load(f))
    if creds:
        logger.info("🔑 Loading Alpaca credentials from %s", path)
    return creds


def _resolve_from_env() -> Optional[AlpacaCredentials]:
    key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    logger.info("🔑 Loading Alpaca credentials from environment variables")
    return AlpacaCredentials(api_key=key, api_secret=secret)


def resolve_credentials() -> AlpacaCredentials:
    """Resolve Alpaca API credentials or raise."""
    creds = _resolve_from_file() or _resolve_from_env()
    if creds:
        return creds

    raise RuntimeError(
        "No Alpaca credentials found. Provide a JSON file at "
        "ALPACA_CREDENTIALS_FILE (default /secrets/credentials.json) or set "
        "APCA_API_KEY_ID / APCA_API_SECRET_KEY environment variables."
    )
