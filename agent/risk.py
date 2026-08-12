"""
Pure risk/sizing math - no I/O, no Alpaca/Kafka dependency, so this is the
easiest part of the agent to unit test in isolation.

Implements the numeric side of agent/spec.md's "Rules for risk management":
  - risk at most RISK_PER_TRADE_PCT of equity per position
  - never let a single position's market value exceed MAX_POSITION_SIZE_PCT of equity
  - never push total exposure above MAX_PORTFOLIO_UTILIZATION_PCT of equity
  - daily circuit breaker at DAILY_CIRCUIT_BREAKER_PCT
  - liquidity floor of MIN_DAILY_DOLLAR_VOLUME_USD
"""
import math
from typing import Optional


def daily_dollar_volume_usd(volume: Optional[float], close: Optional[float]) -> float:
    """Dollar volume for the current trading day. `volume` is already a
    running daily aggregate (not a single 15-minute bar), so this is just
    volume * close - no extrapolation needed."""
    if not volume or not close or volume <= 0 or close <= 0:
        return 0.0
    return volume * close


def passes_liquidity_floor(daily_dollar_volume_usd: float, floor_usd: float) -> bool:
    return daily_dollar_volume_usd >= floor_usd


def upside_pct(exit_price: Optional[float], close: Optional[float], side: str = "long") -> float:
    """Favorable potential of a trade: how far price would have to move from
    close to exit_price in the profitable direction for `side` - up for a
    long, down for a short."""
    if not exit_price or not close or close <= 0:
        return 0.0
    if side == "short":
        return (close - exit_price) / close
    return (exit_price - close) / close


def is_circuit_breaker_tripped(daily_pnl_pct: float, threshold_pct: float) -> bool:
    return daily_pnl_pct >= threshold_pct


def is_portfolio_fully_booked(current_exposure_usd: float, equity: float, max_utilization_pct: float) -> bool:
    """True once total exposure has reached the portfolio utilization cap,
    i.e. there's no headroom left to size a new entry against `equity`."""
    return current_exposure_usd >= equity * max_utilization_pct


def position_risk_usd(
    qty: float, avg_entry_price: float, stop_price: Optional[float], side: str = "long"
) -> float:
    """Dollar risk currently resting on an existing holding: shares held
    times the distance from entry to the active stop, on the losing side for
    `side` (below entry for a long, above entry for a short). Used to make
    the risk_per_trade_pct cap apply per *position* (spec.md: "at most 2% of
    the total portfolio per position"), not per individual scale-in fill."""
    if not qty or not stop_price:
        return 0.0
    if side == "short":
        if stop_price <= avg_entry_price:
            return 0.0
        return qty * (stop_price - avg_entry_price)
    if stop_price >= avg_entry_price:
        return 0.0
    return qty * (avg_entry_price - stop_price)


def position_size(
    equity: float,
    close: float,
    stop_loss: Optional[float],
    risk_per_trade_pct: float,
    already_at_risk_usd: float = 0.0,
    side: str = "long",
) -> int:
    """Shares for an entry/scale-in, sized so the *combined* fill-to-stop
    cost of this order plus any risk already resting on the position (see
    position_risk_usd) stays within risk_per_trade_pct of equity. Returns 0
    if the risk is undefined (no stop, or the stop isn't on the losing side
    of the entry price for `side`) or if the position is already at/over its
    risk cap."""
    if not stop_loss:
        return 0
    if side == "short":
        if stop_loss <= close:
            return 0
        per_share_risk = stop_loss - close
    else:
        if stop_loss >= close:
            return 0
        per_share_risk = close - stop_loss
    risk_budget = max(0.0, equity * risk_per_trade_pct - already_at_risk_usd)
    return max(0, math.floor(risk_budget / per_share_risk))


def cap_by_position_size(
    shares: int,
    close: float,
    current_position_value_usd: float,
    equity: float,
    max_position_size_pct: float,
) -> int:
    """Clip `shares` so this symbol's post-trade market value doesn't exceed
    max_position_size_pct of equity, independent of the stop-loss-driven risk
    budget in position_size(). This bounds a single position's notional size
    even against a wide stop or a signal with no stop at all."""
    if shares <= 0 or close <= 0:
        return 0

    max_position_value_usd = equity * max_position_size_pct
    headroom_usd = max_position_value_usd - current_position_value_usd
    if headroom_usd <= 0:
        return 0

    capped_shares = math.floor(headroom_usd / close)
    return max(0, min(shares, capped_shares))


def cap_by_exposure(
    shares: int,
    close: float,
    current_exposure_usd: float,
    equity: float,
    max_utilization_pct: float,
    buying_power: float,
) -> int:
    """Clip `shares` so post-trade exposure stays within the portfolio
    utilization cap and within available buying power."""
    if shares <= 0 or close <= 0:
        return 0

    max_exposure_usd = equity * max_utilization_pct
    headroom_usd = max_exposure_usd - current_exposure_usd
    if headroom_usd <= 0:
        return 0

    headroom_usd = min(headroom_usd, buying_power)
    capped_shares = math.floor(headroom_usd / close)
    return max(0, min(shares, capped_shares))
