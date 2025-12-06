#!/usr/bin/env python3
"""
Generate display data from tracking database with enriched links.

This is the main entry point for the NRW data generation pipeline.
All business logic has been extracted to the pipeline/ module for maintainability.
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
        '--enrichment',
        action='store_true',
        help='Enable enrichment (scrapers, link fetching) explicitly'
    )

    args = parser.parse_args()
    incremental = not args.full
    force_refresh = args.full  # Force refresh cache on full runs

    # Set debug mode globally (could be passed to DataGenerator if needed)
    if args.debug:
        os.environ['AGENT_SCRAPER_DEBUG'] = 'true'
        print("🐛 Debug mode enabled for intake/discovery and agent scraper")

    # Set enrichment flag: false for intake/discovery, true for final generation
    if args.intake or args.discover:
        enrichment_enabled = args.enrichment  # Only enable if explicitly requested
        if enrichment_enabled:
            print("🎯 Enrichment enabled for intake/discovery mode")
        else:
            print("🚫 Enrichment disabled for intake/discovery mode")
    else:
        enrichment_enabled = True  # Always enabled for final generation phase
        print("🎯 Enrichment enabled for final generation phase")

    # Initialize data generator from pipeline module
    generator = DataGenerator()
    generator.enrichment_enabled = enrichment_enabled

    if args.debug:
        generator.logger.setLevel(logging.DEBUG)
        generator.logger.debug("Debug mode enabled - verbose logging active")

    # Run discovery if requested
    discovered_count = 0
    if args.intake:
        print("🔍 Running intake for new premieres...")
        discovered_count = generator.discover_new_premieres(
            debug=args.debug,
            since_date=args.since,
            bootstrap=args.bootstrap
        )
        print(f"✅ Intake complete: {discovered_count} new movies added")

    # Check tracking movies for digital availability if requested
    newly_digital_count = 0
    if args.discover:
        print("\n🔍 Discovering provider availability for tracking movies...")
        newly_digital_count = generator.check_tracking_movies()

    # CLI metrics handling removed - orchestrator now handles metrics consolidation from discovery_run.json

    # Generate the final display data
    generator.generate_display_data(incremental=incremental, force_refresh=force_refresh)


if __name__ == "__main__":
    main()
