"""
Shared constants for the NRW production system.
"""

PLACEHOLDER_ASINS = ['B0FMPYFP9W', 'B0FNDR5BW5', 'B0FMPYFP9X']

# Scraper Default Settings
# These can be overridden per-scraper in config.yaml
SCRAPER_DEFAULTS = {
    'timeout': 15,           # Page load timeout in seconds
    'rate_limit': 2.0,       # Minimum seconds between scrapes
    'max_retries': 3,        # Maximum retry attempts
    'exponential_backoff': {
        'base_delay': 0.5,   # Initial retry delay (seconds)
        'max_delay': 5.0,    # Maximum retry delay (seconds)
        'jitter_ratio': 0.2  # Randomness factor (±20%)
    },
    'cache_ttl_days': 30,    # Cache expiration (days)
    'screenshots_enabled': True,  # Capture screenshots on failure
    'screenshot_retention_days': 7  # Auto-delete old screenshots
}

# Enrichment Safety Limits
MAX_ENRICHMENT_BATCH = 100  # Maximum movies to enrich in a single run
ENRICHMENT_LOOP_TIMEOUT_MINUTES = 50  # No new film is started this long after the enrichment
# phase began (the clock includes the pre-order link finder and IMDb load before the loop). The
# daily orchestrator kills --enrich at 60 min (daily_orchestrator.py); 50 leaves room for one more
# film (5-min cap) plus the final saves, so the phase stops itself and saves (unprocessed films stay
# queued for the next run) instead of being killed with nothing saved. (The final saves include
# apply_admin_overrides, which in CI rebuilds the distributor lookup over the network: about a
# minute, longer if Wikipedia is slow.) The purge and the metrics run right after the data.json
# save; trailer hosting comes last and starts no new download after 55 min (one already running
# can outlast the kill; the nightly local run hosts the rest)
PREORDER_LINK_FINDER_MAX_MINUTES = 15  # The pre-order link finder (before the loop) stops
# starting new films after this long, so it can't eat the loop's time (soonest releases first)
MAX_ENRICHMENT_ATTEMPTS = 5  # Maximum catch-up retry attempts per movie (1 initial + 4 retries)
RETRY_BACKOFF_DAYS = [1, 3, 7, 14]  # Days to wait after attempt 1, 2, 3, 4 before retrying

def get_scraper_config(config, scraper_name):
    """
    Get scraper configuration with defaults applied.

    Args:
        config: Full config dict (usually from config.yaml)
        scraper_name: Name of scraper section (e.g., 'rt_scraper', 'wikipedia_scraper')

    Returns:
        dict: Merged configuration with defaults applied
    """
    # Start with global defaults
    merged_config = SCRAPER_DEFAULTS.copy()

    # Apply scraper-specific config if available
    if config and scraper_name in config:
        scraper_config = config[scraper_name]

        # Handle nested exponential_backoff config
        if 'exponential_backoff' in scraper_config:
            merged_backoff = merged_config['exponential_backoff'].copy()
            merged_backoff.update(scraper_config['exponential_backoff'])
            scraper_config = scraper_config.copy()
            scraper_config['exponential_backoff'] = merged_backoff

        # Update with scraper-specific values
        merged_config.update(scraper_config)

    return merged_config