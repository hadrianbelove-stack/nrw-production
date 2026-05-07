#!/usr/bin/env python3
"""
Agent Link Scraper - Uses Playwright to find direct watch links on streaming platforms.

Inherits from PlaywrightScraperBase for shared functionality:
- _log(), _log_metrics() - overridden to use print instead of logger
- _load_cache(), _save_cache()
- _cleanup_old_screenshots()
- _init_browser(), _init_browser_shared(), _init_browser_local()
- _cleanup_browser()
- _enforce_rate_limit()
- counters initialization

Includes platform-specific scrapers:
- NetflixScraper
- DisneyPlusScraper
- HBOMaxScraper
- HuluScraper
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import random
import re
import unicodedata
import logging
from datetime import datetime, timedelta
from urllib.parse import quote

from scraper_base import PlaywrightScraperBase

# Module-level logger
logger = logging.getLogger(__name__)


class BasePlatformScraper:
    """Base class for platform-specific scrapers."""

    def __init__(self, page, config):
        self.page = page
        self.config = config

    def normalize_text(self, text):
        """Normalize text by removing accents and special characters"""
        # Normalize Unicode characters (accents, etc.)
        normalized = unicodedata.normalize('NFD', text)
        # Remove accent marks
        ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        # Keep only alphanumeric and spaces
        return re.sub(r'[^a-zA-Z0-9\s]', ' ', ascii_text)

    def validate_title_match(self, search_title, result_text, threshold=0.7):
        """Enhanced title validation with stopword filtering and character normalization"""
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'from', 'that', 'this', 'as', 'it'}

        # Normalize and filter stopwords from search title
        normalized_title = self.normalize_text(search_title.lower())
        search_title_words = {word for word in normalized_title.split() if word and word not in stopwords and len(word) > 1}

        # Extract potential title from the result text (first few lines usually contain title)
        result_text_lines = result_text.split('\n')[:3]  # First 3 lines most likely to contain title
        processed_result_text = ' '.join(result_text_lines).lower()
        normalized_result = self.normalize_text(processed_result_text)

        # Count word overlap (excluding stopwords)
        matching_words = sum(1 for word in search_title_words if word in normalized_result)
        overlap_percentage = matching_words / len(search_title_words) if search_title_words else 0

        # Exact title match bonus: if result contains the exact full title, accept with lower threshold
        has_exact_title = normalized_title in normalized_result

        # Short titles (1-2 words) require exact full title match to prevent false positives
        # e.g., "Women's Hell" must appear as a phrase — matching just "hell" alone won't work
        if len(search_title_words) <= 2:
            actual_threshold = 0.5 if has_exact_title else 1.0
        else:
            actual_threshold = 0.6 if has_exact_title else threshold

        is_match = overlap_percentage >= actual_threshold
        return (is_match, overlap_percentage, has_exact_title)

    def validate_year_match(self, search_year, result_text):
        """Year validation with flexible ±1 year matching"""
        year_bonus = 0  # Bonus points for year matching
        year_penalty = 0  # Penalty for wrong year

        if search_year and str(search_year).isdigit():
            search_year_int = int(search_year)
            # Check for exact year or ±1 year
            if str(search_year_int) in result_text:
                year_bonus = 10  # Exact match
            elif str(search_year_int - 1) in result_text or str(search_year_int + 1) in result_text:
                year_bonus = 5  # Close match (±1 year)
            else:
                # Check if any year appears that's way off (2+ years)
                years_in_text = re.findall(r'\b(19\d{2}|20\d{2})\b', result_text)
                years_in_text = [int(y) for y in years_in_text]
                if years_in_text:
                    closest_year = min(years_in_text, key=lambda y: abs(y - search_year_int))
                    year_diff = abs(closest_year - search_year_int)
                    if year_diff >= 2:
                        year_penalty = 20  # Probably wrong movie
                # If search_year present but no year found in result_text, treat as neutral (year_penalty=0)
                # This handles cases where year is missing rather than conflicting

        return (year_bonus, year_penalty)

    def find_watch_link(self, title, year):
        """Override in subclasses to implement platform-specific logic."""
        raise NotImplementedError


class NetflixScraper(BasePlatformScraper):
    """Scraper for Netflix watch links using Playwright."""

    SELECTORS = [
        ".title-card a",
        "[data-uia='title-card'] a",
        ".search-result a",
        "a[href*='/title/']",
        "[data-testid='movie-card'] a",
        ".gallery-lockups a"
    ]

    def find_watch_link(self, title, year):
        """Find Netflix watch link by searching for the movie."""
        try:
            search_url = f"https://www.netflix.com/search?q={quote(title)}"
            logger.debug(f"[NetflixScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short randomized wait for dynamic content (stealth hardening)
            self.page.wait_for_timeout(random.randint(400, 900))

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    logger.debug(f"[NetflixScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('agent_scraper', {}).get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        logger.debug(f"[NetflixScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            for j, element in enumerate(elements[:8]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and 'netflix.com/title/' in href:
                                        # Title validation - consistent threshold for all selectors
                                        try:
                                            parent_text = element.locator("xpath=./..").text_content().lower()
                                            is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, parent_text, 0.7)

                                            if not is_match:
                                                logger.debug(f"[NetflixScraper] Element {j+1}: Title match failed ({overlap_percentage:.1%}), skipping")
                                                continue

                                            # Year validation - always applied
                                            year_bonus, year_penalty = self.validate_year_match(year, parent_text)
                                            if year_penalty > 0:
                                                logger.debug(f"[NetflixScraper] Element {j+1}: Year penalty applied (probably wrong movie), skipping")
                                                continue

                                            # Negative keyword detection
                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                            has_negative = any(keyword in parent_text for keyword in negative_keywords)
                                            if has_negative:
                                                logger.debug(f"[NetflixScraper] Element {j+1}: Contains negative keywords, skipping")
                                                continue

                                            logger.info(f"[NetflixScraper] ✓ Found Netflix link for {title} using selector {selector}")
                                            logger.debug(f"[NetflixScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                            return {
                                                'link': href,
                                                'selector_used': selector
                                            }

                                        except Exception as validation_error:
                                            # Try expanded parent container selection
                                            try:
                                                ancestor_selectors = [
                                                    "xpath=./ancestor::div[contains(@class, 'title-card')]",
                                                    "xpath=./ancestor::div[contains(@class, 'slider-item')]",
                                                    "xpath=./ancestor::div[contains(@class, 'gallery-lockups')]",
                                                    "xpath=./ancestor::div[contains(@data-uia, 'title')]"
                                                ]

                                                expanded_parent_text = None
                                                for ancestor_selector in ancestor_selectors:
                                                    try:
                                                        ancestor = element.locator(ancestor_selector).first
                                                        if ancestor.count() > 0:
                                                            expanded_parent_text = ancestor.text_content().lower()
                                                            if expanded_parent_text and len(expanded_parent_text.strip()) > 0:
                                                                break
                                                    except:
                                                        continue

                                                if expanded_parent_text:
                                                    is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, expanded_parent_text)
                                                    if is_match:
                                                        year_bonus, year_penalty = self.validate_year_match(year, expanded_parent_text)
                                                        if year_penalty == 0:
                                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                                            has_negative = any(keyword in expanded_parent_text for keyword in negative_keywords)
                                                            if not has_negative:
                                                                logger.info(f"[NetflixScraper] ✓ Found Netflix link using expanded parent search")
                                                                logger.debug(f"[NetflixScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                                                return {
                                                                    'link': href,
                                                                    'selector_used': selector
                                                                }
                                            except Exception:
                                                pass

                                            logger.debug(f"[NetflixScraper] Element {j+1}: Validation error: {validation_error}")
                                            continue

                                except Exception as e:
                                    logger.warning(f"[NetflixScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        logger.debug(f"[NetflixScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    logger.warning(f"[NetflixScraper] Error with selector {selector}: {e}")
                    continue

            logger.warning(f"[NetflixScraper] ✗ No valid Netflix links found for: {title}")
            return None

        except Exception as e:
            logger.error(f"[NetflixScraper] ✗ Netflix scraping error for {title}: {e}")
            return None


class DisneyPlusScraper(BasePlatformScraper):
    """Scraper for Disney+ watch links using Playwright."""

    SELECTORS = [
        "[data-testid='search-result'] a",
        ".search-result a",
        "[data-testid='movie-card'] a",
        "a[href*='/movies/']",
        "a[href*='/series/']",
        "a[href*='/video/']"
    ]

    def find_watch_link(self, title, year):
        """Find Disney+ watch link by searching for the movie."""
        try:
            search_url = f"https://www.disneyplus.com/search?q={quote(title)}"
            logger.debug(f"[DisneyPlusScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short randomized wait for dynamic content (stealth hardening)
            self.page.wait_for_timeout(random.randint(400, 900))

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    logger.debug(f"[DisneyPlusScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('agent_scraper', {}).get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        logger.debug(f"[DisneyPlusScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            for j, element in enumerate(elements[:8]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and ('disneyplus.com/movies/' in href or 'disneyplus.com/series/' in href or 'disneyplus.com/video/' in href):
                                        try:
                                            parent_text = element.locator("xpath=./..").text_content().lower()
                                            is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, parent_text, 0.7)

                                            if not is_match:
                                                logger.debug(f"[DisneyPlusScraper] Element {j+1}: Title match failed ({overlap_percentage:.1%}), skipping")
                                                continue

                                            year_bonus, year_penalty = self.validate_year_match(year, parent_text)
                                            if year_penalty > 0:
                                                logger.debug(f"[DisneyPlusScraper] Element {j+1}: Year penalty applied (probably wrong movie), skipping")
                                                continue

                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                            has_negative = any(keyword in parent_text for keyword in negative_keywords)
                                            if has_negative:
                                                logger.debug(f"[DisneyPlusScraper] Element {j+1}: Contains negative keywords, skipping")
                                                continue

                                            logger.info(f"[DisneyPlusScraper] ✓ Found Disney+ link for {title} using selector {selector}")
                                            logger.debug(f"[DisneyPlusScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                            return {
                                                'link': href,
                                                'selector_used': selector
                                            }

                                        except Exception as validation_error:
                                            try:
                                                ancestor_selectors = [
                                                    "xpath=./ancestor::div[contains(@data-testid, 'search-result')]",
                                                    "xpath=./ancestor::div[contains(@class, 'search-result')]",
                                                    "xpath=./ancestor::div[contains(@data-testid, 'movie-card')]",
                                                    "xpath=./ancestor::div[contains(@class, 'content-tile')]"
                                                ]

                                                expanded_parent_text = None
                                                for ancestor_selector in ancestor_selectors:
                                                    try:
                                                        ancestor = element.locator(ancestor_selector).first
                                                        if ancestor.count() > 0:
                                                            expanded_parent_text = ancestor.text_content().lower()
                                                            if expanded_parent_text and len(expanded_parent_text.strip()) > 0:
                                                                break
                                                    except:
                                                        continue

                                                if expanded_parent_text:
                                                    is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, expanded_parent_text)
                                                    if is_match:
                                                        year_bonus, year_penalty = self.validate_year_match(year, expanded_parent_text)
                                                        if year_penalty == 0:
                                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                                            has_negative = any(keyword in expanded_parent_text for keyword in negative_keywords)
                                                            if not has_negative:
                                                                logger.info(f"[DisneyPlusScraper] ✓ Found Disney+ link using expanded parent search")
                                                                logger.debug(f"[DisneyPlusScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                                                return {
                                                                    'link': href,
                                                                    'selector_used': selector
                                                                }
                                            except Exception:
                                                pass

                                            logger.debug(f"[DisneyPlusScraper] Element {j+1}: Validation error: {validation_error}")
                                            continue

                                except Exception as e:
                                    logger.warning(f"[DisneyPlusScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        logger.debug(f"[DisneyPlusScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    logger.warning(f"[DisneyPlusScraper] Error with selector {selector}: {e}")
                    continue

            logger.warning(f"[DisneyPlusScraper] ✗ No valid Disney+ links found for: {title}")
            return None

        except Exception as e:
            logger.error(f"[DisneyPlusScraper] ✗ Disney+ scraping error for {title}: {e}")
            return None


class HBOMaxScraper(BasePlatformScraper):
    """Scraper for HBO Max/Max watch links using Playwright."""

    SELECTORS = [
        ".search-result a",
        "[data-testid='tile'] a",
        "[data-testid='movie-card'] a",
        "a[href*='/movies/']",
        "a[href*='/shows/']",
        ".content-card a"
    ]

    def find_watch_link(self, title, year):
        """Find HBO Max/Max watch link by searching for the movie."""
        try:
            search_url = f"https://www.max.com/search?q={quote(title)}"
            logger.debug(f"[HBOMaxScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short randomized wait for dynamic content (stealth hardening)
            self.page.wait_for_timeout(random.randint(400, 900))

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    logger.debug(f"[HBOMaxScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('agent_scraper', {}).get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        logger.debug(f"[HBOMaxScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            for j, element in enumerate(elements[:8]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and ('max.com/movies/' in href or 'max.com/shows/' in href):
                                        # Title validation - consistent threshold for all selectors
                                        try:
                                            parent_text = element.locator("xpath=./..").text_content().lower()
                                            is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, parent_text, 0.7)

                                            if not is_match:
                                                logger.debug(f"[HBOMaxScraper] Element {j+1}: Title match failed ({overlap_percentage:.1%}), skipping")
                                                continue

                                            # Year validation - always applied
                                            year_bonus, year_penalty = self.validate_year_match(year, parent_text)
                                            if year_penalty > 0:
                                                logger.debug(f"[HBOMaxScraper] Element {j+1}: Year penalty applied (probably wrong movie), skipping")
                                                continue

                                            # Negative keyword detection
                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                            has_negative = any(keyword in parent_text for keyword in negative_keywords)
                                            if has_negative:
                                                logger.debug(f"[HBOMaxScraper] Element {j+1}: Contains negative keywords, skipping")
                                                continue

                                            logger.info(f"[HBOMaxScraper] ✓ Found Max link for {title} using selector {selector}")
                                            logger.debug(f"[HBOMaxScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                            return {
                                                'link': href,
                                                'selector_used': selector
                                            }

                                        except Exception as validation_error:
                                            # Try expanded parent container selection
                                            try:
                                                ancestor_selectors = [
                                                    "xpath=./ancestor::div[contains(@class, 'search-result')]",
                                                    "xpath=./ancestor::div[contains(@data-testid, 'tile')]",
                                                    "xpath=./ancestor::div[contains(@data-testid, 'movie-card')]",
                                                    "xpath=./ancestor::div[contains(@class, 'content-card')]"
                                                ]

                                                expanded_parent_text = None
                                                for ancestor_selector in ancestor_selectors:
                                                    try:
                                                        ancestor = element.locator(ancestor_selector).first
                                                        if ancestor.count() > 0:
                                                            expanded_parent_text = ancestor.text_content().lower()
                                                            if expanded_parent_text and len(expanded_parent_text.strip()) > 0:
                                                                break
                                                    except:
                                                        continue

                                                if expanded_parent_text:
                                                    is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, expanded_parent_text)
                                                    if is_match:
                                                        year_bonus, year_penalty = self.validate_year_match(year, expanded_parent_text)
                                                        if year_penalty == 0:
                                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                                            has_negative = any(keyword in expanded_parent_text for keyword in negative_keywords)
                                                            if not has_negative:
                                                                logger.info(f"[HBOMaxScraper] ✓ Found Max link using expanded parent search")
                                                                logger.debug(f"[HBOMaxScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                                                return {
                                                                    'link': href,
                                                                    'selector_used': selector
                                                                }
                                            except Exception:
                                                pass

                                            logger.debug(f"[HBOMaxScraper] Element {j+1}: Validation error: {validation_error}")
                                            continue

                                except Exception as e:
                                    logger.warning(f"[HBOMaxScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        logger.debug(f"[HBOMaxScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    logger.warning(f"[HBOMaxScraper] Error with selector {selector}: {e}")
                    continue

            logger.warning(f"[HBOMaxScraper] ✗ No valid Max links found for: {title}")
            return None

        except Exception as e:
            logger.error(f"[HBOMaxScraper] ✗ Max scraping error for {title}: {e}")
            return None


class HuluScraper(BasePlatformScraper):
    """Scraper for Hulu watch links using Playwright."""

    SELECTORS = [
        ".entity-card a",
        ".search-results a",
        "[data-testid='movie-card'] a",
        "a[href*='/movie/']",
        "a[href*='/series/']",
        "a[href*='/watch/']"
    ]

    def find_watch_link(self, title, year):
        """Find Hulu watch link by searching for the movie."""
        try:
            search_url = f"https://www.hulu.com/search?q={quote(title)}"
            logger.debug(f"[HuluScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short randomized wait for dynamic content (stealth hardening)
            self.page.wait_for_timeout(random.randint(400, 900))

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    logger.debug(f"[HuluScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('agent_scraper', {}).get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        logger.debug(f"[HuluScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            for j, element in enumerate(elements[:8]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and ('hulu.com/movie/' in href or 'hulu.com/series/' in href or 'hulu.com/watch/' in href):
                                        # Title validation - consistent threshold for all selectors
                                        try:
                                            parent_text = element.locator("xpath=./..").text_content().lower()
                                            is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, parent_text, 0.7)

                                            if not is_match:
                                                logger.debug(f"[HuluScraper] Element {j+1}: Title match failed ({overlap_percentage:.1%}), skipping")
                                                continue

                                            # Year validation - always applied
                                            year_bonus, year_penalty = self.validate_year_match(year, parent_text)
                                            if year_penalty > 0:
                                                logger.debug(f"[HuluScraper] Element {j+1}: Year penalty applied (probably wrong movie), skipping")
                                                continue

                                            # Negative keyword detection
                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                            has_negative = any(keyword in parent_text for keyword in negative_keywords)
                                            if has_negative:
                                                logger.debug(f"[HuluScraper] Element {j+1}: Contains negative keywords, skipping")
                                                continue

                                            logger.info(f"[HuluScraper] ✓ Found Hulu link for {title} using selector {selector}")
                                            logger.debug(f"[HuluScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                            return {
                                                'link': href,
                                                'selector_used': selector
                                            }

                                        except Exception as validation_error:
                                            # Try expanded parent container selection
                                            try:
                                                ancestor_selectors = [
                                                    "xpath=./ancestor::div[contains(@class, 'entity-card')]",
                                                    "xpath=./ancestor::div[contains(@class, 'search-results')]",
                                                    "xpath=./ancestor::div[contains(@data-testid, 'movie-card')]",
                                                    "xpath=./ancestor::div[contains(@class, 'content-tile')]"
                                                ]

                                                expanded_parent_text = None
                                                for ancestor_selector in ancestor_selectors:
                                                    try:
                                                        ancestor = element.locator(ancestor_selector).first
                                                        if ancestor.count() > 0:
                                                            expanded_parent_text = ancestor.text_content().lower()
                                                            if expanded_parent_text and len(expanded_parent_text.strip()) > 0:
                                                                break
                                                    except:
                                                        continue

                                                if expanded_parent_text:
                                                    is_match, overlap_percentage, has_exact_title = self.validate_title_match(title, expanded_parent_text)
                                                    if is_match:
                                                        year_bonus, year_penalty = self.validate_year_match(year, expanded_parent_text)
                                                        if year_penalty == 0:
                                                            negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order']
                                                            has_negative = any(keyword in expanded_parent_text for keyword in negative_keywords)
                                                            if not has_negative:
                                                                logger.info(f"[HuluScraper] ✓ Found Hulu link using expanded parent search")
                                                                logger.debug(f"[HuluScraper] ✓ Title match: {overlap_percentage:.1%}, Year bonus: +{year_bonus}")
                                                                return {
                                                                    'link': href,
                                                                    'selector_used': selector
                                                                }
                                            except Exception:
                                                pass

                                            logger.debug(f"[HuluScraper] Element {j+1}: Validation error: {validation_error}")
                                            continue

                                except Exception as e:
                                    logger.warning(f"[HuluScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        logger.debug(f"[HuluScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    logger.warning(f"[HuluScraper] Error with selector {selector}: {e}")
                    continue

            logger.warning(f"[HuluScraper] ✗ No valid Hulu links found for: {title}")
            return None

        except Exception as e:
            logger.error(f"[HuluScraper] ✗ Hulu scraping error for {title}: {e}")
            return None


class AgentLinkScraper(PlaywrightScraperBase):
    """Agent-based link scraper using Playwright to find direct watch links.

    v2: Now inherits from PlaywrightScraperBase for shared functionality.
    """

    def __init__(self, cache_file='cache/agent_links_cache.json', config=None):
        """Initialize the agent scraper with configuration."""
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=None,  # Agent scraper uses print, not logger
            config_key=None,  # No centralized config key for agent scraper
            log_prefix='AgentLinkScraper',
            screenshot_subdir='agent'
        )

        # Supported platforms mapping
        self.platform_scrapers = {
            'Netflix': NetflixScraper,
            'Disney+': DisneyPlusScraper,
            'Disney Plus': DisneyPlusScraper,
            'HBO Max': HBOMaxScraper,
            'Max': HBOMaxScraper,
            'Hulu': HuluScraper
        }

        logger.info(f"[AgentLinkScraper] Initialized with cache_file={cache_file}")
        logger.info(f"[AgentLinkScraper] Cache loaded: {len(self.cache.get('movies', {}))} entries")
        logger.info(f"[AgentLinkScraper] Supported platforms: {list(self.platform_scrapers.keys())}")

    def _get_cache_default(self):
        """Return custom cache structure for agent scraper."""
        return {'movies': {}, 'last_updated': datetime.now().isoformat()}

    def _get_cache_count(self):
        """Count movies in custom cache structure."""
        return len(self.cache.get('movies', {}))

    def _log(self, message, level='info'):
        """Log message using Python logger."""
        log_method = getattr(logger, level, logger.info)
        log_method(f"[AgentLinkScraper] {message}")

    def _save_cache(self):
        """Save cache with last_updated timestamp."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            self.cache['last_updated'] = datetime.now().isoformat()
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            logger.info(f"[AgentLinkScraper] Cache saved: {len(self.cache.get('movies', {}))} entries")
        except Exception as e:
            logger.error(f"[AgentLinkScraper] Failed to save cache: {e}")
            raise

    def _retry_with_backoff(self, fn, max_attempts=None, base_delay=None, max_delay=None, jitter_ratio=None):
        """Retry function with exponential backoff and result metadata."""
        if max_attempts is None:
            max_attempts = self.config.get('max_retries', 3)

        backoff_config = self.config.get('exponential_backoff', {})
        if base_delay is None:
            base_delay = backoff_config.get('base_delay', 0.5)
        if max_delay is None:
            max_delay = backoff_config.get('max_delay', 5.0)
        if jitter_ratio is None:
            jitter_ratio = backoff_config.get('jitter_ratio', 0.2)

        last_error = None
        for attempt in range(max_attempts):
            try:
                result = fn()
                if result is not None:
                    if isinstance(result, dict):
                        result['retry_count'] = attempt + 1
                        if last_error:
                            result['last_error'] = str(last_error)
                        return result
                    else:
                        return {
                            'link': result,
                            'retry_count': attempt + 1,
                            'last_error': str(last_error) if last_error else None
                        }

                if attempt < max_attempts - 1:
                    delay = min(max_delay, base_delay * (2 ** attempt))
                    jitter = random.uniform(-jitter_ratio * delay, jitter_ratio * delay)
                    sleep_time = delay + jitter
                    logger.warning(f"[AgentLinkScraper] Attempt {attempt + 1} failed, retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

            except (PlaywrightTimeoutError, Exception) as e:
                last_error = e
                logger.error(f"[AgentLinkScraper] Attempt {attempt + 1} error: {e}")
                if attempt < max_attempts - 1:
                    delay = min(max_delay, base_delay * (2 ** attempt))
                    jitter = random.uniform(-jitter_ratio * delay, jitter_ratio * delay)
                    sleep_time = delay + jitter
                    logger.warning(f"[AgentLinkScraper] Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

        return {
            'link': None,
            'retry_count': max_attempts,
            'last_error': str(last_error) if last_error else "No link found after retries"
        }

    def _capture_failure_diagnostics(self, movie_id, title, service, error_msg):
        """Capture screenshot and HTML on failure for debugging."""
        if not self.screenshots_enabled or not self.page:
            return {}

        try:
            os.makedirs(self.screenshot_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_base = f"{movie_id}_{service}_{timestamp}"

            screenshot_path = os.path.join(self.screenshot_dir, f"{filename_base}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)

            html_path = os.path.join(self.screenshot_dir, f"{filename_base}.html")
            html_content = self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.debug(f"[AgentLinkScraper] Screenshot saved: {screenshot_path}")
            self._cleanup_old_screenshots()

            return {
                'screenshot': screenshot_path,
                'html': html_path,
                'error': error_msg
            }

        except Exception as e:
            logger.error(f"[AgentLinkScraper] Failed to capture diagnostics: {e}")
            return {'error': error_msg}

    def _is_cache_expired(self, cached_entry):
        """Check if cache entry has expired."""
        if 'expires_at' not in cached_entry:
            if 'scraped_at' in cached_entry:
                try:
                    scraped_at = datetime.fromisoformat(cached_entry['scraped_at'])
                    cache_ttl_days = self.config.get('cache_ttl_days', 30)
                    expires_at = scraped_at + timedelta(days=cache_ttl_days)
                    return datetime.now() > expires_at
                except (ValueError, KeyError):
                    pass
            return False

        try:
            expires_at = datetime.fromisoformat(cached_entry['expires_at'])
            return datetime.now() > expires_at
        except (ValueError, KeyError):
            return True

    def _is_service_cache_expired(self, service_cache):
        """Check if service-specific cache entry has expired."""
        return self._is_cache_expired(service_cache)

    def find_watch_link(self, movie_id, title, year, service_name):
        """Main entry point to find watch link for a movie on a specific service."""
        logger.info(f"[AgentLinkScraper] Finding link for {title} ({year}) on {service_name}...")
        movie_id_str = str(movie_id)

        # Check cache first
        if movie_id_str in self.cache['movies']:
            cached_entry = self.cache['movies'][movie_id_str]
            if 'streaming' in cached_entry:
                cached_streaming = cached_entry['streaming']

                service_cache = None
                if isinstance(cached_streaming, dict):
                    if 'service' in cached_streaming and cached_streaming.get('service') == service_name:
                        service_cache = cached_streaming
                    elif service_name in cached_streaming:
                        service_cache = cached_streaming[service_name]

                if service_cache and not self._is_service_cache_expired(service_cache):
                    logger.info(f"[AgentLinkScraper] Cache hit for {title} on {service_name}")
                    result_dict = {
                        'service': service_name,
                        'link': service_cache.get('link'),
                        'cached': True
                    }

                    if 'selector_used' in service_cache:
                        result_dict['selector_used'] = service_cache['selector_used']
                    if 'last_error' in service_cache:
                        result_dict['last_error'] = service_cache['last_error']
                    if 'retry_count' in service_cache:
                        result_dict['retry_count'] = service_cache['retry_count']

                    return result_dict

        # Check if service is supported
        if service_name not in self.platform_scrapers:
            logger.warning(f"[AgentLinkScraper] Service '{service_name}' not supported")
            return {
                'service': service_name,
                'link': None,
                'cached': False,
                'last_error': f"Service '{service_name}' not supported",
                'retry_count': 0
            }

        try:
            logger.debug(f"[AgentLinkScraper] Initializing browser for {title}...")
            self._init_browser()

            logger.debug(f"[AgentLinkScraper] Applying rate limit...")
            self._enforce_rate_limit()

            # Get appropriate scraper class and create instance
            scraper_class = self.platform_scrapers[service_name]
            logger.debug(f"[AgentLinkScraper] Using {scraper_class.__name__} for {service_name}")
            scraper = scraper_class(self.page, self.config)

            # Attempt to find link with retry
            def scrape_attempt():
                return scraper.find_watch_link(title, year)

            backoff_config = self.config.get('exponential_backoff', {})
            result = self._retry_with_backoff(
                scrape_attempt,
                base_delay=backoff_config.get('base_delay', 0.5),
                max_delay=backoff_config.get('max_delay', 5.0),
                jitter_ratio=backoff_config.get('jitter_ratio', 0.2)
            )
            logger.debug(f"[AgentLinkScraper] Scraper returned: {result}")

            # Extract data from result
            if isinstance(result, dict):
                link = result.get('link')
                retry_count = result.get('retry_count')
                last_error = result.get('last_error')
                selector_used = result.get('selector_used')
            else:
                link = result
                retry_count = None
                last_error = None
                selector_used = None

            # Cache result
            logger.debug(f"[AgentLinkScraper] Caching result for {title}...")
            success = link is not None
            diagnostics = {}

            if not success:
                diagnostics = self._capture_failure_diagnostics(
                    movie_id_str, title, service_name, last_error or "No link found after retries"
                )

            self._cache_result(
                movie_id_str, service_name, link, success, diagnostics,
                retry_count=retry_count, last_error=last_error, selector_used=selector_used
            )

            result_dict = {
                'service': service_name,
                'link': link,
                'cached': False
            }

            if selector_used is not None:
                result_dict['selector_used'] = selector_used
            if last_error is not None:
                result_dict['last_error'] = last_error
            if retry_count is not None:
                result_dict['retry_count'] = retry_count

            return result_dict

        except Exception as e:
            logger.error(f"[AgentLinkScraper] Agent scraper error for {title} on {service_name}: {e}")

            diagnostics = self._capture_failure_diagnostics(
                movie_id_str, title, service_name, str(e)
            )

            self._cache_result(
                movie_id_str, service_name, None, False, diagnostics,
                retry_count=1, last_error=str(e), selector_used=None
            )

            return {
                'service': service_name,
                'link': None,
                'cached': False,
                'last_error': str(e),
                'retry_count': 1
            }

    def _cache_result(self, movie_id, service_name, link, success, diagnostics=None, retry_count=None, last_error=None, selector_used=None):
        """Cache the scraping result with enhanced metadata."""
        if movie_id not in self.cache['movies']:
            self.cache['movies'][movie_id] = {'streaming': {}}

        if 'streaming' not in self.cache['movies'][movie_id]:
            self.cache['movies'][movie_id]['streaming'] = {}
        elif not isinstance(self.cache['movies'][movie_id]['streaming'], dict) or 'service' in self.cache['movies'][movie_id]['streaming']:
            # Migrate old format
            old_streaming = self.cache['movies'][movie_id]['streaming']
            if isinstance(old_streaming, dict) and 'service' in old_streaming:
                old_service = old_streaming.get('service')
                if old_service:
                    migrated_entry = {
                        'link': old_streaming.get('link'),
                        'scraped_at': self.cache['movies'][movie_id].get('scraped_at', datetime.now().isoformat()),
                        'expires_at': self.cache['movies'][movie_id].get('expires_at', (datetime.now() + timedelta(days=30)).isoformat()),
                        'success': self.cache['movies'][movie_id].get('success', False),
                    }
                    migrated_entry = {k: v for k, v in migrated_entry.items() if v is not None}
                    self.cache['movies'][movie_id]['streaming'] = {old_service: migrated_entry}
                else:
                    self.cache['movies'][movie_id]['streaming'] = {}
            else:
                self.cache['movies'][movie_id]['streaming'] = {}

        cache_ttl_days = self.config.get('cache_ttl_days', 30)
        expires_at = datetime.now() + timedelta(days=cache_ttl_days)

        service_entry = {
            'link': link,
            'scraped_at': datetime.now().isoformat(),
            'expires_at': expires_at.isoformat(),
            'success': success
        }

        if retry_count is not None:
            service_entry['retry_count'] = retry_count
        if last_error is not None:
            service_entry['last_error'] = last_error
        if selector_used is not None:
            service_entry['selector_used'] = selector_used

        if diagnostics:
            if 'error' in diagnostics:
                diagnostics['last_error'] = diagnostics.pop('error')
            service_entry.update(diagnostics)

        self.cache['movies'][movie_id]['streaming'][service_name] = service_entry

        self.cache['movies'][movie_id].update({
            'source': 'agent_scraper',
            'last_updated': datetime.now().isoformat()
        })

    def close(self):
        """Cleanup method to quit browser and save cache."""
        logger.info("[AgentLinkScraper] Closing browser and saving cache...")

        self._cleanup_browser()
        logger.info("[AgentLinkScraper] Browser closed")

        self._save_cache()
        logger.info("[AgentLinkScraper] Cleanup complete")
