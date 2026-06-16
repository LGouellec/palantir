"""
Daily ticker refresh job.

Run on a schedule (Kubernetes CronJob, ~06:00 ET before the US open). It
fetches the current NASDAQ + NYSE universe and patches the MarketShardConfig's
spec.symbols / spec.symbolsHash. The operator watches the resource and performs
the actual reconciliation (ConfigMap + StatefulSet rollout).

If the symbol list is unchanged (same hash) the patch is skipped, so no rollout
is triggered on days the universe didn't move.

Environment:
  MARKETSHARDCONFIG_NAME  (default: us-equities)
  MARKETSHARDCONFIG_NAMESPACE (default: longbridge / POD namespace)
  EXCHANGES               (default: NASDAQ,NYSE)
  INCLUDE_ETF             (default: true)
"""
import logging
import os
import sys

import kubernetes
from kubernetes.client.rest import ApiException

from sharding import symbols_hash
from tickers import fetch_us_symbols

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger("longbridge.operator.refresh")

GROUP = "trading.palantir.io"
VERSION = "v1alpha1"
PLURAL = "marketshardconfigs"


def _load_kube_config() -> None:
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    name = os.environ.get("MARKETSHARDCONFIG_NAME", "us-equities")
    namespace = os.environ.get("MARKETSHARDCONFIG_NAMESPACE", "longbridge")
    exchanges = tuple(
        e.strip() for e in os.environ.get("EXCHANGES", "NASDAQ,NYSE").split(",") if e.strip()
    )
    include_etf = _env_bool("INCLUDE_ETF", True)

    logger.info("Fetching US symbols (exchanges=%s, include_etf=%s)", exchanges, include_etf)
    symbols = fetch_us_symbols(exchanges=exchanges, include_etf=include_etf)
    if not symbols:
        logger.error("No symbols fetched; aborting without patch")
        return 1

    new_hash = symbols_hash(symbols)
    logger.info("Fetched %d symbols, hash=%s", len(symbols), new_hash[:18])

    _load_kube_config()
    api = kubernetes.client.CustomObjectsApi()

    try:
        current = api.get_namespaced_custom_object(GROUP, VERSION, namespace, PLURAL, name)
    except ApiException as exc:
        if exc.status == 404:
            logger.error(
                "MarketShardConfig %s/%s not found; apply the CR manifest first", namespace, name
            )
            return 1
        raise

    current_hash = (current.get("spec") or {}).get("symbolsHash")
    if current_hash == new_hash:
        logger.info("Symbol list unchanged (hash match); skipping patch")
        return 0

    patch = {"spec": {"symbols": symbols, "symbolsHash": new_hash}}
    api.patch_namespaced_custom_object(GROUP, VERSION, namespace, PLURAL, name, patch)
    logger.info(
        "Patched MarketShardConfig %s/%s with %d symbols (was hash=%s)",
        namespace,
        name,
        len(symbols),
        (current_hash or "none")[:18],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
