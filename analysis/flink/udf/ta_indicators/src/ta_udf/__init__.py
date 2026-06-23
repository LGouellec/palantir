"""Technical-analysis UDFs for Confluent Cloud for Apache Flink.

Note: we intentionally do NOT import ``indicators`` (the PyFlink wrapper) here.
That keeps ``ta_udf.compute`` importable without a Flink runtime for local
testing. Flink loads the UDF via its fully qualified name
``ta_udf.indicators.ta_indicators``.
"""
