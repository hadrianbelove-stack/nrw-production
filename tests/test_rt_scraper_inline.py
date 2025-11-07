#!/usr/bin/env python3
"""
Test script for inlined RT scraping functionality
Verifies RT scraping works correctly after being inlined into generate_data.py
"""

import sys
import os
import json
import time
from datetime import datetime

def test_rt_scraper_inline():
    """Test inlined RT scraping functionality"""

    print("============================================================")
    print("RT SCRAPER INLINE TEST")
    print("============================================================")

    try:
        # Import DataGenerator
        from generate_data import DataGenerator

        # Initialize generator
        print("Initializing DataGenerator...")
        generator = DataGenerator()

        # Test movies with known RT pages
        test_cases = [
            ("Landmarks", 2025, "Known to have RT page with 92% score (cached)"),
            ("Inspector Zende", 2025, "Known to have RT page (cached)"),
            ("The Substance", 2024, "Popular movie, should have RT page"),
            ("Fake Movie Title", 2025, "Should fail gracefully")
        ]

        results = []

        for i, (title, year, description) in enumerate(test_cases, 1):
            print(f"\nTest {i}: {title} ({year})")
            print("------------------------------------------------------------")
            print(f"  {description}")

            start_time = time.time()

            # Test find_rt_url method
            try:
                result = generator.find_rt_url(title, year, None)
                end_time = time.time()
                duration = end_time - start_time

                if result and result.get('url'):
                    if 'search?search=' in result['url']:
                        print(f"  ✗ No RT page found")
                        print(f"  Fallback: {result['url']}")
                        success = False
                    else:
                        print(f"  ✓ Found RT: {result['url']} (Score: {result.get('score', 'N/A')})")
                        success = True
                else:
                    print(f"  ✗ Failed to get result")
                    success = False

                print(f"  Time: {duration:.3f}s")

                results.append({
                    'title': title,
                    'year': year,
                    'success': success,
                    'duration': duration,
                    'result': result
                })

            except Exception as e:
                print(f"  ✗ Error: {e}")
                results.append({
                    'title': title,
                    'year': year,
                    'success': False,
                    'duration': time.time() - start_time,
                    'error': str(e)
                })

        # Print summary
        print("\n============================================================")
        print("SUMMARY")
        print("============================================================")

        total_tests = len(results)
        successful_tests = sum(1 for r in results if r['success'])
        failed_tests = total_tests - successful_tests

        # Calculate statistics from generator
        cache_hits = generator.watchmode_stats['rt_cache_hits']
        scraping_attempts = generator.watchmode_stats['rt_attempts']
        scraping_successes = generator.watchmode_stats['rt_successes']

        print(f"Total tests: {total_tests}")
        print(f"Cache hits: {cache_hits}")
        print(f"Scraping attempts: {scraping_attempts}")
        print(f"Successes: {successful_tests}")
        print(f"Failures: {failed_tests}")

        if scraping_attempts > 0:
            success_rate = (scraping_successes / scraping_attempts * 100)
            print(f"Success rate: {success_rate:.1f}%")

        # Rate limiting analysis
        scrape_times = [r['duration'] for r in results if r.get('duration', 0) > 1]  # Filter cache hits
        if len(scrape_times) > 1:
            min_delay = min(scrape_times[1:])  # Skip first scrape (no rate limit)
            avg_delay = sum(scrape_times) / len(scrape_times)
            print(f"\nRate limiting:")
            print(f"  Average delay between scrapes: {avg_delay:.1f}s")
            print(f"  Min delay: {min_delay:.1f}s {'✓' if min_delay >= 2.0 else '✗'}")

        # Statistics verification
        print(f"\nStatistics:")
        print(f"  rt_attempts: {generator.watchmode_stats['rt_attempts']}")
        print(f"  rt_successes: {generator.watchmode_stats['rt_successes']}")
        print(f"  rt_cache_hits: {generator.watchmode_stats['rt_cache_hits']}")

        # Cleanup
        if hasattr(generator, 'rt_driver') and generator.rt_driver and generator.rt_driver is not False:
            try:
                generator.rt_driver.quit()
                print(f"\n✓ RT driver cleanup successful")
            except Exception as e:
                print(f"\n✗ RT driver cleanup failed: {e}")

        print(f"\n{'✅ All tests completed successfully' if failed_tests == 0 else '⚠️  Some tests failed'}")

    except ImportError as e:
        print(f"✗ Failed to import DataGenerator: {e}")
        print("Make sure generate_data.py is in the current directory")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

    return failed_tests == 0


def test_cache_behavior():
    """Test cache hit/miss behavior specifically"""
    print("\n============================================================")
    print("CACHE BEHAVIOR TEST")
    print("============================================================")

    try:
        from generate_data import DataGenerator
        generator = DataGenerator()

        test_title = "The Substance"
        test_year = 2024

        print(f"Testing cache behavior with: {test_title} ({test_year})")

        # First call - should be cache hit or scrape
        print("\n1. First call:")
        start_time = time.time()
        result1 = generator.find_rt_url(test_title, test_year, None)
        time1 = time.time() - start_time
        print(f"   Result: {result1}")
        print(f"   Time: {time1:.3f}s")

        # Second call - should be cache hit
        print("\n2. Second call (should be cache hit):")
        start_time = time.time()
        result2 = generator.find_rt_url(test_title, test_year, None)
        time2 = time.time() - start_time
        print(f"   Result: {result2}")
        print(f"   Time: {time2:.3f}s")

        # Verify cache hit
        if time2 < 0.1:  # Cache hits should be very fast
            print("   ✓ Cache hit confirmed (fast response)")
        else:
            print("   ✗ Cache hit expected but took too long")

        # Verify results are identical
        if result1 == result2:
            print("   ✓ Results are identical")
        else:
            print("   ✗ Results differ between calls")

        # Cleanup
        if hasattr(generator, 'rt_driver') and generator.rt_driver and generator.rt_driver is not False:
            generator.rt_driver.quit()

    except Exception as e:
        print(f"✗ Cache test error: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test inlined RT scraper functionality")
    parser.add_argument("--visible", action="store_true", help="Run with visible browser (for debugging selectors)")
    parser.add_argument("--cache-test", action="store_true", help="Run cache behavior test only")

    args = parser.parse_args()

    if args.visible:
        print("Note: --visible flag not implemented yet (all tests run in headless mode)")

    if args.cache_test:
        test_cache_behavior()
    else:
        success = test_rt_scraper_inline()
        if not success:
            test_cache_behavior()

        sys.exit(0 if success else 1)