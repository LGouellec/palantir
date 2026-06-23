"""Local unit test for the TA UDF logic.

Targets `compute_indicators`, which has no PyFlink dependency, so the tests run
locally and in CI without a Flink runtime / JVM.

Run with:  uv run --group dev pytest   (or just: pytest)
"""

import math

from ta_udf.compute import INDICATOR_FIELDS, compute_indicators


def _ramp(n: int, start: float = 100.0, step: float = 1.0):
    """A simple increasing close series with synthetic high/low/volume."""
    close = [start + i * step for i in range(n)]
    high = [c + 0.5 for c in close]
    low = [c - 0.5 for c in close]
    volume = [1000.0 + i for i in range(n)]
    return close, high, low, volume


def test_full_window_populates_indicators():
    close, high, low, volume = _ramp(100)
    ind = compute_indicators(close, high, low, volume)

    # On a steadily rising series RSI should be high and SMA should trail close.
    assert ind["rsi"] is not None and ind["rsi"] > 70
    assert ind["sma"] is not None and ind["sma"] < close[-1]
    assert ind["ema"] is not None
    assert ind["macd"] is not None
    assert ind["bb_upper"] >= ind["bb_mid"] >= ind["bb_lower"]
    assert ind["atr"] is not None
    assert ind["obv"] is not None


def test_short_window_returns_nulls_without_error():
    # Fewer rows than any indicator length -> all None, no exception.
    close, high, low, volume = _ramp(5)
    ind = compute_indicators(close, high, low, volume)
    assert ind["rsi"] is None
    assert ind["macd"] is None
    assert ind["bb_mid"] is None


def test_empty_window_is_all_null():
    ind = compute_indicators([], [], [], [])
    assert set(ind) == set(INDICATOR_FIELDS)
    # Numeric indicators are None; the signal defaults to NEUTRAL / 0 strength.
    derived = ("signal", "signal_score", "signal_strength")
    numeric = {k: v for k, v in ind.items() if k not in derived}
    assert all(v is None for v in numeric.values())
    assert ind["signal"] == "NEUTRAL"
    assert ind["signal_score"] == 0
    assert ind["signal_strength"] == 0.0


def test_signal_strength_higher_for_cleaner_trend():
    # Same upward drift; the smoother series should score higher conviction.
    clean = [100.0 + i * 0.6 for i in range(120)]
    noisy = [c + (8.0 if i % 2 else -8.0) for i, c in enumerate(clean)]

    def strength(close):
        high = [c + 0.5 for c in close]
        low = [c - 0.5 for c in close]
        volume = [1000.0 + i for i in range(len(close))]
        return compute_indicators(close, high, low, volume)["signal_strength"]

    assert strength(clean) >= strength(noisy)


def test_handles_nan_safely():
    close, high, low, volume = _ramp(30)
    ind = compute_indicators(close, high, low, volume)
    assert ind["rsi"] is not None
    assert not math.isnan(ind["rsi"])


def test_uptrend_is_bullish():
    close, high, low, volume = _ramp(120, step=0.6)
    ind = compute_indicators(close, high, low, volume)
    assert ind["signal"] == "BULLISH"
    assert ind["signal_score"] > 0
    assert ind["di_plus"] > ind["di_minus"]


def test_downtrend_is_bearish():
    close, high, low, volume = _ramp(120, start=200.0, step=-0.6)
    ind = compute_indicators(close, high, low, volume)
    assert ind["signal"] == "BEARISH"
    assert ind["signal_score"] < 0
    assert ind["di_minus"] > ind["di_plus"]
