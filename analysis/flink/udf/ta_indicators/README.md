# `ta_indicators` — technical-indicators UDF for Confluent Cloud Flink

A **scalar** Python UDF that computes technical indicators over a trailing
window of candles using
[`pandas-ta-classic`](https://github.com/xgboosted/pandas-ta-classic).

> ⚠️ Python UDFs on Confluent Cloud for Apache Flink are an **Early Access**
> feature: scalar functions only, **Python 3.11 only**, and exactly
> `apache-flink==2.0.0`. Don't use them for production workloads yet.

## Why arrays instead of a streaming aggregate?

Confluent Cloud only supports *scalar* Python UDFs — they receive one row at a
time and can't accumulate state. `pandas-ta` needs a whole *series* to compute
RSI/MACD/Bollinger/etc. So the SQL side does the windowing: it aggregates the
last 100 candles per symbol into `ARRAY<DOUBLE>` columns and passes those arrays
in on every row. The UDF rebuilds a small DataFrame and returns the indicator
values for the **most recent** candle as a `ROW`.

```
stock_quotes.candles_1m  ──►  ARRAY_AGG OVER (last 100 rows)  ──►  ta_indicators(arrays) ──►  ROW<rsi, macd, ...>
```

## Layout

```
ta_indicators/
├── pyproject.toml            # deps + Python 3.11 + apache-flink 2.0.0 pin
├── src/ta_udf/
│   ├── __init__.py
│   ├── compute.py            # pure indicator math (pandas only, no PyFlink)
│   └── indicators.py         # PyFlink UDF wrapper: ta_udf.indicators.ta_indicators
├── examples/local_run.py     # run the UDF locally on a set of candles
└── tests/test_indicators.py
```

All indicator math lives in `compute.py`, which depends only on `pandas` +
`pandas-ta-classic` — **no PyFlink, no JVM, no cluster**. `indicators.py` is a
thin PyFlink wrapper that Flink loads. This split is what makes local testing
cheap.

## Run the UDF locally (no Flink cluster)

`examples/local_run.py` calls the exact same `compute_indicators` the UDF uses,
so the output matches what Flink emits for the latest candle of the window.

```bash
cd analysis/flink/udf/ta_indicators

# Synthetic candles (a rising series of 100):
uv run python examples/local_run.py

# Your own candles from CSV (columns: close,high,low,volume):
uv run python examples/local_run.py --csv candles.csv

# ...or from JSON: {"close": [...], "high": [...], "low": [...], "volume": [...]}
uv run python examples/local_run.py --json candles.json
```

No `uv`? `pip install pandas pandas-ta-classic` then
`python examples/local_run.py`.

To call it from your own Python instead of the CLI:

```python
from ta_udf.compute import compute_indicators
print(compute_indicators(close, high, low, volume))  # -> {"rsi": ..., "macd": ..., ...}
```

## Test

```bash
cd analysis/flink/udf/ta_indicators
uv run --group dev pytest      # or just: pytest  (tests don't need PyFlink)
```

## Build the artifact

```bash
cd analysis/flink/udf/ta_indicators
uv build --sdist
# Confluent expects a .zip artifact; repackage the sdist tarball:
zip -FS -j dist/ta_udf-0.1.0.zip dist/ta_udf-0.1.0.tar.gz
```

## Upload & register

```bash
# 1. Upload the artifact (note the returned id, e.g. cfa-xxxxxxx)
confluent flink artifact create ta_udf \
  --artifact-file dist/ta_udf-0.1.0.zip \
  --cloud azure --region <region> --environment <env-id>

# 2. Register the function — paste the artifact id into
#    analysis/flink/statements/stock_candle_1m_indicators.sql
#    (CREATE FUNCTION ... USING JAR 'confluent-artifact://<id>')
#    then run that statement, followed by the INSERT.
```

SQL lives in `analysis/flink/statements/`:
- `stock_candle_1m_indicators.sql` — sink table DDL + `CREATE FUNCTION`.
- `stock_candle_1m_ta_aggregate.sql` — the windowed aggregation + UDF-call
  `INSERT` (run after the two statements above).

## Tuning indicators

Indicator lengths live at the top of `src/ta_udf/indicators.py` (`RSI_LENGTH`,
`MACD_*`, `BBANDS_LENGTH`, ...). Keep every length **≤** the number of periods
aggregated in SQL (`ROWS BETWEEN 99 PRECEDING AND CURRENT ROW` = 100 candles).
To add an indicator: compute it in `_f_ta_indicators`, add a `DataTypes.FIELD`
to `_RESULT_TYPE`, and a column to the sink table + `SELECT` in the SQL file.

## Caveat: `ARRAY_AGG` in an `OVER` window

The `INSERT` uses `ARRAY_AGG(...) OVER (... ROWS BETWEEN 99 PRECEDING ...)`. If
your Confluent Cloud Flink version rejects `ARRAY_AGG` as an `OVER` function,
build the trailing arrays in an upstream step instead (e.g. a `MATCH_RECOGNIZE`
that emits the last 100 closes, or a pre-aggregation job), then call the UDF the
same way. The UDF itself is agnostic to how the arrays are assembled.
