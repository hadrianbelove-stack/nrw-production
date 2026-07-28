#!/usr/bin/env python3
"""
Batch Pull Quotes Scraper

Fetches pull quotes for current wall movies using PullQuoteFinder.
Results are cached and written to pull_quotes_combined.json for admin curation.

Usage:
    python3 scripts/batch_pull_quotes.py              # Default: 20 most recent movies
    python3 scripts/batch_pull_quotes.py --limit 50   # Process 50 movies
    python3 scripts/batch_pull_quotes.py --all         # Process all wall movies
    python3 scripts/batch_pull_quotes.py --force       # Re-scrape even if cached
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import load_env
from gemini_scraper import PullQuoteFinder

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

COMBINED_CACHE = 'cache/pull_quotes_combined.json'


def load_json(filepath, default=None):
    if default is None:
        default = {}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return default


def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def convert_to_combined_format(title, year, quotes):
    """Convert PullQuoteFinder results to pull_quotes_combined.json format."""
    rt_quotes = []
    lb_quotes = []

    for q in quotes:
        entry = {
            'text': q.get('text', ''),
            'critic': q.get('critic', ''),
            'outlet': q.get('outlet', ''),
            'source': q.get('source', 'critic'),
            'verbatim': True,
            'selected': q.get('selected', False),
            'fresh': None,
            'review_url': q.get('review_url', ''),
            'added_at': q.get('added_at', datetime.now().isoformat())
        }

        if q.get('source') == 'letterboxd':
            entry['source'] = 'letterboxd'
            entry['pull_quote'] = q.get('text', '')
            lb_quotes.append(entry)
        else:
            entry['source'] = 'rt_critic'
            rt_quotes.append(entry)

    return {
        'title': title,
        'year': year,
        'rt_quotes': rt_quotes,
        'lb_quotes': lb_quotes,
        'scraped_at': datetime.now().isoformat(),
        'scrape_method': 'gemini_pull_quote_finder'
    }


def main():
    parser = argparse.ArgumentParser(description='Batch scrape pull quotes for wall movies')
    parser.add_argument('--days', type=int, default=7,
                        help='Scrape films whose digital_date is within the last N days (default: 7, matches the '
                             'curate window). This is the normal limit — catches up across missed days, drops older films.')
    parser.add_argument('--limit', type=int, default=None,
                        help='Optional hard cap on movie count (default: none — the date window is the limit)')
    parser.add_argument('--all', action='store_true',
                        help='Ignore the date window — process every uncached wall movie')
    parser.add_argument('--force', action='store_true', help='Re-scrape even if cached')
    parser.add_argument('--backend', choices=['gemini', 'claude'], default=None,
                        help="Extraction backend: 'gemini' (paid API) or 'claude' "
                             "(local `claude -p` on the Max plan, ~$0). Playwright "
                             "scraping is unchanged. Default: $NRW_QUOTES_BACKEND or 'gemini'.")
    args = parser.parse_args()

    # PullQuoteFinder reads NRW_QUOTES_BACKEND at scrape time; --backend sets it.
    if args.backend:
        os.environ['NRW_QUOTES_BACKEND'] = args.backend

    # Load movies from data.json
    data = load_json('data.json', {})
    if isinstance(data, dict) and 'movies' in data:
        movies = data['movies']
    elif isinstance(data, list):
        movies = data
    else:
        logger.error("Could not load movies from data.json")
        return

    # Sort newest digital_date first (nice log order; the date window below is what
    # actually gates which films get scraped).
    from datetime import date as _date, timedelta as _timedelta
    _today = str(_date.today())
    _window_start = str(_date.today() - _timedelta(days=args.days))
    movies.sort(key=lambda m: (
        1 if (m.get('digital_date') or '') <= _today else 0,
        m.get('digital_date', '') or ''
    ), reverse=True)

    # Load existing combined cache
    combined = load_json(COMBINED_CACHE, {})

    # When --force, bust all three internal caches so stale results don't shadow
    # freshly scraped reviews (pull_quotes_cache, quote_extractions_cache, combined)
    if args.force:
        for cache_path in ['cache/pull_quotes_cache.json', 'cache/quote_extractions_cache.json']:
            c = load_json(cache_path, {})
            if c:
                json.dump({}, open(cache_path, 'w'))
                logger.info(f"--force: cleared {cache_path}")

    # Determine which movies to process. Normal mode: every uncached film whose
    # digital_date falls within the last --days days (catches up across a missed
    # run, drops anything older). --all ignores the window. --limit is an optional cap.
    to_process = []

    for m in movies:
        title = m.get('title', '')
        year = m.get('year', 0)
        if not title or not year:
            continue

        # Date window (skipped by --all): recent arrivals only — excludes old films
        # AND future-dated pre-orders (which have no reviews yet).
        if not args.all:
            dd = m.get('digital_date') or ''
            if not (_window_start <= dd <= _today):
                continue

        cache_key = f"{title}_{year}"

        # Skip if already in combined cache (unless --force).
        # Negative-cache entries (_no_quotes_tried, empty quotes) are retried
        # after 14 days — reviews often appear weeks after release.
        if not args.force and cache_key in combined:
            entry = combined[cache_key]
            tried = entry.get('_no_quotes_tried', '') if isinstance(entry, dict) else ''
            if tried:
                try:
                    days_ago = (_date.today() - _date.fromisoformat(tried)).days
                except ValueError:
                    days_ago = 0
                if days_ago < 14:
                    continue
            else:
                continue

        to_process.append(m)
        if args.limit is not None and len(to_process) >= args.limit:
            break

    if not to_process:
        logger.info("No movies to process (all cached). Use --force to re-scrape.")
        return

    logger.info(f"\n{'='*60}")
    logger.info(f"Batch Pull Quotes — {len(to_process)} movies")
    logger.info(f"{'='*60}\n")

    # Initialize finder
    finder = PullQuoteFinder()
    stats = {'processed': 0, 'with_quotes': 0, 'empty': 0, 'errors': 0}

    for i, movie in enumerate(to_process, 1):
        title = movie['title']
        year = movie.get('year', 0)
        director = None
        crew = movie.get('crew', {})
        if isinstance(crew, dict):
            director = crew.get('director')

        cache_key = f"{title}_{year}"
        rt_url = movie.get('links', {}).get('rt', '')
        mc_url = movie.get('links', {}).get('metacritic', '')
        lb_url = movie.get('links', {}).get('letterboxd', '')

        logger.info(f"[{i}/{len(to_process)}] {title} ({year})...")

        try:
            # Direct call — no thread wrapper. Hang protection lives in two
            # layers: every Gemini request has a 120s timeout (base.py) and
            # all Playwright page loads have their own timeouts; local_daily.sh
            # additionally hard-kills this script after 1 hour.
            quotes = finder.find_pull_quotes(
                title, year,
                director=director, rt_url=rt_url, mc_url=mc_url, lb_url=lb_url
            )

            if quotes:
                # Write to combined cache in admin-compatible format
                combined[cache_key] = convert_to_combined_format(title, year, quotes)
                stats['with_quotes'] += 1
                rt_count = sum(1 for q in quotes if q.get('source') != 'letterboxd')
                lb_count = sum(1 for q in quotes if q.get('source') == 'letterboxd')
                logger.info(f"  → {len(quotes)} quotes (RT: {rt_count}, LB: {lb_count})")
            else:
                # Negative cache: remember the attempt so this movie doesn't
                # re-queue every night (retried after 14 days, see above)
                combined[cache_key] = {
                    'title': title,
                    'year': year,
                    'rt_quotes': [],
                    'lb_quotes': [],
                    'scraped_at': datetime.now().isoformat(),
                    'scrape_method': 'gemini_pull_quote_finder',
                    '_no_quotes_tried': str(_date.today()),
                }
                stats['empty'] += 1
                logger.info(f"  → No quotes found (negative-cached for 14 days)")

            stats['processed'] += 1

        except Exception as e:
            stats['errors'] += 1
            logger.error(f"  → Error: {e}")

        # Save combined cache periodically (every 10 movies)
        if i % 10 == 0:
            save_json(COMBINED_CACHE, combined)
            logger.info(f"  [Cache saved: {len(combined)} movies total]")

    # Final save
    save_json(COMBINED_CACHE, combined)

    logger.info(f"\n{'='*60}")
    logger.info(f"Done! Processed: {stats['processed']}, "
                f"With quotes: {stats['with_quotes']}, "
                f"Empty: {stats['empty']}, "
                f"Errors: {stats['errors']}")
    logger.info(f"Combined cache: {len(combined)} movies total")
    logger.info(f"{'='*60}\n")


if __name__ == '__main__':
    main()
