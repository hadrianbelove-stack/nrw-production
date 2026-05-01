#!/usr/bin/env python3
"""
Standalone script for Letterboxd Video Store film discovery.

Usage:
    python3 letterboxd_discovery.py
    python3 letterboxd_discovery.py --sections unreleased-gems,lost-and-found
    python3 letterboxd_discovery.py --output letterboxd_films.json --verbose
"""

import argparse
import json
import sys
import time
from datetime import datetime

from letterboxd_scraper import LetterboxdScraper
from constants import get_scraper_config


def main():
    parser = argparse.ArgumentParser(description='Discover films from Letterboxd Video Store')
    parser.add_argument('--sections', type=str,
                        help='Comma-separated sections to scrape (default: all). Options: unreleased-gems, lost-and-found, new-releases')
    parser.add_argument('--output', default='letterboxd_discoveries.json',
                        help='Output JSON file path (default: letterboxd_discoveries.json)')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='Run browser in headless mode (default: true)')
    parser.add_argument('--no-headless', action='store_false', dest='headless',
                        help='Run browser with GUI (useful for debugging)')
    parser.add_argument('--cache-file', default='cache/letterboxd_cache.json',
                        help='Cache file path (default: cache/letterboxd_cache.json)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('--add-to-data', action='store_true',
                        help='Add discovered films to data.json (with Letterboxd rent links)')

    args = parser.parse_args()

    # Load configuration
    try:
        import yaml
        with open('config.yaml', 'r') as f:
            full_config = yaml.safe_load(f)
        config = get_scraper_config(full_config, "letterboxd_scraper")
    except Exception:
        from constants import SCRAPER_DEFAULTS
        config = SCRAPER_DEFAULTS.copy()
        config['discovery'] = {
            'sections': ['unreleased-gems', 'lost-and-found', 'new-releases'],
            'min_runtime': 60
        }

    # Parse sections
    sections = None
    if args.sections:
        sections = [s.strip() for s in args.sections.split(',')]

    print("=" * 60)
    print("Letterboxd Video Store Discovery")
    print("=" * 60)
    print(f"Sections: {sections or 'all'}")
    print(f"Output file: {args.output}")
    print(f"Headless mode: {args.headless}")
    print(f"Cache file: {args.cache_file}")
    print("-" * 60)

    start_time = time.time()

    try:
        # Initialize scraper
        scraper = LetterboxdScraper(
            cache_file=args.cache_file,
            config=config,
            headless=args.headless
        )

        # Discover films
        print("\nStarting Letterboxd Video Store discovery...")
        films = scraper.discover_films(sections=sections)

        # Save results
        print(f"\nSaving {len(films)} films to {args.output}")
        output_data = {
            'source': 'letterboxd_video_store',
            'scraped_at': datetime.now().isoformat(),
            'sections': sections or list(LetterboxdScraper.SECTIONS.keys()),
            'count': len(films),
            'films': films
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        # Print summary
        total_time = time.time() - start_time
        tmdb_matches = [f for f in films if f.get('tmdb_match_confidence') != 'none']
        high_confidence = [f for f in films if f.get('tmdb_match_confidence') == 'high']
        medium_confidence = [f for f in films if f.get('tmdb_match_confidence') == 'medium']

        print("\n" + "=" * 60)
        print("DISCOVERY SUMMARY")
        print("=" * 60)
        print(f"Total films discovered: {len(films)}")
        pct = (len(tmdb_matches)/len(films)*100) if films else 0
        print(f"TMDB matches: {len(tmdb_matches)} ({pct:.1f}%)")
        print(f"  High confidence: {len(high_confidence)}")
        print(f"  Medium confidence: {len(medium_confidence)}")
        print(f"  No match: {len(films) - len(tmdb_matches)}")
        print(f"Discovery time: {total_time:.1f} seconds")
        print(f"Output saved to: {args.output}")

        # Show discoveries by section
        print("\nBy Section:")
        for section in set(f.get('section', 'unknown') for f in films):
            count = len([f for f in films if f.get('section') == section])
            print(f"  {section}: {count} films")

        # Show sample discoveries
        if args.verbose and films:
            print("\n" + "-" * 60)
            print("DISCOVERED FILMS:")
            print("-" * 60)
            for i, film in enumerate(films, 1):
                print(f"\n{i}. {film['title']}")
                if film.get('year'):
                    print(f"   Year: {film['year']}")
                if film.get('section'):
                    print(f"   Section: {film['section']}")
                print(f"   TMDB: {film.get('tmdb_match_confidence', 'none')}")
                if film.get('tmdb_id'):
                    print(f"   TMDB ID: {film['tmdb_id']}")
                if film.get('letterboxd_url'):
                    print(f"   Letterboxd: {film['letterboxd_url']}")
                if film.get('rent_link'):
                    print(f"   Rent Link: {film['rent_link']}")

        # Optionally add to data.json
        if args.add_to_data and films:
            added = add_films_to_data(films, verbose=args.verbose)
            print(f"\nAdded {added} new films to data.json")

        return 0

    except KeyboardInterrupt:
        print("\nDiscovery interrupted by user")
        return 1
    except Exception as e:
        print(f"\nError during discovery: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def add_films_to_data(films: list, verbose: bool = False) -> int:
    """Add discovered films to data.json with Letterboxd as rent source."""
    try:
        with open('data.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("data.json not found")
        return 0

    existing_ids = {m['id'] for m in data['movies']}
    existing_titles = {m['title'].lower() for m in data['movies']}

    added = 0
    now = datetime.now().isoformat()

    for film in films:
        # Skip if no TMDB match
        if film.get('tmdb_match_confidence') not in ['high', 'medium']:
            if verbose:
                print(f"Skipping {film['title']} - no TMDB match")
            continue

        tmdb_id = film.get('tmdb_id')
        if not tmdb_id:
            continue

        # Skip if already exists
        if tmdb_id in existing_ids or film['title'].lower() in existing_titles:
            if verbose:
                print(f"Skipping {film['title']} - already in data.json")
            continue

        # Create entry
        entry = {
            'id': tmdb_id,
            'title': film['title'],
            'digital_date': datetime.now().strftime('%Y-%m-%d'),
            'bootstrap_date': False,
            'manually_corrected': False,
            'synopsis': film.get('tmdb_overview', ''),
            'genres': [],
            'runtime': film.get('runtime', 90),
            'year': film.get('year', datetime.now().year),
            'rt_score': None,
            'providers': {
                'rent': ['Letterboxd Video Store'],
                'buy': [],
                'streaming': []
            },
            'links': {
                'trailer': None,
                'rt': None
            },
            'watch_links': {
                'vod': {
                    'service': 'Letterboxd',
                    'link': film.get('rent_link') or film.get('letterboxd_url')
                }
            },
            '_enrichment_status': 'pending',
            '_discovered_at': now,
            '_tmdb_fetch_failed': False,
            '_minimal_entry': True,
            'poster': f"https://image.tmdb.org/t/p/w500{film['tmdb_poster']}" if film.get('tmdb_poster') else None,
            '_discovery_source': 'letterboxd_video_store',
            '_digital_date_source': 'letterboxd_video_store'
        }

        data['movies'].append(entry)
        existing_ids.add(tmdb_id)
        added += 1

        if verbose:
            print(f"Added: {film['title']}")

    if added > 0:
        data['count'] = len(data['movies'])
        data['generated_at'] = now

        with open('data.json', 'w') as f:
            json.dump(data, f, indent=2)

    return added


if __name__ == "__main__":
    sys.exit(main())
