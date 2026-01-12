#!/usr/bin/env python3
"""
Test script: Compare JustWatch discovery vs TMDB discovery

This explores whether JustWatch's newTitles query catches releases
that our current TMDB-based approach misses.

Safe to run - doesn't modify any production files.
"""

import requests
import json
import yaml
import time
from datetime import datetime, timedelta

# Load TMDB key
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)
TMDB_KEY = config['api']['tmdb_api_key']

# Year filter: only include movies from these years (handles Q4/Q1 crossover)
CURRENT_YEAR = datetime.now().year
MIN_RELEASE_YEAR = CURRENT_YEAR - 1  # 2024
MAX_RELEASE_YEAR = CURRENT_YEAR      # 2025


def justwatch_new_releases(count: int = 50, filter_by_year: bool = True) -> list:
    """Fetch new movie releases from JustWatch GraphQL."""

    API_URL = "https://apis.justwatch.com/graphql"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        'Content-Type': 'application/json',
    }

    query = '''
    query GetNewReleases($country: Country!, $first: Int!, $after: String) {
      newTitles(
        country: $country
        first: $first
        after: $after
        filter: {
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
              standardWebURL
              package {
                clearName
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
        totalCount
      }
    }
    '''

    movies = []
    cursor = None
    fetched = 0

    while fetched < count:
        batch_size = min(50, count - fetched)
        variables = {
            'country': 'US',
            'first': batch_size,
            'after': cursor
        }

        try:
            resp = requests.post(API_URL, json={'query': query, 'variables': variables},
                               headers=headers, timeout=15)
            data = resp.json()

            if 'errors' in data:
                print(f"JustWatch error: {data['errors']}")
                break

            edges = data.get('data', {}).get('newTitles', {}).get('edges', [])
            page_info = data.get('data', {}).get('newTitles', {}).get('pageInfo', {})

            for edge in edges:
                node = edge['node']
                content = node.get('content', {})
                offers = node.get('offers', [])

                # Get unique services
                services = set()
                for offer in offers:
                    svc = offer.get('package', {}).get('clearName', '')
                    mtype = offer.get('monetizationType', '')
                    if svc and mtype in ['FLATRATE', 'RENT', 'BUY']:
                        services.add(f"{svc} ({mtype.lower()})")

                year = content.get('originalReleaseYear')

                # Filter by year if enabled (skip classics like Die Hard 1988)
                if filter_by_year and year:
                    if year < MIN_RELEASE_YEAR or year > MAX_RELEASE_YEAR:
                        continue

                movies.append({
                    'jw_id': node.get('objectId'),
                    'title': content.get('title', ''),
                    'year': year,
                    'services': list(services)[:5],  # Top 5
                    'source': 'justwatch'
                })

            fetched += len(edges)
            cursor = page_info.get('endCursor')

            if not page_info.get('hasNextPage'):
                break

            time.sleep(0.1)

        except Exception as e:
            print(f"JustWatch error: {e}")
            break

    return movies


def tmdb_recent_releases(days: int = 7) -> list:
    """Fetch recent releases from TMDB with watch providers."""

    movies = []
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Get movies with recent premiere dates
    page = 1
    while page <= 5:  # Limit pages for test
        resp = requests.get("https://api.themoviedb.org/3/discover/movie", params={
            'api_key': TMDB_KEY,
            'primary_release_date.gte': start_date,
            'primary_release_date.lte': end_date,
            'sort_by': 'primary_release_date.desc',
            'page': page
        }, timeout=15)

        if resp.status_code != 200:
            break

        data = resp.json()

        for movie in data.get('results', []):
            tmdb_id = movie['id']

            # Check watch providers
            wp_resp = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers",
                                  params={'api_key': TMDB_KEY}, timeout=10)

            services = []
            if wp_resp.status_code == 200:
                wp_data = wp_resp.json()
                us_data = wp_data.get('results', {}).get('US', {})

                for cat in ['flatrate', 'rent', 'buy']:
                    for provider in us_data.get(cat, []):
                        services.append(f"{provider['provider_name']} ({cat})")

            movies.append({
                'tmdb_id': tmdb_id,
                'title': movie.get('title', ''),
                'year': movie.get('release_date', '')[:4] if movie.get('release_date') else None,
                'services': services[:5],
                'has_providers': len(services) > 0,
                'source': 'tmdb'
            })

            time.sleep(0.05)

        if page >= data.get('total_pages', 1):
            break
        page += 1

    return movies


def lookup_tmdb_ids(jw_movies: list) -> list:
    """Look up TMDB IDs for JustWatch movies (for metadata enrichment only).

    Note: We trust JustWatch for release year, not TMDB - TMDB dates are often wrong.
    """
    for movie in jw_movies:
        title = movie['title']
        year = movie.get('year')

        # Search TMDB just to get the ID
        try:
            resp = requests.get("https://api.themoviedb.org/3/search/movie", params={
                'api_key': TMDB_KEY,
                'query': title,
                'year': year,
            }, timeout=10)

            if resp.status_code == 200:
                results = resp.json().get('results', [])
                if results:
                    movie['tmdb_id'] = results[0]['id']
                    movie['tmdb_found'] = True
                else:
                    movie['tmdb_found'] = False

            time.sleep(0.05)

        except Exception:
            movie['tmdb_found'] = False

    return jw_movies


def load_movie_tracking() -> set:
    """Load titles from movie_tracking.json (the actual NRW database)."""
    try:
        with open('movie_tracking.json', 'r') as f:
            data = json.load(f)

        titles = set()
        # movie_tracking.json structure: {"movies": {"tmdb_id": {...}, ...}}
        movies = data.get('movies', {})
        for tmdb_id, movie in movies.items():
            title = movie.get('title', '').lower().strip()
            if title:
                titles.add(title)
        return titles
    except Exception as e:
        print(f"   Error loading movie_tracking.json: {e}")
        return set()


def compare_results():
    """Compare JustWatch vs actual NRW pipeline (movie_tracking.json)."""

    print("=" * 60)
    print("JustWatch Discovery vs NRW Pipeline")
    print(f"Filtering to {MIN_RELEASE_YEAR}-{MAX_RELEASE_YEAR} releases")
    print("=" * 60)

    # Load current NRW database
    print("\n1. Loading movie_tracking.json (current NRW database)...")
    nrw_titles = load_movie_tracking()
    print(f"   {len(nrw_titles)} movies in pipeline")

    # Fetch from JustWatch
    print("\n2. Fetching from JustWatch (new releases)...")
    jw_all = justwatch_new_releases(count=100, filter_by_year=False)
    print(f"   Raw results: {len(jw_all)} movies")

    # Filter by year
    jw_movies = [m for m in jw_all if m.get('year') and MIN_RELEASE_YEAR <= m['year'] <= MAX_RELEASE_YEAR]
    filtered_out = len(jw_all) - len(jw_movies)
    print(f"   After year filter ({MIN_RELEASE_YEAR}-{MAX_RELEASE_YEAR}): {len(jw_movies)} movies")
    print(f"   Filtered out: {filtered_out} older titles")

    # Look up TMDB IDs (for metadata, not verification)
    print("\n3. Looking up TMDB IDs...")
    jw_movies = lookup_tmdb_ids(jw_movies)
    with_tmdb = len([m for m in jw_movies if m.get('tmdb_found')])
    print(f"   Found TMDB IDs for: {with_tmdb}/{len(jw_movies)}")

    # Analyze
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)

    # JustWatch titles
    jw_titles = {m['title'].lower().strip() for m in jw_movies}

    # What's in JustWatch but NOT in NRW pipeline?
    missing_from_nrw = jw_titles - nrw_titles
    already_in_nrw = jw_titles & nrw_titles

    print(f"\nJustWatch new releases (2024-2025): {len(jw_movies)}")
    print(f"Already in NRW pipeline: {len(already_in_nrw)}")
    print(f"Missing from NRW pipeline: {len(missing_from_nrw)}")

    # Show what's missing
    if missing_from_nrw:
        print("\n*** MOVIES NRW PIPELINE IS MISSING ***")
        missing_movies = [m for m in jw_movies if m['title'].lower().strip() in missing_from_nrw]
        for m in missing_movies[:20]:
            services = ', '.join(m['services'][:3]) if m['services'] else 'unknown'
            tmdb_id = m.get('tmdb_id', 'N/A')
            print(f"   - {m['title']} ({m['year']}) [TMDB:{tmdb_id}]")
            print(f"     Available on: {services}")
    else:
        print("\n✅ NRW pipeline has all JustWatch new releases!")

    # Show overlap
    print(f"\n--- Already tracked ({len(already_in_nrw)} movies) ---")
    overlap_movies = [m for m in jw_movies if m['title'].lower().strip() in already_in_nrw][:10]
    for m in overlap_movies:
        services = ', '.join(m['services'][:2]) if m['services'] else 'unknown'
        print(f"   ✓ {m['title']} ({m['year']}) - {services}")

    # Save detailed results
    missing_movies = [m for m in jw_movies if m['title'].lower().strip() in missing_from_nrw]

    results = {
        'timestamp': datetime.now().isoformat(),
        'year_filter': f"{MIN_RELEASE_YEAR}-{MAX_RELEASE_YEAR}",
        'nrw_pipeline_count': len(nrw_titles),
        'justwatch_raw': len(jw_all),
        'justwatch_filtered': len(jw_movies),
        'already_in_nrw': len(already_in_nrw),
        'missing_from_nrw': len(missing_from_nrw),
        'missing_movies': missing_movies,  # Movies to potentially add
        'all_jw_movies': jw_movies
    }

    with open('test_discovery_comparison.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nDetailed results saved to: test_discovery_comparison.json")

    return results


if __name__ == '__main__':
    compare_results()
