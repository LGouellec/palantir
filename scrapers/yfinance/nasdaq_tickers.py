"""
NASDAQ Ticker List Fetcher

Fetches the list of all NASDAQ-listed stocks from the official FTP server.
URL: ftp.nasdaqtrader.com

Files available:
- nasdaqlisted.txt - NASDAQ-listed stocks
- otherlisted.txt - NYSE, AMEX, and other exchanges

Reference: https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
"""
import asyncio
import logging
from ftplib import FTP
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
import os

logger = logging.getLogger(__name__)


class NASDAQTickerFetcher:
    """
    Fetches and caches NASDAQ ticker lists from the official FTP server.

    Features:
    - Downloads from ftp.nasdaqtrader.com
    - Parses both NASDAQ and other exchanges
    - Filters test symbols and preferred stocks
    - Caches results to avoid repeated downloads
    - Async-friendly using asyncio.to_thread()
    """

    FTP_HOST = "ftp.nasdaqtrader.com"
    NASDAQ_FILE = "/SymbolDirectory/nasdaqlisted.txt"
    OTHER_FILE = "/SymbolDirectory/otherlisted.txt"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cache_ttl_hours: int = 24,
        include_nasdaq: bool = True,
        include_nyse: bool = True,
        include_amex: bool = True,
        exclude_test_symbols: bool = True,
        include_etf: bool = False,
    ):
        """
        Initialize the NASDAQ ticker fetcher.

        Args:
            cache_dir: Directory to cache downloaded files (default: .nasdaq_cache)
            cache_ttl_hours: Cache validity in hours (default: 24)
            include_nasdaq: Include NASDAQ-listed stocks (default: True)
            include_nyse: Include NYSE-listed stocks (default: True)
            include_amex: Include AMEX-listed stocks (default: True)
            exclude_test_symbols: Exclude test symbols (default: True)
            include_etf: Include ETFs in the results (default: False)
        """
        self.cache_dir = cache_dir or ".nasdaq_cache"
        self.cache_ttl_hours = cache_ttl_hours
        self.include_nasdaq = include_nasdaq
        self.include_nyse = include_nyse
        self.include_amex = include_amex
        self.exclude_test_symbols = exclude_test_symbols
        self.include_etf = include_etf

        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

    async def fetch_all_tickers(self) -> List[str]:
        """
        Fetch all ticker symbols from NASDAQ FTP server.

        Returns:
            List of ticker symbols (e.g., ["AAPL", "GOOGL", "MSFT", ...])
        """
        logger.info("Fetching NASDAQ ticker list from FTP server...")

        tickers = set()

        # Fetch NASDAQ-listed stocks
        if self.include_nasdaq:
            nasdaq_tickers = await self._fetch_nasdaq_listed()
            tickers.update(nasdaq_tickers)
            logger.info(f"NASDAQ: {len(nasdaq_tickers)} tickers")

        # Fetch other exchanges (NYSE, AMEX, etc.)
        if self.include_nyse or self.include_amex:
            other_tickers = await self._fetch_other_listed()
            tickers.update(other_tickers)
            logger.info(f"Other exchanges: {len(other_tickers)} tickers")

        ticker_list = sorted(list(tickers))
        logger.info(f"Total: {len(ticker_list)} unique tickers")

        return ticker_list

    async def _fetch_nasdaq_listed(self) -> Set[str]:
        """Fetch NASDAQ-listed stocks."""
        cache_file = os.path.join(self.cache_dir, "nasdaqlisted.txt")

        # Check cache
        if self._is_cache_valid(cache_file):
            logger.debug("Using cached NASDAQ list")
            return await asyncio.to_thread(self._parse_nasdaq_file, cache_file)

        # Download from FTP
        logger.debug("Downloading NASDAQ list from FTP server")
        await asyncio.to_thread(self._download_file, self.NASDAQ_FILE, cache_file)
        return await asyncio.to_thread(self._parse_nasdaq_file, cache_file)

    async def _fetch_other_listed(self) -> Set[str]:
        """Fetch NYSE, AMEX, and other exchange stocks."""
        cache_file = os.path.join(self.cache_dir, "otherlisted.txt")

        # Check cache
        if self._is_cache_valid(cache_file):
            logger.debug("Using cached other exchanges list")
            return await asyncio.to_thread(self._parse_other_file, cache_file)

        # Download from FTP
        logger.debug("Downloading other exchanges list from FTP server")
        await asyncio.to_thread(self._download_file, self.OTHER_FILE, cache_file)
        return await asyncio.to_thread(self._parse_other_file, cache_file)

    def _download_file(self, remote_path: str, local_path: str) -> None:
        """Download file from FTP server."""
        try:
            with FTP(self.FTP_HOST) as ftp:
                ftp.login()  # Anonymous login

                with open(local_path, "wb") as f:
                    ftp.retrbinary(f"RETR {remote_path}", f.write)

        except Exception as e:
            raise RuntimeError(f"Failed to download {remote_path} from FTP: {e}")

    def _parse_nasdaq_file(self, file_path: str) -> Set[str]:
        """
        Parse nasdaqlisted.txt file.

        Format:
        Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
        """
        tickers = set()

        with open(file_path, "r") as f:
            lines = f.readlines()

        # Skip header and footer
        for line in lines[1:]:
            if line.startswith("File Creation Time"):
                break

            parts = line.strip().split("|")
            if len(parts) < 7:
                continue

            ticker = parts[0].strip()
            test_issue = parts[3].strip()
            is_etf = parts[6].strip()

            # Skip test symbols
            if self.exclude_test_symbols and test_issue == "Y":
                continue

            # Skip ETFs if not included
            if not self.include_etf and is_etf == "Y":
                continue

            # Skip symbols with special characters (preferred stocks, warrants, etc.)
            if self._is_valid_ticker(ticker):
                tickers.add(ticker)

        return tickers

    def _parse_other_file(self, file_path: str) -> Set[str]:
        """
        Parse otherlisted.txt file.

        Format:
        ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
        """
        tickers = set()

        with open(file_path, "r") as f:
            lines = f.readlines()

        # Skip header and footer
        for line in lines[1:]:
            if line.startswith("File Creation Time"):
                break

            parts = line.strip().split("|")
            if len(parts) < 7:
                continue

            ticker = parts[0].strip()
            exchange = parts[2].strip()
            is_etf = parts[4].strip()
            test_issue = parts[6].strip()

            # Skip test symbols
            if self.exclude_test_symbols and test_issue == "Y":
                continue

            # Skip ETFs if not included
            if not self.include_etf and is_etf == "Y":
                continue

            # Filter by exchange
            if exchange == "N" and not self.include_nyse:  # NYSE
                continue
            if exchange == "A" and not self.include_amex:  # AMEX
                continue

            # Skip symbols with special characters
            if self._is_valid_ticker(ticker):
                tickers.add(ticker)

        return tickers

    def _is_valid_ticker(self, ticker: str) -> bool:
        """
        Check if ticker is valid (not a preferred stock, warrant, etc.).

        Invalid patterns:
        - Contains $ (preferred stocks)
        - Contains ^ (warrants)
        - Contains . (class shares, usually)
        - Contains special characters
        """
        if not ticker:
            return False

        # Exclude symbols with special characters
        invalid_chars = ["$", "^", ".", "/", " "]
        for char in invalid_chars:
            if char in ticker:
                return False

        # Exclude very short or very long tickers
        if len(ticker) < 1 or len(ticker) > 5:
            return False

        return True

    def _is_cache_valid(self, cache_file: str) -> bool:
        """Check if cached file is still valid."""
        if not os.path.exists(cache_file):
            return False

        # Check file age
        file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
        age = datetime.now() - file_time

        return age < timedelta(hours=self.cache_ttl_hours)

    def clear_cache(self) -> None:
        """Clear the ticker cache."""
        for filename in ["nasdaqlisted.txt", "otherlisted.txt"]:
            cache_file = os.path.join(self.cache_dir, filename)
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logger.info(f"Removed cache: {filename}")


async def fetch_nasdaq_tickers(
    include_nasdaq: bool = True,
    include_nyse: bool = True,
    include_amex: bool = True,
    include_etf: bool = False,
) -> List[str]:
    """
    Convenience function to fetch NASDAQ ticker list.

    Args:
        include_nasdaq: Include NASDAQ-listed stocks
        include_nyse: Include NYSE-listed stocks
        include_amex: Include AMEX-listed stocks
        include_etf: Include ETFs in the results (default: False)

    Returns:
        List of ticker symbols

    Example:
        tickers = await fetch_nasdaq_tickers()
        print(f"Found {len(tickers)} stocks")
    """
    fetcher = NASDAQTickerFetcher(
        include_nasdaq=include_nasdaq,
        include_nyse=include_nyse,
        include_amex=include_amex,
        include_etf=include_etf,
    )
    return await fetcher.fetch_all_tickers()


def fetch_nasdaq_tickers_sync(
    include_nasdaq: bool = True,
    include_nyse: bool = True,
    include_amex: bool = True,
    include_etf: bool = False,
) -> List[str]:
    """
    Synchronous version of fetch_nasdaq_tickers.

    For use in non-async contexts.
    """
    return asyncio.run(fetch_nasdaq_tickers(
        include_nasdaq=include_nasdaq,
        include_nyse=include_nyse,
        include_amex=include_amex,
        include_etf=include_etf,
    ))
