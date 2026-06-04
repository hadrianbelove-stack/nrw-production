#!/usr/bin/env python3
"""Backfill TMDB keywords for all data.json movies missing the keywords field."""

import json
import os
import time
import requests

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data.json')
ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')

def load_tmdb_key():
    with open(ENV_PATH) as f:
        for line in f:
            if line.startswith('TMDB_API_KEY='):
                return line.strip().split('=', 1)[1]
    raise RuntimeError("TMDB_API_KEY not found in .env")

def fetch_keywords(tmdb_id, api_key):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/keywords"
    try:
        r = requests.get(url, params={'api_key': api_key}, timeout=10)
        if r.status_code == 200:
            kw_list = r.json().get('keywords', [])
            return [k['name'] for k in kw_list if k.get('name')]
        elif r.status_code == 404:
            return []
        else:
            print(f"  HTTP {r.status_code} for id={tmdb_id}")
            return None  # signal failure
    except Exception as e:
        print(f"  Error for id={tmdb_id}: {e}")
        return None

def main():
    api_key = load_tmdb_key()

    with open(DATA_PATH) as f:
        data = json.load(f)

    movies = data['movies']
    to_fill = [m for m in movies if 'keywords' not in m]
    print(f"Movies missing keywords field: {len(to_fill)}")

    updated = 0
    failed = 0
    for i, movie in enumerate(to_fill, 1):
        tmdb_id = movie.get('id')
        title = movie.get('title', '?')
        if not tmdb_id:
            print(f"  [{i}/{len(to_fill)}] SKIP (no id): {title}")
            movie['keywords'] = []
            updated += 1
            continue

        kws = fetch_keywords(tmdb_id, api_key)
        if kws is None:
            failed += 1
            print(f"  [{i}/{len(to_fill)}] FAIL: {title} (id={tmdb_id})")
        else:
            movie['keywords'] = kws
            updated += 1
            if kws:
                print(f"  [{i}/{len(to_fill)}] {title}: {kws[:4]}")
            else:
                print(f"  [{i}/{len(to_fill)}] {title}: (none)")

        time.sleep(0.025)  # ~40 req/sec, under TMDB's 50/sec limit

    print(f"\nDone. Updated: {updated}, Failed: {failed}")
    with_kw = sum(1 for m in movies if m.get('keywords'))
    print(f"Total movies with keywords: {with_kw}/{len(movies)}")

    with open(DATA_PATH, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("data.json written.")

if __name__ == '__main__':
    main()
