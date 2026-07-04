"""
Display data generation module — Phase 4 helpers for the NRW pipeline.

Extracted from DataGenerator (pipeline/generator.py) for maintainability.
Handles pull quote injection, watch link caching, movie categorization,
and admin override application for the final display output.
"""

import json
import os
import re
from datetime import datetime, timedelta


def inject_notability_into(movies_list):
    """Attach a 0-100 Buzz score + notability block to every movie that has
    notability facts cached. Returns the count injected.

    Reuses the capsule factoid pass's `notability` facts (festival/awards/
    year-end/press_volume) from cache/capsule_cache.json, combined with the
    record's numeric signals (IMDb votes from enrichment, TMDB popularity,
    Wikipedia language count). Only touches movies that have notability facts —
    i.e. recently researched arrivals — so it never web-scans the whole wall.

    Buzz feeds the Selects ("what's supposed to be good") ranking in /curate; it
    never auto-selects anything and the slop classifier never reads it.

    Module-level so the nightly post-capsule step (scripts/inject_notability.py)
    can run it standalone on data.json, after the capsule research has produced
    facts for the day's fresh arrivals — the in-build pass runs too early for them.
    """
    from pipeline import notability as notab
    cap_path = 'cache/capsule_cache.json'
    if not os.path.exists(cap_path):
        return 0
    try:
        with open(cap_path) as f:
            cap = json.load(f)
    except (ValueError, OSError):
        return 0

    facts = {}
    for entry in (cap.values() if isinstance(cap, dict) else cap):
        if isinstance(entry, dict) and entry.get('notability'):
            key = ((entry.get('title') or '').lower(), str(entry.get('year', '')))
            facts[key] = entry['notability']

    injected = 0
    for movie in movies_list:
        key = ((movie.get('title') or '').lower(), str(movie.get('year', '')))
        qual = facts.get(key)
        if not qual:
            continue
        # _wiki_language_count is set during enrichment (network stays out of
        # the display pass); read it as-is, None is fine — buzz tolerates it.
        if movie.get('_tmdb_popularity') is None:
            movie['_tmdb_popularity'] = movie.get('popularity')
        block = notab.build(movie, qual)
        movie['buzz_score'] = block['buzz_score']
        movie['notability'] = block
        injected += 1

    if injected:
        print(f"\U0001f4ca Injected notability (Buzz) for {injected} movies")
    return injected


class DisplayGenerator:
    """Prepares movies for final display output in data.json.

    Parameters
    ----------
    ctx : PipelineContext
        Shared pipeline dependencies (config, logger, storage, enrichment_service, tmdb_key).
    host : DataGenerator
        Parent generator instance — provides _fetch_eventive_screening_info().
    """

    def __init__(self, ctx, host):
        self.ctx = ctx
        self.host = host

    def inject_selected_pull_quotes(self, movies_list):
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
            self.ctx.logger.warning(f"Pull quotes injection: Error loading caches: {e}")
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
                        'source': q.get('source', ''),
                        'review_url': q.get('review_url', '')
                    })

            if selected:
                movie['pull_quotes'] = selected
                injected += 1
            elif movie.get('pull_quotes'):
                # Non-empty but nothing selected in cache → stale, remove it.
                # An empty list [] is a deliberate "reviewed, skipped" marker
                # (set by /curate skip) and must survive rebuilds, so leave it.
                del movie['pull_quotes']

        if injected:
            print(f"\U0001f4ac Injected pull quotes for {injected} movies")

    def inject_approved_capsules(self, movies_list):
        """Restore approved capsules from the bank for movies missing one.

        Capsules are written to data.json at approve-time, but a movie can fall
        off the wall (reverted to tracking, archived) and later re-transition
        with an empty capsule field. The approved bank persists the text, so
        re-inject it by title+year. Fills ONLY when the movie has no capsule —
        never overwrites a live capsule and never deletes anything (unlike pull
        quotes, plenty of movies have capsules that predate the bank).
        """
        bank_path = 'admin/approved_capsules.json'
        if not os.path.exists(bank_path):
            return
        try:
            with open(bank_path, 'r') as f:
                bank = json.load(f)
        except Exception as e:
            self.ctx.logger.warning(f"Capsule injection: Error loading bank: {e}")
            return

        # Lookup by (title.lower(), str(year)); later (newer) bank entries win
        by_key = {}
        for entry in (bank if isinstance(bank, list) else []):
            title = (entry.get('title') or '').lower()
            year = str(entry.get('year', ''))
            capsule = entry.get('capsule', '')
            if title and capsule:
                by_key[(title, year)] = capsule

        injected = 0
        for movie in movies_list:
            if movie.get('capsule'):
                continue  # never overwrite a live capsule
            key = ((movie.get('title') or '').lower(), str(movie.get('year', '')))
            capsule = by_key.get(key)
            if capsule:
                movie['capsule'] = capsule
                injected += 1

        if injected:
            print(f"\U0001f4dd Restored capsules from bank for {injected} movies")

    def inject_notability(self, movies_list):
        """Attach a 0-100 Buzz score + notability block to each movie.

        Thin wrapper over the module-level inject_notability_into() so the same
        logic can run both in-build (here) and standalone post-capsule
        (scripts/inject_notability.py).
        """
        return inject_notability_into(movies_list)

    def apply_cached_watch_links(self, movies_list):
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
            self.ctx.logger.warning(f"Watch links cache injection: Error loading cache: {e}")
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
            self.ctx.logger.debug(f"Applied cached watch links for {movie.get('title')}")

        if applied:
            print(f"\U0001f517 Applied cached watch links for {applied} movies")
        return applied

    @staticmethod
    def _normalize_title(title):
        """Normalize a film title for distributor lookup matching."""
        t = title.lower().strip()
        t = re.sub(r'^the\s+', '', t)
        t = re.sub(r'\s+', ' ', t)
        return t

    def categorize_movie(self, movie, category_config, distributor_lookup=None):
        """
        Categorize a movie as 'studio', 'indie', or None based on studio and budget.

        Logic:
        1. Check manual override first (admin can force tier)
        2. Check distributor filmography lookup (Wikipedia-sourced)
        3. Check Wikidata distributors against indie list (enrichment signal)
        4. Check TMDB studio against indie/studio lists
        5. Fallback to budget threshold ($10M default)
        6. Default to None (uncategorized) if no match

        Returns:
            dict: Categories object with tier, is_foreign, is_staff_pick, auto_categorized, manual_override
        """
        studio_list = category_config.get('studio_list', [])
        indie_distributors = category_config.get('indie_distributors', [])
        budget_threshold = category_config.get('budget_threshold', 10000000)

        # Get movie properties
        studio = movie.get('studio', '')
        budget = movie.get('budget', 0) or 0  # Handle None
        original_language = movie.get('original_language', 'en')
        genres = movie.get('genres', []) or []
        wikidata_distributors = movie.get('wikidata_distributors', [])

        # Check for existing manual override from movie_tracking.json
        manual_override = movie.get('filters', {}).get('manual_override')

        # Determine foreign status (needed for indie check)
        is_foreign = original_language and original_language != 'en'

        # Check distributor filmography lookup (scraped from Wikipedia)
        lookup_distributor = None
        if distributor_lookup:
            by_title_year = distributor_lookup.get('by_title_year', {})
            title = movie.get('title', '')
            year = movie.get('year', '')
            key = f"{self._normalize_title(title)}_{year}"
            lookup_distributor = by_title_year.get(key)

        lookup_matches_indie = lookup_distributor and lookup_distributor in indie_distributors
        lookup_matches_studio = lookup_distributor and any(
            s.lower() in lookup_distributor.lower() for s in studio_list
        )

        # Check distributor matches — TMDB studio field
        matches_studio = studio and any(bs.lower() in studio.lower() for bs in studio_list)
        matches_indie = studio and any(bs.lower() in studio.lower() for bs in indie_distributors)

        # Check Wikidata distributors (from P750 property, populated during enrichment)
        wikidata_matches_indie = any(
            any(ind.lower() in wd.lower() for ind in indie_distributors)
            for wd in wikidata_distributors
        ) if wikidata_distributors else False
        wikidata_matches_studio = any(
            any(s.lower() in wd.lower() for s in studio_list)
            for wd in wikidata_distributors
        ) if wikidata_distributors else False

        # Determine tier
        # Priority: manual override > lookup/Wikidata/TMDB indie > studio match > budget fallback
        # Indie rules: matches indie distributor, budget under threshold, NOT foreign
        # If on both lists (e.g. A24, NEON): budget is tiebreaker
        any_indie = matches_indie or lookup_matches_indie or wikidata_matches_indie
        any_studio = matches_studio or lookup_matches_studio or wikidata_matches_studio

        if manual_override:
            tier = manual_override
            auto_categorized = False
        elif any_indie and budget < budget_threshold and not is_foreign:
            tier = 'indie'
            auto_categorized = True
        elif any_studio:
            tier = 'studio'
            auto_categorized = True
        elif budget >= budget_threshold:
            tier = 'studio'
            auto_categorized = True
        else:
            tier = None
            auto_categorized = True

        # Determine documentary status from TMDB genres
        is_documentary = 'Documentary' in genres

        return {
            'is_indie': tier == 'indie',
            'is_foreign': is_foreign,
            'is_staff_pick': False,  # Set later from staff_picks.json
            'is_restoration': False,  # Set later from restoration detection
            'is_virtual_screening': False,  # Set later from watch_links detection
            'is_series': False,  # Set later from content_type detection
            'is_documentary': is_documentary,
            'auto_categorized': auto_categorized,
            'manual_override': manual_override,
        }

    def apply_admin_overrides(self, display_movies):
        """Apply admin panel decisions to final output including categorization."""

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

        # Load reissue labels (TMDB ID → display label string)
        reissue_labels = {}
        if os.path.exists('admin/reissue_labels.json'):
            with open('admin/reissue_labels.json', 'r') as f:
                reissue_labels = json.load(f)

        # Load category overrides (admin toggles for all categories)
        category_overrides = {}
        if os.path.exists('admin/category_overrides.json'):
            with open('admin/category_overrides.json', 'r') as f:
                category_overrides = json.load(f)

        # Load the general durable override layer (admin/overrides.json). Applied as
        # the LAST mutation per movie below, so it survives re-enrichment of any field
        # that gets rebuilt from TMDB (genres, studio, cast, etc.). Supports:
        #   "set":           {field: value}   -> overwrite any top-level field
        #   "genres_add":    [..]             -> append to movie['genres'] (deduped)
        #   "genres_remove": [..]             -> drop from movie['genres']
        field_overrides = {}
        if os.path.exists('admin/overrides.json'):
            with open('admin/overrides.json', 'r') as f:
                try:
                    field_overrides = json.load(f)
                except (ValueError, json.JSONDecodeError):
                    field_overrides = {}  # a malformed file must never break the build

        # Auto-refresh distributor filmography lookup if stale (>7 days)
        try:
            from scripts.build_distributor_lookup import build_lookup
            build_lookup(quiet=True)
        except Exception as e:
            self.ctx.logger.debug(f"Distributor lookup refresh skipped: {e}")

        # Load distributor filmography lookup (Wikipedia-sourced)
        distributor_lookup = {}
        lookup_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache', 'distributor_lookup.json')
        if os.path.exists(lookup_path):
            try:
                with open(lookup_path, 'r') as f:
                    distributor_lookup = json.load(f)
            except Exception as e:
                self.ctx.logger.warning(f"Distributor lookup: Error loading: {e}")

        if os.path.exists('admin/ordering.json'):
            with open('admin/ordering.json', 'r') as f:
                ordering_data = json.load(f)
                if isinstance(ordering_data, list):
                    ordering = ordering_data

        # Load tracking DB to apply manual field edits
        try:
            tracking_data = self.ctx.storage.tracking_db.load_all().get('movies', {})
        except Exception as e:
            self.ctx.logger.warning(f"Could not load tracking DB: {e}")
            tracking_data = {}

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
            print(f"\U0001f4dd Applied {fields_updated} manual field edits from movie_tracking.json")

        # Sync pre-order flags from tracking → data.json (recovery for stripped flags)
        _preorder_overrides = self.ctx.config.get('preorder_overrides', {})
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
            print(f"\U0001f3f7\ufe0f  Synced {_preorder_synced} pre-order flag(s) from tracking \u2192 data.json")

        # Load screening name mapping and manual end dates from config
        screening_names_map = self.ctx.config.get('screening_names', {})
        screening_end_dates_map = self.ctx.config.get('screening_end_dates', {})

        # Apply categorization to all movies
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
            categories = self.categorize_movie(movie, category_config, distributor_lookup)


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

            reissue_label = reissue_labels.get(str(movie_id))
            if reissue_label:
                is_restoration = True

            # Reissue confirmed via the /curate "Confirm Reissues" stage (intake Pass D).
            # The flag + label live on the tracking entry; the manual reissue_labels.json
            # still wins if both are set.
            tracking_entry = tracking_data.get(str(movie_id), {})
            is_reissue = bool(tracking_entry.get('_reissue'))
            if is_reissue:
                is_restoration = True
                if not reissue_label:
                    reissue_label = tracking_entry.get('reissue_label')

            categories['is_restoration'] = is_restoration
            movie['reissue_label'] = reissue_label
            # Propagate the reissue marker to the wall so /curate and /morning can treat a
            # reissue as a normal new arrival (capsule + quotes) while still skipping
            # auto-detected restorations. Distinct from is_restoration, which is the section.
            movie['_reissue'] = is_reissue

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

                # Look up per-film dates from cache first (most accurate), then festival-level
                _movie_id_str = str(movie.get('id', ''))
                _cache_entry = self.host.watch_links_cache.get(_movie_id_str, {})
                _cached_start = _cache_entry.get('start_time', '')
                _cached_end = _cache_entry.get('end_time', '')
                _cached_festival = _cache_entry.get('festival_name', '')

                # Only fetch festival page if we don't have per-film dates from cache
                if not _cached_start and not _cached_end:
                    eventive_info = self.host._fetch_eventive_screening_info(screening_slug) if screening_slug else {}
                    # White-label / custom-domain Eventive (e.g. watch.imaginenative.org):
                    # no recognizable slug and the festival page exposes no dates. Read the
                    # window straight from the play link so it can expire on schedule.
                    if (not eventive_info.get('available_end') and screening_link
                            and (screening_service or '').lower() == 'eventive'):
                        _play_info = self.host._fetch_eventive_play_info(screening_link)
                        if _play_info.get('available_end'):
                            eventive_info = _play_info
                            if not screening_slug:
                                # Derive a slug from the play URL's first path segment so the
                                # config end-date fallback and metrics have a key.
                                try:
                                    screening_slug = screening_link.split('://', 1)[1].split('/')[1]
                                except (IndexError, AttributeError):
                                    pass
                else:
                    eventive_info = {}

                screening_name = _cached_festival or screening_names_map.get(screening_slug, '') or eventive_info.get('name', screening_slug)

                today_str = datetime.now().strftime('%Y-%m-%d')

                # Per-film dates from cache take priority over festival-level dates
                if _cached_start:
                    try:
                        _s_dt = datetime.fromisoformat(_cached_start.replace('Z', '+00:00'))
                        available_start = _s_dt.strftime('%Y-%m-%d')
                    except (ValueError, TypeError):
                        available_start = eventive_info.get('available_start') or existing_screening_info.get('available_start')
                else:
                    available_start = eventive_info.get('available_start') or existing_screening_info.get('available_start')

                if _cached_end:
                    try:
                        _e_dt = datetime.fromisoformat(_cached_end.replace('Z', '+00:00'))
                        available_end = _e_dt.strftime('%Y-%m-%d')
                    except (ValueError, TypeError):
                        available_end = eventive_info.get('available_end') or screening_end_dates_map.get(screening_slug) or existing_screening_info.get('available_end')
                else:
                    available_end = eventive_info.get('available_end') or screening_end_dates_map.get(screening_slug) or existing_screening_info.get('available_end')

                screening_expired = available_end and available_end < today_str

                movie['virtual_screening_info'] = {
                    'platform': screening_service or 'Unknown',
                    'screening_slug': screening_slug,
                    'screening_name': screening_name,
                    'available_start': available_start,
                    'available_end': available_end,
                    'discovered': existing_screening_info.get('discovered', today_str),
                    'last_checked': existing_screening_info.get('last_checked', today_str),
                    'status': 'expired' if screening_expired else existing_screening_info.get('status', 'active')
                }

                # Correct digital_date and pre-order status from screening dates
                if available_start:
                    movie['digital_date'] = available_start
                    if available_start > today_str:
                        movie['_is_preorder'] = True
                    elif movie.get('_is_preorder'):
                        # Screening has started — no longer a pre-order
                        del movie['_is_preorder']

                # Hide expired virtual screenings automatically
                if screening_expired:
                    movie['hidden'] = True

            # Mark limited series
            categories['is_series'] = movie.get('content_type') == 'limited_series'

            movie['filters'] = categories

            # Apply category overrides from admin panel
            if movie_id in category_overrides:
                overrides = category_overrides[movie_id]
                # Tolerate legacy string format (e.g. "indie" meaning {"is_indie": True}).
                # One malformed override must never crash the whole enrichment phase.
                if isinstance(overrides, str):
                    legacy_key = 'is_%s' % overrides
                    overrides = {legacy_key: True} if legacy_key in categories else {}
                elif not isinstance(overrides, dict):
                    overrides = {}
                for key, val in overrides.items():
                    if key in categories:
                        categories[key] = val
                        categories['auto_categorized'] = False

            # Crime + Drama -> also tag Thriller (site filter section). True-crime
            # documentaries and crime-comedies are deliberately excluded.
            genres = movie.get('genres') or []
            if ('Crime' in genres and 'Drama' in genres
                    and 'Comedy' not in genres and 'Documentary' not in genres
                    and 'Thriller' not in genres):
                genres.append('Thriller')
                movie['genres'] = genres

            # General durable override layer (admin/overrides.json) — applied LAST so
            # nothing downstream (incl. the rules above) overwrites a manual decision.
            ov = field_overrides.get(movie_id)
            if isinstance(ov, dict):
                cur = movie.get('genres') or []
                for g in ov.get('genres_add', []) or []:
                    if g not in cur:
                        cur.append(g)
                cur = [g for g in cur if g not in (ov.get('genres_remove', []) or [])]
                movie['genres'] = cur
                for key, val in (ov.get('set') or {}).items():
                    movie[key] = val

            # Retire the legacy _is_slop_guess shadow flag: the slop verdict now
            # lives solely in is_slop. Strip it on every build so the stale fields
            # drain out of data.json through the pipeline (no direct data.json edit).
            movie.pop('_is_slop_guess', None)

            # Set 'featured' field for backwards compatibility (true or false)
            movie['featured'] = categories['is_staff_pick']

            # Count for stats
            if categories.get('is_indie'):
                indie_count += 1
            else:
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

        # Coming Soon cap — never publish a pre-order more than COMING_SOON_MAX_DAYS
        # ahead of release. Far-future placeholders / pre-orders are hidden (NOT
        # deleted — they stay tracked and curation auto-restores) and reappear on
        # their own once the date is within the window. Mirrors the enrichment-side
        # cap. We tag our own hides with _coming_soon_capped so un-hiding can never
        # clobber an expired-screening hide.
        COMING_SOON_MAX_DAYS = 30  # keep in sync with enricher.py
        _cs_cap = (datetime.now() + timedelta(days=COMING_SOON_MAX_DAYS)).strftime('%Y-%m-%d')
        _cs_hidden = 0
        for movie in display_movies:
            dd = movie.get('digital_date') or ''
            if movie.get('_is_preorder') and dd > _cs_cap:
                if not movie.get('hidden'):
                    movie['hidden'] = True
                    _cs_hidden += 1
                movie['_coming_soon_capped'] = True
            elif movie.get('_coming_soon_capped'):
                # Was capped before; now within the window (or no longer a pre-order)
                # — restore it. Only films WE capped carry this marker.
                movie.pop('_coming_soon_capped', None)
                movie['hidden'] = False
        if _cs_hidden:
            print(f"⏳ Coming Soon cap: hid {_cs_hidden} pre-order(s) dated >{COMING_SOON_MAX_DAYS}d out")

        staff_pick_count = len([m for m in display_movies if m.get('filters', {}).get('is_staff_pick')])
        ordered_count = len(ordering) if ordering else 0

        print(f"\U0001f4dd Admin overrides applied:")
        print(f"  Filters: {indie_count} Indie, {uncategorized_count} Uncategorized, {foreign_count} Foreign, {restoration_count} Restorations, {virtual_screening_count} Virtual Screenings, {documentary_count} Documentaries")
        print(f"  Staff Picks: {staff_pick_count}")
        if ordered_count > 0:
            print(f"  Editorial ordering: {ordered_count} movies pinned to top")

        return display_movies, staff_picks
