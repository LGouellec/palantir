"""
Async base classes for data fetchers.

All async fetchers should inherit from AsyncBaseFetcher.
"""
from abc import ABC, abstractmethod
from typing import Optional

from .base import FetchResult, HistoryResult


class AsyncBaseFetcher(ABC):
    """Abstract base class for async data fetchers."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this data source."""
        pass

    @abstractmethod
    async def fetch_quote(self, ticker: str) -> FetchResult:
        """
        Fetch current quote data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            FetchResult with quote data
        """
        pass

    @abstractmethod
    async def fetch_fundamentals(self, ticker: str) -> FetchResult:
        """
        Fetch fundamental data (financials, ratios, etc.) for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            FetchResult with fundamental data
        """
        pass

    @abstractmethod
    async def fetch_all(self, ticker: str) -> FetchResult:
        """
        Fetch both quote and fundamental data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            FetchResult with combined data
        """
        pass

    @abstractmethod
    async def fetch_history(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "5y",
        adjust: str = "qfq",
    ) -> HistoryResult:
        """
        Fetch historical price data for a ticker.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Period string (1y, 2y, 5y, 10y, max)
            adjust: Adjustment type (qfq, hfq, None)

        Returns:
            HistoryResult with price history DataFrame
        """
        pass
