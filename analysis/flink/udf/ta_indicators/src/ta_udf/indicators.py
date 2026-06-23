"""PyFlink scalar UDF wrapper around `compute_indicators`.

Confluent Cloud for Apache Flink only supports *scalar* Python UDFs, so we can
not stream rows in one at a time and keep state. Instead the caller aggregates
the trailing N candles into parallel `ARRAY<DOUBLE>` columns (see
`analysis/flink/statements/stock_candle_1m_ta_aggregate.sql`) and passes them in
on every row. This wrapper hands the arrays to `compute_indicators` and returns
the result as a `ROW`.

All indicator math lives in `compute.py`, which has no PyFlink dependency so it
can be tested and run locally without a Flink runtime.

Qualified name used in `CREATE FUNCTION`: ``ta_udf.indicators.ta_indicators``
"""

from __future__ import annotations

from typing import Optional, Sequence

from pyflink.common import Row
from pyflink.table.types import DataTypes
from pyflink.table.udf import udf

from ta_udf.compute import compute_indicators


def _f_ta_indicators(
    close: Sequence[Optional[float]],
    high: Sequence[Optional[float]],
    low: Sequence[Optional[float]],
    volume: Sequence[Optional[float]],
) -> Row:
    result = compute_indicators(close, high, low, volume)
    return Row(**result)


# Result is a structured ROW so a single scalar UDF can return every indicator.
_RESULT_TYPE = DataTypes.ROW(
    [
        DataTypes.FIELD("sma", DataTypes.DOUBLE()),
        DataTypes.FIELD("ema", DataTypes.DOUBLE()),
        DataTypes.FIELD("rsi", DataTypes.DOUBLE()),
        DataTypes.FIELD("macd", DataTypes.DOUBLE()),
        DataTypes.FIELD("macd_signal", DataTypes.DOUBLE()),
        DataTypes.FIELD("macd_hist", DataTypes.DOUBLE()),
        DataTypes.FIELD("bb_lower", DataTypes.DOUBLE()),
        DataTypes.FIELD("bb_mid", DataTypes.DOUBLE()),
        DataTypes.FIELD("bb_upper", DataTypes.DOUBLE()),
        DataTypes.FIELD("atr", DataTypes.DOUBLE()),
        DataTypes.FIELD("obv", DataTypes.DOUBLE()),
        DataTypes.FIELD("adx", DataTypes.DOUBLE()),
        DataTypes.FIELD("di_plus", DataTypes.DOUBLE()),
        DataTypes.FIELD("di_minus", DataTypes.DOUBLE()),
        DataTypes.FIELD("sharpe", DataTypes.DOUBLE()),
        DataTypes.FIELD("signal_score", DataTypes.INT()),
        DataTypes.FIELD("signal_strength", DataTypes.DOUBLE()),
        DataTypes.FIELD("signal", DataTypes.STRING()),
    ]
)

_INPUT_TYPES = [
    DataTypes.ARRAY(DataTypes.DOUBLE()),  # close (oldest -> newest)
    DataTypes.ARRAY(DataTypes.DOUBLE()),  # high
    DataTypes.ARRAY(DataTypes.DOUBLE()),  # low
    DataTypes.ARRAY(DataTypes.DOUBLE()),  # volume
]

# This is the object Flink loads: <package>.<module>.<variable>
ta_indicators = udf(
    _f_ta_indicators,
    input_types=_INPUT_TYPES,
    result_type=_RESULT_TYPE,
)
