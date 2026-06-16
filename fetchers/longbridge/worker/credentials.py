"""
Longbridge credential resolution for a shard.

Longbridge allows a single long-lived WebSocket per account and 500 tickers
per WebSocket. To cover ~6000 US tickers we run one shard per account, so each
pod needs its *own* set of credentials selected by its shard index.

Resolution order (first match wins):
  1. Per-shard file in LONGPORT_CREDENTIALS_DIR (default /secrets):
       <dir>/shard-<index>.json | <dir>/shard-<index> | <dir>/<index>.json
     Each file is JSON: {"app_key": "...", "app_secret": "...", "access_token": "..."}
     Or a single combined <dir>/credentials.json mapping "<index>" -> {...}
     or a JSON array indexed by position.
  2. Indexed environment variables:
       LONGPORT_APP_KEY_<index> / LONGPORT_APP_SECRET_<index> / LONGPORT_ACCESS_TOKEN_<index>
  3. Shared environment variables (handy for local/dev with a single account):
       LONGPORT_APP_KEY / LONGPORT_APP_SECRET / LONGPORT_ACCESS_TOKEN
"""
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_FIELDS = ("app_key", "app_secret", "access_token")


@dataclass(frozen=True)
class LongbridgeCredentials:
    app_key: str
    app_secret: str
    access_token: str

    def masked(self) -> str:
        return f"app_key={self.app_key[:4]}…({len(self.app_key)} chars)"


def _from_mapping(data: dict) -> LongbridgeCredentials:
    missing = [f for f in _FIELDS if not data.get(f)]
    if missing:
        raise ValueError(f"credentials missing fields: {missing}")
    return LongbridgeCredentials(
        app_key=str(data["app_key"]),
        app_secret=str(data["app_secret"]),
        access_token=str(data["access_token"]),
    )


def _load_file(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _resolve_from_dir(cred_dir: str, shard_index: int) -> Optional[LongbridgeCredentials]:
    candidates = (
        f"shard-{shard_index}.json",
        f"shard-{shard_index}",
        f"{shard_index}.json",
        f"{shard_index}",
    )
    for name in candidates:
        path = os.path.join(cred_dir, name)
        if os.path.isfile(path):
            logger.info("🔑 Loading shard %s credentials from %s", shard_index, path)
            return _from_mapping(_load_file(path))

    combined = os.path.join(cred_dir, "credentials.json")
    if os.path.isfile(combined):
        data = _load_file(combined)
        if isinstance(data, list):
            if shard_index >= len(data):
                raise IndexError(
                    f"shard {shard_index} out of range: credentials.json has {len(data)} entries"
                )
            entry = data[shard_index]
        elif isinstance(data, dict):
            entry = data.get(str(shard_index)) or data.get(shard_index)
            if entry is None:
                raise KeyError(f"no credentials for shard {shard_index} in credentials.json")
        else:
            raise ValueError("credentials.json must be a list or an object")
        logger.info("🔑 Loading shard %s credentials from %s", shard_index, combined)
        return _from_mapping(entry)
    return None


def _resolve_from_indexed_env(shard_index: int) -> Optional[LongbridgeCredentials]:
    key = os.environ.get(f"LONGPORT_APP_KEY_{shard_index}")
    if not key:
        return None
    logger.info("🔑 Loading shard %s credentials from indexed env vars", shard_index)
    return _from_mapping(
        {
            "app_key": key,
            "app_secret": os.environ.get(f"LONGPORT_APP_SECRET_{shard_index}", ""),
            "access_token": os.environ.get(f"LONGPORT_ACCESS_TOKEN_{shard_index}", ""),
        }
    )


def _resolve_from_shared_env() -> Optional[LongbridgeCredentials]:
    key = os.environ.get("LONGPORT_APP_KEY")
    if not key:
        return None
    logger.warning(
        "🔑 Using SHARED Longbridge credentials (LONGPORT_APP_KEY). "
        "This is fine for local/dev but does not respect the 1-account-per-shard limit."
    )
    return _from_mapping(
        {
            "app_key": key,
            "app_secret": os.environ.get("LONGPORT_APP_SECRET", ""),
            "access_token": os.environ.get("LONGPORT_ACCESS_TOKEN", ""),
        }
    )


def resolve_credentials(shard_index: int) -> LongbridgeCredentials:
    """Resolve the Longbridge credentials for `shard_index` or raise."""
    cred_dir = os.environ.get("LONGPORT_CREDENTIALS_DIR", "/secrets")
    if os.path.isdir(cred_dir):
        creds = _resolve_from_dir(cred_dir, shard_index)
        if creds:
            return creds

    creds = _resolve_from_indexed_env(shard_index)
    if creds:
        return creds

    creds = _resolve_from_shared_env()
    if creds:
        return creds

    raise RuntimeError(
        f"No Longbridge credentials found for shard {shard_index}. "
        f"Provide a per-shard file in LONGPORT_CREDENTIALS_DIR ({cred_dir}), "
        f"indexed env vars (LONGPORT_APP_KEY_{shard_index}), "
        f"or shared env vars (LONGPORT_APP_KEY)."
    )
