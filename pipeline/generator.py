#!/usr/bin/env python3
"""
Data Generator - Core data generation pipeline for NRW.

Extracted from monolithic generate_data.py (2025-11-10) for better maintainability.
Handles movie discovery, tracking, enrichment, and display data generation.
"""

import json
import requests
import yaml
from datetime import datetime, timedelta
import time
import os
import re
from urllib.parse import quote
import logging
from logging.handlers import RotatingFileHandler
from agent_link_scraper import AgentLinkScraper
from scripts.youtube_trailer_scraper import YouTubeTrailerScraper
from rt_scraper_playwright import RTScraperPlaywright
from wikipedia_scraper_playwright import WikipediaScraperPlaywright
from constants import PLACEHOLDER_ASINS, get_scraper_config
try:
    from streaming_platform_scraper import StreamingPlatformScraper
except ImportError:
    StreamingPlatformScraper = None

# Phase 3: Watchmode API with quota management
from watchmode_api import create_watchmode_client


def setup_logger(name, log_file='logs/admin.log', level=logging.INFO):
    """
    Configure logging with file rotation and console output.

    Args:
        name (str): Logger name (e.g., 'admin', 'data_generator')
        log_file (str): Path to log file (default: 'logs/admin.log')
        level (int): Logging level (default: logging.INFO)

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Get or create logger
    logger = logging.getLogger(name)

    # Prevent duplicate handlers
    if not logger.handlers:
        logger.setLevel(level)

        # Create formatter (no user context for generate_data.py)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler with rotation (10MB, 5 backups)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler for development visibility
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


class DataGenerator:
    def __init__(self):
        # Initialize logger FIRST before any operations that might log
        self.logger = setup_logger('data_generator', 'logs/admin.log', logging.INFO)

        # Initialize storage service (extracted 2025-11-10)
        from pipeline import StorageService
        self.storage = StorageService(self.logger)

        # Default enrichment flag (will be overridden by CLI)
        self.enrichment_enabled = True

        self.config = self.load_config()

        # Note: Validation service initialization deferred until after watchmode_stats is created (line ~160)
        # Get TMDB API key from environment or config.yaml (12-factor app pattern)
        self.tmdb_key = os.environ.get('TMDB_API_KEY')
        if not self.tmdb_key:
            # Fall back to config.yaml for local development
            self.tmdb_key = self.config.get('api', {}).get('tmdb_api_key')

        if not self.tmdb_key:
            self.logger.error(
                "TMDB_API_KEY not found. Please set the TMDB_API_KEY environment variable "
                "or add 'tmdb_api_key' to the 'api' section in config.yaml. "
                "Get a free key from https://www.themoviedb.org/settings/api"
            )
            raise ValueError("TMDB_API_KEY is required")

        # Watchmode API - Get new key from https://api.watchmode.com/ (free tier: 1000 calls/month)
        self.watchmode_key = os.environ.get('WATCHMODE_API_KEY')
        if not self.watchmode_key:
            # Try fallback from config.yaml
            self.watchmode_key = self.config.get('api', {}).get('watchmode_api_key')

        # Phase 3: Initialize Watchmode API with quota management
        self.watchmode_client = create_watchmode_client(self.watchmode_key, quota_limit=1000)
        self.watchmode_enabled = self.watchmode_client is not None

        if not self.watchmode_enabled:
            self.logger.error(
                "WATCHMODE_API_KEY not found or using placeholder value. "
                "Please set the WATCHMODE_API_KEY environment variable or add "
                "'watchmode_api_key' to the 'api' section in config.yaml. "
                "Get a free key from https://api.watchmode.com/"
            )
            self.watchmode_key = None
        self.wikipedia_cache = self.storage.load_cache('cache/wikipedia_cache.json')
        self.rt_cache = self.storage.load_cache('cache/rt_cache.json')
        self.wikipedia_overrides = self.storage.load_cache('overrides/wikipedia_overrides.json')
        self.rt_overrides = self.storage.load_cache('overrides/rt_overrides.json')
        self.watch_links_overrides = self.storage.load_cache('overrides/watch_links_overrides.json')
        self.trailer_overrides = self.storage.load_cache('overrides/trailer_overrides.json')
        self.watch_links_cache = self.storage.load_cache('cache/watch_links_cache.json')
        self.watch_link_overrides = self.storage.load_cache('admin/watch_link_overrides.json')

        # Load reviews
        self.reviews = {}
        if os.path.exists('admin/movie_reviews.json'):
            try:
                with open('admin/movie_reviews.json', 'r') as f:
                    self.reviews = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load movie reviews from admin/movie_reviews.json: {e}")
                self.reviews = {}

        # Watchmode usage statistics
        self.watchmode_stats = {
            'search_calls': 0,
            'source_calls': 0,
            'cache_hits': 0,
            'watchmode_successes': 0,
            'agent_attempts': 0,
            'agent_successes': 0,
            'agent_cache_hits': 0,
            'override_hits': 0,
            'rt_attempts': 0,
            'rt_successes': 0,
            'rt_cache_hits': 0,
            'schema_validation_warnings': 0,
            'schema_validation_passes': 0
        }

        # Initialize validation service (extracted 2025-11-10) - shares watchmode_stats dict
        from pipeline import ValidationService
        self.validator = ValidationService(
            logger=self.logger,
            storage_service=self.storage,
            config=self.config,
            stats_dict=self.watchmode_stats
        )

        # Initialize enrichment service (extracted 2025-11-10) - shares watchmode_stats dict
        from pipeline import EnrichmentService
        self.enrichment = EnrichmentService(
            logger=self.logger,
            config=self.config,
            storage_service=self.storage,
            validator_service=self.validator,
            stats_dict=self.watchmode_stats,
            watchmode_client=self.watchmode_client,
            enrichment_enabled=self.enrichment_enabled
        )
        # Inject cache references into enrichment service
        self.enrichment.set_cache_references(
            self.watch_links_cache,
            self.watch_links_overrides,
            self.watch_link_overrides
        )

        # Wikipedia usage statistics
        self.wikipedia_stats = {
            'wikidata_attempts': 0,
            'wikidata_successes': 0
        }

        # Discovery statistics
        self.discovery_stats = {
            'pages_fetched': 0,
            'total_results': 0,
            'new_movies_added': 0,
            'duplicates_skipped': 0,
            'api_calls': 0,
            'debug_enabled': False
        }

        self.agent_scraper = None  # Lazy initialization
        self.youtube_scraper = None  # Lazy initialization for YouTube trailer scraping
        self.youtube_trailer_cache = self.storage.load_cache('cache/youtube_trailer_cache.json')
        self.rt_scraper = None  # Lazy initialization for RT scraping with Playwright
        self.wikipedia_scraper = None  # Lazy initialization for Wikipedia scraping with Playwright
        self.platform_scraper = None  # Lazy initialization for streaming platform scraper

        # ASIN cache for Amazon links to avoid repeated searches
        self._amazon_asin_cache = {}

        # Perform startup consistency checks
        self.perform_startup_consistency_check()

    def load_config(self):
        """Load configuration from config.yaml and environment variables"""
        config = {}

        # Load from config.yaml if it exists
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config = yaml_config  # Load entire config, not just 'api' section

        # Environment variable takes precedence for API key
        tmdb_key = os.environ.get('TMDB_API_KEY')
        if tmdb_key:
            if 'api' not in config:
                config['api'] = {}
            config['api']['tmdb_api_key'] = tmdb_key

        # Validate that we have a key
        if not config.get('api', {}).get('tmdb_api_key'):
            raise ValueError(
                "TMDB API key not found. Please set the TMDB_API_KEY environment variable "
                "or add 'tmdb_api_key' to the 'api' section in config.yaml"
            )

        return config

    def perform_startup_consistency_check(self):
        """Perform consistency checks at startup to detect corrupted enrichment flags"""
        if not os.path.exists('movie_tracking.json'):
            return  # No tracking file to check

        try:
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)

            movies = db.get('movies', {})
            if not movies:
                return

            # Sample 50 entries for consistency check
            sample_size = min(50, len(movies))
            sample_movies = list(movies.values())[:sample_size]

            available_movies = [m for m in sample_movies if m.get('status') == 'available']
            if not available_movies:
                return

            enriched_false_count = sum(1 for m in available_movies if m.get('enriched') is False)
            total_available = len(available_movies)

            # Check if proportion of enriched=false is suspiciously high
            if total_available > 0:
                proportion = enriched_false_count / total_available
                threshold = 0.10  # 10% threshold

                if proportion > threshold:
                    self.logger.error(
                        f"🚨 CONSISTENCY CHECK FAILED: {enriched_false_count}/{total_available} "
                        f"({proportion:.1%}) available movies have enriched=false (threshold: {threshold:.1%})"
                    )
                    print(f"🚨 CONSISTENCY CHECK FAILED:")
                    print(f"   {enriched_false_count}/{total_available} ({proportion:.1%}) available movies have enriched=false")
                    print(f"   This suggests bulk enrichment flag corruption!")
                    print(f"   To restore from backup:")
                    print(f"   1. List backups: ls -la backups/movie_tracking.backup-*.json")
                    print(f"   2. Restore: cp backups/movie_tracking.backup-YYYYMMDD_HHMMSS.json movie_tracking.json")
                    print(f"   3. Retry operation")

                    # Import sys here to avoid circular imports
                    import sys
                    sys.exit(1)
                else:
                    self.logger.debug(f"✅ Consistency check passed: {enriched_false_count}/{total_available} ({proportion:.1%}) have enriched=false")

        except Exception as e:
            self.logger.warning(f"Could not perform startup consistency check: {e}")

    def validate_enrichment_changes(self, new_db, filepath):
        """Validate enrichment changes to prevent bulk corruption

        Args:
            new_db: New database to be written
            filepath: Path to existing file to compare against

        Returns:
            bool: True if changes are valid, False if suspicious bulk changes detected
        """
        try:
            if not os.path.exists(filepath):
                return True  # No existing file to compare against

            # Load current database
            with open(filepath, 'r') as f:
                current_db = json.load(f)

            current_movies = current_db.get('movies', {})
            new_movies = new_db.get('movies', {})

            # Count status transitions and enrichment changes
            status_changes = 0
            enriched_to_false_changes = 0
            total_available = 0

            for movie_id, new_movie in new_movies.items():
                current_movie = current_movies.get(movie_id, {})

                current_status = current_movie.get('status', '')
                new_status = new_movie.get('status', '')

                current_enriched = current_movie.get('enriched', False)
                new_enriched = new_movie.get('enriched', False)

                # Count status transitions
                if current_status != new_status:
                    status_changes += 1

                # Count suspicious enriched=false changes for available movies
                if (new_status == 'available' and
                    current_enriched is True and
                    new_enriched is False):
                    enriched_to_false_changes += 1

                if new_status == 'available':
                    total_available += 1

            # Check for suspicious bulk changes
            if total_available > 10:  # Only check if we have enough movies
                corruption_threshold = max(5, total_available * 0.20)  # 20% or 5 movies, whichever is higher

                if enriched_to_false_changes >= corruption_threshold:
                    self.logger.error(
                        f"Bulk enrichment corruption detected: {enriched_to_false_changes} "
                        f"movies changing from enriched=true to enriched=false "
                        f"(threshold: {corruption_threshold:.0f})"
                    )
                    print(f"🚨 BULK ENRICHMENT CORRUPTION DETECTED:")
                    print(f"   {enriched_to_false_changes} available movies changing enriched=true → enriched=false")
                    print(f"   This suggests a bug or corruption in the enrichment logic!")
                    print(f"   Changes blocked to prevent data corruption.")
                    return False

            self.logger.debug(f"Enrichment validation passed: {enriched_to_false_changes} enriched→false changes, {status_changes} status changes")
            return True

        except Exception as e:
            self.logger.warning(f"Could not validate enrichment changes: {e}")
            return True  # Allow changes if validation fails

    # ============================================================================
    # Enrichment methods moved to pipeline/enrichment.py (2025-11-10)
    # ============================================================================
    # The following methods have been extracted to pipeline/enrichment.py:
    # - get_excluded_services
    # - is_excluded_service
    # - append_affiliate_tag
    # - _init_agent_scraper
    # - get_watch_links (main enrichment orchestration)
    # - _enforce_platform_scraper_rate_limit
    # - _get_platform_deep_link_with_cache
    # - _normalize_watch_links_urls
    # - _try_agent_scraper
    # - is_actual_amazon_service
    # - is_actual_apple_service
    # - validate_service_link_consistency
    # - _try_platform_scraper
    # - _migrate_legacy_cache_format
    #
    # These methods are now accessed via self.enrichment.method_name()
    # See pipeline/enrichment.py for current implementation
    # ============================================================================


    def save_daily_metrics(self, discovered=0, newly_digital=0):
        """Save daily discovery and availability metrics for 3-day baselining"""
        try:
            # Ensure metrics directory exists
            os.makedirs('metrics', exist_ok=True)

            # Load current tracking database for counts
            total_tracking = 0
            total_available = 0
            if os.path.exists('movie_tracking.json'):
                with open('movie_tracking.json', 'r') as f:
                    db = json.load(f)
                    movies = db.get('movies', {})
                    total_tracking = len([m for m in movies.values() if m.get('status') == 'tracking'])
                    total_available = len([m for m in movies.values() if m.get('status') == 'available'])

            # Create metrics entry
            metrics_entry = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'discovered': discovered,
                'newly_digital': newly_digital,
                'total_tracking': total_tracking,
                'total_available': total_available,
                'timestamp': datetime.now().isoformat()
            }

            # Append to daily metrics log (JSONL format)
            metrics_file = 'metrics/daily.jsonl'
            with open(metrics_file, 'a') as f:
                f.write(json.dumps(metrics_entry) + '\n')

            self.logger.info(f"Daily metrics saved: {discovered} discovered, {newly_digital} newly digital")

        except Exception as e:
            self.logger.error(f"Failed to save daily metrics: {e}")

    def get_3_day_baseline(self):
        """Compute 3-day average for discovery and newly-digital counts"""
        try:
            metrics_file = 'metrics/daily.jsonl'
            if not os.path.exists(metrics_file):
                return None

            # Read last 3 days of metrics
            recent_metrics = []
            with open(metrics_file, 'r') as f:
                for line in f:
                    if line.strip():
                        recent_metrics.append(json.loads(line))

            # Get last 3 entries
            if len(recent_metrics) < 3:
                return {
                    'days_available': len(recent_metrics),
                    'discovery_avg': None,
                    'newly_digital_avg': None,
                    'note': f'Need at least 3 days of data, have {len(recent_metrics)}'
                }

            last_3 = recent_metrics[-3:]
            discovery_avg = sum(m['discovered'] for m in last_3) / 3
            newly_digital_avg = sum(m['newly_digital'] for m in last_3) / 3

            return {
                'days_available': 3,
                'discovery_avg': round(discovery_avg, 1),
                'newly_digital_avg': round(newly_digital_avg, 1),
                'dates': [m['date'] for m in last_3]
            }

        except Exception as e:
            self.logger.error(f"Failed to compute 3-day baseline: {e}")
            return None

    def _load_discovery_state(self, state_file):
        """Load discovery state from metrics/discovery_state.json"""
        try:
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    return json.load(f)
            else:
                # Return default state if file doesn't exist
                return {
                    'last_success_at': None,
                    'last_success_date': None
                }
        except Exception as e:
            self.logger.warning(f"Failed to load discovery state from {state_file}: {e}")
            return {
                'last_success_at': None,
                'last_success_date': None
            }

    def _update_discovery_state(self, state_file):
        """Atomically update discovery state after successful discovery"""
        try:
            now = datetime.now()
            new_state = {
                'last_success_at': now.isoformat(),
                'last_success_date': now.strftime('%Y-%m-%d')
            }

            # Ensure metrics directory exists
            os.makedirs(os.path.dirname(state_file), exist_ok=True)

            # Write atomically with temporary file
            temp_file = state_file + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(new_state, f, indent=2)

            # Atomic move
            os.rename(temp_file, state_file)

            self.logger.info(f"Discovery state updated: {new_state['last_success_date']}")
        except Exception as e:
            self.logger.error(f"Failed to update discovery state: {e}")

    def discover_new_premieres(self, debug=False, since_date=None, bootstrap=False):
        """Discover new movie premieres and add them to movie_tracking.json

        Args:
            debug: Enable detailed logging of discovery process
            since_date: Discovery since date (YYYY-MM-DD) for manual override
            bootstrap: Bootstrap discovery state by using full discovery.days_back window

        Returns:
            Number of new movies added
        """
        self.discovery_stats['debug_enabled'] = debug

        # Get discovery configuration with CI optimizations
        discovery_config = self.config.get('discovery', {})

        # Use CI-optimized values if running in CI environment
        if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
            fallback_days_back = int(os.getenv('CI_DISCOVERY_DAYS', discovery_config.get('ci_days_back', 7)))
            max_pages = int(os.getenv('CI_DISCOVERY_PAGES', discovery_config.get('ci_max_pages', 10)))
        else:
            fallback_days_back = discovery_config.get('days_back', 14)
            max_pages = discovery_config.get('max_pages', 20)

        # Load discovery state for stateful incremental discovery
        state_file = 'metrics/discovery_state.json'
        discovery_state = self._load_discovery_state(state_file)

        # Calculate since_date with stateful logic
        if since_date:
            # Manual override
            try:
                since_datetime = datetime.strptime(since_date, '%Y-%m-%d')
                if debug:
                    self.logger.info(f"Using manual since_date override: {since_date}")
            except ValueError:
                self.logger.warning(f"Invalid since_date format '{since_date}', falling back to state-based discovery")
                since_datetime = None
                since_date = None
        else:
            since_datetime = None

        if not since_date:
            if bootstrap or not discovery_state.get('last_success_date'):
                # Bootstrap mode or missing state - use full window
                days_back = fallback_days_back
                since_datetime = datetime.now() - timedelta(days=days_back)
                if debug:
                    self.logger.info(f"Bootstrap mode: using full discovery window ({days_back} days)")
            else:
                # Incremental mode - use last success with 1-day overlap
                last_success_date = discovery_state.get('last_success_date')
                try:
                    since_datetime = datetime.strptime(last_success_date, '%Y-%m-%d') - timedelta(days=1)
                    days_back = (datetime.now() - since_datetime).days
                    if debug:
                        self.logger.info(f"Incremental mode: since {last_success_date} with 1-day overlap")
                except (ValueError, TypeError):
                    # Invalid state, fall back to full window
                    days_back = fallback_days_back
                    since_datetime = datetime.now() - timedelta(days=days_back)
                    if debug:
                        self.logger.info(f"Invalid state, falling back to full discovery window ({days_back} days)")

        days_back = max(1, (datetime.now() - since_datetime).days)  # Ensure at least 1 day

        # Get hybrid discovery flags
        enable_pass_a = discovery_config.get('enable_pass_a', True)  # Digital releases (release_date + type=4)
        enable_pass_b = discovery_config.get('enable_pass_b', True)  # Theatrical releases (primary_release_date)

        if debug:
            self.logger.info(f"Starting discovery: days_back={days_back}, max_pages={max_pages}")
            self.logger.info(f"Discovery passes: A={enable_pass_a}, B={enable_pass_b}")

        # Load existing tracking database
        if os.path.exists('movie_tracking.json'):
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
        else:
            db = {'movies': {}, 'last_update': None}

        existing_ids = set(db['movies'].keys())
        if debug:
            self.logger.info(f"Existing database has {len(existing_ids)} movies")

        # Calculate date range for discovery
        end_date = datetime.now()
        start_date = since_datetime

        self.logger.info(f"Discovering new premieres from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        new_movies_added = 0
        all_discovered_movies = {}

        # Pass A: Direct-to-digital releases (release_date + type=4)
        if enable_pass_a:
            if debug:
                self.logger.info("Starting Pass A: Direct-to-digital releases")

            pass_a_count = self._run_discovery_pass(
                'A', 'digital', start_date, end_date, max_pages,
                all_discovered_movies, existing_ids, debug
            )

            if debug:
                self.logger.info(f"Pass A completed: {pass_a_count} movies discovered")

        # Pass B: Theatrical releases (primary_release_date)
        if enable_pass_b:
            if debug:
                self.logger.info("Starting Pass B: Theatrical releases")

            pass_b_count = self._run_discovery_pass(
                'B', 'theatrical', start_date, end_date, max_pages,
                all_discovered_movies, existing_ids, debug
            )

            if debug:
                self.logger.info(f"Pass B completed: {pass_b_count} movies discovered")

        # Merge all discovered movies into database
        for movie_id, movie_data in all_discovered_movies.items():
            if movie_id not in existing_ids:
                db['movies'][movie_id] = movie_data
                new_movies_added += 1
                existing_ids.add(movie_id)

        # Save updated database
        if new_movies_added > 0:
            db['last_update'] = datetime.now().isoformat()
            with open('movie_tracking.json', 'w') as f:
                json.dump(db, f, indent=2)

        # Collect sample titles for metrics
        sample_titles = []
        for movie_data in list(all_discovered_movies.values())[:5]:  # Get up to 5 sample titles
            sample_titles.append(movie_data['title'])

        # Write per-run metrics
        self._write_discovery_metrics(
            days_back, new_movies_added, sample_titles
        )

        # Log discovery summary
        self.logger.info(f"Discovery complete: {new_movies_added} new movies added from {self.discovery_stats['pages_fetched']} pages")
        if debug or new_movies_added == 0:
            self.logger.info(f"Discovery stats: {self.discovery_stats['total_results']} total results, {self.discovery_stats['duplicates_skipped']} duplicates")

        # Emit JSON artifact for robust metrics capture
        try:
            os.makedirs('metrics', exist_ok=True)
            discovery_run_data = {
                'timestamp': datetime.now().isoformat(),
                'operation': 'discover_premieres',
                'discovered': new_movies_added,
                'pages_fetched': self.discovery_stats['pages_fetched'],
                'total_results': self.discovery_stats['total_results'],
                'duplicates_skipped': self.discovery_stats['duplicates_skipped']
            }

            with open('metrics/discovery_run.json', 'w') as f:
                json.dump(discovery_run_data, f, indent=2)

            print(f"📊 Discovery metrics saved to metrics/discovery_run.json")
            self.logger.info(f"Discovery metrics saved: {discovery_run_data}")
        except Exception as e:
            self.logger.warning(f"Failed to save discovery metrics artifact: {e}")

        # Update discovery state after successful discovery
        # CRITICAL: Always update state so next run checks from today forward
        # Even if 0 movies found, we still successfully checked this date range
        # This prevents getting stuck in bootstrap mode checking same dates forever
        self._update_discovery_state(state_file)

        return new_movies_added

    def check_tracking_movies(self, max_to_check=None, priority_days=180):
        """
        CHANGE DETECTION INVARIANT: This function MUST poll ALL tracking movies to maintain
        data integrity. Any missing polls could result in permanently missed transitions
        from 'tracking' to 'available' status, breaking the change detection system.

        Pure change detection: Compare current TMDB providers with our previous DB state.
        On first appearance, set `digital_date = today` and `status = available`.
        No reliance on external 'digital release' dates. No fixed polling windows;
        we prioritize recent titles but do not skip older ones.

        Check tracking movies for provider availability (monitoring component)

        Checks movies in 'tracking' status to see if they have gotten digital releases
        by querying TMDB watch/providers API. Updates status to 'available' when providers found.

        Args:
            max_to_check: Maximum number of movies to check (None = all)
                         WARNING: FOR TESTING/DIAGNOSTICS ONLY. Production must always poll
                         ALL tracking movies to maintain "Always poll ALL tracking" invariant.
            priority_days: Prioritize movies released within this many days (default 180)

        Returns:
            int: Number of newly digital movies found
        """
        import random
        import requests
        import os

        # Load poll_all_tracking configuration
        poll_all_tracking = self.config.get('tracking', {}).get('poll_all_tracking', True)

        # Production safety guard: Prevent max_to_check in production
        if max_to_check is not None:
            nrw_env = os.getenv('NRW_ENV', '').lower()
            if nrw_env == 'production':
                self.logger.error(f"⚠️  PRODUCTION VIOLATION: max_to_check={max_to_check} parameter is forbidden in production")
                self.logger.error(f"   Production MUST always poll ALL tracking movies to maintain data integrity")
                raise ValueError("max_to_check parameter violates 'Always poll ALL tracking' production invariant")
            elif poll_all_tracking:
                self.logger.warning(f"⚠️  poll_all_tracking is enabled but max_to_check={max_to_check} specified - ignoring limit")
                max_to_check = None

        # Load tracking database
        if not os.path.exists('movie_tracking.json'):
            print("⚠️  No movie_tracking.json found")
            return 0

        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)

        # Get all tracking movies with their IDs
        tracking_movies = [(movie_id, movie) for movie_id, movie in db['movies'].items()
                          if movie['status'] == 'tracking']

        print(f"🔍 Found {len(tracking_movies)} movies in tracking status")

        if not tracking_movies:
            return 0

        # Sort by premiere_date/digital_date (most recent first) for smart prioritization
        def get_sort_key(item):
            movie_id, movie = item
            date_str = movie.get('digital_date') or movie.get('premiere_date')
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
            return datetime.min  # Put movies with no date at the end

        tracking_movies.sort(key=get_sort_key, reverse=True)

        # Apply priority window if specified
        # Prioritization only; older titles are always included after the priority queue.
        if priority_days:
            cutoff_date = datetime.now() - timedelta(days=priority_days)
            priority_movies = []
            older_movies = []

            for movie_id, movie in tracking_movies:
                date_str = movie.get('digital_date') or movie.get('premiere_date')
                if date_str:
                    try:
                        date_dt = datetime.strptime(date_str, '%Y-%m-%d')
                        if date_dt >= cutoff_date:
                            priority_movies.append((movie_id, movie))
                        else:
                            older_movies.append((movie_id, movie))
                    except:
                        older_movies.append((movie_id, movie))
                else:
                    older_movies.append((movie_id, movie))

            # Check priority movies first, then older ones
            tracking_movies = priority_movies + older_movies
            print(f"  Priority queue (last {priority_days} days): {len(priority_movies)} movies")
            print(f"  Older movies: {len(older_movies)} movies")
            print(f"  Note: Both priority and older titles will be processed in the same run")

        # Limit if max_to_check specified (only when poll_all_tracking is false)
        if max_to_check and not poll_all_tracking:
            tracking_movies = tracking_movies[:max_to_check]
            print(f"  Limiting check to first {len(tracking_movies)} movies")

        newly_digital = 0
        checked = 0
        failed = 0
        total_to_check = len(tracking_movies)

        print(f"\n🎬 Checking {total_to_check} movies for digital availability...\n")

        try:
            for movie_id, movie in tracking_movies:
                checked += 1

                # Progress indicator every 50 movies
                if checked % 50 == 0 or checked == total_to_check:
                    progress_pct = (checked / total_to_check) * 100
                    print(f"  Progress: {checked}/{total_to_check} ({progress_pct:.1f}%) - Found {newly_digital} newly digital, {failed} failed")

                # Check providers with retry logic
                url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
                params = {'api_key': self.tmdb_key}

                data = None
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = requests.get(url, params=params, timeout=(5, 15))
                        if response.status_code == 200:
                            data = response.json()
                            break
                        elif response.status_code == 429:  # Rate limited
                            wait_time = (2 ** attempt) + random.uniform(0, 1)
                            print(f"  Rate limited on {movie['title']}, waiting {wait_time:.1f}s")
                            time.sleep(wait_time)
                            continue
                        else:
                            self.logger.warning(f"HTTP {response.status_code} for {movie['title']}")
                            break
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        if attempt < max_retries - 1:
                            print(f"  Timeout/connection error for {movie['title']}, retrying in {wait_time:.1f}s")
                            time.sleep(wait_time)
                            continue
                        else:
                            self.logger.warning(f"Failed after {max_retries} attempts for {movie['title']}: {type(e).__name__}")
                            failed += 1
                            break
                    except requests.exceptions.RequestException as e:
                        self.logger.warning(f"Request error for {movie['title']}: {type(e).__name__}")
                        failed += 1
                        break

                if data:
                    us = data.get('results', {}).get('US', {})

                    # Get all provider types
                    rent_providers = us.get('rent', [])
                    buy_providers = us.get('buy', [])
                    stream_providers = us.get('flatrate', [])

                    # Extract provider names (using centralized excluded services helper)
                    rent_names = [p.get('provider_name', '') for p in rent_providers if not self.enrichment.is_excluded_service(p.get('provider_name', ''))]
                    buy_names = [p.get('provider_name', '') for p in buy_providers if not self.enrichment.is_excluded_service(p.get('provider_name', ''))]
                    stream_names = [p.get('provider_name', '') for p in stream_providers if not self.enrichment.is_excluded_service(p.get('provider_name', ''))]

                    # Check if ANY providers exist (after filtering out excluded services)
                    has_providers = bool(rent_names or buy_names or stream_names)

                    if has_providers and movie['status'] == 'tracking':
                        # Status-only lifecycle: Change status to exclude from future polls
                        # (status != 'tracking' means no longer monitored for availability)
                        movie['status'] = 'available'
                        movie['digital_date'] = datetime.now().strftime('%Y-%m-%d')
                        movie['providers'] = {
                            'rent': rent_names,
                            'buy': buy_names,
                            'streaming': stream_names
                        }
                        # Mark for enrichment (Phase 2.1 optimization)
                        movie['enriched'] = False
                        movie['enrichment_date'] = None

                        newly_digital += 1
                        # Show which service it appeared on
                        first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0]
                        print(f"  ✓ {movie['title']} now on {first_service}!")

                # Incremental save every 100 movies
                if checked % 100 == 0:
                    if self.storage.atomic_write_json(db, 'movie_tracking.json'):
                        print(f"  💾 Progress saved (batch {checked//100})")
                    else:
                        print(f"  ⚠️ Progress save failed (batch {checked//100})")

                # Rate limiting
                time.sleep(self.config.get('api', {}).get('tmdb_rate_limit', 0.25))

        except Exception as e:
            self.logger.error(f"Unexpected error during provider checking: {e}")
            print(f"\n⚠️  Unexpected error during provider checking: {e}")
            print(f"  Processed {checked}/{total_to_check} movies before error")
        finally:
            # Always save database before exiting
            if self.storage.atomic_write_json(db, 'movie_tracking.json'):
                print(f"  💾 Final database save completed")
            else:
                print(f"  ❌ Failed to save database")

        # Generate completion message with full-scan indicator
        if poll_all_tracking:
            scan_tag = " (full scan, no limits)"
        else:
            scan_tag = ""

        completion_msg = f"Polled {checked} tracking movies, found {newly_digital} changes{scan_tag}. {failed} failed."
        print(f"\n✅ {completion_msg}")
        self.logger.info(completion_msg)

        # Emit standardized metrics line for CI parsing
        print(f"Polled {checked} movies, {newly_digital} changes detected{scan_tag}")
        self.logger.info(f"Polled {checked} movies, {newly_digital} changes detected{scan_tag}")

        # Emit JSON artifact for robust metrics capture
        try:
            os.makedirs('metrics', exist_ok=True)
            discovery_run_data = {
                'timestamp': datetime.now().isoformat(),
                'operation': 'check_tracking',
                'polled': checked,
                'transitions': newly_digital,
                'scan_tag': scan_tag.strip() if scan_tag else None,
                'failed': failed
            }

            with open('metrics/discovery_run.json', 'w') as f:
                json.dump(discovery_run_data, f, indent=2)

            print(f"📊 Metrics saved to metrics/discovery_run.json")
            self.logger.info(f"Discovery metrics saved: {discovery_run_data}")
        except Exception as e:
            self.logger.warning(f"Failed to save metrics artifact: {e}")

        # Incremental compaction: move available movies to archive
        if self.config.get('tracking', {}).get('archive_available_on_detect', False):
            batch_size = self.config.get('tracking', {}).get('compaction_batch_size', 50)
            recent_days = self.config.get('tracking', {}).get('compaction_recent_days')

            # Collect all available movies with digital_date
            available_movies = []
            for movie_id, movie in db['movies'].items():
                if (movie.get('status') == 'available' and
                    movie.get('digital_date')):
                    try:
                        digital_date = datetime.strptime(movie['digital_date'], '%Y-%m-%d')
                        available_movies.append((movie_id, movie, digital_date))
                    except:
                        pass

            # Filter by age if compaction_recent_days is set
            if recent_days is not None:
                recent_cutoff = datetime.now() - timedelta(days=recent_days)
                available_movies = [(mid, m, d) for mid, m, d in available_movies
                                   if d >= recent_cutoff]

            # Sort by digital_date descending (most recent first)
            available_movies.sort(key=lambda x: x[2], reverse=True)

            # Take up to batch_size entries for archival
            to_archive = {}
            for movie_id, movie, _ in available_movies[:batch_size]:
                to_archive[movie_id] = movie

            if to_archive:
                moved_count = self.storage.atomic_move_to_archive(to_archive)
                if moved_count > 0:
                    age_filter = f" (from last {recent_days} days)" if recent_days else ""
                    self.logger.info(f"Compaction: moved {moved_count} available movies to archive{age_filter}")
                    print(f"📦 Compaction: moved {moved_count} available movies to archive{age_filter}")

        return newly_digital

    # validate_enrichment_consistency moved to pipeline/validation.py (2025-11-10)

    # atomic_write_json moved to pipeline/storage.py (2025-11-10)

    # atomic_move_to_archive moved to pipeline/storage.py (2025-11-10)

    # load_all_movies moved to pipeline/storage.py (2025-11-10)

    # validate_data_json_schema moved to pipeline/validation.py (2025-11-10)

    def _write_discovery_metrics(self, window_days, new_movies_added, sample_titles):
        """Write per-run discovery metrics to metrics/daily.jsonl"""
        try:
            # Ensure metrics directory exists
            os.makedirs('metrics', exist_ok=True)

            # Create metrics object
            metrics_object = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'timestamp': datetime.now().isoformat(),
                'window_days': window_days,
                'pages_fetched': self.discovery_stats['pages_fetched'],
                'total_results': self.discovery_stats['total_results'],
                'new_movies_added': new_movies_added,
                'duplicates_skipped': self.discovery_stats['duplicates_skipped'],
                'api_calls': self.discovery_stats['api_calls'],
                'sample_titles': sample_titles[:5]  # Limit to 5 samples
            }

            # Append to daily metrics log (JSONL format)
            metrics_file = 'metrics/daily.jsonl'
            with open(metrics_file, 'a') as f:
                f.write(json.dumps(metrics_object) + '\n')

            self.logger.info(f"Discovery metrics written to {metrics_file}")

        except Exception as e:
            self.logger.error(f"Failed to write discovery metrics: {e}")

    def _run_discovery_pass(self, pass_name, pass_type, start_date, end_date, max_pages, discovered_movies, existing_ids, debug):
        """Run a single discovery pass (A or B)

        Args:
            pass_name: 'A' or 'B' for logging
            pass_type: 'digital' or 'theatrical' to determine API parameters
            start_date: Discovery start date
            end_date: Discovery end date
            max_pages: Maximum pages to fetch
            discovered_movies: Dict to accumulate discovered movies
            existing_ids: Set of existing movie IDs to skip
            debug: Enable debug logging

        Returns:
            Number of new movies discovered in this pass
        """
        pass_new_count = 0

        for page in range(1, max_pages + 1):
            try:
                if debug:
                    self.logger.info(f"Pass {pass_name} - Fetching page {page}/{max_pages}")

                # Use bounded timeout and retry logic
                page_results = self._fetch_tmdb_page_with_retry(
                    page, start_date, end_date, debug, pass_type=pass_type
                )

                if not page_results:
                    if debug:
                        self.logger.warning(f"Pass {pass_name} - No results from page {page}, stopping pass")
                    break

                self.discovery_stats['pages_fetched'] += 1
                self.discovery_stats['total_results'] += len(page_results)

                # Process results from this page
                page_new_count = 0
                page_duplicate_count = 0
                sample_titles = []

                for movie in page_results:
                    movie_id = str(movie['id'])
                    title = movie.get('title', 'Unknown')

                    # Collect sample titles for debugging
                    if len(sample_titles) < 3:
                        sample_titles.append(f"{title} (ID: {movie_id})")

                    # Skip if already in existing database or already discovered in this run
                    if movie_id in existing_ids or movie_id in discovered_movies:
                        page_duplicate_count += 1
                        continue

                    # Add new movie with tracking status
                    # Note: digital_date is intentionally None here - monitoring will set it when providers are detected
                    discovered_movies[movie_id] = {
                        'title': title,
                        'status': 'tracking',
                        'first_seen': datetime.now().strftime('%Y-%m-%d'),
                        'digital_date': None,
                        'providers': {},
                        'discovery_pass': pass_name  # Track which pass found this movie
                    }

                    page_new_count += 1
                    pass_new_count += 1

                self.discovery_stats['new_movies_added'] += page_new_count
                self.discovery_stats['duplicates_skipped'] += page_duplicate_count

                # Log page summary
                if debug:
                    self.logger.info(f"Pass {pass_name} - Page {page}: {len(page_results)} results, {page_new_count} new, {page_duplicate_count} duplicates")
                    if sample_titles:
                        self.logger.info(f"Sample titles: {', '.join(sample_titles)}")

                # Rate limiting
                time.sleep(self.config.get('api', {}).get('tmdb_rate_limit', 0.1))

            except Exception as e:
                self.logger.error(f"Pass {pass_name} - Error processing page {page}: {e}")
                continue

        return pass_new_count

    def _fetch_tmdb_page_with_retry(self, page, start_date, end_date, debug=False, pass_type='digital', max_retries=3):
        """Fetch TMDB discover page with bounded timeout and retry logic"""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # Configure session with retry strategy
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        url = "https://api.themoviedb.org/3/discover/movie"

        # Build parameters based on pass type
        if pass_type == 'digital':
            # Pass A: Direct-to-digital releases
            params = {
                'api_key': self.tmdb_key,
                'release_date.gte': start_date.strftime('%Y-%m-%d'),
                'release_date.lte': end_date.strftime('%Y-%m-%d'),
                'with_release_type': '4',  # Digital only
                'region': 'US',
                'language': 'en-US',
                'include_adult': 'false',
                'sort_by': 'release_date.desc',
                'page': page
            }
        else:  # pass_type == 'theatrical'
            # Pass B: Theatrical releases
            params = {
                'api_key': self.tmdb_key,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'region': 'US',
                'language': 'en-US',
                'include_adult': 'false',
                'sort_by': 'primary_release_date.desc',
                'page': page
            }

        self.discovery_stats['api_calls'] += 1

        # Log exact TMDB params (excluding API key)
        if debug:
            log_params = {k: v for k, v in params.items() if k != 'api_key'}
            self.logger.info(f"TMDB API call (pass_type={pass_type}): {log_params}")

        try:
            # Use bounded timeouts: (connect_timeout, read_timeout)
            response = session.get(url, params=params, timeout=(10, 30))
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            if debug and results:
                self.logger.info(f"TMDB API success: page {page} returned {len(results)} results")

            return results

        except requests.exceptions.Timeout as e:
            self.logger.error(f"TMDB API timeout for page {page}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"TMDB API error for page {page}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching page {page}: {e}")
            return None

    def process_movie(self, movie_id, movie_data, movie_details, force_refresh=False):
        """Process a single movie into display format"""
        if not movie_details:
            return None
        
        title = movie_details['title']
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')
        
        # Extract key people
        credits = movie_details.get('credits', {})
        director = "Unknown"
        cast = []
        
        for crew in credits.get('crew', []):
            if crew['job'] == 'Director':
                director = crew['name']
                break
        
        for actor in credits.get('cast', [])[:2]:  # Top 2 actors
            cast.append(actor['name'])
        
        # Extract additional metadata
        genres = [g['name'] for g in movie_details.get('genres', [])]
        studio = None
        production_companies = movie_details.get('production_companies', [])
        if production_companies:
            studio = production_companies[0]['name']
        
        runtime = movie_details.get('runtime')
        
        # Country from production countries
        country = None
        production_countries = movie_details.get('production_countries', [])
        if production_countries:
            country = production_countries[0]['name']
        
        # Build links object with waterfall approach
        links = {}

        # Wikipedia link
        wiki_url = self.find_wikipedia_url(title, year, imdb_id, movie_id)
        if wiki_url:
            links['wikipedia'] = wiki_url
        
        # Trailer link
        trailer_url = self.find_trailer_url(movie_details)
        if trailer_url:
            links['trailer'] = trailer_url
        
        # RT link and score
        rt_data = self.find_rt_url(title, year, imdb_id)
        rt_score = None
        if rt_data:
            if isinstance(rt_data, dict):
                links['rt'] = rt_data.get('url')
                rt_score = rt_data.get('score')
            else:
                links['rt'] = rt_data

        # Watch links (deep links to streaming platforms)
        watch_links_raw = self.enrichment.get_watch_links(movie_id, title, year, movie_data.get('providers', {}), force_refresh, tracking_data=movie_data)

        # Simplify provider names in watch links
        watch_links = {}
        for category, link_obj in watch_links_raw.items():
            if isinstance(link_obj, dict) and 'service' in link_obj:
                simplified_service = self.simplify_provider_name(link_obj['service'])
                watch_links[category] = {
                    'service': simplified_service,
                    'link': link_obj.get('link')
                }
            else:
                watch_links[category] = link_obj

        # Build movie dict
        movie_dict = {
            'id': movie_id,
            'title': title,
            'digital_date': movie_data.get('digital_date'),
            'bootstrap_date': movie_data.get('bootstrap_date', False),
            'manually_corrected': movie_data.get('manually_corrected', False),
            'poster': f"https://image.tmdb.org/t/p/w500{movie_details['poster_path']}" if movie_details.get('poster_path') else None,
            'synopsis': movie_details.get('overview', 'No synopsis available.'),
            'crew': {
                'director': director,
                'cast': cast
            },
            'genres': genres,
            'studio': studio,
            'runtime': runtime,
            'year': int(year) if year else None,
            'country': country,
            'rt_score': rt_score,
            'providers': movie_data.get('providers', {}),
            'links': links,
            'watch_links': watch_links
        }

        # Only add review key if a review exists
        review = self.reviews.get(str(movie_id))
        if review:
            movie_dict['review'] = review

        return movie_dict
    
    def generate_display_data(self, days_back=90, incremental=True, force_refresh=False):
        """Generate display data from tracking database

        Args:
            days_back: How many days back to look for available movies
            incremental: If True, only process NEW movies not already in data.json (default)
                        If False, regenerate entire data.json from scratch
        """

        # Load main tracking database for updating enrichment flags
        if os.path.exists('movie_tracking.json'):
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
        else:
            self.logger.error("No movie_tracking.json found. Run 'python movie_tracker.py daily' first")
            return

        # Load all movies (merged from tracking and archived)
        archive_enabled = self.config.get('tracking', {}).get('archive_available_on_detect', False)
        combined = self.storage.load_all_movies(archive_enabled=archive_enabled)
        if not combined.get('movies'):
            self.logger.error("No tracking database found. Run 'python movie_tracker.py daily' first")
            return

        # Load existing data.json for merging later
        existing_movies = []
        existing_ids = set()
        if os.path.exists('data.json'):
            # Validate schema before loading
            if self.validator.validate_data_json_schema('data.json'):
                with open('data.json', 'r') as f:
                    existing_data = json.load(f)
                    existing_movies = existing_data.get('movies', [])
                    existing_ids = {str(m['id']) for m in existing_movies if isinstance(m, dict) and 'id' in m}
                message = f"Found {len(existing_movies)} existing movies in data.json"
                self.logger.info(message)
                print(f"📂 {message}")
            else:
                self.logger.error("data.json schema validation failed - treating as corrupted, will rebuild from scratch")
                print(f"❌ data.json schema validation failed - treating as corrupted, will rebuild from scratch")
                # Backup corrupted file
                backup_path = f"data.json.corrupted.validation.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.rename('data.json', backup_path)
                self.logger.info(f"Corrupted data.json backed up to {backup_path}")
                print(f"💾 Corrupted data.json backed up to {backup_path}")

        # Validate enrichment consistency before categorization
        print(f"\n🔍 Validating enrichment consistency...")
        self.validator.validate_enrichment_consistency()

        # Filter to recently available movies
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Build lookup of existing movies by ID for watch_links validation
        existing_movies_lookup = {str(m['id']): m for m in existing_movies if isinstance(m, dict) and 'id' in m}

        # Separate movies by enrichment status (Phase 2.1 optimization)
        needs_enrichment = []
        already_enriched = []
        stale_enrichment = []

        for movie_id, movie_data in combined['movies'].items():
            if movie_data['status'] == 'available' and movie_data.get('digital_date'):
                try:
                    digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                    if digital_date >= cutoff_date:
                        # Check enrichment status
                        is_enriched = movie_data.get('enriched', False)
                        enrichment_date = movie_data.get('enrichment_date')

                        # Check if enrichment is stale (> 90 days old)
                        is_stale = False
                        if is_enriched and enrichment_date:
                            try:
                                enrich_dt = datetime.fromisoformat(enrichment_date)
                                age_days = (datetime.now() - enrich_dt).days
                                is_stale = age_days > 90
                            except:
                                pass

                        if not is_enriched:
                            needs_enrichment.append((movie_id, movie_data))
                        elif is_stale:
                            stale_enrichment.append((movie_id, movie_data))
                        else:
                            # Before classifying as already_enriched, validate watch_links for placeholders
                            existing_movie = existing_movies_lookup.get(movie_id)
                            has_valid_links = True

                            if existing_movie and 'watch_links' in existing_movie:
                                validated_links = self.validator.validate_watch_links_schema(
                                    existing_movie['watch_links'],
                                    movie_data.get('title', 'Unknown')
                                )
                                # If validation removes all categories or results in empty dict,
                                # don't classify as already_enriched
                                if not validated_links:
                                    has_valid_links = False

                            if has_valid_links:
                                already_enriched.append((movie_id, movie_data))
                            else:
                                # Movie has placeholder ASINs or invalid links, needs re-enrichment
                                needs_enrichment.append((movie_id, movie_data))

                except Exception as e:
                    self.logger.warning(f"Error parsing date for {movie_data.get('title')}: {e}")

        # Phase 2.1 Optimization Report
        total_available = len(needs_enrichment) + len(already_enriched) + len(stale_enrichment)
        print(f"\n📊 Phase 2.1 Enrichment Optimization:")
        print(f"   Total available movies (last {days_back} days): {total_available}")
        print(f"   ✅ Already enriched (cached): {len(already_enriched)}")
        print(f"   🆕 Need enrichment: {len(needs_enrichment)}")
        print(f"   ⏰ Stale (>90 days, will re-enrich): {len(stale_enrichment)}")

        if incremental:
            # Re-enrich stale movies in batches (max 10 per run to avoid quota issues)
            stale_to_process = stale_enrichment[:10]
            if stale_to_process:
                print(f"   📝 Re-enriching {len(stale_to_process)} stale movies (batch of 10)")
            needs_enrichment.extend(stale_to_process)
        else:
            # Full mode: re-enrich everything
            print(f"   🔄 FULL MODE: Re-enriching ALL movies")
            needs_enrichment.extend(already_enriched)
            needs_enrichment.extend(stale_enrichment)

        print(f"\n🎬 Processing {len(needs_enrichment)} movies (enrichment phase)...")
        print(f"   API savings: {len(already_enriched)} movies skipped (95% cost reduction)")

        # Process only movies that need enrichment
        new_movies = []
        enriched_count = 0

        for movie_id, movie_data in needs_enrichment:
            try:
                # Get full movie details (movie_id is the TMDB ID)
                movie_details = self.get_movie_details(movie_id)
                if movie_details:
                    processed = self.process_movie(movie_id, movie_data, movie_details, force_refresh)
                    if processed:
                        new_movies.append(processed)
                        print(f"  ✓ {processed['title']} - Links: {len(processed['links'])}")

                        # Mark as enriched in tracking database
                        if movie_id in db['movies']:
                            db['movies'][movie_id]['enriched'] = True
                            db['movies'][movie_id]['enrichment_date'] = datetime.now().isoformat()
                        enriched_count += 1

                time.sleep(self.config.get('api', {}).get('tmdb_rate_limit', 0.25))  # Rate limiting

            except Exception as e:
                print(f"  ✗ Error processing {movie_data.get('title')}: {e}")

        # Pre-commit validation: prevent bulk enrichment flag corruption
        if not self.validate_enrichment_changes(db, 'movie_tracking.json'):
            self.logger.error("Pre-commit validation failed - aborting write to prevent corruption")
            print("❌ Pre-commit validation failed - enrichment changes rejected to prevent corruption")
            return []

        # Save updated tracking database with enrichment flags
        if self.storage.atomic_write_json(db, 'movie_tracking.json'):
            print(f"\n💾 Enrichment tracking saved: {enriched_count} movies marked as enriched")
        else:
            print(f"\n❌ Failed to save enrichment tracking")

        # Merge with existing movies that are already enriched
        if incremental and already_enriched:
            # Get cached data from existing data.json
            already_enriched_ids = {movie_id for movie_id, _ in already_enriched}
            raw_cached_movies = [m for m in existing_movies if isinstance(m, dict) and 'id' in m and str(m['id']) in already_enriched_ids]

            # Validate and clean cached movies' watch_links
            cached_movies = []
            for movie in raw_cached_movies:
                if 'watch_links' in movie:
                    validated_links = self.validator.validate_watch_links_schema(
                        movie['watch_links'],
                        movie.get('title', 'Unknown')
                    )
                    # Replace watch_links with validated result
                    movie_copy = movie.copy()
                    movie_copy['watch_links'] = validated_links

                    # Only include movie if it has valid links after validation
                    if validated_links:
                        cached_movies.append(movie_copy)
                    # If validated result is empty, drop the movie (it will be re-enriched in next run)
                else:
                    # Movie without watch_links, include as-is
                    cached_movies.append(movie)

            print(f"\n📋 Using {len(cached_movies)} cached movies + {len(new_movies)} newly enriched = {len(cached_movies) + len(new_movies)} total")
            display_movies = cached_movies + new_movies
        else:
            display_movies = new_movies
        
        # Sort by digital release date (newest first)
        display_movies.sort(key=lambda x: x['digital_date'], reverse=True)

        # Apply admin panel overrides (hide/feature movies)
        display_movies, hidden_ids, featured_ids = self.apply_admin_overrides(display_movies)

        # Save display data (includes hidden/featured for frontend filtering)
        output_data = {
            'generated_at': datetime.now().isoformat(),
            'count': len(display_movies),
            'movies': display_movies,
            'hidden': hidden_ids,  # For frontend filtering (as of 2025-11-09)
            'featured': featured_ids  # For frontend filtering (as of 2025-11-09)
        }
        
        with open('data.json', 'w') as f:
            json.dump(output_data, f, indent=2)
        
        # Cleanup agent scraper if initialized
        if self.agent_scraper and self.agent_scraper != False:
            try:
                self.agent_scraper.close()
            except Exception as e:
                self.logger.warning(f"Failed to close agent scraper: {e}")

        # Cleanup platform scraper if initialized
        if self.platform_scraper and self.platform_scraper != False:
            try:
                self.platform_scraper.close()
            except Exception as e:
                self.logger.warning(f"Failed to close platform scraper: {e}")

        # Cleanup RT scraper if initialized
        if self.rt_scraper and self.rt_scraper is not False:
            try:
                self.rt_scraper.close()
                self.logger.debug("RT scraper closed")
            except Exception as e:
                self.logger.warning(f"Failed to close RT scraper: {e}")

        # Save caches (RT cache is managed by rt_scraper)
        self.storage.save_cache(self.wikipedia_cache, 'cache/wikipedia_cache.json')
        
        message = f"Generated data.json with {len(display_movies)} movies"
        self.logger.info(message)
        print(f"✅ {message}")  # Also print to console for visibility
        wiki_count = len([m for m in display_movies if m['links'].get('wikipedia')])
        trailer_count = len([m for m in display_movies if m['links'].get('trailer') and 'watch?v=' in m['links']['trailer']])
        rt_count = len([m for m in display_movies if m['rt_score']])
        reviewed_count = len([m for m in display_movies if m.get('review')])

        self.logger.info(f"Wikipedia links found: {wiki_count}")
        self.logger.info(f"Direct trailers found: {trailer_count}")
        self.logger.info(f"RT scores cached: {rt_count}")
        self.logger.info(f"Movies with reviews: {reviewed_count}")

        print(f"Wikipedia links found: {wiki_count}")
        print(f"Direct trailers found: {trailer_count}")
        print(f"RT scores cached: {rt_count}")
        print(f"Movies with reviews: {reviewed_count}")

        # Wikidata usage statistics
        print(f"\n📊 Wikidata Usage:")
        print(f"  Wikidata attempts: {self.wikipedia_stats['wikidata_attempts']}")
        print(f"  Wikidata successes: {self.wikipedia_stats['wikidata_successes']}")
        if self.wikipedia_stats['wikidata_attempts'] > 0:
            wikidata_success_rate = (self.wikipedia_stats['wikidata_successes'] / self.wikipedia_stats['wikidata_attempts'] * 100)
            print(f"  Wikidata success rate: {wikidata_success_rate:.1f}%")
        print(f"  Wikipedia links recovered via Wikidata: {self.wikipedia_stats['wikidata_successes']}")

        # Watchmode usage statistics
        total_calls = self.watchmode_stats['search_calls'] + self.watchmode_stats['source_calls']
        cache_hit_rate = (self.watchmode_stats['cache_hits'] / (self.watchmode_stats['cache_hits'] + total_calls) * 100) if (self.watchmode_stats['cache_hits'] + total_calls) > 0 else 0
        success_rate = (self.watchmode_stats['watchmode_successes'] / self.watchmode_stats['search_calls'] * 100) if self.watchmode_stats['search_calls'] > 0 else 0

        print(f"\n📊 Watchmode API Usage:")
        print(f"  Search calls: {self.watchmode_stats['search_calls']}")
        print(f"  Source calls: {self.watchmode_stats['source_calls']}")
        print(f"  Cache hits: {self.watchmode_stats['cache_hits']}")
        print(f"  Cache hit rate: {cache_hit_rate:.1f}%")
        print(f"  Watchmode success rate: {success_rate:.1f}%")

        # Phase 3: Print Watchmode quota report and save metrics
        if self.watchmode_client:
            self.watchmode_client.print_quota_report()
            self.watchmode_client.save_run_metrics()

        print(f"\n📊 Agent Scraper Usage:")
        print(f"  Agent enabled: {self.config.get('agent_scraper', {}).get('enabled', True)}")
        print(f"  Agent initialized: {self.agent_scraper is not None and self.agent_scraper is not False}")
        print(f"  Agent attempts: {self.watchmode_stats['agent_attempts']}")
        print(f"  Agent successes: {self.watchmode_stats['agent_successes']}")
        print(f"  Agent cache hits: {self.watchmode_stats['agent_cache_hits']}")
        if self.watchmode_stats['agent_attempts'] > 0:
            agent_success_rate = (self.watchmode_stats['agent_successes'] / self.watchmode_stats['agent_attempts'] * 100)
            print(f"  Agent success rate: {agent_success_rate:.1f}%")
        else:
            print(f"  ⚠️  Agent scraper was never called (check if movies have Netflix/Disney+/Hulu providers)")

        print(f"\n📊 Platform Scraper Statistics (Amazon/Apple TV):")
        platform_config = self.config.get('platform_scraper', {})
        print(f"  Platform scraper enabled: {platform_config.get('enabled', True)}")
        print(f"  Platform scraper initialized: {self.platform_scraper is not None and self.platform_scraper is not False}")
        platforms_config = platform_config.get('platforms', {})
        print(f"  Amazon enabled: {platforms_config.get('amazon', True)}")
        print(f"  Apple TV enabled: {platforms_config.get('apple_tv', True)}")

        platform_attempts = self.watchmode_stats.get('platform_scraper_attempts', 0)
        platform_successes = self.watchmode_stats.get('platform_scraper_successes', 0)
        platform_failures = self.watchmode_stats.get('platform_scraper_failures', 0)

        print(f"  Platform scraper attempts: {platform_attempts}")
        print(f"  Platform scraper successes: {platform_successes}")
        print(f"  Platform scraper failures: {platform_failures}")

        if platform_attempts > 0:
            platform_success_rate = (platform_successes / platform_attempts * 100)
            print(f"  Platform scraper success rate: {platform_success_rate:.1f}%")

            # Compare with Watchmode success rate
            if success_rate > 0:
                comparison = "higher" if platform_success_rate > success_rate else "lower"
                print(f"  Success rate vs Watchmode API: {platform_success_rate:.1f}% ({comparison} than {success_rate:.1f}%)")
        else:
            print(f"  ⚠️  Platform scraper was never called (check if movies have Amazon/Apple TV providers)")

        # Show maintenance info
        last_update = platform_config.get('maintenance', {}).get('last_selector_update', 'unknown')
        update_freq = platform_config.get('maintenance', {}).get('expected_update_frequency', 'quarterly')
        print(f"  Last selector update: {last_update}")
        print(f"  Expected update frequency: {update_freq}")

        print(f"\n📊 RT Scraper Usage:")
        print(f"  RT attempts: {self.watchmode_stats['rt_attempts']}")
        print(f"  RT successes: {self.watchmode_stats['rt_successes']}")
        print(f"  RT cache hits: {self.watchmode_stats['rt_cache_hits']}")
        if self.watchmode_stats['rt_attempts'] > 0:
            rt_success_rate = (self.watchmode_stats['rt_successes'] / self.watchmode_stats['rt_attempts'] * 100)
            print(f"  RT success rate: {rt_success_rate:.1f}%")

        print(f"\n📊 Admin Override Usage:")
        print(f"  Manual tracking hits: {self.watchmode_stats.get('manual_tracking_hits', 0)}")
        print(f"  Override hits: {self.watchmode_stats['override_hits']}")
        if self.watchmode_stats['override_hits'] > 0:
            print(f"  Movies with manual overrides: {self.watchmode_stats['override_hits']}")

        print(f"\n🔍 Schema Validation:")
        print(f"  Validation passes: {self.watchmode_stats['schema_validation_passes']}")
        print(f"  Validation warnings: {self.watchmode_stats['schema_validation_warnings']}")
        total_validations = self.watchmode_stats['schema_validation_passes'] + self.watchmode_stats['schema_validation_warnings']
        if total_validations > 0:
            pass_rate = (self.watchmode_stats['schema_validation_passes'] / total_validations * 100)
            print(f"  Validation pass rate: {pass_rate:.1f}%")
            if self.watchmode_stats['schema_validation_warnings'] > total_validations * 0.05:  # Alert if warnings > 5%
                print(f"  ⚠️  WARNING: High validation failure rate ({self.watchmode_stats['schema_validation_warnings']}/{total_validations}) - check for systematic schema issues")

        # Discovery statistics (if discovery was run)
        if self.discovery_stats['api_calls'] > 0:
            print(f"\n🔍 Discovery Statistics:")
            print(f"  API calls: {self.discovery_stats['api_calls']}")
            print(f"  Pages fetched: {self.discovery_stats['pages_fetched']}")
            print(f"  Total results: {self.discovery_stats['total_results']}")
            print(f"  New movies added: {self.discovery_stats['new_movies_added']}")
            print(f"  Duplicates skipped: {self.discovery_stats['duplicates_skipped']}")
            if self.discovery_stats['pages_fetched'] > 0:
                avg_results_per_page = self.discovery_stats['total_results'] / self.discovery_stats['pages_fetched']
                print(f"  Average results per page: {avg_results_per_page:.1f}")
            if self.discovery_stats['debug_enabled']:
                print(f"  Debug mode was enabled for this run")

        # Clear ASIN cache at end of generation run to bound memory
        cache_size = len(self._amazon_asin_cache)
        self._amazon_asin_cache.clear()
        if cache_size > 0:
            print(f"\n📦 Amazon ASIN cache cleared ({cache_size} entries)")

    def apply_admin_overrides(self, display_movies):
        """Apply admin panel decisions to final output"""

        # Load admin decisions if they exist
        hidden = []
        featured = []
        ordering = []

        if os.path.exists('admin/hidden_movies.json'):
            with open('admin/hidden_movies.json', 'r') as f:
                hidden = json.load(f)

        if os.path.exists('admin/featured_movies.json'):
            with open('admin/featured_movies.json', 'r') as f:
                featured = json.load(f)

        if os.path.exists('admin/ordering.json'):
            with open('admin/ordering.json', 'r') as f:
                ordering_data = json.load(f)
                if isinstance(ordering_data, list):
                    ordering = ordering_data

        # Filter out hidden movies
        filtered_movies = [m for m in display_movies
                          if str(m['id']) not in hidden]

        # Mark featured movies
        for movie in filtered_movies:
            if str(movie['id']) in featured:
                movie['featured'] = True

        # Apply editorial ordering if specified
        if ordering:
            ordered_movies = []
            remaining_movies = []

            # Create a map of movie ID to movie object for quick lookup
            movie_map = {str(movie['id']): movie for movie in filtered_movies}

            # Add ordered movies first (in specified order)
            for movie_id in ordering:
                movie_id_str = str(movie_id)
                if movie_id_str in movie_map:
                    ordered_movies.append(movie_map[movie_id_str])
                    # Remove from remaining to avoid duplicates
                    del movie_map[movie_id_str]

            # Add remaining movies in their original order (by digital_date desc)
            remaining_movies = list(movie_map.values())
            remaining_movies.sort(key=lambda x: x['digital_date'], reverse=True)

            # Combine ordered + remaining
            filtered_movies = ordered_movies + remaining_movies

        hidden_count = len(display_movies) - len(filtered_movies)
        featured_count = len([m for m in filtered_movies if m.get('featured')])
        ordered_count = len(ordering) if ordering else 0

        print(f"📝 Admin overrides applied:")
        print(f"  Hidden movies: {hidden_count}")
        print(f"  Featured movies: {featured_count}")
        if ordered_count > 0:
            print(f"  Editorial ordering: {ordered_count} movies pinned to top")

        return filtered_movies, hidden, featured

