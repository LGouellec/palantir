"""Run the TA UDF locally — no Flink cluster, no JVM, just pandas.

This calls the same `compute_indicators` the PyFlink UDF uses, so what you see
here is exactly what Flink would emit for the latest candle of the window.

Usage:
    # Built-in synthetic candles (a rising series):
    uv run python examples/local_run.py

    # Your own candles from CSV (needs columns: close,high,low,volume):
    uv run python examples/local_run.py --csv candles.csv

    # Or from a JSON file shaped like {"close": [...], "high": [...], ...}:
    uv run python examples/local_run.py --json candles.json

Without uv:  pip install pandas pandas-ta-classic, then `python examples/local_run.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `ta_udf` importable when run straight from the repo (src layout).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ta_udf.compute import compute_indicators  # noqa: E402


def _synthetic(n: int = 100) -> dict[str, list[float]]:
    """A simple rising close series with synthetic high/low/volume."""
    close = [100.0 + i * 0.7 for i in range(n)]
    return {
        "close": close,
        "high": [c + 0.5 for c in close],
        "low": [c - 0.5 for c in close],
        "volume": [1000.0 + i for i in range(n)],
    }


def _from_csv(path: str) -> dict[str, list[float]]:
    import csv

    cols = {"close": [], "high": [], "low": [], "volume": []}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            for key in cols:
                cols[key].append(float(row[key]))
    return cols


def _from_json(path: str) -> dict[str, list[float]]:
    data = json.loads(Path(path).read_text())
    return {key: [float(v) for v in data[key]] for key in ("close", "high", "low", "volume")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TA UDF on a set of candles.")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--csv", help="CSV file with close,high,low,volume columns")
    src.add_argument("--json", help="JSON file with close/high/low/volume arrays")
    parser.add_argument(
        "-n", type=int, default=100, help="number of synthetic candles (default 100)"
    )
    args = parser.parse_args()

    if args.csv:
        candles = _from_csv(args.csv)
    elif args.json:
        candles = _from_json(args.json)
    else:
        candles = _synthetic(args.n)

    indicators = compute_indicators(
        candles["close"], candles["high"], candles["low"], candles["volume"]
    )

    n = len(candles["close"])
    print(f"Candles in window: {n}")
    print(f"Latest close:      {candles['close'][-1] if n else None}")
    print("Indicators (latest candle):")
    width = max(len(k) for k in indicators)
    for key, value in indicators.items():
        if value is None:
            shown = "null"
        elif isinstance(value, float):
            shown = f"{value:.6f}"
        else:
            shown = str(value)
        print(f"  {key:<{width}}  {shown}")


if __name__ == "__main__":
    main()
