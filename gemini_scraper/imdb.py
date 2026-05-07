"""
IMDb rating finder via Gemini + Google Search grounding.

Fallback when the IMDb bulk dataset and OMDb API both miss a movie
(typically very new or low-vote titles). Gemini reads the rating
from Google's Knowledge Panel, which updates faster than the daily dataset.
"""

import re
import time
import logging
from typing import Optional, Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.imdb')


class GeminiIMDbFinder(GeminiFinderBase):
    """
    Finds IMDb ratings using Gemini API with Google Search grounding.

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
            response = self._generate(
                prompt,
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
