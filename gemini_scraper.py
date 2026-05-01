#!/usr/bin/env python3
"""
Gemini-based scraper for YouTube trailers, RT scores, and Wikipedia URLs.

Uses Google's Gemini API with Google Search grounding to intelligently find
movie-related content. Replaces Playwright-based scrapers for these use cases.

Created: 2026-02-23
"""

import load_env  # Load .env into os.environ
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
- Must be the official trailer or preview (not fan-made, not clips, not reviews)
- If there are multiple trailers, prefer the main theatrical trailer
- An official preview (e.g. from a network or studio) is acceptable if no trailer exists
- If no official trailer or preview exists, respond with exactly: NO_TRAILER_EXISTS
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
            self.stats['gemini_resolved'] += 1
            return result

        # Gemini returned None — always try Playwright fallback
        # (Gemini's NO_TRAILER_EXISTS is unreliable for small/indie films)
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

    def _validate_rt_url_matches_title(self, url: str, title: str, year: Any = None) -> bool:
        """Validate that an RT URL slug reasonably matches the movie title.

        Catches obvious Gemini hallucinations where the URL is for a completely
        different movie (e.g., 'hachi_a_dogs_tale' for 'Muerta en Vida').

        Args:
            url: The Rotten Tomatoes URL
            title: The expected movie title
            year: The expected movie year (int or str)

        Returns:
            True if the URL plausibly matches the title
        """
        if not url or not title:
            return False

        # Extract slug from URL (e.g., "hachi_a_dogs_tale" from ".../m/hachi_a_dogs_tale")
        slug = url.rstrip('/').split('/m/')[-1].split('?')[0]

        # Year validation: if slug contains a year, it must match the requested year
        slug_year_match = re.search(r'_(\d{4})$', slug)
        if slug_year_match and year:
            slug_year = int(slug_year_match.group(1))
            requested_year = int(year)
            if abs(slug_year - requested_year) > 1:  # Allow ±1 year for release date differences
                logger.warning(f"RT URL year mismatch: slug has {slug_year}, "
                               f"expected ~{requested_year} for '{title}'")
                return False

        # Strip year suffixes from slug (e.g., "movie_name_2025" → "movie_name")
        slug_no_year = re.sub(r'_\d{4}$', '', slug)

        # Normalize title: lowercase, remove articles and punctuation, split to words
        title_normalized = title.lower()
        title_normalized = re.sub(r'^(the|a|an)\s+', '', title_normalized)
        title_normalized = re.sub(r'[^a-z0-9\s]', '', title_normalized)
        title_words = set(title_normalized.split())

        # Normalize slug to words
        slug_words = set(slug_no_year.lower().replace('-', '_').split('_'))

        # Remove common stop words from both
        stop_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'and', 'or', 'is', 'it'}
        title_words -= stop_words
        slug_words -= stop_words

        # Filter to significant words (>2 chars)
        title_significant = {w for w in title_words if len(w) > 2}
        slug_significant = {w for w in slug_words if len(w) > 2}

        if not title_significant:
            # Very short title, can't validate meaningfully
            return True

        # Check for word overlap
        overlap = title_significant & slug_significant
        if overlap:
            return True

        # Also check if title words appear as substrings in the slug
        slug_flat = slug_no_year.lower().replace('_', '').replace('-', '')
        title_flat = re.sub(r'[^a-z0-9]', '', title.lower())

        # Check if the title (without spaces) appears in the slug
        if title_flat in slug_flat or slug_flat in title_flat:
            return True

        logger.warning(f"RT URL mismatch: slug '{slug}' doesn't match title '{title}' "
                       f"(title_words={title_significant}, slug_words={slug_significant})")
        return False

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
        director: str = None,
        original_language: str = None,
        original_title: str = None
    ) -> Optional[Dict[str, str]]:
        """
        Find Rotten Tomatoes URL and score for a movie using Gemini.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for disambiguation
            original_language: ISO 639-1 language code (e.g. 'es', 'fr')
            original_title: Original-language title from TMDB (if different from title)

        Returns:
            Dict with 'url' and 'score' keys, or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            # Handle both old format (just url/score) and new format (with metadata)
            if isinstance(cached_data, dict) and cached_data.get('url') and cached_data.get('score'):
                self.stats['cache_hits'] += 1
                logger.debug(f"RT cache hit for {title} ({year})")
                return {'url': cached_data.get('url'), 'score': cached_data.get('score')}
            # If URL exists but no score, fall through to re-query Gemini
            if isinstance(cached_data, dict) and cached_data.get('url') and not cached_data.get('score'):
                logger.debug(f"RT cache partial hit for {title} ({year}): URL exists but no score, re-querying")

        # Initialize Gemini if needed
        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # Build context for better matching
        context_parts = [f'"{title}" ({year})']
        if director:
            context_parts.append(f"directed by {director}")
        if original_language and original_language != 'en':
            lang_names = {
                'es': 'Spanish', 'fr': 'French', 'ja': 'Japanese',
                'ko': 'Korean', 'he': 'Hebrew', 'ta': 'Tamil',
                'pt': 'Portuguese', 'sv': 'Swedish', 'ml': 'Malayalam',
                'ro': 'Romanian', 'tl': 'Tagalog', 'id': 'Indonesian',
                'th': 'Thai', 'hi': 'Hindi', 'zh': 'Chinese',
                'de': 'German', 'it': 'Italian', 'ar': 'Arabic',
            }
            lang_name = lang_names.get(original_language, original_language)
            context_parts.append(f"(original language: {lang_name})")
        if original_title and original_title != title:
            context_parts.append(f"(original title: {original_title})")
        movie_context = " ".join(context_parts)

        # Construct prompt
        prompt = f"""Find the Rotten Tomatoes page and Tomatometer critic score for the movie {movie_context}.

Requirements:
- The movie MUST be from {year}. Do not return a different movie with a similar title from a different year.
- Return the RT URL in format: https://www.rottentomatoes.com/m/movie_name
- Return the Tomatometer critic score as a percentage
- Format your response as: URL: [url] SCORE: [XX]%
- If no RT page exists for this specific movie, respond with exactly: NO_RT_PAGE
- If you are not confident you found the exact right movie, respond with exactly: NOT_FOUND

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
                # Validate that the URL actually matches the requested movie
                if not self._validate_rt_url_matches_title(data['url'], title, year=year):
                    logger.warning(f"RT URL rejected (wrong movie): {data['url']} for '{title}' ({year})")
                    self.stats['invalid_responses'] += 1
                    self.stats['gemini_failures'] += 1
                    return None

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


    def find_score_for_url(self, url: str, title: str = None, year: int = None) -> Optional[str]:
        """Ask Gemini for the score on a SPECIFIC RT URL (no searching).

        This is fundamentally safer than find_rt_score() because Gemini reads
        a known page rather than searching for a movie (where hallucinations happen).

        Args:
            url: The known-correct Rotten Tomatoes URL
            title: Movie title (for logging only)
            year: Movie year (for logging only)

        Returns:
            Score string (e.g., "85%") or None
        """
        if not self._init_gemini():
            return None

        label = f"{title} ({year})" if title else url

        prompt = (
            f"What is the Tomatometer critic score percentage shown on this exact "
            f"Rotten Tomatoes page: {url}\n\n"
            f"Return ONLY the percentage number (e.g., 85%) or NO_SCORE if no "
            f"Tomatometer score is displayed on the page."
        )

        try:
            from google.genai import types
            api_config = types.GenerateContentConfig(
                tools=[self.grounding_tool],
                temperature=0.0,
            )

            def _make_request():
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=api_config
                )
                return response.text.strip()

            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_make_request)
            if not result_text:
                return None

            if 'NO_SCORE' in result_text.upper():
                logger.info(f"No score on RT page for {label}: {url}")
                return None

            # Extract percentage
            score_match = re.search(r'(\d{1,3})%', result_text)
            if score_match:
                score = int(score_match.group(1))
                if 0 <= score <= 100:
                    logger.info(f"Gemini URL-specific score for {label}: {score}%")
                    return f"{score}%"

            logger.warning(f"Could not parse Gemini URL-specific response for {label}: {result_text}")
            return None

        except Exception as e:
            logger.error(f"Gemini URL-specific query error for {label}: {e}")
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

    def _validate_with_playwright(self, gemini_result: Dict, title: str, year: int,
                                    original_language: str = None, original_title: str = None) -> Optional[Dict[str, str]]:
        """Visit a Gemini-returned RT URL with Playwright to verify it's the right movie.

        Navigates to the RT page, extracts the actual movie title, and compares
        it against the expected title. Also extracts the real score from the page.

        Args:
            gemini_result: Dict with 'url' and 'score' from Gemini
            title: The movie title we searched for
            year: The movie release year
            original_language: ISO 639-1 language code; when not 'en' and neither
                             title matches, accept anyway (RT slug may be translated)
            original_title: Original-language title from TMDB (checked as alt match)

        Returns:
            Validated dict with 'url' and 'score', or None if wrong movie
        """
        url = gemini_result.get('url')
        if not url:
            return None

        playwright = self._get_playwright_scraper()
        if not playwright:
            logger.info("Playwright not available for validation, trusting Gemini result")
            return gemini_result

        try:
            # Initialize browser if needed
            playwright._init_browser()
            playwright._enforce_rate_limit()

            logger.info(f"Playwright validating Gemini URL: {url}")
            response = playwright.page.goto(url, wait_until='domcontentloaded')
            time.sleep(2)

            # Check HTTP status code
            if response and response.status >= 400:
                logger.warning(f"RT page returned HTTP {response.status}: {url}")
                return None

            # Extract page title — RT format: "Movie Name (Year) | Rotten Tomatoes"
            page_title = playwright.page.title() or ""

            # Check for 404 / not found (belt and suspenders with status check above)
            if 'page not found' in page_title.lower() or '404' in page_title:
                logger.warning(f"RT page not found: {url}")
                return None

            # Extract movie title from page title
            movie_part = page_title.split('|')[0].strip() if '|' in page_title else page_title.strip()
            page_movie_title = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_part).strip()

            # Compare titles (check both stored title and original_title)
            title_matches = self._page_title_matches(page_movie_title, title)
            alt_matches = (original_title and original_title != title and
                           self._page_title_matches(page_movie_title, original_title))

            if not title_matches and not alt_matches:
                if original_language and original_language != 'en':
                    # Foreign film — RT slug may be a translation we don't have
                    logger.info(
                        f"Accepting foreign-language film despite title mismatch "
                        f"({original_language}): page='{page_movie_title}', expected='{title}'"
                    )
                else:
                    logger.warning(
                        f"Playwright validation FAILED: page shows '{page_movie_title}', "
                        f"expected '{title}'"
                    )
                    return None

            # Title matched — extract actual score from the loaded page
            actual_score = self._extract_score_from_loaded_page(playwright)

            # If Playwright couldn't extract score, try Gemini URL-specific query
            if not actual_score:
                logger.info(f"Playwright couldn't extract score, trying Gemini URL-specific for {url}")
                actual_score = self.gemini_finder.find_score_for_url(url, title, year)

            logger.info(f"Playwright validated: '{page_movie_title}' matches '{title}', score={actual_score}")

            return {
                'url': url,
                'score': actual_score or gemini_result.get('score')
            }

        except Exception as e:
            logger.warning(f"Playwright validation error for {url}: {e}")
            # Don't trust unvalidated results — better no link than a wrong link
            return None

    def _page_title_matches(self, page_title: str, expected_title: str) -> bool:
        """Check if an RT page title matches the expected movie title.

        Uses word overlap comparison, similar to URL slug validation.
        """
        if not page_title or not expected_title:
            return False

        def normalize(s):
            s = s.lower()
            s = re.sub(r'^(the|a|an)\s+', '', s)
            s = re.sub(r'[^a-z0-9\s]', '', s)
            words = set(s.split())
            words -= {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'and', 'or', 'is', 'it'}
            return {w for w in words if len(w) > 2}

        page_words = normalize(page_title)
        expected_words = normalize(expected_title)

        if not expected_words:
            return True

        overlap = page_words & expected_words
        # Need at least one significant word overlap
        if overlap:
            return True

        # Also check substring match for single-word or transliterated titles
        page_flat = re.sub(r'[^a-z0-9]', '', page_title.lower())
        expected_flat = re.sub(r'[^a-z0-9]', '', expected_title.lower())
        if page_flat in expected_flat or expected_flat in page_flat:
            return True

        return False

    def _extract_score_from_loaded_page(self, playwright_scraper) -> Optional[str]:
        """Extract RT critic score from an already-loaded Playwright page.

        Waterfall: JSON-LD → CSS selectors → text regex.
        """
        page = playwright_scraper.page

        # 1. JSON-LD structured data (most reliable)
        try:
            json_ld_scripts = page.query_selector_all('script[type="application/ld+json"]')
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.text_content() or '{}')
                    if 'aggregateRating' in data:
                        rating = data['aggregateRating'].get('ratingValue')
                        if rating:
                            score = str(int(float(rating)))
                            logger.debug(f"Found score via JSON-LD: {score}%")
                            return f"{score}%"
                except (json.JSONDecodeError, ValueError):
                    continue
        except Exception:
            pass

        # 2. media-scorecard (current RT layout since ~2025)
        try:
            scorecard = page.query_selector('media-scorecard')
            if scorecard:
                text = (scorecard.text_content() or "").strip()
                # First percentage in scorecard is the critics score
                score_match = re.search(r'(\d{1,3})%', text)
                if score_match:
                    score = int(score_match.group(1))
                    if 0 <= score <= 100:
                        logger.debug(f"Found score via media-scorecard: {score}%")
                        return f"{score}%"
        except Exception:
            pass

        # 3. CSS selectors (legacy layouts)
        score_selectors = [
            '[slot="criticsScore"]',
            'rt-text[slot="criticsScore"]',
            '[data-testid="critic-score"] .percentage',
            '[data-testid="critics-score"] .percentage',
            '[class*="criticsScore"]',
            'score-board',
            '.scoreboard__critic .percentage',
            '.mop-ratings-wrap__percentage',
            '.meter-value',
            '.critic-score .percentage',
            '[class*="percentage"]',
        ]

        for selector in score_selectors:
            try:
                elements = page.query_selector_all(selector)
                for element in elements:
                    text = (element.text_content() or "").strip()
                    score_match = re.search(r'(\d+)%?', text)
                    if score_match:
                        return f"{score_match.group(1)}%"
            except Exception:
                continue

        # 4. Text regex patterns (fallback)
        try:
            body = page.query_selector('body')
            if body:
                page_text = body.text_content() or ""
                for pattern in [r'(\d+)%\s*Tomatometer', r'(\d+)%\s*(?:Critics|Critic)', r'Tomatometer.*?(\d+)%']:
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        return f"{match.group(1)}%"
        except Exception:
            pass

        return None

    def find_rt_score(
        self,
        title: str,
        year: int,
        director: str = None,
        use_fallback: bool = True,
        original_language: str = None,
        original_title: str = None
    ) -> Optional[Dict[str, str]]:
        """
        Find RT score using Gemini, validated by Playwright, with Playwright fallback.

        Flow:
        1. Gemini finds URL + score
        2. Playwright visits the URL to verify it's the right movie
        3. If validation passes, return result (with Playwright's score if available)
        4. If validation fails or Gemini fails, fall back to Playwright search

        Args:
            title: Movie title
            year: Release year
            director: Optional director for disambiguation
            use_fallback: Whether to try Playwright if Gemini fails
            original_language: ISO 639-1 language code (e.g. 'es', 'fr')
            original_title: Original-language title from TMDB (if different from title)

        Returns:
            Dict with 'url' and 'score', or None
        """
        self.stats['total_requests'] += 1
        cache_key = f"{title}_{year}"

        # Try Gemini first
        result = self.gemini_finder.find_rt_score(title, year, director, original_language=original_language, original_title=original_title)

        if result is not None:
            # Check if already Playwright-validated (cached validation)
            cached = self.gemini_finder.cache.get(cache_key, {})
            if isinstance(cached, dict) and cached.get('_playwright_validated'):
                self.stats['gemini_resolved'] += 1
                return result

            # Validate with Playwright
            validated = self._validate_with_playwright(result, title, year,
                                                       original_language=original_language,
                                                       original_title=original_title)
            if validated:
                # Mark as validated in cache
                if cache_key in self.gemini_finder.cache:
                    self.gemini_finder.cache[cache_key]['_playwright_validated'] = True
                    # Update score if Playwright found one
                    if validated.get('score'):
                        self.gemini_finder.cache[cache_key]['score'] = validated['score']
                    self.gemini_finder._save_cache()
                self.stats['gemini_resolved'] += 1
                return validated
            else:
                # Validation failed — clear bad entry from cache
                logger.warning(f"Clearing bad Gemini cache entry for '{title}' ({year})")
                if cache_key in self.gemini_finder.cache:
                    del self.gemini_finder.cache[cache_key]
                    self.gemini_finder._save_cache()
                # Fall through to Playwright fallback

        # Check if this was a cache hit that returned None (no RT page exists)
        if cache_key in self.gemini_finder.cache:
            cached = self.gemini_finder.cache[cache_key]
            if isinstance(cached, dict) and cached.get('url') is None:
                return None

        # Gemini failed or was rejected — try Playwright fallback if enabled
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
    def scrape_rt_score(self, title: str, year: int, director: str = None) -> Optional[Dict[str, str]]:
        """Compatibility wrapper matching RTScraperPlaywright interface."""
        return self.find_rt_score(title, year, director=director)

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


# =============================================================================
# VOD Date Finder
# =============================================================================

class GeminiVODDateFinder(GeminiFinderBase):
    """
    Finds VOD (digital purchase/rental) release dates using Gemini with Google Search grounding.

    Used during daily pre-order resolution to find when a pre-ordered movie
    will actually become available for digital purchase/rental.

    Usage:
        finder = GeminiVODDateFinder()
        result = finder.find_vod_date("I Can Only Imagine 2", 2026)
        # Returns: '2026-04-15' or None
    """

    _finder_name = 'VOD'

    def __init__(self, cache_file: str = 'cache/vod_date_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'invalid_dates': 0, 'future_dates': 0, 'past_dates': 0}

    def find_vod_date(
        self,
        title: str,
        year: int,
        provider: str = None
    ) -> Optional[str]:
        """
        Find VOD/digital release date for a movie using Gemini.

        Args:
            title: Movie title
            year: Release year
            provider: Optional provider name for context (e.g., "Fandango At Home")

        Returns:
            Date string in YYYY-MM-DD format, or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache (14-day TTL — dates get announced over time)
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict):
                scraped_at = cached_data.get('scraped_at', '')
                if scraped_at:
                    try:
                        from datetime import datetime, timedelta
                        cached_dt = datetime.fromisoformat(scraped_at)
                        if datetime.now() - cached_dt < timedelta(days=14):
                            vod_date = cached_data.get('vod_date')
                            if vod_date:
                                self.stats['cache_hits'] += 1
                                logger.debug(f"VOD date cache hit for {title} ({year}): {vod_date}")
                                return vod_date
                    except (ValueError, TypeError):
                        pass

        # Initialize Gemini
        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # Build context
        context = f'"{title}" ({year})'
        if provider:
            context += f" (currently listed on {provider})"

        prompt = f"""Find the VOD (Video on Demand) digital release date for the movie {context}.

I need to know when this movie becomes available for digital purchase or rental (NOT theatrical, NOT DVD/Blu-ray).

Requirements:
- Search for the official digital/VOD release date in the United States
- Return the date in format: DATE: YYYY-MM-DD
- If the movie is currently only available for pre-order but not yet released digitally, respond with: PREORDER_ONLY
- If no VOD date information can be found, respond with: NOT_FOUND
- Only return dates you are confident about from reliable sources

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
                logger.error(f"All retries failed for VOD date {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            logger.debug(f"Gemini VOD response for {title}: {result_text}")

            # Handle explicit responses
            if 'NOT_FOUND' in result_text:
                logger.info(f"No VOD date found for {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            if 'PREORDER_ONLY' in result_text:
                logger.info(f"Pre-order only confirmed for {title} ({year}), no date yet")
                self.stats['gemini_failures'] += 1
                return None

            # Extract date from response
            date_match = re.search(r'DATE:\s*(\d{4}-\d{2}-\d{2})', result_text)
            if not date_match:
                # Try broader date pattern
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', result_text)

            if date_match:
                vod_date = date_match.group(1)

                # Validate it's a real date
                try:
                    from datetime import datetime
                    parsed = datetime.strptime(vod_date, '%Y-%m-%d')

                    # Track future vs past
                    if parsed > datetime.now():
                        self.stats['future_dates'] += 1
                    else:
                        self.stats['past_dates'] += 1

                    logger.info(f"Found VOD date for {title} ({year}): {vod_date}")

                    # Cache the result
                    self.cache[cache_key] = {
                        'vod_date': vod_date,
                        'title': title,
                        'year': year,
                        'source': 'gemini',
                        'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                        'raw_response': result_text[:500]
                    }
                    self._save_cache()
                    self.stats['gemini_successes'] += 1
                    return vod_date

                except ValueError:
                    logger.warning(f"Invalid date format for {title} ({year}): {vod_date}")
                    self.stats['invalid_dates'] += 1
                    self.stats['gemini_failures'] += 1
                    return None
            else:
                logger.warning(f"No date found in VOD response for {title} ({year}): {result_text[:200]}")
                self.stats['gemini_failures'] += 1
                return None

        except Exception as e:
            logger.error(f"Gemini VOD date API error for {title} ({year}): {e}")
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


# =============================================================================
# Pull Quote Finder
# =============================================================================

class GeminiPullQuoteFinder(GeminiFinderBase):
    """
    Finds real critic quotes and Letterboxd reviews using Gemini with Google Search grounding.

    Returns 5-10 quotes per movie for curator selection. All quotes default to
    unselected — nothing displays on the site until manually approved.

    Usage:
        finder = GeminiPullQuoteFinder()
        quotes = finder.find_pull_quotes("The Brutalist", 2024, director="Brady Corbet")
        # Returns: list of quote dicts, or empty list
    """

    _finder_name = 'PullQuotes'

    def __init__(self, cache_file: str = 'cache/pull_quotes_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'quotes_found': 0, 'insufficient_quotes': 0}

    def _parse_quotes(self, text: str, source_type: str = 'critic') -> list:
        """Parse quote lines from Gemini response text."""
        quotes = []
        # Match: QUOTE: "text" -- Critic Name, Publication
        pattern = r'QUOTE:\s*["\u201c]([^"\u201d]+)["\u201d]\s*[-\u2014]{1,2}\s*([^,\n]+),\s*([^\n]+)'
        for match in re.finditer(pattern, text):
            quote_text = match.group(1).strip()
            critic = match.group(2).strip()
            outlet = match.group(3).strip()
            # Skip if quote is too short or looks like an error
            if len(quote_text) < 10:
                continue
            quotes.append({
                'text': quote_text,
                'critic': critic,
                'outlet': outlet,
                'source': source_type,
                'selected': False,
                'added_at': time.strftime('%Y-%m-%dT%H:%M:%S')
            })
        return quotes

    def find_pull_quotes(
        self,
        title: str,
        year: int,
        director: str = None,
        num_quotes: int = 8
    ) -> list:
        """
        Find pull quotes for a movie using Gemini with Google Search grounding.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for context
            num_quotes: Number of quotes to request (default 8)

        Returns:
            List of quote dicts with keys: text, critic, outlet, source, selected, added_at
            Returns empty list if not enough quotes found.
        """
        cache_key = f"{title}_{year}"

        # Check cache
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict):
                scraped_at = cached_data.get('scraped_at', '')
                if scraped_at:
                    try:
                        from datetime import datetime, timedelta
                        cached_dt = datetime.fromisoformat(scraped_at)
                        if datetime.now() - cached_dt < timedelta(days=self.cache_ttl_days):
                            cached_quotes = cached_data.get('quotes', [])
                            if cached_quotes:
                                self.stats['cache_hits'] += 1
                                logger.debug(f"Pull quotes cache hit for {title} ({year}): {len(cached_quotes)} quotes")
                                return cached_quotes
                    except (ValueError, TypeError):
                        pass

        # Initialize Gemini
        if not self._init_gemini():
            return []

        self.stats['gemini_attempts'] += 1

        # Build context
        context = f'"{title}" ({year})'
        if director:
            context += f" directed by {director}"

        # --- Critic quotes prompt ---
        critic_prompt = f"""Find {num_quotes} real critic pull quotes for the movie {context}.

Requirements:
- Return ONLY real quotes from published professional reviews
- Each quote must include: the exact quote text, critic name, and publication name
- Prefer short, punchy quotes (1-2 sentences, under 30 words ideal)
- Include a mix of major outlets (NYT, Variety, Hollywood Reporter, The Guardian) and notable indie outlets (IndieWire, The Playlist, RogerEbert.com)
- Do NOT fabricate or paraphrase quotes - only real published quotes
- If fewer than 3 real quotes exist, respond with: INSUFFICIENT_QUOTES

Format each quote as:
QUOTE: "exact quote text" -- Critic Name, Publication Name

Response:"""

        all_quotes = []

        # Fetch critic quotes
        def _fetch_critic_quotes():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=critic_prompt,
                config=api_config
            )
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_fetch_critic_quotes)

            if result_text and 'INSUFFICIENT_QUOTES' not in result_text:
                critic_quotes = self._parse_quotes(result_text, source_type='critic')
                all_quotes.extend(critic_quotes)
                logger.info(f"Found {len(critic_quotes)} critic quotes for {title} ({year})")
            else:
                logger.info(f"Insufficient critic quotes for {title} ({year})")
                self.stats['insufficient_quotes'] += 1

        except Exception as e:
            logger.warning(f"Error fetching critic quotes for {title} ({year}): {e}")

        # --- Letterboxd quotes prompt ---
        letterboxd_prompt = f"""Find 3 notable Letterboxd user reviews for the movie {context}.

Requirements:
- Only reviews with significant engagement (popular/liked reviews)
- Prefer witty, insightful, or unusually well-written reviews
- Include the Letterboxd username (with @ prefix)
- Do NOT fabricate reviews - only real Letterboxd reviews
- If no notable reviews exist, respond with: NO_REVIEWS

Format each as:
QUOTE: "review text" -- @username, Letterboxd

Response:"""

        def _fetch_letterboxd_quotes():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=letterboxd_prompt,
                config=api_config
            )
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            lb_text = self._retry_with_backoff(_fetch_letterboxd_quotes)

            if lb_text and 'NO_REVIEWS' not in lb_text:
                lb_quotes = self._parse_quotes(lb_text, source_type='letterboxd')
                all_quotes.extend(lb_quotes)
                logger.info(f"Found {len(lb_quotes)} Letterboxd quotes for {title} ({year})")

        except Exception as e:
            logger.warning(f"Error fetching Letterboxd quotes for {title} ({year}): {e}")

        # Cache results (even if empty, to avoid re-fetching)
        if all_quotes:
            self.stats['gemini_successes'] += 1
            self.stats['quotes_found'] += len(all_quotes)
        else:
            self.stats['gemini_failures'] += 1

        self.cache[cache_key] = {
            'quotes': all_quotes,
            'title': title,
            'year': year,
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
        }
        self._save_cache()

        return all_quotes


class GeminiQuoteExtractor(GeminiFinderBase):
    """
    Extracts the punchiest pull-quote line from Letterboxd reviews.

    NOT a generator — Gemini selects from existing text.
    Every extraction is verified as a verbatim substring of the original.
    """

    _finder_name = 'QuoteExtractor'

    def __init__(self):
        super().__init__(cache_file='cache/quote_extractions_cache.json')

    def _get_extra_stats(self) -> Dict[str, int]:
        return {
            'reviews_processed': 0,
            'quotes_extracted': 0,
            'quotes_skipped': 0,
            'verification_failures': 0
        }

    def _verify_verbatim(self, extracted: str, original: str) -> bool:
        """Verify extracted quote exists verbatim in original review text."""
        # Normalize whitespace for comparison (reviews may have odd spacing)
        norm_extracted = ' '.join(extracted.split()).strip()
        norm_original = ' '.join(original.split()).strip()
        return norm_extracted.lower() in norm_original.lower()

    def _build_prompt(self, reviews: list) -> str:
        """Build the extraction prompt for a batch of reviews."""
        review_block = []
        for i, review in enumerate(reviews):
            text = review.get('text', '').strip()
            word_count = len(text.split())
            review_block.append(f"[{i+1}] ({word_count} words) \"{text}\"")

        reviews_text = '\n\n'.join(review_block)

        return f"""You are extracting pull quotes from Letterboxd movie reviews.

For each numbered review below, extract the SINGLE most quotable sentence or phrase.

RULES:
- Copy the text EXACTLY as written. Do not change, rephrase, or "improve" ANY words.
- Maximum 50 words for the extracted quote.
- If the review is already short (under 50 words) and punchy, return it exactly as-is.
- If the review has no quotable material (boring, generic, or incoherent), return SKIP.
- Look for: wit, humor, sharp observations, vivid imagery, memorable one-liners, personality.
- Avoid: generic praise ("great movie"), vague feelings ("it made me feel things"), plot summaries.

FORMAT (one per line):
[1] "exact extracted text here"
[2] SKIP
[3] "exact extracted text here"

REVIEWS:
{reviews_text}"""

    def _parse_response(self, response_text: str, reviews: list) -> Dict[int, str]:
        """Parse Gemini response into index -> extracted quote mapping."""
        results = {}
        pattern = r'\[(\d+)\]\s*(?:"([^"]+)"|[\u201c]([^\u201d]+)[\u201d]|SKIP)'

        for match in re.finditer(pattern, response_text):
            idx = int(match.group(1)) - 1  # Convert to 0-based
            quote = match.group(2) or match.group(3)  # ASCII or smart quotes

            if idx < 0 or idx >= len(reviews):
                continue

            if quote:  # Not SKIP
                results[idx] = quote.strip()
            # SKIP entries are intentionally omitted

        return results

    def extract_quotes(self, reviews: list, title: str = '', year: int = 0) -> list:
        """
        Extract punchy pull quotes from a list of Letterboxd reviews.

        Args:
            reviews: List of review dicts (from letterboxd_reviews_cache.json)
            title: Movie title (for cache key)
            year: Movie year (for cache key)

        Returns:
            The same list with 'pull_quote' field added to each review.
            pull_quote = extracted line, or None if skipped/failed.
        """
        if not reviews:
            return reviews

        # Check cache
        cache_key = f"{title}_{year}" if title else None
        if cache_key and cache_key in self.cache:
            cached = self.cache[cache_key]
            cached_at = cached.get('extracted_at', '')
            # Check TTL
            if cached_at:
                try:
                    from datetime import datetime, timedelta
                    cached_time = datetime.fromisoformat(cached_at)
                    if datetime.now() - cached_time < timedelta(days=self.cache_ttl_days):
                        logger.info(f"Using cached extractions for {title} ({year})")
                        self.stats['cache_hits'] += 1
                        return cached.get('reviews', reviews)
                except (ValueError, TypeError):
                    pass

        if not self._init_gemini():
            logger.error("Cannot extract quotes - Gemini not available")
            return reviews

        # Process in batches of 10 (to stay within prompt limits)
        batch_size = 10
        all_results = {}

        for batch_start in range(0, len(reviews), batch_size):
            batch = reviews[batch_start:batch_start + batch_size]
            prompt = self._build_prompt(batch)

            self.stats['gemini_attempts'] += 1
            self._enforce_rate_limit()

            def _make_request():
                # No grounding needed — we're analyzing provided text, not searching
                config = self.types.GenerateContentConfig()
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                return response.text.strip()

            response_text = self._retry_with_backoff(_make_request)

            if not response_text:
                self.stats['gemini_failures'] += 1
                logger.warning(f"No response from Gemini for batch starting at {batch_start}")
                continue

            self.stats['gemini_successes'] += 1
            batch_results = self._parse_response(response_text, batch)

            # Map batch indices back to global indices
            for batch_idx, quote in batch_results.items():
                all_results[batch_start + batch_idx] = quote

        # Apply results to reviews with verbatim verification
        for i, review in enumerate(reviews):
            self.stats['reviews_processed'] += 1
            original_text = review.get('text', '')
            word_count = len(original_text.split())

            if i in all_results:
                extracted = all_results[i]

                # Verify verbatim
                if self._verify_verbatim(extracted, original_text):
                    review['pull_quote'] = extracted
                    self.stats['quotes_extracted'] += 1
                    logger.debug(f"  Extracted: \"{extracted[:60]}...\"")
                else:
                    # Verification failed — Gemini modified the text
                    self.stats['verification_failures'] += 1
                    logger.warning(
                        f"  Verification FAILED for review {i+1} by {review.get('critic', '?')}: "
                        f"extracted text not found verbatim in original"
                    )
                    # Fallback: use full text if short, otherwise None
                    if word_count <= 50:
                        review['pull_quote'] = original_text
                    else:
                        review['pull_quote'] = None
            else:
                # Gemini returned SKIP or didn't include this review
                self.stats['quotes_skipped'] += 1
                # For very short reviews, keep them anyway — they're already punchy
                if word_count <= 20:
                    review['pull_quote'] = original_text
                else:
                    review['pull_quote'] = None

        # Cache results
        if cache_key:
            from datetime import datetime
            self.cache[cache_key] = {
                'reviews': reviews,
                'title': title,
                'year': year,
                'extracted_at': datetime.now().isoformat()
            }
            self._save_cache()

        extracted_count = sum(1 for r in reviews if r.get('pull_quote'))
        logger.info(
            f"Quote extraction for {title}: {extracted_count}/{len(reviews)} reviews → pull quotes"
        )

        return reviews


# =============================================================================
# IMDb Rating Finder (Gemini + Google Search grounding)
# =============================================================================

class GeminiIMDbFinder(GeminiFinderBase):
    """
    Finds IMDb ratings using Gemini API with Google Search grounding.

    Used as a fallback when the IMDb bulk dataset and OMDb API both miss
    a movie (typically very new or low-vote titles). Gemini reads the rating
    from Google's Knowledge Panel, which updates faster than the daily dataset.

    Usage:
        finder = GeminiIMDbFinder()
        rating = finder.find_rating("Color Theories by Julio Torres", 2026, imdb_id="tt38641367")
        # Returns: "6.9" or None
    """

    _finder_name = 'IMDb'

    def __init__(self, cache_file: str = 'cache/imdb_gemini_cache.json'):
        super().__init__(cache_file=cache_file)

    def find_rating(self, title: str, year: int, imdb_id: str = None) -> Optional[str]:
        """Find IMDb rating via Gemini + Google Search grounding.

        Args:
            title: Movie title
            year: Release year
            imdb_id: Optional IMDb ID for disambiguation

        Returns:
            Rating string (e.g., "7.4") or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if isinstance(cached, dict) and cached.get('rating'):
                self.stats['cache_hits'] += 1
                logger.debug(f"IMDb Gemini cache hit for {title} ({year})")
                return cached['rating']

        # Initialize Gemini if needed
        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        id_hint = f" (IMDb ID: {imdb_id})" if imdb_id else ""
        prompt = f"""What is the IMDb user rating for the movie "{title}" ({year}){id_hint}?

Requirements:
- Return ONLY the numeric rating on a 1-10 scale (e.g. "7.4")
- The rating must be the IMDb user rating for this specific movie from {year}
- If the movie has no IMDb rating yet or you cannot find it, respond with exactly: NOT_FOUND

Response:"""

        def _query():
            self._enforce_rate_limit()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    tools=[self.grounding_tool],
                    temperature=0.0
                )
            )
            return response.text if response.text else None

        try:
            text = self._retry_with_backoff(_query)
            rating = self._parse_rating(text)

            if rating:
                logger.info(f"Gemini found IMDb rating for {title} ({year}): {rating}")
                self.cache[cache_key] = {
                    'rating': rating,
                    'title': title,
                    'year': year,
                    'imdb_id': imdb_id,
                    'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'source': 'gemini'
                }
                self._save_cache()
                self.stats['gemini_successes'] += 1
                return rating
            else:
                logger.debug(f"Gemini: no IMDb rating found for {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

        except Exception as e:
            logger.error(f"Gemini IMDb API error for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1
            return None

    def _parse_rating(self, text: str) -> Optional[str]:
        """Extract numeric rating from Gemini response."""
        if not text or 'NOT_FOUND' in text:
            return None
        # Match ratings like "7.4", "6.9", "10"
        match = re.search(r'\b(\d{1,2}\.?\d?)\b', text.strip())
        if match:
            val = float(match.group(1))
            if 1.0 <= val <= 10.0:
                return str(val)
        return None


# =============================================================================
# Watch Link Finder (Gemini + Google Search grounding)
# =============================================================================

class GeminiWatchLinkFinder(GeminiFinderBase):
    """
    Finds direct watch/streaming URLs using Gemini API with Google Search grounding.

    Tested: Netflix (3/3), Paramount+ (1/1). Disney+, Hulu, Amazon: 0 hits
    (not well-indexed by Google).

    Usage:
        finder = GeminiWatchLinkFinder()
        url = finder.find_watch_link("The Brutalist", 2024, "Netflix")
        # Returns: "https://www.netflix.com/title/81234567" or None
    """

    _finder_name = 'WatchLink'

    # Only try Gemini for platforms where Google indexes their pages well.
    # Tested hit rates: Netflix 7/7, Paramount+ 2/3, Film Movement Plus 1/1, Angel Studios 1/1.
    # Disney+, Hulu, Amazon, Starz, Criterion, Peacock, Discovery+: 0% — don't waste API calls.
    SUPPORTED_SERVICES = {
        'Netflix', 'Netflix Standard with Ads',
        'Paramount+', 'Paramount Plus', 'Paramount Plus Premium',
        'Paramount Plus Essential', 'Paramount Plus Apple TV Channel',
        'Paramount+ Amazon Channel',
        'Film Movement Plus', 'Film Movement Plus Amazon Channel',
        'Angel Studios',
        'MUBI',  # Publicly indexed site, likely findable
    }

    # Map service names to their expected URL domains
    SERVICE_DOMAINS = {
        'Netflix': 'netflix.com',
        'Netflix Standard with Ads': 'netflix.com',
        'Paramount+': 'paramountplus.com',
        'Paramount Plus': 'paramountplus.com',
        'Paramount Plus Premium': 'paramountplus.com',
        'Paramount Plus Essential': 'paramountplus.com',
        'Paramount Plus Apple TV Channel': 'paramountplus.com',
        'Paramount+ Amazon Channel': 'paramountplus.com',
        'Angel Studios': 'angel.com',
        'Film Movement Plus': 'filmmovementplus.com',
        'Film Movement Plus Amazon Channel': 'filmmovementplus.com',
        'MUBI': 'mubi.com',
    }

    # Normalize service variants to a canonical name for the prompt
    SERVICE_CANONICAL = {
        'Netflix Standard with Ads': 'Netflix',
        'Paramount Plus Premium': 'Paramount+',
        'Paramount Plus Essential': 'Paramount+',
        'Paramount Plus Apple TV Channel': 'Paramount+',
        'Paramount+ Amazon Channel': 'Paramount+',
        'Paramount Plus': 'Paramount+',
        'Film Movement Plus Amazon Channel': 'Film Movement Plus',
    }

    def __init__(self, cache_file: str = 'cache/gemini_watch_links_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {
            'invalid_urls': 0,
            'domain_mismatches': 0,
        }

    def _extract_url(self, text: str, expected_domain: str) -> Optional[str]:
        """Extract a URL from Gemini response matching the expected domain."""
        if not text or not expected_domain:
            return None
        pattern = rf'https?://[^\s<>"\']*{re.escape(expected_domain)}[^\s<>"\']*'
        match = re.search(pattern, text)
        if match:
            url = match.group(0).rstrip('.,;:)]}')
            return url
        return None

    def find_watch_link(self, title: str, year: int, service: str,
                        director: str = None) -> Optional[str]:
        """Find watch URL for a movie/show on a specific streaming service.

        Args:
            title: Movie or show title
            year: Release year
            service: Service name (e.g., "Netflix", "Paramount+")
            director: Optional director for disambiguation

        Returns:
            URL string or None
        """
        # Only try platforms where Gemini actually works
        if service not in self.SUPPORTED_SERVICES:
            return None

        expected_domain = self.SERVICE_DOMAINS.get(service)
        if not expected_domain:
            return None

        # Normalize service name for the prompt
        canonical = self.SERVICE_CANONICAL.get(service, service)

        # Cache key includes service
        cache_key = f"{title}_{year}_{canonical}"

        # Check cache
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if isinstance(cached, dict):
                scraped_at = cached.get('scraped_at', '')
                if scraped_at:
                    try:
                        from datetime import datetime, timedelta
                        cached_dt = datetime.fromisoformat(scraped_at)
                        if datetime.now() - cached_dt < timedelta(days=self.cache_ttl_days):
                            self.stats['cache_hits'] += 1
                            return cached.get('url')  # May be None (negative cache)
                    except (ValueError, TypeError):
                        pass

        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # Build prompt
        context = f'"{title}" ({year})'
        if director:
            context += f" directed by {director}"

        prompt = f"""Search for where to watch {context} on {canonical}.

I need the direct URL on {expected_domain} where this title can be watched or viewed.

Rules:
- Return ONLY the URL, nothing else
- The URL must contain "{expected_domain}"
- If this title is not available on {canonical}, respond with exactly: NOT_AVAILABLE
- If you cannot find a specific {expected_domain} URL, respond with exactly: NOT_FOUND

URL:"""

        def _call():
            self._enforce_rate_limit()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    tools=[self.grounding_tool],
                    temperature=0.0
                )
            )
            return response.text.strip() if response.text else None

        try:
            result_text = self._retry_with_backoff(_call)
        except Exception as e:
            logger.error(f"WatchLink API error for {title} on {canonical}: {e}")
            self.stats['gemini_failures'] += 1
            return None

        if result_text is None:
            self.stats['gemini_failures'] += 1
            return None

        logger.debug(f"WatchLink response for {title} on {canonical}: {result_text}")

        # NOT_AVAILABLE = confirmed not on platform → cache negative
        if 'NOT_AVAILABLE' in result_text:
            logger.info(f"WatchLink: {title} confirmed not on {canonical}")
            self.cache[cache_key] = {
                'url': None, 'service': canonical, 'title': title,
                'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'result': 'not_available'
            }
            self._save_cache()
            self.stats['gemini_successes'] += 1
            return None

        # NOT_FOUND = couldn't find it → don't cache (may succeed later)
        if 'NOT_FOUND' in result_text:
            logger.info(f"WatchLink: couldn't find {title} on {canonical}")
            self.stats['gemini_failures'] += 1
            return None

        # Extract URL
        url = self._extract_url(result_text, expected_domain)

        if not url:
            logger.warning(f"WatchLink: no valid URL in response for {title} on {canonical}: {result_text}")
            self.stats['invalid_urls'] += 1
            self.stats['gemini_failures'] += 1
            return None

        if expected_domain not in url.lower():
            logger.warning(f"WatchLink: domain mismatch for {title} on {canonical}: {url}")
            self.stats['domain_mismatches'] += 1
            self.stats['gemini_failures'] += 1
            return None

        # Success — cache and return
        logger.info(f"WatchLink: found {title} on {canonical}: {url}")
        self.cache[cache_key] = {
            'url': url, 'service': canonical, 'title': title,
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'result': 'found'
        }
        self._save_cache()
        self.stats['gemini_successes'] += 1
        return url


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
