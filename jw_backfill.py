#!/usr/bin/env python3
"""
JustWatch Backfill Script

One-time script to populate jw_seen.json with all 2024-2025 movies
currently on Amazon/iTunes. This creates the baseline for daily
new arrival detection.

Run once, then use jw_daily_check.py for ongoing monitoring.
"""

import requests
import json
import time
from datetime import datetime

API_URL = "https://apis.justwatch.com/graphql"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Content-Type': 'application/json',
}

# Filter settings
MIN_YEAR = 2025
MAX_YEAR = 2025
PACKAGES = ["amz", "itu"]  # Amazon, iTunes - expand later if needed

JW_SEEN_FILE = "jw_seen.json"


def fetch_movies_for_year_package(year: int, package: str) -> list:
    """Fetch movies for a specific year and package (to work around 2000 result limit)."""

    query = '''
    query BrowseMovies($country: Country!, $first: Int!, $after: String) {
      popularTitles(
        country: $country
        first: $first
        after: $after
        filter: {
          objectTypes: [MOVIE]
          releaseYear: {min: %d, max: %d}
          packages: ["%s"]
        }
      ) {
        totalCount
        edges {
          node {
            objectId
            content(country: $country, language: "en") {
              title
              originalReleaseYear
            }
            offers(country: $country, platform: WEB) {
              monetizationType
              package { clearName, packageId }
            }
          }
        }
        pageInfo { hasNextPage, endCursor }
      }
    }
    ''' % (year, year, package)

    movies = []
    cursor = None
    page = 0

    while True:
        variables = {'country': 'US', 'first': 50}
        if cursor:
            variables['after'] = cursor

        try:
            resp = requests.post(API_URL, json={'query': query, 'variables': variables},
                               headers=HEADERS, timeout=30)
            data = resp.json()

            if 'errors' in data:
                print(f"    Error: {data['errors']}")
                break

            result = data['data']['popularTitles']
            total = result['totalCount']
            edges = result['edges']
            page_info = result['pageInfo']

            # Check for API pagination limit (returns 0 total when exhausted)
            if total == 0 and page > 0:
                break

            for edge in edges:
                node = edge['node']
                content = node.get('content') or {}
                offers = node.get('offers') or []

                # Get provider info
                providers = {}
                for offer in offers:
                    pkg = offer.get('package', {})
                    name = pkg.get('clearName', '')
                    mtype = offer.get('monetizationType', '')
                    if name and mtype:
                        if name not in providers:
                            providers[name] = []
                        if mtype not in providers[name]:
                            providers[name].append(mtype)

                movies.append({
                    'jw_id': node.get('objectId'),
                    'title': content.get('title', ''),
                    'year': content.get('originalReleaseYear'),
                    'providers': providers,
                    'first_seen': datetime.now().strftime('%Y-%m-%d'),
                })

            page += 1

            if not page_info.get('hasNextPage'):
                break

            cursor = page_info.get('endCursor')
            time.sleep(0.1)

        except Exception as e:
            print(f"    Error on page {page}: {e}")
            break

    return movies


def fetch_all_movies() -> list:
    """Fetch all movies by splitting queries to avoid 2000 result limit."""

    all_movies = {}  # Use dict to dedupe by jw_id

    # Split by year and package to maximize coverage
    for year in [MIN_YEAR, MAX_YEAR]:
        for package in PACKAGES:
            print(f"  Fetching {year} / {package}...")
            movies = fetch_movies_for_year_package(year, package)
            print(f"    Got {len(movies)} movies")

            for movie in movies:
                jw_id = movie['jw_id']
                if jw_id not in all_movies:
                    all_movies[jw_id] = movie
                else:
                    # Merge providers from different queries
                    existing = all_movies[jw_id]
                    for provider, mtypes in movie['providers'].items():
                        if provider not in existing['providers']:
                            existing['providers'][provider] = mtypes
                        else:
                            for mtype in mtypes:
                                if mtype not in existing['providers'][provider]:
                                    existing['providers'][provider].append(mtype)

    return list(all_movies.values())


def save_jw_seen(movies: list):
    """Save movies to jw_seen.json."""

    # Structure: keyed by jw_id for fast lookup
    seen = {}
    for movie in movies:
        jw_id = str(movie['jw_id'])
        seen[jw_id] = {
            'title': movie['title'],
            'year': movie['year'],
            'providers': movie['providers'],
            'first_seen': movie['first_seen'],
        }

    data = {
        'metadata': {
            'created': datetime.now().isoformat(),
            'min_year': MIN_YEAR,
            'max_year': MAX_YEAR,
            'packages': PACKAGES,
            'total_movies': len(seen),
        },
        'seen': seen
    }

    with open(JW_SEEN_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved {len(seen)} movies to {JW_SEEN_FILE}")


def main():
    print("=" * 60)
    print("JustWatch Backfill")
    print(f"Fetching {MIN_YEAR}-{MAX_YEAR} movies on {PACKAGES}")
    print("=" * 60)

    start = time.time()
    movies = fetch_all_movies()
    elapsed = time.time() - start

    print(f"\nFetched {len(movies)} movies in {elapsed:.1f}s")

    save_jw_seen(movies)

    # Show sample
    print("\nSample entries:")
    for m in movies[:10]:
        providers = ', '.join(m['providers'].keys())
        print(f"  - {m['title']} ({m['year']}) - {providers}")

    print("\nBackfill complete! Now run jw_daily_check.py for ongoing monitoring.")


if __name__ == '__main__':
    main()
