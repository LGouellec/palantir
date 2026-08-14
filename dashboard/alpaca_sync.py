"""Incremental Alpaca order sync into the local SQLite cache, plus a live
positions lookup for unrealized PnL (positions are never cached — they change
every tick, so they're always fetched fresh)."""
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.common.enums import Sort
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest

from db import get_sync_state, set_sync_state, upsert_orders

PAGE_LIMIT = 500
WINDOW = timedelta(hours=1)


def build_client() -> TradingClient:
    api_key = os.environ["APCA_API_KEY_ID"]
    api_secret = os.environ["APCA_API_SECRET_KEY"]
    paper = os.getenv("APCA_PAPER", "true").lower() != "false"
    return TradingClient(api_key, api_secret, paper=paper)


def _val(x):
    """Render an enum/UUID/datetime field as a plain str for SQLite storage."""
    if x is None:
        return None
    if hasattr(x, "isoformat"):
        return x.isoformat()
    if hasattr(x, "value"):
        return x.value
    return str(x) if not isinstance(x, str) else x


def _num(x) -> float | None:
    return float(x) if x is not None else None


def flatten_order(order, parent_id: str | None = None) -> dict:
    return {
        "id": str(order.id),
        "parent_id": parent_id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": _val(order.side),
        "order_class": _val(order.order_class),
        "type": _val(order.type),
        "qty": _num(order.qty),
        "filled_qty": _num(order.filled_qty),
        "limit_price": _num(order.limit_price),
        "stop_price": _num(order.stop_price),
        "filled_avg_price": _num(order.filled_avg_price),
        "status": _val(order.status),
        "submitted_at": _val(order.submitted_at),
        "filled_at": _val(order.filled_at),
        "canceled_at": _val(order.canceled_at),
        "replaced_by": str(order.replaced_by) if order.replaced_by else None,
        "replaces": str(order.replaces) if order.replaces else None,
        "updated_at": _val(order.updated_at),
    }


def _flatten_batch(orders) -> list[dict]:
    rows = []
    for o in orders:
        rows.append(flatten_order(o))
        for leg in o.legs or []:
            rows.append(flatten_order(leg, parent_id=str(o.id)))
    return rows


def _sweep_window(client: TradingClient, start: datetime, end: datetime) -> list[dict]:
    """Fetch every order submitted in [start, end), paging within the window
    just in case it ever holds more than PAGE_LIMIT."""
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
        if not batch:
            break
        rows.extend(_flatten_batch(batch))
        if len(batch) < PAGE_LIMIT:
            break
        after = batch[-1].submitted_at
    return rows


def sync_orders(client: TradingClient, conn) -> int:
    """Refetch open orders in full (there are always few, and their status
    changes as legs fill/cancel), then sweep everything submitted since the
    last-seen cursor in fixed-size time windows up to now.

    Alpaca's account-wide, open-ended `status=ALL`/`CLOSED` order listing has
    been observed to silently drop orders that fall well inside its own
    covered time range (reproduced on a paper account: a symbol-scoped query
    found orders an unfiltered open-ended sweep over the same window missed
    entirely). Narrow time windows have proven reliable, so history is
    walked in fixed-size chunks (default 1 hour) instead of one big sweep.
    """
    rows = []

    open_orders = client.get_orders(
        GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True, limit=PAGE_LIMIT)
    )
    rows.extend(_flatten_batch(open_orders))

    cursor = get_sync_state(conn, "last_closed_submitted_at")
    window_start = datetime.fromisoformat(cursor) if cursor else client.get_account().created_at
    now = datetime.now(timezone.utc)

    while window_start < now:
        window_end = min(window_start + WINDOW, now)
        rows.extend(_sweep_window(client, window_start, window_end))
        window_start = window_end
        set_sync_state(conn, "last_closed_submitted_at", window_start.isoformat())

    n = upsert_orders(conn, rows)
    set_sync_state(conn, "last_synced_wallclock", datetime.now(timezone.utc).isoformat())
    return n


def fetch_positions_df(client: TradingClient) -> pd.DataFrame:
    positions = client.get_all_positions()
    rows = [
        {
            "symbol": p.symbol,
            "side": _val(p.side),
            "qty": _num(p.qty),
            "avg_entry_price": _num(p.avg_entry_price),
            "current_price": _num(p.current_price),
            "market_value": _num(p.market_value),
            "unrealized_pl": _num(p.unrealized_pl),
            "unrealized_plpc": (
                _num(p.unrealized_plpc) * 100 if p.unrealized_plpc is not None else None
            ),
        }
        for p in positions
    ]
    return pd.DataFrame(rows)


def fetch_equity(client: TradingClient) -> float:
    return _num(client.get_account().equity)


def fetch_starting_equity(client: TradingClient) -> float | None:
    """Alpaca's own basis for its all-time PnL calculation, rather than a
    hand-typed guess. `start` must be the account's actual creation time —
    passing an earlier date (assuming it'd just clamp to inception) instead
    breaks the calculation entirely and `base_value` comes back None."""
    created_at = client.get_account().created_at
    history = client.get_portfolio_history(
        GetPortfolioHistoryRequest(start=created_at, timeframe="1D")
    )
    return _num(history.base_value)
