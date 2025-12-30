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

    args = parser.parse_args()
    incremental = not args.full
    force_refresh = args.full  # Force refresh cache on full runs

    # Set debug mode globally (could be passed to DataGenerator if needed)
    if args.debug:
        os.environ['AGENT_SCRAPER_DEBUG'] = 'true'
        print("🐛 Debug mode enabled for intake/provider discovery and agent scraper")

    # Enrichment is now handled by --enrich flag and runs separately

    # Initialize data generator from pipeline module
    # Enrichment is now controlled by the --enrich flag and runs separately
    generator = DataGenerator(enrichment_enabled=False)

    if args.debug:
        generator.logger.setLevel(logging.DEBUG)
        generator.logger.debug("Debug mode enabled - verbose logging active")

    # Run discovery if requested
    intaked_count = 0
    if args.intake:
        print("🔍 Running intake for new premieres...")
        intaked_count = generator.discover_new_premieres(
            debug=args.debug,
            since_date=args.since,
            bootstrap=args.bootstrap
        )
        print(f"✅ Intake complete: {intaked_count} new movies added")

    # Check tracking movies for digital availability if requested
    newly_digital_count = 0
    if args.discover:
        print("\n🔍 Discovering provider availability for tracking movies...")
        newly_digital_count = generator.check_tracking_movies()

    # CLI metrics handling removed - orchestrator now handles metrics consolidation from discovery_run.json

    # Run enrichment if requested
    enriched_count = 0
    if args.enrich:
        print("\n🎨 Running enrichment for newly available movies...")
        enriched_count = generator.enrich_newly_available_movies()
        print(f"✅ Enrichment complete: {enriched_count} movies enriched")

    # Generate the final display data (only for final generation phase, not intake/discovery/enrich)
    if not args.intake and not args.discover and not args.enrich:
        print("\n🎬 Generating final display data...")
        generator.generate_display_data(incremental=incremental, force_refresh=force_refresh)
    else:
        print("📋 Phase complete")


if __name__ == "__main__":
    main()
