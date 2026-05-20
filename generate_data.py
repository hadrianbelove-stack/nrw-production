#!/usr/bin/env python3
"""
Generate display data from tracking database with enriched links.

This is the main entry point for the NRW data generation pipeline.
All business logic has been extracted to the pipeline/ module for maintainability.

Core phases: --intake, --discover, --enrich, and bare display generation.
Additional operations: --enrich-id, --festival-backfill, --scan-eventive,
--reenrich-gaps, --reenrich-trailer-gaps, --gap-fill, --check-screenings, --archive.
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
        help='Intake since date (YYYY-MM-DD) — overrides stateful incremental window'
    )
    parser.add_argument(
        '--bootstrap',
        action='store_true',
        help='Bootstrap intake state using full intake.days_back window'
    )
    parser.add_argument(
        '--enrich',
        action='store_true',
        help='Enrichment: Add metadata to newly discovered movies in data.json'
    )
    parser.add_argument(
        '--festival-backfill',
        action='store_true',
        help='Backfill festival premieres to tracking database (years from config.yaml)'
    )
    parser.add_argument(
        '--festival-years',
        type=str,
        help='Comma-separated years for festival backfill (e.g., "2024,2025"). Defaults to all.'
    )
    parser.add_argument(
        '--reenrich-gaps',
        action='store_true',
        help='Re-enrich movies missing VOD deep links or with unverified watch links'
    )
    parser.add_argument(
        '--reenrich-trailer-gaps',
        action='store_true',
        help='Re-enrich completed movies missing trailers (retry trailer discovery waterfall)'
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
    parser.add_argument(
        '--scan-eventive',
        action='store_true',
        help='Scan Eventive festivals for active virtual screenings matching NRW movies'
    )

    args = parser.parse_args()

    # Set debug mode globally
    if args.debug:
        print("🐛 Debug mode enabled for intake/provider discovery and agent scraper")

    # Initialize data generator from pipeline module
    # Enrichment (scrapers, etc.) enabled when --enrich or --enrich-id is passed
    generator = DataGenerator(enrichment_enabled=args.enrich or bool(args.enrich_id) or args.gap_fill or args.reenrich_trailer_gaps)

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

        # Also intake Apple Music Live specials (JW blind spot)
        print("\n🔍 Running intake for Apple Music Live specials...")
        aml_count = generator.intake_apple_music_live(debug=args.debug)
        print(f"✅ Apple Music Live intake complete: {aml_count} new titles added")

    # Run festival backfill if requested
    festival_count = 0
    if args.festival_backfill:
        years = None
        if args.festival_years:
            years = [int(y.strip()) for y in args.festival_years.split(',')]
        print(f"🎬 Running festival backfill{' for years: ' + str(years) if years else ' for all available years'}...")
        festival_count = generator.run_festival_backfill(years=years, debug=args.debug)
        print(f"✅ Festival backfill complete: {festival_count} new movies added")

    # Scan Eventive for virtual screenings if requested
    eventive_count = 0
    if args.scan_eventive:
        print("\n🎬 Scanning Eventive for virtual screenings...")
        eventive_count = generator.scan_eventive_screenings()
        print(f"✅ Eventive scan complete: {eventive_count} new links cached")

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

    # Re-enrich trailer gaps if requested
    if args.reenrich_trailer_gaps:
        print("\n🎬 Re-enriching movies with missing trailers...")
        trailer_count = generator.reenrich_trailer_gaps()
        print(f"✅ Trailer re-enrichment complete: {trailer_count} movies updated")

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

    # Generate the final display data (only when no phase flags are passed)
    if not args.intake and not args.discover and not args.enrich and not args.festival_backfill and not args.reenrich_gaps and not args.reenrich_trailer_gaps and not args.gap_fill and not args.check_screenings and not args.archive and not args.scan_eventive:
        print("\n🎬 Generating final display data...")
        generator.generate_display_data()
    else:
        print("📋 Phase complete")


if __name__ == "__main__":
    main()
