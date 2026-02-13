#!/usr/bin/env python3
"""
Playwright Scraper Base Class - Common functionality for all Playwright-based scrapers.

Configuration Defaults:
    These values can be overridden via config.yaml under the scraper's config_key:
    - rate_limit: 2.0 seconds between requests
    - timeout: 15 seconds for page loads
    - screenshots_enabled: True
    - screenshot_retention_days: 7 days
    - viewport: 1920x1080 pixels

Created 2026-02-04 as part of technical debt cleanup.
Extracts ~450 lines of duplicated code from:
- rt_scraper_playwright.py
- wikipedia_scraper_playwright.py
- streaming_platform_scraper.py
- agent_link_scraper.py

Usage:
    class MyScraper(PlaywrightScraperBase):
        def __init__(self, cache_file='cache/my_cache.json', config=None, logger=None):
            super().__init__(
                cache_file=cache_file,
                config=config,
                logger=logger,
                config_key='my_scraper',
                log_prefix='MyScraper',
                screenshot_subdir='my_scraper'
            )
            # Scraper-specific initialization...

        def _get_cache_default(self):
            # Override if your cache needs a different default structure
            return {}

        # Implement scraper-specific methods...
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from playwright_manager import get_playwright_manager
from constants import get_scraper_config


class PlaywrightScraperBase:
    """
    Base class for Playwright-based scrapers.

    Provides common functionality:
    - Browser lifecycle management (lazy initialization via shared manager)
    - Cache loading/saving with configurable default structure
    - Screenshot management with retention cleanup
    - Logging with configurable prefix
    - Structured metrics logging
    - Rate limiting state
    - Stats and counters tracking
    """

    def __init__(
        self,
        cache_file: str,
        config: Optional[Dict] = None,
        logger: Optional[Any] = None,
        config_key: Optional[str] = None,
        log_prefix: str = 'Scraper',
        screenshot_subdir: str = ''
    ):
        """
        Initialize base scraper with common configuration.

        Args:
            cache_file: Path to JSON cache file
            config: Configuration dict (typically from config.yaml)
            logger: Logger instance (if None, uses print)
            config_key: Key for scraper-specific config in constants.py (e.g., 'rt_scraper')
            log_prefix: Prefix for log messages (e.g., 'RTScraperPlaywright')
            screenshot_subdir: Subdirectory under cache/screenshots/ (e.g., 'rt', 'wikipedia')
        """
        self.cache_file = cache_file
        self.config = config or {}
        self.logger = logger
        self.log_prefix = log_prefix

        # Get centralized scraper configuration with defaults
        self.scraper_config = get_scraper_config(config, config_key) if config_key else {}

        # Browser components (lazy initialization)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Manager reference for shared browser instances
        self.manager = get_playwright_manager()

        # Rate limiting
        self.last_scrape_time = 0
        rate_limit = self.scraper_config.get('rate_limit')
        self.rate_limit = rate_limit if rate_limit is not None else 2.0

        # Screenshots configuration
        if screenshot_subdir:
            self.screenshot_dir = f'cache/screenshots/{screenshot_subdir}'
        else:
            self.screenshot_dir = 'cache/screenshots'
        self.screenshots_enabled = self.scraper_config.get('screenshots_enabled', True)
        self.screenshot_retention_days = self.scraper_config.get('screenshot_retention_days', 7)

        # Operational counters for structured logging
        self.counters = {
            'start_count': 0,
            'stop_count': 0,
            'retry_count': 0,
            'error_count': 0
        }

        # Stats - subclasses can extend with scraper-specific stats
        self.stats = {
            'attempts': 0,
            'successes': 0,
            'cache_hits': 0,
            'failures': 0
        }

        # Load cache
        self.cache = self._load_cache()

        # Clean up old screenshots on initialization
        if self.screenshots_enabled:
            self._cleanup_old_screenshots()

        self._log(f"Initialized with cache_file={cache_file}")
        self._log(f"Cache loaded: {self._get_cache_count()} entries")
        self._log(f"Screenshots: {'enabled' if self.screenshots_enabled else 'disabled'}")

    def _get_cache_default(self) -> Any:
        """
        Return the default value for an empty cache.

        Override in subclasses that need a different structure.
        For example, AgentLinkScraper uses {'movies': {}, 'last_updated': ...}

        Returns:
            Default cache structure (typically empty dict)
        """
        return {}

    def _get_cache_count(self) -> int:
        """
        Return the count of entries in the cache for logging.

        Override in subclasses with different cache structures.

        Returns:
            Number of cache entries
        """
        if isinstance(self.cache, dict):
            # Handle nested structure like {'movies': {...}}
            if 'movies' in self.cache:
                return len(self.cache.get('movies', {}))
            return len(self.cache)
        return 0

    def _log(self, message: str, level: str = 'info'):
        """
        Log message using logger if available, otherwise print.

        Args:
            message: Message to log
            level: Log level ('debug', 'info', 'warning', 'error')
        """
        if self.logger:
            if level == 'debug':
                self.logger.debug(message)
            elif level == 'warning':
                self.logger.warning(message)
            elif level == 'error':
                self.logger.error(message)
            else:
                self.logger.info(message)
        else:
            print(f"[{self.log_prefix}] {message}")

    def _log_metrics(self, operation: str, data: Dict):
        """
        Log structured metrics for operations.

        Args:
            operation: Name of the operation being logged
            data: Additional data to include in metrics
        """
        metrics_data = {
            'timestamp': datetime.now().isoformat(),
            'component': self.log_prefix.lower().replace(' ', '_'),
            'operation': operation,
            'counters': self.counters.copy(),
            'stats': self.stats.copy(),
            'data': data
        }

        if self.logger:
            self.logger.info(f"METRICS: {json.dumps(metrics_data)}")
        else:
            print(f"[{self.log_prefix}] METRICS: {json.dumps(metrics_data)}")

    def _load_cache(self) -> Any:
        """
        Load cache from disk.

        Returns:
            Loaded cache data or default from _get_cache_default()
        """
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                self._log(f"Failed to load cache: {e}", level='warning')
        return self._get_cache_default()

    def _save_cache(self):
        """Save cache to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            self._log(f"Cache saved: {self._get_cache_count()} entries", level='debug')
        except Exception as e:
            self._log(f"Failed to save cache: {e}", level='error')

    def _cleanup_old_screenshots(self):
        """Delete old screenshots based on retention policy."""
        if not self.screenshots_enabled or not os.path.exists(self.screenshot_dir):
            return

        try:
            retention_days = self.screenshot_retention_days
            cutoff_time = datetime.now() - timedelta(days=retention_days)
            cutoff_timestamp = cutoff_time.timestamp()

            deleted_count = 0
            for filename in os.listdir(self.screenshot_dir):
                file_path = os.path.join(self.screenshot_dir, filename)
                if os.path.isfile(file_path):
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_timestamp:
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except OSError as e:
                            self._log(f"Failed to delete old screenshot {filename}: {e}", level='warning')

            if deleted_count > 0:
                self._log(f"Cleaned up {deleted_count} old screenshots (older than {retention_days} days)")

        except Exception as e:
            self._log(f"Failed to cleanup old screenshots: {e}", level='warning')

    def _init_browser(self):
        """Initialize Playwright browser with context (lazy initialization)."""
        if self.browser is not None:
            self._log("Browser already initialized, reusing...", level='debug')
            return

        self._log("Initializing Playwright browser via shared manager...")
        self._init_browser_shared()

    def _init_browser_shared(self):
        """Initialize browser using shared Playwright manager."""
        try:
            # Get shared Playwright instance
            self.playwright = self.manager.get_playwright()

            # Get shared browser from manager
            headless = self.config.get('headless', True)
            # Also check scraper-specific config
            if self.scraper_config:
                headless = self.scraper_config.get('headless', headless)

            self.browser = self.manager.get_browser(headless=headless, browser_type='chromium')

            # Create context with viewport, user agent, and stealth headers
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                extra_http_headers={'DNT': '1', 'Upgrade-Insecure-Requests': '1'}
            )

            # Set default timeout from config
            timeout_seconds = self.scraper_config.get('timeout', 15)
            timeout_ms = timeout_seconds * 1000
            self.context.set_default_timeout(timeout_ms)

            # Create page
            self.page = self.context.new_page()

            self._log("Browser initialized successfully via shared manager")
            self.counters['start_count'] += 1

        except Exception as e:
            self._log(f"Browser initialization failed: {e}", level='error')
            self.counters['error_count'] += 1
            self._cleanup_browser()
            raise

    def _init_browser_local(self):
        """
        Initialize local browser instance as fallback.

        Used when shared manager is unavailable.
        """
        try:
            from playwright.sync_api import sync_playwright

            self.playwright = sync_playwright().start()

            headless = self.config.get('headless', True)
            if self.scraper_config:
                headless = self.scraper_config.get('headless', headless)

            self.browser = self.playwright.chromium.launch(headless=headless)

            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US'
            )

            timeout_seconds = self.scraper_config.get('timeout', 15)
            self.context.set_default_timeout(timeout_seconds * 1000)

            self.page = self.context.new_page()

            self._log("Browser initialized locally (fallback mode)")
            self.counters['start_count'] += 1

        except Exception as e:
            self._log(f"Local browser initialization failed: {e}", level='error')
            self.counters['error_count'] += 1
            self._cleanup_browser()
            raise

    def _cleanup_browser(self):
        """Clean up browser resources."""
        try:
            if self.page:
                try:
                    self.page.close()
                except Exception:
                    pass
                self.page = None

            if self.context:
                try:
                    self.context.close()
                except Exception:
                    pass
                self.context = None

            # Don't close browser or playwright if using shared manager
            # The manager handles lifecycle
            if not self.manager:
                if self.browser:
                    try:
                        self.browser.close()
                    except Exception:
                        pass
                    self.browser = None

                if self.playwright:
                    try:
                        self.playwright.stop()
                    except Exception:
                        pass
                    self.playwright = None

            self.counters['stop_count'] += 1

        except Exception as e:
            self._log(f"Error during browser cleanup: {e}", level='warning')

    def _enforce_rate_limit(self):
        """Enforce rate limiting between scrape operations."""
        if self.rate_limit > 0:
            time_since_last = time.time() - self.last_scrape_time
            if time_since_last < self.rate_limit:
                sleep_time = self.rate_limit - time_since_last
                self._log(f"Rate limiting: sleeping {sleep_time:.1f}s", level='debug')
                time.sleep(sleep_time)
        self.last_scrape_time = time.time()

    def _take_screenshot(self, name: str):
        """
        Take a screenshot for debugging purposes.

        Args:
            name: Base name for the screenshot file
        """
        if not self.screenshots_enabled or not self.page:
            return

        try:
            os.makedirs(self.screenshot_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{name}_{timestamp}.png"
            filepath = os.path.join(self.screenshot_dir, filename)
            self.page.screenshot(path=filepath)
            self._log(f"Screenshot saved: {filename}", level='debug')
        except Exception as e:
            self._log(f"Failed to take screenshot: {e}", level='warning')

    def get_stats(self) -> Dict:
        """
        Return current stats for external consumers.

        Returns:
            Copy of current stats dict
        """
        return self.stats.copy()

    def cleanup(self):
        """Public method to clean up browser resources."""
        self._cleanup_browser()

    def __enter__(self):
        """Context manager entry - initialize browser."""
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup browser."""
        self._cleanup_browser()
        return False
