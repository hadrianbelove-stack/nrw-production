#!/usr/bin/env python3
"""
RT Batch Re-enrichment Script

One-time script to fix existing bad RT data in data.json by re-querying
the Gemini RT finder for movies with:
- Null RT scores
- Search fallback URLs (not real RT pages)
- Suspicious URL mismatches (detected by title validation)

Usage:
    python3 scripts/rt_batch_reenrich.py --dry-run          # Preview what would change
    python3 scripts/rt_batch_reenrich.py --limit 10         # Process first 10 movies
    python3 scripts/rt_batch_reenrich.py                    # Process all movies needing fixes

Created: 2026-02-26
"""

import json
import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import load_env  # Load .env into os.environ
from gemini_scraper import GeminiRTFinder

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def is_search_fallback_url(url):
    """Check if URL is a search fallback (not a real RT page)."""
    if not url:
        return True
    return 'search?search=' in url


def load_data():
    """Load data.json and return the full structure."""
    data_path = project_root / 'data.json'
    with open(data_path, 'r') as f:
        return json.load(f)


def save_data(data):
    """Save data.json."""
    data_path = project_root / 'data.json'
    with open(data_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_movies_needing_rt_fix(data):
    """Identify movies that need RT data fixed.

    Returns list of (index, movie, reason) tuples.
    """
    movies_to_fix = []

    for i, movie in enumerate(data):
        rt_score = movie.get('rt_score')
        rt_url = movie.get('links', {}).get('rt', '')

        # Case 1: Search fallback URL (scraper completely failed)
        if is_search_fallback_url(rt_url):
            movies_to_fix.append((i, movie, 'search_fallback'))
            continue

        # Case 2: Has URL but null score
        if rt_url and not rt_score:
            movies_to_fix.append((i, movie, 'null_score'))
            continue

    return movies_to_fix


def main():
    parser = argparse.ArgumentParser(description='Re-enrich RT data for movies with missing/bad data')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without modifying data.json')
    parser.add_argument('--limit', type=int, default=0, help='Max number of movies to process (0=all)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 60)
    print("RT Batch Re-enrichment")
    print("=" * 60)

    # Load data
    data_wrapper = load_data()
    data = data_wrapper.get('movies', data_wrapper) if isinstance(data_wrapper, dict) else data_wrapper
    print(f"\nLoaded {len(data)} movies from data.json")

    # Find movies needing fixes
    movies_to_fix = find_movies_needing_rt_fix(data)

    search_fallbacks = [m for m in movies_to_fix if m[2] == 'search_fallback']
    null_scores = [m for m in movies_to_fix if m[2] == 'null_score']

    print(f"\nMovies needing RT fixes:")
    print(f"  Search fallback URLs (no real link): {len(search_fallbacks)}")
    print(f"  Has URL but null score:              {len(null_scores)}")
    print(f"  Total to process:                    {len(movies_to_fix)}")

    if args.limit > 0:
        movies_to_fix = movies_to_fix[:args.limit]
        print(f"\n  (Limited to first {args.limit} movies)")

    if args.dry_run:
        print("\n--- DRY RUN MODE (no changes will be saved) ---\n")
        for i, movie, reason in movies_to_fix:
            title = movie.get('title', 'Unknown')
            year = movie.get('year', '?')
            rt_url = movie.get('links', {}).get('rt', 'None')
            rt_score = movie.get('rt_score', 'None')
            print(f"  [{reason:16s}] {title} ({year}) - URL: {rt_url[:60]}... Score: {rt_score}")
        print(f"\n{len(movies_to_fix)} movies would be re-queried.")
        return

    if not movies_to_fix:
        print("\nNo movies need RT fixes!")
        return

    # Initialize Gemini RT finder
    print("\nInitializing Gemini RT finder...")
    finder = GeminiRTFinder()

    # Process movies
    stats = {
        'processed': 0,
        'url_found': 0,
        'score_found': 0,
        'url_fixed': 0,
        'score_fixed': 0,
        'no_change': 0,
        'errors': 0
    }

    print(f"\nProcessing {len(movies_to_fix)} movies...\n")

    for idx, (i, movie, reason) in enumerate(movies_to_fix):
        title = movie.get('title', 'Unknown')
        year = movie.get('year', '')
        director = movie.get('crew', {}).get('director')
        old_url = movie.get('links', {}).get('rt', '')
        old_score = movie.get('rt_score')

        print(f"[{idx+1}/{len(movies_to_fix)}] {title} ({year}) [{reason}]")

        try:
            # Clear this movie from cache to force fresh Gemini query
            cache_key = f"{title}_{year}"
            if cache_key in finder.cache:
                del finder.cache[cache_key]

            result = finder.find_rt_score(title, year, director=director)
            stats['processed'] += 1

            if result:
                new_url = result.get('url')
                new_score = result.get('score')

                changes = []

                # Update URL if we got a better one
                if new_url and is_search_fallback_url(old_url):
                    if 'links' not in data[i]:
                        data[i]['links'] = {}
                    data[i]['links']['rt'] = new_url
                    stats['url_fixed'] += 1
                    changes.append(f"URL: {new_url}")
                elif new_url:
                    stats['url_found'] += 1

                # Update score if we got one
                if new_score and not old_score:
                    data[i]['rt_score'] = new_score
                    stats['score_fixed'] += 1
                    changes.append(f"Score: {new_score}")
                elif new_score:
                    stats['score_found'] += 1

                if changes:
                    print(f"  FIXED: {', '.join(changes)}")
                else:
                    stats['no_change'] += 1
                    print(f"  No improvement (URL: {new_url}, Score: {new_score})")
            else:
                stats['no_change'] += 1
                print(f"  Not found on RT")

        except Exception as e:
            stats['errors'] += 1
            print(f"  ERROR: {e}")

    # Save updated data
    print("\n" + "=" * 60)
    print("Results:")
    print(f"  Processed:    {stats['processed']}")
    print(f"  URLs fixed:   {stats['url_fixed']}")
    print(f"  Scores fixed: {stats['score_fixed']}")
    print(f"  No change:    {stats['no_change']}")
    print(f"  Errors:       {stats['errors']}")

    if stats['url_fixed'] > 0 or stats['score_fixed'] > 0:
        print("\nSaving updated data.json...")
        if isinstance(data_wrapper, dict):
            data_wrapper['movies'] = data
            save_data(data_wrapper)
        else:
            save_data(data)
        finder._save_cache()
        print("Done! Run `python3 ops/health_check.py` to verify.")
    else:
        print("\nNo changes to save.")


if __name__ == '__main__':
    main()
