"""Turns raw orders into closed round-trip trades and win/loss stats.

Every entry in this bot is a bracket order (see agent/alpaca_trading.py), so
each filled entry has a stop-loss leg and a take-profit leg attached (OCO:
whichever fills first cancels the other). PnL per trade is entry fill vs.
whichever leg actually filled.

A stop-loss can be replaced (ratcheted up as a trade gains, or nudged by
ADJUST_STOPS) any number of times before it fills. Each replacement is a new
order id linked via `replaces`/`replaced_by`, and is never itself nested
under the parent bracket order, so the *original* leg id is only a starting
point: the actual outcome is found by walking `replaced_by` forward to the
final order in that lineage and reading its status/fill from there.

Portfolio "reorient" logic can also close a position manually: it cancels
both resting legs (and their replacement chains) and submits a plain market
order instead, so that trade never has a filled leg anywhere in the chain.
Those are matched separately, best-effort, against the next filled
opposite-side order for the same symbol.
"""
import pandas as pd

TRADE_COLUMNS = [
    "order_id", "symbol", "side", "qty", "entry_time", "entry_price",
    "exit_time", "exit_price", "exit_reason", "pnl", "pnl_pct",
]

# Leg statuses that definitively mean "this leg will never fill" (excludes
# "replaced" — a replaced order's replacement should already have been
# followed by _resolve_final, so seeing "replaced" here means the
# replacement isn't in our data yet, which is a reason to *not* conclude the
# leg is done rather than a reason to conclude it is).
DEAD_LEG_STATUSES = {"canceled", "expired", "rejected"}


def _build_trade(entry: pd.Series, exit_row: pd.Series, reason: str) -> dict:
    qty = float(entry["filled_qty"] or entry["qty"])
    entry_price = float(entry["filled_avg_price"])
    exit_price = float(exit_row["filled_avg_price"])
    sign = 1.0 if entry["side"] == "buy" else -1.0
    pnl = (exit_price - entry_price) * qty * sign
    pnl_pct = (exit_price - entry_price) / entry_price * sign * 100.0
    return {
        "order_id": entry["id"],
        "symbol": entry["symbol"],
        "side": entry["side"],
        "qty": qty,
        "entry_time": entry["filled_at"],
        "entry_price": entry_price,
        "exit_time": exit_row["filled_at"],
        "exit_price": exit_price,
        "exit_reason": reason,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


def _match_manual_closes(orders_df: pd.DataFrame, unresolved: list[pd.Series]) -> list[dict]:
    """Match entries with no filled leg lineage against a plain closing order.

    Scale-ins mean several entries can be resting on the same symbol at once,
    and a single reorient close typically flattens the *whole* position in
    one order. So this doesn't just pair 1-to-1: it accumulates consecutive
    (FIFO, same-side) unresolved entries for a symbol until their combined
    qty matches the next candidate close's qty, then splits that one fill
    across all of them at the same exit price/time. A close whose qty can't
    be built exactly from the entries ahead of it (e.g. a partial close) is
    left unmatched rather than guessed at.
    """
    if not unresolved:
        return []

    manual = orders_df[
        orders_df["parent_id"].isna()
        & (orders_df["order_class"] == "simple")
        & (orders_df["status"] == "filled")
    ]

    trades = []
    by_symbol: dict[str, list[pd.Series]] = {}
    for entry in unresolved:
        by_symbol.setdefault(entry["symbol"], []).append(entry)

    for symbol, entries in by_symbol.items():
        entries = sorted(entries, key=lambda e: e["filled_at"])
        candidates = manual[manual["symbol"] == symbol].sort_values("filled_at")

        i = 0
        for _, close in candidates.iterrows():
            if i >= len(entries):
                break
            close_qty = float(close["filled_qty"] or close["qty"])
            opposite_side = "sell" if entries[i]["side"] == "buy" else "buy"
            if close["side"] != opposite_side or close["filled_at"] <= entries[i]["filled_at"]:
                continue

            group, group_qty, j = [], 0.0, i
            while j < len(entries) and group_qty < close_qty - 1e-6:
                if entries[j]["side"] != entries[i]["side"]:
                    break
                group.append(entries[j])
                group_qty += float(entries[j]["filled_qty"] or entries[j]["qty"])
                j += 1

            if abs(group_qty - close_qty) < 1e-6:
                trades.extend(_build_trade(e, close, "manual_close") for e in group)
                i = j

    return trades


def _resolve_final(by_id: dict, order_id: str) -> pd.Series | None:
    """Follow `replaced_by` forward from `order_id` to the last order in its
    replacement lineage — the one whose status actually decided the trade."""
    row = by_id.get(order_id)
    seen: set[str] = set()
    while row is not None:
        nxt = row.get("replaced_by")
        if not nxt or nxt in seen or nxt not in by_id:
            return row
        seen.add(nxt)
        row = by_id[nxt]
    return row


def compute_trades(orders_df: pd.DataFrame) -> pd.DataFrame:
    if orders_df.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)

    parents = orders_df[orders_df["parent_id"].isna() & (orders_df["order_class"] == "bracket")]
    legs = orders_df[orders_df["parent_id"].notna()]
    by_id = {row["id"]: row for _, row in orders_df.iterrows()}

    trades = []
    unresolved = []

    for _, entry in parents.iterrows():
        if entry["status"] != "filled" or pd.isna(entry["filled_avg_price"]):
            continue

        entry_legs = legs[legs["parent_id"] == entry["id"]]
        stop_orig = entry_legs[entry_legs["stop_price"].notna()]
        tp_orig = entry_legs[entry_legs["stop_price"].isna() & entry_legs["limit_price"].notna()]

        stop_final = _resolve_final(by_id, stop_orig.iloc[0]["id"]) if not stop_orig.empty else None
        tp_final = _resolve_final(by_id, tp_orig.iloc[0]["id"]) if not tp_orig.empty else None

        exit_leg, reason = None, None
        if stop_final is not None and stop_final["status"] == "filled":
            exit_leg, reason = stop_final, "stop_loss"
        elif tp_final is not None and tp_final["status"] == "filled":
            exit_leg, reason = tp_final, "take_profit"

        if exit_leg is None:
            # Neither leg filled. If either is still resting (or missing
            # entirely — nesting was never established), the position might
            # genuinely still be open, so leave it alone; a symbol-level
            # "any open position" check isn't good enough here since the same
            # symbol can be re-entered after this exact entry already closed.
            # Only treat it as needing a manual-close match once both legs
            # are confirmed dead ends.
            still_pending = any(
                leg is not None and leg["status"] not in DEAD_LEG_STATUSES
                for leg in (stop_final, tp_final)
            )
            if not still_pending:
                unresolved.append(entry)
            continue

        trades.append(_build_trade(entry, exit_leg, reason))

    trades.extend(_match_manual_closes(orders_df, unresolved))

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
