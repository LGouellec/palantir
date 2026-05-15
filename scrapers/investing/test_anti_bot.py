#!/usr/bin/env python3
"""
Anti-bot stress test for Investing.com scraper
Scrapes the same article 100 times to test for blocking
"""

import time
import sys
from pathlib import Path
from datetime import datetime
from investing_scraper_stealth import InvestingScraperStealth


def test_anti_bot_protection(url: str, iterations: int = 100, headless: bool = True):
    """
    Test scraper by fetching the same article multiple times

    Args:
        url: Article URL to scrape
        iterations: Number of times to scrape (default: 100)
        headless: Run browser in headless mode for speed (default: True)
    """
    print(f"🧪 Anti-bot Protection Test")
    print(f"=" * 60)
    print(f"URL: {url}")
    print(f"Iterations: {iterations}")
    print(f"=" * 60)
    print()

    # Create test output directory
    test_output = Path("test_output")
    test_output.mkdir(exist_ok=True)

    # Create scraper instance
    # NOTE: headless=True is 3-5x faster than headless=False
    scraper = InvestingScraperStealth(
        output_dir="test_output",
        headless=headless,
        verbose=True,  # Reduce noise
        category="commodities-news",
        history_file="test_history.json"
    )

    # Track results
    successes = 0
    failures = 0
    errors = []
    start_time = time.time()

    print("Starting scrape test...\n")

    for i in range(1, iterations + 1):
        iteration_start = time.time()

        # Optional: Refresh browser context every 50 iterations to prevent memory buildup
        # (Only needed for very long tests, adds ~3s overhead per refresh)
        if i > 1 and i % 50 == 0:
            print(f"[{i:3d}/{iterations}] 🔄 Refreshing browser context...")
            try:
                scraper._cleanup_browser_context()
            except Exception as e:
                print(f"   Warning: Cleanup failed: {e}")

        try:
            # Scrape the article
            article_data = scraper.scrape_article(url, article_metadata={'id': f'test-{i}'})

            if article_data and article_data.get('content'):
                word_count = article_data.get('word_count', 0)

                if word_count > 50:
                    # Save as markdown with iteration number
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = test_output / f"iteration_{i:03d}_{timestamp}.md"

                    markdown_content = scraper.to_markdown(article_data)
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(markdown_content)

                    successes += 1
                    elapsed = time.time() - iteration_start

                    # Progress indicator (print every 10 iterations)
                    if i % 10 == 0:
                        success_rate = (successes / i) * 100
                        print(f"[{i:3d}/{iterations}] ✅ Success | "
                              f"Rate: {success_rate:.1f}% | "
                              f"Time: {elapsed:.2f}s | "
                              f"Words: {word_count}")
                else:
                    failures += 1
                    errors.append((i, f"Low word count: {word_count} (paywalled?)"))
                    print(f"[{i:3d}/{iterations}] ⚠️  Low content ({word_count} words)")
            else:
                failures += 1
                errors.append((i, "No content extracted"))
                print(f"[{i:3d}/{iterations}] ❌ No content")

        except Exception as e:
            failures += 1
            error_msg = str(e)
            errors.append((i, error_msg))

            # Check for blocking indicators
            if '403' in error_msg or 'Forbidden' in error_msg:
                print(f"[{i:3d}/{iterations}] 🚫 BLOCKED (403)")
            elif '429' in error_msg or 'Too Many' in error_msg:
                print(f"[{i:3d}/{iterations}] 🚫 RATE LIMITED (429)")
            else:
                print(f"[{i:3d}/{iterations}] ❌ Error: {error_msg[:50]}")

        # Small delay between requests
        # Note: Can be reduced or removed for stress testing, but be respectful to the server
        if i < iterations:
            time.sleep(0.2)  # Reduced from 0.5s for faster testing

    # Calculate statistics
    total_time = time.time() - start_time
    success_rate = (successes / iterations) * 100
    avg_time_per_scrape = total_time / iterations

    # Print summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    print(f"Total iterations:     {iterations}")
    print(f"Successful scrapes:   {successes} ({success_rate:.1f}%)")
    print(f"Failed scrapes:       {failures}")
    print(f"Total time:           {total_time:.2f}s")
    print(f"Avg time per scrape:  {avg_time_per_scrape:.2f}s")
    print(f"Output directory:     {test_output.absolute()}")
    print()

    # Analyze errors
    if errors:
        print("❌ Errors Encountered:")

        # Count error types
        error_types = {}
        for _, error in errors:
            error_key = error.split(':')[0] if ':' in error else error
            error_types[error_key] = error_types.get(error_key, 0) + 1

        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {error_type}: {count} times")

        # Show first few errors
        print("\n   First errors:")
        for iteration, error in errors[:5]:
            print(f"   [{iteration:3d}] {error}")

    # Check for blocking patterns
    blocked_403 = sum(1 for _, e in errors if '403' in e or 'Forbidden' in e)
    blocked_429 = sum(1 for _, e in errors if '429' in e or 'Too Many' in e)

    if blocked_403 > 0 or blocked_429 > 0:
        print("\n⚠️  BLOCKING DETECTED:")
        if blocked_403 > 0:
            print(f"   - 403 Forbidden errors: {blocked_403}")
        if blocked_429 > 0:
            print(f"   - 429 Rate limit errors: {blocked_429}")
    else:
        print("\n✅ NO BLOCKING DETECTED")
        if success_rate >= 90:
            print("   Scraper appears to be working reliably!")
        elif success_rate >= 70:
            print("   Scraper mostly working but some issues detected")
        else:
            print("   Low success rate - investigate errors above")

    print("=" * 60)

    return {
        'iterations': iterations,
        'successes': successes,
        'failures': failures,
        'success_rate': success_rate,
        'total_time': total_time,
        'avg_time': avg_time_per_scrape,
        'errors': errors,
        'blocked_403': blocked_403,
        'blocked_429': blocked_429
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Anti-bot stress test for Investing.com scraper')
    parser.add_argument('--iterations', '-n', type=int, default=100,
                        help='Number of times to scrape (default: 100)')
    parser.add_argument('--url', default="https://www.investing.com/news/commodities-news/oil-set-for-weekly-surge-as-hormuz-risks-persist-trumpxi-talks-in-focus-4690975",
                        help='Article URL to test')
    parser.add_argument('--visible', action='store_true',
                        help='Show browser (slower but useful for debugging)')
    args = parser.parse_args()

    # Update the scraper creation in test_anti_bot_protection to accept headless parameter
    # For now, just run with the URL and iterations
    test_url = args.url

    # Run test
    try:
        results = test_anti_bot_protection(
            test_url,
            iterations=args.iterations,
            headless=not args.visible  # visible=True means headless=False
        )

        # Exit with appropriate code
        if results['success_rate'] >= 90:
            sys.exit(0)  # Success
        elif results['blocked_403'] > 0 or results['blocked_429'] > 0:
            sys.exit(2)  # Blocking detected
        else:
            sys.exit(1)  # Other failures

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        sys.exit(1)
