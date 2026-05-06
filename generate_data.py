#!/usr/bin/env python3
"""
Generate display data from tracking database with enriched links.

This is the main entry point for the NRW data generation pipeline.
All business logic has been extracted to the pipeline/ module for maintainability.

Clean 4-Phase Architecture:
  Phase 1: INTAKE    - python3 generate_data.py --intake
  Phase 2: DISCOVERY - python3 generate_data.py --discover
  Phase 3: ENRICHMENT - python3 generate_data.py --enrich
  Phase 4: DISPLAY   - python3 generate_data.py (reads data.json for final processing)
"""

import os
import argparse
import logging

# Import the complete DataGenerator from pipeline module
from pipeline import DataGenerator


def main():
    """Main entry point for data generation CLI."""
    parser = argparse.ArgumentParser(
        description="Generate display data from tracking database with enriched links"
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Regenerate entire data.json from scratch (default: incremental mode - only process new movies)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging for provider discovery and agent scraper'
    )
    parser.add_argument(
        '--intake',
        action='store_true',
        help='Intake: Find new movie premieres from TMDB API and add to tracking database'
    )
    parser.add_argument(
        '--discover',
        action='store_true',
        help='Discovery: Check provider availability for all tracking movies'
    )
    parser.add_argument(
        '--since',
        type=str,
        help='Provider discovery since date (YYYY-MM-DD) for stateful incremental checks'
    )
    parser.add_argument(
        '--bootstrap',
        action='store_true',
        help='Bootstrap provider discovery state using full discovery.days_back window'
    )
    parser.add_argument(
        '--enrich',
        action='store_true',
        help='Enrichment: Add metadata to newly discovered movies in data.json'
    )
    parser.add_argument(
        '--festival-backfill',
        action='store_true',
        help='Backfill festival premieres to tracking database (2024, 2025, 2026)'
    )
    parser.add_argument(
        '--festival-years',
        type=str,
        help='Comma-separated years for festival backfill (e.g., "2024,2025"). Defaults to all.'
    )
    parser.add_argument(
        '--reenrich-gaps',
        action='store_true',
        help='Re-enrich movies that have Amazon/Apple providers but no watch links'
    )
    parser.add_argument(
        '--check-screenings',
        action='store_true',
        help='Check virtual screening links for expiration (dead links get hidden, movies return to tracking)'
    )
    parser.add_argument(
        '--archive',
        action='store_true',
        help='Archive movies older than 90 days from data.json to data_archive.json'
    )
    parser.add_argument(
        '--enrich-id',
        type=str,
        help='Enrich a single movie by TMDB ID (skips queue, enriches just this one)'
    )
    parser.add_argument(
        '--gap-fill',
        action='store_true',
        help='Daily gap fill: refresh JustWatch links and Wikipedia for all wall movies'
    )

    args = parser.parse_args()
    incremental = not args.full
    force_refresh = args.full  # Force refresh cache on full runs

    # Set debug mode globally (could be passed to DataGenerator if needed)
    if args.debug:
        os.environ['AGENT_SCRAPER_DEBUG'] = 'true'
        print("🐛 Debug mode enabled for intake/provider discovery and agent scraper")

    # Initialize data generator from pipeline module
    # Enrichment (scrapers, etc.) enabled when --enrich or --enrich-id is passed
    generator = DataGenerator(enrichment_enabled=args.enrich or bool(args.enrich_id) or args.gap_fill)

    if args.debug:
        generator.logger.setLevel(logging.DEBUG)
        generator.logger.debug("Debug mode enabled - verbose logging active")

    # Run intake if requested
    intaked_count = 0
    miniseries_count = 0
    if args.intake:
        print("🔍 Running intake for new premieres...")
        intaked_count = generator.intake_new_premieres(
            debug=args.debug,
            since_date=args.since,
            bootstrap=args.bootstrap
        )
        print(f"✅ Movie intake complete: {intaked_count} new movies added")

        # Also intake miniseries (limited series)
        print("\n🔍 Running intake for new miniseries...")
        miniseries_count = generator.intake_new_miniseries(debug=args.debug)
        print(f"✅ Miniseries intake complete: {miniseries_count} new series added")

        # Update intake metrics to include miniseries count
        if miniseries_count > 0:
            try:
                import json
                metrics_path = 'metrics/intake_run.json'
                if os.path.exists(metrics_path):
                    with open(metrics_path, 'r') as f:
                        metrics = json.load(f)
                    metrics['results']['miniseries_intaked'] = miniseries_count
                    metrics['results']['total_intaked'] = metrics['results'].get('intaked', 0) + miniseries_count
                    with open(metrics_path, 'w') as f:
                        json.dump(metrics, f, indent=2)
                    print(f"📊 Updated intake metrics with miniseries count")
            except Exception as e:
                print(f"⚠️  Could not update intake metrics: {e}")

    # Run festival backfill if requested
    festival_count = 0
    if getattr(args, 'festival_backfill', False):
        years = None
        if args.festival_years:
            years = [int(y.strip()) for y in args.festival_years.split(',')]
        print(f"🎬 Running festival backfill{' for years: ' + str(years) if years else ' for all available years'}...")
        festival_count = generator.run_festival_backfill(years=years, debug=args.debug)
        print(f"✅ Festival backfill complete: {festival_count} new movies added")

    # Check tracking movies for digital availability if requested
    if args.discover:
        print("\n🔍 Discovering provider availability for tracking movies...")
        generator.check_tracking_movies()

    # Run enrichment if requested
    enriched_count = 0
    if args.enrich:
        print("\n🎨 Running enrichment for newly available movies...")
        enriched_count = generator.enrich_newly_available_movies()
        print(f"✅ Enrichment complete: {enriched_count} movies enriched")

    # Single-movie enrichment if requested
    elif args.enrich_id:
        print(f"\n🎯 Running single-movie enrichment for TMDB ID {args.enrich_id}...")
        enriched_count = generator.enrich_newly_available_movies(target_id=args.enrich_id)
        print(f"✅ Single-movie enrichment complete: {enriched_count} enriched")

    # Re-enrich watch link gaps if requested
    if args.reenrich_gaps:
        print("\n🔗 Re-enriching movies with watch link gaps...")
        gap_count = generator.reenrich_watch_link_gaps()
        print(f"✅ Re-enrichment complete: {gap_count} movies updated")

    # Daily gap fill — refresh JustWatch + Wikipedia for all wall movies
    if args.gap_fill:
        print("\n🔄 Running daily gap fill for all wall movies...")
        gap_results = generator.daily_gap_fill()
        print(f"✅ Gap fill complete: {gap_results.get('jw_updated', 0)} watch links updated, "
              f"{gap_results.get('wiki_filled', 0)} Wikipedia filled, "
              f"{gap_results.get('preorders_graduated', 0)} pre-orders graduated")

    # Check virtual screening links for expiration
    if args.check_screenings:
        print("\n🎪 Checking virtual screening links...")
        generator.check_virtual_screening_expirations()
        print(f"✅ Virtual screening check complete")

    # Archive old movies (90-day cleanup)
    if args.archive:
        print("\n📦 Archiving movies older than 90 days...")
        generator.archive_old_movies(days=90)
        print("✅ Archive complete")

    # Generate the final display data (only for final generation phase, not intake/discovery/enrich/festival)
    festival_backfill = getattr(args, 'festival_backfill', False)
    if not args.intake and not args.discover and not args.enrich and not festival_backfill and not args.reenrich_gaps and not args.gap_fill and not args.check_screenings and not args.archive:
        print("\n🎬 Generating final display data...")
        generator.generate_display_data(incremental=incremental, force_refresh=force_refresh)
    else:
        print("📋 Phase complete")


if __name__ == "__main__":
    main()
