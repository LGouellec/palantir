"""SQLite storage for Alpaca orders, used as a local cache so the dashboard
doesn't have to refetch full order history from Alpaca on every run."""
import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    client_order_id TEXT,
    symbol TEXT,
    side TEXT,
    order_class TEXT,
    type TEXT,
    qty REAL,
    filled_qty REAL,
    limit_price REAL,
    stop_price REAL,
    filled_avg_price REAL,
    status TEXT,
    submitted_at TEXT,
    filled_at TEXT,
    canceled_at TEXT,
    replaced_by TEXT,
    replaces TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_conn(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_orders(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Upsert order rows, keeping `parent_id` sticky once learned.

    A bracket leg is only ever seen nested under its parent's `legs` field
    at the moment the parent itself is fetched. Every other time we see that
    same leg id again (e.g. the plain "open orders" poll while it's still
    resting), it arrives as a flat, unparented row. A plain REPLACE would let
    that flat sighting wipe out the parent_id link we'd already learned, so
    parent_id is COALESCEd instead of overwritten.
    """
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(
        f"{c} = COALESCE(excluded.{c}, orders.{c})" if c == "parent_id" else f"{c} = excluded.{c}"
        for c in cols
        if c != "id"
    )
    sql = (
        f"INSERT INTO orders ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}"
    )
    conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    conn.commit()
    return len(rows)


def fetch_all_orders(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM orders", conn)
    for col in ("submitted_at", "filled_at", "canceled_at"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def get_sync_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_sync_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
