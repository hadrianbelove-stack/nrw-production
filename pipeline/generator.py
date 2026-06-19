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
from datetime import datetime, timedelta
import re
import logging
# NOTE: Scraper imports are LAZY (inside methods) to protect intake/discovery phases
# If a scraper import fails, only enrichment breaks - not the whole pipeline
# YouTube trailer finder: Try Gemini-based hybrid first, fall back to Playwright-only
try:
    from gemini_scraper import HybridYouTubeFinder
    from gemini_scraper.youtube import validate_youtube_url_live
    GEMINI_AVAILABLE = True
except ImportError:
    # Fallback: If Gemini module fails, use Playwright-only scraper
    from scripts.youtube_trailer_scraper import YouTubeTrailerScraper as HybridYouTubeFinder
    GEMINI_AVAILABLE = False
    # gemini_scraper unavailable — define liveness check inline
    def validate_youtube_url_live(url):
        try:
            import requests
            resp = requests.head(f"https://www.youtube.com/oembed?url={url}&format=json", timeout=5)
            return resp.status_code == 200
        except Exception:
            return True

# RT finder: Try Gemini-based hybrid first, fall back to Playwright-only
try:
    from gemini_scraper import HybridRTFinder
    GEMINI_RT_AVAILABLE = True
except ImportError:
    # Fallback: If Gemini module fails, use Playwright-only scraper
    from rt_scraper_playwright import RTScraperPlaywright as HybridRTFinder
    GEMINI_RT_AVAILABLE = False

from pipeline.context import PipelineContext
from pipeline.intake import MovieIntake
from pipeline.discoverer import ProviderDiscoverer
from pipeline.enricher import MovieEnricher
from pipeline.display import DisplayGenerator
from pipeline.archive import ArchiveManager
from utils.logger import setup_logger


class DataGenerator:
    def __init__(self, enrichment_enabled: bool = True):
        # Set enrichment flag immediately to avoid timing bugs
        self.enrichment_enabled = enrichment_enabled

        # Initialize logger FIRST before any operations that might log
        self.logger = setup_logger('data_generator', 'logs/admin.log', logging.INFO)

        # Initialize storage service (extracted 2025-11-10)
        from pipeline import StorageService
        self.storage = StorageService(self.logger)

        self.config = self.load_config()

        # Get TMDB API key from environment or config.yaml (12-factor app pattern)
        self.tmdb_key = os.environ.get('TMDB_API_KEY')
        if not self.tmdb_key:
            # Fall back to config.yaml for local development
            self.tmdb_key = self.config.get('api', {}).get('tmdb_api_key')

        # Watch link discovery via cache + Playwright scrapers
        self.wikipedia_cache = self.storage.load_cache('cache/wikipedia_cache.json')
        self.wikipedia_overrides = self.storage.load_cache('overrides/wikipedia_overrides.json')
        self.rt_overrides = self.storage.load_cache('overrides/rt_overrides.json')
        self.watch_links_overrides = self.storage.load_cache('overrides/watch_links_overrides.json')
        self.trailer_overrides = self.storage.load_cache('overrides/trailer_overrides.json')
        self.watch_links_cache = self.storage.load_cache('cache/watch_links_cache.json')

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
            'lb_attempts': 0,
            'lb_successes': 0,
            'lb_cache_hits': 0,
            'trailer_attempts': 0,
            'trailer_successes': 0,
            'schema_validation_warnings': 0,
            'schema_validation_passes': 0
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
        self.letterboxd_scraper = None  # Lazy initialization for Letterboxd score scraping
        self.wikipedia_scraper = None  # Lazy initialization for Wikipedia scraping with Playwright

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
        self.last_wikidata_distributors = []

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
        self._enricher = MovieEnricher(self._ctx, host=self, discoverer=self._discoverer)
        self._display = DisplayGenerator(self._ctx, host=self)
        self._archive = ArchiveManager(self._ctx)

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

    # ------------------------------------------------------------------
    # Intake delegation (implementation in pipeline/intake.py)
    # ------------------------------------------------------------------

    def intake_new_premieres(self, debug=False, since_date=None, bootstrap=False):
        """Intake new movie premieres — delegates to pipeline/intake.py"""
        return self._intake.intake_new_premieres(debug=debug, since_date=since_date, bootstrap=bootstrap)

    def intake_new_miniseries(self, debug=False, days_back=30):
        """Intake new miniseries — delegates to pipeline/intake.py"""
        return self._intake.intake_new_miniseries(debug=debug, days_back=days_back)

    def intake_apple_music_live(self, debug=False):
        """Intake Apple Music Live specials — delegates to pipeline/intake.py"""
        return self._intake.intake_apple_music_live(debug=debug)

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
        movie['_transitioned_at'] = datetime.now().strftime('%Y-%m-%d')
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
        - 'Amazon Prime Video' → 'Amazon Prime Video' (streaming — different from VOD)
        - 'Amazon Video' → 'Amazon' (VOD rent/buy)
        - 'DocuramaFilms Amazon Channel' → 'DocuramaFilms' (NOT 'Amazon')
        - 'Shudder Amazon Channel' → 'Shudder'
        - 'AMC Plus Apple TV Channel' → 'AMC+'
        """
        if not provider_name:
            return provider_name

        # Strip platform channel suffixes FIRST — these are third-party channels
        # hosted on Amazon/Apple, not Amazon/Apple themselves
        provider_lower = provider_name.lower()
        channel_suffixes = ['amazon channel', 'apple tv channel']
        for suffix in channel_suffixes:
            if suffix in provider_lower:
                # Extract the actual channel name (everything before the suffix)
                idx = provider_lower.index(suffix)
                channel_name = provider_name[:idx].strip()
                if channel_name:
                    # Re-run the channel name through simplification (e.g. "AMC Plus" → "AMC+")
                    return self.simplify_provider_name(channel_name)

        # Most specific patterns first
        # NOTE: 'amazon prime' MUST come before 'amazon' — Prime Video (streaming)
        # is a different service from Amazon (VOD rent/buy) with different logos
        simplifications = [
            ('amc', 'AMC+'),
            ('netflix', 'Netflix'),
            ('disney', 'Disney+'),
            ('hulu', 'Hulu'),
            ('hbo max', 'Max'),
            ('paramount', 'Paramount+'),
            ('peacock', 'Peacock'),
            ('amazon prime', 'Amazon Prime Video'),
            ('prime video', 'Amazon Prime Video'),
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
            'append_to_response': 'credits,videos,external_ids,alternative_titles,keywords'
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.logger.error(f"Error fetching details for {movie_id}: {e}")
        return None

    def get_tv_details(self, tv_id):
        """Get full TV series details from TMDB (for miniseries/limited series)"""
        url = f"https://api.themoviedb.org/3/tv/{tv_id}"
        params = {
            'api_key': self.tmdb_key,
            'language': 'en-US',
            'append_to_response': 'credits,videos,external_ids,alternative_titles,keywords'
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.logger.error(f"Error fetching TV details for {tv_id}: {e}")
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

    @staticmethod
    def _compute_display_title(title, original_title, original_language):
        """Compute display_title — foreign films always use 'English (Original)' format."""
        if original_title and original_title != title and original_language != 'en':
            return f"{title} ({original_title})"
        return title or ''

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
                    return False

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
        """Delegate to ArchiveManager. Kept for external callers (discoverer, enricher)."""
        return self._archive.safe_save_data_json(display_data, existing_movies, label)

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
        # Prefer origin_country (true origin) over production_countries[0] (alphabetical co-production order)
        origin_countries = movie_details.get('origin_country', [])
        production_countries = movie_details.get('production_countries', [])
        if origin_countries:
            origin_iso = origin_countries[0]
            if is_tv:
                entry['country'] = origin_iso
            else:
                match = next((pc.get('name') for pc in production_countries if pc.get('iso_3166_1') == origin_iso), None)
                entry['country'] = match or origin_iso
        elif production_countries:
            entry['country'] = production_countries[0].get('name', 'Unknown') if not is_tv else production_countries[0].get('iso_3166_1', 'Unknown')
        else:
            entry['country'] = 'Unknown'

        # Add original language (ISO 639-1 code: 'en', 'es', 'fr', etc.)
        entry['original_language'] = movie_details.get('original_language')
        entry['original_title'] = movie_details.get(original_title_field)

        # Generate display_title (foreign films get bilingual format)
        entry['display_title'] = self._compute_display_title(
            entry.get('title', ''), entry.get('original_title'), entry.get('original_language', 'en')
        )

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

    def get_omdb_data(self, imdb_id):
        """Fetch awards, box office, and scores from OMDb in one call.

        Returns dict with keys: awards, box_office, rt_score, metacritic, imdb_rating
        All values are strings or None. Returns None if imdb_id missing or API fails.
        """
        if not imdb_id:
            return None

        omdb_key = os.environ.get('OMDB_API_KEY') or self.config.get('api', {}).get('omdb_api_key')
        if not omdb_key:
            return None

        try:
            url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}"
            response = requests.get(url, timeout=8)
            if response.status_code != 200:
                return None
            d = response.json()
            if d.get('Response') == 'False':
                return None

            def _na(val):
                return val if val and val != 'N/A' else None

            rt_score = None
            metacritic = None
            for rat in d.get('Ratings', []):
                src = rat.get('Source', '')
                val = rat.get('Value', '')
                if 'Rotten Tomatoes' in src:
                    rt_score = _na(val)
                elif 'Metacritic' in src:
                    metacritic = _na(val.split('/')[0]) if val and '/' in val else _na(val)
            if metacritic is None:
                metacritic = _na(d.get('Metascore'))

            return {
                'awards':      _na(d.get('Awards')),
                'box_office':  _na(d.get('BoxOffice')),
                'rt_score':    rt_score,
                'metacritic':  metacritic,
                'imdb_rating': _na(d.get('imdbRating')),
            }
        except Exception as e:
            self.logger.debug(f"OMDb get_omdb_data error for {imdb_id}: {e}")
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
        """Fetch IMDb rating using 4-tier waterfall.

        Tiers:
            1. Cache check
            2. IMDb bulk dataset (daily TSV from datasets.imdbws.com)
            3. OMDb API by ID
            4. Gemini + Google Search grounding (catches new/low-vote movies)

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

        return None

    def find_wikipedia_url(self, title, year, imdb_id, movie_id=None, director=None, original_title=None, skip_playwright=False, skip_gemini=False):
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
                skip_playwright=skip_playwright,
                skip_gemini=skip_gemini
            )

            # Update our local cache reference to match scraper's cache
            self.wikipedia_cache = self.wikipedia_scraper.cache

            # Track stats for this attempt
            self.wikipedia_stats['wikidata_attempts'] = self.wikipedia_scraper.stats.get('wikidata_attempts', 0)
            self.wikipedia_stats['wikidata_successes'] = self.wikipedia_scraper.stats.get('wikidata_successes', 0)

            # Pass through Wikidata distributors if found
            self.last_wikidata_distributors = getattr(self.wikipedia_scraper, 'last_wikidata_distributors', [])

            return wiki_url

        except Exception as e:
            self.logger.error(f"Wikipedia scraper error for {title} ({year}): {e}")
            return None

    def find_director_wikipedia_url(self, name):
        """Find a film director's Wikipedia URL using the existing scraper infrastructure."""
        if not name or not self.enrichment_enabled:
            return None
        if self.wikipedia_scraper is None:
            try:
                from wikipedia_scraper_playwright import WikipediaScraperPlaywright
                self.wikipedia_scraper = WikipediaScraperPlaywright(
                    cache_file='cache/wikipedia_cache.json',
                    config=self.config,
                    logger=self.logger
                )
            except Exception as e:
                self.logger.error(f"Failed to initialize Wikipedia scraper for director lookup: {e}")
                return None
        try:
            return self.wikipedia_scraper.find_director_wikipedia_url(name)
        except Exception as e:
            self.logger.error(f"Director Wikipedia lookup error for {name}: {e}")
            return None

    def find_cast_wikipedia_url(self, name):
        """Find a cast member's Wikipedia URL using the existing scraper infrastructure."""
        if not name or not self.enrichment_enabled:
            return None
        if self.wikipedia_scraper is None:
            try:
                from wikipedia_scraper_playwright import WikipediaScraperPlaywright
                self.wikipedia_scraper = WikipediaScraperPlaywright(
                    cache_file='cache/wikipedia_cache.json',
                    config=self.config,
                    logger=self.logger
                )
            except Exception as e:
                self.logger.error(f"Failed to initialize Wikipedia scraper for cast lookup: {e}")
                return None
        try:
            return self.wikipedia_scraper.find_cast_wikipedia_url(name)
        except Exception as e:
            self.logger.error(f"Cast Wikipedia lookup error for {name}: {e}")
            return None

    def _validate_youtube_url_live(self, url):
        """Check if a YouTube URL actually resolves to a playable video.
        Uses YouTube's oEmbed endpoint — fast (~100ms), no API key needed."""
        return validate_youtube_url_live(url)

    def _cache_bad_trailer_key(self, key, title, year, url):
        """Add a dead YouTube key to bad_trailer_urls cache and save."""
        self.bad_trailer_urls[key] = {
            'title': title,
            'year': str(year),
            'reason': 'failed_live_validation',
            'url': url,
            'recorded_at': datetime.now().isoformat()
        }
        self.storage.save_cache(self.bad_trailer_urls, 'cache/bad_trailer_urls.json')

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
          2. YouTube scraper cache (validated — free/instant, best quality)
          3. Gemini+Playwright live search (validated — most reliable, costs tokens)
          4. TMDB official trailers (validated — TMDB data can go stale)
          5. TMDB any YouTube video (validated — teasers/clips, last resort from TMDB)
          6. Broad YouTube search (validated — last resort)
        """
        title = movie_details.get('name') or movie_details.get('title', '')
        year = (movie_details.get('first_air_date') or movie_details.get('release_date', ''))[:4] if (movie_details.get('first_air_date') or movie_details.get('release_date')) else ''

        # --- Tier 1: Manual overrides (always trusted) ---
        override_key = f"{title}_{year}"
        if override_key in self.trailer_overrides:
            self.logger.info(f"Trailer for {title} ({year}): tier=override")
            return self.trailer_overrides[override_key], 'override'

        # --- Tier 2: YouTube scraper cache (validated — free/instant, best quality) ---
        cache_key = f"{title}_{year}"
        if cache_key in self.youtube_trailer_cache:
            cached_url = self.youtube_trailer_cache[cache_key]
            if cached_url and self._validate_youtube_url_live(cached_url):
                self.logger.info(f"Trailer for {title} ({year}): tier=cache, url={cached_url}")
                return cached_url, 'cache'
            elif cached_url:
                self.logger.warning(f"Trailer dead link for {title} ({year}): tier=cache, url={cached_url}")
                del self.youtube_trailer_cache[cache_key]  # Invalidate dead cache entry

        # --- Tier 3: Gemini+Playwright live search (validated — most reliable) ---
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
                    # We already proved this URL is dead in Tier 2
                    del finder_cache[cache_key]
                    self.logger.info(f"Cleared dead URL from finder cache for {title} ({year})")

            self.enrichment_stats['trailer_attempts'] += 1

            # TMDB raw data has credits.crew as a list, not crew.director as a string
            credits = (movie_details.get('credits') or {}) if movie_details else {}
            crew_list = credits.get('crew', [])
            cast_members = credits.get('cast', [])
            director = next((c['name'] for c in crew_list if c.get('job') == 'Director'), None)
            cast = [c['name'] for c in cast_members[:3]] if cast_members else None

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

        videos = movie_details.get('videos', {}).get('results', [])

        # --- Tier 4: TMDB official trailers (validated — fallback after scraper) ---
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
        result = self.scrape_rt_score(title, year, director=director, original_language=original_language, original_title=original_title, imdb_id=imdb_id)
        if result:
            return result

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

    def find_letterboxd_score(self, title, year, tmdb_id=None):
        """Find Letterboxd URL and average rating via HTTP scraper."""
        enabled = self.config.get('letterboxd_scraper', {}).get('enabled', True)
        if not enabled:
            return None

        if not self._init_letterboxd_scraper():
            return None

        try:
            result = self.letterboxd_scraper.scrape_letterboxd_score(title, int(year), tmdb_id=tmdb_id)
            scraper_stats = self.letterboxd_scraper.get_stats()
            self.enrichment_stats['lb_attempts'] = scraper_stats['attempts']
            self.enrichment_stats['lb_successes'] = scraper_stats['successes']
            self.enrichment_stats['lb_cache_hits'] = scraper_stats['cache_hits']
            return result
        except Exception as e:
            self.logger.warning(f"Letterboxd scraper error for {title}: {e}")
            return None

    def _init_letterboxd_scraper(self):
        """Initialize Letterboxd scraper (lazy initialization)."""
        if self.letterboxd_scraper is not None:
            return self.letterboxd_scraper is not False

        if not self.enrichment_enabled:
            self.logger.debug("Letterboxd scraper disabled - enrichment not enabled")
            self.letterboxd_scraper = False
            return False

        try:
            from letterboxd_scraper import LetterboxdScoreScraper
            self.letterboxd_scraper = LetterboxdScoreScraper(
                cache_file='cache/letterboxd_score_cache.json',
                config=self.config,
                logger=self.logger
            )
            self.logger.info("Letterboxd scraper initialized (HTTP-based)")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Letterboxd scraper: {e}")
            self.letterboxd_scraper = False
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


    def scrape_rt_score(self, title, year, director=None, original_language=None, original_title=None, imdb_id=None):
        """Public wrapper function to scrape RT score for external consumers

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for disambiguation
            original_language: ISO 639-1 language code
            original_title: Original-language title from TMDB
            imdb_id: IMDb ID for OMDb cross-check validation

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        # Initialize scraper if needed
        if not self._init_rt_scraper():
            return None

        try:
            # HybridRTFinder uses find_rt_score(); Playwright-only uses scrape_rt_score()
            if GEMINI_RT_AVAILABLE:
                result = self.rt_scraper.find_rt_score(title, year, director=director, original_language=original_language, original_title=original_title, imdb_id=imdb_id)
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

            _, bucket, bucket_url = self._b2_connection
            # Prefer config bucket_url over B2 native URL
            config_url = trailer_config.get('bucket_url', '') or bucket_url

            hosted_url, _, _fail_reason, _fail_detail = download_and_upload_trailer(movie_id, title, year, youtube_url, bucket, config_url)
            if hosted_url:
                self.logger.info(f"Trailer hosted: {title} ({year}) -> {hosted_url}")
            return hosted_url
        except BaseException as e:
            # BaseException catches RuntimeError from get_b2_api() and other trailer hosting failures
            self.logger.warning(f"Trailer hosting failed for {title}: {type(e).__name__}: {str(e)[:500]}")
            return None


    def enrich_newly_available_movies(self, target_id=None) -> int:
        """Enrich newly available movies — delegates to pipeline/enricher.py"""
        return self._enricher.enrich_newly_available_movies(target_id=target_id)


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

    def _fetch_eventive_play_info(self, play_url):
        """Fetch a single Eventive screening's window directly from its play link.

        Works for both the central watch.eventive.org domain AND white-label
        festival domains (e.g. watch.imaginenative.org). The slug extractor and
        festival-page scraper only recognize watch.eventive.org, so custom-domain
        festivals discovered via TMDB arrive with no end date and never expire.
        The play page's embedded __NEXT_DATA__ carries the window regardless of
        domain, so we read it straight from the link we already have.

        Returns dict: {'name', 'available_start', 'available_end', 'is_available'}
        Dates are 'YYYY-MM-DD' (UTC) or None.
        """
        if not hasattr(self, '_play_info_cache'):
            self._play_info_cache = {}
        if play_url in self._play_info_cache:
            return self._play_info_cache[play_url]

        result = {'name': None, 'available_start': None, 'available_end': None, 'is_available': None}

        def _to_date(ts):
            if not ts:
                return None
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                return None

        try:
            resp = requests.get(play_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.ok:
                nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text)
                if nd_match:
                    nd = json.loads(nd_match.group(1))
                    page_props = nd.get('props', {}).get('pageProps', {})
                    init = page_props.get('initialData', {}) or {}
                    tenant = page_props.get('initialTenant', {}) or {}
                    result['available_start'] = _to_date(init.get('start_time'))
                    result['available_end'] = _to_date(init.get('end_time'))
                    result['is_available'] = init.get('is_available')
                    result['name'] = tenant.get('display_name') or init.get('name')
                    if result['available_end']:
                        print(f"  ℹ️  Eventive play-link window for \"{result['name']}\": "
                              f"{result['available_start']} to {result['available_end']}")
        except Exception as e:
            self.logger.debug(f"Could not fetch Eventive play page '{play_url}': {e}")

        self._play_info_cache[play_url] = result
        return result

    def scan_eventive_screenings(self):
        """Scan Eventive for active virtual screenings matching NRW movies.

        Populates watch_links_cache and updates tracking providers so the
        discoverer's VS bypass can transition matched movies on the same run.

        Only auto-caches matches from festivals with clear date windows
        (both start_time and end_time present) to avoid false positives
        from undated/evergreen festivals.

        Returns:
            int: Number of new Eventive links cached.
        """
        from pipeline.eventive import (
            scan_all_festivals,
            build_title_indexes,
            match_film,
        )

        self.logger.info("Starting Eventive virtual screening scan...")

        # Scan all festivals
        try:
            scan_result = scan_all_festivals(logger=self.logger)
        except Exception as e:
            self.logger.error(f"Eventive scan failed: {e}")
            print(f"  ❌ Eventive scan failed: {e}")
            return 0

        unique_films = scan_result['films']
        stats = scan_result['stats']

        # Load tracking and wall data
        tracking_data = self.storage.tracking_db.load_all()
        tracking_movies = tracking_data.get('movies', {})

        wall_movies = []
        if os.path.exists('data.json'):
            with open('data.json', 'r') as f:
                data = json.load(f)
            wall_movies = data.get('movies', []) if isinstance(data, dict) else data

        # Build title indexes
        tier1_index, tier2_index = build_title_indexes(tracking_movies, wall_movies)

        # Match films against NRW
        new_cached = 0
        tracking_matches = []
        wall_matches = []
        skipped_undated = 0

        for film in unique_films:
            match = match_film(film, tier1_index, tier2_index)
            if not match:
                continue

            # Only auto-cache matches with clear date windows
            has_dates = bool(film.get('start_time')) and bool(film.get('end_time'))

            for mid, orig_title, source, nrw_status in match['matches']:
                entry = {
                    'movie_id': mid,
                    'nrw_title': orig_title,
                    'eventive_title': film['name'],
                    'festival': film.get('festival_name', film.get('slug', '')),
                    'link': film['link'],
                    'start': film.get('start_time', ''),
                    'end': film.get('end_time', ''),
                    'status': film.get('status', 'active'),
                    'match_tier': match['tier'],
                    'nrw_status': nrw_status,
                }

                if source == 'wall':
                    wall_matches.append(entry)
                else:
                    tracking_matches.append(entry)

                if not has_dates:
                    skipped_undated += 1
                    continue

                movie_id = str(mid)

                # Write to watch_links_cache
                existing_cache = self.watch_links_cache.get(movie_id, {})
                existing_source = existing_cache.get('source', '')

                # Don't overwrite non-Eventive cache entries (JustWatch, manual, etc.)
                if existing_source and existing_source != 'eventive_scanner':
                    continue

                self.watch_links_cache[movie_id] = {
                    'links': {
                        'vod': [{
                            'service': 'Eventive',
                            'link': film['link'],
                        }]
                    },
                    'cached_at': datetime.now().isoformat(),
                    'source': 'eventive_scanner',
                    'start_time': film.get('start_time', ''),
                    'end_time': film.get('end_time', ''),
                    'festival_name': film.get('festival_name', ''),
                }

                # Update tracking providers if this is a tracking movie
                if source == 'tracking' and movie_id in tracking_movies:
                    movie = tracking_movies[movie_id]
                    providers = movie.get('providers', {})
                    rent = providers.get('rent', [])
                    if 'eventive' not in [p.lower() if isinstance(p, str) else '' for p in rent]:
                        rent.append('Eventive')
                        providers['rent'] = rent
                        movie['providers'] = providers

                new_cached += 1
                print(f"  ✓ {orig_title} — cached Eventive link ({film.get('festival_name', '')})")

        # Save updated cache
        if new_cached > 0:
            self.storage.atomic_write_json(
                self.watch_links_cache,
                'cache/watch_links_cache.json',
                backup=True
            )
            self.storage.tracking_db.save_all(tracking_data)
            print(f"  💾 Saved {new_cached} Eventive links to cache + tracking")

        # Save scan metrics
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'eventive_scan_pipeline',
            'stats': {
                **stats,
                'tracking_matches': len(tracking_matches),
                'wall_matches': len(wall_matches),
                'new_cached': new_cached,
                'skipped_undated': skipped_undated,
            },
            'tracking_matches': tracking_matches,
            'wall_matches': wall_matches,
        }
        os.makedirs('metrics', exist_ok=True)
        with open('metrics/eventive_scan_run.json', 'w') as f:
            json.dump(metrics, f, indent=2)

        self.logger.info(
            f"Eventive scan complete: {len(tracking_matches)} tracking matches, "
            f"{len(wall_matches)} wall matches, {new_cached} new cached, "
            f"{skipped_undated} skipped (undated)"
        )

        return new_cached

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
        screening_movies = [m for m in movies if m.get('filters', {}).get('is_virtual_screening')]

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
        tracking_data = self.storage.tracking_db.load_all()

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

    def reenrich_trailer_gaps(self):
        """Re-enrich trailer gaps — delegates to pipeline/discoverer.py"""
        return self._discoverer.reenrich_trailer_gaps()

    def daily_gap_fill(self):
        """Daily gap fill — delegates to pipeline/discoverer.py"""
        return self._discoverer.daily_gap_fill()


    def archive_old_movies(self, days=90):
        """Delegate to ArchiveManager. Kept for external callers (generate_data.py)."""
        return self._archive.archive_old_movies(days)

    def purge_removed_movies(self, movies_list=None):
        """Delegate to ArchiveManager. Kept for external callers (enricher)."""
        return self._archive.purge_removed_movies(movies_list)

    def _inject_selected_pull_quotes(self, movies_list):
        """Delegate to DisplayGenerator."""
        return self._display.inject_selected_pull_quotes(movies_list)

    def _inject_approved_capsules(self, movies_list):
        """Delegate to DisplayGenerator."""
        return self._display.inject_approved_capsules(movies_list)

    def _apply_cached_watch_links(self, movies_list):
        """Delegate to DisplayGenerator."""
        return self._display.apply_cached_watch_links(movies_list)

    def generate_display_data(self, days_back=90):
        """
        PHASE 4: Apply admin overrides and prepare final display data.

        Loads data.json, applies admin overrides (hide/featured/ordering),
        and saves the result. Old movies (>90 days) are archived to data_archive.json.

        Args:
            days_back: Used for stats only (frontend handles date filtering)
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

        # Compute display_title for all movies (foreign films get bilingual format)
        for m in all_movies:
            m['display_title'] = self._compute_display_title(
                m.get('title', ''), m.get('original_title'), m.get('original_language', 'en')
            )

        # Inject selected pull quotes from cache into movie data
        self._inject_selected_pull_quotes(all_movies)

        # Restore approved capsules from the bank for movies missing one
        self._inject_approved_capsules(all_movies)

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
        cache_hits = self.enrichment_stats['cache_hits']
        print(f"\n📊 Watch Links Enrichment:")
        print(f"  Cache hits: {cache_hits}")
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

        print(f"\n📊 Letterboxd Scraper Usage:")
        print(f"  LB attempts: {self.enrichment_stats['lb_attempts']}")
        print(f"  LB successes: {self.enrichment_stats['lb_successes']}")
        print(f"  LB cache hits: {self.enrichment_stats['lb_cache_hits']}")
        if self.enrichment_stats['lb_attempts'] > 0:
            lb_success_rate = (self.enrichment_stats['lb_successes'] / self.enrichment_stats['lb_attempts'] * 100)
            print(f"  LB success rate: {lb_success_rate:.1f}%")

        print(f"\n📊 Trailer Scraper Usage:")
        print(f"  Trailer attempts: {self.enrichment_stats['trailer_attempts']}")
        print(f"  Trailer successes: {self.enrichment_stats['trailer_successes']}")
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
                    ),
                    "error_types": self.rt_scraper.get_error_counts() if self.rt_scraper and self.rt_scraper is not False else {}
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
                    ),
                    "error_types": self.metacritic_scraper.get_error_counts() if self.metacritic_scraper and self.metacritic_scraper is not False else {}
                },
                "lb_scraper": {
                    "attempts": self.enrichment_stats['lb_attempts'],
                    "successes": self.enrichment_stats['lb_successes'],
                    "cache_hits": self.enrichment_stats['lb_cache_hits'],
                    "success_rate": calc_rate(
                        self.enrichment_stats['lb_successes'],
                        self.enrichment_stats['lb_attempts']
                    ),
                    "cache_hit_rate": calc_rate(
                        self.enrichment_stats['lb_cache_hits'],
                        self.enrichment_stats['lb_attempts']
                    ),
                    "error_types": self.letterboxd_scraper.get_error_counts() if self.letterboxd_scraper and self.letterboxd_scraper is not False else {}
                },
                "wikipedia_scraper": {
                    "wikidata_attempts": self.wikipedia_stats['wikidata_attempts'],
                    "wikidata_successes": self.wikipedia_stats['wikidata_successes'],
                    "success_rate": calc_rate(
                        self.wikipedia_stats['wikidata_successes'],
                        self.wikipedia_stats['wikidata_attempts']
                    ),
                    "error_types": self.wikipedia_scraper.get_error_counts() if self.wikipedia_scraper and self.wikipedia_scraper is not False else {}
                },
                "trailer_scraper": {
                    "attempts": self.enrichment_stats['trailer_attempts'],
                    "successes": self.enrichment_stats['trailer_successes'],
                    "success_rate": calc_rate(
                        self.enrichment_stats['trailer_successes'],
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

    def apply_admin_overrides(self, display_movies):
        """Delegate to DisplayGenerator. Kept for external callers (enricher)."""
        return self._display.apply_admin_overrides(display_movies)

