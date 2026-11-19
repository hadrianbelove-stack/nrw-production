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

from pipeline import putback
from pipeline.provider_names import normalize_watch_links


# Stores JustWatch lists that sell discs, not digital copies (Barnes & Noble: DVD / Blu-ray).
PHYSICAL_STORES = frozenset({'Barnes & Noble'})


def _is_held(movie):
    """A film held off the wall as "not out yet" — JustWatch strikes, the old permanent
    skip, a festival screening that ended, or a store pre-order. JustWatch decides for
    it every run: no shortcut (pre-order graduation, festival bypass) lets it through."""
    return bool(movie.get('_jw_revert_count') or movie.get('_skip_provider_discovery')
                or movie.get('_screening_expired') or movie.get('_rent_preorder_held'))


def _page_key(url):
    """A store page's identity for the per-day verdict cache: the URL without the affiliate
    `tag=` (one check reads Amazon's link tagged, another untagged -- the same page)."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    try:
        p = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k != 'tag']
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ''))
    except ValueError:
        return url


# A festival page is not a release: JustWatch lists some films' own (often expired)
# Eventive screening as a "rental" (Disposable Humanity, Nov 2026). Excluded when JustWatch
# decides for a held film or a buy-only pre-order. Not "Sundance": that token would also
# drop the streaming service Sundance Now (exclusion matches any service containing it).
FESTIVAL_PLATFORMS = ['Eventive', 'Shift72']


def _is_festival_link(v):
    link = (v.get('link') or '').lower() if isinstance(v, dict) else ''
    svc = (v.get('service') or '').lower() if isinstance(v, dict) else ''
    return (svc in ('eventive', 'shift72') or 'eventive.org' in link
            or 'shift72.com' in link or 'festivalplayer' in link)


def strip_festival_links(watch_links):
    """Drop festival screening pages (Eventive, Shift72, Festival Player) from a film's
    watch links, in place: a returned screening's own (expired) festival page is not a
    release. True if any were dropped."""
    changed = False
    if isinstance(watch_links, dict):
        for kind in ('vod', 'streaming'):
            v = watch_links.get(kind)
            if isinstance(v, list) and any(_is_festival_link(x) for x in v):
                watch_links[kind] = [x for x in v if not _is_festival_link(x)]
                changed = True
            elif isinstance(v, dict) and _is_festival_link(v):
                watch_links.pop(kind, None)
                changed = True
    return changed


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
        self._jw_healthy = None  # JW_BREAKER: health (None=unchecked, True/False=canary result)
        self._jw_healthy_at = 0.0  # when the canary last ran (re-run after _JW_HEALTH_TTL_S)
        self._backlog_putbacks = 0  # long-held films put back this run (see MAX_BACKLOG_PUTBACKS_PER_RUN)
        self._pending_putbacks = {}  # held films confirmed this run, put back at the wall move
        self._jw_lookups = 0  # JustWatch lookups this run (metrics)
        self._jw_errors = 0   # lookups that failed — films left waiting, no strike (metrics)
        self._page_verdicts = {}  # (day, store URL) -> store page verdict: read once a day

    # ------------------------------------------------------------------
    # JustWatch verification gate
    # ------------------------------------------------------------------

    # JW_BREAKER: blockbuster control titles guaranteed to have US offers on
    # JustWatch. If JW can't find ANY of them, it is unreachable/blocked from
    # this environment (datacenter IP → HTTP 200 + empty results) and its "no
    # match" answers cannot be trusted. Title+year matching is enough here.
    _JW_CANARY_TITLES = [("Oppenheimer", 2023), ("Barbie", 2023), ("Dune: Part Two", 2024)]

    _JW_HEALTH_TTL_S = 900  # re-run the canary at most every 15 min, so a mid-run outage is caught

    # Long-held films (the old permanent-skip backlog, returned festival screenings) put
    # back per run. Each put-back needs enrichment, which is capped at 100 films a run
    # (a normal day already brings ~60 arrivals). Over this number, a confirmed backlog
    # film simply waits for the next run (no strike, same date) — today's new releases
    # go first (held films are also checked after them).
    # No trickle (owner, Nov 2026): every confirmed put-back lands the same run. (Old ones never go
    # on the wall -- PUTBACK_MAX_AGE_DAYS -- so they cost enrichment nothing.)
    MAX_BACKLOG_PUTBACKS_PER_RUN = 10 ** 6
    # A film put back (or a buy-only one graduated) whose real release date is older than this goes
    # to 'available' in tracking but NOT onto the wall (owner, Nov 2026: "don't worry about anything
    # more than 30 days old; the more recent ones on their actual release dates").
    PUTBACK_MAX_AGE_DAYS = 30

    def _check_jw_health(self):
        """Confirm JustWatch is reachable by looking up known-available control titles.
        Cached for _JW_HEALTH_TTL_S. Uses a fresh client every time: the shared
        client's search cache would otherwise answer the canary from memory and
        never notice an outage that starts mid-run. True if healthy, False if not."""
        if self._jw_healthy is not None and (time.time() - self._jw_healthy_at) < self._JW_HEALTH_TTL_S:
            return self._jw_healthy
        from pipeline.justwatch import JustWatchClient
        canary = JustWatchClient(logger=self.logger)
        self._jw_healthy_at = time.time()
        for _title, _year in self._JW_CANARY_TITLES:
            try:
                # Healthy only if JustWatch returns real OFFERS for a control title: an
                # outage can also return titles with empty offer lists ("no valid offers").
                _r = canary.verify_availability(_title, _year)
                if _r and _r.get('verified'):
                    self._jw_healthy = True
                    return True
            except Exception:
                continue
        # No control title came back with offers → JustWatch is not answering for us.
        self._jw_healthy = False
        self.logger.error(
            "JW_BREAKER: JustWatch returned no offers for ALL control titles — treating "
            "as an outage. Suppressing JW strikes this run (films stay in tracking, "
            "revert counts untouched)."
        )
        print("  🛑 JW_BREAKER: JustWatch appears blocked/down — suppressing reverts this run")
        return False

    def _deferred_reissue_signal_changed(self, movie_id, movie):
        """True if a deferred reissue has gained a NEW digital signal versus the baseline
        captured at defer time — a Type-4 digital date that wasn't there before, or a watch
        provider outside the baseline set (e.g. it lands on Criterion).

        Read-only: the caller un-defers the film and lets the normal Type-4 / provider
        discovery perform the actual transition. Both signals are compared against the same
        TMDB endpoints used in normal discovery, so the baseline and the live read agree.
        """
        # Signal 1: new Type-4 digital date (baseline is usually None for an old film, so any
        # real digital release is unambiguously new).
        baseline_t4 = movie.get('_reissue_baseline_type4')
        new_t4 = self.host.fetch_tmdb_type4_date(movie_id)
        if new_t4 and (not baseline_t4 or new_t4 > baseline_t4):
            return True

        # Signal 2: a watch provider not present at defer time.
        baseline = {p.lower() for p in movie.get('_reissue_baseline_providers', [])}
        if str(movie_id).startswith('tv_'):
            url = f"https://api.themoviedb.org/3/tv/{str(movie_id).replace('tv_', '')}/watch/providers"
        else:
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
        try:
            r = requests.get(url, params={'api_key': self.tmdb_key}, timeout=(5, 15))
            if r.ok:
                us = r.json().get('results', {}).get('US', {})
                for kind in ('flatrate', 'rent', 'buy'):
                    for p in us.get(kind, []):
                        name = (p.get('provider_name') or '').lower()
                        if name and name not in baseline:
                            return True
        except Exception as e:
            self.logger.warning(f"Deferred reissue provider check failed for "
                                f"{movie.get('title', movie_id)}: {e}")
        return False

    def _verify_before_wall(self, movie_id, movie, buyonly=False):
        """JustWatch pre-check before adding a movie to the wall.

        Calls verify_availability() to confirm the movie has real streaming/VOD
        links on our target platforms. Prevents movies from hitting the wall
        with zero watch links.

        Bypasses (let through without JW check):
        - Manually-added movies (_added_manually) — curator decision
        - Apple Music Live specials (_apple_music_live) — JW blind spot
        - Movies with watch_link overrides — curator decision
        - Virtual screenings (Eventive, Shift72, etc.) — own link lifecycle
        None for a film the owner reverted: JustWatch decides (an Apple Music Live special,
        which JustWatch can't see, on TMDB's date after the revert).

        Returns:
            dict: JW result with watch_links on success, or bypass marker
            None: on failure/no match (movie stays in tracking)
        """
        title = movie.get('title', '')
        year = movie.get('year')
        content_type = 'tv' if str(movie_id).startswith('tv_') else 'movie'
        original_title = movie.get('original_title')
        tmdb_id = str(movie_id).replace('tv_', '')

        self._pending_putbacks.pop(str(movie_id), None)
        # A buy-only pre-order (its flags dropped just before this check) is held here too: no
        # pre-order or festival bypass, festival pages left out -- JustWatch decides for it.
        held = _is_held(movie) or bool(buyonly)
        # A film the owner sent back (Revert): JustWatch decides, never a curator bypass.
        reverted = bool(movie.get('_reverted_by_owner'))

        # --- Bypass checks: these movies skip JW verification ---
        if movie.get('_added_manually') and not reverted:
            return {'verified': True, '_bypass': 'manual_add'}
        if movie.get('_apple_music_live'):
            if reverted:
                return self._reverted_apple_music_live(movie_id, movie)
            return {'verified': True, '_bypass': 'apple_music_live'}
        if (not reverted and hasattr(self.host, 'watch_links_overrides')
                and str(movie_id) in self.host.watch_links_overrides):
            return {'verified': True, '_bypass': 'override'}
        # Pre-orders already on wall — date arrived, let enrichment handle them.
        # Blocking here would leave them stuck as pre-orders forever. Not for a HELD
        # film: enrichment already sent it back once, and letting it through again
        # every run was the nightly pre-order loop (66 films, Nov 2026). JustWatch
        # decides for it here instead, every run.
        if not held and (movie.get('_type4_pending') or movie.get('_is_preorder') or movie.get('_buyonly_preorder')):
            return {'verified': True, '_bypass': 'preorder_graduation'}
        # Virtual screenings (Eventive, Shift72, Sundance) have their own links, not on JW.
        # Not for a held film (incl. an EXPIRED screening returned to tracking): it must be
        # confirmed on JustWatch like any release — TMDB still lists 'Eventive' for some.
        # (A held film with a screening confirmed live this run is let through by the
        # provider path's own live-link check, never by a stale listing.)
        _vs_platforms = {'eventive', 'shift72', 'sundance'}
        all_providers = (movie.get('providers', {}).get('streaming', [])
                         + movie.get('providers', {}).get('rent', [])
                         + movie.get('providers', {}).get('buy', []))
        if not held and any(
                any(vs in p.lower() for vs in _vs_platforms)
                for p in all_providers if isinstance(p, str)):
            return {'verified': True, '_bypass': 'virtual_screening'}

        # A held film is checked EVERY run until it lands — no strike limit (owner,
        # Nov 2026: "all things flagged as pre-releases should be checked daily ... we
        # need to catch them the day they come out"). The old 4-strike permanent skip
        # silently dropped 443 films; its flag is retired here, but remembered for
        # dating: those films went unchecked for months.
        was_skipped = bool(movie.pop('_skip_provider_discovery', None))
        revert_count = movie.get('_jw_revert_count', 0)
        today = datetime.now().strftime('%Y-%m-%d')

        # Lazy-init JustWatch client
        if self._jw_client is None:
            from pipeline.justwatch import JustWatchClient
            self._jw_client = JustWatchClient(logger=self.logger)

        excl_list = self.config.get('tracking', {}).get('excluded_services',
                     ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play',
                      'Shahid VIP', 'Viki', 'Futo'])
        if held:
            excl_list = list(excl_list) + FESTIVAL_PLATFORMS
        amazon_tag = self.enrichment._get_amazon_affiliate_tag() if self.enrichment else None

        self._jw_lookups += 1
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
            # A malformed reply (offers/package null) or a crash in the lookup is a
            # JustWatch error, not an answer about the film: nothing goes on the wall
            # unconfirmed, no strike, checked again next run.
            self._jw_errors += 1
            self.logger.warning(f"JW verification error for {title}: {e}")
            print(f"  ⏸ {title} — JustWatch error ({type(e).__name__}: {str(e)[:80]}), "
                  f"leaving in tracking (no strike)")
            if was_skipped:
                movie['_skip_provider_discovery'] = True  # still unchecked: keep for dating
            return None

        # A JustWatch API/network error (incl. throttling) says nothing about the film:
        # no strike, re-checked next run.
        if result is None and getattr(self._jw_client, 'last_error', None):
            self._jw_errors += 1
            print(f"  ⏸ {title} — JustWatch error ({self._jw_client.last_error}), "
                  f"leaving in tracking (no strike)")
            if was_skipped:
                movie['_skip_provider_discovery'] = True  # still unchecked: keep for dating
            return None

        if result is None or not result.get('verified'):
            # JW_BREAKER: a blocked JustWatch returns HTTP 200 with empty results ("no
            # match"), and an outage can return titles with empty offer lists ("no valid
            # offers"). Confirm JW is healthy before counting either against the film.
            if not self._check_jw_health():
                print(f"  ⏸ {title} — JW unreachable, leaving in tracking (no strike)")
                if was_skipped:
                    movie['_skip_provider_discovery'] = True
                return None
            # Count the check (for the report) and keep holding — checked again next run.
            revert_count += 1
            movie['_jw_revert_count'] = revert_count
            # A different film's result (title mismatch) means JustWatch didn't find ours.
            no_match = result is None or result.get('match_confidence') == 'first_result'
            reason = 'justwatch_no_match' if no_match else 'justwatch_no_valid_offers'
            # Keep the last "not out yet" day first: an older hold has it only as an
            # estimate tied to its reason, which a "no match" reason would erase.
            putback.note_refuted(movie, putback.last_refuted_day(movie, today))
            movie['_jw_revert_reason'] = reason
            movie.setdefault('_jw_reverted_at', today)
            movie['_jw_last_checked'] = today
            if not no_match:
                putback.note_refuted(movie, today)  # JustWatch has it, no way to watch it today
            print(f"  🚫 {title} — not on JustWatch yet ({reason}), held in tracking, "
                  f"checked again next run (check #{revert_count})")
            return None

        held_reason = movie.get('_jw_revert_reason') if movie.get('_jw_revert_count') else None
        # An expired festival screening returned to tracking is a pulled film too:
        # date its regular release from evidence, not from the day we notice it.
        if not held_reason and movie.get('_screening_expired') and not movie.get('_put_back_on'):
            held_reason = 'screening_returned'
        if not held_reason and movie.get('_rent_preorder_held'):
            held_reason = 'rent_preorder'   # the store page read "Pre-order" until now
        backlog = bool(held_reason) and (was_skipped or revert_count >= 4
                                         or held_reason == 'screening_returned')
        if backlog and self._backlog_putbacks >= self.MAX_BACKLOG_PUTBACKS_PER_RUN:
            # Confirmed, but today's batch of long-held put-backs is full: land it next
            # run so enrichment's 100-film cap goes to today's releases first. No strike.
            print(f"  ⏳ {title} — confirmed after a long hold; queued for the next run "
                  f"(backlog limit {self.MAX_BACKLOG_PUTBACKS_PER_RUN}/run)")
            if was_skipped:
                movie['_skip_provider_discovery'] = True
            return None

        # Cache watch_links for enrichment to reuse (avoids redundant JW call)
        wl = result.get('watch_links', {})
        if wl and self.enrichment:
            self.enrichment.watch_links_cache[str(movie_id)] = {
                'links': wl,
                'cached_at': datetime.now().isoformat(),
                'source': 'discovery_pre_verification'
            }

        # A held film is dated now (pipeline/putback.py: the day it actually became
        # available, never on a day it was seen not out yet) but PUT BACK only when it
        # really goes on the wall (_transition). A later check this run — the store
        # pre-order page — may still hold it, and then its hold history must survive so
        # tomorrow's check happens.
        if held_reason:
            tmdb_failed = False
            if str(movie_id).startswith('tv_'):
                tmdb_theatrical, tmdb_digital = None, None
            else:
                _dates = self.host.fetch_tmdb_us_release_dates(movie_id)
                tmdb_failed = _dates is None  # TMDB error: its date is unknown, not absent
                tmdb_theatrical, tmdb_digital = _dates or (None, None)
            day, source = putback.putback_date(movie, was_skipped, tmdb_digital,
                                               result.get('offer_dates'), tmdb_theatrical, today)
            _page_ok = False
            if reverted:
                # The owner sent it back as not out yet: only something new since then that shows
                # it watchable now brings it back (a new streaming offer, an Amazon rental going
                # live) -- or its store page turning from "Pre-order" (read after the revert) to
                # "available". What JustWatch lists otherwise, and TMDB's date, are what put it on
                # the wall by mistake; a page that read "available" all along is the owner's call.
                # Full times where JustWatch gives them: a release the afternoon of a morning
                # revert is new since it, though its day isn't.
                _streams = result.get('stream_offer_times') or result.get('stream_offer_dates')
                _starts = result.get('live_rent_start_times') or result.get('live_rent_starts')
                _vod = (result.get('watch_links') or {}).get('vod') or []
                if not putback.revert_live_evidence(movie, _streams, _starts, today) and _vod:
                    # Amazon's page when JustWatch lists Amazon (the store page we can read),
                    # else the first store's (_check_preorder_page picks it).
                    _verdict = self._check_preorder_page(result, title)
                    if _verdict == 'pre-order':   # an unreadable page ('captcha', None) says nothing
                        putback.note_refuted(movie, today)   # the store page: still a pre-order today
                        movie['_revert_page_preorder'] = today
                    # The turn: a page read "Pre-order" after the revert, and now shows it for rent
                    # or sale ('released': Amazon's real wording, "Rent HD $9.99 Buy HD $19.99").
                    _page_ok = (_verdict in ('available', 'released')
                                and bool(movie.get('_revert_page_preorder')))
                back = putback.owner_revert_putback(movie, _streams, _starts, _page_ok, tmdb_digital, today)
                if not back:
                    # Waits, no strike; checked again next run. Not a "not out yet" day by
                    # itself (JustWatch may list a release late), so its reason goes back to the
                    # revert's: an earlier no-offer day keeps its own record (_jw_last_refuted).
                    movie['_jw_last_checked'] = today
                    movie['_jw_revert_reason'] = putback.OWNER_REVERT
                    print(f"  ⏳ {title} — reverted by the owner on {movie.get('_reverted_by_owner')}; "
                          f"nothing new since, still waiting")
                    return None
                day, source = back
            self._pending_putbacks[str(movie_id)] = {
                'day': day, 'source': source, 'backlog': backlog,
                # TMDB unreachable: its dates are unknown, and the theater-week guard is off —
                # whatever the source, the owner checks this date.
                'review': putback.needs_review(source, movie, was_skipped, today) or tmdb_failed,
                'held_since': (movie.get('_jw_reverted_at') or movie.get('_screening_returned_at')
                               or movie.get('_rent_preorder_held')),
                # A reverted film its store page shows out now: proof enough before TMDB's date.
                'page_available': _page_ok,
            }

        return result

    def _reverted_apple_music_live(self, movie_id, movie):
        """An Apple Music Live special the owner reverted. JustWatch lists no Apple Music offers
        (a special not reverted skips it altogether), so TMDB's digital date is the only signal:
        back once that date falls after the revert, and after any later "not out yet" day, and
        has arrived. Otherwise it waits (no strike), checked again next run."""
        today = datetime.now().strftime('%Y-%m-%d')
        dates = None if str(movie_id).startswith('tv_') else self.host.fetch_tmdb_us_release_dates(movie_id)
        digital = ((dates or (None, None))[1] or '')[:10]
        floor = putback.last_refuted_day(movie, today) or (movie.get('_reverted_by_owner') or '')[:10]
        if digital and floor < digital <= today:
            self._pending_putbacks[str(movie_id)] = {
                'day': digital, 'source': putback.EVIDENCE, 'backlog': False, 'review': False,
                'held_since': movie.get('_jw_reverted_at')}
            return {'verified': True, '_bypass': 'apple_music_live'}
        movie['_jw_last_checked'] = today
        print(f"  ⏳ {movie.get('title', movie_id)} — Apple Music Live special reverted by the owner on "
              f"{movie.get('_reverted_by_owner')}; waiting for TMDB to date its release after that")
        return None

    def _putback_still_preorder(self, movie_id, movie, jw_result):
        """A held film about to go back on the wall on TMDB's date (the Type-4 paths) gets the
        provider path's store check: a store page still reading "Pre-order" keeps it waiting --
        JustWatch's listing decides, never TMDB's date alone. True if it was held here."""
        _held = str(movie_id) in self._pending_putbacks and self._is_held_rent_preorder(
            movie_id, movie, jw_result)
        if not _held:
            return False
        self._pending_putbacks.pop(str(movie_id), None)
        today = datetime.now().strftime('%Y-%m-%d')
        if _held != 'captcha':   # Amazon's robot check proves nothing: held today, nothing recorded
            movie['_rent_preorder_held'] = today
            putback.note_refuted(movie, today)
            print(f"  ⏳ {movie.get('title', movie_id)} — TMDB dates it out, but its store page still "
                  f"reads 'Pre-order'; holding in tracking")
        else:
            print(f"  ⏸ {movie.get('title', movie_id)} — TMDB dates it out, but its store page couldn't "
                  f"be read (Amazon's robot check); checked again next run")
        return True

    def _transition(self, movie_id, movie, source, newly_available_ids):
        """Put a film on the wall. A held film confirmed this run is PUT BACK here — dated
        from evidence (computed in _verify_before_wall) — now that it actually goes on;
        the transition then clears its hold history."""
        pb = self._pending_putbacks.pop(str(movie_id), None)
        title = movie.get('title', movie_id)
        # Keep the last "not out yet" day past this move: the transition clears the hold
        # fields, and a later pull (a PVOD gate, a no-match) must not let the next
        # put-back land on or before it.
        putback.note_refuted(movie, putback.last_refuted_day(movie))
        if pb:
            day, how = pb['day'], pb['source']
            movie['_held_since'] = pb.get('held_since')
            movie['_put_back_on'] = datetime.now().strftime('%Y-%m-%d')
            if movie.get('digital_date') and movie.get('digital_date') != day:
                movie['_date_before_putback'] = movie.get('digital_date')
            movie['digital_date'] = day
            movie['_digital_date_source'] = how
            movie.pop('_rent_preorder_held', None)
            movie.pop('_is_preorder', None)  # JustWatch confirmed it: watchable now
            if pb.get('review'):
                movie['_date_needs_review'] = True
                print(f"  📅 {title} — back after a hold since {pb.get('held_since')}; dated {day} "
                      f"({how}) — date flagged for review")
            else:
                movie.pop('_date_needs_review', None)
                print(f"  📅 {title} — back after a hold since {pb.get('held_since')}; dated {day} ({how})")
            if pb.get('backlog'):
                self._backlog_putbacks += 1
        elif movie.get('_digital_date_source') in putback.PROTECTED_SOURCES:
            movie.pop('_digital_date_source', None)  # an old put-back's date: this path dates it
        _first_offer_dated = bool(movie.pop('_dated_by_first_offer', None))
        if not pb and not _first_offer_dated:
            # Never dated on or before a day a check proved it not out (a TMDB date that moved
            # back past it): it is out from today.
            _lr = putback.last_refuted_day(movie)
            _dd = (movie.get('digital_date') or '')[:10]
            if _lr and _dd and _dd <= _lr:
                movie['digital_date'] = datetime.now().strftime('%Y-%m-%d')
                print(f"  📅 {title} — TMDB dates it {_dd}, but a check found it not out on {_lr}; "
                      f"dated {movie['digital_date']}")
        _max_age = int(os.environ.get('NRW_PUTBACK_MAX_AGE_DAYS') or self.PUTBACK_MAX_AGE_DAYS)  # tests widen it
        _cutoff = (datetime.now() - timedelta(days=_max_age)).strftime('%Y-%m-%d')
        _too_old = bool(pb or _first_offer_dated) and bool(movie.get('digital_date')) and \
            movie['digital_date'][:10] < _cutoff
        if _too_old:
            print(f"  🗄  {title} — out since {movie['digital_date'][:10]}, more than "
                  f"{_max_age} days ago: marked available, not added to the wall")
        self.host._transition_movie_to_available(movie_id, movie, source, newly_available_ids,
                                                 add_to_site=not _too_old)

    def _jw_shows_rent_or_stream(self, movie_id, movie):
        """Daily JustWatch check for a buy-only pre-order: can you watch it NOW? A
        streaming offer, or an Amazon rental past its offer start. Another store's rental
        counts only if its page reads "available": stores list pre-order rentals as plain
        RENT offers (Fandango At Home: DreamQuil, Nov 2026; Apple's store from the theater
        opening), and Fandango's pages can't be read. (A day TMDB lists a rental or stream,
        the provider path makes the same check on its own JustWatch lookup.) True / False, or
        None when JustWatch couldn't answer — an error or no match says nothing: "not today",
        nothing recorded."""
        if self._jw_client is None:
            from pipeline.justwatch import JustWatchClient
            self._jw_client = JustWatchClient(logger=self.logger)
        excl_list = list(self.config.get('tracking', {}).get('excluded_services',
                     ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play',
                      'Shahid VIP', 'Viki', 'Futo'])) + FESTIVAL_PLATFORMS
        self._jw_lookups += 1
        try:
            r = self._jw_client.verify_availability(
                movie.get('title', ''), movie.get('year'), excluded_services=excl_list,
                content_type='tv' if str(movie_id).startswith('tv_') else 'movie',
                original_title=movie.get('original_title'),
                tmdb_id=str(movie_id).replace('tv_', ''))
        except Exception as e:
            self._jw_errors += 1
            self.logger.warning(f"Buy-only daily check failed for {movie.get('title', movie_id)}: {e}")
            return None
        if r is None and getattr(self._jw_client, 'last_error', None):
            self._jw_errors += 1  # an API/network error: counted for /morning, nothing recorded
            return None
        if not r or r.get('match_confidence') == 'first_result':
            return None
        # No offers at all can be an outage (titles come back with empty offer lists): it
        # must not count as a "still not out" day unless JustWatch is healthy.
        if not r.get('verified') and not self._check_jw_health():
            return None
        self._last_buyonly_jw = r   # for dating the graduation (its first offer record)
        _lab = self._detect_buyonly_preorder(r, movie_id, movie.get('title', ''))
        if _lab['reason'] == 'unreadable':
            return None   # Amazon's robot check: no answer today
        return not _lab['is_preorder']

    def _buyonly_still_waiting(self, movie_id, movie, tmdb_rent_or_stream=False, date_today=False):
        """A buy-only pre-order waits until the pre-order labeler (_detect_buyonly_preorder)
        says it is out -- buyable counts. True while it waits; otherwise drops its pre-order
        flags (graduation) and returns False, dated by JustWatch's first offer record. A day
        the labeler finds positive pre-order evidence is remembered as "not out yet".
        tmdb_rent_or_stream: TMDB lists a rental/stream -- the provider path decides (PO-3)."""
        if not movie.get('_buyonly_preorder'):
            return False
        today = datetime.now().strftime('%Y-%m-%d')
        if not tmdb_rent_or_stream:
            shows = self._jw_shows_rent_or_stream(movie_id, movie)
            if not shows:
                if shows is False:  # JustWatch answered: still a pre-order today
                    movie['_jw_last_checked'] = today
                    putback.note_refuted(movie, today)
                return True
        movie.pop('_buyonly_preorder', None)
        movie.pop('_is_preorder', None)
        if not tmdb_rent_or_stream:
            # Out by JustWatch's own answer: dated the day it became watchable (its first offer
            # record), never on a day the store page read "Pre-order".
            movie['digital_date'] = self._first_offer_day(getattr(self, '_last_buyonly_jw', None), movie, today, movie_id)
        elif date_today:
            movie['digital_date'] = today
        if tmdb_rent_or_stream:   # the provider path checks JustWatch next, and may keep it waiting
            print(f"  … {movie.get('title', movie_id)} — buy-only pre-order: TMDB lists a rental or "
                  f"stream; checking JustWatch")
        else:
            print(f"  ✓ {movie.get('title', movie_id)} — buy-only pre-order graduated (rent/streaming found)")
        return False

    # ------------------------------------------------------------------
    # Main discovery entry point
    # ------------------------------------------------------------------

    def _fetch_providers(self, movie_id, movie):
        """Fetch the TMDB watch/providers payload for ONE movie (the SECONDARY
        discovery signal). Extracted verbatim from the old inline loop block so the
        retry/backoff/error behaviour is byte-identical.

        Thread-safe: uses module-level requests.get (no shared Session), so it is
        safe to call from many prefetch workers at once.

        Returns (data_or_None, errors_list, failed_count) — the caller merges these
        into api_errors / failed exactly as the inline code used to.
        """
        if str(movie_id).startswith('tv_'):
            numeric_id = str(movie_id).replace('tv_', '')
            url = f"https://api.themoviedb.org/3/tv/{numeric_id}/watch/providers"
        else:
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
        params = {'api_key': self.tmdb_key}

        errors = []
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=(5, 15))
                if response.status_code == 200:
                    return response.json(), errors, 0
                elif response.status_code == 429:  # Rate limited
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': 'rate_limit', 'status_code': 429, 'timestamp': datetime.now().isoformat()})
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.warning(f"HTTP {response.status_code} for {movie['title']}")
                    errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': 'http_error', 'status_code': response.status_code, 'timestamp': datetime.now().isoformat()})
                    return None, errors, 0
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.warning(f"Failed after {max_retries} attempts for {movie['title']}: {type(e).__name__}")
                    errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': type(e).__name__, 'status_code': None, 'timestamp': datetime.now().isoformat()})
                    return None, errors, 1
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request error for {movie['title']}: {type(e).__name__}")
                errors.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'error_type': type(e).__name__, 'status_code': None, 'timestamp': datetime.now().isoformat()})
                return None, errors, 1
        return None, errors, 0

    def _prefetch_discovery_data(self, tracking_movies, max_workers=8):
        """Concurrently collect the per-movie TMDB payloads discovery needs — the
        Type 4 digital date and (when there's no usable Type 4 date) the
        watch/providers data. READ-ONLY: it mutates no state and makes no
        decisions; check_tracking_movies still does every transition, exactly as
        before, just reading these results instead of calling the network inline.
        That is what turns the ~84-minute serial poll into a few minutes WITHOUT
        changing a single discovery decision.

        Correctness note: a missing entry (or missing key) makes the caller fall
        back to a live fetch, so results never depend on prefetch coverage — an
        un-deferred reissue, a malformed Type 4 date, etc. all still resolve.

        Memory: holds one small JSON per movie (~tens of MB for the full ~14k
        wall); released when this method returns.

        Returns {movie_id: {'type4_date', 'provider_data', 'provider_errors',
        'provider_failed'}} (provider_* present only when fetched).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _work(item):
            movie_id, movie = item
            out = {}
            # Every film gets a fresh Type 4 read — pending pre-orders included: their
            # stored date is re-checked daily (TMDB moves announced dates).
            td = self.host.fetch_tmdb_type4_date(movie_id)
            out['type4_date'] = td
            if not movie.get('_type4_pending'):
                # The loop consults providers only when there's no usable Type 4
                # date (a valid past/future date short-circuits it). Mirror that so
                # we never fetch payloads the loop won't read. (A malformed-but-
                # non-empty date is rare and handled by the caller's live fallback.)
                if not td:
                    data, errors, failed = self._fetch_providers(movie_id, movie)
                    out['provider_data'] = data
                    out['provider_errors'] = errors
                    out['provider_failed'] = failed
            return movie_id, out

        results = {}
        total = len(tracking_movies)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_work, item) for item in tracking_movies]
            done = 0
            for fut in as_completed(futures):
                movie_id, out = fut.result()
                results[movie_id] = out
                done += 1
                if done % 1000 == 0 or done == total:
                    print(f"  ⚡ Prefetch: {done}/{total} movies fetched")
        return results

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

        self._backlog_putbacks = 0
        self._pending_putbacks = {}
        self._jw_lookups = 0
        self._jw_errors = 0

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

        # Held films (~600, each a JustWatch lookup every run) go after everything else:
        # today's releases reach JustWatch first (a mid-run throttle hits put-backs, which
        # just wait a day) and come first in enrichment's 100-film queue. Stable sort:
        # date order is kept within each group.
        tracking_movies.sort(key=lambda item: _is_held(item[1]))

        # Limit if max_to_check specified (only when poll_all_tracking is false)
        if max_to_check and not poll_all_tracking:
            tracking_movies = tracking_movies[:max_to_check]
            print(f"  Limiting check to first {len(tracking_movies)} movies")

        newly_digital = 0
        checked = 0
        failed = 0
        rent_preorders_held = 0  # Amazon pre-order rentals held in tracking (JustWatch lists them as live RENT)
        held_preorder_details = []  # Breadcrumb: which titles were held as pre-orders
        self._captcha_blocks = []  # Titles where the store page hit a CAPTCHA wall (for the report)
        total_to_check = len(tracking_movies)
        newly_available_ids = []  # Track movie IDs that transition to available
        transition_details = []  # Breadcrumb: which movies transitioned and why
        api_errors = []  # Breadcrumb: API failures during discovery

        print(f"\n🎬 Checking {total_to_check} movies for digital availability...\n")
        discovery_start_time = time.time()

        # PARALLEL PREFETCH (read-only): collect every movie's TMDB Type 4 + provider
        # payloads concurrently up front, so the decision loop below is pure in-memory
        # logic. Same data → same decisions; the 14k serial waits + per-movie sleeps
        # are gone. A missing entry falls back to a live fetch inside the loop.
        max_workers = self.config.get('api', {}).get('tmdb_max_workers', 8)
        prefetch_start = time.time()
        print(f"  ⚡ Prefetching discovery data for {total_to_check} movies "
              f"({max_workers} workers)...")
        prefetched = self._prefetch_discovery_data(tracking_movies, max_workers=max_workers)
        print(f"  ⚡ Prefetch complete in {int(time.time() - prefetch_start)}s")

        try:
            for movie_id, movie in tracking_movies:
                checked += 1
                putback.freeze_legacy_check(movie)  # an old hold's estimated last check stops sliding

                # Progress indicator every 100 movies (less noisy but still informative)
                if checked % 100 == 0 or checked == total_to_check:
                    progress_pct = (checked / total_to_check) * 100
                    elapsed = time.time() - discovery_start_time
                    rate = checked / elapsed if elapsed > 0 else 0
                    remaining = (total_to_check - checked) / rate if rate > 0 else 0
                    print(f"  📊 Discovery: {checked}/{total_to_check} ({progress_pct:.1f}%) | {newly_digital} found | {int(elapsed//60)}m elapsed | ~{int(remaining//60)}m remaining")

                # DEFERRED REISSUE: an OLD film parked in tracking until its RESTORATION gets
                # a *new* digital release. Old films usually already carry stale VOD availability
                # (Utena: already rentable on Amazon), so the normal binary checks would
                # false-fire immediately. Only act when something CHANGED versus the baseline
                # captured at defer time; if so, un-defer and fall through to the normal Type-4 /
                # provider discovery below (which handles past/future/pre-order/JW correctly).
                if movie.get('_reissue_deferred') and movie['status'] == 'tracking':
                    if self._deferred_reissue_signal_changed(movie_id, movie):
                        for k in ('_reissue_deferred', '_reissue_baseline_type4',
                                  '_reissue_baseline_providers', '_skip_provider_discovery'):
                            movie.pop(k, None)
                        self.logger.info(f"Deferred reissue un-deferred (new digital signal): {movie.get('title', movie_id)}")
                        print(f"  🎬 {movie.get('title', movie_id)} — reissue digital release detected, evaluating for wall")
                        # fall through to normal discovery below (no continue)
                    else:
                        continue  # still no change — keep waiting, skip the normal binary checks

                # PRIMARY: Type 4 digital release check (authoritative, gives accurate date)
                type4_found = False
                if movie['status'] == 'tracking':
                    today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

                    if movie.get('_type4_pending'):
                        # Pre-order with a stored Type 4 date. Re-read TMDB's date every
                        # run: a stored date was never refreshed, so a moved or mistyped
                        # date parked films for months (Spa Weekend sat on 2028-09-22
                        # while TMDB said 2026-09-22).
                        _fresh = (prefetched.get(movie_id) or {}).get('type4_date')
                        if _fresh and _fresh != movie.get('digital_date'):
                            print(f"  🗓 {movie.get('title', movie_id)} — TMDB digital date moved "
                                  f"{movie.get('digital_date')} → {_fresh}")
                            movie['digital_date'] = _fresh
                            # Its PRE-ORDER entry moves too (never creates one): a stale later
                            # date would let enrichment graduate it unchecked (Wicker, Nov 2026).
                            self.host.update_wall_entry_date(movie_id, _fresh)
                        pending_date = movie.get('digital_date')
                        if pending_date:
                            try:
                                pending_dt = datetime.strptime(pending_date, '%Y-%m-%d')
                                if pending_dt <= today_dt:
                                    # Date arrived — a buy-only pre-order still needs a rental
                                    if self._buyonly_still_waiting(movie_id, movie, date_today=True):
                                        type4_found = True
                                        continue
                                    # Verify JW before transitioning
                                    jw_result = self._verify_before_wall(movie_id, movie)
                                    if jw_result is None:
                                        type4_found = True  # Don't fall through to provider check
                                        continue
                                    if self._putback_still_preorder(movie_id, movie, jw_result):
                                        rent_preorders_held += 1
                                        held_preorder_details.append({'movie_id': str(movie_id), 'title': movie.get('title', '')})
                                        type4_found = True
                                        continue
                                    self._transition(
                                        movie_id, movie, 'tmdb_type4', newly_available_ids)
                                    newly_digital += 1
                                    transition_details.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'source': 'tmdb_type4', 'timestamp': datetime.now().isoformat()})
                                    self.logger.info(f"Type 4 pending released: {movie['title']} — {pending_date}")
                                    print(f"  📅 {movie['title']} — pending Type 4 arrived ({pending_date})")
                                else:
                                    days_until = (pending_dt - today_dt).days
                                    # Ensure pending movie is on wall as pre-order (migrates existing pending movies)
                                    # -- not one the owner reverted: off the wall until it's really out.
                                    if not movie.get('_is_preorder') and not movie.get('_reverted_by_owner'):
                                        movie['_is_preorder'] = True
                                        self.host.add_movie_to_site_immediately(movie_id, movie)
                                        newly_available_ids.append(str(movie_id))  # Enrich on entry (trailers, Wiki, RT)
                                        print(f"  🏷️ {movie['title']} — added to wall as pre-order ({pending_date})")
                                    self.logger.debug(f"Type 4 still pending: {movie['title']} — {days_until}d until {pending_date}")
                            except ValueError:
                                pass
                            # Skip the provider check — valid pending date. Not for a HELD film:
                            # JustWatch decides for it every run (provider path), whatever date
                            # TMDB gives (Liberation: on Amazon while TMDB said 11-17).
                            type4_found = not (_is_held(movie) and movie['status'] == 'tracking')
                        else:
                            # Bad state: pending flag with no date — clear and fall through to provider check
                            movie.pop('_type4_pending', None)
                            self.logger.warning(f"Cleared _type4_pending with no digital_date: {movie.get('title', movie_id)}")

                    else:
                        # Fresh lookup — Type 4 date from the parallel prefetch.
                        # Live fallback if this movie wasn't prefetched (e.g. an
                        # un-deferred reissue), so results stay identical to serial.
                        _pf = prefetched.get(movie_id)
                        if _pf is not None and 'type4_date' in _pf:
                            type4_date = _pf['type4_date']
                        else:
                            type4_date = self.host.fetch_tmdb_type4_date(movie_id)
                        if type4_date:
                            try:
                                type4_dt = datetime.strptime(type4_date, '%Y-%m-%d')
                                if type4_dt <= today_dt:
                                    # Past or today — verify JW before transitioning
                                    _dd_before_t4 = movie.get('digital_date')
                                    movie['digital_date'] = type4_date
                                    # A buy-only pre-order still needs a rental first
                                    if self._buyonly_still_waiting(movie_id, movie, date_today=True):
                                        if _dd_before_t4 is None:
                                            movie.pop('digital_date', None)
                                        else:
                                            movie['digital_date'] = _dd_before_t4
                                        type4_found = True
                                        continue
                                    jw_result = self._verify_before_wall(movie_id, movie)
                                    if jw_result is None:
                                        type4_found = True  # Don't fall through to provider check
                                        continue
                                    if self._putback_still_preorder(movie_id, movie, jw_result):
                                        if _dd_before_t4 is None:
                                            movie.pop('digital_date', None)
                                        else:
                                            movie['digital_date'] = _dd_before_t4
                                        rent_preorders_held += 1
                                        held_preorder_details.append({'movie_id': str(movie_id), 'title': movie.get('title', '')})
                                        type4_found = True
                                        continue
                                    self._transition(
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
                                    # Skip the provider check -- not for a HELD film: JustWatch
                                    # decides for it every run, whatever date TMDB gives.
                                    type4_found = not (_is_held(movie) and movie['status'] == 'tracking')
                                    if movie.get('_reverted_by_owner'):
                                        # The owner reverted it: off the wall (no pre-order entry)
                                        # until it's really out; JustWatch checks it every run.
                                        print(f"  ⏳ {movie['title']} — digital in {days_until}d ({type4_date}); "
                                              f"reverted by the owner, stays off the wall until then")
                                    else:
                                        movie['_is_preorder'] = True
                                        self.host.add_movie_to_site_immediately(movie_id, movie)
                                        newly_available_ids.append(str(movie_id))  # Enrich on entry (trailers, Wiki, RT)
                                        self.logger.info(f"Type 4 future: {movie['title']} — {days_until}d until {type4_date} [pre-order on wall]")
                                        print(f"  ⏳ {movie['title']} — digital in {days_until}d ({type4_date}) [pre-order on wall]")
                            except ValueError:
                                pass

                # SECONDARY: Provider availability check (for ~44% of movies without Type 4)
                if not type4_found and movie['status'] == 'tracking':
                    # Provider payload from the parallel prefetch; live fallback when
                    # absent (movie not prefetched, or a malformed Type 4 date left
                    # the loop here without a prefetched provider payload). The
                    # error/failed accounting is merged exactly as the inline code did.
                    _pf = prefetched.get(movie_id)
                    if _pf is not None and 'provider_data' in _pf:
                        data = _pf['provider_data']
                        if _pf.get('provider_errors'):
                            api_errors.extend(_pf['provider_errors'])
                        failed += _pf.get('provider_failed', 0)
                    else:
                        data, _errs, _failed = self._fetch_providers(movie_id, movie)
                        api_errors.extend(_errs)
                        failed += _failed

                    # A held film (or buy-only pre-order) is checked on JustWatch even when
                    # TMDB's provider lookup failed today (data None): JustWatch decides.
                    if data or _is_held(movie) or movie.get('_buyonly_preorder'):
                        us = (data or {}).get('results', {}).get('US', {})

                        # Get all provider types
                        rent_providers = us.get('rent', [])
                        buy_providers = us.get('buy', [])
                        stream_providers = us.get('flatrate', [])

                        # Extract provider names — NO exclusion filter here.
                        rent_names = [p.get('provider_name', '') for p in rent_providers]
                        buy_names = [p.get('provider_name', '') for p in buy_providers]
                        stream_names = [p.get('provider_name', '') for p in stream_providers]

                        has_providers = bool(rent_names or buy_names or stream_names)

                        # A held film (or a buy-only pre-order) is checked every run.
                        _held = _is_held(movie) or bool(movie.get('_buyonly_preorder'))
                        _vs_live = False  # a screening link confirmed live THIS run

                        # Virtual screening platforms (Eventive, Shift72, Sundance) may not appear
                        # in TMDB provider data. If tracking already has a VS platform AND a cached
                        # or override link exists AND the link is still live, force transition.
                        # Never for an expired screening returned to tracking (JustWatch decides).
                        _vs_platforms = {'eventive', 'shift72', 'sundance'}
                        _orig_providers = (movie.get('providers', {}).get('streaming', [])
                                           + movie.get('providers', {}).get('rent', [])
                                           + movie.get('providers', {}).get('buy', []))
                        # Not for a film the owner reverted either: JustWatch decides
                        # (owner_revert_putback), never its festival screening.
                        _is_virtual_screening = (not movie.get('_screening_expired')
                                                 and not movie.get('_reverted_by_owner') and any(
                            any(vs in p.lower() for vs in _vs_platforms)
                            for p in _orig_providers if isinstance(p, str)))
                        # Held films always get the live-link check: a stale Eventive entry from an
                        # old festival run must not wave them onto the wall unchecked.
                        if _is_virtual_screening and (not has_providers or _held):
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
                            # Validate the screening is still available before forcing transition.
                            # Recognize both the central watch.eventive.org domain and white-label
                            # festival domains (e.g. watch.imaginenative.org/<slug>/play/<id>).
                            _is_eventive_link = bool(_vs_link) and (
                                'eventive.org' in _vs_link
                                or re.match(r'https?://watch\.[^/]+/[^/]+/play/', _vs_link))
                            if _is_eventive_link:
                                _play_info = self.host._fetch_eventive_play_info(_vs_link)
                                _end_date = _play_info.get('available_end')
                                _today = datetime.now().strftime('%Y-%m-%d')
                                _end_in_future = bool(_end_date) and _end_date >= _today
                                if _play_info.get('is_available') is True:
                                    has_providers = True
                                    _vs_live = True
                                    movie['_virtual_screening'] = True
                                    print(f"  ✓ {movie['title']} — VS bypass: screening active ({_vs_link})")
                                elif _end_in_future:
                                    # Upcoming/pre-order — screening hasn't started but end date is future
                                    has_providers = True
                                    _vs_live = True
                                    movie['_virtual_screening'] = True
                                    print(f"  ✓ {movie['title']} — VS bypass: upcoming screening (ends {_end_date})")
                                else:
                                    print(f"  ⏭ {movie['title']} — VS bypass skipped: screening expired (ended {_end_date or 'unknown'})")
                            elif _vs_link:
                                # Non-Eventive VS links (Shift72, etc.) — HEAD check fallback
                                try:
                                    _head = requests.head(_vs_link, timeout=10, allow_redirects=True)
                                    if _head.status_code < 400:
                                        has_providers = True
                                        _vs_live = True
                                        movie['_virtual_screening'] = True
                                        print(f"  ✓ {movie['title']} — VS bypass: link verified ({_vs_link})")
                                    else:
                                        print(f"  ⏭ {movie['title']} — VS bypass skipped: HTTP {_head.status_code}")
                                except requests.RequestException:
                                    print(f"  ⏭ {movie['title']} — VS bypass skipped: link unreachable")

                        if _held:
                            # JustWatch decides for a held film — the festival bypass only for a
                            # screening confirmed live above — and it is checked even on a day TMDB
                            # lists no provider: a release must be caught the day it comes out.
                            if _is_virtual_screening and not _vs_live:
                                _is_virtual_screening = False
                            if not has_providers:
                                has_providers = True

                        movie['has_providers'] = has_providers

                        if has_providers and movie['status'] == 'tracking':
                            movie['_discovery_source'] = 'provider_availability_check'

                        # DISCOVERY IS STRICTLY BINARY.
                        # Transition provider-discovered movie
                        if has_providers and movie['status'] == 'tracking':
                            # Preserve any pre-existing digital_date so a HOLD below can restore it
                            # (the block further down sets digital_date=today in anticipation of transition).
                            _orig_digital_date = movie.get('digital_date')
                            _was_buyonly = bool(movie.get('_buyonly_preorder'))
                            # Buy-only pre-order guard: only transition if rent/streaming appeared.
                            # Checked daily on JustWatch too, not only TMDB's list (TMDB lags).
                            if self._buyonly_still_waiting(movie_id, movie,
                                                           tmdb_rent_or_stream=bool(rent_names or stream_names)):
                                continue  # Still buy-only — keep as pre-order on wall

                            if not movie.get('digital_date'):
                                # For VS bypass, use screening start_time as digital_date
                                _resolved_date = None
                                # str(movie_id), not _mid: _mid is only set in the VS branch above,
                                # so here it was stale (another film's id) or unbound (NameError).
                                _vs_mid = str(movie_id)
                                if movie.get('_virtual_screening') and _vs_mid in getattr(self.enrichment, 'watch_links_cache', {}):
                                    _vs_cache = self.enrichment.watch_links_cache[_vs_mid]
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
                            if data is not None or not movie.get('providers'):  # keep them on a TMDB error
                                movie['providers'] = {
                                    'rent': rent_names,
                                    'buy': buy_names,
                                    'streaming': stream_names
                                }

                            # JW verification gate — skip for virtual screening platforms
                            if _is_virtual_screening:
                                jw_result = {'verified': True, '_bypass': 'virtual_screening'}
                            else:
                                jw_result = self._verify_before_wall(movie_id, movie, buyonly=_was_buyonly)
                                if jw_result is None:
                                    if _was_buyonly:
                                        # No JustWatch answer (an error, no match): still a buy-only
                                        # pre-order, flags and date as they were -- nothing recorded.
                                        movie['_buyonly_preorder'] = True
                                        movie['_is_preorder'] = True
                                        if _orig_digital_date is None:
                                            movie.pop('digital_date', None)
                                        else:
                                            movie['digital_date'] = _orig_digital_date
                                        continue
                                    # Stay in tracking. A held film (incl. one JustWatch just said
                                    # isn't out) gets the speculative 'today' date undone — a hold
                                    # must not move the date; put-back dating dates it later. After
                                    # a JustWatch ERROR, a film with no hold keeps today as its
                                    # first-signal date, so it isn't dated the day JustWatch recovers.
                                    if _is_held(movie):
                                        if _orig_digital_date is None:
                                            movie.pop('digital_date', None)
                                        else:
                                            movie['digital_date'] = _orig_digital_date
                                    continue
                                # A buy-only pre-order TMDB lists a rental or stream for: JustWatch
                                # decides, by the daily check's rule -- streaming, or an Amazon rental
                                # past its offer start; any other listing (purchase only, another
                                # store's rental: stores list pre-order rentals as RENT) only on the
                                # owner's override or a store page reading "available" (the check
                                # enrichment makes). Letting it on here was the nightly loop: on the
                                # wall, flagged back, on again.
                                if (_was_buyonly and not jw_result.get('_bypass')
                                        and not (jw_result.get('has_streaming') or jw_result.get('has_live_rent'))
                                        and self._detect_buyonly_preorder(
                                            jw_result, movie_id, movie.get('title', ''))['is_preorder']):
                                    _t_bo = datetime.now().strftime('%Y-%m-%d')
                                    self._pending_putbacks.pop(str(movie_id), None)
                                    movie['_buyonly_preorder'] = True
                                    movie['_is_preorder'] = True
                                    if _orig_digital_date is None:
                                        movie.pop('digital_date', None)
                                    else:
                                        movie['digital_date'] = _orig_digital_date
                                    movie['_jw_last_checked'] = _t_bo
                                    putback.note_refuted(movie, _t_bo)   # no rental or stream today
                                    print(f"  ⏳ {movie['title']} — TMDB lists a rental or stream, but JustWatch "
                                          f"shows no live way to rent or stream it; still a buy-only pre-order")
                                    continue
                                # A film TMDB still dates in the future goes on early only if
                                # JustWatch shows it watchable NOW (streaming, or an Amazon rental
                                # past its offer start): a store's pre-order listing (Apple's
                                # store lists rentals from the theater opening) waits for its date.
                                _today_pf = datetime.now().strftime('%Y-%m-%d')
                                if (movie.get('_type4_pending') and (_orig_digital_date or '') > _today_pf
                                        and not (jw_result.get('has_streaming') or jw_result.get('has_live_rent'))
                                        and not (self._pending_putbacks.get(str(movie_id)) or {}).get('page_available')):
                                    self._pending_putbacks.pop(str(movie_id), None)
                                    movie['digital_date'] = _orig_digital_date
                                    movie['_jw_last_checked'] = _today_pf
                                    putback.note_refuted(movie, _today_pf)  # not watchable today
                                    print(f"  ⏳ {movie['title']} — JustWatch lists it before TMDB's date "
                                          f"{_orig_digital_date}, but nothing is live yet; waiting")
                                    continue

                            # Pre-order guard: JustWatch lists store pre-order rentals (Amazon,
                            # Apple, Fandango at Home) as ordinary RENT offers with a price. For
                            # pre-orders the only accurate source is the store page, so verify every
                            # rent-listed VOD transition there before going live; if the page reads
                            # as a pre-order, hold in tracking and re-check next run (no fake price).
                            _rp_held = self._is_held_rent_preorder(movie_id, movie, jw_result)
                            if _rp_held:
                                self._pending_putbacks.pop(str(movie_id), None)  # still held
                                # Undo the speculative digital_date set above — real date comes at release
                                if _orig_digital_date is None:
                                    movie.pop('digital_date', None)
                                else:
                                    movie['digital_date'] = _orig_digital_date
                                # Amazon's robot check proves nothing about today: a film already
                                # held (checked daily anyway) records no "not out yet" day for it.
                                if _rp_held != 'captcha' or not _is_held(movie):
                                    movie['_rent_preorder_held'] = datetime.now().strftime('%Y-%m-%d')
                                    putback.note_refuted(movie, movie['_rent_preorder_held'])
                                if _rp_held == 'captcha':
                                    print(f"  ⏸ {movie['title']} — store page unreadable (Amazon's robot check); "
                                          f"holding in tracking, checked again next run")
                                    continue  # stay in tracking (listed in captcha_block_titles)
                                rent_preorders_held += 1
                                held_preorder_details.append({'movie_id': str(movie_id), 'title': movie.get('title', '')})
                                self.logger.info(f"Rent pre-order held: {movie['title']} ({movie_id}) — Amazon page not yet available")
                                print(f"  ⏳ {movie['title']} — rent-listed pre-order (Amazon not yet available), holding in tracking")
                                continue  # stay in tracking

                            # Genuine release — clear any stale hold flag and transition
                            movie.pop('_rent_preorder_held', None)
                            if _was_buyonly and not jw_result.get('_bypass') and str(movie_id) not in self._pending_putbacks:
                                # Out by the pre-order labeler: dated the day it became watchable
                                # (old "still buy-only" days were not proof it wasn't out).
                                movie['digital_date'] = self._first_offer_day(
                                    jw_result, movie, datetime.now().strftime('%Y-%m-%d'), movie_id)
                                movie['_dated_by_first_offer'] = True
                            self._transition(
                                movie_id, movie, 'provider_availability_check', newly_available_ids)
                            newly_digital += 1
                            transition_details.append({'movie_id': movie_id, 'title': movie.get('title', ''), 'source': 'provider_availability_check', 'timestamp': datetime.now().isoformat()})

                            first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0] if buy_names else '?'
                            print(f"  ✓ {movie['title']} now on {first_service}!")

                # Incremental save. The network now happens in the prefetch, so this
                # loop is fast in-memory work — save in larger batches to avoid a rapid
                # burst of full-DB writes (the finally-block still does a final save).
                if checked % 2000 == 0:
                    if self.storage.atomic_write_json(db, 'movie_tracking.json'):
                        print(f"  💾 Progress saved (batch {checked//2000})")
                    else:
                        print(f"  ⚠️ Progress save failed (batch {checked//2000})")

                # (No per-movie rate-limit sleep here anymore — rate limiting now lives
                # in the concurrent prefetch above. This pass is pure in-memory logic.)

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

        held_tag = f", {rent_preorders_held} pre-order rental(s) held" if rent_preorders_held else ""
        completion_msg = f"Polled {checked} tracking movies, found {newly_digital} changes{scan_tag}{held_tag}. {failed} failed."
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
                    'rent_preorders_held': rent_preorders_held,
                    'jw_healthy': self._jw_healthy,  # JW_BREAKER: None=not checked, False=outage detected
                    'jw_lookups': self._jw_lookups,
                    'jw_errors': self._jw_errors,  # films left waiting after a JustWatch error (no strike)
                    'scan_tag': scan_tag.strip() if scan_tag else None
                },
                'transition_details': transition_details[:100],
                'total_transitions': len(transition_details),
                'held_preorder_details': held_preorder_details[:100],
                'captcha_block_titles': list(self._captcha_blocks)[:100],
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

            # Once each: a held film put on the wall as a pre-order and then put back in the
            # same run was listed twice (enriched twice, two slots of the 100-film cap).
            newly_available_ids = list(dict.fromkeys(str(x) for x in newly_available_ids))
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
            str: 'pre-order', 'available', 'captcha' (Amazon's robot check: unreadable --
            callers hold, but record nothing), 'released' (an Amazon page showing it for rent
            or sale, no pre-order wording: only the revert gate acts on it -- every other
            caller treats it as None), or None (could not determine)
        """
        vod_links = jw_result.get('watch_links', {}).get('vod', [])
        if not vod_links:
            return None
        # Amazon's page when JustWatch lists Amazon (the store page we can read), else the first
        # store's: every check (the revert gate, the pre-order guard, the gap fill, the buy-only
        # checks) reads the same page, so one verdict a day per film.
        _links = [e['link'] for e in vod_links if isinstance(e, dict) and e.get('link')]
        url = next((u for u in _links if 'amazon.' in str(u).lower()), _links[0] if _links else None)
        if not url:
            return None
        # One read per page a day: a reverted film's check and the pre-order guard right after
        # it ask about the same page (a second read could also disagree with the first).
        _cache = self.__dict__.setdefault('_page_verdicts', {})
        _key = (datetime.now().strftime('%Y-%m-%d'), _page_key(url))
        if _key not in _cache:
            _cache[_key] = self._read_preorder_page(url, title)
        return _cache[_key]

    def _read_preorder_page(self, url, title):
        """Render one store page and read its buttons: 'pre-order', 'available', 'captcha',
        'released' (Amazon price buttons, no pre-order wording) or None."""
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
                    msg = f"Amazon CAPTCHA wall hit for '{title}' — store page unreadable, holding as pre-order this run"
                    self.logger.warning(msg)
                    print(f"  ⚠️ {msg}")
                    # Record for the morning report so a real CAPTCHA event is visible
                    if isinstance(getattr(self, '_captcha_blocks', None), list):
                        self._captcha_blocks.append(title)
                    return 'captcha'

                has_preorder = any(signal in body_text for signal in preorder_signals)
                has_available = any(signal in body_text for signal in available_signals)

                if has_preorder and not has_available:
                    return 'pre-order'
                elif has_available and not has_preorder:
                    return 'available'
                elif has_preorder and has_available:
                    # Both signals — pre-order takes precedence (safer)
                    return 'pre-order'
                elif (is_amazon and 'pre-order' not in body_text and re.search(
                        r'\b(rent|buy)\s*(sd|hd|uhd|4k)\b[^$]{0,40}\$\s?\d', body_text)):
                    # No button word, but Amazon's own price buttons and no pre-order wording
                    # anywhere (a pre-order reads "Pre-order UHD $24.99"): shown for rent or sale.
                    return 'released'
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
        The pre-order labeler (owner, Nov 2026: "if a movie is rentable it's rentable", "buy-only
        is buyable"; a $19.99 rental while in theaters is a red flag to CHECK, never a block).
        Is this film -- buy-only, or listed with a rental that isn't confirmed live -- still a
        pre-order? Out unless there is positive pre-order evidence:

          1. preorder_overrides[id] True / False -> that verdict
          2. streaming -> out (streaming has no pre-orders)
          3. no digital store at all (nothing, or only Barnes & Noble discs) -> waits
          4. the store page (Amazon's when listed): "Pre-order" -> pre-order (Amazon's page can
             lag its own offer start: The Last Blossom); Amazon's robot check -> waits this run
             (unreadable: 'reason' 'unreadable', callers record nothing); "available" / Amazon's
             own rent/buy price buttons ("Buy UHD $14.99") -> out
          5. an Amazon rental past its offer start -> out; else store offers (rent or buy) whose
             start is still ahead, none already started -> pre-order (with that date)
          6. TMDB dates its US digital release in the future -> pre-order (with that date)
          7. TMDB's digital date has passed -> out (a store lists it, TMDB dates it out)
          8. still in theaters on JustWatch, nothing above confirming a digital start (Apple and
             Fandango list pre-order rentals and purchases from the theater opening) -> pre-order
          9. listed only on Fandango At Home with its page unreadable (Fandango lists pre-orders
             as plain offers: DreamQuil) -> pre-order
         10. otherwise -> out: it can be bought or rented now.

        Returns:
            dict: {'is_preorder', 'override', 'preorder_date' (future Type 4 date),
                   'type4_date', 'verified_genuine' (out), 'reason'}
        """
        result = {'is_preorder': True, 'override': None, 'preorder_date': None,
                  'type4_date': None, 'verified_genuine': False, 'reason': None}

        def _out(why):
            result.update(is_preorder=False, verified_genuine=True, reason=why)
            print(f"  ✓ {title} — out ({why})")
            return result

        def _waits(why):
            result.update(is_preorder=True, reason=why)
            print(f"  🏷️  {title} — pre-order ({why})")
            return result

        override_val = self.config.get('preorder_overrides', {}).get(str(movie_id))
        if override_val is True:
            result['override'] = True
            return _waits('manual override')
        if override_val is False:
            result['override'] = False
            return _out('manual override')
        jw = jw_result if isinstance(jw_result, dict) else {}
        if jw.get('has_streaming'):
            return _out('streaming')
        vod = (jw.get('watch_links') or {}).get('vod') or []

        # Digital stores only: not a disc seller, not a festival's own screening page.
        stores = [v for v in vod if isinstance(v, dict) and v.get('link')
                  and (v.get('service') or '') not in PHYSICAL_STORES and not _is_festival_link(v)]
        if not stores:
            return _waits('no digital store yet' + (' (discs / festival only)' if vod else ''))
        jw = dict(jw, watch_links=dict(jw.get('watch_links') or {}, vod=stores))   # pages: stores only

        page = self._check_preorder_page(jw, title)
        if page == 'pre-order':
            return _waits('store page reads Pre-order')
        if page == 'captcha':
            return _waits('unreadable')   # Amazon's robot check: no answer this run
        if page in ('available', 'released'):
            return _out('store page shows it for sale')
        if jw.get('has_live_rent'):
            return _out('Amazon rental live')
        if jw.get('future_offer_starts') and not jw.get('has_past_offer_start'):
            # A store's own start date still ahead (Amazon's release, Apple's theater opening):
            # nothing is watchable yet -- a pre-order.
            result['preorder_date'] = jw['future_offer_starts'][0]
            return _waits(f"a store's offer starts {jw['future_offer_starts'][0]}")

        type4_date = None if str(movie_id).startswith('tv_') else self.host.fetch_tmdb_type4_date(movie_id)
        today = datetime.now().strftime('%Y-%m-%d')
        if type4_date:
            result['type4_date'] = type4_date
            if type4_date[:10] > today:
                result['preorder_date'] = type4_date
                return _waits(f'TMDB digital date {type4_date}')
        if type4_date and type4_date[:10] <= today:
            return _out(f'TMDB digital date {type4_date}')
        if jw.get('has_cinema'):
            return _waits('in theaters, no confirmed digital start')
        if page is None and all('fandango' in (v.get('service') or '').lower() for v in stores):
            # Fandango At Home lists pre-orders as plain offers ("available to watch on Dec 4 --
            # preorder": DreamQuil) and its page often can't be read: only TMDB's date, another
            # store, or a readable page says it's out.
            return _waits('Fandango-only listing, page unreadable')
        return _out('buyable now')

    def _first_offer_day(self, jw_result, movie, today, movie_id=None):
        """The day a film labelled out became watchable: JustWatch's first record of a real way
        to watch it -- not before TMDB's US digital date when TMDB has one (a listing before it
        was a pre-order listing: Project Hail Mary, Wicker), never on or before a day a check
        proved it not out, never after today."""
        days = sorted(d for d in ((jw_result or {}).get('offer_dates') or []) if d and d <= today)
        # Never on or before a day a check proved it not out (rule 3) -- a store page reading
        # "Pre-order", a labeler pre-order day. (The live system never stored such days for
        # buy-only films, so there is no old "still buy-only" day to discount.)
        floor = max([(movie.get(k) or '')[:10] for k in ('_rent_preorder_held', '_revert_page_preorder')]
                    + [putback.last_refuted_day(movie, today) or ''])
        days = [d for d in days if d > floor]
        day = days[0] if days else today
        mid = str(movie_id or movie.get('id') or '')
        if mid and not mid.startswith('tv_'):
            t4 = (self.host.fetch_tmdb_type4_date(mid) or '')[:10]
            if t4 and day < t4 <= today and t4 > floor:
                day = t4
        return day

    def _is_held_rent_preorder(self, movie_id, movie, jw_result):
        """
        Hold a rent-listed VOD title in tracking if it's actually a store pre-order.

        JustWatch reports store pre-order RENTALS (Amazon/Apple/Fandango at Home) as
        ordinary RENT offers with a price, so the only accurate source is the store page.
        We HOLD only on a positive pre-order signal: the scraper reads an explicit
        "Pre-order" label reliably but can't confirm "available", so "hold unless available"
        would freeze real rentals. (Buy-only pre-orders are handled by _detect_buyonly_preorder.)

          - has streaming / no rent → False (transition; streaming has no pre-orders)
          - preorder_overrides[id] False/True → forced genuine / forced hold
          - page says 'pre-order' → True (hold); CAPTCHA → 'captcha' (hold, nothing
            recorded); else → False (transition)

        Held titles stay status='tracking', re-checked each run, go live once the page no
        longer reads as a pre-order. Escape hatch: preorder_overrides[id] = false.
        """
        # Bypass results (manual add, override, virtual screening, JW fail-open) carry no
        # offer metadata — never hold those.
        if not isinstance(jw_result, dict) or jw_result.get('_bypass') or jw_result.get('_fail_open'):
            return False

        # Verify any rent-listed VOD transition with no subscription (streaming) home —
        # that's where store pre-orders hide. Streaming services have no pre-order concept.
        if not (jw_result.get('has_rent') and not jw_result.get('has_streaming')):
            return False

        # The pre-order labeler decides (override, the store page, Amazon's live rental, TMDB's
        # digital date, still in theaters) -- the $15-rental block in enrichment is gone: a
        # $19.99 rental while in theaters is a red flag to check, never a block by itself.
        _lab = self._detect_buyonly_preorder(jw_result, movie_id, movie.get('title', ''))
        if _lab['reason'] == 'unreadable':
            return 'captcha'   # Amazon's robot check: held this run (truthy), but it proves nothing
        return bool(_lab['is_preorder'])

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
                if watch_links and (tracking_movie or {}).get('_screening_expired'):
                    strip_festival_links(watch_links)   # its own (expired) festival page is not a release

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

            # Curator lock: film deliberately has no trailer (e.g. title-collision
            # cleanup where the only online "trailer" is the wrong film). Never re-scrape.
            if movie.get('_lock_trailer'):
                continue

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
        # Every pre-order too, whatever its age or date: a pre-order is checked every night
        # until it is out (six dateless buy-only "pre-orders" sat invisible for months, Nov 2026).
        recent_movies = [
            m for m in existing_movies
            if (m.get('digital_date') or m.get('release_date') or '') >= cutoff
            or (m.get('_is_preorder') and not m.get('hidden'))
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
            _trk = ((tracking_data or {}).get('movies') or {}).get(movie_id) or {}
            if (movie.get('_enrichment_status') == 'reverted' or _trk.get('status') == 'removed'
                    or putback.is_owner_reverted(_trk)):
                # Sent back to tracking (a revert -- even an entry a stale write left unmarked)
                # or removed: its entry waits for enrichment's purge. Never graduate it or mark
                # it available here.
                continue
            # A returned festival screening: its own (expired) festival page is not a release.
            _gf_excl = (list(excluded_services) + FESTIVAL_PLATFORMS
                        if _trk.get('_screening_expired') else excluded_services)

            try:
                # --- JustWatch refresh ---
                content_type = 'tv' if movie_id.startswith('tv_') else 'movie'
                result = jw_client.verify_availability(
                    title, year,
                    excluded_services=_gf_excl,
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

                        # Merge streaming: add if not already present.
                        # JustWatch returns a LIST here; bare dict is legacy.
                        # (The dict-only check made this a dead path for months
                        # once JustWatch switched to lists — fixed Jul 2026.)
                        new_streaming = new_links.get('streaming')
                        if isinstance(new_streaming, dict):
                            new_streaming = [new_streaming]
                        if isinstance(new_streaming, list):
                            linked = [s for s in new_streaming
                                      if isinstance(s, dict) and s.get('link')]
                            existing_streaming = current_links.get('streaming')
                            has_existing = (
                                (isinstance(existing_streaming, dict) and existing_streaming.get('link'))
                                or (isinstance(existing_streaming, list) and any(
                                    isinstance(s, dict) and s.get('link') for s in existing_streaming))
                            )
                            if linked and not has_existing:
                                current_links['streaming'] = normalize_watch_links(
                                    {'streaming': linked})['streaming']
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

                    # Pre-order graduation. A pre-order still dated in the future, or a buy-only
                    # one, graduates only when JustWatch shows it watchable NOW -- streaming, or an
                    # Amazon rental past its offer start (discovery's rule): stores list pre-order
                    # rentals as ordinary RENT offers (Apple's from the theater opening), and
                    # graduating on those put not-yet-out films on the main wall. One whose date
                    # has arrived graduates on any rental, as before. Buy-only by its wall entry
                    # OR its tracking record (the two can disagree). A held film is left to
                    # discovery, which checks it on JustWatch every run.
                    _dd_gf = (movie.get('digital_date') or '')[:10]
                    _can_graduate = (result.get('has_streaming') or result.get('has_live_rent')
                                     or (result.get('has_rent') and bool(_dd_gf) and _dd_gf <= today_str
                                         and not (movie.get('_buyonly_preorder') or _trk.get('_buyonly_preorder'))))
                    # A buy-only pre-order is out when the pre-order labeler says so (buyable is out).
                    _bo_gf = bool(movie.get('_buyonly_preorder') or _trk.get('_buyonly_preorder'))
                    _bo_out = False
                    if (is_preorder and not _can_graduate and not _is_held(_trk)
                            and (movie.get('_buyonly_preorder') or _trk.get('_buyonly_preorder'))
                            and (result.get('has_buy') or result.get('has_rent'))):
                        _bo_out = not self._detect_buyonly_preorder(result, movie_id, title)['is_preorder']
                        _can_graduate = _bo_out
                    if is_preorder and _can_graduate and not _is_held(_trk) and not result.get('has_streaming'):
                        # A rental (even an Amazon one past its offer start) gets discovery's store
                        # check first: a page still reading "Pre-order" means not out yet.
                        _gf_page = self._is_held_rent_preorder(movie_id, movie, result)
                        if _gf_page:
                            _can_graduate = False
                            if _gf_page != 'captcha' and _trk:   # (a robot check proves nothing)
                                putback.note_refuted(_trk, today_str)
                                tracking_changed = True
                            print(f"  ⏳ {title} — JustWatch lists a rental, but its store page "
                                  + ("couldn't be read (Amazon's robot check)" if _gf_page == 'captcha'
                                     else "still reads 'Pre-order'") + "; stays a pre-order")
                    if is_preorder and _can_graduate and not _is_held(_trk):
                        movie.pop('_is_preorder', None)
                        movie.pop('_buyonly_preorder', None)
                        movie.pop('pre_order_links', None)
                        # Anchor the availability date to when the film FIRST became
                        # available, not "today". A stale pre-order flag can otherwise
                        # re-flag an already-released film every run; blindly stamping
                        # today then re-stamps its date daily, so it perpetually looks
                        # brand-new (Carolina Caroline, Jul 2026). Only for a film tracking
                        # already has as out: a genuine pre-order (still 'tracking') graduates
                        # today, never on an old pre-order date or a stale transition day --
                        # and never on or before a day it was proven not out yet.
                        grad_date = today_str
                        prior_dates = []
                        trec = (tracking_data or {}).get('movies', {}).get(movie_id) or {}
                        existing_dd = movie.get('digital_date')
                        # Already out by tracking AND dated in the past. A 'coming soon' pre-order
                        # (tracking 'available', dated ahead) graduating early is out from today,
                        # not from its old transition day.
                        _was_available = (trec.get('status') == 'available' and bool(existing_dd)
                                          and existing_dd[:10] < today_str)
                        if _was_available and existing_dd and existing_dd < today_str:
                            prior_dates.append(existing_dd)
                        prior_transition = (trec.get('_transitioned_at') or '')[:10]
                        if _was_available and prior_transition and prior_transition < today_str:
                            prior_dates.append(prior_transition)
                        _floor = putback.last_refuted_day(trec, today_str)
                        _trk_dd = (trec.get('digital_date') or '')[:10]
                        if trec.get('_virtual_screening') and trec.get('status') == 'available':
                            # The display pass re-flags a festival film a pre-order dated its
                            # screening every night: keep the date tracking already gave it,
                            # never re-stamp today.
                            prior_dates = [_trk_dd] if _trk_dd and _trk_dd < today_str else []
                        if _floor:
                            prior_dates = [d for d in prior_dates if d > _floor]
                        if prior_dates:
                            grad_date = min(prior_dates)
                        if _bo_out or _bo_gf:
                            # A buy-only film: out since it became watchable (its first offer record,
                            # not before TMDB's digital date) -- Olmo, Gregg Allman and Secrets of the
                            # Matriarch sat as dateless "pre-orders" for months after they were out.
                            grad_date = self._first_offer_day(result, trec, today_str, movie_id)
                        movie['digital_date'] = grad_date
                        if new_links:
                            movie['watch_links'] = current_links
                        preorders_graduated += 1
                        unsaved_count += 1
                        print(f"  🎓 {title} — pre-order graduated (available {grad_date})")

                        # Sync tracking — mark as available so discovery doesn't re-process
                        if tracking_data and tracking_data.get('movies', {}).get(movie_id):
                            tracking_data['movies'][movie_id]['status'] = 'available'
                            tracking_data['movies'][movie_id]['digital_date'] = grad_date
                            tracking_data['movies'][movie_id]['enriched'] = True
                            # Its pre-order flags go too: left on, a later pull would send it
                            # round the pre-order bypass again (the nightly pre-order loop).
                            for _k in ('_buyonly_preorder', '_is_preorder', '_type4_pending'):
                                tracking_data['movies'][movie_id].pop(_k, None)
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
                                    _t_bo = tracking_data['movies'][movie_id]
                                    _t_bo['_buyonly_preorder'] = True
                                    # Back to waiting, as enrichment's own buy-only path does:
                                    # discovery checks a buy-only pre-order on JustWatch every run
                                    # only while it is 'tracking'. One left 'available' was never
                                    # checked again -- Olmo and Gregg Allman stayed invisible,
                                    # dateless pre-orders months after their rentals went live.
                                    _t_bo['status'] = 'tracking'
                                    _t_bo.pop('digital_date', None)
                                    tracking_changed = True
                                preorders_flagged += 1
                                unsaved_count += 1
                            elif _gf_detect['verified_genuine']:
                                movie['_buyonly_verified'] = True
                                unsaved_count += 1

                # --- Wikipedia fill (only if missing) ---
                # Curator lock: skip films whose Wikipedia was deliberately cleared
                # (title-collision cleanup where title-matching keeps grabbing the wrong page).
                links = movie.get('links', {})
                if not links.get('wikipedia') and not movie.get('_lock_wikipedia'):
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
