"""
Trading agent entrypoint.

  1. Resolve config (risk thresholds, Kafka, Schema Registry) and Alpaca
     credentials.
  2. Subscribe to `stock_quotes.trade_signal`.
  3. For each message: parse -> pull a fresh Alpaca account/positions
     snapshot -> decide an Action against agent/spec.md's rules -> execute it
     (or just log it, if DRY_RUN) -> mark the message processed.

Every decision is logged with the signal in and the action + reason out: this
is the audit trail for a system placing real orders.
"""
import logging
import signal
import sys
import threading

from alpaca_trading import AlpacaTrading
from config import WorkerConfig
from credentials import resolve_credentials
from kafka_consumer import TradeSignalConsumer
from rules import decide
from trade_signal import InvalidSignal, TradeSignal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("trading.agent")

_shutdown = threading.Event()


def _handle_signal(signum, _frame):
    logger.info("📨 Received signal %s; shutting down", signum)
    _shutdown.set()


def _process_message(msg, cfg: WorkerConfig, trading: AlpacaTrading) -> None:
    payload = msg.value()
    if payload is None:
        return

    try:
        trade_signal = TradeSignal.from_dict(payload)
    except InvalidSignal as exc:
        logger.warning("⚠️  Skipping invalid signal: %s", exc)
        return

    snapshot = trading.build_snapshot(trade_signal.symbol)
    action = decide(trade_signal, snapshot, cfg)
    _log_and_execute(trade_signal, action, cfg, trading)

    if action.kind == "CLOSE_POSITION" and action.follow_up_signal is not None:
        # This CLOSE_POSITION freed up exposure for action.follow_up_signal
        # (portfolio reorientation), not a plain SELL/BUY-cover exit. The
        # snapshot above is now stale for that signal - equity/exposure no
        # longer reflect the just-closed position - so pull a fresh one and
        # re-decide once before moving on, rather than dropping the
        # more-profitable signal on the floor until another one happens to
        # arrive for the same symbol.
        follow_up_signal = action.follow_up_signal
        logger.info(
            "🔁 Reoriented portfolio (closed %s); refreshing account state to retry %s",
            action.symbol,
            follow_up_signal.symbol,
        )
        refreshed_snapshot = trading.build_snapshot(follow_up_signal.symbol)
        follow_up_action = decide(follow_up_signal, refreshed_snapshot, cfg)
        _log_and_execute(follow_up_signal, follow_up_action, cfg, trading)


def _log_and_execute(trade_signal: TradeSignal, action, cfg: WorkerConfig, trading: AlpacaTrading) -> None:
    logger.info(
        "📊 %s signal=%s close=%s -> %s %s (%s)%s",
        trade_signal.symbol,
        trade_signal.signal,
        trade_signal.close,
        action.kind,
        action.symbol,
        action.reason,
        f" qty={action.qty}" if action.qty else "",
    )

    if cfg.dry_run:
        logger.info("🧪 DRY_RUN: not calling Alpaca for %s", action.kind)
        return

    try:
        trading.execute(action)
    except Exception:  # noqa: BLE001
        logger.exception("❌ Failed to execute %s for %s", action.kind, action.symbol)


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cfg = WorkerConfig.from_env()
    logger.info(
        "🚀 Trading agent starting (topic=%s, group=%s, paper=%s, dry_run=%s)",
        cfg.trade_signal_topic,
        cfg.consumer_group_id,
        not cfg.trading_live,
        cfg.dry_run,
    )

    creds = resolve_credentials()
    logger.info("🔑 Credentials resolved (%s)", creds.masked())

    trading = AlpacaTrading(creds.api_key, creds.api_secret, paper=not cfg.trading_live)
    consumer = TradeSignalConsumer(cfg)

    try:
        while not _shutdown.is_set():
            msg = consumer.poll(cfg.poll_timeout_s)
            if msg is None:
                continue
            _process_message(msg, cfg, trading)
            consumer.mark_processed(msg)
    finally:
        logger.info("🧹 Cleaning up")
        consumer.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
