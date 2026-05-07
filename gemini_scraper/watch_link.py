"""
Watch link finder — discovers direct streaming URLs via Gemini + Google Search grounding.

Tested: Netflix (3/3), Paramount+ (1/1). Disney+, Hulu, Amazon: 0 hits
(not well-indexed by Google).
"""

import re
import time
import logging
from typing import Optional, Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.watch_link')


class GeminiWatchLinkFinder(GeminiFinderBase):
    """
    Finds direct watch/streaming URLs using Gemini API with Google Search grounding.

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
            response = self._generate(
                prompt,
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
