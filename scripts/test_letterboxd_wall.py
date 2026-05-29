#!/usr/bin/env python3
"""Test Letterboxd scraper against all movies on the wall.

Runs through data.json, scrapes each movie, and reports results.
Uses the cache, so subsequent runs skip already-found movies.
"""

import json
import sys
import time
import yaml

sys.path.insert(0, '.')
from letterboxd_scraper import LetterboxdScraper

# Load config
config = {}
try:
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f) or {}
except Exception:
    pass

# Load movies
with open('data.json', 'r') as f:
    data = json.load(f)

movies = data.get('movies', [])
print(f"Testing Letterboxd scraper on {len(movies)} movies\n")

scraper = LetterboxdScraper(config=config)

found = 0
not_found = 0
cached = 0
errors = []
start = time.time()

for i, movie in enumerate(movies, 1):
    title = movie.get('title', '?')
    year = movie.get('year', 0)
    if not year:
        not_found += 1
        continue

    old_cache_hits = scraper.stats['cache_hits']
    result = scraper.scrape_letterboxd_score(title, year)
    was_cached = scraper.stats['cache_hits'] > old_cache_hits

    if result and result.get('url'):
        found += 1
        score_str = result.get('score') or 'no rating'
        status = '(cached)' if was_cached else ''
        if not was_cached:
            print(f"  [{i}/{len(movies)}] {title} ({year}) → {score_str} {status}")
    else:
        not_found += 1
        if not was_cached:
            print(f"  [{i}/{len(movies)}] {title} ({year}) → NOT FOUND")

    if was_cached:
        cached += 1

    # Progress every 50
    if i % 50 == 0:
        elapsed = time.time() - start
        print(f"  --- {i}/{len(movies)} processed ({elapsed:.0f}s elapsed) ---")

elapsed = time.time() - start
stats = scraper.get_stats()

print(f"\n{'='*60}")
print(f"Results:")
print(f"  Total movies:  {len(movies)}")
print(f"  Found:         {found} ({found/len(movies)*100:.1f}%)")
print(f"  Not found:     {not_found}")
print(f"  Cache hits:    {cached}")
print(f"  New lookups:   {stats['attempts']}")
print(f"  Time:          {elapsed:.0f}s")
print(f"{'='*60}")
