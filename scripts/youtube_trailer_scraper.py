#!/usr/bin/env python3
"""
YouTube Trailer Scraper - Uses Selenium to find direct trailer links
Converts YouTube search URLs to direct watch URLs
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import os

class YouTubeTrailerScraper:
    def __init__(self, cache_file='youtube_trailer_cache.json', headless=True):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.headless = headless
        self.driver = None

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

    def _init_driver(self):
        """Initialize Selenium driver"""
        if self.driver is not None:
            return

        print("Initializing Chrome driver...")
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')

        if self.headless:
            chrome_options.add_argument('--headless')

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def _close_driver(self):
        """Close Selenium driver"""
        if self.driver:
            self.driver.quit()
            self.driver = None

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

        # Initialize driver if needed
        self._init_driver()

        try:
            # Build search query
            search_query = f"{title} {year} official trailer"
            search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"

            print(f"  → Searching YouTube: {title} ({year})")
            self.driver.get(search_url)

            # Wait for video results to load with proper WebDriverWait
            try:
                wait = WebDriverWait(self.driver, 10)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a#video-title")))
                time.sleep(1)  # Small additional wait for full render
            except Exception as e:
                print(f"  ✗ Timeout waiting for results: {e}")
                self.cache[cache_key] = None
                self._save_cache()
                return None

            # Try to find the first video link
            # YouTube uses <a> tags with /watch?v= in the href
            video_links = self.driver.find_elements(By.CSS_SELECTOR, "a#video-title")

            if video_links:
                # Get the href of the first video
                first_video = video_links[0]
                video_url = first_video.get_attribute('href')

                if video_url and '/watch?v=' in video_url:
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
            self._close_driver()

        return results

    def cleanup(self):
        """Clean up resources"""
        self._close_driver()


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
