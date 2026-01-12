#!/usr/bin/env python3
"""
Standalone script for Vimeo On Demand film discovery.
Usage: python3 vimeo_discovery.py --max-pages 10 --output vimeo_discoveries.json
"""

import argparse
import json
import sys
import time
from datetime import datetime

from vimeo_ondemand_scraper import VimeoOnDemandScraper
from constants import get_scraper_config


def main():
    parser = argparse.ArgumentParser(description='Discover indie films from Vimeo On Demand')
    parser.add_argument('--max-pages', type=int, default=5,
                        help='Number of browse pages to scrape (default: 5)')
    parser.add_argument('--output', default='vimeo_discoveries.json',
                        help='Output JSON file path (default: vimeo_discoveries.json)')
    parser.add_argument('--categories',
                        help='Comma-separated list of categories to scrape (e.g., drama,comedy)')
    parser.add_argument('--min-runtime', type=int, default=70,
                        help='Minimum runtime filter in minutes (default: 70)')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='Run browser in headless mode (default: true)')
    parser.add_argument('--no-headless', action='store_false', dest='headless',
                        help='Run browser with GUI (useful for debugging)')
    parser.add_argument('--cache-file', default='cache/vimeo_cache.json',
                        help='Cache file path (default: cache/vimeo_cache.json)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    # Load configuration
    try:
        import yaml
        with open('config.yaml', 'r') as f:
            full_config = yaml.safe_load(f)
        config = get_scraper_config(full_config, "vimeo_scraper")
    except Exception:
        # Fallback to defaults
        from constants import SCRAPER_DEFAULTS
        config = SCRAPER_DEFAULTS.copy()
        config['discovery'] = {
            'max_pages': 5,
            'min_runtime': 70,
            'categories': ["drama", "documentary", "comedy", "thriller"]
        }

    # Override config with command line arguments
    if args.categories:
        config['discovery']['categories'] = [cat.strip() for cat in args.categories.split(',')]

    config['discovery']['min_runtime'] = args.min_runtime

    print(f"Vimeo On Demand Discovery")
    print(f"Max pages: {args.max_pages}")
    print(f"Min runtime: {args.min_runtime} minutes")
    print(f"Categories: {config['discovery']['categories']}")
    print(f"Output file: {args.output}")
    print(f"Headless mode: {args.headless}")
    print(f"Cache file: {args.cache_file}")
    print("-" * 50)

    start_time = time.time()

    try:
        # Initialize scraper
        scraper = VimeoOnDemandScraper(
            cache_file=args.cache_file,
            config=config,
            headless=args.headless
        )

        # Discover films
        print("Starting Vimeo discovery...")
        films = scraper.discover_films(max_pages=args.max_pages)

        # Save results
        print(f"\nSaving {len(films)} films to {args.output}")
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(films, f, indent=2, ensure_ascii=False)

        # Print summary statistics
        total_time = time.time() - start_time
        tmdb_matches = [f for f in films if f.get('tmdb_match_confidence') != 'none']
        high_confidence = [f for f in films if f.get('tmdb_match_confidence') == 'high']
        medium_confidence = [f for f in films if f.get('tmdb_match_confidence') == 'medium']

        avg_runtime = sum(f.get('runtime', 0) for f in films) / len(films) if films else 0

        print("\n" + "=" * 50)
        print("DISCOVERY SUMMARY")
        print("=" * 50)
        print(f"Total films discovered: {len(films)}")
        print(f"TMDB matches: {len(tmdb_matches)} ({len(tmdb_matches)/len(films)*100:.1f}%)")
        print(f"  High confidence: {len(high_confidence)}")
        print(f"  Medium confidence: {len(medium_confidence)}")
        print(f"  No match: {len(films) - len(tmdb_matches)}")
        print(f"Average runtime: {avg_runtime:.0f} minutes")
        print(f"Discovery time: {total_time:.1f} seconds")
        print(f"Output saved to: {args.output}")

        # Show sample discoveries
        if args.verbose and films:
            print("\nSAMPLE DISCOVERIES:")
            print("-" * 30)
            for i, film in enumerate(films[:5], 1):
                print(f"{i}. {film['title']}")
                if film.get('filmmaker'):
                    print(f"   Director: {film['filmmaker']}")
                print(f"   Runtime: {film.get('runtime', 'Unknown')} min")
                print(f"   TMDB: {film.get('tmdb_match_confidence', 'none')}")
                print(f"   URL: {film.get('vimeo_url', 'N/A')}")
                if film.get('price_rent'):
                    print(f"   Rent: {film['price_rent']}")
                print()

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


if __name__ == "__main__":
    sys.exit(main())