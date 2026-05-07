"""
YouTube trailer finder — Gemini + Playwright hybrid.

Classes: GeminiYouTubeFinder, HybridYouTubeFinder
Function: find_youtube_trailer()
"""

import re
import logging
from typing import Optional, Dict, Any

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.youtube')


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
