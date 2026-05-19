#!/usr/bin/env python3
"""
RT Full Validation + Rerun Script

Phase 1: Validate all existing RT links (check for 404s, wrong movies)
Phase 2: Re-attempt finding URLs for movies without links (with improved matching)
Phase 3: Report summary

Usage:
    python3 scripts/rt_full_validate.py              # Full run
    python3 scripts/rt_full_validate.py --validate    # Phase 1 only (validate existing)
    python3 scripts/rt_full_validate.py --enrich      # Phase 2 only (find missing)
    python3 scripts/rt_full_validate.py --dry-run     # Preview without saving
"""

import html
import json
import re
import sys
import time
import signal
import argparse
import logging
import requests
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import load_env
from gemini_scraper.rt_validation import page_title_matches

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class MovieTimeout(Exception):
    pass


def timeout_handler(signum, frame):
    raise MovieTimeout("Timed out processing movie")


def load_data():
    data_path = project_root / 'data.json'
    with open(data_path) as f:
        return json.load(f)


def save_data(data):
    data_path = project_root / 'data.json'
    with open(data_path, 'w') as f:
        json.dump(data, f, indent=2)


def phase1_validate(data, dry_run=False):
    """Validate all existing RT links using HTTP HEAD requests."""
    movies = data['movies']
    with_links = [(i, m) for i, m in enumerate(movies) if m.get('links', {}).get('rt')]

    print(f"\n{'='*60}")
    print(f"Phase 1: Validating {len(with_links)} existing RT links")
    print(f"{'='*60}\n")

    if not with_links:
        print("No links to validate.")
        return {'checked': 0, 'valid': 0, 'invalid': 0}

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })

    stats = {'checked': 0, 'valid': 0, 'invalid': 0, 'mismatches': 0, 'errors': 0}
    invalid_movies = []
    mismatched_movies = []

    for idx, (i, movie) in enumerate(with_links):
        title = movie['title']
        url = movie['links']['rt']
        stats['checked'] += 1

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)

        try:
            response = session.get(url, timeout=10, allow_redirects=True)

            if response.status_code >= 400:
                stats['invalid'] += 1
                reason = f"HTTP {response.status_code}"
                invalid_movies.append((title, movie.get('year'), url, reason))
                print(f"  INVALID: {title} ({movie.get('year')}) -> {url} [{reason}]")

                if not dry_run:
                    movies[i]['links']['rt'] = None
                    movies[i]['rt_score'] = None
            else:
                # Title verification: extract page title from HTML
                title_tag = re.search(r'<title>(.*?)</title>', response.text[:4096], re.IGNORECASE | re.DOTALL)
                if title_tag:
                    page_title_text = html.unescape(title_tag.group(1).strip())
                    # RT format: "Movie Name (YYYY) | Rotten Tomatoes"
                    movie_part = page_title_text.split('|')[0].strip() if '|' in page_title_text else page_title_text.strip()
                    page_movie_title = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_part).strip()

                    if page_movie_title and not page_title_matches(page_movie_title, title):
                        stats['mismatches'] += 1
                        mismatched_movies.append((title, movie.get('year'), url, page_movie_title))
                        print(f"  MISMATCH: {title} ({movie.get('year')}) -> page shows '{page_movie_title}'")
                    else:
                        stats['valid'] += 1
                else:
                    # Could not extract title tag — count as valid (don't penalize)
                    stats['valid'] += 1

        except MovieTimeout:
            stats['errors'] += 1
            print(f"  TIMEOUT: {title} ({movie.get('year')}) -> {url}")
        except requests.RequestException as e:
            stats['errors'] += 1
            logger.debug(f"Error checking {title}: {e}")
        finally:
            signal.alarm(0)

        # Progress every 50
        if (idx + 1) % 50 == 0:
            print(f"  ... checked {idx+1}/{len(with_links)} ({stats['invalid']} invalid, {stats['mismatches']} mismatches so far)")

    print(f"\nPhase 1 Results:")
    print(f"  Checked:    {stats['checked']}")
    print(f"  Valid:      {stats['valid']}")
    print(f"  Invalid:    {stats['invalid']}")
    print(f"  Mismatches: {stats['mismatches']}")
    print(f"  Errors:     {stats['errors']}")

    if invalid_movies:
        print(f"\nInvalid links nulled out:")
        for title, year, url, reason in invalid_movies:
            print(f"  {title} ({year}): {url} [{reason}]")

    if mismatched_movies:
        print(f"\nTitle mismatches found (NOT auto-nulled — review manually):")
        for title, year, url, page_title_found in mismatched_movies:
            print(f"  {title} ({year}): {url}")
            print(f"    Page shows: '{page_title_found}'")

    return stats


def phase2_enrich(data, dry_run=False):
    """Find RT URLs for movies that don't have one."""
    from gemini_scraper import HybridRTFinder

    movies = data['movies']
    to_process = [(i, m) for i, m in enumerate(movies) if not m.get('links', {}).get('rt')]

    print(f"\n{'='*60}")
    print(f"Phase 2: Finding RT links for {len(to_process)} movies")
    print(f"{'='*60}\n")

    if not to_process:
        print("No movies need RT links.")
        return {'urls_found': 0, 'scores_found': 0, 'not_found': 0}

    finder = HybridRTFinder()

    stats = {'urls_found': 0, 'scores_found': 0, 'not_found': 0, 'errors': 0, 'timeouts': 0}

    for idx, (i, movie) in enumerate(to_process):
        title = movie.get('title', 'Unknown')
        year = movie.get('year', '')
        director = movie.get('crew', {}).get('director')
        original_language = movie.get('original_language')
        original_title = movie.get('original_title')

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(90)

        try:
            # Clear caches for fresh attempt with improved matching
            cache_key = f"{title}_{year}"
            if cache_key in finder.gemini_finder.cache:
                del finder.gemini_finder.cache[cache_key]
            if finder.playwright_scraper and cache_key in finder.playwright_scraper.cache:
                del finder.playwright_scraper.cache[cache_key]

            result = finder.find_rt_score(
                title, year,
                director=director,
                original_language=original_language,
                original_title=original_title
            )

            if result:
                url = result.get('url')
                score = result.get('score')

                if url and '/m/' in url:
                    stats['urls_found'] += 1
                    slug = url.split('/m/')[-1]

                    if not dry_run:
                        if 'links' not in movies[i]:
                            movies[i]['links'] = {}
                        movies[i]['links']['rt'] = url
                        if score:
                            movies[i]['rt_score'] = score
                            stats['scores_found'] += 1

                    print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> {slug} | {score or 'None'}")
                else:
                    stats['not_found'] += 1
                    print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> not found")
            else:
                stats['not_found'] += 1
                print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> not found")

        except MovieTimeout:
            stats['timeouts'] += 1
            print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> TIMEOUT")
        except Exception as e:
            stats['errors'] += 1
            print(f"[{idx+1}/{len(to_process)}] {title} ({year}) -> ERROR: {e}")
            if '429' in str(e) or 'quota' in str(e).lower():
                print("Rate limited, waiting 60s...")
                time.sleep(60)
        finally:
            signal.alarm(0)

        sys.stdout.flush()

        # Checkpoint every 25 movies
        if (idx + 1) % 25 == 0 and stats['urls_found'] > 0 and not dry_run:
            save_data(data)
            print(f"  [checkpoint saved at {idx+1}]")

    print(f"\nPhase 2 Results:")
    print(f"  URLs found:  {stats['urls_found']}")
    print(f"  Scores found: {stats['scores_found']}")
    print(f"  Not found:   {stats['not_found']}")
    print(f"  Timeouts:    {stats['timeouts']}")
    print(f"  Errors:      {stats['errors']}")

    return stats


def main():
    parser = argparse.ArgumentParser(description='Full RT validation and re-enrichment')
    parser.add_argument('--validate', action='store_true', help='Phase 1 only: validate existing links')
    parser.add_argument('--enrich', action='store_true', help='Phase 2 only: find missing links')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    args = parser.parse_args()

    # Default: run both phases
    run_validate = args.validate or (not args.validate and not args.enrich)
    run_enrich = args.enrich or (not args.validate and not args.enrich)

    data = load_data()
    movies = data['movies']

    total = len(movies)
    with_links = sum(1 for m in movies if m.get('links', {}).get('rt'))
    with_scores = sum(1 for m in movies if m.get('rt_score'))

    print(f"RT Full Validation")
    print(f"{'='*60}")
    print(f"Total movies:     {total}")
    print(f"With RT links:    {with_links}")
    print(f"With RT scores:   {with_scores}")
    print(f"Without RT links: {total - with_links}")
    if args.dry_run:
        print(f"\n*** DRY RUN — no changes will be saved ***")

    if run_validate:
        phase1_validate(data, dry_run=args.dry_run)
        if not args.dry_run:
            save_data(data)
            print("Phase 1 changes saved.")

    if run_enrich:
        phase2_enrich(data, dry_run=args.dry_run)
        if not args.dry_run:
            save_data(data)
            print("Phase 2 changes saved.")

    # Final summary
    with_links_after = sum(1 for m in movies if m.get('links', {}).get('rt'))
    with_scores_after = sum(1 for m in movies if m.get('rt_score'))

    print(f"\n{'='*60}")
    print(f"Final Summary")
    print(f"{'='*60}")
    print(f"RT links:  {with_links} -> {with_links_after}")
    print(f"RT scores: {with_scores} -> {with_scores_after}")
    print(f"\nRun `python3 ops/health_check.py` to verify.")


if __name__ == '__main__':
    main()
