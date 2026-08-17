"""
Periodic position review: two safety-net rules that run on a timer against
the live Alpaca account, independent of incoming Kafka signals (runner.py
runs sweep() from a background thread every cfg.position_sweep_interval_s).

Pure decision functions here take plain dataclasses (rules.Position) and
return an Optional[rules.Action], same split as rules.py/risk.py - no
Alpaca/Kafka dependency, easy to unit test with plain data. alpaca_trading.py
is responsible for building the Position/opened_at inputs from the real API
and for actually executing the resulting Action.

Rules:
  - Profit-lock trailing stop (longs only): once a position's unrealized P&L
    clears TRAILING_STOP_TRIGGER_PCT, jump its stop straight to at least
    breakeven. From then on, each sweep eases the stop TRAILING_STOP_STEP_PCT
    of the remaining distance from where it last rested toward
    current_price * (1 - TRAILING_STOP_TRAIL_PCT) - gradual, and anchored on
    the last resting stop rather than jumping straight to that target every
    time. Never loosens.
  - Stale/flat position close (longs and shorts): this is an intraday agent,
    so a position open at least STALE_POSITION_MAX_AGE_MINUTES with
    unrealized P&L within STALE_POSITION_FLAT_BAND_PCT of flat is stuck
    capital tying up exposure/risk budget a fresh signal could use instead -
    close it rather than let it sit.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from rules import Action, Position

logger = logging.getLogger(__name__)


def decide_trailing_stop(symbol: str, position: Position, cfg) -> Optional[Action]:
    if position.side != "long":
        return None
    if position.current_price is None or position.stop_price is None:
        return None
    if position.unrealized_plpc < cfg.trailing_stop_trigger_pct:
        return None

    trail_target = position.current_price * (1 - cfg.trailing_stop_trail_pct)

    if position.stop_price < position.avg_entry_price:
        # First lock-in since triggering: jump straight to at least
        # breakeven rather than easing in - the spec's "at least above the
        # entry price" is immediate, not gradual.
        desired_stop = max(position.avg_entry_price, trail_target)
    else:
        # Already ratcheted above breakeven by an earlier sweep: the
        # "gradually" ask - ease the stop trailing_stop_step_pct of the
        # remaining distance from where it last rested toward trail_target,
        # instead of jumping straight to trail_target on every sweep. The
        # new candidate is a function of the *last* stop_price, not of
        # current_price alone.
        desired_stop = position.stop_price + (trail_target - position.stop_price) * cfg.trailing_stop_step_pct

    desired_stop = round(desired_stop, 2)

    if desired_stop <= position.stop_price:
        return None

    return Action(
        kind="ADJUST_STOPS",
        symbol=symbol,
        reason="trailing_stop_lock_profit",
        stop_loss=desired_stop,
        take_profit=position.take_profit_price,
    )


def decide_stale_close(
    symbol: str, position: Position, opened_at: Optional[datetime], now: datetime, cfg
) -> Optional[Action]:
    if opened_at is None:
        return None

    age_minutes = (now - opened_at).total_seconds() / 60.0
    if age_minutes < cfg.stale_position_max_age_minutes:
        return None
    if abs(position.unrealized_plpc) > cfg.stale_position_flat_band_pct:
        return None

    return Action(kind="CLOSE_POSITION", symbol=symbol, reason="stale_flat_position_intraday_cleanup")


def review_position(
    symbol: str, position: Position, opened_at: Optional[datetime], now: datetime, cfg
) -> Optional[Action]:
    """A stale close preempts a stop adjustment - no point ratcheting a stop
    on a position that's about to be closed anyway."""
    if cfg.stale_position_enabled:
        stale_action = decide_stale_close(symbol, position, opened_at, now, cfg)
        if stale_action is not None:
            return stale_action

    if cfg.trailing_stop_enabled:
        trailing_action = decide_trailing_stop(symbol, position, cfg)
        if trailing_action is not None:
            return trailing_action

    return None


def sweep(trading, cfg) -> None:
    now = datetime.now(timezone.utc)
    positions = trading.list_positions_with_details()

    for symbol, position in positions.items():
        opened_at = trading.position_opened_at(symbol, position.side) if cfg.stale_position_enabled else None
        action = review_position(symbol, position, opened_at, now, cfg)
        if action is None:
            continue
        _execute(action, cfg, trading)


def _execute(action: Action, cfg, trading) -> None:
    logger.info(
        "🔍 sweep -> %s %s (%s)%s",
        action.kind,
        action.symbol,
        action.reason,
        f" stop={action.stop_loss:.2f}" if action.stop_loss is not None else "",
    )

    if cfg.dry_run:
        logger.info("🧪 DRY_RUN: not calling Alpaca for %s", action.kind)
        return

    try:
        trading.execute(action)
    except Exception:  # noqa: BLE001
        logger.exception("❌ Failed to execute %s for %s", action.kind, action.symbol)
