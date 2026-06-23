"""Pure technical-indicator computation — no PyFlink, no JVM.

This module deliberately depends only on `pandas` and `pandas-ta-classic` so the
indicator logic can be imported, unit-tested and run locally without a Flink
runtime. The PyFlink UDF wrapper lives in `indicators.py` and calls in here.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

import pandas as pd
import pandas_ta_classic as ta

# ---------------------------------------------------------------------------
# Indicator configuration. Tune the lengths here; they must stay <= the number
# of periods the SQL side aggregates (we recommend 100, see the SQL file).
# ---------------------------------------------------------------------------
RSI_LENGTH = 14
SMA_LENGTH = 20
EMA_LENGTH = 100
BBANDS_LENGTH = 20
ATR_LENGTH = 14
ADX_LENGTH = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9

# ---------------------------------------------------------------------------
# Bullish / bearish signal configuration.
#
# No single indicator is reliable on its own, so we score four dimensions
# (trend, trend strength+direction, momentum, volume) and sum weighted votes.
# Each vote is -1 (bearish) / 0 (neutral) / +1 (bullish), scaled by its weight.
# Tune the weights and threshold to your strategy / timeframe.
# ---------------------------------------------------------------------------
W_TREND_MA = 2      # SMA(fast) vs EMA(slow) trend filter
W_ADX_DMI = 2       # DI+ vs DI- direction, gated by ADX trend strength
W_MACD = 1          # MACD histogram sign (momentum)
W_MACD_CROSS = 1    # extra weight when the histogram flips sign (trigger)
W_RSI = 1           # RSI momentum bias
W_BBANDS = 1        # price vs Bollinger mid band
W_OBV = 1           # OBV slope (volume confirmation)

ADX_TREND_MIN = 20.0    # ADX below this = no real trend, DMI vote ignored
RSI_BULL = 55.0         # RSI above -> bullish bias
RSI_BEAR = 45.0         # RSI below -> bearish bias
SIGNAL_THRESHOLD = 3    # |score| >= this -> BULLISH / BEARISH, else NEUTRAL

# Max achievable |score|, used to turn the vote sum into a 0..1 consensus.
MAX_ABS_SCORE = (
    W_TREND_MA + W_ADX_DMI + W_MACD + W_MACD_CROSS + W_RSI + W_BBANDS + W_OBV
)

# Sharpe is used as a CONVICTION layer on top of the directional signal, not as
# a direction vote (its sign just echoes the trend). `signal_strength` (0..100)
# blends the vote consensus with a Sharpe factor: boosted when the (per-bar)
# Sharpe agrees with the signal direction, dampened when it disagrees.
SHARPE_SCALE = 0.10     # per-bar |Sharpe| mapped through tanh(|s|/scale); calibrate per asset/timeframe
SHARPE_BOOST = 0.50     # max +/- adjustment the Sharpe factor applies to strength

# Field order is the contract shared with the Flink ROW result type.
INDICATOR_FIELDS = (
    "sma",
    "ema",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_lower",
    "bb_mid",
    "bb_upper",
    "atr",
    "obv",
    "adx",
    "di_plus",
    "di_minus",
    "sharpe",
    "signal_score",
    "signal_strength",
    "signal",
)


def _last(series: Optional[pd.Series]) -> Optional[float]:
    """Return the final non-NaN-safe value of a pandas Series as a float."""
    if series is None or len(series) == 0:
        return None
    value = series.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _column(frame: Optional[pd.DataFrame], name: str) -> Optional[float]:
    """Pull the last value of a named column out of an indicator DataFrame."""
    if frame is None or name not in frame.columns:
        return None
    return _last(frame[name])


def _prev(series: Optional[pd.Series]) -> Optional[float]:
    """Return the second-to-last (previous bar) value of a Series, NaN-safe."""
    if series is None or len(series) < 2:
        return None
    value = series.iloc[-2]
    if pd.isna(value):
        return None
    return float(value)


def _vote(bullish: Optional[bool], weight: int) -> int:
    """Map a tri-state condition to a weighted vote: +w / -w / 0 (unknown)."""
    if bullish is None:
        return 0
    return weight if bullish else -weight


def _signal(score: int) -> str:
    if score >= SIGNAL_THRESHOLD:
        return "BULLISH"
    if score <= -SIGNAL_THRESHOLD:
        return "BEARISH"
    return "NEUTRAL"


def compute_indicators(
    close: Sequence[Optional[float]],
    high: Sequence[Optional[float]],
    low: Sequence[Optional[float]],
    volume: Sequence[Optional[float]],
) -> dict[str, object]:
    """Compute indicators + a bullish/bearish signal for the latest candle.

    Each argument is the ordered (oldest -> newest) sequence of the last N
    candle values for a single symbol. Arrays must be the same length. Returns
    a dict keyed by `INDICATOR_FIELDS`: numeric indicators are floats (or None
    when there is not enough history), `signal_score` is an int and `signal` is
    one of "BULLISH" / "BEARISH" / "NEUTRAL".
    """
    if not close:
        out: dict[str, object] = {field: None for field in INDICATOR_FIELDS}
        out["signal_score"] = 0
        out["signal_strength"] = 0.0
        out["signal"] = "NEUTRAL"
        return out

    frame = pd.DataFrame(
        {
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    ).astype("float64")

    n = len(frame)

    rsi = ta.rsi(frame["close"], length=RSI_LENGTH) if n > RSI_LENGTH else None
    sma = ta.sma(frame["close"], length=SMA_LENGTH) if n >= SMA_LENGTH else None
    ema = ta.ema(frame["close"], length=EMA_LENGTH) if n >= EMA_LENGTH else None
    bbands = ta.bbands(frame["close"], length=BBANDS_LENGTH) if n >= BBANDS_LENGTH else None
    atr = (
        ta.atr(frame["high"], frame["low"], frame["close"], length=ATR_LENGTH)
        if n > ATR_LENGTH
        else None
    )
    macd = (
        ta.macd(frame["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
        if n >= MACD_SLOW + MACD_SIGNAL
        else None
    )
    obv = ta.obv(frame["close"], frame["volume"]) if n >= 2 else None
    adx = (
        ta.adx(frame["high"], frame["low"], frame["close"], length=ADX_LENGTH)
        if n > 2 * ADX_LENGTH
        else None
    )

    macd_hist_series = macd[f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"] if macd is not None else None

    # Latest scalar values used both as outputs and for scoring.
    close_now = float(frame["close"].iloc[-1])
    sma_v = _last(sma)
    ema_v = _last(ema)
    rsi_v = _last(rsi)
    macd_hist_v = _last(macd_hist_series)
    macd_hist_prev = _prev(macd_hist_series)
    bb_mid_v = _column(bbands, f"BBM_{BBANDS_LENGTH}_2.0")
    obv_v = _last(obv)
    obv_prev = _prev(obv)
    adx_v = _column(adx, f"ADX_{ADX_LENGTH}")
    di_plus_v = _column(adx, f"DMP_{ADX_LENGTH}")
    di_minus_v = _column(adx, f"DMN_{ADX_LENGTH}")

    # --- Composite bullish/bearish score (weighted votes, see config above) ---
    score = 0
    # Trend: fast MA above slow MA.
    if sma_v is not None and ema_v is not None:
        score += _vote(sma_v > ema_v, W_TREND_MA)
    # Trend strength + direction: only vote when ADX confirms a real trend.
    if adx_v is not None and di_plus_v is not None and di_minus_v is not None:
        if adx_v >= ADX_TREND_MIN:
            score += _vote(di_plus_v > di_minus_v, W_ADX_DMI)
    # Momentum: MACD histogram sign, plus a trigger when it flips this bar.
    if macd_hist_v is not None:
        score += _vote(macd_hist_v > 0, W_MACD)
        if macd_hist_prev is not None and (macd_hist_v > 0) != (macd_hist_prev > 0):
            score += _vote(macd_hist_v > 0, W_MACD_CROSS)
    # Momentum: RSI bias (neutral in the 45-55 band so it won't fight a trend).
    if rsi_v is not None:
        if rsi_v > RSI_BULL:
            score += W_RSI
        elif rsi_v < RSI_BEAR:
            score -= W_RSI
    # Mean reversion: price relative to Bollinger mid band.
    if bb_mid_v is not None:
        score += _vote(close_now > bb_mid_v, W_BBANDS)
    # Volume confirmation: OBV rising vs the previous bar.
    if obv_v is not None and obv_prev is not None:
        score += _vote(obv_v > obv_prev, W_OBV)

    # --- Sharpe-based conviction -> signal_strength (0..100) ------------------
    # Per-bar Sharpe over the window: mean(return) / std(return), unannualized.
    returns = frame["close"].pct_change()
    sharpe_v: Optional[float] = None
    if returns.notna().sum() >= 2:
        mu = returns.mean()
        sd = returns.std()  # sample std (ddof=1)
        if sd is not None and sd > 0:
            sharpe_v = float(mu / sd)
        elif mu == 0:
            sharpe_v = 0.0

    consensus = min(abs(score) / MAX_ABS_SCORE, 1.0) if MAX_ABS_SCORE else 0.0
    sharpe_factor = 1.0
    if sharpe_v is not None and score != 0:
        conviction = math.tanh(abs(sharpe_v) / SHARPE_SCALE)  # 0..1
        aligned = (sharpe_v > 0) == (score > 0)
        sharpe_factor = 1.0 + SHARPE_BOOST * conviction if aligned else 1.0 - SHARPE_BOOST * conviction
    signal_strength = max(0.0, min(100.0, 100.0 * consensus * sharpe_factor))

    return {
        "sma": sma_v,
        "ema": ema_v,
        "rsi": rsi_v,
        "macd": _column(macd, f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"),
        "macd_signal": _column(macd, f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"),
        "macd_hist": macd_hist_v,
        "bb_lower": _column(bbands, f"BBL_{BBANDS_LENGTH}_2.0"),
        "bb_mid": bb_mid_v,
        "bb_upper": _column(bbands, f"BBU_{BBANDS_LENGTH}_2.0"),
        "atr": _last(atr),
        "obv": obv_v,
        "adx": adx_v,
        "di_plus": di_plus_v,
        "di_minus": di_minus_v,
        "sharpe": sharpe_v,
        "signal_score": score,
        "signal_strength": round(signal_strength, 1),
        "signal": _signal(score),
    }
