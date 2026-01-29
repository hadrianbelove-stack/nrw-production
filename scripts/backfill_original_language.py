#!/usr/bin/env python3
"""Backfill original_language field from TMDB for movies missing it."""

import json
import sys
import time
import requests

sys.path.insert(0, '.')
from museum_legacy.tmdb_auth import resolve_tmdb_auth

DATA_FILE = 'data.json'

def main():
    # Load data
    with open(DATA_FILE) as f:
        data = json.load(f)

    movies = data.get('movies', [])

    # Find movies missing original_language
    missing = [m for m in movies if not m.get('original_language')]
    print(f"Found {len(missing)} movies missing original_language")

    if not missing:
        print("Nothing to backfill!")
        return

    # Get TMDB auth
    headers, params = resolve_tmdb_auth()

    updated = 0
    errors = 0

    for i, movie in enumerate(missing):
        tmdb_id = movie.get('id')
        title = movie.get('title', 'Unknown')
        content_type = movie.get('content_type', 'movie')

        # Determine endpoint based on content type
        if content_type == 'limited_series':
            endpoint = f"https://api.themoviedb.org/3/tv/{tmdb_id}"
        else:
            endpoint = f"https://api.themoviedb.org/3/movie/{tmdb_id}"

        try:
            resp = requests.get(endpoint, headers=headers, params=params, timeout=10)

            if resp.status_code == 200:
                tmdb_data = resp.json()
                lang = tmdb_data.get('original_language')

                if lang:
                    movie['original_language'] = lang
                    updated += 1
                    print(f"[{i+1}/{len(missing)}] {title}: {lang}")
                else:
                    print(f"[{i+1}/{len(missing)}] {title}: no language in response")
                    errors += 1
            else:
                print(f"[{i+1}/{len(missing)}] {title}: HTTP {resp.status_code}")
                errors += 1

        except Exception as e:
            print(f"[{i+1}/{len(missing)}] {title}: error - {e}")
            errors += 1

        # Rate limit: TMDB allows ~40 requests per 10 seconds
        time.sleep(0.25)

    # Save updated data
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print()
    print(f"Done! Updated: {updated}, Errors: {errors}")

if __name__ == '__main__':
    main()
