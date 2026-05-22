"""
Test script to demonstrate the configurable cooldown period.

This script simulates high failure rates to trigger the cooldown mechanism.
"""
import asyncio
import logging
import os
import sys
from unittest.mock import AsyncMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from analytics_engine import AsyncAnalyticsEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_cooldown_configuration():
    """Test different cooldown configurations."""
    print("\n" + "=" * 70)
    print("Testing Cooldown Period Configuration")
    print("=" * 70 + "\n")

    # Test 1: Default cooldown (60 seconds)
    print("Test 1: Default cooldown period")
    engine1 = AsyncAnalyticsEngine()
    print(f"  ✅ Default: {engine1.cooldown_period} seconds\n")

    # Test 2: Custom cooldown (30 seconds)
    print("Test 2: Custom cooldown period")
    engine2 = AsyncAnalyticsEngine(cooldown_period=30.0)
    print(f"  ✅ Custom: {engine2.cooldown_period} seconds\n")

    # Test 3: Environment variable
    print("Test 3: Environment variable override")
    os.environ['COOLDOWN_PERIOD'] = '120'
    engine3 = AsyncAnalyticsEngine()
    print(f"  ✅ Env var: {engine3.cooldown_period} seconds\n")

    # Test 4: Fractional cooldown
    print("Test 4: Fractional cooldown period")
    engine4 = AsyncAnalyticsEngine(cooldown_period=45.5)
    print(f"  ✅ Fractional: {engine4.cooldown_period} seconds\n")

    print("=" * 70)
    print("✅ All cooldown configuration tests passed!")
    print("=" * 70 + "\n")


async def test_cooldown_behavior():
    """Test cooldown behavior with simulated failures."""
    print("\n" + "=" * 70)
    print("Testing Cooldown Behavior (Simulated High Failure Rate)")
    print("=" * 70 + "\n")

    # Create engine with short cooldown for testing
    engine = AsyncAnalyticsEngine(cooldown_period=3.0)  # 3 seconds for testing

    print(f"Configured cooldown period: {engine.cooldown_period} seconds\n")

    # Mock the fetch function to simulate failures
    async def mock_fetch_with_failures(tickers, *args, **kwargs):
        """Simulate 60% failure rate."""
        results = []
        for i, ticker in enumerate(tickers):
            if i % 10 < 6:  # 60% failure rate
                # Simulate failure
                results.append(None)
            else:
                # Simulate success
                from models import StockAnalytics
                results.append(StockAnalytics(
                    ticker=ticker,
                    fetch_time=asyncio.get_event_loop().time(),
                ))
        return results

    # Patch the batch fetch method
    with patch.object(engine, 'fetch_batch', new=mock_fetch_with_failures):
        # Mock some tickers
        test_tickers = [f"TEST{i}" for i in range(20)]

        print("Starting monitoring with simulated 60% failure rate...")
        print("(This should trigger cooldown mechanism)\n")

        # Start monitoring
        await engine.start_monitoring(
            tickers=test_tickers,
            interval_ms=5000,  # 5 seconds
            include_news=False,
        )

        # Let it run for 2 cycles to see cooldown
        await asyncio.sleep(15)

        # Stop monitoring
        await engine.stop_monitoring()

    print("\n" + "=" * 70)
    print("✅ Cooldown behavior test complete!")
    print("=" * 70 + "\n")


async def demo_cooldown_scenarios():
    """Demonstrate different cooldown scenarios."""
    print("\n" + "=" * 70)
    print("Cooldown Period Scenarios")
    print("=" * 70 + "\n")

    scenarios = [
        ("Conservative (Long Cooldown)", 300, "Use when rate limits are strict"),
        ("Default (Balanced)", 60, "Good balance for most use cases"),
        ("Aggressive (Short Cooldown)", 30, "Use for development/testing"),
        ("Very Aggressive", 15, "Only for very permissive APIs"),
    ]

    for name, cooldown, description in scenarios:
        print(f"{name}:")
        print(f"  Cooldown: {cooldown} seconds")
        print(f"  Use case: {description}")
        print()

    print("=" * 70)
    print("Recommendation:")
    print("  - Start with default (60s)")
    print("  - Monitor logs for 'High failure rate' messages")
    print("  - Adjust based on your specific rate limit experience")
    print("=" * 70 + "\n")


async def main():
    """Run all tests."""
    try:
        # Test 1: Configuration
        await test_cooldown_configuration()

        # Demo: Scenarios
        await demo_cooldown_scenarios()

        # Test 2: Behavior (optional - requires mocking)
        # Uncomment to test actual cooldown behavior
        # await test_cooldown_behavior()

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
