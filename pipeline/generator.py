#!/usr/bin/env python3
"""
Data Generator - Core data generation pipeline for NRW.

Extracted from monolithic generate_data.py (2025-11-10) for better maintainability.
Handles movie discovery, tracking, enrichment, and display data generation.
"""

import json
import requests
import yaml
from datetime import datetime, timedelta, timezone
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
from constants import PLACEHOLDER_ASINS, get_scraper_config, MAX_ENRICHMENT_BATCH, ENRICHMENT_LOOP_TIMEOUT_MINUTES
try:
    from streaming_platform_scraper import StreamingPlatformScraper
except ImportError:
    StreamingPlatformScraper = None

# Phase 3: TMDB-only provider discovery (Watchmode removed for cost/quota reasons)


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
    def __init__(self, enrichment_enabled: bool = True):
        # Set enrichment flag immediately to avoid timing bugs
        self.enrichment_enabled = enrichment_enabled

        # Initialize logger FIRST before any operations that might log
        self.logger = setup_logger('data_generator', 'logs/admin.log', logging.INFO)

        # Initialize storage service (extracted 2025-11-10)
        from pipeline import StorageService
        self.storage = StorageService(self.logger)

        # Initialize enrichment state manager (2025-11-11)
        # Separate persistence for enrichment tracking to prevent race conditions
        from enrichment_state import EnrichmentStateManager
        self.enrichment_state = EnrichmentStateManager()

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

        # Phase 3: TMDB-only provider discovery (no external API needed)
        # Watchmode API removed for cost/quota reasons - using TMDB providers instead
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
            'cache_hits': 0,
            'streaming_attempts': 0,
            'streaming_successes': 0,
            'streaming_failures': 0,  # Added - required by EnrichmentService
            'streaming_cache_hits': 0,
            'override_hits': 0,
            'rt_attempts': 0,
            'rt_successes': 0,
            'rt_cache_hits': 0,
            'trailer_attempts': 0,
            'trailer_successes': 0,
            'trailer_cache_hits': 0,
            'schema_validation_warnings': 0,
            'schema_validation_passes': 0,
            'search_calls': 0,  # Added - missing key causing crash
            'source_calls': 0,  # Added - missing key causing crash
            'watchmode_successes': 0  # Added - used in success rate calculation
        }

        # Initialize validation service (extracted 2025-11-10) - shares watchmode_stats dict
        from pipeline import ValidationService
        self.validator = ValidationService(
            logger=self.logger,
            storage_service=self.storage,
            config=self.config,
            stats_dict=self.watchmode_stats
        )

        # Initialize scraper instances before enrichment service
        self.streaming_scraper = None  # Initialize attribute first
        self.vod_scraper = None  # Initialize attribute first
        self._init_streaming_scraper()  # Initialize streaming scraper
        self.trailer_scraper = None  # Lazy initialization for trailer scraping
        self.youtube_trailer_cache = self.storage.load_cache('cache/youtube_trailer_cache.json')
        self.rt_scraper = None  # Lazy initialization for RT scraping with Playwright
        self.wikipedia_scraper = None  # Lazy initialization for Wikipedia scraping with Playwright

        # ASIN cache for Amazon links to avoid repeated searches
        self._amazon_asin_cache = {}

        # Initialize enrichment service (extracted 2025-11-10) - shares watchmode_stats dict
        from pipeline import EnrichmentService
        self.enrichment = EnrichmentService(
            logger=self.logger,
            config=self.config,
            storage_service=self.storage,
            validator_service=self.validator,
            stats_dict=self.watchmode_stats,
            streaming_scraper=self.streaming_scraper,
            vod_scraper=self.vod_scraper,
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
    # - _init_streaming_scraper
    # - get_watch_links (main enrichment orchestration)
    # - _enforce_vod_scraper_rate_limit
    # - _get_platform_deep_link_with_cache
    # - _normalize_watch_links_urls
    # - _try_streaming_scraper
    # - is_actual_amazon_service
    # - is_actual_apple_service
    # - validate_service_link_consistency
    # - _try_vod_scraper
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

            self.logger.info(f"Intake state updated: {new_state['last_success_date']}")
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

        self.logger.info(f"Intaking new premieres from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

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
            if not self.storage.atomic_write_json(db, 'movie_tracking.json', backup=True):
                self.logger.error("Failed to save movie_tracking.json after discovery")
                raise IOError("Discovery database write failed")

        # Log discovery summary
        self.logger.info(f"Intake complete: {new_movies_added} new movies added from {self.discovery_stats['pages_fetched']} pages")
        if debug or new_movies_added == 0:
            self.logger.info(f"Intake stats: {self.discovery_stats['total_results']} total results, {self.discovery_stats['duplicates_skipped']} duplicates")

        # Emit JSON artifact for robust metrics capture
        try:
            os.makedirs('metrics', exist_ok=True)

            # Calculate scan window for audit trail
            start_date = since_datetime.strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')

            # Determine discovery mode
            if since_date:
                mode = 'manual'
            elif bootstrap or not discovery_state.get('last_success_date'):
                mode = 'bootstrap'
            else:
                mode = 'incremental'

            discovery_run_data = {
                'timestamp': datetime.now().isoformat(),
                'operation': 'intake_premieres',
                'scan_window': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'days_back': days_back,
                    'mode': mode,
                    'bootstrap': bootstrap
                },
                'results': {
                    'discovered': new_movies_added,
                    'pages_fetched': self.discovery_stats['pages_fetched'],
                    'total_results': self.discovery_stats['total_results'],
                    'duplicates_skipped': self.discovery_stats['duplicates_skipped']
                }
            }

            with open('metrics/intake_run.json', 'w') as f:
                json.dump(discovery_run_data, f, indent=2)

            print(f"📊 Intake metrics saved to metrics/intake_run.json: {start_date} to {end_date} ({mode} mode, {new_movies_added} found)")
            self.logger.info(f"Intake metrics saved: {discovery_run_data}")
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

        print(f'DB loaded: {len(db.get("movies", {}))} total movies')
        tracking_count = len([m for m in db['movies'].values() if m['status'] == 'tracking'])
        print(f"🔍 Raw tracking filter: {tracking_count} movies")

        # Get all tracking movies with their IDs
        tracking_movies = [(movie_id, movie) for movie_id, movie in db['movies'].items()
                          if movie['status'] == 'tracking']

        print(f"🔍 Assigned tracking_movies list: {len(tracking_movies)}")
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
        newly_available_ids = []  # Track movie IDs that transition to available

        print(f"\n🎬 Checking {total_to_check} movies for digital availability...\n")
        discovery_start_time = time.time()

        try:
            for movie_id, movie in tracking_movies:
                checked += 1

                # Progress indicator every 100 movies (less noisy but still informative)
                if checked % 100 == 0 or checked == total_to_check:
                    progress_pct = (checked / total_to_check) * 100
                    elapsed = time.time() - discovery_start_time
                    rate = checked / elapsed if elapsed > 0 else 0
                    remaining = (total_to_check - checked) / rate if rate > 0 else 0
                    print(f"  📊 Discovery: {checked}/{total_to_check} ({progress_pct:.1f}%) | {newly_digital} found | {int(elapsed//60)}m elapsed | ~{int(remaining//60)}m remaining")

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

                    # Always update has_providers flag based on current provider availability
                    movie['has_providers'] = has_providers

                    # Check if this movie needs enrichment
                    needs_enrichment = False

                    if has_providers and movie['status'] == 'tracking':
                        # Newly discovered movie - always needs enrichment
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
                        needs_enrichment = True

                        # Show which service it appeared on
                        first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0]
                        print(f"  ✓ {movie['title']} now on {first_service}!")

                    elif has_providers and movie['status'] == 'available':
                        # Already available movie - check if it needs enrichment
                        is_enriched = self.enrichment_state.is_enriched(movie_id)

                        if not is_enriched:
                            # Never been enriched - check if it became available recently
                            digital_date_str = movie.get('digital_date', '')
                            if digital_date_str:
                                try:
                                    digital_date = datetime.strptime(digital_date_str, '%Y-%m-%d')
                                    days_since_available = (datetime.now() - digital_date).days

                                    if days_since_available <= 7:
                                        # Available in last 7 days and never enriched
                                        needs_enrichment = True
                                        print(f"  🔄 {movie['title']} available {days_since_available} days ago, needs enrichment")
                                except ValueError:
                                    # Invalid date format, skip
                                    pass

                    # Add to enrichment queue if needed
                    if needs_enrichment:
                        newly_available_ids.append(movie_id)  # Track for enrichment state file

                        # ARCHITECTURAL FIX: Immediately add newly discovered movie to data.json
                        # Movies should appear on site upon discovery, not contingent on enrichment success
                        if movie['status'] == 'available' and needs_enrichment:
                            self.add_movie_to_site_immediately(movie_id, movie)

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
                'operation': 'discover_availability',
                'scan_context': {
                    'poll_all_tracking': poll_all_tracking,
                    'max_to_check': max_to_check,
                    'priority_days': priority_days,
                    'full_scan': poll_all_tracking
                },
                'results': {
                    'polled': checked,
                    'transitions': newly_digital,
                    'failed': failed,
                    'scan_tag': scan_tag.strip() if scan_tag else None
                }
            }

            with open('metrics/discovery_run.json', 'w') as f:
                json.dump(discovery_run_data, f, indent=2)

            print(f"📊 Metrics saved to metrics/discovery_run.json")
            self.logger.info(f"Provider discovery metrics saved: {discovery_run_data}")

            # Write enrichment state file with newly available movie IDs
            # This file is consumed by generate_display_data() to determine which movies need enrichment
            print(f"📝 Creating enrichment state file for {len(newly_available_ids)} newly available movies")
            self.logger.info(f"Creating enrichment state file for {len(newly_available_ids)} newly available movies")

            # Use consistent datetime object for both date and timestamp to prevent discrepancies
            # State file uses UTC timestamps for consistency with CI and other metrics
            now = datetime.now(timezone.utc)
            today_date = now.strftime('%Y-%m-%d')
            print(f"📅 State file date: {today_date}")
            self.logger.info(f"State file date: {today_date}")

            # Load existing queue and merge with new discoveries (persistent queue)
            existing_queue = set()
            if os.path.exists('metrics/newly_available.json'):
                try:
                    with open('metrics/newly_available.json', 'r') as f:
                        existing_data = json.load(f)
                        existing_queue = set(existing_data.get('movie_ids', []))
                except Exception as e:
                    print(f"⚠️  Could not load existing queue: {e}")

            # Merge new discoveries with existing queue
            merged_queue = existing_queue.union(set(newly_available_ids))
            new_count = len(newly_available_ids)
            existing_count = len(existing_queue)
            total_count = len(merged_queue)

            newly_available_data = {
                'date': today_date,
                'timestamp': now.isoformat(),
                'movie_ids': list(merged_queue),
                'count': total_count
            }

            try:
                with open('metrics/newly_available.json', 'w') as f:
                    json.dump(newly_available_data, f, indent=2)

                # Verify file was written successfully
                file_size = os.path.getsize('metrics/newly_available.json')
                print(f"✅ State file written successfully: {file_size} bytes")
                self.logger.info(f"State file written successfully: {file_size} bytes")
            except Exception as write_error:
                print(f"❌ Failed to write state file: {write_error}")
                self.logger.error(f"Failed to write enrichment state file: {write_error}")
                raise

            if new_count > 0:
                print(f"📝 Persistent queue updated: {new_count} new discoveries")
                print(f"   Queue totals: {existing_count} existing + {new_count} new = {total_count} pending enrichment")
                self.logger.info(f"Persistent queue: {new_count} new discoveries added, {total_count} total pending: {newly_available_ids}")
            else:
                print(f"📝 No new discoveries - queue unchanged ({total_count} movies still pending)")
                self.logger.info(f"No new discoveries - persistent queue unchanged with {total_count} pending movies")

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

    # validate_enrichment_consistency DELETED (2025-12-05) - was causing loop bug

    # atomic_write_json moved to pipeline/storage.py (2025-11-10)

    # atomic_move_to_archive moved to pipeline/storage.py (2025-11-10)

    # load_all_movies moved to pipeline/storage.py (2025-11-10)

    # validate_data_json_schema moved to pipeline/validation.py (2025-11-10)

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

    # ============================================================================
    # Essential helper methods (2025-11-11 - added during enrichment state fix)
    # ============================================================================

    def simplify_provider_name(self, provider_name):
        """Simplify provider names for display
        Examples:
        - 'Amazon Prime Video' → 'Amazon'
        - 'Viaplay Amazon Channel' → 'Amazon'
        - 'AMC Plus Apple TV Channel' → 'AMC+'
        """
        if not provider_name:
            return provider_name

        # Most specific patterns first (check AMC before Amazon)
        simplifications = [
            ('amc', 'AMC+'),
            ('netflix', 'Netflix'),
            ('disney', 'Disney+'),
            ('hulu', 'Hulu'),
            ('hbo max', 'Max'),
            ('paramount', 'Paramount+'),
            ('peacock', 'Peacock'),
            ('amazon', 'Amazon'),
            ('apple tv', 'Apple TV'),
            ('shudder', 'Shudder'),
            ('mubi', 'MUBI'),
            ('criterion', 'Criterion'),
            ('vudu', 'Vudu'),
            ('google play', 'Google Play'),
            ('youtube', 'YouTube'),
            ('fandango', 'Fandango'),
        ]

        provider_lower = provider_name.lower()
        for pattern, simplified in simplifications:
            if pattern in provider_lower:
                return simplified

        return provider_name


    def get_movie_details(self, movie_id):
        """Get full movie details from TMDB"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {
            'api_key': self.tmdb_key,
            'append_to_response': 'credits,videos,external_ids'
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching details for {movie_id}: {e}")
        return None

    def fetch_tmdb_type4_date(self, movie_id):
        """
        Fetch US Type 4 (Digital) release date from TMDB release_dates endpoint.

        Args:
            movie_id: TMDB movie ID (string or int)

        Returns:
            str: Date in YYYY-MM-DD format if Type 4 found, None otherwise
        """
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        params = {'api_key': self.tmdb_key}

        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return None

            data = response.json()
            for entry in data.get('results', []):
                if entry.get('iso_3166_1') == 'US':
                    for release in entry.get('release_dates', []):
                        if release.get('type') == 4:  # Type 4 = Digital
                            release_date = release.get('release_date', '')
                            if release_date:
                                # Return YYYY-MM-DD portion only
                                return release_date[:10]
            return None
        except Exception as e:
            self.logger.debug(f"Type 4 date lookup failed for {movie_id}: {e}")
            return None

    def add_movie_to_site_immediately(self, movie_id, movie_data):
        """
        ENHANCED: Add newly discovered movie to data.json immediately upon discovery

        This is the PRIMARY path for getting movies into data.json.
        Enrichment becomes a secondary overlay process.

        ENHANCEMENTS:
        - Atomic writes with backups
        - Fallback for TMDB failures (never skips writing)
        - Schema validation before reading
        - Discovery metadata tracking
        - Enhanced error handling

        Args:
            movie_id: TMDB movie ID (string)
            movie_data: Movie data from movie_tracking.json with basic info and providers

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Load current data.json with validation - CRITICAL: Do not proceed if loading fails
            data_movies = []
            if os.path.exists('data.json'):
                try:
                    # Validate schema before loading
                    if not self.validator.validate_data_json_schema('data.json'):
                        # Schema validation failed - abort to prevent data loss
                        error_msg = "data.json schema validation failed"
                        self.logger.error(f"Immediate write aborted for {movie_id}: {error_msg}")
                        print(f"   ❌ Schema validation failed - aborting immediate write to protect existing data")

                        # Optionally quarantine the bad file
                        quarantine_path = f"data.json.quarantine.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        try:
                            os.rename('data.json', quarantine_path)
                            self.logger.warning(f"Quarantined invalid data.json to {quarantine_path}")
                            print(f"   🚨 Invalid data.json quarantined to {quarantine_path}")
                        except Exception as quarantine_error:
                            self.logger.error(f"Failed to quarantine invalid data.json: {quarantine_error}")

                        return False

                    # Use storage method for safer reading if available
                    if hasattr(self.storage, 'load_json') and callable(self.storage.load_json):
                        try:
                            existing_data = self.storage.load_json('data.json')
                            data_movies = existing_data.get('movies', []) if existing_data else []
                        except Exception as storage_error:
                            raise Exception(f"Storage load_json failed: {storage_error}")
                    else:
                        # Fallback to direct file reading
                        with open('data.json', 'r') as f:
                            existing_data = json.load(f)
                            data_movies = existing_data.get('movies', [])

                    self.logger.debug(f"Loaded {len(data_movies)} existing movies from data.json")

                except Exception as e:
                    # CRITICAL: Do NOT continue with empty list - abort to prevent data loss
                    self.logger.error(f"Failed to load data.json for immediate write: {e}")
                    print(f"   ❌ Cannot load data.json - aborting immediate write to protect existing data")

                    # Backup the problematic file
                    backup_path = f"data.json.backup.failed_read.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    try:
                        import shutil
                        shutil.copy2('data.json', backup_path)
                        self.logger.info(f"Backed up problematic data.json to {backup_path}")
                        print(f"   💾 Problematic data.json backed up to {backup_path}")
                    except Exception as backup_error:
                        self.logger.error(f"Failed to backup problematic data.json: {backup_error}")

                    return False
            else:
                # data.json doesn't exist - safe to create new one
                data_movies = []
                self.logger.info("data.json doesn't exist - creating new file")

            # Check if movie already exists
            existing_index = None
            for i, existing in enumerate(data_movies):
                if str(existing.get('id')) == str(movie_id):
                    existing_index = i
                    break

            if existing_index is not None:
                title = movie_data.get('title', f'Movie {movie_id}')
                self.logger.info(f"Movie {title} ({movie_id}) already in data.json - skipping")
                print(f"   📝 Movie {title} already in data.json - skipping immediate add")
                return True

            # Get TMDB details with fallback
            movie_details = None
            try:
                movie_details = self.get_movie_details(movie_id)
            except Exception as e:
                self.logger.warning(f"TMDB fetch failed for {movie_id}: {e}")
                # Continue with minimal data - don't fail discovery

            # Create movie entry (minimal or full based on TMDB availability)
            if movie_details:
                basic_entry = self._create_full_basic_entry(movie_id, movie_data, movie_details)
            else:
                basic_entry = self._create_minimal_entry(movie_id, movie_data)
                self.logger.info(f"Created minimal entry for {movie_id} due to TMDB unavailability")

            # Add discovery metadata
            basic_entry.update({
                '_discovery_date': datetime.now().isoformat(),
                '_discovery_source': 'provider_availability_check',
                '_enrichment_status': 'pending'
            })

            # Add to beginning of movies list (newest first)
            data_movies.insert(0, basic_entry)

            # Save with atomic write and backup
            updated_data = {
                'generated_at': datetime.now().isoformat(),
                'count': len(data_movies),
                'movies': data_movies,
                '_metadata': {
                    'last_discovery_write': datetime.now().isoformat(),
                    'discovery_count': sum(1 for m in data_movies if m.get('_discovery_source')),
                    'schema_version': '2.0'
                }
            }

            # Use atomic write to prevent corruption
            if not self.storage.atomic_write_json(updated_data, 'data.json', backup=True):
                raise IOError("Atomic write to data.json failed")

            title = basic_entry.get('title', f'Movie {movie_id}')
            self.logger.info(f"Discovery-driven add: {title} ({movie_id}) -> data.json")
            print(f"   ✅ Added {title} to site immediately (discovery-driven)")

            return True

        except Exception as e:
            title = movie_data.get('title', f'Movie {movie_id}')
            self.logger.error(f"Failed immediate site add for {movie_id}: {e}")
            print(f"   ❌ Failed to add {title} to site: {e}")

            # JSONL failure-context logging for postmortems
            try:
                import os
                import json
                from datetime import datetime

                os.makedirs('logs', exist_ok=True)

                # Build failure context
                failure_context = {
                    'movie_id': str(movie_id),
                    'title': title,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'timestamp': datetime.now().isoformat(),
                    'tmdb_available': 'movie_details' in locals() and movie_details is not None,
                    'data_json_exists': os.path.exists('data.json')
                }

                # Append as JSON line to failure log
                with open('logs/immediate_write_failures.jsonl', 'a') as f:
                    f.write(json.dumps(failure_context) + '\n')

            except Exception as log_error:
                # Don't let logging errors break the main flow
                self.logger.error(f"Failed to log immediate write failure: {log_error}")

            # CRITICAL: Return False but don't raise - discovery should continue
            return False

    def _create_minimal_entry(self, movie_id, movie_data):
        """Create minimal movie entry when TMDB details unavailable

        This ensures movies appear on site even if TMDB API is down
        """
        current_time = datetime.now().isoformat()

        return {
            'id': str(movie_id),
            'title': movie_data.get('title', f'Movie {movie_id}'),
            'digital_date': movie_data.get('digital_date'),
            'bootstrap_date': False,
            'manually_corrected': False,
            'poster': None,  # Will be filled by enrichment
            'synopsis': '',  # Will be filled by enrichment
            'crew': {'director': 'Unknown', 'cast': []},  # Will be filled by enrichment
            'genres': [],    # Will be filled by enrichment
            'studio': 'Unknown',  # Will be filled by enrichment
            'runtime': None,      # Will be filled by enrichment
            'year': None,         # Will be filled by enrichment
            'country': 'Unknown', # Will be filled by enrichment
            'rt_score': None,     # Will be filled by enrichment
            'providers': movie_data.get('providers', {'rent': [], 'buy': [], 'streaming': []}),
            'links': {'wikipedia': None, 'trailer': None, 'rt': None},
            'watch_links': {},
            '_enrichment_status': 'pending',
            '_discovery_date': current_time,
            '_tmdb_fetch_failed': True,
            '_minimal_entry': True
        }

    def _create_full_basic_entry(self, movie_id, movie_data, movie_details):
        """Create full basic entry with TMDB details"""
        current_time = datetime.now().isoformat()

        # Start with minimal entry structure
        entry = {
            'id': str(movie_id),
            'title': movie_details.get('title', movie_data.get('title', f'Movie {movie_id}')),
            'digital_date': movie_data.get('digital_date'),
            'bootstrap_date': False,
            'manually_corrected': False,
            'synopsis': movie_details.get('overview', ''),
            'genres': [genre['name'] for genre in movie_details.get('genres', [])],
            'runtime': movie_details.get('runtime'),
            'year': int(movie_details.get('release_date', '1900')[:4]) if movie_details.get('release_date') else None,
            'rt_score': None,  # Will be filled by enrichment
            'providers': movie_data.get('providers', {'rent': [], 'buy': [], 'streaming': []}),
            'links': {'wikipedia': None, 'trailer': None, 'rt': None},
            'watch_links': {},
            '_enrichment_status': 'pending',
            '_discovery_date': current_time,
            '_tmdb_fetch_failed': False,
            '_minimal_entry': False
        }

        # Add poster with error handling
        if movie_details.get('poster_path'):
            entry['poster'] = f"https://image.tmdb.org/t/p/w500{movie_details['poster_path']}"
        else:
            entry['poster'] = None

        # Add studio with error handling
        production_companies = movie_details.get('production_companies', [])
        if production_companies and len(production_companies) > 0:
            entry['studio'] = production_companies[0].get('name', 'Unknown')
        else:
            entry['studio'] = 'Unknown'

        # Add country with error handling
        production_countries = movie_details.get('production_countries', [])
        if production_countries and len(production_countries) > 0:
            entry['country'] = production_countries[0].get('name', 'Unknown')
        else:
            entry['country'] = 'Unknown'

        # Add cast/crew with error handling
        entry['crew'] = {'director': 'Unknown', 'cast': []}
        if movie_details.get('credits'):
            try:
                credits = movie_details['credits']

                # Get director
                directors = [person['name'] for person in credits.get('crew', [])
                            if person.get('job') == 'Director' and person.get('name')]
                if directors:
                    entry['crew']['director'] = directors[0]

                # Get main cast (first 5)
                cast = [person['name'] for person in credits.get('cast', [])[:5]
                       if person.get('name')]
                entry['crew']['cast'] = cast

            except Exception as e:
                self.logger.warning(f"Failed to parse credits for {movie_id}: {e}")
                # Keep default values

        return entry

    def get_imdb_from_omdb(self, title, year):
        """Fallback to get IMDb ID from OMDb API when TMDB doesn't have it.

        Args:
            title: Movie title
            year: Release year (can be empty string)

        Returns:
            str: IMDb ID (e.g., 'tt12345678') or None if not found
        """
        omdb_key = self.config.get('api', {}).get('omdb_api_key')
        if not omdb_key:
            self.logger.debug("OMDb API key not configured, skipping IMDb fallback")
            return None

        try:
            from urllib.parse import quote

            # Build OMDb API URL
            url = f"http://www.omdbapi.com/?t={quote(title)}&apikey={omdb_key}"
            if year:
                url += f"&y={year}"

            response = requests.get(url, timeout=5)

            if response.status_code != 200:
                self.logger.debug(f"OMDb API error: HTTP {response.status_code}")
                return None

            data = response.json()

            if data.get('Response') == 'False':
                self.logger.debug(f"OMDb: No match for '{title}' ({year})")
                return None

            imdb_id = data.get('imdbID')
            if imdb_id:
                self.logger.debug(f"OMDb: Found IMDb ID {imdb_id} for '{title}' ({year})")
                return imdb_id

            return None

        except Exception as e:
            self.logger.debug(f"OMDb API error for '{title}': {e}")
            return None

    def find_wikipedia_url(self, title, year, imdb_id, movie_id=None):
        """Find Wikipedia URL using Playwright-based scraper with waterfall approach

        Priority waterfall:
        1. Overrides (overrides/wikipedia_overrides.json) - Manual curator fixes
        2. Playwright Scraper - Uses cache, Wikidata SPARQL, REST API, and web scraping
        3. Log missing and return None

        Args:
            title: Movie title
            year: Release year
            imdb_id: IMDb ID from TMDB external_ids (e.g., 'tt35076553')
            movie_id: TMDB ID for logging purposes

        Returns:
            Wikipedia URL string or None if not found
        """
        # 1. Check overrides first (manual curator fixes take precedence)
        if imdb_id and imdb_id in self.wikipedia_overrides:
            return f"https://en.wikipedia.org/wiki/{self.wikipedia_overrides[imdb_id]}"

        # 2. Initialize Playwright scraper lazily
        if self.wikipedia_scraper is None:
            # Check enrichment flag first
            if not self.enrichment_enabled:
                self.logger.debug("Wikipedia scraper disabled - enrichment not enabled")
                return None

            self.wikipedia_scraper = WikipediaScraperPlaywright(
                cache_file='cache/wikipedia_cache.json',
                config=self.config,
                logger=self.logger
            )

        # 3. Use Playwright scraper with waterfall approach
        # The scraper internally handles: Cache → Wikidata → REST API → Playwright scraping
        try:
            wiki_url = self.wikipedia_scraper.find_wikipedia_url(
                title=title,
                year=year,
                imdb_id=imdb_id,
                use_api=True,
                use_wikidata=True
            )

            # Update our local cache reference to match scraper's cache
            self.wikipedia_cache = self.wikipedia_scraper.cache

            # Track stats for this attempt
            self.wikipedia_stats['wikidata_attempts'] = self.wikipedia_scraper.stats.get('wikidata_attempts', 0)
            self.wikipedia_stats['wikidata_successes'] = self.wikipedia_scraper.stats.get('wikidata_successes', 0)

            return wiki_url

        except Exception as e:
            print(f"Wikipedia scraper error for {title} ({year}): {e}")
            self.logger.error(f"Wikipedia scraper error for {title} ({year}): {e}")
            return None
    

    def find_trailer_url(self, movie_details):
        """Extract trailer URL from TMDB movie details or scrape YouTube"""
        title = movie_details.get('title', '')
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''

        # 1. Check manual overrides first
        override_key = f"{title}_{year}"
        if override_key in self.trailer_overrides:
            return self.trailer_overrides[override_key]

        videos = movie_details.get('videos', {}).get('results', [])

        # 2. Prioritize official trailers from TMDB
        for video in videos:
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"

        # 3. Fall back to any YouTube video from TMDB
        for video in videos:
            if video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"

        # 4. Check YouTube scraper cache
        cache_key = f"{title}_{year}"
        if cache_key in self.youtube_trailer_cache:
            cached_url = self.youtube_trailer_cache[cache_key]
            if cached_url:  # Don't return None from cache, keep trying
                return cached_url

        # 5. Try scraping YouTube for the trailer
        if self.trailer_scraper is None:
            # Check enrichment flag first
            if not self.enrichment_enabled:
                self.logger.debug("YouTube trailer scraper disabled - enrichment not enabled")
                return None

            self.trailer_scraper = YouTubeTrailerScraper(
                cache_file='cache/youtube_trailer_cache.json',
                headless=True
            )

        # Check if this is a cache hit first
        cache_key = f"{title}_{year}"
        is_cache_hit = cache_key in self.trailer_scraper.cache

        # Track trailer scraper usage
        self.watchmode_stats['trailer_attempts'] += 1
        if is_cache_hit:
            self.watchmode_stats['trailer_cache_hits'] += 1

        scraped_url = self.trailer_scraper.find_trailer(title, year)
        if scraped_url:
            self.watchmode_stats['trailer_successes'] += 1
            return scraped_url

        # 6. Final fallback: generate YouTube search URL
        search_query = quote(f"{title} {year} trailer")
        return f"https://www.youtube.com/results?search_query={search_query}"
    

    def find_rt_url(self, title, year, imdb_id):
        """Find Rotten Tomatoes URL and score"""
        # 1. Check overrides first
        if imdb_id and imdb_id in self.rt_overrides:
            override = self.rt_overrides[imdb_id]
            if isinstance(override, dict):
                return override
            return {'url': override, 'score': None}

        # 2. Check if RT scraper is enabled
        enabled = self.config.get('rt_scraper', {}).get('enabled', True)
        if not enabled:
            print("  RT scraping disabled via config")
            search_query = quote(f"{title} {year}")
            return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}

        # 3. Use RT scraper (handles caching internally)
        result = self.scrape_rt_score(title, year)
        if result:
            return result

        # 4. Fall back to search
        search_query = quote(f"{title} {year}")
        return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}




    # ============================================================================
    # Additional helper methods from backup (2025-11-11 - Option 1 bulk copy)
    # TODO: Review and refactor these during next cleanup phase
    # ============================================================================

    def _init_streaming_scraper(self):
        """Initialize agent scraper if not already initialized"""
        if self.streaming_scraper is None:
            # Check enrichment flag first
            if not self.enrichment_enabled:
                self.logger.debug("Agent scraper disabled - enrichment not enabled")
                self.streaming_scraper = False
                return

            # Check if agent scraper is enabled in config
            streaming_config = self.config.get('streaming_scraper', {})
            enabled = streaming_config.get('enabled', True)  # Default to True if not specified

            if not enabled:
                self.logger.debug("Agent scraper disabled in config.yaml")
                self.streaming_scraper = False
                return

            # Check if playwright is available
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                self.logger.debug("Playwright not installed, agent scraper disabled")
                self.logger.debug("Install with: pip install playwright && playwright install chromium")
                self.streaming_scraper = False
                return

            try:
                # Read config settings
                cache_file = 'cache/agent_links_cache.json'  # Could be configurable

                self.logger.debug("Initializing agent scraper with Playwright...")
                self.streaming_scraper = AgentLinkScraper(
                    cache_file=cache_file,
                    config=streaming_config  # Pass entire config dict
                )
                self.logger.debug("Agent scraper initialized (Playwright)")
            except Exception as e:
                self.logger.exception(f"Failed to initialize agent scraper: {e}")
                self.streaming_scraper = False  # Mark as failed to prevent retries


    def _init_rt_scraper(self):
        """Initialize RT scraper with Playwright (lazy initialization)"""
        if self.rt_scraper is not None:
            return self.rt_scraper is not False

        # Check enrichment flag first
        if not self.enrichment_enabled:
            self.logger.debug("RT scraper disabled - enrichment not enabled")
            self.rt_scraper = False
            return False

        try:
            self.rt_scraper = RTScraperPlaywright(
                cache_file='cache/rt_cache.json',
                config=self.config,
                logger=self.logger
            )
            self.logger.debug("RT scraper initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize RT scraper: {e}")
            self.rt_scraper = False  # Mark as failed to prevent retries
            return False


    def scrape_rt_score(self, title, year):
        """Public wrapper function to scrape RT score for external consumers

        Args:
            title: Movie title
            year: Release year

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        # Initialize scraper if needed
        if not self._init_rt_scraper():
            return None

        # Check scraper availability
        if self.rt_scraper is False:
            return None

        # Use the new Playwright scraper
        try:
            result = self.rt_scraper.scrape_rt_score(title, year)

            # Update stats from scraper
            scraper_stats = self.rt_scraper.get_stats()
            self.watchmode_stats['rt_attempts'] = scraper_stats['attempts']
            self.watchmode_stats['rt_successes'] = scraper_stats['successes']
            self.watchmode_stats['rt_cache_hits'] = scraper_stats['cache_hits']

            return result
        except Exception as e:
            self.logger.error(f"RT scraping error: {e}")
            return None


    def load_cache(self, filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return {}
    

    def save_cache(self, data, filename):
        os.makedirs(os.path.dirname(filename) if '/' in filename else '.', exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)


    def generate_google_search_fallback(self, title, year, service):
        """Generate a Google search URL as fallback when no direct link is available"""
        search_query = quote(f"{title} {year} watch {service}")
        return f"https://www.google.com/search?q={search_query}"


    def log_missing_wikipedia(self, movie_id, title, year, imdb_id):
        """Log missing Wikipedia links for manual review"""
        try:
            missing_file = 'missing_wikipedia.json'
            if os.path.exists(missing_file):
                with open(missing_file, 'r') as f:
                    missing = json.load(f)
            else:
                missing = {"missing": []}
            
            entry = {
                "tmdb_id": movie_id,
                "title": title,
                "year": year,
                "imdb_id": imdb_id,
                "timestamp": datetime.now().isoformat()
            }
            
            # Avoid duplicates
            if not any(m['tmdb_id'] == movie_id for m in missing['missing']):
                missing['missing'].append(entry)
                with open(missing_file, 'w') as f:
                    json.dump(missing, f, indent=2)
        except Exception as e:
            print(f"Failed to log missing Wikipedia: {e}")


    def get_watch_links(self, movie_id, title, year, providers, force_refresh=False, tracking_data=None):
        """Get deep links with canonical streaming/rent/buy structure

        Priority waterfall:
        1. Manual watch links from movie_tracking.json - highest priority
        2. Admin overrides (admin/watch_link_overrides.json) - backward compatibility
        3. Cache (cache/watch_links_cache.json)
        4. Watchmode API
        5. Agent scraper (Netflix, Disney+, HBO Max, Hulu)
        6. TMDB provider names with null links

        Returns: {
            'streaming': {'service': 'Netflix', 'link': 'https://...'},  # subscription streaming
            'rent': {'service': 'Amazon', 'link': 'https://...'},        # rental
            'buy': {'service': 'Apple TV', 'link': 'https://...'}        # purchase
        }
        """
        # 1. Check manual watch links from tracking data FIRST (highest priority)
        if tracking_data and 'watch_links' in tracking_data and tracking_data.get('manual_watch_links'):
            manual_links = tracking_data['watch_links']
            try:
                validated_manual = self.validator.validate_watch_links_schema(manual_links, title)
                if validated_manual:
                    print(f"  Using manual watch links from tracking data for {title}: {list(validated_manual.keys())}")
                    self.watchmode_stats['manual_tracking_hits'] = self.watchmode_stats.get('manual_tracking_hits', 0) + 1

                    # Cache the validated manual links
                    cache_key = str(movie_id)
                    now = datetime.now().isoformat()
                    self.watch_links_cache[cache_key] = {
                        'links': validated_manual,
                        'cached_at': now,
                        'source': 'manual_tracking'
                    }
                    self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

                    return validated_manual
            except Exception as e:
                print(f"  Warning: Invalid manual watch links in tracking data for {title}: {e}")

        # 2. Check overrides/watch_links_overrides.json (highest priority after manual tracking)
        cache_key = str(movie_id)
        if cache_key in self.watch_links_overrides:
            override_data = self.watch_links_overrides[cache_key]
            try:
                validated_override = self.validator.validate_watch_links_schema(override_data, title)
                if validated_override:
                    print(f"  Using override from watch_links_overrides.json for {title}: {list(validated_override.keys())}")
                    self.watchmode_stats['override_hits'] = self.watchmode_stats.get('override_hits', 0) + 1
                    return validated_override
            except Exception as e:
                print(f"  Warning: Invalid override in watch_links_overrides.json for {title}: {e}")

        # 3. Check admin overrides (backward compatibility)
        validated_overrides = {}
        if cache_key in self.watch_link_overrides:
            overrides = self.watch_link_overrides[cache_key]
            # Validate overrides but continue with waterfall for non-overridden categories
            for category in ['streaming', 'rent', 'buy']:
                if category in overrides:
                    override_data = overrides[category]
                    # Validate structure
                    if isinstance(override_data, dict) and 'service' in override_data and 'link' in override_data:
                        # Validate service name is non-empty string
                        service = override_data['service']
                        if not service or not isinstance(service, str) or not service.strip():
                            print(f"  Warning: Invalid override service name for {title} {category}: {service}")
                            continue
                        # Validate URL if link is not None/empty
                        link = override_data['link']
                        if link and isinstance(link, str) and (link.startswith('http://') or link.startswith('https://')):
                            validated_overrides[category] = override_data
                        elif not link:  # Empty link means "no override for this category"
                            continue
                        else:
                            print(f"  Warning: Invalid override link for {title} {category}: {link}")

            if validated_overrides:
                print(f"  Using admin overrides for {title}: {list(validated_overrides.keys())}")
                self.watchmode_stats['override_hits'] += 1

        # 2. Check cache (unless force refresh)
        if not force_refresh and cache_key in self.watch_links_cache:
            cached = self.watch_links_cache[cache_key]
            if cached.get('links'):
                self.watchmode_stats['cache_hits'] += 1

                # Check for placeholder ASINs in cached links and purge if found
                has_placeholder_asin = False
                detected_asin = None
                for category in ['streaming', 'rent', 'buy']:
                    category_data = cached['links'].get(category, {})
                    if category_data and isinstance(category_data, dict):
                        link = category_data.get('link', '')
                        if link and any(asin in link for asin in PLACEHOLDER_ASINS):
                            detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                            has_placeholder_asin = True
                            break

                if has_placeholder_asin:
                    # Delete the cache entry with placeholder ASIN
                    del self.watch_links_cache[cache_key]
                    self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                    print(f"  Purged cache entry {cache_key} containing placeholder ASIN {detected_asin}")
                else:
                    # Migrate legacy cache format if needed
                    migrated_links = self.enrichment.migrate_legacy_cache_format(cached['links'])
                    if migrated_links != cached['links']:
                        # Update cache with migrated format
                        self.watch_links_cache[cache_key]['links'] = migrated_links

                        # Recompute source metadata based on whether any category has a non-null link
                        has_links = any(
                            link.get('link') is not None
                            for link in migrated_links.values()
                            if isinstance(link, dict)
                        )
                        source_type = 'watchmode_api' if has_links else 'tmdb_providers'
                        self.watch_links_cache[cache_key]['source'] = source_type
                        self.watch_links_cache[cache_key]['cached_at'] = datetime.now().isoformat()

                        self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                    return migrated_links

        # Service priority hierarchies
        STREAMING_PRIORITY = ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max',
                              'Hulu', 'Amazon Prime Video', 'Prime Video', 'Apple TV+',
                              'Paramount+', 'Paramount Plus', 'Peacock', 'MUBI', 'Shudder', 'Criterion Channel']

        PAID_PRIORITY = ['Amazon Video', 'Amazon', 'Prime Video', 'Apple TV', 'Vudu',
                         'Google Play Movies', 'Google Play', 'Microsoft Store']

        # Services to exclude from the database (niche/low-quality services)
        # Use centralized helper methods

        def select_best_service(service_list, priority_list):
            """Select best service from list based on priority, filtering out excluded services"""
            # Filter out excluded services first
            filtered_services = [s for s in service_list if not self.enrichment.is_excluded_service(s)]

            if not filtered_services:
                return None

            for priority_service in priority_list:
                for available_service in filtered_services:
                    if priority_service.lower() in available_service.lower():
                        return available_service
            # If no priority match, return first available (from filtered list)
            return filtered_services[0] if filtered_services else None

        # Skip external API calls for categories that already have overrides
        skip_streaming = 'streaming' in validated_overrides
        skip_rent = 'rent' in validated_overrides
        skip_buy = 'buy' in validated_overrides

        # Initialize empty provider lists (TMDB providers will be processed by scrapers)
        tmdb_streaming = []
        tmdb_rent = []
        tmdb_buy = []

        # Helper function to check if a list contains Google fallback URLs
        def has_google_fallback(link_list):
            """Check if any links in the list are Google search fallbacks"""
            if not link_list:
                return False
            return any('google.com/search' in item.get('link', '') for item in link_list)

        # Call platform scraper if:
        # 1. No data from Watchmode (original logic), OR
        # 2. Watchmode returned Google fallback URLs (needs real link)
        should_try_vod_scraper = (
            not tmdb_streaming or not tmdb_rent or not tmdb_buy or
            has_google_fallback(tmdb_streaming) or
            has_google_fallback(tmdb_rent) or
            has_google_fallback(tmdb_buy)
        )

        if StreamingPlatformScraper and should_try_vod_scraper:
            self.enrichment.try_vod_scraper(title, year, providers, tmdb_streaming, tmdb_rent, tmdb_buy, skip_streaming, skip_rent, skip_buy)

        # Check if platform scraper actually added any links
        vod_scraper_used = (
            len(tmdb_streaming) > streaming_len_before or
            len(tmdb_rent) > rent_len_before or
            len(tmdb_buy) > buy_len_before
        )

        # Build final watch_links with canonical streaming/rent/buy structure
        watch_links = {}

        # STREAMING: Prefer Watchmode, fallback to TMDB providers with smart Amazon handling (skip if overridden)
        if not skip_streaming:
            if tmdb_streaming:
                # Use Watchmode streaming data
                best_service = select_best_service([s['service'] for s in tmdb_streaming], STREAMING_PRIORITY)
                for source in tmdb_streaming:
                    if source['service'] == best_service:
                        watch_links['streaming'] = source
                        break
            elif providers.get('streaming'):
                # Fallback to TMDB provider data
                service = select_best_service(providers['streaming'], STREAMING_PRIORITY)

                # SMART FALLBACK: If TMDB says "Amazon Prime Video" but Watchmode didn't find subscription,
                # reuse any Amazon rent/buy link we have (it's the same detail page on Amazon)
                if 'Amazon Prime Video' in service and (tmdb_rent or tmdb_buy):
                    # Find any Amazon link in rent or buy sources
                    amazon_link = None
                    for source in tmdb_rent + tmdb_buy:
                        if 'Amazon' in source['service'] and source.get('link'):
                            amazon_link = source['link']
                            break

                    if amazon_link:
                        watch_links['streaming'] = {
                            'service': service,
                            'link': amazon_link  # Same page shows both Prime (free) and rent/buy options
                        }
                    else:
                        # No Amazon link available, leave as null (no Google fallback)
                        watch_links['streaming'] = {
                            'service': service,
                            'link': None
                        }
                else:
                    # Try agent scraper for supported platforms before returning null
                    agent_result = self.enrichment.try_streaming_scraper(movie_id, title, year, service, 'streaming')
                    watch_links['streaming'] = agent_result

        # RENT: Use Watchmode or fallback to platform links (skip if overridden)
        if not skip_rent:
            if tmdb_rent:
                best_service = select_best_service([s['service'] for s in tmdb_rent], PAID_PRIORITY)
                for source in tmdb_rent:
                    if source['service'] == best_service:
                        watch_links['rent'] = source
                        break
            elif providers.get('rent'):
                rent_service = select_best_service(providers.get('rent', []), PAID_PRIORITY)
                if rent_service:
                    # Try platform scraper for Amazon/Apple TV before returning null
                    if StreamingPlatformScraper and (self.enrichment.is_actual_amazon_service(rent_service) or self.enrichment.is_actual_apple_service(rent_service)):
                        self.enrichment.try_vod_scraper(title, year, providers, [], tmdb_rent, [], True, False, True)
                        # Check if platform scraper added rent links
                        if tmdb_rent:
                            best_service = select_best_service([s['service'] for s in tmdb_rent], PAID_PRIORITY)
                            for source in tmdb_rent:
                                if source['service'] == best_service:
                                    watch_links['rent'] = source
                                    break
                        else:
                            # Try agent scraper for supported services
                            agent_result = self.enrichment.try_streaming_scraper(movie_id, title, year, rent_service, 'rent')
                            watch_links['rent'] = agent_result
                    else:
                        # Try agent scraper for supported services
                        agent_result = self.enrichment.try_streaming_scraper(movie_id, title, year, rent_service, 'rent')
                        watch_links['rent'] = agent_result

        # BUY: Use Watchmode or fallback to platform links (skip if overridden)
        if not skip_buy:
            if tmdb_buy:
                best_service = select_best_service([s['service'] for s in tmdb_buy], PAID_PRIORITY)
                for source in tmdb_buy:
                    if source['service'] == best_service:
                        watch_links['buy'] = source
                        break
            elif providers.get('buy'):
                buy_service = select_best_service(providers.get('buy', []), PAID_PRIORITY)
                if buy_service:
                    # Try platform scraper for Amazon/Apple TV before returning null
                    if StreamingPlatformScraper and (self.enrichment.is_actual_amazon_service(buy_service) or self.enrichment.is_actual_apple_service(buy_service)):
                        self.enrichment.try_vod_scraper(title, year, providers, [], [], tmdb_buy, True, True, False)
                        # Check if platform scraper added buy links
                        if tmdb_buy:
                            best_service = select_best_service([s['service'] for s in tmdb_buy], PAID_PRIORITY)
                            for source in tmdb_buy:
                                if source['service'] == best_service:
                                    watch_links['buy'] = source
                                    break
                        else:
                            # Try agent scraper for supported services
                            agent_result = self.enrichment.try_streaming_scraper(movie_id, title, year, buy_service, 'buy')
                            watch_links['buy'] = agent_result
                    else:
                        # Try agent scraper for supported services
                        agent_result = self.enrichment.try_streaming_scraper(movie_id, title, year, buy_service, 'buy')
                        watch_links['buy'] = agent_result

        # Overlay admin overrides on top of auto-discovered links
        for category, override_data in validated_overrides.items():
            watch_links[category] = override_data

        # Normalize relative URLs to absolute URLs as second line of defense
        watch_links = self.enrichment.normalize_watch_links_urls(watch_links)

        # Validate schema before caching and returning
        validated_links = self.validator.validate_watch_links_schema(watch_links, title)

        # Apply affiliate tags to all validated links (after validation, before caching)
        for category in ['streaming', 'rent', 'buy']:
            if category in validated_links and isinstance(validated_links[category], dict):
                link_data = validated_links[category]
                if link_data.get('link') and link_data.get('service'):
                    # Append affiliate tag to the link
                    original_link = link_data['link']
                    tagged_link = self.enrichment.append_affiliate_tag(original_link, link_data['service'])
                    if tagged_link != original_link:
                        validated_links[category]['link'] = tagged_link
                        self.logger.debug(f"Added affiliate tag to {category} link for {title}: {link_data['service']}")

        # Validate service/link consistency and fix mismatches
        for category in ['streaming', 'rent', 'buy']:
            if category in validated_links and isinstance(validated_links[category], dict):
                link_data = validated_links[category]
                service = link_data.get('service')
                link = link_data.get('link')

                if service and link and not self.enrichment.validate_service_link_consistency(service, link, title):
                    # Mismatch detected, set to null (no Google fallback)
                    self.logger.warning(f"Replacing mismatched {category} link for {title} with null (admin flag needed)")
                    validated_links[category]['link'] = None

        # Cache result with canonical schema (use validated links)
        if validated_links:
            # Determine source type based on where links came from
            has_links = any(
                link.get('link') is not None
                for link in validated_links.values()
                if isinstance(link, dict)
            )

            # Use vod_scraper_used to accurately determine if streamer scraper added links
            if vod_scraper_used:
                source_type = 'agent_search'
            elif has_links:
                source_type = 'watchmode_api'
            else:
                source_type = 'tmdb_providers'

            self.watch_links_cache[cache_key] = {
                'links': validated_links,
                'cached_at': datetime.now().isoformat(),
                'source': source_type
            }
            self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

        return validated_links


    def _enforce_vod_scraper_rate_limit(self):
        """Enforce rate limiting for platform scraper calls"""
        if hasattr(self.vod_scraper, 'rate_limit_seconds') and self.vod_scraper.rate_limit_seconds:
            if not hasattr(self, '_last_vod_scraper_time'):
                self._last_vod_scraper_time = 0

            time_since_last = time.time() - self._last_vod_scraper_time
            if time_since_last < self.vod_scraper.rate_limit_seconds:
                sleep_time = self.vod_scraper.rate_limit_seconds - time_since_last
                print(f"  Rate limiting: sleeping {sleep_time:.1f}s before platform scraper")
                time.sleep(sleep_time)

            self._last_vod_scraper_time = time.time()


    def _get_platform_deep_link_with_cache(self, title, year, provider):
        """Get platform deep link with ASIN caching for Amazon services"""
        # Check ASIN cache for Amazon links first
        cached_asin = self._amazon_asin_cache.get((title.lower(), str(year or '').strip()))
        if cached_asin and self.enrichment.is_actual_amazon_service(provider):
            print(f"  ✓ Using cached Amazon ASIN {cached_asin} for {title}")
            return f"https://www.amazon.com/gp/video/detail/{cached_asin}"

        # No cache hit, perform actual search
        self.enrichment.enforce_vod_scraper_rate_limit()
        deep_link = self.vod_scraper.get_platform_deep_link(title, year, provider)

        # Cache Amazon ASIN if found
        if deep_link and self.enrichment.is_actual_amazon_service(provider):
            import re
            asin_match = re.search(r'/gp/video/detail/([A-Z0-9]{10})', deep_link)
            if asin_match:
                self._amazon_asin_cache[(title.lower(), str(year or '').strip())] = asin_match.group(1)

        return deep_link


    def get_enrichment_only_fields(self, movie_id, movie_data, movie_details, force_refresh=False):
        """Extract enrichment-only fields with graceful partial failure handling

        This method implements a graceful degradation strategy where individual
        enrichment source failures don't prevent saving partial data. Each source
        (Wikipedia, trailers, RT scores, watch links) is wrapped in try-catch blocks.

        Returns:
            dict: Always returns a dictionary with available data, never None
        """
        if not movie_details:
            self.logger.error(f"Movie details missing for movie_id {movie_id}")
            return None

        # Safely extract basic info with fallbacks
        title = movie_details.get('title', f'Unknown Movie {movie_id}')
        release_date = movie_details.get('release_date', '')
        year = release_date[:4] if release_date else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')

        # OMDb fallback: If TMDB doesn't have IMDb ID, try OMDb
        if not imdb_id:
            imdb_id = self.get_imdb_from_omdb(title, year)

        # Start timing this movie's enrichment
        import time
        movie_start_time = time.time()

        # Initialize result with basic TMDB data (always available)
        result = {
            'title': title,
            'poster': f"https://image.tmdb.org/t/p/w500{movie_details['poster_path']}" if movie_details.get('poster_path') else None,
            'synopsis': movie_details.get('overview', 'No synopsis available.'),
            'runtime': movie_details.get('runtime'),
            'year': int(year) if year.isdigit() else None,
            'rt_score': None,
            'links': {},
            'watch_links': {}
        }

        # Track enrichment success/failure for detailed logging
        enrichment_results = {
            'wikipedia': 'not_attempted',
            'trailer': 'not_attempted',
            'rt_score': 'not_attempted',
            'watch_links': 'not_attempted',
            'digital_date': 'not_attempted'
        }

        # Wikipedia link (isolated failure handling)
        try:
            wiki_url = self.find_wikipedia_url(title, year, imdb_id, movie_id)
            if wiki_url:
                result['links']['wikipedia'] = wiki_url
                enrichment_results['wikipedia'] = 'success'
                self.logger.debug(f"Wikipedia: Found page for {title} ({year})")
            else:
                enrichment_results['wikipedia'] = 'not_found'
                self.logger.debug(f"Wikipedia: No page found for {title} ({year})")
        except Exception as e:
            enrichment_results['wikipedia'] = 'error'
            self.logger.warning(f"Wikipedia: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # Trailer link (isolated failure handling)
        try:
            trailer_url = self.find_trailer_url(movie_details)
            if trailer_url:
                result['links']['trailer'] = trailer_url
                enrichment_results['trailer'] = 'success'
                self.logger.debug(f"Trailer: Found for {title} ({year})")
            else:
                enrichment_results['trailer'] = 'not_found'
                self.logger.debug(f"Trailer: Not found for {title} ({year})")
        except Exception as e:
            enrichment_results['trailer'] = 'error'
            self.logger.warning(f"Trailer: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # RT score and link (isolated failure handling)
        try:
            rt_data = self.find_rt_url(title, year, imdb_id)
            if rt_data:
                if isinstance(rt_data, dict):
                    if rt_data.get('url'):
                        result['links']['rt'] = rt_data.get('url')
                    result['rt_score'] = rt_data.get('score')
                else:
                    result['links']['rt'] = rt_data
                enrichment_results['rt_score'] = 'success'
                self.logger.debug(f"RT: Found data for {title} ({year}) - Score: {result['rt_score']}")
            else:
                enrichment_results['rt_score'] = 'not_found'
                self.logger.debug(f"RT: No data found for {title} ({year})")
        except Exception as e:
            enrichment_results['rt_score'] = 'error'
            self.logger.warning(f"RT: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # Watch links (isolated failure handling)
        try:
            watch_links_raw = self.enrichment.get_watch_links(movie_id, title, year, movie_data.get('providers', {}), force_refresh, tracking_data=movie_data)

            # Simplify provider names in watch links
            for category, link_obj in watch_links_raw.items():
                if isinstance(link_obj, dict) and 'service' in link_obj:
                    simplified_service = self.simplify_provider_name(link_obj['service'])
                    result['watch_links'][category] = {
                        'service': simplified_service,
                        'link': link_obj.get('link')
                    }
                else:
                    result['watch_links'][category] = link_obj

            if result['watch_links']:
                enrichment_results['watch_links'] = 'success'
                self.logger.debug(f"Watch Links: Found {len(result['watch_links'])} categories for {title} ({year})")
            else:
                enrichment_results['watch_links'] = 'not_found'
                self.logger.debug(f"Watch Links: No links found for {title} ({year})")
        except Exception as e:
            enrichment_results['watch_links'] = 'error'
            self.logger.warning(f"Watch Links: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # Extract additional TMDB metadata (with safe fallbacks)
        try:
            credits = movie_details.get('credits', {})
            director = "Unknown"
            cast = []

            for crew in credits.get('crew', []):
                if crew['job'] == 'Director':
                    director = crew['name']
                    break

            for actor in credits.get('cast', [])[:2]:  # Top 2 actors
                cast.append(actor['name'])

            genres = [g['name'] for g in movie_details.get('genres', [])]
            studio = None
            production_companies = movie_details.get('production_companies', [])
            if production_companies:
                studio = production_companies[0]['name']

            country = None
            production_countries = movie_details.get('production_countries', [])
            if production_countries:
                country = production_countries[0]['name']

            # Add metadata to result
            result.update({
                'crew': {
                    'director': director,
                    'cast': cast
                },
                'genres': genres,
                'studio': studio,
                'country': country
            })
        except Exception as e:
            self.logger.warning(f"TMDB Metadata: Error extracting for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")
            # Add fallback metadata
            result.update({
                'crew': {'director': 'Unknown', 'cast': []},
                'genres': [],
                'studio': None,
                'country': None
            })

        # Digital date correction from TMDB Type 4 (isolated failure handling)
        try:
            type4_date = self.fetch_tmdb_type4_date(movie_id)
            if type4_date:
                result['digital_date'] = type4_date
                result['_digital_date_source'] = 'tmdb_type4'
                enrichment_results['digital_date'] = 'success'
                self.logger.debug(f"Digital Date: Corrected to {type4_date} for {title}")
            else:
                result['_digital_date_source'] = 'detection'
                enrichment_results['digital_date'] = 'not_found'
        except Exception as e:
            enrichment_results['digital_date'] = 'error'
            result['_digital_date_source'] = 'detection'
            self.logger.warning(f"Digital Date: Error for {title}: {type(e).__name__}: {str(e)[:100]}")

        # Calculate enrichment timing and log detailed results
        movie_duration = time.time() - movie_start_time

        # Create enrichment summary for logging
        success_count = len([v for v in enrichment_results.values() if v == 'success'])
        error_count = len([v for v in enrichment_results.values() if v == 'error'])
        not_found_count = len([v for v in enrichment_results.values() if v == 'not_found'])

        # Enhanced console output with component-level status
        status_icons = {
            'success': '✓',
            'not_found': '○',
            'error': '✗',
            'not_attempted': '?'
        }

        wiki_icon = status_icons.get(enrichment_results['wikipedia'], '?')
        trailer_icon = status_icons.get(enrichment_results['trailer'], '?')
        rt_icon = status_icons.get(enrichment_results['rt_score'], '?')
        links_icon = status_icons.get(enrichment_results['watch_links'], '?')
        date_icon = status_icons.get(enrichment_results['digital_date'], '?')

        print(f"  ⚡ {title} ({movie_duration:.1f}s) - Wiki:{wiki_icon} Trailer:{trailer_icon} RT:{rt_icon} Links:{links_icon} Date:{date_icon} | {success_count} success, {error_count} errors")

        # Detailed logging for metrics
        self.logger.info(f"Enrichment completed for {title} ({year}) in {movie_duration:.1f}s: {enrichment_results}")

        # Always return result - never None for partial failures
        return result

    def process_movie(self, movie_id, movie_data, movie_details, force_refresh=False):
        """Process a single movie into display format"""
        if not movie_details:
            return None

        title = movie_details['title']
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')

        # OMDb fallback: If TMDB doesn't have IMDb ID, try OMDb
        if not imdb_id:
            imdb_id = self.get_imdb_from_omdb(title, year)

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
        
        # Build links object with waterfall approach and graceful failure handling
        links = {}
        rt_score = None

        # Track enrichment success/failure for detailed logging
        enrichment_results = {
            'wikipedia': 'not_attempted',
            'trailer': 'not_attempted',
            'rt_score': 'not_attempted',
            'digital_date': 'not_attempted'
        }

        # Digital date correction from TMDB Type 4 (isolated failure handling)
        digital_date = movie_data.get('digital_date')
        digital_date_source = 'detection'
        try:
            type4_date = self.fetch_tmdb_type4_date(movie_id)
            if type4_date:
                digital_date = type4_date
                digital_date_source = 'tmdb_type4'
                enrichment_results['digital_date'] = 'success'
                self.logger.debug(f"Digital Date: Corrected to {type4_date} for {title}")
            else:
                enrichment_results['digital_date'] = 'not_found'
        except Exception as e:
            enrichment_results['digital_date'] = 'error'
            self.logger.warning(f"Digital Date: Error for {title}: {type(e).__name__}: {str(e)[:100]}")

        # Wikipedia link (isolated failure handling)
        try:
            wiki_url = self.find_wikipedia_url(title, year, imdb_id, movie_id)
            if wiki_url:
                links['wikipedia'] = wiki_url
                enrichment_results['wikipedia'] = 'success'
                self.logger.debug(f"Wikipedia: Found page for {title} ({year})")
            else:
                enrichment_results['wikipedia'] = 'not_found'
                self.logger.debug(f"Wikipedia: No page found for {title} ({year})")
        except Exception as e:
            enrichment_results['wikipedia'] = 'error'
            self.logger.warning(f"Wikipedia: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # Trailer link (isolated failure handling)
        try:
            trailer_url = self.find_trailer_url(movie_details)
            if trailer_url:
                links['trailer'] = trailer_url
                enrichment_results['trailer'] = 'success'
                self.logger.debug(f"Trailer: Found for {title} ({year})")
            else:
                enrichment_results['trailer'] = 'not_found'
                self.logger.debug(f"Trailer: Not found for {title} ({year})")
        except Exception as e:
            enrichment_results['trailer'] = 'error'
            self.logger.warning(f"Trailer: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # RT link and score (isolated failure handling)
        try:
            rt_data = self.find_rt_url(title, year, imdb_id)
            if rt_data:
                if isinstance(rt_data, dict):
                    if rt_data.get('url'):
                        links['rt'] = rt_data.get('url')
                    rt_score = rt_data.get('score')
                else:
                    links['rt'] = rt_data
                enrichment_results['rt_score'] = 'success'
                self.logger.debug(f"RT: Found data for {title} ({year}) - Score: {rt_score}")
            else:
                enrichment_results['rt_score'] = 'not_found'
                self.logger.debug(f"RT: No data found for {title} ({year})")
        except Exception as e:
            enrichment_results['rt_score'] = 'error'
            self.logger.warning(f"RT: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

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
            'digital_date': digital_date,
            '_digital_date_source': digital_date_source,
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

        # Log enrichment results with visual indicators
        status_icons = {
            'success': '✓',
            'not_found': '○',
            'error': '✗',
            'not_attempted': '?'
        }

        wiki_icon = status_icons.get(enrichment_results['wikipedia'], '?')
        trailer_icon = status_icons.get(enrichment_results['trailer'], '?')
        rt_icon = status_icons.get(enrichment_results['rt_score'], '?')
        date_icon = status_icons.get(enrichment_results['digital_date'], '?')
        watch_icon = '✓' if watch_links else '○'

        self.logger.info(f"  [{wiki_icon}] Wikipedia  [{trailer_icon}] Trailer  [{rt_icon}] RT  [{date_icon}] Date  [{watch_icon}] Watch  | {title} ({year})")

        return movie_dict
    
    def generate_display_data(self, days_back=90, incremental=True, force_refresh=False):
        """Generate display data from tracking database

        Args:
            days_back: How many days back to look for available movies
            incremental: If True, only process NEW movies not already in data.json (default)
                        If False, regenerate entire data.json from scratch

        ARCHITECTURE NOTE (2025-12-05):
        Movies are no longer gated on successful enrichment. This function builds
        data.json from ALL eligible movies first (minimal stubs), then overlays
        enrichment when possible. Enrichment failures no longer hide movies.

        Data flow: Discovery → data.json (minimal) → Enrichment Overlay
        Previous: Discovery → Enrichment Gate → data.json (failures hide movies)
        """

        # Load all movies (merged from tracking and archived)
        # READ-ONLY: We no longer write back to movie_tracking.json
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

        # Filter to recently available movies
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Build lookup of existing movies by ID for watch_links validation
        existing_movies_lookup = {str(m['id']): m for m in existing_movies if isinstance(m, dict) and 'id' in m}

        # Pre-flight check: ensure metrics directory and state file environment is ready
        print("🔍 Pre-flight check: validating state file environment...")
        try:
            # Ensure metrics directory exists
            if not os.path.exists('metrics'):
                print("📁 Creating metrics directory")
                os.makedirs('metrics', exist_ok=True)
                self.logger.info("Created metrics directory")

            # Check if state file exists and is readable
            state_file_path = 'metrics/newly_available.json'
            if os.path.exists(state_file_path):
                try:
                    with open(state_file_path, 'r') as f:
                        test_data = json.load(f)
                    print(f"✅ State file exists and is readable")
                    self.logger.info("State file pre-flight check passed")
                except json.JSONDecodeError as e:
                    print(f"⚠️  State file exists but has invalid JSON: {e}")
                    self.logger.warning(f"State file JSON validation failed: {e}")
                except Exception as e:
                    print(f"⚠️  State file exists but is not readable: {e}")
                    self.logger.warning(f"State file read error: {e}")
            else:
                print(f"📄 State file doesn't exist yet - will be created if needed")
                self.logger.info("State file not found - will create if needed")

        except Exception as e:
            print(f"❌ Pre-flight check failed: {e}")
            self.logger.error(f"State file pre-flight check failed: {e}")

        # Load enrichment state file to determine which movies just became available
        # This implements enrichment-on-transition pattern (only enrich NEW arrivals)
        newly_available_ids = set()
        state_fresh = False
        today = datetime.now().strftime('%Y-%m-%d')

        if os.path.exists('metrics/newly_available.json'):
            try:
                with open('metrics/newly_available.json', 'r') as f:
                    state_data = json.load(f)
                    all_pending_ids = set(state_data.get('movie_ids', []))
                    state_date = state_data.get('date', 'unknown')

                    # Filter out already enriched movies from pending list
                    unenriched_ids = set()
                    for movie_id in all_pending_ids:
                        if not self.enrichment_state.is_enriched(str(movie_id)):
                            unenriched_ids.add(movie_id)

                    newly_available_ids = unenriched_ids
                    state_fresh = True

                    if all_pending_ids:
                        enriched_count = len(all_pending_ids) - len(unenriched_ids)
                        print(f"\n📋 Loaded pending movies: {len(all_pending_ids)} total, {enriched_count} already enriched, {len(unenriched_ids)} need enrichment")
                        if state_date != today:
                            print(f"ℹ️  State file from {state_date} - processing accumulated movies until enriched")
                    else:
                        print(f"\n📋 No pending movies to enrich")

                    self.logger.info(f"Persistent queue: {len(unenriched_ids)} movies pending enrichment from accumulated discoveries")
            except Exception as e:
                print(f"\n⚠️  Failed to load enrichment state file: {e}")
                print(f"🚫 Skipping new enrichment for this run due to unreadable state file; only stale items will be processed")
                self.logger.warning(f"Failed to load metrics/newly_available.json: {e}")
                self.logger.warning(f"Skipping new enrichment for this run due to unreadable state file; only stale items will be processed")
        else:
            print(f"\n📝 No enrichment state file found - creating empty state file for today")
            print(f"🚫 Skipping new enrichment for this run due to missing state file; only stale items will be processed")
            self.logger.info(f"No enrichment state file found - creating empty state file for today")
            self.logger.warning(f"Skipping new enrichment for this run due to missing state file; only stale items will be processed")

            # Create fresh empty state file when none exists
            empty_state_data = {
                'date': today,
                'timestamp': datetime.now().isoformat(),
                'movie_ids': [],
                'count': 0
            }

            try:
                # Ensure metrics directory exists
                os.makedirs('metrics', exist_ok=True)
                with open('metrics/newly_available.json', 'w') as f:
                    json.dump(empty_state_data, f, indent=2)
                print(f"🔄 Created empty state file for today")
                self.logger.info(f"Created empty state file for {today}")
            except Exception as write_error:
                print(f"❌ Failed to create state file: {write_error}")
                self.logger.error(f"Failed to create state file: {write_error}")
                print(f"\n📝 Will use enrichment_state.json fallback instead")

        # Separate movies by enrichment status (Phase 2.1 optimization)
        needs_enrichment = []
        already_enriched = []
        stale_enrichment = []
        deferred_enrichment = []

        for movie_id, movie_data in combined['movies'].items():
            if movie_data['status'] == 'available' and movie_data.get('digital_date'):
                try:
                    digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                    if digital_date >= cutoff_date:
                        # Check enrichment status from separate enrichment state
                        is_enriched = self.enrichment_state.is_enriched(movie_id)
                        enrichment_date = self.enrichment_state.get_enrichment_date(movie_id)

                        # Check if enrichment is stale (> 90 days old)
                        is_stale = False
                        if is_enriched and enrichment_date:
                            try:
                                enrich_dt = datetime.fromisoformat(enrichment_date)
                                age_days = (datetime.now() - enrich_dt).days
                                is_stale = age_days > 90
                            except:
                                pass

                        # ENRICHMENT-ON-TRANSITION: Only enrich if movie just became available today
                        # Requires fresh newly_available.json state file - no fallback processing
                        if state_fresh:
                            # State file is fresh - strict enrichment-on-transition mode
                            if movie_id in newly_available_ids:
                                # Movie just transitioned today - needs enrichment
                                needs_enrichment.append((movie_id, movie_data))
                            elif is_stale:
                                # Old movie but enrichment data is stale
                                stale_enrichment.append((movie_id, movie_data))
                            else:
                                # Already enriched and not stale - skip
                                already_enriched.append((movie_id, movie_data))
                        else:
                            # State file not fresh - defer new enrichment
                            if is_stale:
                                # Still process stale enrichment
                                stale_enrichment.append((movie_id, movie_data))
                            elif is_enriched:
                                # Already enriched and not stale - preserve existing
                                already_enriched.append((movie_id, movie_data))
                            else:
                                # Unenriched movies are deferred until fresh state available
                                deferred_enrichment.append((movie_id, movie_data))

                except Exception as e:
                    self.logger.warning(f"Error parsing date for {movie_data.get('title')}: {e}")

        # Phase 2.1 Optimization Report
        total_available = len(needs_enrichment) + len(already_enriched) + len(stale_enrichment) + len(deferred_enrichment)
        print(f"\n📊 Phase 2.1 Enrichment Optimization:")
        print(f"   Total available movies (last {days_back} days): {total_available}")
        print(f"   ✅ Already enriched (cached): {len(already_enriched)}")
        print(f"   🆕 Need enrichment: {len(needs_enrichment)}")
        print(f"   ⏰ Stale (>90 days, will re-enrich): {len(stale_enrichment)}")
        if not state_fresh and deferred_enrichment:
            print(f"   ⏸️  Deferred (no fresh state file): {len(deferred_enrichment)} unenriched movies will be picked up once fresh state is available")

        # Build display_index from ALL eligible movies (status=available, within days_back)
        display_index = {}

        # Add all eligible movies to display_index
        all_eligible = needs_enrichment + already_enriched + stale_enrichment + deferred_enrichment
        for movie_id, movie_data in all_eligible:
            # Initialize display_index[movie_id] with existing or minimal entry
            if movie_id in existing_movies_lookup:
                # Use existing entry as base
                display_index[movie_id] = existing_movies_lookup[movie_id].copy()
            else:
                # Create minimal dict for new movies
                display_index[movie_id] = {
                    'id': movie_id,
                    'title': movie_data.get('title', 'Unknown Title'),
                    'digital_date': movie_data.get('digital_date'),
                    'providers': movie_data.get('providers', {}),
                    'links': {},
                    'watch_links': {}
                }

        # Determine which movies to enrich this run
        to_enrich = []
        if incremental:
            # Re-enrich stale movies in batches (max 10 per run to avoid quota issues)
            stale_to_process = stale_enrichment[:10]
            if stale_to_process:
                print(f"   📝 Re-enriching {len(stale_to_process)} stale movies (batch of 10)")
            to_enrich = needs_enrichment + stale_to_process
        else:
            # Full mode: re-enrich everything
            # Check if full mode is explicitly allowed
            allow_full_enrichment = os.environ.get('ALLOW_FULL_ENRICHMENT', '').lower() == 'true'

            if not allow_full_enrichment:
                print(f"   ⚠️  FULL MODE requested but ALLOW_FULL_ENRICHMENT not set - defaulting to incremental mode")
                self.logger.warning("Full enrichment mode blocked - set ALLOW_FULL_ENRICHMENT=true to enable")

                # Fall back to incremental mode behavior
                stale_to_process = stale_enrichment[:10]
                if stale_to_process:
                    print(f"   📝 Re-enriching {len(stale_to_process)} stale movies (batch of 10)")
                to_enrich = needs_enrichment + stale_to_process
            else:
                print(f"   🔄 FULL MODE: Re-enriching ALL movies (this is a heavy maintenance operation)")
                print(f"   ⚠️  Warning: Full mode will attempt to re-enrich all {len(already_enriched)} already-enriched movies")
                self.logger.warning(f"Full enrichment mode enabled - will re-enrich all {len(already_enriched)} movies")
                to_enrich = needs_enrichment + already_enriched + stale_enrichment

        # Apply emergency batch limit to prevent runaway enrichment
        original_count = len(to_enrich)
        batch_cap_triggered = len(to_enrich) > MAX_ENRICHMENT_BATCH
        if batch_cap_triggered:
            print(f"\n⚠️  SAFETY LIMIT: Capping enrichment from {original_count} to {MAX_ENRICHMENT_BATCH} movies")
            self.logger.warning(f"Enrichment batch capped from {original_count} to {MAX_ENRICHMENT_BATCH} movies")
            to_enrich = to_enrich[:MAX_ENRICHMENT_BATCH]

        print(f"\n🎬 Processing {len(to_enrich)} movies (enrichment phase)...")
        if original_count > len(to_enrich):
            print(f"   ⚠️  Batch limited: {original_count - len(to_enrich)} movies deferred to next run")
        print(f"   API savings: {len(already_enriched) - (0 if incremental else len(already_enriched))} movies skipped")
        print(f"   ⏱️  Enrichment timeout: {ENRICHMENT_LOOP_TIMEOUT_MINUTES} minutes")

        # Enrich movies in the to_enrich list
        enriched_count = 0
        circuit_breaker_skipped = 0
        total_to_enrich = len(to_enrich)
        enrichment_start_time = time.time()
        loop_timeout_triggered = False

        for idx, (movie_id, movie_data) in enumerate(to_enrich):
            # Check if we've exceeded timeout
            elapsed_minutes = (time.time() - enrichment_start_time) / 60
            if elapsed_minutes >= ENRICHMENT_LOOP_TIMEOUT_MINUTES:
                print(f"\n⏱️  TIMEOUT: Enrichment stopped after {elapsed_minutes:.1f} minutes ({idx}/{total_to_enrich} movies processed)")
                self.logger.warning(f"Enrichment timeout after {elapsed_minutes:.1f} minutes, processed {idx}/{total_to_enrich} movies")
                loop_timeout_triggered = True
                break

            # Circuit breaker check - skip movies with too many consecutive failures
            if self.enrichment_state.should_skip_for_failures(movie_id, threshold=5):
                failure_count = self.enrichment_state.get_failure_count(movie_id)
                print(f"  🚫 Skipping {movie_data.get('title')} (circuit breaker: {failure_count} consecutive failures)")
                self.logger.warning(f"Circuit breaker triggered for movie ID {movie_id} ({movie_data.get('title')}) - {failure_count} consecutive failures")
                circuit_breaker_skipped += 1
                continue

            # Progress indicator every 10 movies
            if (idx + 1) % 10 == 0 or idx == total_to_enrich - 1:
                progress_pct = ((idx + 1) / total_to_enrich) * 100
                elapsed = time.time() - enrichment_start_time
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                remaining = (total_to_enrich - idx - 1) / rate if rate > 0 else 0
                circuit_breaker_info = f" | {circuit_breaker_skipped} skipped" if circuit_breaker_skipped > 0 else ""
                print(f"  📊 Enrichment: {idx + 1}/{total_to_enrich} ({progress_pct:.1f}%) | {enriched_count} success{circuit_breaker_info} | {int(elapsed//60)}m elapsed | ~{int(remaining//60)}m remaining")

            try:
                # Get full movie details (movie_id is the TMDB ID)
                movie_details = self.get_movie_details(movie_id)
                if movie_details:
                    # Look up existing entry in display_index
                    existing_entry = display_index[movie_id].copy()

                    # For new movies (not in data.json), use process_movie for full dict
                    if movie_id not in existing_movies_lookup:
                        enriched_dict = self.process_movie(movie_id, movie_data, movie_details, force_refresh)
                        if enriched_dict:
                            display_index[movie_id] = enriched_dict
                            print(f"  ✓ {enriched_dict['title']} - Links: {len(enriched_dict['links'])}")
                            # Mark as enriched and reset failure count
                            self.enrichment_state.mark_enriched(movie_id)
                            enriched_count += 1
                        else:
                            print(f"  ✗ process_movie failed for {movie_data.get('title')} - keeping minimal entry")
                            # Record failure for circuit breaker
                            self.enrichment_state.record_failure(movie_id, "process_movie failed")
                    else:
                        # For existing movies, overlay only enrichment fields
                        enrichment_fields = self.get_enrichment_only_fields(movie_id, movie_data, movie_details, force_refresh)
                        if enrichment_fields:
                            existing_entry.update(enrichment_fields)
                            display_index[movie_id] = existing_entry
                            print(f"  ✓ {existing_entry['title']} - Links: {len(enrichment_fields.get('links', {}))}")
                            # Mark as enriched and reset failure count
                            self.enrichment_state.mark_enriched(movie_id)
                            enriched_count += 1
                        else:
                            print(f"  ✗ enrichment overlay failed for {movie_data.get('title')} - keeping existing entry")
                            # Record failure for circuit breaker
                            self.enrichment_state.record_failure(movie_id, "enrichment overlay failed")

                else:
                    print(f"  ✗ get_movie_details failed for {movie_data.get('title')} - keeping minimal/existing entry")
                    # Record failure for circuit breaker
                    self.enrichment_state.record_failure(movie_id, "get_movie_details failed")

                # Checkpoint save every 5 movies to prevent data loss on crashes
                if (idx + 1) % 5 == 0:
                    self.enrichment_state.save()
                    print(f"  💾 Checkpoint: Enrichment state saved after {idx + 1} movies processed")
                    self.logger.info(f"Checkpoint: Enrichment state saved after {idx + 1} movies processed")

                time.sleep(self.config.get('api', {}).get('tmdb_rate_limit', 0.25))  # Rate limiting

            except Exception as e:
                print(f"  ✗ Error enriching {movie_data.get('title')}: {e} - keeping minimal/existing entry")
                # Record failure for circuit breaker
                self.enrichment_state.record_failure(movie_id, f"Exception: {str(e)[:100]}")
                # Movie stays in display_index with minimal or cached entry

                # Checkpoint save every 5 movies even on exceptions
                if (idx + 1) % 5 == 0:
                    self.enrichment_state.save()
                    print(f"  💾 Checkpoint: Enrichment state saved after {idx + 1} movies processed")
                    self.logger.info(f"Checkpoint: Enrichment state saved after {idx + 1} movies processed")

        # Save enrichment state to separate file
        self.enrichment_state.save()
        print(f"\n💾 Enrichment tracking saved: {enriched_count} movies marked as enriched")
        if circuit_breaker_skipped > 0:
            print(f"🚫 Circuit breaker: {circuit_breaker_skipped} movies skipped due to consecutive failures")
        self.logger.info(f"Enrichment state saved: {enriched_count} movies marked as enriched, {circuit_breaker_skipped} skipped by circuit breaker")

        # Clean up newly_available.json - remove successfully enriched movies from persistent queue
        if enriched_count > 0 and os.path.exists('metrics/newly_available.json'):
            try:
                with open('metrics/newly_available.json', 'r') as f:
                    queue_data = json.load(f)

                original_queue = set(queue_data.get('movie_ids', []))
                # Remove movies that are now enriched
                updated_queue = set()
                for movie_id in original_queue:
                    if not self.enrichment_state.is_enriched(str(movie_id)):
                        updated_queue.add(movie_id)

                cleaned_count = len(original_queue) - len(updated_queue)
                if cleaned_count > 0:
                    # Update the persistent queue
                    updated_data = {
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'timestamp': datetime.now().isoformat(),
                        'movie_ids': list(updated_queue),
                        'count': len(updated_queue)
                    }

                    with open('metrics/newly_available.json', 'w') as f:
                        json.dump(updated_data, f, indent=2)

                    print(f"🧹 Cleaned persistent queue: {cleaned_count} enriched movies removed, {len(updated_queue)} remain")
                    self.logger.info(f"Persistent queue cleanup: {cleaned_count} movies removed after enrichment, {len(updated_queue)} remaining")

            except Exception as e:
                print(f"⚠️  Failed to clean persistent queue: {e}")
                self.logger.warning(f"Failed to clean persistent queue: {e}")

        # Convert display_index to list for final processing
        display_movies = list(display_index.values())
        
        # Sort by digital release date (newest first)
        display_movies.sort(key=lambda x: x['digital_date'], reverse=True)

        # Apply admin panel overrides (hide/feature movies)
        display_movies, hidden_ids, featured_ids = self.apply_admin_overrides(display_movies)

        # Save enrichment metrics for orchestrator diagnostics
        enrichment_duration_seconds = time.time() - enrichment_start_time
        enrichment_metrics = {
            'timestamp': datetime.now().isoformat(),
            'batch_cap_triggered': batch_cap_triggered,
            'loop_timeout_triggered': loop_timeout_triggered,
            'movies_requested': original_count,
            'movies_processed': len(to_enrich),
            'movies_enriched': enriched_count,
            'movies_deferred': max(0, original_count - len(to_enrich)),
            'enrichment_duration_seconds': enrichment_duration_seconds,
            'max_batch_size': MAX_ENRICHMENT_BATCH,
            'timeout_limit_minutes': ENRICHMENT_LOOP_TIMEOUT_MINUTES
        }

        try:
            os.makedirs('metrics', exist_ok=True)
            with open('metrics/enrichment_run.json', 'w') as f:
                json.dump(enrichment_metrics, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save enrichment metrics: {e}")

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
        if self.streaming_scraper and self.streaming_scraper != False:
            try:
                self.streaming_scraper.close()
            except Exception as e:
                self.logger.warning(f"Failed to close agent scraper: {e}")

        # Cleanup platform scraper if initialized
        if self.vod_scraper and self.vod_scraper != False:
            try:
                self.vod_scraper.close()
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
        rt_count = len([m for m in display_movies if m.get('rt_score')])
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

        # Phase 3: TMDB-only metrics (Watchmode removed)

        print(f"\n📊 Agent Scraper Usage:")
        print(f"  Streaming enabled: {self.config.get('streaming_scraper', {}).get('enabled', True)}")
        print(f"  Agent initialized: {self.streaming_scraper is not None and self.streaming_scraper is not False}")
        print(f"  VOD attempts: {self.watchmode_stats['streaming_attempts']}")
        print(f"  VOD successes: {self.watchmode_stats['streaming_successes']}")
        print(f"  VOD cache hits: {self.watchmode_stats['streaming_cache_hits']}")
        print(f"  VOD failures: {self.watchmode_stats['streaming_failures']}")
        if self.watchmode_stats['streaming_attempts'] > 0:
            vod_success_rate = (self.watchmode_stats['streaming_successes'] / self.watchmode_stats['streaming_attempts'] * 100)
            print(f"  VOD success rate: {vod_success_rate:.1f}%")
        else:
            print(f"  ⚠️  VOD scraper was never called (check if movies have Netflix/Disney+/Hulu providers)")

        print(f"\n📊 Platform Scraper Statistics (Amazon/Apple TV):")
        vod_config = self.config.get('vod_scraper', {})
        print(f"  VOD scraper enabled: {vod_config.get('enabled', True)}")
        print(f"  VOD scraper initialized: {self.vod_scraper is not None and self.vod_scraper is not False}")
        platforms_config = vod_config.get('platforms', {})
        print(f"  Amazon enabled: {platforms_config.get('amazon', True)}")
        print(f"  Apple TV enabled: {platforms_config.get('apple_tv', True)}")

        platform_attempts = self.watchmode_stats.get('vod_attempts', 0)
        platform_successes = self.watchmode_stats.get('vod_successes', 0)
        platform_failures = self.watchmode_stats.get('vod_failures', 0)

        print(f"  VOD scraper attempts: {platform_attempts}")
        print(f"  VOD scraper successes: {platform_successes}")
        print(f"  VOD scraper failures: {platform_failures}")

        if platform_attempts > 0:
            platform_success_rate = (platform_successes / platform_attempts * 100)
            print(f"  VOD scraper success rate: {platform_success_rate:.1f}%")

            # Compare with Watchmode success rate
            if success_rate > 0:
                comparison = "higher" if platform_success_rate > success_rate else "lower"
                print(f"  Success rate vs Watchmode API: {platform_success_rate:.1f}% ({comparison} than {success_rate:.1f}%)")
        else:
            print(f"  ⚠️  VOD scraper was never called (check if movies have Amazon/Apple TV providers)")

        # Show maintenance info
        last_update = vod_config.get('maintenance', {}).get('last_selector_update', 'unknown')
        update_freq = vod_config.get('maintenance', {}).get('expected_update_frequency', 'quarterly')
        print(f"  Last selector update: {last_update}")
        print(f"  Expected update frequency: {update_freq}")

        print(f"\n📊 RT Scraper Usage:")
        print(f"  RT attempts: {self.watchmode_stats['rt_attempts']}")
        print(f"  RT successes: {self.watchmode_stats['rt_successes']}")
        print(f"  RT cache hits: {self.watchmode_stats['rt_cache_hits']}")
        if self.watchmode_stats['rt_attempts'] > 0:
            rt_success_rate = (self.watchmode_stats['rt_successes'] / self.watchmode_stats['rt_attempts'] * 100)
            print(f"  RT success rate: {rt_success_rate:.1f}%")

        print(f"\n📊 Trailer Scraper Usage:")
        print(f"  Trailer attempts: {self.watchmode_stats['trailer_attempts']}")
        print(f"  Trailer successes: {self.watchmode_stats['trailer_successes']}")
        print(f"  Trailer cache hits: {self.watchmode_stats['trailer_cache_hits']}")
        if self.watchmode_stats['trailer_attempts'] > 0:
            trailer_success_rate = (self.watchmode_stats['trailer_successes'] / self.watchmode_stats['trailer_attempts'] * 100)
            print(f"  Trailer success rate: {trailer_success_rate:.1f}%")

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

        # Intake statistics (if intake was run - TMDB API premiere ingestion)
        if self.discovery_stats['api_calls'] > 0:
            print(f"\n🔍 Intake Statistics (TMDB Premieres):")
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

        # Save scraper health metrics for operational monitoring
        self._save_scraper_health_metrics()

    def _save_scraper_health_metrics(self):
        """
        Aggregate and save scraper health metrics for operational monitoring.

        Tracks success rates, cache hits, and failure patterns across all scrapers
        to enable proactive maintenance and debugging.
        """
        from datetime import datetime
        import os

        # Calculate success rates
        def calc_rate(successes, attempts):
            if attempts == 0:
                return None
            return round((successes / attempts) * 100, 1)

        # Aggregate health metrics from all scrapers
        health = {
            "timestamp": datetime.now().isoformat(),
            "scrapers": {
                "rt_scraper": {
                    "attempts": self.watchmode_stats['rt_attempts'],
                    "successes": self.watchmode_stats['rt_successes'],
                    "cache_hits": self.watchmode_stats['rt_cache_hits'],
                    "success_rate": calc_rate(
                        self.watchmode_stats['rt_successes'],
                        self.watchmode_stats['rt_attempts']
                    ),
                    "cache_hit_rate": calc_rate(
                        self.watchmode_stats['rt_cache_hits'],
                        self.watchmode_stats['rt_attempts']
                    )
                },
                "wikipedia_scraper": {
                    "wikidata_attempts": self.wikipedia_stats['wikidata_attempts'],
                    "wikidata_successes": self.wikipedia_stats['wikidata_successes'],
                    "success_rate": calc_rate(
                        self.wikipedia_stats['wikidata_successes'],
                        self.wikipedia_stats['wikidata_attempts']
                    )
                },
                "trailer_scraper": {
                    "attempts": self.watchmode_stats['trailer_attempts'],
                    "successes": self.watchmode_stats['trailer_successes'],
                    "cache_hits": self.watchmode_stats['trailer_cache_hits'],
                    "success_rate": calc_rate(
                        self.watchmode_stats['trailer_successes'],
                        self.watchmode_stats['trailer_attempts']
                    ),
                    "cache_hit_rate": calc_rate(
                        self.watchmode_stats['trailer_cache_hits'],
                        self.watchmode_stats['trailer_attempts']
                    )
                },
                "streaming_scraper": {
                    "attempts": self.watchmode_stats['streaming_attempts'],
                    "successes": self.watchmode_stats['streaming_successes'],
                    "failures": self.watchmode_stats['streaming_failures'],
                    "cache_hits": self.watchmode_stats['streaming_cache_hits'],
                    "success_rate": calc_rate(
                        self.watchmode_stats['streaming_successes'],
                        self.watchmode_stats['streaming_attempts']
                    )
                },
                "vod_scraper": {
                    "attempts": self.watchmode_stats.get('vod_attempts', 0),
                    "successes": self.watchmode_stats.get('vod_successes', 0),
                    "failures": self.watchmode_stats.get('vod_failures', 0),
                    "success_rate": calc_rate(
                        self.watchmode_stats.get('vod_successes', 0),
                        self.watchmode_stats.get('vod_attempts', 0)
                    )
                }
            },
            "validation": {
                "passes": self.watchmode_stats['schema_validation_passes'],
                "warnings": self.watchmode_stats['schema_validation_warnings'],
                "pass_rate": calc_rate(
                    self.watchmode_stats['schema_validation_passes'],
                    self.watchmode_stats['schema_validation_passes'] +
                    self.watchmode_stats['schema_validation_warnings']
                )
            }
        }

        # Ensure metrics directory exists
        os.makedirs('metrics', exist_ok=True)

        # Append to scraper_health.jsonl (one JSON object per line for historical tracking)
        health_file = 'metrics/scraper_health.jsonl'
        try:
            with open(health_file, 'a') as f:
                import json
                f.write(json.dumps(health) + '\n')

            # Also save as latest snapshot for easy viewing
            with open('metrics/scraper_health_latest.json', 'w') as f:
                json.dump(health, f, indent=2)

            # Print concise health summary
            print(f"\n💊 Scraper Health Summary:")

            # RT Scraper
            rt_rate = health['scrapers']['rt_scraper']['success_rate']
            if rt_rate is not None:
                status = "✅" if rt_rate >= 80 else "⚠️" if rt_rate >= 50 else "❌"
                print(f"  RT Scraper: {status} {rt_rate}% success ({health['scrapers']['rt_scraper']['successes']}/{health['scrapers']['rt_scraper']['attempts']})")

            # Wikipedia Scraper
            wiki_rate = health['scrapers']['wikipedia_scraper']['success_rate']
            if wiki_rate is not None:
                status = "✅" if wiki_rate >= 80 else "⚠️" if wiki_rate >= 50 else "❌"
                print(f"  Wikipedia: {status} {wiki_rate}% success ({health['scrapers']['wikipedia_scraper']['wikidata_successes']}/{health['scrapers']['wikipedia_scraper']['wikidata_attempts']})")

            # Watchmode API
            # Watchmode API removed - using TMDB providers instead

            # Validation
            val_rate = health['validation']['pass_rate']
            if val_rate is not None:
                status = "✅" if val_rate >= 95 else "⚠️" if val_rate >= 90 else "❌"
                print(f"  Validation: {status} {val_rate}% pass rate")

            print(f"  📊 Health metrics saved to {health_file}")

        except Exception as e:
            self.logger.error(f"Failed to save scraper health metrics: {e}")
            print(f"  ⚠️  Failed to save health metrics: {e}")

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

