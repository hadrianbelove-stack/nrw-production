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
        '--resolve-preorders',
        action='store_true',
        help='Resolve pre-order movies: find VOD dates via TMDB Type 4 and Gemini'
    )
    parser.add_argument(
        '--check-festivals',
        action='store_true',
        help='Check festival screening links for expiration (dead links get hidden, movies return to tracking)'
    )

    args = parser.parse_args()
    incremental = not args.full
    force_refresh = args.full  # Force refresh cache on full runs

    # Set debug mode globally (could be passed to DataGenerator if needed)
    if args.debug:
        os.environ['AGENT_SCRAPER_DEBUG'] = 'true'
        print("🐛 Debug mode enabled for intake/provider discovery and agent scraper")

    # Initialize data generator from pipeline module
    # Enrichment (YouTube scraper, etc.) enabled only when --enrich flag is passed
    generator = DataGenerator(enrichment_enabled=args.enrich)

    if args.debug:
        generator.logger.setLevel(logging.DEBUG)
        generator.logger.debug("Debug mode enabled - verbose logging active")

    # Run discovery if requested
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
    newly_digital_count = 0
    if args.discover:
        print("\n🔍 Discovering provider availability for tracking movies...")
        newly_digital_count = generator.check_tracking_movies()

    # CLI metrics handling removed - orchestrator now handles metrics consolidation from discovery_run.json

    # Resolve pre-order dates if requested
    preorder_resolved = 0
    if args.resolve_preorders:
        print("\n📅 Resolving pre-order movie dates...")
        preorder_resolved = generator.resolve_preorder_dates()
        print(f"✅ Pre-order resolution complete: {preorder_resolved} resolved")

    # Run enrichment if requested
    enriched_count = 0
    if args.enrich:
        print("\n🎨 Running enrichment for newly available movies...")
        enriched_count = generator.enrich_newly_available_movies()
        print(f"✅ Enrichment complete: {enriched_count} movies enriched")

    # Re-enrich watch link gaps if requested
    if args.reenrich_gaps:
        print("\n🔗 Re-enriching movies with watch link gaps...")
        gap_count = generator.reenrich_watch_link_gaps()
        print(f"✅ Re-enrichment complete: {gap_count} movies updated")

    # Check festival screening links for expiration
    if args.check_festivals:
        print("\n🎪 Checking festival screening links...")
        generator.check_festival_expirations()
        print(f"✅ Festival check complete")

    # Generate the final display data (only for final generation phase, not intake/discovery/enrich/festival)
    festival_backfill = getattr(args, 'festival_backfill', False)
    if not args.intake and not args.discover and not args.enrich and not festival_backfill and not args.reenrich_gaps and not args.resolve_preorders and not args.check_festivals:
        print("\n🎬 Generating final display data...")
        generator.generate_display_data(incremental=incremental, force_refresh=force_refresh)
    else:
        print("📋 Phase complete")


if __name__ == "__main__":
    main()
