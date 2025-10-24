#!/usr/bin/env python3
"""
Selenium-based streaming platform scraper for Amazon Prime Video and Apple TV deep links

Purpose: Find direct deep links to movie pages when Watchmode API has no data
Supports: Amazon Prime Video, Apple TV (Netflix/Disney+ skipped due to anti-bot measures)
Usage: Optional enhancement to watch links system

Integration: Called from generate_data.py when Watchmode API returns no data
Returns: Deep link URL or None if not found

Maintenance: Requires selector updates when platforms change UI (~1-2 hours/month)
Performance: ~5-10 seconds per search, acceptable for daily automation
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import urllib.parse


class StreamingPlatformScraper:
    def __init__(self, headless=True, timeout_seconds=30, rate_limit_seconds=None):
        """Initialize Chrome WebDriver with anti-bot measures"""
        self.options = Options()
        if headless:
            self.options.add_argument('--headless')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # Store configuration
        self.timeout_seconds = timeout_seconds
        self.rate_limit_seconds = rate_limit_seconds

        # Initialize WebDriver
        service = webdriver.chrome.service.Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=self.options)
        self.driver.set_page_load_timeout(timeout_seconds)
        self.wait = WebDriverWait(self.driver, timeout_seconds)

    def find_amazon_link(self, title, year):
        """Search Amazon Prime Video and extract movie detail page URL

        Args:
            title: Movie title
            year: Release year

        Returns:
            Deep link URL (https://www.amazon.com/gp/video/detail/{ASIN}) or None
        """
        start_time = time.time()
        try:
            # Build Amazon video search URL
            search_query = f"{title} {year}"
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://www.amazon.com/s?k={encoded_query}&i=instant-video"

            print(f"  Searching Amazon for: {search_query}")
            print(f"  URL: {search_url}")
            self.driver.get(search_url)

            # Wait for page load with explicit wait for better reliability
            print(f"  Page loaded, waiting for search results...")
            try:
                # Wait for search results to appear
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".s-result-item, .s-widget-container")))
                print(f"  Search results loaded successfully")
            except TimeoutException:
                print(f"  Warning: Search results may not have loaded completely")

            # Wait for high-confidence elements to be present instead of fixed sleep
            try:
                # Wait for first high-confidence selector to have elements present
                high_confidence_selector = "div[data-component-type='s-search-result'] h2 a[href*='/gp/video/detail/'], .s-widget-container a[href*='/gp/video/detail/'], a[href*='/gp/video/detail/']"
                self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, high_confidence_selector)))
                print(f"  High-confidence elements loaded")
            except TimeoutException:
                # If high-confidence elements not found, wait for any result elements
                try:
                    fallback_selector = "div[data-component-type='s-search-result'] h2 a, .s-result-item h2 a"
                    self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, fallback_selector)))
                    print(f"  Fallback result elements loaded")
                except TimeoutException:
                    print(f"  Warning: No specific result elements found, proceeding with available content")

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

                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"    Found {len(elements)} elements")

                    for j, element in enumerate(elements):
                        href = element.get_attribute('href')
                        if href and ('/gp/video/detail/' in href or '/dp/' in href):
                            print(f"    Element {j+1}: Checking href = {href}")

                            # For high-confidence selectors, require less validation
                            if is_high_confidence and '/gp/video/detail/' in href:
                                elapsed_time = time.time() - start_time
                                print(f"  ✓ Found Amazon link (high-confidence): {href}")
                                print(f"  ✓ Search completed in {elapsed_time:.2f} seconds using {selector_type} selector")
                                return href

                            # Validate this is a video result (not physical product)
                            try:
                                parent = element.find_element(By.XPATH, "./ancestor::div[@data-component-type='s-search-result']")
                                if parent:
                                    # Check if result contains video-related text
                                    text_content = parent.text.lower()
                                    print(f"    Element {j+1}: Text content preview: {text_content[:100]}...")

                                    video_keywords = ['prime video', 'stream', 'watch', 'rent', 'buy', 'included with prime']
                                    found_keywords = [kw for kw in video_keywords if kw in text_content]

                                    # For /dp/ links, check for negative keywords to avoid Blu-ray/DVD products
                                    if '/dp/' in href:
                                        negative_keywords = ['blu-ray', 'dvd', '4k uhd', 'steelbook']
                                        found_negative = [kw for kw in negative_keywords if kw in text_content]
                                        if found_negative:
                                            print(f"    Element {j+1}: Found negative keywords {found_negative}, skipping /dp/ link")
                                            continue

                                    if found_keywords:
                                        elapsed_time = time.time() - start_time
                                        print(f"  ✓ Found Amazon link: {href}")
                                        print(f"  ✓ Matched keywords: {found_keywords}")
                                        print(f"  ✓ Search completed in {elapsed_time:.2f} seconds using {selector_type} selector")
                                        return href
                                    else:
                                        print(f"    Element {j+1}: No video keywords found, skipping")
                                else:
                                    # If no parent found but high confidence selector, still accept video links
                                    if is_high_confidence and '/gp/video/detail/' in href:
                                        elapsed_time = time.time() - start_time
                                        print(f"  ✓ Found Amazon link (high-confidence, no parent validation): {href}")
                                        print(f"  ✓ Search completed in {elapsed_time:.2f} seconds")
                                        return href
                            except Exception as e:
                                print(f"    Element {j+1}: Error validating parent: {e}")
                                # For high confidence selectors with video detail URLs, proceed anyway
                                if is_high_confidence and '/gp/video/detail/' in href:
                                    elapsed_time = time.time() - start_time
                                    print(f"  ✓ Found Amazon link (high-confidence, validation failed): {href}")
                                    print(f"  ✓ Search completed in {elapsed_time:.2f} seconds")
                                    return href
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
        try:
            # Build Apple TV search URL
            search_query = urllib.parse.quote(title)
            search_url = f"https://tv.apple.com/search?term={search_query}"

            print(f"  Searching Apple TV for: {title}")
            self.driver.get(search_url)
            time.sleep(3)  # Apple TV needs more time for React rendering

            # Try multiple selectors for search results (in order of preference)
            selectors = [
                "a[href*='/movie/'][href*='umc.cmc']",
                ".shelf-grid__list-item a",
                "[data-test-id='lockup'] a",
                "a[href*='umc.cmc']"
            ]

            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        href = element.get_attribute('href')
                        if href and '/movie/' in href and 'umc.cmc' in href:
                            # Validate the title matches (basic check)
                            link_text = element.text.lower()
                            title_words = title.lower().split()
                            if any(word in link_text for word in title_words):
                                print(f"  ✓ Found Apple TV link: {href}")
                                return href
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

    def close(self):
        """Clean up WebDriver resources"""
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
        except Exception as e:
            print(f"Warning: Failed to close platform scraper: {e}")


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