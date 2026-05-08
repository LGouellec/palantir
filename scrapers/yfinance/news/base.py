"""
News data models for stock market news and analyst guidance.

Defines common data structures used across all news fetchers.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class Market(str, Enum):
    """Market identifier."""
    US = "US"
    CN = "CN"


class AnalystRating(str, Enum):
    """Analyst recommendation rating."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class Sentiment(str, Enum):
    """News sentiment classification."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class NewsCategory(str, Enum):
    """News article category."""
    EARNINGS = "earnings"
    DIVIDEND = "dividend"
    GUIDANCE = "guidance"
    INDUSTRY = "industry"
    MACRO = "macro"
    GOVERNANCE = "governance"
    COMPANY = "company"
    UNKNOWN = "unknown"


@dataclass
class NewsItem:
    """Individual news article about a stock."""
    ticker: str
    title: str
    content: str
    source: str
    publish_date: datetime
    market: Market
    url: str

    # Sentiment analysis fields (optional, filled by analyzer)
    sentiment: Optional[Sentiment] = None
    confidence: float = 0.0
    impact_score: float = 0.0
    category: Optional[NewsCategory] = None
    keywords: List[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def is_positive(self) -> bool:
        """Check if sentiment is positive."""
        return self.sentiment == Sentiment.POSITIVE if self.sentiment else False

    @property
    def is_negative(self) -> bool:
        """Check if sentiment is negative."""
        return self.sentiment == Sentiment.NEGATIVE if self.sentiment else False

    @property
    def is_neutral(self) -> bool:
        """Check if sentiment is neutral."""
        return self.sentiment == Sentiment.NEUTRAL if self.sentiment else True


@dataclass
class Guidance:
    """Company guidance and analyst expectations."""
    ticker: str
    market: Market
    fiscal_year: int
    source: str
    updated_date: datetime
    quarter: Optional[int] = None
    analyst_eps_mean: Optional[float] = None
    analyst_eps_low: Optional[float] = None
    analyst_eps_high: Optional[float] = None
    analyst_revenue_mean: Optional[float] = None
    analyst_revenue_low: Optional[float] = None
    analyst_revenue_high: Optional[float] = None
    analyst_count: int = 0
    analyst_rating: Optional[AnalystRating] = None
    analyst_rating_distribution: Optional[Dict[str, int]] = None


@dataclass
class NewsFetchResult:
    """Result of fetching news and guidance for a stock."""
    success: bool
    ticker: str
    market: Market
    source: str
    news: List[NewsItem] = field(default_factory=list)
    guidance: List[Guidance] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class NewsAnalysisResult:
    """Result of sentiment analysis on news articles."""
    ticker: str
    market: Optional[Market]
    analyzer_type: str
    news: List[NewsItem] = field(default_factory=list)

    # Aggregated sentiment metrics
    sentiment_score: float = 0.0  # -1.0 to 1.0
    confidence: float = 0.0  # 0.0 to 1.0

    # News counts
    news_count_7d: int = 0
    news_count_30d: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0

    # Insights
    key_themes: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    catalysts: List[str] = field(default_factory=list)

    # LLM-specific fields (optional)
    sentiment_trend: str = "stable"  # improving, deteriorating, stable
    growth_sentiment: str = "neutral"  # positive, negative, neutral
    dividend_safety: str = "stable"  # stable, at_risk, improving
