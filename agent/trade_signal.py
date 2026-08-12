"""
TradeSignal: parses and validates one message from `stock_quotes.trade_signal`
(schema + example payload in agent/spec.md) into the fields the decision
engine (rules.py) actually needs.

Validation is deliberately strict: a signal that's missing a field required
for its own branch (e.g. a BUY with no stop_loss) is rejected rather than
guessed at, since a wrong guess here places a real order.
"""
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

VALID_SIGNALS = {"BUY", "HOLD", "SELL"}


class InvalidSignal(ValueError):
    pass


@dataclass(frozen=True)
class TradeSignal:
    symbol: str
    window_start: int
    window_end: int
    signal: str
    close: Optional[float]
    volume: Optional[float]
    stop_loss: Optional[float]
    exit_price: Optional[float]

    @classmethod
    def from_dict(cls, payload: dict) -> "TradeSignal":
        symbol = payload.get("symbol")
        window_start = payload.get("window_start")
        window_end = payload.get("window_end")
        signal = payload.get("signal")

        if not symbol or window_start is None or window_end is None:
            raise InvalidSignal(f"missing required key fields: {payload}")

        if signal not in VALID_SIGNALS:
            raise InvalidSignal(f"{symbol}: unrecognized signal {signal!r}")

        close = _as_float(payload.get("close"))
        stop_loss = _as_float(payload.get("stop_loss"))
        exit_price = _as_float(payload.get("exit_price"))
        volume = _as_float(payload.get("volume"))

        if close is None:
            raise InvalidSignal(f"{symbol}: missing close price, cannot size or gate a trade")

        # Any branch that can open or scale into a position needs both legs
        # of the bracket. HOLD-and-held only needs whichever leg improved,
        # but we still require both here as the decision engine reasons about
        # both at once - a signal that can't stand up a full bracket is
        # rejected rather than half-acted on.
        if signal in ("BUY", "HOLD") and (stop_loss is None or exit_price is None):
            raise InvalidSignal(
                f"{symbol}: {signal} signal missing stop_loss/exit_price, cannot size a bracket"
            )

        return cls(
            symbol=str(symbol),
            window_start=int(window_start),
            window_end=int(window_end),
            signal=str(signal),
            close=close,
            volume=volume,
            stop_loss=stop_loss,
            exit_price=exit_price,
        )

    @property
    def client_order_id(self) -> str:
        # Deterministic per (symbol, window, signal) so a redelivered Kafka
        # message that gets resubmitted is rejected by Alpaca as a duplicate
        # client_order_id instead of double-entering the same position.
        return f"{self.symbol}-{self.window_start}-{self.signal}"


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
