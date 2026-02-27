#!/usr/bin/env python3
"""
JustWatch API Client - Fetch watch links from JustWatch's GraphQL API.

This module provides reliable watch links for movies by querying JustWatch,
which aggregates streaming availability across all major platforms.

Returns direct deep links to:
- Streaming services (Netflix, HBO Max, Prime Video, Disney+, etc.)
- Rent options (Amazon, Apple TV, Google Play, etc.)
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
        'Crackle', 'Vudu Free',
        # Tier 3: Library-based free services
        'Kanopy', 'Hoopla',
        # Tier 4: Niche paid subscriptions
        'MUBI', 'Criterion Channel', 'Shudder', 'AMC Plus'
    ]

    VOD_PRIORITY = [
        'Amazon Video', 'Apple TV', 'Google Play Movies', 'Fandango At Home',
        'YouTube', 'Microsoft Store'
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

    def search_movie(self, title: str, year: Optional[int] = None) -> Optional[Dict]:
        """
        Search for a movie by title and optional year.

        Args:
            title: Movie title
            year: Release year (helps disambiguate)

        Returns:
            Movie data with offers, or None if not found
        """
        # Normalize year to int (handle string input from enrichment pipeline)
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        cache_key = f"{title}_{year or 'any'}"
        if cache_key in self._cache:
            self.stats['cache_hits'] += 1
            return self._cache[cache_key]

        query = '''
        query SearchMovies($country: Country!, $searchQuery: String!, $first: Int!) {
          popularTitles(
            country: $country
            first: $first
            filter: {
              searchQuery: $searchQuery
              objectTypes: [MOVIE]
            }
          ) {
            edges {
              node {
                id
                objectId
                objectType
                content(country: $country, language: "en") {
                  title
                  originalReleaseYear
                  fullPath
                }
                offers(country: $country, platform: WEB) {
                  monetizationType
                  presentationType
                  retailPrice(language: "en")
                  currency
                  standardWebURL
                  package {
                    clearName
                    technicalName
                  }
                }
              }
            }
          }
        }
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

            # Find best match by year if provided
            best_match = None
            for edge in edges:
                node = edge['node']
                content = node.get('content', {})
                node_title = content.get('title', '')
                node_year = content.get('originalReleaseYear')

                # Exact year match
                if year and node_year == year:
                    best_match = node
                    break

                # Close year match (within 1 year)
                if year and node_year and abs(node_year - year) <= 1:
                    if not best_match:
                        best_match = node

                # Title match without year
                if not best_match and node_title.lower() == title.lower():
                    best_match = node

            # Fall back to first result
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
        excluded_services: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get watch links in canonical NRW schema.

        Args:
            title: Movie title
            year: Release year
            affiliate_tag: Optional Amazon affiliate tag to append
            excluded_services: Optional list of service names to exclude (e.g. ['Philo', 'fuboTV'])

        Returns:
            Dict with 'streaming' and 'vod' categories:
            {
                'streaming': {'service': 'Netflix', 'link': 'https://...'},
                'vod': {'service': 'Amazon Video', 'link': 'https://...', 'price': '$4.99'}
            }
        """
        movie = self.search_movie(title, year)

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

            if mtype == 'FLATRATE':
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

    def _select_vod_offers(
        self,
        offers: List[Dict],
        affiliate_tag: Optional[str] = None
    ) -> List[Dict]:
        """
        Select up to one Amazon and one Apple TV offer from VOD offers.
        Returns an array of offer dicts (1 or 2 entries).
        """
        amazon_offer = None
        apple_offer = None

        # Find best Amazon and best Apple TV offer (prefer rent over buy)
        for offer in offers:
            svc = offer['service'].lower()
            if not amazon_offer and ('amazon' in svc or 'prime' in svc):
                amazon_offer = offer
            elif not apple_offer and ('apple' in svc or 'itunes' in svc):
                apple_offer = offer

        result = []
        for offer in [amazon_offer, apple_offer]:
            if offer:
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
