"""
Data models for AsyncAnalyticsEngine.

Provides type-safe dataclasses instead of Dict[str, Any].
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from news.base import NewsItem, Guidance, NewsAnalysisResult


@dataclass
class StockQuote:
    """Stock quote data."""
    ticker: str
    name: str
    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    open_price: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[int] = None
    avg_volume_10d: Optional[int] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    shares_outstanding: Optional[int] = None


@dataclass
class Fundamentals:
    """Fundamental analysis data."""
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_income: Optional[float] = None
    profit_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    total_debt: Optional[float] = None
    total_equity: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    book_value_per_share: Optional[float] = None
    pb_ratio: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None


@dataclass
class ValuationMetrics:
    """Valuation and performance metrics."""
    cagr_1y: Optional[float] = None
    cagr_3y: Optional[float] = None
    cagr_5y: Optional[float] = None
    volatility_1y: Optional[float] = None
    volatility_3y: Optional[float] = None
    max_drawdown_1y: Optional[float] = None
    sharpe_ratio_1y: Optional[float] = None
    sortino_ratio_1y: Optional[float] = None


@dataclass
class PriceHistory:
    """Historical price data."""
    dates: List[datetime] = field(default_factory=list)
    prices: List[float] = field(default_factory=list)
    volumes: List[int] = field(default_factory=list)
    period: str = ""


@dataclass
class StockAnalytics:
    """
    Complete stock analytics data.

    Replaces Dict[str, Any] return type from fetch_stock_analytics().
    """
    ticker: str
    fetch_time: datetime

    # Core data
    quote: Optional[StockQuote] = None
    fundamentals: Optional[Fundamentals] = None
    valuation: Optional[ValuationMetrics] = None

    # News and sentiment
    news: List[NewsItem] = field(default_factory=list)
    guidance: List[Guidance] = field(default_factory=list)
    sentiment_analysis: Optional[NewsAnalysisResult] = None

    # Historical data
    history: Optional[PriceHistory] = None

    # Additional raw data from yfinance
    # Includes: dividends_history, splits_history, recommendations,
    # quarterly_financials, institutional_holders, insider_transactions,
    # options_expiration_dates, and all other info fields
    additional_data: Dict[str, Any] = field(default_factory=dict)

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "ticker": self.ticker,
            "fetch_time": self.fetch_time.isoformat(),
            "data": {
                # Quote data
                **(self.quote.__dict__ if self.quote else {}),

                # Fundamentals
                "fundamentals": self.fundamentals.__dict__ if self.fundamentals else {},

                # Valuation
                "valuation": self.valuation.__dict__ if self.valuation else {},
            },
            "news": [
                {
                    "title": n.title,
                    "content": n.content,
                    "source": n.source,
                    "publish_date": n.publish_date.isoformat(),
                    "url": n.url,
                    "sentiment": n.sentiment.value if n.sentiment else None,
                    "confidence": n.confidence,
                    "impact_score": n.impact_score,
                    "category": n.category.value if n.category else None,
                    "keywords": n.keywords,
                }
                for n in self.news
            ],
            "guidance": [
                {
                    "fiscal_year": g.fiscal_year,
                    "quarter": g.quarter,
                    "analyst_eps_mean": g.analyst_eps_mean,
                    "analyst_revenue_mean": g.analyst_revenue_mean,
                    "analyst_count": g.analyst_count,
                    "analyst_rating": g.analyst_rating.value if g.analyst_rating else None,
                }
                for g in self.guidance
            ],
            "sentiment_analysis": {
                "sentiment_score": self.sentiment_analysis.sentiment_score,
                "confidence": self.sentiment_analysis.confidence,
                "positive_count": self.sentiment_analysis.positive_count,
                "negative_count": self.sentiment_analysis.negative_count,
                "neutral_count": self.sentiment_analysis.neutral_count,
                "news_count_7d": self.sentiment_analysis.news_count_7d,
                "news_count_30d": self.sentiment_analysis.news_count_30d,
                "key_themes": self.sentiment_analysis.key_themes,
                "risks": self.sentiment_analysis.risks,
                "catalysts": self.sentiment_analysis.catalysts,
                "analyzer_type": self.sentiment_analysis.analyzer_type,
                "sentiment_trend": self.sentiment_analysis.sentiment_trend,
                "growth_sentiment": self.sentiment_analysis.growth_sentiment,
                "dividend_safety": self.sentiment_analysis.dividend_safety,
            } if self.sentiment_analysis else None,
            "history": {
                "dates": [d.isoformat() for d in self.history.dates],
                "prices": self.history.prices,
                "volumes": self.history.volumes,
                "period": self.history.period,
            } if self.history else None,
            "additional_data": self.additional_data,
            "errors": self.errors,
        }


@dataclass
class RateLimiterStats:
    """Rate limiter statistics."""
    enabled: bool
    rate: float
    capacity: float
    available_tokens: float


@dataclass
class RetryStats:
    """Retry statistics for monitoring."""
    total_requests: int
    total_retries: int
    rate_limit_errors: int
    failed_after_retries: int


@dataclass
class BatchSummary:
    """Summary of batch analytics operation."""
    total_stocks: int
    successful: int
    failed: int
    stocks: dict  # ticker -> simplified data
    errors: dict  # ticker -> error list
