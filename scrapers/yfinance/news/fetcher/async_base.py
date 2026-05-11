"""
Async base class for news fetchers.

All async market-specific news fetchers should inherit from AsyncBaseNewsFetcher.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar, List, Optional

from ..base import Guidance, Market, NewsFetchResult, NewsItem


class AsyncBaseNewsFetcher(ABC):
    """Abstract base class for async market-specific news fetchers."""

    market: ClassVar[Market]

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this data source."""
        pass

    @abstractmethod
    async def fetch_news(
        self,
        ticker: str,
        days: int = 30,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[NewsItem]:
        """
        Fetch news for a given ticker.

        Args:
            ticker: Stock ticker symbol
            days: Number of days to look back (default 30)
            start_date: Explicit start date (overrides days)
            end_date: Explicit end date (defaults to now)

        Returns:
            List of NewsItem objects
        """
        pass

    @abstractmethod
    async def fetch_guidance(self, ticker: str) -> List[Guidance]:
        """
        Fetch company guidance and analyst expectations.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of Guidance objects (may be empty if not available)
        """
        pass

    async def fetch_all(
        self,
        ticker: str,
        days: int = 30,
        include_guidance: bool = True,
    ) -> NewsFetchResult:
        """
        Fetch both news and guidance for a ticker.

        Args:
            ticker: Stock ticker symbol
            days: Number of days of news to fetch
            include_guidance: Whether to fetch guidance data

        Returns:
            NewsFetchResult with all fetched data
        """
        errors = []
        news = []
        guidance = []

        try:
            news = await self.fetch_news(ticker, days=days)
        except Exception as e:
            errors.append(f"Failed to fetch news: {str(e)}")

        if include_guidance:
            try:
                guidance = await self.fetch_guidance(ticker)
            except Exception as e:
                errors.append(f"Failed to fetch guidance: {str(e)}")

        return NewsFetchResult(
            success=len(errors) == 0 or len(news) > 0,
            ticker=ticker,
            market=self.market,
            source=self.source_name,
            news=news,
            guidance=guidance,
            errors=errors,
        )
