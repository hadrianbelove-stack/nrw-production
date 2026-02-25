#!/usr/bin/env python3
"""
Gemini-based scraper for YouTube trailers, RT scores, and Wikipedia URLs.

Uses Google's Gemini API with Google Search grounding to intelligently find
movie-related content. Replaces Playwright-based scrapers for these use cases.

Created: 2026-02-23
"""

import json
import os
import re
import time
import logging
import random
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

# Module-level logger
logger = logging.getLogger(__name__)


def _load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml."""
    try:
        import yaml
        config_path = Path(__file__).parent / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load config.yaml: {e}")
    return {}


def _get_gemini_api_key() -> Optional[str]:
    """Get Gemini API key from environment or config."""
    # Environment variable takes precedence
    key = os.environ.get('GEMINI_API_KEY')
    if key:
        return key

    # Fall back to config.yaml
    config = _load_config()
    return config.get('api', {}).get('gemini_api_key')


# =============================================================================
# Shared Base Class
# =============================================================================

class GeminiFinderBase:
    """
    Base class for all Gemini-powered finders.

    Provides shared functionality:
    - Gemini API initialization
    - Rate limiting between API calls
    - Retry with exponential backoff
    - Cache load/save
    - Cleanup interface
    """

    # Subclasses set this for log messages (e.g., "YouTube", "RT", "Wikipedia")
    _finder_name = 'Gemini'

    def __init__(self, cache_file: str):
        """Initialize common Gemini finder attributes.

        Args:
            cache_file: Path to cache file
        """
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.client = None
        self.types = None
        self.grounding_tool = None
        self.model_name = None
        self._initialized = False

        # Load config values from config.yaml
        config = _load_config()
        scraper_config = config.get('gemini_scraper', {})
        self.timeout_seconds = scraper_config.get('timeout_seconds', 30)
        self.rate_limit = scraper_config.get('rate_limit', 1.0)
        self.cache_ttl_days = scraper_config.get('cache_ttl_days', 90)
        self.max_retries = scraper_config.get('max_retries', 3)
        self.last_request_time = 0

        # Base stats - subclasses extend via _get_extra_stats()
        self.stats = {
            'gemini_attempts': 0,
            'gemini_successes': 0,
            'gemini_failures': 0,
            'cache_hits': 0,
            'retries': 0
        }
        self.stats.update(self._get_extra_stats())

    def _get_extra_stats(self) -> Dict[str, int]:
        """Override in subclasses to add finder-specific stats."""
        return {}

    def _load_cache(self) -> Dict:
        """Load cache from file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load {self._finder_name} cache: {e}")
        return {}

    def _save_cache(self):
        """Save cache to file."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save {self._finder_name} cache: {e}")

    def _enforce_rate_limit(self):
        """Ensure minimum time between API requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _retry_with_backoff(self, fn, max_attempts: int = None):
        """Retry function with exponential backoff.

        Args:
            fn: Function to call (should return result or raise exception)
            max_attempts: Maximum retry attempts (defaults to self.max_retries)

        Returns:
            Result from fn, or None if all attempts failed
        """
        if max_attempts is None:
            max_attempts = self.max_retries

        for attempt in range(max_attempts):
            try:
                result = fn()
                if result is not None:
                    return result
                # fn returned None - still counts as "success" (no error)
                return None
            except Exception as e:
                if attempt < max_attempts - 1:
                    # Exponential backoff: 0.5s, 1s, 2s, capped at 5s
                    base_delay = 0.5 * (2 ** attempt)
                    delay = min(5.0, base_delay)
                    # Add jitter (±20%)
                    jitter = random.uniform(-0.2 * delay, 0.2 * delay)
                    sleep_time = delay + jitter
                    logger.warning(f"{self._finder_name} attempt {attempt + 1} failed: {e}, retrying in {sleep_time:.1f}s")
                    self.stats['retries'] += 1
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All {max_attempts} {self._finder_name} attempts failed: {e}")
        return None

    def _init_gemini(self) -> bool:
        """Initialize Gemini API client. Returns True if successful."""
        if self._initialized:
            return self.client is not None

        self._initialized = True

        api_key = _get_gemini_api_key()
        if not api_key:
            logger.error(f"No Gemini API key found for {self._finder_name} finder")
            return False

        try:
            from google import genai
            from google.genai import types

            self.client = genai.Client(api_key=api_key)
            self.types = types
            self.grounding_tool = types.Tool(google_search=types.GoogleSearch())
            self.model_name = 'gemini-2.5-flash'

            logger.info(f"Gemini {self._finder_name} finder initialized")
            return True

        except ImportError:
            logger.error("google-genai not installed. Run: pip install google-genai")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Gemini for {self._finder_name}: {e}")
            return False

    def get_stats(self) -> Dict[str, int]:
        """Return statistics about finder usage."""
        return self.stats.copy()

    def cleanup(self):
        """Clean up resources. Override in subclasses if needed."""
        pass

    def close(self):
        """Alias for cleanup (compatibility with other scrapers)."""
        self.cleanup()


class GeminiYouTubeFinder(GeminiFinderBase):
    """
    Finds YouTube trailer URLs using Gemini API with Google Search grounding.

    Usage:
        finder = GeminiYouTubeFinder()
        url = finder.find_trailer("The Brutalist", 2024)
        # Returns: "https://www.youtube.com/watch?v=..." or None
    """

    _finder_name = 'YouTube'

    def __init__(self, cache_file: str = 'cache/youtube_trailer_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'invalid_urls': 0}

    def _validate_youtube_url(self, url: str) -> bool:
        """Validate that a URL is a valid YouTube watch URL."""
        if not url:
            return False

        # Match youtube.com/watch?v= or youtu.be/ formats
        patterns = [
            r'^https?://(www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11}',
            r'^https?://youtu\.be/[a-zA-Z0-9_-]{11}'
        ]

        for pattern in patterns:
            if re.match(pattern, url):
                return True

        return False

    def _extract_youtube_url(self, text: str) -> Optional[str]:
        """Extract YouTube URL from Gemini response text."""
        if not text:
            return None

        # Look for YouTube URLs in the response
        patterns = [
            r'https?://(www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11}',
            r'https?://youtu\.be/[a-zA-Z0-9_-]{11}'
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                url = match.group(0)
                # Normalize youtu.be to youtube.com format
                if 'youtu.be/' in url:
                    video_id = url.split('youtu.be/')[-1][:11]
                    url = f"https://www.youtube.com/watch?v={video_id}"
                return url

        return None

    def find_trailer(
        self,
        title: str,
        year: int,
        director: str = None,
        cast: list = None
    ) -> Optional[str]:
        """
        Find YouTube trailer URL for a movie using Gemini.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for disambiguation
            cast: Optional list of cast members for disambiguation

        Returns:
            YouTube URL string or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            self.stats['cache_hits'] += 1
            cached_value = self.cache[cache_key]
            logger.debug(f"Cache hit for {title} ({year}): {cached_value}")
            return cached_value

        # Initialize Gemini if needed
        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # Build context for better matching
        context_parts = [f'"{title}" ({year})']
        if director:
            context_parts.append(f"directed by {director}")
        if cast and len(cast) > 0:
            context_parts.append(f"starring {', '.join(cast[:3])}")

        movie_context = " ".join(context_parts)

        # Construct prompt
        prompt = f"""Find the official YouTube trailer URL for the movie {movie_context}.

Requirements:
- Return ONLY the YouTube URL, nothing else
- Must be the official trailer (not fan-made, not clips, not reviews)
- If there are multiple trailers, prefer the main theatrical trailer
- If no official trailer exists, respond with exactly: NO_TRAILER_EXISTS
- If you cannot find it, respond with exactly: NOT_FOUND

YouTube URL:"""

        # Define the API call as a function for retry wrapper
        def _make_api_request():
            # Use grounding with Google Search for real-time results
            api_config = self.types.GenerateContentConfig(
                tools=[self.grounding_tool]
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=api_config
            )
            return response.text.strip()

        try:
            # Apply rate limiting before API call
            self._enforce_rate_limit()

            # Make API call with retry logic
            result_text = self._retry_with_backoff(_make_api_request)

            if result_text is None:
                logger.error(f"All retries failed for {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            logger.debug(f"Gemini response for {title}: {result_text}")

            # Handle explicit "no trailer" responses
            if 'NO_TRAILER_EXISTS' in result_text:
                logger.info(f"No trailer exists for {title} ({year})")
                self.cache[cache_key] = None
                self._save_cache()
                self.stats['gemini_successes'] += 1
                return None

            if 'NOT_FOUND' in result_text:
                logger.info(f"Could not find trailer for {title} ({year})")
                # Don't cache NOT_FOUND - might succeed on retry
                self.stats['gemini_failures'] += 1
                return None

            # Extract URL from response
            url = self._extract_youtube_url(result_text)

            if url and self._validate_youtube_url(url):
                logger.info(f"Found trailer for {title} ({year}): {url}")
                self.cache[cache_key] = url
                self._save_cache()
                self.stats['gemini_successes'] += 1
                return url
            else:
                logger.warning(f"Invalid URL returned for {title} ({year}): {result_text}")
                self.stats['invalid_urls'] += 1
                self.stats['gemini_failures'] += 1
                return None

        except Exception as e:
            logger.error(f"Gemini API error for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1
            return None


class HybridYouTubeFinder:
    """
    Hybrid finder that tries Gemini first, falls back to Playwright.

    Usage:
        finder = HybridYouTubeFinder()
        url = finder.find_trailer("The Brutalist", 2024)
    """

    def __init__(self, cache_file: str = 'cache/youtube_trailer_cache.json'):
        """Initialize hybrid finder with both backends."""
        self.gemini_finder = GeminiYouTubeFinder(cache_file=cache_file)
        self.playwright_finder = None  # Lazy load
        self.cache_file = cache_file

        self.stats = {
            'total_requests': 0,
            'gemini_resolved': 0,
            'playwright_resolved': 0,
            'fallback_attempts': 0,
            'total_failures': 0
        }

    def _get_playwright_finder(self):
        """Lazy-load Playwright finder only when needed."""
        if self.playwright_finder is None:
            try:
                from scripts.youtube_trailer_scraper import YouTubeTrailerScraper
                self.playwright_finder = YouTubeTrailerScraper(
                    cache_file=self.cache_file,
                    headless=True
                )
            except ImportError as e:
                logger.warning(f"Could not load Playwright fallback: {e}")
        return self.playwright_finder

    def find_trailer(
        self,
        title: str,
        year: int,
        director: str = None,
        cast: list = None,
        use_fallback: bool = True
    ) -> Optional[str]:
        """
        Find trailer using Gemini, with optional Playwright fallback.

        Args:
            title: Movie title
            year: Release year
            director: Optional director for disambiguation
            cast: Optional cast list for disambiguation
            use_fallback: Whether to try Playwright if Gemini fails

        Returns:
            YouTube URL or None
        """
        self.stats['total_requests'] += 1

        # Try Gemini first
        result = self.gemini_finder.find_trailer(title, year, director, cast)

        if result is not None:
            # Found via Gemini (including explicit None for "no trailer exists")
            self.stats['gemini_resolved'] += 1
            return result

        # Check if this was a cache hit that returned None (no trailer exists)
        cache_key = f"{title}_{year}"
        if cache_key in self.gemini_finder.cache:
            # Cached as None = confirmed no trailer
            return None

        # Gemini failed - try Playwright fallback if enabled
        if use_fallback:
            self.stats['fallback_attempts'] += 1
            logger.info(f"Falling back to Playwright for {title} ({year})")

            playwright = self._get_playwright_finder()
            if playwright:
                try:
                    result = playwright.find_trailer(title, str(year))
                    if result:
                        self.stats['playwright_resolved'] += 1
                        return result
                except Exception as e:
                    logger.error(f"Playwright fallback error: {e}")

        self.stats['total_failures'] += 1
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Return combined statistics."""
        return {
            **self.stats,
            'gemini_stats': self.gemini_finder.get_stats()
        }

    def cleanup(self):
        """Clean up resources."""
        if self.playwright_finder:
            try:
                self.playwright_finder.cleanup()
            except Exception as e:
                logger.warning(f"Failed to cleanup Playwright YouTube finder: {e}")


# =============================================================================
# Rotten Tomatoes Finder Classes
# =============================================================================

class GeminiRTFinder(GeminiFinderBase):
    """
    Finds Rotten Tomatoes URLs and scores using Gemini API with Google Search grounding.

    Usage:
        finder = GeminiRTFinder()
        result = finder.find_rt_score("Conclave", 2024)
        # Returns: {'url': 'https://rottentomatoes.com/m/...', 'score': '93%'} or None
    """

    _finder_name = 'RT'

    def __init__(self, cache_file: str = 'cache/rt_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'invalid_responses': 0}

    def _validate_rt_url(self, url: str) -> bool:
        """Validate that a URL is a valid Rotten Tomatoes movie URL."""
        if not url:
            return False
        # Match rottentomatoes.com/m/ format
        pattern = r'^https?://(www\.)?rottentomatoes\.com/m/[a-zA-Z0-9_-]+'
        return bool(re.match(pattern, url))

    def _extract_rt_data(self, text: str) -> Optional[Dict[str, str]]:
        """Extract RT URL and score from Gemini response text."""
        if not text:
            return None

        result = {}

        # Extract URL
        url_pattern = r'https?://(www\.)?rottentomatoes\.com/m/[a-zA-Z0-9_-]+'
        url_match = re.search(url_pattern, text)
        if url_match:
            result['url'] = url_match.group(0)
            # Normalize to www version
            if not result['url'].startswith('https://www.'):
                result['url'] = result['url'].replace('https://', 'https://www.')

        # Extract score (look for percentage)
        score_patterns = [
            r'(\d{1,3})%',  # Simple percentage
            r'SCORE:\s*(\d{1,3})%',  # SCORE: XX%
            r'Tomatometer[:\s]+(\d{1,3})%',  # Tomatometer: XX%
        ]
        for pattern in score_patterns:
            score_match = re.search(pattern, text, re.IGNORECASE)
            if score_match:
                score = int(score_match.group(1))
                if 0 <= score <= 100:
                    result['score'] = f"{score}%"
                    break

        # Must have at least URL to be valid
        if 'url' in result:
            return result
        return None

    def find_rt_score(
        self,
        title: str,
        year: int,
        director: str = None
    ) -> Optional[Dict[str, str]]:
        """
        Find Rotten Tomatoes URL and score for a movie using Gemini.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for disambiguation

        Returns:
            Dict with 'url' and 'score' keys, or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            # Handle both old format (just url/score) and new format (with metadata)
            if isinstance(cached_data, dict) and cached_data.get('url'):
                self.stats['cache_hits'] += 1
                logger.debug(f"RT cache hit for {title} ({year})")
                return {'url': cached_data.get('url'), 'score': cached_data.get('score')}

        # Initialize Gemini if needed
        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # Build context for better matching
        context_parts = [f'"{title}" ({year})']
        if director:
            context_parts.append(f"directed by {director}")
        movie_context = " ".join(context_parts)

        # Construct prompt
        prompt = f"""Find the Rotten Tomatoes page and Tomatometer critic score for the movie {movie_context}.

Requirements:
- Return the RT URL in format: https://www.rottentomatoes.com/m/movie_name
- Return the Tomatometer critic score as a percentage
- Format your response as: URL: [url] SCORE: [XX]%
- If no RT page exists, respond with exactly: NO_RT_PAGE
- If you cannot find it, respond with exactly: NOT_FOUND

Response:"""

        def _make_api_request():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=api_config
            )
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_make_api_request)

            if result_text is None:
                logger.error(f"All retries failed for RT {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            logger.debug(f"Gemini RT response for {title}: {result_text}")

            # Handle explicit "no page" responses
            if 'NO_RT_PAGE' in result_text:
                logger.info(f"No RT page exists for {title} ({year})")
                self.cache[cache_key] = {'url': None, 'score': None, 'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
                self._save_cache()
                self.stats['gemini_successes'] += 1
                return None

            if 'NOT_FOUND' in result_text:
                logger.info(f"Could not find RT page for {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            # Extract data from response
            data = self._extract_rt_data(result_text)

            if data and self._validate_rt_url(data.get('url', '')):
                logger.info(f"Found RT for {title} ({year}): {data['url']} ({data.get('score', 'N/A')})")
                self.cache[cache_key] = {
                    'url': data['url'],
                    'score': data.get('score'),
                    'title': title,
                    'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                }
                self._save_cache()
                self.stats['gemini_successes'] += 1
                return data
            else:
                logger.warning(f"Invalid RT response for {title} ({year}): {result_text}")
                self.stats['invalid_responses'] += 1
                self.stats['gemini_failures'] += 1
                return None

        except Exception as e:
            logger.error(f"Gemini RT API error for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1
            return None


class HybridRTFinder:
    """
    Hybrid RT finder that tries Gemini first, falls back to Playwright.

    Usage:
        finder = HybridRTFinder()
        result = finder.find_rt_score("Conclave", 2024)
    """

    def __init__(self, cache_file: str = 'cache/rt_cache.json', config: Dict = None, logger_instance=None):
        """Initialize hybrid finder with both backends."""
        self.gemini_finder = GeminiRTFinder(cache_file=cache_file)
        self.playwright_scraper = None  # Lazy load
        self.cache_file = cache_file
        self.config = config or {}
        self.logger_instance = logger_instance

        self.stats = {
            'total_requests': 0,
            'gemini_resolved': 0,
            'playwright_resolved': 0,
            'fallback_attempts': 0,
            'total_failures': 0
        }

    def _get_playwright_scraper(self):
        """Lazy-load Playwright RT scraper only when needed."""
        if self.playwright_scraper is None:
            try:
                from rt_scraper_playwright import RTScraperPlaywright
                self.playwright_scraper = RTScraperPlaywright(
                    cache_file=self.cache_file,
                    config=self.config,
                    logger=self.logger_instance
                )
            except ImportError as e:
                logger.warning(f"Could not load Playwright RT fallback: {e}")
        return self.playwright_scraper

    @property
    def cache(self):
        """Expose cache for compatibility with generator.py."""
        return self.gemini_finder.cache

    def find_rt_score(
        self,
        title: str,
        year: int,
        director: str = None,
        use_fallback: bool = True
    ) -> Optional[Dict[str, str]]:
        """
        Find RT score using Gemini, with optional Playwright fallback.

        Args:
            title: Movie title
            year: Release year
            director: Optional director for disambiguation
            use_fallback: Whether to try Playwright if Gemini fails

        Returns:
            Dict with 'url' and 'score', or None
        """
        self.stats['total_requests'] += 1

        # Try Gemini first
        result = self.gemini_finder.find_rt_score(title, year, director)

        if result is not None:
            self.stats['gemini_resolved'] += 1
            return result

        # Check if this was a cache hit that returned None (no RT page exists)
        cache_key = f"{title}_{year}"
        if cache_key in self.gemini_finder.cache:
            cached = self.gemini_finder.cache[cache_key]
            if isinstance(cached, dict) and cached.get('url') is None:
                # Cached as None = confirmed no RT page
                return None

        # Gemini failed - try Playwright fallback if enabled
        if use_fallback:
            self.stats['fallback_attempts'] += 1
            logger.info(f"Falling back to Playwright RT for {title} ({year})")

            playwright = self._get_playwright_scraper()
            if playwright:
                try:
                    result = playwright.scrape_rt_score(title, year)
                    if result:
                        self.stats['playwright_resolved'] += 1
                        return result
                except Exception as e:
                    logger.error(f"Playwright RT fallback error: {e}")

        self.stats['total_failures'] += 1
        return None

    # Compatibility methods to match RTScraperPlaywright interface
    def scrape_rt_score(self, title: str, year: int) -> Optional[Dict[str, str]]:
        """Compatibility wrapper matching RTScraperPlaywright interface."""
        return self.find_rt_score(title, year)

    def get_stats(self) -> Dict[str, Any]:
        """Return combined statistics with compatibility aliases for generator.py."""
        gemini_stats = self.gemini_finder.get_stats()
        return {
            **self.stats,
            'gemini_stats': gemini_stats,
            # Compatibility aliases expected by generator.py
            'attempts': self.stats['total_requests'],
            'successes': self.stats['gemini_resolved'] + self.stats['playwright_resolved'],
            'cache_hits': gemini_stats.get('cache_hits', 0)
        }

    def close(self):
        """Clean up resources (compatibility with RTScraperPlaywright)."""
        self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        if self.playwright_scraper:
            try:
                self.playwright_scraper.close()
            except Exception as e:
                logger.warning(f"Failed to cleanup Playwright RT scraper: {e}")


# =============================================================================
# Wikipedia Finder Class
# =============================================================================

class GeminiWikipediaFinder(GeminiFinderBase):
    """
    Finds Wikipedia URLs using Gemini API with Google Search grounding.

    Used as step 2.5 in Wikipedia waterfall (after Wikidata, before REST API).

    Usage:
        finder = GeminiWikipediaFinder()
        result = finder.find_wikipedia_url("The Brutalist", 2024)
        # Returns: 'https://en.wikipedia.org/wiki/The_Brutalist_(film)' or None
    """

    _finder_name = 'Wikipedia'

    def __init__(self, cache_file: str = 'cache/wikipedia_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'invalid_responses': 0}

    def _validate_wikipedia_url(self, url: str) -> bool:
        """Validate that URL is a valid Wikipedia article URL (not a search page)."""
        if not url or not isinstance(url, str):
            return False
        # Must be en.wikipedia.org/wiki/ format (not search)
        pattern = r'^https?://en\.wikipedia\.org/wiki/[^?]+'
        if not re.match(pattern, url):
            return False
        # Reject search URLs
        if 'index.php?search=' in url or 'Special:Search' in url:
            return False
        return True

    def find_wikipedia_url(
        self,
        title: str,
        year: int,
        director: str = None
    ) -> Optional[str]:
        """
        Find Wikipedia URL for a movie using Gemini.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for disambiguation

        Returns:
            Wikipedia URL or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first (but honor existing scraper's cache format)
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict):
                url = cached_data.get('url')
                source = cached_data.get('source', '')
                # Skip old search fallback entries
                if source == 'search_fallback' or cached_data.get('is_search_fallback'):
                    pass  # Don't return, let Gemini try
                elif url and '/wiki/' in url and 'index.php?search=' not in url:
                    self.stats['cache_hits'] += 1
                    logger.debug(f"Wikipedia cache hit for {title} ({year})")
                    return url
            elif isinstance(cached_data, str) and '/wiki/' in cached_data and 'index.php?search=' not in cached_data:
                self.stats['cache_hits'] += 1
                return cached_data

        # Initialize Gemini if needed
        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # Build context for better matching
        context_parts = [f'"{title}" ({year})']
        if director:
            context_parts.append(f"directed by {director}")
        movie_context = " ".join(context_parts)

        # Construct prompt
        prompt = f"""Find the English Wikipedia article URL for the movie {movie_context}.

Requirements:
- Return ONLY the direct Wikipedia article URL in format: https://en.wikipedia.org/wiki/Article_Name
- Do NOT return search URLs or disambiguation pages
- If there is a "(film)" or "(YEAR film)" version, prefer that
- If no Wikipedia article exists, respond with exactly: NO_ARTICLE_EXISTS
- If you cannot find it, respond with exactly: NOT_FOUND

Response:"""

        def _make_api_request():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=api_config
            )
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_make_api_request)

            if result_text is None:
                logger.error(f"All retries failed for Wikipedia {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            logger.debug(f"Gemini Wikipedia response for {title}: {result_text}")

            # Handle explicit "no article" responses
            if 'NO_ARTICLE_EXISTS' in result_text:
                logger.info(f"No Wikipedia article exists for {title} ({year})")
                # Don't cache this - let other methods try
                self.stats['gemini_successes'] += 1
                return None

            if 'NOT_FOUND' in result_text:
                logger.info(f"Could not find Wikipedia article for {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            # Extract URL from response (allow parentheses for disambiguation pages)
            url_pattern = r'https://en\.wikipedia\.org/wiki/[^\s\]<>"]+'
            url_match = re.search(url_pattern, result_text)

            if url_match:
                url = url_match.group(0)
                # Clean up any trailing punctuation (but preserve closing parens)
                url = url.rstrip('.,;:')

                if self._validate_wikipedia_url(url):
                    logger.info(f"Found Wikipedia for {title} ({year}): {url}")
                    # Cache in compatible format
                    self.cache[cache_key] = {
                        'url': url,
                        'title': title,
                        'source': 'gemini',
                        'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                    }
                    self._save_cache()
                    self.stats['gemini_successes'] += 1
                    return url
                else:
                    logger.warning(f"Invalid Wikipedia URL for {title} ({year}): {url}")
                    self.stats['invalid_responses'] += 1
                    self.stats['gemini_failures'] += 1
                    return None
            else:
                logger.warning(f"No Wikipedia URL in response for {title} ({year}): {result_text}")
                self.stats['invalid_responses'] += 1
                self.stats['gemini_failures'] += 1
                return None

        except Exception as e:
            logger.error(f"Gemini Wikipedia API error for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1
            return None


# Convenience function for quick usage
def find_youtube_trailer(
    title: str,
    year: int,
    use_fallback: bool = True
) -> Optional[str]:
    """
    Quick function to find a YouTube trailer.

    Args:
        title: Movie title
        year: Release year
        use_fallback: Whether to use Playwright fallback

    Returns:
        YouTube URL or None
    """
    finder = HybridYouTubeFinder()
    try:
        return finder.find_trailer(title, year, use_fallback=use_fallback)
    finally:
        finder.cleanup()


if __name__ == "__main__":
    # Test the finder
    import sys

    logging.basicConfig(level=logging.INFO)

    # Test movies - including some known failures
    test_movies = [
        ("The Brutalist", 2024),
        ("Anora", 2024),
        ("Kill Tony: Mayhem at Madison Square Garden", 2025),  # Known null
        ("signal/noise", 2025),  # Known null
    ]

    print("Testing Gemini YouTube Trailer Finder")
    print("=" * 50)

    finder = GeminiYouTubeFinder()

    for title, year in test_movies:
        print(f"\nSearching: {title} ({year})")
        url = finder.find_trailer(title, year)
        if url:
            print(f"  Found: {url}")
        else:
            print(f"  Not found")

    print("\n" + "=" * 50)
    print("Stats:", finder.get_stats())
