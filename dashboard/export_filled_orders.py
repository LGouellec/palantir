"""Standalone diagnostic: fetch every filled Alpaca order and export it to
CSV, sorted by symbol then fill time, plus a second CSV of matched trades
using the exact same bracket/replacement-lineage logic as the dashboard
(pnl.py) — so this is a way to eyeball the dashboard's own numbers up close,
not an independent cross-check.

Usage:
    python export_filled_orders.py [output.csv]
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from alpaca.trading.client import TradingClient
import pandas as pd
from alpaca.common.enums import Sort
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from dotenv import load_dotenv

from alpaca_sync import _flatten_batch, build_client
from pnl import compute_stats, compute_trades

load_dotenv(Path(__file__).parent / ".env")

PAGE_LIMIT = 500


WINDOW = timedelta(hours=1)


def _sweep_window(client: TradingClient, start: datetime, end: datetime) -> list[dict]:
    """Fetch every order submitted in [start, end), paging within the window
    just in case it ever holds more than PAGE_LIMIT (shouldn't, for an hour
    of this bot's activity, but paging costs nothing extra when it doesn't)."""
    rows = []
    after = start
    while True:
        batch = client.get_orders(
            GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                nested=True,
                limit=PAGE_LIMIT,
                direction=Sort.ASC,
                after=after,
                until=end,
            )
        )

        if len(batch) >= PAGE_LIMIT:
            print(
                f"Warning: window {start.isoformat()}..{end.isoformat()} returned {len(batch)} orders, "
                "which is the page limit. Some orders may be missing from this window."
            )

        if not batch:
            break
        rows.extend(_flatten_batch(batch))
        if len(batch) < PAGE_LIMIT:
            break
        after = batch[-1].submitted_at
    return rows


def _merge(by_id: dict[str, dict], row: dict) -> None:
    """Keep parent_id sticky across merges, same rule as db.py's SQL upsert:
    a given order id can be seen both nested under its parent (parent_id
    set) and as a flat top-level entry (parent_id None) within the sweep, and
    a plain overwrite risks the flat sighting erasing an already-learned
    link depending on which one happens to be seen last."""
    existing = by_id.get(row["id"])
    if existing is not None and row.get("parent_id") is None and existing.get("parent_id") is not None:
        row = {**row, "parent_id": existing["parent_id"]}
    by_id[row["id"]] = row


def fetch_all_orders(client: TradingClient) -> list[dict]:
    """Alpaca's account-wide, open-ended `status=ALL` order listing has been
    observed to silently drop orders that fall well inside its own covered
    time range (reproduced on a paper account: a symbol-scoped query found
    orders an unfiltered sweep over the same window missed entirely). Narrow
    time windows appear reliable, so this walks the account's full history
    in fixed-size chunks (default 1 hour) from account creation to now,
    assuming no window ever holds more than PAGE_LIMIT orders (each window
    still pages defensively in case that assumption is wrong for a burst).
    """
    start = client.get_account().created_at
    now = datetime.now(timezone.utc)

    by_id: dict[str, dict] = {}
    window_start = start
    while window_start < now:
        window_end = min(window_start + WINDOW, now)
        for r in _sweep_window(client, window_start, window_end):
            _merge(by_id, r)
        window_start = window_end

    return list(by_id.values())


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "filled_orders.csv"

    client = build_client()
    rows = fetch_all_orders(client)

    df_all = pd.DataFrame(rows)  # fetch_all_orders already dedupes by id, parent_id sticky
    df_all["filled_at"] = pd.to_datetime(df_all["filled_at"], utc=True)
    df_all["submitted_at"] = pd.to_datetime(df_all["submitted_at"], utc=True)

    df_filled = df_all[df_all["status"] == "filled"].copy()
    df_filled["cost_op"] = df_filled["filled_qty"] * df_filled["filled_avg_price"] * df_filled["side"].map(
        {"buy": -1, "sell": 1}
    )
    df_filled = df_filled.sort_values(["symbol", "filled_at"])
    df_filled.to_csv(out_path, index=False)
    print(f"Wrote {len(df_filled)} filled orders to {out_path}")

    # Same bracket/replacement-lineage matching the dashboard uses (pnl.py),
    # not an independent FIFO reconstruction, so trade counts agree with the app.
    trades_df = compute_trades(df_all)

    trades_path = Path(out_path).with_name(Path(out_path).stem + "_trades.csv")
    trades_df.to_csv(trades_path, index=False)

    stats = compute_stats(trades_df)
    print(
        f"Wrote {len(trades_df)} trades to {trades_path} "
        f"(total pnl=${stats['total_pnl']:.2f}, wins={stats['wins']}/{stats['total_trades']}, "
        f"win_rate={stats['win_rate'] * 100:.1f}%)"
    )


if __name__ == "__main__":
    main()
