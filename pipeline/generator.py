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
import random
import requests
import yaml
from datetime import date, datetime, timedelta, timezone
import time
import re
from urllib.parse import quote
import logging
import signal
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

from constants import PLACEHOLDER_ASINS, get_scraper_config, MAX_ENRICHMENT_BATCH, ENRICHMENT_LOOP_TIMEOUT_MINUTES, MAX_ENRICHMENT_ATTEMPTS, RETRY_BACKOFF_DAYS
from pipeline.context import PipelineContext
from pipeline.intake import MovieIntake
from pipeline.discoverer import ProviderDiscoverer
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
            'mc_attempts': 0,
            'mc_successes': 0,
            'mc_cache_hits': 0,
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
        self.metacritic_scraper = None  # Lazy initialization for Metacritic API scraping
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

        # Intake statistics
        self.intake_stats = {
            'pages_fetched': 0,
            'total_results': 0,
            'new_movies_added': 0,
            'duplicates_skipped': 0,
            'api_calls': 0,
            'debug_enabled': False
        }

        # Shared context for extracted modules
        self._ctx = PipelineContext(
            config=self.config,
            logger=self.logger,
            storage=self.storage,
            enrichment_service=self.enrichment,
            tmdb_key=self.tmdb_key,
            intake_stats=self.intake_stats,
        )

        # Extracted modules
        self._intake = MovieIntake(self._ctx)
        self._discoverer = ProviderDiscoverer(self._ctx, host=self)

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

    # ------------------------------------------------------------------
    # Intake delegation (implementation in pipeline/intake.py)
    # ------------------------------------------------------------------

    def intake_new_premieres(self, debug=False, since_date=None, bootstrap=False):
        """Intake new movie premieres — delegates to pipeline/intake.py"""
        return self._intake.intake_new_premieres(debug=debug, since_date=since_date, bootstrap=bootstrap)

    def intake_new_miniseries(self, debug=False, days_back=30):
        """Intake new miniseries — delegates to pipeline/intake.py"""
        return self._intake.intake_new_miniseries(debug=debug, days_back=days_back)

    def _transition_movie_to_available(self, movie_id, movie, source, newly_available_ids):
        """Transition a movie from tracking to available status.

        Shared logic for both Type 4 and provider discovery paths.
        Clears all revert/false-positive flags and queues the movie for enrichment.
        """
        movie['has_providers'] = True
        movie['status'] = 'available'
        movie['enriched'] = False
        movie['enrichment_date'] = None
        movie['_discovery_source'] = source
        if 'providers' not in movie or not movie['providers']:
            movie['providers'] = {'rent': [], 'buy': [], 'streaming': []}
        # Clear ALL revert/false-positive flags from any prior state
        for flag in ['_reverted_from_available', '_false_positive_source',
                     '_jw_revert_reason', '_jw_reverted_at', '_jw_reverted',
                     '_type4_false_positive', '_providers_false_positive',
                     '_type4_pending']:
            movie.pop(flag, None)
        newly_available_ids.append(movie_id)
        self.add_movie_to_site_immediately(movie_id, movie)

    def check_tracking_movies(self, max_to_check=None, priority_days=180):
        """Discovery — delegates to pipeline/discoverer.py"""
        return self._discoverer.check_tracking_movies(max_to_check=max_to_check, priority_days=priority_days)
    def run_festival_backfill(self, years=None, debug=False):
        """Festival backfill — delegates to pipeline/intake.py"""
        return self._intake.run_festival_backfill(years=years, debug=debug)

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
                if not self.validator.fix_data_json_schema('data.json'):
                    self.logger.error("data.json schema unfixable — aborting discovery to preserve data")
                    return 0

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
                '_discovery_source': movie_data.get('_discovery_source', 'provider_availability_check'),
                '_enrichment_status': 'pending'
            })

            # Copy pre-order flag if set (Type 4 pending movies surfaced on wall)
            if movie_data.get('_is_preorder'):
                basic_entry['_is_preorder'] = True

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
                    for dm in disk_movies:
                        dm_id = str(dm.get('id', ''))
                        if dm_id and dm_id not in in_memory_ids:
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
            'pre_order_links': movie_data.get('pre_order_links', []),
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
            'pre_order_links': movie_data.get('pre_order_links', []),
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

        # Generate display_title for foreign films
        # Latin-script originals: "Original (English)" — e.g. "Nukkad Naatak (A Street Play)"
        # Non-Latin originals: "English (Original)" — e.g. "The Adventure (奇遇)"
        import re
        original_title = entry.get('original_title')
        orig_lang = entry.get('original_language', 'en')
        if original_title and original_title != entry.get('title') and orig_lang != 'en':
            _is_latin = bool(re.match(r'^[\u0000-\u024F\u1E00-\u1EFF\s\d\W]+$', original_title))
            if _is_latin:
                entry['display_title'] = f"{original_title} ({entry['title']})"
            else:
                entry['display_title'] = f"{entry['title']} ({original_title})"

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

    def find_wikipedia_url(self, title, year, imdb_id, movie_id=None, director=None, original_title=None, skip_playwright=False):
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
            director: Director name for disambiguation (optional)
            original_title: Original-language title for alternate searching (optional)
            skip_playwright: If True, skip the slow Playwright scraper step (for gap fill)

        Returns:
            Wikipedia URL string or None if not found
        """
        # 1. Check overrides first (manual curator fixes take precedence)
        if imdb_id and imdb_id in self.wikipedia_overrides:
            override_val = self.wikipedia_overrides[imdb_id]
            if override_val is None:
                return None
            return f"https://en.wikipedia.org/wiki/{override_val}"

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
                use_wikidata=True,
                director=director,
                original_title=original_title,
                skip_playwright=skip_playwright
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

    def find_metacritic_score(self, title, year):
        """Find Metacritic URL and score via API."""
        # Check if MC scraper is enabled
        enabled = self.config.get('metacritic_scraper', {}).get('enabled', True)
        if not enabled:
            return None

        # Initialize scraper if needed
        if not self._init_metacritic_scraper():
            return None

        try:
            result = self.metacritic_scraper.scrape_metacritic_score(title, int(year))
            # Sync stats from scraper
            scraper_stats = self.metacritic_scraper.get_stats()
            self.enrichment_stats['mc_attempts'] = scraper_stats['attempts']
            self.enrichment_stats['mc_successes'] = scraper_stats['successes']
            self.enrichment_stats['mc_cache_hits'] = scraper_stats['cache_hits']
            return result
        except Exception as e:
            self.logger.warning(f"Metacritic scraper error for {title}: {e}")
            return None

    def _init_metacritic_scraper(self):
        """Initialize Metacritic API scraper (lazy initialization)."""
        if self.metacritic_scraper is not None:
            return self.metacritic_scraper is not False

        if not self.enrichment_enabled:
            self.logger.debug("Metacritic scraper disabled - enrichment not enabled")
            self.metacritic_scraper = False
            return False

        try:
            from metacritic_scraper import MetacriticScraper
            self.metacritic_scraper = MetacriticScraper(
                cache_file='cache/metacritic_cache.json',
                config=self.config,
                logger=self.logger
            )
            self.logger.info("Metacritic scraper initialized (API-based)")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Metacritic scraper: {e}")
            self.metacritic_scraper = False
            return False

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

            hosted_url, new_trailer_url, _fail_reason = download_and_upload_trailer(movie_id, title, year, youtube_url, bucket, config_url)
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

    def _run_enrichment_source(self, source_name, fn, enrichment_results, title, year):
        """Run a single enrichment source with isolated failure handling.

        Wraps the source function in try/except, logs success/failure/error,
        and returns the result (or None on failure).
        """
        try:
            result = fn()
            if result:
                enrichment_results[source_name] = 'success'
                self.logger.debug(f"{source_name}: Found for {title} ({year})")
            else:
                enrichment_results[source_name] = 'not_found'
                self.logger.debug(f"{source_name}: Not found for {title} ({year})")
            return result
        except Exception as e:
            enrichment_results[source_name] = 'error'
            self.logger.warning(f"{source_name}: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")
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

        # Skip short films that bypassed intake's runtime filter (TMDB had null runtime at intake)
        _runtime = movie_details.get('runtime')
        _min_runtime = self.config.get('intake', {}).get('min_runtime', 60)
        if _runtime and _runtime < _min_runtime:
            self.logger.info(f"Skipping {movie_details.get('title', movie_id)}: runtime {_runtime}min < {_min_runtime}min minimum")
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

        # Wikipedia link
        wiki_director = movie_details.get('crew', {}).get('director') if movie_details else None
        wiki_orig_title = movie_details.get('original_name' if is_tv else 'original_title') if movie_details else None
        wiki_url = self._run_enrichment_source(
            'wikipedia',
            lambda: self.find_wikipedia_url(title, year, imdb_id, movie_id,
                                            director=wiki_director, original_title=wiki_orig_title),
            enrichment_results, title, year)
        if wiki_url:
            result['links']['wikipedia'] = wiki_url

        # Trailer link
        trailer_result = self._run_enrichment_source(
            'trailer', lambda: self.find_trailer_url(movie_details),
            enrichment_results, title, year)
        if trailer_result:
            trailer_url, trailer_source = trailer_result
            result['links']['trailer'] = trailer_url
            result['_trailer_source'] = trailer_source

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
                # Only mark success if we actually got a score value
                if result.get('rt_score'):
                    enrichment_results['rt_score'] = 'success'
                else:
                    enrichment_results['rt_score'] = 'not_found'
                self.logger.debug(f"RT: Found data for {title} ({year}) - Score: {result.get('rt_score', 'None')}")
            else:
                enrichment_results['rt_score'] = 'not_found'
                self.logger.debug(f"RT: No data found for {title} ({year})")
        except Exception as e:
            enrichment_results['rt_score'] = 'error'
            self.logger.warning(f"RT: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # Metacritic score and link
        try:
            mc_data = self.find_metacritic_score(title, year)
            if mc_data:
                if mc_data.get('url'):
                    result['links']['metacritic'] = mc_data['url']
                result['metacritic_score'] = mc_data.get('score')
                if result.get('metacritic_score'):
                    enrichment_results['metacritic_score'] = 'success'
                else:
                    enrichment_results['metacritic_score'] = 'not_found'
                self.logger.debug(f"MC: Found data for {title} ({year}) - Score: {result.get('metacritic_score', 'None')}")
            else:
                enrichment_results['metacritic_score'] = 'not_found'
        except Exception as e:
            enrichment_results['metacritic_score'] = 'error'
            self.logger.warning(f"MC: Error for {title} ({year}): {type(e).__name__}: {str(e)[:100]}")

        # IMDB rating
        imdb_rating = self._run_enrichment_source(
            'imdb_rating', lambda: self.get_imdb_rating(imdb_id, title, year),
            enrichment_results, title, year)
        if imdb_rating:
            result['imdb_rating'] = imdb_rating
        if imdb_id:
            result['links']['imdb'] = f"https://www.imdb.com/title/{imdb_id}/"

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

            enrich_director = result.get('crew', {}).get('director') if result.get('crew') else None
            watch_links_raw = self.enrichment.get_watch_links(
                movie_id, title, year, movie_data.get('providers', {}), force_refresh,
                tracking_data=movie_data,
                original_title=original_title,
                alternative_titles=alt_titles_raw,
                director=enrich_director,
                tmdb_id=str(movie_id).replace('tv_', '')
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
        elif movie_data.get('_added_manually') and movie_data.get('digital_date'):
            # Manually-added movies keep their curator-chosen date
            result['_digital_date_source'] = 'manual_override'
            enrichment_results['digital_date'] = 'skipped_manual'
            self.logger.info(f"Digital Date: Preserved manual date {movie_data['digital_date']} for {title}")
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

    def enrich_newly_available_movies(self, target_id=None) -> int:
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

        # Single-movie mode: skip queue building, enrich just this one
        if target_id:
            target_id = str(target_id)
            if target_id not in movie_lookup:
                print(f"❌ Movie {target_id} not found in data.json - add it first")
                return 0
            movie_ids_to_enrich = [target_id]
            newly_count = 1
            print(f"🎯 Single-movie enrichment: targeting {target_id}")
        else:

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

            # Pre-order link finder: use Gemini with Google Search grounding to find
            # Amazon and Fandango At Home pre-order URLs for movies approaching release.
            _plf_days = self.config.get('preorder', {}).get('link_finder_days', 14)
            _plf_cutoff = (datetime.now() + timedelta(days=_plf_days)).strftime('%Y-%m-%d')
            _plf_candidates = []
            for _m in existing_movies:
                if not _m.get('_is_preorder'):
                    continue
                _dd = _m.get('digital_date', '')
                if not _dd or _dd > _plf_cutoff:
                    continue
                if _m.get('pre_order_links'):
                    continue
                _plf_candidates.append(_m)

            if _plf_candidates:
                print(f"\n  🔍 Pre-order link finder: {len(_plf_candidates)} movies within {_plf_days}d window")
                _plf_found = 0
                try:
                    from google import genai
                    from google.genai import types as genai_types
                    import re as _re_plf

                    _gemini_key = os.environ.get('GEMINI_API_KEY') or self.config.get('gemini_api_key', '')
                    if not _gemini_key:
                        self.logger.warning("Pre-order link finder: no GEMINI_API_KEY, skipping")
                    else:
                        _gclient = genai.Client(api_key=_gemini_key)
                        _gtool = genai_types.Tool(google_search=genai_types.GoogleSearch())
                        _gconfig = genai_types.GenerateContentConfig(tools=[_gtool])

                        _movie_lines = []
                        for _i, _sm in enumerate(_plf_candidates, 1):
                            _sm_title = _sm.get('title', '')
                            _sm_year = _sm.get('year', '')
                            _extra = ''
                            _crew = _sm.get('crew', {})
                            if _crew and _crew.get('director') and _crew['director'] != 'Unknown':
                                _extra = f", directed by {_crew['director']}"
                            _movie_lines.append(f"{_i}. {_sm_title} ({_sm_year}{_extra})")

                        _movies_text = '\n'.join(_movie_lines)
                        _prompt = f'''Find digital pre-order pages for these movies in the United States.

URL FORMATS:
- Amazon Video: amazon.com/dp/[ASIN]
- Fandango At Home: athome.fandango.com/content/browse/details/[slug]/[numeric-id]

RULES:
- Only report URLs from search results. Write NONE if not found.
- Digital video only (NOT DVD/Blu-ray)
- Return the actual URL string, not a redirect or reference link

Movies:
{_movies_text}

Format each as (with blank line between entries):

[number]. [title]
AMAZON: [url or NONE]
FANDANGO: [url or NONE]
PRICE: [price or UNKNOWN]

[number]. [title]
...'''

                        _response = _gclient.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=_prompt,
                            config=_gconfig
                        )
                        _resp_text = _response.text

                        # Parse response: split into per-movie blocks, then extract URLs
                        import requests as _requests_plf

                        def _normalize_url(url):
                            """Add https:// if missing — Gemini often omits the scheme."""
                            if url and not url.startswith('http'):
                                url = 'https://www.' + url if 'amazon.com' in url else 'https://' + url
                            return url

                        def _extract_url(text, keyword):
                            """Extract URL after keyword (e.g. 'AMAZON:') from text block."""
                            _idx = text.find(keyword)
                            if _idx == -1:
                                return None
                            _after = text[_idx + len(keyword):].strip()
                            _tok = _after.split()[0] if _after.split() else ''
                            _tok = _tok.strip('[]()').split('](')[0]
                            return _tok if _tok and _tok != 'NONE' else None

                        # Split response into per-movie blocks using finditer
                        _n = len(_plf_candidates)
                        _nums_alt = '|'.join(str(i) for i in range(1, _n + 1))
                        _hdr_pattern = rf'(?:^|(?<=\D))({_nums_alt})\.\s'
                        _headers = list(_re_plf.finditer(_hdr_pattern, _resp_text))

                        _movie_blocks = {}
                        for _hi, _hm in enumerate(_headers):
                            _midx = int(_hm.group(1)) - 1
                            _start = _hm.end()
                            _end = _headers[_hi + 1].start() if _hi + 1 < len(_headers) else len(_resp_text)
                            _movie_blocks[_midx] = _resp_text[_start:_end]

                        for _midx, _block in _movie_blocks.items():
                            if _midx < 0 or _midx >= _n:
                                continue
                            _sm = _plf_candidates[_midx]
                            _sm_title = _sm.get('title', '')

                            _amz = _extract_url(_block, 'AMAZON:')
                            if _amz and 'amazon.com' in _amz:
                                _amz = _normalize_url(_amz)
                                try:
                                    _hr = _requests_plf.head(_amz, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True, timeout=8)
                                    if _hr.status_code == 200:
                                        if 'pre_order_links' not in _sm:
                                            _sm['pre_order_links'] = []
                                        _sm['pre_order_links'].append({
                                            'service': 'Amazon',
                                            'link': _amz,
                                            'type': 'pre_order'
                                        })
                                        print(f"      ✓ {_sm_title}: Amazon verified")
                                    else:
                                        print(f"      ✗ {_sm_title}: Amazon {_hr.status_code}")
                                except Exception as _e:
                                    print(f"      ✗ {_sm_title}: Amazon error — {_e}")

                            _fan = _extract_url(_block, 'FANDANGO:')
                            if _fan and 'fandango' in _fan:
                                _fan = _normalize_url(_fan)
                                try:
                                    _hr = _requests_plf.head(_fan, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True, timeout=8)
                                    if _hr.status_code == 200:
                                        if 'pre_order_links' not in _sm:
                                            _sm['pre_order_links'] = []
                                        _sm['pre_order_links'].append({
                                            'service': 'Fandango At Home',
                                            'link': _fan,
                                            'type': 'pre_order'
                                        })
                                        print(f"      ✓ {_sm_title}: Fandango verified")
                                    else:
                                        print(f"      ✗ {_sm_title}: Fandango {_hr.status_code}")
                                except Exception as _e:
                                    print(f"      ✗ {_sm_title}: Fandango error — {_e}")

                            _price_raw = _extract_url(_block, 'PRICE:')
                            if _price_raw and _price_raw != 'UNKNOWN' and _sm.get('pre_order_links'):
                                _price_match = _re_plf.search(r'\$\d+\.\d{2}', _price_raw)
                                _price = _price_match.group(0) if _price_match else _price_raw
                                for _pl in _sm['pre_order_links']:
                                    if not _pl.get('price'):
                                        _pl['price'] = _price

                        for _sm in _plf_candidates:
                            if _sm.get('pre_order_links'):
                                _plf_found += 1
                                _sm_title = _sm.get('title', '')
                                _n_links = len(_sm['pre_order_links'])
                                print(f"    🔗 {_sm_title} — {_n_links} pre-order link{'s' if _n_links > 1 else ''}")

                except Exception as _plf_err:
                    self.logger.warning(f"Pre-order link finder error: {_plf_err}")

                if _plf_found:
                    print(f"  🔍 Link finder: {_plf_found}/{len(_plf_candidates)} pre-order movies got links")

            # Catch-up: retry movies with failed/incomplete enrichment
            # NOTE: 'completed' movies with gaps are NOT retried here — cosmetic gaps
            # (RT, Metacritic, Wikipedia, trailer, IMDb) are often legitimately nonexistent.
            # Watch link gaps are handled by the separate reenrich_watch_link_gaps() pass.
            seen_ids = set(movie_ids_to_enrich)
            catchup_ids = []
            catchup_cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            today_catchup = datetime.now().strftime('%Y-%m-%d')
            for movie in existing_movies:
                movie_id = str(movie.get('id', ''))
                if not movie_id or movie_id in seen_ids:
                    continue
                # Pre-order handling in catch-up
                if movie.get('_is_preorder'):
                    # Buy-only pre-orders wait for discovery to find rent/streaming — skip catch-up
                    if movie.get('_buyonly_preorder'):
                        continue
                    dd = movie.get('digital_date', '')
                    if dd > today_catchup:
                        continue  # Future — skip enrichment (link scan handles these)
                    # Date arrived — no longer a pre-order
                    movie.pop('_is_preorder', None)
                    movie.pop('pre_order_links', None)
                    print(f"  🏷️  {movie.get('title')} — pre-order ended (date {dd})")
                    # Fall through to normal catch-up → enrich or revert like any movie
                digital_date = movie.get('digital_date', '')
                status = movie.get('_enrichment_status', '')
                attempts = movie.get('_enrichment_attempts', 0)
                if attempts >= MAX_ENRICHMENT_ATTEMPTS:
                    continue
                # Never attempted — wider 30-day window since these were missed entirely
                if not status and not movie.get('enriched', True):
                    if digital_date >= catchup_cutoff:
                        catchup_ids.append(movie_id)
                # Retry failed/error/timeout/pending — exponential backoff
                elif status in ('pending', 'failed', 'error', 'timeout'):
                    last_attempt = movie.get('_last_enrichment_attempt', '')
                    if not last_attempt:
                        # Legacy movie with no timestamp — retry now
                        catchup_ids.append(movie_id)
                    elif attempts > 0 and attempts - 1 < len(RETRY_BACKOFF_DAYS):
                        wait_days = RETRY_BACKOFF_DAYS[attempts - 1]
                        next_retry = (datetime.strptime(last_attempt, '%Y-%m-%d') + timedelta(days=wait_days)).strftime('%Y-%m-%d')
                        if today_catchup >= next_retry:
                            catchup_ids.append(movie_id)

            movie_ids_to_enrich.extend(catchup_ids)

            # Enforce batch limit — new discoveries take priority over catch-up retries
            new_count = len(movie_ids_to_enrich) - len(catchup_ids)
            if len(movie_ids_to_enrich) > MAX_ENRICHMENT_BATCH:
                dropped = len(movie_ids_to_enrich) - MAX_ENRICHMENT_BATCH
                movie_ids_to_enrich = movie_ids_to_enrich[:MAX_ENRICHMENT_BATCH]
                print(f"  ⚠️ Batch limit: {dropped} catch-up retries deferred (new discoveries prioritized)")

            if not movie_ids_to_enrich:
                print("✅ No movies to enrich (no new arrivals, no catch-up needed)")
                return 0

            catchup_used = len(movie_ids_to_enrich) - new_count
            print(f"🎯 Enrichment queue: {new_count} new + {catchup_used} catch-up = {len(movie_ids_to_enrich)} total")

        # Preload IMDb dataset so first movie isn't penalized
        self._load_imdb_dataset()

        # Load tracking database for movie details
        tracking_data = self.storage.load_all_movies()
        if not tracking_data:
            print("❌ Could not load movie tracking database")
            return 0

        enriched_count = 0
        deferred_details = []  # Track per-movie deferred reasons for metrics

        def _deferred_entry(title, reason, movie_idx=None, tracking_movie=None):
            """Build a deferred-details dict with all available context."""
            entry = {'title': title, 'reason': reason}
            if movie_idx is not None and movie_idx < len(existing_movies):
                m = existing_movies[movie_idx]
                entry['digital_date'] = m.get('digital_date', '')
                entry['discovered_at'] = m.get('_discovered_at', '')
                entry['discovery_source'] = m.get('_discovery_source', '')
            if tracking_movie:
                entry['revert_count'] = tracking_movie.get('_jw_revert_count', 0)
                provs = tracking_movie.get('providers', {})
                flat = []
                for kind in ('streaming', 'rent', 'buy'):
                    flat.extend(provs.get(kind, []))
                entry['tmdb_platforms'] = list(dict.fromkeys(flat))  # dedupe, preserve order
            return entry

        _loop_start = time.time()
        _loop_timeout = ENRICHMENT_LOOP_TIMEOUT_MINUTES * 60

        # Per-movie timeout: prevents a single stalled Playwright scrape from hanging the whole loop.
        # The loop-level timeout (ENRICHMENT_LOOP_TIMEOUT_MINUTES) is checked between movies only,
        # so a hung page.goto() inside one movie would block it from ever firing.
        _PER_MOVIE_TIMEOUT_S = 300  # 5 minutes per movie

        def _per_movie_timeout_handler(signum, frame):
            raise TimeoutError(f"Movie enrichment exceeded {_PER_MOVIE_TIMEOUT_S}s")

        signal.signal(signal.SIGALRM, _per_movie_timeout_handler)

        for movie_id in movie_ids_to_enrich:
            # Safety net: bail out if enrichment has been running too long
            if (time.time() - _loop_start) > _loop_timeout:
                _remaining = len(movie_ids_to_enrich) - movie_ids_to_enrich.index(movie_id)
                print(f"  ⏰ Enrichment loop exceeded {ENRICHMENT_LOOP_TIMEOUT_MINUTES} min — stopping. {_remaining} remaining movies will be retried next run.")
                deferred_details.append(_deferred_entry(f'({_remaining} movies)', 'loop_timeout'))
                break

            movie_id = str(movie_id)  # Ensure consistent string format for lookup
            if movie_id not in movie_lookup:
                print(f"  ⚠️ Movie {movie_id} not found in data.json - skipping")
                deferred_details.append(_deferred_entry(f'ID:{movie_id}', 'not_in_data_json'))
                continue

            if movie_id not in tracking_data.get('movies', {}):
                print(f"  ⚠️ Movie {movie_id} not found in tracking database - skipping")
                deferred_details.append(_deferred_entry(f'ID:{movie_id}', 'not_in_tracking'))
                continue

            movie_data = tracking_data['movies'][movie_id]
            movie_index = movie_lookup[movie_id]

            signal.alarm(_PER_MOVIE_TIMEOUT_S)
            try:
                # Track enrichment attempts and timestamp for backoff scheduling
                existing_movies[movie_index]['_enrichment_attempts'] = \
                    existing_movies[movie_index].get('_enrichment_attempts', 0) + 1
                existing_movies[movie_index]['_last_enrichment_attempt'] = datetime.now().strftime('%Y-%m-%d')

                # Get full movie/TV details from TMDB
                if str(movie_id).startswith('tv_'):
                    numeric_id = str(movie_id).replace('tv_', '')
                    movie_details = self.get_tv_details(numeric_id)
                else:
                    movie_details = self.get_movie_details(movie_id)
                if not movie_details:
                    existing_movies[movie_index]['_enrichment_status'] = 'failed'
                    print(f"  ✗ Could not fetch TMDB details for {movie_data.get('title', movie_id)} — marked failed for retry")
                    deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), 'tmdb_fetch_failed', movie_index, tracking_data['movies'].get(movie_id)))
                    continue

                # JustWatch pre-verification: confirm the movie is on our target platforms
                # BEFORE investing time in full enrichment (RT, Wiki, trailers, etc.).
                # Discovery is binary (any TMDB provider = discovered); this step handles
                # platform filtering. If JustWatch can't confirm valid platforms → revert
                # to tracking with a note for the daily launch report.
                #
                # Manually-added movies and movies with watch link overrides skip JW
                # pre-check entirely — curator decision overrides JustWatch verification.
                _title = existing_movies[movie_index].get('title', movie_data.get('title', ''))
                _year = movie_data.get('year')
                _original_title = existing_movies[movie_index].get('original_title')
                _director = existing_movies[movie_index].get('crew', {}).get('director') if existing_movies[movie_index].get('crew') else None
                _content_type_jw = 'tv' if str(movie_id).startswith('tv_') else 'movie'
                _is_manual = (movie_data.get('_added_manually')
                              or existing_movies[movie_index].get('_added_manually'))
                _has_override = str(movie_id) in self.watch_links_overrides
                _jw_verified = False
                _revert_reason = 'justwatch_error'
                try:
                    if not hasattr(self.enrichment, '_justwatch_client') or self.enrichment._justwatch_client is None:
                        from pipeline.justwatch import JustWatchClient
                        self.enrichment._justwatch_client = JustWatchClient(logger=self.logger)
                    _amazon_tag = self.enrichment._get_amazon_affiliate_tag()
                    _excl_list = self.enrichment.config.get('tracking', {}).get('excluded_services', ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play', 'Shahid VIP', 'Viki', 'Futo'])
                    _jw_result = self.enrichment._justwatch_client.verify_availability(
                        _title, _year, excluded_services=_excl_list,
                        affiliate_tag=_amazon_tag, content_type=_content_type_jw,
                        original_title=_original_title, director=_director,
                        tmdb_id=str(movie_id).replace('tv_', '')
                    )
                    if _jw_result is None:
                        _jw_verified = False
                        _revert_reason = "justwatch_no_match"
                    elif not _jw_result['verified']:
                        _jw_verified = False
                        _revert_reason = "justwatch_no_valid_offers"
                    else:
                        _jw_verified = True
                        _revert_reason = None
                        # Cache pre-verified watch_links so enrichment skips redundant JW search
                        _wl = _jw_result.get('watch_links', {})
                        if _wl:
                            self.enrichment.watch_links_cache[str(movie_id)] = {
                                'links': _wl,
                                'cached_at': datetime.now().isoformat(),
                                'source': 'justwatch_pre_verification'
                            }
                        # Clear revert history — movie now has valid providers
                        tracking_data['movies'][movie_id].pop('_jw_reverted_at', None)
                        tracking_data['movies'][movie_id].pop('_jw_revert_reason', None)
                        tracking_data['movies'][movie_id].pop('_jw_revert_count', None)
                        # Record JW-discovered English title when it differs from ours
                        _jw_title = _jw_result.get('jw_title', '')
                        if _jw_title and _jw_title.lower() != _title.lower():
                            _cur_orig = existing_movies[movie_index].get('original_title', '')
                            if not _cur_orig or _cur_orig.lower() == _title.lower():
                                existing_movies[movie_index]['title'] = _jw_title
                                self.logger.info(f"JustWatch revealed English title for {_title}: '{_jw_title}'")

                        # Pre-order detection: buy-only on JustWatch is a pre-order signal.
                        # Manual overrides apply regardless of buy-only status.
                        _po_overrides = self.config.get('preorder_overrides', {})
                        _po_override = _po_overrides.get(str(movie_id))
                        if _po_override is True:
                            existing_movies[movie_index]['_is_preorder'] = True
                            print(f"  🏷️  {_title} — flagged as pre-order (manual override)")
                        elif _po_override is False:
                            existing_movies[movie_index].pop('_is_preorder', None)
                        elif _jw_result.get('buy_only'):
                            _bo_detect = self._detect_buyonly_preorder(_jw_result, movie_id, _title)

                            if _bo_detect['is_preorder']:
                                existing_movies[movie_index]['_is_preorder'] = True
                                existing_movies[movie_index]['_buyonly_preorder'] = True
                                _jw_links = _jw_result.get('watch_links', {})
                                if _jw_links.get('vod'):
                                    existing_movies[movie_index]['pre_order_links'] = _jw_links['vod']

                                if _bo_detect['preorder_date']:
                                    existing_movies[movie_index]['digital_date'] = _bo_detect['preorder_date']
                                    existing_movies[movie_index]['_digital_date_source'] = 'tmdb_type4'
                                else:
                                    existing_movies[movie_index].pop('digital_date', None)
                                    existing_movies[movie_index].pop('_digital_date_source', None)

                                # Clear cached JW links — pre-orders use pre_order_links, not watch_links
                                self.enrichment.watch_links_cache[str(movie_id)] = {
                                    'links': {'streaming': [], 'vod': []},
                                    'cached_at': datetime.now().isoformat(),
                                    'source': 'buyonly_preorder_empty'
                                }

                                # Soft revert tracking — stay in tracking for continued polling
                                tracking_data['movies'][movie_id]['status'] = 'tracking'
                                tracking_data['movies'][movie_id]['_buyonly_preorder'] = True
                                tracking_data['movies'][movie_id].pop('digital_date', None)
                                tracking_changed = True

                                _bo_dd = f", date: {_bo_detect['preorder_date']}" if _bo_detect['preorder_date'] else ", no date"
                                print(f"  🏷️  {_title} — pre-order (buy-only{_bo_dd}) → tracking + wall")
                            else:
                                # Genuine buy-only release confirmed by page check
                                existing_movies[movie_index]['_buyonly_verified'] = True
                                if _bo_detect['type4_date']:
                                    existing_movies[movie_index]['digital_date'] = _bo_detect['type4_date']
                                    existing_movies[movie_index]['_digital_date_source'] = 'tmdb_type4'
                        else:
                            # Not buy-only anymore — clear pre-order flag if previously set
                            # BUT only if digital_date has passed (future-dated = still a pre-order)
                            if existing_movies[movie_index].get('_is_preorder'):
                                dd = existing_movies[movie_index].get('digital_date', '')
                                today_str = datetime.now().strftime('%Y-%m-%d')
                                if dd <= today_str:
                                    existing_movies[movie_index].pop('_is_preorder', None)
                                    print(f"  🏷️  {_title} — pre-order flag cleared (date passed, no longer buy-only)")
                                else:
                                    print(f"  🏷️  {_title} — keeping pre-order (date {dd} still future despite JW not buy-only)")

                except Exception as _jw_err:
                    self.logger.warning(f"JustWatch pre-check error for {_title}: {_jw_err} — proceeding with enrichment")

                if not _jw_verified and not _is_manual and not _has_override:
                    _today_iso = datetime.now().strftime('%Y-%m-%d')
                    tracking_data['movies'][movie_id]['status'] = 'tracking'
                    tracking_data['movies'][movie_id]['_jw_revert_reason'] = _revert_reason
                    tracking_data['movies'][movie_id].setdefault('_jw_reverted_at', _today_iso)
                    _revert_count = tracking_data['movies'][movie_id].get('_jw_revert_count', 0) + 1
                    tracking_data['movies'][movie_id]['_jw_revert_count'] = _revert_count
                    existing_movies[movie_index]['_jw_reverted'] = True
                    existing_movies[movie_index]['_jw_revert_reason'] = _revert_reason
                    existing_movies[movie_index]['_enrichment_status'] = 'reverted'
                    existing_movies[movie_index]['status'] = 'tracking'
                    tracking_changed = True
                    if _revert_count == 1:
                        print(f"  🔄 {_title} — JustWatch pre-check: {_revert_reason} → reverted to tracking")
                    deferred_details.append(_deferred_entry(_title, f'jw_revert:{_revert_reason}', movie_index, tracking_data['movies'].get(movie_id)))
                    signal.alarm(0)
                    continue
                elif not _jw_verified:
                    _skip_reason = 'manual add' if _is_manual else 'watch link override'
                    print(f"  ⏭️  {_title} — JW pre-check failed but skipping revert ({_skip_reason})")

                # Propagate _added_manually from data.json entry to movie_data so
                # get_enrichment_only_fields can see it (tracking save may lose the flag)
                if existing_movies[movie_index].get('_added_manually'):
                    movie_data['_added_manually'] = True

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
                    # Merge guard: don't overwrite existing non-None values with None
                    # (prevents retry from regressing data found on a previous attempt)
                    for _ek, _ev in enrichment_fields.items():
                        if _ev is None and existing_movies[movie_index].get(_ek) is not None:
                            continue
                        existing_movies[movie_index][_ek] = _ev
                    # Buy-only pre-orders: enrichment fetched watch_links before the
                    # buy-only detection cleared the cache — wipe them so the site
                    # shows pre_order_links instead of regular VOD buttons.
                    if existing_movies[movie_index].get('_buyonly_preorder'):
                        existing_movies[movie_index]['watch_links'] = {}

                    # Mark enrichment status as completed
                    existing_movies[movie_index]['_enrichment_status'] = 'completed'
                    # Ensure status is available (may be stale 'tracking' from a prior revert)
                    existing_movies[movie_index]['status'] = 'available'
                    existing_movies[movie_index].pop('_jw_reverted', None)
                    existing_movies[movie_index].pop('_jw_revert_reason', None)

                    # Track enrichment gaps (all meaningful fields, not just watch_links/rt)
                    gaps = []
                    # Check for actual watch link content, not just dict truthiness
                    # (get_watch_links returns {"streaming": [], "vod": []} when empty)
                    wl = enrichment_fields.get('watch_links', {})
                    has_real_links = any(
                        (isinstance(v, list) and len(v) > 0) or (isinstance(v, dict) and v.get('link'))
                        for v in wl.values()
                    ) if isinstance(wl, dict) else bool(wl)
                    # Clear pre-order flag if movie now has real watch links
                    # BUT only if digital_date has actually passed — future-dated movies
                    # with links are still pre-orders (the links are purchase pre-order URLs)
                    # Buy-only pre-orders never clear here — they wait for discovery to find rent/streaming
                    if has_real_links and existing_movies[movie_index].get('_is_preorder') and not existing_movies[movie_index].get('_buyonly_preorder'):
                        dd = existing_movies[movie_index].get('digital_date', '')
                        today_str = datetime.now().strftime('%Y-%m-%d')
                        if dd <= today_str:
                            existing_movies[movie_index].pop('_is_preorder', None)
                            print(f"  🏷️  {_title} — pre-order flag cleared (date passed, has real links)")
                        else:
                            # Future date — links are pre-order purchase URLs, keep flag
                            existing_movies[movie_index]['pre_order_links'] = wl.get('vod', [])
                            print(f"  🏷️  {_title} — keeping pre-order (date {dd} still future, links stored as pre_order_links)")

                    if not has_real_links:
                        gaps.append('watch_links')
                    if enrichment_fields.get('rt_score') is None:
                        gaps.append('rt_score')
                    if not enrichment_fields.get('links', {}).get('trailer'):
                        gaps.append('trailer')
                    if not enrichment_fields.get('links', {}).get('wikipedia'):
                        gaps.append('wikipedia')
                    if enrichment_fields.get('imdb_rating') is None:
                        gaps.append('imdb_rating')
                    if enrichment_fields.get('metacritic_score') is None:
                        gaps.append('metacritic_score')
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
                    deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), 'enrichment_failed', movie_index, tracking_data['movies'].get(movie_id)))

            except TimeoutError:
                print(f"  ⏰ {movie_data.get('title', movie_id)} timed out after {_PER_MOVIE_TIMEOUT_S}s — will retry next run")
                if movie_index < len(existing_movies):
                    existing_movies[movie_index]['_enrichment_status'] = 'timeout'
                deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), 'timeout', movie_index, tracking_data['movies'].get(movie_id)))
                # Reset Playwright singleton so next movie gets a clean browser
                try:
                    from playwright_manager import PlaywrightManager
                    PlaywrightManager().cleanup()
                    PlaywrightManager._instance = None
                except Exception:
                    pass
                for _attr in ('streaming_scraper', 'rt_scraper', 'vod_scraper', 'trailer_finder'):
                    setattr(self, _attr, None)
            except Exception as e:
                # Mark enrichment status as error but keep movie in data.json
                if movie_index < len(existing_movies):
                    existing_movies[movie_index]['_enrichment_status'] = 'error'
                print(f"  ✗ Error enriching {movie_data.get('title', movie_id)}: {e}")
                deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), f'error:{type(e).__name__}', movie_index, tracking_data['movies'].get(movie_id)))
            finally:
                signal.alarm(0)  # Always cancel the per-movie alarm

        # Sync enriched flag to movie_tracking.json + zero-link revert
        try:
            _enrich_success = 0
            _enrich_reverted = 0
            _reverted_details = []
            tracking_changed = False
            for mid in movie_ids_to_enrich:
                mid = str(mid)
                if mid in movie_lookup:
                    movie = existing_movies[movie_lookup[mid]]
                    if movie.get('_enrichment_status') == 'completed' and mid in tracking_data.get('movies', {}):
                        tracking_data['movies'][mid]['enriched'] = True
                        tracking_data['movies'][mid]['enrichment_date'] = datetime.now().strftime('%Y-%m-%d')
                        tracking_changed = True

                        # Zero watch links after enrichment — revert to tracking
                        # A movie with no links (VOD or streaming) should never be on the wall.
                        wl = movie.get('watch_links', {})
                        wl_count = sum(
                            len(v) if isinstance(v, list) else (1 if isinstance(v, dict) and v.get('service') else 0)
                            for v in wl.values()
                        ) if isinstance(wl, dict) else 0
                        if wl_count == 0 and tracking_data['movies'][mid].get('status') == 'available':
                            _title_zl = movie.get('title', '?')
                            _dd_zl = movie.get('digital_date', '')
                            _today_zl = datetime.now().strftime('%Y-%m-%d')
                            # Guard: pre-orders with future dates (no links expected yet)
                            if movie.get('_is_preorder') and _dd_zl > _today_zl:
                                _enrich_success += 1
                                print(f"  ⏭️  {_title_zl} — zero links but pre-order (future date {_dd_zl}), keeping")
                            # Guard: virtual screenings (own lifecycle)
                            elif movie.get('categories', {}).get('is_virtual_screening'):
                                _enrich_success += 1
                                print(f"  ⏭️  {_title_zl} — zero links but virtual screening, keeping")
                            # Guard: manually-added movies (curator decision)
                            elif movie.get('_added_manually') or tracking_data['movies'][mid].get('_added_manually'):
                                _enrich_success += 1
                                print(f"  ⏭️  {_title_zl} — zero links but manually added, keeping")
                            # Guard: watch link overrides
                            elif str(mid) in self.watch_links_overrides:
                                _enrich_success += 1
                                print(f"  ⏭️  {_title_zl} — zero links but has override, keeping")
                            else:
                                # Revert to tracking — movie will be purged from data.json
                                _zl_revert_count = tracking_data['movies'][mid].get('_jw_revert_count', 0) + 1
                                tracking_data['movies'][mid]['status'] = 'tracking'
                                tracking_data['movies'][mid]['_jw_revert_reason'] = 'zero_watch_links'
                                tracking_data['movies'][mid].setdefault('_jw_reverted_at', _today_zl)
                                tracking_data['movies'][mid]['_jw_revert_count'] = _zl_revert_count
                                tracking_data['movies'][mid]['enriched'] = False
                                tracking_data['movies'][mid].pop('enrichment_date', None)
                                movie['_enrichment_status'] = 'reverted'
                                movie['_jw_revert_reason'] = 'zero_watch_links'
                                movie['status'] = 'tracking'
                                _enrich_reverted += 1
                                _rv_source = movie.get('_discovery_source', 'unknown')
                                _reverted_details.append((_title_zl, _rv_source, _zl_revert_count))
                                print(f"  🔄 {_title_zl} — zero watch links → reverted to tracking (count: {_zl_revert_count})")
                                deferred_details.append(_deferred_entry(_title_zl, 'zero_watch_links', movie_lookup.get(mid), tracking_data['movies'].get(mid)))
                        else:
                            _enrich_success += 1
            _enrich_attempted = _enrich_success + _enrich_reverted
            if tracking_changed:
                self.storage.atomic_write_json(tracking_data, 'movie_tracking.json', backup=True)
                if _enrich_reverted:
                    print(f"📝 Enrichment: {_enrich_attempted} attempted, {_enrich_success} succeeded, {_enrich_reverted} reverted (zero links)")
                    for _rv_title, _rv_source, _rv_count in _reverted_details:
                        _rv_via = 'Type 4' if _rv_source == 'tmdb_type4' else 'providers' if _rv_source == 'provider_availability_check' else _rv_source
                        _rv_suffix = f' (attempt #{_rv_count})' if _rv_count > 1 else ''
                        print(f"   ↳ {_rv_title} — discovered via {_rv_via}, no deeplinks found{_rv_suffix}")
                else:
                    print(f"📝 Enrichment: {_enrich_attempted} movies successfully enriched")
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
                "deferred_details": deferred_details,
                "enrichment_duration_seconds": round(time.time() - _enrich_start, 2),
            }
            with open('metrics/enrichment_run.json', 'w') as f:
                json.dump(enrichment_metrics, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not write enrichment metrics: {e}")

        # Purge reverted/removed movies from the in-memory list and archive them.
        # Must happen BEFORE any subsequent save to prevent the merge-rescue from
        # re-adding purged movies back to disk.
        existing_movies[:] = self.purge_removed_movies(existing_movies) or existing_movies

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
            self.storage.atomic_write_json(data, data_file, backup=True)
            print(f"  💾 Updated data.json")

            # Save tracking data if we reset any movies
            if expired_count > 0 and tracking_data:
                self.storage.atomic_write_json(tracking_data, tracking_path, backup=True)
                print(f"  💾 Updated movie_tracking.json")

        print(f"  📊 Results: {active_count} active, {expired_count} expired")

    def reenrich_watch_link_gaps(self):
        """Re-enrich watch link gaps — delegates to pipeline/discoverer.py"""
        return self._discoverer.reenrich_watch_link_gaps()

    def daily_gap_fill(self):
        """Daily gap fill — delegates to pipeline/discoverer.py"""
        return self._discoverer.daily_gap_fill()


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

    def purge_removed_movies(self, movies_list=None):
        """Remove movies with status='removed' or _enrichment_status='reverted'.

        Handles two cases:
        1. Manually removed movies (status='removed' in movie_tracking.json)
        2. JW-reverted movies (_enrichment_status='reverted') — discovered
           but only available on excluded platforms, shouldn't be on the wall

        When movies_list is provided, filters in-memory and returns the filtered list
        (caller is responsible for saving). When None, reads/writes data.json directly.
        Purged movies are archived to data_archive.json either way.

        Returns:
            Filtered list when movies_list provided, None otherwise.
        """
        # Get manually removed IDs from tracking
        removed_ids = set()
        if os.path.exists('movie_tracking.json'):
            with open('movie_tracking.json', 'r') as f:
                tracking = json.load(f)
            removed_ids = {str(mid) for mid, entry in tracking.get('movies', {}).items()
                           if isinstance(entry, dict) and entry.get('status') == 'removed'}

        if movies_list is not None:
            movies = movies_list
        elif os.path.exists('data.json'):
            with open('data.json', 'r') as f:
                data = json.load(f)
            movies = data.get('movies', [])
        else:
            return movies_list

        keep = []
        to_purge_removed = []
        to_purge_reverted = []
        for m in movies:
            if str(m.get('id')) in removed_ids:
                to_purge_removed.append(m)
            elif m.get('_enrichment_status') == 'reverted':
                to_purge_reverted.append(m)
            else:
                keep.append(m)

        all_purged = to_purge_removed + to_purge_reverted
        if not all_purged:
            return movies_list if movies_list is not None else None

        # Archive purged movies (same pattern as archive_old_movies)
        archive_path = 'data_archive.json'
        archive_movies = []
        if os.path.exists(archive_path):
            try:
                with open(archive_path, 'r') as f:
                    archive_data = json.load(f)
                archive_movies = archive_data.get('movies', [])
            except Exception:
                archive_movies = []

        existing_ids = {str(m.get('id')) for m in archive_movies}
        new_archived = [m for m in all_purged if str(m.get('id')) not in existing_ids]
        archive_movies.extend(new_archived)

        archive_data = {
            'archived_at': datetime.now().isoformat(),
            'count': len(archive_movies),
            'movies': archive_movies
        }
        self.storage.atomic_write_json(archive_data, archive_path, backup=False)

        if to_purge_removed:
            titles = [m.get('title', '?') for m in to_purge_removed]
            print(f"🗑️ Purged {len(to_purge_removed)} manually removed movies → data_archive.json")
            for t in titles:
                print(f"   - {t}")
            self.logger.info(f"Purged {len(to_purge_removed)} removed movies: {titles}")

        if to_purge_reverted:
            titles = [m.get('title', '?') for m in to_purge_reverted]
            print(f"🔄 Purged {len(to_purge_reverted)} JW-reverted movies from wall → data_archive.json")
            for t in titles:
                print(f"   - {t}")
            self.logger.info(f"Purged {len(to_purge_reverted)} reverted movies from wall: {titles}")

        if movies_list is not None:
            return keep
        else:
            data['movies'] = keep
            data['count'] = len(keep)
            self.storage.atomic_write_json(data, 'data.json', backup=False)

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
            if not self.validator.fix_data_json_schema('data.json'):
                self.logger.error("data.json schema unfixable — aborting display generation to preserve data")
                return

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

        # Compute display_title for non-English films
        # Latin-script originals: "Original (English)" — e.g. "Nukkad Naatak (A Street Play)"
        # Non-Latin originals: "English (Original)" — e.g. "The Adventure (奇遇)"
        import re
        for m in all_movies:
            orig = m.get('original_title')
            lang = m.get('original_language', 'en')
            if orig and orig != m.get('title') and lang != 'en':
                _is_latin = bool(re.match(r'^[\u0000-\u024F\u1E00-\u1EFF\s\d\W]+$', orig))
                if _is_latin:
                    m['display_title'] = f"{orig} ({m['title']})"
                else:
                    m['display_title'] = f"{m['title']} ({orig})"
            else:
                m['display_title'] = m.get('title', '')

        # Inject selected pull quotes from cache into movie data
        self._inject_selected_pull_quotes(all_movies)

        # Apply cached watch links to movies with empty watch_links
        self._apply_cached_watch_links(all_movies)

        # Report movies with zero watch links (report-only, no removal)
        zero_link_titles = []
        for m in all_movies:
            wl = m.get('watch_links', {})
            wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
            if wl_count == 0:
                zero_link_titles.append(m.get('title', m.get('id', '?')))
        if zero_link_titles:
            print(f"⚠️  {len(zero_link_titles)} movies have zero watch links (kept on wall):")
            for title in zero_link_titles:
                print(f"   - {title}")
            self.logger.info(f"Zero-watch-link movies on wall: {zero_link_titles}")

        # Apply admin overrides to ALL movies (not just recent ones)
        print(f"🔧 Applying admin overrides to {len(all_movies)} movies...")

        # Sort by digital release date (newest first)
        # Handle None values by treating them as empty strings
        all_movies.sort(key=lambda x: x.get('digital_date') or '', reverse=True)

        # Apply admin panel overrides (categorize movies, apply staff picks, ordering)
        display_movies, staff_pick_ids = self.apply_admin_overrides(all_movies)

        # Purge reverted/removed movies BEFORE saving — prevents merge-rescue from
        # re-adding purged movies that are still in the in-memory list.
        display_movies = self.purge_removed_movies(display_movies) or display_movies

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

        # Cleanup Gemini watch link finder if initialized
        if hasattr(self.enrichment, '_gemini_watch_link_finder') and self.enrichment._gemini_watch_link_finder and self.enrichment._gemini_watch_link_finder is not False:
            try:
                self.enrichment._gemini_watch_link_finder._save_cache()
                self.logger.debug("Gemini watch link finder cache saved")
            except Exception as e:
                self.logger.warning(f"Failed to save Gemini watch link finder cache: {e}")

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

        print(f"\n📊 Metacritic Scraper Usage:")
        print(f"  MC attempts: {self.enrichment_stats['mc_attempts']}")
        print(f"  MC successes: {self.enrichment_stats['mc_successes']}")
        print(f"  MC cache hits: {self.enrichment_stats['mc_cache_hits']}")
        if self.enrichment_stats['mc_attempts'] > 0:
            mc_success_rate = (self.enrichment_stats['mc_successes'] / self.enrichment_stats['mc_attempts'] * 100)
            print(f"  MC success rate: {mc_success_rate:.1f}%")

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
                "mc_scraper": {
                    "attempts": self.enrichment_stats['mc_attempts'],
                    "successes": self.enrichment_stats['mc_successes'],
                    "cache_hits": self.enrichment_stats['mc_cache_hits'],
                    "success_rate": calc_rate(
                        self.enrichment_stats['mc_successes'],
                        self.enrichment_stats['mc_attempts']
                    ),
                    "cache_hit_rate": calc_rate(
                        self.enrichment_stats['mc_cache_hits'],
                        self.enrichment_stats['mc_attempts']
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
                if tracking_movie.get('manual_watch_links') and tracking_movie.get('watch_links'):
                    movie['watch_links'] = tracking_movie['watch_links']
                    fields_updated += 1

        if fields_updated > 0:
            print(f"📝 Applied {fields_updated} manual field edits from movie_tracking.json")

        # Sync pre-order flags from tracking → data.json (recovery for stripped flags)
        _preorder_overrides = self.config.get('preorder_overrides', {})
        _today_sync = datetime.now().strftime('%Y-%m-%d')
        _preorder_synced = 0
        for movie in display_movies:
            movie_id = str(movie.get('id'))
            _po_override = _preorder_overrides.get(movie_id)
            if _po_override is False:
                # Explicit override: NOT a pre-order
                if movie.get('_is_preorder'):
                    movie.pop('_is_preorder', None)
                    movie.pop('pre_order_links', None)
                continue
            if _po_override is True:
                dd = movie.get('digital_date', '')
                if dd > _today_sync and not movie.get('_is_preorder'):
                    movie['_is_preorder'] = True
                    _preorder_synced += 1
                continue
            # No override — check tracking for flag that was lost from data.json
            if movie_id in tracking_data:
                tracking_movie = tracking_data[movie_id]
                if tracking_movie.get('_is_preorder') and not movie.get('_is_preorder'):
                    dd = movie.get('digital_date', '')
                    if dd > _today_sync:
                        movie['_is_preorder'] = True
                        _preorder_synced += 1
        if _preorder_synced > 0:
            print(f"🏷️  Synced {_preorder_synced} pre-order flag(s) from tracking → data.json")

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
        screening_url_patterns = ['eventive.org', 'festivalplayer.sundance.org', 'shift72.com']

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
            remaining_movies.sort(key=lambda x: x.get('digital_date') or '', reverse=True)

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

