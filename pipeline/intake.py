"""
Movie Intake — discovers new movies from TMDB and adds them to tracking.

Handles three intake passes:
  A) Direct-to-digital releases (release_date + type=4)
  B) Theatrical releases (primary_release_date)
  C) Festival premieres (with_release_type=1 in festival regions)

Plus miniseries intake (TMDB /discover/tv with type=Miniseries).
"""

import json
import os
import time
import requests
from datetime import date, datetime, timedelta


class MovieIntake:
    """Intake new movies from TMDB into movie_tracking.json."""

    def __init__(self, ctx):
        """
        Args:
            ctx: PipelineContext with config, logger, storage, tmdb_key, intake_stats
        """
        self.config = ctx.config
        self.logger = ctx.logger
        self.storage = ctx.storage
        self.tmdb_key = ctx.tmdb_key
        self.intake_stats = ctx.intake_stats

    # ------------------------------------------------------------------
    # Intake state persistence
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Main intake entry points
    # ------------------------------------------------------------------

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
        intake_config = self.config.get('intake', {})

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
                    'intake_date': datetime.now().strftime('%Y-%m-%d'),
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
        if not self.storage.atomic_write_json(db, 'movie_tracking.json', backup=True):
            self.logger.error("Failed to save movie_tracking.json after miniseries intake")

        print(f"\n📊 Miniseries intake complete: {new_series_added} new series added")
        self.logger.info(f"Miniseries intake: {new_series_added} new series added")

        return new_series_added

    # ------------------------------------------------------------------
    # Internal intake helpers
    # ------------------------------------------------------------------

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
                        'intake_date': datetime.now().strftime('%Y-%m-%d'),
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

    # ------------------------------------------------------------------
    # Festival intake
    # ------------------------------------------------------------------

    def _generate_editions_from_templates(self, year):
        """Auto-generate festival editions for a year from festival_templates config.

        Used as fallback when no explicit editions_YYYY section exists.
        Templates define typical_start [month, day] and duration_days for each festival.

        Returns:
            dict: Festival editions in the same format as editions_YYYY config sections,
                  or empty dict if no templates defined.
        """
        templates = self.config.get('festivals', {}).get('festival_templates', {})
        if not templates:
            return {}

        editions = {}
        for fest_key, tmpl in templates.items():
            try:
                month, day = tmpl['typical_start']
                start = date(year, month, day)
                end = start + timedelta(days=tmpl['duration_days'])
                editions[fest_key] = {
                    'name': tmpl['name'],
                    'region': tmpl['region'],
                    'start': start.strftime('%Y-%m-%d'),
                    'end': end.strftime('%Y-%m-%d'),
                }
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning(f"Bad festival template '{fest_key}': {e}")
                continue

        if editions:
            self.logger.info(f"Auto-generated {len(editions)} festival editions for {year} from templates")
        return editions

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

        # Check current year's festivals (explicit editions override templates)
        editions_key = f'editions_{current_year}'
        editions = festivals_config.get(editions_key, {})

        if not editions:
            editions = self._generate_editions_from_templates(current_year)

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
                editions = self._generate_editions_from_templates(year)

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
                        'intake_date': datetime.now().strftime('%Y-%m-%d'),
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
