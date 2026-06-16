"""
Kopf operator that reconciles a MarketShardConfig into a running fleet of
Longbridge shard workers.

For each MarketShardConfig it:
  1. Computes shardCount = ceil(len(symbols) / maxPerShard)
  2. Writes the full ordered symbol list + SHARD_COUNT/MAX_PER_SHARD into a
     ConfigMap that the StatefulSet mounts and reads.
  3. Patches the StatefulSet's replicas to shardCount and stamps the symbols
     hash on the pod template so a changed ticker list triggers a rolling
     restart (each pod re-reads its slice on boot).
  4. Records observed state back into the resource's status.

The daily ticker fetch lives in refresh.py (run as a CronJob); it patches the
MarketShardConfig's spec.symbols, which wakes this operator via on.update.
"""
import datetime
import json
import logging
import os

import kopf
import kubernetes
from kubernetes.client.rest import ApiException

from sharding import shard_count, symbols_hash

logger = logging.getLogger("longbridge.operator")

GROUP = "trading.palantir.io"
VERSION = "v1alpha1"
PLURAL = "marketshardconfigs"

HASH_ANNOTATION = f"{GROUP}/symbols-hash"

# Names of the workload objects the operator manages. They live in the same
# namespace as the MarketShardConfig unless TARGET_NAMESPACE is set.
STATEFULSET_NAME = os.environ.get("STATEFULSET_NAME", "market-shard")
CONFIGMAP_NAME = os.environ.get("CONFIGMAP_NAME", "market-shard-symbols")
SELF_HEAL_INTERVAL_S = float(os.environ.get("SELF_HEAL_INTERVAL_S", "300"))


def _load_kube_config() -> None:
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    _load_kube_config()
    settings.posting.level = logging.INFO
    logger.info(
        "Longbridge operator started (statefulset=%s, configmap=%s)",
        STATEFULSET_NAME,
        CONFIGMAP_NAME,
    )


def _target_namespace(cr_namespace: str) -> str:
    return os.environ.get("TARGET_NAMESPACE") or cr_namespace


def _upsert_configmap(namespace: str, symbols, count: int, max_per_shard: int, shash: str):
    core = kubernetes.client.CoreV1Api()
    data = {
        "us-equities.json": json.dumps(symbols, separators=(",", ":")),
        "SHARD_COUNT": str(count),
        "MAX_PER_SHARD": str(max_per_shard),
        "SYMBOLS_HASH": shash,
    }
    body = kubernetes.client.V1ConfigMap(
        metadata=kubernetes.client.V1ObjectMeta(
            name=CONFIGMAP_NAME,
            namespace=namespace,
            labels={"app": "market-shard", "managed-by": "longbridge-operator"},
        ),
        data=data,
    )
    try:
        core.replace_namespaced_config_map(CONFIGMAP_NAME, namespace, body)
        logger.info("ConfigMap %s/%s updated", namespace, CONFIGMAP_NAME)
    except ApiException as exc:
        if exc.status == 404:
            core.create_namespaced_config_map(namespace, body)
            logger.info("ConfigMap %s/%s created", namespace, CONFIGMAP_NAME)
        else:
            raise


def _patch_statefulset(namespace: str, count: int, shash: str):
    apps = kubernetes.client.AppsV1Api()
    patch = {
        "spec": {
            "replicas": count,
            "template": {
                "metadata": {
                    "annotations": {HASH_ANNOTATION: shash},
                }
            },
        }
    }
    try:
        apps.patch_namespaced_stateful_set(STATEFULSET_NAME, namespace, patch)
        logger.info(
            "StatefulSet %s/%s patched: replicas=%d, hash=%s",
            namespace,
            STATEFULSET_NAME,
            count,
            shash[:18],
        )
    except ApiException as exc:
        if exc.status == 404:
            logger.warning(
                "StatefulSet %s/%s not found; apply the workload manifest first",
                namespace,
                STATEFULSET_NAME,
            )
        else:
            raise


def _reconcile(spec, cr_namespace, patch, logger):
    symbols = list(spec.get("symbols", []) or [])
    max_per_shard = int(spec.get("maxPerShard", 500))
    count = shard_count(len(symbols), max_per_shard)
    shash = spec.get("symbolsHash") or symbols_hash(symbols)

    namespace = _target_namespace(cr_namespace)
    logger.info(
        "Reconciling: %d symbols, maxPerShard=%d -> shardCount=%d (ns=%s)",
        len(symbols),
        max_per_shard,
        count,
        namespace,
    )

    if symbols:
        _upsert_configmap(namespace, symbols, count, max_per_shard, shash)
        _patch_statefulset(namespace, count, shash)
    else:
        logger.warning("MarketShardConfig has no symbols yet; nothing to reconcile")

    patch.status["shardCount"] = count
    patch.status["symbolCount"] = len(symbols)
    patch.status["observedHash"] = shash
    patch.status["targetNamespace"] = namespace
    patch.status["lastReconcile"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {"shardCount": count, "symbolCount": len(symbols)}


@kopf.on.create(GROUP, VERSION, PLURAL)
@kopf.on.update(GROUP, VERSION, PLURAL)
@kopf.on.resume(GROUP, VERSION, PLURAL)
def reconcile(spec, namespace, patch, logger, **_):
    return _reconcile(spec, namespace, patch, logger)


@kopf.timer(GROUP, VERSION, PLURAL, interval=SELF_HEAL_INTERVAL_S)
def self_heal(spec, namespace, patch, logger, **_):
    """Periodically re-assert desired state in case the workload drifted."""
    return _reconcile(spec, namespace, patch, logger)
