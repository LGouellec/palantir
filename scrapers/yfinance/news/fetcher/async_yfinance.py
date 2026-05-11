"""
Async US stock news fetcher using yfinance.

Fetches news and analyst data from Yahoo Finance asynchronously.
"""
import asyncio
from datetime import datetime
from typing import List, Optional

from .async_base import AsyncBaseNewsFetcher
from .yfinance import YFinanceNewsFetcher
from ..base import Guidance, Market, NewsItem


class AsyncYFinanceNewsFetcher(AsyncBaseNewsFetcher):
    """Async wrapper for YFinance news fetcher."""

    market = Market.US

    def __init__(self, proxy: Optional[str] = None) -> None:
        """
        Initialize async YFinance news fetcher.

        Args:
            proxy: Optional proxy URL (http://host:port or http://user:pass@host:port)
        """
        self._sync_fetcher = YFinanceNewsFetcher(proxy=proxy)
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
        self._sync_fetcher = YFinanceNewsFetcher(proxy=proxy)

    async def fetch_news(
        self,
        ticker: str,
        days: int = 30,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[NewsItem]:
        """
        Fetch news asynchronously.

        Args:
            ticker: Stock ticker symbol
            days: Number of days to look back
            start_date: Explicit start date
            end_date: Explicit end date

        Returns:
            List of NewsItem objects
        """
        return await asyncio.to_thread(
            self._sync_fetcher.fetch_news,
            ticker,
            days,
            start_date,
            end_date,
        )

    async def fetch_guidance(self, ticker: str) -> List[Guidance]:
        """
        Fetch company guidance and analyst expectations asynchronously.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of Guidance objects
        """
        return await asyncio.to_thread(self._sync_fetcher.fetch_guidance, ticker)
