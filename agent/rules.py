"""
Decision engine: turns one TradeSignal + a snapshot of the current Alpaca
account into a single Action, implementing agent/spec.md's "Rules of the
trading agent" and "Rules for risk management" tables exactly.

Deliberately takes plain dataclasses (Position/AccountSnapshot) rather than
alpaca-py SDK objects, so this module has no Alpaca/Kafka dependency and can
be unit tested with plain data. alpaca_trading.py is responsible for building
an AccountSnapshot from the real API.
"""
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import risk
from trade_signal import TradeSignal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Position:
    qty: float
    avg_entry_price: float
    market_value: float
    side: str = "long"  # "long" or "short"
    # Unrealized P&L as a fraction of cost basis, sign-correct for `side`
    # (positive means profitable) - used to pick the "worst position" when
    # reorienting the portfolio for a more profitable signal.
    unrealized_plpc: float = 0.0
    # Live market price - only populated by list_positions_with_details()
    # (position_review.py's sweep), not by build_snapshot()'s per-signal
    # path, which never needs it.
    current_price: Optional[float] = None
    # Currently resting bracket legs for this position, if any.
    stop_order_id: Optional[str] = None
    stop_price: Optional[float] = None
    take_profit_order_id: Optional[str] = None
    take_profit_price: Optional[float] = None


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    last_equity: float
    buying_power: float
    total_exposure_usd: float
    positions: Dict[str, Position]
    # Whether NYSE/NASDAQ is currently open (alpaca_trading.py populates this
    # from Alpaca's clock endpoint). Defaults to True so callers/tests that
    # don't care about market hours are unaffected.
    market_open: bool = True

    @property
    def daily_pnl_pct(self) -> float:
        if not self.last_equity:
            return 0.0
        return (self.equity - self.last_equity) / self.last_equity


# ---------------------------------------------------------------------------
# Action: what the runner should actually do about a signal.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Action:
    kind: str  # ENTER_LONG | SCALE_IN | ENTER_SHORT | SCALE_IN_SHORT | ADJUST_STOPS | CLOSE_POSITION | NO_OP
    symbol: str
    reason: str
    qty: int = 0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_order_id: Optional[str] = None
    # Set only on a portfolio-reorientation CLOSE_POSITION (see
    # _reorient_for_better_signal): the signal that couldn't be sized because
    # the portfolio was fully booked. The runner must pull a fresh
    # AccountSnapshot after executing this close and re-decide this signal
    # against it - the snapshot used to produce this Action is now stale for
    # that purpose (exposure/buying power no longer reflect the closed
    # position).
    follow_up_signal: Optional[TradeSignal] = None

    @classmethod
    def no_op(cls, symbol: str, reason: str) -> "Action":
        return cls(kind="NO_OP", symbol=symbol, reason=reason)


def decide(signal: TradeSignal, snapshot: AccountSnapshot, cfg) -> Action:
    position = snapshot.positions.get(signal.symbol)
    held_side = position.side if position is not None else None

    circuit_breaker_tripped = risk.is_circuit_breaker_tripped(
        snapshot.daily_pnl_pct, cfg.daily_circuit_breaker_pct
    )

    # Exits are risk-reducing: always allowed, even mid circuit-breaker.
    if signal.signal == "SELL" and held_side == "long":
        return Action(kind="CLOSE_POSITION", symbol=signal.symbol, reason="sell_signal")
    if signal.signal == "BUY" and held_side == "short":
        return Action(kind="CLOSE_POSITION", symbol=signal.symbol, reason="buy_signal_cover_short")

    if signal.signal == "SELL" and held_side is None and not cfg.short_selling_enabled:
        return Action.no_op(signal.symbol, "no_margin_short_not_supported")

    # New trades (entries and scale-ins) only happen while NYSE/NASDAQ is
    # open; a closed market still lets the protective-exit branches above
    # run, but everything below here is a new/added position.
    if not snapshot.market_open:
        return Action.no_op(signal.symbol, "market_closed")

    if circuit_breaker_tripped:
        return Action.no_op(signal.symbol, "circuit_breaker")

    if signal.signal == "SELL":
        if held_side == "short":
            return _scale_in_short(signal, snapshot, cfg, position)
        return _enter_short(signal, snapshot, cfg, current_exposure_usd=snapshot.total_exposure_usd)

    if signal.signal == "BUY":
        if held_side == "long":
            return _scale_in(signal, snapshot, cfg, position)
        return _enter_long(signal, snapshot, cfg, current_exposure_usd=snapshot.total_exposure_usd)

    if signal.signal == "HOLD":
        if held_side == "long":
            return _adjust_stops(signal, position)
        if held_side == "short":
            return _adjust_stops_short(signal, position)
        return _enter_on_hold(signal, snapshot, cfg)

    return Action.no_op(signal.symbol, f"unhandled_signal:{signal.signal}")


def _liquidity_ok(signal: TradeSignal, cfg) -> bool:
    daily_dollar_volume = risk.daily_dollar_volume_usd(signal.volume, signal.close)
    return risk.passes_liquidity_floor(daily_dollar_volume, cfg.min_daily_dollar_volume_usd)


def _max_utilization_pct_for(symbol: str, cfg) -> float:
    """Preferred symbols (cfg.preferred_symbols) get extra headroom above
    max_portfolio_utilization_pct, so a signal for one of them can still
    size a trade once the portfolio-wide cap has otherwise been reached."""
    if symbol in cfg.preferred_symbols:
        return cfg.max_portfolio_utilization_pct + cfg.preferred_symbol_extra_utilization_pct
    return cfg.max_portfolio_utilization_pct


def _size_entry(
    signal: TradeSignal,
    snapshot: AccountSnapshot,
    cfg,
    current_exposure_usd: float,
    position: Optional[Position] = None,
    side: str = "long",
) -> int:
    already_at_risk_usd = (
        risk.position_risk_usd(position.qty, position.avg_entry_price, position.stop_price, side=side)
        if position is not None
        else 0.0
    )
    shares = risk.position_size(
        equity=snapshot.equity,
        close=signal.close,
        stop_loss=signal.stop_loss,
        risk_per_trade_pct=cfg.risk_per_trade_pct,
        already_at_risk_usd=already_at_risk_usd,
        side=side,
    )
    shares = risk.cap_by_position_size(
        shares=shares,
        close=signal.close,
        current_position_value_usd=position.market_value if position is not None else 0.0,
        equity=snapshot.equity,
        max_position_size_pct=cfg.max_position_size_pct,
    )
    return risk.cap_by_exposure(
        shares=shares,
        close=signal.close,
        current_exposure_usd=current_exposure_usd,
        equity=snapshot.equity,
        max_utilization_pct=_max_utilization_pct_for(signal.symbol, cfg),
        buying_power=snapshot.buying_power,
    )


def _worst_position(positions: Dict[str, Position], exclude_symbol: str) -> Optional[Tuple[str, Position]]:
    """The held position with the lowest unrealized P&L, i.e. the one to
    give up first when the portfolio needs to make room."""
    candidates = [(symbol, position) for symbol, position in positions.items() if symbol != exclude_symbol]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1].unrealized_plpc)


def _reorient_for_better_signal(
    signal: TradeSignal, snapshot: AccountSnapshot, cfg, side: str = "long"
) -> Optional[Action]:
    """Spec: if the portfolio is already fully booked and this signal's
    potential PnL beats our worst open position's by a meaningful edge, sell
    that worst position to reorient the portfolio instead of leaving the
    more profitable signal on the table."""
    if not cfg.portfolio_reorient_enabled:
        return None
    if not risk.is_portfolio_fully_booked(
        snapshot.total_exposure_usd, snapshot.equity, _max_utilization_pct_for(signal.symbol, cfg)
    ):
        return None

    worst = _worst_position(snapshot.positions, exclude_symbol=signal.symbol)
    if worst is None:
        return None
    worst_symbol, worst_position = worst

    new_signal_upside_pct = risk.upside_pct(signal.exit_price, signal.close, side=side)
    if new_signal_upside_pct - worst_position.unrealized_plpc < cfg.reorient_min_edge_pct:
        return None

    return Action(
        kind="CLOSE_POSITION",
        symbol=worst_symbol,
        reason=f"reorient_worst_position_for_more_profitable_signal:{signal.symbol}",
        follow_up_signal=signal,
    )


def _zero_size_action(signal: TradeSignal, snapshot: AccountSnapshot, cfg, side: str = "long") -> Action:
    reorient = _reorient_for_better_signal(signal, snapshot, cfg, side=side)
    if reorient is not None:
        return reorient
    return Action.no_op(signal.symbol, "zero_size_after_risk_and_exposure_caps")


def _enter_long(signal: TradeSignal, snapshot: AccountSnapshot, cfg, current_exposure_usd: float) -> Action:
    if not _liquidity_ok(signal, cfg):
        return Action.no_op(signal.symbol, "illiquid")

    qty = _size_entry(signal, snapshot, cfg, current_exposure_usd)
    if qty < 1:
        return _zero_size_action(signal, snapshot, cfg, side="long")

    return Action(
        kind="ENTER_LONG",
        symbol=signal.symbol,
        reason="buy_signal_not_held",
        qty=qty,
        stop_loss=signal.stop_loss,
        take_profit=signal.exit_price,
        client_order_id=signal.client_order_id,
    )


def _scale_in(signal: TradeSignal, snapshot: AccountSnapshot, cfg, position: Position) -> Action:
    upside = risk.upside_pct(signal.exit_price, signal.close)
    if upside < cfg.scale_in_min_upside_pct:
        return Action.no_op(signal.symbol, "insufficient_upside_to_scale_in")

    qty = _size_entry(
        signal, snapshot, cfg, current_exposure_usd=snapshot.total_exposure_usd, position=position
    )
    if qty < 1:
        return _zero_size_action(signal, snapshot, cfg, side="long")

    return Action(
        kind="SCALE_IN",
        symbol=signal.symbol,
        reason="buy_signal_held_significant_upside",
        qty=qty,
        stop_loss=signal.stop_loss,
        take_profit=signal.exit_price,
        client_order_id=signal.client_order_id,
    )


def _enter_short(signal: TradeSignal, snapshot: AccountSnapshot, cfg, current_exposure_usd: float) -> Action:
    if not _liquidity_ok(signal, cfg):
        return Action.no_op(signal.symbol, "illiquid")

    qty = _size_entry(signal, snapshot, cfg, current_exposure_usd, side="short")
    if qty < 1:
        return _zero_size_action(signal, snapshot, cfg, side="short")

    return Action(
        kind="ENTER_SHORT",
        symbol=signal.symbol,
        reason="sell_signal_not_held_short_selling_enabled",
        qty=qty,
        stop_loss=signal.stop_loss,
        take_profit=signal.exit_price,
        client_order_id=signal.client_order_id,
    )


def _scale_in_short(signal: TradeSignal, snapshot: AccountSnapshot, cfg, position: Position) -> Action:
    downside = risk.upside_pct(signal.exit_price, signal.close, side="short")
    if downside < cfg.scale_in_min_upside_pct:
        return Action.no_op(signal.symbol, "insufficient_downside_to_scale_in")

    qty = _size_entry(
        signal,
        snapshot,
        cfg,
        current_exposure_usd=snapshot.total_exposure_usd,
        position=position,
        side="short",
    )
    if qty < 1:
        return _zero_size_action(signal, snapshot, cfg, side="short")

    return Action(
        kind="SCALE_IN_SHORT",
        symbol=signal.symbol,
        reason="sell_signal_held_short_significant_downside",
        qty=qty,
        stop_loss=signal.stop_loss,
        take_profit=signal.exit_price,
        client_order_id=signal.client_order_id,
    )


def _adjust_stops(signal: TradeSignal, position: Position) -> Action:
    new_stop = signal.stop_loss
    new_take_profit = signal.exit_price

    tighter_stop = (
        new_stop is not None
        and (position.stop_price is None or new_stop > position.stop_price)
    )
    better_target = (
        new_take_profit is not None
        and (position.take_profit_price is None or new_take_profit > position.take_profit_price)
    )

    if not tighter_stop and not better_target:
        return Action.no_op(signal.symbol, "hold_no_more_favorable_levels")

    return Action(
        kind="ADJUST_STOPS",
        symbol=signal.symbol,
        reason="hold_signal_more_favorable_levels",
        stop_loss=new_stop if tighter_stop else position.stop_price,
        take_profit=new_take_profit if better_target else position.take_profit_price,
    )


def _adjust_stops_short(signal: TradeSignal, position: Position) -> Action:
    """Mirror of _adjust_stops for a short: favorable movement is *down*, so
    a tighter stop and a better target are both lower than what's resting."""
    new_stop = signal.stop_loss
    new_take_profit = signal.exit_price

    tighter_stop = (
        new_stop is not None
        and (position.stop_price is None or new_stop < position.stop_price)
    )
    better_target = (
        new_take_profit is not None
        and (position.take_profit_price is None or new_take_profit < position.take_profit_price)
    )

    if not tighter_stop and not better_target:
        return Action.no_op(signal.symbol, "hold_no_more_favorable_levels")

    return Action(
        kind="ADJUST_STOPS",
        symbol=signal.symbol,
        reason="hold_signal_more_favorable_levels_short",
        stop_loss=new_stop if tighter_stop else position.stop_price,
        take_profit=new_take_profit if better_target else position.take_profit_price,
    )


def _enter_on_hold(signal: TradeSignal, snapshot: AccountSnapshot, cfg) -> Action:
    upside = risk.upside_pct(signal.exit_price, signal.close)
    if upside <= cfg.new_entry_min_upside_pct:
        return Action.no_op(signal.symbol, "hold_not_held_insufficient_upside")

    if not _liquidity_ok(signal, cfg):
        return Action.no_op(signal.symbol, "illiquid")

    qty = _size_entry(signal, snapshot, cfg, current_exposure_usd=snapshot.total_exposure_usd)
    if qty < 1:
        return _zero_size_action(signal, snapshot, cfg, side="long")

    return Action(
        kind="ENTER_LONG",
        symbol=signal.symbol,
        reason="hold_signal_not_held_significant_upside",
        qty=qty,
        stop_loss=signal.stop_loss,
        take_profit=signal.exit_price,
        client_order_id=signal.client_order_id,
    )
