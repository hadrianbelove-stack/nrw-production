#!/usr/bin/env python3
"""
JustWatch API Client - Fetch watch links from JustWatch's GraphQL API.

This module provides reliable watch links for movies by querying JustWatch,
which aggregates streaming availability across all major platforms.

Returns direct deep links to:
- Streaming services (Netflix, HBO Max, Prime Video, Disney+, etc.)
- Rent options (Amazon, Apple TV, YouTube, etc.)
- Buy options (Amazon, Apple TV, etc.)

Usage:
    from justwatch_client import JustWatchClient

    client = JustWatchClient()
    links = client.get_watch_links("Conclave", 2024)
    # Returns: {'streaming': {...}, 'vod': {...}}
"""

import requests
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime


class JustWatchClient:
    """
    Client for JustWatch's GraphQL API.

    JustWatch provides streaming availability data for movies and TV shows
    across 200+ services in 50+ countries.
    """

    API_URL = "https://apis.justwatch.com/graphql"

    # Service priority for selecting best option per category
    STREAMING_PRIORITY = [
        # Tier 1: Major paid subscriptions
        'Netflix', 'Amazon Prime Video', 'Disney Plus', 'HBO Max', 'Max',
        'Hulu', 'Apple TV Plus', 'Paramount Plus', 'Peacock',
        # Tier 2: Free ad-supported services
        'Tubi', 'Tubi TV', 'Pluto TV', 'Plex', 'The Roku Channel',
        'Crackle', 'Vudu Free', 'Fawesome',
        # Tier 3: Library-based free services
        'Kanopy', 'Hoopla',
        # Tier 4: Niche paid subscriptions
        'MUBI', 'Criterion Channel', 'Shudder', 'AMC Plus', 'Bloodstream'
    ]

    VOD_PRIORITY = [
        'Amazon Video', 'Apple TV', 'YouTube', 'Fandango At Home',
        'Microsoft Store'
    ]

    def __init__(self, country: str = "US", logger: Optional[logging.Logger] = None):
        """
        Initialize JustWatch client.

        Args:
            country: ISO country code (default: US)
            logger: Optional logger instance
        """
        self.country = country
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

        # Stats tracking
        self.stats = {
            'queries': 0,
            'successes': 0,
            'failures': 0,
            'cache_hits': 0
        }

        # Simple in-memory cache
        self._cache: Dict[str, Dict] = {}

    def search_movie(self, title: str, year: Optional[int] = None, content_type: str = 'movie') -> Optional[Dict]:
        """
        Search for a movie or TV show by title and optional year.

        Args:
            title: Movie title
            year: Release year (helps disambiguate)
            content_type: 'movie' or 'tv' — determines JustWatch objectTypes filter

        Returns:
            Movie data with offers, or None if not found
        """
        # Normalize year to int (handle string input from enrichment pipeline)
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        object_type = 'SHOW' if content_type == 'tv' else 'MOVIE'
        cache_key = f"{title}_{year or 'any'}_{object_type}"
        if cache_key in self._cache:
            self.stats['cache_hits'] += 1
            return self._cache[cache_key]

        query = f'''
        query SearchMovies($country: Country!, $searchQuery: String!, $first: Int!) {{
          popularTitles(
            country: $country
            first: $first
            filter: {{
              searchQuery: $searchQuery
              objectTypes: [{object_type}]
            }}
          ) {{
            edges {{
              node {{
                id
                objectId
                objectType
                content(country: $country, language: "en") {{
                  title
                  originalReleaseYear
                  fullPath
                }}
                offers(country: $country, platform: WEB) {{
                  monetizationType
                  presentationType
                  retailPrice(language: "en")
                  currency
                  standardWebURL
                  package {{
                    clearName
                    technicalName
                  }}
                }}
              }}
            }}
          }}
        }}
        '''

        variables = {
            'country': self.country,
            'searchQuery': title,
            'first': 10  # Get top 10 results for better matching
        }

        self.stats['queries'] += 1

        try:
            response = self.session.post(
                self.API_URL,
                json={'query': query, 'variables': variables},
                timeout=15
            )
            response.raise_for_status()
            data = response.json()

            if 'errors' in data:
                self.logger.warning(f"JustWatch API errors: {data['errors']}")
                self.stats['failures'] += 1
                return None

            edges = data.get('data', {}).get('popularTitles', {}).get('edges', [])

            if not edges:
                self.logger.debug(f"No results for '{title}'")
                self.stats['failures'] += 1
                return None

            # Find best match: prefer title match + year over year alone.
            # JustWatch search already ranks by relevance, so result #1 with a
            # matching title is almost always correct. Prioritizing year alone
            # can pick a completely wrong movie that happens to share the year.
            title_lower = title.lower()
            best_match = None

            # Pass 1: exact title + exact year (strongest signal)
            for edge in edges:
                node = edge['node']
                content = node.get('content', {})
                if content.get('title', '').lower() == title_lower and year and content.get('originalReleaseYear') == year:
                    best_match = node
                    break

            # Pass 2: exact title + close year (within 1 year — common for foreign films)
            if not best_match:
                for edge in edges:
                    node = edge['node']
                    content = node.get('content', {})
                    node_year = content.get('originalReleaseYear')
                    if content.get('title', '').lower() == title_lower and year and node_year and abs(node_year - year) <= 1:
                        best_match = node
                        break

            # Pass 3: exact title, any year
            if not best_match:
                for edge in edges:
                    node = edge['node']
                    content = node.get('content', {})
                    if content.get('title', '').lower() == title_lower:
                        best_match = node
                        break

            # Pass 4: close year match without title check (original fallback)
            if not best_match and year:
                for edge in edges:
                    node = edge['node']
                    content = node.get('content', {})
                    node_year = content.get('originalReleaseYear')
                    if node_year and abs(node_year - year) <= 1:
                        best_match = node
                        break

            # Pass 5: fall back to first result
            if not best_match:
                best_match = edges[0]['node']

            self.stats['successes'] += 1
            self._cache[cache_key] = best_match
            return best_match

        except requests.RequestException as e:
            self.logger.error(f"JustWatch API request failed: {e}")
            self.stats['failures'] += 1
            return None
        except Exception as e:
            self.logger.error(f"JustWatch API error: {e}")
            self.stats['failures'] += 1
            return None

    def get_watch_links(
        self,
        title: str,
        year: Optional[int] = None,
        affiliate_tag: Optional[str] = None,
        excluded_services: Optional[List[str]] = None,
        content_type: str = 'movie'
    ) -> Dict[str, Any]:
        """
        Get watch links in canonical NRW schema.

        Args:
            title: Movie title
            year: Release year
            affiliate_tag: Optional Amazon affiliate tag to append
            excluded_services: Optional list of service names to exclude (e.g. ['Philo', 'fuboTV'])
            content_type: 'movie' or 'tv' — determines JustWatch objectTypes filter

        Returns:
            Dict with 'streaming' and 'vod' categories:
            {
                'streaming': {'service': 'Netflix', 'link': 'https://...'},
                'vod': {'service': 'Amazon Video', 'link': 'https://...', 'price': '$4.99'}
            }
        """
        movie = self.search_movie(title, year, content_type=content_type)

        if not movie:
            return {}

        offers = movie.get('offers', [])

        if not offers:
            self.logger.debug(f"No offers for '{title}'")
            return {}

        # Build lowercase exclusion set for fast matching
        excluded_lower = [s.lower() for s in (excluded_services or [])]

        result = {}

        # Group offers by monetization type
        streaming_offers = []
        rent_offers = []
        buy_offers = []

        for offer in offers:
            mtype = offer.get('monetizationType')
            url = offer.get('standardWebURL')
            service = offer.get('package', {}).get('clearName', '')
            price = offer.get('retailPrice')

            if not url or not service:
                continue

            # Skip excluded services (e.g. Philo, fuboTV)
            if any(excluded in service.lower() for excluded in excluded_lower):
                self.logger.debug(f"Skipping excluded service '{service}' for '{title}'")
                continue

            # Skip YouTube search results (not real links)
            if 'youtube.com/results' in url:
                continue

            offer_data = {
                'service': service,
                'link': url,
                'price': price
            }

            if mtype in ('FLATRATE', 'ADS', 'FREE'):
                streaming_offers.append(offer_data)
            elif mtype == 'RENT':
                rent_offers.append(offer_data)
            elif mtype == 'BUY':
                buy_offers.append(offer_data)

        # Select best streaming option
        if streaming_offers:
            best_streaming = self._select_best_offer(streaming_offers, self.STREAMING_PRIORITY)
            if best_streaming:
                result['streaming'] = {
                    'service': best_streaming['service'],
                    'link': best_streaming['link']
                }

        # Select VOD options — return both Amazon and Apple TV when available
        vod_offers = rent_offers + buy_offers
        if vod_offers:
            vod_entries = self._select_vod_offers(vod_offers, affiliate_tag)
            if vod_entries:
                result['vod'] = vod_entries

        return result

    def verify_availability(
        self,
        title: str,
        year: Optional[int] = None,
        excluded_services: Optional[List[str]] = None,
        affiliate_tag: Optional[str] = None,
        content_type: str = 'movie'
    ) -> Optional[Dict[str, Any]]:
        """
        Verify a movie's availability for the discovery phase.

        Called ONLY for movies TMDB flags as having providers (~1-10/day).
        Returns structured verification data including match confidence,
        offer breakdown, and ready-to-use watch_links.

        Returns:
            Dict with:
              'verified': True, False, or 'buy_only'
              'match_confidence': 'exact_year', 'close_year', 'title_only', 'first_result'
              'jw_title': str - title JustWatch matched
              'jw_year': int or None - year JustWatch matched
              'has_streaming': bool
              'has_rent': bool
              'has_buy': bool
              'provider_names': {'streaming': [...], 'rent': [...], 'buy': [...]}
              'watch_links': dict in NRW schema (ready to store)
            None if search fails entirely.
        """
        movie = self.search_movie(title, year, content_type=content_type)
        if not movie:
            return None

        content = movie.get('content', {})
        jw_title = content.get('title', '')
        jw_year = content.get('originalReleaseYear')

        # Determine match confidence
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        # Title similarity check: ensure we matched the right movie, not just
        # a movie with the right year. Without this, "Lupin" can match "Peaky
        # Blinders" if Peaky Blinders has the exact year we're looking for.
        titles_match = jw_title.lower() == title.lower()

        if titles_match and year and jw_year == year:
            confidence = 'exact_year'
        elif titles_match and year and jw_year and abs(jw_year - year) <= 1:
            confidence = 'close_year'
        elif titles_match:
            confidence = 'title_only'
        elif year and jw_year == year:
            # Year matches but title doesn't — risky, downgrade
            confidence = 'first_result'
            self.logger.warning(
                f"JustWatch title mismatch: searched '{title}' but matched "
                f"'{jw_title}' (year {jw_year}). Downgrading confidence."
            )
        elif year and jw_year and abs(jw_year - year) <= 1:
            confidence = 'first_result'
            self.logger.warning(
                f"JustWatch title mismatch: searched '{title}' but matched "
                f"'{jw_title}' (year {jw_year}). Downgrading confidence."
            )
        else:
            confidence = 'first_result'

        offers = movie.get('offers', [])
        excluded_lower = [s.lower() for s in (excluded_services or [])]

        # Group offers by monetization type
        streaming_offers = []
        rent_offers = []
        buy_offers = []
        streaming_names = []
        rent_names = []
        buy_names = []

        for offer in offers:
            mtype = offer.get('monetizationType')
            url = offer.get('standardWebURL')
            service = offer.get('package', {}).get('clearName', '')
            price = offer.get('retailPrice')

            if not url or not service:
                continue

            if any(excluded in service.lower() for excluded in excluded_lower):
                continue

            if 'youtube.com/results' in url:
                continue

            offer_data = {'service': service, 'link': url, 'price': price}

            if mtype in ('FLATRATE', 'ADS', 'FREE'):
                streaming_offers.append(offer_data)
                if service not in streaming_names:
                    streaming_names.append(service)
            elif mtype == 'RENT':
                rent_offers.append(offer_data)
                if service not in rent_names:
                    rent_names.append(service)
            elif mtype == 'BUY':
                buy_offers.append(offer_data)
                if service not in buy_names:
                    buy_names.append(service)

        has_streaming = bool(streaming_offers)
        has_rent = bool(rent_offers)
        has_buy = bool(buy_offers)

        # Determine verification status
        if has_rent or has_streaming:
            verified = True
        elif has_buy and not has_rent and not has_streaming:
            verified = 'buy_only'
        else:
            verified = False

        # Build watch_links in NRW schema (same format as get_watch_links)
        watch_links = {}
        if streaming_offers:
            best_streaming = self._select_best_offer(streaming_offers, self.STREAMING_PRIORITY)
            if best_streaming:
                watch_links['streaming'] = {
                    'service': best_streaming['service'],
                    'link': best_streaming['link']
                }

        vod_offers = rent_offers + buy_offers
        if vod_offers:
            vod_entries = self._select_vod_offers(vod_offers, affiliate_tag)
            if vod_entries:
                watch_links['vod'] = vod_entries

        return {
            'verified': verified,
            'match_confidence': confidence,
            'jw_title': jw_title,
            'jw_year': jw_year,
            'has_streaming': has_streaming,
            'has_rent': has_rent,
            'has_buy': has_buy,
            'provider_names': {
                'streaming': streaming_names,
                'rent': rent_names,
                'buy': buy_names
            },
            'watch_links': watch_links
        }

    def _select_vod_offers(
        self,
        offers: List[Dict],
        affiliate_tag: Optional[str] = None
    ) -> List[Dict]:
        """
        Select best VOD offers — one per service, deduplicated.
        Returns an array of offer dicts.
        """
        # Deduplicate: keep first (best) offer per service
        seen_services = set()
        unique_offers = []
        for offer in offers:
            svc = offer['service'].lower()
            if svc not in seen_services:
                seen_services.add(svc)
                unique_offers.append(offer)

        result = []
        for offer in unique_offers:
            link = offer['link']
            # Add affiliate tag to Amazon links
            if affiliate_tag and 'amazon' in link.lower():
                separator = '&' if '?' in link else '?'
                if 'tag=' not in link:
                    link = f"{link}{separator}tag={affiliate_tag}"
            entry = {'service': offer['service'], 'link': link}
            if offer.get('price'):
                entry['price'] = offer['price']
            result.append(entry)

        return result

    def _select_best_offer(
        self,
        offers: List[Dict],
        priority_list: List[str]
    ) -> Optional[Dict]:
        """
        Select best offer based on service priority.

        Args:
            offers: List of offer dicts
            priority_list: Ordered list of preferred services

        Returns:
            Best offer dict, or None
        """
        if not offers:
            return None

        # Try to find a priority service
        for priority_service in priority_list:
            for offer in offers:
                if priority_service.lower() in offer['service'].lower():
                    return offer

        # Fall back to first offer
        return offers[0]

    def get_stats(self) -> Dict[str, int]:
        """Get client statistics."""
        return self.stats.copy()


def test_client():
    """Test the JustWatch client."""
    client = JustWatchClient()

    test_movies = [
        ("Conclave", 2024),
        ("Heretic", 2024),
        ("The Brutalist", 2024),
        ("Anora", 2024),
    ]

    for title, year in test_movies:
        print(f"\n{'='*60}")
        print(f"Testing: {title} ({year})")
        print('='*60)

        links = client.get_watch_links(title, year, affiliate_tag="nrw-20")

        if links.get('streaming'):
            s = links['streaming']
            print(f"  STREAMING: {s['service']}")
            print(f"    {s['link'][:80]}...")

        if links.get('vod'):
            v = links['vod']
            price = v.get('price', 'N/A')
            print(f"  VOD: {v['service']} ({price})")
            print(f"    {v['link'][:80]}...")

        if not links:
            print("  No links found")

    print(f"\n\nStats: {client.get_stats()}")


if __name__ == "__main__":
    test_client()
