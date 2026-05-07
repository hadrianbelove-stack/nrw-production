"""
Wikipedia URL finder via Gemini + Google Search grounding.

Used as step 2.5 in Wikipedia waterfall (after Wikidata, before REST API).
"""

import re
import time
import logging
from typing import Optional, Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.wikipedia')


class GeminiWikipediaFinder(GeminiFinderBase):
    """
    Finds Wikipedia URLs using Gemini API with Google Search grounding.

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
