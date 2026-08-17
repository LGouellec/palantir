"""
Read-only diagnostic for position_review.sweep(): hits the real Alpaca
account (paper or live, whichever AlpacaTrading/credentials resolve to) to
fetch actual positions and run the exact same decision path runner.py's
sweep thread does, but with cfg.dry_run forced True so _execute() never
reaches trading.execute() - no orders are placed or modified.

Beyond just calling sweep() (which only logs when an action fires),
this prints the full trailing-stop arithmetic for every long position -
trigger check, trail_target, breakeven-jump vs gradual-ease branch, and the
"never loosens" guard - so a stop that looks stuck can be diagnosed even
when no Action comes out.

Usage:
    cd agent && python debug_trailing_stop.py
Respects the same env vars as the real agent (.env / ALPACA_CREDENTIALS_FILE
/ TRADING_LIVE / TRAILING_STOP_* etc.) - just export them first, or run via
`make` if the repo's Makefile loads .env for you.
"""
import dataclasses
import logging
import sys
from datetime import datetime, timezone

import position_review
from alpaca_trading import AlpacaTrading
from config import WorkerConfig
from credentials import resolve_credentials
from rules import Position

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("debug_trailing_stop")


def _describe_trailing_stop(symbol: str, position: Position, cfg) -> None:
    if position.side != "long":
        logger.info("%-6s side=%s -> trailing stop N/A (longs only)", symbol, position.side)
        return

    if position.current_price is None or position.stop_price is None:
        logger.info(
            "%-6s current_price=%s stop_price=%s -> trailing stop N/A "
            "(no resting stop order found; position may not have a bracket stop)",
            symbol,
            position.current_price,
            position.stop_price,
        )
        return

    logger.info(
        "%-6s entry=%.2f current=%.2f stop=%.2f take_profit=%s plpc=%.4f (trigger=%.4f)",
        symbol,
        position.avg_entry_price,
        position.current_price,
        position.stop_price,
        f"{position.take_profit_price:.2f}" if position.take_profit_price is not None else "None",
        position.unrealized_plpc,
        cfg.trailing_stop_trigger_pct,
    )

    if position.unrealized_plpc < cfg.trailing_stop_trigger_pct:
        gap = cfg.trailing_stop_trigger_pct - position.unrealized_plpc
        logger.info(
            "  -> not triggered yet: plpc %.4f < trigger %.4f (needs %.4f more)",
            position.unrealized_plpc,
            cfg.trailing_stop_trigger_pct,
            gap,
        )
        return

    trail_target = position.current_price * (1 - cfg.trailing_stop_trail_pct)

    if position.stop_price < position.avg_entry_price:
        desired_stop = max(position.avg_entry_price, trail_target)
        branch = "breakeven-jump (first lock-in)"
    else:
        desired_stop = position.stop_price + (trail_target - position.stop_price) * cfg.trailing_stop_step_pct
        branch = "gradual-ease"

    logger.info(
        "  -> triggered; branch=%s trail_target=%.2f desired_stop=%.2f",
        branch,
        trail_target,
        desired_stop,
    )

    if desired_stop <= position.stop_price:
        logger.info(
            "  -> SUPPRESSED: desired_stop %.2f <= current stop %.2f (never-loosens guard) - no ADJUST_STOPS",
            desired_stop,
            position.stop_price,
        )
    else:
        logger.info(
            "  -> WOULD ADJUST_STOPS: %.2f -> %.2f (+%.2f)",
            position.stop_price,
            desired_stop,
            desired_stop - position.stop_price,
        )


def main() -> int:
    cfg = WorkerConfig.from_env()
    if cfg.dry_run is False:
        logger.info("Overriding DRY_RUN=%s -> True for this diagnostic run (no orders will be placed)", cfg.dry_run)
    cfg = dataclasses.replace(cfg, dry_run=True)

    creds = resolve_credentials()
    trading = AlpacaTrading(creds.api_key, creds.api_secret, paper=not cfg.trading_live)

    logger.info(
        "🧪 Read-only sweep diagnostic | account=%s | trailing_stop(enabled=%s trigger=%.4f trail=%.4f step=%.4f) | "
        "stale_position(enabled=%s max_age_min=%.0f flat_band=%.4f)",
        "LIVE" if cfg.trading_live else "PAPER",
        cfg.trailing_stop_enabled,
        cfg.trailing_stop_trigger_pct,
        cfg.trailing_stop_trail_pct,
        cfg.trailing_stop_step_pct,
        cfg.stale_position_enabled,
        cfg.stale_position_max_age_minutes,
        cfg.stale_position_flat_band_pct,
    )

    positions = trading.list_positions_with_details()
    if not positions:
        logger.info("No open positions - nothing to review.")
        return 0

    now = datetime.now(timezone.utc)
    logger.info("--- Per-position trailing-stop arithmetic ---")
    for symbol, position in positions.items():
        _describe_trailing_stop(symbol, position, cfg)

    logger.info("--- Cross-check against the real decision path (review_position) ---")
    for symbol, position in positions.items():
        opened_at = trading.position_opened_at(symbol, position.side) if cfg.stale_position_enabled else None
        if opened_at is not None:
            age_minutes = (now - opened_at).total_seconds() / 60.0
            logger.info("%-6s opened_at=%s age_minutes=%.1f", symbol, opened_at, age_minutes)
        action = position_review.review_position(symbol, position, opened_at, now, cfg)
        logger.info("%-6s -> %s", symbol, action if action is not None else "NO_OP (no action)")

    logger.info("--- Calling the real sweep() entrypoint (dry_run=True, so no orders are sent) ---")
    position_review.sweep(trading, cfg)

    return 0


if __name__ == "__main__":
    sys.exit(main())
