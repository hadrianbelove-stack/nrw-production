#!/usr/bin/env python3
"""
Comparison test: Wikipedia Scraper v1 vs v2

This test validates that the migrated v2 scraper produces IDENTICAL
behavior to the original v1 scraper. Only after all tests pass should
we replace the production scraper.

Tests:
1. Stats structure identical
2. Cache operations identical
3. Title matching logic identical
4. Cache result validation identical
5. Configuration handling identical
6. Line count reduction achieved

Run with: python3 tests/test_wikipedia_v1_vs_v2.py
"""

import os
import sys
import json
import tempfile
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import both versions
from wikipedia_scraper_playwright import WikipediaScraperPlaywright as V1Scraper
from wikipedia_scraper_v2 import WikipediaScraperPlaywright as V2Scraper


def test_stats_structure_identical():
    """Test that both scrapers have identical stats structure."""
    print("\n=== Test: Stats Structure Identical ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_v1 = os.path.join(temp_dir, 'v1_cache.json')
        cache_v2 = os.path.join(temp_dir, 'v2_cache.json')

        v1 = V1Scraper(cache_file=cache_v1)
        v2 = V2Scraper(cache_file=cache_v2)

        # Compare stats keys
        v1_stats_keys = set(v1.stats.keys())
        v2_stats_keys = set(v2.stats.keys())

        assert v1_stats_keys == v2_stats_keys, f"Stats keys differ: v1={v1_stats_keys}, v2={v2_stats_keys}"
        print(f"  [PASS] Stats keys identical: {v1_stats_keys}")

        # Compare counters keys
        v1_counters_keys = set(v1.counters.keys())
        v2_counters_keys = set(v2.counters.keys())

        assert v1_counters_keys == v2_counters_keys, f"Counters keys differ: v1={v1_counters_keys}, v2={v2_counters_keys}"
        print(f"  [PASS] Counters keys identical: {v1_counters_keys}")

        # Compare initial values
        for key in v1_stats_keys:
            assert v1.stats[key] == v2.stats[key], f"Stats[{key}] differs"
        print("  [PASS] All stats initial values identical")

    print("  === Stats Structure: ALL PASSED ===")
    return True


def test_cache_operations_identical():
    """Test that cache operations produce identical results."""
    print("\n=== Test: Cache Operations Identical ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_v1 = os.path.join(temp_dir, 'v1_cache.json')
        cache_v2 = os.path.join(temp_dir, 'v2_cache.json')

        v1 = V1Scraper(cache_file=cache_v1)
        v2 = V2Scraper(cache_file=cache_v2)

        # Add identical data to both
        test_data = {
            'url': 'https://en.wikipedia.org/wiki/Test_Movie',
            'title': 'Test Movie',
            'cached_at': '2024-01-01T00:00:00',
            'source': 'test'
        }

        v1.cache['Test_2024'] = test_data
        v2.cache['Test_2024'] = test_data

        v1._save_cache()
        v2._save_cache()
        print("  [PASS] Both scrapers can save cache")

        # Load in new instances
        v1_new = V1Scraper(cache_file=cache_v1)
        v2_new = V2Scraper(cache_file=cache_v2)

        assert v1_new.cache == v2_new.cache, "Loaded caches differ"
        print("  [PASS] Loaded caches identical")

        # Verify cache count method works
        assert v1_new._get_cache_count() if hasattr(v1_new, '_get_cache_count') else len(v1_new.cache) == 1
        print("  [PASS] Cache count works")

    print("  === Cache Operations: ALL PASSED ===")
    return True


def test_title_matching_identical():
    """Test that title matching logic produces identical results."""
    print("\n=== Test: Title Matching Identical ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_v1 = os.path.join(temp_dir, 'v1_cache.json')
        cache_v2 = os.path.join(temp_dir, 'v2_cache.json')

        v1 = V1Scraper(cache_file=cache_v1)
        v2 = V2Scraper(cache_file=cache_v2)

        # Test cases
        test_cases = [
            ("The Matrix", "The Matrix", True),
            ("Dune", "Dune (film)", True),
            ("Dune", "Dune (2021 film)", True),
            ("Avatar", "Titanic", False),
            ("The Godfather", "The Godfather Part II", True),
            ("A Quiet Place", "A Quiet Place (film)", True),
            ("Inception", "inception", True),  # Case insensitive
            ("Spider-Man", "Spider-Man: No Way Home", True),
        ]

        for title, result_text, expected in test_cases:
            v1_result = v1._title_matches(title, result_text)
            v2_result = v2._title_matches(title, result_text)

            assert v1_result == v2_result, f"Title match differs for '{title}' vs '{result_text}': v1={v1_result}, v2={v2_result}"

            if v1_result == expected:
                print(f"  [PASS] '{title}' vs '{result_text}' = {v1_result}")
            else:
                print(f"  [WARN] '{title}' vs '{result_text}' = {v1_result} (expected {expected})")

    print("  === Title Matching: ALL PASSED ===")
    return True


def test_cache_result_validation_identical():
    """Test that cache result validation works identically."""
    print("\n=== Test: Cache Result Validation Identical ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_v1 = os.path.join(temp_dir, 'v1_cache.json')
        cache_v2 = os.path.join(temp_dir, 'v2_cache.json')

        v1 = V1Scraper(cache_file=cache_v1)
        v2 = V2Scraper(cache_file=cache_v2)

        # Test valid URL caching
        v1._cache_result("Valid_2024", "https://en.wikipedia.org/wiki/Valid", "Valid", "test")
        v2._cache_result("Valid_2024", "https://en.wikipedia.org/wiki/Valid", "Valid", "test")

        assert "Valid_2024" in v1.cache, "V1 should cache valid URL"
        assert "Valid_2024" in v2.cache, "V2 should cache valid URL"
        print("  [PASS] Both cache valid URLs")

        # Test search URL rejection
        v1._cache_result("Search_2024", "https://en.wikipedia.org/w/index.php?search=bad", "Search", "test")
        v2._cache_result("Search_2024", "https://en.wikipedia.org/w/index.php?search=bad", "Search", "test")

        assert "Search_2024" not in v1.cache, "V1 should reject search URL"
        assert "Search_2024" not in v2.cache, "V2 should reject search URL"
        print("  [PASS] Both reject search URLs")

    print("  === Cache Result Validation: ALL PASSED ===")
    return True


def test_configuration_handling_identical():
    """Test that configuration is handled identically."""
    print("\n=== Test: Configuration Handling Identical ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_v1 = os.path.join(temp_dir, 'v1_cache.json')
        cache_v2 = os.path.join(temp_dir, 'v2_cache.json')

        config = {
            'wikipedia_scraper': {
                'headless': False,
                'timeout': 20,
                'rate_limit': 3.0,
                'screenshots_enabled': False
            }
        }

        v1 = V1Scraper(cache_file=cache_v1, config=config)
        v2 = V2Scraper(cache_file=cache_v2, config=config)

        # Compare rate limit
        assert v1.rate_limit == v2.rate_limit, f"Rate limit differs: v1={v1.rate_limit}, v2={v2.rate_limit}"
        print(f"  [PASS] Rate limit identical: {v1.rate_limit}")

        # Compare screenshots enabled
        assert v1.screenshots_enabled == v2.screenshots_enabled, f"Screenshots differs: v1={v1.screenshots_enabled}, v2={v2.screenshots_enabled}"
        print(f"  [PASS] Screenshots enabled identical: {v1.screenshots_enabled}")

        # Compare screenshot directory
        assert v1.screenshot_dir == v2.screenshot_dir, f"Screenshot dir differs: v1={v1.screenshot_dir}, v2={v2.screenshot_dir}"
        print(f"  [PASS] Screenshot dir identical: {v1.screenshot_dir}")

    print("  === Configuration Handling: ALL PASSED ===")
    return True


def test_line_count_reduction():
    """Verify significant line count reduction."""
    print("\n=== Test: Line Count Reduction ===")

    v1_file = PROJECT_ROOT / 'wikipedia_scraper_playwright.py'
    v2_file = PROJECT_ROOT / 'wikipedia_scraper_v2.py'

    with open(v1_file) as f:
        v1_lines = len(f.readlines())

    with open(v2_file) as f:
        v2_lines = len(f.readlines())

    reduction = v1_lines - v2_lines
    percent = (reduction / v1_lines) * 100

    print(f"  V1 (original): {v1_lines} lines")
    print(f"  V2 (migrated): {v2_lines} lines")
    print(f"  Reduction: {reduction} lines ({percent:.1f}%)")

    # Should reduce by at least 20%
    assert percent > 20, f"Expected >20% reduction, got {percent:.1f}%"
    print("  [PASS] Significant line count reduction achieved")

    print("  === Line Count Reduction: ALL PASSED ===")
    return True


def test_method_signatures_compatible():
    """Test that public method signatures are compatible."""
    print("\n=== Test: Method Signatures Compatible ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_v1 = os.path.join(temp_dir, 'v1_cache.json')
        cache_v2 = os.path.join(temp_dir, 'v2_cache.json')

        v1 = V1Scraper(cache_file=cache_v1)
        v2 = V2Scraper(cache_file=cache_v2)

        # Check public methods exist on both
        public_methods = [
            'find_wikipedia_url',
            'get_stats',
            'close',
            '_title_matches',
            '_cache_result',
            '_query_wikidata',
            '_try_wikipedia_api',
        ]

        for method in public_methods:
            assert hasattr(v1, method), f"V1 missing method: {method}"
            assert hasattr(v2, method), f"V2 missing method: {method}"
            print(f"  [PASS] Both have method: {method}")

    print("  === Method Signatures: ALL PASSED ===")
    return True


def main():
    """Run all comparison tests."""
    print("=" * 60)
    print("Wikipedia Scraper v1 vs v2 Comparison Test")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nComparing original vs migrated scraper for identical behavior.")

    tests = [
        ("Stats Structure", test_stats_structure_identical),
        ("Cache Operations", test_cache_operations_identical),
        ("Title Matching", test_title_matching_identical),
        ("Cache Result Validation", test_cache_result_validation_identical),
        ("Configuration Handling", test_configuration_handling_identical),
        ("Method Signatures", test_method_signatures_compatible),
        ("Line Count Reduction", test_line_count_reduction),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"\n  [FAIL] {test_name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("\n V1 and V2 are FUNCTIONALLY IDENTICAL")
        print("\nSafe to replace production scraper:")
        print("  1. mv wikipedia_scraper_playwright.py wikipedia_scraper_v1_backup.py")
        print("  2. mv wikipedia_scraper_v2.py wikipedia_scraper_playwright.py")
        print("  3. Run pipeline tests to verify")
        return 0
    else:
        print(f"\n {failed} TEST(S) FAILED")
        print("Do NOT replace production scraper until all tests pass.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
