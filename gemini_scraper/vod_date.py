"""
VOD (digital purchase/rental) release date finder via Gemini + Google Search grounding.

Used during daily pre-order resolution to find when a pre-ordered movie
will actually become available for digital purchase/rental.
"""

import re
import time
import logging
from typing import Optional, Dict, Any

from gemini_scraper.base import GeminiFinderBase
from utils.datetime_utils import is_cache_fresh

logger = logging.getLogger('gemini_scraper.vod_date')


class GeminiVODDateFinder(GeminiFinderBase):
    """
    Finds VOD (digital purchase/rental) release dates using Gemini with Google Search grounding.

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
                if scraped_at and is_cache_fresh(scraped_at, 14):
                    vod_date = cached_data.get('vod_date')
                    if vod_date:
                        self.stats['cache_hits'] += 1
                        logger.debug(f"VOD date cache hit for {title} ({year}): {vod_date}")
                        return vod_date

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
            response = self._generate(prompt, config=api_config)
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
                self.stats['preorder_detected'] = self.stats.get('preorder_detected', 0) + 1
                return 'PREORDER_ONLY'

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
