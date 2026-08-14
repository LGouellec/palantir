import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from alpaca_sync import (
    build_client,
    fetch_equity,
    fetch_positions_df,
    fetch_starting_equity,
    sync_orders,
)
from db import fetch_all_orders, get_conn, get_sync_state, init_db
from pnl import compute_stats, compute_trades

load_dotenv(Path(__file__).parent / ".env")

# --- palette (validated categorical/status colors, see dataviz skill) ---
GOOD = "#0ca30c"
CRITICAL = "#d03b3b"
BLUE = "#2a78d6"
MUTED = "#898781"
GRID = "#e1e0d9"

st.set_page_config(page_title="Alpaca Trading Dashboard", layout="wide")

DB_PATH = os.getenv("DASHBOARD_DB_PATH") or str(Path(__file__).parent / "data" / "orders.db")

conn = get_conn(DB_PATH)
init_db(conn)

try:
    client = build_client()
except KeyError:
    st.error(
        "Missing Alpaca credentials. Copy dashboard/.env.example to "
        "dashboard/.env and fill in APCA_API_KEY_ID / APCA_API_SECRET_KEY."
    )
    st.stop()

st.sidebar.header("Sync")
last_sync = get_sync_state(conn, "last_synced_wallclock")
st.sidebar.caption(f"Last synced: {last_sync or 'never'}")
if st.sidebar.button("🔄 Sync orders from Alpaca", use_container_width=True):
    with st.spinner("Fetching orders from Alpaca..."):
        n = sync_orders(client, conn)
    st.sidebar.success(f"Synced — {n} order rows updated.")
    st.rerun()

orders_df = fetch_all_orders(conn)

if orders_df.empty:
    st.title("📊 Alpaca Trading Dashboard")
    st.info("No orders cached yet. Click **Sync orders from Alpaca** in the sidebar to get started.")
    st.stop()

positions_df = fetch_positions_df(client)

trades_df = compute_trades(orders_df)
stats = compute_stats(trades_df)

st.title("📊 Alpaca Trading Dashboard")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Closed trades", stats["total_trades"])
col2.metric("Win rate", f"{stats['win_rate'] * 100:.1f}%")
col3.metric("Realized PnL", f"${stats['total_pnl']:.2f}")
col4.metric(
    "Profit factor",
    f"{stats['profit_factor']:.2f}" if stats["profit_factor"] is not None else "∞" if stats["wins"] else "—",
)
col5.metric("Avg win / avg loss", f"${stats['avg_win']:.2f} / ${stats['avg_loss']:.2f}")

starting_equity = fetch_starting_equity(client)
if starting_equity is not None:
    unrealized_total = positions_df["unrealized_pl"].sum() if not positions_df.empty else 0.0
    current_equity = fetch_equity(client)
    implied_pnl = current_equity - starting_equity
    reconstructed_pnl = stats["total_pnl"] + unrealized_total
    gap = implied_pnl - reconstructed_pnl
    with st.expander(
        f"Reconciliation — gap: ${gap:,.2f}"
        + (" ✅" if abs(gap) < 1.0 else " ⚠️ some closed trade may not be matched"),
        expanded=abs(gap) >= 1.0,
    ):
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("Starting equity", f"${starting_equity:,.2f}", help="Alpaca's own base_value, from portfolio history")
        rc2.metric("Current equity", f"${current_equity:,.2f}")
        rc3.metric("Implied all-time PnL", f"${implied_pnl:,.2f}", help="current equity − starting equity")
        rc4.metric(
            "Reconstructed PnL", f"${reconstructed_pnl:,.2f}",
            help="dashboard's realized PnL + unrealized PnL from current positions",
        )
        if abs(gap) >= 1.0:
            st.caption(
                "A nonzero gap here isn't necessarily a bug in this dashboard's matching logic. "
                "Alpaca's paper-account order-listing API has been observed, on investigation, to "
                "silently omit some real orders from its responses — reproduced in multiple different "
                "forms (an unfiltered account-wide query missing orders a symbol-scoped one found, and "
                "vice versa) — so the local order cache this reconciliation is built from can itself be "
                "incomplete. Re-syncing won't fix a gap caused by this; it reflects orders Alpaca's API "
                "didn't return to any query this dashboard has tried."
            )

st.divider()

st.subheader("Open positions — unrealized PnL")
if positions_df.empty:
    st.caption("No open positions.")
else:
    total_unrealized = positions_df["unrealized_pl"].sum()
    st.metric("Total unrealized PnL", f"${total_unrealized:.2f}")
    st.dataframe(
        positions_df.rename(columns={
            "symbol": "Symbol", "side": "Side", "qty": "Qty",
            "avg_entry_price": "Avg entry", "current_price": "Current",
            "market_value": "Market value", "unrealized_pl": "Unrealized PnL ($)",
            "unrealized_plpc": "Unrealized PnL (%)",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.divider()

if trades_df.empty:
    st.info("No closed trades yet — a stop-loss or take-profit hasn't triggered on any position.")
else:
    st.subheader("Cumulative realized PnL")
    cum_df = trades_df.copy()
    cum_df["cum_pnl"] = cum_df["pnl"].cumsum()
    fig = go.Figure()
    fig.add_hline(y=0, line_width=1, line_color=GRID)
    fig.add_trace(go.Scatter(
        x=cum_df["exit_time"], y=cum_df["cum_pnl"], mode="lines",
        line=dict(color=BLUE, width=2), name="Cumulative PnL",
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(
        height=320, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
        xaxis=dict(showgrid=False, linecolor=GRID),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False, title="PnL ($)"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("PnL per trade")
    colors = [GOOD if p >= 0 else CRITICAL for p in trades_df["pnl"]]
    fig2 = go.Figure(go.Bar(
        x=trades_df["exit_time"], y=trades_df["pnl"], marker_color=colors,
        customdata=trades_df[["symbol", "exit_reason"]],
        hovertemplate="%{customdata[0]} — %{customdata[1]}<br>$%{y:.2f}<extra></extra>",
    ))
    fig2.update_layout(
        height=280, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
        xaxis=dict(showgrid=False, linecolor=GRID),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor=GRID, title="PnL ($)"),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

    reason_counts = trades_df["exit_reason"].value_counts()
    rcol1, rcol2, rcol3 = st.columns(3)
    rcol1.metric("Take-profit exits", int(reason_counts.get("take_profit", 0)))
    rcol2.metric("Stop-loss exits", int(reason_counts.get("stop_loss", 0)))
    rcol3.metric("Manual-close exits", int(reason_counts.get("manual_close", 0)))

    st.subheader("Closed trades")
    display_df = trades_df.copy()
    display_df["entry_time"] = display_df["entry_time"].dt.strftime("%Y-%m-%d %H:%M")
    display_df["exit_time"] = display_df["exit_time"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(
        display_df.rename(columns={
            "symbol": "Symbol", "side": "Side", "qty": "Qty",
            "entry_time": "Entry time", "entry_price": "Entry price",
            "exit_time": "Exit time", "exit_price": "Exit price",
            "exit_reason": "Exit reason", "pnl": "PnL ($)", "pnl_pct": "PnL (%)",
        }).drop(columns=["order_id"]),
        use_container_width=True,
        hide_index=True,
    )
