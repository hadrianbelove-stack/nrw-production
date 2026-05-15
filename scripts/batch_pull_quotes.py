#!/usr/bin/env python3
"""
Batch Pull Quotes Scraper

Fetches pull quotes for current wall movies using GeminiPullQuoteFinder.
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
from gemini_scraper import GeminiPullQuoteFinder

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
    """Convert GeminiPullQuoteFinder results to pull_quotes_combined.json format."""
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
    parser.add_argument('--limit', type=int, default=20, help='Number of movies to process (default: 20)')
    parser.add_argument('--all', action='store_true', help='Process all wall movies')
    parser.add_argument('--force', action='store_true', help='Re-scrape even if cached')
    args = parser.parse_args()

    # Load movies from data.json
    data = load_json('data.json', {})
    if isinstance(data, dict) and 'movies' in data:
        movies = data['movies']
    elif isinstance(data, list):
        movies = data
    else:
        logger.error("Could not load movies from data.json")
        return

    # Sort by most recent digital_date
    movies.sort(key=lambda m: m.get('digital_date', '') or '', reverse=True)

    # Load existing combined cache
    combined = load_json(COMBINED_CACHE, {})

    # Determine which movies to process
    limit = len(movies) if args.all else args.limit
    to_process = []

    for m in movies:
        title = m.get('title', '')
        year = m.get('year', 0)
        if not title or not year:
            continue

        cache_key = f"{title}_{year}"

        # Skip if already in combined cache (unless --force)
        if not args.force and cache_key in combined:
            continue

        to_process.append(m)
        if len(to_process) >= limit:
            break

    if not to_process:
        logger.info("No movies to process (all cached). Use --force to re-scrape.")
        return

    logger.info(f"\n{'='*60}")
    logger.info(f"Batch Pull Quotes — {len(to_process)} movies")
    logger.info(f"{'='*60}\n")

    # Initialize finder
    finder = GeminiPullQuoteFinder()
    stats = {'processed': 0, 'with_quotes': 0, 'empty': 0, 'errors': 0}

    for i, movie in enumerate(to_process, 1):
        title = movie['title']
        year = movie.get('year', 0)
        director = None
        crew = movie.get('crew', {})
        if isinstance(crew, dict):
            director = crew.get('director')

        cache_key = f"{title}_{year}"

        logger.info(f"[{i}/{len(to_process)}] {title} ({year})...")

        try:
            quotes = finder.find_pull_quotes(title, year, director=director)

            if quotes:
                # Write to combined cache in admin-compatible format
                combined[cache_key] = convert_to_combined_format(title, year, quotes)
                stats['with_quotes'] += 1
                rt_count = sum(1 for q in quotes if q.get('source') != 'letterboxd')
                lb_count = sum(1 for q in quotes if q.get('source') == 'letterboxd')
                logger.info(f"  → {len(quotes)} quotes (RT: {rt_count}, LB: {lb_count})")
            else:
                stats['empty'] += 1
                logger.info(f"  → No quotes found")

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
