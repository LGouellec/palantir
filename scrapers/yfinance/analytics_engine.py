"""
Async Analytics Engine for Yahoo Finance stock data.

Provides concurrent fetching of stock analytics for real-time monitoring
of large batches (100+ stocks).
"""
import asyncio
import inspect
import logging
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, List, Optional, Union

from data.fetcher.async_yfinance import AsyncYFinanceFetcher
from news.fetcher.async_yfinance import AsyncYFinanceNewsFetcher
from nasdaq_tickers import NASDAQTickerFetcher
from proxy_rotator import ProxyRotator
from models import (
    StockAnalytics,
    StockQuote,
    Fundamentals,
    ValuationMetrics,
    PriceHistory,
    RateLimiterStats,
    RetryStats,
    BatchSummary,
)

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    Token bucket algorithm for rate limiting.

    Allows bursts up to bucket capacity while maintaining average rate over time.
    More flexible than simple delays between requests.
    """

    def __init__(self, rate: float, capacity: Optional[float] = None):
        """
        Initialize token bucket.

        Args:
            rate: Tokens added per second (requests per second)
            capacity: Maximum tokens in bucket (allows bursts). Defaults to rate * 2
        """
        self.rate = rate
        self.capacity = capacity or (rate * 2)
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """
        Acquire tokens from the bucket, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire (default: 1.0)
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Add tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= tokens:
                    # We have enough tokens
                    self.tokens -= tokens
                    return

                # Not enough tokens, calculate wait time
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate

                # Wait and retry
                await asyncio.sleep(wait_time)


def is_market_open() -> bool:
    """
    Check if NASDAQ/NYSE market is currently open.

    Market hours (Eastern Time):
    - Weekdays only (Monday-Friday)
    - 7:30 AM - 6:00 PM ET (2 hours before open, 2 hours after close)

    Returns:
        True if market is open, False otherwise
    """
    # Get current time in Eastern Time
    et_tz = ZoneInfo("America/New_York")
    now_et = datetime.now(et_tz)

    # Check if weekend (Saturday=5, Sunday=6)
    if now_et.weekday() >= 5:
        return False

    # Check if within trading hours (7:30 AM - 6:00 PM ET)
    market_open = now_et.replace(hour=7, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=18, minute=0, second=0, microsecond=0)

    return market_open <= now_et <= market_close


def seconds_until_market_open() -> int:
    """
    Calculate seconds until next market open (7:30 AM ET).

    Returns:
        Number of seconds until market opens
    """
    et_tz = ZoneInfo("America/New_York")
    now_et = datetime.now(et_tz)

    # Market opens at 7:30 AM ET
    next_open = now_et.replace(hour=7, minute=30, second=0, microsecond=0)

    # If already past 7:30 AM today, move to next day
    if now_et >= next_open:
        next_open += timedelta(days=1)

    # Skip weekends - move to Monday if needed
    while next_open.weekday() >= 5:  # Saturday or Sunday
        next_open += timedelta(days=1)

    # Calculate seconds until open
    seconds = int((next_open - now_et).total_seconds())
    return max(0, seconds)


class AsyncAnalyticsEngine:
    """
    Async analytics engine for batch stock data fetching with built-in scheduler.

    Features:
    - Concurrent fetching of 100+ stocks
    - Semaphore-based rate limiting (default 20 concurrent requests)
    - Combines quote, fundamentals, news, and valuation metrics
    - Graceful error handling per stock
    - Internal scheduler for automatic data refresh
    - Callback support for real-time updates
    """

    def __init__(
        self,
        max_concurrent: int = 20,
        max_requests_per_second: float = 20.0,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
        enable_proxy_rotation: bool = True,
    ):
        """
        Initialize the analytics engine.

        Args:
            max_concurrent: Maximum concurrent requests (default 20)
            max_requests_per_second: Maximum requests per second (default 20.0)
                Uses token bucket algorithm for smooth rate limiting.
                Set to 0 to disable rate limiting (not recommended).
            max_retries: Maximum retry attempts for failed requests (default 3)
            base_retry_delay: Base delay in seconds for exponential backoff (default 1.0)
            max_retry_delay: Maximum retry delay in seconds (default 60.0)
            enable_proxy_rotation: Enable proxy rotation if proxies are configured (default True)
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.data_fetcher = AsyncYFinanceFetcher()
        self.news_fetcher = AsyncYFinanceNewsFetcher()

        # Rate limiting with token bucket
        self.max_requests_per_second = max_requests_per_second
        if max_requests_per_second > 0:
            self.rate_limiter = TokenBucket(rate=max_requests_per_second)
        else:
            self.rate_limiter = None

        # Retry configuration
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay

        # Proxy rotation
        self.proxy_rotator: Optional[ProxyRotator] = None
        if enable_proxy_rotation:
            self.proxy_rotator = ProxyRotator()
            if self.proxy_rotator.is_enabled():
                logger.info(f"🔄 Proxy rotation enabled with {self.proxy_rotator.get_healthy_count()} proxies")
            else:
                self.proxy_rotator = None

        # Scheduler state
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitored_tickers: List[str] = []
        self._refresh_interval_ms: int = 60000  # Default 60 seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self._update_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._monitor_config: Dict[str, Any] = {
            "include_news": True,
            "news_days": 7,
            "include_history": False,
        }

        # Retry statistics
        self._retry_stats: Dict[str, int] = {
            "total_requests": 0,
            "total_retries": 0,
            "rate_limit_errors": 0,
            "failed_after_retries": 0,
        }

        # NASDAQ ticker cache
        self._nasdaq_tickers: Optional[List[str]] = None

        # Batch rotation indices for monitoring
        self._preferred_index: int = 0
        self._non_preferred_index: int = 0

    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Check if an error is retryable.

        Args:
            error: The exception to check

        Returns:
            True if the error should be retried
        """
        error_str = str(error).lower()

        # HTTP 429 (Too Many Requests)
        if "429" in error_str or "too many requests" in error_str:
            return True

        # HTTP 503 (Service Unavailable)
        if "503" in error_str or "service unavailable" in error_str:
            return True

        # Connection errors
        if any(x in error_str for x in ["connection", "timeout", "timed out"]):
            return True

        # Network errors
        if any(x in error_str for x in ["network", "unreachable", "refused"]):
            return True

        return False

    def _build_stock_quote(self, ticker: str, data: Dict[str, Any]) -> StockQuote:
        """Build StockQuote from raw data dictionary."""
        return StockQuote(
            ticker=ticker,
            name=data.get("name", ""),
            current_price=data.get("current_price"),
            previous_close=data.get("previous_close"),
            open_price=data.get("open_price"),
            day_high=data.get("day_high"),
            day_low=data.get("day_low"),
            volume=data.get("volume"),
            avg_volume_10d=data.get("avg_volume_10d"),
            market_cap=data.get("market_cap"),
            pe_ratio=data.get("pe_ratio"),
            eps=data.get("eps"),
            dividend_yield=data.get("dividend_yield"),
            beta=data.get("beta"),
            week_52_high=data.get("week_52_high"),
            week_52_low=data.get("week_52_low"),
            shares_outstanding=data.get("shares_outstanding"),
        )

    def _build_fundamentals(self, data: Dict[str, Any]) -> Fundamentals:
        """Build Fundamentals from raw data dictionary."""
        fundamentals_data = data.get("fundamentals", {}) if isinstance(data.get("fundamentals"), dict) else {}
        return Fundamentals(
            revenue=fundamentals_data.get("revenue") or data.get("revenue"),
            revenue_growth=fundamentals_data.get("revenue_growth") or data.get("revenue_growth"),
            net_income=fundamentals_data.get("net_income") or data.get("net_income"),
            profit_margin=fundamentals_data.get("profit_margin") or data.get("profit_margin"),
            operating_margin=fundamentals_data.get("operating_margin") or data.get("operating_margin"),
            total_debt=fundamentals_data.get("total_debt") or data.get("total_debt"),
            total_equity=fundamentals_data.get("total_equity") or data.get("total_equity"),
            debt_to_equity=fundamentals_data.get("debt_to_equity") or data.get("debt_to_equity"),
            current_ratio=fundamentals_data.get("current_ratio") or data.get("current_ratio"),
            book_value_per_share=fundamentals_data.get("book_value_per_share") or data.get("book_value_per_share"),
            pb_ratio=fundamentals_data.get("pb_ratio") or data.get("pb_ratio"),
            roe=fundamentals_data.get("roe") or data.get("roe"),
            roa=fundamentals_data.get("roa") or data.get("roa"),
        )

    def _build_valuation_metrics(self, history_data: Optional[Dict[str, Any]]) -> Optional[ValuationMetrics]:
        """Build ValuationMetrics from history data."""
        if not history_data:
            return None

        return ValuationMetrics(
            cagr_1y=history_data.get("cagr"),
            cagr_3y=None,  # Can add if history result provides this
            cagr_5y=None,
            volatility_1y=history_data.get("volatility"),
            volatility_3y=None,
            max_drawdown_1y=history_data.get("max_drawdown"),
            sharpe_ratio_1y=None,
            sortino_ratio_1y=None,
        )

    async def fetch_nasdaq_tickers(
        self,
        include_nasdaq: bool = True,
        include_nyse: bool = True,
        include_amex: bool = True,
        include_etf: bool = False,
        cache_ttl_hours: int = 24,
    ) -> List[str]:
        """
        Fetch list of all NASDAQ-listed stocks from FTP server.

        Downloads ticker lists from ftp.nasdaqtrader.com and caches them locally.
        Results are cached for 24 hours by default.

        Args:
            include_nasdaq: Include NASDAQ-listed stocks (default True)
            include_nyse: Include NYSE-listed stocks (default True)
            include_amex: Include AMEX-listed stocks (default True)
            include_etf: Include ETFs in the results (default False)
            cache_ttl_hours: Cache validity in hours (default 24)

        Returns:
            List of ticker symbols (e.g., ["AAPL", "GOOGL", "MSFT", ...])

        Example:
            engine = AsyncAnalyticsEngine()
            tickers = await engine.fetch_nasdaq_tickers()
            print(f"Found {len(tickers)} stocks")

            # Start monitoring all NASDAQ stocks
            engine.start_monitoring(tickers, interval_ms=60000)
        """
        fetcher = NASDAQTickerFetcher(
            include_nasdaq=include_nasdaq,
            include_nyse=include_nyse,
            include_amex=include_amex,
            include_etf=include_etf,
            cache_ttl_hours=cache_ttl_hours,
        )

        tickers = await fetcher.fetch_all_tickers()
        self._nasdaq_tickers = tickers

        return tickers

    @property
    def nasdaq_tickers(self) -> Optional[List[str]]:
        """
        Get cached NASDAQ ticker list.

        Returns None if fetch_nasdaq_tickers() hasn't been called yet.

        Example:
            if engine.nasdaq_tickers:
                print(f"Cached {len(engine.nasdaq_tickers)} tickers")
        """
        return self._nasdaq_tickers

    def _prioritize_tickers(
        self,
        tickers: List[str],
        preferred_tickers: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Reorder ticker list to prioritize preferred tickers.

        Args:
            tickers: Full list of tickers
            preferred_tickers: Optional list of tickers to fetch first

        Returns:
            Reordered list with preferred tickers first, then remaining tickers
        """
        if not preferred_tickers:
            return tickers

        # Convert to sets for efficient lookup
        ticker_set = set(tickers)
        preferred_set = set(preferred_tickers)

        # Filter preferred tickers that are actually in the ticker list
        valid_preferred = [t for t in preferred_tickers if t in ticker_set]

        # Get remaining tickers (preserve original order)
        remaining = [t for t in tickers if t not in preferred_set]

        # Return preferred first, then remaining
        ordered = valid_preferred + remaining

        if valid_preferred:
            logger.debug(f"Prioritized {len(valid_preferred)} preferred tickers out of {len(tickers)} total")

        return ordered

    async def _retry_with_backoff(
        self,
        func: Callable,
        *args,
        operation_name: str = "request",
        **kwargs,
    ) -> Any:
        """
        Execute a function with exponential backoff retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            operation_name: Name of operation for logging
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            Exception: If all retries are exhausted
        """
        self._retry_stats["total_requests"] += 1
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                return result

            except Exception as e:
                last_exception = e

                # Check if this is the last attempt
                if attempt >= self.max_retries:
                    self._retry_stats["failed_after_retries"] += 1
                    raise

                # Check if error is retryable
                if not self._is_retryable_error(e):
                    raise

                # Track retry statistics
                self._retry_stats["total_retries"] += 1

                if "429" in str(e).lower():
                    self._retry_stats["rate_limit_errors"] += 1

                # Calculate delay with exponential backoff + jitter
                delay = min(
                    self.base_retry_delay * (2 ** attempt),
                    self.max_retry_delay,
                )

                # Add random jitter (±25% of delay)
                jitter = delay * 0.25 * (2 * random.random() - 1)
                delay = delay + jitter

                logger.warning(
                    f"{operation_name} failed (attempt {attempt + 1}/{self.max_retries + 1}): {str(e)[:100]}"
                )
                logger.info(f"Retrying in {delay:.2f}s...")

                await asyncio.sleep(delay)

        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError(f"{operation_name} failed after {self.max_retries + 1} attempts")

    async def fetch_stock_analytics(
        self,
        ticker: str,
        include_news: bool = True,
        news_days: int = 30,
        include_history: bool = False,
        history_period: str = "5y",
        analyze_sentiment: bool = False,
        sentiment_analyzer: str = "keyword",
        llm_api_key: Optional[str] = None,
        llm_model: str = "gpt-4o-mini",
        llm_base_url: Optional[str] = None,
    ) -> StockAnalytics:
        """
        Fetch complete analytics for a single stock.

        Args:
            ticker: Stock ticker symbol
            include_news: Whether to fetch news and guidance (default True)
            news_days: Number of days of news to fetch (default 30)
            include_history: Whether to fetch historical price data (default False)
            history_period: Period for historical data (1y, 2y, 5y, 10y, max)
            analyze_sentiment: Whether to analyze sentiment of news (default False)
            sentiment_analyzer: Analyzer type: "keyword" or "llm" (default "keyword")
            llm_api_key: OpenAI API key (required if sentiment_analyzer="llm")
            llm_model: LLM model to use (default "gpt-4o-mini")
            llm_base_url: Optional base URL for OpenAI-compatible API

        Returns:
            StockAnalytics object containing quote, fundamentals, news, sentiment, and history
        """
        # Acquire token from rate limiter (if enabled)
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        # Get proxy for this request (if proxy rotation enabled)
        proxy_url = None
        if self.proxy_rotator:
            proxy_url = await self.proxy_rotator.get_proxy(strategy="round_robin")
            if proxy_url:
                logger.debug(f"Using proxy for {ticker}: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")

        # Create fetchers with proxy
        data_fetcher = AsyncYFinanceFetcher(proxy=proxy_url)
        news_fetcher = AsyncYFinanceNewsFetcher(proxy=proxy_url)

        async with self.semaphore:
            fetch_time = datetime.now()
            errors = []

            try:
                # Build list of tasks to run concurrently with retry logic
                tasks = [
                    self._retry_with_backoff(
                        data_fetcher.fetch_all,
                        ticker,
                        operation_name=f"Data fetch for {ticker}",
                    )
                ]

                if include_news:
                    tasks.append(
                        self._retry_with_backoff(
                            news_fetcher.fetch_all,
                            ticker,
                            days=news_days,
                            operation_name=f"News fetch for {ticker}",
                        )
                    )

                if include_history:
                    tasks.append(
                        self._retry_with_backoff(
                            data_fetcher.fetch_history,
                            ticker,
                            period=history_period,
                            operation_name=f"History fetch for {ticker}",
                        )
                    )

                # Execute all fetches concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process data result
                data_result = results[0]
                data = {}
                if isinstance(data_result, Exception):
                    errors.append(f"Data fetch failed: {str(data_result)}")
                else:
                    data = data_result.data
                    errors.extend(data_result.errors)

                # Process news result
                news_items = []
                guidance_items = []
                sentiment_analysis = None
                if include_news:
                    news_result = results[1]
                    if isinstance(news_result, Exception):
                        errors.append(f"News fetch failed: {str(news_result)}")
                    else:
                        # Apply sentiment analysis if requested
                        news_objects = news_result.news
                        if analyze_sentiment and news_objects:
                            try:
                                sentiment_analysis = await self._analyze_sentiment(
                                    ticker=ticker,
                                    news=news_objects,
                                    analyzer_type=sentiment_analyzer,
                                    llm_api_key=llm_api_key,
                                    llm_model=llm_model,
                                    llm_base_url=llm_base_url,
                                )
                                # Use analyzed news from sentiment analysis
                                news_objects = sentiment_analysis.news
                            except Exception as e:
                                errors.append(f"Sentiment analysis failed: {str(e)}")
                                logger.warning(f"Sentiment analysis error for {ticker}: {e}")

                        # Keep news items as NewsItem objects
                        news_items = news_objects
                        guidance_items = news_result.guidance
                        errors.extend(news_result.errors)

                # Process history result
                history_data = None
                if include_history:
                    history_result = results[2] if include_news else results[1]
                    if isinstance(history_result, Exception):
                        errors.append(f"History fetch failed: {str(history_result)}")
                    else:
                        if history_result.success and history_result.df is not None:
                            history_data = {
                                "start_date": history_result.start_date.isoformat() if history_result.start_date else None,
                                "end_date": history_result.end_date.isoformat() if history_result.end_date else None,
                                "cagr": history_result.calculate_cagr(),
                                "volatility": history_result.calculate_volatility(),
                                "max_drawdown": history_result.calculate_max_drawdown(),
                                "price_count": len(history_result.df),
                            }
                        errors.extend(history_result.errors)

                # Build StockAnalytics object
                quote = self._build_stock_quote(ticker, data) if data else None
                fundamentals = self._build_fundamentals(data) if data else None
                valuation = self._build_valuation_metrics(history_data) if history_data else None

                # Extract additional data fields (everything not in core dataclasses)
                additional_data = {}
                if data:
                    # List of fields to include in additional_data
                    additional_fields = [
                        # Historical data
                        'dividends_history', 'splits_history', 'actions_history',
                        # Analyst and earnings data
                        'recommendations', 'earnings_dates', 'quarterly_earnings',
                        # Quarterly financial statements
                        'quarterly_financials', 'quarterly_balance_sheet', 'quarterly_cashflow',
                        # Annual financial statements (raw)
                        'financials_raw', 'balance_sheet_raw', 'cashflow_raw',
                        # Ownership data
                        'major_holders', 'institutional_holders', 'mutualfund_holders',
                        # Insider data
                        'insider_transactions', 'insider_purchases', 'insider_roster_holders',
                        # Options data
                        'options_expiration_dates',
                        # All other fields from info
                    ]

                    # Add specified fields
                    for field in additional_fields:
                        if field in data:
                            additional_data[field] = data[field]

                    # Also include all info fields that aren't in the standard dataclasses
                    # This captures everything from stock.info
                    excluded_keys = {
                        'ticker', 'name', 'current_price', 'shares_outstanding',
                        'eps', 'bvps', 'revenue', 'net_income', 'ebit', 'roe',
                        'operating_margin', 'total_assets', 'fcf', 'ebitda',
                    }
                    for key, value in data.items():
                        if key not in excluded_keys and key not in additional_data:
                            additional_data[key] = value

                result = StockAnalytics(
                    ticker=ticker,
                    fetch_time=fetch_time,
                    quote=quote,
                    fundamentals=fundamentals,
                    valuation=valuation,
                    news=news_items,
                    guidance=guidance_items,
                    sentiment_analysis=sentiment_analysis,
                    history=None,  # TODO: build PriceHistory object
                    additional_data=additional_data,
                    errors=errors,
                )

                # Mark proxy as successful if used
                if self.proxy_rotator and proxy_url:
                    await self.proxy_rotator.mark_success(proxy_url)

                return result

            except Exception as e:
                # Mark proxy as failed if used
                if self.proxy_rotator and proxy_url:
                    await self.proxy_rotator.mark_failure(proxy_url, e)
                raise

    async def _analyze_sentiment(
        self,
        ticker: str,
        news: List,
        analyzer_type: str = "keyword",
        llm_api_key: Optional[str] = None,
        llm_model: str = "gpt-4o-mini",
        llm_base_url: Optional[str] = None,
    ):
        """
        Analyze sentiment of news articles.

        Args:
            ticker: Stock ticker symbol
            news: List of NewsItem objects
            analyzer_type: "keyword" or "llm"
            llm_api_key: OpenAI API key (for LLM analyzer)
            llm_model: LLM model name
            llm_base_url: Optional base URL for OpenAI-compatible API

        Returns:
            NewsAnalysisResult object
        """
        if not news:
            from news.base import NewsAnalysisResult, Market
            return NewsAnalysisResult(
                ticker=ticker,
                market=Market.US,
                analyzer_type=analyzer_type,
            )

        if analyzer_type == "llm":
            from news.analyzer.llm import LLMSentimentAnalyzer
            analyzer = LLMSentimentAnalyzer(
                api_key=llm_api_key,
                model=llm_model,
                base_url=llm_base_url,
            )
            # Run LLM analysis in thread pool (blocking I/O)
            return await asyncio.to_thread(analyzer.analyze_batch, news, ticker)
        else:
            # Keyword analyzer
            from news.analyzer.keyword import KeywordSentimentAnalyzer
            analyzer = KeywordSentimentAnalyzer()
            # Run in thread pool to avoid blocking
            return await asyncio.to_thread(analyzer.analyze_batch, news, ticker)

    async def fetch_batch_analytics(
        self,
        tickers: List[str],
        include_news: bool = True,
        news_days: int = 30,
        include_history: bool = False,
        history_period: str = "5y",
        analyze_sentiment: bool = False,
        sentiment_analyzer: str = "keyword",
        llm_api_key: Optional[str] = None,
        llm_model: str = "gpt-4o-mini",
        llm_base_url: Optional[str] = None,
        preferred_tickers: Optional[List[str]] = None,
    ) -> Dict[str, StockAnalytics]:
        """
        Fetch analytics for multiple stocks concurrently.

        Args:
            tickers: List of stock ticker symbols
            include_news: Whether to fetch news and guidance (default True)
            news_days: Number of days of news to fetch (default 30)
            include_history: Whether to fetch historical price data (default False)
            history_period: Period for historical data (1y, 2y, 5y, 10y, max)
            analyze_sentiment: Whether to analyze sentiment of news (default False)
            sentiment_analyzer: Analyzer type: "keyword" or "llm" (default "keyword")
            llm_api_key: OpenAI API key (required if sentiment_analyzer="llm")
            llm_model: LLM model to use (default "gpt-4o-mini")
            llm_base_url: Optional base URL for OpenAI-compatible API
            preferred_tickers: Optional list of tickers to fetch first (default None)

        Returns:
            Dictionary mapping ticker -> analytics data
            Each analytics entry contains the same fields as fetch_stock_analytics()
        """
        # Reorder tickers to prioritize preferred ones
        ordered_tickers = self._prioritize_tickers(tickers, preferred_tickers)

        tasks = [
            self.fetch_stock_analytics(
                ticker,
                include_news=include_news,
                news_days=news_days,
                include_history=include_history,
                history_period=history_period,
                analyze_sentiment=analyze_sentiment,
                sentiment_analyzer=sentiment_analyzer,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
                llm_base_url=llm_base_url,
            )
            for ticker in ordered_tickers
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict
        batch_results = {}
        for ticker, result in zip(ordered_tickers, results):
            if isinstance(result, Exception):
                batch_results[ticker] = StockAnalytics(
                    ticker=ticker,
                    fetch_time=datetime.now(),
                    errors=[f"Fatal error: {str(result)}"],
                )
            else:
                batch_results[ticker] = result

        return batch_results

    async def fetch_batch_summary(
        self,
        tickers: List[str],
    ) -> Dict[str, Any]:
        """
        Fetch analytics for multiple stocks and return aggregated summary.

        Args:
            tickers: List of stock ticker symbols

        Returns:
            Dictionary containing:
            - total_stocks: Total number of stocks
            - successful: Number of successful fetches
            - failed: Number of failed fetches
            - stocks: Dict mapping ticker -> simplified data (price, PE, market cap)
            - errors: Dict mapping ticker -> list of errors
        """
        results = await self.fetch_batch_analytics(
            tickers,
            include_news=False,
            include_history=False,
        )

        successful = 0
        failed = 0
        stocks = {}
        errors = {}

        for ticker, analytics in results.items():
            if analytics.errors:
                failed += 1
                errors[ticker] = analytics.errors
            else:
                successful += 1

            # Extract key metrics from StockAnalytics
            stocks[ticker] = {
                "current_price": analytics.quote.current_price if analytics.quote else 0,
                "pe_ratio": analytics.quote.pe_ratio if analytics.quote else 0,
                "pb_ratio": analytics.fundamentals.pb_ratio if analytics.fundamentals else 0,
                "market_cap": analytics.quote.market_cap if analytics.quote else 0,
                "sector": "",  # Not available in current data model
                "industry": "",  # Not available in current data model
            }

        return {
            "total_stocks": len(tickers),
            "successful": successful,
            "failed": failed,
            "stocks": stocks,
            "errors": errors,
        }

    # ========================================================================
    # Scheduler Methods
    # ========================================================================

    def start_monitoring(
        self,
        tickers: List[str],
        interval_ms: int = 60000,
        include_news: bool = True,
        news_days: int = 7,
        include_history: bool = False,
        analyze_sentiment: bool = False,
        sentiment_analyzer: str = "keyword",
        llm_api_key: Optional[str] = None,
        llm_model: str = "gpt-4o-mini",
        llm_base_url: Optional[str] = None,
        preferred_tickers: Optional[List[str]] = None,
        batch_size: Optional[int] = 200,
    ) -> None:
        """
        Start monitoring stocks with automatic refresh at specified interval.

        Args:
            tickers: List of stock ticker symbols to monitor
            interval_ms: Refresh interval in milliseconds (default: 60000 = 1 minute)
            include_news: Whether to fetch news (default: True)
            news_days: Days of news to fetch (default: 7)
            include_history: Whether to fetch historical data (default: False)
            analyze_sentiment: Whether to analyze sentiment of news (default: False)
            sentiment_analyzer: Analyzer type: "keyword" or "llm" (default "keyword")
            llm_api_key: OpenAI API key (required if sentiment_analyzer="llm")
            llm_model: LLM model to use (default "gpt-4o-mini")
            llm_base_url: Optional base URL for OpenAI-compatible API
            preferred_tickers: Optional list of tickers with 3x weight (default None)
            batch_size: Optional batch size for each iteration (default None = fetch all)

        Example:
            # Fetch all tickers on each refresh
            engine.start_monitoring(["AAPL", "GOOGL"], interval_ms=30000)

            # Batch mode: fetch 100 tickers per iteration with preferred tickers 3x weighted
            engine.start_monitoring(
                tickers=all_nasdaq_tickers,  # 3000+ stocks
                batch_size=100,  # Fetch 100 per iteration
                preferred_tickers=["AAPL", "GOOGL", "MSFT"],  # 3x weight
                interval_ms=60000,
            )
        """
        if self._monitoring:
            raise RuntimeError("Monitoring already started. Call stop_monitoring() first.")

        # Randomize ticker order to avoid patterns
        shuffled_tickers = tickers.copy()
        random.shuffle(shuffled_tickers)
        logger.info(f"🔀 Randomized order of {len(shuffled_tickers)} tickers")

        shuffled_preferred = None
        if preferred_tickers:
            shuffled_preferred = preferred_tickers.copy()
            random.shuffle(shuffled_preferred)
            logger.info(f"🔀 Randomized order of {len(shuffled_preferred)} preferred tickers")

        self._monitored_tickers = shuffled_tickers
        self._refresh_interval_ms = interval_ms
        self._monitor_config = {
            "include_news": include_news,
            "news_days": news_days,
            "include_history": include_history,
            "analyze_sentiment": analyze_sentiment,
            "sentiment_analyzer": sentiment_analyzer,
            "llm_api_key": llm_api_key,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "preferred_tickers": shuffled_preferred,
            "batch_size": batch_size,
        }

        # Reset rotation indices
        self._preferred_index = 0
        self._non_preferred_index = 0

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        if batch_size:
            logger.info(f"Started monitoring {len(tickers)} stocks in batches of {batch_size} (refresh every {interval_ms}ms)")
            if preferred_tickers:
                logger.info(f"Preferred tickers ({len(preferred_tickers)}) have 3x weight")
        else:
            logger.info(f"Started monitoring {len(tickers)} stocks (refresh every {interval_ms}ms)")

    async def stop_monitoring(self) -> None:
        """
        Stop the monitoring scheduler and clean up.

        Example:
            await engine.stop_monitoring()
        """
        if not self._monitoring:
            return

        self._monitoring = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("Stopped monitoring")

    def add_update_callback(self, callback: Callable[[str, StockAnalytics], None]) -> None:
        """
        Add a callback function to be called when stock data is updated.

        The callback will receive (ticker, analytics) as arguments.

        Args:
            callback: Function with signature: callback(ticker: str, analytics: StockAnalytics)

        Example:
            def on_update(ticker, analytics):
                if analytics.quote:
                    price = analytics.quote.current_price
                    print(f"{ticker}: ${price:.2f}")

            engine.add_update_callback(on_update)
        """
        self._update_callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[str, StockAnalytics], None]) -> None:
        """
        Remove a previously added callback.

        Args:
            callback: The callback function to remove
        """
        if callback in self._update_callbacks:
            self._update_callbacks.remove(callback)

    async def get_cached_data(self, ticker: str) -> Optional[StockAnalytics]:
        """
        Get the latest cached data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Cached StockAnalytics object or None if not available

        Example:
            analytics = await engine.get_cached_data("AAPL")
            if analytics and analytics.quote:
                print(f"Price: ${analytics.quote.current_price:.2f}")
        """
        async with self._cache_lock:
            return self._cache.get(ticker)

    async def get_all_cached_data(self) -> Dict[str, StockAnalytics]:
        """
        Get all cached stock data.

        Returns:
            Dictionary mapping ticker -> analytics data

        Example:
            all_data = await engine.get_all_cached_data()
            for ticker, data in all_data.items():
                print(f"{ticker}: ${data['data']['current_price']:.2f}")
        """
        async with self._cache_lock:
            return self._cache.copy()

    @property
    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active."""
        return self._monitoring

    @property
    def monitored_tickers(self) -> List[str]:
        """Get the list of currently monitored tickers."""
        return self._monitored_tickers.copy()

    @property
    def refresh_interval_ms(self) -> int:
        """Get the current refresh interval in milliseconds."""
        return self._refresh_interval_ms

    def get_retry_stats(self) -> RetryStats:
        """
        Get retry statistics for monitoring rate limit issues.

        Returns:
            RetryStats object containing request and retry statistics

        Example:
            stats = engine.get_retry_stats()
            print(f"Total requests: {stats.total_requests}")
            print(f"429 errors: {stats.rate_limit_errors}")
        """
        return RetryStats(
            total_requests=self._retry_stats["total_requests"],
            total_retries=self._retry_stats["total_retries"],
            rate_limit_errors=self._retry_stats["rate_limit_errors"],
            failed_after_retries=self._retry_stats["failed_after_retries"],
        )

    def reset_retry_stats(self) -> None:
        """
        Reset retry statistics counters.

        Useful for tracking stats over a specific time period.

        Example:
            engine.reset_retry_stats()
            # ... run some operations ...
            stats = engine.get_retry_stats()
        """
        self._retry_stats = {
            "total_requests": 0,
            "total_retries": 0,
            "rate_limit_errors": 0,
            "failed_after_retries": 0,
        }

    def get_rate_limiter_stats(self) -> RateLimiterStats:
        """
        Get current rate limiter status.

        Returns:
            RateLimiterStats object containing enabled, rate, capacity, and available tokens

        Example:
            stats = engine.get_rate_limiter_stats()
            print(f"Rate limit: {stats.rate} req/s")
            print(f"Available tokens: {stats.available_tokens:.2f}")
        """
        if not self.rate_limiter:
            return RateLimiterStats(
                enabled=False,
                rate=0,
                available_tokens=float('inf'),
                capacity=float('inf'),
            )

        # Update tokens based on elapsed time (snapshot)
        now = time.monotonic()
        elapsed = now - self.rate_limiter.last_update
        current_tokens = min(
            self.rate_limiter.capacity,
            self.rate_limiter.tokens + elapsed * self.rate_limiter.rate
        )

        return RateLimiterStats(
            enabled=True,
            rate=self.max_requests_per_second,
            available_tokens=round(current_tokens, 2),
            capacity=self.rate_limiter.capacity,
        )

    def _build_weighted_batch(
        self,
        all_tickers: List[str],
        preferred_tickers: Optional[List[str]],
        batch_size: int,
    ) -> List[str]:
        """
        Build a batch of tickers with preferred tickers having 3x weight.

        Args:
            all_tickers: Full list of tickers to monitor
            preferred_tickers: Optional list of preferred tickers (3x weight)
            batch_size: Number of tickers to include in batch

        Returns:
            List of tickers for this batch (may include duplicates for preferred)
        """
        if not preferred_tickers or batch_size >= len(all_tickers):
            # No preferred tickers or batch size >= all tickers, return subset
            return all_tickers[:batch_size]

        # Calculate slots: preferred get 75% (3x weight), non-preferred get 25%
        preferred_count = int(batch_size * 0.75)
        non_preferred_count = batch_size - preferred_count

        # Separate preferred and non-preferred tickers
        preferred_set = set(preferred_tickers)
        non_preferred_tickers = [t for t in all_tickers if t not in preferred_set]

        # Validate preferred tickers exist in all_tickers
        valid_preferred = [t for t in preferred_tickers if t in all_tickers]

        if not valid_preferred:
            # No valid preferred tickers, return regular batch
            return all_tickers[:batch_size]

        batch = []

        # Add preferred tickers with rotation
        for i in range(preferred_count):
            idx = (self._preferred_index + i) % len(valid_preferred)
            batch.append(valid_preferred[idx])

        # Add non-preferred tickers with rotation
        if non_preferred_tickers:
            for i in range(non_preferred_count):
                idx = (self._non_preferred_index + i) % len(non_preferred_tickers)
                batch.append(non_preferred_tickers[idx])

        # Update indices for next iteration
        self._preferred_index = (self._preferred_index + preferred_count) % len(valid_preferred)
        if non_preferred_tickers:
            self._non_preferred_index = (self._non_preferred_index + non_preferred_count) % len(non_preferred_tickers)

        return batch

    async def _monitor_loop(self) -> None:
        """Internal monitoring loop that refreshes data at intervals."""
        iteration = 0

        while self._monitoring:
            # Check if market is open
            if not is_market_open():
                wait_seconds = seconds_until_market_open()
                et_tz = ZoneInfo("America/New_York")
                now_et = datetime.now(et_tz)
                logger.info(f"🌙 Market is closed (current time: {now_et.strftime('%A %I:%M %p ET')})")
                logger.info(f"⏰ Sleeping {wait_seconds / 3600:.1f} hours until market opens at 7:30 AM ET")

                # Sleep in chunks to allow graceful shutdown
                sleep_chunk = 60  # Check every minute if still monitoring
                while wait_seconds > 0 and self._monitoring:
                    chunk = min(sleep_chunk, wait_seconds)
                    await asyncio.sleep(chunk)
                    wait_seconds -= chunk

                if not self._monitoring:
                    break

                logger.info("🔔 Market is now open - resuming monitoring")

            iteration += 1
            start_time = datetime.now()

            try:
                batch_size = self._monitor_config.get("batch_size")
                preferred_tickers = self._monitor_config.get("preferred_tickers")

                # Determine which tickers to fetch this iteration
                if batch_size:
                    # Build weighted batch with preferred tickers having 3x weight
                    tickers_to_fetch = self._build_weighted_batch(
                        self._monitored_tickers,
                        preferred_tickers,
                        batch_size,
                    )
                    logger.info(f"Refresh #{iteration} - Fetching batch of {len(tickers_to_fetch)} stocks...")
                else:
                    # Fetch all tickers
                    tickers_to_fetch = self._monitored_tickers
                    logger.info(f"Refresh #{iteration} - Fetching {len(tickers_to_fetch)} stocks...")

                # Fetch stocks concurrently
                results = await self.fetch_batch_analytics(
                    tickers_to_fetch,
                    include_news=self._monitor_config["include_news"],
                    news_days=self._monitor_config["news_days"],
                    include_history=self._monitor_config["include_history"],
                    analyze_sentiment=self._monitor_config.get("analyze_sentiment", False),
                    sentiment_analyzer=self._monitor_config.get("sentiment_analyzer", "keyword"),
                    llm_api_key=self._monitor_config.get("llm_api_key"),
                    llm_model=self._monitor_config.get("llm_model", "gpt-4o-mini"),
                    llm_base_url=self._monitor_config.get("llm_base_url"),
                )

                # Update cache
                async with self._cache_lock:
                    for ticker, data in results.items():
                        self._cache[ticker] = data

                        # Trigger callbacks
                        for callback in self._update_callbacks:
                            try:
                                if inspect.iscoroutinefunction(callback):
                                    await callback(ticker, data)
                                else:
                                    callback(ticker, data)
                            except Exception as e:
                                logger.warning(f"Callback error for {ticker}: {e}")

                elapsed = (datetime.now() - start_time).total_seconds()
                successful = sum(1 for analytics in results.values() if not analytics.errors)
                failed = len(results) - successful

                logger.info(f"Refresh complete: {successful} OK, {failed} errors ({elapsed:.2f}s)")

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            # Wait for next interval
            if self._monitoring:
                await asyncio.sleep(self._refresh_interval_ms / 1000.0)

    async def __aenter__(self):
        """Support async context manager for automatic cleanup."""
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Ensure monitoring stops when exiting context."""
        await self.stop_monitoring()
        return False
