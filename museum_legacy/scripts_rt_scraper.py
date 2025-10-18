#!/usr/bin/env python3
"""
Rotten Tomatoes Scraper - Uses Selenium to find actual RT pages and scores
"""

# DEPRECATED: This class has been inlined into generate_data.py
# This file is kept for reference only and will be archived to museum_legacy/
# Use generate_data.py's built-in RT scraping instead

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import os
import re

class RTScraper:
    def __init__(self, cache_file='rt_cache.json', headless=True):
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

        print("Initializing Chrome driver for RT scraping...")
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

    def find_rt_page(self, title, year):
        """
        Find actual Rotten Tomatoes page and score for a movie

        Args:
            title: Movie title
            year: Movie year

        Returns:
            dict: {'url': 'https://...', 'score': '85%'} or None
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if cached:
                print(f"  ✓ RT cache hit: {title} ({year})")
                return cached
            else:
                print(f"  ✓ RT cache (no page found): {title} ({year})")
                return None

        # Initialize driver if needed
        self._init_driver()

        try:
            # Search RT
            search_query = f"{title} {year}"
            search_url = f"https://www.rottentomatoes.com/search?search={search_query.replace(' ', '%20')}"

            print(f"  → Searching RT: {title} ({year})")
            self.driver.get(search_url)
            time.sleep(2)  # Let page load

            # Try to find the first movie result
            # RT uses different selectors, let's try a few
            movie_links = self.driver.find_elements(By.CSS_SELECTOR, "search-page-media-row a[data-qa='info-name']")

            if not movie_links:
                # Try alternative selector
                movie_links = self.driver.find_elements(By.CSS_SELECTOR, "a[data-qa='thumbnail-link']")

            if movie_links:
                first_link = movie_links[0]
                rt_url = first_link.get_attribute('href')

                # Make sure it's a full URL
                if rt_url and not rt_url.startswith('http'):
                    rt_url = f"https://www.rottentomatoes.com{rt_url}"

                # Now go to the page to get the score
                if rt_url:
                    self.driver.get(rt_url)
                    time.sleep(2)

                    # Try to find the Tomatometer score
                    score = None
                    try:
                        # Try different score selectors
                        score_selectors = [
                            "rt-text[slot='criticsScore']",
                            "score-board",
                            "[data-qa='tomatometer']"
                        ]

                        for selector in score_selectors:
                            try:
                                score_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                                score_text = score_elem.text
                                # Extract percentage
                                match = re.search(r'(\d+)%', score_text)
                                if match:
                                    score = f"{match.group(1)}%"
                                    break
                            except:
                                continue

                    except Exception as e:
                        print(f"  Could not extract score: {e}")

                    result = {'url': rt_url, 'score': score}
                    print(f"  ✓ Found RT: {rt_url} (Score: {score or 'N/A'})")

                    # Cache the result
                    self.cache[cache_key] = result
                    self._save_cache()

                    return result

            print(f"  ✗ No RT page found for {title} ({year})")

            # Cache the failure
            self.cache[cache_key] = None
            self._save_cache()

            return None

        except Exception as e:
            print(f"  ✗ Error scraping RT for {title}: {e}")
            return None

    def cleanup(self):
        """Clean up resources"""
        self._close_driver()


if __name__ == "__main__":
    # Test the scraper
    scraper = RTScraper(headless=False)

    test_movies = [
        ("Our Fault", "2025"),
        ("The Long Walk", "2025"),
        ("Freakier Friday", "2025"),
    ]

    print("Testing RT scraper...")
    print("=" * 50)

    for title, year in test_movies:
        result = scraper.find_rt_page(title, year)
        print()

    scraper.cleanup()
