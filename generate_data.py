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
        help='Enable debug logging for discovery and agent scraper'
    )
    parser.add_argument(
        '--discover',
        action='store_true',
        help='Run discovery to find new premieres before generating data'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Check tracking movies for digital availability (provider monitoring)'
    )
    parser.add_argument(
        '--since',
        type=str,
        help='Discovery since date (YYYY-MM-DD) for stateful incremental discovery'
    )
    parser.add_argument(
        '--bootstrap',
        action='store_true',
        help='Bootstrap discovery state by using full discovery.days_back window'
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
        print("🐛 Debug mode enabled for discovery and agent scraper")

    # Set enrichment flag: false for discovery/monitoring, true for final generation
    if args.discover or args.check:
        enrichment_enabled = args.enrichment  # Only enable if explicitly requested
        if enrichment_enabled:
            print("🎯 Enrichment enabled for discovery/monitoring mode")
        else:
            print("🚫 Enrichment disabled for discovery/monitoring mode")
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
    if args.discover:
        print("🔍 Running discovery for new premieres...")
        discovered_count = generator.discover_new_premieres(
            debug=args.debug,
            since_date=args.since,
            bootstrap=args.bootstrap
        )
        print(f"✅ Discovery complete: {discovered_count} new movies added")

    # Check tracking movies for digital availability if requested
    newly_digital_count = 0
    if args.check:
        print("\n🔍 Checking tracking movies for digital availability...")
        newly_digital_count = generator.check_tracking_movies()

    # CLI metrics handling removed - orchestrator now handles metrics consolidation from discovery_run.json

    # Generate the final display data
    generator.generate_display_data(incremental=incremental, force_refresh=force_refresh)


if __name__ == "__main__":
    main()
