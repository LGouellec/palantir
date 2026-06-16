"""
Fetch the universe of US equity tickers from Nasdaq Trader's public FTP.

Two pipe-delimited files are published daily:
  - nasdaqlisted.txt : all NASDAQ-listed securities
  - otherlisted.txt  : non-NASDAQ securities (NYSE, NYSE American, Arca, ...)

We normalise them into Longbridge symbols (``AAPL.US``), de-duplicate, and
return a deterministically sorted list so the shard -> ticker mapping is stable.
"""
import io
import logging
from ftplib import FTP
from typing import Iterable, List, Sequence, Set

logger = logging.getLogger("longbridge.operator.tickers")

NASDAQ_FTP_HOST = "ftp.nasdaqtrader.com"
NASDAQ_FTP_DIR = "SymbolDirectory"
NASDAQ_LISTED = "nasdaqlisted.txt"
OTHER_LISTED = "otherlisted.txt"

US_SUFFIX = ".US"

# Exchange codes used in otherlisted.txt
EXCHANGE_CODES = {
    "NYSE": "N",
    "NYSE_AMERICAN": "A",
    "NYSE_ARCA": "P",
    "BATS": "Z",
    "IEX": "V",
}


def _download(host: str, path: str, filename: str) -> str:
    buffer = io.BytesIO()
    ftp = FTP(host, timeout=60)
    try:
        ftp.login()  # anonymous
        ftp.cwd(path)
        ftp.retrbinary(f"RETR {filename}", buffer.write)
    finally:
        ftp.quit()
    return buffer.getvalue().decode("utf-8", errors="replace")


def _parse_pipe_file(content: str) -> List[dict]:
    """Parse a Nasdaq Trader pipe-delimited file into a list of row dicts.

    The first line is the header; the last line is a "File Creation Time" footer.
    """
    lines = [ln for ln in content.splitlines() if ln.strip()]
    if not lines:
        return []
    header = lines[0].split("|")
    rows = []
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        fields = line.split("|")
        if len(fields) != len(header):
            continue
        rows.append(dict(zip(header, fields)))
    return rows


def _clean_symbol(raw: str) -> str:
    return raw.strip().upper()


def _is_usable(symbol: str) -> bool:
    if not symbol:
        return False
    # Skip warrants/units/rights/preferreds encoded with $ or other markers,
    # and anything with whitespace. Class shares (BRK.A) keep their dot.
    if any(ch in symbol for ch in (" ", "$", "^")):
        return False
    return True


def _to_longbridge(symbol: str) -> str:
    return f"{symbol}{US_SUFFIX}"


def fetch_us_symbols(
    exchanges: Sequence[str] = ("NASDAQ", "NYSE"),
    include_etf: bool = True,
    host: str = NASDAQ_FTP_HOST,
) -> List[str]:
    """Return the sorted, de-duplicated list of Longbridge US symbols.

    `exchanges` accepts: NASDAQ, NYSE, NYSE_AMERICAN, NYSE_ARCA, BATS, IEX.
    """
    wanted = {e.upper() for e in exchanges}
    symbols: Set[str] = set()

    if "NASDAQ" in wanted:
        content = _download(host, NASDAQ_FTP_DIR, NASDAQ_LISTED)
        rows = _parse_pipe_file(content)
        symbols |= _collect(
            rows,
            symbol_key="Symbol",
            include_etf=include_etf,
            exchange_filter=None,
        )
        logger.info("Fetched NASDAQ: %d rows", len(rows))

    other_exchanges = {EXCHANGE_CODES[e] for e in wanted if e in EXCHANGE_CODES}
    if other_exchanges:
        content = _download(host, NASDAQ_FTP_DIR, OTHER_LISTED)
        rows = _parse_pipe_file(content)
        symbols |= _collect(
            rows,
            symbol_key="ACT Symbol",
            include_etf=include_etf,
            exchange_filter=other_exchanges,
        )
        logger.info("Fetched otherlisted: %d rows", len(rows))

    result = sorted(symbols)
    logger.info("Total US symbols after cleaning/dedup: %d", len(result))
    return result


def _collect(
    rows: Iterable[dict],
    symbol_key: str,
    include_etf: bool,
    exchange_filter: Set[str] = None,
) -> Set[str]:
    out: Set[str] = set()
    for row in rows:
        if row.get("Test Issue", "N").strip().upper() == "Y":
            continue
        if not include_etf and row.get("ETF", "N").strip().upper() == "Y":
            continue
        if exchange_filter is not None and row.get("Exchange", "").strip().upper() not in exchange_filter:
            continue
        symbol = _clean_symbol(row.get(symbol_key, ""))
        if _is_usable(symbol):
            out.add(_to_longbridge(symbol))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    syms = fetch_us_symbols()
    print(f"{len(syms)} symbols, first 10: {syms[:10]}")
