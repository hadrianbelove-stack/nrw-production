"""
Display data generation module — Phase 4 helpers for the NRW pipeline.

Extracted from DataGenerator (pipeline/generator.py) for maintainability.
Handles pull quote injection, watch link caching, movie categorization,
and admin override application for the final display output.
"""

import json
import os
from datetime import datetime


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
                        'source': q.get('source', '')
                    })

            if selected:
                movie['pull_quotes'] = selected
                injected += 1
            elif 'pull_quotes' in movie:
                # Remove stale quotes if none are selected anymore
                del movie['pull_quotes']

        if injected:
            print(f"\U0001f4ac Injected pull quotes for {injected} movies")

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

    def categorize_movie(self, movie, category_config):
        """
        Categorize a movie as 'studio', 'indie', or None based on studio and budget.

        Logic:
        1. Check manual override first (admin can force tier)
        2. Match studio against studio_list
        3. Fallback to budget threshold ($10M default)
        4. Default to None (uncategorized) if no match

        Returns:
            dict: Categories object with tier, is_foreign, is_staff_pick, auto_categorized, manual_override
        """
        studio_list = category_config.get('studio_list', [])
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
        elif studio and any(bs.lower() in studio.lower() for bs in studio_list):
            tier = 'studio'
            auto_categorized = True
        elif budget >= budget_threshold:
            tier = 'studio'
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
            'is_studio': tier == 'studio',
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
                print(f"\u26a0\ufe0f  Could not load movie_tracking.json: {e}")

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
        studio_count = 0
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
                eventive_info = self.host._fetch_eventive_screening_info(screening_slug) if screening_slug else {}
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
                if categories.get('is_studio'):
                    categories['tier'] = 'studio'
                elif categories.get('is_indie'):
                    categories['tier'] = 'indie'
                elif 'is_studio' in overrides or 'is_indie' in overrides:
                    categories['tier'] = None

            # Set 'featured' field for backwards compatibility (true or false)
            movie['featured'] = categories['is_staff_pick']

            # Count for stats
            if categories.get('is_studio'):
                studio_count += 1
            if categories.get('is_indie'):
                indie_count += 1
            if not categories.get('is_studio') and not categories.get('is_indie'):
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

        print(f"\U0001f4dd Admin overrides applied:")
        print(f"  Categories: {studio_count} Studio, {indie_count} Indie, {uncategorized_count} Uncategorized, {foreign_count} Foreign, {restoration_count} Restorations, {virtual_screening_count} Virtual Screenings, {documentary_count} Documentaries")
        print(f"  Staff Picks: {staff_pick_count}")
        if ordered_count > 0:
            print(f"  Editorial ordering: {ordered_count} movies pinned to top")

        return display_movies, staff_picks
