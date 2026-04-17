#!/usr/bin/env python3
"""
Data Generator - Core data generation pipeline for NRW.

Extracted from monolithic generate_data.py (2025-11-10) for better maintainability.
Handles movie intake, tracking, enrichment, and display data generation.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import load_env  # Load .env into os.environ
import json
import requests
import yaml
from datetime import datetime, timedelta, timezone
import time
import re
from urllib.parse import quote
import logging
from logging.handlers import RotatingFileHandler
# NOTE: Scraper imports are LAZY (inside methods) to protect intake/discovery phases
# If a scraper import fails, only enrichment breaks - not the whole pipeline
# YouTube trailer finder: Try Gemini-based hybrid first, fall back to Playwright-only
try:
    from gemini_scraper import HybridYouTubeFinder
    GEMINI_AVAILABLE = True
except ImportError as e:
    # Fallback: If Gemini module fails, use Playwright-only scraper
    from scripts.youtube_trailer_scraper import YouTubeTrailerScraper as HybridYouTubeFinder
    GEMINI_AVAILABLE = False
    # Logger not available yet at import time, will log during initialization

# RT finder: Try Gemini-based hybrid first, fall back to Playwright-only
try:
    from gemini_scraper import HybridRTFinder
    GEMINI_RT_AVAILABLE = True
except ImportError as e:
    # Fallback: If Gemini module fails, use Playwright-only scraper
    from rt_scraper_playwright import RTScraperPlaywright as HybridRTFinder
    GEMINI_RT_AVAILABLE = False

from constants import PLACEHOLDER_ASINS, get_scraper_config, MAX_ENRICHMENT_BATCH, ENRICHMENT_LOOP_TIMEOUT_MINUTES, MAX_ENRICHMENT_ATTEMPTS
try:
    from streaming_platform_scraper import StreamingPlatformScraper
except ImportError:
    StreamingPlatformScraper = None

# Watch link discovery: cache + Playwright scrapers


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

        # enrichment_state removed (2025-12-29): No longer tracking retries/failures
        # Enrichment metrics tracked in metrics/enrichment_run.json
        # Movies get ONE enrichment attempt on the day they transition to available

        self.config = self.load_config()

        # Note: Validation service initialization deferred until after enrichment_stats is created (line ~160)
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

        # Watch link discovery via cache + Playwright scrapers
        self.wikipedia_cache = self.storage.load_cache('cache/wikipedia_cache.json')
        self.rt_cache = self.storage.load_cache('cache/rt_cache.json')
        self.wikipedia_overrides = self.storage.load_cache('overrides/wikipedia_overrides.json')
        self.rt_overrides = self.storage.load_cache('overrides/rt_overrides.json')
        self.watch_links_overrides = self.storage.load_cache('overrides/watch_links_overrides.json')
        self.trailer_overrides = self.storage.load_cache('overrides/trailer_overrides.json')
        self.watch_links_cache = self.storage.load_cache('cache/watch_links_cache.json')

        # Load reviews
        self.reviews = {}
        if os.path.exists('admin/movie_reviews.json'):
            try:
                with open('admin/movie_reviews.json', 'r') as f:
                    self.reviews = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load movie reviews from admin/movie_reviews.json: {e}")
                self.reviews = {}

        # Enrichment statistics (shared across all enrichment sources)
        self.enrichment_stats = {
            'cache_hits': 0,
            'streaming_attempts': 0,
            'streaming_successes': 0,
            'streaming_failures': 0,
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
            'search_calls': 0,
            'source_calls': 0,
            'scraper_successes': 0
        }

        # Initialize validation service (extracted 2025-11-10) - shares enrichment_stats dict
        from pipeline import ValidationService
        self.validator = ValidationService(
            logger=self.logger,
            storage_service=self.storage,
            config=self.config,
            stats_dict=self.enrichment_stats
        )

        # Initialize scraper instances before enrichment service
        self.streaming_scraper = None  # Initialize attribute first
        self.vod_scraper = None  # Initialize attribute first
        self._init_streaming_scraper()  # Initialize streaming scraper
        self.trailer_finder = None  # Lazy initialization (HybridYouTubeFinder: Gemini + Playwright fallback)
        self.youtube_trailer_cache = self.storage.load_cache('cache/youtube_trailer_cache.json')
        self.bad_trailer_urls = self.storage.load_cache('cache/bad_trailer_urls.json')
        self.rt_scraper = None  # Lazy initialization for RT scraping with Playwright
        self.wikipedia_scraper = None  # Lazy initialization for Wikipedia scraping with Playwright

        # ASIN cache for Amazon links to avoid repeated searches
        self._amazon_asin_cache = {}

        # Initialize enrichment service (extracted 2025-11-10) - shares enrichment_stats dict
        from pipeline import EnrichmentService
        self.enrichment = EnrichmentService(
            logger=self.logger,
            config=self.config,
            storage_service=self.storage,
            validator_service=self.validator,
            stats_dict=self.enrichment_stats,
            streaming_scraper=self.streaming_scraper,
            vod_scraper=self.vod_scraper,
            enrichment_enabled=self.enrichment_enabled
        )
        # Inject cache references into enrichment service
        self.enrichment.set_cache_references(
            self.watch_links_cache,
            self.watch_links_overrides
        )

        # IMDB rating cache (persistent across pipeline runs)
        self._imdb_rating_cache = None
        self._imdb_dataset = None  # Lazy-loaded IMDb bulk dataset

        # Wikipedia usage statistics
        self.wikipedia_stats = {
            'wikidata_attempts': 0,
            'wikidata_successes': 0
        }

        # Discovery statistics
        self.intake_stats = {
            'pages_fetched': 0,
            'total_results': 0,
            'new_movies_added': 0,
            'duplicates_skipped': 0,
            'api_calls': 0,
            'debug_enabled': False
        }

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

    # ============================================================================
    # Enrichment methods live in pipeline/enrichment.py
    # ============================================================================
    # Watch link discovery methods are accessed via self.enrichment.method_name()
    # See pipeline/enrichment.py for: get_watch_links, try_streaming_scraper,
    # try_vod_scraper, is_excluded_service, append_affiliate_tag, etc.
    #
    # Note: _init_streaming_scraper remains here because generator creates
    # scrapers and passes them to EnrichmentService during initialization.
    # ============================================================================



    def get_3_day_baseline(self):
        """Compute 3-day average for intake and newly-digital counts"""
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
                    'intake_avg': None,
                    'newly_digital_avg': None,
                    'note': f'Need at least 3 days of data, have {len(recent_metrics)}'
                }

            last_3 = recent_metrics[-3:]
            # Handle legacy key names: intaked_today (current) > discovered_today > discovered
            def get_intake_count(m):
                return m.get('intaked_today') or m.get('discovered_today') or m.get('discovered') or 0
            # Handle legacy key names: transitions (current) > newly_digital
            def get_transition_count(m):
                return m.get('transitions') or m.get('newly_digital') or 0
            intake_avg = sum(get_intake_count(m) for m in last_3) / 3
            newly_digital_avg = sum(get_transition_count(m) for m in last_3) / 3

            return {
                'days_available': 3,
                'intake_avg': round(intake_avg, 1),
                'newly_digital_avg': round(newly_digital_avg, 1),
                'dates': [m['date'] for m in last_3]
            }

        except Exception as e:
            self.logger.error(f"Failed to compute 3-day baseline: {e}")
            return None

    def _load_intake_state(self, state_file):
        """Load intake state from metrics/intake_state.json"""
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
            self.logger.warning(f"Failed to load intake state from {state_file}: {e}")
            return {
                'last_success_at': None,
                'last_success_date': None
            }

    def _update_intake_state(self, state_file):
        """Atomically update intake state after successful intake operations"""
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
            self.logger.error(f"Failed to update intake state: {e}")

    def intake_new_premieres(self, debug=False, since_date=None, bootstrap=False):
        """Intake new movie premieres and add them to movie_tracking.json

        Args:
            debug: Enable detailed logging of intake process
            since_date: Intake since date (YYYY-MM-DD) for manual override
            bootstrap: Bootstrap intake state by using full intake.days_back window

        Returns:
            Number of new movies added
        """
        self.intake_stats['debug_enabled'] = debug

        # Get intake configuration with CI optimizations
        # Support legacy 'discovery' key fallback - prefer 'intake' key
        intake_config = self.config.get('intake', self.config.get('discovery', {}))

        # Use CI-optimized values if running in CI environment
        if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
            fallback_days_back = int(os.getenv('CI_DISCOVERY_DAYS', intake_config.get('ci_days_back', 7)))
            max_pages = int(os.getenv('CI_DISCOVERY_PAGES', intake_config.get('ci_max_pages', 10)))
        else:
            fallback_days_back = intake_config.get('days_back', 14)
            max_pages = intake_config.get('max_pages', 20)

        # Load intake state for stateful incremental intake
        state_file = 'metrics/intake_state.json'
        intake_state = self._load_intake_state(state_file)

        # Calculate since_date with stateful logic
        if since_date:
            # Manual override
            try:
                since_datetime = datetime.strptime(since_date, '%Y-%m-%d')
                if debug:
                    self.logger.info(f"Using manual since_date override: {since_date}")
            except ValueError:
                self.logger.warning(f"Invalid since_date format '{since_date}', falling back to state-based intake")
                since_datetime = None
                since_date = None
        else:
            since_datetime = None

        if not since_date:
            if bootstrap or not intake_state.get('last_success_date'):
                # Bootstrap mode or missing state - use full window
                days_back = fallback_days_back
                since_datetime = datetime.now() - timedelta(days=days_back)
                if debug:
                    self.logger.info(f"Bootstrap mode: using full intake window ({days_back} days)")
            else:
                # Incremental mode - use last success with 1-day overlap
                last_success_date = intake_state.get('last_success_date')
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
                        self.logger.info(f"Invalid state, falling back to full intake window ({days_back} days)")

        days_back = max(1, (datetime.now() - since_datetime).days)  # Ensure at least 1 day

        # Get hybrid intake flags
        enable_pass_a = intake_config.get('enable_pass_a', True)  # Digital releases (release_date + type=4)
        enable_pass_b = intake_config.get('enable_pass_b', True)  # Theatrical releases (primary_release_date)
        min_runtime = intake_config.get('min_runtime', 60)  # Minimum runtime in minutes (features only)

        if debug:
            self.logger.info(f"Starting intake: days_back={days_back}, max_pages={max_pages}")
            self.logger.info(f"Intake passes: A={enable_pass_a}, B={enable_pass_b}")

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
        all_intaked_movies = {}

        # Pass A: Direct-to-digital releases (release_date + type=4)
        if enable_pass_a:
            if debug:
                self.logger.info("Starting Pass A: Direct-to-digital releases")

            pass_a_count = self._run_intake_pass(
                'A', 'digital', start_date, end_date, max_pages,
                all_intaked_movies, existing_ids, debug, min_runtime
            )

            if debug:
                self.logger.info(f"Pass A completed: {pass_a_count} movies intaked")

        # Pass B: Theatrical releases (primary_release_date)
        if enable_pass_b:
            if debug:
                self.logger.info("Starting Pass B: Theatrical releases")

            pass_b_count = self._run_intake_pass(
                'B', 'theatrical', start_date, end_date, max_pages,
                all_intaked_movies, existing_ids, debug, min_runtime
            )

            if debug:
                self.logger.info(f"Pass B completed: {pass_b_count} movies intaked")

        # Pass C: Festival premieres (with_release_type=1 in festival regions)
        enable_pass_c = intake_config.get('enable_pass_c', True)
        if enable_pass_c:
            if debug:
                self.logger.info("Starting Pass C: Festival premieres")

            # For ongoing intake, only check current/recent festivals
            # For backfill, run_festival_backfill is called separately
            pass_c_count = self._run_festival_intake_current(
                all_intaked_movies, existing_ids, debug, min_runtime
            )

            if debug:
                self.logger.info(f"Pass C completed: {pass_c_count} festival premieres intaked")

        # Merge all intaked movies into database
        for movie_id, movie_data in all_intaked_movies.items():
            if movie_id not in existing_ids:
                db['movies'][movie_id] = movie_data
                new_movies_added += 1
                existing_ids.add(movie_id)

        # Save updated database
        if new_movies_added > 0:
            db['last_update'] = datetime.now().isoformat()
            if not self.storage.atomic_write_json(db, 'movie_tracking.json', backup=True):
                self.logger.error("Failed to save movie_tracking.json after intake")
                raise IOError("Intake database write failed")

        # Log intake summary
        self.logger.info(f"Intake complete: {new_movies_added} new movies added from {self.intake_stats['pages_fetched']} pages")
        if debug or new_movies_added == 0:
            self.logger.info(f"Intake stats: {self.intake_stats['total_results']} total results, {self.intake_stats['duplicates_skipped']} duplicates")

        # Emit JSON artifact for robust metrics capture
        try:
            os.makedirs('metrics', exist_ok=True)

            # Calculate scan window for audit trail
            start_date = since_datetime.strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')

            # Determine intake mode
            if since_date:
                mode = 'manual'
            elif bootstrap or not intake_state.get('last_success_date'):
                mode = 'bootstrap'
            else:
                mode = 'incremental'

            intake_run_data = {
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
                    'intaked': new_movies_added,  # Single field, no dual-write
                    'pages_fetched': self.intake_stats['pages_fetched'],
                    'total_results': self.intake_stats['total_results'],
                    'duplicates_skipped': self.intake_stats['duplicates_skipped'],
                    'blocked_by_filter': self.intake_stats.get('blocked_by_filter', 0)
                }
            }

            with open('metrics/intake_run.json', 'w') as f:
                json.dump(intake_run_data, f, indent=2)

            print(f"📊 Intake metrics saved to metrics/intake_run.json: {start_date} to {end_date} ({mode} mode, {new_movies_added} intaked)")
            self.logger.info(f"Intake metrics saved: {intake_run_data}")
        except Exception as e:
            self.logger.warning(f"Failed to save intake metrics artifact: {e}")

        # Update intake state after successful intake
        # CRITICAL: Always update state so next run checks from today forward
        # Even if 0 movies found, we still successfully checked this date range
        # This prevents getting stuck in bootstrap mode checking same dates forever
        self._update_intake_state(state_file)

        return new_movies_added

    def intake_new_miniseries(self, debug=False, days_back=30):
        """Intake new miniseries (limited series) from TMDB.

        Queries TMDB's /discover/tv endpoint for shows with type=Miniseries
        that premiered recently. Adds them to movie_tracking.json with
        content_type='limited_series'.

        Args:
            debug: Enable detailed logging
            days_back: How far back to look for premieres (default 30 days)

        Returns:
            int: Number of new miniseries added to tracking
        """
        print("\n" + "="*60)
        print("MINISERIES INTAKE - Discovering new limited series")
        print("="*60)

        # Load existing tracking database
        if not os.path.exists('movie_tracking.json'):
            print("⚠️  No movie_tracking.json found - creating new one")
            db = {'movies': {}}
        else:
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)

        existing_ids = set(db.get('movies', {}).keys())

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        print(f"📅 Checking miniseries from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        new_series_added = 0
        page = 1
        max_pages = 10

        while page <= max_pages:
            # TMDB /discover/tv with type=2 (Miniseries)
            url = "https://api.themoviedb.org/3/discover/tv"
            params = {
                'api_key': self.tmdb_key,
                'with_type': 2,  # Miniseries
                'first_air_date.gte': start_date.strftime('%Y-%m-%d'),
                'first_air_date.lte': end_date.strftime('%Y-%m-%d'),
                # NOTE: Removed watch_region and with_watch_monetization_types filters
                # TMDB provider data lags for new shows - we check providers separately
                'sort_by': 'first_air_date.desc',
                'language': 'en-US',
                'page': page
            }

            try:
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                self.logger.error(f"TMDB miniseries discover failed (page {page}): {e}")
                break

            results = data.get('results', [])
            if not results:
                break

            for series in results:
                tmdb_id = f"tv_{series['id']}"  # Prefix with tv_ to distinguish from movies

                if tmdb_id in existing_ids:
                    if debug:
                        print(f"   ⏭️  Already tracking: {series.get('name')}")
                    continue

                # Get full series details
                details_url = f"https://api.themoviedb.org/3/tv/{series['id']}"
                try:
                    details_resp = requests.get(details_url, params={'api_key': self.tmdb_key, 'language': 'en-US'}, timeout=15)
                    details = details_resp.json()
                except Exception as e:
                    self.logger.warning(f"Failed to get details for {series.get('name')}: {e}")
                    continue

                # Verify it's actually a miniseries
                if details.get('type') != 'Miniseries':
                    if debug:
                        print(f"   ⏭️  Not a miniseries (type={details.get('type')}): {series.get('name')}")
                    continue

                # Skip single-episode shows (TV movies misclassified as miniseries)
                episode_count = details.get('number_of_episodes', 0)
                if episode_count < 2:
                    if debug:
                        print(f"   ⏭️  Too few episodes ({episode_count}): {series.get('name')}")
                    continue

                # Get watch providers
                providers_url = f"https://api.themoviedb.org/3/tv/{series['id']}/watch/providers"
                try:
                    prov_resp = requests.get(providers_url, params={'api_key': self.tmdb_key, 'language': 'en-US'}, timeout=15)
                    prov_data = prov_resp.json()
                    us_providers = prov_data.get('results', {}).get('US', {})
                except Exception as e:
                    us_providers = {}

                # Build tracking entry
                first_air_date = series.get('first_air_date', '')
                entry = {
                    'title': series.get('name', 'Unknown'),
                    'content_type': 'limited_series',
                    'tmdb_id': series['id'],
                    'status': 'tracking',  # Always start as tracking; discovery phase handles transition to available
                    'first_air_date': first_air_date,
                    'digital_date': first_air_date,  # Use first_air_date as digital_date for sorting
                    'episode_count': details.get('number_of_episodes'),
                    'runtime': details.get('episode_run_time', [None])[0] if details.get('episode_run_time') else None,
                    'poster': f"https://image.tmdb.org/t/p/w500{series.get('poster_path')}" if series.get('poster_path') else None,
                    'synopsis': series.get('overview', ''),
                    'genres': [g['name'] for g in details.get('genres', [])],
                    'original_language': series.get('original_language'),
                    'providers': {
                        'streaming': [p['provider_name'] for p in us_providers.get('flatrate', [])],
                        'rent': [p['provider_name'] for p in us_providers.get('rent', [])],
                        'buy': [p['provider_name'] for p in us_providers.get('buy', [])]
                    },
                    'intaked_at': datetime.now().isoformat(),
                    'networks': [n['name'] for n in details.get('networks', [])]
                }

                db['movies'][tmdb_id] = entry
                existing_ids.add(tmdb_id)
                new_series_added += 1

                status_icon = "✅" if entry['status'] == 'available' else "📋"
                streaming = entry['providers'].get('streaming', [])
                streaming_info = f" on {streaming[0]}" if streaming else ""
                print(f"   {status_icon} {entry['title']} ({entry['episode_count']} eps){streaming_info}")

            # Check if more pages
            total_pages = data.get('total_pages', 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.25)  # Rate limiting

        # Save updated tracking database
        with open('movie_tracking.json', 'w') as f:
            json.dump(db, f, indent=2, ensure_ascii=False)

        print(f"\n📊 Miniseries intake complete: {new_series_added} new series added")
        self.logger.info(f"Miniseries intake: {new_series_added} new series added")

        return new_series_added

    def check_tracking_movies(self, max_to_check=None, priority_days=180):
        """
        PHASE 2: Discovery - Check tracking movies for provider availability.

        Discovers availability and writes minimal entries to data.json for immediate display.
        No enrichment happens here - that's handled by the separate --enrich phase.

        Args:
            max_to_check: Maximum number of movies to check (None = all)
            priority_days: Prioritize movies released within this many days (default 180)

        Returns:
            int: Number of newly digital movies found
        """
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

        # One-time cleanup: revert future-dated Type 4 movies incorrectly marked available
        # Safe to remove after 2026-04-28
        today_str = datetime.now().strftime('%Y-%m-%d')
        reverted_count = 0
        for mid, m in db['movies'].items():
            if (m.get('status') == 'available' and
                m.get('_discovery_source') == 'tmdb_type4' and
                m.get('digital_date', '') > today_str):
                m['status'] = 'tracking'
                m['_type4_pending'] = True
                m['enriched'] = False
                m['enrichment_date'] = None
                reverted_count += 1
                self.logger.info(f"Reverted future Type 4: {m['title']} ({m['digital_date']})")
                print(f"  🔧 Reverted future Type 4: {m['title']} ({m['digital_date']})")
        if reverted_count:
            print(f"  🔧 Reverted {reverted_count} future-dated Type 4 movies to pending")

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
                except ValueError:
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
                    except ValueError:
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
        preorder_detected = 0
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

                # False-positive awareness: if this movie was reverted from available,
                # skip the discovery source that caused the false positive.
                skip_type4 = False
                skip_provider = False
                if movie.get('_reverted_from_available'):
                    fp_source = movie.get('_false_positive_source', '')
                    if fp_source == 'tmdb_type4':
                        skip_type4 = True
                    elif fp_source == 'provider_availability_check':
                        skip_provider = True

                # PRIMARY: Type 4 digital release check (authoritative, gives accurate date)
                # Type 4 is checked first — it provides the real digital release date
                # and has fewer false positives than provider availability.
                # Future dates are stored as pending — no transition until the date arrives.
                type4_found = False
                if movie['status'] == 'tracking' and not skip_type4:
                    today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

                    if movie.get('_type4_pending'):
                        # Already have a Type 4 date stored — check if it has arrived
                        pending_date = movie.get('digital_date')
                        if pending_date:
                            try:
                                pending_dt = datetime.strptime(pending_date, '%Y-%m-%d')
                                if pending_dt <= today_dt:
                                    # Date arrived — transition to available
                                    movie['has_providers'] = True
                                    movie['status'] = 'available'
                                    movie['enriched'] = False
                                    movie['enrichment_date'] = None
                                    movie['providers'] = {'rent': [], 'buy': [], 'streaming': []}
                                    del movie['_type4_pending']
                                    movie.pop('_reverted_from_available', None)
                                    movie.pop('_false_positive_source', None)
                                    newly_digital += 1
                                    newly_available_ids.append(movie_id)
                                    self.add_movie_to_site_immediately(movie_id, movie)
                                    self.logger.info(f"Type 4 pending released: {movie['title']} — {pending_date}")
                                    print(f"  📅 {movie['title']} — pending Type 4 arrived ({pending_date})")
                                else:
                                    days_until = (pending_dt - today_dt).days
                                    self.logger.debug(f"Type 4 still pending: {movie['title']} — {days_until}d until {pending_date}")
                            except ValueError:
                                pass
                        type4_found = True  # Skip provider check either way

                    else:
                        # Fresh lookup — call TMDB Type 4 API
                        type4_date = self.fetch_tmdb_type4_date(movie_id)
                        if type4_date:
                            try:
                                type4_dt = datetime.strptime(type4_date, '%Y-%m-%d')
                                if type4_dt <= today_dt:
                                    # Skip if Type 4 was already a false positive — wait for provider discovery instead
                                    if movie.get('_type4_false_positive'):
                                        self.logger.info(f"Skipping Type 4 re-discovery for {movie['title']} (previously false positive)")
                                        continue
                                    # Past or today — immediate transition
                                    movie['has_providers'] = True
                                    movie['_discovery_source'] = 'tmdb_type4'
                                    movie['digital_date'] = type4_date
                                    movie['status'] = 'available'
                                    movie['enriched'] = False
                                    movie['enrichment_date'] = None
                                    movie['providers'] = {'rent': [], 'buy': [], 'streaming': []}
                                    movie.pop('_reverted_from_available', None)
                                    movie.pop('_false_positive_source', None)
                                    movie.pop('_providers_false_positive', None)  # Clear other source's flag
                                    newly_digital += 1
                                    newly_available_ids.append(movie_id)
                                    self.add_movie_to_site_immediately(movie_id, movie)
                                    type4_found = True
                                    self.logger.info(f"Type 4 discovery: {movie['title']} — digital release {type4_date}")
                                    print(f"  📅 {movie['title']} — digital release {type4_date}")
                                else:
                                    # Future date — store as pending, stay tracking
                                    days_until = (type4_dt - today_dt).days
                                    movie['digital_date'] = type4_date
                                    movie['_discovery_source'] = 'tmdb_type4'
                                    movie['_type4_pending'] = True
                                    type4_found = True  # Skip provider check
                                    self.logger.info(f"Type 4 future: {movie['title']} — {days_until}d until {type4_date} [pending]")
                                    print(f"  ⏳ {movie['title']} — digital in {days_until}d ({type4_date}) [pending]")
                            except ValueError:
                                pass

                # SECONDARY: Provider availability check (for ~44% of movies without Type 4)
                # Only runs when Type 4 didn't find a digital release date.
                if not type4_found and movie['status'] == 'tracking' and not movie.get('_skip_provider_discovery') and not skip_provider:
                    if str(movie_id).startswith('tv_'):
                        numeric_id = str(movie_id).replace('tv_', '')
                        url = f"https://api.themoviedb.org/3/tv/{numeric_id}/watch/providers"
                    else:
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

                        has_providers = bool(rent_names or buy_names or stream_names)
                        movie['has_providers'] = has_providers

                        if has_providers and movie['status'] == 'tracking':
                            movie['_discovery_source'] = 'provider_availability_check'

                        # Pre-order detection: buy-only + single provider = check Amazon
                        is_buy_only = bool(buy_names) and not rent_names and not stream_names
                        if is_buy_only and len(buy_names) == 1 and has_providers and movie['status'] == 'tracking':
                            amazon_status = None
                            try:
                                if not hasattr(self, '_amazon_detector'):
                                    from amazon_preorder_detector import AmazonPreorderDetector
                                    self._amazon_detector = AmazonPreorderDetector()
                                amazon_status = self._amazon_detector.check_preorder(movie['title'], movie.get('year'))
                            except Exception as e:
                                self.logger.warning(f"Amazon pre-order check failed for {movie['title']}: {e}")

                            if amazon_status == 'pre-order':
                                movie['status'] = 'pre-order'
                                movie['pre_order_detected'] = datetime.now().strftime('%Y-%m-%d')
                                movie['providers'] = {
                                    'rent': rent_names,
                                    'buy': buy_names,
                                    'streaming': stream_names
                                }
                                preorder_detected += 1
                                print(f"  ⏳ {movie['title']} is a pre-order on {buy_names[0]} — tracking for VOD date")
                                self.logger.info(f"Pre-order detected: {movie['title']} ({movie_id}) on {buy_names[0]}")
                                has_providers = False
                            elif amazon_status == 'available':
                                print(f"  ~ {movie['title']} buy-only ({buy_names[0]}) confirmed available on Amazon")
                            else:
                                has_providers = False
                                print(f"  ? {movie['title']} — Amazon check inconclusive, skipping")

                        # Transition provider-discovered movie
                        if has_providers and movie['status'] == 'tracking':
                            # Skip if providers were already a false positive — wait for Type 4 instead
                            if movie.get('_providers_false_positive'):
                                self.logger.info(f"Skipping provider re-discovery for {movie['title']} (previously false positive)")
                                continue
                            movie['status'] = 'available'
                            if not movie.get('digital_date'):
                                movie['digital_date'] = datetime.now().strftime('%Y-%m-%d')
                            movie['providers'] = {
                                'rent': rent_names,
                                'buy': buy_names,
                                'streaming': stream_names
                            }
                            movie['enriched'] = False
                            movie['enrichment_date'] = None
                            movie.pop('_reverted_from_available', None)
                            movie.pop('_false_positive_source', None)
                            movie.pop('_type4_false_positive', None)  # Clear other source's flag
                            newly_digital += 1

                            first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0] if buy_names else '?'
                            print(f"  ✓ {movie['title']} now on {first_service}!")

                            newly_available_ids.append(movie_id)
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

        preorder_note = f" {preorder_detected} pre-orders detected." if preorder_detected else ""
        completion_msg = f"Polled {checked} tracking movies, found {newly_digital} changes{scan_tag}. {failed} failed.{preorder_note}"
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
                    'preorder_detected': preorder_detected,
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

            # Write state file with ONLY today's transitions (no merge/accumulation)
            # Each day starts fresh - movies get one enrichment attempt on transition day
            newly_available_data = {
                'date': today_date,
                'timestamp': now.isoformat(),
                'movie_ids': list(newly_available_ids),
                'count': len(newly_available_ids)
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

            if len(newly_available_ids) > 0:
                print(f"📝 State file updated: {len(newly_available_ids)} new transitions to enrich")
                self.logger.info(f"State file: {len(newly_available_ids)} new transitions: {newly_available_ids}")
            else:
                print(f"📝 No new transitions today")
                self.logger.info(f"No new transitions - state file is empty")

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
                    except ValueError:
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

    def resolve_preorder_dates(self):
        """
        Daily check for all pre-order movies: try to find their actual VOD release date.

        Resolution chain per movie:
        1. TMDB Type 4 date (free, fast)
        2. Gemini search (grounded with Google Search)
        3. Neither found — skip, try again tomorrow

        When a date is found:
        - If today or past: promote to 'available', set digital_date, add to site immediately
        - If future: promote to 'available', set digital_date (front-end hides until date arrives)

        Returns:
            int: Number of pre-orders resolved
        """
        print("\n📅 Resolving pre-order dates...")
        self.logger.info("Starting daily pre-order date resolution")

        # Load tracking database
        db = self.storage.load_json('movie_tracking.json')
        if not db:
            print("  ❌ Could not load movie_tracking.json")
            return 0

        movies = db.get('movies', db)

        # Find all pre-order movies
        preorder_movies = {
            mid: movie for mid, movie in movies.items()
            if movie.get('status') == 'pre-order'
        }

        if not preorder_movies:
            print("  No pre-order movies to resolve")
            self.logger.info("No pre-order movies found")
            return 0

        print(f"  Found {len(preorder_movies)} pre-order movie(s) to check")

        resolved = 0
        gemini_finder = None

        for movie_id, movie in preorder_movies.items():
            title = movie.get('title', f'Movie {movie_id}')
            year = movie.get('year')
            buy_providers = movie.get('providers', {}).get('buy', [])
            provider_name = buy_providers[0] if buy_providers else None

            print(f"  Checking: {title} ({year or 'unknown year'})...")

            vod_date = None

            # Step 1: Try TMDB Type 4 date (free, fast)
            try:
                type4_date = self.fetch_tmdb_type4_date(movie_id)
                if type4_date:
                    vod_date = type4_date
                    print(f"    Found TMDB Type 4 date: {vod_date}")
                    self.logger.info(f"Pre-order {title}: TMDB Type 4 date = {vod_date}")
            except Exception as e:
                self.logger.debug(f"TMDB Type 4 check failed for {title}: {e}")

            # Step 2: If no TMDB date, try Gemini
            if not vod_date:
                try:
                    if gemini_finder is None:
                        from gemini_scraper import GeminiVODDateFinder
                        gemini_finder = GeminiVODDateFinder()

                    vod_date = gemini_finder.find_vod_date(title, year, provider=provider_name)
                    if vod_date:
                        print(f"    Found Gemini VOD date: {vod_date}")
                        self.logger.info(f"Pre-order {title}: Gemini VOD date = {vod_date}")
                    else:
                        print(f"    No VOD date found yet — will retry tomorrow")
                        self.logger.info(f"Pre-order {title}: no date found, will retry")
                except Exception as e:
                    self.logger.warning(f"Gemini VOD check failed for {title}: {e}")
                    print(f"    Gemini check failed: {e}")

            # Step 3: If we found a date, promote the movie
            if vod_date:
                movie['status'] = 'available'
                movie['digital_date'] = vod_date
                movie['pre_order_resolved'] = datetime.now().strftime('%Y-%m-%d')
                movie['has_providers'] = True

                # Determine if it's available now or in the future
                try:
                    date_obj = datetime.strptime(vod_date, '%Y-%m-%d')
                    is_future = date_obj > datetime.now()
                except ValueError:
                    is_future = False

                if is_future:
                    print(f"    Promoted to available (future date: {vod_date})")
                else:
                    print(f"    Promoted to available (date: {vod_date})")

                # Add to site immediately — front-end will handle future dates
                self.add_movie_to_site_immediately(movie_id, movie)
                resolved += 1

        # Save tracking database
        if self.storage.atomic_write_json(db, 'movie_tracking.json'):
            print(f"  💾 Tracking database saved")
        else:
            print(f"  ❌ Failed to save tracking database")

        # Emit metrics
        try:
            os.makedirs('metrics', exist_ok=True)
            preorder_metrics = {
                'timestamp': datetime.now().isoformat(),
                'operation': 'resolve_preorders',
                'total_preorders': len(preorder_movies),
                'resolved': resolved,
                'remaining': len(preorder_movies) - resolved
            }
            with open('metrics/preorder_resolution.json', 'w') as f:
                json.dump(preorder_metrics, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save pre-order metrics: {e}")

        completion_msg = f"Pre-order resolution: {resolved}/{len(preorder_movies)} resolved"
        print(f"  ✅ {completion_msg}")
        self.logger.info(completion_msg)

        return resolved

    # validate_enrichment_consistency DELETED (2025-12-05) - was causing loop bug

    # atomic_write_json moved to pipeline/storage.py (2025-11-10)

    # atomic_move_to_archive moved to pipeline/storage.py (2025-11-10)

    # load_all_movies moved to pipeline/storage.py (2025-11-10)

    # validate_data_json_schema moved to pipeline/validation.py (2025-11-10)

    def _run_intake_pass(self, pass_name, pass_type, start_date, end_date, max_pages, intaked_movies, existing_ids, debug, min_runtime=60):
        """Run a single intake pass (A or B)

        Args:
            pass_name: 'A' or 'B' for logging
            pass_type: 'digital' or 'theatrical' to determine API parameters
            start_date: Intake start date
            end_date: Intake end date
            max_pages: Maximum pages to fetch
            intaked_movies: Dict to accumulate intaked movies
            existing_ids: Set of existing movie IDs to skip
            debug: Enable debug logging
            min_runtime: Minimum runtime in minutes (features only)

        Returns:
            Number of new movies intaked in this pass
        """
        pass_new_count = 0

        for page in range(1, max_pages + 1):
            try:
                if debug:
                    self.logger.info(f"Pass {pass_name} - Fetching page {page}/{max_pages}")

                # Use bounded timeout and retry logic
                page_results = self._fetch_tmdb_page_with_retry(
                    page, start_date, end_date, debug, pass_type=pass_type, min_runtime=min_runtime
                )

                if not page_results:
                    if debug:
                        self.logger.warning(f"Pass {pass_name} - No results from page {page}, stopping pass")
                    break

                self.intake_stats['pages_fetched'] += 1
                self.intake_stats['total_results'] += len(page_results)

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

                    # Skip if already in existing database or already intaked in this run
                    if movie_id in existing_ids or movie_id in intaked_movies:
                        page_duplicate_count += 1
                        continue

                    # Skip blocked title keywords (wrestling events, sports broadcasts)
                    blocked_keywords = self.config.get('tracking', {}).get('blocked_title_keywords', [])
                    if blocked_keywords and any(kw.lower() in title.lower() for kw in blocked_keywords):
                        self.intake_stats.setdefault('blocked_by_filter', 0)
                        self.intake_stats['blocked_by_filter'] += 1
                        if debug:
                            self.logger.info(f"  Blocked by title filter: {title}")
                        continue

                    # Add new movie with tracking status
                    # Note: digital_date is intentionally None here - monitoring will set it when providers are detected
                    # Extract year from release_date (YYYY-MM-DD format)
                    release_date = movie.get('release_date', '')
                    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

                    intaked_movies[movie_id] = {
                        'title': title,
                        'year': year,
                        'status': 'tracking',
                        'first_seen': datetime.now().strftime('%Y-%m-%d'),
                        'digital_date': None,
                        'providers': {},
                        'intake_pass': pass_name  # Track which pass found this movie
                    }

                    page_new_count += 1
                    pass_new_count += 1

                self.intake_stats['new_movies_added'] += page_new_count
                self.intake_stats['duplicates_skipped'] += page_duplicate_count

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

    def _fetch_tmdb_page_with_retry(self, page, start_date, end_date, debug=False, pass_type='digital', max_retries=3, min_runtime=60):
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
        blocked_companies = self.config.get('tracking', {}).get('blocked_companies', [])
        without_companies = '|'.join(str(c) for c in blocked_companies) if blocked_companies else None

        if pass_type == 'digital':
            # Pass A: Direct-to-digital releases
            params = {
                'api_key': self.tmdb_key,
                'release_date.gte': start_date.strftime('%Y-%m-%d'),
                'release_date.lte': end_date.strftime('%Y-%m-%d'),
                'with_release_type': '4',  # Digital only
                'with_runtime.gte': min_runtime,  # Features only (60+ min default)
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
                'with_runtime.gte': min_runtime,  # Features only (60+ min default)
                'region': 'US',
                'language': 'en-US',
                'include_adult': 'false',
                'sort_by': 'primary_release_date.desc',
                'page': page
            }

        if without_companies:
            params['without_companies'] = without_companies

        self.intake_stats['api_calls'] += 1

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
    # Festival intake methods (2026-01-06 - added for festival premiere discovery)
    # ============================================================================

    def _run_festival_intake_current(self, intaked_movies, existing_ids, debug, min_runtime=60):
        """Run festival intake for current/recent festivals only.

        For ongoing daily intake, only checks festivals happening now or recently.
        For full backfill, use run_festival_backfill() separately.

        Args:
            intaked_movies: Dict to accumulate intaked movies
            existing_ids: Set of existing movie IDs to skip
            debug: Enable debug logging
            min_runtime: Minimum runtime in minutes (features only)

        Returns:
            Number of new movies intaked from current festivals
        """
        festivals_config = self.config.get('festivals', {})
        intake_config = self.config.get('intake', {})
        max_pages = intake_config.get('festival_max_pages', 50)
        wiggle_days = festivals_config.get('wiggle_days', 2)

        # Determine which year's festivals to check based on current date
        now = datetime.now()
        current_year = now.year

        total_new = 0

        # Check current year's festivals
        editions_key = f'editions_{current_year}'
        editions = festivals_config.get(editions_key, {})

        if not editions:
            if debug:
                self.logger.info(f"No festival editions found for {current_year}")
            return 0

        for fest_key, fest_data in editions.items():
            try:
                start_date = datetime.strptime(fest_data['start'], '%Y-%m-%d')
                end_date = datetime.strptime(fest_data['end'], '%Y-%m-%d')

                # Add wiggle room
                start_with_wiggle = start_date - timedelta(days=wiggle_days)
                end_with_wiggle = end_date + timedelta(days=wiggle_days)

                # Only intake festivals that are in progress or recently ended (within 30 days)
                # Skip future festivals and old festivals (for ongoing intake)
                days_since_end = (now - end_with_wiggle).days
                if days_since_end > 30:
                    # Festival ended more than 30 days ago - skip for ongoing intake
                    continue
                if start_with_wiggle > now:
                    # Festival hasn't started yet - skip
                    continue

                if debug:
                    self.logger.info(f"Checking {fest_data['name']} ({fest_data['region']}): "
                                   f"{fest_data['start']} to {fest_data['end']}")

                fest_new = self._fetch_festival_premieres(
                    fest_data['name'],
                    fest_data['region'],
                    start_with_wiggle,
                    end_with_wiggle,
                    max_pages,
                    intaked_movies,
                    existing_ids,
                    debug,
                    min_runtime
                )
                total_new += fest_new

                if fest_new > 0:
                    self.logger.info(f"Festival {fest_data['name']}: {fest_new} new movies intaked")

            except Exception as e:
                self.logger.error(f"Error processing festival {fest_key}: {e}")
                continue

        return total_new

    def run_festival_backfill(self, years=None, debug=False):
        """Backfill festival premieres for specified years.

        This is meant to be called manually or via CLI for historical backfill.

        Args:
            years: List of years to backfill (e.g., [2024, 2025]). Defaults to all available.
            debug: Enable debug logging

        Returns:
            Number of new movies added across all festivals
        """
        festivals_config = self.config.get('festivals', {})
        intake_config = self.config.get('intake', {})
        max_pages = intake_config.get('festival_max_pages', 50)
        wiggle_days = festivals_config.get('wiggle_days', 2)
        min_runtime = intake_config.get('min_runtime', 60)

        # Load existing tracking database
        if os.path.exists('movie_tracking.json'):
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
        else:
            db = {'movies': {}, 'last_update': None}

        existing_ids = set(db['movies'].keys())
        all_intaked_movies = {}

        # Determine which years to process
        if years is None:
            # Find all editions_YYYY keys
            years = []
            for key in festivals_config.keys():
                if key.startswith('editions_'):
                    try:
                        year = int(key.replace('editions_', ''))
                        years.append(year)
                    except ValueError:
                        continue
            years.sort()

        self.logger.info(f"Festival backfill starting for years: {years}")
        total_new = 0

        for year in years:
            editions_key = f'editions_{year}'
            editions = festivals_config.get(editions_key, {})

            if not editions:
                self.logger.warning(f"No festival editions found for {year}")
                continue

            self.logger.info(f"Processing {year} festivals ({len(editions)} festivals)")

            for fest_key, fest_data in editions.items():
                try:
                    start_date = datetime.strptime(fest_data['start'], '%Y-%m-%d')
                    end_date = datetime.strptime(fest_data['end'], '%Y-%m-%d')

                    # Add wiggle room
                    start_with_wiggle = start_date - timedelta(days=wiggle_days)
                    end_with_wiggle = end_date + timedelta(days=wiggle_days)

                    print(f"  📽️ {fest_data['name']} ({fest_data['region']}): "
                          f"{fest_data['start']} to {fest_data['end']}", flush=True)

                    fest_new = self._fetch_festival_premieres(
                        fest_data['name'],
                        fest_data['region'],
                        start_with_wiggle,
                        end_with_wiggle,
                        max_pages,
                        all_intaked_movies,
                        existing_ids,
                        debug,
                        min_runtime
                    )

                    if fest_new > 0:
                        print(f"    ✅ {fest_new} new movies", flush=True)
                        total_new += fest_new
                    else:
                        print(f"    (no new movies)", flush=True)

                    # Rate limiting between festivals
                    time.sleep(0.5)

                except Exception as e:
                    self.logger.error(f"Error processing festival {fest_key}: {e}")
                    print(f"    ❌ Error: {e}", flush=True)
                    continue

        # Merge all intaked movies into database
        new_movies_added = 0
        for movie_id, movie_data in all_intaked_movies.items():
            if movie_id not in existing_ids:
                db['movies'][movie_id] = movie_data
                new_movies_added += 1
                existing_ids.add(movie_id)

        # Save updated database
        if new_movies_added > 0:
            db['last_update'] = datetime.now().isoformat()
            if not self.storage.atomic_write_json(db, 'movie_tracking.json', backup=True):
                self.logger.error("Failed to save movie_tracking.json after festival backfill")
                raise IOError("Festival backfill database write failed")

        self.logger.info(f"Festival backfill complete: {new_movies_added} new movies added")
        print(f"\n🎬 Festival backfill complete: {new_movies_added} new movies added to tracking")

        return new_movies_added

    def _fetch_festival_premieres(self, fest_name, region, start_date, end_date, max_pages,
                                   intaked_movies, existing_ids, debug, min_runtime=60):
        """Fetch premieres from a specific festival via TMDB discover API.

        Args:
            fest_name: Festival name for logging
            region: ISO country code (e.g., 'US', 'FR', 'IT')
            start_date: Festival start date (datetime)
            end_date: Festival end date (datetime)
            max_pages: Maximum pages to fetch
            intaked_movies: Dict to accumulate intaked movies
            existing_ids: Set of existing movie IDs to skip
            debug: Enable debug logging
            min_runtime: Minimum runtime in minutes

        Returns:
            Number of new movies intaked from this festival
        """
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # Configure session with retry strategy
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        url = "https://api.themoviedb.org/3/discover/movie"
        fest_new_count = 0
        blocked_companies = self.config.get('tracking', {}).get('blocked_companies', [])
        without_companies = '|'.join(str(c) for c in blocked_companies) if blocked_companies else None

        for page in range(1, max_pages + 1):
            params = {
                'api_key': self.tmdb_key,
                'region': region,
                'with_release_type': '1',  # Premiere type
                'release_date.gte': start_date.strftime('%Y-%m-%d'),
                'release_date.lte': end_date.strftime('%Y-%m-%d'),
                'with_runtime.gte': min_runtime,  # Features only
                'language': 'en-US',
                'include_adult': 'false',
                'sort_by': 'release_date.asc',
                'page': page
            }
            if without_companies:
                params['without_companies'] = without_companies

            try:
                self.intake_stats['api_calls'] += 1
                response = session.get(url, params=params, timeout=(10, 30))
                response.raise_for_status()

                data = response.json()
                results = data.get('results', [])
                total_pages = data.get('total_pages', 1)

                if not results:
                    break

                self.intake_stats['pages_fetched'] += 1
                self.intake_stats['total_results'] += len(results)

                page_new_count = 0
                for movie in results:
                    movie_id = str(movie['id'])

                    # Skip if already exists
                    if movie_id in existing_ids or movie_id in intaked_movies:
                        self.intake_stats['duplicates_skipped'] += 1
                        continue

                    # Skip blocked title keywords (wrestling events, sports broadcasts)
                    title = movie.get('title', 'Unknown')
                    blocked_keywords = self.config.get('tracking', {}).get('blocked_title_keywords', [])
                    if blocked_keywords and any(kw.lower() in title.lower() for kw in blocked_keywords):
                        self.intake_stats.setdefault('blocked_by_filter', 0)
                        self.intake_stats['blocked_by_filter'] += 1
                        continue

                    # Extract year from release_date
                    release_date = movie.get('release_date', '')
                    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

                    intaked_movies[movie_id] = {
                        'title': title,
                        'year': year,
                        'status': 'tracking',
                        'first_seen': datetime.now().strftime('%Y-%m-%d'),
                        'digital_date': None,
                        'providers': {},
                        'intake_pass': 'C',  # Festival pass
                        'festival': fest_name  # Track which festival found this
                    }

                    page_new_count += 1
                    fest_new_count += 1

                self.intake_stats['new_movies_added'] += page_new_count

                if debug:
                    self.logger.info(f"{fest_name} page {page}/{total_pages}: "
                                   f"{len(results)} results, {page_new_count} new")

                # Stop if we've reached the last page
                if page >= total_pages:
                    break

                # Rate limiting
                time.sleep(self.config.get('api', {}).get('tmdb_rate_limit', 0.1))

            except Exception as e:
                self.logger.error(f"Error fetching {fest_name} page {page}: {e}")
                break

        return fest_new_count

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
            'language': 'en-US',
            'append_to_response': 'credits,videos,external_ids,alternative_titles'
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching details for {movie_id}: {e}")
        return None

    def get_tv_details(self, tv_id):
        """Get full TV series details from TMDB (for miniseries/limited series)"""
        url = f"https://api.themoviedb.org/3/tv/{tv_id}"
        params = {
            'api_key': self.tmdb_key,
            'language': 'en-US',
            'append_to_response': 'credits,videos,external_ids,alternative_titles'
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching TV details for {tv_id}: {e}")
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
        Write minimal movie entry to data.json for immediate display.

        Never blocked by validation failures - discovery must always succeed.
        Creates graceful fallbacks and backups to ensure movies appear on site immediately.

        Args:
            movie_id: TMDB movie ID (string)
            movie_data: Movie data from movie_tracking.json with basic info and providers

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Load current data.json (old movies auto-archived to data_archive.json)
            data_movies = []
            if os.path.exists('data.json'):
                # Try to fix schema issues (adds missing keys, never removes movies)
                self.validator.fix_data_json_schema('data.json')

                # Load existing movies - if this fails, ABORT to preserve data
                try:
                    with open('data.json', 'r') as f:
                        existing_data = json.load(f)
                        data_movies = existing_data.get('movies', [])
                    self.logger.debug(f"Loaded {len(data_movies)} existing movies from data.json")
                except Exception as load_error:
                    # CRITICAL: Do NOT create fresh file - abort to preserve existing data
                    self.logger.error(f"Cannot load data.json: {load_error} - aborting to preserve data")
                    print(f"   ❌ Cannot load data.json - aborting this movie to preserve existing data")
                    return False
            else:
                # data.json doesn't exist - safe to create new one (first run)
                data_movies = []
                self.logger.info("data.json doesn't exist - will create new file")

            # Check if movie already exists
            existing_index = None
            for i, existing in enumerate(data_movies):
                if str(existing.get('id')) == str(movie_id):
                    existing_index = i
                    break

            if existing_index is not None:
                title = movie_data.get('title', f'Movie {movie_id}')
                existing_entry = data_movies[existing_index]

                # Re-discovery of a previously hidden movie (e.g., pre-sale that has now genuinely released)
                if existing_entry.get('hidden'):
                    existing_entry.pop('hidden', None)
                    existing_entry['digital_date'] = movie_data.get('digital_date', datetime.now().strftime('%Y-%m-%d'))
                    existing_entry['providers'] = movie_data.get('providers', {})
                    existing_entry['_enrichment_status'] = 'pending'
                    existing_entry['_discovered_at'] = datetime.now().isoformat()

                    updated_data = existing_data.copy() if 'existing_data' in locals() and existing_data else {}
                    updated_data['movies'] = data_movies
                    updated_data['generated_at'] = datetime.now().isoformat()

                    if self.storage.atomic_write_json(updated_data, 'data.json', backup=True):
                        self.logger.info(f"Re-discovered hidden movie: {title} ({movie_id}) - unhidden in data.json")
                        print(f"   🔄 {title} re-discovered and unhidden in data.json")
                    else:
                        self.logger.error(f"Failed to unhide {title} ({movie_id}) in data.json")
                        print(f"   ❌ Failed to unhide {title} in data.json")
                    return True

                self.logger.info(f"Movie {title} ({movie_id}) already in data.json - skipping")
                print(f"   📝 Movie {title} already in data.json - skipping immediate add")
                return True

            # Get TMDB details with fallback (use TV endpoint for miniseries)
            movie_details = None
            try:
                if str(movie_id).startswith('tv_'):
                    numeric_id = str(movie_id).replace('tv_', '')
                    movie_details = self.get_tv_details(numeric_id)
                else:
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
                '_discovered_at': datetime.now().isoformat(),
                '_discovery_source': 'provider_availability_check',
                '_enrichment_status': 'pending'
            })

            # Add to beginning of movies list (newest first)
            data_movies.insert(0, basic_entry)

            # Save with atomic write and backup
            # IMPORTANT: Preserve existing fields (latest_playlist_url, staff_picks, featured, etc.)
            updated_data = existing_data.copy() if 'existing_data' in locals() and existing_data else {}
            updated_data.update({
                'generated_at': datetime.now().isoformat(),
                'count': len(data_movies),
                'movies': data_movies,
                '_metadata': {
                    'last_discovery_write': datetime.now().isoformat(),
                    'discovery_count': sum(1 for m in data_movies if m.get('_discovery_source')),
                    'schema_version': '2.0'
                }
            })

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

    def _safe_save_data_json(self, display_data, existing_movies, label="save"):
        """Save data.json with reload-merge to prevent lost updates.

        Reloads data.json from disk before saving. Any movies present on disk
        but missing from the in-memory copy are appended (rescued from being
        silently dropped). Uses atomic_write_json for crash-safe writes.

        Args:
            display_data: The full data.json dict (movies will be overwritten)
            existing_movies: The in-memory movies list to save
            label: Log label for this save point (e.g. "enrichment", "trailer")

        Returns:
            bool: True if save succeeded
        """
        try:
            # Reload from disk to catch any movies added since we loaded
            rescued = []
            if os.path.exists('data.json'):
                try:
                    with open('data.json', 'r') as f:
                        disk_data = json.load(f)
                    disk_movies = disk_data.get('movies', [])
                    in_memory_ids = {str(m.get('id', '')) for m in existing_movies if m.get('id')}
                    removed_ids = getattr(self, '_false_positive_removed_ids', set())
                    for dm in disk_movies:
                        dm_id = str(dm.get('id', ''))
                        if dm_id and dm_id not in in_memory_ids:
                            if dm_id in removed_ids:
                                continue  # Intentionally removed (false positive)
                            existing_movies.append(dm)
                            rescued.append(f"{dm.get('title', dm_id)} ({dm_id})")
                except Exception as reload_err:
                    self.logger.warning(f"Reload-merge failed during {label}: {reload_err}")

            if rescued:
                self.logger.warning(f"MERGE [{label}]: rescued {len(rescued)} movies that would have been lost: {rescued}")
                print(f"  🔀 MERGE: rescued {len(rescued)} movies from being dropped")

            display_data['movies'] = existing_movies
            display_data['generated_at'] = datetime.now().isoformat()
            display_data['count'] = len(existing_movies)

            if not self.storage.atomic_write_json(display_data, 'data.json', backup=True):
                self.logger.error(f"Atomic write failed during {label}")
                return False

            self.logger.info(f"Safe save [{label}]: {len(existing_movies)} movies written")
            return True

        except Exception as e:
            self.logger.error(f"Failed safe save [{label}]: {e}")
            print(f"❌ Error saving data.json ({label}): {e}")
            return False

    def _create_minimal_entry(self, movie_id, movie_data):
        """Create minimal movie entry when TMDB details unavailable

        This ensures movies appear on site even if TMDB API is down
        """
        # Use date from movie_tracking if available, otherwise today
        digital_date = movie_data.get('digital_date') or datetime.now().strftime('%Y-%m-%d')

        return {
            'id': str(movie_id),
            'title': movie_data.get('title', f'Movie {movie_id}'),
            'digital_date': digital_date,  # YYYY-MM-DD format for display
            'bootstrap_date': False,
            'manually_corrected': False,
            'poster': None,  # Will be filled by enrichment
            'synopsis': '',  # Will be filled by enrichment
            'crew': {'director': 'Unknown', 'cast': []},  # Will be filled by enrichment
            'genres': [],    # Will be filled by enrichment
            'studio': 'Unknown',  # Will be filled by enrichment
            'runtime': None,      # Will be filled by enrichment
            'year': movie_data.get('year'),  # From movie_tracking.json (intake captures this)
            'country': 'Unknown', # Will be filled by enrichment
            'original_language': None,  # Will be filled by enrichment (ISO 639-1 code)
            'original_title': None,  # Will be filled by enrichment (original-language title)
            'rt_score': None,     # Will be filled by enrichment
            'providers': movie_data.get('providers', {'rent': [], 'buy': [], 'streaming': []}),
            'links': {'wikipedia': None, 'trailer': None, 'rt': None},
            'watch_links': {},
            '_enrichment_status': 'pending',
            '_discovered_at': datetime.now().isoformat(),  # ISO timestamp when we found it
            '_tmdb_fetch_failed': True,
            '_minimal_entry': True
        }

    def _create_full_basic_entry(self, movie_id, movie_data, movie_details):
        """Create full basic entry with TMDB details"""
        # Use date from movie_tracking if available, otherwise today
        digital_date = movie_data.get('digital_date') or datetime.now().strftime('%Y-%m-%d')

        # TV shows use different field names than movies in TMDB
        is_tv = movie_data.get('content_type') == 'limited_series'
        title_field = 'name' if is_tv else 'title'
        date_field = 'first_air_date' if is_tv else 'release_date'
        original_title_field = 'original_name' if is_tv else 'original_title'

        # TV runtime: use episode_run_time array or tracking data
        if is_tv:
            ep_runtimes = movie_details.get('episode_run_time', [])
            runtime = ep_runtimes[0] if ep_runtimes else movie_data.get('runtime')
        else:
            runtime = movie_details.get('runtime')

        release_date_str = movie_details.get(date_field, '')

        # Start with minimal entry structure
        entry = {
            'id': str(movie_id),
            'title': movie_details.get(title_field, movie_data.get('title', f'Movie {movie_id}')),
            'digital_date': digital_date,  # YYYY-MM-DD format for display
            'bootstrap_date': False,
            'manually_corrected': False,
            'synopsis': movie_details.get('overview', ''),
            'genres': [genre['name'] for genre in movie_details.get('genres', [])],
            'runtime': runtime,
            'year': int(release_date_str[:4]) if release_date_str else None,
            'rt_score': None,  # Will be filled by enrichment
            'providers': movie_data.get('providers', {'rent': [], 'buy': [], 'streaming': []}),
            'links': {'wikipedia': None, 'trailer': None, 'rt': None},
            'watch_links': {},
            '_enrichment_status': 'pending',
            '_discovered_at': datetime.now().isoformat(),  # ISO timestamp when we found it
            '_tmdb_fetch_failed': False,
            '_minimal_entry': False
        }

        # Copy content_type and series metadata from tracking data
        if is_tv:
            entry['content_type'] = 'limited_series'
            entry['episode_count'] = movie_data.get('episode_count')
            networks = movie_details.get('networks', [])
            entry['networks'] = [n.get('name') for n in networks if n.get('name')]

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

        # Add budget from TMDB (used for auto-categorization; TV shows don't have budget)
        entry['budget'] = movie_details.get('budget', 0)

        # Add country with error handling
        if is_tv:
            # TV shows use origin_country (ISO codes like 'US', 'GB')
            origin_countries = movie_details.get('origin_country', [])
            entry['country'] = origin_countries[0] if origin_countries else 'Unknown'
        else:
            production_countries = movie_details.get('production_countries', [])
            if production_countries and len(production_countries) > 0:
                entry['country'] = production_countries[0].get('name', 'Unknown')
            else:
                entry['country'] = 'Unknown'

        # Add original language (ISO 639-1 code: 'en', 'es', 'fr', etc.)
        entry['original_language'] = movie_details.get('original_language')
        entry['original_title'] = movie_details.get(original_title_field)

        # Add cast/crew with error handling
        entry['crew'] = {'director': 'Unknown', 'cast': []}
        if is_tv:
            # TV shows: use created_by for director, aggregate_credits for cast
            try:
                created_by = movie_details.get('created_by', [])
                if created_by:
                    entry['crew']['director'] = created_by[0].get('name', 'Unknown')
                credits = movie_details.get('credits', {})
                cast = [person['name'] for person in credits.get('cast', [])[:5]
                       if person.get('name')]
                entry['crew']['cast'] = cast
            except Exception as e:
                self.logger.warning(f"Failed to parse TV credits for {movie_id}: {e}")
        elif movie_details.get('credits'):
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
        omdb_key = os.environ.get('OMDB_API_KEY') or self.config.get('api', {}).get('omdb_api_key')
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

    def _load_imdb_cache(self):
        """Lazy-load IMDB rating cache from cache/imdb_rating_cache.json."""
        if self._imdb_rating_cache is None:
            cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache', 'imdb_rating_cache.json')
            try:
                with open(cache_path, 'r') as f:
                    self._imdb_rating_cache = json.load(f)
                self.logger.debug(f"Loaded IMDB cache: {len(self._imdb_rating_cache)} entries")
            except (FileNotFoundError, json.JSONDecodeError):
                self._imdb_rating_cache = {}
        return self._imdb_rating_cache

    def _save_to_imdb_cache(self, imdb_id, rating, title=None, source='omdb_pipeline'):
        """Write a single rating to the IMDB cache (in-memory + disk)."""
        cache = self._load_imdb_cache()
        cache[imdb_id] = {
            'imdb_id': imdb_id,
            'rating': rating,
            'title': title,
            'scraped_at': datetime.now().isoformat(),
            'source': source
        }
        cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache', 'imdb_rating_cache.json')
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f, indent=2)
        except Exception as e:
            self.logger.debug(f"Failed to save IMDB cache: {e}")

    def _load_imdb_dataset(self):
        """Download and parse IMDb's bulk ratings dataset (lazy, once per run).

        Downloads title.ratings.tsv.gz (~5MB) from datasets.imdbws.com,
        parses into a dict: {imdb_id: rating_string}.
        Free for non-commercial use. Updated daily by IMDb.
        """
        if self._imdb_dataset is not None:
            return self._imdb_dataset

        import gzip
        import io

        dataset_url = 'https://datasets.imdbws.com/title.ratings.tsv.gz'
        self._imdb_dataset = {}

        try:
            self.logger.info("Downloading IMDb ratings dataset (~5MB)...")
            response = requests.get(dataset_url, timeout=30)
            if response.status_code != 200:
                self.logger.warning(f"IMDb dataset download failed: HTTP {response.status_code}")
                return self._imdb_dataset

            with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz:
                reader = io.TextIOWrapper(gz, encoding='utf-8')
                header = reader.readline()  # Skip header: tconst\taverageRating\tnumVotes
                for line in reader:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        self._imdb_dataset[parts[0]] = parts[1]  # {tt_id: "7.4"}

            self.logger.info(f"IMDb dataset loaded: {len(self._imdb_dataset)} ratings")

        except Exception as e:
            self.logger.warning(f"IMDb dataset download error: {e}")

        return self._imdb_dataset

    def get_imdb_rating(self, imdb_id, title=None, year=None):
        """Fetch IMDb rating using 5-tier waterfall.

        Tiers:
            1. Cache check
            2. IMDb bulk dataset (daily TSV from datasets.imdbws.com)
            3. OMDb API by ID
            4. Gemini + Google Search grounding (catches new/low-vote movies)
            5. OMDb title search (finds ID + rating, only when no IMDb ID)

        Args:
            imdb_id: IMDb ID (e.g., 'tt12345678'), can be None
            title: Movie title (for fallback search tiers)
            year: Release year (for fallback search tiers)

        Returns:
            str: IMDb rating (e.g., '7.5') or None if not found
        """
        # Tier 1: Cache check
        if imdb_id:
            cache = self._load_imdb_cache()
            if imdb_id in cache:
                cached_rating = cache[imdb_id].get('rating')
                if cached_rating:
                    self.logger.debug(f"IMDB cache hit: {imdb_id} -> {cached_rating}")
                    return cached_rating

        # Tier 2: IMDb bulk dataset lookup (free daily dump, covers 99%+ of rated titles)
        if imdb_id:
            dataset = self._load_imdb_dataset()
            if imdb_id in dataset:
                rating = dataset[imdb_id]
                self.logger.debug(f"IMDb dataset: rating {rating} for {imdb_id}")
                self._save_to_imdb_cache(imdb_id, rating, title=title, source='imdb_dataset')
                return rating

        # Tier 3: OMDb API by ID (fallback for very new movies not yet in daily dump)
        if imdb_id:
            omdb_key = os.environ.get('OMDB_API_KEY') or self.config.get('api', {}).get('omdb_api_key')
            if omdb_key:
                try:
                    url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('Response') != 'False':
                            rating = data.get('imdbRating')
                            if rating and rating != 'N/A':
                                self.logger.debug(f"OMDb: rating {rating} for {imdb_id}")
                                self._save_to_imdb_cache(imdb_id, rating, title=title, source='omdb')
                                return rating
                except Exception as e:
                    self.logger.debug(f"OMDb rating error for {imdb_id}: {e}")

        # Tier 4: Gemini + Google Search grounding (catches new/obscure movies)
        if imdb_id and title:
            try:
                if not hasattr(self, '_gemini_imdb'):
                    from gemini_scraper import GeminiIMDbFinder
                    self._gemini_imdb = GeminiIMDbFinder()
                rating = self._gemini_imdb.find_rating(title, year, imdb_id=imdb_id)
                if rating:
                    self.logger.debug(f"Gemini IMDb: rating {rating} for {imdb_id}")
                    self._save_to_imdb_cache(imdb_id, rating, title=title, source='gemini')
                    return rating
            except Exception as e:
                self.logger.debug(f"Gemini IMDb error for {imdb_id}: {e}")

        # Tier 5: OMDb title search (finds both ID and rating, only when no IMDb ID)
        if title and not imdb_id:
            omdb_key = os.environ.get('OMDB_API_KEY') or self.config.get('api', {}).get('omdb_api_key')
            if omdb_key:
                try:
                    url = f"http://www.omdbapi.com/?t={quote(title)}&apikey={omdb_key}"
                    if year:
                        url += f"&y={year}"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('Response') != 'False':
                            found_id = data.get('imdbID')
                            rating = data.get('imdbRating')
                            if rating == 'N/A':
                                rating = None
                            if found_id and rating:
                                self.logger.debug(f"OMDb title search: {found_id} -> {rating}")
                                self._save_to_imdb_cache(found_id, rating, title=title, source='omdb')
                                return rating
                except Exception as e:
                    self.logger.debug(f"OMDb title search error for '{title}': {e}")

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

            from wikipedia_scraper_playwright import WikipediaScraperPlaywright
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
    

    def _validate_youtube_url_live(self, url):
        """Check if a YouTube URL actually resolves to a playable video.
        Uses YouTube's oEmbed endpoint — fast (~100ms), no API key needed."""
        try:
            import requests
            oembed = f"https://www.youtube.com/oembed?url={url}&format=json"
            resp = requests.head(oembed, timeout=5)
            return resp.status_code == 200
        except Exception:
            return True  # If check itself fails, don't block — assume valid

    def _cache_bad_trailer_key(self, key, title, year, url):
        """Add a dead YouTube key to bad_trailer_urls cache and save."""
        self.bad_trailer_urls[key] = {
            'title': title,
            'year': str(year),
            'reason': 'failed_live_validation',
            'url': url,
            'recorded_at': datetime.now().isoformat()
        }
        self.save_cache(self.bad_trailer_urls, 'cache/bad_trailer_urls.json')

    def _init_trailer_finder(self):
        """Lazily initialize the Gemini+Playwright trailer finder."""
        if self.trailer_finder is not None:
            return True
        if not self.enrichment_enabled:
            self.logger.debug("YouTube trailer finder disabled - enrichment not enabled")
            return False
        gemini_config = self.config.get('gemini_scraper', {})
        youtube_gemini_disabled = not gemini_config.get('enabled', True) or not gemini_config.get('youtube_enabled', True)
        if GEMINI_AVAILABLE and not youtube_gemini_disabled:
            self.trailer_finder = HybridYouTubeFinder(
                cache_file='cache/youtube_trailer_cache.json'
            )
            self.logger.info("YouTube trailer finder initialized (Gemini + Playwright fallback)")
        else:
            from scripts.youtube_trailer_scraper import YouTubeTrailerScraper
            self.trailer_finder = YouTubeTrailerScraper(
                cache_file='cache/youtube_trailer_cache.json',
                headless=True
            )
            reason = "config disabled" if youtube_gemini_disabled else "Gemini unavailable"
            self.logger.warning(f"YouTube trailer finder initialized (Playwright-only, {reason})")
        return True

    def find_trailer_url(self, movie_details):
        """Find trailer URL using a tiered waterfall with liveness validation.

        Returns (url, source_tier) tuple, or None if no trailer found.
        source_tier is one of: override, tmdb_official, cache, gemini_playwright,
        tmdb_fallback, broad_search, search_fallback.

        Tier order (each validated before accepting):
          1. Manual overrides (trusted, no validation)
          2. TMDB official trailers (validated — TMDB data can go stale)
          3. YouTube scraper cache (validated — free/instant, checked before Gemini)
          4. Gemini+Playwright live search (validated — most reliable but costs tokens)
          5. TMDB any YouTube video (validated — teasers/clips, last resort from TMDB)
          6. YouTube search URL fallback (no validation — not a direct video)
        """
        title = movie_details.get('name') or movie_details.get('title', '')
        year = (movie_details.get('first_air_date') or movie_details.get('release_date', ''))[:4] if (movie_details.get('first_air_date') or movie_details.get('release_date')) else ''

        # --- Tier 1: Manual overrides (always trusted) ---
        override_key = f"{title}_{year}"
        if override_key in self.trailer_overrides:
            self.logger.info(f"Trailer for {title} ({year}): tier=override")
            return self.trailer_overrides[override_key], 'override'

        videos = movie_details.get('videos', {}).get('results', [])

        # --- Tier 2: TMDB official trailers (validated) ---
        for video in videos:
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                if video['key'] in self.bad_trailer_urls:
                    self.logger.info(f"Skipping known-bad TMDB trailer for {title} ({year}): {video['key']}")
                    continue
                url = f"https://www.youtube.com/watch?v={video['key']}"
                if self._validate_youtube_url_live(url):
                    self.logger.info(f"Trailer for {title} ({year}): tier=tmdb_official, url={url}")
                    return url, 'tmdb_official'
                self.logger.warning(f"Trailer dead link for {title} ({year}): tier=tmdb_official, url={url}")
                self._cache_bad_trailer_key(video['key'], title, year, url)

        # --- Tier 3: YouTube scraper cache (validated, checked before Gemini to save cost) ---
        cache_key = f"{title}_{year}"
        if cache_key in self.youtube_trailer_cache:
            cached_url = self.youtube_trailer_cache[cache_key]
            if cached_url and self._validate_youtube_url_live(cached_url):
                self.logger.info(f"Trailer for {title} ({year}): tier=cache, url={cached_url}")
                return cached_url, 'cache'
            elif cached_url:
                self.logger.warning(f"Trailer dead link for {title} ({year}): tier=cache, url={cached_url}")
                del self.youtube_trailer_cache[cache_key]  # Invalidate dead cache entry

        # --- Tier 4: Gemini+Playwright live search (validated) ---
        if self._init_trailer_finder():
            # Clear dead entries from finder's internal cache (loaded from same file)
            # HybridYouTubeFinder stores cache at .gemini_finder.cache
            # YouTubeTrailerScraper stores cache at .cache directly
            finder_cache = None
            if hasattr(self.trailer_finder, 'gemini_finder'):
                finder_cache = self.trailer_finder.gemini_finder.cache
            elif hasattr(self.trailer_finder, 'cache'):
                finder_cache = self.trailer_finder.cache
            if finder_cache and cache_key in finder_cache:
                finder_url = finder_cache[cache_key]
                if finder_url and cache_key not in self.youtube_trailer_cache:
                    # We already proved this URL is dead in Tier 3
                    del finder_cache[cache_key]
                    self.logger.info(f"Cleared dead URL from finder cache for {title} ({year})")

            self.enrichment_stats['trailer_attempts'] += 1

            director = movie_details.get('crew', {}).get('director') if movie_details else None
            cast_list = movie_details.get('crew', {}).get('cast', []) if movie_details else []
            cast = cast_list[:3] if cast_list else None

            if GEMINI_AVAILABLE:
                scraped_url = self.trailer_finder.find_trailer(title, year, director=director, cast=cast)
            else:
                scraped_url = self.trailer_finder.find_trailer(title, year)

            if scraped_url and self._validate_youtube_url_live(scraped_url):
                self.enrichment_stats['trailer_successes'] += 1
                self.logger.info(f"Trailer for {title} ({year}): tier=gemini_playwright, url={scraped_url}")
                return scraped_url, 'gemini_playwright'
            elif scraped_url:
                self.logger.warning(f"Trailer dead link for {title} ({year}): tier=gemini_playwright, url={scraped_url}")

        # --- Tier 5: TMDB any YouTube video — teasers/clips (validated) ---
        for video in videos:
            if video['site'] == 'YouTube' and video['type'] != 'Trailer':
                if video['key'] in self.bad_trailer_urls:
                    self.logger.info(f"Skipping known-bad TMDB fallback for {title} ({year}): {video['key']}")
                    continue
                url = f"https://www.youtube.com/watch?v={video['key']}"
                if self._validate_youtube_url_live(url):
                    self.logger.info(f"Trailer for {title} ({year}): tier=tmdb_fallback ({video['type']}), url={url}")
                    return url, 'tmdb_fallback'
                self.logger.warning(f"Trailer dead link for {title} ({year}): tier=tmdb_fallback, url={url}")
                self._cache_bad_trailer_key(video['key'], title, year, url)

        # --- Tier 6: Broad YouTube search (validated — searches for 'trailer' and 'preview') ---
        if self._init_trailer_finder():
            # Use Playwright broad search if available (tries 'trailer' then 'preview',
            # filters results to only accept videos with trailer/preview in title)
            scraper = None
            if hasattr(self.trailer_finder, '_get_playwright_finder'):
                scraper = self.trailer_finder._get_playwright_finder()
            elif hasattr(self.trailer_finder, 'find_trailer_broad'):
                scraper = self.trailer_finder

            if scraper and hasattr(scraper, 'find_trailer_broad'):
                broad_url = scraper.find_trailer_broad(title, year)
                if broad_url and self._validate_youtube_url_live(broad_url):
                    self.logger.info(f"Trailer for {title} ({year}): tier=broad_search, url={broad_url}")
                    return broad_url, 'broad_search'
                elif broad_url:
                    self.logger.warning(f"Trailer dead link for {title} ({year}): tier=broad_search, url={broad_url}")

        self.logger.info(f"Trailer for {title} ({year}): no trailer found across all tiers")
        return None
    

    def find_rt_url(self, title, year, imdb_id, director=None, original_language=None, original_title=None):
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
            return None

        # 3. Use RT scraper (handles caching internally)
        result = self.scrape_rt_score(title, year, director=director, original_language=original_language, original_title=original_title)
        if result:
            return result

        # 4. No result — return None (deep links or nothing)
        return None




    # ============================================================================
    # Helper methods
    # ============================================================================

    def _is_recent(self, date_str: str, cutoff_date) -> bool:
        """Check if a date string is after the cutoff date."""
        try:
            digital_date = datetime.strptime(date_str, '%Y-%m-%d')
            return digital_date >= cutoff_date
        except (ValueError, TypeError):
            return False

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
                from agent_link_scraper import AgentLinkScraper
                self.streaming_scraper = AgentLinkScraper(
                    cache_file=cache_file,
                    config=streaming_config  # Pass entire config dict
                )
                self.logger.debug("Agent scraper initialized (Playwright)")
            except Exception as e:
                self.logger.exception(f"Failed to initialize agent scraper: {e}")
                self.streaming_scraper = False  # Mark as failed to prevent retries


    def _init_rt_scraper(self):
        """Initialize RT scraper (Gemini hybrid or Playwright-only, lazy initialization)"""
        if self.rt_scraper is not None:
            return self.rt_scraper is not False

        # Check enrichment flag first
        if not self.enrichment_enabled:
            self.logger.debug("RT scraper disabled - enrichment not enabled")
            self.rt_scraper = False
            return False

        # Check config kill switch for Gemini RT
        rt_enabled = self.config.get('gemini_scraper', {}).get('rt_enabled', True)

        try:
            if GEMINI_RT_AVAILABLE and rt_enabled:
                # Use hybrid finder (Gemini first, Playwright fallback)
                self.rt_scraper = HybridRTFinder(
                    cache_file='cache/rt_cache.json',
                    config=self.config,
                    logger_instance=self.logger
                )
                self.logger.info("RT scraper initialized (Gemini + Playwright fallback)")
            else:
                # Use Playwright-only scraper
                from rt_scraper_playwright import RTScraperPlaywright
                self.rt_scraper = RTScraperPlaywright(
                    cache_file='cache/rt_cache.json',
                    config=self.config,
                    logger=self.logger
                )
                if not GEMINI_RT_AVAILABLE:
                    self.logger.warning("RT scraper initialized (Playwright-only, Gemini unavailable)")
                else:
                    self.logger.info("RT scraper initialized (Playwright-only, Gemini disabled via config)")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize RT scraper: {e}")
            self.rt_scraper = False  # Mark as failed to prevent retries
            return False


    def scrape_rt_score(self, title, year, director=None, original_language=None, original_title=None):
        """Public wrapper function to scrape RT score for external consumers

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for disambiguation
            original_language: ISO 639-1 language code
            original_title: Original-language title from TMDB

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
            # HybridRTFinder uses find_rt_score(); Playwright-only uses scrape_rt_score()
            if GEMINI_RT_AVAILABLE:
                result = self.rt_scraper.find_rt_score(title, year, director=director, original_language=original_language, original_title=original_title)
            else:
                result = self.rt_scraper.scrape_rt_score(title, year)

            # Update stats from scraper
            scraper_stats = self.rt_scraper.get_stats()
            self.enrichment_stats['rt_attempts'] = scraper_stats['attempts']
            self.enrichment_stats['rt_successes'] = scraper_stats['successes']
            self.enrichment_stats['rt_cache_hits'] = scraper_stats['cache_hits']

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

    # NOTE: get_watch_links, _enforce_vod_scraper_rate_limit, and _get_platform_deep_link_with_cache
    # were removed 2026-02-04 as dead code. All watch link logic now lives in pipeline/enrichment.py
    # and is accessed via self.enrichment.get_watch_links()

    def host_trailer_for_movie(self, movie_id, title, year, youtube_url):
        """Download, upload, and return hosted trailer URL. None on failure.

        Runs as a post-enrichment step — never blocks the main enrichment pipeline.
        Lazy-initializes B2 connection on first call.
        """
        trailer_config = self.config.get('trailer_hosting', {})
        if not trailer_config.get('enabled', False) or not trailer_config.get('pipeline_integration', False):
            self.logger.debug("Trailer hosting: disabled (config)")
            return None

        try:
            from scripts.trailer_pipeline import download_and_upload_trailer, get_b2_connection

            if not hasattr(self, '_b2_connection'):
                self.logger.info("Trailer hosting: connecting to B2...")
                self._b2_connection = get_b2_connection()

            api, bucket, bucket_url = self._b2_connection
            # Prefer config bucket_url over B2 native URL
            config_url = trailer_config.get('bucket_url', '') or bucket_url

            hosted_url, new_trailer_url = download_and_upload_trailer(movie_id, title, year, youtube_url, bucket, config_url)
            if hosted_url:
                self.logger.info(f"Trailer hosted: {title} ({year}) -> {hosted_url}")
            return hosted_url
        except BaseException as e:
            # BaseException catches RuntimeError from get_b2_api() and other trailer hosting failures
            self.logger.warning(f"Trailer hosting failed for {title}: {type(e).__name__}: {str(e)[:100]}")
            return None

    def validate_enrichment_quality(self, result, movie_data, movie_details, movie_id, is_tv=False):
        """Post-enrichment quality gate: flag suspicious entries before publishing.

        Checks for mismatched watch links, unexpected title changes, foreign titles,
        and other data quality issues. Sets _needs_review and _quality_warnings on
        entries that fail checks.
        """
        from urllib.parse import urlparse
        warnings = []

        title = result.get('title', '')
        tracking_title = movie_data.get('title', '')

        # --- Check 1: URL domain vs service name ---
        EXPECTED_DOMAINS = {
            'Netflix': ['netflix.com'],
            'Disney+': ['disneyplus.com'],
            'HBO Max': ['max.com', 'play.max.com'],
            'Max': ['max.com', 'play.max.com'],
            'Hulu': ['hulu.com'],
            'Amazon Video': ['amazon.com', 'watch.amazon.com', 'primevideo.com'],
            'Amazon Prime Video': ['amazon.com', 'watch.amazon.com', 'primevideo.com'],
            'Prime Video': ['amazon.com', 'watch.amazon.com', 'primevideo.com'],
            'Apple TV': ['tv.apple.com'],
            'Shudder': ['shudder.com'],
            'Criterion': ['criterionchannel.com'],
            'MUBI': ['mubi.com'],
        }

        for category, link_obj in result.get('watch_links', {}).items():
            items = link_obj if isinstance(link_obj, list) else [link_obj] if isinstance(link_obj, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                service = item.get('service', '')
                link = item.get('link', '')
                if not link or not service:
                    continue
                expected = EXPECTED_DOMAINS.get(service)
                if expected and not any(d in link.lower() for d in expected):
                    warnings.append(f"Watch link domain mismatch: '{service}' link is '{link}' (expected domains: {expected})")

        # --- Check 2: Watch link service vs TMDB providers ---
        tmdb_providers = movie_data.get('providers', {})
        tmdb_streaming = [p.lower() for p in tmdb_providers.get('streaming', [])]
        tmdb_rent = [p.lower() for p in tmdb_providers.get('rent', [])]
        tmdb_buy = [p.lower() for p in tmdb_providers.get('buy', [])]
        all_tmdb = set(tmdb_streaming + tmdb_rent + tmdb_buy)

        for category, link_obj in result.get('watch_links', {}).items():
            items = link_obj if isinstance(link_obj, list) else [link_obj] if isinstance(link_obj, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                service = item.get('service', '')
                link = item.get('link', '')
                if not link or not service:
                    continue
                # Check if the scraped service appears anywhere in TMDB providers
                service_lower = service.lower()
                if all_tmdb and not any(service_lower in tp or tp in service_lower for tp in all_tmdb):
                    warnings.append(f"Service '{service}' not in TMDB providers for this title (TMDB has: {list(all_tmdb)[:5]})")

        # --- Check 3: Title change detection ---
        if tracking_title and title:
            tracking_norm = tracking_title.lower().strip()
            title_norm = title.lower().strip()
            if tracking_norm != title_norm:
                # Allow minor differences (punctuation, "the" prefix, etc.)
                clean = lambda s: re.sub(r'[^a-z0-9 ]', '', s).strip()
                if clean(tracking_norm) != clean(title_norm):
                    warnings.append(f"Title changed from tracking: '{tracking_title}' -> '{title}'")

        # --- Check 4: Foreign title detection ---
        orig_lang = movie_details.get('original_language', 'en') if movie_details else 'en'
        orig_title = movie_details.get('original_name' if is_tv else 'original_title', '') if movie_details else ''
        if orig_lang != 'en':
            # Check if we might be using the foreign title
            if orig_title and title and orig_title.lower() == title.lower():
                warnings.append(f"Title matches original foreign title (language: {orig_lang}): '{orig_title}'")
            # Also check for non-ASCII characters suggesting a non-English title
            if title and not all(ord(c) < 128 for c in title):
                warnings.append(f"Title contains non-ASCII characters (language: {orig_lang}): '{title}'")

        # --- Check 5: Content type sanity ---
        if is_tv:
            for category, link_obj in result.get('watch_links', {}).items():
                items = link_obj if isinstance(link_obj, list) else [link_obj] if isinstance(link_obj, dict) else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    link = item.get('link', '') or ''
                    if '/movies/' in link.lower() or '/movie/' in link.lower():
                        warnings.append(f"TV series has movie-type URL: '{link}'")

        # Apply warnings to result
        if warnings:
            result['_needs_review'] = True
            result['_quality_warnings'] = warnings
            for w in warnings:
                self.logger.warning(f"Quality gate [{movie_id}] {title}: {w}")
        else:
            result['_needs_review'] = False

        return warnings

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

        # Safely extract basic info with fallbacks (TV series use different TMDB field names)
        is_tv = movie_data.get('content_type') == 'limited_series'
        title = movie_details.get('name' if is_tv else 'title', f'Unknown Movie {movie_id}')
        release_date = movie_details.get('first_air_date' if is_tv else 'release_date', '')
        year = release_date[:4] if release_date else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')

        # OMDb fallback: If TMDB doesn't have IMDb ID, try OMDb
        if not imdb_id:
            imdb_id = self.get_imdb_from_omdb(title, year)

        # Start timing this movie's enrichment
        movie_start_time = time.time()

        # Initialize result with basic TMDB data (always available)
        # TV series runtime: use episode_run_time array; movies: use runtime directly
        if is_tv:
            ep_runtimes = movie_details.get('episode_run_time', [])
            runtime = ep_runtimes[0] if ep_runtimes else movie_data.get('runtime')
        else:
            runtime = movie_details.get('runtime')

        result = {
            'title': title,
            'poster': f"https://image.tmdb.org/t/p/w500{movie_details['poster_path']}" if movie_details.get('poster_path') else None,
            'synopsis': movie_details.get('overview', 'No synopsis available.'),
            'runtime': runtime,
            'year': int(year) if year.isdigit() else None,
            'rt_score': None,
            'imdb_rating': None,
            'links': {},
            'watch_links': {}
        }

        # Track enrichment success/failure for detailed logging
        enrichment_results = {
            'wikipedia': 'not_attempted',
            'trailer': 'not_attempted',
            'rt_score': 'not_attempted',
            'pull_quotes': 'not_attempted',
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
            trailer_result = self.find_trailer_url(movie_details)
            if trailer_result:
                trailer_url, trailer_source = trailer_result
                result['links']['trailer'] = trailer_url
                result['_trailer_source'] = trailer_source
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
            rt_director = movie_details.get('crew', {}).get('director') if movie_details else None
            rt_lang = movie_details.get('original_language') if movie_details else None
            rt_orig_title = movie_details.get('original_name' if is_tv else 'original_title') if movie_details else None
            rt_data = self.find_rt_url(title, year, imdb_id, director=rt_director, original_language=rt_lang, original_title=rt_orig_title)
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

        # IMDB rating (isolated failure handling)
        try:
            imdb_rating = self.get_imdb_rating(imdb_id, title, year)
            if imdb_rating:
                result['imdb_rating'] = imdb_rating
                enrichment_results['imdb_rating'] = 'success'
                self.logger.debug(f"IMDB: Rating {imdb_rating} for {title} ({year})")
            else:
                enrichment_results['imdb_rating'] = 'not_found'
                self.logger.debug(f"IMDB: No rating found for {title} ({year})")
            if imdb_id:
                result['links']['imdb'] = f"https://www.imdb.com/title/{imdb_id}/"
        except Exception as e:
            enrichment_results['imdb_rating'] = 'error'
            self.logger.warning(f"IMDB: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # Pull quotes (isolated failure handling)
        pull_quotes_enabled = self.config.get('gemini_scraper', {}).get('pull_quotes_enabled', False)
        if pull_quotes_enabled:
            try:
                from gemini_scraper import GeminiPullQuoteFinder
                pq_finder = GeminiPullQuoteFinder()
                pq_director = result.get('crew', {}).get('director') if result.get('crew') else None
                pq_count = self.config.get('gemini_scraper', {}).get('pull_quotes_count', 8)
                quotes = pq_finder.find_pull_quotes(title, year, director=pq_director, num_quotes=pq_count)
                if quotes:
                    enrichment_results['pull_quotes'] = 'success'
                else:
                    enrichment_results['pull_quotes'] = 'not_found'
            except Exception as e:
                enrichment_results['pull_quotes'] = 'error'
                self.logger.warning(f"Pull quotes: Error for {title} ({year}): {str(e)[:100]}")
        else:
            enrichment_results['pull_quotes'] = 'disabled'

        # Watch links (isolated failure handling)
        try:
            # Extract title variants for scraper fallback (English → original → US alternative)
            orig_title_key = 'original_name' if is_tv else 'original_title'
            original_title = movie_details.get(orig_title_key) if movie_details else None
            alt_titles_raw = movie_details.get('alternative_titles', {}).get('results', []) if movie_details else []

            watch_links_raw = self.enrichment.get_watch_links(
                movie_id, title, year, movie_data.get('providers', {}), force_refresh,
                tracking_data=movie_data,
                original_title=original_title,
                alternative_titles=alt_titles_raw
            )

            # Simplify provider names in watch links (handle both array and dict formats)
            for category, link_obj in watch_links_raw.items():
                # Handle array format (new)
                if isinstance(link_obj, list):
                    simplified_array = []
                    for item in link_obj:
                        if isinstance(item, dict) and 'service' in item:
                            simplified_array.append({
                                'service': self.simplify_provider_name(item['service']),
                                'link': item.get('link')
                            })
                        else:
                            simplified_array.append(item)
                    result['watch_links'][category] = simplified_array
                # Handle dict format (legacy backward compatibility)
                elif isinstance(link_obj, dict) and 'service' in link_obj:
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

            if is_tv:
                # TV series: use created_by for director
                created_by = movie_details.get('created_by', [])
                if created_by:
                    director = created_by[0].get('name', 'Unknown')
            else:
                for crew in credits.get('crew', []):
                    if crew['job'] == 'Director':
                        director = crew['name']
                        break

            for actor in credits.get('cast', [])[:5]:  # Top 5 actors
                cast.append(actor['name'])

            genres = [g['name'] for g in movie_details.get('genres', [])]
            studio = None
            production_companies = movie_details.get('production_companies', [])
            if production_companies:
                studio = production_companies[0]['name']

            country = None
            if is_tv:
                # TV series: origin_country is ISO codes like ['US', 'GB']
                origin_countries = movie_details.get('origin_country', [])
                if origin_countries:
                    country = origin_countries[0]
            else:
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
        # TV series don't have Type 4 release dates - skip for limited series
        if is_tv:
            result['_digital_date_source'] = 'first_air_date'
            enrichment_results['digital_date'] = 'not_attempted'
        else:
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
        pq_icon = status_icons.get(enrichment_results.get('pull_quotes', 'not_attempted'), '?')
        links_icon = status_icons.get(enrichment_results['watch_links'], '?')
        date_icon = status_icons.get(enrichment_results['digital_date'], '?')

        print(f"  ⚡ {title} ({movie_duration:.1f}s) - Wiki:{wiki_icon} Trailer:{trailer_icon} RT:{rt_icon} PQ:{pq_icon} Links:{links_icon} Date:{date_icon} | {success_count} success, {error_count} errors")

        # Detailed logging for metrics
        self.logger.info(f"Enrichment completed for {title} ({year}) in {movie_duration:.1f}s: {enrichment_results}")

        # Post-enrichment quality gate
        quality_warnings = self.validate_enrichment_quality(result, movie_data, movie_details, movie_id, is_tv=is_tv)
        if quality_warnings:
            print(f"  ⚠️  Quality gate flagged {title}: {len(quality_warnings)} warning(s)")
            enrichment_results['quality_gate'] = 'flagged'
        else:
            enrichment_results['quality_gate'] = 'passed'

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
        
        for actor in credits.get('cast', [])[:5]:  # Top 5 actors
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
        imdb_rating = None

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
        trailer_source = None
        try:
            trailer_result = self.find_trailer_url(movie_details)
            if trailer_result:
                trailer_url, trailer_source = trailer_result
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
            orig_lang = movie_data.get('original_language')
            orig_title = movie_data.get('original_title')
            rt_data = self.find_rt_url(title, year, imdb_id, director=director, original_language=orig_lang, original_title=orig_title)
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

        # IMDB rating (isolated failure handling)
        try:
            imdb_rating = self.get_imdb_rating(imdb_id, title, year)
            if imdb_rating:
                enrichment_results['imdb_rating'] = 'success'
                self.logger.debug(f"IMDB: Rating {imdb_rating} for {title} ({year})")
            else:
                enrichment_results['imdb_rating'] = 'not_found'
                self.logger.debug(f"IMDB: No rating found for {title} ({year})")
            if imdb_id:
                links['imdb'] = f"https://www.imdb.com/title/{imdb_id}/"
        except Exception as e:
            enrichment_results['imdb_rating'] = 'error'
            self.logger.warning(f"IMDB: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # Watch links (deep links to streaming platforms)
        watch_links_raw = self.enrichment.get_watch_links(movie_id, title, year, movie_data.get('providers', {}), force_refresh, tracking_data=movie_data)

        # Simplify provider names in watch links (handle both array and dict formats)
        watch_links = {}
        for category, link_obj in watch_links_raw.items():
            # Handle array format (new)
            if isinstance(link_obj, list):
                simplified_array = []
                for item in link_obj:
                    if isinstance(item, dict) and 'service' in item:
                        simplified_array.append({
                            'service': self.simplify_provider_name(item['service']),
                            'link': item.get('link')
                        })
                    else:
                        simplified_array.append(item)
                watch_links[category] = simplified_array
            # Handle dict format (legacy backward compatibility)
            elif isinstance(link_obj, dict) and 'service' in link_obj:
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
            'imdb_rating': imdb_rating,
            'providers': movie_data.get('providers', {}),
            'links': links,
            'watch_links': watch_links
        }

        # Only add review key if a review exists
        review = self.reviews.get(str(movie_id))
        if review:
            movie_dict['review'] = review

        if trailer_source:
            movie_dict['_trailer_source'] = trailer_source

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
    
    def enrich_newly_available_movies(self) -> int:
        """
        Enrich movies listed in metrics/newly_available.json.

        This is Phase 3 of the pipeline: overlay enrichment metadata onto
        movies that were added to data.json during discovery (Phase 2).

        Returns:
            int: Number of movies successfully enriched
        """
        print("🎨 Starting enrichment phase...")
        _enrich_start = time.time()

        # Check if data.json exists
        if not os.path.exists('data.json'):
            print("❌ No data.json found - run discovery phase first")
            return 0

        # Fix schema gracefully
        if not self.validator.fix_data_json_schema('data.json'):
            print("❌ Could not fix data.json schema")
            return 0

        # Load existing data.json
        try:
            with open('data.json', 'r') as f:
                display_data = json.load(f)
        except Exception as e:
            print(f"❌ Error loading data.json: {e}")
            return 0

        existing_movies = display_data.get('movies', [])
        movie_lookup = {str(m.get('id', '')): i for i, m in enumerate(existing_movies) if m.get('id')}
        _initial_movie_count = len(existing_movies)
        self.logger.info(f"Enrichment loaded data.json: {_initial_movie_count} movies")

        # Auto-retire movies whose digital_date is older than 90 days
        retire_cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        retired_count = 0
        for movie in existing_movies:
            dd = movie.get('digital_date') or ''
            if dd and dd < retire_cutoff and movie.get('_enrichment_status') != 'retired':
                movie['_enrichment_status'] = 'retired'
                retired_count += 1
        if retired_count:
            print(f"  📦 Retired {retired_count} movies older than 90 days from enrichment")
            self.logger.info(f"Retired {retired_count} movies older than 90 days from enrichment")

        # Find movies to enrich from newly_available.json
        newly_available_file = 'metrics/newly_available.json'
        movie_ids_to_enrich = []
        if os.path.exists(newly_available_file):
            try:
                with open(newly_available_file, 'r') as f:
                    newly_available = json.load(f)
                movie_ids_to_enrich = [str(mid) for mid in newly_available.get('movie_ids', [])]
                state_date = newly_available.get('date', 'unknown')

                today = datetime.now().strftime('%Y-%m-%d')
                if state_date != today:
                    print(f"⚠️ State file date ({state_date}) is not today ({today}) - may be stale")
            except Exception as e:
                print(f"⚠️ Could not load {newly_available_file}: {e}")

        newly_count = len(movie_ids_to_enrich)

        # Catch-up: retry movies with incomplete enrichment
        seen_ids = set(movie_ids_to_enrich)
        catchup_ids = []
        retry_cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        orphan_cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        for movie in existing_movies:
            movie_id = str(movie.get('id', ''))
            if not movie_id or movie_id in seen_ids:
                continue
            digital_date = movie.get('digital_date', '')
            status = movie.get('_enrichment_status', '')
            gaps = movie.get('_enrichment_gaps')
            attempts = movie.get('_enrichment_attempts', 0)
            if attempts >= MAX_ENRICHMENT_ATTEMPTS:
                continue
            # Never attempted — wider 30-day window since these were missed entirely
            if not status and not movie.get('enriched', True):
                if digital_date >= orphan_cutoff:
                    catchup_ids.append(movie_id)
            # Retry failed/pending — 7-day window
            elif digital_date >= retry_cutoff:
                if status in ('pending', 'failed', 'error', 'timeout'):
                    catchup_ids.append(movie_id)
                elif status == 'completed' and gaps:
                    catchup_ids.append(movie_id)

        movie_ids_to_enrich.extend(catchup_ids)

        # Enforce batch limit
        if len(movie_ids_to_enrich) > MAX_ENRICHMENT_BATCH:
            movie_ids_to_enrich = movie_ids_to_enrich[:MAX_ENRICHMENT_BATCH]

        if not movie_ids_to_enrich:
            print("✅ No movies to enrich (no new arrivals, no catch-up needed)")
            return 0

        catchup_count = len(catchup_ids)
        print(f"🎯 Enrichment queue: {newly_count} new + {catchup_count} catch-up = {len(movie_ids_to_enrich)} total")

        # Preload IMDb dataset so first movie isn't penalized
        self._load_imdb_dataset()

        # Load tracking database for movie details
        tracking_data = self.storage.load_all_movies()
        if not tracking_data:
            print("❌ Could not load movie tracking database")
            return 0

        enriched_count = 0
        _loop_start = time.time()
        _loop_timeout = ENRICHMENT_LOOP_TIMEOUT_MINUTES * 60

        for movie_id in movie_ids_to_enrich:
            # Safety net: bail out if enrichment has been running too long
            if (time.time() - _loop_start) > _loop_timeout:
                print(f"  ⏰ Enrichment loop exceeded {ENRICHMENT_LOOP_TIMEOUT_MINUTES} min — stopping. Remaining movies will be retried next run.")
                break

            movie_id = str(movie_id)  # Ensure consistent string format for lookup
            if movie_id not in movie_lookup:
                print(f"  ⚠️ Movie {movie_id} not found in data.json - skipping")
                continue

            if movie_id not in tracking_data.get('movies', {}):
                print(f"  ⚠️ Movie {movie_id} not found in tracking database - skipping")
                continue

            movie_data = tracking_data['movies'][movie_id]
            movie_index = movie_lookup[movie_id]

            try:
                # Track enrichment attempts for catch-up retry limiting
                existing_movies[movie_index]['_enrichment_attempts'] = \
                    existing_movies[movie_index].get('_enrichment_attempts', 0) + 1

                # Get full movie/TV details from TMDB
                if str(movie_id).startswith('tv_'):
                    numeric_id = str(movie_id).replace('tv_', '')
                    movie_details = self.get_tv_details(numeric_id)
                else:
                    movie_details = self.get_movie_details(movie_id)
                if not movie_details:
                    existing_movies[movie_index]['_enrichment_status'] = 'failed'
                    print(f"  ✗ Could not fetch TMDB details for {movie_data.get('title', movie_id)} — marked failed for retry")
                    continue

                # Get enrichment fields only
                _movie_start = time.time()
                enrichment_fields = self.get_enrichment_only_fields(movie_id, movie_data, movie_details, force_refresh=False)
                _movie_elapsed = time.time() - _movie_start
                if _movie_elapsed > 90:
                    print(f"  ⚠️ {movie_data.get('title', movie_id)} took {_movie_elapsed:.0f}s (slow)", flush=True)
                if enrichment_fields:
                    # Deep merge links: enrichment sets {wikipedia, trailer, rt},
                    # but external processes may have added other keys (e.g. trailer_hosted).
                    # Merge enrichment links INTO existing links, not replace.
                    if 'links' in enrichment_fields:
                        existing_links = existing_movies[movie_index].get('links', {})
                        existing_links.update(enrichment_fields['links'])
                        enrichment_fields['links'] = existing_links

                    # Update the movie in place with enriched fields
                    existing_movies[movie_index].update(enrichment_fields)
                    # Mark enrichment status as completed
                    existing_movies[movie_index]['_enrichment_status'] = 'completed'

                    # Track enrichment gaps (all meaningful fields, not just watch_links/rt)
                    gaps = []
                    if not enrichment_fields.get('watch_links'):
                        gaps.append('watch_links')
                    if enrichment_fields.get('links', {}).get('rt') is None and enrichment_fields.get('rt_score') is None:
                        gaps.append('rt_score')
                    if not enrichment_fields.get('links', {}).get('trailer'):
                        gaps.append('trailer')
                    if not enrichment_fields.get('links', {}).get('wikipedia'):
                        gaps.append('wikipedia')
                    if enrichment_fields.get('imdb_rating') is None:
                        gaps.append('imdb_rating')
                    if gaps:
                        existing_movies[movie_index]['_enrichment_gaps'] = gaps
                    elif '_enrichment_gaps' in existing_movies[movie_index]:
                        del existing_movies[movie_index]['_enrichment_gaps']

                    # Log with warning when providers exist but no watch links found
                    watch_links_count = len(enrichment_fields.get('watch_links', {}))
                    providers_rent_buy = len(movie_data.get('providers', {}).get('rent', [])) + \
                                         len(movie_data.get('providers', {}).get('buy', []))
                    if providers_rent_buy > 0 and watch_links_count == 0:
                        print(f"  ⚠ {movie_data.get('title')} - WARNING: {providers_rent_buy} providers but 0 watch links")
                    else:
                        print(f"  ✓ {movie_data.get('title')} - Links: {watch_links_count}")
                    enriched_count += 1
                else:
                    # Mark enrichment status as failed but keep movie in data.json
                    existing_movies[movie_index]['_enrichment_status'] = 'failed'
                    print(f"  ✗ Enrichment failed for {movie_data.get('title')}")

            except Exception as e:
                # Mark enrichment status as error but keep movie in data.json
                if movie_index < len(existing_movies):
                    existing_movies[movie_index]['_enrichment_status'] = 'error'
                print(f"  ✗ Error enriching {movie_data.get('title', movie_id)}: {e}")
                continue

        # Sync enriched flag to movie_tracking.json
        # Also revert false positives (available + zero watch_links) back to tracking
        try:
            tracking_updated = 0
            reverted_count = 0
            for mid in movie_ids_to_enrich:
                mid = str(mid)
                if mid in movie_lookup:
                    movie = existing_movies[movie_lookup[mid]]
                    if movie.get('_enrichment_status') == 'completed' and mid in tracking_data.get('movies', {}):
                        tracking_data['movies'][mid]['enriched'] = True
                        tracking_data['movies'][mid]['enrichment_date'] = datetime.now().strftime('%Y-%m-%d')
                        tracking_updated += 1

                        # Check for false positive: enriched successfully but zero watch links
                        wl = movie.get('watch_links', {})
                        wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
                        if wl_count == 0 and tracking_data['movies'][mid].get('status') == 'available':
                            old_source = tracking_data['movies'][mid].get('_discovery_source', 'unknown')
                            # Mark which discovery source was false positive (so the OTHER can still try)
                            if old_source == 'tmdb_type4':
                                tracking_data['movies'][mid]['_type4_false_positive'] = True
                            else:
                                tracking_data['movies'][mid]['_providers_false_positive'] = True
                            tracking_data['movies'][mid]['status'] = 'tracking'
                            tracking_data['movies'][mid]['_reverted_from_available'] = True
                            tracking_data['movies'][mid]['_false_positive_source'] = old_source
                            # Keep digital_date as evidence (don't null it)
                            reverted_count += 1
                            # Also remove from data.json so it doesn't stay on the wall
                            if mid in movie_lookup:
                                existing_movies[movie_lookup[mid]] = None
                            print(f"  ↩ {movie.get('title')} — reverted to tracking, removed from wall (zero watch links, was: {old_source})")
            # Clean up any false-positive removals before saving
            if reverted_count > 0:
                # Track removed IDs so _safe_save_data_json won't rescue them from disk
                self._false_positive_removed_ids = {
                    str(m.get('id', m.get('tmdb_id', '')))
                    for i, m in enumerate(existing_movies) if m is None
                }
                existing_movies = [m for m in existing_movies if m is not None]
                movie_lookup = {str(m.get('id', m.get('tmdb_id', ''))): i for i, m in enumerate(existing_movies)}
            if tracking_updated > 0 or reverted_count > 0:
                self.storage.atomic_write_json(tracking_data, 'movie_tracking.json', backup=True)
                print(f"📝 Updated movie_tracking.json: {tracking_updated} movies marked enriched")
                if reverted_count > 0:
                    print(f"↩ Reverted {reverted_count} false-positive movies back to tracking")
        except Exception as e:
            print(f"⚠️ Could not update movie_tracking.json: {e}")

        # Categorize all movies (backfills any missing categories from prior runs)
        existing_movies, _ = self.apply_admin_overrides(existing_movies)

        # Save enrichment results to data.json BEFORE trailer hosting
        # Uses safe save with reload-merge to prevent lost updates
        if not self._safe_save_data_json(display_data, existing_movies, label="enrichment"):
            return 0
        print(f"✅ Enriched {enriched_count}/{len(movie_ids_to_enrich)} movies ({len(existing_movies)} total, was {_initial_movie_count} at load)")

        # Post-enrichment: Host trailers for newly enriched movies
        trailer_config = self.config.get('trailer_hosting', {})
        if trailer_config.get('enabled', False) and trailer_config.get('pipeline_integration', False):
            print("🎬 Hosting trailers for newly enriched movies...")
            hosted_count = 0
            for movie_id in movie_ids_to_enrich:
                movie_id = str(movie_id)
                if movie_id not in movie_lookup:
                    continue
                movie_index = movie_lookup[movie_id]
                movie = existing_movies[movie_index]
                trailer_url = movie.get('links', {}).get('trailer')
                if trailer_url and not movie.get('links', {}).get('trailer_hosted'):
                    hosted_url = self.host_trailer_for_movie(
                        movie_id,
                        movie.get('title', ''),
                        str(movie.get('year', '')),
                        trailer_url
                    )
                    if hosted_url:
                        existing_movies[movie_index]['links']['trailer_hosted'] = hosted_url
                        hosted_count += 1
            if hosted_count > 0:
                # Re-save with trailer_hosted URLs added (safe save prevents lost updates)
                self._safe_save_data_json(display_data, existing_movies, label="trailer_hosting")
                print(f"  ✓ Hosted {hosted_count} trailer(s)")
            else:
                print("  No new trailers to host")
        else:
            print("🎬 Trailer hosting: disabled (config)")

        # Write enrichment metrics
        try:
            enrichment_metrics = {
                "timestamp": datetime.now().isoformat(),
                "movies_requested": len(movie_ids_to_enrich),
                "movies_enriched": enriched_count,
                "movies_deferred": len(movie_ids_to_enrich) - enriched_count,
                "enrichment_duration_seconds": round(time.time() - _enrich_start, 2),
            }
            with open('metrics/enrichment_run.json', 'w') as f:
                json.dump(enrichment_metrics, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not write enrichment metrics: {e}")

        return enriched_count

    def _fetch_eventive_screening_info(self, slug):
        """
        Fetch festival name and availability window from Eventive page.
        Returns dict: {'name': str, 'available_start': str|None, 'available_end': str|None}

        Results are cached in memory so each slug is only fetched once per run.
        """
        if not hasattr(self, '_screening_info_cache'):
            self._screening_info_cache = {}

        if slug in self._screening_info_cache:
            return self._screening_info_cache[slug]

        result = {'name': None, 'available_start': None, 'available_end': None}

        try:
            resp = requests.get(f'https://watch.eventive.org/{slug}/', timeout=10,
                                headers={'User-Agent': 'Mozilla/5.0'})
            if resp.ok:
                # Extract festival name from <title> tag
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', resp.text, re.IGNORECASE)
                if title_match:
                    raw_title = title_match.group(1).strip()
                    # Eventive titles: "Catalog | Name", "Festival Program | Name", etc.
                    name = re.sub(r'^[^|]+\|\s*', '', raw_title).strip() if '|' in raw_title else raw_title.strip()
                    # Strip trailing edition numbers like "31" from "EBIJFF31" (but keep 4-digit years)
                    name = re.sub(r'(?<!\d)\d{1,2}$', '', name).strip()
                    if name:
                        result['name'] = name

                # Extract availability window from embedded JSON (start_time/end_time)
                time_matches = re.findall(
                    r'"start_time":"(\d{4}-\d{2}-\d{2})T[^"]*","end_time":"(\d{4}-\d{2}-\d{2})T[^"]*"',
                    resp.text
                )
                if time_matches:
                    # All films in a festival share the same window — use the latest end date
                    starts = sorted(set(s for s, _ in time_matches))
                    ends = sorted(set(e for _, e in time_matches))
                    result['available_start'] = starts[0]
                    result['available_end'] = ends[-1]

                if result['name']:
                    dates_str = f", {result['available_start']} to {result['available_end']}" if result['available_end'] else ""
                    print(f"  ℹ️  Auto-detected screening info for '{slug}': \"{result['name']}\"{dates_str}")

        except Exception as e:
            self.logger.debug(f"Could not fetch Eventive page for slug '{slug}': {e}")

        # Fallback name if nothing was found
        if not result['name']:
            result['name'] = slug.replace('_', ' ').replace('-', ' ').title()
            print(f"  ⚠️  Could not auto-detect screening name for '{slug}', using fallback: \"{result['name']}\"")

        self._screening_info_cache[slug] = result
        return result

    def check_virtual_screening_expirations(self):
        """
        Check virtual screening links for expiration.
        Dead links (404/410) cause the movie to be hidden and returned to tracking.
        """
        data_file = 'data.json'
        if not os.path.exists(data_file):
            print("  No data.json found")
            return

        with open(data_file, 'r') as f:
            data = json.load(f)

        movies = data.get('movies', [])
        screening_movies = [m for m in movies if m.get('categories', {}).get('is_virtual_screening')]

        if not screening_movies:
            print("  No virtual screening movies found")
            return

        print(f"  Checking {len(screening_movies)} virtual screening movies...")
        active_count = 0
        expired_count = 0
        today_str = datetime.now().strftime('%Y-%m-%d')
        modified = False

        # Load manual end dates from config as fallback
        config_end_dates = self.config.get('screening_end_dates', {})

        # Load tracking database for status reset
        tracking_path = 'movie_tracking.json'
        tracking_data = {}
        if os.path.exists(tracking_path):
            with open(tracking_path, 'r') as f:
                tracking_data = json.load(f)

        for movie in screening_movies:
            title = movie.get('title', 'Unknown')
            screening_info = movie.get('virtual_screening_info', {})

            # Skip already-expired movies
            if screening_info.get('status') == 'expired':
                continue

            # Find the screening link to check
            screening_link = None
            watch_links = movie.get('watch_links', {})
            vod = watch_links.get('vod')
            if isinstance(vod, list):
                for v in vod:
                    svc = v.get('service', '').lower()
                    link = v.get('link', '') or ''
                    if svc == 'eventive' or 'eventive.org' in link or 'festivalplayer' in link or 'shift72.com' in link:
                        screening_link = link
                        break
            elif isinstance(vod, dict):
                link = vod.get('link', '') or ''
                svc = vod.get('service', '').lower()
                if svc == 'eventive' or 'eventive.org' in link or 'festivalplayer' in link or 'shift72.com' in link:
                    screening_link = link

            def _expire_movie(reason):
                """Mark a screening as expired, hide it, return to tracking."""
                nonlocal expired_count, modified
                expired_count += 1
                screening_info['status'] = 'expired'
                screening_info['last_checked'] = today_str
                movie['virtual_screening_info'] = screening_info
                movie['hidden'] = True
                modified = True
                slug = screening_info.get('screening_slug', '?')
                print(f"  ❌ Expired: {title} ({slug}) — {reason}")

                movie_id = str(movie.get('id', ''))
                if movie_id and movie_id in tracking_data.get('movies', {}):
                    tracking_movie = tracking_data['movies'][movie_id]
                    tracking_movie['status'] = 'tracking'
                    if 'digital_date' in tracking_movie:
                        del tracking_movie['digital_date']
                    print(f"    → Returned to tracking for VOD re-discovery")

            # Check 1: Date-based expiration (available_end in the past)
            slug = screening_info.get('screening_slug', '')
            available_end = screening_info.get('available_end') or config_end_dates.get(slug)
            if available_end and available_end < today_str:
                _expire_movie(f"availability ended {available_end}")
                continue

            # Check 2: No watch link at all (festival likely ended, link was never found)
            if not screening_link:
                _expire_movie("no watch link found")
                continue

            # Check 3: HTTP HEAD check on the actual link
            try:
                resp = requests.head(screening_link, timeout=10, allow_redirects=True)
                if resp.status_code in (404, 410, 403):
                    _expire_movie(f"HTTP {resp.status_code}")
                else:
                    # Link is still alive
                    active_count += 1
                    screening_info['last_checked'] = today_str
                    movie['virtual_screening_info'] = screening_info
                    modified = True
            except requests.RequestException as e:
                # Network error — don't mark as expired, just log
                print(f"  ⚠️  Could not check {title}: {e}")

        # Save changes
        if modified:
            with open(data_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"  💾 Updated data.json")

            # Save tracking data if we reset any movies
            if expired_count > 0 and tracking_data:
                with open(tracking_path, 'w') as f:
                    json.dump(tracking_data, f, indent=2)
                print(f"  💾 Updated movie_tracking.json")

        print(f"  📊 Results: {active_count} active, {expired_count} expired")

    def reenrich_watch_link_gaps(self):
        """
        Re-enrich movies with missing or unverified watch links.

        Finds two categories:
        1. Gap movies: missing VOD deep links entirely
        2. Unverified movies: have watch_links but were never verified by the
           improved JustWatch title-matching code (_watch_links_verified not set)

        Re-runs JustWatch with force_refresh=True. JustWatch's own confidence
        checking decides if links are good — no TMDB cross-referencing needed.

        Returns:
            int: Number of movies successfully re-enriched with watch links
        """
        if not os.path.exists('data.json'):
            print("❌ No data.json found")
            return 0

        with open('data.json', 'r') as f:
            display_data = json.load(f)

        existing_movies = display_data.get('movies', [])

        # Find movies missing VOD deep links
        gap_movies = []
        gap_indices = set()
        for i, movie in enumerate(existing_movies):
            watch_links = movie.get('watch_links', {})
            vod = watch_links.get('vod')
            has_vod = (isinstance(vod, list) and any(isinstance(v, dict) and v.get('link') for v in vod)) or \
                      (isinstance(vod, dict) and bool(vod.get('link')))
            if not has_vod:
                gap_movies.append((i, movie))
                gap_indices.add(i)

        # Find movies with unverified watch links — re-run through improved JustWatch
        unverified_movies = []
        unverified_indices = set()
        for i, movie in enumerate(existing_movies):
            if movie.get('_watch_links_verified'):
                continue
            watch_links = movie.get('watch_links', {})
            if not watch_links:
                continue
            unverified_movies.append((i, movie))
            unverified_indices.add(i)

        if not gap_movies and not unverified_movies:
            print("✅ No watch link issues found — all movies verified")
            return 0

        # Combine — unverified first (wrong data worse than missing), deduplicate
        gap_only = [(i, m) for i, m in gap_movies if i not in unverified_indices]
        all_movies = unverified_movies + gap_only
        vod_config = self.config.get('vod_scraper', {})
        max_batch = vod_config.get('reenrich_batch_size', 50)

        if unverified_movies:
            print(f"🔍 Found {len(unverified_movies)} movies with unverified watch links")
        if gap_movies:
            print(f"🔍 Found {len(gap_movies)} movies missing VOD links")

        if max_batch > 0 and len(all_movies) > max_batch:
            print(f"  Processing first {max_batch} of {len(all_movies)} total:")
            all_movies = all_movies[:max_batch]
        else:
            print(f"  Processing {len(all_movies)} movies:")

        for _, movie in all_movies:
            print(f"  • {movie.get('title')}")

        # Load tracking database for enrichment
        tracking_data = self.storage.load_all_movies()
        if not tracking_data:
            print("❌ Could not load movie tracking database")
            return 0

        fixed_count = 0
        unsaved_count = 0
        save_interval = 10
        for movie_index, movie in all_movies:
            movie_id = str(movie.get('id', ''))
            title = movie.get('title', 'Unknown')
            year = str(movie.get('year', ''))
            providers = movie.get('providers', {})
            is_unverified = movie_index in unverified_indices

            try:
                # Clear old watch_links for unverified movies so JustWatch starts fresh
                if is_unverified:
                    existing_movies[movie_index]['watch_links'] = {}

                tracking_movie = tracking_data.get('movies', {}).get(movie_id, movie)

                watch_links = self.enrichment.get_watch_links(
                    movie_id, title, year, providers,
                    force_refresh=True, tracking_data=tracking_movie
                )

                vod = watch_links.get('vod', []) if watch_links else []
                has_real_vod = False
                if isinstance(vod, list):
                    has_real_vod = any(isinstance(v, dict) and v.get('link') for v in vod)
                elif isinstance(vod, dict):
                    has_real_vod = bool(vod.get('link'))

                if has_real_vod or (watch_links and watch_links.get('streaming')):
                    existing_movies[movie_index]['watch_links'] = watch_links
                    existing_gaps = existing_movies[movie_index].get('_enrichment_gaps', [])
                    if 'watch_links' in existing_gaps:
                        existing_gaps.remove('watch_links')
                        if existing_gaps:
                            existing_movies[movie_index]['_enrichment_gaps'] = existing_gaps
                        else:
                            existing_movies[movie_index].pop('_enrichment_gaps', None)
                    existing_movies[movie_index].pop('_quality_warnings', None)
                    existing_movies[movie_index].pop('_needs_review', None)
                    existing_movies[movie_index]['_watch_links_verified'] = datetime.now().isoformat()
                    label = "verified" if is_unverified else "resolved"
                    print(f"  ✓ {title} — {label}")
                    fixed_count += 1
                    unsaved_count += 1

                    if unsaved_count >= save_interval:
                        self._safe_save_data_json(display_data, existing_movies, label="reenrich_incremental")
                        print(f"  💾 Incremental save ({fixed_count} fixed so far)")
                        unsaved_count = 0
                elif is_unverified:
                    existing_movies[movie_index]['watch_links'] = {}
                    existing_movies[movie_index].pop('_quality_warnings', None)
                    existing_movies[movie_index].pop('_needs_review', None)
                    existing_movies[movie_index]['_watch_links_verified'] = datetime.now().isoformat()
                    print(f"  ○ {title} — cleared (JustWatch no match)")
                    unsaved_count += 1
                else:
                    print(f"  ○ {title} — not found")
            except Exception as e:
                print(f"  ✗ Error re-enriching {title}: {e}")
                continue

        # Final save (safe save prevents lost updates)
        if unsaved_count > 0:
            if not self._safe_save_data_json(display_data, existing_movies, label="reenrich_final"):
                return 0
            print(f"✅ Re-enriched {fixed_count}/{len(all_movies)} movies")

        return fixed_count

    def archive_old_movies(self, days=90):
        """
        Move movies older than `days` from data.json into data_archive.json.

        Keeps data.json lean. Archive is append-only and deduped by movie ID.
        Pre-order movies (future dates) and movies without digital_date are never archived.
        """
        if not os.path.exists('data.json'):
            return

        with open('data.json', 'r') as f:
            data = json.load(f)

        movies = data.get('movies', [])
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')

        keep = []
        to_archive = []
        for m in movies:
            dd = m.get('digital_date') or ''
            # Archive if digital_date exists, is in the past, and older than cutoff
            if dd and dd <= today and dd < cutoff:
                to_archive.append(m)
            else:
                keep.append(m)

        if not to_archive:
            return

        # Load or create archive
        archive_path = 'data_archive.json'
        archive_movies = []
        if os.path.exists(archive_path):
            try:
                with open(archive_path, 'r') as f:
                    archive_data = json.load(f)
                archive_movies = archive_data.get('movies', [])
            except Exception:
                archive_movies = []

        # Dedupe by ID before appending
        existing_ids = {str(m.get('id')) for m in archive_movies}
        new_archived = [m for m in to_archive if str(m.get('id')) not in existing_ids]
        archive_movies.extend(new_archived)

        # Save archive FIRST (before modifying data.json) — atomic so a crash
        # mid-write doesn't destroy the archive before data.json is trimmed.
        archive_data = {
            'archived_at': datetime.now().isoformat(),
            'count': len(archive_movies),
            'movies': archive_movies
        }
        self.storage.atomic_write_json(archive_data, archive_path, backup=False)

        # Now slim down data.json (atomic write — archive IS the backup)
        data['movies'] = keep
        data['count'] = len(keep)
        self.storage.atomic_write_json(data, 'data.json', backup=False)

        print(f"📦 Archived {len(to_archive)} movies (>{days} days old) → data_archive.json")
        print(f"   data.json: {len(keep)} movies | archive: {len(archive_movies)} total")
        self.logger.info(f"Archived {len(to_archive)} movies older than {days} days")

    def _inject_selected_pull_quotes(self, movies_list):
        """Add selected pull quotes from cache to movies for data.json output."""
        combined_path = 'cache/pull_quotes_combined.json'
        gemini_path = 'cache/pull_quotes_cache.json'

        combined = {}
        gemini = {}
        try:
            if os.path.exists(combined_path):
                with open(combined_path, 'r') as f:
                    combined = json.load(f)
            if os.path.exists(gemini_path):
                with open(gemini_path, 'r') as f:
                    gemini = json.load(f)
        except Exception as e:
            self.logger.warning(f"Pull quotes injection: Error loading caches: {e}")
            return

        injected = 0
        for movie in movies_list:
            title = movie.get('title', '')
            year = movie.get('year', '')
            key = f"{title}_{year}"

            # Check combined cache first (richer data with curation), then gemini cache
            all_quotes = []
            entry = combined.get(key, {})
            if entry:
                all_quotes = entry.get('rt_quotes', []) + entry.get('lb_quotes', [])
            elif key in gemini:
                all_quotes = gemini[key].get('quotes', [])

            # Only include selected quotes
            selected = []
            for q in all_quotes:
                if q.get('selected'):
                    selected.append({
                        'text': q.get('text') or q.get('pull_quote', ''),
                        'critic': q.get('critic', ''),
                        'outlet': q.get('outlet', ''),
                        'source': q.get('source', '')
                    })

            if selected:
                movie['pull_quotes'] = selected
                injected += 1
            elif 'pull_quotes' in movie:
                # Remove stale quotes if none are selected anymore
                del movie['pull_quotes']

        if injected:
            print(f"💬 Injected pull quotes for {injected} movies")

    def _apply_cached_watch_links(self, movies_list):
        """Apply cached watch links to movies with empty watch_links.

        Reads from cache/watch_links_cache.json and patches movies whose
        watch_links are empty but have cached data (e.g. from TV show fix).
        """
        cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache', 'watch_links_cache.json')
        if not os.path.exists(cache_path):
            return

        try:
            with open(cache_path, 'r') as f:
                cache = json.load(f)
        except Exception as e:
            self.logger.warning(f"Watch links cache injection: Error loading cache: {e}")
            return

        applied = 0
        for movie in movies_list:
            # Skip movies that already have working watch links (non-null URLs)
            existing = movie.get('watch_links', {})
            streaming = existing.get('streaming', [])
            if isinstance(streaming, dict):
                streaming = [streaming]
            vod = existing.get('vod', [])
            if isinstance(vod, dict):
                vod = [vod]
            has_real_streaming = any(s.get('link') for s in streaming if isinstance(s, dict))
            has_real_vod = any(v.get('link') for v in vod if isinstance(v, dict))
            if has_real_streaming or has_real_vod:
                continue

            # Check cache by movie ID
            movie_id = str(movie.get('id', ''))
            cached = cache.get(movie_id, {})
            cached_links = cached.get('links', {})
            if not cached_links:
                continue

            movie['watch_links'] = cached_links
            applied += 1
            self.logger.debug(f"Applied cached watch links for {movie.get('title')}")

        if applied:
            print(f"🔗 Applied cached watch links for {applied} movies")

    def generate_display_data(self, days_back=90, incremental=True, force_refresh=False):
        """
        PHASE 4: Apply admin overrides and prepare final display data.

        Loads data.json, applies admin overrides (hide/featured/ordering),
        and saves the result. Old movies (>90 days) are archived to data_archive.json.

        Args:
            days_back: Used for stats only (frontend handles date filtering)
            incremental: Deprecated (kept for compatibility)
            force_refresh: Deprecated (kept for compatibility)
        """
        # Try to fix schema issues first (adds missing keys, never removes movies)
        if os.path.exists('data.json'):
            self.validator.fix_data_json_schema('data.json')

        # Load ALL current movies from data.json (old movies already archived)
        all_movies = []
        existing_display_data = None  # Initialize for later use preserving fields like latest_playlist_url
        cutoff_date = datetime.now() - timedelta(days=days_back)

        try:
            with open('data.json', 'r') as f:
                existing_display_data = json.load(f)
                all_movies = existing_display_data.get('movies', [])

                # Count movies within days_back window for stats only (not for filtering)
                recent_count = sum(1 for m in all_movies if m.get('digital_date') and
                    self._is_recent(m['digital_date'], cutoff_date))

                print(f"📊 Loaded {len(all_movies)} movies from data.json ({recent_count} within {days_back} days)")
                self.logger.info(f"Display preparation: {len(all_movies)} total movies, {recent_count} recent")

        except FileNotFoundError:
            print(f"⚠️  No data.json found - run discovery phase first")
            self.logger.warning("No data.json found for display preparation")
            return

        except Exception as e:
            print(f"❌ Error loading data.json for display: {e} - aborting to preserve data")
            self.logger.error(f"Error loading data.json for display: {e}")
            return

        # Inject selected pull quotes from cache into movie data
        self._inject_selected_pull_quotes(all_movies)

        # Apply cached watch links to movies with empty watch_links
        self._apply_cached_watch_links(all_movies)

        # Filter out movies with zero watch links (likely false-positive discoveries)
        pre_filter_count = len(all_movies)
        filtered_out = []
        filtered_movies = []
        for m in all_movies:
            wl = m.get('watch_links', {})
            wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
            if wl_count == 0:
                filtered_out.append(m.get('title', m.get('id', '?')))
            else:
                filtered_movies.append(m)
        if filtered_out:
            print(f"🚫 Filtered {len(filtered_out)} movies with zero watch links:")
            for title in filtered_out:
                print(f"   - {title}")
            self.logger.info(f"Filtered {len(filtered_out)} zero-watch-link movies from display: {filtered_out}")
        all_movies = filtered_movies

        # Apply admin overrides to ALL movies (not just recent ones)
        print(f"🔧 Applying admin overrides to {len(all_movies)} movies...")

        # Sort by digital release date (newest first)
        # Handle None values by treating them as empty strings
        all_movies.sort(key=lambda x: x.get('digital_date') or '', reverse=True)

        # Apply admin panel overrides (categorize movies, apply staff picks, ordering)
        display_movies, staff_pick_ids = self.apply_admin_overrides(all_movies)

        # Save movies to data.json (old movies archived separately after this step)
        # Preserve latest_playlist_url if it exists from YouTube playlist manager
        existing_playlist_url = existing_display_data.get('latest_playlist_url') if existing_display_data else None

        output_data = {
            'generated_at': datetime.now().isoformat(),
            'count': len(display_movies),
            'movies': display_movies,
            'staff_picks': staff_pick_ids,  # New: curated recommendations
            'featured': staff_pick_ids,  # Backwards compatibility (same as staff_picks)
            'latest_playlist_url': existing_playlist_url or 'NOT SET'
        }

        self._safe_save_data_json(output_data, display_movies, label="display_generation")

        # Archive movies older than 90 days to data_archive.json
        self.archive_old_movies(days=90)

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

        # Cleanup trailer finder if initialized (Gemini + Playwright fallback)
        if self.trailer_finder:
            try:
                self.trailer_finder.cleanup()
                self.logger.debug("Trailer finder closed")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup trailer finder: {e}")

        # Save caches (RT cache is managed by rt_scraper)
        self.storage.save_cache(self.wikipedia_cache, 'cache/wikipedia_cache.json')
        
        message = f"Generated data.json with {len(display_movies)} movies"
        self.logger.info(message)
        print(f"✅ {message}")  # Also print to console for visibility
        wiki_count = len([m for m in display_movies if m.get('links', {}).get('wikipedia')])
        trailer_count = len([m for m in display_movies if m.get('links', {}).get('trailer') and 'watch?v=' in m.get('links', {}).get('trailer', '')])
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

        # Enrichment statistics
        total_calls = self.enrichment_stats['search_calls'] + self.enrichment_stats['source_calls']
        cache_hit_rate = (self.enrichment_stats['cache_hits'] / (self.enrichment_stats['cache_hits'] + total_calls) * 100) if (self.enrichment_stats['cache_hits'] + total_calls) > 0 else 0

        print(f"\n📊 Watch Links Enrichment:")
        print(f"  Cache hits: {self.enrichment_stats['cache_hits']}")
        print(f"  Cache hit rate: {cache_hit_rate:.1f}%")
        scraper_successes = self.enrichment_stats.get('scraper_successes', 0)
        print(f"  Scraper successes: {scraper_successes}")

        print(f"\n📊 Agent Scraper Usage:")
        print(f"  Streaming enabled: {self.config.get('streaming_scraper', {}).get('enabled', True)}")
        print(f"  Agent initialized: {self.streaming_scraper is not None and self.streaming_scraper is not False}")
        print(f"  VOD attempts: {self.enrichment_stats['streaming_attempts']}")
        print(f"  VOD successes: {self.enrichment_stats['streaming_successes']}")
        print(f"  VOD cache hits: {self.enrichment_stats['streaming_cache_hits']}")
        print(f"  VOD failures: {self.enrichment_stats['streaming_failures']}")
        if self.enrichment_stats['streaming_attempts'] > 0:
            vod_success_rate = (self.enrichment_stats['streaming_successes'] / self.enrichment_stats['streaming_attempts'] * 100)
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

        platform_attempts = self.enrichment_stats.get('vod_attempts', 0)
        platform_successes = self.enrichment_stats.get('vod_successes', 0)
        platform_failures = self.enrichment_stats.get('vod_failures', 0)

        print(f"  VOD scraper attempts: {platform_attempts}")
        print(f"  VOD scraper successes: {platform_successes}")
        print(f"  VOD scraper failures: {platform_failures}")

        if platform_attempts > 0:
            platform_success_rate = (platform_successes / platform_attempts * 100)
            print(f"  VOD scraper success rate: {platform_success_rate:.1f}%")

            # Show overall success comparison
            if success_rate > 0:
                comparison = "higher" if platform_success_rate > success_rate else "lower"
                print(f"  Success rate vs cache: {platform_success_rate:.1f}% ({comparison} than {success_rate:.1f}%)")
        else:
            print(f"  ⚠️  VOD scraper was never called (check if movies have Amazon/Apple TV providers)")

        # Show maintenance info
        last_update = vod_config.get('maintenance', {}).get('last_selector_update', 'unknown')
        update_freq = vod_config.get('maintenance', {}).get('expected_update_frequency', 'quarterly')
        print(f"  Last selector update: {last_update}")
        print(f"  Expected update frequency: {update_freq}")

        print(f"\n📊 RT Scraper Usage:")
        print(f"  RT attempts: {self.enrichment_stats['rt_attempts']}")
        print(f"  RT successes: {self.enrichment_stats['rt_successes']}")
        print(f"  RT cache hits: {self.enrichment_stats['rt_cache_hits']}")
        if self.enrichment_stats['rt_attempts'] > 0:
            rt_success_rate = (self.enrichment_stats['rt_successes'] / self.enrichment_stats['rt_attempts'] * 100)
            print(f"  RT success rate: {rt_success_rate:.1f}%")

        print(f"\n📊 Trailer Scraper Usage:")
        print(f"  Trailer attempts: {self.enrichment_stats['trailer_attempts']}")
        print(f"  Trailer successes: {self.enrichment_stats['trailer_successes']}")
        print(f"  Trailer cache hits: {self.enrichment_stats['trailer_cache_hits']}")
        if self.enrichment_stats['trailer_attempts'] > 0:
            trailer_success_rate = (self.enrichment_stats['trailer_successes'] / self.enrichment_stats['trailer_attempts'] * 100)
            print(f"  Trailer success rate: {trailer_success_rate:.1f}%")

        print(f"\n📊 Admin Override Usage:")
        print(f"  Manual tracking hits: {self.enrichment_stats.get('manual_tracking_hits', 0)}")
        print(f"  Override hits: {self.enrichment_stats['override_hits']}")
        if self.enrichment_stats['override_hits'] > 0:
            print(f"  Movies with manual overrides: {self.enrichment_stats['override_hits']}")

        print(f"\n🔍 Schema Validation:")
        print(f"  Validation passes: {self.enrichment_stats['schema_validation_passes']}")
        print(f"  Validation warnings: {self.enrichment_stats['schema_validation_warnings']}")
        total_validations = self.enrichment_stats['schema_validation_passes'] + self.enrichment_stats['schema_validation_warnings']
        if total_validations > 0:
            pass_rate = (self.enrichment_stats['schema_validation_passes'] / total_validations * 100)
            print(f"  Validation pass rate: {pass_rate:.1f}%")
            if self.enrichment_stats['schema_validation_warnings'] > total_validations * 0.05:  # Alert if warnings > 5%
                print(f"  ⚠️  WARNING: High validation failure rate ({self.enrichment_stats['schema_validation_warnings']}/{total_validations}) - check for systematic schema issues")

        # Intake statistics (if intake was run - TMDB API premiere ingestion)
        if self.intake_stats['api_calls'] > 0:
            print(f"\n🔍 Intake Statistics (TMDB Premieres):")
            print(f"  API calls: {self.intake_stats['api_calls']}")
            print(f"  Pages fetched: {self.intake_stats['pages_fetched']}")
            print(f"  Total results: {self.intake_stats['total_results']}")
            print(f"  New movies added: {self.intake_stats['new_movies_added']}")
            print(f"  Duplicates skipped: {self.intake_stats['duplicates_skipped']}")
            blocked = self.intake_stats.get('blocked_by_filter', 0)
            if blocked > 0:
                print(f"  Blocked by content filter: {blocked}")
            if self.intake_stats['pages_fetched'] > 0:
                avg_results_per_page = self.intake_stats['total_results'] / self.intake_stats['pages_fetched']
                print(f"  Average results per page: {avg_results_per_page:.1f}")
            if self.intake_stats['debug_enabled']:
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
                    "attempts": self.enrichment_stats['rt_attempts'],
                    "successes": self.enrichment_stats['rt_successes'],
                    "cache_hits": self.enrichment_stats['rt_cache_hits'],
                    "success_rate": calc_rate(
                        self.enrichment_stats['rt_successes'],
                        self.enrichment_stats['rt_attempts']
                    ),
                    "cache_hit_rate": calc_rate(
                        self.enrichment_stats['rt_cache_hits'],
                        self.enrichment_stats['rt_attempts']
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
                    "attempts": self.enrichment_stats['trailer_attempts'],
                    "successes": self.enrichment_stats['trailer_successes'],
                    "cache_hits": self.enrichment_stats['trailer_cache_hits'],
                    "success_rate": calc_rate(
                        self.enrichment_stats['trailer_successes'],
                        self.enrichment_stats['trailer_attempts']
                    ),
                    "cache_hit_rate": calc_rate(
                        self.enrichment_stats['trailer_cache_hits'],
                        self.enrichment_stats['trailer_attempts']
                    )
                },
                "streaming_scraper": {
                    "attempts": self.enrichment_stats['streaming_attempts'],
                    "successes": self.enrichment_stats['streaming_successes'],
                    "failures": self.enrichment_stats['streaming_failures'],
                    "cache_hits": self.enrichment_stats['streaming_cache_hits'],
                    "success_rate": calc_rate(
                        self.enrichment_stats['streaming_successes'],
                        self.enrichment_stats['streaming_attempts']
                    )
                },
                "vod_scraper": {
                    "attempts": self.enrichment_stats.get('vod_attempts', 0),
                    "successes": self.enrichment_stats.get('vod_successes', 0),
                    "failures": self.enrichment_stats.get('vod_failures', 0),
                    "success_rate": calc_rate(
                        self.enrichment_stats.get('vod_successes', 0),
                        self.enrichment_stats.get('vod_attempts', 0)
                    )
                }
            },
            "validation": {
                "passes": self.enrichment_stats['schema_validation_passes'],
                "warnings": self.enrichment_stats['schema_validation_warnings'],
                "pass_rate": calc_rate(
                    self.enrichment_stats['schema_validation_passes'],
                    self.enrichment_stats['schema_validation_passes'] +
                    self.enrichment_stats['schema_validation_warnings']
                )
            }
        }

        # Ensure metrics directory exists
        os.makedirs('metrics', exist_ok=True)

        # Append to scraper_health.jsonl (one JSON object per line for historical tracking)
        health_file = 'metrics/scraper_health.jsonl'
        try:
            with open(health_file, 'a') as f:
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

            # Validation
            val_rate = health['validation']['pass_rate']
            if val_rate is not None:
                status = "✅" if val_rate >= 95 else "⚠️" if val_rate >= 90 else "❌"
                print(f"  Validation: {status} {val_rate}% pass rate")

            print(f"  📊 Health metrics saved to {health_file}")

        except Exception as e:
            self.logger.error(f"Failed to save scraper health metrics: {e}")
            print(f"  ⚠️  Failed to save health metrics: {e}")

    def categorize_movie(self, movie, category_config):
        """
        Categorize a movie as 'big_time', 'indie', or None based on studio and budget.

        Logic:
        1. Check manual override first (admin can force tier)
        2. Match studio against big_time_studios list
        3. Fallback to budget threshold ($10M default)
        4. Default to None (uncategorized) if no match

        Returns:
            dict: Categories object with tier, is_foreign, is_staff_pick, auto_categorized, manual_override
        """
        big_time_studios = category_config.get('big_time_studios', [])
        budget_threshold = category_config.get('budget_threshold', 10000000)

        # Get movie properties
        studio = movie.get('studio', '')
        budget = movie.get('budget', 0) or 0  # Handle None
        original_language = movie.get('original_language', 'en')
        genres = movie.get('genres', []) or []

        # Check for existing manual override from movie_tracking.json
        manual_override = movie.get('categories', {}).get('manual_override')

        # Determine tier
        if manual_override:
            tier = manual_override
            auto_categorized = False
        elif studio and any(bs.lower() in studio.lower() for bs in big_time_studios):
            tier = 'big_time'
            auto_categorized = True
        elif budget >= budget_threshold:
            tier = 'big_time'
            auto_categorized = True
        else:
            tier = None
            auto_categorized = True

        # Determine foreign status
        is_foreign = original_language and original_language != 'en'

        # Determine documentary status from TMDB genres
        is_documentary = 'Documentary' in genres

        return {
            'tier': tier,  # Kept for backward compatibility
            'is_big_time': tier == 'big_time',
            'is_indie': False,  # Default; set via admin override
            'is_foreign': is_foreign,
            'is_staff_pick': False,  # Set later from staff_picks.json
            'is_restoration': False,  # Set later from restoration detection
            'is_virtual_screening': False,  # Set later from watch_links detection
            'is_series': False,  # Set later from content_type detection
            'is_documentary': is_documentary,
            'auto_categorized': auto_categorized,
            'manual_override': manual_override
        }

    def apply_admin_overrides(self, display_movies):
        """Apply admin panel decisions to final output including categorization"""

        # Load admin decisions if they exist
        staff_picks = []
        ordering = []

        # Load staff picks (renamed from featured_movies.json)
        if os.path.exists('admin/staff_picks.json'):
            with open('admin/staff_picks.json', 'r') as f:
                staff_picks = json.load(f)
        elif os.path.exists('admin/featured_movies.json'):
            # Fallback to old file for backwards compatibility
            with open('admin/featured_movies.json', 'r') as f:
                staff_picks = json.load(f)

        # Load category config
        category_config = {}
        if os.path.exists('admin/category_config.json'):
            with open('admin/category_config.json', 'r') as f:
                category_config = json.load(f)

        # Load restoration config
        restoration_config = {}
        if os.path.exists('admin/restoration_config.json'):
            with open('admin/restoration_config.json', 'r') as f:
                restoration_config = json.load(f)

        # Load manual restorations list
        manual_restorations = []
        if os.path.exists('admin/restorations.json'):
            with open('admin/restorations.json', 'r') as f:
                manual_restorations = json.load(f)

        # Load category overrides (admin toggles for all categories)
        category_overrides = {}
        if os.path.exists('admin/category_overrides.json'):
            with open('admin/category_overrides.json', 'r') as f:
                category_overrides = json.load(f)

        if os.path.exists('admin/ordering.json'):
            with open('admin/ordering.json', 'r') as f:
                ordering_data = json.load(f)
                if isinstance(ordering_data, list):
                    ordering = ordering_data

        # Load movie_tracking.json to apply manual field edits
        tracking_data = {}
        if os.path.exists('movie_tracking.json'):
            try:
                with open('movie_tracking.json', 'r') as f:
                    tracking_data = json.load(f).get('movies', {})
            except Exception as e:
                print(f"⚠️  Could not load movie_tracking.json: {e}")

        # Apply manual field edits from movie_tracking.json
        fields_updated = 0
        for movie in display_movies:
            movie_id = str(movie.get('id'))
            if movie_id in tracking_data:
                tracking_movie = tracking_data[movie_id]

                # Apply manual trailer link
                if tracking_movie.get('manual_trailer') and tracking_movie.get('links', {}).get('trailer'):
                    if 'links' not in movie:
                        movie['links'] = {}
                    movie['links']['trailer'] = tracking_movie['links']['trailer']
                    fields_updated += 1

                # Apply manual RT link
                if tracking_movie.get('manual_rt_link') and tracking_movie.get('links', {}).get('rt'):
                    if 'links' not in movie:
                        movie['links'] = {}
                    movie['links']['rt'] = tracking_movie['links']['rt']
                    fields_updated += 1

                # Apply manual Wikipedia link
                if tracking_movie.get('manual_wikipedia') and tracking_movie.get('links', {}).get('wikipedia'):
                    if 'links' not in movie:
                        movie['links'] = {}
                    movie['links']['wikipedia'] = tracking_movie['links']['wikipedia']
                    fields_updated += 1

                # Apply manual poster URL
                if tracking_movie.get('manual_poster') and tracking_movie.get('poster_url'):
                    movie['poster_url'] = tracking_movie['poster_url']
                    movie['poster'] = tracking_movie['poster_url']  # Some code uses 'poster'
                    fields_updated += 1

                # Apply manual RT score
                if tracking_movie.get('manual_rt_score') and tracking_movie.get('rt_score') is not None:
                    movie['rt_score'] = tracking_movie['rt_score']
                    fields_updated += 1

                # Apply manual director
                if tracking_movie.get('manual_director') and tracking_movie.get('crew', {}).get('director'):
                    if 'crew' not in movie:
                        movie['crew'] = {}
                    movie['crew']['director'] = tracking_movie['crew']['director']
                    fields_updated += 1

                # Apply manual country
                if tracking_movie.get('manual_country') and tracking_movie.get('country'):
                    movie['country'] = tracking_movie['country']
                    fields_updated += 1

                # Apply manual synopsis
                if tracking_movie.get('manual_synopsis') and tracking_movie.get('synopsis'):
                    movie['synopsis'] = tracking_movie['synopsis']
                    fields_updated += 1

                # Apply manual watch links
                if tracking_movie.get('watch_links'):
                    movie['watch_links'] = tracking_movie['watch_links']
                    fields_updated += 1

        if fields_updated > 0:
            print(f"📝 Applied {fields_updated} manual field edits from movie_tracking.json")

        # Load screening name mapping and manual end dates from config
        screening_names_map = self.config.get('screening_names', {})
        screening_end_dates_map = self.config.get('screening_end_dates', {})

        # Apply categorization to all movies
        big_time_count = 0
        indie_count = 0
        uncategorized_count = 0
        foreign_count = 0
        restoration_count = 0
        virtual_screening_count = 0
        documentary_count = 0
        screening_services = ['eventive']
        screening_url_patterns = ['eventive.org', 'festivalplayer.sundance.org', 'shift72.com', 'xerb.tv', 'festivalscope.com']

        def _check_virtual_screening_vod(entry):
            """Check if a single vod entry is from a virtual screening platform."""
            svc = entry.get('service', '').lower()
            link = entry.get('link', '') or ''
            if svc in screening_services:
                return True
            for pattern in screening_url_patterns:
                if pattern in link.lower():
                    return True
            return False

        for movie in display_movies:
            movie_id = str(movie.get('id'))

            # First, auto-categorize the movie
            categories = self.categorize_movie(movie, category_config)

            # Check for manual category override from tracking data
            if movie_id in tracking_data and tracking_data[movie_id].get('categories'):
                manual_categories = tracking_data[movie_id]['categories']
                # Apply manual override - preserve tier and other manual settings
                if manual_categories.get('manual_override'):
                    categories['tier'] = manual_categories.get('tier', categories['tier'])
                    categories['manual_override'] = manual_categories['manual_override']
                    categories['auto_categorized'] = False

            # Mark staff picks
            if movie_id in staff_picks:
                categories['is_staff_pick'] = True

            # Mark restorations & reissues
            is_restoration = False
            movie_year = movie.get('year', 0) or 0
            digital_date_str = movie.get('digital_date', '')
            if digital_date_str and movie_year:
                digital_year = int(digital_date_str[:4])
                year_gap = digital_year - movie_year

                year_threshold = restoration_config.get('year_gap_threshold', 10)
                if year_gap >= year_threshold:
                    is_restoration = True

                restoration_distributors = restoration_config.get('restoration_distributors', [])
                studio = movie.get('studio', '') or ''
                if studio and year_gap >= 5 and any(rd.lower() in studio.lower() for rd in restoration_distributors):
                    is_restoration = True

            if str(movie_id) in [str(r) for r in manual_restorations]:
                is_restoration = True

            categories['is_restoration'] = is_restoration

            # Mark virtual screenings (Eventive and similar platforms)
            is_virtual_screening = False
            watch_links = movie.get('watch_links', {})
            vod = watch_links.get('vod')
            screening_link = None
            screening_service = None

            if isinstance(vod, list):
                for v in vod:
                    if _check_virtual_screening_vod(v):
                        is_virtual_screening = True
                        screening_link = v.get('link', '')
                        screening_service = v.get('service', '')
                        break
            elif isinstance(vod, dict):
                if _check_virtual_screening_vod(vod):
                    is_virtual_screening = True
                    screening_link = vod.get('link', '')
                    screening_service = vod.get('service', '')

            categories['is_virtual_screening'] = is_virtual_screening

            # Populate virtual_screening_info metadata for expiration tracking
            if is_virtual_screening:
                existing_screening_info = movie.get('virtual_screening_info', {})

                # Extract screening slug from URL (pattern: watch.eventive.org/{slug}/play/{id})
                screening_slug = ''
                if screening_link:
                    if 'eventive.org/' in screening_link:
                        try:
                            slug_part = screening_link.split('eventive.org/')[1].split('/')[0]
                            if slug_part:
                                screening_slug = slug_part
                        except (IndexError, AttributeError):
                            pass
                    elif 'festivalplayer.sundance.org' in screening_link:
                        screening_slug = 'sundance'

                # Look up screening info: config.yaml name → Eventive page (name + dates) → fallback
                eventive_info = self._fetch_eventive_screening_info(screening_slug) if screening_slug else {}
                screening_name = screening_names_map.get(screening_slug, '') or eventive_info.get('name', screening_slug)

                today_str = datetime.now().strftime('%Y-%m-%d')
                available_end = eventive_info.get('available_end') or screening_end_dates_map.get(screening_slug) or existing_screening_info.get('available_end')
                screening_expired = available_end and available_end < today_str

                movie['virtual_screening_info'] = {
                    'platform': screening_service or 'Unknown',
                    'screening_slug': screening_slug,
                    'screening_name': screening_name,
                    'available_start': eventive_info.get('available_start') or existing_screening_info.get('available_start'),
                    'available_end': available_end,
                    'discovered': existing_screening_info.get('discovered', today_str),
                    'last_checked': existing_screening_info.get('last_checked', today_str),
                    'status': 'expired' if screening_expired else existing_screening_info.get('status', 'active')
                }

                # Hide expired virtual screenings automatically
                if screening_expired:
                    movie['hidden'] = True

            # Mark limited series
            categories['is_series'] = movie.get('content_type') == 'limited_series'

            movie['categories'] = categories

            # Apply category overrides from admin panel
            if movie_id in category_overrides:
                overrides = category_overrides[movie_id]
                for key, val in overrides.items():
                    if key in categories:
                        categories[key] = val
                        categories['auto_categorized'] = False
                # Sync tier field for backward compatibility
                if categories.get('is_big_time'):
                    categories['tier'] = 'big_time'
                elif categories.get('is_indie'):
                    categories['tier'] = 'indie'
                elif 'is_big_time' in overrides or 'is_indie' in overrides:
                    categories['tier'] = None

            # Set 'featured' field for backwards compatibility (true or false)
            movie['featured'] = categories['is_staff_pick']

            # Count for stats
            if categories.get('is_big_time'):
                big_time_count += 1
            if categories.get('is_indie'):
                indie_count += 1
            if not categories.get('is_big_time') and not categories.get('is_indie'):
                uncategorized_count += 1
            if categories['is_foreign']:
                foreign_count += 1
            if categories['is_restoration']:
                restoration_count += 1
            if categories['is_virtual_screening']:
                virtual_screening_count += 1
            if categories.get('is_documentary'):
                documentary_count += 1

        # Apply editorial ordering if specified
        if ordering:
            ordered_movies = []

            # Create a map of movie ID to movie object for quick lookup
            movie_map = {str(movie['id']): movie for movie in display_movies}

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
            display_movies = ordered_movies + remaining_movies

        staff_pick_count = len([m for m in display_movies if m.get('categories', {}).get('is_staff_pick')])
        ordered_count = len(ordering) if ordering else 0

        print(f"📝 Admin overrides applied:")
        print(f"  Categories: {big_time_count} Big Time, {indie_count} Indie, {uncategorized_count} Uncategorized, {foreign_count} Foreign, {restoration_count} Restorations, {virtual_screening_count} Virtual Screenings, {documentary_count} Documentaries")
        print(f"  Staff Picks: {staff_pick_count}")
        if ordered_count > 0:
            print(f"  Editorial ordering: {ordered_count} movies pinned to top")

        return display_movies, staff_picks

