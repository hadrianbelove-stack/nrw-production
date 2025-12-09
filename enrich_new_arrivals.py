#!/usr/bin/env python3
"""
Enrichment-only script for NRW pipeline.

This script ONLY enriches movies that:
1. Have status='available' (providers found)
2. Have a digital_date set
3. Are NOT already in enrichment_state.json

Can be run independently from discovery/check phases.
Supports batch processing to avoid memory issues with Playwright.

Usage:
    python3 enrich_new_arrivals.py              # Enrich all pending (default batch: 20)
    python3 enrich_new_arrivals.py --batch 10   # Enrich 10 movies
    python3 enrich_new_arrivals.py --list       # Just list what needs enrichment
    python3 enrich_new_arrivals.py --all        # Enrich all (no batch limit)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Force unbuffered output for real-time logging
os.environ['PYTHONUNBUFFERED'] = '1'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)


def load_json(filepath):
    """Load JSON file safely."""
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r') as f:
        return json.load(f)


def save_json(filepath, data):
    """Save JSON file."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def get_movies_needing_enrichment():
    """Find available movies that haven't been enriched yet."""
    tracking = load_json('movie_tracking.json')
    enrichment_state = load_json('enrichment_state.json')

    enriched_ids = set(enrichment_state.keys())

    needs_enrichment = []
    for movie_id, movie_data in tracking.get('movies', {}).items():
        # Only enrich movies that are available with a digital date
        if movie_data.get('status') == 'available' and movie_data.get('digital_date'):
            if movie_id not in enriched_ids:
                needs_enrichment.append((movie_id, movie_data))

    # Sort by digital_date (newest first)
    needs_enrichment.sort(key=lambda x: x[1].get('digital_date', ''), reverse=True)

    return needs_enrichment, len(enriched_ids)


def list_pending():
    """List movies that need enrichment."""
    needs_enrichment, enriched_count = get_movies_needing_enrichment()

    print(f"\n{'='*60}")
    print(f"ENRICHMENT STATUS")
    print(f"{'='*60}")
    print(f"Already enriched: {enriched_count}")
    print(f"Need enrichment:  {len(needs_enrichment)}")
    print(f"{'='*60}\n")

    if not needs_enrichment:
        print("All available movies are enriched!")
        return

    print("Movies needing enrichment (newest first):\n")
    for i, (movie_id, movie_data) in enumerate(needs_enrichment, 1):
        title = movie_data.get('title', 'Unknown')
        digital_date = movie_data.get('digital_date', 'N/A')
        providers = movie_data.get('providers', {})
        # providers is a dict with 'streaming', 'rent', 'buy' keys
        all_providers = []
        if isinstance(providers, dict):
            all_providers = providers.get('streaming', []) + providers.get('rent', []) + providers.get('buy', [])
        elif isinstance(providers, list):
            all_providers = providers
        provider_str = ', '.join(all_providers[:3]) if all_providers else 'Unknown'
        print(f"  {i:3}. [{movie_id}] {title}")
        print(f"       Date: {digital_date} | Providers: {provider_str}")

    print(f"\nTotal: {len(needs_enrichment)} movies need enrichment")


def run_enrichment(batch_size=20, no_limit=False):
    """Run enrichment for pending movies."""
    needs_enrichment, enriched_count = get_movies_needing_enrichment()

    if not needs_enrichment:
        print("All available movies are already enriched!")
        return True

    total_pending = len(needs_enrichment)

    # Apply batch limit unless --all specified
    if not no_limit and batch_size and len(needs_enrichment) > batch_size:
        needs_enrichment = needs_enrichment[:batch_size]
        print(f"\nBatch mode: Processing {batch_size} of {total_pending} pending movies")
        print(f"Run again to process more, or use --all for no limit\n")

    print(f"\n{'='*60}")
    print(f"ENRICHMENT RUN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    print(f"Already enriched: {enriched_count}")
    print(f"To process:       {len(needs_enrichment)}")
    print(f"Remaining after:  {total_pending - len(needs_enrichment)}")
    print(f"{'='*60}\n")

    # Import the generator (heavy imports, do lazily)
    print("Initializing enrichment pipeline...")
    try:
        from pipeline.generator import DataGenerator

        generator = DataGenerator(enrichment_enabled=True)

    except Exception as e:
        print(f"Failed to initialize generator: {e}")
        return False

    # Load enrichment state for updating
    enrichment_state = load_json('enrichment_state.json')

    # Process each movie
    success_count = 0
    fail_count = 0

    for i, (movie_id, movie_data) in enumerate(needs_enrichment, 1):
        title = movie_data.get('title', 'Unknown')
        print(f"\n[{i}/{len(needs_enrichment)}] Enriching: {title}")

        try:
            # Get full movie details from TMDB
            movie_details = generator.get_movie_details(movie_id)

            if movie_details:
                # Process the movie (enrichment)
                processed = generator.process_movie(movie_id, movie_data, movie_details, force_refresh=False)

                if processed:
                    # Mark as enriched
                    enrichment_state[movie_id] = {
                        'enriched': True,
                        'enrichment_date': datetime.now().isoformat(),
                        'enrichment_version': 1
                    }

                    # Save state after each success (in case of crash)
                    save_json('enrichment_state.json', enrichment_state)

                    links_count = len(processed.get('links', []))
                    print(f"  Enriched: {title} - {links_count} links")
                    success_count += 1
                else:
                    print(f"  Failed to process: {title}")
                    fail_count += 1
            else:
                print(f"  No TMDB details found for: {title}")
                fail_count += 1

            # Rate limiting
            time.sleep(0.25)

        except Exception as e:
            print(f"  Error enriching {title}: {e}")
            fail_count += 1

    # Cleanup scrapers
    print("\nCleaning up scrapers...")
    try:
        if generator.agent_scraper and generator.agent_scraper != False:
            generator.agent_scraper.close()
        if generator.platform_scraper and generator.platform_scraper != False:
            generator.platform_scraper.close()
        if generator.rt_scraper and generator.rt_scraper is not False:
            generator.rt_scraper.close()
        if generator.wikipedia_scraper and generator.wikipedia_scraper is not False:
            generator.wikipedia_scraper.close()
    except Exception as e:
        print(f"  Cleanup warning: {e}")

    # Summary
    print(f"\n{'='*60}")
    print(f"ENRICHMENT COMPLETE")
    print(f"{'='*60}")
    print(f"Successful: {success_count}")
    print(f"Failed:     {fail_count}")
    print(f"Remaining:  {total_pending - len(needs_enrichment)}")
    print(f"{'='*60}\n")

    # Now regenerate data.json with the newly enriched movies
    if success_count > 0:
        print("Regenerating data.json with enriched movies...")
        try:
            generator.generate_display_data(incremental=True)
            print("data.json updated successfully!")
        except Exception as e:
            print(f"Warning: Failed to regenerate data.json: {e}")

    return fail_count == 0


def main():
    parser = argparse.ArgumentParser(
        description='Enrich new arrivals (available movies with providers)'
    )
    parser.add_argument('--batch', type=int, default=20,
                        help='Number of movies to process per run (default: 20)')
    parser.add_argument('--all', action='store_true',
                        help='Process all pending movies (no batch limit)')
    parser.add_argument('--list', action='store_true',
                        help='Just list movies needing enrichment')

    args = parser.parse_args()

    # Change to script directory
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)

    if args.list:
        list_pending()
        return 0

    success = run_enrichment(batch_size=args.batch, no_limit=args.all)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
