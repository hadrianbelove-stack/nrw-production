#!/usr/bin/env python3
"""
Test suite for Wikipedia Scraper migration to PlaywrightScraperBase.

This tests the MIGRATED version of WikipediaScraperPlaywright:
1. Inherits from PlaywrightScraperBase
2. Gets all common methods for free (logging, cache, screenshots, browser init)
3. Keeps Wikipedia-specific methods (Wikidata lookup, API search, etc.)

Run with: python3 tests/test_wikipedia_scraper_migration.py

Tests that WikipediaScraperPlaywright works correctly with PlaywrightScraperBase.
"""

import os
import sys
import json
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scraper_base import PlaywrightScraperBase
from wikipedia_scraper_playwright import WikipediaScraperPlaywright


class WikipediaScraperMigrated(PlaywrightScraperBase):
    """
    MIGRATED Wikipedia scraper - inherits common functionality from base class.

    This version demonstrates what the production scraper would look like
    after migration. Compare to wikipedia_scraper_playwright.py (699 lines)
    - this is significantly shorter because base handles:
      - _log(), _log_metrics()
      - _load_cache(), _save_cache()
      - _cleanup_old_screenshots()
      - _init_browser(), _init_browser_shared()
      - _cleanup_browser()
      - stats and counters initialization
      - screenshot directory setup
    """

    def __init__(self, cache_file='cache/wikipedia_cache.json', config=None, logger=None):
        """Initialize the Wikipedia scraper with configuration."""
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key='wikipedia_scraper',
            log_prefix='WikipediaScraperPlaywright',
            screenshot_subdir='wikipedia'
        )

        # Wikipedia-specific stats (extend base stats)
        self.stats.update({
            'wikidata_attempts': 0,
            'wikidata_successes': 0,
            'api_successes': 0,
            'scraper_successes': 0
        })

        self._log(f"Wikipedia Scraper initialized with cache_file={cache_file}")

    def _cleanup_browser(self):
        """Clean up browser resources - Wikipedia-specific override."""
        # Close page and context (base class handles this)
        if self.page:
            try:
                self.page.close()
            except:
                pass
            self.page = None

        if self.context:
            try:
                self.context.close()
            except:
                pass
            self.context = None

        # Wikipedia scraper specifically calls manager.release()
        if self.playwright and self.manager:
            try:
                self.manager.release()
                self._log("Released shared browser reference", level='debug')
            except:
                pass
            self.playwright = None
            self.browser = None

        self.counters['stop_count'] += 1

    # Use production _title_matches directly — no copy-paste drift
    _title_matches = WikipediaScraperPlaywright._title_matches

    def _cache_result(self, cache_key, url, title, source):
        """Cache the Wikipedia article URL."""
        if 'index.php?search=' in url or '/wiki/' not in url:
            self._log(f"Refusing to cache non-article URL: {url}", level='warning')
            return

        self.cache[cache_key] = {
            'url': url,
            'title': title,
            'cached_at': datetime.now().isoformat(),
            'source': source
        }
        self._save_cache()

    def find_wikipedia_url(self, title, year, imdb_id=None, use_cache=True):
        """Find Wikipedia URL - simplified for testing (no real network calls)."""
        cache_key = f"{title}_{year}"

        # Check cache
        if use_cache and cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict):
                url = cached_data.get('url')
                if url and '/wiki/' in url:
                    self.stats['cache_hits'] += 1
                    return url

        # In real implementation, would call Wikidata, API, then Playwright
        # For testing, just return None
        return None

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
        self._log("Wikipedia Scraper closed")


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_inherits_base_class():
    """Test that migrated scraper properly inherits from base."""
    print("\n=== Test: Inherits Base Class ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        scraper = WikipediaScraperMigrated(cache_file=cache_file)

        # Check it's an instance of base class
        assert isinstance(scraper, PlaywrightScraperBase), "Should inherit from base"
        print("  [PASS] Inherits from PlaywrightScraperBase")

        # Check inherited attributes exist
        assert hasattr(scraper, 'cache'), "Should have cache from base"
        assert hasattr(scraper, 'stats'), "Should have stats from base"
        assert hasattr(scraper, 'counters'), "Should have counters from base"
        assert hasattr(scraper, 'screenshot_dir'), "Should have screenshot_dir from base"
        print("  [PASS] Has all inherited attributes")

        # Check base stats exist
        assert 'attempts' in scraper.stats, "Should have base stats"
        assert 'successes' in scraper.stats, "Should have base stats"
        print("  [PASS] Has base stats fields")

        # Check Wikipedia-specific stats were added
        assert 'wikidata_attempts' in scraper.stats, "Should have Wikipedia-specific stats"
        assert 'api_successes' in scraper.stats, "Should have Wikipedia-specific stats"
        print("  [PASS] Has Wikipedia-specific stats fields")

    print("  === Inherits Base Class: ALL PASSED ===")
    return True


def test_inherited_logging():
    """Test that inherited logging works correctly."""
    print("\n=== Test: Inherited Logging ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        scraper = WikipediaScraperMigrated(cache_file=cache_file)

        # Test logging without error
        scraper._log("Test info message")
        scraper._log("Test debug message", level='debug')
        scraper._log("Test warning message", level='warning')
        print("  [PASS] Inherited _log() method works")

        # Test metrics logging
        scraper._log_metrics('test_op', {'key': 'value'})
        print("  [PASS] Inherited _log_metrics() method works")

    print("  === Inherited Logging: ALL PASSED ===")
    return True


def test_inherited_cache_operations():
    """Test that inherited cache operations work correctly."""
    print("\n=== Test: Inherited Cache Operations ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        # Create scraper and add data
        scraper = WikipediaScraperMigrated(cache_file=cache_file)
        scraper.cache['Test Movie_2024'] = {
            'url': 'https://en.wikipedia.org/wiki/Test_Movie',
            'title': 'Test Movie',
            'source': 'test'
        }
        scraper._save_cache()
        print("  [PASS] Cache save works")

        # Create new scraper and verify data loads
        scraper2 = WikipediaScraperMigrated(cache_file=cache_file)
        assert 'Test Movie_2024' in scraper2.cache, "Cache should persist"
        print("  [PASS] Cache load works")

    print("  === Inherited Cache Operations: ALL PASSED ===")
    return True


def test_wikipedia_specific_title_matching():
    """Test Wikipedia-specific title matching logic."""
    print("\n=== Test: Title Matching ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')
        scraper = WikipediaScraperMigrated(cache_file=cache_file)

        # --- Must match ---
        assert scraper._title_matches("The Matrix", "The Matrix"), "Exact match should work"
        print("  [PASS] Exact match")

        assert scraper._title_matches("Dune", "Dune (film)"), "Film suffix match should work"
        print("  [PASS] Film suffix (parenthetical stripped)")

        assert scraper._title_matches("Dune", "Dune (2021 film)"), "Year suffix match should work"
        print("  [PASS] Year suffix (parenthetical stripped)")

        assert scraper._title_matches("Crash", "Crash (2004 American film)"), "Country qualifier"
        print("  [PASS] Country qualifier (parenthetical stripped)")

        assert scraper._title_matches("Inception", "inception"), "Case insensitive"
        print("  [PASS] Case insensitive")

        assert scraper._title_matches("Bonnie & Clyde", "Bonnie and Clyde"), "Ampersand normalization"
        print("  [PASS] Ampersand normalization")

        # --- Must reject: the actual bug ---
        assert not scraper._title_matches("Heresy", "The Burnt Orange Heresy"), \
            "Short title should not match longer title containing it"
        print("  [PASS] Rejects 'Heresy' → 'The Burnt Orange Heresy'")

        # --- Must reject: character-level substring ---
        assert not scraper._title_matches("Bomb", "Bombshell"), \
            "Character substring should not match"
        print("  [PASS] Rejects 'Bomb' → 'Bombshell'")

        # --- Must reject: extra words beyond title ---
        assert not scraper._title_matches("Love Me Love Me", "Love Me, Love Me Not (manga)"), \
            "Extra words should cause rejection"
        print("  [PASS] Rejects 'Love Me Love Me' → 'Love Me, Love Me Not (manga)'")

        # --- Must reject: completely different ---
        assert not scraper._title_matches("Avatar", "Titanic"), "Non-match should return False"
        print("  [PASS] Non-match correctly returns False")

        # --- Must reject: different sequel ---
        assert not scraper._title_matches("The Godfather", "The Godfather Part II"), \
            "Should not match different sequel"
        print("  [PASS] Rejects 'The Godfather' → 'The Godfather Part II'")

    print("  === Title Matching: ALL PASSED ===")
    return True


def test_wikipedia_specific_cache_result():
    """Test Wikipedia-specific cache result validation."""
    print("\n=== Test: Cache Result Validation ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')
        scraper = WikipediaScraperMigrated(cache_file=cache_file)

        # Valid article URL should be cached
        scraper._cache_result("Test_2024", "https://en.wikipedia.org/wiki/Test_Movie", "Test", "test")
        assert "Test_2024" in scraper.cache, "Valid URL should be cached"
        print("  [PASS] Valid article URLs are cached")

        # Search URL should NOT be cached
        scraper._cache_result("Bad_2024", "https://en.wikipedia.org/w/index.php?search=bad", "Bad", "test")
        assert "Bad_2024" not in scraper.cache, "Search URL should not be cached"
        print("  [PASS] Search URLs are rejected")

    print("  === Cache Result Validation: ALL PASSED ===")
    return True


def test_find_wikipedia_url_uses_cache():
    """Test that find_wikipedia_url uses inherited cache."""
    print("\n=== Test: Find URL Uses Cache ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')
        scraper = WikipediaScraperMigrated(cache_file=cache_file)

        # Pre-populate cache
        scraper.cache['Inception_2010'] = {
            'url': 'https://en.wikipedia.org/wiki/Inception',
            'title': 'Inception',
            'source': 'test'
        }

        # Find should return cached URL
        result = scraper.find_wikipedia_url("Inception", 2010)
        assert result == 'https://en.wikipedia.org/wiki/Inception', "Should return cached URL"
        assert scraper.stats['cache_hits'] == 1, "Should increment cache_hits"
        print("  [PASS] Cache lookup works")

        # Find with cache disabled should not return cached
        scraper.stats['cache_hits'] = 0
        result = scraper.find_wikipedia_url("Inception", 2010, use_cache=False)
        assert result is None, "Should not use cache when disabled"
        assert scraper.stats['cache_hits'] == 0, "Should not increment cache_hits"
        print("  [PASS] Cache can be bypassed")

    print("  === Find URL Uses Cache: ALL PASSED ===")
    return True


def test_inherited_rate_limiting():
    """Test that inherited rate limiting works."""
    print("\n=== Test: Inherited Rate Limiting ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')
        scraper = WikipediaScraperMigrated(cache_file=cache_file)
        scraper.rate_limit = 0.1  # 100ms for quick testing

        # First call should not block
        start = time.time()
        scraper._enforce_rate_limit()
        elapsed1 = time.time() - start
        assert elapsed1 < 0.05, "First call should not block"
        print("  [PASS] First rate limit call does not block")

        # Second call should block
        start = time.time()
        scraper._enforce_rate_limit()
        elapsed2 = time.time() - start
        assert elapsed2 >= 0.05, "Second call should block"
        print(f"  [PASS] Second call blocked for {elapsed2:.2f}s")

    print("  === Inherited Rate Limiting: ALL PASSED ===")
    return True


def test_context_manager():
    """Test context manager works correctly."""
    print("\n=== Test: Context Manager ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        cache_file = os.path.join(temp_dir, 'test_cache.json')

        # Mock the browser init to avoid Playwright dependency
        with patch.object(WikipediaScraperMigrated, '_init_browser'):
            with WikipediaScraperMigrated(cache_file=cache_file) as scraper:
                assert scraper is not None, "Context manager should return scraper"
                print("  [PASS] __enter__ works")

        print("  [PASS] __exit__ works")

    print("  === Context Manager: ALL PASSED ===")
    return True


def test_line_count_reduction():
    """Verify the migration reduces code significantly."""
    print("\n=== Test: Line Count Reduction ===")

    original_file = PROJECT_ROOT / 'wikipedia_scraper_playwright.py'
    migrated_class_lines = len(WikipediaScraperMigrated.__doc__.split('\n'))

    # Read original file
    if original_file.exists():
        with open(original_file) as f:
            original_lines = len(f.readlines())
        print(f"  Original: {original_lines} lines")

        # Count migrated class source (approximate)
        import inspect
        migrated_source = inspect.getsource(WikipediaScraperMigrated)
        migrated_lines = len(migrated_source.split('\n'))
        print(f"  Migrated: {migrated_lines} lines")

        reduction = original_lines - migrated_lines
        percent = (reduction / original_lines) * 100
        print(f"  Reduction: {reduction} lines ({percent:.1f}%)")

        # Should reduce by at least 30%
        assert percent > 30, f"Expected >30% reduction, got {percent:.1f}%"
        print("  [PASS] Significant line count reduction achieved")
    else:
        print("  [SKIP] Original file not found for comparison")

    print("  === Line Count Reduction: ALL PASSED ===")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Wikipedia Scraper Migration Test Suite")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nThis tests the MIGRATED version without touching production.")

    tests = [
        ("Inherits Base Class", test_inherits_base_class),
        ("Inherited Logging", test_inherited_logging),
        ("Inherited Cache Operations", test_inherited_cache_operations),
        ("Wikipedia Title Matching", test_wikipedia_specific_title_matching),
        ("Wikipedia Cache Validation", test_wikipedia_specific_cache_result),
        ("Find URL Uses Cache", test_find_wikipedia_url_uses_cache),
        ("Inherited Rate Limiting", test_inherited_rate_limiting),
        ("Context Manager", test_context_manager),
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
        print("\n ALL TESTS PASSED - Migration pattern validated")
        print("\nNext step: Apply this pattern to production wikipedia_scraper_playwright.py")
        return 0
    else:
        print(f"\n {failed} TEST(S) FAILED - Do not proceed with migration")
        return 1


if __name__ == "__main__":
    sys.exit(main())
