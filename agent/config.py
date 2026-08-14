"""
Worker configuration, resolved from environment variables.

Mirrors the WorkerConfig pattern used by the other Python workers in this
repo (fetchers/alpaca/worker/config.py, fetchers/longbridge/worker/config.py).
"""
import os
from dataclasses import dataclass
from typing import List


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: List[str]) -> List[str]:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return [symbol.strip().upper() for symbol in val.split(",") if symbol.strip()]


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return float(val)


@dataclass
class WorkerConfig:
    # Kafka
    trade_signal_topic: str
    consumer_group_id: str
    kafka_bootstrap_servers: str
    kafka_config_path: str

    # Schema Registry (unset -> plain JSON, used for the local smoke test;
    # set -> Confluent wire-format decoding against a real registry)
    schema_registry_url: str
    schema_registry_api_key: str
    schema_registry_api_secret: str

    # Trading safety
    trading_live: bool
    dry_run: bool

    # Risk management (see agent/spec.md "Rules of the trading agent")
    risk_per_trade_pct: float
    max_position_size_pct: float
    max_portfolio_utilization_pct: float
    daily_circuit_breaker_pct: float
    min_daily_dollar_volume_usd: float
    new_entry_min_upside_pct: float
    scale_in_min_upside_pct: float

    # Short selling: disabled by default since it requires a margin account.
    # When enabled, a SELL signal with no existing position opens a short
    # instead of being a no-op.
    short_selling_enabled: bool

    # Preferred stocks are allowed to push total exposure past
    # max_portfolio_utilization_pct by this extra amount, on top of the
    # normal cap, when a signal comes in for one of them.
    preferred_symbols: List[str]
    preferred_symbol_extra_utilization_pct: float

    # Portfolio reorientation: when the portfolio is already fully booked
    # (see risk.is_portfolio_fully_booked) and a new signal's potential PnL
    # beats our worst open position's unrealized P&L by at least this edge,
    # close that worst position to make room instead of just no-op'ing the
    # more-profitable signal away.
    portfolio_reorient_enabled: bool
    reorient_min_edge_pct: float

    poll_timeout_s: float

    # Periodic position review (see position_review.py): runs on a timer in
    # a background thread, independent of incoming Kafka signals.
    position_sweep_interval_s: float

    # Rule 1: once a long's unrealized P&L clears trailing_stop_trigger_pct,
    # jump its stop straight to at least breakeven (first lock-in). From
    # then on, each sweep eases the stop trailing_stop_step_pct of the way
    # from where it last rested toward current_price * (1 - trailing_stop_trail_pct),
    # rather than jumping straight to that target - i.e. the new candidate
    # is always computed from the last resting stop, not from price alone.
    trailing_stop_enabled: bool
    trailing_stop_trigger_pct: float
    trailing_stop_trail_pct: float
    trailing_stop_step_pct: float

    # Rule 2: this is an intraday agent, so a position open at least
    # stale_position_max_age_minutes with unrealized P&L within
    # stale_position_flat_band_pct of flat is stuck capital - close it
    # instead of leaving it to tie up exposure/risk budget.
    stale_position_enabled: bool
    stale_position_max_age_minutes: float
    stale_position_flat_band_pct: float

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls(
            trade_signal_topic=os.environ.get("TRADE_SIGNAL_TOPIC", "stock_quotes.trade_signal"),
            consumer_group_id=os.environ.get("CONSUMER_GROUP_ID", "trading-agent"),
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            kafka_config_path=os.environ.get("KAFKA_CONFIG_PATH", ""),
            schema_registry_url=os.environ.get("SCHEMA_REGISTRY_URL", ""),
            schema_registry_api_key=os.environ.get("SCHEMA_REGISTRY_API_KEY", ""),
            schema_registry_api_secret=os.environ.get("SCHEMA_REGISTRY_API_SECRET", ""),
            trading_live=_env_bool("TRADING_LIVE", False),
            dry_run=_env_bool("DRY_RUN", False),
            risk_per_trade_pct=_env_float("RISK_PER_TRADE_PCT", 0.02),
            max_position_size_pct=_env_float("MAX_POSITION_SIZE_PCT", 0.02),
            max_portfolio_utilization_pct=_env_float("MAX_PORTFOLIO_UTILIZATION_PCT", 0.60),
            daily_circuit_breaker_pct=_env_float("DAILY_CIRCUIT_BREAKER_PCT", 0.10),
            min_daily_dollar_volume_usd=_env_float("MIN_DAILY_DOLLAR_VOLUME_USD", 5_000_000),
            new_entry_min_upside_pct=_env_float("NEW_ENTRY_MIN_UPSIDE_PCT", 0.03),
            scale_in_min_upside_pct=_env_float("SCALE_IN_MIN_UPSIDE_PCT", 0.05),
            short_selling_enabled=_env_bool("SHORT_SELLING_ENABLED", False),
            preferred_symbols=_env_list("PREFERRED_SYMBOLS", []),
            preferred_symbol_extra_utilization_pct=_env_float(
                "PREFERRED_SYMBOL_EXTRA_UTILIZATION_PCT", 0.10
            ),
            portfolio_reorient_enabled=_env_bool("PORTFOLIO_REORIENT_ENABLED", True),
            reorient_min_edge_pct=_env_float("REORIENT_MIN_EDGE_PCT", 0.05),
            poll_timeout_s=_env_float("POLL_TIMEOUT_S", 5.0),
            position_sweep_interval_s=_env_float("POSITION_SWEEP_INTERVAL_S", 300.0),
            trailing_stop_enabled=_env_bool("TRAILING_STOP_ENABLED", True),
            trailing_stop_trigger_pct=_env_float("TRAILING_STOP_TRIGGER_PCT", 0.05),
            trailing_stop_trail_pct=_env_float("TRAILING_STOP_TRAIL_PCT", 0.02),
            trailing_stop_step_pct=_env_float("TRAILING_STOP_STEP_PCT", 0.5),
            stale_position_enabled=_env_bool("STALE_POSITION_ENABLED", True),
            stale_position_max_age_minutes=_env_float("STALE_POSITION_MAX_AGE_MINUTES", 120.0),
            stale_position_flat_band_pct=_env_float("STALE_POSITION_FLAT_BAND_PCT", 0.005),
        )
