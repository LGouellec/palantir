"""Turns raw orders into closed round-trip trades and win/loss stats.

Matching is pure FIFO quantity reconciliation per symbol, treating every
order that actually executed shares as one lot of "shares in" (buy) or
"shares out" (sell) — the same model as export_filled_orders.py /
test.py's standalone reconciliation, which tracked closer to Alpaca's own
equity numbers than the bracket/leg-aware matching this replaced.

That earlier approach tried to reconstruct *why* each position closed by
walking bracket parent/child links and `replaces`/`replaced_by` chains, and
matched manual (reorient) closes as a separate special case. It kept
under-counting realized PnL because any order it couldn't place in that
structure (a stop/take-profit replacement chain it couldn't fully resolve
from cached data, a split fill it didn't expect) was dropped rather than
counted. Since P&L only cares about shares in vs. shares out, matching by
raw quantity sidesteps all of that: a buy lot and a sell lot of the same
symbol are matched smallest-qty-first regardless of which order or leg
produced them, splitting whichever side has quantity left over (handles a
single order's fill being split across multiple partial fills, e.g. a
reorient's market order partially filling, getting canceled, and the
remainder filling via a follow-up order).

Every order that actually executed some quantity counts as a lot even if
it was ultimately canceled (a partial fill is still real, executed
quantity), which is why the filter below is "filled OR (canceled with
filled_qty > 0)" rather than status == "filled".

Because entries can be a long (buy first, sell to close) or a short (sell
first, buy to close), "entry" vs "exit" for a matched pair is decided by
whichever side's lot has the earlier fill time, not by side alone.

`exit_reason` is inferred from the exit lot's own order fields, since a
specific filled order row is itself the leg that closed the position: a
`stop_price` means it's a stop-loss leg, a `limit_price` (with no stop
price) means take-profit, and neither means a plain manual/reorient close.
"""
from collections import deque

import pandas as pd

TRADE_COLUMNS = [
    "order_id", "symbol", "side", "qty", "entry_time", "entry_price",
    "exit_time", "exit_price", "exit_reason", "pnl", "pnl_pct",
]

EPS = 1e-6


def _classify_reason(order: pd.Series) -> str:
    if pd.notna(order.get("stop_price")):
        return "stop_loss"
    if pd.notna(order.get("limit_price")):
        return "take_profit"
    return "manual_close"


def _build_trade(order_id, symbol: str, side: str, qty: float,
                  entry_time, entry_price: float, exit_time, exit_price: float,
                  reason: str) -> dict:
    sign = 1.0 if side == "buy" else -1.0
    pnl = (exit_price - entry_price) * qty * sign
    pnl_pct = (exit_price - entry_price) / entry_price * sign * 100.0
    return {
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "entry_time": entry_time,
        "entry_price": entry_price,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": reason,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


def compute_trades(orders_df: pd.DataFrame) -> pd.DataFrame:
    if orders_df.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)

    filled = orders_df[
        (orders_df["status"] == "filled")
        | ((orders_df["status"] == "canceled") & (orders_df["filled_qty"] > 0))
    ]
    filled = filled[filled["filled_avg_price"].notna()].sort_values("filled_at")

    buys: dict[str, deque] = {}
    sells: dict[str, deque] = {}
    for _, row in filled.iterrows():
        lots = buys if row["side"] == "buy" else sells
        lots.setdefault(row["symbol"], deque()).append({
            "order_id": row["id"],
            "qty": float(row["filled_qty"]),
            "price": float(row["filled_avg_price"]),
            "at": row["filled_at"],
            "reason": _classify_reason(row),
        })

    trades = []
    for symbol in sorted(set(buys) | set(sells)):
        buy_lots = buys.get(symbol, deque())
        sell_lots = sells.get(symbol, deque())

        while buy_lots and sell_lots:
            buy_lot, sell_lot = buy_lots[0], sell_lots[0]
            matched_qty = min(buy_lot["qty"], sell_lot["qty"])

            # whichever lot filled first opened the position; the other closed it
            if buy_lot["at"] <= sell_lot["at"]:
                side, entry, exit_ = "buy", buy_lot, sell_lot
            else:
                side, entry, exit_ = "sell", sell_lot, buy_lot

            trades.append(_build_trade(
                entry["order_id"], symbol, side, matched_qty,
                entry["at"], entry["price"], exit_["at"], exit_["price"], exit_["reason"],
            ))

            buy_lot["qty"] -= matched_qty
            sell_lot["qty"] -= matched_qty
            if buy_lot["qty"] <= EPS:
                buy_lots.popleft()
            if sell_lot["qty"] <= EPS:
                sell_lots.popleft()

    trades_df = pd.DataFrame(trades, columns=TRADE_COLUMNS)
    if not trades_df.empty:
        trades_df = trades_df.sort_values("exit_time").reset_index(drop=True)
    return trades_df


def compute_stats(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return dict(
            total_trades=0, wins=0, losses=0, win_rate=0.0, total_pnl=0.0,
            avg_win=0.0, avg_loss=0.0, profit_factor=None,
        )

    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] < 0]
    gross_loss = -losses["pnl"].sum()

    return dict(
        total_trades=len(trades_df),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(trades_df),
        total_pnl=trades_df["pnl"].sum(),
        avg_win=wins["pnl"].mean() if not wins.empty else 0.0,
        avg_loss=losses["pnl"].mean() if not losses.empty else 0.0,
        profit_factor=(wins["pnl"].sum() / gross_loss) if gross_loss > 0 else None,
    )
