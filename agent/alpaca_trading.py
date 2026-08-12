"""
Alpaca trading-API wrapper, built on alpaca-py's TradingClient.

Builds the plain AccountSnapshot/Position dataclasses that rules.py reasons
over, and executes the Action rules.py decides on. Bracket orders
(order_class=BRACKET) are used for every entry so the stop-loss/take-profit
protection lives on Alpaca's servers, not in this process's memory.
"""
import logging
from typing import Dict, Optional, Tuple

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, PositionSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
    ReplaceOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from rules import Action, AccountSnapshot, Position

logger = logging.getLogger(__name__)


class AlpacaTradingError(Exception):
    pass


class AlpacaTrading:
    def __init__(self, api_key: str, api_secret: str, paper: bool):
        self._client = TradingClient(api_key, api_secret, paper=paper)
        logger.info("🦙 Alpaca trading client ready (paper=%s)", paper)

    # ------------------------------------------------------------------ #
    # Snapshot: everything rules.decide() needs about the account.
    # ------------------------------------------------------------------ #
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
        )

    def _open_bracket_legs(
        self, symbol: str, position_side: str = "long"
    ) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[float]]:
        """Find the resting stop-loss / take-profit legs protecting a
        position: the two open orders for this symbol on the side that
        *closes* it (SELL for a long, BUY for a short) - one with a
        stop_price, one with a limit_price."""
        orders = self._client.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
        )
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
        # (an open stop/take-profit leg still reserves the shares it covers).
        orders = self._client.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
        )
        for order in orders:
            self._client.cancel_order_by_id(order.id)

        closed = self._client.close_position(symbol)
        logger.info("✅ CLOSE_POSITION %s order_id=%s", symbol, closed.id)
