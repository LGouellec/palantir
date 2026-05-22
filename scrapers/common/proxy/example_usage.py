"""
Example usage of ProxyRotator with auto-fetch functionality.

This script demonstrates:
1. Auto-fetching proxies from free lists
2. Manual proxy configuration
3. Using environment variables
4. Health tracking and rotation strategies
"""
import asyncio
import logging
import os
from common import ProxyRotator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_auto_fetch():
    """Example: Auto-fetch proxies from free proxy list."""
    logger.info("=== Example 1: Auto-Fetch Proxies ===")

    # Enable auto-fetch mode
    rotator = ProxyRotator(
        auto_fetch_proxies=True,
        auto_fetch_max_proxies=20,  # Limit to 20 validated proxies
        max_requests_per_minute=60,
        max_consecutive_failures=3
    )

    # Get a proxy (initialization happens automatically)
    proxy = await rotator.get_proxy(strategy="round_robin")

    if proxy:
        logger.info(f"Got proxy: {proxy}")

        # Simulate successful request
        await rotator.mark_success(proxy)

        # Get stats
        stats = rotator.get_stats()
        logger.info(f"Healthy proxies: {rotator.get_healthy_count()}/{len(stats)}")
    else:
        logger.warning("No proxies available")


async def example_manual_proxies():
    """Example: Use manually configured proxies."""
    logger.info("=== Example 2: Manual Proxies ===")

    rotator = ProxyRotator(
        proxies=[
            "socks5://proxy1.example.com:1080",
            "socks5://proxy2.example.com:1080",
            "socks5://proxy3.example.com:1080"
        ],
        max_requests_per_minute=100
    )

    # Initialize
    await rotator.initialize()

    # Get multiple proxies using different strategies
    for strategy in ["round_robin", "least_used", "random"]:
        proxy = await rotator.get_proxy(strategy=strategy)
        logger.info(f"Strategy '{strategy}': {proxy}")


async def example_env_variables():
    """Example: Use environment variables for configuration."""
    logger.info("=== Example 3: Environment Variables ===")

    # Set environment variables
    os.environ["PROXY_AUTO_FETCH"] = "true"
    os.environ["PROXY_AUTO_FETCH_MAX"] = "10"
    os.environ["PROXY_MAX_RPM"] = "120"
    os.environ["PROXY_CACHE_TTL"] = "7200"  # 2 hours

    rotator = ProxyRotator()

    # Check if auto-fetch is enabled
    if rotator._auto_fetch:
        logger.info("Auto-fetch is enabled via environment variable")

    await rotator.initialize()

    if rotator.is_enabled():
        proxy = await rotator.get_proxy()
        logger.info(f"Got proxy: {proxy}")


async def example_health_tracking():
    """Example: Health tracking and failure handling."""
    logger.info("=== Example 4: Health Tracking ===")

    rotator = ProxyRotator(
        proxies=[
            "socks5://proxy1.example.com:1080",
            "socks5://proxy2.example.com:1080"
        ],
        max_consecutive_failures=2  # Mark unhealthy after 2 failures
    )

    await rotator.initialize()

    # Simulate some requests with failures
    for i in range(5):
        proxy = await rotator.get_proxy()

        if proxy:
            if i % 2 == 0:
                # Simulate success
                logger.info(f"Request {i}: SUCCESS with {proxy}")
                await rotator.mark_success(proxy)
            else:
                # Simulate failure
                logger.info(f"Request {i}: FAILURE with {proxy}")
                await rotator.mark_failure(proxy, Exception("Connection timeout"))

    # Print stats
    logger.info("\nProxy Stats:")
    stats = rotator.get_stats()
    for proxy, stat in stats.items():
        logger.info(
            f"  {proxy}: "
            f"healthy={stat['healthy']}, "
            f"requests={stat['total_requests']}, "
            f"failures={stat['consecutive_failures']}"
        )


async def example_real_world_usage():
    """Example: Real-world usage pattern for scraping."""
    logger.info("=== Example 5: Real-World Usage ===")

    # Initialize rotator with auto-fetch
    rotator = ProxyRotator(
        auto_fetch_proxies=True,
        auto_fetch_max_proxies=30,
        max_requests_per_minute=60
    )

    # Simulate scraping multiple pages
    urls = [f"https://example.com/page{i}" for i in range(10)]

    for url in urls:
        # Get next proxy
        proxy = await rotator.get_proxy()

        if not proxy:
            logger.warning("No proxies available, waiting...")
            await asyncio.sleep(5)
            continue

        try:
            # Simulate HTTP request (replace with actual aiohttp request)
            logger.info(f"Fetching {url} via {proxy}")
            # response = await session.get(url, proxy=proxy)

            # Mark success
            await rotator.mark_success(proxy)

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            await rotator.mark_failure(proxy, e)

    # Final stats
    logger.info(f"\nFinal healthy proxies: {rotator.get_healthy_count()}")


async def main():
    """Run all examples."""

    # Uncomment the examples you want to run:

    # Note: Auto-fetch examples will download and test proxies from the internet
    # This can take several minutes depending on the proxy list size

    # await example_auto_fetch()
    await example_manual_proxies()
    # await example_env_variables()
    await example_health_tracking()
    # await example_real_world_usage()


if __name__ == "__main__":
    asyncio.run(main())
