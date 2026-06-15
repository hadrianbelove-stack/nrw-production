"""
Provider Discovery — checks tracking movies for digital availability.

Handles three phases:
  - check_tracking_movies: TMDB Type 4 + provider availability polling
  - daily_gap_fill: Re-queries JustWatch for all wall movies, finds late services,
    graduates pre-orders, retroactively flags buy-only pre-orders
  - reenrich_watch_link_gaps: Re-enriches movies with missing/unverified watch links

Also contains the buy-only pre-order detection pipeline:
  _detect_buyonly_preorder → _check_preorder_page (Playwright store visit)
"""

import json
import os
import random
import re
import time
import requests
from datetime import datetime, timedelta


class ProviderDiscoverer:
    """Discovers provider availability for tracking movies."""

    def __init__(self, ctx, host):
        """
        Args:
            ctx: PipelineContext with config, logger, storage, enrichment_service, tmdb_key
            host: DataGenerator instance (provides shared utilities like
                  fetch_tmdb_type4_date, simplify_provider_name, add_movie_to_site_immediately,
                  _transition_movie_to_available, _safe_save_data_json, find_wikipedia_url)
        """
        self.config = ctx.config
        self.logger = ctx.logger
        self.storage = ctx.storage
        self.enrichment = ctx.enrichment_service
        self.tmdb_key = ctx.tmdb_key
        self.host = host
        self._jw_client = None  # Lazy-initialized for verification gate
        self._jw_healthy = None  # JW_BREAKER: run-scoped health (None=unchecked, True/False=canary result)

    # ------------------------------------------------------------------
    # JustWatch verification gate
    # ------------------------------------------------------------------

    # JW_BREAKER: blockbuster control titles guaranteed to have US offers on
    # JustWatch. If JW can't find ANY of them, it is unreachable/blocked from
    # this environment (datacenter IP → HTTP 200 + empty results) and its "no
    # match" answers cannot be trusted. Title+year matching is enough here.
    _JW_CANARY_TITLES = [("Oppenheimer", 2023), ("Barbie", 2023), ("Dune: Part Two", 2024)]

    def _check_jw_health(self):
        """Confirm JustWatch is reachable by looking up known-available control titles.
        Result is cached for the whole run. Returns True if healthy, False if degraded."""
        if self._jw_healthy is not None:
            return self._jw_healthy
        if self._jw_client is None:
            from pipeline.justwatch import JustWatchClient
            self._jw_client = JustWatchClient(logger=self.logger)
        for _title, _year in self._JW_CANARY_TITLES:
            try:
                if self._jw_client.verify_availability(_title, _year) is not None:
                    self._jw_healthy = True
                    return True
            except Exception:
                continue
        # Every control title came back empty → JustWatch is not answering for us.
        self._jw_healthy = False
        self.logger.error(
            "JW_BREAKER: JustWatch returned no match for ALL control titles — treating "
            "as an outage. Suppressing JW reverts this run (films stay in tracking, "
            "revert counts untouched) to avoid poisoning the permanent-skip ceiling."
        )
        print("  🛑 JW_BREAKER: JustWatch appears blocked/down — suppressing reverts this run")
        return False

    def _verify_before_wall(self, movie_id, movie):
        """JustWatch pre-check before adding a movie to the wall.

        Calls verify_availability() to confirm the movie has real streaming/VOD
        links on our target platforms. Prevents movies from hitting the wall
        with zero watch links.

        Bypasses (let through without JW check):
        - Manually-added movies (_added_manually) — curator decision
        - Apple Music Live specials (_apple_music_live) — JW blind spot
        - Movies with watch_link overrides — curator decision
        - Virtual screenings (Eventive, Shift72, etc.) — own link lifecycle

        Returns:
            dict: JW result with watch_links on success, or bypass marker
            None: on failure/no match (movie stays in tracking)
        """
        title = movie.get('title', '')
        year = movie.get('year')
        content_type = 'tv' if str(movie_id).startswith('tv_') else 'movie'
        original_title = movie.get('original_title')
        tmdb_id = str(movie_id).replace('tv_', '')

        # --- Bypass checks: these movies skip JW verification ---
        if movie.get('_added_manually'):
            return {'verified': True, '_bypass': 'manual_add'}
        if movie.get('_apple_music_live'):
            return {'verified': True, '_bypass': 'apple_music_live'}
        if hasattr(self.host, 'watch_links_overrides') and str(movie_id) in self.host.watch_links_overrides:
            return {'verified': True, '_bypass': 'override'}
        # Pre-orders already on wall — date arrived, let enrichment handle them.
        # Blocking here would leave them stuck as pre-orders forever.
        if movie.get('_type4_pending') or movie.get('_is_preorder') or movie.get('_buyonly_preorder'):
            return {'verified': True, '_bypass': 'preorder_graduation'}
        # Virtual screenings (Eventive, Shift72, Sundance) have their own links, not on JW
        _vs_platforms = {'eventive', 'shift72', 'sundance'}
        all_providers = (movie.get('providers', {}).get('streaming', [])
                         + movie.get('providers', {}).get('rent', [])
                         + movie.get('providers', {}).get('buy', []))
        if any(any(vs in p.lower() for vs in _vs_platforms)
               for p in all_providers if isinstance(p, str)):
            return {'verified': True, '_bypass': 'virtual_screening'}

        # Revert ceiling: stop wasting API calls on perpetual failures
        revert_count = movie.get('_jw_revert_count', 0)
        if revert_count >= 10:
            movie['_skip_provider_discovery'] = True
            self.logger.info(f"Revert ceiling reached for {title} ({revert_count} reverts) — skipping future discovery")
            print(f"  ⛔ {title} — {revert_count} reverts, skipping permanently")
            return None

        # Lazy-init JustWatch client
        if self._jw_client is None:
            from pipeline.justwatch import JustWatchClient
            self._jw_client = JustWatchClient(logger=self.logger)

        excl_list = self.config.get('tracking', {}).get('excluded_services',
                     ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play',
                      'Shahid VIP', 'Viki', 'Futo'])
        amazon_tag = self.enrichment._get_amazon_affiliate_tag() if self.enrichment else None

        try:
            result = self._jw_client.verify_availability(
                title, year,
                excluded_services=excl_list,
                affiliate_tag=amazon_tag,
                content_type=content_type,
                original_title=original_title,
                tmdb_id=tmdb_id
            )
        except Exception as e:
            # Fail-open: if JW is down, let the movie through to enrichment
            self.logger.warning(f"JW verification error for {title}: {e} — allowing through")
            return {'verified': True, '_fail_open': True}

        if result is None or not result.get('verified'):
            # JW_BREAKER: result is None means "no match" — but a blocked/throttled
            # JustWatch returns the same thing (HTTP 200, empty results). Before we
            # revert (which inflates the revert count toward the 10-revert permanent-
            # skip ceiling), confirm JW is actually healthy. If it's down, leave the
            # movie untouched in tracking — re-checked next run, no count poisoning.
            if result is None and not self._check_jw_health():
                print(f"  ⏸ {title} — JW unreachable, leaving in tracking (no revert recorded)")
                return None
            # Increment revert count and log — always print so blocked titles are visible
            revert_count += 1
            movie['_jw_revert_count'] = revert_count
            reason = 'justwatch_no_match' if result is None else 'justwatch_no_valid_offers'
            movie['_jw_revert_reason'] = reason
            movie.setdefault('_jw_reverted_at', datetime.now().strftime('%Y-%m-%d'))
            print(f"  🚫 {title} — JW verification failed ({reason}), staying in tracking (attempt #{revert_count})")
            return None

        # Cache watch_links for enrichment to reuse (avoids redundant JW call)
        wl = result.get('watch_links', {})
        if wl and self.enrichment:
            self.enrichment.watch_links_cache[str(movie_id)] = {
                'links': wl,
                'cached_at': datetime.now().isoformat(),
                'source': 'discovery_pre_verification'
            }

        # Clear revert history on success
        movie.pop('_jw_revert_count', None)
        movie.pop('_jw_revert_reason', None)
        movie.pop('_jw_reverted_at', None)

        return result

    # ------------------------------------------------------------------
    # Main discovery entry point
    # ------------------------------------------------------------------

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
        db = self.storage.tracking_db.load_all()
        if not db.get('movies'):
            print("⚠️  No movies in tracking database")
            return 0

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
            movie = item[1]
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
        checked = 0
        failed = 0
        total_to_check = len(tracking_movies)
        newly_available_ids = []  # Track movie IDs that transition to available
        transition_details = []  # Breadcrumb: which movies transitioned and why
        api_errors = []  # Breadcrumb: API failures during discovery

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

                # PRIMARY: Type 4 digital release check (authoritative, gives accurate date)
                type4_found = False
                if movie['status'] == 'tracking':
                    today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

                    if movie.get('_type4_pending'):
                        # Already have a Type 4 date stored — check if it has arrived
                        pending_date = movie.get('digital_date')
                        if pending_date:
                            try:
                                pending_dt = datetime.strptime(pending_date, '%Y-%m-%d')
                                if pending_dt <= today_dt:
                                    # Date arrived — verify JW before transitioning
                                    jw_result = self._verify_before_wall(movie_id, movie)
                                    if jw_result is None:
                                        type4_found = True  # Don't fall through to provider check
                                        continue
                                    self.host._transition_movie_to_available(
                                        movie_id, movie, 'tmdb_type4', newly_available_ids)
                                    newly_digital += 1
                                    transition_details.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'source': 'tmdb_type4', 'timestamp': datetime.now().isoformat()})
                                    self.logger.info(f"Type 4 pending released: {movie['title']} — {pending_date}")
                                    print(f"  📅 {movie['title']} — pending Type 4 arrived ({pending_date})")
                                else:
                                    days_until = (pending_dt - today_dt).days
                                    # Ensure pending movie is on wall as pre-order (migrates existing pending movies)
                                    if not movie.get('_is_preorder'):
                                        movie['_is_preorder'] = True
                                        self.host.add_movie_to_site_immediately(movie_id, movie)
                                        newly_available_ids.append(str(movie_id))  # Enrich on entry (trailers, Wiki, RT)
                                        print(f"  🏷️ {movie['title']} — added to wall as pre-order ({pending_date})")
                                    self.logger.debug(f"Type 4 still pending: {movie['title']} — {days_until}d until {pending_date}")
                            except ValueError:
                                pass
                            type4_found = True  # Skip provider check — valid pending date
                        else:
                            # Bad state: pending flag with no date — clear and fall through to provider check
                            movie.pop('_type4_pending', None)
                            self.logger.warning(f"Cleared _type4_pending with no digital_date: {movie.get('title', movie_id)}")

                    else:
                        # Fresh lookup — call TMDB Type 4 API
                        type4_date = self.host.fetch_tmdb_type4_date(movie_id)
                        if type4_date:
                            try:
                                type4_dt = datetime.strptime(type4_date, '%Y-%m-%d')
                                if type4_dt <= today_dt:
                                    # Past or today — verify JW before transitioning
                                    movie['digital_date'] = type4_date
                                    jw_result = self._verify_before_wall(movie_id, movie)
                                    if jw_result is None:
                                        type4_found = True  # Don't fall through to provider check
                                        continue
                                    self.host._transition_movie_to_available(
                                        movie_id, movie, 'tmdb_type4', newly_available_ids)
                                    newly_digital += 1
                                    transition_details.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'source': 'tmdb_type4', 'timestamp': datetime.now().isoformat()})
                                    type4_found = True
                                    self.logger.info(f"Type 4 discovery: {movie['title']} — digital release {type4_date}")
                                    print(f"  📅 {movie['title']} — digital release {type4_date}")
                                else:
                                    # Future date — add to wall as pre-order, enrich immediately (trailers, Wiki, RT)
                                    days_until = (type4_dt - today_dt).days
                                    movie['digital_date'] = type4_date
                                    movie['_discovery_source'] = 'tmdb_type4'
                                    movie['_type4_pending'] = True
                                    movie['_is_preorder'] = True
                                    type4_found = True  # Skip provider check
                                    self.host.add_movie_to_site_immediately(movie_id, movie)
                                    newly_available_ids.append(str(movie_id))  # Enrich on entry (trailers, Wiki, RT)
                                    self.logger.info(f"Type 4 future: {movie['title']} — {days_until}d until {type4_date} [pre-order on wall]")
                                    print(f"  ⏳ {movie['title']} — digital in {days_until}d ({type4_date}) [pre-order on wall]")
                            except ValueError:
                                pass

                # SECONDARY: Provider availability check (for ~44% of movies without Type 4)
                if not type4_found and movie['status'] == 'tracking' and not movie.get('_skip_provider_discovery'):
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
                                api_errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': 'rate_limit', 'status_code': 429, 'timestamp': datetime.now().isoformat()})
                                time.sleep(wait_time)
                                continue
                            else:
                                self.logger.warning(f"HTTP {response.status_code} for {movie['title']}")
                                api_errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': 'http_error', 'status_code': response.status_code, 'timestamp': datetime.now().isoformat()})
                                break
                        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                            wait_time = (2 ** attempt) + random.uniform(0, 1)
                            if attempt < max_retries - 1:
                                print(f"  Timeout/connection error for {movie['title']}, retrying in {wait_time:.1f}s")
                                time.sleep(wait_time)
                                continue
                            else:
                                self.logger.warning(f"Failed after {max_retries} attempts for {movie['title']}: {type(e).__name__}")
                                api_errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': type(e).__name__, 'status_code': None, 'timestamp': datetime.now().isoformat()})
                                failed += 1
                                break
                        except requests.exceptions.RequestException as e:
                            self.logger.warning(f"Request error for {movie['title']}: {type(e).__name__}")
                            api_errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': type(e).__name__, 'status_code': None, 'timestamp': datetime.now().isoformat()})
                            failed += 1
                            break

                    if data:
                        us = data.get('results', {}).get('US', {})

                        # Get all provider types
                        rent_providers = us.get('rent', [])
                        buy_providers = us.get('buy', [])
                        stream_providers = us.get('flatrate', [])

                        # Extract provider names — NO exclusion filter here.
                        rent_names = [p.get('provider_name', '') for p in rent_providers]
                        buy_names = [p.get('provider_name', '') for p in buy_providers]
                        stream_names = [p.get('provider_name', '') for p in stream_providers]

                        has_providers = bool(rent_names or buy_names or stream_names)

                        # Virtual screening platforms (Eventive, Shift72, Sundance) may not appear
                        # in TMDB provider data. If tracking already has a VS platform AND a cached
                        # or override link exists AND the link is still live, force transition.
                        _vs_platforms = {'eventive', 'shift72', 'sundance'}
                        _orig_providers = (movie.get('providers', {}).get('streaming', [])
                                           + movie.get('providers', {}).get('rent', [])
                                           + movie.get('providers', {}).get('buy', []))
                        _is_virtual_screening = any(
                            any(vs in p.lower() for vs in _vs_platforms)
                            for p in _orig_providers if isinstance(p, str))
                        if _is_virtual_screening and not has_providers:
                            _mid = str(movie_id)
                            # Extract the actual screening link from cache or overrides
                            _vs_link = None
                            if (hasattr(self.host, 'watch_links_overrides')
                                    and _mid in self.host.watch_links_overrides):
                                _ovr = self.host.watch_links_overrides[_mid]
                                for _v in (_ovr.get('vod') or []):
                                    _vs_link = _v.get('link')
                                    if _vs_link:
                                        break
                            if not _vs_link and (hasattr(self, 'enrichment') and self.enrichment
                                    and _mid in getattr(self.enrichment, 'watch_links_cache', {})):
                                _cached = self.enrichment.watch_links_cache[_mid]
                                for _v in (_cached.get('links', {}).get('vod') or []):
                                    _vs_link = _v.get('link')
                                    if _vs_link:
                                        break
                            # Validate the screening is still available before forcing transition
                            if _vs_link and 'eventive.org' in _vs_link:
                                try:
                                    _resp = requests.get(_vs_link, timeout=10,
                                                         headers={'User-Agent': 'Mozilla/5.0'})
                                    _nd_match = re.search(
                                        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                                        _resp.text)
                                    if _nd_match:
                                        _nd = json.loads(_nd_match.group(1))
                                        _init = _nd.get('props', {}).get('pageProps', {}).get('initialData', {})
                                        _end_time = _init.get('end_time', '')
                                        _end_in_future = False
                                        if _end_time:
                                            try:
                                                from datetime import datetime as _dt
                                                _end_dt = _dt.fromisoformat(_end_time.replace('Z', '+00:00'))
                                                _end_in_future = _end_dt > _dt.now(_end_dt.tzinfo)
                                            except (ValueError, TypeError):
                                                pass
                                        if _init.get('is_available') is True:
                                            has_providers = True
                                            movie['_virtual_screening'] = True
                                            print(f"  ✓ {movie['title']} — VS bypass: screening active ({_vs_link})")
                                        elif _end_in_future:
                                            # Upcoming/pre-order — screening hasn't started but end_time is future
                                            has_providers = True
                                            movie['_virtual_screening'] = True
                                            print(f"  ✓ {movie['title']} — VS bypass: upcoming screening (ends {_end_time[:10]})")
                                        else:
                                            _end = _end_time or 'unknown'
                                            print(f"  ⏭ {movie['title']} — VS bypass skipped: screening expired (ended {_end})")
                                    else:
                                        print(f"  ⏭ {movie['title']} — VS bypass skipped: could not parse page")
                                except requests.RequestException:
                                    print(f"  ⏭ {movie['title']} — VS bypass skipped: link unreachable")
                            elif _vs_link:
                                # Non-Eventive VS links (Shift72, etc.) — HEAD check fallback
                                try:
                                    _head = requests.head(_vs_link, timeout=10, allow_redirects=True)
                                    if _head.status_code < 400:
                                        has_providers = True
                                        movie['_virtual_screening'] = True
                                        print(f"  ✓ {movie['title']} — VS bypass: link verified ({_vs_link})")
                                    else:
                                        print(f"  ⏭ {movie['title']} — VS bypass skipped: HTTP {_head.status_code}")
                                except requests.RequestException:
                                    print(f"  ⏭ {movie['title']} — VS bypass skipped: link unreachable")

                        movie['has_providers'] = has_providers

                        if has_providers and movie['status'] == 'tracking':
                            movie['_discovery_source'] = 'provider_availability_check'

                        # DISCOVERY IS STRICTLY BINARY.
                        # Transition provider-discovered movie
                        if has_providers and movie['status'] == 'tracking':
                            # Buy-only pre-order guard: only transition if rent/streaming appeared
                            if movie.get('_buyonly_preorder'):
                                if not rent_names and not stream_names:
                                    continue  # Still buy-only — keep as pre-order on wall
                                # Rent/streaming found — clear pre-order, fall through to transition
                                movie.pop('_buyonly_preorder', None)
                                movie.pop('_is_preorder', None)
                                print(f"  ✓ {movie['title']} — buy-only pre-order graduated (rent/streaming found)")

                            if not movie.get('digital_date'):
                                # For VS bypass, use screening start_time as digital_date
                                _resolved_date = None
                                if movie.get('_virtual_screening') and _mid in getattr(self.enrichment, 'watch_links_cache', {}):
                                    _vs_cache = self.enrichment.watch_links_cache[_mid]
                                    _vs_start = _vs_cache.get('start_time', '')
                                    if _vs_start:
                                        try:
                                            _start_dt = datetime.fromisoformat(_vs_start.replace('Z', '+00:00'))
                                            _resolved_date = _start_dt.strftime('%Y-%m-%d')
                                        except (ValueError, TypeError):
                                            pass

                                # Fallback: use virtual_screening_info.available_start if already populated
                                if not _resolved_date:
                                    _vsi_start = movie.get('virtual_screening_info', {}).get('available_start')
                                    if _vsi_start:
                                        _resolved_date = _vsi_start

                                if _resolved_date:
                                    movie['digital_date'] = _resolved_date
                                    # Future screening = pre-order (hidden unless filter active)
                                    if _resolved_date > datetime.now().strftime('%Y-%m-%d'):
                                        movie['_is_preorder'] = True
                                elif not movie.get('_virtual_screening'):
                                    # Only non-VS movies get today's date as fallback;
                                    # VS movies wait for display phase to resolve from Eventive data
                                    movie['digital_date'] = datetime.now().strftime('%Y-%m-%d')
                            # For VS bypass, preserve original streaming providers (TMDB returns empty)
                            if movie.get('_virtual_screening') and not stream_names:
                                _orig_streaming = movie.get('providers', {}).get('streaming', [])
                                stream_names = _orig_streaming if _orig_streaming else stream_names
                            movie['providers'] = {
                                'rent': rent_names,
                                'buy': buy_names,
                                'streaming': stream_names
                            }

                            # JW verification gate — skip for virtual screening platforms
                            if _is_virtual_screening:
                                jw_result = {'verified': True, '_bypass': 'virtual_screening'}
                            else:
                                jw_result = self._verify_before_wall(movie_id, movie)
                                if jw_result is None:
                                    continue  # Stay in tracking

                            self.host._transition_movie_to_available(
                                movie_id, movie, 'provider_availability_check', newly_available_ids)
                            newly_digital += 1
                            transition_details.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'source': 'provider_availability_check', 'timestamp': datetime.now().isoformat()})

                            first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0] if buy_names else '?'
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
            from datetime import timezone
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
                    'jw_healthy': self._jw_healthy,  # JW_BREAKER: None=not checked, False=outage detected
                    'scan_tag': scan_tag.strip() if scan_tag else None
                },
                'transition_details': transition_details[:100],
                'total_transitions': len(transition_details),
                'api_errors': api_errors[:100],
                'total_api_errors': len(api_errors),
            }

            with open('metrics/discovery_run.json', 'w') as f:
                json.dump(discovery_run_data, f, indent=2)

            print(f"📊 Metrics saved to metrics/discovery_run.json")
            self.logger.info(f"Provider discovery metrics saved: {discovery_run_data}")

            # Write enrichment state file with newly available movie IDs
            print(f"📝 Creating enrichment state file for {len(newly_available_ids)} newly available movies")
            self.logger.info(f"Creating enrichment state file for {len(newly_available_ids)} newly available movies")

            now = datetime.now(timezone.utc)
            today_date = now.strftime('%Y-%m-%d')
            print(f"📅 State file date: {today_date}")
            self.logger.info(f"State file date: {today_date}")

            newly_available_data = {
                'date': today_date,
                'timestamp': now.isoformat(),
                'movie_ids': list(newly_available_ids),
                'count': len(newly_available_ids)
            }

            try:
                with open('metrics/newly_available.json', 'w') as f:
                    json.dump(newly_available_data, f, indent=2)

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
            for movie_id_key, movie_val in db['movies'].items():
                if (movie_val.get('status') == 'available' and
                    movie_val.get('digital_date')):
                    try:
                        digital_date = datetime.strptime(movie_val['digital_date'], '%Y-%m-%d')
                        available_movies.append((movie_id_key, movie_val, digital_date))
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
            for archive_mid, archive_movie, _ in available_movies[:batch_size]:
                to_archive[archive_mid] = archive_movie

            if to_archive:
                moved_count = self.storage.atomic_move_to_archive(to_archive)
                if moved_count > 0:
                    age_filter = f" (from last {recent_days} days)" if recent_days else ""
                    self.logger.info(f"Compaction: moved {moved_count} available movies to archive{age_filter}")
                    print(f"📦 Compaction: moved {moved_count} available movies to archive{age_filter}")

        return newly_digital

    # ------------------------------------------------------------------
    # Buy-only pre-order detection
    # ------------------------------------------------------------------

    def _check_preorder_page(self, jw_result, title):
        """
        Visit the store URL from a buy-only JW result and scan for pre-order vs available signals.

        Uses Playwright to render the actual page (needed for SPAs like Fandango and
        bot-protected sites like Amazon). Scans rendered body text for button words.

        Args:
            jw_result: JustWatch verify_availability result dict
            title: Movie title (for logging)

        Returns:
            str: 'pre-order', 'available', or None (could not determine)
        """
        # Extract the first VOD link URL from JW result
        vod_links = jw_result.get('watch_links', {}).get('vod', [])
        if not vod_links:
            return None

        url = None
        for entry in vod_links:
            if isinstance(entry, dict) and entry.get('link'):
                url = entry['link']
                break
        if not url:
            return None

        preorder_signals = ['preorder', 'available for pre-order', 'available to pre-order']
        available_signals = ['buy now', 'rent now', 'watch now']

        try:
            from playwright_manager import get_playwright_manager
            manager = get_playwright_manager()
            browser = manager.get_browser(headless=True, browser_type='chromium')

            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                extra_http_headers={'DNT': '1', 'Upgrade-Insecure-Requests': '1'}
            )

            # Stealth JS — hide automation signals
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(window, 'chrome', { get: () => ({ runtime: {} }) });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """)

            context.set_default_timeout(20000)
            page = context.new_page()

            try:
                is_amazon = 'amazon.com' in url.lower()
                is_fandango = 'fandango.com' in url.lower()

                # Navigate to the store page
                page.goto(url, wait_until='load', timeout=20000)

                # Extra wait for SPAs (Fandango) and anti-bot delays (Amazon)
                if is_fandango:
                    page.wait_for_timeout(2000)
                elif is_amazon:
                    page.wait_for_timeout(random.randint(1500, 2500))

                body_text = (page.text_content('body') or '').lower()

                # Amazon CAPTCHA detection — default to pre-order if blocked
                if is_amazon and ('captcha' in body_text or 'not a robot' in body_text or 'automated access' in body_text):
                    self.logger.info(f"Pre-order page check for {title}: Amazon CAPTCHA detected → defaulting to pre-order")
                    return 'pre-order'

                has_preorder = any(signal in body_text for signal in preorder_signals)
                has_available = any(signal in body_text for signal in available_signals)

                if has_preorder and not has_available:
                    return 'pre-order'
                elif has_available and not has_preorder:
                    return 'available'
                elif has_preorder and has_available:
                    # Both signals — pre-order takes precedence (safer)
                    return 'pre-order'
                else:
                    # Neither signal found — page may not have rendered properly
                    return None

            finally:
                page.close()
                context.close()

        except Exception as e:
            self.logger.warning(f"Pre-order page check failed for {title} ({url}): {e}")
            return None

    def _detect_buyonly_preorder(self, jw_result, movie_id, title):
        """
        Determine if a buy-only JustWatch result is a pre-order or genuine release.

        Decision logic:
        1. Manual override in config.preorder_overrides → immediate verdict
        2. Type 4 future date → pre-order (with that date)
        3. Page check (Playwright visits store page):
           - 'available' → genuine release (only way to confirm genuine)
           - 'pre-order' or inconclusive → pre-order (safer default)
        Type 4 past date alone does NOT confirm genuine — only page check does.

        Returns:
            dict: {
                'is_preorder': bool,
                'override': True|False|None (manual override value),
                'preorder_date': str|None (future Type 4 date),
                'type4_date': str|None (any Type 4 date found),
                'verified_genuine': bool (page check confirmed available),
            }
        """
        result = {
            'is_preorder': True,  # default: safer to assume pre-order
            'override': None,
            'preorder_date': None,
            'type4_date': None,
            'verified_genuine': False,
        }

        # Step 0: Manual override
        overrides = self.config.get('preorder_overrides', {})
        override_val = overrides.get(str(movie_id))
        if override_val is True:
            result['override'] = True
            result['is_preorder'] = True
            return result
        elif override_val is False:
            result['override'] = False
            result['is_preorder'] = False
            result['verified_genuine'] = True
            return result

        # Step 1: Type 4 date — provides date info, but past date alone ≠ genuine
        type4_date = self.host.fetch_tmdb_type4_date(movie_id)
        if type4_date:
            result['type4_date'] = type4_date
            try:
                t4dt = datetime.strptime(type4_date, '%Y-%m-%d')
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                if t4dt > today:
                    # Future date — definitively a pre-order
                    result['preorder_date'] = type4_date
                    result['is_preorder'] = True
                    print(f"  🏷️  {title} — buy-only, Type 4 future date ({type4_date})")
                    return result
                # Past date — informational only, still need page check
            except ValueError:
                pass

        # Step 2: Page check — the ONLY way to confirm genuine release
        page_verdict = self._check_preorder_page(jw_result, title)
        if page_verdict == 'available':
            result['is_preorder'] = False
            result['verified_genuine'] = True
            print(f"  ✓ {title} — buy-only, page confirms available")
        elif page_verdict == 'pre-order':
            result['is_preorder'] = True
            print(f"  🏷️  {title} — buy-only, page confirms pre-order")
        else:
            # Inconclusive — default to pre-order (safer)
            result['is_preorder'] = True
            print(f"  🏷️  {title} — buy-only, page check inconclusive → treating as pre-order")

        return result

    # ------------------------------------------------------------------
    # Watch link gap fill and re-enrichment
    # ------------------------------------------------------------------

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

                catchup_original_title = existing_movies[movie_index].get('original_title')
                catchup_director = existing_movies[movie_index].get('crew', {}).get('director') if existing_movies[movie_index].get('crew') else None
                watch_links = self.enrichment.get_watch_links(
                    movie_id, title, year, providers,
                    force_refresh=True, tracking_data=tracking_movie,
                    original_title=catchup_original_title, director=catchup_director,
                    tmdb_id=str(movie_id).replace('tv_', '')
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
                        self.host._safe_save_data_json(display_data, existing_movies, label="reenrich_incremental")
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
            if not self.host._safe_save_data_json(display_data, existing_movies, label="reenrich_final"):
                return 0
            print(f"✅ Re-enriched {fixed_count}/{len(all_movies)} movies")

        return fixed_count

    def reenrich_trailer_gaps(self):
        """
        Re-enrich movies missing trailer links.

        Finds completed movies with no links.trailer and re-runs the TMDB +
        find_trailer_url waterfall for each. Uses retry tracking to avoid
        hammering movies that genuinely have no trailer.

        Does NOT modify _enrichment_status or _is_preorder flags.

        Returns:
            int: Number of movies that got a trailer filled in.
        """
        if not os.path.exists('data.json'):
            print("❌ No data.json found")
            return 0

        with open('data.json', 'r') as f:
            display_data = json.load(f)

        existing_movies = display_data.get('movies', [])

        # Config
        trailer_config = self.config.get('trailer_hosting', {})
        max_batch = trailer_config.get('trailer_gap_batch_size', 30)
        max_retries = trailer_config.get('trailer_gap_max_retries', 5)
        cooldown_days = trailer_config.get('trailer_gap_cooldown_days', 7)
        cooldown_cutoff = (datetime.now() - timedelta(days=cooldown_days)).isoformat()

        # Find movies missing links.trailer
        gap_movies = []
        for i, movie in enumerate(existing_movies):
            if movie.get('links', {}).get('trailer'):
                continue  # Already has a trailer

            # Only retry completed movies (pending ones will get enriched normally)
            status = movie.get('_enrichment_status', '')
            if status != 'completed':
                continue

            # Check retry limits
            retry_count = movie.get('_trailer_retry_count', 0)
            if retry_count >= max_retries:
                continue

            # Check cooldown
            last_retry = movie.get('_trailer_last_retry', '')
            if last_retry and last_retry > cooldown_cutoff:
                continue

            gap_movies.append((i, movie))

        if not gap_movies:
            print("✅ No trailer gaps eligible for retry")
            return 0

        # Apply batch limit
        if max_batch > 0 and len(gap_movies) > max_batch:
            print(f"🎬 Found {len(gap_movies)} movies missing trailers, processing first {max_batch}:")
            gap_movies = gap_movies[:max_batch]
        else:
            print(f"🎬 Found {len(gap_movies)} movies missing trailers:")

        for _, movie in gap_movies:
            print(f"  • {movie.get('title')}")

        # Process each movie
        fixed_count = 0
        unsaved_count = 0
        save_interval = 10

        for movie_index, movie in gap_movies:
            movie_id = str(movie.get('id', ''))
            title = movie.get('title', 'Unknown')

            try:
                # Fetch TMDB details (handles TV shows via tv_ prefix)
                if movie_id.startswith('tv_'):
                    numeric_id = movie_id.replace('tv_', '')
                    movie_details = self.host.get_tv_details(numeric_id)
                else:
                    movie_details = self.host.get_movie_details(movie_id)

                # Update retry tracking regardless of result
                existing_movies[movie_index]['_trailer_retry_count'] = \
                    existing_movies[movie_index].get('_trailer_retry_count', 0) + 1
                existing_movies[movie_index]['_trailer_last_retry'] = datetime.now().isoformat()
                unsaved_count += 1

                if not movie_details:
                    print(f"  ✗ {title} — TMDB fetch failed")
                    continue

                # Run the existing 6-tier trailer waterfall
                trailer_result = self.host.find_trailer_url(movie_details)

                if trailer_result:
                    trailer_url, trailer_source = trailer_result
                    existing_movies[movie_index].setdefault('links', {})['trailer'] = trailer_url
                    existing_movies[movie_index]['_trailer_source'] = trailer_source

                    # Clear 'trailer' from _enrichment_gaps if present
                    existing_gaps = existing_movies[movie_index].get('_enrichment_gaps', [])
                    if 'trailer' in existing_gaps:
                        existing_gaps.remove('trailer')
                        if existing_gaps:
                            existing_movies[movie_index]['_enrichment_gaps'] = existing_gaps
                        else:
                            existing_movies[movie_index].pop('_enrichment_gaps', None)

                    print(f"  ✓ {title} — trailer found (tier={trailer_source})")
                    fixed_count += 1
                else:
                    count = existing_movies[movie_index]['_trailer_retry_count']
                    print(f"  ○ {title} — no trailer found (attempt {count}/{max_retries})")

                # Incremental save
                if unsaved_count >= save_interval:
                    self.host._safe_save_data_json(display_data, existing_movies, label="trailer_gaps_incremental")
                    print(f"  💾 Incremental save ({fixed_count} fixed so far)")
                    unsaved_count = 0

            except Exception as e:
                print(f"  ✗ Error re-enriching trailer for {title}: {e}")
                continue

        # Final save
        if unsaved_count > 0:
            if not self.host._safe_save_data_json(display_data, existing_movies, label="trailer_gaps_final"):
                return 0

        print(f"✅ Trailer gap fill: {fixed_count}/{len(gap_movies)} movies got trailers")
        return fixed_count

    def daily_gap_fill(self):
        """
        Daily refresh of JustWatch watch links and Wikipedia for all wall movies.

        For every movie on the wall:
        - Re-queries JustWatch via verify_availability() to find late-arriving
          VOD services (e.g., Apple TV lists 2-5 days after Amazon)
        - MERGES new services into existing watch_links (never removes)
        - Graduates pre-orders when rent/streaming offers appear
        - Retroactively flags buy-only movies as pre-orders if missed during initial enrichment
        - Fills missing Wikipedia links using fast API methods (no Playwright)

        Returns:
            dict: Results summary {jw_updated, wiki_filled, preorders_graduated, preorders_flagged}
        """
        gap_fill_start = time.time()

        if not os.path.exists('data.json'):
            print("❌ No data.json found")
            return {'jw_updated': 0, 'wiki_filled': 0, 'preorders_graduated': 0, 'preorders_flagged': 0}

        with open('data.json', 'r') as f:
            display_data = json.load(f)

        existing_movies = display_data.get('movies', [])
        if not existing_movies:
            print("❌ No movies in data.json")
            return {'jw_updated': 0, 'wiki_filled': 0, 'preorders_graduated': 0, 'preorders_flagged': 0}

        # Only gap-fill movies from the last 30 days — older movies have stable watch links
        cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        recent_movies = [
            m for m in existing_movies
            if (m.get('digital_date') or m.get('release_date') or '') >= cutoff
        ]
        print(f"  📊 Processing {len(recent_movies)} of {len(existing_movies)} wall movies (last 30 days)")

        # Initialize JustWatch client
        from pipeline.justwatch import JustWatchClient
        jw_client = JustWatchClient(logger=self.logger)

        # Get config values
        amazon_tag = self.enrichment._get_amazon_affiliate_tag() if self.enrichment else None
        excluded_services = self.config.get('tracking', {}).get('excluded_services',
            ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play', 'Shahid VIP', 'Viki', 'Futo'])

        # Load watch links cache
        cache_path = 'cache/watch_links_cache.json'
        watch_cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    watch_cache = json.load(f)
            except Exception:
                watch_cache = {}

        # Load tracking DB for syncing pre-order graduations
        tracking_path = 'movie_tracking.json'
        tracking_data = None
        tracking_changed = False
        try:
            tracking_data = self.storage.tracking_db.load_all()
        except Exception:
            tracking_data = None

        jw_updated = 0
        wiki_filled = 0
        dir_wiki_filled = 0
        preorders_graduated = 0
        preorders_flagged = 0
        unsaved_count = 0
        save_interval = 25
        errors = 0
        today_str = datetime.now().strftime('%Y-%m-%d')

        for movie in recent_movies:
            movie_id = str(movie.get('id', ''))
            title = movie.get('title', 'Unknown')
            year = movie.get('year', '')
            original_title = movie.get('original_title')
            director = movie.get('crew', {}).get('director') if movie.get('crew') else None
            is_preorder = movie.get('_is_preorder', False)

            try:
                # --- JustWatch refresh ---
                content_type = 'tv' if movie_id.startswith('tv_') else 'movie'
                result = jw_client.verify_availability(
                    title, year,
                    excluded_services=excluded_services,
                    affiliate_tag=amazon_tag,
                    content_type=content_type,
                    original_title=original_title,
                    director=director,
                    tmdb_id=movie_id
                )

                if result and result.get('match_confidence') not in ('first_result',):
                    new_links = result.get('watch_links', {})

                    if new_links:
                        current_links = movie.get('watch_links', {})
                        merged = False

                        # Merge VOD: add new services not already present
                        new_vod = new_links.get('vod', [])
                        if isinstance(new_vod, list) and new_vod:
                            current_vod = current_links.get('vod', [])

                            # Normalize existing service names for comparison
                            current_services = set()
                            for v in current_vod:
                                if isinstance(v, dict) and v.get('service'):
                                    current_services.add(self.host.simplify_provider_name(v['service']).lower())

                            for new_entry in new_vod:
                                if isinstance(new_entry, dict) and new_entry.get('link'):
                                    simplified = self.host.simplify_provider_name(new_entry['service'])
                                    if simplified.lower() not in current_services:
                                        # Add with simplified name
                                        merged_entry = {
                                            'service': simplified,
                                            'link': new_entry['link'],
                                        }
                                        for price_key in ('rent_price', 'buy_price', 'price'):
                                            if new_entry.get(price_key):
                                                merged_entry[price_key] = new_entry[price_key]
                                        current_vod.append(merged_entry)
                                        current_services.add(simplified.lower())
                                        merged = True
                                    else:
                                        # Update prices for existing service
                                        for v in current_vod:
                                            if isinstance(v, dict) and self.host.simplify_provider_name(v.get('service', '')).lower() == simplified.lower():
                                                price_updated = False
                                                for price_key in ('rent_price', 'buy_price'):
                                                    if new_entry.get(price_key) and v.get(price_key) != new_entry[price_key]:
                                                        v[price_key] = new_entry[price_key]
                                                        price_updated = True
                                                if price_updated:
                                                    merged = True
                                                break

                            if merged:
                                current_links['vod'] = current_vod

                        # Merge streaming: add if not already present
                        new_streaming = new_links.get('streaming')
                        if isinstance(new_streaming, dict) and new_streaming.get('link'):
                            existing_streaming = current_links.get('streaming')
                            has_existing = (
                                (isinstance(existing_streaming, dict) and existing_streaming.get('link'))
                                or (isinstance(existing_streaming, list) and any(
                                    isinstance(s, dict) and s.get('link') for s in existing_streaming))
                            )
                            if not has_existing:
                                current_links['streaming'] = {
                                    'service': self.host.simplify_provider_name(new_streaming['service']),
                                    'link': new_streaming['link']
                                }
                                merged = True

                        if merged:
                            movie['watch_links'] = current_links
                            movie['_watch_links_verified'] = datetime.now().isoformat()

                            # Update cache
                            cache_key = f"tv_{movie_id}" if content_type == 'tv' else movie_id
                            watch_cache[cache_key] = {
                                'links': current_links,
                                'cached_at': datetime.now().isoformat(),
                                'source': 'gap_fill'
                            }

                            jw_updated += 1
                            unsaved_count += 1
                            print(f"  + {title} — new services added")

                    # Pre-order graduation
                    if is_preorder and (result.get('has_rent') or result.get('has_streaming')):
                        movie.pop('_is_preorder', None)
                        movie.pop('_buyonly_preorder', None)
                        movie.pop('pre_order_links', None)
                        movie['digital_date'] = today_str
                        if new_links:
                            movie['watch_links'] = current_links
                        preorders_graduated += 1
                        unsaved_count += 1
                        print(f"  🎓 {title} — pre-order graduated (now available)")

                        # Sync tracking — mark as available so discovery doesn't re-process
                        if tracking_data and tracking_data.get('movies', {}).get(movie_id):
                            tracking_data['movies'][movie_id]['status'] = 'available'
                            tracking_data['movies'][movie_id]['digital_date'] = today_str
                            tracking_data['movies'][movie_id]['enriched'] = True
                            tracking_data['movies'][movie_id].pop('_buyonly_preorder', None)
                            tracking_changed = True

                    # Retroactive buy-only pre-order detection
                    if not is_preorder and result.get('buy_only') and not (result.get('has_rent') or result.get('has_streaming')):
                        if not movie.get('_buyonly_verified'):
                            _gf_detect = self._detect_buyonly_preorder(result, movie_id, title)

                            if _gf_detect['is_preorder']:
                                movie['_is_preorder'] = True
                                movie['_buyonly_preorder'] = True
                                _jw_vod = new_links.get('vod', []) if new_links else []
                                if _jw_vod:
                                    movie['pre_order_links'] = _jw_vod
                                if _gf_detect['preorder_date']:
                                    movie['digital_date'] = _gf_detect['preorder_date']
                                movie['watch_links'] = {}
                                if tracking_data and tracking_data.get('movies', {}).get(movie_id):
                                    tracking_data['movies'][movie_id]['_buyonly_preorder'] = True
                                    tracking_changed = True
                                preorders_flagged += 1
                                unsaved_count += 1
                            elif _gf_detect['verified_genuine']:
                                movie['_buyonly_verified'] = True
                                unsaved_count += 1

                # --- Wikipedia fill (only if missing) ---
                links = movie.get('links', {})
                if not links.get('wikipedia'):
                    imdb_id = links.get('imdb', '').replace('https://www.imdb.com/title/', '').rstrip('/')
                    if not imdb_id:
                        imdb_id = movie.get('imdb_id', '')

                    wiki_url = self.host.find_wikipedia_url(
                        title=title,
                        year=str(year),
                        imdb_id=imdb_id,
                        movie_id=movie_id,
                        director=director,
                        original_title=original_title,
                        skip_playwright=True,
                        skip_gemini=True
                    )

                    if wiki_url:
                        if 'links' not in movie:
                            movie['links'] = {}
                        movie['links']['wikipedia'] = wiki_url
                        # Store Wikidata distributors if found (for indie detection)
                        wd_dist = getattr(self.host, 'last_wikidata_distributors', [])
                        if wd_dist:
                            movie['wikidata_distributors'] = wd_dist
                        wiki_filled += 1
                        unsaved_count += 1
                        print(f"  📚 {title} — Wikipedia link added")

                # --- Director Wikipedia fill (only if missing) ---
                # Small sleep to avoid back-to-back Wikidata calls within the same movie
                if director and not links.get('director_wiki'):
                    time.sleep(0.15)
                    director_wiki_url = self.host.find_director_wikipedia_url(director)
                    if director_wiki_url:
                        if 'links' not in movie:
                            movie['links'] = {}
                        movie['links']['director_wiki'] = director_wiki_url
                        dir_wiki_filled += 1
                        unsaved_count += 1
                        print(f"  🎬 {title} — Director Wikipedia added ({director})")

                # Incremental save
                if unsaved_count >= save_interval:
                    self.host._safe_save_data_json(display_data, existing_movies, label="gap_fill_incremental")
                    print(f"  💾 Incremental save ({jw_updated} JW + {wiki_filled} wiki so far)")
                    unsaved_count = 0

                # Rate limit for JustWatch
                time.sleep(0.2)

            except Exception as e:
                errors += 1
                self.logger.error(f"Gap fill error for {title} ({movie_id}): {e}")
                if errors <= 5:
                    print(f"  ✗ {title} — error: {e}")
                continue

        # Final save
        if unsaved_count > 0:
            self.host._safe_save_data_json(display_data, existing_movies, label="gap_fill_final")

        # Save updated cache
        try:
            self.storage.save_cache(watch_cache, cache_path)
        except Exception as e:
            self.logger.error(f"Failed to save watch links cache: {e}")

        # Apply cached watch links to older movies outside the 30-day window
        if self.host._apply_cached_watch_links(existing_movies):
            self.host._safe_save_data_json(display_data, existing_movies, label="gap_fill_cache_apply")

        # Save tracking if any pre-orders were graduated
        if tracking_changed and tracking_data:
            try:
                if not self.storage.atomic_write_json(tracking_data, tracking_path):
                    self.logger.error("gap_fill: failed to save tracking DB after pre-order graduation")
                    errors += 1
                _sync_parts = []
                if preorders_graduated:
                    _sync_parts.append(f"{preorders_graduated} graduation(s)")
                if preorders_flagged:
                    _sync_parts.append(f"{preorders_flagged} flagged")
                print(f"  💾 Tracking synced ({', '.join(_sync_parts) if _sync_parts else 'updated'})")
            except Exception as e:
                self.logger.error(f"Failed to save tracking after gap_fill: {e}")

        # Save metrics
        duration = time.time() - gap_fill_start
        results = {
            'jw_updated': jw_updated,
            'wiki_filled': wiki_filled,
            'dir_wiki_filled': dir_wiki_filled,
            'preorders_graduated': preorders_graduated,
            'preorders_flagged': preorders_flagged,
            'errors': errors,
            'total_processed': len(recent_movies),
            'total_wall_movies': len(existing_movies),
            'duration_seconds': round(duration, 1)
        }

        try:
            metrics_path = 'metrics/gap_fill_run.json'
            os.makedirs('metrics', exist_ok=True)
            with open(metrics_path, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'duration_seconds': round(duration, 1),
                    'results': results
                }, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save gap fill metrics: {e}")

        print(f"\n  📊 Gap fill results ({duration:.0f}s, {len(recent_movies)} movies):")
        print(f"     Watch links updated: {jw_updated}")
        print(f"     Wikipedia filled: {wiki_filled}")
        if dir_wiki_filled:
            print(f"     Director Wikipedia filled: {dir_wiki_filled}")
        print(f"     Pre-orders graduated: {preorders_graduated}")
        if preorders_flagged:
            print(f"     Pre-orders flagged: {preorders_flagged}")
        if errors:
            print(f"     Errors: {errors}")

        return results
