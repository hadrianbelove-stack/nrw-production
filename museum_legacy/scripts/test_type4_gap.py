#!/usr/bin/env python3
"""
Test: Find tracking movies with Type 4 (digital) release but no providers.
This measures the gap between TMDB's release_dates and watch/providers data.
"""

import json
import requests
import time
import os

TMDB_KEY = os.environ.get('TMDB_API_KEY')

def check_movie(movie_id):
    """Check if movie has Type 4 release and/or providers."""
    # Check Type 4 release
    type4_date = None
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
    try:
        resp = requests.get(url, params={'api_key': TMDB_KEY}, timeout=10)
        if resp.status_code == 200:
            for entry in resp.json().get('results', []):
                if entry.get('iso_3166_1') == 'US':
                    for release in entry.get('release_dates', []):
                        if release.get('type') == 4:
                            type4_date = release.get('release_date', '')[:10]
                            break
    except Exception as e:
        pass

    # Check providers
    has_providers = False
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    try:
        resp = requests.get(url, params={'api_key': TMDB_KEY}, timeout=10)
        if resp.status_code == 200:
            us = resp.json().get('results', {}).get('US', {})
            has_providers = bool(us.get('rent') or us.get('buy') or us.get('flatrate'))
    except Exception as e:
        pass

    return type4_date, has_providers

def main():
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)

    tracking = [(mid, m) for mid, m in db['movies'].items()
                if m['status'] == 'tracking' and not mid.startswith('tv_')]

    print(f"Checking {len(tracking)} tracking movies...")

    type4_only = []  # Has Type 4, no providers
    both = []        # Has Type 4 AND providers
    providers_only = [] # Has providers, no Type 4
    neither = []     # Neither

    for i, (mid, movie) in enumerate(tracking):
        if i % 100 == 0:
            print(f"  Progress: {i}/{len(tracking)}")

        type4_date, has_providers = check_movie(mid)

        if type4_date and not has_providers:
            type4_only.append((mid, movie['title'], type4_date))
        elif type4_date and has_providers:
            both.append((mid, movie['title']))
        elif has_providers and not type4_date:
            providers_only.append((mid, movie['title']))
        else:
            neither.append((mid, movie['title']))

        time.sleep(0.25)  # Rate limit

    print(f"\n=== RESULTS ===")
    print(f"Type 4 ONLY (no providers): {len(type4_only)}")
    print(f"Both Type 4 AND providers: {len(both)}")
    print(f"Providers ONLY (no Type 4): {len(providers_only)}")
    print(f"Neither: {len(neither)}")

    if type4_only:
        print(f"\n=== TYPE 4 ONLY (would be caught by new logic) ===")
        for mid, title, date in type4_only[:20]:
            print(f"  {title} (ID: {mid}, Type 4 date: {date})")
        if len(type4_only) > 20:
            print(f"  ... and {len(type4_only) - 20} more")

if __name__ == '__main__':
    main()
