#!/usr/bin/env python3
"""
YouTube Trailer Scraper - Uses Playwright to find direct trailer links
Converts YouTube search URLs to direct watch URLs
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import re
import sys

# Add parent directory to path for playwright_manager import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Shared manager support (enabled by default)
from playwright_manager import get_playwright_manager

class YouTubeTrailerScraper:
    # Words too common to help identify a specific movie in title matching
    STOP_WORDS = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'is', 'it', 'and'}

    # Minimum ratio of movie title words that must appear as whole words in the
    # video title. 0.75 was chosen after testing against 816 real trailers:
    # - Lower (0.67) lets in wrong movies (e.g. "Boy in the Pool" for "The Boy by the Pool")
    # - Higher (0.80+) rejects correct trailers with long subtitles
    # - 0.75 correctly passes all verified matches while rejecting wrong-movie matches
    TITLE_MATCH_THRESHOLD = 0.75

    @staticmethod
    def check_title_match(movie_title, video_title):
        """Check if a video title matches the movie title using whole-word matching.

        Returns (ratio, passed) where ratio is the fraction of movie words found
        in the video title, and passed is True if ratio >= TITLE_MATCH_THRESHOLD.
        """
        cleaned_movie = re.sub(r'[^\w\s]', ' ', movie_title.lower())
        movie_words = [w for w in cleaned_movie.split()
                       if w not in YouTubeTrailerScraper.STOP_WORDS]
        if not movie_words:
            movie_words = cleaned_movie.split()

        video_words = set(re.sub(r'[^\w\s]', ' ', video_title.lower()).split())
        matching = sum(1 for w in movie_words if w in video_words)
        ratio = matching / len(movie_words) if movie_words else 0.0
        return ratio, ratio >= YouTubeTrailerScraper.TITLE_MATCH_THRESHOLD

    @staticmethod
    def check_primary_segment(movie_title, video_title):
        """Check movie title appears in the primary film-title segment of the video title.

        Splits at | or — to isolate the primary portion, strips parentheticals (cast
        credits, dates), then checks word overlap. Catches cast-name-as-title confusion
        where the movie title only appears in a parenthetical credit like (Eva Marcille).

        Returns (ratio, passed) same shape as check_title_match.
        """
        cleaned_movie = re.sub(r'[^\w\s]', ' ', movie_title.lower())
        movie_words = [w for w in cleaned_movie.split()
                       if w not in YouTubeTrailerScraper.STOP_WORDS]
        if not movie_words:
            movie_words = cleaned_movie.split()

        primary = re.split(r'\s*[|—]\s*', video_title)[0].strip()
        primary_clean = re.sub(r'\([^)]*\)', '', primary).strip()
        primary_words = set(re.sub(r'[^\w\s]', ' ', primary_clean.lower()).split())
        matching = sum(1 for w in movie_words if w in primary_words)
        ratio = matching / len(movie_words) if movie_words else 0.0
        return ratio, ratio >= YouTubeTrailerScraper.TITLE_MATCH_THRESHOLD

    def __init__(self, cache_file='cache/youtube_trailer_cache.json', headless=True):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.headless = headless

        # Browser components (lazy initialization)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Manager reference
        self.manager = get_playwright_manager()


    def _load_cache(self):
        """Load cache from file"""
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        """Save cache to file"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def _init_browser(self):
        """Initialize Playwright browser"""
        if self.browser is not None:
            return

        print("[YouTubeTrailerScraper] Initializing browser via shared manager...")
        self._init_browser_shared()

    def _init_browser_shared(self):
        """Initialize browser using shared manager"""
        try:
            # Get shared Playwright instance
            self.playwright = self.manager.get_playwright()

            # Get shared browser from manager
            self.browser = self.manager.get_browser(headless=self.headless, browser_type='chromium')

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

        # Cleanup Playwright via shared manager
        if self.playwright:
            try:
                self.manager.release()
            except:
                pass
            self.playwright = None

    def find_trailer(self, title, year, director=None):
        """
        Find direct YouTube trailer link for a movie

        Args:
            title: Movie title
            year: Movie year
            director: Optional director name — appended to search for short/ambiguous titles

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

        # For short titles (≤2 significant words), add director to disambiguate.
        # "Immortals", "Eva", "Mongrels" are common words; director makes the query specific.
        _stop = YouTubeTrailerScraper.STOP_WORDS | {'s'}
        _sig = [w for w in re.sub(r'[^\w\s]', ' ', title.lower()).split()
                if w not in _stop and not w.isdigit()]
        _dir = f" {director}" if director and len(_sig) <= 2 else ""

        search_terms = [
            f"{title}{_dir} {year} official trailer",
            f"{title}{_dir} {year} official preview",
        ]

        for search_query in search_terms:
            try:
                search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"

                print(f"  → Searching YouTube: {search_query}")
                self.page.goto(search_url, wait_until='domcontentloaded')

                # Wait for video results to load
                try:
                    self.page.wait_for_selector('a#video-title', timeout=10000)
                    self.page.wait_for_timeout(1000)  # Small additional wait for full render
                except PlaywrightTimeoutError:
                    continue

                # Try to find a matching video link from top results
                # YouTube uses <a> tags with /watch?v= in the href
                video_links = self.page.locator('a#video-title').all()

                for video_link in video_links[:5]:
                    video_url = video_link.get_attribute('href')

                    if not video_url or '/watch?v=' not in video_url:
                        continue

                    # Verify the video title matches the movie
                    video_title_text = video_link.get_attribute('title') or ''
                    ratio, passed = self.check_title_match(title, video_title_text)
                    if not passed:
                        print(f"  ✗ Title mismatch ({ratio:.0%}): '{video_title_text[:60]}' for '{title}'")
                        continue
                    _, seg_passed = self.check_primary_segment(title, video_title_text)
                    if not seg_passed:
                        print(f"  ✗ Title in credit only: '{video_title_text[:60]}' for '{title}'")
                        continue

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

            except Exception as e:
                print(f"  ✗ Error scraping {title} with '{search_query}': {e}")
                continue

        print(f"  ✗ No trailer found for {title} ({year})")

        # Cache the failure (so we don't keep trying)
        self.cache[cache_key] = None
        self._save_cache()

        return None

    def find_trailer_broad(self, title, year, director=None):
        """
        Broader trailer search — tries 'trailer' then 'preview' as search terms,
        and filters results to only accept videos with 'trailer' or 'preview' in
        the title. Used as a last-resort fallback (Tier 6) after Gemini/Playwright
        standard search has already failed.

        Args:
            title: Movie title
            year: Movie year
            director: Optional director name — appended to search for short/ambiguous titles

        Returns:
            Direct YouTube watch URL or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Initialize browser if needed
        self._init_browser()

        _stop = YouTubeTrailerScraper.STOP_WORDS | {'s'}
        _sig = [w for w in re.sub(r'[^\w\s]', ' ', title.lower()).split()
                if w not in _stop and not w.isdigit()]
        _dir = f" {director}" if director and len(_sig) <= 2 else ""

        search_terms = [
            f"{title}{_dir} {year} trailer",
            f"{title}{_dir} {year} preview",
        ]

        for search_query in search_terms:
            try:
                search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
                print(f"  → Broad search: {search_query}")
                self.page.goto(search_url, wait_until='domcontentloaded')

                try:
                    self.page.wait_for_selector('a#video-title', timeout=10000)
                    self.page.wait_for_timeout(1000)
                except PlaywrightTimeoutError:
                    continue

                video_links = self.page.locator('a#video-title').all()

                # Check up to first 5 results for a title containing 'trailer' or 'preview'
                for link in video_links[:5]:
                    video_title = (link.get_attribute('title') or '').lower()
                    video_url = link.get_attribute('href')

                    if not video_url or '/watch?v=' not in video_url:
                        continue

                    # Filter: video title must contain 'trailer' or 'preview'
                    if 'trailer' not in video_title and 'preview' not in video_title:
                        continue

                    # Filter: video title must contain the movie title words as whole words
                    # Prevents matching wrong movie (e.g., "BODYCAM" for "Cat Cam")
                    ratio, passed = self.check_title_match(title, video_title)
                    if not passed:
                        print(f"  ✗ Broad search title mismatch ({ratio:.0%}): '{video_title[:60]}' for '{title}'")
                        continue
                    _, seg_passed = self.check_primary_segment(title, video_title)
                    if not seg_passed:
                        print(f"  ✗ Broad search title in credit only: '{video_title[:60]}' for '{title}'")
                        continue

                    if video_url.startswith('/watch'):
                        video_url = f"https://www.youtube.com{video_url}"
                    if '&' in video_url:
                        video_url = video_url.split('&')[0]

                    print(f"  ✓ Broad search found: {video_url} ({video_title[:60]})")
                    self.cache[cache_key] = video_url
                    self._save_cache()
                    return video_url

            except Exception as e:
                print(f"  ✗ Broad search error for '{search_query}': {e}")
                continue

        print(f"  ✗ Broad search: no trailer/preview found for {title} ({year})")
        self.cache[cache_key] = None
        self._save_cache()
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

                # Check if cached BEFORE calling find_trailer (which adds to cache)
                cache_key = f"{title}_{year}"
                was_cached = cache_key in self.cache

                url = self.find_trailer(title, year)
                results[(title, year)] = url

                if url and not was_cached:  # Only count new searches, not cache hits
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