"""
Sharding + hashing helpers for the operator.

Mirrors fetchers/longbridge/worker/sharding.py so both sides agree on the
shard count for a given symbol list and max_per_shard.
"""
import hashlib
import math
from typing import Sequence


def shard_count(num_symbols: int, max_per_shard: int) -> int:
    if max_per_shard <= 0:
        raise ValueError("max_per_shard must be > 0")
    if num_symbols <= 0:
        return 0
    return max(1, math.ceil(num_symbols / max_per_shard))


def symbols_hash(symbols: Sequence[str]) -> str:
    """Stable content hash of the (ordered) symbol list."""
    h = hashlib.sha256()
    for s in symbols:
        h.update(s.encode("utf-8"))
        h.update(b"\n")
    return "sha256:" + h.hexdigest()
