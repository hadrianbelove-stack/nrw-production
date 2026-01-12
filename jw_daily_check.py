#!/usr/bin/env python3
"""
JustWatch Daily Check

Daily script to check JustWatch newTitles for new arrivals.
Mirrors the NRW pipeline but uses JustWatch as the source.

Flow:
1. Load jw_seen.json (baseline of known movies)
2. Fetch newTitles from JustWatch (2024-2025, Amazon/iTunes)
3. Filter out movies already in jw_seen
4. New movies = potential new arrivals
5. Look up TMDB ID for enrichment
6. Append to jw_arrivals.json
7. Update jw_seen.json with newly seen movies
"""

import requests
import json
import time
import yaml
from datetime import datetime

API_URL = "https://apis.justwatch.com/graphql"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Content-Type': 'application/json',
}

# Filter settings (match backfill)
MIN_YEAR = 2025
MAX_YEAR = 2025
PACKAGES = ["amz", "itu"]

JW_SEEN_FILE = "jw_seen.json"
JW_ARRIVALS_FILE = "jw_arrivals.json"

# Load TMDB key for enrichment
try:
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    TMDB_KEY = config['api']['tmdb_api_key']
except:
    TMDB_KEY = None


def load_jw_seen() -> dict:
    """Load the jw_seen.json baseline."""
    try:
        with open(JW_SEEN_FILE, 'r') as f:
            data = json.load(f)
        return data.get('seen', {})
    except FileNotFoundError:
        print(f"WARNING: {JW_SEEN_FILE} not found. Run jw_backfill.py first!")
        return {}


def save_jw_seen(seen: dict, metadata: dict = None):
    """Save updated jw_seen.json."""
    data = {
        'metadata': metadata or {
            'updated': datetime.now().isoformat(),
            'total_movies': len(seen),
        },
        'seen': seen
    }
    with open(JW_SEEN_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_jw_arrivals() -> list:
    """Load existing arrivals."""
    try:
        with open(JW_ARRIVALS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_jw_arrivals(arrivals: list):
    """Save arrivals list."""
    with open(JW_ARRIVALS_FILE, 'w') as f:
        json.dump(arrivals, f, indent=2)


def fetch_new_titles() -> list:
    """Fetch newTitles from JustWatch (rolling 500 window)."""

    query = '''
    query GetNewReleases($country: Country!, $first: Int!, $after: String) {
      newTitles(
        country: $country
        first: $first
        after: $after
        filter: {
          objectTypes: [MOVIE]
          releaseYear: {min: %d, max: %d}
          packages: %s
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
              package { clearName }
            }
          }
        }
        pageInfo { hasNextPage, endCursor }
      }
    }
    ''' % (MIN_YEAR, MAX_YEAR, json.dumps(PACKAGES))

    movies = []
    cursor = None

    while True:
        variables = {'country': 'US', 'first': 50}
        if cursor:
            variables['after'] = cursor

        try:
            resp = requests.post(API_URL, json={'query': query, 'variables': variables},
                               headers=HEADERS, timeout=30)
            data = resp.json()

            if 'errors' in data:
                print(f"Error: {data['errors']}")
                break

            result = data['data']['newTitles']
            edges = result['edges']
            page_info = result['pageInfo']

            for edge in edges:
                node = edge['node']
                content = node.get('content') or {}
                offers = node.get('offers') or []

                # Get providers
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
                })

            if not page_info.get('hasNextPage'):
                break

            cursor = page_info.get('endCursor')
            time.sleep(0.1)

        except Exception as e:
            print(f"Error: {e}")
            break

    return movies


def lookup_tmdb_id(title: str, year: int) -> dict:
    """Look up TMDB ID for a movie."""
    if not TMDB_KEY:
        return {'tmdb_id': None, 'tmdb_found': False}

    try:
        resp = requests.get("https://api.themoviedb.org/3/search/movie", params={
            'api_key': TMDB_KEY,
            'query': title,
            'year': year,
        }, timeout=10)

        if resp.status_code == 200:
            results = resp.json().get('results', [])
            if results:
                movie = results[0]
                return {
                    'tmdb_id': movie['id'],
                    'tmdb_found': True,
                    'overview': movie.get('overview', ''),
                    'poster_path': movie.get('poster_path'),
                    'vote_average': movie.get('vote_average'),
                }
        return {'tmdb_id': None, 'tmdb_found': False}

    except Exception:
        return {'tmdb_id': None, 'tmdb_found': False}


def run_daily_check():
    """Main daily check routine."""

    print("=" * 60)
    print("JustWatch Daily Check")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Load baseline
    print("\n1. Loading jw_seen.json...")
    seen = load_jw_seen()
    if not seen:
        print("   No baseline found. Run jw_backfill.py first!")
        return

    print(f"   {len(seen)} movies in baseline")

    # 2. Fetch newTitles
    print("\n2. Fetching JustWatch newTitles...")
    new_titles = fetch_new_titles()
    print(f"   {len(new_titles)} movies in newTitles feed")

    # 3. Filter out already-seen
    print("\n3. Finding new arrivals...")
    new_arrivals = []
    for movie in new_titles:
        jw_id = str(movie['jw_id'])
        if jw_id not in seen:
            new_arrivals.append(movie)

    print(f"   {len(new_arrivals)} NEW movies not in baseline")

    if not new_arrivals:
        print("\n   No new arrivals today!")
        return

    # 4. Enrich with TMDB
    print("\n4. Enriching with TMDB data...")
    enriched = []
    for movie in new_arrivals:
        tmdb_data = lookup_tmdb_id(movie['title'], movie['year'])
        movie.update(tmdb_data)
        movie['discovered'] = datetime.now().isoformat()

        enriched.append(movie)
        time.sleep(0.05)

    tmdb_found = len([m for m in enriched if m.get('tmdb_found')])
    print(f"   Found TMDB data for {tmdb_found}/{len(enriched)}")

    # 5. Append to arrivals file
    print("\n5. Saving new arrivals...")
    existing_arrivals = load_jw_arrivals()
    existing_arrivals.extend(enriched)
    save_jw_arrivals(existing_arrivals)
    print(f"   Total arrivals: {len(existing_arrivals)}")

    # 6. Update baseline
    print("\n6. Updating jw_seen.json...")
    for movie in new_arrivals:
        jw_id = str(movie['jw_id'])
        seen[jw_id] = {
            'title': movie['title'],
            'year': movie['year'],
            'providers': movie['providers'],
            'first_seen': datetime.now().strftime('%Y-%m-%d'),
        }
    save_jw_seen(seen)
    print(f"   Baseline now has {len(seen)} movies")

    # 7. Summary
    print("\n" + "=" * 60)
    print("NEW ARRIVALS TODAY")
    print("=" * 60)
    for movie in enriched:
        providers = ', '.join(movie['providers'].keys())
        tmdb = f"[TMDB:{movie['tmdb_id']}]" if movie.get('tmdb_id') else "[no TMDB]"
        print(f"  - {movie['title']} ({movie['year']}) {tmdb}")
        print(f"    Providers: {providers}")

    print(f"\nTotal new arrivals: {len(enriched)}")
    print(f"Saved to: {JW_ARRIVALS_FILE}")


if __name__ == '__main__':
    run_daily_check()
