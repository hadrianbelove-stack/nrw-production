#!/usr/bin/env python3
"""
Streaming Platform Scraper v2 - Migrated to use PlaywrightScraperBase.

This is a WALLED GARDEN version for testing. Do not use in production
until comparison tests pass.

Changes from v1 (streaming_platform_scraper.py):
- Inherits from PlaywrightScraperBase instead of duplicating code
- Maintains backward-compatible constructor signature
- All platform-specific logic preserved exactly

Inherited from base class:
- _log(), _log_metrics()
- _cleanup_old_screenshots()
- _init_browser(), _init_browser_shared(), _init_browser_local()
- _cleanup_browser()
- _enforce_rate_limit()
- stats and counters initialization
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import urllib.parse
import os
import random
import re
import json
import logging
from datetime import datetime, timedelta
from constants import PLACEHOLDER_ASINS, get_scraper_config

from scraper_base import PlaywrightScraperBase

# Module-level logger
logger = logging.getLogger(__name__)


class StreamingPlatformScraper(PlaywrightScraperBase):
    """Playwright-based streaming platform scraper for Amazon Prime Video and Apple TV deep links.

    v2: Now inherits from PlaywrightScraperBase for shared functionality.
    """

    def __init__(self, headless=True, timeout_seconds=None, rate_limit_seconds=None, config=None, **kwargs):
        """Initialize Playwright browser with anti-bot measures.

        Maintains backward-compatible constructor signature from v1.
        """
        # Build config dict for base class
        internal_config = config or {}

        # Get centralized scraper configuration
        scraper_config = get_scraper_config(internal_config, 'vod_scraper')

        # Store original parameters before base class init
        self._headless = headless
        self._timeout_seconds = timeout_seconds or scraper_config.get('timeout', 30)
        self._rate_limit_seconds = rate_limit_seconds or scraper_config.get('rate_limit', 2.0)

        # Retry and backoff configuration
        backoff_config = scraper_config.get('exponential_backoff', {})
        self.max_retries = kwargs.get('max_retries') or scraper_config.get('max_retries', 3)
        self.base_delay = kwargs.get('base_delay') or backoff_config.get('base_delay', 0.5)
        self.max_delay = kwargs.get('max_delay') or backoff_config.get('max_delay', 5.0)
        self.jitter_ratio = kwargs.get('jitter_ratio') or backoff_config.get('jitter_ratio', 0.2)

        # Initialize base class with ASIN cache file
        super().__init__(
            cache_file='cache/amazon_asin_cache.json',
            config=internal_config,
            logger=None,  # Streaming scraper uses print, not logger
            config_key='vod_scraper',
            log_prefix='StreamingPlatformScraper',
            screenshot_subdir='streaming'
        )

        # Override rate limit with constructor parameter
        self.rate_limit = self._rate_limit_seconds

        # Alias for backward compatibility
        self.timeout_seconds = self._timeout_seconds
        self.headless = self._headless
        self._amazon_asin_cache = self.cache  # Alias for v1 compatibility

        # Override stats with streaming-specific fields
        self.stats = {
            'searches': 0,
            'successes': 0,
            'failures': 0,
            'timeouts': 0
        }

    def _log(self, message, level='info'):
        """Log message with component prefix using Python logger."""
        log_method = getattr(logger, level, logger.info)
        log_method(f"[StreamingPlatformScraper] {message}")

    def _save_asin_cache(self):
        """Save Amazon ASIN cache to disk - alias for base _save_cache."""
        self._save_cache()

    def _load_asin_cache(self):
        """Load Amazon ASIN cache - returns current cache (already loaded by base)."""
        return self.cache

    def _retry_with_backoff(self, fn):
        """Retry function with exponential backoff."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = fn()
                if result is not None:
                    return result

                if attempt < self.max_retries - 1:
                    delay = min(self.max_delay, self.base_delay * (2 ** attempt))
                    jitter = random.uniform(-self.jitter_ratio * delay, self.jitter_ratio * delay)
                    sleep_time = delay + jitter
                    logger.warning(f"  Attempt {attempt + 1} failed, retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

            except (PlaywrightTimeoutError, Exception) as e:
                last_error = e
                logger.error(f"  Attempt {attempt + 1} error: {e}")
                if attempt < self.max_retries - 1:
                    delay = min(self.max_delay, self.base_delay * (2 ** attempt))
                    jitter = random.uniform(-self.jitter_ratio * delay, self.jitter_ratio * delay)
                    sleep_time = delay + jitter
                    logger.warning(f"  Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

        return None

    def _capture_failure_diagnostics(self, title, year, platform, error_msg):
        """Capture screenshot and HTML on failure for debugging."""
        if not self.screenshots_enabled or not self.page:
            return

        try:
            os.makedirs(self.screenshot_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r'[^\w\-_\.]', '_', title)[:30]
            filename_base = f"{safe_title}_{year}_{platform}_{timestamp}"

            screenshot_path = os.path.join(self.screenshot_dir, f"{filename_base}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)

            html_path = os.path.join(self.screenshot_dir, f"{filename_base}.html")
            html_content = self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.debug(f"  Diagnostics saved: {screenshot_path}")
            self._cleanup_old_screenshots()

        except Exception as e:
            logger.error(f"  Failed to capture diagnostics: {e}")

    def find_amazon_link(self, title, year):
        """Search Amazon Prime Video and extract movie detail page URL.

        Args:
            title: Movie title
            year: Release year

        Returns:
            Deep link URL (https://www.amazon.com/gp/video/detail/{ASIN}) or None
        """
        def search_attempt():
            return self._find_amazon_link_core(title, year)

        result = self._retry_with_backoff(search_attempt)
        if result is None:
            self._capture_failure_diagnostics(title, year, "amazon", "No link found after retries")
        return result

    def _find_amazon_link_core(self, title, year):
        """Core Amazon search logic (wrapped by retry mechanism)."""
        start_time = time.time()
        try:
            self._init_browser()

            search_query = f"{title} {year}"
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://www.amazon.com/s?k={encoded_query}&i=instant-video"

            logger.debug(f"  Searching Amazon for: {search_query}")
            logger.debug(f"  URL: {search_url}")

            self.page.goto(search_url, wait_until='domcontentloaded', timeout=self.timeout_seconds * 1000)

            logger.debug(f"  Page loaded, waiting for search results...")

            try:
                self.page.wait_for_selector("article[data-testid='card'], .s-result-item, .s-widget-container, [data-testid='grid-container'], a[href*='/gp/video/detail/']", timeout=self.timeout_seconds * 1000)
                logger.debug(f"  Search results loaded successfully")
            except PlaywrightTimeoutError:
                logger.warning(f"  Warning: Search results may not have loaded completely")

            # High-confidence selectors
            high_confidence_selectors = [
                "article[data-testid='card'] a[href*='/gp/video/detail/']",
                "[data-testid='packshot'] a[href*='/gp/video/detail/']",
                "div[data-component-type='s-search-result'] h2 a[href*='/gp/video/detail/']",
                ".s-widget-container a[href*='/gp/video/detail/']",
                "a[href*='/gp/video/detail/']",
            ]

            all_selectors = high_confidence_selectors + [
                "div[data-component-type='s-search-result'] h2 a[href*='/dp/']",
                "[data-cy='title-recipe-title'] a",
                ".s-widget-container a[href*='/dp/']",
                ".s-result-item h2.a-size-mini a",
                ".s-result-item .a-text-normal",
                ".s-result-item a.a-link-normal",
                "h2 a[href*='/dp/']",
                "a[href*='/dp/'][data-asin]",
                "[data-asin] a[href*='/dp/']",
                ".s-title-instructions-style a",
                "a[href*='/dp/']",
                "a[href*='/gp/video/']"
            ]

            logger.debug(f"  Trying {len(all_selectors)} different selectors...")

            for i, selector in enumerate(all_selectors, 1):
                try:
                    is_high_confidence = selector in high_confidence_selectors
                    selector_type = "HIGH-CONFIDENCE" if is_high_confidence else "FALLBACK"

                    elements = self.page.locator(selector).all()

                    for j, element in enumerate(elements):
                        href = element.get_attribute('href')
                        if href and ('/gp/video/detail/' in href or '/dp/' in href):
                            # Check for placeholder ASINs
                            if any(asin in href for asin in PLACEHOLDER_ASINS):
                                continue

                            # Enhanced sponsored detection
                            is_sponsored = False
                            try:
                                parent = element.locator("xpath=./ancestor::div[contains(@class, 'sp-sponsored') or contains(@data-component-type, 'sp-sponsored-result')]").first
                                if parent.count() > 0:
                                    is_sponsored = True
                            except:
                                pass

                            if is_sponsored:
                                continue

                            # Title validation
                            try:
                                parent = None
                                # Try Prime Video search layout (article cards)
                                try:
                                    parent = element.locator("xpath=./ancestor::article[@data-testid='card']").first
                                    if parent.count() == 0:
                                        parent = None
                                except:
                                    pass

                                # Try classic Amazon product search layout
                                if parent is None:
                                    try:
                                        parent = element.locator("xpath=./ancestor::div[@data-component-type='s-search-result']").first
                                        if parent.count() == 0:
                                            parent = None
                                    except:
                                        pass

                                if parent is None:
                                    try:
                                        parent = element.locator("xpath=./ancestor::div[contains(@class, 's-result-item')]").first
                                        if parent.count() == 0:
                                            parent = element.locator("xpath=./ancestor::div[contains(@class, 's-widget-container')]").first
                                    except:
                                        pass

                                if parent and parent.count() > 0:
                                    text_content = parent.text_content().lower()

                                    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}

                                    def normalize_text(text):
                                        import unicodedata
                                        normalized = unicodedata.normalize('NFD', text)
                                        ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
                                        return re.sub(r'[^a-zA-Z0-9\s]', ' ', ascii_text)

                                    normalized_title = normalize_text(title.lower())
                                    search_title_words = {word for word in normalized_title.split() if word and word not in stopwords and len(word) > 1}

                                    result_text_lines = text_content.split('\n')[:3]
                                    result_text = ' '.join(result_text_lines).lower()
                                    normalized_result = normalize_text(result_text)

                                    matching_words = sum(1 for word in search_title_words if word in normalized_result)
                                    overlap_percentage = matching_words / len(search_title_words) if search_title_words else 0

                                    has_exact_title = normalized_title in normalized_result

                                    # Short titles require exact full title match to prevent false positives
                                    if len(search_title_words) <= 2:
                                        threshold = 0.5 if has_exact_title else 1.0
                                    else:
                                        threshold = 0.6 if has_exact_title else 0.7

                                    # Use consistent threshold — no relaxation for high-confidence selectors
                                    if overlap_percentage < threshold:
                                        continue

                                    # Check negative keywords
                                    negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order', 'tv series', 'season']
                                    has_negative = any(keyword in result_text for keyword in negative_keywords)
                                    if has_negative:
                                        continue

                                    # Extract ASIN and return
                                    asin_match = re.search(r'/(dp|gp/video/detail)/([A-Z0-9]{10})', href)
                                    if asin_match:
                                        canonical_href = f"https://www.amazon.com/gp/video/detail/{asin_match.group(2)}"
                                    else:
                                        canonical_href = urllib.parse.urljoin('https://www.amazon.com', href)

                                    elapsed_time = time.time() - start_time
                                    logger.info(f"  Found Amazon link: {canonical_href}")
                                    logger.debug(f"  Title match: {overlap_percentage:.1%}")
                                    logger.debug(f"  Search completed in {elapsed_time:.2f} seconds")
                                    return canonical_href

                            except Exception as e:
                                continue

                except Exception as e:
                    continue

            elapsed_time = time.time() - start_time
            logger.warning(f"  No Amazon link found for {title} ({year}) after {elapsed_time:.2f} seconds")
            return None

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"  Error searching Amazon for {title} after {elapsed_time:.2f} seconds: {e}")
            return None

    def find_apple_tv_link(self, title, year):
        """Search Apple TV and extract movie detail page URL.

        Args:
            title: Movie title
            year: Release year

        Returns:
            Deep link URL or None
        """
        def search_attempt():
            return self._find_apple_tv_link_core(title, year)

        result = self._retry_with_backoff(search_attempt)
        if result is None:
            self._capture_failure_diagnostics(title, year, "apple_tv", "No link found after retries")
        return result

    def _find_apple_tv_link_core(self, title, year):
        """Core Apple TV search logic."""
        try:
            self._init_browser()

            search_query = urllib.parse.quote(title)
            search_url = f"https://tv.apple.com/search?term={search_query}"

            logger.debug(f"  Searching Apple TV for: {title}")
            self.page.goto(search_url, wait_until='domcontentloaded', timeout=self.timeout_seconds * 1000)

            selectors = [
                "a[href*='/movie/'][href*='umc.cmc']",
                "[data-test-lockup-type='MOVIE'] a[href*='umc.cmc']",
                ".shelf-grid__list-item a[href*='/movie/']",
                ".shelf-grid__list-item a",
                "[data-test-id='lockup'] a",
                "a[href*='umc.cmc']"
            ]

            for i, selector in enumerate(selectors):
                try:
                    # First selector gets full timeout (page may still render);
                    # rest get quick 3s check since page is already loaded
                    selector_timeout = (self.timeout_seconds * 1000) if i == 0 else 3000
                    self.page.wait_for_selector(selector, timeout=selector_timeout)
                    elements = self.page.locator(selector).all()
                    for element in elements:
                        href = element.get_attribute('href')
                        if href and '/movie/' in href and 'umc.cmc' in href:
                            stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}

                            def normalize_text(text):
                                import unicodedata
                                normalized = unicodedata.normalize('NFD', text)
                                ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
                                return re.sub(r'[^a-zA-Z0-9\s]', ' ', ascii_text)

                            link_text = element.text_content().lower()
                            normalized_title = normalize_text(title.lower())
                            normalized_link_text = normalize_text(link_text)

                            title_words = {word for word in normalized_title.split() if word and word not in stopwords and len(word) > 1}

                            matching_words = sum(1 for word in title_words if word in normalized_link_text)
                            has_exact_title = normalized_title in normalized_link_text

                            title_match = has_exact_title or (len(title_words) <= 2 and matching_words >= 2) or (len(title_words) > 2 and matching_words >= 2)

                            if title_match:
                                normalized_href = urllib.parse.urljoin('https://tv.apple.com', href)
                                logger.info(f"  Found Apple TV link: {normalized_href}")
                                return normalized_href

                except PlaywrightTimeoutError:
                    continue
                except Exception:
                    continue

            logger.warning(f"  No Apple TV link found for {title} ({year})")
            return None

        except Exception as e:
            logger.error(f"  Error searching Apple TV for {title}: {e}")
            return None

    def find_youtube_link(self, title, year):
        """Find YouTube movie purchase page using YouTube Data API.

        Uses duration filtering (>60 min) to reliably distinguish
        full movies from trailers. Returns direct watch URL.

        Args:
            title: Movie title
            year: Release year

        Returns:
            Deep link URL (https://www.youtube.com/watch?v=...) or None
        """
        start_time = time.time()
        try:
            import pickle
            import unicodedata

            try:
                from googleapiclient.discovery import build
            except ImportError:
                logger.warning("  googleapiclient not installed, cannot search YouTube")
                return None

            # Load YouTube API credentials
            credentials_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'youtube_credentials')
            token_file = os.path.join(credentials_dir, 'token.pickle')

            if not os.path.exists(token_file):
                logger.warning("  YouTube API token not found, cannot search")
                return None

            with open(token_file, 'rb') as f:
                credentials = pickle.load(f)
            youtube = build('youtube', 'v3', credentials=credentials)

            # 1. Search for the movie (videoDuration='long' pre-filters to >20 min)
            search_query = f"{title} {year}"
            logger.debug(f"  YouTube API search for: {search_query}")

            search_response = youtube.search().list(
                q=search_query,
                type='video',
                part='snippet',
                videoDuration='long',
                maxResults=10
            ).execute()

            video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
            if not video_ids:
                elapsed = time.time() - start_time
                logger.warning(f"  No YouTube results for {title} ({year}) after {elapsed:.1f}s")
                return None

            # 2. Get exact durations
            videos_response = youtube.videos().list(
                id=','.join(video_ids),
                part='contentDetails,snippet'
            ).execute()

            # Duration parser (ISO 8601: PT1H45M30S → minutes)
            def parse_duration_minutes(iso_duration):
                match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
                if not match:
                    return 0
                hours = int(match.group(1) or 0)
                minutes = int(match.group(2) or 0)
                seconds = int(match.group(3) or 0)
                return hours * 60 + minutes + seconds / 60

            # Title matching
            stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}

            def normalize_text(text):
                normalized = unicodedata.normalize('NFD', text)
                ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
                return re.sub(r'[^a-zA-Z0-9\s]', ' ', ascii_text)

            normalized_title = normalize_text(title.lower())
            title_words = {word for word in normalized_title.split() if word and word not in stopwords and len(word) > 1}

            # 3. Find the movie: duration >= 60 min + title match
            for video in videos_response.get('items', []):
                duration_iso = video.get('contentDetails', {}).get('duration', 'PT0S')
                runtime = parse_duration_minutes(duration_iso)

                # Must be >= 60 min (eliminates all trailers)
                if runtime < 60:
                    continue

                video_title = video.get('snippet', {}).get('title', '')
                normalized_video = normalize_text(video_title.lower())

                matching_words = sum(1 for word in title_words if word in normalized_video)
                overlap = matching_words / len(title_words) if title_words else 0
                has_exact = normalized_title in normalized_video

                if len(title_words) <= 2:
                    threshold = 0.5 if has_exact else 1.0
                else:
                    threshold = 0.6 if has_exact else 0.7

                if overlap < threshold:
                    continue

                url = f"https://www.youtube.com/watch?v={video['id']}"
                elapsed = time.time() - start_time
                logger.info(f"  Found YouTube link: {url} (runtime={round(runtime)}min, title='{video_title}')")
                return url

            elapsed = time.time() - start_time
            logger.warning(f"  No YouTube purchase page found for {title} ({year}) after {elapsed:.1f}s")
            return None

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"  Error searching YouTube API for {title} after {elapsed:.1f}s: {e}")
            return None

    def get_platform_deep_link(self, title, year, service_name):
        """Orchestrate platform-specific search based on service name.

        Args:
            title: Movie title
            year: Release year
            service_name: Service name from TMDB providers

        Returns:
            Deep link URL or None if not found/unsupported
        """
        if not title or not service_name:
            return None

        try:
            if 'Amazon' in service_name:
                result = self.find_amazon_link(title, year)
                if result:
                    return urllib.parse.urljoin('https://www.amazon.com', result)
                return result
            elif 'Apple' in service_name:
                result = self.find_apple_tv_link(title, year)
                if result:
                    return urllib.parse.urljoin('https://tv.apple.com', result)
                return result
            elif 'YouTube' in service_name:
                return self.find_youtube_link(title, year)
            else:
                logger.warning(f"  Platform '{service_name}' not supported by agent search")
                return None

        except Exception as e:
            logger.error(f"  Error in platform search for {service_name}: {e}")
            return None


# Backward compatibility alias
StreamingPlatformScraperV2 = StreamingPlatformScraper


def test_scraper():
    """Test function for manual testing."""
    scraper = StreamingPlatformScraper(headless=False)

    try:
        test_movies = [
            ("Afterburn", "2025"),
        ]

        for title, year in test_movies:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing Amazon search for: {title} ({year})")
            logger.info(f"{'='*60}")

            amazon_link = scraper.find_amazon_link(title, year)
            logger.info(f"Amazon result: {amazon_link}")

    finally:
        scraper.close()


if __name__ == "__main__":
    test_scraper()
