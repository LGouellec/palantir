"""
Proxy rotation system for distributing requests across multiple proxies.

Helps avoid rate limiting by masking total request volume across different IPs.
"""
import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .fetcher import ProxyFetcher
from .validator import ProxyValidator

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Configuration for a single proxy."""
    url: str  # Format: socks5://host:port or socks5://user:pass@host:port (recommended)
              #         http://host:port or http://user:pass@host:port (may be blocked by Yahoo)
    max_requests_per_minute: int = 60
    healthy: bool = True
    total_requests: int = 0
    last_used: float = 0.0
    consecutive_failures: int = 0


class ProxyRotator:
    """
    Manages a pool of proxies with round-robin rotation and health checking.

    Features:
    - Round-robin rotation across healthy proxies
    - Per-proxy rate limiting (max requests per minute)
    - Automatic health checking and failover
    - Dead proxy detection (consecutive failures)
    - Load balancing based on least recently used
    - Supports HTTP and SOCKS5 proxies (SOCKS5 recommended for Yahoo Finance)

    Important:
        Yahoo Finance detects and blocks local HTTP proxies. Use SOCKS5 proxies instead.
        Format: socks5://host:port or socks5://user:pass@host:port

    Environment Variables:
        PROXY_LIST: Comma-separated list of proxy URLs
        PROXY_CONFIG_PATH: Path to proxy config file (one proxy per line)
        PROXY_AUTO_FETCH: Enable automatic proxy fetching from free lists (default: false)
        PROXY_AUTO_FETCH_MAX: Maximum validated proxies when auto-fetching (default: 50)
        PROXY_MAX_RPM: Max requests per minute per proxy (default: 60)
        PROXY_MAX_FAILURES: Consecutive failures before marking unhealthy (default: 3)
    """

    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        max_requests_per_minute: int = 60,
        max_consecutive_failures: int = 3,
        enable_health_check: Optional[bool] = None,
        auto_fetch_proxies: Optional[bool] = None,
        auto_fetch_max_proxies: int = 50,
    ):
        """
        Initialize proxy rotator.

        Args:
            proxies: List of proxy URLs (socks5://host:port or http://host:port)
                     SOCKS5 recommended - Yahoo Finance blocks HTTP proxies
            max_requests_per_minute: Max requests per proxy per minute
            max_consecutive_failures: Failures before marking proxy as unhealthy
            enable_health_check: Enable automatic health checking
            auto_fetch_proxies: Automatically fetch and validate proxies from free lists
            auto_fetch_max_proxies: Maximum number of validated proxies when auto-fetching
        """
        self._proxies: Dict[str, ProxyConfig] = {}
        self._max_consecutive_failures = max_consecutive_failures
        self._enable_health_check = enable_health_check
        self._current_index = 0
        self._lock = asyncio.Lock()
        self._auto_fetch = auto_fetch_proxies or os.environ.get("PROXY_AUTO_FETCH", "false").lower() == "true"
        self._auto_fetch_max = int(os.environ.get("PROXY_AUTO_FETCH_MAX", auto_fetch_max_proxies))
        self._initialized = False

        # Store params for async initialization
        self._provided_proxies = proxies
        self._max_rpm = int(os.environ.get("PROXY_MAX_RPM", max_requests_per_minute))

    async def initialize(self) -> None:
        """
        Async initialization of proxy rotator.

        Must be called before using the rotator if auto_fetch_proxies is enabled.
        Safe to call multiple times (idempotent).
        """
        if self._initialized:
            return

        # Load proxies from config or environment
        proxy_list = self._provided_proxies or self._load_proxies_from_env()

        # Auto-fetch proxies if enabled and no manual proxies provided
        if self._auto_fetch and not proxy_list:
            logger.info("🔄 Auto-fetching proxies from free proxy list...")
            proxy_list = await self._fetch_and_validate_proxies()

        if not proxy_list:
            logger.warning("⚠️  No proxies configured - ProxyRotator disabled")
            self._initialized = True
            return

        # Initialize proxy configs
        for proxy_url in proxy_list:
            self._proxies[proxy_url] = ProxyConfig(
                url=proxy_url,
                max_requests_per_minute=self._max_rpm,
            )

        logger.info(f"✅ ProxyRotator initialized with {len(self._proxies)} proxies")
        logger.info(f"   Max requests per proxy: {self._max_rpm}/min")
        logger.info(f"   Health check: {'Enabled' if self._enable_health_check else 'Disabled'}")
        logger.info(f"   Auto-fetch: {'Enabled' if self._auto_fetch else 'Disabled'}")

        self._initialized = True

    async def _fetch_and_validate_proxies(self) -> List[str]:
        """
        Fetch proxies from free list and validate them.

        Returns:
            List of validated proxy URLs
        """
        try:
            # Fetch proxies from remote source
            fetcher = ProxyFetcher()
            proxies = await fetcher.fetch_proxies()

            if not proxies:
                logger.warning("⚠️  No proxies fetched from remote source")
                return []

            logger.info(f"📥 Fetched {len(proxies)} proxies, starting validation...")

            # Validate proxies
            validator = ProxyValidator()
            validated_proxies = await validator.validate_proxies(
                proxies, max_proxies=self._auto_fetch_max
            )

            if not validated_proxies:
                logger.warning("⚠️  No working proxies found after validation")
            else:
                logger.info(
                    f"✅ Validated {len(validated_proxies)} working proxies "
                    f"out of {len(proxies)} total"
                )

            return validated_proxies

        except Exception as e:
            logger.error(f"❌ Failed to fetch and validate proxies: {e}")
            return []

    def _load_proxies_from_env(self) -> List[str]:
        """
        Load proxy list from environment variables.

        Returns:
            List of proxy URLs
        """
        proxies = []

        # Option 1: PROXY_LIST environment variable (comma-separated)
        proxy_list_env = os.environ.get("PROXY_LIST")
        if proxy_list_env:
            proxies = [p.strip() for p in proxy_list_env.split(",") if p.strip()]
            logger.info(f"📋 Loaded {len(proxies)} proxies from PROXY_LIST env var")
            return proxies

        # Option 2: PROXY_CONFIG_PATH (file with one proxy per line)
        config_path = os.environ.get("PROXY_CONFIG_PATH")
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        proxies.append(line)
            logger.info(f"📋 Loaded {len(proxies)} proxies from {config_path}")
            return proxies

        return proxies

    async def get_proxy(self, strategy: str = "round_robin") -> Optional[str]:
        """
        Get next proxy URL based on rotation strategy.

        Args:
            strategy: Rotation strategy ("round_robin", "least_used", "random")

        Returns:
            Proxy URL or None if no proxies available
        """
        # Ensure initialization has happened
        if not self._initialized:
            await self.initialize()

        if not self._proxies:
            return None

        async with self._lock:
            healthy_proxies = [
                (url, config) for url, config in self._proxies.items()
                if config.healthy and not self._is_rate_limited(config)
            ]

            if not healthy_proxies:
                # All proxies unhealthy or rate limited - wait for cooldown
                logger.warning("⚠️  All proxies are rate limited or unhealthy")
                return None

            # Select proxy based on strategy
            if strategy == "round_robin":
                proxy_url, config = healthy_proxies[self._current_index % len(healthy_proxies)]
                self._current_index = (self._current_index + 1) % len(healthy_proxies)

            elif strategy == "least_used":
                # Sort by last used time (oldest first)
                healthy_proxies.sort(key=lambda p: p[1].last_used)
                proxy_url, config = healthy_proxies[0]

            elif strategy == "random":
                proxy_url, config = random.choice(healthy_proxies)

            else:
                raise ValueError(f"Unknown strategy: {strategy}")

            # Update usage stats
            config.last_used = time.time()
            config.total_requests += 1

            return proxy_url

    def _is_rate_limited(self, config: ProxyConfig) -> bool:
        """
        Check if proxy has exceeded rate limit.

        Args:
            config: Proxy configuration

        Returns:
            True if rate limited
        """
        if config.max_requests_per_minute <= 0:
            return False

        now = time.time()
        time_since_last_use = now - config.last_used

        # Reset if more than 1 minute has passed
        if time_since_last_use > 60:
            return False

        # Check if we're within the rate limit window
        return time_since_last_use < (60.0 / config.max_requests_per_minute)

    async def mark_success(self, proxy_url: str) -> None:
        """
        Mark a proxy request as successful.

        Args:
            proxy_url: Proxy URL that succeeded
        """
        if proxy_url not in self._proxies:
            return

        async with self._lock:
            config = self._proxies[proxy_url]
            config.consecutive_failures = 0

            # Restore health if it was marked unhealthy
            if not config.healthy and self._enable_health_check:
                config.healthy = True
                logger.info(f"✅ Proxy restored to healthy: {self._sanitize_url(proxy_url)}")

    async def mark_failure(self, proxy_url: str, error: Exception) -> None:
        """
        Mark a proxy request as failed.

        Args:
            proxy_url: Proxy URL that failed
            error: Exception that occurred
        """
        if proxy_url not in self._proxies:
            return

        async with self._lock:
            config = self._proxies[proxy_url]
            config.consecutive_failures += 1

            error_str = str(error).lower()
            is_proxy_error = any(term in error_str for term in [
                "proxy", "connection", "timeout", "unreachable"
            ])

            # Mark unhealthy if too many consecutive failures
            if is_proxy_error and config.consecutive_failures >= self._max_consecutive_failures:
                config.healthy = False
                logger.warning(
                    f"❌ Proxy marked unhealthy after {config.consecutive_failures} failures: "
                    f"{self._sanitize_url(proxy_url)}"
                )

    def _sanitize_url(self, url: str) -> str:
        """
        Sanitize proxy URL for logging (hide credentials).

        Args:
            url: Proxy URL

        Returns:
            Sanitized URL
        """
        if "@" in url:
            # Format: http://user:pass@host:port -> http://***:***@host:port
            parts = url.split("@")
            return f"***:***@{parts[1]}"
        return url

    def get_stats(self) -> Dict[str, any]:
        """
        Get proxy pool statistics.

        Returns:
            Dictionary with statistics for each proxy
        """
        stats = {}
        for url, config in self._proxies.items():
            stats[self._sanitize_url(url)] = {
                "healthy": config.healthy,
                "total_requests": config.total_requests,
                "consecutive_failures": config.consecutive_failures,
                "last_used": config.last_used,
            }
        return stats

    def get_healthy_count(self) -> int:
        """
        Get count of healthy proxies.

        Returns:
            Number of healthy proxies
        """
        return sum(1 for config in self._proxies.values() if config.healthy)

    def is_enabled(self) -> bool:
        """
        Check if proxy rotation is enabled or will be enabled.

        Returns True if:
        - Proxies are already loaded
        - Proxies were provided in constructor (not yet initialized)
        - Auto-fetch is enabled (not yet initialized)
        - Proxies are configured via environment variables (not yet initialized)

        Returns False if:
        - Initialization completed but found no working proxies
        - No proxy configuration provided

        Returns:
            True if proxies are configured or will be available
        """
        # Already have proxies loaded
        if len(self._proxies) > 0:
            return True

        # If initialization already happened but found no proxies, disabled
        if self._initialized:
            return False

        # Have proxies to load
        if self._provided_proxies:
            return True

        # Will auto-fetch proxies
        if self._auto_fetch:
            return True

        # Check environment variables
        if os.environ.get("PROXY_LIST") or os.environ.get("PROXY_CONFIG_PATH"):
            return True

        return False
