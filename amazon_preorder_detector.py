#!/usr/bin/env python3
"""
Amazon Pre-Order Detector - Checks Amazon product pages for pre-order vs buy status.

Uses Playwright to visit Amazon movie pages and detect whether the purchase button
says "Pre-order" (not yet available) or "Buy" (available now).

Created: 2026-02-27
"""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import urllib.parse
import time
import random
import logging
import json
import os
from datetime import datetime, timedelta

from scraper_base import PlaywrightScraperBase

logger = logging.getLogger(__name__)


class AmazonPreorderDetector(PlaywrightScraperBase):
    """Detect pre-order vs buy status on Amazon movie pages."""

    def __init__(self, config=None):
        super().__init__(
            cache_file='cache/amazon_preorder_cache.json',
            config=config,
            logger=logger,
            config_key='amazon_preorder',
            log_prefix='AmazonPreorder',
            screenshot_subdir='amazon_preorder'
        )
        self.timeout_seconds = self.scraper_config.get('timeout', 15)
        self.last_url = None  # Product URL from last check_preorder() call; caller reads this

    def _init_browser_shared(self):
        """Override to add Amazon-specific stealth scripts."""
        try:
            self.playwright = self.manager.get_playwright()

            headless = self.scraper_config.get('headless', True)
            self.browser = self.manager.get_browser(headless=headless, browser_type='chromium')

            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                extra_http_headers={'DNT': '1', 'Upgrade-Insecure-Requests': '1'}
            )

            # Amazon-specific stealth: hide automation signals
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                Object.defineProperty(window, 'chrome', {
                    get: () => ({ runtime: {} }),
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            timeout_ms = self.timeout_seconds * 1000
            self.context.set_default_timeout(timeout_ms)
            self.page = self.context.new_page()

            self._log("Browser initialized with Amazon stealth scripts")
            self.counters['start_count'] += 1

        except Exception as e:
            self._log(f"Browser initialization failed: {e}", level='error')
            self.counters['error_count'] += 1
            self._cleanup_browser()
            raise

    def check_preorder(self, title, year=None):
        """Check if a movie is listed as pre-order on Amazon.

        Args:
            title: Movie title
            year: Release year (optional, improves search accuracy)

        Returns:
            'pre-order' if pre-order detected
            'available' if buy/rent button found
            None if check failed (CAPTCHA, not found, etc.)
        """
        cache_key = f"{title}_{year or ''}"

        # Check cache (7-day TTL)
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            cached_at = cached.get('checked_at', '')
            if cached_at:
                try:
                    cached_dt = datetime.fromisoformat(cached_at)
                    if datetime.now() - cached_dt < timedelta(days=7):
                        self.stats['cache_hits'] += 1
                        self._log(f"Cache hit for {title}: {cached['status']}", level='debug')
                        return cached['status']
                except (ValueError, TypeError):
                    pass

        self.stats['attempts'] += 1
        result = self._check_amazon_page(title, year)

        # Cache the result
        self.cache[cache_key] = {
            'status': result,
            'title': title,
            'year': year,
            'checked_at': datetime.now().isoformat()
        }
        self._save_cache()

        if result:
            self.stats['successes'] += 1
        else:
            self.stats['failures'] += 1

        return result

    def _check_amazon_page(self, title, year):
        """Navigate to Amazon and check button text."""
        try:
            self._init_browser()
            self._enforce_rate_limit()

            # Search Amazon for the movie
            search_query = f"{title} {year}" if year else title
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://www.amazon.com/s?k={encoded_query}&i=instant-video"

            self._log(f"Searching Amazon for: {search_query}")
            self.page.goto(search_url, wait_until='networkidle')

            # Random delay to appear human
            time.sleep(random.uniform(1.0, 2.5))

            # Check for CAPTCHA
            page_text = self.page.text_content('body') or ''
            if 'captcha' in page_text.lower() or 'robot' in page_text.lower():
                self._log(f"CAPTCHA detected for {title}", level='warning')
                self._capture_failure_diagnostics(title, year or '', "amazon_preorder", "CAPTCHA detected")
                return None

            # Find first movie result link
            product_url = self._find_product_link(title)
            self.last_url = product_url  # Save for caller
            if not product_url:
                self._log(f"No Amazon product found for {title}", level='warning')
                return None

            # Navigate to product page
            self._log(f"Checking product page: {product_url}")
            self.page.goto(product_url, wait_until='networkidle')
            time.sleep(random.uniform(1.0, 2.0))

            # Check for CAPTCHA on product page
            page_text = self.page.text_content('body') or ''
            if 'captcha' in page_text.lower() or 'robot' in page_text.lower():
                self._log(f"CAPTCHA on product page for {title}", level='warning')
                return None

            # Check button text for pre-order signals
            return self._detect_button_status()

        except PlaywrightTimeoutError:
            self._log(f"Timeout checking Amazon for {title}", level='warning')
            return None
        except Exception as e:
            self._log(f"Error checking Amazon for {title}: {e}", level='error')
            return None

    def _find_product_link(self, title):
        """Find the first relevant movie product link from search results."""
        selectors = [
            "a[href*='/gp/video/detail/']",
            "div[data-component-type='s-search-result'] h2 a[href*='/dp/']",
            "a[href*='/dp/']",
        ]

        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                for element in elements:
                    href = element.get_attribute('href')
                    if href:
                        # Build full URL
                        if href.startswith('/'):
                            href = f"https://www.amazon.com{href}"
                        return href
            except Exception:
                continue

        return None

    def _detect_button_status(self):
        """Check the product page for pre-order vs buy/rent buttons.

        Returns:
            'pre-order' if pre-order detected
            'available' if buy/rent found
            None if can't determine
        """
        # Get all visible text from the page's purchase area
        # Amazon uses various button/span patterns
        button_selectors = [
            # Direct button text
            'input[name*="submit.buy"]',
            'input[name*="submit.preorder"]',
            'span.a-button-text',
            'a.a-button-text',
            # Purchase section buttons
            '#buy-now-button',
            '#preorder-button',
            '#rent-button',
            # Generic action buttons in the purchase area
            '[data-feature-name="buyNow"] span',
            '[data-feature-name="preorder"] span',
            '[data-action="buy-now"] span',
        ]

        all_button_text = []
        for selector in button_selectors:
            try:
                elements = self.page.locator(selector).all()
                for element in elements:
                    text = (element.get_attribute('value') or element.text_content() or '').strip().lower()
                    if text:
                        all_button_text.append(text)
            except Exception:
                continue

        # Also check the broader page text in the purchase/action area
        try:
            # Amazon's purchase section
            purchase_area_selectors = [
                '#digitalPurchaseActions',
                '#watch-party-section',
                '.av-detail-section',
                '#dp-container',
            ]
            for selector in purchase_area_selectors:
                try:
                    el = self.page.locator(selector).first
                    if el.count() > 0:
                        area_text = (el.text_content() or '').lower()
                        all_button_text.append(area_text)
                except Exception:
                    continue
        except Exception:
            pass

        combined_text = ' '.join(all_button_text)
        self._log(f"Button text signals: {combined_text[:200]}", level='debug')

        # Check for pre-order signals
        preorder_signals = ['pre-order', 'preorder', 'pre order']
        for signal in preorder_signals:
            if signal in combined_text:
                self._log(f"Pre-order detected: found '{signal}'")
                return 'pre-order'

        # Check for available signals
        available_signals = ['buy now', 'rent now', 'buy hd', 'buy sd', 'rent hd', 'rent sd',
                             'buy $', 'rent $', 'watch now', 'buy movie', 'rent movie']
        for signal in available_signals:
            if signal in combined_text:
                self._log(f"Available detected: found '{signal}'")
                return 'available'

        # If we found button text but no clear signal, log it
        if combined_text.strip():
            self._log(f"Unclear button status for page. Text: {combined_text[:300]}", level='warning')

        return None

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
