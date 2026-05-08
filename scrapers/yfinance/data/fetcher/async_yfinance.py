"""
Async YFinance data fetcher.

Wraps synchronous yfinance calls with asyncio.to_thread() for concurrent execution.
"""
import asyncio
from typing import Optional

from .async_base import AsyncBaseFetcher
from .base import FetchResult, HistoryResult
from .yfinance import YFinanceFetcher


class AsyncYFinanceFetcher(AsyncBaseFetcher):
    """Async wrapper for YFinance data fetcher."""

    def __init__(self, proxy: Optional[str] = None) -> None:
        """
        Initialize async YFinance fetcher.

        Args:
            proxy: Optional proxy URL (http://host:port or http://user:pass@host:port)
        """
        self._sync_fetcher = YFinanceFetcher(proxy=proxy)
        self._proxy = proxy

    @property
    def source_name(self) -> str:
        return "yfinance"

    def set_proxy(self, proxy: Optional[str]) -> None:
        """
        Update the proxy for this fetcher.

        Args:
            proxy: Proxy URL or None to disable
        """
        self._proxy = proxy
        self._sync_fetcher = YFinanceFetcher(proxy=proxy)

    async def fetch_quote(self, ticker: str) -> FetchResult:
        """
        Fetch current quote data asynchronously.

        Args:
            ticker: Stock ticker symbol

        Returns:
            FetchResult with quote data
        """
        return await asyncio.to_thread(self._sync_fetcher.fetch_quote, ticker)

    async def fetch_fundamentals(self, ticker: str) -> FetchResult:
        """
        Fetch fundamental data asynchronously.

        Args:
            ticker: Stock ticker symbol

        Returns:
            FetchResult with fundamental data
        """
        return await asyncio.to_thread(self._sync_fetcher.fetch_fundamentals, ticker)

    async def fetch_all(self, ticker: str) -> FetchResult:
        """
        Fetch both quote and fundamental data asynchronously.

        Args:
            ticker: Stock ticker symbol

        Returns:
            FetchResult with combined data
        """
        return await asyncio.to_thread(self._sync_fetcher.fetch_all, ticker)

    async def fetch_history(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "5y",
        adjust: str = "qfq",
    ) -> HistoryResult:
        """
        Fetch historical price data asynchronously.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Period string (1y, 2y, 5y, 10y, max)
            adjust: Adjustment type (qfq, hfq, None)

        Returns:
            HistoryResult with price history DataFrame
        """
        return await asyncio.to_thread(
            self._sync_fetcher.fetch_history,
            ticker,
            start_date,
            end_date,
            period,
            adjust,
        )
