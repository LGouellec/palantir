#!/usr/bin/env python3
"""
Example: Synchronous Proxy Rotator API

Demonstrates how to use ProxyRotator from synchronous code,
particularly useful for:
- curl_cffi (synchronous HTTP requests)
- requests library
- Other synchronous web scraping tools

The sync API (_sync methods) allows using the rotator without
needing async/await syntax.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.proxy import ProxyRotator


def example_basic_sync():
    """
    Example 1: Basic synchronous usage.

    Shows how to initialize and use the rotator from sync code.
    """
    print("=" * 70)
    print("Example 1: Basic Synchronous Usage")
    print("=" * 70)

    # Create rotator with auto-fetch
    rotator = ProxyRotator(
        auto_fetch_proxies=True,
        auto_fetch_max_proxies=10
    )

    # Initialize synchronously (blocks until complete)
    print("\n🔄 Initializing proxy rotator...")
    rotator.initialize_sync()

    print(f"✅ Initialized with {rotator.get_healthy_count()} proxies")

    # Get a proxy synchronously
    print("\n🔄 Getting proxy...")
    proxy = rotator.get_proxy_sync()

    if proxy:
        print(f"✅ Got proxy: {proxy}")

        # Mark success
        rotator.mark_success_sync(proxy)
        print("✅ Marked proxy as successful")
    else:
        print("❌ No proxy available")


def example_with_curl_cffi():
    """
    Example 2: Using with curl_cffi.

    Shows real-world usage with curl_cffi requests.
    """
    print("\n" + "=" * 70)
    print("Example 2: Using with curl_cffi")
    print("=" * 70)

    try:
        from curl_cffi import requests
    except ImportError:
        print("⚠️  curl_cffi not installed, skipping example")
        print("   Install with: pip install curl-cffi")
        return

    # Initialize rotator
    rotator = ProxyRotator(
        auto_fetch_proxies=True,
        auto_fetch_max_proxies=5
    )

    print("\n🔄 Initializing...")
    rotator.initialize_sync()
    print(f"✅ Ready with {rotator.get_healthy_count()} proxies")

    # Make a request with proxy rotation
    test_url = "https://httpbin.org/ip"

    for i in range(3):
        print(f"\n[{i+1}] Making request to {test_url}...")

        # Get next proxy
        proxy = rotator.get_proxy_sync(strategy="round_robin")

        if not proxy:
            print("❌ No proxy available")
            continue

        print(f"   Using proxy: {proxy[:50]}...")

        try:
            # Make request with curl_cffi
            response = requests.get(
                test_url,
                proxy=proxy,
                timeout=10,
                impersonate="chrome119"
            )

            if response.status_code == 200:
                print(f"   ✅ Success! IP: {response.json().get('origin', 'N/A')}")
                rotator.mark_success_sync(proxy)
            else:
                print(f"   ❌ Failed with status {response.status_code}")
                rotator.mark_failure_sync(proxy, Exception(f"HTTP {response.status_code}"))

        except Exception as e:
            print(f"   ❌ Error: {str(e)[:50]}...")
            rotator.mark_failure_sync(proxy, e)

    # Show stats
    print("\n📊 Final Statistics:")
    stats = rotator.get_stats()
    for proxy_url, stat in list(stats.items())[:3]:  # Show first 3
        print(f"   {proxy_url[:50]}: {stat['total_requests']} requests, "
              f"{'✅ healthy' if stat['healthy'] else '❌ unhealthy'}")


def example_manual_proxies():
    """
    Example 3: Using with manual proxy list.

    Shows usage with a pre-defined proxy list (no auto-fetch).
    """
    print("\n" + "=" * 70)
    print("Example 3: Manual Proxy List")
    print("=" * 70)

    # Manual proxy list
    proxies = [
        "socks5://proxy1.example.com:1080",
        "socks5://proxy2.example.com:1080",
        "http://proxy3.example.com:8080"
    ]

    rotator = ProxyRotator(proxies=proxies)

    print(f"\n🔄 Initializing with {len(proxies)} manual proxies...")
    rotator.initialize_sync()

    print(f"✅ Initialized with {rotator.get_healthy_count()} proxies")

    # Test rotation strategies
    print("\n🔄 Testing different strategies:")

    for strategy in ["round_robin", "least_used", "random"]:
        proxy = rotator.get_proxy_sync(strategy=strategy)
        if proxy:
            print(f"   {strategy:15s}: {proxy}")


def example_error_handling():
    """
    Example 4: Error handling and health tracking.

    Shows how to handle errors and track proxy health.
    """
    print("\n" + "=" * 70)
    print("Example 4: Error Handling & Health Tracking")
    print("=" * 70)

    rotator = ProxyRotator(
        proxies=[
            "socks5://proxy1.example.com:1080",
            "socks5://proxy2.example.com:1080"
        ],
        max_consecutive_failures=2  # Mark unhealthy after 2 failures
    )

    rotator.initialize_sync()

    print(f"\n📊 Initial state: {rotator.get_healthy_count()} healthy proxies")

    # Simulate some requests with failures
    for i in range(5):
        proxy = rotator.get_proxy_sync()

        if proxy:
            print(f"\n[{i+1}] Using proxy: {proxy}")

            # Simulate alternating success/failure
            if i % 2 == 0:
                print("   ✅ Simulated success")
                rotator.mark_success_sync(proxy)
            else:
                print("   ❌ Simulated failure")
                rotator.mark_failure_sync(proxy, Exception("Connection timeout"))

    # Show final stats
    print("\n📊 Final Health Status:")
    stats = rotator.get_stats()
    for proxy_url, stat in stats.items():
        status = "✅ Healthy" if stat['healthy'] else "❌ Unhealthy"
        print(f"   {proxy_url}: {status} ({stat['consecutive_failures']} failures)")


def example_cache_refresh():
    """
    Example 5: Cache refresh with sync API.

    Shows how to use cache refresh from synchronous code.
    """
    print("\n" + "=" * 70)
    print("Example 5: Cache Refresh (Sync)")
    print("=" * 70)

    rotator = ProxyRotator(
        auto_fetch_proxies=True,
        auto_fetch_max_proxies=5
    )

    print("\n🔄 Initializing...")
    rotator.initialize_sync()

    print(f"✅ Initialized with {rotator.get_healthy_count()} proxies")
    print(f"📊 Cache age: {rotator.get_cache_age():.1f} seconds")

    # Simulate cache aging
    print("\n⏱️  Simulating cache aging (6+ hours)...")
    import time
    rotator._cache_timestamp = time.time() - (6 * 3600 + 1)

    print(f"📊 Cache age: {rotator.get_cache_age() / 3600:.1f} hours")
    print(f"   Cache is stale: {rotator._is_cache_stale()}")

    # Auto-refresh on next get_proxy_sync() call
    print("\n🔄 Getting proxy (will trigger auto-refresh)...")
    proxy = rotator.get_proxy_sync()

    if proxy:
        print(f"✅ Got proxy: {proxy[:50]}...")
        print(f"📊 Cache age after refresh: {rotator.get_cache_age():.1f} seconds")
        print(f"   Total proxies: {rotator.get_healthy_count()}")

    # Manual refresh
    print("\n🔄 Triggering manual refresh...")
    success = rotator.refresh_proxies_sync()

    if success:
        print(f"✅ Manual refresh successful")
        print(f"   Proxies: {rotator.get_healthy_count()}")
    else:
        print("❌ Refresh failed")


def main():
    """Run examples."""
    print("\n" + "=" * 70)
    print("Synchronous Proxy Rotator API - Examples")
    print("=" * 70)

    # Run examples
    # Uncomment the ones you want to test

    example_basic_sync()
    # example_with_curl_cffi()  # Requires curl_cffi and working proxies
    example_manual_proxies()
    example_error_handling()
    # example_cache_refresh()    # Requires auto-fetch (downloads proxies)

    print("\n" + "=" * 70)
    print("✅ Examples complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
