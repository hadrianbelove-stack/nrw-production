#!/usr/bin/env python3
"""
YouTube Trailer Scraper - Uses Playwright to find direct trailer links
Converts YouTube search URLs to direct watch URLs
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import sys

# Add parent directory to path for playwright_manager import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Optional shared manager support (disabled by default)
USE_SHARED_PLAYWRIGHT = os.environ.get('NRW_USE_SHARED_PLAYWRIGHT', 'false').lower() == 'true'
if USE_SHARED_PLAYWRIGHT:
    from playwright_manager import get_playwright_manager

class YouTubeTrailerScraper:
    def __init__(self, cache_file='youtube_trailer_cache.json', headless=True):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.headless = headless

        # Browser components (lazy initialization)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Manager reference (only if shared mode enabled)
        self.manager = get_playwright_manager() if USE_SHARED_PLAYWRIGHT else None


    def _load_cache(self):
        """Load cache from file"""
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        """Save cache to file"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def _init_browser(self):
        """Initialize Playwright browser"""
        if self.browser is not None:
            return

        if USE_SHARED_PLAYWRIGHT:
            print("[YouTubeTrailerScraper] Initializing browser via shared manager...")
            self._init_browser_shared()
        else:
            print("[YouTubeTrailerScraper] Initializing browser with local lifecycle...")
            self._init_browser_local()

    def _init_browser_shared(self):
        """Initialize browser using shared manager"""
        try:
            # Get shared Playwright instance
            self.playwright = self.manager.get_playwright()

            # Launch browser
            self.browser = self.playwright.chromium.launch(headless=self.headless)

            # Create context with viewport and user agent
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Set default timeout
            self.context.set_default_timeout(10000)  # 10 seconds

            # Create page
            self.page = self.context.new_page()

        except Exception as e:
            print(f"Browser initialization failed: {e}")
            self._cleanup_browser()
            raise

    def _init_browser_local(self):
        """Initialize browser using local lifecycle"""
        try:
            # Start Playwright locally
            self.playwright = sync_playwright().start()

            # Launch browser
            self.browser = self.playwright.chromium.launch(headless=self.headless)

            # Create context with viewport and user agent
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Set default timeout
            self.context.set_default_timeout(10000)  # 10 seconds

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

        # Cleanup Playwright based on mode
        if self.playwright:
            try:
                if USE_SHARED_PLAYWRIGHT and self.manager:
                    self.manager.release()
                else:
                    self.playwright.stop()
            except:
                pass
            self.playwright = None

    def find_trailer(self, title, year):
        """
        Find direct YouTube trailer link for a movie

        Args:
            title: Movie title
            year: Movie year

        Returns:
            Direct YouTube watch URL or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            print(f"  ✓ Cache hit: {title} ({year})")
            return self.cache[cache_key]

        # Initialize browser if needed
        self._init_browser()

        try:
            # Build search query
            search_query = f"{title} {year} official trailer"
            search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"

            print(f"  → Searching YouTube: {title} ({year})")
            self.page.goto(search_url, wait_until='domcontentloaded')

            # Wait for video results to load
            try:
                self.page.wait_for_selector('a#video-title', timeout=10000)
                self.page.wait_for_timeout(1000)  # Small additional wait for full render
            except PlaywrightTimeoutError as e:
                print(f"  ✗ Timeout waiting for results: {e}")
                self.cache[cache_key] = None
                self._save_cache()
                return None

            # Try to find the first video link
            # YouTube uses <a> tags with /watch?v= in the href
            video_links = self.page.locator('a#video-title').all()

            if video_links:
                # Get the href of the first video
                first_video = video_links[0]
                video_url = first_video.get_attribute('href')

                if video_url and '/watch?v=' in video_url:
                    # Normalize relative URLs to absolute URLs
                    if video_url.startswith('/watch'):
                        video_url = f"https://www.youtube.com{video_url}"

                    # Clean up URL (remove any extra parameters after video ID)
                    if '&' in video_url:
                        video_url = video_url.split('&')[0]

                    print(f"  ✓ Found: {video_url}")

                    # Cache the result
                    self.cache[cache_key] = video_url
                    self._save_cache()

                    return video_url

            print(f"  ✗ No trailer found for {title} ({year})")

            # Cache the failure (so we don't keep trying)
            self.cache[cache_key] = None
            self._save_cache()

            return None

        except Exception as e:
            print(f"  ✗ Error scraping {title}: {e}")
            return None

    def batch_find_trailers(self, movies_list, max_searches=None):
        """
        Find trailers for multiple movies

        Args:
            movies_list: List of tuples (title, year)
            max_searches: Maximum number of searches to perform (None = unlimited)

        Returns:
            Dict of {(title, year): url}
        """
        results = {}
        searches_done = 0

        try:
            for title, year in movies_list:
                if max_searches and searches_done >= max_searches:
                    print(f"\nReached max searches limit ({max_searches})")
                    break

                url = self.find_trailer(title, year)
                results[(title, year)] = url

                if url and url not in self.cache:  # Only count new searches
                    searches_done += 1
                    time.sleep(1)  # Rate limiting - be nice to YouTube

        finally:
            self._cleanup_browser()

        return results

    def cleanup(self):
        """Clean up resources"""
        self._cleanup_browser()


if __name__ == "__main__":
    # Test the scraper
    scraper = YouTubeTrailerScraper(headless=False)

    test_movies = [
        ("Our Fault", "2025"),
        ("The Long Walk", "2025"),
        ("A Woman with No Filter", "2025"),
    ]

    print("Testing YouTube trailer scraper...")
    print("=" * 50)

    results = scraper.batch_find_trailers(test_movies)

    print("\n" + "=" * 50)
    print("Results:")
    for (title, year), url in results.items():
        print(f"  {title} ({year}): {url}")

    scraper.cleanup()