#!/usr/bin/env python3
"""
Phase B: Find RT URLs and scores for movies without RT links.
Uses HybridRTFinder (Gemini + Playwright validation).
Saves checkpoints every 25 movies.
"""

import json
import sys
import time
import signal
import traceback
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import load_env
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

# Timeout handler for per-movie processing
class MovieTimeout(Exception):
    pass

def timeout_handler(signum, frame):
    raise MovieTimeout("Timed out processing movie")

def main():
    data_path = project_root / 'data.json'

    with open(data_path) as f:
        data = json.load(f)

    movies = data['movies']

    # Find movies without RT links
    to_process = [(i, m) for i, m in enumerate(movies) if not m.get('links', {}).get('rt')]

    print(f"Phase B: {len(to_process)} movies without RT URLs")
    print("=" * 60)
    sys.stdout.flush()

    from gemini_scraper import HybridRTFinder
    finder = HybridRTFinder()

    stats = {'urls_found': 0, 'scores_found': 0, 'not_found': 0, 'errors': 0, 'timeouts': 0}

    for idx, (i, movie) in enumerate(to_process):
        title = movie.get('title', 'Unknown')
        year = movie.get('year', '')
        director = movie.get('crew', {}).get('director')

        # Set 90-second timeout per movie
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(90)

        try:
            result = finder.find_rt_score(title, year, director=director)

            if result:
                url = result.get('url')
                score = result.get('score')

                if url and '/m/' in url:
                    if 'links' not in movies[i]:
                        movies[i]['links'] = {}
                    movies[i]['links']['rt'] = url
                    stats['urls_found'] += 1

                    slug = url.split('/m/')[-1] if '/m/' in url else '?'

                    if score:
                        movies[i]['rt_score'] = score
                        stats['scores_found'] += 1
                        print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> {slug} | {score}")
                    else:
                        print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> {slug} | None")
                else:
                    stats['not_found'] += 1
                    print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> not found")
            else:
                stats['not_found'] += 1
                print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> not found")

        except MovieTimeout:
            stats['timeouts'] += 1
            print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> TIMEOUT (skipped)")

        except Exception as e:
            stats['errors'] += 1
            print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> ERROR: {e}")
            if '429' in str(e) or 'quota' in str(e).lower():
                print("Rate limited, waiting 60s...")
                time.sleep(60)

        finally:
            signal.alarm(0)  # Cancel alarm

        sys.stdout.flush()

        # Checkpoint every 25 movies
        if (idx + 1) % 25 == 0 and stats['urls_found'] > 0:
            with open(data_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  [checkpoint saved at {idx+1}]")
            sys.stdout.flush()

    # Final save
    if stats['urls_found'] > 0:
        with open(data_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 60)
    print(f"Phase B Complete")
    print(f"  URLs found:  {stats['urls_found']}")
    print(f"  Scores found: {stats['scores_found']}")
    print(f"  Not found:   {stats['not_found']}")
    print(f"  Timeouts:    {stats['timeouts']}")
    print(f"  Errors:      {stats['errors']}")
    print("Data saved to data.json")


if __name__ == '__main__':
    main()
