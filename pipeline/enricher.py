"""
Movie enrichment module — Phase 3 of the NRW pipeline.

Extracted from DataGenerator (pipeline/generator.py) for maintainability.
Handles metadata enrichment for newly available movies: Wikipedia, trailers,
RT/Metacritic scores, IMDb ratings, watch links, and digital date correction.
"""

import json
import os
import re
import signal
import time
from datetime import datetime, timedelta

from constants import (
    MAX_ENRICHMENT_BATCH,
    ENRICHMENT_LOOP_TIMEOUT_MINUTES,
    MAX_ENRICHMENT_ATTEMPTS,
    RETRY_BACKOFF_DAYS,
)


class MovieEnricher:
    """Enriches movies with metadata after discovery adds them to data.json.

    Parameters
    ----------
    ctx : PipelineContext
        Shared pipeline dependencies (config, logger, storage, enrichment_service, tmdb_key).
    host : DataGenerator
        Parent generator instance — provides shared utilities
        (get_movie_details, find_wikipedia_url, simplify_provider_name, etc.).
    discoverer : ProviderDiscoverer
        Discovery module instance — provides _detect_buyonly_preorder().
    """

    def __init__(self, ctx, host, discoverer):
        self.ctx = ctx
        self.host = host
        self.discoverer = discoverer
        self._error_details = []
        self._current_enrichment_step = None

    # ------------------------------------------------------------------
    # Quality validation
    # ------------------------------------------------------------------

    def validate_enrichment_quality(self, result, movie_data, movie_details, movie_id, is_tv=False):
        """Post-enrichment quality gate: flag suspicious entries before publishing.

        Checks for mismatched watch links, unexpected title changes, foreign titles,
        and other data quality issues. Sets _needs_review and _quality_warnings on
        entries that fail checks.
        """
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
                self.ctx.logger.warning(f"Quality gate [{movie_id}] {title}: {w}")
        else:
            result['_needs_review'] = False

        return warnings

    # ------------------------------------------------------------------
    # Per-source enrichment runner
    # ------------------------------------------------------------------

    def _run_enrichment_source(self, source_name, fn, enrichment_results, title, year):
        """Run a single enrichment source with isolated failure handling.

        Wraps the source function in try/except, logs success/failure/error,
        and returns the result (or None on failure).
        """
        self._current_enrichment_step = source_name
        try:
            result = fn()
            if result:
                enrichment_results[source_name] = 'success'
                self.ctx.logger.debug(f"{source_name}: Found for {title} ({year})")
            else:
                enrichment_results[source_name] = 'not_found'
                self.ctx.logger.debug(f"{source_name}: Not found for {title} ({year})")
            return result
        except Exception as e:
            enrichment_results[source_name] = 'error'
            self.ctx.logger.warning(f"{source_name}: Error for {title} ({year}): {type(e).__name__}: {str(e)[:500]}")
            self._error_details.append({
                'timestamp': datetime.now().isoformat(),
                'title': title,
                'source': source_name,
                'error_type': type(e).__name__,
                'error_message': str(e)[:500],
            })
            return None

    # ------------------------------------------------------------------
    # Per-movie enrichment field extraction
    # ------------------------------------------------------------------

    def get_enrichment_only_fields(self, movie_id, movie_data, movie_details, force_refresh=False):
        """Extract enrichment-only fields with graceful partial failure handling

        This method implements a graceful degradation strategy where individual
        enrichment source failures don't prevent saving partial data. Each source
        (Wikipedia, trailers, RT scores, watch links) is wrapped in try-catch blocks.

        Returns:
            dict or None: Enrichment fields dict, or None if movie is
            ineligible (missing TMDB details or runtime below minimum).
        """
        if not movie_details:
            self.ctx.logger.error(f"Movie details missing for movie_id {movie_id}")
            return None

        # Skip short films that bypassed intake's runtime filter (TMDB had null runtime at intake)
        _runtime = movie_details.get('runtime')
        _min_runtime = self.ctx.config.get('intake', {}).get('min_runtime', 60)
        if _runtime and _runtime < _min_runtime:
            self.ctx.logger.info(f"Skipping {movie_details.get('title', movie_id)}: runtime {_runtime}min < {_min_runtime}min minimum")
            return None

        # Safely extract basic info with fallbacks (TV series use different TMDB field names)
        is_tv = movie_data.get('content_type') == 'limited_series'
        title = movie_details.get('name' if is_tv else 'title', f'Unknown Movie {movie_id}')
        release_date = movie_details.get('first_air_date' if is_tv else 'release_date', '')
        year = release_date[:4] if release_date else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')

        # OMDb fallback: If TMDB doesn't have IMDb ID, try OMDb
        if not imdb_id:
            imdb_id = self.host.get_imdb_from_omdb(title, year)

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
            lambda: self.host.find_wikipedia_url(title, year, imdb_id, movie_id,
                                            director=wiki_director, original_title=wiki_orig_title),
            enrichment_results, title, year)
        if wiki_url:
            result['links']['wikipedia'] = wiki_url

        # Trailer link
        trailer_result = self._run_enrichment_source(
            'trailer', lambda: self.host.find_trailer_url(movie_details),
            enrichment_results, title, year)
        if trailer_result:
            trailer_url, trailer_source = trailer_result
            result['links']['trailer'] = trailer_url
            result['_trailer_source'] = trailer_source

        # RT score and link (isolated failure handling)
        self._current_enrichment_step = 'rt_score'
        try:
            rt_director = movie_details.get('crew', {}).get('director') if movie_details else None
            rt_lang = movie_details.get('original_language') if movie_details else None
            rt_orig_title = movie_details.get('original_name' if is_tv else 'original_title') if movie_details else None
            rt_data = self.host.find_rt_url(title, year, imdb_id, director=rt_director, original_language=rt_lang, original_title=rt_orig_title)
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
                self.ctx.logger.debug(f"RT: Found data for {title} ({year}) - Score: {result.get('rt_score', 'None')}")
            else:
                enrichment_results['rt_score'] = 'not_found'
                self.ctx.logger.debug(f"RT: No data found for {title} ({year})")
        except Exception as e:
            enrichment_results['rt_score'] = 'error'
            self.ctx.logger.warning(f"RT: Error for {title} ({year}): {type(e).__name__}: {str(e)[:500]}")
            self._error_details.append({
                'timestamp': datetime.now().isoformat(),
                'title': title, 'source': 'rt_score',
                'error_type': type(e).__name__, 'error_message': str(e)[:500],
            })

        # Metacritic score and link
        self._current_enrichment_step = 'metacritic_score'
        try:
            mc_data = self.host.find_metacritic_score(title, year)
            if mc_data:
                if mc_data.get('url'):
                    result['links']['metacritic'] = mc_data['url']
                result['metacritic_score'] = mc_data.get('score')
                if result.get('metacritic_score'):
                    enrichment_results['metacritic_score'] = 'success'
                else:
                    enrichment_results['metacritic_score'] = 'not_found'
                self.ctx.logger.debug(f"MC: Found data for {title} ({year}) - Score: {result.get('metacritic_score', 'None')}")
            else:
                enrichment_results['metacritic_score'] = 'not_found'
        except Exception as e:
            enrichment_results['metacritic_score'] = 'error'
            self.ctx.logger.warning(f"MC: Error for {title} ({year}): {type(e).__name__}: {str(e)[:500]}")
            self._error_details.append({
                'timestamp': datetime.now().isoformat(),
                'title': title, 'source': 'metacritic_score',
                'error_type': type(e).__name__, 'error_message': str(e)[:500],
            })

        # IMDB rating
        imdb_rating = self._run_enrichment_source(
            'imdb_rating', lambda: self.host.get_imdb_rating(imdb_id, title, year),
            enrichment_results, title, year)
        if imdb_rating:
            result['imdb_rating'] = imdb_rating
        if imdb_id:
            result['links']['imdb'] = f"https://www.imdb.com/title/{imdb_id}/"

        # Pull quotes (isolated failure handling)
        pull_quotes_enabled = self.ctx.config.get('gemini_scraper', {}).get('pull_quotes_enabled', False)
        if pull_quotes_enabled:
            try:
                from gemini_scraper import GeminiPullQuoteFinder
                pq_finder = GeminiPullQuoteFinder()
                pq_director = result.get('crew', {}).get('director') if result.get('crew') else None
                pq_count = self.ctx.config.get('gemini_scraper', {}).get('pull_quotes_count', 8)
                quotes = pq_finder.find_pull_quotes(title, year, director=pq_director, num_quotes=pq_count)
                if quotes:
                    enrichment_results['pull_quotes'] = 'success'
                else:
                    enrichment_results['pull_quotes'] = 'not_found'
            except Exception as e:
                enrichment_results['pull_quotes'] = 'error'
                self.ctx.logger.warning(f"Pull quotes: Error for {title} ({year}): {str(e)[:500]}")
        else:
            enrichment_results['pull_quotes'] = 'disabled'

        # Watch links (isolated failure handling)
        self._current_enrichment_step = 'watch_links'
        try:
            # Extract title variants for scraper fallback (English -> original -> US alternative)
            orig_title_key = 'original_name' if is_tv else 'original_title'
            original_title = movie_details.get(orig_title_key) if movie_details else None
            alt_titles_raw = movie_details.get('alternative_titles', {}).get('results', []) if movie_details else []

            enrich_director = result.get('crew', {}).get('director') if result.get('crew') else None
            watch_links_raw = self.ctx.enrichment_service.get_watch_links(
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
                                'service': self.host.simplify_provider_name(item['service']),
                                'link': item.get('link')
                            })
                        else:
                            simplified_array.append(item)
                    result['watch_links'][category] = simplified_array
                # Handle dict format (legacy backward compatibility)
                elif isinstance(link_obj, dict) and 'service' in link_obj:
                    simplified_service = self.host.simplify_provider_name(link_obj['service'])
                    result['watch_links'][category] = {
                        'service': simplified_service,
                        'link': link_obj.get('link')
                    }
                else:
                    result['watch_links'][category] = link_obj

            if result['watch_links']:
                enrichment_results['watch_links'] = 'success'
                self.ctx.logger.debug(f"Watch Links: Found {len(result['watch_links'])} categories for {title} ({year})")
            else:
                enrichment_results['watch_links'] = 'not_found'
                self.ctx.logger.debug(f"Watch Links: No links found for {title} ({year})")
        except Exception as e:
            enrichment_results['watch_links'] = 'error'
            self.ctx.logger.warning(f"Watch Links: Error for {title} ({year}): {type(e).__name__}: {str(e)[:500]}")

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
            origin_countries = movie_details.get('origin_country', [])
            production_countries = movie_details.get('production_countries', [])
            if origin_countries:
                origin_iso = origin_countries[0]
                if is_tv:
                    country = origin_iso
                else:
                    # Find full country name from production_countries matching origin
                    match = next((pc['name'] for pc in production_countries if pc.get('iso_3166_1') == origin_iso), None)
                    country = match or origin_iso
            elif production_countries:
                country = production_countries[0]['name'] if not is_tv else production_countries[0].get('iso_3166_1', production_countries[0]['name'])

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
            self.ctx.logger.warning(f"TMDB Metadata: Error extracting for {title} ({year}): {type(e).__name__}: {str(e)[:500]}")
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
            self.ctx.logger.info(f"Digital Date: Preserved manual date {movie_data['digital_date']} for {title}")
        else:
            try:
                type4_date = self.host.fetch_tmdb_type4_date(movie_id)
                if type4_date:
                    result['digital_date'] = type4_date
                    result['_digital_date_source'] = 'tmdb_type4'
                    enrichment_results['digital_date'] = 'success'
                    self.ctx.logger.debug(f"Digital Date: Corrected to {type4_date} for {title}")
                else:
                    result['_digital_date_source'] = 'detection'
                    enrichment_results['digital_date'] = 'not_found'
            except Exception as e:
                enrichment_results['digital_date'] = 'error'
                result['_digital_date_source'] = 'detection'
                self.ctx.logger.warning(f"Digital Date: Error for {title}: {type(e).__name__}: {str(e)[:500]}")

        # Calculate enrichment timing and log detailed results
        movie_duration = time.time() - movie_start_time

        # Create enrichment summary for logging
        success_count = len([v for v in enrichment_results.values() if v == 'success'])
        error_count = len([v for v in enrichment_results.values() if v == 'error'])

        # Enhanced console output with component-level status
        status_icons = {
            'success': '\u2713',
            'not_found': '\u25cb',
            'error': '\u2717',
            'not_attempted': '?'
        }

        wiki_icon = status_icons.get(enrichment_results['wikipedia'], '?')
        trailer_icon = status_icons.get(enrichment_results['trailer'], '?')
        rt_icon = status_icons.get(enrichment_results['rt_score'], '?')
        pq_icon = status_icons.get(enrichment_results.get('pull_quotes', 'not_attempted'), '?')
        links_icon = status_icons.get(enrichment_results['watch_links'], '?')
        date_icon = status_icons.get(enrichment_results['digital_date'], '?')

        print(f"  \u26a1 {title} ({movie_duration:.1f}s) - Wiki:{wiki_icon} Trailer:{trailer_icon} RT:{rt_icon} PQ:{pq_icon} Links:{links_icon} Date:{date_icon} | {success_count} success, {error_count} errors")

        # Detailed logging for metrics
        self.ctx.logger.info(f"Enrichment completed for {title} ({year}) in {movie_duration:.1f}s: {enrichment_results}")

        # Post-enrichment quality gate
        quality_warnings = self.validate_enrichment_quality(result, movie_data, movie_details, movie_id, is_tv=is_tv)
        if quality_warnings:
            print(f"  \u26a0\ufe0f  Quality gate flagged {title}: {len(quality_warnings)} warning(s)")
            enrichment_results['quality_gate'] = 'flagged'
        else:
            enrichment_results['quality_gate'] = 'passed'

        return result

    # ------------------------------------------------------------------
    # Main enrichment orchestrator
    # ------------------------------------------------------------------

    def enrich_newly_available_movies(self, target_id=None) -> int:
        """
        Enrich movies listed in metrics/newly_available.json.

        This is Phase 3 of the pipeline: overlay enrichment metadata onto
        movies that were added to data.json during discovery (Phase 2).

        Returns:
            int: Number of movies successfully enriched
        """
        print("\U0001f3a8 Starting enrichment phase...")
        _enrich_start = time.time()

        # Check if data.json exists
        if not os.path.exists('data.json'):
            print("\u274c No data.json found - run discovery phase first")
            return 0

        # Fix schema gracefully
        if not self.host.validator.fix_data_json_schema('data.json'):
            print("\u274c Could not fix data.json schema")
            return 0

        # Load existing data.json
        try:
            with open('data.json', 'r') as f:
                display_data = json.load(f)
        except Exception as e:
            print(f"\u274c Error loading data.json: {e}")
            return 0

        existing_movies = display_data.get('movies', [])
        movie_lookup = {str(m.get('id', '')): i for i, m in enumerate(existing_movies) if m.get('id')}
        _initial_movie_count = len(existing_movies)
        self.ctx.logger.info(f"Enrichment loaded data.json: {_initial_movie_count} movies")
        tracking_data = None      # Loaded before catch-up (batch) or before main loop (single)
        tracking_changed = False  # Track whether movie_tracking.json needs saving

        # Single-movie mode: skip queue building, enrich just this one
        if target_id:
            target_id = str(target_id)
            if target_id not in movie_lookup:
                print(f"\u274c Movie {target_id} not found in data.json - add it first")
                return 0
            movie_ids_to_enrich = [target_id]
            print(f"\U0001f3af Single-movie enrichment: targeting {target_id}")
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
                        print(f"\u26a0\ufe0f State file date ({state_date}) is not today ({today}) - may be stale")
                except Exception as e:
                    print(f"\u26a0\ufe0f Could not load {newly_available_file}: {e}")

            # Pre-order link finder: use Playwright scrapers to find
            # Amazon and Fandango At Home pre-order URLs for movies approaching release.
            _plf_days = self.ctx.config.get('preorder', {}).get('link_finder_days', 14)
            _plf_cutoff = (datetime.now() + timedelta(days=_plf_days)).strftime('%Y-%m-%d')
            _plf_candidates = []
            for _m in existing_movies:
                if not _m.get('_is_preorder'):
                    continue
                _dd = _m.get('digital_date', '')
                if not _dd or _dd > _plf_cutoff:
                    continue
                # Only skip if both Amazon and Fandango already found
                _existing_pol = _m.get('pre_order_links', [])
                _has_amazon = any('amazon' in p.get('service', '').lower() for p in _existing_pol)
                _has_fandango = any('fandango' in p.get('service', '').lower() for p in _existing_pol)
                if _has_amazon and _has_fandango:
                    continue
                _plf_candidates.append(_m)

            if _plf_candidates:
                print(f"\n  \U0001f50d Pre-order link finder: {len(_plf_candidates)} movies within {_plf_days}d window")
                _plf_found = 0
                try:
                    self.ctx.enrichment_service._init_vod_scraper()
                    _scraper = self.ctx.enrichment_service.vod_scraper
                    if _scraper and _scraper is not False:
                        for _m in _plf_candidates:
                            _title = _m.get('title', '')
                            _year = _m.get('year', '')
                            _director = _m.get('crew', {}).get('director')
                            _existing_pol = _m.get('pre_order_links', [])
                            _has_amz = any('amazon' in p.get('service', '').lower() for p in _existing_pol)
                            _has_fan = any('fandango' in p.get('service', '').lower() for p in _existing_pol)
                            _found_any = False

                            if not _has_amz:
                                try:
                                    _amz_link = _scraper.find_amazon_link(_title, _year, _director)
                                    if _amz_link:
                                        _m.setdefault('pre_order_links', []).append({
                                            'service': 'Amazon',
                                            'link': _amz_link,
                                            'type': 'pre_order'
                                        })
                                        print(f"      \u2713 {_title}: Amazon found")
                                        _found_any = True
                                    else:
                                        print(f"      \u00b7 {_title}: Amazon not found")
                                except Exception as _e:
                                    print(f"      \u2717 {_title}: Amazon error \u2014 {_e}")

                            if not _has_fan:
                                try:
                                    _fan_link = _scraper.find_fandango_link(_title, _year, _director)
                                    if _fan_link:
                                        _m.setdefault('pre_order_links', []).append({
                                            'service': 'Fandango At Home',
                                            'link': _fan_link,
                                            'type': 'pre_order'
                                        })
                                        print(f"      \u2713 {_title}: Fandango found")
                                        _found_any = True
                                    else:
                                        print(f"      \u00b7 {_title}: Fandango not found")
                                except Exception as _e:
                                    print(f"      \u2717 {_title}: Fandango error \u2014 {_e}")

                            if _found_any:
                                _plf_found += 1
                    else:
                        self.ctx.logger.warning("Pre-order link finder: VOD scraper unavailable, skipping")

                except Exception as _plf_err:
                    self.ctx.logger.warning(f"Pre-order link finder error: {_plf_err}")

                if _plf_found:
                    print(f"  \U0001f50d Link finder: {_plf_found}/{len(_plf_candidates)} pre-order movies got new links")

            # Load tracking database early — needed by pre-order catch-up below
            tracking_data = self.ctx.storage.load_all_movies()

            # Catch-up: retry movies with failed/incomplete enrichment
            # NOTE: 'completed' movies with gaps are NOT retried here -- cosmetic gaps
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
                    if movie.get('_buyonly_preorder'):
                        dd = movie.get('digital_date', '')
                        if not dd or dd > today_catchup:
                            continue  # Future or no date — skip (normal behavior)

                        # Date passed — check if pre_order_links exist
                        pol = movie.get('pre_order_links', [])
                        if pol:
                            # Links exist — date was wrong, clear it, keep as pre-order
                            movie['digital_date'] = ''
                            movie.pop('_digital_date_source', None)
                            if tracking_data and tracking_data.get('movies', {}).get(movie_id):
                                tracking_data['movies'][movie_id].pop('digital_date', None)
                                tracking_changed = True
                            print(f"  \U0001f3f7\ufe0f  {movie.get('title')} \u2014 date {dd} passed but links exist, clearing date")
                            continue  # Stay as pre-order, skip catch-up
                        else:
                            # No links AND date passed — revert to tracking
                            movie.pop('_is_preorder', None)
                            movie.pop('_buyonly_preorder', None)
                            movie.pop('digital_date', None)
                            movie.pop('_digital_date_source', None)
                            movie['status'] = 'tracking'
                            if tracking_data and tracking_data.get('movies', {}).get(movie_id):
                                tracking_data['movies'][movie_id]['status'] = 'tracking'
                                tracking_data['movies'][movie_id].pop('_buyonly_preorder', None)
                                tracking_data['movies'][movie_id].pop('digital_date', None)
                                tracking_changed = True
                            print(f"  \U0001f504 {movie.get('title')} \u2014 date {dd} passed, no links, reverting to tracking")
                            continue
                    dd = movie.get('digital_date', '')
                    if dd > today_catchup:
                        continue  # Future -- skip enrichment (link scan handles these)
                    # Date arrived -- no longer a pre-order
                    movie.pop('_is_preorder', None)
                    movie.pop('pre_order_links', None)
                    print(f"  \U0001f3f7\ufe0f  {movie.get('title')} \u2014 pre-order ended (date {dd})")
                    # Fall through to normal catch-up -> enrich or revert like any movie
                digital_date = movie.get('digital_date', '')
                status = movie.get('_enrichment_status', '')
                attempts = movie.get('_enrichment_attempts', 0)
                if attempts >= MAX_ENRICHMENT_ATTEMPTS:
                    continue
                # Never attempted -- wider 30-day window since these were missed entirely
                if not status and not movie.get('enriched', True):
                    if digital_date >= catchup_cutoff:
                        catchup_ids.append(movie_id)
                # Retry failed/error/timeout/pending -- exponential backoff
                elif status in ('pending', 'failed', 'error', 'timeout'):
                    last_attempt = movie.get('_last_enrichment_attempt', '')
                    if not last_attempt:
                        # Legacy movie with no timestamp -- retry now
                        catchup_ids.append(movie_id)
                    elif attempts > 0 and attempts - 1 < len(RETRY_BACKOFF_DAYS):
                        wait_days = RETRY_BACKOFF_DAYS[attempts - 1]
                        next_retry = (datetime.strptime(last_attempt, '%Y-%m-%d') + timedelta(days=wait_days)).strftime('%Y-%m-%d')
                        if today_catchup >= next_retry:
                            catchup_ids.append(movie_id)

            movie_ids_to_enrich.extend(catchup_ids)

            # Enforce batch limit -- new discoveries take priority over catch-up retries
            new_count = len(movie_ids_to_enrich) - len(catchup_ids)
            if len(movie_ids_to_enrich) > MAX_ENRICHMENT_BATCH:
                dropped = len(movie_ids_to_enrich) - MAX_ENRICHMENT_BATCH
                movie_ids_to_enrich = movie_ids_to_enrich[:MAX_ENRICHMENT_BATCH]
                print(f"  \u26a0\ufe0f Batch limit: {dropped} catch-up retries deferred (new discoveries prioritized)")

            if not movie_ids_to_enrich:
                print("\u2705 No movies to enrich (no new arrivals, no catch-up needed)")
                # Still purge any reverted/removed movies from prior runs
                self.host.purge_removed_movies()
                return 0

            catchup_used = len(movie_ids_to_enrich) - new_count
            print(f"\U0001f3af Enrichment queue: {new_count} new + {catchup_used} catch-up = {len(movie_ids_to_enrich)} total")

        # Preload IMDb dataset so first movie isn't penalized
        self.host._load_imdb_dataset()

        # Batch path loads tracking_data before catch-up loop; single-movie path skips that
        if tracking_data is None:
            tracking_data = self.ctx.storage.load_all_movies()
        if not tracking_data:
            print("\u274c Could not load movie tracking database")
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
                print(f"  \u23f0 Enrichment loop exceeded {ENRICHMENT_LOOP_TIMEOUT_MINUTES} min \u2014 stopping. {_remaining} remaining movies will be retried next run.")
                deferred_details.append(_deferred_entry(f'({_remaining} movies)', 'loop_timeout'))
                break

            movie_id = str(movie_id)  # Ensure consistent string format for lookup
            if movie_id not in movie_lookup:
                print(f"  \u26a0\ufe0f Movie {movie_id} not found in data.json - skipping")
                deferred_details.append(_deferred_entry(f'ID:{movie_id}', 'not_in_data_json'))
                continue

            if movie_id not in tracking_data.get('movies', {}):
                print(f"  \u26a0\ufe0f Movie {movie_id} not found in tracking database - skipping")
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
                    movie_details = self.host.get_tv_details(numeric_id)
                else:
                    movie_details = self.host.get_movie_details(movie_id)
                if not movie_details:
                    existing_movies[movie_index]['_enrichment_status'] = 'failed'
                    print(f"  \u2717 Could not fetch TMDB details for {movie_data.get('title', movie_id)} \u2014 marked failed for retry")
                    deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), 'tmdb_fetch_failed', movie_index, tracking_data['movies'].get(movie_id)))
                    continue

                # JustWatch pre-verification: confirm the movie is on our target platforms
                # BEFORE investing time in full enrichment (RT, Wiki, trailers, etc.).
                # Discovery is binary (any TMDB provider = discovered); this step handles
                # platform filtering. If JustWatch can't confirm valid platforms -> revert
                # to tracking with a note for the daily launch report.
                #
                # Manually-added movies and movies with watch link overrides skip JW
                # pre-check entirely -- curator decision overrides JustWatch verification.
                _title = existing_movies[movie_index].get('title', movie_data.get('title', ''))
                _year = movie_data.get('year')
                _original_title = existing_movies[movie_index].get('original_title')
                _director = existing_movies[movie_index].get('crew', {}).get('director') if existing_movies[movie_index].get('crew') else None
                _content_type_jw = 'tv' if str(movie_id).startswith('tv_') else 'movie'
                _is_manual = (movie_data.get('_added_manually')
                              or existing_movies[movie_index].get('_added_manually'))
                _has_override = str(movie_id) in self.host.watch_links_overrides
                _jw_verified = False
                _revert_reason = 'justwatch_error'
                try:
                    if not hasattr(self.ctx.enrichment_service, '_justwatch_client') or self.ctx.enrichment_service._justwatch_client is None:
                        from pipeline.justwatch import JustWatchClient
                        self.ctx.enrichment_service._justwatch_client = JustWatchClient(logger=self.ctx.logger)
                    _amazon_tag = self.ctx.enrichment_service._get_amazon_affiliate_tag()
                    _excl_list = self.ctx.enrichment_service.config.get('tracking', {}).get('excluded_services', ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play', 'Shahid VIP', 'Viki', 'Futo'])
                    _jw_result = self.ctx.enrichment_service._justwatch_client.verify_availability(
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
                            self.ctx.enrichment_service.watch_links_cache[str(movie_id)] = {
                                'links': _wl,
                                'cached_at': datetime.now().isoformat(),
                                'source': 'justwatch_pre_verification'
                            }
                        # Clear revert history -- movie now has valid providers
                        tracking_data['movies'][movie_id].pop('_jw_reverted_at', None)
                        tracking_data['movies'][movie_id].pop('_jw_revert_reason', None)
                        tracking_data['movies'][movie_id].pop('_jw_revert_count', None)
                        # Record JW-discovered English title when it differs from ours
                        _jw_title = _jw_result.get('jw_title', '')
                        if _jw_title and _jw_title.lower() != _title.lower():
                            _cur_orig = existing_movies[movie_index].get('original_title', '')
                            if not _cur_orig or _cur_orig.lower() == _title.lower():
                                existing_movies[movie_index]['title'] = _jw_title
                                self.ctx.logger.info(f"JustWatch revealed English title for {_title}: '{_jw_title}'")

                        # Pre-order detection: buy-only on JustWatch is a pre-order signal.
                        # Manual overrides apply regardless of buy-only status.
                        _po_overrides = self.ctx.config.get('preorder_overrides', {})
                        _po_override = _po_overrides.get(str(movie_id))
                        if _po_override is True:
                            existing_movies[movie_index]['_is_preorder'] = True
                            print(f"  \U0001f3f7\ufe0f  {_title} \u2014 flagged as pre-order (manual override)")
                        elif _po_override is False:
                            existing_movies[movie_index].pop('_is_preorder', None)
                        elif _jw_result.get('buy_only'):
                            _bo_detect = self.discoverer._detect_buyonly_preorder(_jw_result, movie_id, _title)

                            if _bo_detect['is_preorder']:
                                existing_movies[movie_index]['_is_preorder'] = True
                                existing_movies[movie_index]['_buyonly_preorder'] = True
                                _jw_links = _jw_result.get('watch_links', {})
                                if _jw_links.get('vod'):
                                    # Filter out physical media (DVD/Blu-ray) — NRW is digital-only
                                    _vod_filtered = [v for v in _jw_links['vod']
                                                     if 'dvd' not in v.get('service', '').lower()
                                                     and 'blu-ray' not in v.get('service', '').lower()]
                                    if _vod_filtered:
                                        existing_movies[movie_index]['pre_order_links'] = _vod_filtered

                                if _bo_detect['preorder_date']:
                                    existing_movies[movie_index]['digital_date'] = _bo_detect['preorder_date']
                                    existing_movies[movie_index]['_digital_date_source'] = 'tmdb_type4'
                                else:
                                    existing_movies[movie_index].pop('digital_date', None)
                                    existing_movies[movie_index].pop('_digital_date_source', None)

                                # Clear cached JW links -- pre-orders use pre_order_links, not watch_links
                                self.ctx.enrichment_service.watch_links_cache[str(movie_id)] = {
                                    'links': {'streaming': [], 'vod': []},
                                    'cached_at': datetime.now().isoformat(),
                                    'source': 'buyonly_preorder_empty'
                                }

                                # Soft revert tracking -- stay in tracking for continued polling
                                tracking_data['movies'][movie_id]['status'] = 'tracking'
                                tracking_data['movies'][movie_id]['_buyonly_preorder'] = True
                                tracking_data['movies'][movie_id].pop('digital_date', None)
                                tracking_changed = True

                                _bo_dd = f", date: {_bo_detect['preorder_date']}" if _bo_detect['preorder_date'] else ", no date"
                                print(f"  \U0001f3f7\ufe0f  {_title} \u2014 pre-order (buy-only{_bo_dd}) \u2192 tracking + wall")
                            else:
                                # Genuine buy-only release confirmed by page check
                                existing_movies[movie_index]['_buyonly_verified'] = True
                                if _bo_detect['type4_date']:
                                    existing_movies[movie_index]['digital_date'] = _bo_detect['type4_date']
                                    existing_movies[movie_index]['_digital_date_source'] = 'tmdb_type4'
                        else:
                            # Not buy-only anymore -- clear pre-order flag if previously set
                            # BUT only if digital_date has passed (future-dated = still a pre-order)
                            if existing_movies[movie_index].get('_is_preorder'):
                                dd = existing_movies[movie_index].get('digital_date', '')
                                today_str = datetime.now().strftime('%Y-%m-%d')
                                if dd <= today_str:
                                    existing_movies[movie_index].pop('_is_preorder', None)
                                    print(f"  \U0001f3f7\ufe0f  {_title} \u2014 pre-order flag cleared (date passed, no longer buy-only)")
                                else:
                                    print(f"  \U0001f3f7\ufe0f  {_title} \u2014 keeping pre-order (date {dd} still future despite JW not buy-only)")

                except Exception as _jw_err:
                    self.ctx.logger.warning(f"JustWatch pre-check error for {_title}: {_jw_err} \u2014 proceeding with enrichment")

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
                        print(f"  \U0001f504 {_title} \u2014 JustWatch pre-check: {_revert_reason} \u2192 reverted to tracking")
                    deferred_details.append(_deferred_entry(_title, f'jw_revert:{_revert_reason}', movie_index, tracking_data['movies'].get(movie_id)))
                    signal.alarm(0)
                    continue
                elif not _jw_verified:
                    _skip_reason = 'manual add' if _is_manual else 'watch link override'
                    print(f"  \u23ed\ufe0f  {_title} \u2014 JW pre-check failed but skipping revert ({_skip_reason})")

                # Propagate _added_manually from data.json entry to movie_data so
                # get_enrichment_only_fields can see it (tracking save may lose the flag)
                if existing_movies[movie_index].get('_added_manually'):
                    movie_data['_added_manually'] = True

                # Runtime gate: skip enrichment for short films that bypassed intake
                # (TMDB had null runtime at intake, but now reports below minimum).
                # Trust data.json runtime if it's higher than TMDB (manual correction).
                _runtime_tmdb = movie_details.get('runtime')
                _runtime_local = existing_movies[movie_index].get('runtime')
                _runtimes = [r for r in [_runtime_tmdb, _runtime_local] if r]
                _runtime = max(_runtimes) if _runtimes else None
                if _runtime_local and _runtime_tmdb and _runtime_local > _runtime_tmdb:
                    movie_details['runtime'] = _runtime_local  # propagate fix into enrichment
                _min_runtime = self.ctx.config.get('intake', {}).get('min_runtime', 60)
                if _runtime and _runtime < _min_runtime:
                    existing_movies[movie_index]['_enrichment_status'] = 'under_60min'
                    print(f"  ⏩ {_title} — {_runtime}min < {_min_runtime}min minimum, skipping enrichment")
                    deferred_details.append(_deferred_entry(_title, 'under_60min', movie_index, tracking_data['movies'].get(movie_id)))
                    signal.alarm(0)
                    continue

                # Get enrichment fields only
                _movie_start = time.time()
                enrichment_fields = self.get_enrichment_only_fields(movie_id, movie_data, movie_details, force_refresh=False)
                _movie_elapsed = time.time() - _movie_start
                if _movie_elapsed > 90:
                    print(f"  \u26a0\ufe0f {movie_data.get('title', movie_id)} took {_movie_elapsed:.0f}s (slow)", flush=True)
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
                    # buy-only detection cleared the cache -- wipe them so the site
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
                    # BUT only if digital_date has actually passed -- future-dated movies
                    # with links are still pre-orders (the links are purchase pre-order URLs)
                    # Buy-only pre-orders never clear here -- they wait for discovery to find rent/streaming
                    if has_real_links and existing_movies[movie_index].get('_is_preorder') and not existing_movies[movie_index].get('_buyonly_preorder'):
                        dd = existing_movies[movie_index].get('digital_date', '')
                        today_str = datetime.now().strftime('%Y-%m-%d')
                        if dd <= today_str:
                            existing_movies[movie_index].pop('_is_preorder', None)
                            print(f"  \U0001f3f7\ufe0f  {_title} \u2014 pre-order flag cleared (date passed, has real links)")
                        else:
                            # Future date -- links are pre-order purchase URLs, keep flag
                            # Filter out physical media (DVD/Blu-ray) — NRW is digital-only
                            _vod_po = [v for v in wl.get('vod', [])
                                       if 'dvd' not in v.get('service', '').lower()
                                       and 'blu-ray' not in v.get('service', '').lower()]
                            if _vod_po:
                                existing_movies[movie_index]['pre_order_links'] = _vod_po
                            print(f"  \U0001f3f7\ufe0f  {_title} \u2014 keeping pre-order (date {dd} still future, links stored as pre_order_links)")

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
                        print(f"  \u26a0 {movie_data.get('title')} - WARNING: {providers_rent_buy} providers but 0 watch links")
                    else:
                        print(f"  \u2713 {movie_data.get('title')} - Links: {watch_links_count}")
                    enriched_count += 1
                else:
                    # Mark enrichment status as failed but keep movie in data.json
                    existing_movies[movie_index]['_enrichment_status'] = 'failed'
                    print(f"  \u2717 Enrichment failed for {movie_data.get('title')}")
                    deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), 'enrichment_failed', movie_index, tracking_data['movies'].get(movie_id)))
                    self._error_details.append({
                        'timestamp': datetime.now().isoformat(),
                        'title': movie_data.get('title', str(movie_id)),
                        'source': self._current_enrichment_step or 'unknown',
                        'error_type': 'enrichment_failed',
                        'error_message': 'All enrichment sources returned empty',
                    })

            except TimeoutError:
                _step = self._current_enrichment_step or 'unknown'
                print(f"  \u23f0 {movie_data.get('title', movie_id)} timed out after {_PER_MOVIE_TIMEOUT_S}s at step '{_step}' \u2014 will retry next run")
                if movie_index < len(existing_movies):
                    existing_movies[movie_index]['_enrichment_status'] = 'timeout'
                deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), f'timeout:at_{_step}', movie_index, tracking_data['movies'].get(movie_id)))
                self._error_details.append({
                    'timestamp': datetime.now().isoformat(),
                    'title': movie_data.get('title', str(movie_id)),
                    'source': _step,
                    'error_type': 'TimeoutError',
                    'error_message': f'Exceeded {_PER_MOVIE_TIMEOUT_S}s at step {_step}',
                })
                # Reset Playwright singleton so next movie gets a clean browser
                try:
                    from playwright_manager import PlaywrightManager
                    PlaywrightManager().cleanup()
                    PlaywrightManager._instance = None
                except Exception:
                    pass
                for _attr in ('streaming_scraper', 'rt_scraper', 'vod_scraper', 'trailer_finder'):
                    setattr(self.host, _attr, None)
            except Exception as e:
                # Mark enrichment status as error but keep movie in data.json
                if movie_index < len(existing_movies):
                    existing_movies[movie_index]['_enrichment_status'] = 'error'
                print(f"  \u2717 Error enriching {movie_data.get('title', movie_id)}: {e}")
                deferred_details.append(_deferred_entry(movie_data.get('title', str(movie_id)), f'error:{type(e).__name__}', movie_index, tracking_data['movies'].get(movie_id)))
                self._error_details.append({
                    'timestamp': datetime.now().isoformat(),
                    'title': movie_data.get('title', str(movie_id)),
                    'source': self._current_enrichment_step or 'unknown',
                    'error_type': type(e).__name__,
                    'error_message': str(e)[:500],
                })
            finally:
                signal.alarm(0)  # Always cancel the per-movie alarm

        # Sync enriched flag to movie_tracking.json + zero-link revert
        try:
            _enrich_success = 0
            _enrich_reverted = 0
            _reverted_details = []
            # NOTE: do NOT reset tracking_changed here — earlier phases (catch-up, main loop)
            # may have already set it True. Resetting would silently discard those changes.
            for mid in movie_ids_to_enrich:
                mid = str(mid)
                if mid in movie_lookup:
                    movie = existing_movies[movie_lookup[mid]]
                    if movie.get('_enrichment_status') == 'completed' and mid in tracking_data.get('movies', {}):
                        tracking_data['movies'][mid]['enriched'] = True
                        tracking_data['movies'][mid]['enrichment_date'] = datetime.now().strftime('%Y-%m-%d')
                        tracking_changed = True

                        # Zero watch links after enrichment -- revert to tracking
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
                                print(f"  \u23ed\ufe0f  {_title_zl} \u2014 zero links but pre-order (future date {_dd_zl}), keeping")
                            # Guard: virtual screenings (own lifecycle)
                            elif movie.get('categories', {}).get('is_virtual_screening'):
                                _enrich_success += 1
                                print(f"  \u23ed\ufe0f  {_title_zl} \u2014 zero links but virtual screening, keeping")
                            # Guard: manually-added movies (curator decision)
                            elif movie.get('_added_manually') or tracking_data['movies'][mid].get('_added_manually'):
                                _enrich_success += 1
                                print(f"  \u23ed\ufe0f  {_title_zl} \u2014 zero links but manually added, keeping")
                            # Guard: watch link overrides
                            elif str(mid) in self.host.watch_links_overrides:
                                _enrich_success += 1
                                print(f"  \u23ed\ufe0f  {_title_zl} \u2014 zero links but has override, keeping")
                            else:
                                # Revert to tracking -- movie will be purged from data.json
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
                                print(f"  \U0001f504 {_title_zl} \u2014 zero watch links \u2192 reverted to tracking (count: {_zl_revert_count})")
                                deferred_details.append(_deferred_entry(_title_zl, 'zero_watch_links', movie_lookup.get(mid), tracking_data['movies'].get(mid)))
                    else:
                        _enrich_success += 1
            _enrich_attempted = _enrich_success + _enrich_reverted
            if tracking_changed:
                self.ctx.storage.atomic_write_json(tracking_data, 'movie_tracking.json', backup=True)
                if _enrich_reverted:
                    print(f"\U0001f4dd Enrichment: {_enrich_attempted} attempted, {_enrich_success} succeeded, {_enrich_reverted} reverted (zero links)")
                    for _rv_title, _rv_source, _rv_count in _reverted_details:
                        _rv_via = 'Type 4' if _rv_source == 'tmdb_type4' else 'providers' if _rv_source == 'provider_availability_check' else _rv_source
                        _rv_suffix = f' (attempt #{_rv_count})' if _rv_count > 1 else ''
                        print(f"   \u21b3 {_rv_title} \u2014 discovered via {_rv_via}, no deeplinks found{_rv_suffix}")
                else:
                    print(f"\U0001f4dd Enrichment: {_enrich_attempted} movies successfully enriched")
        except Exception as e:
            print(f"\u26a0\ufe0f Could not update movie_tracking.json: {e}")

        # Categorize all movies (backfills any missing categories from prior runs)
        existing_movies, _ = self.host.apply_admin_overrides(existing_movies)

        # Save enrichment results to data.json BEFORE trailer hosting
        # Uses safe save with reload-merge to prevent lost updates
        if not self.host._safe_save_data_json(display_data, existing_movies, label="enrichment"):
            return 0
        print(f"\u2705 Enriched {enriched_count}/{len(movie_ids_to_enrich)} movies ({len(existing_movies)} total, was {_initial_movie_count} at load)")

        # Post-enrichment: Host trailers for newly enriched movies
        trailer_config = self.ctx.config.get('trailer_hosting', {})
        if trailer_config.get('enabled', False) and trailer_config.get('pipeline_integration', False):
            print("\U0001f3ac Hosting trailers for newly enriched movies...")
            hosted_count = 0
            for movie_id in movie_ids_to_enrich:
                movie_id = str(movie_id)
                if movie_id not in movie_lookup:
                    continue
                movie_index = movie_lookup[movie_id]
                movie = existing_movies[movie_index]
                trailer_url = movie.get('links', {}).get('trailer')
                if trailer_url and not movie.get('links', {}).get('trailer_hosted'):
                    hosted_url = self.host.host_trailer_for_movie(
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
                self.host._safe_save_data_json(display_data, existing_movies, label="trailer_hosting")
                print(f"  \u2713 Hosted {hosted_count} trailer(s)")
            else:
                print("  No new trailers to host")
        else:
            print("\U0001f3ac Trailer hosting: disabled (config)")

        # Disk-level purge: remove reverted/removed movies from the saved data.json.
        # Runs AFTER all safe_save calls because the merge-rescue in safe_save can
        # re-add reverted movies from disk. The no-argument form reads data.json,
        # filters out reverted/removed movies, archives them, and writes back clean.
        self.host.purge_removed_movies()

        # Write enrichment metrics
        try:
            enrichment_metrics = {
                "timestamp": datetime.now().isoformat(),
                "movies_requested": len(movie_ids_to_enrich),
                "movies_enriched": enriched_count,
                "movies_deferred": len(movie_ids_to_enrich) - enriched_count,
                "deferred_details": deferred_details,
                "enrichment_duration_seconds": round(time.time() - _enrich_start, 2),
                "error_details": self._error_details[:100],
                "total_errors": len(self._error_details),
            }
            with open('metrics/enrichment_run.json', 'w') as f:
                json.dump(enrichment_metrics, f, indent=2)
        except Exception as e:
            print(f"\u26a0\ufe0f Could not write enrichment metrics: {e}")

        # Purge reverted/removed movies from the in-memory list and archive them.
        # Must happen BEFORE any subsequent save to prevent the merge-rescue from
        # re-adding purged movies back to disk.
        existing_movies[:] = self.host.purge_removed_movies(existing_movies) or existing_movies

        return enriched_count
