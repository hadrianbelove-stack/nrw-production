#!/usr/bin/env python3
"""
Comprehensive test script for the Playwright-based platform scraper.

Tests Amazon and Apple TV scraping with validation for:
- Direct method testing (find_amazon_link, find_apple_tv_link)
- Platform routing testing (get_platform_deep_link)
- Placeholder ASIN detection
- Performance measurement
- Success rate calculation

Usage:
    python3 test_platform_scraper.py [--headless] [--debug]

Args:
    --headless: Run browser in headless mode (default: visible for debugging)
    --debug: Enable verbose debug output
"""

import sys
import time
import argparse
from streaming_platform_scraper import StreamingPlatformScraper
from constants import PLACEHOLDER_ASINS


def check_dependencies():
    """Check if Playwright is properly installed."""
    try:
        from playwright.sync_api import sync_playwright
        print("✓ Playwright dependencies found")
        return True
    except ImportError as e:
        print(f"✗ Playwright not installed: {e}")
        print("Please install Playwright with: pip install playwright && playwright install chromium")
        return False


def validate_result(url, platform_name, movie_title):
    """Validate scraping result for correctness."""
    if not url:
        return {"valid": False, "reason": "No URL returned"}

    # Check for placeholder ASINs
    for asin in PLACEHOLDER_ASINS:
        if asin in url:
            return {"valid": False, "reason": f"Contains placeholder ASIN {asin}"}

    # Validate URL format
    if platform_name == "Amazon":
        if "amazon.com" not in url or ("/gp/video/detail/" not in url and "/dp/" not in url):
            return {"valid": False, "reason": "Invalid Amazon URL format"}
    elif platform_name == "Apple TV":
        if "tv.apple.com" not in url or "umc.cmc" not in url:
            return {"valid": False, "reason": "Invalid Apple TV URL format"}

    return {"valid": True, "reason": "Valid URL"}


def test_platform_scraper_smoke():
    """
    Lightweight smoke test for platform scraper with deterministic known titles.
    Uses 2-3 stable, older titles known to exist on Amazon/Apple.
    """
    print("Running deterministic platform scraper smoke test...")

    # Use older, stable titles from studio catalogs / public domain
    stable_test_movies = [
        ("The Godfather", "1972"),  # Classic title, widely available
        ("Jaws", "1975"),           # Universal catalog title
        ("Casablanca", "1942")      # Classic, public domain
    ]

    scraper = None
    results = {"amazon": 0, "apple": 0, "total": 0}

    try:
        # Initialize with minimal config for CI
        scraper = StreamingPlatformScraper(
            headless=True,
            timeout_seconds=10,
            screenshots_enabled=False
        )

        for title, year in stable_test_movies:
            results["total"] += 1
            print(f"Testing: {title} ({year})")

            # Test Amazon
            amazon_result = scraper.get_platform_deep_link(title, year, "Amazon Video")
            if amazon_result and "amazon.com" in amazon_result and all(asin not in amazon_result for asin in PLACEHOLDER_ASINS):
                results["amazon"] += 1
                print(f"  ✓ Amazon: Found valid link")
            else:
                print(f"  ✗ Amazon: No valid link")

            # Test Apple TV
            apple_result = scraper.get_platform_deep_link(title, year, "Apple TV")
            if apple_result and "tv.apple.com" in apple_result:
                results["apple"] += 1
                print(f"  ✓ Apple TV: Found valid link")
            else:
                print(f"  ✗ Apple TV: No valid link")

    except Exception as e:
        print(f"Error in smoke test: {e}")
        return False

    finally:
        if scraper:
            scraper.close()

    # Pass if at least one platform found at least one valid link
    success = results["amazon"] > 0 or results["apple"] > 0
    print(f"Smoke test result: {results['amazon']} Amazon + {results['apple']} Apple successes out of {results['total']} movies")
    return success


def test_platform_scraper(headless=False, debug=False, max_amazon_tests=None, max_apple_tests=None):
    """Main test function for platform scraper.

    Args:
        headless: Run browser in headless mode
        debug: Enable verbose debug output
        max_amazon_tests: Limit number of Amazon tests (None = all)
        max_apple_tests: Limit number of Apple TV tests (None = all)
    """
    print("="*80)
    print("PLATFORM SCRAPER TEST - PLAYWRIGHT VERSION")
    print("="*80)

    # Test configuration
    test_timeout = 15  # seconds per search
    scraper = None

    # Test data - expanded to 10-20 recent titles for comprehensive verification
    amazon_test_movies = [
        # 2025 releases
        ("Afterburn", "2025"),
        ("Pet Shop Days", "2025"),
        ("The Eichmann Trial", "2025"),
        ("Little Brother", "2025"),
        ("Captain America: Brave New World", "2025"),
        ("Thunderbolts", "2025"),
        ("Karate Kid: Legends", "2025"),
        # 2024 releases (for broader validation)
        ("Dune: Part Two", "2024"),
        ("Deadpool & Wolverine", "2024"),
        ("Inside Out 2", "2024"),
        ("Moana 2", "2024"),
        ("Wicked", "2024"),
        ("Gladiator II", "2024"),
        ("Beetlejuice Beetlejuice", "2024"),
        ("The Wild Robot", "2024")
    ]

    apple_test_movies = [
        # 2025 releases
        ("Afterburn", "2025"),
        ("Pet Shop Days", "2025"),
        ("Captain America: Brave New World", "2025"),
        ("Thunderbolts", "2025"),
        # 2024 releases
        ("Dune: Part Two", "2024"),
        ("Inside Out 2", "2024"),
        ("Moana 2", "2024"),
        ("Wicked", "2024"),
        ("The Wild Robot", "2024")
    ]

    # Apply test limits if specified
    if max_amazon_tests is not None:
        amazon_test_movies = amazon_test_movies[:max_amazon_tests]
    if max_apple_tests is not None:
        apple_test_movies = apple_test_movies[:max_apple_tests]

    print(f"Testing {len(amazon_test_movies)} Amazon movies and {len(apple_test_movies)} Apple TV movies")

    # Statistics tracking
    stats = {
        "amazon": {"success": 0, "total": 0, "errors": 0, "times": []},
        "apple": {"success": 0, "total": 0, "errors": 0, "times": []},
        "routing": {"success": 0, "total": 0, "errors": 0},
        "placeholder_violations": [],
        "duplicate_asins": set(),
        "all_results": []
    }

    try:
        print(f"Initializing scraper (headless={headless}, timeout={test_timeout}s)...")
        scraper = StreamingPlatformScraper(
            headless=headless,
            timeout_seconds=test_timeout,
            rate_limit_seconds=2.0
        )
        print("✓ Scraper initialized successfully\n")

        # Test 1: Amazon Direct Method Testing
        print("="*60)
        print("TEST 1: AMAZON DIRECT METHOD TESTING")
        print("="*60)

        for title, year in amazon_test_movies:
            print(f"\nTesting: {title} ({year})")
            print("-" * 40)

            start_time = time.time()
            stats["amazon"]["total"] += 1

            try:
                result = scraper.find_amazon_link(title, year)
                search_time = time.time() - start_time
                stats["amazon"]["times"].append(search_time)

                validation = validate_result(result, "Amazon", title)

                if result and validation["valid"]:
                    stats["amazon"]["success"] += 1
                    stats["all_results"].append(result)

                    # Check for ASIN duplicates
                    if "amazon.com" in result:
                        asin_part = result.split("/")[-1] if "/" in result else result
                        if asin_part in stats["duplicate_asins"]:
                            print(f"  ⚠️  Duplicate ASIN detected: {asin_part}")
                        stats["duplicate_asins"].add(asin_part)

                    print(f"  ✓ SUCCESS: {result}")
                    print(f"  ✓ Time: {search_time:.2f}s")
                elif result:
                    print(f"  ✗ INVALID: {result}")
                    print(f"  ✗ Reason: {validation['reason']}")
                    if "placeholder" in validation["reason"].lower():
                        stats["placeholder_violations"].append((title, year, result))
                else:
                    print(f"  ✗ NO RESULT FOUND")

            except Exception as e:
                stats["amazon"]["errors"] += 1
                search_time = time.time() - start_time
                print(f"  ✗ ERROR: {e}")
                print(f"  ✗ Time: {search_time:.2f}s")
                if debug:
                    import traceback
                    traceback.print_exc()

        # Test 2: Apple TV Direct Method Testing
        print("\n\n" + "="*60)
        print("TEST 2: APPLE TV DIRECT METHOD TESTING")
        print("="*60)

        for title, year in apple_test_movies:
            print(f"\nTesting: {title} ({year})")
            print("-" * 40)

            start_time = time.time()
            stats["apple"]["total"] += 1

            try:
                result = scraper.find_apple_tv_link(title, year)
                search_time = time.time() - start_time
                stats["apple"]["times"].append(search_time)

                validation = validate_result(result, "Apple TV", title)

                if result and validation["valid"]:
                    stats["apple"]["success"] += 1
                    stats["all_results"].append(result)
                    print(f"  ✓ SUCCESS: {result}")
                    print(f"  ✓ Time: {search_time:.2f}s")
                elif result:
                    print(f"  ✗ INVALID: {result}")
                    print(f"  ✗ Reason: {validation['reason']}")
                else:
                    print(f"  ✗ NO RESULT FOUND")

            except Exception as e:
                stats["apple"]["errors"] += 1
                search_time = time.time() - start_time
                print(f"  ✗ ERROR: {e}")
                print(f"  ✗ Time: {search_time:.2f}s")
                if debug:
                    import traceback
                    traceback.print_exc()

        # Test 3: Platform Routing Testing
        print("\n\n" + "="*60)
        print("TEST 3: PLATFORM ROUTING TESTING")
        print("="*60)

        routing_tests = [
            ("Afterburn", "2025", "Amazon Video"),
            ("Pet Shop Days", "2025", "Amazon Prime Video"),
            ("Afterburn", "2025", "Apple TV"),
            ("Unknown Movie", "2025", "Netflix"),  # Should return None (unsupported)
        ]

        for title, year, service in routing_tests:
            print(f"\nTesting: {title} ({year}) on {service}")
            print("-" * 50)

            stats["routing"]["total"] += 1

            try:
                result = scraper.get_platform_deep_link(title, year, service)

                if service in ["Netflix", "Disney+", "Hulu"]:
                    # Unsupported platforms should return None
                    if result is None:
                        stats["routing"]["success"] += 1
                        print(f"  ✓ EXPECTED: None (unsupported platform)")
                    else:
                        print(f"  ✗ UNEXPECTED: Got result for unsupported platform: {result}")
                else:
                    # Supported platforms
                    validation = validate_result(result, service.split()[0], title)
                    if result and validation["valid"]:
                        stats["routing"]["success"] += 1
                        print(f"  ✓ SUCCESS: {result}")
                    elif result:
                        print(f"  ✗ INVALID: {result}")
                        print(f"  ✗ Reason: {validation['reason']}")
                    else:
                        print(f"  ✗ NO RESULT FOUND")

            except Exception as e:
                stats["routing"]["errors"] += 1
                print(f"  ✗ ERROR: {e}")
                if debug:
                    import traceback
                    traceback.print_exc()

    finally:
        if scraper:
            print("\nCleaning up browser...")
            scraper.close()
            print("✓ Browser closed")

    # Test Results Summary
    print("\n\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)

    # Amazon Results
    amazon_success_rate = (stats["amazon"]["success"] / stats["amazon"]["total"] * 100) if stats["amazon"]["total"] > 0 else 0
    amazon_avg_time = sum(stats["amazon"]["times"]) / len(stats["amazon"]["times"]) if stats["amazon"]["times"] else 0

    print(f"\nAMAZON SCRAPING:")
    print(f"  Success Rate: {stats['amazon']['success']}/{stats['amazon']['total']} ({amazon_success_rate:.1f}%)")
    print(f"  Average Time: {amazon_avg_time:.2f}s per search")
    print(f"  Errors: {stats['amazon']['errors']}")

    # Apple TV Results
    apple_success_rate = (stats["apple"]["success"] / stats["apple"]["total"] * 100) if stats["apple"]["total"] > 0 else 0
    apple_avg_time = sum(stats["apple"]["times"]) / len(stats["apple"]["times"]) if stats["apple"]["times"] else 0

    print(f"\nAPPLE TV SCRAPING:")
    print(f"  Success Rate: {stats['apple']['success']}/{stats['apple']['total']} ({apple_success_rate:.1f}%)")
    print(f"  Average Time: {apple_avg_time:.2f}s per search")
    print(f"  Errors: {stats['apple']['errors']}")

    # Routing Results
    routing_success_rate = (stats["routing"]["success"] / stats["routing"]["total"] * 100) if stats["routing"]["total"] > 0 else 0

    print(f"\nPLATFORM ROUTING:")
    print(f"  Success Rate: {stats['routing']['success']}/{stats['routing']['total']} ({routing_success_rate:.1f}%)")
    print(f"  Errors: {stats['routing']['errors']}")

    # Overall Performance
    total_searches = stats["amazon"]["total"] + stats["apple"]["total"]
    total_successes = stats["amazon"]["success"] + stats["apple"]["success"]
    overall_success_rate = (total_successes / total_searches * 100) if total_searches > 0 else 0

    all_times = stats["amazon"]["times"] + stats["apple"]["times"]
    overall_avg_time = sum(all_times) / len(all_times) if all_times else 0

    print(f"\nOVERALL PERFORMANCE:")
    print(f"  Total Success Rate: {total_successes}/{total_searches} ({overall_success_rate:.1f}%)")
    print(f"  Average Time per Search: {overall_avg_time:.2f}s")
    print(f"  Performance vs Selenium: ~{((10.0 - overall_avg_time) / 10.0 * 100):.0f}% faster (baseline: 10s)")

    # Validation Results
    print(f"\nVALIDATION RESULTS:")
    print(f"  Placeholder ASIN Violations: {len(stats['placeholder_violations'])}")
    if stats["placeholder_violations"]:
        for title, year, url in stats["placeholder_violations"]:
            print(f"    - {title} ({year}): {url}")

    print(f"  Unique ASINs Found: {len(stats['duplicate_asins'])}")
    print(f"  Total Results Generated: {len(stats['all_results'])}")

    # Performance Benchmarks
    print(f"\nPERFORMANCE BENCHMARKS:")
    print(f"  Target: 6-8 seconds per search")
    print(f"  Actual: {overall_avg_time:.2f} seconds per search")

    if overall_avg_time <= 8:
        print(f"  ✓ PASSED: Within target performance range")
    else:
        print(f"  ✗ FAILED: Exceeds target performance")

    if len(stats["placeholder_violations"]) == 0:
        print(f"  ✓ PASSED: No placeholder ASINs detected")
    else:
        print(f"  ✗ FAILED: {len(stats['placeholder_violations'])} placeholder ASIN violations")

    # Next Steps
    print(f"\nNEXT STEPS:")
    if overall_success_rate >= 50:  # Reasonable threshold for initial testing
        print("  ✓ Ready for integration testing with generate_data.py")
        print("  ✓ Run: python3 generate_data.py --full --debug")
        print("  ✓ Verify: grep -c 'B0FMPYFP9W\\|B0FNDR5BW5' data.json (should be 0)")
    else:
        print("  ✗ Success rate too low for production use")
        print("  ✗ Review selector strategies and validation logic")

    print("  ▶ Monitor Playwright performance vs Selenium baseline")
    print("  ▶ Consider extracting shared utilities with agent_link_scraper.py")

    return stats


def main():
    """Main entry point for test script."""
    parser = argparse.ArgumentParser(description="Test Playwright-based platform scraper")
    parser.add_argument("--headless", action="store_true",
                       help="Run browser in headless mode (default: visible for debugging)")
    parser.add_argument("--debug", action="store_true",
                       help="Enable verbose debug output")
    parser.add_argument("--max-amazon", type=int, default=None,
                       help="Maximum number of Amazon movies to test (default: all 15)")
    parser.add_argument("--max-apple", type=int, default=None,
                       help="Maximum number of Apple TV movies to test (default: all 9)")
    parser.add_argument("--smoke", action="store_true",
                       help="Run lightweight smoke test only")

    args = parser.parse_args()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Run tests
    try:
        if args.smoke:
            success = test_platform_scraper_smoke()
            if success:
                print("\n✓ SMOKE TEST PASSED")
                sys.exit(0)
            else:
                print("\n✗ SMOKE TEST FAILED")
                sys.exit(1)
        else:
            stats = test_platform_scraper(
                headless=args.headless,
                debug=args.debug,
                max_amazon_tests=args.max_amazon,
                max_apple_tests=args.max_apple
            )

        # Exit code based on success rate
        total_searches = stats["amazon"]["total"] + stats["apple"]["total"]
        total_successes = stats["amazon"]["success"] + stats["apple"]["success"]
        success_rate = (total_successes / total_searches) if total_searches > 0 else 0

        if success_rate >= 0.5 and len(stats["placeholder_violations"]) == 0:
            print("\n✓ TEST SUITE PASSED")
            sys.exit(0)
        else:
            print("\n✗ TEST SUITE FAILED")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nTest suite failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()