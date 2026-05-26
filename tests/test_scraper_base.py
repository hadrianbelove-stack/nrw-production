#!/usr/bin/env python3
"""
Test suite for PlaywrightScraperBase class.

Tests the base class functionality WITHOUT:
- Launching any browser (no Playwright required)
- Touching any production cache files
- Using any external APIs

Run with: python3 tests/test_scraper_base.py
"""

import os
import sys
import json
import tempfile
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scraper_base import PlaywrightScraperBase


class TestScraper(PlaywrightScraperBase):
    """
    Minimal test scraper that inherits from base class.
    Used to test base class functionality without any real scraping.
    """

    def __init__(self, cache_file, config=None, logger=None):
        # Override manager to avoid Playwright dependency
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key=None,  # No config key - use defaults
            log_prefix='TestScraper',
            screenshot_subdir='test'
        )

    def _get_cache_default(self):
        """Test with simple dict structure."""
        return {}


class TestScraperWithCustomCache(PlaywrightScraperBase):
    """
    Test scraper with custom cache structure (like AgentLinkScraper).
    """

    def __init__(self, cache_file, config=None, logger=None):
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key=None,
            log_prefix='TestScraperCustomCache',
            screenshot_subdir='test_custom'
        )

    def _get_cache_default(self):
        """Return custom structure like AgentLinkScraper."""
        return {'movies': {}, 'last_updated': datetime.now().isoformat()}

    def _get_cache_count(self):
        """Count movies in custom structure."""
        return len(self.cache.get('movies', {}))


def test_cache_operations():
    """Test cache load and save operations."""
    print("\n=== Test: Cache Operations ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        # Test 1: Create scraper with non-existent cache (should use default)
        scraper = TestScraper(cache_file=cache_file)
        assert scraper.cache == {}, f"Expected empty dict, got {scraper.cache}"
        print("  [PASS] New scraper with no cache file uses default empty dict")

        # Test 2: Save some data
        scraper.cache['test_key'] = {'value': 123, 'timestamp': datetime.now().isoformat()}
        scraper._save_cache()
        assert os.path.exists(cache_file), "Cache file should exist after save"
        print("  [PASS] Cache saved to disk")

        # Test 3: Create new scraper and verify it loads the saved data
        scraper2 = TestScraper(cache_file=cache_file)
        assert 'test_key' in scraper2.cache, "Loaded cache should contain saved key"
        assert scraper2.cache['test_key']['value'] == 123, "Loaded value should match"
        print("  [PASS] New scraper loads existing cache correctly")

        # Test 4: Test custom cache structure
        custom_cache_file = os.path.join(temp_dir, 'custom_cache.json')
        custom_scraper = TestScraperWithCustomCache(cache_file=custom_cache_file)
        assert 'movies' in custom_scraper.cache, "Custom cache should have 'movies' key"
        assert 'last_updated' in custom_scraper.cache, "Custom cache should have 'last_updated' key"
        print("  [PASS] Custom cache structure works correctly")

        # Test 5: Cache count for custom structure
        custom_scraper.cache['movies']['12345'] = {'title': 'Test Movie'}
        assert custom_scraper._get_cache_count() == 1, "Cache count should be 1"
        print("  [PASS] Custom cache count works correctly")

    print("  === Cache Operations: ALL PASSED ===")
    return True


def test_logging():
    """Test logging with both logger and print fallback."""
    print("\n=== Test: Logging ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        # Test 1: Logging without logger (uses print)
        scraper = TestScraper(cache_file=cache_file)
        # This should print to stdout without error
        scraper._log("Test message - info level")
        scraper._log("Test debug message", level='debug')
        scraper._log("Test warning message", level='warning')
        scraper._log("Test error message", level='error')
        print("  [PASS] Logging without logger (print fallback) works")

        # Test 2: Logging with actual logger
        logger = logging.getLogger('test_logger')
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('  [LOGGER] %(message)s'))
        logger.addHandler(handler)

        scraper_with_logger = TestScraper(cache_file=cache_file, logger=logger)
        scraper_with_logger._log("Test message via logger")
        print("  [PASS] Logging with logger works")

        # Test 3: Metrics logging
        scraper._log_metrics('test_operation', {'key': 'value'})
        print("  [PASS] Metrics logging works")

    print("  === Logging: ALL PASSED ===")
    return True


def test_screenshot_cleanup():
    """Test screenshot cleanup with retention policy."""
    print("\n=== Test: Screenshot Cleanup ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')
        screenshot_dir = os.path.join(temp_dir, 'cache', 'screenshots', 'test')
        os.makedirs(screenshot_dir, exist_ok=True)

        # Create some test screenshot files
        old_time = (datetime.now() - timedelta(days=10)).timestamp()
        new_time = datetime.now().timestamp()

        # Old file (should be deleted)
        old_file = os.path.join(screenshot_dir, 'old_screenshot.png')
        with open(old_file, 'w') as f:
            f.write('old')
        os.utime(old_file, (old_time, old_time))

        # New file (should be kept)
        new_file = os.path.join(screenshot_dir, 'new_screenshot.png')
        with open(new_file, 'w') as f:
            f.write('new')
        os.utime(new_file, (new_time, new_time))

        # Verify both files exist
        assert os.path.exists(old_file), "Old file should exist before cleanup"
        assert os.path.exists(new_file), "New file should exist before cleanup"
        print("  [PASS] Test files created")

        # Create scraper with screenshots enabled (config with 7-day retention)
        config = {'screenshots_enabled': True, 'screenshot_retention_days': 7}

        # Manually set screenshot_dir to our temp location
        scraper = TestScraper(cache_file=cache_file, config=config)
        scraper.screenshot_dir = screenshot_dir
        scraper.screenshots_enabled = True
        scraper.screenshot_retention_days = 7

        # Run cleanup
        scraper._cleanup_old_screenshots()

        # Verify old file deleted, new file kept
        assert not os.path.exists(old_file), "Old file should be deleted after cleanup"
        assert os.path.exists(new_file), "New file should still exist after cleanup"
        print("  [PASS] Old screenshots cleaned up, new ones kept")

    print("  === Screenshot Cleanup: ALL PASSED ===")
    return True


def test_stats_and_counters():
    """Test stats and counters initialization and updates."""
    print("\n=== Test: Stats and Counters ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        scraper = TestScraper(cache_file=cache_file)

        # Test 1: Stats initialized
        assert 'attempts' in scraper.stats, "Stats should have 'attempts'"
        assert 'successes' in scraper.stats, "Stats should have 'successes'"
        assert 'cache_hits' in scraper.stats, "Stats should have 'cache_hits'"
        assert 'failures' in scraper.stats, "Stats should have 'failures'"
        print("  [PASS] Stats initialized correctly")

        # Test 2: Counters initialized
        assert 'start_count' in scraper.counters, "Counters should have 'start_count'"
        assert 'stop_count' in scraper.counters, "Counters should have 'stop_count'"
        assert 'retry_count' in scraper.counters, "Counters should have 'retry_count'"
        assert 'error_count' in scraper.counters, "Counters should have 'error_count'"
        print("  [PASS] Counters initialized correctly")

        # Test 3: Stats can be updated
        scraper.stats['attempts'] += 1
        scraper.stats['successes'] += 1
        assert scraper.stats['attempts'] == 1, "Stats should be updatable"
        print("  [PASS] Stats can be updated")

        # Test 4: get_stats returns copy
        stats_copy = scraper.get_stats()
        stats_copy['attempts'] = 999
        assert scraper.stats['attempts'] == 1, "get_stats should return a copy"
        print("  [PASS] get_stats returns a copy (not reference)")

    print("  === Stats and Counters: ALL PASSED ===")
    return True


def test_rate_limiting():
    """Test rate limiting functionality."""
    print("\n=== Test: Rate Limiting ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        # Test with short rate limit for quick testing
        scraper = TestScraper(cache_file=cache_file)
        scraper.rate_limit = 0.1  # 100ms

        # First call should not block
        import time
        start = time.time()
        scraper._enforce_rate_limit()
        elapsed1 = time.time() - start
        assert elapsed1 < 0.05, "First rate limit call should not block"
        print("  [PASS] First rate limit call does not block")

        # Second call should block
        start = time.time()
        scraper._enforce_rate_limit()
        elapsed2 = time.time() - start
        assert elapsed2 >= 0.05, "Second rate limit call should block"
        print(f"  [PASS] Second rate limit call blocked for {elapsed2:.2f}s")

    print("  === Rate Limiting: ALL PASSED ===")
    return True


def test_config_handling():
    """Test configuration handling."""
    print("\n=== Test: Config Handling ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        # Test 1: No config provided
        scraper = TestScraper(cache_file=cache_file)
        assert scraper.config == {}, "Empty config should be empty dict"
        print("  [PASS] No config provided uses empty dict")

        # Test 2: Config with custom values
        config = {
            'headless': False,
            'rate_limit': 5.0,
            'screenshots_enabled': False
        }
        scraper2 = TestScraper(cache_file=cache_file, config=config)
        assert scraper2.config == config, "Config should be stored"
        print("  [PASS] Custom config stored correctly")

    print("  === Config Handling: ALL PASSED ===")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("PlaywrightScraperBase Test Suite")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    tests = [
        ("Cache Operations", test_cache_operations),
        ("Logging", test_logging),
        ("Screenshot Cleanup", test_screenshot_cleanup),
        ("Stats and Counters", test_stats_and_counters),
        ("Rate Limiting", test_rate_limiting),
        ("Config Handling", test_config_handling),
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
        print("\n✅ ALL TESTS PASSED - Base class is ready for use")
        return 0
    else:
        print(f"\n❌ {failed} TEST(S) FAILED - Do not proceed with migration")
        return 1


if __name__ == "__main__":
    sys.exit(main())
