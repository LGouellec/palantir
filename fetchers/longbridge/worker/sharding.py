"""
Sharding helpers shared between the operator and the worker.

The operator writes the *full*, deterministically ordered list of Longbridge
symbols into a ConfigMap. Each worker pod owns a contiguous slice of that list,
selected by its shard index. As long as both sides agree on `max_per_shard`
and the operator keeps the list ordered, the mapping shard -> tickers is stable.
"""
import math
from typing import List, Sequence


def shard_count(num_symbols: int, max_per_shard: int) -> int:
    """Number of shards required to cover `num_symbols` at `max_per_shard` each."""
    if max_per_shard <= 0:
        raise ValueError("max_per_shard must be > 0")
    return max(1, math.ceil(num_symbols / max_per_shard))


def shard_slice(symbols: Sequence[str], shard_index: int, max_per_shard: int) -> List[str]:
    """Return the contiguous chunk of symbols owned by `shard_index`.

    Shard i owns symbols[i * max_per_shard : (i + 1) * max_per_shard].
    Returns an empty list if the index is beyond the populated shards.
    """
    if shard_index < 0:
        raise ValueError("shard_index must be >= 0")
    if max_per_shard <= 0:
        raise ValueError("max_per_shard must be > 0")
    start = shard_index * max_per_shard
    end = start + max_per_shard
    return list(symbols[start:end])
