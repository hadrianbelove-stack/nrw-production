#!/usr/bin/env python3
"""
Playwright-based streaming platform scraper for Amazon Prime Video and Apple TV deep links

Purpose: Find direct deep links to movie pages when Watchmode API has no data
Supports: Amazon Prime Video, Apple TV (Netflix/Disney+ skipped due to anti-bot measures)
Usage: Optional enhancement to watch links system

Integration: Called from generate_data.py when Watchmode API returns no data
Returns: Deep link URL or None if not found

Maintenance: Requires selector updates when platforms change UI (~1-2 hours/month)
Performance: ~6-8 seconds per search, 30-40% faster than Selenium version
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_manager import get_playwright_manager
import time
import urllib.parse
import os
import random
import re
from datetime import datetime, timedelta
from constants import PLACEHOLDER_ASINS


class StreamingPlatformScraper:
    def __init__(self, headless=True, timeout_seconds=30, rate_limit_seconds=None, **kwargs):
        """Initialize Playwright browser with anti-bot measures"""

        # Store configuration
        self.headless = headless
        self.timeout_seconds = timeout_seconds
        self.rate_limit_seconds = rate_limit_seconds

        # Retry and backoff configuration
        self.max_retries = kwargs.get('max_retries', 3)
        self.base_delay = kwargs.get('base_delay', 0.5)
        self.max_delay = kwargs.get('max_delay', 5.0)
        self.jitter_ratio = kwargs.get('jitter_ratio', 0.2)

        # Screenshots configuration
        self.screenshot_dir = 'cache/screenshots'
        self.screenshots_enabled = kwargs.get('screenshots_enabled', True)
        self.screenshot_retention_days = kwargs.get('screenshot_retention_days', 7)

        # Browser components (lazy initialization)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Shared manager reference
        self.manager = get_playwright_manager()

        # Clean up old screenshots on initialization
        if self.screenshots_enabled:
            self._cleanup_old_screenshots()

    def _init_browser(self):
        """Initialize Playwright browser with context (lazy initialization)"""
        if self.browser is not None:
            return

        try:
            # Get shared Playwright instance
            self.playwright = self.manager.get_playwright()

            # Launch Chromium browser
            self.browser = self.playwright.chromium.launch(headless=self.headless)

            # Create context with viewport and user agent (same as Selenium version)
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Set default timeout
            timeout_ms = self.timeout_seconds * 1000
            self.context.set_default_timeout(timeout_ms)

            # Create page
            self.page = self.context.new_page()

        except Exception as e:
            print(f"Browser initialization failed: {e}")
            self._cleanup_browser()
            raise

    def _cleanup_browser(self):
        """Clean up browser resources"""
        if self.page:
            try:
                self.page.close()
            except:
                pass
            self.page = None

        # Shared manager reference
        self.manager = get_playwright_manager()

        if self.context:
            try:
                self.context.close()
            except:
                pass
            self.context = None

        if self.browser:
            try:
                self.browser.close()
            except:
                pass
            self.browser = None

        if self.playwright:
            try:
                self.manager.release()
            except:
                pass
            self.playwright = None

    def _cleanup_old_screenshots(self):
        """Delete old screenshots based on retention policy."""
        if not self.screenshots_enabled or not os.path.exists(self.screenshot_dir):
            return

        try:
            cutoff_time = datetime.now() - timedelta(days=self.screenshot_retention_days)
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
                            print(f"Failed to delete old screenshot {filename}: {e}")

            if deleted_count > 0:
                print(f"🧹 Cleaned up {deleted_count} old screenshots (older than {self.screenshot_retention_days} days)")

        except Exception as e:
            print(f"Failed to cleanup old screenshots: {e}")

    def _retry_with_backoff(self, fn):
        """Retry function with exponential backoff."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = fn()
                if result is not None:
                    return result

                # If function returned None, continue to retry
                if attempt < self.max_retries - 1:
                    delay = min(self.max_delay, self.base_delay * (2 ** attempt))
                    jitter = random.uniform(-self.jitter_ratio * delay, self.jitter_ratio * delay)
                    sleep_time = delay + jitter
                    print(f"  Attempt {attempt + 1} failed, retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

            except (PlaywrightTimeoutError, Exception) as e:
                last_error = e
                print(f"  Attempt {attempt + 1} error: {e}")
                if attempt < self.max_retries - 1:
                    delay = min(self.max_delay, self.base_delay * (2 ** attempt))
                    jitter = random.uniform(-self.jitter_ratio * delay, self.jitter_ratio * delay)
                    sleep_time = delay + jitter
                    print(f"  Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

        # All attempts failed
        return None

    def _capture_failure_diagnostics(self, title, year, platform, error_msg):
        """Capture screenshot and HTML on failure for debugging."""
        if not self.screenshots_enabled or not self.page:
            return

        try:
            # Create screenshot directory
            os.makedirs(self.screenshot_dir, exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r'[^\w\-_\.]', '_', title)[:30]  # Sanitize filename
            filename_base = f"{safe_title}_{year}_{platform}_{timestamp}"

            # Capture screenshot
            screenshot_path = os.path.join(self.screenshot_dir, f"{filename_base}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)

            # Save HTML
            html_path = os.path.join(self.screenshot_dir, f"{filename_base}.html")
            html_content = self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"  📸 Diagnostics saved: {screenshot_path}")

            # Clean up old screenshots after saving a new one
            self._cleanup_old_screenshots()

        except Exception as e:
            print(f"  Failed to capture diagnostics: {e}")

    def close(self):
        """Clean up WebDriver resources"""
        try:
            self._cleanup_browser()
        except Exception as e:
            print(f"Warning: Failed to close platform scraper: {e}")

    def find_amazon_link(self, title, year):
        """Search Amazon Prime Video and extract movie detail page URL

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
        """Core Amazon search logic (wrapped by retry mechanism)"""
        start_time = time.time()
        try:
            # Initialize browser if needed
            self._init_browser()

            # Build Amazon video search URL
            search_query = f"{title} {year}"
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://www.amazon.com/s?k={encoded_query}&i=instant-video"

            print(f"  Searching Amazon for: {search_query}")
            print(f"  URL: {search_url}")

            # Navigate to search page
            self.page.goto(search_url, wait_until='networkidle')

            print(f"  Page loaded, waiting for search results...")

            # Wait for search results to appear
            try:
                self.page.wait_for_selector(".s-result-item, .s-widget-container", timeout=self.timeout_seconds * 1000)
                print(f"  Search results loaded successfully")
            except PlaywrightTimeoutError:
                print(f"  Warning: Search results may not have loaded completely")

            # Try multiple selectors for search results (in order of preference)
            # Updated selectors based on modern Amazon HTML structure (2025)
            # High-confidence selectors (try first, exit early if found)
            high_confidence_selectors = [
                "div[data-component-type='s-search-result'] h2 a[href*='/gp/video/detail/']",  # Direct video detail links in search results
                ".s-widget-container a[href*='/gp/video/detail/']",  # Widget container video links
                "a[href*='/gp/video/detail/']",  # Any direct video detail links
            ]

            # All selectors including fallbacks
            all_selectors = high_confidence_selectors + [
                # Video-likely selectors
                "div[data-component-type='s-search-result'] h2 a[href*='/dp/']",  # Product detail links that may be video
                "[data-cy='title-recipe-title'] a",  # Video title recipe links
                ".s-widget-container a[href*='/dp/']",  # Widget container product links

                # Standard result selectors
                ".s-result-item h2.a-size-mini a",  # Amazon's current title link structure
                ".s-result-item .a-text-normal",  # Text-based title links
                ".s-result-item a.a-link-normal",  # Standard result item links
                "h2 a[href*='/dp/']",  # Generic h2 title links

                # Fallback selectors
                "a[href*='/dp/'][data-asin]",  # Product links with ASIN data
                "[data-asin] a[href*='/dp/']",  # ASIN-based product links
                ".s-title-instructions-style a",  # Legacy title style link (keep for compatibility)

                # Last resort - any Amazon product/video links
                "a[href*='/dp/']",  # Any Amazon product detail page
                "a[href*='/gp/video/']"  # Any Amazon video page
            ]

            # Track which selector strategy we're using
            selectors = all_selectors

            print(f"  Trying {len(selectors)} different selectors...")

            for i, selector in enumerate(selectors, 1):
                try:
                    is_high_confidence = selector in high_confidence_selectors
                    selector_type = "HIGH-CONFIDENCE" if is_high_confidence else "FALLBACK"
                    print(f"    Selector {i} ({selector_type}): {selector}")

                    elements = self.page.locator(selector).all()
                    print(f"    Found {len(elements)} elements")

                    for j, element in enumerate(elements):
                        href = element.get_attribute('href')
                        if href and ('/gp/video/detail/' in href or '/dp/' in href):
                            print(f"    Element {j+1}: Checking href = {href}")

                            # Position-based filtering: DISABLED (featured results can be in position 0-1)
                            # The sponsored detection below will catch actual ads
                            # if j < 2:
                            #     print(f"    Element {j+1}: Skipping position {j+1} (likely sponsored)")
                            #     continue

                            # Check for known placeholder ASINs
                            if any(asin in href for asin in PLACEHOLDER_ASINS):
                                print(f"    Element {j+1}: Skipping known placeholder ASIN")
                                continue

                            # Enhanced sponsored result detection with multiple strategies
                            is_sponsored = False
                            try:
                                # Strategy 1: Traditional sponsored parent classes
                                parent = element.locator("xpath=./ancestor::div[contains(@class, 'sp-sponsored') or contains(@data-component-type, 'sp-sponsored-result')]").first
                                if parent.count() > 0:
                                    is_sponsored = True
                            except:
                                pass

                            if not is_sponsored:
                                try:
                                    # Strategy 2: Check for 'sponsored' keyword in any ancestor class or data attribute
                                    parent = element.locator("xpath=./ancestor::div[contains(@class, 'sponsored') or contains(@data-testid, 'sponsored') or contains(@id, 'AdHolder')]").first
                                    if parent.count() > 0:
                                        is_sponsored = True
                                except:
                                    pass

                            if not is_sponsored:
                                try:
                                    # Strategy 3: Check for ad-related IDs and classes
                                    parent = element.locator("xpath=./ancestor::div[contains(@id, 'ad-') or contains(@class, 'AdHolder') or contains(@class, 'sp-sponsored')]").first
                                    if parent.count() > 0:
                                        is_sponsored = True
                                except:
                                    pass

                            if not is_sponsored:
                                # Strategy 4: Look for "Sponsored" text in nearby elements (within 3 ancestors)
                                try:
                                    parent = element.locator("xpath=./ancestor::div[contains(., 'Sponsored')]").first
                                    if parent.count() > 0:
                                        # Verify "Sponsored" text is actually visible (not deep in nested content)
                                        sponsored_text = parent.text_content()
                                        if sponsored_text and 'Sponsored' in sponsored_text and len(sponsored_text) < 500:  # Reasonable text length
                                            is_sponsored = True
                                except:
                                    pass

                            if is_sponsored:
                                print(f"    Element {j+1}: Skipping sponsored result (enhanced detection)")
                                continue

                            # Validate title match for all results (including high-confidence)
                            try:
                                # Try to find the result container
                                parent = None
                                try:
                                    parent = element.locator("xpath=./ancestor::div[@data-component-type='s-search-result']").first
                                    if parent.count() == 0:
                                        parent = None
                                except:
                                    pass

                                if parent is None:
                                    # Try alternative parent selectors
                                    try:
                                        parent = element.locator("xpath=./ancestor::div[contains(@class, 's-result-item')]").first
                                        if parent.count() == 0:
                                            parent = element.locator("xpath=./ancestor::div[contains(@class, 's-widget-container')]").first
                                    except:
                                        pass

                                if parent and parent.count() > 0:
                                    # Get the text content for title validation
                                    text_content = parent.text_content().lower()
                                    print(f"    Element {j+1}: Text content preview: {text_content[:100]}...")

                                    # Enhanced title validation with stopword filtering and character normalization
                                    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'from', 'that', 'this', 'as', 'it'}

                                    def normalize_text(text):
                                        """Normalize text by removing accents and special characters"""
                                        import unicodedata
                                        # Normalize Unicode characters (accents, etc.)
                                        normalized = unicodedata.normalize('NFD', text)
                                        # Remove accent marks
                                        ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
                                        # Keep only alphanumeric and spaces
                                        return re.sub(r'[^a-zA-Z0-9\s]', ' ', ascii_text)

                                    # Normalize and filter stopwords from search title
                                    normalized_title = normalize_text(title.lower())
                                    search_title_words = {word for word in normalized_title.split() if word and word not in stopwords and len(word) > 1}

                                    # Extract potential title from the result text (first few lines usually contain title)
                                    result_text_lines = text_content.split('\n')[:3]  # First 3 lines most likely to contain title
                                    result_text = ' '.join(result_text_lines).lower()
                                    normalized_result = normalize_text(result_text)

                                    # Count word overlap (excluding stopwords)
                                    matching_words = sum(1 for word in search_title_words if word in normalized_result)
                                    overlap_percentage = matching_words / len(search_title_words) if search_title_words else 0

                                    # Exact title match bonus: if result contains the exact full title, accept with lower threshold
                                    has_exact_title = normalized_title in normalized_result

                                    # Require at least two non-stopword matches or exact title presence for very short titles
                                    if len(search_title_words) <= 2:
                                        threshold = 0.5 if (has_exact_title or matching_words >= 2) else 1.0
                                    else:
                                        threshold = 0.6 if has_exact_title else 0.7

                                    # Year validation: flexible ±1 year matching
                                    # Year is a bonus, not required (some listings don't show year)
                                    year_bonus = 0  # Bonus points for year matching
                                    year_penalty = 0  # Penalty for wrong year
                                    if year and year.isdigit():
                                        search_year = int(year)
                                        # Check for exact year or ±1 year
                                        if str(search_year) in text_content:
                                            year_bonus = 10  # Exact match
                                        elif str(search_year - 1) in text_content or str(search_year + 1) in text_content:
                                            year_bonus = 5  # Close match (±1 year)
                                        else:
                                            # Check if any year appears that's way off (2+ years)
                                            import re
                                            years_in_text = re.findall(r'\b(19\d{2}|20\d{2})\b', text_content)
                                            years_in_text = [int(y) for y in years_in_text]
                                            if years_in_text:
                                                closest_year = min(years_in_text, key=lambda y: abs(y - search_year))
                                                year_diff = abs(closest_year - search_year)
                                                if year_diff >= 2:
                                                    year_penalty = 20  # Probably wrong movie
                                                    print(f"    Element {j+1}: Year mismatch (search: {search_year}, found: {closest_year}, diff: {year_diff} years)")
                                            # If no year found in text, that's okay (year_bonus = 0, year_penalty = 0)

                                    print(f"    Element {j+1}: Title match: {matching_words}/{len(search_title_words)} words ({overlap_percentage:.1%})")
                                    print(f"    Element {j+1}: Exact title: {has_exact_title}, Year bonus: +{year_bonus}, Year penalty: -{year_penalty}, Threshold: {threshold:.1%}")

                                    # Title must still meet minimum threshold
                                    if overlap_percentage < threshold:
                                        print(f"    Element {j+1}: Insufficient title match ({overlap_percentage:.1%} < {threshold:.1%}), skipping")
                                        continue

                                    # Apply year penalty (skip if year is way off)
                                    if year_penalty > 0:
                                        print(f"    Element {j+1}: Year penalty applied (probably wrong movie), skipping")
                                        continue

                                    # Check for negative keywords that indicate wrong content
                                    negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order', 'tv series', 'season']
                                    has_negative = any(keyword in result_text for keyword in negative_keywords)
                                    if has_negative:
                                        print(f"    Element {j+1}: Contains negative keywords, skipping")
                                        continue

                                    # For high-confidence selectors, accept if title matches
                                    if is_high_confidence and '/gp/video/detail/' in href:
                                        elapsed_time = time.time() - start_time
                                        print(f"  ✓ Found Amazon link (high-confidence): {href}")
                                        print(f"  ✓ Title match: {overlap_percentage:.1%}")
                                        print(f"  ✓ Search completed in {elapsed_time:.2f} seconds using {selector_type} selector")
                                        return href

                                    # Stricter video keyword validation: require at least 2 keywords
                                    video_keywords = ['prime video', 'stream', 'watch', 'rent', 'buy', 'included with prime', 'digital video', 'hd']
                                    found_keywords = [kw for kw in video_keywords if kw in text_content]

                                    # Check for negative keywords that indicate non-video content
                                    extended_negative_keywords = ['not available', 'unavailable', 'coming soon', 'pre-order', 'blu-ray', 'dvd', '4k uhd', 'steelbook']
                                    found_negative = [kw for kw in extended_negative_keywords if kw in text_content]
                                    if found_negative:
                                        print(f"    Element {j+1}: Found negative keywords {found_negative}, skipping")
                                        continue

                                    # Verify this is actually a video product (check for runtime, video format indicators)
                                    video_indicators = ['min', 'hr', 'hours', 'minutes', 'runtime', 'duration', 'episode', 'movie']
                                    has_video_indicators = any(indicator in text_content for indicator in video_indicators)

                                    # Require at least 2 video keywords OR 1 keyword + video indicators
                                    keyword_threshold = 2 if not has_video_indicators else 1
                                    if len(found_keywords) >= keyword_threshold:
                                        elapsed_time = time.time() - start_time
                                        print(f"  ✓ Found Amazon link: {href}")
                                        print(f"  ✓ Matched keywords: {found_keywords}")
                                        print(f"  ✓ Title match: {overlap_percentage:.1%}")
                                        print(f"  ✓ Search completed in {elapsed_time:.2f} seconds using {selector_type} selector")
                                        return href
                                    else:
                                        print(f"    Element {j+1}: Insufficient video validation (need {keyword_threshold} keywords, found {len(found_keywords)}), skipping")
                                else:
                                    # No parent container found (likely a featured hero result)
                                    # For high-confidence video detail links, try alternative title extraction
                                    if is_high_confidence and '/gp/video/detail/' in href:
                                        print(f"    Element {j+1}: No parent container, but this is a high-confidence video link")
                                        print(f"    Element {j+1}: Attempting alternative title validation...")

                                        # Try to get title from the link element itself or nearby elements
                                        try:
                                            # Strategy 1: Get text from the link itself
                                            link_text = element.text_content().strip().lower()

                                            # Strategy 2: Try to find title in nearby elements
                                            # Look for parent divs that might contain the title
                                            nearby_text = ""
                                            try:
                                                # Try getting text from up to 5 levels of parent
                                                for level in range(1, 6):
                                                    parent_candidate = element.locator(f"xpath={'/..' * level}").first
                                                    if parent_candidate.count() > 0:
                                                        candidate_text = parent_candidate.text_content().lower()
                                                        # Check if this text contains meaningful content (not too long, not empty)
                                                        if 10 < len(candidate_text) < 500:
                                                            nearby_text = candidate_text
                                                            print(f"    Element {j+1}: Found text at parent level {level}: {nearby_text[:100]}...")
                                                            break
                                            except:
                                                pass

                                            # Use whichever text source we found
                                            text_to_check = nearby_text if nearby_text else link_text

                                            if text_to_check:
                                                # Simple title matching: check if key words from search title appear
                                                search_words = title.lower().replace('the ', '').replace('a ', '').split()
                                                # Remove single-character words
                                                search_words = [w for w in search_words if len(w) > 1]

                                                matches = sum(1 for word in search_words if word in text_to_check)
                                                match_pct = matches / len(search_words) if search_words else 0

                                                print(f"    Element {j+1}: Simple title match: {matches}/{len(search_words)} words ({match_pct:.1%})")

                                                # Lower threshold for featured results (50% instead of 70%)
                                                if match_pct >= 0.5:
                                                    elapsed_time = time.time() - start_time
                                                    print(f"  ✓ Found Amazon link (featured result, alternative validation): {href}")
                                                    print(f"  ✓ Title match: {match_pct:.1%}")
                                                    print(f"  ✓ Search completed in {elapsed_time:.2f} seconds")
                                                    return href
                                                else:
                                                    print(f"    Element {j+1}: Insufficient title match ({match_pct:.1%}), skipping")
                                            else:
                                                print(f"    Element {j+1}: No text content found for validation, skipping")
                                        except Exception as alt_e:
                                            print(f"    Element {j+1}: Alternative validation failed: {alt_e}")
                                    else:
                                        print(f"    Element {j+1}: No parent container found for title validation, skipping")
                            except Exception as e:
                                print(f"    Element {j+1}: Error validating title/parent: {e}")
                                # Skip this result rather than proceeding without validation
                                continue
                        else:
                            print(f"    Element {j+1}: No video href found")

                except Exception as e:
                    print(f"    Selector {i} failed: {e}")
                    continue

            elapsed_time = time.time() - start_time
            print(f"  ✗ No Amazon link found for {title} ({year}) after {elapsed_time:.2f} seconds")
            return None

        except Exception as e:
            elapsed_time = time.time() - start_time
            print(f"  Error searching Amazon for {title} after {elapsed_time:.2f} seconds: {e}")
            return None

    def find_apple_tv_link(self, title, year):
        """Search Apple TV and extract movie detail page URL

        Args:
            title: Movie title
            year: Release year

        Returns:
            Deep link URL (https://tv.apple.com/us/movie/{slug}/umc.cmc.{id}) or None
        """
        def search_attempt():
            return self._find_apple_tv_link_core(title, year)

        result = self._retry_with_backoff(search_attempt)
        if result is None:
            self._capture_failure_diagnostics(title, year, "apple_tv", "No link found after retries")
        return result

    def _find_apple_tv_link_core(self, title, year):
        """Core Apple TV search logic (wrapped by retry mechanism)"""
        try:
            # Initialize browser if needed
            self._init_browser()

            # Build Apple TV search URL
            search_query = urllib.parse.quote(title)
            search_url = f"https://tv.apple.com/search?term={search_query}"

            print(f"  Searching Apple TV for: {title}")
            self.page.goto(search_url, wait_until='networkidle')

            # Try multiple selectors for search results (in order of preference)
            selectors = [
                "a[href*='/movie/'][href*='umc.cmc']",
                ".shelf-grid__list-item a",
                "[data-test-id='lockup'] a",
                "a[href*='umc.cmc']"
            ]

            for selector in selectors:
                try:
                    # Wait for selector to appear before attempting to enumerate elements
                    self.page.wait_for_selector(selector, timeout=self.timeout_seconds*1000)
                    elements = self.page.locator(selector).all()
                    for element in elements:
                        href = element.get_attribute('href')
                        if href and '/movie/' in href and 'umc.cmc' in href:
                            # Enhanced title validation with stopword filtering and character normalization
                            stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'from', 'that', 'this', 'as', 'it'}

                            def normalize_text(text):
                                """Normalize text by removing accents and special characters"""
                                import unicodedata
                                # Normalize Unicode characters (accents, etc.)
                                normalized = unicodedata.normalize('NFD', text)
                                # Remove accent marks
                                ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
                                # Keep only alphanumeric and spaces
                                return re.sub(r'[^a-zA-Z0-9\s]', ' ', ascii_text)

                            link_text = element.text_content().lower()
                            normalized_title = normalize_text(title.lower())
                            normalized_link_text = normalize_text(link_text)

                            # Filter stopwords from title
                            title_words = {word for word in normalized_title.split() if word and word not in stopwords and len(word) > 1}

                            # Require at least two non-stopword matches or exact title presence
                            matching_words = sum(1 for word in title_words if word in normalized_link_text)
                            has_exact_title = normalized_title in normalized_link_text

                            if (len(title_words) <= 2 and (has_exact_title or matching_words >= 2)) or (len(title_words) > 2 and matching_words >= 2):
                                print(f"  ✓ Found Apple TV link: {href}")
                                print(f"  ✓ Title match: {matching_words}/{len(title_words)} words, exact: {has_exact_title}")
                                return href
                except PlaywrightTimeoutError:
                    print(f"  Selector not found within timeout: {selector}")
                    continue
                except Exception:
                    continue

            print(f"  ✗ No Apple TV link found for {title} ({year})")
            return None

        except Exception as e:
            print(f"  Error searching Apple TV for {title}: {e}")
            return None

    def get_platform_deep_link(self, title, year, service_name):
        """Orchestrate platform-specific search based on service name

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
            # Route to appropriate platform search
            if 'Amazon' in service_name:
                return self.find_amazon_link(title, year)
            elif 'Apple' in service_name:
                return self.find_apple_tv_link(title, year)
            else:
                # Unsupported platform (Netflix, Disney+, etc.)
                print(f"  Platform '{service_name}' not supported by agent search")
                return None

        except Exception as e:
            print(f"  Error in platform search for {service_name}: {e}")
            return None


def test_scraper():
    """Test function for manual testing with recent 2025 releases"""
    scraper = StreamingPlatformScraper(headless=False)  # Ensure browser is visible for inspection

    try:
        # Test Amazon search with recent 2025 releases
        test_movies = [
            ("Afterburn", "2025"),
            ("Pet Shop Days", "2025"),
            ("The Eichmann Trial", "2025"),
            ("Little Brother", "2025")
        ]

        for title, year in test_movies:
            print(f"\n{'='*60}")
            print(f"Testing Amazon search for: {title} ({year})")
            print(f"{'='*60}")

            amazon_link = scraper.find_amazon_link(title, year)
            print(f"Amazon result: {amazon_link}")

            # Add pause for manual inspection
            input("Press Enter to continue to next test movie...")

        # Test Apple TV search with one movie
        print(f"\n{'='*60}")
        print("Testing Apple TV search...")
        print(f"{'='*60}")
        apple_link = scraper.find_apple_tv_link("Afterburn", "2025")
        print(f"Apple TV result: {apple_link}")

        # Test platform routing
        print(f"\n{'='*60}")
        print("Testing platform routing...")
        print(f"{'='*60}")
        result1 = scraper.get_platform_deep_link("Afterburn", "2025", "Amazon Video")
        print(f"Amazon routing result: {result1}")

        result2 = scraper.get_platform_deep_link("Afterburn", "2025", "Apple TV")
        print(f"Apple TV routing result: {result2}")

    finally:
        scraper.close()


if __name__ == "__main__":
    test_scraper()