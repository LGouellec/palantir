"""
Alpaca trading-API wrapper, built on alpaca-py's TradingClient.

Builds the plain AccountSnapshot/Position dataclasses that rules.py reasons
over, and executes the Action rules.py decides on. Bracket orders
(order_class=BRACKET) are used for every entry so the stop-loss/take-profit
protection lives on Alpaca's servers, not in this process's memory.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from alpaca.common.enums import Sort
from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    OrderClass,
    OrderSide,
    OrderStatus,
    PositionSide,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.models import Order
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
    ReplaceOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)
from pydantic import TypeAdapter

from rules import Action, AccountSnapshot, Position

logger = logging.getLogger(__name__)


def _match_bracket_legs(
    orders: List, position_side: str
) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[float]]:
    """Pick the resting stop-loss / take-profit legs out of `orders`: the
    ones on the side that *closes* a position of `position_side` (SELL for a
    long, BUY for a short) - one with a stop_price, one with a limit_price."""
    closing_side = OrderSide.BUY if position_side == "short" else OrderSide.SELL

    stop_id = stop_price = tp_id = tp_price = None
    for order in orders:
        if order.side != closing_side:
            continue
        if order.stop_price is not None:
            stop_id, stop_price = str(order.id), float(order.stop_price)
        elif order.limit_price is not None:
            tp_id, tp_price = str(order.id), float(order.limit_price)
    return stop_id, stop_price, tp_id, tp_price


class AlpacaTradingError(Exception):
    pass


class AlpacaTrading:
    def __init__(self, api_key: str, api_secret: str, paper: bool):
        self._client = TradingClient(api_key, api_secret, paper=paper)
        logger.info("🦙 Alpaca trading client ready (paper=%s)", paper)

    # ------------------------------------------------------------------ #
    # Snapshot: everything rules.decide() needs about the account.
    # ------------------------------------------------------------------ #
    def is_market_open(self) -> bool:
        return bool(self._client.get_clock().is_open)

    def build_snapshot(self, symbol: str) -> AccountSnapshot:
        account = self._client.get_account()
        equity = float(account.equity or 0)
        last_equity = float(account.last_equity or 0)
        buying_power = float(account.buying_power or 0)

        positions: Dict[str, Position] = {}
        total_exposure_usd = 0.0
        for p in self._client.get_all_positions():
            market_value = abs(float(p.market_value or 0))
            total_exposure_usd += market_value
            side = "short" if p.side == PositionSide.SHORT else "long"
            positions[p.symbol] = Position(
                qty=abs(float(p.qty)),
                avg_entry_price=float(p.avg_entry_price),
                market_value=market_value,
                side=side,
                unrealized_plpc=float(p.unrealized_plpc or 0),
                current_price=float(p.current_price) if p.current_price is not None else None,
            )

        if symbol in positions:
            pos = positions[symbol]
            stop_id, stop_price, tp_id, tp_price = self._open_bracket_legs(symbol, pos.side)
            positions[symbol] = Position(
                qty=pos.qty,
                avg_entry_price=pos.avg_entry_price,
                market_value=pos.market_value,
                side=pos.side,
                unrealized_plpc=pos.unrealized_plpc,
                current_price=pos.current_price,
                stop_order_id=stop_id,
                stop_price=stop_price,
                take_profit_order_id=tp_id,
                take_profit_price=tp_price,
            )

        return AccountSnapshot(
            equity=equity,
            last_equity=last_equity,
            buying_power=buying_power,
            total_exposure_usd=total_exposure_usd,
            positions=positions,
            market_open=self.is_market_open(),
        )

    def held_orders_for_symbols(self, symbols: List[str]) -> Dict[str, List[Order]]:
        """All status=held orders - a bracket's stop-loss/take-profit legs
        rest in this status once their entry fills, which is a distinct
        status from new/accepted and isn't matched by GetOrdersRequest's
        status=open/closed/all (its status field is a client-side enum
        restricted to those three - "held" isn't one of them, even though
        the API itself accepts it as a filter value). Goes around that by
        calling the underlying authenticated GET directly with a raw params
        dict instead of a typed GetOrdersRequest, then deserializing the
        response the same way TradingClient.get_orders() does internally.
        Grouped by symbol; empty dict if `symbols` is empty."""
        if not symbols:
            return {}

        response = self._client.get("/orders", {"status": "held", "symbols": ",".join(symbols), "limit": 500})
        orders = TypeAdapter(List[Order]).validate_python(response)

        grouped: Dict[str, List[Order]] = {}
        for order in orders:
            grouped.setdefault(order.symbol, []).append(order)
        return grouped

    def open_orders_for_symbols(self, symbols: List[str]) -> Dict[str, List[Order]]:
        """All status=open orders, grouped by symbol - a bracket's
        take-profit (limit) leg genuinely rests on the book once its entry
        fills, so it shows up here, unlike the stop-loss leg (a conditional
        order Alpaca monitors rather than rests, sitting in status=held -
        see held_orders_for_symbols) which status=open does not match."""
        if not symbols:
            return {}

        orders = self._client.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=symbols, nested=False, limit=500)
        )
        grouped: Dict[str, List[Order]] = {}
        for order in orders:
            grouped.setdefault(order.symbol, []).append(order)
        return grouped

    def resting_bracket_orders_for_symbols(self, symbols: List[str]) -> Dict[str, List[Order]]:
        """Resting bracket legs for `symbols`, merged from the two queries
        above since a bracket's stop-loss and take-profit legs sit in
        different statuses (held vs. open) and neither query alone sees
        both."""
        held = self.held_orders_for_symbols(symbols)
        open_orders = self.open_orders_for_symbols(symbols)
        return {symbol: held.get(symbol, []) + open_orders.get(symbol, []) for symbol in symbols}

    def _open_bracket_legs(
        self, symbol: str, position_side: str = "long"
    ) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[float]]:
        """Find the resting stop-loss / take-profit legs protecting a
        position: the resting orders for this symbol on the side that
        *closes* it (SELL for a long, BUY for a short) - one with a
        stop_price, one with a limit_price."""
        orders = self.resting_bracket_orders_for_symbols([symbol]).get(symbol, [])
        return _match_bracket_legs(orders, position_side)

    def list_positions_with_details(self) -> Dict[str, Position]:
        """Full positions snapshot for position_review.py's periodic sweep:
        every held position, including current_price and resting bracket
        legs, fetched with one positions call + one open-orders call (rather
        than build_snapshot()'s per-symbol N+1 lookups, which are fine there
        since it only ever looks up the one symbol a signal is for)."""
        positions: Dict[str, Position] = {}
        for p in self._client.get_all_positions():
            side = "short" if p.side == PositionSide.SHORT else "long"
            positions[p.symbol] = Position(
                qty=abs(float(p.qty)),
                avg_entry_price=float(p.avg_entry_price),
                market_value=abs(float(p.market_value or 0)),
                side=side,
                unrealized_plpc=float(p.unrealized_plpc or 0),
                current_price=float(p.current_price) if p.current_price is not None else None,
            )
        if not positions:
            return positions

        orders_by_symbol = self.resting_bracket_orders_for_symbols(list(positions.keys()))

        for symbol, position in positions.items():
            stop_id, stop_price, tp_id, tp_price = _match_bracket_legs(
                orders_by_symbol.get(symbol, []), position.side
            )
            positions[symbol] = Position(
                qty=position.qty,
                avg_entry_price=position.avg_entry_price,
                market_value=position.market_value,
                side=position.side,
                unrealized_plpc=position.unrealized_plpc,
                current_price=position.current_price,
                stop_order_id=stop_id,
                stop_price=stop_price,
                take_profit_order_id=tp_id,
                take_profit_price=tp_price,
            )
        return positions

    def position_opened_at(self, symbol: str, side: str) -> Optional[datetime]:
        """Best-effort 'when did the currently-open position in `symbol`
        start' timestamp - Alpaca's Position has no entry-time field, so this
        is derived from fill history rather than a real one.

        Walks closed orders for `symbol` newest-first and returns the
        earliest *filled* order in the current unbroken run of opening-side
        fills (BUY for long, SELL for short), stopping as soon as a filled
        closing-side order is hit - that's the close that started the
        current run. Correct for this agent's normal intraday lifecycle
        (flat -> open -> flat within the same day); if the position was
        never fully closed since the queried history began, this may return
        the oldest fill in that history rather than the true open time.
        """
        opening_side = OrderSide.SELL if side == "short" else OrderSide.BUY
        closing_side = OrderSide.BUY if side == "short" else OrderSide.SELL

        orders = self._client.get_orders(
            GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                symbols=[symbol],
                direction=Sort.DESC,
                limit=100,
            )
        )

        earliest: Optional[datetime] = None
        for order in orders:
            if order.status != OrderStatus.FILLED or order.filled_at is None:
                continue
            if order.side == closing_side:
                break
            if order.side == opening_side:
                earliest = order.filled_at
        return earliest

    # ------------------------------------------------------------------ #
    # Execute a decided Action.
    # ------------------------------------------------------------------ #
    def execute(self, action: Action) -> None:
        if action.kind in ("ENTER_LONG", "SCALE_IN"):
            self._submit_bracket_order(action, side=OrderSide.BUY)
        elif action.kind in ("ENTER_SHORT", "SCALE_IN_SHORT"):
            self._submit_bracket_order(action, side=OrderSide.SELL)
        elif action.kind == "ADJUST_STOPS":
            self._adjust_stops(action)
        elif action.kind == "CLOSE_POSITION":
            self._close_position(action.symbol)
        elif action.kind == "NO_OP":
            pass
        else:
            raise AlpacaTradingError(f"unhandled action kind: {action.kind}")

    def _submit_bracket_order(self, action: Action, side: OrderSide) -> None:
        # A BRACKET entry's take-profit/stop-loss legs automatically close on
        # the opposite side of `side`, so this works unchanged for a short
        # entry (side=SELL): take_profit/stop_loss legs are submitted as BUY.
        order_data = MarketOrderRequest(
            symbol=action.symbol,
            qty=action.qty,
            side=side,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=action.take_profit),
            stop_loss=StopLossRequest(stop_price=action.stop_loss),
            client_order_id=action.client_order_id,
        )
        order = self._client.submit_order(order_data)
        logger.info(
            "✅ %s %s qty=%d stop=%.2f target=%.2f order_id=%s",
            action.kind,
            action.symbol,
            action.qty,
            action.stop_loss,
            action.take_profit,
            order.id,
        )

    def _adjust_stops(self, action: Action) -> None:
        try:
            position_side = (
                "short" if self._client.get_open_position(action.symbol).side == PositionSide.SHORT else "long"
            )
        except APIError:
            position_side = "long"

        stop_id, current_stop, tp_id, current_tp = self._open_bracket_legs(action.symbol, position_side)

        if stop_id and action.stop_loss is not None and action.stop_loss != current_stop:
            self._client.replace_order_by_id(stop_id, ReplaceOrderRequest(stop_price=action.stop_loss))
            logger.info("✅ ADJUST_STOPS %s stop_loss -> %.2f", action.symbol, action.stop_loss)

        if tp_id and action.take_profit is not None and action.take_profit != current_tp:
            self._client.replace_order_by_id(tp_id, ReplaceOrderRequest(limit_price=action.take_profit))
            logger.info("✅ ADJUST_STOPS %s take_profit -> %.2f", action.symbol, action.take_profit)

        if not stop_id and not tp_id:
            logger.warning(
                "⚠️  ADJUST_STOPS %s but no resting bracket legs found; nothing to amend",
                action.symbol,
            )

    def _close_position(self, symbol: str) -> None:
        # Cancel any resting bracket legs first so they don't race the close
        # (a resting stop/take-profit leg still reserves the shares it covers).
        for order in self.resting_bracket_orders_for_symbols([symbol]).get(symbol, []):
            self._client.cancel_order_by_id(order.id)

        closed = self._client.close_position(symbol)
        logger.info("✅ CLOSE_POSITION %s order_id=%s", symbol, closed.id)
