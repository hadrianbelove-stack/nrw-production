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

from constants import PLACEHOLDER_ASINS, get_scraper_config, MAX_ENRICHMENT_BATCH, ENRICHMENT_LOOP_TIMEOUT_MINUTES
try:
    from streaming_platform_scraper import StreamingPlatformScraper
except ImportError:
    StreamingPlatformScraper = None

# Watch link discovery: JustWatch API (primary) + Playwright scrapers (fallback)


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

        # Watch link discovery via JustWatch API (primary) + scrapers (fallback)
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
            'justwatch_successes': 0
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
                    'duplicates_skipped': self.intake_stats['duplicates_skipped']
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
        import requests
        from datetime import datetime, timedelta

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
                    details_resp = requests.get(details_url, params={'api_key': self.tmdb_key}, timeout=15)
                    details = details_resp.json()
                except Exception as e:
                    self.logger.warning(f"Failed to get details for {series.get('name')}: {e}")
                    continue

                # Verify it's actually a miniseries
                if details.get('type') != 'Miniseries':
                    if debug:
                        print(f"   ⏭️  Not a miniseries (type={details.get('type')}): {series.get('name')}")
                    continue

                # Get watch providers
                providers_url = f"https://api.themoviedb.org/3/tv/{series['id']}/watch/providers"
                try:
                    prov_resp = requests.get(providers_url, params={'api_key': self.tmdb_key}, timeout=15)
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
                    'status': 'available' if us_providers else 'tracking',
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

                # Check providers with retry logic (use /tv/ endpoint for miniseries)
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

                    # Check if ANY providers exist (after filtering out excluded services)
                    has_providers = bool(rent_names or buy_names or stream_names)

                    # Always update has_providers flag based on current provider availability
                    movie['has_providers'] = has_providers

                    # Pre-order detection: buy-only + single provider = check Amazon
                    is_buy_only = bool(buy_names) and not rent_names and not stream_names
                    if is_buy_only and len(buy_names) == 1 and has_providers and movie['status'] == 'tracking':
                        # Check Amazon product page for "Pre-order" vs "Buy" button
                        amazon_status = None
                        try:
                            if not hasattr(self, '_amazon_detector'):
                                from amazon_preorder_detector import AmazonPreorderDetector
                                self._amazon_detector = AmazonPreorderDetector()
                            amazon_status = self._amazon_detector.check_preorder(movie['title'], movie.get('year'))
                        except Exception as e:
                            self.logger.warning(f"Amazon pre-order check failed for {movie['title']}: {e}")

                        if amazon_status == 'pre-order':
                            # Confirmed pre-order — track it but don't add to site yet
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
                            # Skip normal discovery — don't set digital_date, don't add to data.json
                            has_providers = False
                        else:
                            # Amazon says "Buy"/"Rent" or check failed — proceed normally
                            if amazon_status == 'available':
                                print(f"  ~ {movie['title']} buy-only ({buy_names[0]}) confirmed available on Amazon")
                            # has_providers stays True, normal discovery proceeds below

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

                    # Catch-up logic removed: Only enrich brand new transitions
                    # Movies get ONE enrichment attempt on the day they transition to available

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

                    # Extract year from release_date
                    release_date = movie.get('release_date', '')
                    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

                    intaked_movies[movie_id] = {
                        'title': movie.get('title', 'Unknown'),
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

    def get_tv_details(self, tv_id):
        """Get full TV series details from TMDB (for miniseries/limited series)"""
        url = f"https://api.themoviedb.org/3/tv/{tv_id}"
        params = {
            'api_key': self.tmdb_key,
            'append_to_response': 'credits,videos,external_ids'
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
            # Load current data.json - APPEND-ONLY: never wipe existing movies
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

        # 5. Try scraping YouTube for the trailer (Gemini-first with Playwright fallback)
        if self.trailer_finder is None:
            # Check enrichment flag first
            if not self.enrichment_enabled:
                self.logger.debug("YouTube trailer finder disabled - enrichment not enabled")
                return None

            # Check config kill switch for YouTube Gemini
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

        # Check if this is a cache hit first
        cache_key = f"{title}_{year}"
        is_cache_hit = cache_key in self.trailer_finder.cache if hasattr(self.trailer_finder, 'cache') else False

        # Track trailer scraper usage
        self.enrichment_stats['trailer_attempts'] += 1
        if is_cache_hit:
            self.enrichment_stats['trailer_cache_hits'] += 1

        # Pass director/cast context for better Gemini accuracy
        director = movie_details.get('crew', {}).get('director') if movie_details else None
        cast_list = movie_details.get('crew', {}).get('cast', []) if movie_details else []
        cast = cast_list[:3] if cast_list else None

        # Call with context if Gemini available and method supports it
        if GEMINI_AVAILABLE:
            scraped_url = self.trailer_finder.find_trailer(title, year, director=director, cast=cast)
        else:
            scraped_url = self.trailer_finder.find_trailer(title, year)

        if scraped_url:
            self.enrichment_stats['trailer_successes'] += 1
            return scraped_url

        # 6. Final fallback: generate YouTube search URL
        search_query = quote(f"{title} {year} trailer")
        return f"https://www.youtube.com/results?search_query={search_query}"
    

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

            hosted_url = download_and_upload_trailer(movie_id, title, year, youtube_url, bucket, config_url)
            if hosted_url:
                self.logger.info(f"Trailer hosted: {title} ({year}) -> {hosted_url}")
            return hosted_url
        except BaseException as e:
            # BaseException catches SystemExit from trailer_uploader's sys.exit(1)
            # which would otherwise kill the entire enrichment process
            self.logger.warning(f"Trailer hosting failed for {title}: {type(e).__name__}: {str(e)[:100]}")
            return None

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
            rt_director = movie_details.get('crew', {}).get('director') if movie_details else None
            rt_lang = movie_details.get('original_language') if movie_details else None
            rt_orig_title = movie_details.get('original_title') if movie_details else None
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

        # Watch links (isolated failure handling)
        try:
            watch_links_raw = self.enrichment.get_watch_links(movie_id, title, year, movie_data.get('providers', {}), force_refresh, tracking_data=movie_data)

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
    
    def enrich_newly_available_movies(self) -> int:
        """
        Enrich movies listed in metrics/newly_available.json.

        This is Phase 3 of the pipeline: overlay enrichment metadata onto
        movies that were added to data.json during discovery (Phase 2).

        Returns:
            int: Number of movies successfully enriched
        """
        print("🎨 Starting enrichment phase...")

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

        # Find movies to enrich from newly_available.json
        newly_available_file = 'metrics/newly_available.json'
        if not os.path.exists(newly_available_file):
            print(f"❌ No {newly_available_file} found - no movies to enrich")
            return 0

        try:
            with open(newly_available_file, 'r') as f:
                newly_available = json.load(f)
            movie_ids_to_enrich = newly_available.get('movie_ids', [])
            state_date = newly_available.get('date', 'unknown')

            # Validate the state file has today's date - warn if stale
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            if state_date != today:
                print(f"⚠️ State file date ({state_date}) is not today ({today}) - may be stale")

        except Exception as e:
            print(f"❌ Error loading {newly_available_file}: {e}")
            return 0

        if not movie_ids_to_enrich:
            print("✅ No new movies to enrich")
            return 0

        print(f"🎯 Found {len(movie_ids_to_enrich)} movies to enrich")

        # Load tracking database for movie details
        tracking_data = self.storage.load_all_movies()
        if not tracking_data:
            print("❌ Could not load movie tracking database")
            return 0

        enriched_count = 0
        for movie_id in movie_ids_to_enrich:
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
                # Get full movie details from TMDB
                movie_details = self.get_movie_details(movie_id)
                if not movie_details:
                    print(f"  ✗ Could not fetch details for {movie_data.get('title', movie_id)}")
                    continue

                # Get enrichment fields only
                enrichment_fields = self.get_enrichment_only_fields(movie_id, movie_data, movie_details, force_refresh=False)
                if enrichment_fields:
                    # Update the movie in place with enriched fields
                    existing_movies[movie_index].update(enrichment_fields)
                    # Mark enrichment status as completed
                    existing_movies[movie_index]['_enrichment_status'] = 'completed'

                    # Track enrichment gaps (fields that enrichment couldn't resolve)
                    gaps = []
                    if not enrichment_fields.get('watch_links'):
                        gaps.append('watch_links')
                    if enrichment_fields.get('links', {}).get('rt') is None and enrichment_fields.get('rt_score') is None:
                        gaps.append('rt_score')
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

        # Save enrichment results to data.json BEFORE trailer hosting
        # (trailer hosting can crash and must not prevent saving enrichment data)
        display_data['movies'] = existing_movies
        display_data['generated_at'] = datetime.now().isoformat()
        display_data['count'] = len(existing_movies)

        try:
            backup_path = f"data.json.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            import shutil
            if os.path.exists('data.json'):
                shutil.copy2('data.json', backup_path)

            with open('data.json', 'w') as f:
                json.dump(display_data, f, indent=2)
            print(f"✅ Enriched {enriched_count}/{len(movie_ids_to_enrich)} movies")
        except Exception as e:
            print(f"❌ Error saving enriched data.json: {e}")
            return 0

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
                # Re-save with trailer_hosted URLs added
                with open('data.json', 'w') as f:
                    json.dump(display_data, f, indent=2)
                print(f"  ✓ Hosted {hosted_count} trailer(s)")
            else:
                print("  No new trailers to host")
        else:
            print("🎬 Trailer hosting: disabled (config)")

        return enriched_count

    def check_festival_expirations(self):
        """
        Check festival screening links for expiration.
        Dead links (404/410) cause the movie to be hidden and returned to tracking.
        """
        import requests
        from datetime import datetime

        data_file = 'data.json'
        if not os.path.exists(data_file):
            print("  No data.json found")
            return

        with open(data_file, 'r') as f:
            data = json.load(f)

        movies = data.get('movies', [])
        festival_movies = [m for m in movies if m.get('categories', {}).get('is_festival')]

        if not festival_movies:
            print("  No festival movies found")
            return

        print(f"  Checking {len(festival_movies)} festival movies...")
        active_count = 0
        expired_count = 0
        today_str = datetime.now().strftime('%Y-%m-%d')
        modified = False

        # Load tracking database for status reset
        tracking_path = 'movie_tracking.json'
        tracking_data = {}
        if os.path.exists(tracking_path):
            with open(tracking_path, 'r') as f:
                tracking_data = json.load(f)

        for movie in festival_movies:
            title = movie.get('title', 'Unknown')
            festival_info = movie.get('festival_info', {})

            # Skip already-expired movies
            if festival_info.get('status') == 'expired':
                continue

            # Find the festival link to check
            festival_link = None
            watch_links = movie.get('watch_links', {})
            vod = watch_links.get('vod')
            if isinstance(vod, list):
                for v in vod:
                    svc = v.get('service', '').lower()
                    link = v.get('link', '') or ''
                    if svc == 'eventive' or 'eventive.org' in link or 'festivalplayer' in link or 'shift72.com' in link:
                        festival_link = link
                        break
            elif isinstance(vod, dict):
                link = vod.get('link', '') or ''
                svc = vod.get('service', '').lower()
                if svc == 'eventive' or 'eventive.org' in link or 'festivalplayer' in link or 'shift72.com' in link:
                    festival_link = link

            if not festival_link:
                continue

            # HTTP HEAD check
            try:
                resp = requests.head(festival_link, timeout=10, allow_redirects=True)
                if resp.status_code in (404, 410, 403):
                    # Link is dead — festival screening has ended
                    expired_count += 1
                    festival_info['status'] = 'expired'
                    festival_info['last_checked'] = today_str
                    movie['festival_info'] = festival_info
                    movie['hidden'] = True
                    modified = True
                    slug = festival_info.get('festival_slug', '?')
                    print(f"  ❌ Expired: {title} ({slug}) — HTTP {resp.status_code}")

                    # Reset movie in tracking for re-discovery of normal VOD
                    movie_id = str(movie.get('id', ''))
                    if movie_id and movie_id in tracking_data.get('movies', {}):
                        tracking_movie = tracking_data['movies'][movie_id]
                        tracking_movie['status'] = 'tracking'
                        if 'digital_date' in tracking_movie:
                            del tracking_movie['digital_date']
                        print(f"    → Returned to tracking for VOD re-discovery")
                else:
                    # Link is still alive
                    active_count += 1
                    festival_info['last_checked'] = today_str
                    movie['festival_info'] = festival_info
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
        Re-enrich movies that have Amazon/Apple providers but empty watch_links.
        Uses force_refresh=True to bypass cache and retry JustWatch.

        Returns:
            int: Number of movies successfully re-enriched with watch links
        """
        if not os.path.exists('data.json'):
            print("❌ No data.json found")
            return 0

        with open('data.json', 'r') as f:
            display_data = json.load(f)

        existing_movies = display_data.get('movies', [])

        # Find movies with Amazon/Apple providers but no watch_links.vod
        amazon_apple_variants = ['amazon', 'prime video', 'apple tv', 'apple itunes', 'itunes']
        gap_movies = []

        for i, movie in enumerate(existing_movies):
            providers = movie.get('providers', {})
            watch_links = movie.get('watch_links', {})
            rent_buy = providers.get('rent', []) + providers.get('buy', [])
            relevant = [p for p in rent_buy if any(v in p.lower() for v in amazon_apple_variants)]

            vod = watch_links.get('vod')
            has_vod = (isinstance(vod, list) and any(isinstance(v, dict) and v.get('link') for v in vod)) or \
                      (isinstance(vod, dict) and bool(vod.get('link')))
            if relevant and not has_vod:
                gap_movies.append((i, movie))

        if not gap_movies:
            print("✅ No watch link gaps found — all Amazon/Apple providers have links")
            return 0

        print(f"🔍 Found {len(gap_movies)} movies with watch link gaps:")
        for _, movie in gap_movies:
            providers = movie.get('providers', {})
            rent_buy = providers.get('rent', []) + providers.get('buy', [])
            print(f"  • {movie.get('title')} ({', '.join(rent_buy)})")

        # Load tracking database for enrichment
        tracking_data = self.storage.load_all_movies()
        if not tracking_data:
            print("❌ Could not load movie tracking database")
            return 0

        fixed_count = 0
        for movie_index, movie in gap_movies:
            movie_id = str(movie.get('id', ''))
            title = movie.get('title', 'Unknown')

            try:
                movie_details = self.get_movie_details(movie_id)
                if not movie_details:
                    print(f"  ✗ Could not fetch TMDB details for {title}")
                    continue

                # Get tracking data for this movie (needed for manual_watch_links check)
                tracking_movie = tracking_data.get('movies', {}).get(movie_id, movie)

                enrichment_fields = self.get_enrichment_only_fields(
                    movie_id, tracking_movie, movie_details, force_refresh=True
                )

                if enrichment_fields and enrichment_fields.get('watch_links'):
                    existing_movies[movie_index].update(enrichment_fields)
                    existing_movies[movie_index]['_enrichment_status'] = 'completed'
                    # Clear gap tracking if watch_links resolved
                    existing_gaps = existing_movies[movie_index].get('_enrichment_gaps', [])
                    if 'watch_links' in existing_gaps:
                        existing_gaps.remove('watch_links')
                        if existing_gaps:
                            existing_movies[movie_index]['_enrichment_gaps'] = existing_gaps
                        else:
                            existing_movies[movie_index].pop('_enrichment_gaps', None)
                    print(f"  ✓ {title} — watch links resolved")
                    fixed_count += 1
                else:
                    print(f"  ○ {title} — still no links (may need manual override)")
            except Exception as e:
                print(f"  ✗ Error re-enriching {title}: {e}")
                continue

        # Save if anything changed
        if fixed_count > 0:
            display_data['movies'] = existing_movies
            display_data['generated_at'] = datetime.now().isoformat()

            try:
                import shutil
                backup_path = f"data.json.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                if os.path.exists('data.json'):
                    shutil.copy2('data.json', backup_path)
                with open('data.json', 'w') as f:
                    json.dump(display_data, f, indent=2)
                print(f"✅ Re-enriched {fixed_count}/{len(gap_movies)} movies with watch links")
            except Exception as e:
                print(f"❌ Error saving data.json: {e}")
                return 0

        return fixed_count

    def generate_display_data(self, days_back=90, incremental=True, force_refresh=False):
        """
        PHASE 4: Apply admin overrides and prepare final display data.

        Loads data.json, applies admin overrides (hide/featured/ordering),
        and saves the result. APPEND-ONLY: never removes movies.

        Args:
            days_back: Used for stats only (frontend handles date filtering)
            incremental: Deprecated (kept for compatibility)
            force_refresh: Deprecated (kept for compatibility)
        """
        # Try to fix schema issues first (adds missing keys, never removes movies)
        if os.path.exists('data.json'):
            self.validator.fix_data_json_schema('data.json')

        # APPEND-ONLY: Load ALL movies from data.json - never filter out old movies
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

        # Apply admin overrides to ALL movies (not just recent ones)
        print(f"🔧 Applying admin overrides to {len(all_movies)} movies...")

        # Sort by digital release date (newest first)
        # Handle None values by treating them as empty strings
        all_movies.sort(key=lambda x: x.get('digital_date') or '', reverse=True)

        # Apply admin panel overrides (categorize movies, apply staff picks, ordering)
        display_movies, staff_pick_ids = self.apply_admin_overrides(all_movies)

        # Save ALL movies back to data.json (APPEND-ONLY: never remove old movies)
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

        # Enrichment statistics (JustWatch API is primary source)
        total_calls = self.enrichment_stats['search_calls'] + self.enrichment_stats['source_calls']
        cache_hit_rate = (self.enrichment_stats['cache_hits'] / (self.enrichment_stats['cache_hits'] + total_calls) * 100) if (self.enrichment_stats['cache_hits'] + total_calls) > 0 else 0

        print(f"\n📊 Watch Links Enrichment:")
        print(f"  Cache hits: {self.enrichment_stats['cache_hits']}")
        print(f"  Cache hit rate: {cache_hit_rate:.1f}%")
        justwatch_successes = self.enrichment_stats.get('justwatch_successes', 0)
        print(f"  JustWatch successes: {justwatch_successes}")

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

            # Compare with JustWatch API success rate
            if success_rate > 0:
                comparison = "higher" if platform_success_rate > success_rate else "lower"
                print(f"  Success rate vs JustWatch API: {platform_success_rate:.1f}% ({comparison} than {success_rate:.1f}%)")
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

            # JustWatch API (primary source for watch links)
            # Note: JustWatch replaced Watchmode API in Dec 2024

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
        Categorize a movie as 'big_time' or 'niche' based on studio and budget.

        Logic:
        1. Check manual override first (admin can force tier)
        2. Match studio against big_time_studios list
        3. Fallback to budget threshold ($10M default)
        4. Default to 'niche' if no match

        Returns:
            dict: Categories object with tier, is_foreign, is_staff_pick, auto_categorized, manual_override
        """
        big_time_studios = category_config.get('big_time_studios', [])
        budget_threshold = category_config.get('budget_threshold', 10000000)

        # Get movie properties
        studio = movie.get('studio', '')
        budget = movie.get('budget', 0) or 0  # Handle None
        original_language = movie.get('original_language', 'en')

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
            tier = 'niche'
            auto_categorized = True

        # Determine foreign status
        is_foreign = original_language and original_language != 'en'

        return {
            'tier': tier,
            'is_foreign': is_foreign,
            'is_staff_pick': False,  # Set later from staff_picks.json
            'is_restoration': False,  # Set later from restoration detection
            'is_festival': False,  # Set later from watch_links detection
            'is_series': False,  # Set later from content_type detection
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

        # Load festival name mapping from config
        festival_names_map = self.config.get('festival_names', {})

        # Apply categorization to all movies
        big_time_count = 0
        niche_count = 0
        foreign_count = 0
        restoration_count = 0
        festival_count = 0
        festival_services = ['eventive']
        festival_url_patterns = ['eventive.org', 'festivalplayer.sundance.org', 'shift72.com', 'xerb.tv', 'festivalscope.com']

        def _check_festival_vod(entry):
            """Check if a single vod entry is from a festival platform."""
            svc = entry.get('service', '').lower()
            link = entry.get('link', '') or ''
            if svc in festival_services:
                return True
            for pattern in festival_url_patterns:
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

            # Mark festival screenings (Eventive and similar platforms)
            is_festival = False
            watch_links = movie.get('watch_links', {})
            vod = watch_links.get('vod')
            festival_link = None
            festival_service = None

            if isinstance(vod, list):
                for v in vod:
                    if _check_festival_vod(v):
                        is_festival = True
                        festival_link = v.get('link', '')
                        festival_service = v.get('service', '')
                        break
            elif isinstance(vod, dict):
                if _check_festival_vod(vod):
                    is_festival = True
                    festival_link = vod.get('link', '')
                    festival_service = vod.get('service', '')

            categories['is_festival'] = is_festival

            # Populate festival_info metadata for expiration tracking
            if is_festival:
                existing_festival_info = movie.get('festival_info', {})

                # Extract festival slug from URL (pattern: watch.eventive.org/{slug}/play/{id})
                festival_slug = ''
                if festival_link:
                    if 'eventive.org/' in festival_link:
                        try:
                            slug_part = festival_link.split('eventive.org/')[1].split('/')[0]
                            if slug_part:
                                festival_slug = slug_part
                        except (IndexError, AttributeError):
                            pass
                    elif 'festivalplayer.sundance.org' in festival_link:
                        festival_slug = 'sundance'

                # Look up festival name from config mapping
                festival_name = festival_names_map.get(festival_slug, '')
                if not festival_name and festival_slug:
                    # Fallback: title-case the slug
                    festival_name = festival_slug.replace('_', ' ').replace('-', ' ').title()
                    print(f"  ⚠️  Unknown festival slug '{festival_slug}' for {movie.get('title', 'Unknown')} — add to config.yaml festival_names")

                today_str = datetime.now().strftime('%Y-%m-%d')
                movie['festival_info'] = {
                    'platform': festival_service or 'Unknown',
                    'festival_slug': festival_slug,
                    'festival_name': festival_name,
                    'discovered': existing_festival_info.get('discovered', today_str),
                    'last_checked': existing_festival_info.get('last_checked', today_str),
                    'status': existing_festival_info.get('status', 'active')
                }

            # Mark limited series
            categories['is_series'] = movie.get('content_type') == 'limited_series'

            movie['categories'] = categories

            # Set 'featured' field for backwards compatibility (true or false)
            movie['featured'] = categories['is_staff_pick']

            # Count for stats
            if categories['tier'] == 'big_time':
                big_time_count += 1
            else:
                niche_count += 1
            if categories['is_foreign']:
                foreign_count += 1
            if categories['is_restoration']:
                restoration_count += 1
            if categories['is_festival']:
                festival_count += 1

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
        print(f"  Categories: {big_time_count} Big Time, {niche_count} Niche, {foreign_count} Foreign, {restoration_count} Restorations, {festival_count} Festivals")
        print(f"  Staff Picks: {staff_pick_count}")
        if ordered_count > 0:
            print(f"  Editorial ordering: {ordered_count} movies pinned to top")

        return display_movies, staff_picks

