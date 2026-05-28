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
import re
import unicodedata
from typing import Dict, Optional, List, Any


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
        # Tier 3: Library/public broadcasting free services
        'Kanopy', 'Hoopla', 'PBS', 'PBS Documentaries',
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

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for comparison.

        Handles: case, diacritics (Sirāt→sirat), punctuation (Spider-Man→spider man),
        trailing parentheticals like "(2005)", and leading English articles (the/a/an).
        """
        if not title:
            return ''
        # Strip trailing parentheticals — e.g. "Crash (2005)" → "Crash"
        t = re.sub(r'\s*\([^)]*\)\s*$', '', title)
        # Strip diacritics (é→e, ā→a, ü→u)
        t = unicodedata.normalize('NFD', t)
        t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
        # Lowercase and replace punctuation with spaces (so "Spider-Man" → "spider man")
        t = re.sub(r'[^\w\s]', ' ', t.lower())
        # Collapse whitespace
        t = ' '.join(t.split())
        # Strip leading English articles
        for article in ('the ', 'a ', 'an '):
            if t.startswith(article):
                t = t[len(article):]
                break
        return t

    def _titles_match(self, jw_title: str, title: str, original_title: Optional[str] = None) -> bool:
        """Check if JustWatch title matches either title or original_title."""
        jw_norm = self._normalize_title(jw_title)
        if jw_norm == self._normalize_title(title):
            return True
        if original_title and jw_norm == self._normalize_title(original_title):
            return True
        return False

    def search_movie(
        self,
        title: str,
        year: Optional[int] = None,
        content_type: str = 'movie',
        original_title: Optional[str] = None,
        director: Optional[str] = None,
        tmdb_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Search for a movie or TV show by title and optional year.

        Args:
            title: Movie title
            year: Release year (helps disambiguate)
            content_type: 'movie' or 'tv' — determines JustWatch objectTypes filter
            original_title: Original language title (checked alongside title)
            director: Director name for disambiguation when multiple titles match

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
        orig_suffix = f"_{original_title}" if original_title and original_title.lower() != title.lower() else ''
        dir_suffix = f"_{director}" if director else ''
        cache_key = f"{title}_{year or 'any'}_{object_type}{orig_suffix}{dir_suffix}"
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
                  externalIds {{
                    tmdbId
                  }}
                  credits(role: DIRECTOR) {{
                    role
                    name
                  }}
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

            # Find best match: require title match (against title OR original_title).
            # Never accept a result based on year alone — that picks wrong movies.
            titles_to_match = {self._normalize_title(title)}
            if original_title and original_title.lower() != title.lower():
                norm_orig = self._normalize_title(original_title)
                if norm_orig:
                    titles_to_match.add(norm_orig)

            best_match = None

            # Pass 1: TMDB ID match (strongest — unique identifier, zero false positives)
            if tmdb_id:
                tmdb_id_str = str(tmdb_id)
                for edge in edges:
                    node = edge['node']
                    ext_ids = node.get('content', {}).get('externalIds', {})
                    if ext_ids and str(ext_ids.get('tmdbId', '')) == tmdb_id_str:
                        best_match = node
                        break

            # Pass 2: title + exact year
            if not best_match:
                for edge in edges:
                    node = edge['node']
                    content = node.get('content', {})
                    node_title_norm = self._normalize_title(content.get('title', ''))
                    if node_title_norm in titles_to_match and year and content.get('originalReleaseYear') == year:
                        best_match = node
                        break

            # Pass 3: title + director (same title + same director = same film)
            if not best_match and director:
                director_lower = director.lower()
                for edge in edges:
                    node = edge['node']
                    content = node.get('content', {})
                    node_title_norm = self._normalize_title(content.get('title', ''))
                    if node_title_norm in titles_to_match:
                        credits = content.get('credits', [])
                        for credit in credits:
                            if credit.get('role') == 'DIRECTOR' and credit.get('name', '').lower() == director_lower:
                                best_match = node
                                break
                        if best_match:
                            break

            if not best_match:
                self.logger.debug(f"No title match for '{title}' in JustWatch results")
                self.stats['failures'] += 1
                return None

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
        content_type: str = 'movie',
        original_title: Optional[str] = None,
        director: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get watch links in canonical NRW schema.

        Args:
            title: Movie title
            year: Release year
            affiliate_tag: Optional Amazon affiliate tag to append
            excluded_services: Optional list of service names to exclude (e.g. ['Philo', 'fuboTV'])
            content_type: 'movie' or 'tv' — determines JustWatch objectTypes filter
            original_title: Original language title (checked alongside title)
            director: Director name for disambiguation when multiple titles match

        Returns:
            Dict with 'streaming' and 'vod' categories:
            {
                'streaming': {'service': 'Netflix', 'link': 'https://...'},
                'vod': {'service': 'Amazon Video', 'link': 'https://...', 'price': '$4.99'}
            }
        """
        movie = self.search_movie(title, year, content_type=content_type,
                                  original_title=original_title, director=director)

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

            # Skip physical media offers (DVD/Blu-ray) — NRW is digital-only
            service_lower = service.lower()
            if 'dvd' in service_lower or 'blu-ray' in service_lower:
                self.logger.debug(f"Skipping physical media offer '{service}' for '{title}'")
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
        if rent_offers or buy_offers:
            vod_entries = self._merge_vod_offers(rent_offers, buy_offers, affiliate_tag)
            if vod_entries:
                result['vod'] = vod_entries

        return result

    def verify_availability(
        self,
        title: str,
        year: Optional[int] = None,
        excluded_services: Optional[List[str]] = None,
        affiliate_tag: Optional[str] = None,
        content_type: str = 'movie',
        original_title: Optional[str] = None,
        director: Optional[str] = None,
        tmdb_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Verify a movie's availability for the discovery phase.

        Called ONLY for movies TMDB flags as having providers (~1-10/day).
        Returns structured verification data including match confidence,
        offer breakdown, and ready-to-use watch_links.

        Returns:
            Dict with:
              'verified': True, False, or 'buy_only'
              'match_confidence': 'exact_year', 'close_year', 'tmdb_id', 'title_only', 'first_result'
              'jw_title': str - title JustWatch matched
              'jw_year': int or None - year JustWatch matched
              'has_streaming': bool
              'has_rent': bool
              'has_buy': bool
              'provider_names': {'streaming': [...], 'rent': [...], 'buy': [...]}
              'watch_links': dict in NRW schema (ready to store)
            None if search fails entirely.
        """
        movie = self.search_movie(title, year, content_type=content_type,
                                  original_title=original_title, director=director,
                                  tmdb_id=tmdb_id)
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

        # Title check: JustWatch result must match either our title or original_title.
        # Normalized comparison (lowercase, strip leading articles like "the/a/an").
        # If neither matches, check TMDB ID as fallback before rejecting.
        titles_match = self._titles_match(jw_title, title, original_title)

        # TMDB ID fallback: when titles differ but same movie confirmed by ID.
        # Handles cases like TMDB "Nukkad Naatak" → JW "A Street Play".
        tmdb_match = False
        if tmdb_id and not titles_match:
            ext_ids = content.get('externalIds', {})
            if ext_ids and str(ext_ids.get('tmdbId', '')) == str(tmdb_id):
                tmdb_match = True
                self.logger.info(
                    f"JustWatch TMDB ID match: searched '{title}' → "
                    f"matched '{jw_title}' by TMDB ID {tmdb_id}"
                )

        if titles_match and year and jw_year == year:
            confidence = 'exact_year'
        elif tmdb_match:
            confidence = 'tmdb_id'
        elif titles_match and year and jw_year and abs(jw_year - year) <= 1:
            confidence = 'close_year'
        elif titles_match:
            confidence = 'title_only'
        else:
            # Title doesn't match and no TMDB ID match → reject.
            # Set verified=False so discovery pre-check also rejects (it only
            # checks verified, not match_confidence).
            confidence = 'first_result'
            alt_info = f" / '{original_title}'" if original_title and original_title.lower() != title.lower() else ''
            self.logger.warning(
                f"JustWatch title mismatch: searched '{title}'{alt_info} but matched "
                f"'{jw_title}' (year {jw_year}). Rejecting (no title match)."
            )
            return {
                'verified': False,
                'match_confidence': confidence,
                'jw_title': jw_title,
                'jw_year': jw_year,
                'has_streaming': False,
                'has_rent': False,
                'has_buy': False,
                'provider_names': {'streaming': [], 'rent': [], 'buy': []},
                'watch_links': {}
            }

        offers = movie.get('offers', [])
        excluded_lower = [s.lower() for s in (excluded_services or [])]

        # Group offers by monetization type
        streaming_offers = []
        rent_offers = []
        buy_offers = []
        streaming_names = []
        rent_names = []
        buy_names = []

        presentation_types = set()

        for offer in offers:
            mtype = offer.get('monetizationType')
            ptype = offer.get('presentationType')
            url = offer.get('standardWebURL')
            service = offer.get('package', {}).get('clearName', '')
            price = offer.get('retailPrice')

            if ptype:
                presentation_types.add(ptype)

            if not url or not service:
                continue

            if any(excluded in service.lower() for excluded in excluded_lower):
                continue

            if 'youtube.com/results' in url:
                continue

            # Skip physical media offers (DVD/Blu-ray) — NRW is digital-only
            service_lower = service.lower()
            if 'dvd' in service_lower or 'blu-ray' in service_lower:
                self.logger.debug(f"Skipping physical media offer '{service}' for '{title}'")
                continue

            offer_data = {'service': service, 'link': url, 'price': price, '_ptype': ptype}

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

        # Detect theatrical (CINEMA) offers — signals movie is still in theaters.
        # Collected from raw offers before filtering so we catch all cinema services.
        cinema_offers = [o for o in offers
                         if o.get('monetizationType') == 'CINEMA'
                         and o.get('standardWebURL') and o.get('package', {}).get('clearName')]
        has_cinema = bool(cinema_offers)

        # Prefer HD prices: sort rent/buy so HD comes first per service
        _ptype_order = {'HD': 0, '4K': 1, 'SD': 2}
        rent_offers.sort(key=lambda o: _ptype_order.get(o.get('_ptype', ''), 99))
        buy_offers.sort(key=lambda o: _ptype_order.get(o.get('_ptype', ''), 99))

        has_streaming = bool(streaming_offers)
        has_rent = bool(rent_offers)
        has_buy = bool(buy_offers)

        # Minimum filtered rent price — used to distinguish PVOD ($15+) from
        # legitimate day-and-date releases with normal rental pricing (<$15).
        min_rent_price = None
        if has_cinema and rent_offers:
            prices = []
            for o in rent_offers:
                p = o.get('price')
                if p:
                    try:
                        prices.append(float(str(p).replace('$', '').strip()))
                    except (ValueError, TypeError):
                        pass
            min_rent_price = min(prices) if prices else None

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

        if rent_offers or buy_offers:
            vod_entries = self._merge_vod_offers(rent_offers, buy_offers, affiliate_tag)
            if vod_entries:
                watch_links['vod'] = vod_entries

        buy_only = has_buy and not has_rent and not has_streaming

        if presentation_types:
            self.logger.debug(f"JustWatch presentationTypes for {title}: {presentation_types}")

        # Build JustWatch page URL from fullPath (e.g. /us/movie/bunny-2025)
        jw_full_path = content.get('fullPath', '')
        jw_url = f'https://www.justwatch.com{jw_full_path}' if jw_full_path else ''

        return {
            'verified': verified,
            'match_confidence': confidence,
            'jw_title': jw_title,
            'jw_year': jw_year,
            'jw_url': jw_url,
            'has_streaming': has_streaming,
            'has_rent': has_rent,
            'has_buy': has_buy,
            'buy_only': buy_only,
            'has_cinema': has_cinema,
            'min_rent_price': min_rent_price,
            '_presentation_types': sorted(presentation_types),
            'provider_names': {
                'streaming': streaming_names,
                'rent': rent_names,
                'buy': buy_names
            },
            'watch_links': watch_links
        }


    def _merge_vod_offers(
        self,
        rent_offers: List[Dict],
        buy_offers: List[Dict],
        affiliate_tag: Optional[str] = None
    ) -> List[Dict]:
        """
        Merge rent and buy offers per service, preserving both prices.
        Returns one entry per service with rent_price and buy_price fields.
        """
        service_map = {}  # lowercase service -> merged entry

        # Enforce HD-first sort so "first wins" keeps the best quality price
        _ptype_order = {'HD': 0, '4K': 1, 'SD': 2}
        rent_offers = sorted(rent_offers, key=lambda o: _ptype_order.get(o.get('_ptype', ''), 99))
        buy_offers = sorted(buy_offers, key=lambda o: _ptype_order.get(o.get('_ptype', ''), 99))

        for offer in rent_offers:
            svc_key = offer['service'].lower()
            if svc_key not in service_map:
                service_map[svc_key] = {
                    'service': offer['service'],
                    'link': offer['link'],
                    'rent_price': offer.get('price'),
                    'buy_price': None
                }

        for offer in buy_offers:
            svc_key = offer['service'].lower()
            if svc_key in service_map:
                # Only set buy_price if not already set (first = HD after sort)
                if service_map[svc_key]['buy_price'] is None:
                    service_map[svc_key]['buy_price'] = offer.get('price')
            else:
                service_map[svc_key] = {
                    'service': offer['service'],
                    'link': offer['link'],
                    'rent_price': None,
                    'buy_price': offer.get('price')
                }

        result = []
        for entry in service_map.values():
            link = entry['link']
            if affiliate_tag and 'amazon' in link.lower():
                separator = '&' if '?' in link else '?'
                if 'tag=' not in link:
                    link = f"{link}{separator}tag={affiliate_tag}"
            item = {'service': entry['service'], 'link': link}
            if entry.get('rent_price'):
                item['rent_price'] = entry['rent_price']
            if entry.get('buy_price'):
                item['buy_price'] = entry['buy_price']
            # Backward compat: 'price' = cheapest available
            item['price'] = entry.get('rent_price') or entry.get('buy_price')
            result.append(item)

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
    """Test the JustWatch client with positive, negative, and disambiguation cases."""
    client = JustWatchClient()
    passed = 0
    failed = 0

    def check(label, condition, detail=""):
        nonlocal passed, failed
        status = "PASS" if condition else "FAIL"
        if condition:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {label}")
        if detail:
            print(f"         {detail}")

    # --- Positive tests: known movies that should return links ---
    print(f"\n{'='*60}")
    print("POSITIVE TESTS (should find links)")
    print('='*60)

    for title, year in [("Conclave", 2024), ("Anora", 2024)]:
        links = client.get_watch_links(title, year, affiliate_tag="nrw-20")
        check(f"{title} ({year}) returns links", bool(links),
              f"streaming={bool(links.get('streaming'))}, vod={bool(links.get('vod'))}")

    # --- Negative tests: movies not in JustWatch should return empty, not wrong data ---
    print(f"\n{'='*60}")
    print("NEGATIVE TESTS (should return empty, NOT wrong movie)")
    print('='*60)

    result = client.search_movie("Ketchup on Waffles", 2025)
    check("'Ketchup on Waffles' returns None (not House on Eden)", result is None,
          f"got: {result.get('content', {}).get('title') if result else 'None'}")

    result = client.search_movie("Pirates Gold 3", 2025)
    check("'Pirates Gold 3' returns None (not Code 3)", result is None,
          f"got: {result.get('content', {}).get('title') if result else 'None'}")

    result = client.search_movie("Bouya Rage Bomb", 2024)
    check("'Bouya Rage Bomb' returns None (not Big Rage)", result is None,
          f"got: {result.get('content', {}).get('title') if result else 'None'}")

    # --- original_title tests: foreign films should match via original title ---
    print(f"\n{'='*60}")
    print("ORIGINAL TITLE TESTS (should match via foreign title)")
    print('='*60)

    # Search by English title, verify it finds the movie
    result = client.search_movie("Conclave", 2024, original_title="Konklave")
    check("'Conclave' with original_title='Konklave' still matches",
          result is not None and result.get('content', {}).get('title') == 'Conclave')

    # --- Director disambiguation tests ---
    print(f"\n{'='*60}")
    print("DIRECTOR DISAMBIGUATION TESTS")
    print('='*60)

    # "Crash" without director — should return something (either version)
    result = client.search_movie("Crash", director=None)
    crash_title = result.get('content', {}).get('title', '') if result else ''
    crash_year = result.get('content', {}).get('originalReleaseYear') if result else None
    check("'Crash' without director returns a result", result is not None, f"got: {crash_title} ({crash_year})")

    # "Crash" with Cronenberg → should get 1996
    result = client.search_movie("Crash", director="David Cronenberg")
    if result:
        got_year = result.get('content', {}).get('originalReleaseYear')
        check("'Crash' + director Cronenberg → 1996", got_year == 1996, f"got year: {got_year}")
    else:
        check("'Crash' + director Cronenberg → 1996", False, "got: None")

    # "Crash" with Haggis → should get 2005
    result = client.search_movie("Crash", director="Paul Haggis")
    if result:
        got_year = result.get('content', {}).get('originalReleaseYear')
        check("'Crash' + director Haggis → 2005", got_year == 2005, f"got year: {got_year}")
    else:
        check("'Crash' + director Haggis → 2005", False, "got: None")

    # --- verify_availability title mismatch rejection ---
    print(f"\n{'='*60}")
    print("VERIFY_AVAILABILITY REJECTION TESTS")
    print('='*60)

    va_result = client.verify_availability("Ketchup on Waffles", 2025)
    check("verify_availability('Ketchup on Waffles') → None or verified=False",
          va_result is None or va_result.get('verified') == False,
          f"got: {va_result}")

    # --- Summary ---
    print(f"\n{'='*60}")
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print(f"API stats: {client.get_stats()}")
    print('='*60)


if __name__ == "__main__":
    test_client()
