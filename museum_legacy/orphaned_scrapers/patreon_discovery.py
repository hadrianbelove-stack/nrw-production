#!/usr/bin/env python3
"""
Standalone script for Patreon film discovery.
Usage: python3 patreon_discovery.py --max-creators 20 --output patreon_discoveries.json
"""

import argparse
import json
import sys
import time
from datetime import datetime

from patreon_film_scraper import PatreonFilmScraper
from constants import get_scraper_config


def main():
    parser = argparse.ArgumentParser(description='Discover indie films from Patreon creators')
    parser.add_argument('--max-creators', type=int, default=20,
                        help='Number of creators to scrape (default: 20)')
    parser.add_argument('--output', default='patreon_discoveries.json',
                        help='Output JSON file path (default: patreon_discoveries.json)')
    parser.add_argument('--search-terms',
                        help='Comma-separated list of search terms (e.g., film,documentary,movie)')
    parser.add_argument('--min-runtime', type=int, default=10,
                        help='Minimum runtime filter in minutes (default: 10)')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='Run browser in headless mode (default: true)')
    parser.add_argument('--no-headless', action='store_false', dest='headless',
                        help='Run browser with GUI (useful for debugging)')
    parser.add_argument('--no-tmdb', action='store_true',
                        help='Skip TMDB cross-referencing (faster but less data)')
    parser.add_argument('--known-creators-only', action='store_true',
                        help='Only scrape known film creators, skip search')

    args = parser.parse_args()

    # Load configuration
    try:
        import yaml
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Warning: Could not load config.yaml: {e}")
        config = {}

    scraper_config = get_scraper_config(config, "patreon_scraper")

    # Override config with command line arguments
    if args.search_terms:
        scraper_config['discovery']['search_terms'] = [t.strip() for t in args.search_terms.split(',')]

    scraper_config['discovery']['max_creators'] = args.max_creators
    scraper_config['discovery']['min_runtime'] = args.min_runtime

    print("🎬 Patreon Film Discovery")
    print("=" * 40)
    print(f"Max creators: {args.max_creators}")
    print(f"Min runtime: {args.min_runtime} minutes")
    print(f"Search terms: {scraper_config['discovery'].get('search_terms', [])}")
    print(f"Headless mode: {args.headless}")
    print(f"TMDB cross-reference: {not args.no_tmdb}")
    print(f"Known creators only: {args.known_creators_only}")
    print()

    # Initialize scraper
    scraper = PatreonFilmScraper(
        config=scraper_config,
        headless=args.headless
    )

    try:
        start_time = time.time()

        if args.known_creators_only:
            print("🔍 Using known film creators only...")
            films = []
            for creator in scraper.known_film_creators[:args.max_creators]:
                try:
                    creator_films = scraper._scrape_creator_page(creator)
                    films.extend(creator_films)
                except Exception as e:
                    print(f"Error scraping {creator}: {e}")
            print(f"Found {len(films)} films from known creators")
        else:
            print("🔍 Discovering films from Patreon...")
            films = scraper.discover_films(max_creators=args.max_creators)

        if not films:
            print("😢 No films found")
            return 0

        print(f"\n📊 Found {len(films)} films")

        # Cross-reference with TMDB if requested
        if not args.no_tmdb:
            films = scraper.cross_reference_tmdb(films)

        # Add metadata
        discovery_data = {
            'discovery_date': datetime.now().isoformat(),
            'total_films': len(films),
            'search_config': {
                'max_creators': args.max_creators,
                'min_runtime': args.min_runtime,
                'search_terms': scraper_config['discovery'].get('search_terms', []),
                'known_creators_only': args.known_creators_only
            },
            'films': films
        }

        # Save results
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(discovery_data, f, indent=2, ensure_ascii=False)

        elapsed_time = time.time() - start_time
        print(f"\n✅ Discovery complete in {elapsed_time:.1f}s")
        print(f"📁 Results saved to {args.output}")

        # Print summary
        print(f"\n📈 Summary:")
        print(f"   Total films: {len(films)}")

        # Creator breakdown
        creators = {}
        for film in films:
            creator = film.get('creator_username', 'unknown')
            creators[creator] = creators.get(creator, 0) + 1

        print(f"   Creators: {len(creators)}")
        top_creators = sorted(creators.items(), key=lambda x: x[1], reverse=True)[:5]
        for creator, count in top_creators:
            print(f"     {creator}: {count} films")

        # Category breakdown
        categories = {}
        for film in films:
            film_cats = film.get('categories', [])
            for cat in film_cats:
                categories[cat] = categories.get(cat, 0) + 1

        if categories:
            print(f"   Categories:")
            top_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat, count in top_cats:
                print(f"     {cat}: {count} films")

        # TMDB match summary
        if not args.no_tmdb:
            tmdb_matches = {}
            for film in films:
                confidence = film.get('tmdb_match_confidence', 'none')
                tmdb_matches[confidence] = tmdb_matches.get(confidence, 0) + 1

            print(f"   TMDB matches:")
            for confidence, count in sorted(tmdb_matches.items()):
                print(f"     {confidence}: {count} films")

        return 0

    except KeyboardInterrupt:
        print("\n❌ Discovery interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error during discovery: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())