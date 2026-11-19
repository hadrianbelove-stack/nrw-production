"""Step 1 v2 (round 2b): films held as "not out yet" are checked every run, and a film that is
put back is dated the day it actually became available.

Ported from the v1 file (nrw-step1-wt, written against commit a5da4f76) to the v2 working tree
(branch step1-putback-v2, uncommitted round-2 + round-2b changes), and extended for v2's
put-back dating and holds:
  * pipeline/putback.py (pure): note_refuted, last_refuted_day, putback_date, needs_review,
    owner_revert, revert_wall_entry;
  * ProviderDiscoverer._verify_before_wall computing a PENDING put-back, and _transition applying
    it at the wall move (persisting `_jw_last_refuted` before the hold fields are cleared);
  * the theater-week guard, reissues, returned festival screenings (`_screening_ended`), the PVOD
    looper's "keep the first confirmed date" rule, the TMDB-lookup-failure review flag (any
    source), the owner's Revert action, and enrichment's Type-4 date refresh never moving a date
    onto or before `_jw_last_refuted`.

The owner's rules under test (round2_changes.md):
  1. a film held as "not out yet" is a WAIT, never a drop;
  2. every held film is re-checked every daily run;
  3. JustWatch decides availability (TMDB never);
  4. it is dated the day it actually became available, never on a day a check proved it
     unavailable;
  5. a JustWatch error/outage never counts against a film and never puts an unconfirmed film on
     the wall.
  Plus (Nov 15): Remove and Revert are opposite purposes. No automatic path may set status
  'removed', and no path may bring a 'removed' title back. Every pipeline run in this file is
  checked for both (World._check_owner_rules).

What is REAL here
  * every pipeline module of the v2 worktree (DataGenerator, ProviderDiscoverer, MovieEnricher,
    JustWatchClient title matching + offer parsing, putback, StorageService/TrackingDB writing a
    temp SQLite DB, movie_tracking.json and data.json), scripts/revert_movie.py,
    scripts/morning_report.py, and the worktree's config.yaml (API keys replaced by dummies);
  * every film record: verbatim from `git show 78303fd6:movie_tracking.json` (data.json /
    data_archive.json for wall and archive entries; the scratchpad copies were checked against
    the git objects by sha). One exception, named where used: Avatar's 2026-11-13 HEAD record
    (v1's), when the owner's restore had it in tracking -- in 78303fd6 it is 'removed', and that
    record is used for the removed-title tests;
  * the TMDB and JustWatch payloads: trimmed copies of what the live APIs returned for these
    films on 2026-11-13/14 (read-only). JustWatch record dates (`dateCreated`) and package names
    (clearName + technicalName: Amazon Video/amazon, Apple TV Store/itunes, Fandango At
    Home/vudu) are real where the live capture has them (Verity, Sense and Sensibility, Avatar,
    Once Upon a Time in Harlem); anything a test adds is marked SYNTHETIC, with the evidence it is
    based on.

What is FAKED: only the network -- requests.get (TMDB), requests.Session.post (JustWatch
GraphQL), requests.head, sockets, Playwright (the store-page pre-order check) and, for the
enrichment runs, the Wikipedia / trailer / RT / Letterboxd / Metacritic / OMDb / IMDb fetchers
and the Playwright link scrapers ("nothing found") -- and the clock: every run happens on
2026-11-14 (the first daily run after the 78303fd6 snapshot, 12:00 UTC) or a stated number of
days later. Each run gets a fresh DataGenerator, as each `generate_data.py` phase is a new process.

All file I/O happens in a pytest tmp dir (chdir). A write guard fails the test on any write,
rename, delete or SQLite open under any NRW checkout.

Known CODE defects (strict xfail -- remove the mark once fixed): see the reasons on
test_k_legacy_floor_survives_a_no_match_answer, test_k_justwatch_error_day_never_becomes_a_refuted_day,
test_g_film_waiting_for_the_backlog_limit_keeps_the_day_it_came_out and
test_o_same_day_run_after_a_revert_never_dates_it_on_the_revert_day.

Run: cd <worktree> && /usr/bin/python3 -m pytest tests/test_step1_holds_and_dates.py -q -p no:cacheprovider
"""
import builtins
import copy
import io
import json
import logging
import os
import shutil
import signal
import socket
import sqlite3
import sys
import time
import types
from contextlib import redirect_stdout
from datetime import datetime as _REAL_DATETIME, timedelta, timezone
from urllib.parse import urlparse

import pytest

sys.dont_write_bytecode = True  # importing the pipeline must not leave __pycache__ in the worktree

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the repo these tests are in
if WORKTREE not in sys.path:
    sys.path.insert(0, WORKTREE)
# Every NRW checkout on this machine: nothing in this file may write into any of them.
PROTECTED = tuple(os.path.realpath(p) for p in (
    WORKTREE, '/Users/hadrianbelove/Downloads/nrw-production', '/Users/hadrianbelove/Downloads/nrw-step1-wt',
    '/Users/hadrianbelove/Downloads/nrw-restoration-wt', '/Users/hadrianbelove/Downloads/nrw-step1v2-dryrun',
    '/Users/hadrianbelove/Downloads/nrw-handoff'))

# utils.logger.setup_logger() attaches file + console handlers only when the logger has none.
# Give it a NullHandler so no test ever opens a log file (logs/admin.log relative to the cwd).
logging.getLogger('data_generator').addHandler(logging.NullHandler())

import requests  # noqa: E402
import yaml  # noqa: E402

import pipeline.archive as archive_mod  # noqa: E402
import pipeline.discoverer as discoverer_mod  # noqa: E402
import pipeline.display as display_mod  # noqa: E402
import pipeline.enricher as enricher_mod  # noqa: E402
import pipeline.enrichment as enrichment_mod  # noqa: E402
import pipeline.generator as generator_mod  # noqa: E402
import pipeline.justwatch as justwatch_mod  # noqa: E402
import pipeline.storage as storage_mod  # noqa: E402
from pipeline import putback  # noqa: E402
from pipeline import tracking_db as tracking_db_mod  # noqa: E402
from pipeline.generator import DataGenerator  # noqa: E402
from pipeline.justwatch import JustWatchClient  # noqa: E402

# The modules under test must be the v2 worktree's copies.
for _mod in (putback, tracking_db_mod, discoverer_mod, generator_mod, justwatch_mod, enricher_mod, archive_mod):
    assert os.path.realpath(_mod.__file__).startswith(WORKTREE), _mod.__file__

FIRST_OFFER, EVIDENCE, CONFIRMED = putback.FIRST_OFFER, putback.EVIDENCE, putback.CONFIRMED
AFTER_HOLD, REVIEW, OWNER_REVERT = putback.AFTER_HOLD, putback.REVIEW, putback.OWNER_REVERT

TOX, MIXTAPE, LIFE, VERITY, SENSE, AVATAR = '1451998', '1690338', '1397375', '1283515', '1503762', '83533'
GO_DEEP, BALEARIC, TRACES, MISTLETOE, HARLEM = '1766609', '1510323', '1439171', '1033671', '1596300'
ACCURSED, MASTERMIND, WILDCARDS, PREY, LEMONADE = '1671305', '1387772', '1396875', '1025835', '1405007'
LOVE, MONTREAL, LIBERATION, HAIL_MARY, AIR = '1746615', '1178620', '1129188', '687163', '273061'
BROTHER, CHUNKS = '1008633', '1730028'

# ---------------------------------------------------------------------------
# The clock: a fixed day
# ---------------------------------------------------------------------------

TODAY = '2026-11-14'   # the first daily run after the 78303fd6 snapshot (2026-11-13)
_BASE_TS = _REAL_DATETIME(2026, 11, 14, 12, 0, tzinfo=timezone.utc).timestamp()  # same date local + UTC


def day(n=0):
    """TODAY shifted by n days (YYYY-MM-DD)."""
    return (_REAL_DATETIME.strptime(TODAY, '%Y-%m-%d') + timedelta(days=n)).strftime('%Y-%m-%d')


class Clock:
    """'Now' for the pipeline: TODAY 12:00 UTC plus `days`, ticking in real time."""

    def __init__(self):
        self.days = 0
        self._t0 = time.time()

    def ts(self):
        return _BASE_TS + self.days * 86400 + (time.time() - self._t0)

    @property
    def today(self):
        return day(self.days)


def clock_datetime(clock):
    class ClockDatetime(_REAL_DATETIME):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(clock.ts(), tz)

        @classmethod
        def today(cls):
            return cls.fromtimestamp(clock.ts())

        @classmethod
        def utcnow(cls):
            return cls.utcfromtimestamp(clock.ts())
    return ClockDatetime


CLOCKED_MODULES = (archive_mod, discoverer_mod, display_mod, enricher_mod, enrichment_mod, generator_mod,
                   justwatch_mod, putback, storage_mod)


# ---------------------------------------------------------------------------
# Fake network
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 400
        if text is None:
            text = json.dumps(payload)[:300] if payload is not None else ''
        self.text = text
        self.content = text.encode()
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError('response has no JSON body')
        return copy.deepcopy(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} Client Error: Too Many Requests', response=self)


class FakeTMDB:
    """api.themoviedb.org/3/movie/{id}/release_dates, /watch/providers and /movie/{id}.
    `down[mid]` = endpoints answering 503 for that film ('release_dates', 'watch/providers');
    `broken[mid]` = endpoints whose request raises (a connection error)."""

    def __init__(self, unexpected):
        self.release_dates = {}
        self.providers = {}
        self.details = {}
        self.down = {}
        self.broken = {}
        self.calls = []
        self._unexpected = unexpected

    def use_real(self, mid):
        self.release_dates[mid] = copy.deepcopy(TMDB_RELEASE_DATES[mid])
        self.providers[mid] = copy.deepcopy(TMDB_PROVIDERS[mid])

    def set_providers(self, mid, flatrate=(), rent=(), buy=()):
        us = {}
        for kind, names in (('flatrate', flatrate), ('rent', rent), ('buy', buy)):
            if names:
                us[kind] = [{'provider_name': n} for n in names]
        self.providers[mid] = {'id': int(mid), 'results': {'US': us} if us else {}}

    def set_dates(self, mid, *entries):
        """entries: (type, YYYY-MM-DD, note)"""
        self.release_dates[mid] = {'id': int(mid), 'results': [{'iso_3166_1': 'US', 'release_dates': [
            {'type': t, 'release_date': f'{d}T00:00:00.000Z', 'note': n} for t, d, n in entries]}]}

    def get(self, url, params=None, timeout=None, **kwargs):
        u = urlparse(url)
        parts = u.path.strip('/').split('/')
        if u.netloc != 'api.themoviedb.org' or parts[:2] != ['3', 'movie'] or len(parts) < 3:
            if url.startswith('https://datasets.imdbws.com/'):
                return FakeResponse(404, None)        # IMDb bulk dataset unavailable
            self._unexpected.append(f'GET {url}')
            raise requests.ConnectionError(f'unexpected network call in test: GET {url}')
        mid, tail = parts[2], '/'.join(parts[3:])
        self.calls.append((mid, tail or 'details'))
        if tail in self.broken.get(mid, ()):
            raise requests.ConnectionError('Connection aborted: RemoteDisconnected')
        if tail in self.down.get(mid, ()):
            return FakeResponse(503, {'status_message': 'Service Unavailable'})
        if tail == 'release_dates':
            return FakeResponse(200, self.release_dates.get(mid, {'id': int(mid), 'results': []}))
        if tail == 'watch/providers':
            return FakeResponse(200, self.providers.get(mid, {'id': int(mid), 'results': {}}))
        if tail == '':
            if mid in self.details:
                return FakeResponse(200, self.details[mid])
            return FakeResponse(404, {'success': False, 'status_code': 34})
        self._unexpected.append(f'GET {url}')
        raise requests.ConnectionError(f'unexpected TMDB call in test: GET {url}')


class FakeJustWatch:
    """apis.justwatch.com/graphql popularTitles search, keyed by searchQuery.
    errors[query]: 'connection_error' | 'timeout' | 'http_429' | 'graphql_error' |
                   'malformed' (HTTP 200, the matched node's offers come back null)
    blocked: HTTP 200 with zero results for every query (datacenter-IP block)
    offers_outage: HTTP 200, the right titles, but every offer list empty"""

    CANARY = ('Oppenheimer', 'Barbie', 'Dune: Part Two')  # ProviderDiscoverer._JW_CANARY_TITLES

    def __init__(self, unexpected):
        self.edges = {q: copy.deepcopy(JW_SEARCH[q]) for q in self.CANARY}
        self.errors = {}
        self.blocked = False
        self.offers_outage = False
        self.queries = []
        self._unexpected = unexpected

    def use_real(self, query, as_query=None):
        self.edges[as_query or query] = copy.deepcopy(JW_SEARCH[query])

    def node(self, query, mid=None):
        """The (first, or TMDB id `mid`) node a query returns, for a test to edit."""
        for n in self.edges[query]:
            if mid is None or str(n['content']['externalIds'].get('tmdbId')) == str(mid):
                return n
        raise KeyError((query, mid))

    def post(self, url, **kwargs):
        if url != JustWatchClient.API_URL:
            self._unexpected.append(f'POST {url}')
            raise requests.ConnectionError(f'unexpected network call in test: POST {url}')
        query = ((kwargs.get('json') or {}).get('variables') or {}).get('searchQuery')
        self.queries.append(query)
        kind = self.errors.get(query)
        if kind == 'connection_error':
            raise requests.ConnectionError('Connection aborted: RemoteDisconnected')
        if kind == 'timeout':
            raise requests.Timeout('Read timed out. (read timeout=15)')
        if kind == 'http_429':
            return FakeResponse(429, None, text='Too Many Requests')
        if kind == 'graphql_error':
            return FakeResponse(200, {'errors': [{'message': 'Internal server error',
                                                  'path': ['popularTitles']}], 'data': None})
        if self.blocked:
            return FakeResponse(200, {'data': {'popularTitles': {'edges': []}}})
        nodes = copy.deepcopy(self.edges.get(query, []))
        for n in nodes:
            if kind == 'malformed':
                n['offers'] = None
            elif self.offers_outage:
                n['offers'] = []
        return FakeResponse(200, {'data': {'popularTitles': {'edges': [{'node': n} for n in nodes]}}})


class FakeStorePages:
    """Stands in for Playwright (playwright_manager) in ProviderDiscoverer._check_preorder_page."""

    AVAILABLE = 'Once Upon a Time in Harlem  Rent HD $5.99  Buy HD $14.99  Rent now  Buy now'
    AMAZON_PREORDER = ('Once Upon a Time in Harlem  Available to pre-order  This video will be released '
                       'in 10 days. Pre-order HD $5.99  Pre-order HD $14.99')

    def __init__(self):
        self.text = self.AVAILABLE
        self.visited = []

    def module(self):
        pages = self

        class _Page:
            def goto(self, url, **kw):
                pages.visited.append(url)

            def wait_for_timeout(self, ms):
                pass

            def text_content(self, selector):
                return pages.text

            def close(self):
                pass

        class _Context:
            def add_init_script(self, script):
                pass

            def set_default_timeout(self, ms):
                pass

            def new_page(self):
                return _Page()

            def close(self):
                pass

        class _Browser:
            def new_context(self, **kw):
                return _Context()

        class _Manager:
            def get_browser(self, headless=True, browser_type='chromium'):
                return _Browser()

        mod = types.ModuleType('playwright_manager')
        mod.get_playwright_manager = lambda: _Manager()
        return mod


class FakeVodScraper:
    """Stands in for streaming_platform_scraper.StreamingPlatformScraper (Playwright)."""
    timeout_seconds = 10
    rate_limit_seconds = 0

    def get_platform_deep_link(self, title, year, provider):
        return None

    def find_amazon_link(self, title, year, director=None):
        return None

    def find_fandango_link(self, title, year, director=None):
        return None


class FakeAgentScraper:
    """Stands in for agent_link_scraper.AgentLinkScraper (Playwright)."""

    def find_watch_link(self, movie_id, title, year, service):
        return {'link': None}


# Host methods that are pure network fetchers (Wikipedia, trailer search, RT/Letterboxd/
# Metacritic scrapers, OMDb, IMDb, B2 trailer hosting): "nothing found" in enrichment runs.
HOST_NETWORK_FETCHERS = (
    'find_wikipedia_url', 'find_director_wikipedia_url', 'find_cast_wikipedia_url',
    'find_trailer_url', 'find_rt_url', 'find_metacritic_score', 'find_letterboxd_score',
    'get_omdb_data', 'get_imdb_from_omdb', 'get_imdb_rating', 'get_imdb_votes',
    'host_trailer_for_movie',
)

# JustWatch's own package names (the live 2026-11-13/14 captures): the live-rental rule reads them.
TECHNICAL_NAMES = {'Amazon Video': 'amazon', 'Apple TV Store': 'itunes', 'Fandango At Home': 'vudu',
                   'Amazon Prime Video': 'amazonprime', 'Fandango': 'fandango'}


def jw_offer(kind, service, url, price=None, available_from=None, ptype='HD', created=None):
    """One JustWatch offer as the GraphQL API returns it (v2 also reads `dateCreated`)."""
    return {'monetizationType': kind, 'presentationType': ptype, 'retailPrice': price, 'currency': 'USD',
            'standardWebURL': url, 'availableFromTime': available_from, 'dateCreated': created,
            'package': {'clearName': service,
                        'technicalName': TECHNICAL_NAMES.get(service, service.lower().replace(' ', ''))}}


def jw_node(mid, title, year, offers):
    return {'id': f'tm{mid}', 'objectId': int(mid), 'objectType': 'MOVIE',
            'content': {'title': title, 'originalReleaseYear': year, 'fullPath': f'/us/movie/{mid}',
                        'externalIds': {'tmdbId': str(mid)}, 'credits': []},
            'offers': list(offers)}


def set_created(node, created, where=lambda o: True):
    """Give the node's offers a JustWatch record date (SYNTHETIC where the capture had none)."""
    for o in node['offers']:
        if where(o):
            o['dateCreated'] = created


def tmdb_details(mid, rec):
    """Minimal TMDB /movie/{id} body for the wall entry written on transition (and enrichment)."""
    year = rec.get('year')
    return {'id': int(mid), 'title': rec.get('title'), 'original_title': rec.get('original_title') or rec.get('title'),
            'original_language': 'en', 'release_date': f'{year}-01-01' if year else '', 'runtime': 95,
            'overview': 'x', 'genres': [], 'production_companies': [], 'production_countries': [],
            'origin_country': [], 'poster_path': None, 'budget': 0, 'credits': {'cast': [], 'crew': []},
            'external_ids': {'imdb_id': None}, 'keywords': {'keywords': []},
            'alternative_titles': {'results': []}, 'videos': {'results': []}}


# ---------------------------------------------------------------------------
# Write guard: nothing may land in an NRW checkout
# ---------------------------------------------------------------------------

def _install_write_guard(mp, hits):
    def protected(path):
        try:
            raw = path.decode() if isinstance(path, bytes) else os.fspath(path)
        except TypeError:
            return False
        return os.path.realpath(raw).startswith(PROTECTED)

    real_open = builtins.open

    def guarded_open(file, mode='r', *a, **k):
        if isinstance(file, (str, bytes, os.PathLike)) and any(c in mode for c in 'wax+') and protected(file):
            hits.append(('open', str(file), mode))
            raise PermissionError(f'write blocked by test guard: {file}')
        return real_open(file, mode, *a, **k)
    mp.setattr(builtins, 'open', guarded_open)
    mp.setattr(io, 'open', guarded_open)

    def wrap(module, name):
        real = getattr(module, name)

        def guarded(*a, **k):
            if any(protected(x) for x in a[:2] if isinstance(x, (str, bytes, os.PathLike))):
                hits.append((name, str(a[:2])))
                raise PermissionError(f'{name} blocked by test guard: {a[:2]}')
            return real(*a, **k)
        mp.setattr(module, name, guarded)

    for name in ('replace', 'rename', 'remove', 'unlink', 'rmdir', 'makedirs', 'mkdir'):
        wrap(os, name)
    for name in ('move', 'copy', 'copy2', 'copyfile', 'rmtree', 'copytree'):
        wrap(shutil, name)
    real_connect = sqlite3.connect

    def guarded_connect(db, *a, **k):
        if isinstance(db, (str, bytes, os.PathLike)) and protected(db):
            hits.append(('sqlite3.connect', str(db)))
            raise PermissionError(f'sqlite connect blocked by test guard: {db}')
        return real_connect(db, *a, **k)
    mp.setattr(sqlite3, 'connect', guarded_connect)


# ---------------------------------------------------------------------------
# The pipeline in a temp directory
# ---------------------------------------------------------------------------

class World:
    def __init__(self, tmp, tdb, tmdb, jw, pages, clock, capsys, monkeypatch, guard_hits):
        self.tmp, self.tdb, self.tmdb, self.jw, self.pages, self.clock = tmp, tdb, tmdb, jw, pages, clock
        self._capsys = capsys
        self._mp = monkeypatch
        self.guard_hits = guard_hits
        self._gen = None
        self.output = ''
        self.last_output = ''

    # -- generators (one per run: a new process) ---------------------------------
    @property
    def gen(self):
        """The discovery DataGenerator of the NEXT run (a fresh one per run)."""
        if self._gen is None:
            self._gen = DataGenerator(enrichment_enabled=False)
            assert self._gen.storage.tracking_db is self.tdb
        return self._gen

    @property
    def disc(self):
        return self.gen._discoverer

    def enrichment_generator(self):
        """A fresh DataGenerator for `generate_data.py --enrich`: real enrichment, every network
        fetcher answering "nothing found"."""
        g = DataGenerator()
        assert g.storage.tracking_db is self.tdb
        g.streaming_scraper = g.enrichment.streaming_scraper = FakeAgentScraper()
        g.vod_scraper = g.enrichment.vod_scraper = FakeVodScraper()
        for name in HOST_NETWORK_FETCHERS:
            setattr(g, name, lambda *a, **k: None)
        g._save_to_imdb_cache = lambda *a, **k: None
        g._imdb_rating_cache = {}
        return g

    # -- state -------------------------------------------------------------
    def seed(self, records, wall=(), archive=None):
        records = {str(k): copy.deepcopy(v) for k, v in records.items()}
        assert self.tdb.save_all({'movies': records}, export_json=True)
        for mid, rec in records.items():
            self.tmdb.details.setdefault(mid, tmdb_details(mid, rec))
        data = {'generated_at': '2026-11-13T23:00:00', 'count': len(wall), 'movies': copy.deepcopy(list(wall)),
                'staff_picks': [], 'featured': [], 'latest_playlist_url': None, '_metadata': {}}
        with open(os.path.join(self.tmp, 'data.json'), 'w') as f:
            json.dump(data, f)
        if archive is not None:
            with open(os.path.join(self.tmp, 'data_archive.json'), 'w') as f:
                json.dump({'movies': copy.deepcopy(list(archive))}, f)

    def tracking(self):
        return self.tdb.load_all()['movies']

    def save_tracking(self, movies):
        assert self.tdb.save_all({'movies': movies}, export_json=True)

    def wall(self):
        with open(os.path.join(self.tmp, 'data.json')) as f:
            data = json.load(f)
        return {str(m.get('id')): m for m in data.get('movies', [])}

    def save_wall(self, entries):
        with open(os.path.join(self.tmp, 'data.json')) as f:
            data = json.load(f)
        data['movies'] = list(entries)
        with open(os.path.join(self.tmp, 'data.json'), 'w') as f:
            json.dump(data, f)

    def metrics(self):
        with open(os.path.join(self.tmp, 'metrics', 'discovery_run.json')) as f:
            return json.load(f)

    # -- runs ----------------------------------------------------------------
    def _check_owner_rules(self, before, phase):
        """Nov 15 owner rules, after every run: nothing automatic sets 'removed'; a removed title
        is never touched (never re-tracked, never put back)."""
        after = self.tracking()
        for mid, rec in before.items():
            now = after.get(mid)
            if rec.get('status') == 'removed':
                assert now == rec, f'{phase} changed REMOVED title {mid} ({rec.get("title")}): {now}'
            else:
                assert (now or {}).get('status') != 'removed', \
                    f'{phase} set status "removed" on {mid} ({rec.get("title")}): only the owner removes'

    def _phase(self, fn, phase, on_day):
        if on_day is not None:
            self.clock.days = on_day
        before = copy.deepcopy(self.tracking())
        self._capsys.readouterr()
        result = fn()
        out = self._capsys.readouterr().out
        sys.stdout.write(out)  # keep the pipeline's own log visible on failure
        self.output += out
        self.last_output = out
        self._gen = None       # the next run is a new process
        self._check_owner_rules(before, phase)
        return result

    def run(self, on_day=None):
        """One discovery run (generate_data.py --discover) through the real entry point."""
        newly = self._phase(lambda: self.gen.check_tracking_movies(), 'discovery', on_day)
        # check_tracking_movies swallows any exception raised inside its loop: never let a
        # crash pass for a quiet run.
        assert 'Unexpected error during provider checking' not in self.last_output, self.last_output[-3000:]
        return newly

    def enrich(self, on_day=None):
        """One enrichment run (generate_data.py --enrich) through the real entry point."""
        return self._phase(lambda: self.enrichment_generator().enrich_newly_available_movies(),
                           'enrichment', on_day)

    def check_screenings(self, on_day=None):
        """generate_data.py --check-screenings (DataGenerator.check_virtual_screening_expirations)."""
        return self._phase(lambda: self.gen.check_virtual_screening_expirations(), 'screening check', on_day)

    def morning_report(self, run_date):
        """What the owner reads in /morning: scripts/morning_report.py held_and_put_back(), run over
        this run's movie_tracking.json / data.json."""
        scripts = os.path.join(WORKTREE, 'scripts')
        if scripts not in sys.path:
            self._mp.syspath_prepend(scripts)
        old = signal.getsignal(signal.SIGPIPE)
        try:
            import morning_report      # sets SIGPIPE to SIG_DFL on import (CLI behaviour)
        finally:
            signal.signal(signal.SIGPIPE, old)
        assert os.path.realpath(morning_report.__file__).startswith(WORKTREE), morning_report.__file__
        buf = io.StringIO()
        with redirect_stdout(buf):
            morning_report.held_and_put_back(list(self.wall().values()), run_date)
        return buf.getvalue()


@pytest.fixture
def world(tmp_path, monkeypatch, capsys):
    hits = []
    _install_write_guard(monkeypatch, hits)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TMDB_API_KEY', 'test-tmdb-key')
    monkeypatch.delenv('NRW_ENV', raising=False)

    with open(os.path.join(WORKTREE, 'config.yaml')) as f:
        cfg = yaml.safe_load(f)
    for key in list(cfg.get('api', {})):
        if key.endswith('_key'):
            cfg['api'][key] = f'test-{key}'
    with open(tmp_path / 'config.yaml', 'w') as f:
        yaml.safe_dump(cfg, f)

    # TrackingDB is a process-wide singleton built on relative paths: pin it to this tmp dir.
    tdb = tracking_db_mod.TrackingDB(db_path=str(tmp_path / 'movie_tracking.db'),
                                     json_path=str(tmp_path / 'movie_tracking.json'))
    monkeypatch.setattr(tracking_db_mod, '_shared_instance', tdb)
    monkeypatch.setattr(logging.getLogger('data_generator'), 'handlers', [logging.NullHandler()])

    clock = Clock()
    clocked = clock_datetime(clock)
    for mod in CLOCKED_MODULES:
        if getattr(mod, 'datetime', None) is _REAL_DATETIME:
            monkeypatch.setattr(mod, 'datetime', clocked)

    unexpected = []
    tmdb, jw, pages = FakeTMDB(unexpected), FakeJustWatch(unexpected), FakeStorePages()

    def _no_other_network(session, method, url, *args, **kwargs):
        unexpected.append(f'{method} {url}')
        raise requests.ConnectionError(f'unexpected network call in test: {method} {url}')

    def _no_head_or_post(url, *args, **kwargs):
        unexpected.append(f'requests {url}')
        raise requests.ConnectionError(f'network disabled in tests: {url}')

    def _blocked(what, target):
        unexpected.append(f'{what} {target}')
        raise OSError(f'network disabled in tests: {what} {target}')

    monkeypatch.setattr(requests.Session, 'request', _no_other_network)
    monkeypatch.setattr(requests.Session, 'post', lambda session, url, *a, **kw: jw.post(url, **kw))
    monkeypatch.setattr(requests, 'get', tmdb.get)
    monkeypatch.setattr(requests, 'head', _no_head_or_post)
    monkeypatch.setattr(requests, 'post', _no_head_or_post)
    monkeypatch.setattr(socket.socket, 'connect', lambda s, addr: _blocked('socket.connect', addr))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda s, addr: _blocked('socket.connect_ex', addr))
    monkeypatch.setattr(socket, 'create_connection', lambda addr, *a, **k: _blocked('socket.create_connection', addr))
    monkeypatch.setitem(sys.modules, 'playwright_manager', pages.module())
    # Network side effects inside otherwise-local enrichment steps: the distributor-lookup refresh
    # (Wikipedia + TMDB), the Wikipedia interlanguage count and the Eventive page fetches.
    import scripts.build_distributor_lookup as bdl
    import pipeline.notability as notability
    monkeypatch.setattr(bdl, 'build_lookup', lambda *a, **k: {})
    monkeypatch.setattr(notability, 'wikipedia_language_count', lambda *a, **k: None)
    monkeypatch.setattr(DataGenerator, '_fetch_eventive_screening_info', lambda self, slug: {}, raising=False)
    monkeypatch.setattr(DataGenerator, '_fetch_eventive_play_info', lambda self, link: {}, raising=False)

    yield World(str(tmp_path), tdb, tmdb, jw, pages, clock, capsys, monkeypatch, hits)
    assert not unexpected, f'pipeline made network calls the test did not fake: {unexpected}'
    assert not hits, f'pipeline tried to write into an NRW checkout: {hits}'


def real(mid):
    """A verbatim 78303fd6 movie_tracking.json record."""
    return copy.deepcopy(REAL_TRACKING[mid])


def _legacy_no_offer(reverted_at, count, **extra):
    rec = {'_jw_revert_reason': 'justwatch_no_valid_offers', '_jw_reverted_at': reverted_at,
           '_jw_revert_count': count}
    rec.update(extra)
    return rec


def test_harness_drives_the_v2_worktree_and_its_clock(world):
    """The modules under test are the v2 worktree's (round 2b: owner_revert, has_live_rent by
    JustWatch's package names), and the pipeline sees the fixed clock."""
    assert hasattr(putback, 'owner_revert') and hasattr(putback, 'revert_wall_entry')
    assert discoverer_mod.ProviderDiscoverer.MAX_BACKLOG_PUTBACKS_PER_RUN >= 10 ** 5   # no trickle (owner)
    assert putback.today_str() == TODAY
    assert generator_mod.datetime.now().strftime('%Y-%m-%d') == TODAY
    assert justwatch_mod.datetime.now(timezone.utc).strftime('%Y-%m-%d') == TODAY
    assert enricher_mod.datetime.now().strftime('%Y-%m-%d') == TODAY
    assert os.path.realpath(os.getcwd()) == os.path.realpath(world.tmp)
    assert not os.path.realpath(world.tmp).startswith(PROTECTED)
    # The write guard refuses a write into a checkout (a path whose folder does not exist, so a
    # broken guard could not write anything either: it would raise FileNotFoundError instead).
    with pytest.raises(PermissionError):
        open(os.path.join(WORKTREE, 'no-such-folder-write-guard-check', 'x.json'), 'w')
    assert world.guard_hits and world.guard_hits[-1][0] == 'open'
    world.guard_hits.clear()


# ===========================================================================
# P. The put-back rules themselves (pipeline/putback.py, pure functions)
# ===========================================================================

def test_p_note_refuted_remembers_the_latest_refuted_day_and_never_moves_back():
    rec = {}
    putback.note_refuted(rec, None)
    putback.note_refuted(rec, '')
    assert '_jw_last_refuted' not in rec
    putback.note_refuted(rec, '2026-11-10T07:00:00Z')
    assert rec['_jw_last_refuted'] == '2026-11-10'
    putback.note_refuted(rec, '2026-11-08')
    assert rec['_jw_last_refuted'] == '2026-11-10', 'an older refuted day moved the floor back'
    putback.note_refuted(rec, '2026-11-12')
    assert rec['_jw_last_refuted'] == '2026-11-12'


@pytest.mark.parametrize('mid, extra, expected', [
    # Legacy no-offer holds: checked once a run from _jw_reverted_at, _jw_revert_count times.
    pytest.param(GO_DEEP, {}, '2026-09-28', id='GoDeep-legacy-estimate-09-25+3'),
    # ... never later than yesterday (that field is re-set mid-hold): 11-13 + 4 days -> 11-13.
    pytest.param(WILDCARDS, {}, '2026-11-13', id='Wildcards-estimate-capped-at-yesterday'),
    pytest.param(WILDCARDS, {'_jw_last_checked': '2026-11-12'}, '2026-11-12', id='Wildcards-stamped-last-check'),
    # A no-match says nothing about availability; a PVOD hold had live rentals.
    pytest.param(MIXTAPE, {}, None, id='Mixtape-no-match-proves-nothing'),
    pytest.param(VERITY, {}, None, id='Verity-PVOD-proves-nothing'),
    # The persisted floor counts whatever the current hold reason is (finding 10).
    pytest.param(MIXTAPE, {'_jw_last_refuted': '2026-11-02'}, '2026-11-02', id='persisted-floor-survives-no-match'),
    pytest.param(VERITY, {'_jw_last_refuted': '2026-10-20'}, '2026-10-20', id='persisted-floor-survives-PVOD-reason'),
    pytest.param(VERITY, {'_jw_revert_reason': OWNER_REVERT, '_jw_last_refuted': TODAY}, TODAY,
                 id='owner-revert-floor'),
    # The store page read "Pre-order".
    pytest.param(HARLEM, {'_rent_preorder_held': TODAY}, TODAY, id='Harlem-store-preorder-page-today'),
    # The latest of all of them.
    pytest.param(GO_DEEP, {'_jw_last_refuted': '2026-09-20'}, '2026-09-28', id='max-legacy-over-older-persisted'),
    pytest.param(GO_DEEP, {'_jw_last_refuted': '2026-10-02'}, '2026-10-02', id='max-persisted-over-legacy'),
])
def test_p_last_refuted_day_is_the_latest_proven_not_out_yet_day(mid, extra, expected):
    rec = real(mid)
    rec.update(extra)
    assert putback.last_refuted_day(rec, TODAY) == expected


@pytest.mark.parametrize('rec, skipped, tmdb, offers, theatrical, expected', [
    # Finding 27 (ii): the earliest candidate is refuted, a later one is not -> the later one
    # (v1 / round 1 gave floor+1). TMDB 10-04, last no-offer check 10-10, first record 11-06.
    pytest.param(_legacy_no_offer('2026-10-04', 7, _jw_last_checked='2026-10-10'), False, '2026-10-04',
                 ['2026-11-06'], None, ('2026-11-06', FIRST_OFFER), id='refuted-TMDB-later-JW-record'),
    # Prey of Wrath (real record: no offer from 05-10, 10 checks -> 05-19; TMDB 05-01 'Xumo
    # Original'); its Amazon offer start 07-08 used as the JustWatch record date (SYNTHETIC).
    pytest.param(PREY, True, '2026-05-01', ['2026-07-08'], None,
                 ('2026-07-08', FIRST_OFFER), id='PreyOfWrath-TMDB-refuted-record-07-08'),
    # Two JustWatch records, the first refuted: the earliest one AFTER the floor.
    pytest.param(_legacy_no_offer('2026-05-10', 10), True, None, ['2026-05-01', '2026-07-08'], None,
                 ('2026-07-08', FIRST_OFFER), id='first-record-refuted-second-not'),
    # Both after the floor: the earlier one wins, whichever source it comes from.
    pytest.param(_legacy_no_offer('2026-10-01', 3, _jw_last_checked='2026-10-03'), False, '2026-10-06',
                 ['2026-10-09'], None, ('2026-10-06', EVIDENCE), id='TMDB-earlier-than-record'),
    pytest.param(_legacy_no_offer('2026-10-01', 3, _jw_last_checked='2026-10-03'), False, '2026-10-09',
                 ['2026-10-06'], None, ('2026-10-06', FIRST_OFFER), id='record-earlier-than-TMDB'),
])
def test_p_putback_date_is_the_earliest_evidence_after_the_last_refuted_day(rec, skipped, tmdb, offers,
                                                                            theatrical, expected):
    rec = real(rec) if isinstance(rec, str) else copy.deepcopy(rec)
    assert putback.putback_date(rec, skipped, tmdb, offers, theatrical, TODAY) == expected


def test_p_evidence_all_on_or_before_the_floor_gives_the_day_after_it():
    go_deep = real(GO_DEEP)   # last no-offer day 09-28 (estimate); TMDB + JustWatch say 09-24
    assert putback.putback_date(go_deep, True, '2026-09-24', ['2026-09-24'], None, TODAY) == ('2026-09-29', AFTER_HOLD)
    assert putback.putback_date(go_deep, True, '2026-09-24', [], None, TODAY) == ('2026-09-29', AFTER_HOLD)
    assert putback.putback_date(go_deep, True, None, ['2026-09-24'], None, TODAY) == ('2026-09-29', AFTER_HOLD)
    # Never in the future: the store page read "Pre-order" yesterday -> today at the latest.
    harlem = dict(real(HARLEM), _rent_preorder_held=day(-1))
    assert putback.putback_date(harlem, False, None, [day(-1)], None, TODAY) == (TODAY, AFTER_HOLD)


@pytest.mark.parametrize('dates, digital, expected', [
    # Project Hail Mary (putback.py docstring): Apple's rental was recorded on its 2026-03-20
    # opening day as a pre-order listing; it came out 2026-05-12.
    pytest.param(['2026-03-20'], '2026-05-12', ('2026-05-12', EVIDENCE), id='opening-day-listing-skipped'),
    pytest.param(['2026-03-27'], '2026-05-12', ('2026-05-12', EVIDENCE), id='theater-week-day-7-skipped'),
    pytest.param(['2026-03-28'], '2026-05-12', ('2026-03-28', FIRST_OFFER), id='day-8-is-a-real-record'),
    pytest.param(['2026-03-20', '2026-05-12'], '2026-05-12', ('2026-05-12', FIRST_OFFER), id='later-record-same-day-as-TMDB'),
    # Day-and-date (TMDB digital on the opening day): the theater-week record is real.
    pytest.param(['2026-03-20'], '2026-03-20', ('2026-03-20', FIRST_OFFER), id='day-and-date-kept'),
])
def test_p_theater_week_guard(dates, digital, expected):
    rec = {'_jw_revert_reason': 'justwatch_theatrical_pvod', '_jw_revert_count': 1, '_jw_reverted_at': '2026-03-21'}
    assert putback.putback_date(rec, False, digital, dates, '2026-03-20', TODAY) == expected


def test_p_theater_week_record_without_a_tmdb_digital_date_is_not_trusted():
    """No TMDB digital date to tell a pre-order listing from a day-and-date rental: the
    theater-week record is not used (it may be a pre-order) -- the film is dated today, and,
    unchecked during the hold, flagged for the owner."""
    rec = {'_jw_revert_reason': 'justwatch_theatrical_pvod', '_jw_revert_count': 1, '_jw_reverted_at': '2026-03-21'}
    day_, source = putback.putback_date(rec, False, None, ['2026-03-20'], '2026-03-20', TODAY)
    assert (day_, source) == (TODAY, REVIEW)
    assert putback.needs_review(source, rec, False, TODAY)


@pytest.mark.parametrize('flag', [{'_reissue': True}, {'reissue_label': 'Restoration'}, {'_reissue_deferred': True}],
                         ids=['_reissue', 'reissue_label', '_reissue_deferred'])
def test_p_a_reissue_never_uses_justwatch_records(flag):
    """A reissue's JustWatch records belong to the original release (Air: The Musical's 2017
    rentals); only TMDB's date dates it -- and JustWatch records alone are no evidence."""
    rec = dict(real(AIR), **flag)   # no-match hold since 09-23 (proves nothing: no floor)
    assert putback.is_reissue(rec)
    assert putback.putback_date(rec, True, '2026-09-22', ['2017-03-01', '2019-06-04'], None, TODAY) == \
        ('2026-09-22', EVIDENCE)
    assert putback.putback_date(rec, True, None, ['2017-03-01'], None, TODAY) == (TODAY, REVIEW)
    # With a floor, JustWatch records are still not "evidence before the floor" for a reissue.
    floored = dict(rec, _jw_last_refuted='2026-10-01')
    assert putback.putback_date(floored, True, None, ['2017-03-01'], None, TODAY) == (TODAY, REVIEW)
    # Not a reissue: the same records date it.
    plain = real(AIR)
    assert not putback.is_reissue(plain)
    assert putback.putback_date(plain, True, None, ['2019-06-04'], None, TODAY) == ('2019-06-04', FIRST_OFFER)


def _returned_love_love():
    """Love - Love (78303fd6: on the wall as an expired Heartland Film Festival screening,
    10-08..10-26; tracking 'available') returned to tracking the way v2 does it."""
    rec = real(LOVE)
    DataGenerator._return_screening_to_tracking(rec, '2026-10-26')
    return rec


def test_p_returned_screening_record_fields(world):
    rec = _returned_love_love()
    assert rec['status'] == 'tracking' and rec['_screening_expired'] is True
    assert rec['_screening_ended'] == '2026-10-26' and rec['_screening_returned_at'] == TODAY
    assert 'digital_date' not in rec and '_is_preorder' not in rec
    # A second return never moves the stored end.
    DataGenerator._return_screening_to_tracking(rec, '2026-12-31')
    assert rec['_screening_ended'] == '2026-10-26'


@pytest.mark.parametrize('tmdb, offers, expected', [
    # TMDB lists the festival screening itself as a digital release (real: Type 4 2026-10-08
    # 'Heartland Film Festival'): ignored. JustWatch's regular-release record dates it.
    pytest.param('2026-10-08', [TODAY], (TODAY, FIRST_OFFER), id='festival-T4-ignored-JW-record-used'),
    pytest.param('2026-10-26', ['2026-11-04'], ('2026-11-04', FIRST_OFFER), id='T4-on-the-last-screening-day-ignored'),
    # Nothing else: today, flagged (it was never checked during the screening).
    pytest.param('2026-10-08', [], (TODAY, REVIEW), id='festival-T4-only-no-evidence'),
    # A TMDB digital date after the screening ended is a real release.
    pytest.param('2026-11-03', [TODAY], ('2026-11-03', EVIDENCE), id='T4-after-the-screening-used'),
])
def test_p_returned_screening_ignores_tmdb_dates_up_to_the_screening_end(world, tmdb, offers, expected):
    rec = _returned_love_love()
    assert putback.putback_date(rec, False, tmdb, offers, None, TODAY) == expected


def _pvod_looper(source, date='2026-11-14'):
    """The record after a put-back (dated `date`, source `source`) that enrichment's PVOD gate
    pulled the same day (enricher.py revert branch: reason, reverted_at, last_checked, count)."""
    return {'status': 'tracking', 'digital_date': date, '_digital_date_source': source,
            '_put_back_on': '2026-11-14', '_jw_last_refuted': '2026-11-13',
            '_jw_revert_reason': 'justwatch_theatrical_pvod', '_jw_reverted_at': '2026-11-14',
            '_jw_last_checked': '2026-11-14', '_jw_revert_count': 1}


@pytest.mark.parametrize('source', [CONFIRMED, REVIEW])
def test_p_pvod_looper_without_evidence_keeps_its_first_confirmed_date(source):
    rec = _pvod_looper(source)
    assert putback.putback_date(rec, False, None, [], None, day(1)) == ('2026-11-14', source)
    assert putback.needs_review(source, rec, False, day(1)) is (source == REVIEW)
    assert putback.putback_date(rec, False, None, [], None, day(5)) == ('2026-11-14', source)


@pytest.mark.parametrize('rec, why', [
    pytest.param(_pvod_looper('tmdb_type4'), 'not a put-back date', id='not-a-putback-source'),
    pytest.param(_pvod_looper(AFTER_HOLD), 'only CONFIRMED/REVIEW are kept', id='after-hold-source'),
    pytest.param(_pvod_looper(CONFIRMED, date='2026-11-13'), 'on the floor', id='on-the-refuted-day'),
    pytest.param(_pvod_looper(CONFIRMED, date='2026-11-20'), 'in the future', id='future-date'),
])
def test_p_previous_date_is_kept_only_when_it_is_a_valid_put_back_date(rec, why):
    assert putback.putback_date(rec, False, None, [], None, day(1)) == (day(1), CONFIRMED), why


@pytest.mark.parametrize('rec, skipped, expected', [
    # checked yesterday ('_jw_last_checked' stamped by every failed v2 check)
    pytest.param(_legacy_no_offer('2026-11-01', 13, _jw_last_checked='2026-11-13'), False, CONFIRMED, id='checked-yesterday'),
    pytest.param(_legacy_no_offer('2026-11-01', 11, _jw_last_checked='2026-11-12'), False, CONFIRMED, id='gap-2-days'),
    pytest.param(_legacy_no_offer('2026-11-01', 10, _jw_last_checked='2026-11-11'), False, REVIEW, id='gap-3-days'),
    pytest.param(_legacy_no_offer('2026-11-01', 13, _jw_last_checked='2026-11-13'), True, REVIEW, id='old-permanent-skip'),
    pytest.param({'_rent_preorder_held': '2026-11-13'}, False, CONFIRMED, id='store-preorder-page-yesterday'),
    pytest.param({'_screening_expired': True, '_screening_ended': '2026-10-26'}, False, REVIEW,
                 id='returned-screening-never-checked'),
    # Brother (1008633, real): 3 no-offer checks from 05-23, nothing since (finding 13).
    pytest.param(BROTHER, False, REVIEW, id='Brother-3-checks-in-May'),
])
def test_p_no_evidence_is_today_confirmed_only_if_checked_daily(rec, skipped, expected):
    rec = real(rec) if isinstance(rec, str) else copy.deepcopy(rec)
    assert putback.putback_date(rec, skipped, None, [], None, TODAY) == (TODAY, expected)
    assert putback.checked_daily(rec, skipped, TODAY) is (expected == CONFIRMED)


def test_p_future_dates_are_never_the_put_back_date():
    rec = _legacy_no_offer('2026-11-01', 13, _jw_last_checked='2026-11-13')
    assert putback.putback_date(rec, False, '2026-11-20', [], None, TODAY) == (TODAY, CONFIRMED)
    assert putback.putback_date(rec, False, None, ['2026-11-20'], None, TODAY)[0] <= TODAY


@pytest.mark.parametrize('source, daily, expected', [
    (REVIEW, True, True), (REVIEW, False, True),
    (AFTER_HOLD, False, True), (AFTER_HOLD, True, False),
    (FIRST_OFFER, False, False), (EVIDENCE, False, False), (CONFIRMED, True, False),
])
def test_p_needs_review(source, daily, expected):
    rec = _legacy_no_offer('2026-11-01', 13, _jw_last_checked='2026-11-13' if daily else '2026-11-01')
    assert putback.needs_review(source, rec, False, TODAY) is expected


def test_p_protected_sources_cover_every_put_back_source():
    assert putback.PROTECTED_SOURCES == {FIRST_OFFER, EVIDENCE, CONFIRMED, AFTER_HOLD, REVIEW,
                                         putback.OFFER_START}


# ===========================================================================
# O. The owner's Revert action (putback.owner_revert / revert_wall_entry)
# ===========================================================================

def test_o_owner_revert_refuses_a_removed_title_and_changes_nothing():
    """Remove and Revert are opposite purposes: a removed title is never reverted (it would come
    back on the wall). 78303fd6 records, both removed for good."""
    for mid in (AVATAR, HAIL_MARY):
        rec = real(mid)
        assert rec['status'] == 'removed'
        before = copy.deepcopy(rec)
        assert putback.owner_revert(rec, today=TODAY) is False
        assert rec == before, f'owner_revert changed removed title {rec["title"]}'


def test_o_owner_revert_sends_a_wall_film_back_to_waiting():
    """Verity as it was put on the wall this run (status available, dated by its put-back).
    Reverted: held (JustWatch checks it every run), today is a proven "not out yet" day, its
    wrong "new" date is gone, and it is never 'removed'."""
    rec = real(VERITY)
    rec.update({'status': 'available', 'digital_date': '2026-10-27', '_digital_date_source': FIRST_OFFER,
                '_put_back_on': TODAY, '_held_since': '2026-11-13', '_date_needs_review': True,
                'enriched': True, 'enrichment_date': TODAY})
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        rec.pop(k)
    assert putback.owner_revert(rec, today=TODAY) is True
    assert rec['status'] == 'tracking'
    assert (rec['_jw_revert_reason'], rec['_jw_reverted_at'], rec['_jw_revert_count']) == (OWNER_REVERT, TODAY, 1)
    assert (rec['_jw_last_checked'], rec['_jw_last_refuted'], rec['_reverted_by_owner']) == (TODAY, TODAY, TODAY)
    assert 'digital_date' not in rec, 'the wrong "new" date survived the revert'
    for k in ('_put_back_on', '_held_since', '_date_needs_review', 'enrichment_date'):
        assert k not in rec, k
    assert rec['enriched'] is False
    assert discoverer_mod._is_held(rec), 'a reverted film is not checked every run'
    assert putback.last_refuted_day(rec, day(1)) == TODAY


def test_o_owner_revert_keeps_a_future_tmdb_date_a_hold_history_and_a_later_floor():
    """Liberation (real: held, pending TMDB date 2026-11-17, 1 strike since 09-15): the pre-order
    date stays; the hold history and strike count are kept; a floor later than today (none can be,
    but never moved back) is untouched."""
    rec = real(LIBERATION)
    assert putback.owner_revert(rec, today=TODAY) is True
    assert rec['digital_date'] == '2026-11-17', 'a future TMDB date was dropped'
    assert (rec['_jw_reverted_at'], rec['_jw_revert_count']) == ('2026-09-15', 1)
    assert rec['_jw_revert_reason'] == OWNER_REVERT and rec['_jw_last_refuted'] == TODAY
    # A record already refuted later keeps the later day (note_refuted never moves back).
    later = dict(real(LIBERATION), _jw_last_refuted=day(2))
    putback.owner_revert(later, today=TODAY)
    assert later['_jw_last_refuted'] == day(2)


@pytest.mark.parametrize('tmdb, offers, expected', [
    # The store's pre-order listing that put it on the wall (recorded before the revert): never.
    pytest.param(None, [day(-1)], (day(1), AFTER_HOLD), id='listing-from-before-the-revert'),
    pytest.param(None, [TODAY], (day(1), AFTER_HOLD), id='listing-recorded-on-the-revert-day'),
    # TMDB's digital date before the revert (the "premature TMDB signal"): never.
    pytest.param('2026-11-09', [], (day(1), AFTER_HOLD), id='tmdb-date-before-the-revert'),
    # A new way to watch it recorded after the revert: that day.
    pytest.param('2026-11-09', [day(-1), day(1)], (day(1), FIRST_OFFER), id='new-offer-after-the-revert'),
    # No evidence at all: the day JustWatch confirms it.
    pytest.param(None, [], (day(1), CONFIRMED), id='no-evidence'),
])
def test_o_a_reverted_film_is_never_dated_on_or_before_the_revert_day(tmdb, offers, expected):
    rec = real(VERITY)
    rec.update({'status': 'available', '_put_back_on': TODAY, '_digital_date_source': FIRST_OFFER})
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        rec.pop(k)
    putback.owner_revert(rec, today=TODAY)
    got = putback.putback_date(rec, False, tmdb, offers, None, day(1))
    assert got == expected
    assert got[0] > TODAY
    assert not putback.needs_review(got[1], rec, False, day(1))


def test_o_revert_wall_entry_hides_only_that_film_through_the_normal_revert_path():
    site = {'movies': [{'id': 1283515, 'title': 'Verity', 'digital_date': '2026-10-27'},
                       {'id': '1503762', 'title': 'Sense and Sensibility'}]}
    assert putback.revert_wall_entry(site, '1283515') is True     # int id in data.json, str asked
    verity, sense = site['movies']
    assert (verity['hidden'], verity['_enrichment_status'], verity['_jw_reverted']) == (True, 'reverted', True)
    assert (verity['_jw_revert_reason'], verity['status']) == (OWNER_REVERT, 'tracking')
    assert sense == {'id': '1503762', 'title': 'Sense and Sensibility'}
    assert putback.revert_wall_entry(site, '999') is False


def _revert_script(world, mid):
    """scripts/revert_movie.py <mid>, in-process in the tmp checkout (real get_tracking_db,
    json_edit). Returns (exit code, output)."""
    scripts = os.path.join(WORKTREE, 'scripts')
    if scripts not in sys.path:
        world._mp.syspath_prepend(scripts)
    import revert_movie
    assert os.path.realpath(revert_movie.__file__).startswith(WORKTREE)
    world._mp.setattr(sys, 'argv', ['revert_movie.py', mid])
    before = copy.deepcopy(world.tracking())
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = revert_movie.main()
    world._check_owner_rules(before, 'revert script')
    return code, buf.getvalue()


def test_o_revert_script_refuses_a_removed_title(world):
    """/revert on a removed title (78303fd6 Avatar, removed by the May PVOD sweep): refused,
    nothing written -- tracking and the wall entry stay exactly as they were."""
    avatar = real(AVATAR)
    entry = {'id': AVATAR, 'title': 'Avatar: Fire and Ash', 'digital_date': '2026-03-31'}
    world.seed({AVATAR: avatar}, wall=[entry])
    code, out = _revert_script(world, AVATAR)
    assert code == 1 and 'REMOVED' in out
    assert world.tracking()[AVATAR] == avatar
    assert world.wall()[AVATAR] == entry


def test_o_revert_script_takes_the_film_off_the_wall_and_back_to_waiting(world):
    """/revert on a film on the wall: held in tracking, wall entry hidden and marked reverted."""
    rec = real(SENSE)
    rec.update({'status': 'available', 'digital_date': '2026-11-03', '_digital_date_source': FIRST_OFFER,
                '_put_back_on': TODAY})
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        rec.pop(k)
    world.seed({SENSE: rec}, wall=[{'id': SENSE, 'title': 'Sense and Sensibility', 'digital_date': '2026-11-03'}])
    code, out = _revert_script(world, SENSE)
    assert code == 0 and 'reverted' in out
    after, entry = world.tracking()[SENSE], world.wall()[SENSE]
    assert (after['status'], after['_jw_revert_reason'], after['_jw_last_refuted']) == ('tracking', OWNER_REVERT, TODAY)
    assert entry['hidden'] is True and entry['_enrichment_status'] == 'reverted'


HARLEM_AMAZON = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.5c1e7f2a-0b6d-4e1f-9a1c-harlem2026'


def harlem_store_offers(amazon_offer_start, created, price='$5.99'):
    """Store rentals as JustWatch lists them (SYNTHETIC: the live capture has only cinema listings).
    Before release day a store pre-order rental looks exactly like a live RENT offer (see
    ProviderDiscoverer._is_held_rent_preorder). Amazon first, so the store-page check reads
    Amazon's page. `created`: JustWatch's record date (the day the listing appeared)."""
    return [
        jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, price, amazon_offer_start, created=created),
        jw_offer('BUY', 'Amazon Video', HARLEM_AMAZON, '$14.99', amazon_offer_start, created=created),
        jw_offer('RENT', 'Apple TV Store', 'https://tv.apple.com/us/movie/once-upon-a-time-in-harlem/umc.cmc.harlem',
                 price, '2026-10-16T07:00:00Z', created=created),
        jw_offer('RENT', 'Fandango At Home',
                 'https://athome.fandango.com/content/browse/details/Once-Upon-a-Time-in-Harlem/5301120', price,
                 created=created),
    ]


def _harlem_on_the_wall_by_mistake(world):
    """Once Upon a Time in Harlem (real hold). Day -1 (SYNTHETIC): JustWatch listed the store
    pre-order rentals, the store page could not be read, so discovery put it on the wall. Today
    the owner reverts it -- the pre-order problem -- with the admin's Revert (the same two calls
    the route and scripts/revert_movie.py make)."""
    rec = real(HARLEM)
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        rec.pop(k)
    rec.update({'status': 'available', 'digital_date': day(-1), '_discovery_source': 'provider_availability_check',
                '_transitioned_at': day(-1), '_jw_last_refuted': '2026-10-31'})
    entry = {'id': HARLEM, 'title': 'Once Upon a Time in Harlem', 'digital_date': day(-1),
             '_enrichment_status': 'completed', 'watch_links': {'vod': [{'service': 'Amazon Video', 'link': HARLEM_AMAZON}]}}
    world.seed({HARLEM: rec}, wall=[entry])
    world.tmdb.use_real(HARLEM)
    world.jw.use_real('Once Upon a Time in Harlem')
    node = world.jw.node('Once Upon a Time in Harlem', HARLEM)
    node['offers'] += harlem_store_offers(f'{day(3)}T07:00:00Z', created=day(-1))
    movies = world.tracking()
    assert putback.owner_revert(movies[HARLEM], today=TODAY)
    world.save_tracking(movies)
    site = {'movies': list(world.wall().values())}
    assert putback.revert_wall_entry(site, HARLEM)
    world.save_wall(site['movies'])
    return node


def test_o_reverted_film_waits_and_comes_back_the_day_it_is_really_out(world):
    """After the revert: days 1 and 2 JustWatch lists the same store rentals that put it on the
    wall by mistake (recorded day -1, Amazon's offer start day 3) and Amazon's page reads
    "Pre-order" -- it keeps waiting (no strike), and each of those days is a "not out yet" day
    (round 2d: the store page is read for a reverted film). Day 3 (its real release, SYNTHETIC)
    Amazon's offer start passes and the page reads normally -> put back, dated day 3 by that offer
    start (OFFER_START) -- never on or before the revert day."""
    node = _harlem_on_the_wall_by_mistake(world)
    world.pages.text = FakeStorePages.AMAZON_PREORDER

    for n in (1, 2):
        asked = len(world.jw.queries)
        world.run(on_day=n)
        held = world.tracking()[HARLEM]
        assert 'Once Upon a Time in Harlem' in world.jw.queries[asked:], f'a reverted film was not checked on day {n}'
        assert held['status'] == 'tracking' and held['_jw_last_checked'] == day(n)
        assert held['_jw_last_refuted'] == day(n) and held['_jw_revert_count'] == 1
        assert held['_jw_revert_reason'] == OWNER_REVERT and held['_revert_page_preorder'] == day(n)
        assert world.wall()[HARLEM].get('hidden') is True
    report = world.morning_report(day(2))
    assert 'Held, checked daily until they come out: 1 (1 you sent it back (not out yet))' in report, report

    node['offers'] = [o for o in node['offers'] if o['monetizationType'] == 'CINEMA'] + \
        harlem_store_offers(f'{day(3)}T07:00:00Z', created=day(-1))
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=3)
    after, wall = world.tracking()[HARLEM], world.wall()
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (day(3), putback.OFFER_START)
    assert after['digital_date'] > TODAY and '_reverted_by_owner' not in after
    assert '_revert_page_preorder' not in after
    assert after['_held_since'] == TODAY and after['_put_back_on'] == day(3)
    assert not wall[HARLEM].get('hidden') and wall[HARLEM]['digital_date'] == day(3)


def test_o_reverted_film_is_not_put_back_on_the_listing_that_put_it_on_by_mistake(world):
    """The next day JustWatch still lists the same store rentals (recorded day -1, Amazon's offer
    start ahead) and the store page reads normally (as it did when the owner reverted it): it keeps
    waiting (round 2c -- 2b put it back the day after the revert: the reviewer's "Revert lasts one
    run"). A store's offer that appears after the revert (an Apple 4K rental recorded day 2) is a
    new store listing alone -- it can be a pre-order -- so it still waits (round 2d; 2c put it back
    dated day 2). When it lands on streaming (a record dated day 4), it goes back on, dated day 4.
    (Amazon's offer start is day 10 here, so the streaming offer is the first live evidence.)"""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = [o for o in node['offers'] if o['monetizationType'] == 'CINEMA'] + \
        harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = FakeStorePages.AVAILABLE

    world.run(on_day=1)
    held = world.tracking()[HARLEM]
    assert held['status'] == 'tracking' and held['_jw_revert_reason'] == OWNER_REVERT
    assert held['_jw_last_checked'] == day(1) and held['_jw_last_refuted'] == TODAY
    assert world.wall()[HARLEM].get('hidden') is True

    node['offers'].append(jw_offer('RENT', 'Apple TV Store',
                                   'https://tv.apple.com/us/movie/once-upon-a-time-in-harlem/umc.cmc.harlem',
                                   '$5.99', '2026-10-16T07:00:00Z', ptype='4K', created=day(2)))
    world.run(on_day=2)
    held = world.tracking()[HARLEM]
    assert held['status'] == 'tracking' and held['_jw_last_checked'] == day(2)
    assert held['_jw_last_refuted'] == TODAY, 'waiting is not a "not out yet" day'

    node['offers'].append(jw_offer('FLATRATE', 'Peacock', 'https://www.peacocktv.com/watch/harlem', created=day(4)))
    world.run(on_day=4)
    after = world.tracking()[HARLEM]
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (day(4), FIRST_OFFER)
    assert not after.get('_date_needs_review')
    assert not world.wall()[HARLEM].get('hidden') and world.wall()[HARLEM]['digital_date'] == day(4)


def test_o_same_day_run_after_a_revert_never_dates_it_on_the_revert_day(world):
    _harlem_on_the_wall_by_mistake(world)
    world.pages.text = FakeStorePages.AVAILABLE

    world.run(on_day=0)
    after = world.tracking()[HARLEM]
    if after['status'] == 'available':
        assert after['digital_date'] > TODAY, (
            f"put back the same day it was reverted, dated {after['digital_date']} "
            f"({after.get('_digital_date_source')})")


# ===========================================================================
# J. JustWatch's record dates (verify_availability: offer_dates / first_offer_date / has_live_rent)
# ===========================================================================

EXCLUDED = ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play', 'Shahid VIP', 'Viki', 'Futo', 'AMC Plus']


def test_j_offer_dates_are_the_record_dates_of_real_ways_to_watch_it(world):
    """Verity, live JustWatch 2026-11-14: rentals/purchases recorded 10-27 (Apple 4K 11-12);
    cinema listings (07-21..11-12), Amazon DVD / Blu-ray (10-08) and Fandango's 2000-07-14
    placeholder are not ways to watch it at home."""
    world.jw.use_real('Verity')
    r = JustWatchClient().verify_availability('Verity', 2026, excluded_services=EXCLUDED, tmdb_id=VERITY)
    assert r['verified'] is True
    assert r['offer_dates'] == ['2026-10-27', '2026-11-12']
    assert r['first_offer_date'] == '2026-10-27'
    assert r['has_live_rent'] is True
    assert r['has_cinema'] is True


def test_j_offer_dates_skip_excluded_services_and_channels(world):
    """Balearic, live JustWatch 2026-11-14 (record dates SYNTHETIC: the v2 dry run on live data,
    v2_discover1.log, dated it 2026-11-10 jw_first_offer -- its first VALID offer, Fandor; Philo is
    an excluded service, Fandor Amazon Channel a channel offer, the Blu-ray a disc)."""
    world.jw.use_real('Balearic')
    node = world.jw.node('Balearic')
    set_created(node, '2026-10-27')
    set_created(node, '2026-11-10', lambda o: o['package']['clearName'] == 'Fandor')
    r = JustWatchClient().verify_availability('Balearic', 2025, excluded_services=EXCLUDED, tmdb_id=BALEARIC)
    assert r['verified'] is True and r['has_streaming'] is True
    assert r['offer_dates'] == ['2026-11-10']


def test_j_avatar_records_start_with_apples_purchase_not_amazons_relisting(world):
    """Avatar: Fire and Ash, live JustWatch 2026-11-13: Apple purchase recorded 2026-03-31
    (= TMDB's first digital date); Amazon's offers are a later re-listing (09-30, 11-03)."""
    world.jw.use_real('Avatar: Fire and Ash')
    r = JustWatchClient().verify_availability('Avatar: Fire and Ash', 2025, excluded_services=EXCLUDED, tmdb_id=AVATAR)
    assert r['offer_dates'] == ['2026-03-31', '2026-06-24', '2026-07-07', '2026-07-09', '2026-09-30', '2026-11-03']


def test_j_amazon_preorder_rental_is_not_live_until_its_offer_start(world):
    world.jw.edges['Once Upon a Time in Harlem'] = [jw_node(HARLEM, 'Once Upon a Time in Harlem', 2026, [
        jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, '$5.99', f'{day(10)}T07:00:00Z', created=TODAY)])]
    r = JustWatchClient().verify_availability('Once Upon a Time in Harlem', 2026, tmdb_id=HARLEM)
    assert r['has_rent'] is True and r['has_live_rent'] is False
    world.jw.edges['Once Upon a Time in Harlem'][0]['offers'][0]['availableFromTime'] = f'{TODAY}T07:00:00Z'
    r = JustWatchClient().verify_availability('Once Upon a Time in Harlem', 2026, tmdb_id=HARLEM)
    assert r['has_live_rent'] is True


def test_j_apple_store_rental_is_not_proof_it_is_out(world):
    """Verity's real Apple TV Store rental (live capture: clearName 'Apple TV Store', technicalName
    'itunes') without Amazon's offers. A rental, but not a LIVE one (round 2c): Apple's store lists
    its RENT offer from the theater opening, with the theatrical date as its offer start (Project
    Hail Mary: recorded on opening day 03-20, out 05-12), so it proves nothing about today."""
    world.jw.use_real('Verity')
    node = world.jw.node('Verity', VERITY)
    node['offers'] = [o for o in node['offers'] if o['package']['clearName'] == 'Apple TV Store']
    assert {o['package']['technicalName'] for o in node['offers']} == {'itunes'}
    r = JustWatchClient().verify_availability('Verity', 2026, excluded_services=EXCLUDED, tmdb_id=VERITY)
    assert r['has_rent'] is True
    assert r['has_live_rent'] is False and r['live_rent_starts'] == []


# ===========================================================================
# (a) the retired 4-strike permanent skip
# ===========================================================================

def test_a_legacy_permanently_skipped_hold_is_checked_this_run_and_flag_is_retired(world):
    """Tox (1451998) reached the old 4-strike ceiling (no offer 2026-10-08..10-11) and got
    _skip_provider_discovery: before Step 1 nothing ever checked it again. Now it is asked of
    JustWatch this run; JustWatch has it with no offer, so today is a proven "not out yet" day."""
    mid = TOX
    before = real(mid)
    assert before['_skip_provider_discovery'] is True and before['_jw_revert_count'] >= 4
    world.seed({mid: before})
    world.tmdb.use_real(mid)     # TMDB: Type 4 2026-01-21, no providers
    world.jw.use_real('Tox')     # JustWatch today: "Tox" (2026, TMDB 1451998) with no offers

    world.run()

    after = world.tracking()[mid]
    assert 'Tox' in world.jw.queries, 'JustWatch was never asked about Tox: the permanent skip is still in force'
    assert '_skip_provider_discovery' not in after, 'legacy skip flag survived a real JustWatch check'
    assert after['_jw_last_checked'] == TODAY
    assert after['_jw_revert_count'] == before['_jw_revert_count'] + 1
    assert after['_jw_revert_reason'] == 'justwatch_no_valid_offers'
    assert after['_jw_last_refuted'] == TODAY
    assert after['status'] == 'tracking' and mid not in world.wall()


# ===========================================================================
# (b) held films are checked even when TMDB shows nothing
# ===========================================================================

def test_b_held_film_with_empty_tmdb_providers_and_no_type4_still_gets_a_justwatch_check(world):
    """Mixtape (1690338) is held ('justwatch_no_match' x3 since 2026-05-10). TMDB today has no
    US release date and an empty watch/providers payload. It must still be checked -- and a
    no-match is not a proven "not out yet" day."""
    mid = MIXTAPE
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)
    assert world.tmdb.providers[mid]['results'] == {}
    assert world.tmdb.release_dates[mid]['results'] == []
    world.jw.use_real('Mixtape')  # JustWatch today: only OTHER films named Mixtape

    world.run()

    after = world.tracking()[mid]
    assert 'Mixtape' in world.jw.queries, 'held film skipped because TMDB listed no provider'
    assert after['_jw_last_checked'] == TODAY
    assert after['_jw_revert_count'] == before['_jw_revert_count'] + 1
    assert after['_jw_revert_reason'] == 'justwatch_no_match'
    assert '_jw_last_refuted' not in after, 'a JustWatch no-match was recorded as a proven "not out yet" day'
    assert after['status'] == 'tracking'


def test_b_title_mismatch_answer_is_a_no_match_not_a_refuted_day(world, monkeypatch):
    """verify_availability answers 'first_result' (a different film's result) as verified=False.
    That says nothing about OUR film: recorded as justwatch_no_match, never as no valid offers."""
    mid = HARLEM
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)

    def mismatch(self, title, year=None, **kw):
        return {'verified': False, 'match_confidence': 'first_result', 'jw_title': 'Once Upon a Time in… Hollywood',
                'jw_year': 2019, 'has_streaming': False, 'has_rent': False, 'has_buy': False,
                'provider_names': {'streaming': [], 'rent': [], 'buy': []}, 'watch_links': {}}
    monkeypatch.setattr(JustWatchClient, 'verify_availability', mismatch)
    world.disc._jw_healthy, world.disc._jw_healthy_at = True, time.time()   # JustWatch is up

    world.run()

    after = world.tracking()[mid]
    assert after['_jw_revert_reason'] == 'justwatch_no_match'
    assert after['_jw_revert_count'] == before['_jw_revert_count'] + 1
    # Not a "not out yet" day: only the hold's OLD last no-offer day is kept (persisted
    # before the reason changes -- round 2c), never the no-match day itself.
    assert after.get('_jw_last_refuted') in (None, putback.last_refuted_day(before, '2026-11-14'))
    assert after.get('_jw_last_refuted') != '2026-11-14'


# ===========================================================================
# (c) JustWatch errors and outages are never strikes (rule 5)
# ===========================================================================

@pytest.mark.parametrize('error', ['connection_error', 'timeout', 'http_429', 'graphql_error', 'malformed'])
def test_c_justwatch_error_is_not_a_strike_and_keeps_the_legacy_flag(world, error):
    """Life Goes This Way (1397375): legacy skip, 4 strikes. JustWatch errors out on its lookup
    -> nothing about the film is recorded; it is simply re-checked next run. 'malformed' (offers
    null: verify_availability raises after the search succeeded) used to FAIL OPEN onto the wall
    (finding 12); now it is a JustWatch error like the others."""
    mid = LIFE
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)   # no Type 4; TMDB lists rent/buy on Amazon, Apple, YouTube...
    world.jw.edges['Life Goes This Way'] = [jw_node(mid, 'Life Goes This Way', 2025, [   # SYNTHETIC listing
        jw_offer('RENT', 'Amazon Video', 'https://watch.amazon.com/detail?gti=life-goes', '$3.99',
                 '2026-07-10T07:00:00Z', created='2026-07-10')])]
    world.jw.errors['Life Goes This Way'] = error

    world.run()

    after = world.tracking()[mid]
    assert 'Life Goes This Way' in world.jw.queries      # the check was attempted
    assert after['_jw_revert_count'] == before['_jw_revert_count'], 'a JustWatch error was counted as a strike'
    assert '_jw_last_checked' not in after, 'a JustWatch error was recorded as a no-offer day'
    assert '_jw_last_refuted' not in after
    assert after.get('_skip_provider_discovery') is True, 'legacy flag (needed for dating) dropped on an error'
    assert after['status'] == 'tracking'
    assert after['digital_date'] == before['digital_date']
    assert mid not in world.wall(), 'an unconfirmed film went on the wall'
    results = world.metrics()['results']
    assert (results['jw_lookups'], results['jw_errors']) == (1, 1)


def test_c_justwatch_outage_seen_by_unhealthy_canary_is_not_a_strike(world):
    """A blocked JustWatch answers HTTP 200 with zero results for everything (looks like "no
    match"). The canary sees the outage, so the held film gets no strike."""
    mid = LIFE
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)
    world.jw.blocked = True

    world.run()

    after = world.tracking()[mid]
    assert any(q in world.jw.queries for q in FakeJustWatch.CANARY), 'canary never ran'
    assert after['_jw_revert_count'] == before['_jw_revert_count'], 'outage counted as a strike'
    assert '_jw_last_checked' not in after and '_jw_last_refuted' not in after
    assert after.get('_skip_provider_discovery') is True
    assert world.metrics()['results']['jw_healthy'] is False


@pytest.mark.parametrize('outage', [True, False], ids=['offers-outage', 'genuine-no-offer'])
def test_c_titles_without_offers_count_only_when_the_canary_has_offers(world, outage):
    """Finding 21: JustWatch answers with the right titles but empty offer lists. For held Once
    Upon a Time in Harlem that reads 'JustWatch has it, no offer' = a proven "not out yet" day.
    The canary now needs real OFFERS for a control title: in an outage of the offer data nothing
    is recorded; when the control titles have offers it is a genuine no-offer day."""
    mid = HARLEM
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)
    world.jw.use_real('Once Upon a Time in Harlem')
    world.jw.node('Once Upon a Time in Harlem', HARLEM)['offers'] = []
    world.jw.offers_outage = outage

    world.run()

    after = world.tracking()[mid]
    assert 'Once Upon a Time in Harlem' in world.jw.queries and 'Oppenheimer' in world.jw.queries
    if outage:
        assert after['_jw_revert_count'] == before['_jw_revert_count'], 'offers outage counted as a strike'
        assert '_jw_last_checked' not in after and '_jw_last_refuted' not in after
        assert world.metrics()['results']['jw_healthy'] is False
    else:
        assert after['_jw_revert_count'] == before['_jw_revert_count'] + 1
        assert after['_jw_last_checked'] == TODAY and after['_jw_last_refuted'] == TODAY
        assert world.metrics()['results']['jw_healthy'] is True
    assert after['status'] == 'tracking'


# ===========================================================================
# (d) the canary must not be answered from the shared client's cache
# ===========================================================================

@pytest.mark.parametrize('canary_state', ['not_run_yet_this_run', 'healthy_16_minutes_ago'])
def test_d_health_canary_uses_a_fresh_client_not_the_shared_cache(world, canary_state):
    """The shared JustWatch client already holds the canary titles in its search cache (matched
    earlier, before an outage began). The outage then starts. A canary that asked the shared
    client would read "healthy" from memory and strike the held film."""
    mid = MIXTAPE
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)

    disc = world.disc
    shared = JustWatchClient(logger=disc.logger)
    for title, year in disc._JW_CANARY_TITLES:
        shared._cache[f'{title}_{year}_MOVIE'] = copy.deepcopy(JW_SEARCH[title][0])
    assert shared.verify_availability('Oppenheimer', 2023)['verified'] is True   # answered from memory
    assert world.jw.queries == []
    disc._jw_client = shared
    if canary_state == 'healthy_16_minutes_ago':
        disc._jw_healthy = True
        disc._jw_healthy_at = time.time() - (disc._JW_HEALTH_TTL_S + 60)
    world.jw.blocked = True  # the outage starts now

    world.run()

    after = world.tracking()[mid]
    assert after['_jw_revert_count'] == before['_jw_revert_count'], 'strike recorded during an outage'
    assert '_jw_last_checked' not in after
    assert 'Oppenheimer' in world.jw.queries, 'canary was answered without asking JustWatch'


# ===========================================================================
# (v) _verify_before_wall dates a held film (pending); _transition applies it
# ===========================================================================

def test_v_verify_before_wall_computes_the_put_back_but_leaves_the_hold_in_place(world):
    """Verity (PVOD hold since 11-13). _verify_before_wall dates it from evidence and records a
    PENDING put-back; nothing is applied to the record until it really goes on the wall (a store
    pre-order page later in the run may still hold it)."""
    rec = real(VERITY)
    world.seed({VERITY: rec})
    world.tmdb.use_real(VERITY)
    world.jw.use_real('Verity')
    disc = world.disc
    movie = copy.deepcopy(rec)

    result = disc._verify_before_wall(VERITY, movie)

    assert result['verified'] is True and result['offer_dates'] == ['2026-10-27', '2026-11-12']
    assert disc._pending_putbacks[VERITY] == {'day': '2026-10-27', 'source': FIRST_OFFER, 'backlog': False,
                                              'review': False, 'held_since': '2026-11-13',
                                              'page_available': False}
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at', 'digital_date', '_is_preorder'):
        assert movie.get(k) == rec.get(k), k
    for k in ('_put_back_on', '_held_since', '_digital_date_source', '_jw_last_refuted', '_date_needs_review'):
        assert k not in movie, k
    # A second check of the same film replaces the pending put-back, never stacks it.
    disc._jw_client = None
    world.jw.errors['Verity'] = 'connection_error'
    assert disc._verify_before_wall(VERITY, movie) is None
    assert VERITY not in disc._pending_putbacks


def test_v_an_unheld_film_gets_no_pending_put_back(world):
    """Traces of Justice (new film, never held): confirmed on JustWatch -> an ordinary first
    appearance, no put-back dating (SYNTHETIC: a Tubi listing)."""
    world.seed({TRACES: real(TRACES)})
    world.jw.edges['Traces of Justice'] = [jw_node(TRACES, 'Traces of Justice', 2026, [
        jw_offer('FLATRATE', 'Tubi TV', 'https://tubitv.com/movies/traces-of-justice', created=TODAY)])]
    disc = world.disc
    movie = real(TRACES)
    assert disc._verify_before_wall(TRACES, movie)['verified'] is True
    assert disc._pending_putbacks == {}


def test_v_owner_reverted_film_waits_on_evidence_from_before_the_revert(world):
    """A film the owner reverted is held with reason 'owner_revert'. Sense and Sensibility's real
    JustWatch rentals (recorded 11-03, Amazon's offer start 11-03) and TMDB's digital date (11-03)
    all predate the revert (day -1): no pending put-back, it keeps waiting, checked again next run
    (round 2c -- 2b put it back dated TODAY, putback_after_hold)."""
    rec = real(SENSE)
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        rec.pop(k)
    rec['status'] = 'available'
    putback.owner_revert(rec, today=day(-1))
    world.seed({SENSE: rec})
    world.tmdb.use_real(SENSE)
    world.jw.use_real('Sense and Sensibility')    # real: rentals recorded 11-03, TMDB digital 11-03
    disc = world.disc
    checked = copy.deepcopy(rec)
    assert disc._verify_before_wall(SENSE, checked) is None
    assert SENSE not in disc._pending_putbacks
    assert checked['_jw_last_checked'] == TODAY and checked['_jw_revert_count'] == rec['_jw_revert_count']
    assert checked['_jw_last_refuted'] == day(-1)   # waiting is not a "not out yet" day


@pytest.mark.parametrize('case, streams, starts, page, tmdb, expect', [
    ('nothing after the revert', ['2026-11-01'], ['2026-11-03'], False, '2026-11-03', None),
    ('a streaming offer recorded after the revert', ['2026-11-01', '2026-11-12'], [], False, None,
     ('2026-11-12', FIRST_OFFER)),
    ("Amazon's offer start after the revert (a pre-order going live)", [], ['2026-11-12'], False, None,
     ('2026-11-12', putback.OFFER_START)),
    ('the earliest wins', ['2026-11-13'], ['2026-11-12'], False, None, ('2026-11-12', putback.OFFER_START)),
    # Round 2d: TMDB's date alone never brings it back (JustWatch decides), nor does a page
    # that did not turn from "Pre-order" (the caller says so: page=False).
    ("TMDB's date after the revert, alone", [], [], False, '2026-11-12', None),
    # The store page turned from "Pre-order" to "available": dated by TMDB's date when it is
    # after the revert, else today.
    ("store page now reads available, TMDB's date after the revert", [], [], True, '2026-11-12',
     ('2026-11-12', EVIDENCE)),
    ('store page now reads available, no TMDB date', [], [], True, None, ('2026-11-14', CONFIRMED)),
    ('store page now reads available, TMDB date before the revert', [], [], True, '2026-11-03',
     ('2026-11-14', CONFIRMED)),
])
def test_p_owner_revert_putback_needs_something_new_that_shows_it_watchable(case, streams, starts, page, tmdb, expect):
    """Reverted 11-10: back only on something NEW since the revert that shows it watchable now --
    a streaming offer JustWatch recorded after it, an Amazon rental going live after it -- or its
    store page turning to "available" (round 2d: a new store listing alone, and TMDB's date, are
    what put it on the wall by mistake)."""
    rec = {'status': 'available', 'title': 'X', 'year': 2026}
    putback.owner_revert(rec, today='2026-11-10')
    assert putback.owner_revert_putback(rec, streams, starts, page, tmdb, '2026-11-14') == expect, case


def test_p_owner_revert_putback_after_a_later_not_out_day_is_dated_the_day_after_it():
    """Amazon's rental went live 11-12 (after the 11-10 revert), but the store page still read
    "Pre-order" on 11-12: it is dated 11-13, the day after -- never on a day proven not out, and
    never left waiting for good."""
    rec = {'status': 'available', 'title': 'X', 'year': 2026}
    putback.owner_revert(rec, today='2026-11-10')
    rec['_rent_preorder_held'] = '2026-11-12'
    assert putback.owner_revert_putback(rec, [], ['2026-11-12'], False, None,
                                        '2026-11-14') == ('2026-11-13', AFTER_HOLD)


def test_p_owner_revert_putback_never_on_the_revert_day():
    rec = {'status': 'available', 'title': 'X', 'year': 2026}
    putback.owner_revert(rec, today='2026-11-14')
    assert putback.owner_revert_putback(rec, ['2026-11-14'], ['2026-11-14'], True, '2026-11-14',
                                        '2026-11-14') is None


@pytest.mark.parametrize('flag', ['_reissue', 'reissue_label', '_reissue_deferred'])
def test_p_owner_revert_putback_a_reissue_never_comes_back_by_itself(flag):
    """Owner, Nov 2026 (no "re-add it yourself"): a reverted reissue comes back like any reverted
    film -- on something NEW since the revert (a stream recorded after it, an Amazon rental going
    live after it, the page turning) -- never on the original's OLD records. The revert's note
    says the original's listing can bring it back. (Name kept from round 2e.)"""
    rec = {'status': 'available', 'title': 'X', 'year': 1990, flag: '4K Restoration' if flag == 'reissue_label' else True}
    putback.owner_revert(rec, today='2026-11-10')
    assert putback.owner_revert_putback(rec, ['2019-03-01'], [], False, None, '2026-11-14') is None   # old record
    assert putback.owner_revert_putback(rec, ['2019-03-01', '2026-11-13'], [], False, None, '2026-11-14') == \
        ('2026-11-13', FIRST_OFFER)
    assert putback.owner_revert_putback(rec, [], ['2026-11-12'], False, None, '2026-11-14') == ('2026-11-12', putback.OFFER_START)
    assert 'original film' in putback.revert_caveat(rec) and '/add-movie' not in putback.revert_caveat(rec)


@pytest.mark.parametrize('start, expect', [
    ('2026-11-10T20:00:00Z', ('2026-11-11', AFTER_HOLD)),    # live that afternoon: next day
    ('2026-11-10T09:00:00Z', None),                           # live before the morning revert
    ('2026-11-11T04:00:00Z', ('2026-11-11', putback.OFFER_START)),
])
def test_p_owner_revert_counts_a_release_later_the_same_day(start, expect):
    """Round 2e (critic CRIT-1): the owner reverts at 16:00 UTC (a morning in California) on 11-10.
    An Amazon rental going live at 20:00 UTC that day is new since the revert -- before, its day
    (= the revert day) didn't count and the film waited forever. Dated the day after the revert
    (never on it). A rental live before the revert moment still doesn't count."""
    rec = {'status': 'available', 'title': 'X', 'year': 2026}
    putback.owner_revert(rec, today='2026-11-10')
    rec['_reverted_by_owner_at'] = '2026-11-10T16:00:00Z'
    assert putback.owner_revert_putback(rec, [], [start], False, None, '2026-11-14') == expect
    # a day-only record on the revert day still says nothing (JustWatch gives no time)
    assert putback.owner_revert_putback(rec, ['2026-11-10'], [], False, None, '2026-11-14') is None
    # an old record (no moment stored) compares days, as before
    rec.pop('_reverted_by_owner_at')
    assert putback.owner_revert_putback(rec, [], ['2026-11-10T20:00:00Z'], False, None, '2026-11-14') is None


def test_p_owner_reverted_helpers():
    rec = {'status': 'available', 'title': 'X', 'year': 2026, '_added_manually': True}
    assert not putback.is_owner_reverted(rec) and putback.revert_caveat({'title': 'Y'}) is None
    putback.owner_revert(rec, today='2026-11-10')
    assert putback.is_owner_reverted(rec) and rec['_added_manually_before_revert'] is True
    assert 'added by hand' in putback.revert_caveat(rec)
    assert 'watch-link override' in putback.revert_caveat({'title': 'Y'}, has_override=True)
    assert 'Apple Music Live' in putback.revert_caveat({'_apple_music_live': True})
    assert putback.revert_live_evidence(rec, ['2026-11-10', '2026-11-11'], ['2026-11-09', '2026-11-20'],
                                        '2026-11-14') == [('2026-11-11', FIRST_OFFER)]
    rec['status'] = 'available'
    assert not putback.is_owner_reverted(rec)   # put back / re-added: no longer waiting
    entry = {'id': 1, '_jw_unconfirmed': '2026-11-09', '_added_manually': True, 'hidden': False}
    putback.mark_reverted_entry(entry)
    assert entry == {'id': 1, 'hidden': True, '_enrichment_status': 'reverted', '_jw_reverted': True,
                     '_jw_revert_reason': OWNER_REVERT, 'status': 'tracking'}


def test_t_transition_applies_the_put_back_and_persists_the_floor(world):
    """_transition, given the pending put-back: dated, hold history cleared by the wall move --
    but the last "not out yet" day (here the legacy estimate 2026-09-28, which exists only while
    the hold fields do) is kept as `_jw_last_refuted`. The store-page and pre-order flags go."""
    movie = real(GO_DEEP)
    movie.pop('_skip_provider_discovery')
    movie.update({'_rent_preorder_held': '2026-09-20', '_is_preorder': True})
    world.seed({GO_DEEP: movie})
    disc = world.disc
    disc._pending_putbacks[GO_DEEP] = {'day': '2026-09-29', 'source': AFTER_HOLD, 'backlog': True,
                                       'review': True, 'held_since': '2026-09-25'}
    ids = []
    disc._transition(GO_DEEP, movie, 'tmdb_type4', ids)

    assert ids == [GO_DEEP] and GO_DEEP not in disc._pending_putbacks
    assert (movie['status'], movie['digital_date'], movie['_digital_date_source']) == ('available', '2026-09-29', AFTER_HOLD)
    assert (movie['_held_since'], movie['_put_back_on'], movie['_date_before_putback']) == ('2026-09-25', TODAY, '2026-09-24')
    assert movie['_date_needs_review'] is True and disc._backlog_putbacks == 1
    assert movie['_jw_last_refuted'] == '2026-09-28'
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at', '_jw_last_checked',
              '_rent_preorder_held', '_is_preorder'):
        assert k not in movie, k
    assert putback.last_refuted_day(movie, TODAY) == '2026-09-28'
    assert world.wall()[GO_DEEP]['digital_date'] == '2026-09-29'


def test_t_transition_without_a_put_back_drops_an_old_put_backs_date_source(world):
    """A film with an old put-back's protected source (dated by a previous put-back, since pulled
    without a hold) that comes out through the ordinary path: the source goes, so enrichment
    dates it again instead of keeping a date from an earlier stint."""
    movie = real(TRACES)
    movie.update({'digital_date': TODAY, '_digital_date_source': CONFIRMED})
    world.seed({TRACES: movie})
    disc = world.disc
    disc._transition(TRACES, movie, 'provider_availability_check', [])
    assert '_digital_date_source' not in movie and '_put_back_on' not in movie
    assert movie['status'] == 'available' and movie['digital_date'] == TODAY


# ===========================================================================
# (e) put-back dates
# ===========================================================================

@pytest.mark.parametrize('mid, query, drop, expected', [
    # Real record as stored: still carries _is_preorder from its pre-order days.
    pytest.param(VERITY, 'Verity', (), '2026-10-27', id='Verity-as-stored'),
    pytest.param(VERITY, 'Verity', ('_is_preorder',), '2026-10-27', id='Verity-PVOD-hold-no-preorder-flag'),
    pytest.param(SENSE, 'Sense and Sensibility', (), '2026-11-03', id='Sense-and-Sensibility-as-stored'),
])
def test_e_pvod_held_film_put_back_is_dated_its_first_digital_day(world, mid, query, drop, expected):
    """PVOD hold (in theaters + premium rental). JustWatch's first record of a real offer and
    TMDB's earliest US digital date agree: Verity 2026-10-27, Sense and Sensibility 2026-11-03.
    The put-back is dated that day, not today, and applied at the wall move."""
    rec = real(mid)
    assert rec['_jw_revert_reason'] == 'justwatch_theatrical_pvod'
    for k in drop:
        rec.pop(k)
    world.seed({mid: rec})
    world.tmdb.use_real(mid)
    world.jw.use_real(query)

    world.run()

    after, wall = world.tracking()[mid], world.wall()
    assert after['status'] == 'available'
    assert after['digital_date'] == expected and wall[mid]['digital_date'] == expected
    assert after['_digital_date_source'] == FIRST_OFFER
    assert (after['_put_back_on'], after['_held_since']) == (TODAY, '2026-11-13')
    assert not after.get('_date_needs_review')
    assert '_is_preorder' not in after and not wall[mid].get('_is_preorder'), 'confirmed film left in the pre-order lane'
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at', '_rent_preorder_held'):
        assert k not in after, k
    assert '_jw_last_refuted' not in after     # a PVOD hold never proved it unavailable


@pytest.mark.parametrize('hold', [
    None,
    {'_jw_revert_count': 1, '_jw_revert_reason': 'justwatch_theatrical_pvod',
     '_jw_reverted_at': '2026-11-13', '_jw_last_checked': '2026-11-13'},
], ids=['restored-no-hold', 'restored-then-held-once-as-PVOD'])
def test_e_restore_like_film_dated_its_first_digital_day_not_amazons_later_relisting(world, hold):
    """Avatar: Fire and Ash (83533) as the 2026-11-13 HEAD had it: back in tracking after the
    owner's restore (fa8cc97e, since reverted -- 78303fd6 has it 'removed'). TMDB lists Type 4
    2026-03-31 and 2026-06-24 (Disney+); JustWatch's first record is Apple's purchase on
    2026-03-31; Amazon's offers (09-30, 11-03) are a re-listing. Dated 2026-03-31."""
    rec = copy.deepcopy(AVATAR_HEAD_20261113)
    assert rec['status'] == 'tracking'
    rec.update(hold or {})
    world.seed({AVATAR: rec})
    world.tmdb.use_real(AVATAR)
    world.jw.use_real('Avatar: Fire and Ash')

    world.run()

    after, wall = world.tracking()[AVATAR], world.wall()
    assert after['status'] == 'available'
    assert after['digital_date'] == '2026-03-31' and wall[AVATAR]['digital_date'] == '2026-03-31'
    if hold:
        assert after['_digital_date_source'] == FIRST_OFFER and after['_put_back_on'] == TODAY
    else:
        assert '_put_back_on' not in after    # not held: the ordinary Type 4 path dated it


@pytest.mark.parametrize('jw_record', [None, '2026-09-24'], ids=['no-JustWatch-record', 'record-on-the-TMDB-day'])
def test_e_legacy_no_offer_hold_is_dated_the_day_after_its_last_no_offer_day(world, jw_record):
    """Go Deep: The DeSean Jackson Story (1766609): legacy hold, JustWatch showed no offer on 4
    daily checks from 2026-09-25 (last: 2026-09-28), then it was skipped. TMDB's digital date
    (2026-09-24, Prime Video) -- and JustWatch's record, if it is that day too (SYNTHETIC: its
    Prime Video offer start) -- fall inside the refuted days, so it is dated 2026-09-29, never on
    a day JustWatch said "no offer". The 09-28 floor is an estimate (the film went unchecked for
    weeks), so the date is flagged for the owner."""
    mid = GO_DEEP
    rec = real(mid)
    assert (rec['_jw_revert_reason'], rec['_jw_reverted_at'], rec['_jw_revert_count']) == \
        ('justwatch_no_valid_offers', '2026-09-25', 4)
    world.seed({mid: rec})
    world.tmdb.use_real(mid)
    world.jw.use_real('Go Deep: The DeSean Jackson Story')   # JustWatch today: Prime Video
    if jw_record:
        set_created(world.jw.node('Go Deep: The DeSean Jackson Story', mid), jw_record)

    world.run()

    after, wall = world.tracking()[mid], world.wall()
    assert after['status'] == 'available'
    assert after['digital_date'] == '2026-09-29' and wall[mid]['digital_date'] == '2026-09-29'
    assert after['_digital_date_source'] == AFTER_HOLD
    assert after.get('_date_needs_review') is True
    assert after['_date_before_putback'] == '2026-09-24'
    # The floor outlives the transition, which clears every hold field.
    assert after['_jw_last_refuted'] == '2026-09-28'
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at', '_jw_last_checked', '_skip_provider_discovery'):
        assert k not in after, k
    assert putback.last_refuted_day(after, TODAY) == '2026-09-28'


@pytest.mark.parametrize('records, expected, source, review', [
    pytest.param(True, '2026-11-10', FIRST_OFFER, False, id='first-valid-offer-recorded-11-10'),
    pytest.param(False, TODAY, REVIEW, True, id='no-record-dates'),
])
def test_e_legacy_hold_is_dated_by_its_first_valid_offer_or_today_for_review(world, records, expected, source, review):
    """Balearic (1510323): legacy hold (no offer 10-28..10-31), unchecked since. JustWatch now has
    it on Fandor (Philo is excluded, Fandor Amazon Channel is a channel offer). v1 kept the old
    10-28 date; v2 dates it by its first VALID offer (record 11-10, after the floor -- the v2 dry
    run on live data gave exactly this), or, with no record dates, today, flagged for the owner
    (visible on the wall, never a stale date). TMDB has no digital date."""
    mid = BALEARIC
    rec = real(mid)
    assert rec['_skip_provider_discovery'] is True and rec['digital_date'] == '2026-10-28'
    world.seed({mid: rec})
    world.tmdb.use_real(mid)
    world.jw.use_real('Balearic')
    if records:   # SYNTHETIC record dates, see test_j_offer_dates_skip_excluded_services_and_channels
        node = world.jw.node('Balearic')
        set_created(node, '2026-10-27')
        set_created(node, '2026-11-10', lambda o: o['package']['clearName'] == 'Fandor')

    world.run()

    after, wall = world.tracking()[mid], world.wall()
    assert after['status'] == 'available'
    assert after['digital_date'] == expected and wall[mid]['digital_date'] == expected
    assert after['_digital_date_source'] == source
    assert bool(after.get('_date_needs_review')) is review
    assert after['_date_before_putback'] == '2026-10-28'


@pytest.mark.parametrize('created, source', [(None, CONFIRMED), (TODAY, FIRST_OFFER)],
                         ids=['no-record-date', 'recorded-today'])
def test_e_daily_checked_hold_released_today_is_dated_today(world, created, source):
    """Christmas at Mistletoe Manor (1033671): held, JustWatch showed only fuboTV (excluded) on
    yesterday's check (2026-11-13). Simulated release today: JustWatch also lists it on Great
    American Pure Flix. No TMDB digital date -> it came out today, and was checked daily, so the
    date is confirmed (no review)."""
    mid = MISTLETOE
    rec = real(mid)
    assert (rec['_jw_reverted_at'], rec['_jw_revert_count']) == ('2026-11-13', 1)
    world.seed({mid: rec})
    world.tmdb.use_real(mid)                # TMDB: no Type 4 (TV premiere only), lists fuboTV
    world.jw.use_real('Christmas at Mistletoe Manor')
    world.jw.node('Christmas at Mistletoe Manor', mid)['offers'].append(jw_offer(
        'FLATRATE', 'Great American Pure Flix',
        'https://www.greatamericanpureflix.com/movies/christmas-at-mistletoe-manor', created=created))

    world.run()

    after, wall = world.tracking()[mid], world.wall()
    assert after['status'] == 'available'
    assert after['digital_date'] == TODAY and wall[mid]['digital_date'] == TODAY
    assert after['_digital_date_source'] == source
    assert not after.get('_date_needs_review')
    assert after['_jw_last_refuted'] == '2026-11-13'


def _mistletoe_released_today(world, created):
    world.seed({MISTLETOE: real(MISTLETOE)})
    world.tmdb.use_real(MISTLETOE)
    world.jw.use_real('Christmas at Mistletoe Manor')
    world.jw.node('Christmas at Mistletoe Manor', MISTLETOE)['offers'].append(jw_offer(
        'FLATRATE', 'Great American Pure Flix',
        'https://www.greatamericanpureflix.com/movies/christmas-at-mistletoe-manor', created=created))


def _harlem_preorder_yesterday_released_today(world, created):
    """Once Upon a Time in Harlem, held as a store pre-order yesterday (the page read "Pre-order";
    v2 stamps _rent_preorder_held and _jw_last_refuted), out today."""
    rec = real(HARLEM)
    rec['_rent_preorder_held'] = day(-1)
    rec['_jw_last_refuted'] = day(-1)
    world.seed({HARLEM: rec})
    world.tmdb.use_real(HARLEM)
    world.jw.use_real('Once Upon a Time in Harlem')
    world.jw.node('Once Upon a Time in Harlem', HARLEM)['offers'] += harlem_store_offers(
        f'{TODAY}T07:00:00Z', created=created)
    world.pages.text = FakeStorePages.AVAILABLE


@pytest.mark.parametrize('scenario, source', [
    pytest.param('mistletoe-no-record', CONFIRMED, id='CONFIRMED'),
    pytest.param('mistletoe-recorded-today', FIRST_OFFER, id='FIRST_OFFER'),
    pytest.param('harlem-records-before-the-floor', AFTER_HOLD, id='AFTER_HOLD'),
    pytest.param('harlem-record-after-the-floor', FIRST_OFFER, id='FIRST_OFFER-after-a-store-hold'),
])
@pytest.mark.parametrize('tmdb', ['down', 'broken', 'up'])
def test_e_tmdb_lookup_failure_flags_the_put_back_for_review_whatever_its_source(world, scenario, source, tmdb):
    """TMDB's release_dates fails all run (503, or the request raises): fetch_tmdb_us_release_dates
    returns None -- TMDB's dates are UNKNOWN, not absent (an earlier digital date may exist, and the
    theater-week guard is off). Round 2b: the put-back date is flagged for the owner whatever its
    source. With TMDB up, the same put-backs are not flagged."""
    if scenario.startswith('mistletoe'):
        mid = MISTLETOE
        _mistletoe_released_today(world, TODAY if scenario.endswith('today') else None)
    else:
        mid = HARLEM
        _harlem_preorder_yesterday_released_today(world, TODAY if scenario.endswith('after-the-floor') else day(-2))
    if tmdb == 'down':
        world.tmdb.down[mid] = {'release_dates'}
    elif tmdb == 'broken':
        world.tmdb.broken[mid] = {'release_dates'}

    world.run()

    after = world.tracking()[mid]
    assert (mid, 'release_dates') in world.tmdb.calls
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (TODAY, source)
    assert bool(after.get('_date_needs_review')) is (tmdb != 'up')


def test_e_fetch_tmdb_us_release_dates_answers_none_only_when_tmdb_fails(world):
    """The (theatrical, digital) pair, either part None when TMDB has no such date; None itself
    (not a pair) only when TMDB couldn't answer."""
    gen = world.gen
    world.tmdb.release_dates[VERITY] = copy.deepcopy(TMDB_RELEASE_DATES[VERITY])
    assert gen.fetch_tmdb_us_release_dates(VERITY) == ('2026-10-02', '2026-10-27')   # Type 1 premiere ignored
    world.tmdb.set_dates(MISTLETOE, (6, '2025-12-07', 'Great American Family'))
    assert gen.fetch_tmdb_us_release_dates(MISTLETOE) == (None, None)
    world.tmdb.release_dates[TRACES] = {'id': int(TRACES), 'results': []}
    assert gen.fetch_tmdb_us_release_dates(TRACES) == (None, None)
    world.tmdb.down[TRACES] = {'release_dates'}
    assert gen.fetch_tmdb_us_release_dates(TRACES) is None
    world.tmdb.broken[MISTLETOE] = {'release_dates'}
    assert gen.fetch_tmdb_us_release_dates(MISTLETOE) is None


# ===========================================================================
# (f) a failed check must not move the date
# ===========================================================================

@pytest.mark.parametrize('mid, query, tmdb_lists', [
    # New film, no date yet. Simulated: TMDB starts listing Amazon; JustWatch (real) only has
    # cinema showtimes for it.
    pytest.param(TRACES, 'Traces of Justice', {'rent': ['Amazon Video'], 'buy': ['Amazon Video']},
                 id='new-film-without-a-date'),
    # Held film with a date; TMDB (real) lists fuboTV, JustWatch (real) only fuboTV (excluded).
    pytest.param(MISTLETOE, 'Christmas at Mistletoe Manor', None, id='held-film-with-a-date'),
])
def test_f_failed_check_on_provider_path_does_not_move_tracking_date(world, mid, query, tmdb_lists):
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)
    if tmdb_lists:
        world.tmdb.set_providers(mid, **tmdb_lists)
    world.jw.use_real(query)

    world.run()

    after = world.tracking()[mid]
    assert query in world.jw.queries
    assert after['status'] == 'tracking'
    assert after['_jw_revert_count'] == (before.get('_jw_revert_count') or 0) + 1   # it failed today
    assert after.get('digital_date') == before.get('digital_date'), \
        'a failed JustWatch check moved the tracking date (old bug: stamped the no-offer day as the date)'
    # JustWatch has the film with no way to watch it at home: a proven "not out yet" day.
    assert (after['_jw_revert_reason'], after['_jw_last_refuted']) == ('justwatch_no_valid_offers', TODAY)
    assert mid not in world.wall()


def test_f_held_film_is_checked_and_keeps_its_providers_when_tmdb_provider_lookup_fails(world):
    """Life Goes This Way (held, legacy skip). TMDB's watch/providers answers 503 today (data
    None): the held film is still checked on JustWatch (rule 2), and TMDB's error does not wipe
    the providers it already has. JustWatch (SYNTHETIC listing) has it with no offer today."""
    mid = LIFE
    before = real(mid)
    world.seed({mid: before})
    world.tmdb.use_real(mid)
    world.tmdb.down[mid] = {'watch/providers'}
    world.jw.edges['Life Goes This Way'] = [jw_node(mid, 'Life Goes This Way', 2025, [])]

    world.run()

    after = world.tracking()[mid]
    assert (mid, 'watch/providers') in world.tmdb.calls
    assert 'Life Goes This Way' in world.jw.queries, 'held film skipped because TMDB errored'
    assert after['providers'] == before['providers'], 'a TMDB error wiped the providers'
    assert (after['_jw_revert_count'], after['_jw_last_refuted']) == (before['_jw_revert_count'] + 1, TODAY)
    assert after['status'] == 'tracking'


def test_f_new_release_keeps_its_first_signal_date_through_a_justwatch_error(world):
    """Round 2: after a JustWatch ERROR on the provider path, only a HELD film gets the speculative
    'today' date undone. Traces of Justice (real: new, no date, never held): day 0 TMDB starts
    listing a Tubi stream (SYNTHETIC) but JustWatch errors -> waits, no strike, keeps day 0 as its
    first-signal date. Day 1 JustWatch confirms it -> dated day 0, not the day JustWatch recovered."""
    world.seed({TRACES: real(TRACES)})
    world.tmdb.use_real(TRACES)
    world.tmdb.set_providers(TRACES, flatrate=['Tubi TV'])
    world.jw.edges['Traces of Justice'] = [jw_node(TRACES, 'Traces of Justice', 2026, [
        jw_offer('FLATRATE', 'Tubi TV', 'https://tubitv.com/movies/traces-of-justice')])]
    world.jw.errors['Traces of Justice'] = 'connection_error'

    world.run()
    waiting = world.tracking()[TRACES]
    assert waiting['status'] == 'tracking' and TRACES not in world.wall()
    assert waiting['digital_date'] == TODAY
    for k in ('_jw_revert_count', '_jw_last_checked', '_jw_last_refuted'):
        assert k not in waiting, k

    world.jw.errors.clear()
    world.run(on_day=1)
    after = world.tracking()[TRACES]
    assert after['status'] == 'available' and '_put_back_on' not in after
    assert after['digital_date'] == TODAY and world.wall()[TRACES]['digital_date'] == TODAY


# ===========================================================================
# (k) "never on a refuted day" must survive the hold reason changing
# ===========================================================================

WILDCARDS_AMAZON = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-wildcards001'


def _wildcards_found(world, offers):
    """Wildcards (1396875) with a JustWatch node carrying `offers` (its live node had none)."""
    world.jw.edges['Wildcards'] = [jw_node(WILDCARDS, 'Wildcards', 2026, offers)]


def _wildcards_rental(on, price='$5.99'):
    """SYNTHETIC: Amazon lists the rental on day `on` (offer start + record date that day)."""
    return [jw_offer('RENT', 'Amazon Video', WILDCARDS_AMAZON, price, f'{on}T07:00:00Z', created=on),
            jw_offer('BUY', 'Amazon Video', WILDCARDS_AMAZON, '$14.99', f'{on}T07:00:00Z', created=on)]


WILDCARDS_CINEMA = jw_offer('CINEMA', 'Fandango', 'https://www.fandango.com/wildcards-2026/movie-overview',
                            ptype='CANVAS', created='2026-08-20')


def test_k_floor_survives_a_put_back_and_a_real_enrichment_pvod_pull(world):
    """Findings 10(b)/20, with the REAL enrichment run after the put-back. Wildcards (real:
    held 'no valid offers', last no-offer day 2026-11-13 by the legacy estimate; TMDB Type 4
    2026-11-09). Day 0: JustWatch lists a $19.99 rental with cinema showtimes, recorded today
    -> put back dated today; the transition clears the hold fields but persists the floor.
    Owner, Nov 2026: a $19.99 rental is rentable -- enrichment no longer pulls it (the $15+
    PVOD block is gone): it stays on the wall dated 2026-11-14 on day 0 and day 5, never
    TMDB's 2026-11-09 (before a day JustWatch said "no offer"). (Name kept from the PVOD era.)"""
    world.seed({WILDCARDS: real(WILDCARDS)})
    world.tmdb.release_dates[WILDCARDS] = copy.deepcopy(TMDB_RELEASE_DATES[WILDCARDS])
    _wildcards_found(world, [WILDCARDS_CINEMA] + _wildcards_rental(TODAY, price='$19.99'))

    world.run()
    after = world.tracking()[WILDCARDS]
    assert (after['status'], after['digital_date'], after['_digital_date_source']) == ('available', TODAY, FIRST_OFFER)
    assert after['_jw_last_refuted'] == '2026-11-13'

    world.enrich()
    kept = world.tracking()[WILDCARDS]
    assert kept['status'] == 'available' and kept.get('_jw_revert_reason') != 'justwatch_theatrical_pvod', kept
    assert putback.last_refuted_day(kept, day(1)) == '2026-11-13'

    world.run(on_day=5)
    world.enrich(on_day=5)
    after, wall = world.tracking()[WILDCARDS], world.wall()
    assert (after['status'], after['digital_date']) == ('available', TODAY)
    assert wall[WILDCARDS]['digital_date'] == TODAY and not wall[WILDCARDS].get('hidden')


@pytest.mark.parametrize('source', [CONFIRMED, REVIEW])
def test_k_pvod_looper_without_record_dates_keeps_its_first_confirmed_date(world, source):
    """The 'keep the first confirmed date' rule end to end, with the REAL enrichment pull: Once
    Upon a Time in Harlem (real hold) comes out on day 0 as a premium rental, with no date evidence
    (TMDB: festivals + limited theatrical only; the JustWatch answer carries no record dates).
    Day 0: dated today (CONFIRMED if yesterday's check was stamped, else REVIEW). A live $19.99
    rental is out (owner, Nov 2026): enrichment keeps it. Day 1: still the day it first came out."""
    rec = real(HARLEM)
    if source == CONFIRMED:
        rec['_jw_last_checked'] = '2026-11-13'   # what v2 stamps on yesterday's failed daily check
    world.seed({HARLEM: rec})
    world.tmdb.use_real(HARLEM)
    world.jw.use_real('Once Upon a Time in Harlem')
    node = world.jw.node('Once Upon a Time in Harlem', HARLEM)
    node['offers'] += harlem_store_offers(f'{TODAY}T07:00:00Z', created=None, price='$19.99')
    world.pages.text = FakeStorePages.AVAILABLE

    world.run()
    after = world.tracking()[HARLEM]
    assert (after['status'], after['digital_date'], after['_digital_date_source']) == ('available', TODAY, source)

    world.enrich()
    kept = world.tracking()[HARLEM]
    assert kept['status'] == 'available' and kept.get('_jw_revert_reason') != 'justwatch_theatrical_pvod', \
        'a live $19.99 rental is out (owner, Nov 2026): enrichment must not pull it'

    world.run(on_day=1)
    after, wall = world.tracking()[HARLEM], world.wall()
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (TODAY, source), \
        'the PVOD looper was re-dated the day it came back instead of the day it first came out'
    assert wall[HARLEM]['digital_date'] == TODAY
    assert bool(after.get('_date_needs_review')) is (source == REVIEW)


def test_k_no_match_answer_after_a_persisted_floor_keeps_it(world):
    """A hold whose floor v2 already persisted: a later 'no match' answer (search miss, real
    capture 2026-11-14: only other films called Wildcards) changes the reason to one that proves
    nothing -- the persisted floor still holds, and the release is dated after it."""
    rec = real(WILDCARDS)
    rec['_jw_last_refuted'] = '2026-11-13'   # stamped by v2's own no-offer check on 11-13
    world.seed({WILDCARDS: rec})
    world.tmdb.release_dates[WILDCARDS] = copy.deepcopy(TMDB_RELEASE_DATES[WILDCARDS])
    world.jw.use_real('Wildcards (other films only)', as_query='Wildcards')

    world.run()
    mid_hold = world.tracking()[WILDCARDS]
    assert mid_hold['_jw_revert_reason'] == 'justwatch_no_match' and mid_hold['status'] == 'tracking'

    _wildcards_found(world, _wildcards_rental(day(1)))
    world.run(on_day=1)
    after = world.tracking()[WILDCARDS]
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (day(1), FIRST_OFFER)


def test_k_legacy_floor_survives_a_no_match_answer(world):
    """Finding 10(a) with the real 78303fd6 Wildcards record (no `_jw_last_refuted` yet): day 0
    JustWatch's search misses it (real capture: only other films called Wildcards) -> a no-match
    strike; day 1 Amazon lists it. JustWatch said "no offer" on 2026-11-13, so the put-back must
    not be dated on or before that day."""
    rec = real(WILDCARDS)
    assert putback.last_refuted_day(rec, TODAY) == '2026-11-13' and '_jw_last_refuted' not in rec
    world.seed({WILDCARDS: rec})
    world.tmdb.release_dates[WILDCARDS] = copy.deepcopy(TMDB_RELEASE_DATES[WILDCARDS])
    world.jw.use_real('Wildcards (other films only)', as_query='Wildcards')

    world.run()
    assert world.tracking()[WILDCARDS]['_jw_revert_reason'] == 'justwatch_no_match'

    _wildcards_found(world, _wildcards_rental(day(1)))
    world.run(on_day=1)
    after = world.tracking()[WILDCARDS]
    assert after['status'] == 'available'
    assert after['digital_date'] > '2026-11-13', (
        f"dated {after['digital_date']} ({after.get('_digital_date_source')}) -- on/before 2026-11-13, "
        f"a day JustWatch said 'no offer'")


def test_k_control_no_offer_answer_moves_the_floor_to_today(world):
    """Same as above, but day 0's answer is 'JustWatch has it, no offer' (its real live node):
    the floor becomes day 0, and the day-1 release is dated day 1 (TMDB's 11-09 is refuted)."""
    world.seed({WILDCARDS: real(WILDCARDS)})
    world.tmdb.release_dates[WILDCARDS] = copy.deepcopy(TMDB_RELEASE_DATES[WILDCARDS])
    world.jw.use_real('Wildcards')

    world.run()
    held = world.tracking()[WILDCARDS]
    assert (held['_jw_revert_reason'], held['_jw_last_refuted']) == ('justwatch_no_valid_offers', TODAY)

    _wildcards_found(world, _wildcards_rental(day(1)))
    world.run(on_day=1)
    after = world.tracking()[WILDCARDS]
    assert (after['status'], after['digital_date'], after['_digital_date_source']) == ('available', day(1), FIRST_OFFER)


def test_k_justwatch_error_day_never_becomes_a_refuted_day(world):
    """Rule 5 + rule 4 with the real Wildcards record: day 0 Amazon lists it (record date day 0)
    but JustWatch errors on the lookup -- nothing may be recorded against the film. Day 1 JustWatch
    answers: it came out on day 0 (its own record says so) and must be dated day 0."""
    world.seed({WILDCARDS: real(WILDCARDS)})
    world.tmdb.release_dates[WILDCARDS] = copy.deepcopy(TMDB_RELEASE_DATES[WILDCARDS])
    _wildcards_found(world, _wildcards_rental(TODAY))
    world.jw.errors['Wildcards'] = 'connection_error'

    world.run()
    held = world.tracking()[WILDCARDS]
    assert held['status'] == 'tracking' and '_jw_last_checked' not in held and '_jw_last_refuted' not in held

    world.jw.errors.clear()
    world.run(on_day=1)
    after = world.tracking()[WILDCARDS]
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (TODAY, FIRST_OFFER), (
        f"dated {after['digital_date']} ({after.get('_digital_date_source')}): the JustWatch-error day "
        f"{TODAY} was counted as a 'not out yet' day")


# ===========================================================================
# (x) enrichment's Type-4 date refresh never moves a date onto/before _jw_last_refuted
# ===========================================================================

def _enrich_fields(world, rec, type4):
    """MovieEnricher.get_enrichment_only_fields for `rec` (the real method; TMDB's Type 4 list
    answered by the fake TMDB, every other source "nothing found")."""
    mid = TRACES
    if type4:
        world.tmdb.set_dates(mid, (4, type4, ''))
    else:
        world.tmdb.release_dates[mid] = {'id': int(mid), 'results': []}
    g = world.enrichment_generator()
    g.enrichment.get_watch_links = lambda *a, **k: {}
    details = tmdb_details(mid, rec)
    return g._enricher.get_enrichment_only_fields(mid, rec, details, existing_movie={})


@pytest.mark.parametrize('type4, floor, keep', [
    pytest.param('2026-11-03', '2026-11-13', True, id='TMDB-date-before-the-floor-kept-out'),
    pytest.param('2026-11-13', '2026-11-13', True, id='TMDB-date-on-the-floor-kept-out'),
    pytest.param('2026-11-14', '2026-11-13', False, id='TMDB-date-after-the-floor-used'),
    pytest.param('2026-11-03', None, False, id='no-floor-TMDB-date-used'),
])
def test_x_type4_refresh_never_moves_a_date_onto_or_before_the_last_refuted_day(world, type4, floor, keep):
    """Round 2b (review finding: a buy-only graduation dated today was re-dated to TMDB's earlier
    buy-only date): the refresh keeps the record's date when TMDB's is on/before `_jw_last_refuted`."""
    rec = real(TRACES)
    rec.update({'status': 'available', 'digital_date': '2026-11-14'})
    if floor:
        rec['_jw_last_refuted'] = floor
    result = _enrich_fields(world, rec, type4)
    if keep:
        assert (result['digital_date'], result['_digital_date_source']) == ('2026-11-14', 'detection'), \
            f'dated {result["digital_date"]}: on/before {floor}, a day a check proved it not out yet'
    else:
        assert (result['digital_date'], result['_digital_date_source']) == (type4, 'tmdb_type4')


@pytest.mark.parametrize('source', sorted(putback.PROTECTED_SOURCES))
def test_x_type4_refresh_never_touches_a_put_back_date(world, source):
    """Put back after a hold (any put-back source): TMDB's date never replaces it, earlier or later."""
    rec = real(TRACES)
    rec.update({'status': 'available', 'digital_date': '2026-11-10', '_digital_date_source': source,
                '_jw_last_refuted': '2026-11-09'})
    for type4 in ('2026-11-01', '2026-11-12'):
        result = _enrich_fields(world, rec, type4)
        assert (result['digital_date'], result['_digital_date_source']) == ('2026-11-10', source)


# ===========================================================================
# (l) a held film with a FUTURE TMDB date is checked every run (Liberation)
# ===========================================================================

LIBERATION_AMAZON = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-liberation01'


def _liberation(world, offers):
    """Liberation (1129188, real): held 'no valid offers' since 09-15, a pending TMDB Type 4 date
    of 2026-11-17 (real) -- three days ahead. JustWatch offers SYNTHETIC (the code's own case:
    'Liberation: on Amazon while TMDB said 11-17')."""
    rec = real(LIBERATION)
    assert rec['_type4_pending'] and rec['digital_date'] == '2026-11-17' and rec['_jw_revert_count'] == 1
    world.seed({LIBERATION: rec})
    world.tmdb.set_dates(LIBERATION, (4, '2026-11-17', ''))
    world.jw.edges['Liberation'] = [jw_node(LIBERATION, 'Liberation', 2026, offers)]
    return rec


def test_l_held_film_with_future_tmdb_date_goes_on_early_when_a_rental_is_live(world):
    before = _liberation(world, [
        jw_offer('RENT', 'Amazon Video', LIBERATION_AMAZON, '$5.99', '2026-11-10T08:00:00Z', created='2026-11-10'),
        jw_offer('BUY', 'Amazon Video', LIBERATION_AMAZON, '$14.99', '2026-11-10T08:00:00Z', created='2026-11-10')])

    world.run()

    after, wall = world.tracking()[LIBERATION], world.wall()
    assert 'Liberation' in world.jw.queries, 'held film with a future TMDB date skipped JustWatch'
    assert after['status'] == 'available' and LIBERATION in wall
    assert (after['digital_date'], after['_digital_date_source']) == ('2026-11-10', FIRST_OFFER)
    assert after['_date_before_putback'] == before['digital_date']
    assert '_is_preorder' not in after and '_type4_pending' not in after
    assert not wall[LIBERATION].get('_is_preorder')


def test_l_held_film_with_future_tmdb_date_waits_on_a_preorder_listing(world):
    """JustWatch lists Amazon's pre-order (offer start = TMDB's 11-17): nothing is live -> it waits,
    keeps TMDB's date, and today is remembered as a proven "not out yet" day."""
    before = _liberation(world, [
        jw_offer('RENT', 'Amazon Video', LIBERATION_AMAZON, '$5.99', '2026-11-17T08:00:00Z', created=TODAY)])

    world.run()

    after = world.tracking()[LIBERATION]
    assert 'Liberation' in world.jw.queries
    assert after['status'] == 'tracking' and LIBERATION not in world.wall()
    assert after['digital_date'] == '2026-11-17' and after['_type4_pending'] is True
    assert (after['_jw_last_checked'], after['_jw_last_refuted']) == (TODAY, TODAY)
    assert after['_jw_revert_count'] == before['_jw_revert_count']
    assert '_put_back_on' not in after
    # Its release day: dated that day, never on the pre-order day.
    world.run(on_day=3)
    after = world.tracking()[LIBERATION]
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (day(3), EVIDENCE)
    assert day(3) == '2026-11-17'


def test_l_held_film_with_future_tmdb_date_waits_on_an_apple_store_rental(world):
    """Round 2c: Apple's store (JustWatch: 'Apple TV Store' / 'itunes') lists rentals from the
    theater opening, so an Apple rental alone does not put a held film on before TMDB's date --
    it waits for its date, as before Step 1 (2b let it on early: the skeptic's Liberation case,
    dated by the listing's record day)."""
    _liberation(world, [
        jw_offer('RENT', 'Apple TV Store', 'https://tv.apple.com/us/movie/liberation/umc.cmc.liberation2026',
                 '$5.99', '2026-11-10T08:00:00Z', created='2026-11-10')])
    world.pages.text = FakeStorePages.AVAILABLE

    world.run()

    after = world.tracking()[LIBERATION]
    assert after['status'] == 'tracking'
    assert after['digital_date'] == '2026-11-17' and after.get('_type4_pending')
    assert LIBERATION not in world.wall() or world.wall()[LIBERATION].get('hidden') or \
        world.wall()[LIBERATION].get('_is_preorder')


# ===========================================================================
# (s) expired festival screenings: returned once, dated by their regular release
# ===========================================================================

def _screenings_world(world, extra=None, wall_extra=(), archive_extra=()):
    """78303fd6: Love - Love on the wall, hidden, as an expired Heartland Film Festival screening
    (10-08..10-26); Montreal, My Beautiful already archived (OUTshine, 05-04..05-11). Both still
    'available' in tracking -- nothing re-checked them."""
    love, montreal = real(LOVE), real(MONTREAL)
    assert love['status'] == montreal['status'] == 'available'
    world.seed({LOVE: love, MONTREAL: montreal, **(extra or {})}, wall=[WALL_78303fd6[LOVE], *wall_extra],
               archive=[ARCHIVE_78303fd6[MONTREAL], *archive_extra])
    world.tmdb.set_dates(LOVE, (4, '2026-10-08', 'Heartland Film Festival'))   # real (live TMDB, Nov 2026)


def test_s_expired_screenings_are_returned_with_the_day_they_ended(world):
    _screenings_world(world)

    out = world.check_screenings()

    trk = world.tracking()
    for mid, ended in ((LOVE, '2026-10-26'), (MONTREAL, '2026-05-11')):
        rec = trk[mid]
        assert rec['status'] == 'tracking' and rec['_screening_expired'] is True, (mid, out)
        assert rec['_screening_ended'] == ended
        assert rec['_screening_returned_at'] == TODAY
        assert 'digital_date' not in rec
    assert world.wall()[LOVE].get('hidden') is True     # still off the main wall until it is out
    # Returned once: a second check changes nothing.
    world.check_screenings()
    assert world.tracking() == trk


def test_s_a_removed_title_is_never_returned_from_an_expired_screening(world):
    """Owner rule: no path brings a removed title back. Avatar (78303fd6: removed) with a stale
    screening -- one archived (the off-wall return), one still on the wall with its end date passed
    (the date-based expiry, which returns whatever tracking record it finds). Both are skipped."""
    avatar = real(AVATAR)
    vs_entry = copy.deepcopy(WALL_78303fd6[LOVE])
    vs_entry.update({'id': AVATAR, 'title': 'Avatar: Fire and Ash', 'hidden': False})
    vs_entry['virtual_screening_info'] = dict(vs_entry['virtual_screening_info'], status='active')
    _screenings_world(world, extra={AVATAR: avatar}, wall_extra=[vs_entry])

    world.check_screenings()
    assert world.tracking()[AVATAR] == avatar
    assert world.wall()[AVATAR].get('hidden') is True     # the screening itself is expired off the wall

    # The same title archived as a screening (the off-wall return path).
    world.seed({AVATAR: avatar}, archive=[dict(vs_entry, hidden=True)])
    world.check_screenings()
    assert world.tracking()[AVATAR] == avatar
    assert DataGenerator._return_screening_to_tracking(avatar, '2026-10-26') is None and avatar == real(AVATAR)


def _love_love_on_amazon(world, created):
    """SYNTHETIC: JustWatch lists the film's own (expired) Eventive page as a rental -- as it does
    for Disposable Humanity -- plus, from today, an Amazon rental (its regular release)."""
    eventive = jw_offer('RENT', 'Eventive', 'https://watch.eventive.org/heartlandfilmfestival/play/6a8caa0d26f98166f0238cae',
                        '$15.00', created='2026-10-08')
    amazon = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-lovelove0001'
    offers = [eventive]
    if created is not False:
        offers += [jw_offer('RENT', 'Amazon Video', amazon, '$4.99', f'{TODAY}T07:00:00Z', created=created),
                   jw_offer('BUY', 'Amazon Video', amazon, '$9.99', f'{TODAY}T07:00:00Z', created=created)]
    world.jw.edges['Love - Love'] = [jw_node(LOVE, 'Love - Love', 2026, offers)]


@pytest.mark.parametrize('created, expected, source, review', [
    pytest.param(TODAY, TODAY, FIRST_OFFER, False, id='regular-release-recorded-today'),
    pytest.param(None, TODAY, REVIEW, True, id='no-record-date'),
])
def test_s_returned_screening_is_dated_by_its_regular_release_not_the_festival(world, created, expected, source, review):
    """Love - Love's TMDB Type 4 date is the festival screening itself (10-08, 'Heartland Film
    Festival'); it is on or before the day the screening ended (10-26) and is ignored. Its own
    Eventive page is not a release (excluded for held films). It is dated by its regular release,
    and its wall entry loses the festival link and flags."""
    _screenings_world(world)
    world.check_screenings()
    _love_love_on_amazon(world, created)

    world.run()

    after, entry = world.tracking()[LOVE], world.wall()[LOVE]
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (expected, source)
    assert bool(after.get('_date_needs_review')) is review
    assert (after['_held_since'], after['_put_back_on']) == (TODAY, TODAY)
    assert entry['digital_date'] == expected and entry['_digital_date_source'] == source
    assert not entry.get('hidden')
    assert not (entry.get('filters') or {}).get('is_virtual_screening')
    assert 'virtual_screening_info' not in entry
    links = json.dumps(entry.get('watch_links') or {})
    assert 'eventive' not in links.lower(), f'expired festival link left on the put-back entry: {links}'


def test_s_returned_screening_only_on_its_festival_page_stays_held(world):
    """Only the stale Eventive listing: no valid offer -> held, a no-offer day recorded, checked
    again next run; the hidden entry stays hidden."""
    _screenings_world(world)
    world.check_screenings()
    _love_love_on_amazon(world, False)

    world.run()

    after = world.tracking()[LOVE]
    assert after['status'] == 'tracking' and after['_screening_expired'] is True
    assert (after['_jw_revert_reason'], after['_jw_last_refuted']) == ('justwatch_no_valid_offers', TODAY)
    assert world.wall()[LOVE].get('hidden') is True


def test_s_archived_screening_is_put_back_with_its_regular_release_date(world):
    """Montreal, My Beautiful: archived after its OUTshine screening (05-04..05-11) while tracking
    said 'available'. On Amazon since 2026-11-04 (record date SYNTHETIC, from the round-2 notes).
    Returned, then put back dated 11-04 -- a new wall entry (it was off the wall)."""
    _screenings_world(world)
    world.check_screenings()
    amazon = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-montreal0001'
    world.jw.edges['Montreal, My Beautiful'] = [jw_node(MONTREAL, 'Montreal, My Beautiful', 2026, [
        jw_offer('RENT', 'Amazon Video', amazon, '$4.99', '2026-11-04T08:00:00Z', created='2026-11-04')])]

    world.run()

    after, wall = world.tracking()[MONTREAL], world.wall()
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == ('2026-11-04', FIRST_OFFER)
    assert wall[MONTREAL]['digital_date'] == '2026-11-04' and not wall[MONTREAL].get('hidden')


# ===========================================================================
# (rm) a removed title is never checked, dated or brought back by discovery
# ===========================================================================

def test_rm_discovery_never_brings_a_removed_title_back(world):
    """Avatar and Project Hail Mary (78303fd6: removed -- by the May PVOD sweep and by hand).
    JustWatch shows both available, TMDB lists digital dates: discovery leaves them alone (never
    asked of JustWatch, never on the wall), while a held film in the same run is checked."""
    avatar, hail_mary = real(AVATAR), real(HAIL_MARY)
    world.seed({AVATAR: avatar, HAIL_MARY: hail_mary, TOX: real(TOX)})
    world.tmdb.use_real(AVATAR)
    world.tmdb.set_dates(HAIL_MARY, (3, '2026-03-20', ''), (4, '2026-05-12', ''))
    world.tmdb.use_real(TOX)
    world.jw.use_real('Avatar: Fire and Ash')
    world.jw.edges['Project Hail Mary'] = [jw_node(HAIL_MARY, 'Project Hail Mary', 2026, [
        jw_offer('FLATRATE', 'Amazon Prime Video', 'https://watch.amazon.com/detail?gti=hailmary', created='2026-06-01')])]
    world.jw.use_real('Tox')

    world.run()

    trk, wall = world.tracking(), world.wall()
    assert trk[AVATAR] == avatar and trk[HAIL_MARY] == hail_mary
    assert AVATAR not in wall and HAIL_MARY not in wall
    assert 'Avatar: Fire and Ash' not in world.jw.queries and 'Project Hail Mary' not in world.jw.queries
    assert 'Tox' in world.jw.queries


def test_rm_no_amount_of_failed_checks_removes_a_held_film(world):
    """Chunks (real: 117 'no offer' checks) and Tox (the old 4-strike ceiling): another failed
    check is one more strike, never 'removed' (the old 4-strike skip is gone; only the owner removes)."""
    world.seed({CHUNKS: real(CHUNKS), TOX: real(TOX)})
    world.tmdb.use_real(TOX)
    world.jw.edges['Chunks'] = [jw_node(CHUNKS, 'Chunks', 2026, [])]
    world.jw.use_real('Tox')

    for n in range(3):
        world.run(on_day=n)

    trk = world.tracking()
    assert (trk[CHUNKS]['status'], trk[CHUNKS]['_jw_revert_count']) == ('tracking', 117 + 3)
    assert (trk[TOX]['status'], trk[TOX]['_jw_revert_count']) == ('tracking', 4 + 3)
    for rec in trk.values():
        assert 'removed_reason' not in rec and 'removed_date' not in rec
        assert rec['_jw_last_refuted'] == day(2) and not rec.get('_skip_provider_discovery')


# ===========================================================================
# (g) backlog throttle: 25 long-held put-backs a run, returned screenings included
# ===========================================================================

def _backlog_world(world, backlog):
    for mid, rec in backlog.items():
        p = rec.get('providers') or {}
        world.tmdb.set_providers(mid, flatrate=p.get('streaming') or (), rent=p.get('rent') or (),
                                 buy=p.get('buy') or ())
        world.jw.edges.setdefault(rec['title'], []).append(jw_node(
            mid, rec['title'], rec.get('year'), [jw_offer('FLATRATE', 'Tubi TV', f'https://tubitv.com/movies/{mid}')]))


def test_g_26th_long_held_film_confirmed_in_a_run_waits_and_new_releases_go_first(world):
    """26 real legacy holds (all flagged _skip_provider_discovery) are confirmed by JustWatch in
    one run: all 26 are put back that run (owner, Nov 2026: no trickle). Two new releases go up
    normally -- and are judged BEFORE any held film (held films are sorted last), so a mid-run
    JustWatch throttle hits put-backs, not today's releases."""
    # Owner, Nov 2026: no trickle -- all 26 land the same run.
    backlog = copy.deepcopy(BACKLOG_26)
    assert len(backlog) == 26 and all(r['_skip_provider_discovery'] for r in backlog.values())
    assert len({r['digital_date'] for r in backlog.values()}) == 26
    last = min(backlog, key=lambda k: backlog[k]['digital_date'])
    new = {ACCURSED: real(ACCURSED), MASTERMIND: real(MASTERMIND)}   # no date yet
    world.seed({**backlog, **new})
    _backlog_world(world, backlog)
    # Simulated: Accursed shows up on TMDB's provider list today; Mastermind gets a Type 4 date today.
    world.tmdb.set_providers(ACCURSED, flatrate=['Hoopla', 'Plex'])
    world.jw.edges['Accursed'] = [jw_node(ACCURSED, 'Accursed', 2026, [
        jw_offer('FLATRATE', 'Hoopla', 'https://www.hoopladigital.com/movie/accursed/1671305')])]
    world.tmdb.set_dates(MASTERMIND, (4, TODAY, ''))
    world.jw.edges['Mastermind'] = [jw_node(MASTERMIND, 'Mastermind', 2026, [
        jw_offer('FLATRATE', 'Hulu', 'https://www.hulu.com/movie/mastermind-1387772')])]

    world.run()

    out = world.last_output
    first_held = out.index('— back after a hold since')
    assert out.index('Accursed now on') < first_held and out.index('Mastermind — digital release') < first_held, out[-4000:]
    assert 'queued for the next run' not in out
    after, wall = world.tracking(), world.wall()
    put_back = sorted(m for m in backlog if after[m]['status'] == 'available')
    assert len(put_back) == 26, f'{len(put_back)} of 26 long-held films put back in one run'
    for mid in new:
        assert after[mid]['status'] == 'available' and mid in wall, f'new release {mid} held back'


def test_g_returned_screenings_count_toward_the_backlog_limit(world):
    """25 legacy holds + Love - Love (a returned festival screening) confirmed in one run: all land
    that run -- no backlog limit any more (owner, Nov 2026: no trickle)."""
    backlog = dict(sorted(copy.deepcopy(BACKLOG_26).items(), key=lambda kv: kv[1]['digital_date'], reverse=True)[:25])
    _screenings_world(world)
    world.check_screenings()
    returned = world.tracking()[LOVE]
    world.seed({**backlog, LOVE: returned}, wall=[WALL_78303fd6[LOVE]])
    world.tmdb.set_dates(LOVE, (4, '2026-10-08', 'Heartland Film Festival'))
    _backlog_world(world, backlog)
    _love_love_on_amazon(world, TODAY)

    world.run()

    after = world.tracking()
    assert sum(after[m]['status'] == 'available' for m in backlog) == 25
    love = after[LOVE]   # no trickle (owner, Nov 2026): it lands the same run, dated its record day
    assert love['status'] == 'available' and love['digital_date'] == TODAY, love
    assert 'queued for the next run' not in world.last_output


def test_g_film_waiting_for_the_backlog_limit_keeps_the_day_it_came_out(world):
    """Chunks (1730028, real): in the nightly pre-order loop -- 117 no-offer checks, _jw_reverted_at
    re-set to 11-13. Day 0: it comes out (JustWatch record day 0, SYNTHETIC) but 25 long-held films
    went first -- they no longer hold it up: put back day 0, dated day 0, the day it came out."""
    backlog = dict(sorted(copy.deepcopy(BACKLOG_26).items(), key=lambda kv: kv[1]['digital_date'], reverse=True)[:25])
    chunks = real(CHUNKS)
    assert chunks['_jw_revert_count'] == 117 and chunks['_jw_reverted_at'] == '2026-11-13'
    assert putback.last_refuted_day(chunks, TODAY) == '2026-11-13'   # the estimate, capped at yesterday
    world.seed({**backlog, CHUNKS: chunks})
    _backlog_world(world, backlog)
    world.jw.edges['Chunks'] = [jw_node(CHUNKS, 'Chunks', 2026, [
        jw_offer('FLATRATE', 'Tubi TV', 'https://tubitv.com/movies/chunks-2026', created=TODAY)])]

    world.run()   # no trickle (owner, Nov 2026): it lands the day it came out
    assert 'queued for the next run' not in world.last_output
    after = world.tracking()[CHUNKS]
    assert after['status'] == 'available'
    assert after['digital_date'] == TODAY, (
        f"dated {after['digital_date']} ({after.get('_digital_date_source')}); it came out {TODAY}")


# ===========================================================================
# (h) put-back vs. the (unchanged) rent pre-order page check
# ===========================================================================

def _harlem_held_as_store_preorder(world, release_in=1):
    """Once Upon a Time in Harlem (1596300): held (JustWatch: no offer on 2026-10-30 and -31). Real
    today: JustWatch has cinema showtimes only; TMDB has festival and limited theatrical dates, no
    digital date and no providers. Simulated run 1 (day 0): JustWatch starts listing the store
    pre-order rentals (offer start in `release_in` days, recorded today) and Amazon's page reads
    "Available to pre-order". The unchanged rent pre-order check holds it -- correctly."""
    rec = real(HARLEM)
    assert (rec['_jw_revert_reason'], rec['_jw_reverted_at'], rec['_jw_revert_count']) == \
        ('justwatch_no_valid_offers', '2026-10-30', 2)
    world.seed({HARLEM: rec})
    world.tmdb.use_real(HARLEM)
    assert world.tmdb.providers[HARLEM]['results'] == {}
    world.jw.use_real('Once Upon a Time in Harlem')
    node = world.jw.node('Once Upon a Time in Harlem', HARLEM)
    node['offers'] += harlem_store_offers(f'{day(release_in)}T07:00:00Z', created=TODAY)
    world.pages.text = FakeStorePages.AMAZON_PREORDER

    world.run()

    after = world.tracking()[HARLEM]
    assert after['status'] == 'tracking' and after.get('_rent_preorder_held') == TODAY, \
        'precondition: the rent pre-order check holds it (it is not out yet)'
    assert HARLEM not in world.wall()
    return node


def _release_day(world, node, on_day):
    """Simulated release day: Amazon's offer starts that morning and its page reads normally; the
    listings keep the record date of the day they appeared (day 0)."""
    node['offers'] = [o for o in node['offers'] if o['monetizationType'] == 'CINEMA'] + \
        harlem_store_offers(f'{day(on_day)}T07:00:00Z', created=TODAY)
    world.pages.text = FakeStorePages.AVAILABLE


def test_h_film_held_as_a_store_preorder_is_not_reported_as_put_back(world):
    """v1 bug (fixed): the put-back was applied before the store-page check held the film, so the
    morning report listed a still-held film as put back. v2 applies it only at the wall move."""
    _harlem_held_as_store_preorder(world)

    after = world.tracking()[HARLEM]
    for k in ('_put_back_on', '_held_since', '_digital_date_source', '_date_needs_review'):
        assert k not in after, k
    # The hold history survives, so tomorrow's check happens and the floor is known.
    assert (after['_jw_revert_count'], after['_jw_revert_reason']) == (2, 'justwatch_no_valid_offers')
    assert after['_jw_last_refuted'] == TODAY and after['digital_date'] == '2026-10-30'
    report = world.morning_report(TODAY)
    put_back_section = report.split('Put back today', 1)[1] if 'Put back today' in report else ''
    assert 'Once Upon a Time in Harlem' not in put_back_section, (
        'morning report says a film that is still held was put back today:\n' + report
        + '\ntracking record: ' + json.dumps(after, sort_keys=True))
    assert 'Held, checked daily until they come out: 1' in report


def test_h_store_preorder_is_caught_on_release_day_although_tmdb_lists_nothing(world):
    """v1 bug (fixed): the hold history was erased on the pre-order day, so on release day the
    film (TMDB still listing nothing) was not checked. Now it is held, so it is checked every run."""
    node = _harlem_held_as_store_preorder(world)
    _release_day(world, node, on_day=1)
    asked = len(world.jw.queries)

    world.run(on_day=1)

    after = world.tracking()[HARLEM]
    assert 'Once Upon a Time in Harlem' in world.jw.queries[asked:], \
        'held (pre-order) film was not checked on its release day'
    assert after['status'] == 'available' and HARLEM in world.wall()


@pytest.mark.parametrize('release_in', [1, 0], ids=['released-next-day', 'released-same-day'])
def test_h_store_preorder_put_back_on_release_day_is_dated_release_day(world, release_in):
    """v1 bug (fixed): released, it was dated 2026-10-30 (its first no-offer day) under a protected
    source. Now: its listings were recorded on the pre-order day (a refuted day), so it is dated the
    day after that -- or, released later the same day (a second run), that day -- and the morning
    report lists it as put back, on the wall."""
    node = _harlem_held_as_store_preorder(world, release_in=release_in)
    _release_day(world, node, on_day=release_in)
    world.tmdb.set_providers(HARLEM, rent=['Amazon Video', 'Apple TV Store', 'Fandango At Home'],
                             buy=['Amazon Video'])   # TMDB catches up the same day

    world.run(on_day=release_in)

    after, wall = world.tracking()[HARLEM], world.wall()
    assert after['status'] == 'available'
    assert wall[HARLEM]['digital_date'] == after['digital_date'] == day(release_in), (
        f"release day {day(release_in)} but dated {wall[HARLEM]['digital_date']} "
        f"(source {after.get('_digital_date_source')}, last pre-order day {TODAY})")
    assert after['_digital_date_source'] == AFTER_HOLD and not after.get('_date_needs_review')
    assert '_rent_preorder_held' not in after and after['_jw_last_refuted'] == TODAY
    report = world.morning_report(day(release_in))
    assert 'Put back today' in report
    line = [ln for ln in report.splitlines() if 'Once Upon a Time in Harlem' in ln]
    assert len(line) == 1 and f'dated {day(release_in)}' in line[0] and line[0].rstrip().endswith('| wall'), report


# ===========================================================================
# (t) the theater-week guard, end to end
# ===========================================================================

APPLE_VERITY = 'https://tv.apple.com/us/movie/verity/umc.cmc.verity2026'


@pytest.mark.parametrize('variant, tmdb_down, expected, source, review', [
    # Verity's real JustWatch node + an Apple rental recorded on its 10-02 theatrical opening
    # (SYNTHETIC: the Project Hail Mary pattern; Apple's real availableFromTime is 10-02 too).
    pytest.param('plus-real-records', False, '2026-10-27', FIRST_OFFER, False, id='opening-week-listing-plus-real-records'),
    pytest.param('listing-only', False, '2026-10-27', EVIDENCE, False, id='opening-week-listing-only'),
    # TMDB down: no theatrical date, so the guard is off -- the listing dates it, flagged.
    pytest.param('listing-only', True, '2026-10-02', FIRST_OFFER, True, id='TMDB-down-guard-off-flagged'),
])
def test_t_theater_week_preorder_listing_does_not_date_the_put_back(world, variant, tmdb_down, expected,
                                                                     source, review):
    """Verity (real PVOD hold since 11-13; TMDB: theatrical 2026-10-02, digital 2026-10-27).
    A store listing recorded in its theater week, while TMDB's digital date is later, is a
    pre-order listing: it never dates the put-back."""
    rec = real(VERITY)
    world.seed({VERITY: rec})
    world.tmdb.use_real(VERITY)
    if tmdb_down:
        world.tmdb.down[VERITY] = {'release_dates'}
    world.jw.use_real('Verity')
    node = world.jw.node('Verity', VERITY)
    listing = [jw_offer('RENT', 'Apple TV Store', APPLE_VERITY, '$19.99', '2026-10-02T07:00:00Z', created='2026-10-02'),
               jw_offer('BUY', 'Apple TV Store', APPLE_VERITY, '$24.99', '2026-10-02T07:00:00Z', created='2026-10-02')]
    if variant == 'listing-only':
        node['offers'] = [o for o in node['offers'] if o['monetizationType'] == 'CINEMA'] + listing
    else:
        node['offers'] += listing

    world.run()

    after = world.tracking()[VERITY]
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (expected, source), \
        f"dated {after['digital_date']}: the opening-week pre-order listing"
    assert bool(after.get('_date_needs_review')) is review


# ===========================================================================
# (r) reissues
# ===========================================================================

@pytest.mark.parametrize('reissue', [True, False], ids=['flagged-reissue', 'not-flagged'])
def test_r_reissue_put_back_ignores_the_original_releases_justwatch_records(world, reissue):
    """Air: The Musical (273061, real record: a 2017 film intaked 2026-09-23, held as a no-match
    since). TMDB's Type 4 list trimmed to the restoration's own date (2026-09-22, '4K Restoration on
    YouTube', real; the real list also has 2017-01-24 -- that TMDB date is finding 14b, Step 2,
    deliberately unchanged). JustWatch (SYNTHETIC) still carries a 2019 Amazon listing of the
    original release. A flagged reissue ignores JustWatch records: dated by the restoration (09-22);
    unflagged, the 2019 record would date it (and send it straight to the archive)."""
    rec = real(AIR)
    if reissue:
        rec['_reissue'] = True
    world.seed({AIR: rec})
    world.tmdb.set_dates(AIR, (4, '2026-09-22', '4K Restoration on YouTube'))
    amz = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-airmusical01'
    world.jw.edges['Air: The Musical'] = [jw_node(AIR, 'Air: The Musical', 2017, [
        jw_offer('RENT', 'Amazon Video', amz, '$3.99', '2019-06-04T07:00:00Z', created='2019-06-04')])]

    world.run()

    after = world.tracking()[AIR]
    assert after['status'] == 'available'
    if reissue:
        assert (after['digital_date'], after['_digital_date_source']) == ('2026-09-22', EVIDENCE)
    else:
        assert (after['digital_date'], after['_digital_date_source']) == ('2019-06-04', FIRST_OFFER)


# ---------------------------------------------------------------------------
# Real data (see module docstring). Records: 78303fd6 movie_tracking.json / data.json /
# data_archive.json (Avatar's 2026-11-13 HEAD record separately). TMDB / JustWatch: live
# read-only responses of 2026-11-13/14, trimmed to the fields the pipeline reads.
# Built by scratchpad/round2b-holds-dates/build_data.py.
# ---------------------------------------------------------------------------
REAL_TRACKING = json.loads(r'''
{
 "1451998": {"title": "Tox", "year": 2026, "status": "tracking", "first_seen": "2026-01-21", "digital_date": "2026-01-21", "providers": {}, "intake_pass": "B", "has_providers": false, "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-08", "_skip_provider_discovery": true},
 "1690338": {"title": "Mixtape", "year": 2026, "status": "tracking", "intake_date": "2026-05-08", "digital_date": "2026-05-07", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "A", "has_providers": true, "enriched": false, "enrichment_date": null, "_discovery_source": "tmdb_type4", "_jw_revert_count": 3, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-05-10"},
 "1397375": {"title": "Life Goes This Way", "status": "tracking", "first_seen": "2025-10-24", "digital_date": "2026-07-10", "providers": {"rent": ["Google Play Movies", "YouTube"], "buy": ["Google Play Movies", "YouTube"], "streaming": []}, "discovery_pass": "B", "has_providers": true, "year": 2025, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-07-10", "_skip_provider_discovery": true},
 "1283515": {"title": "Verity", "year": 2026, "status": "tracking", "intake_date": "2026-09-30", "digital_date": "2026-10-27", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "B", "has_providers": true, "_discovery_source": "tmdb_type4", "_is_preorder": true, "enriched": false, "enrichment_date": null, "_transitioned_at": "2026-11-13", "_jw_revert_reason": "justwatch_theatrical_pvod", "_jw_reverted_at": "2026-11-13", "_jw_revert_count": 1},
 "1503762": {"title": "Sense and Sensibility", "year": 2026, "status": "tracking", "intake_date": "2026-09-22", "digital_date": "2026-11-03", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "B", "has_providers": true, "enriched": false, "enrichment_date": null, "_discovery_source": "tmdb_type4", "_transitioned_at": "2026-11-13", "_jw_revert_reason": "justwatch_theatrical_pvod", "_jw_reverted_at": "2026-11-13", "_jw_revert_count": 1},
 "1766609": {"title": "Go Deep: The DeSean Jackson Story", "year": 2026, "status": "tracking", "intake_date": "2026-09-25", "digital_date": "2026-09-24", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-09-25", "_skip_provider_discovery": true},
 "1510323": {"title": "Balearic", "year": 2025, "status": "tracking", "first_seen": "2026-01-06", "digital_date": "2026-10-28", "providers": {"rent": [], "buy": [], "streaming": ["Philo", "Fandor Amazon Channel"]}, "intake_pass": "C", "festival": "Locarno", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-28", "_skip_provider_discovery": true},
 "1439171": {"title": "Traces of Justice", "year": 2026, "status": "tracking", "intake_date": "2026-10-01", "digital_date": null, "providers": {}, "intake_pass": "B", "has_providers": false},
 "1033671": {"title": "Christmas at Mistletoe Manor", "status": "tracking", "first_seen": "2025-12-07", "digital_date": "2026-11-13", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV"]}, "discovery_pass": "B", "added_at": "2025-12-07T07:00:26.490342", "intake_run_date": "2025-12-07", "has_providers": true, "year": 2025, "_discovery_source": "provider_availability_check", "_jw_revert_count": 1, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-13"},
 "1596300": {"title": "Once Upon a Time in Harlem", "year": 2026, "status": "tracking", "first_seen": "2026-01-20", "digital_date": "2026-10-30", "providers": {"rent": [], "buy": ["Fandango At Home"], "streaming": []}, "intake_pass": "C", "festival": "Sundance", "has_providers": false, "_discovery_source": "provider_availability_check", "_jw_revert_count": 2, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-30"},
 "1671305": {"title": "Accursed", "year": 2026, "status": "tracking", "intake_date": "2026-10-01", "digital_date": null, "providers": {}, "intake_pass": "B", "has_providers": false},
 "1387772": {"title": "Mastermind", "year": 2026, "status": "tracking", "intake_date": "2026-10-01", "digital_date": null, "providers": {}, "intake_pass": "B", "has_providers": false},
 "1396875": {"title": "Wildcards", "year": 2026, "status": "tracking", "intake_date": "2026-08-27", "digital_date": "2026-11-09", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "B", "_discovery_source": "tmdb_type4", "_is_preorder": true, "_jw_revert_count": 5, "has_providers": true, "enriched": false, "enrichment_date": null, "_transitioned_at": "2026-11-13", "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-13"},
 "1025835": {"title": "Prey of Wrath", "year": 2026, "status": "tracking", "first_seen": "2026-05-02", "digital_date": "2026-05-01", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "A", "has_providers": true, "enriched": false, "enrichment_date": null, "_discovery_source": "tmdb_type4", "_jw_revert_count": 10, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-05-10", "_skip_provider_discovery": true},
 "1405007": {"title": "Lemonade Blessing", "status": "tracking", "first_seen": "2026-01-04", "digital_date": "2026-04-29", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "backfill", "has_providers": true, "year": 2025, "premiere_date": "2025-06-05", "_discovery_source": "tmdb_type4", "enriched": false, "enrichment_date": null, "_jw_revert_count": 10, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-05-10", "_skip_provider_discovery": true},
 "1746615": {"title": "Love - Love", "year": 2026, "status": "available", "intake_date": "2026-10-05", "digital_date": "2026-10-08", "providers": {"rent": ["Eventive"], "buy": [], "streaming": []}, "intake_pass": "C", "festival": "NYFF", "has_providers": true, "_discovery_source": "tmdb_type4", "_is_preorder": true, "enriched": true, "enrichment_date": "2026-10-09", "_transitioned_at": "2026-10-09"},
 "1178620": {"title": "Montreal, My Beautiful", "year": 2026, "status": "available", "first_seen": "2026-02-13", "digital_date": "2026-05-06", "providers": {"rent": ["Eventive"], "buy": [], "streaming": ["Eventive"]}, "intake_pass": "B", "has_providers": true, "_discovery_source": "provider_availability_check", "enriched": true, "enrichment_date": "2026-05-06"},
 "1129188": {"title": "Liberation", "year": 2026, "status": "tracking", "first_seen": "2026-01-21", "digital_date": "2026-11-17", "providers": {}, "intake_pass": "B", "has_providers": false, "_discovery_source": "tmdb_type4", "_type4_pending": true, "_is_preorder": true, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-09-15", "_jw_revert_count": 1},
 "273061": {"title": "Air: The Musical", "year": 2017, "status": "tracking", "intake_date": "2026-09-23", "digital_date": "2026-09-22", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-09-23", "_skip_provider_discovery": true},
 "1008633": {"title": "Brother", "status": "tracking", "first_seen": "2026-01-04", "digital_date": "2026-05-23", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV"]}, "intake_pass": "backfill", "has_providers": false, "year": 2024, "premiere_date": "2024-10-30", "_discovery_source": "provider_availability_check", "_jw_revert_count": 3, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-05-23"},
 "1730028": {"title": "Chunks", "year": 2026, "status": "tracking", "intake_date": "2026-07-13", "digital_date": "2026-07-17", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "B", "_discovery_source": "tmdb_type4", "_is_preorder": true, "enriched": false, "enrichment_date": null, "has_providers": true, "_transitioned_at": "2026-11-13", "_jw_revert_count": 117, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-13"},
 "83533": {"title": "Avatar: Fire and Ash", "status": "removed", "first_seen": "2025-12-17", "digital_date": "2026-03-31", "providers": {"rent": [], "buy": [], "streaming": []}, "discovery_pass": "B", "has_providers": true, "year": 2025, "_discovery_source": "tmdb_type4", "enriched": true, "enrichment_date": "2026-03-31", "removed_date": "2026-05-28", "removed_reason": "theatrical_pvod_audit"},
 "687163": {"title": "Project Hail Mary", "year": 2026, "status": "removed", "first_seen": "2026-03-13", "digital_date": "2026-04-06", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "B", "has_providers": true, "_discovery_source": "tmdb_type4", "enriched": true, "enrichment_date": "2026-04-09", "removed_date": "2026-04-27", "removed_reason": "manual_removal"}
}
''')

BACKLOG_26 = json.loads(r'''
{
 "1309725": {"title": "The Richest Woman in the World", "year": 2025, "status": "tracking", "first_seen": "2026-01-06", "digital_date": "2026-11-08", "providers": {"rent": [], "buy": [], "streaming": ["France Channel Amazon Channel"]}, "intake_pass": "C", "festival": "Cannes", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-08", "_skip_provider_discovery": true},
 "1303356": {"title": "L'Épreuve du feu", "premiere_date": "2025-08-13", "digital_date": "2026-11-07", "has_providers": true, "status": "tracking", "added": "2025-09-06T16:47:50.252672", "year": 2025, "_discovery_source": "provider_availability_check", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV"]}, "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-07", "_skip_provider_discovery": true},
 "1246595": {"title": "ElSett", "status": "tracking", "first_seen": "2025-12-12", "digital_date": "2026-11-06", "providers": {"rent": [], "buy": [], "streaming": ["Shahid VIP"]}, "discovery_pass": "B", "has_providers": true, "year": 2025, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-06", "_skip_provider_discovery": true},
 "1815024": {"title": "Too Much Light Makes the Baby Go Blind", "year": 2026, "status": "tracking", "intake_date": "2026-11-05", "digital_date": "2026-11-05", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-11-05", "_skip_provider_discovery": true},
 "1819415": {"title": "Taken: Natalee Holloway", "year": 2026, "status": "tracking", "intake_date": "2026-11-06", "digital_date": "2026-11-04", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-11-06", "_skip_provider_discovery": true},
 "1773378": {"title": "Who's Coming for Christmas?", "year": 2026, "status": "tracking", "intake_date": "2026-11-01", "digital_date": "2026-11-02", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV", "Philo", "Hallmark+ Amazon Channel", "Hallmark+ Apple TV channel", "Hallmark TV Amazon Channel"]}, "intake_pass": "B", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-02", "_skip_provider_discovery": true},
 "1610442": {"title": "Summer's End", "year": 2026, "status": "tracking", "intake_date": "2026-11-01", "digital_date": "2026-11-01", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-11-01", "_skip_provider_discovery": true},
 "1813076": {"title": "Anamnesis", "year": 2026, "status": "tracking", "intake_date": "2026-10-31", "digital_date": "2026-10-31", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-31", "_skip_provider_discovery": true},
 "1496903": {"title": "Exhibition on Screen: Caravaggio", "status": "tracking", "first_seen": "2025-11-11", "digital_date": "2026-10-30", "providers": {"rent": [], "buy": [], "streaming": ["Marquee TV Amazon Channel"]}, "discovery_pass": "B", "has_providers": true, "year": 2025, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-30", "_skip_provider_discovery": true},
 "1811860": {"title": "The Suicide Squad: Is It Canon? The Official Podcast", "year": 2026, "status": "tracking", "intake_date": "2026-10-30", "digital_date": "2026-10-29", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-30", "_skip_provider_discovery": true},
 "1789251": {"title": "I've Been Having Dreams", "year": 2026, "status": "tracking", "intake_date": "2026-10-23", "digital_date": "2026-10-28", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-23", "_skip_provider_discovery": true},
 "1417935": {"title": "Filipiñana", "year": 2026, "status": "tracking", "first_seen": "2026-01-20", "digital_date": "2026-10-27", "providers": {"rent": [], "buy": [], "streaming": ["Criterion Channel"]}, "intake_pass": "C", "festival": "Sundance", "has_providers": false, "enriched": false, "enrichment_date": null, "imdb_id": "tt38268539", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-28", "_skip_provider_discovery": true},
 "1773382": {"title": "Forgotten Holiday", "year": 2026, "status": "tracking", "intake_date": "2026-10-25", "digital_date": "2026-10-26", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV", "Philo", "Hallmark+ Amazon Channel", "Hallmark+ Apple TV channel", "Hallmark TV Amazon Channel"]}, "intake_pass": "B", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-26", "_skip_provider_discovery": true},
 "1257403": {"title": "Agora", "year": 2024, "status": "tracking", "first_seen": "2026-01-06", "digital_date": "2026-10-25", "providers": {"rent": ["Amazon Video"], "buy": ["Amazon Video"], "streaming": []}, "intake_pass": "C", "festival": "Locarno", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-25", "_skip_provider_discovery": true},
 "1757164": {"title": "#LetsBaRock!", "year": 2026, "status": "tracking", "intake_date": "2026-09-04", "digital_date": "2026-10-24", "providers": {"rent": [], "buy": [], "streaming": ["Marquee TV Amazon Channel"]}, "intake_pass": "B", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-24", "_skip_provider_discovery": true},
 "1410175": {"title": "Slackers", "year": 2026, "status": "tracking", "intake_date": "2026-06-18", "digital_date": "2026-10-23", "providers": {}, "intake_pass": "B", "has_providers": false, "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-24", "_skip_provider_discovery": true},
 "1337305": {"title": "Just One Before I Die", "year": 2026, "status": "tracking", "intake_date": "2026-10-22", "digital_date": "2026-10-21", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-22", "_skip_provider_discovery": true},
 "1786891": {"title": "Archives from Hell: The Making of Demo_N", "year": 2026, "status": "tracking", "intake_date": "2026-10-20", "digital_date": "2026-10-20", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-20", "_skip_provider_discovery": true},
 "1102938": {"title": "Jim's Story", "year": 2024, "status": "tracking", "first_seen": "2026-01-06", "digital_date": "2026-10-19", "providers": {"rent": [], "buy": [], "streaming": ["France Channel Amazon Channel"]}, "intake_pass": "C", "festival": "Cannes", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-19", "_skip_provider_discovery": true},
 "1772765": {"title": "'Tis the Season for Setups", "year": 2026, "status": "tracking", "intake_date": "2026-10-18", "digital_date": "2026-10-18", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV", "Philo", "Hallmark+ Amazon Channel", "Hallmark+ Apple TV channel", "Hallmark TV Amazon Channel"]}, "intake_pass": "B", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-18", "_skip_provider_discovery": true},
 "1193440": {"title": "No Way Back", "premiere_date": "2025-07-23", "digital_date": "2026-10-17", "has_providers": true, "status": "tracking", "added": "2025-09-06T16:48:05.149040", "year": 2025, "_discovery_source": "provider_availability_check", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV"]}, "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-17", "_skip_provider_discovery": true},
 "1398750": {"title": "Sea of Love", "status": "tracking", "first_seen": "2026-01-04", "digital_date": "2026-10-16", "providers": {"rent": ["Amazon Video"], "buy": ["Amazon Video"], "streaming": []}, "intake_pass": "backfill", "has_providers": true, "year": 2024, "premiere_date": "2024-08-25", "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-16", "_skip_provider_discovery": true},
 "1001434": {"title": "This Life of Mine", "year": 2024, "status": "tracking", "first_seen": "2026-01-06", "digital_date": "2026-10-15", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV"]}, "intake_pass": "C", "festival": "Cannes", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-10-15", "_skip_provider_discovery": true},
 "1636241": {"title": "Fátima - A Filipe La Féria Opera Rock", "year": 2026, "status": "tracking", "first_seen": "2026-02-16", "digital_date": "2026-10-14", "providers": {"rent": [], "buy": [], "streaming": ["fuboTV"]}, "intake_pass": "B", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-14", "_skip_provider_discovery": true},
 "1597084": {"title": "Dolioo", "year": 2026, "status": "tracking", "intake_date": "2026-10-13", "digital_date": "2026-10-13", "providers": {}, "intake_pass": "A", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-13", "_skip_provider_discovery": true},
 "1790062": {"title": "Center Stage for Murder", "year": 2026, "status": "tracking", "intake_date": "2026-10-09", "digital_date": "2026-10-12", "providers": {"rent": [], "buy": [], "streaming": ["Philo"]}, "intake_pass": "B", "has_providers": true, "_discovery_source": "provider_availability_check", "_jw_revert_count": 4, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-10-12", "_skip_provider_discovery": true}
}
''')

TMDB_RELEASE_DATES = json.loads(r'''
{
 "1451998": {"id": 1451998, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 4, "release_date": "2026-01-21T00:00:00.000Z", "note": ""}]}]},
 "1690338": {"id": 1690338, "results": []},
 "1397375": {"id": 1397375, "results": []},
 "1283515": {"id": 1283515, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 1, "release_date": "2026-09-29T00:00:00.000Z", "note": "AMC Lincoln Square 13 (New York City, New York)"}, {"type": 3, "release_date": "2026-10-02T00:00:00.000Z", "note": ""}, {"type": 4, "release_date": "2026-10-27T00:00:00.000Z", "note": ""}]}]},
 "1503762": {"id": 1503762, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 1, "release_date": "2026-10-10T00:00:00.000Z", "note": "FocusFest "}, {"type": 1, "release_date": "2026-10-07T00:00:00.000Z", "note": "United Artists Theatre (Los Angeles, California)"}, {"type": 1, "release_date": "2026-10-29T00:00:00.000Z", "note": "SCAD Savannah Film Festival "}, {"type": 3, "release_date": "2026-10-16T00:00:00.000Z", "note": ""}, {"type": 4, "release_date": "2026-11-03T00:00:00.000Z", "note": ""}, {"type": 5, "release_date": "2026-12-15T00:00:00.000Z", "note": "4K Ultra HD / Blu-ray / DVD"}]}]},
 "83533": {"id": 83533, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 1, "release_date": "2025-12-01T00:00:00.000Z", "note": "Dolby Theatre, Hollywood"}, {"type": 3, "release_date": "2025-12-19T00:00:00.000Z", "note": ""}, {"type": 4, "release_date": "2026-03-31T00:00:00.000Z", "note": ""}, {"type": 4, "release_date": "2026-06-24T00:00:00.000Z", "note": "Disney+"}, {"type": 5, "release_date": "2026-05-19T00:00:00.000Z", "note": "4K Ultra HD / 3D Blu-ray / Blu-ray / DVD"}]}]},
 "1766609": {"id": 1766609, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 4, "release_date": "2026-09-24T00:00:00.000Z", "note": "Prime Video"}]}]},
 "1510323": {"id": 1510323, "results": []},
 "1439171": {"id": 1439171, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 2, "release_date": "2026-11-13T00:00:00.000Z", "note": ""}]}]},
 "1033671": {"id": 1033671, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 6, "release_date": "2025-12-07T00:00:00.000Z", "note": "Great American Family"}]}]},
 "1596300": {"id": 1596300, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 1, "release_date": "2026-01-25T00:00:00.000Z", "note": "Sundance Film Festival"}, {"type": 1, "release_date": "2026-09-29T00:00:00.000Z", "note": "New York Film Festival"}, {"type": 1, "release_date": "2026-09-05T00:00:00.000Z", "note": "Telluride Film Festival"}, {"type": 1, "release_date": "2026-09-18T00:00:00.000Z", "note": "Camden International Film Festival"}, {"type": 1, "release_date": "2026-09-22T00:00:00.000Z", "note": "Charlotte Film Festival"}, {"type": 1, "release_date": "2026-10-06T00:00:00.000Z", "note": "Mill Valley Film Festival"}, {"type": 1, "release_date": "2026-10-11T00:00:00.000Z", "note": "Hamptons International Film Festival / Heartland Film Festival"}, {"type": 1, "release_date": "2026-10-15T00:00:00.000Z", "note": "Woodstock Film Festival / New Hampshire Film Festival"}, {"type": 1, "release_date": "2026-10-20T00:00:00.000Z", "note": "Chicago International Film Festival / Vermont International Film Festival"}, {"type": 1, "release_date": "2026-10-17T00:00:00.000Z", "note": "Newport Beach Film Festival / Montclair Film Festival / Philadelphia Film Festival"}, {"type": 1, "release_date": "2026-10-14T00:00:00.000Z", "note": "Orcas Island Film Festival / Santa Fe International Film Festival"}, {"type": 1, "release_date": "2026-10-25T00:00:00.000Z", "note": "Hawai'i International Film Festival / Virginia Film Festival"}, {"type": 1, "release_date": "2026-09-25T00:00:00.000Z", "note": "Dialogues Documentary Festival"}, {"type": 1, "release_date": "2026-10-09T00:00:00.000Z", "note": "IFFBoston Fall Focus"}, {"type": 1, "release_date": "2026-10-23T00:00:00.000Z", "note": "Refocus Film Festival"}, {"type": 1, "release_date": "2026-11-07T00:00:00.000Z", "note": "Indie Memphis Film Festival"}, {"type": 1, "release_date": "2026-10-16T00:00:00.000Z", "note": "Middleburg Film Festival"}, {"type": 1, "release_date": "2026-10-27T00:00:00.000Z", "note": "SCAD Savannah Film Festival"}, {"type": 1, "release_date": "2026-10-31T00:00:00.000Z", "note": "Denver Film Festival"}, {"type": 1, "release_date": "2026-10-12T00:00:00.000Z", "note": "Buffalo International Film Festival / Hot Springs Documentary Film Festival"}, {"type": 1, "release_date": "2026-10-08T00:00:00.000Z", "note": "Houston Cinema Arts Festival"}, {"type": 1, "release_date": "2026-11-01T00:00:00.000Z", "note": "Lincoln Center, New York"}, {"type": 2, "release_date": "2026-10-16T00:00:00.000Z", "note": ""}]}]},
 "1396875": {"id": 1396875, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 2, "release_date": "2026-08-27T00:00:00.000Z", "note": ""}, {"type": 4, "release_date": "2026-11-09T00:00:00.000Z", "note": ""}]}]}
}
''')

TMDB_PROVIDERS = json.loads(r'''
{
 "1451998": {"id": 1451998, "results": {}},
 "1690338": {"id": 1690338, "results": {}},
 "1397375": {"id": 1397375, "results": {"US": {"rent": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 3, "provider_name": "Google Play Movies"}, {"provider_id": 192, "provider_name": "YouTube"}, {"provider_id": 7, "provider_name": "Fandango At Home"}], "buy": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 3, "provider_name": "Google Play Movies"}, {"provider_id": 192, "provider_name": "YouTube"}, {"provider_id": 7, "provider_name": "Fandango At Home"}]}}},
 "1283515": {"id": 1283515, "results": {"US": {"rent": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 7, "provider_name": "Fandango At Home"}], "buy": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 7, "provider_name": "Fandango At Home"}]}}},
 "1503762": {"id": 1503762, "results": {"US": {"rent": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 3, "provider_name": "Google Play Movies"}, {"provider_id": 192, "provider_name": "YouTube"}, {"provider_id": 7, "provider_name": "Fandango At Home"}], "buy": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 3, "provider_name": "Google Play Movies"}, {"provider_id": 192, "provider_name": "YouTube"}, {"provider_id": 7, "provider_name": "Fandango At Home"}]}}},
 "83533": {"id": 83533, "results": {"US": {"flatrate": [{"provider_id": 337, "provider_name": "Disney Plus"}], "rent": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 7, "provider_name": "Fandango At Home"}], "buy": [{"provider_id": 10, "provider_name": "Amazon Video"}, {"provider_id": 2, "provider_name": "Apple TV Store"}, {"provider_id": 3, "provider_name": "Google Play Movies"}, {"provider_id": 192, "provider_name": "YouTube"}, {"provider_id": 7, "provider_name": "Fandango At Home"}]}}},
 "1766609": {"id": 1766609, "results": {"US": {"flatrate": [{"provider_id": 9, "provider_name": "Amazon Prime Video"}, {"provider_id": 2100, "provider_name": "Amazon Prime Video with Ads"}]}}},
 "1510323": {"id": 1510323, "results": {"US": {"flatrate": [{"provider_id": 2383, "provider_name": "Philo"}, {"provider_id": 25, "provider_name": "Fandor"}, {"provider_id": 199, "provider_name": "Fandor Amazon Channel"}]}}},
 "1439171": {"id": 1439171, "results": {}},
 "1033671": {"id": 1033671, "results": {"US": {"flatrate": [{"provider_id": 257, "provider_name": "fuboTV"}]}}},
 "1596300": {"id": 1596300, "results": {}}
}
''')

JW_SEARCH = json.loads(r'''
{
 "Tox": [{"id": "tm1919060", "objectId": 1919060, "objectType": "MOVIE", "content": {"title": "Tox", "originalReleaseYear": 2026, "fullPath": "/us/movie/tox", "externalIds": {"tmdbId": "1451998"}, "credits": [{"role": "DIRECTOR", "name": "Kerri Lynn Miller"}]}, "offers": []}, {"id": "tm1483708", "objectId": 1483708, "objectType": "MOVIE", "content": {"title": "Toxic", "originalReleaseYear": 2026, "fullPath": "/us/movie/toxic-2026", "externalIds": {"tmdbId": "1213243"}, "credits": []}, "offers": []}, {"id": "tm178633", "objectId": 178633, "objectType": "MOVIE", "content": {"title": "The Toxic Avenger", "originalReleaseYear": 1984, "fullPath": "/us/movie/atomic-hero", "externalIds": {"tmdbId": "15239"}, "credits": []}, "offers": []}],
 "Mixtape": [{"id": "tm166973", "objectId": 166973, "objectType": "MOVIE", "content": {"title": "Mixtape", "originalReleaseYear": 2021, "fullPath": "/us/movie/mixtape-2021", "externalIds": {"tmdbId": "32471"}, "credits": []}, "offers": []}, {"id": "tm1276452", "objectId": 1276452, "objectType": "MOVIE", "content": {"title": "Mixtape", "originalReleaseYear": 2023, "fullPath": "/us/movie/mixtape-2023", "externalIds": {"tmdbId": "1151002"}, "credits": []}, "offers": []}, {"id": "tm2953206", "objectId": 2953206, "objectType": "MOVIE", "content": {"title": "V/H/S/Mixtape", "originalReleaseYear": 2026, "fullPath": "/us/movie/v-h-s-mixtape", "externalIds": {"tmdbId": "1742441"}, "credits": []}, "offers": []}],
 "Balearic": [{"id": "tm1658403", "objectId": 1658403, "objectType": "MOVIE", "content": {"title": "Balearic", "originalReleaseYear": 2025, "fullPath": "/us/movie/balearic", "externalIds": {"tmdbId": "1510323"}, "credits": [{"role": "DIRECTOR", "name": "Ion De Sosa"}]}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.philo.com/player/show/U2hvdzo2MDg1NDg4OTk2NDg1NTY1MjU", "availableFromTime": "2026-10-27T16:00:00Z", "package": {"clearName": "Philo", "technicalName": "philo"}}, {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.fandor.com/details/6aa275235559a86eb127270e/balearic", "availableFromTime": null, "package": {"clearName": "Fandor", "technicalName": "fandor"}}, {"monetizationType": "FLATRATE", "presentationType": "_4K", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.ca19faba-5544-4b80-9366-efb0106ac9b2", "availableFromTime": "2026-10-27T04:00:00Z", "package": {"clearName": "Fandor Amazon Channel", "technicalName": "amazonfandor"}}, {"monetizationType": "BUY", "presentationType": "BLURAY", "retailPrice": "$15.62", "currency": "USD", "standardWebURL": "https://www.amazon.com/dp/B0GQNRYVP7", "availableFromTime": null, "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}]}],
 "Go Deep: The DeSean Jackson Story": [{"id": "tm1904403", "objectId": 1904403, "objectType": "MOVIE", "content": {"title": "Go Deep: The DeSean Jackson Story", "originalReleaseYear": 2026, "fullPath": "/us/movie/go-deep-the-desean-jackson-story", "externalIds": {"tmdbId": "1766609"}, "credits": [{"role": "DIRECTOR", "name": "Mandon Lovett"}]}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.68de5283-35eb-4221-a920-a306e4734aaa", "availableFromTime": "2026-09-24T07:00:00Z", "package": {"clearName": "Amazon Prime Video", "technicalName": "amazonprime"}}, {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.68de5283-35eb-4221-a920-a306e4734aaa", "availableFromTime": "2026-09-24T07:00:00Z", "package": {"clearName": "Amazon Prime Video with Ads", "technicalName": "amazonprimevideowithads"}}]}, {"id": "tm1270930", "objectId": 1270930, "objectType": "MOVIE", "content": {"title": "Remember Me: The Mahalia Jackson Story", "originalReleaseYear": 2022, "fullPath": "/us/movie/remember-me-the-mahalia-jackson-story", "externalIds": {"tmdbId": "869565"}, "credits": []}, "offers": []}, {"id": "tm150838", "objectId": 150838, "objectType": "MOVIE", "content": {"title": "The Michael Jackson Story", "originalReleaseYear": 2009, "fullPath": "/us/movie/the-michael-jackson-story", "externalIds": {"tmdbId": "23756"}, "credits": []}, "offers": []}],
 "Christmas at Mistletoe Manor": [{"id": "tm1919365", "objectId": 1919365, "objectType": "MOVIE", "content": {"title": "Christmas at Mistletoe Manor", "originalReleaseYear": 2025, "fullPath": "/us/movie/christmas-at-mistletoe-manor", "externalIds": {"tmdbId": "1033671"}, "credits": [{"role": "DIRECTOR", "name": "Shari Hamrick Grewal"}]}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.fubo.tv/welcome/program/MV027334960000", "availableFromTime": "2026-11-12T17:00:00Z", "package": {"clearName": "fuboTV", "technicalName": "fubotv"}}]}, {"id": "tm2890747", "objectId": 2890747, "objectType": "MOVIE", "content": {"title": "Christmas at the Kringles", "originalReleaseYear": 2026, "fullPath": "/us/movie/christmas-at-the-kringles-2026", "externalIds": {"tmdbId": "939541"}, "credits": []}, "offers": []}, {"id": "tm433971", "objectId": 433971, "objectType": "MOVIE", "content": {"title": "Christmas at Pemberley Manor", "originalReleaseYear": 2018, "fullPath": "/us/movie/christmas-at-pemberley-manor", "externalIds": {"tmdbId": "549301"}, "credits": []}, "offers": []}],
 "Traces of Justice": [{"id": "tm2991662", "objectId": 2991662, "objectType": "MOVIE", "content": {"title": "Traces of Justice", "originalReleaseYear": 2026, "fullPath": "/us/movie/shen-tan-zhi-hen-ji", "externalIds": {"tmdbId": "1439171"}, "credits": [{"role": "DIRECTOR", "name": "Chen Sicheng"}]}, "offers": [{"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "currency": "USD", "standardWebURL": "http://www.cinemark.com/movies/traces-of-justice-mandarin-with-chinese-and-english-subtitles", "availableFromTime": null, "package": {"clearName": "Cinemark", "technicalName": "cinemark"}}]}, {"id": "tm850154", "objectId": 850154, "objectType": "MOVIE", "content": {"title": "Riders of Justice", "originalReleaseYear": 2020, "fullPath": "/us/movie/riders-of-justice", "externalIds": {"tmdbId": "663870"}, "credits": []}, "offers": []}, {"id": "tm1881", "objectId": 1881, "objectType": "MOVIE", "content": {"title": "Batman v Superman: Dawn of Justice", "originalReleaseYear": 2016, "fullPath": "/us/movie/batman-v-superman-dawn-of-justice", "externalIds": {"tmdbId": "209112"}, "credits": []}, "offers": []}],
 "Oppenheimer": [{"id": "tm1111989", "objectId": 1111989, "objectType": "MOVIE", "content": {"title": "Oppenheimer", "originalReleaseYear": 2023, "fullPath": "/us/movie/oppenheimer", "externalIds": {"tmdbId": "872585"}, "credits": [{"role": "DIRECTOR", "name": "Christopher Nolan"}]}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.peacocktv.com/watch/asset/movies/oppenheimer/602fd345-3ad6-33fd-a70d-a0e059b8d38a", "availableFromTime": "2026-08-16T10:00:00Z", "package": {"clearName": "Peacock Premium", "technicalName": "peacocktv"}}, {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://tv.youtube.com/browse/UCboqvWjW9JKlu2d2LiB0YHg", "availableFromTime": null, "package": {"clearName": "YouTube TV", "technicalName": "youtubetv"}}]}],
 "Barbie": [{"id": "tm244331", "objectId": 244331, "objectType": "MOVIE", "content": {"title": "Barbie", "originalReleaseYear": 2023, "fullPath": "/us/movie/barbie-2023", "externalIds": {"tmdbId": "346698"}, "credits": [{"role": "DIRECTOR", "name": "Greta Gerwig"}]}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.5750ee96-eb59-40c3-bda6-96904811a3a2", "availableFromTime": "2026-08-29T23:00:00Z", "package": {"clearName": "HBO Max Amazon Channel", "technicalName": "amazonhbomax"}}, {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.tntdrama.com/movies/barbie-theatrical", "availableFromTime": null, "package": {"clearName": "TNT", "technicalName": "tnt"}}]}],
 "Dune: Part Two": [{"id": "tm1133934", "objectId": 1133934, "objectType": "MOVIE", "content": {"title": "Dune: Part Two", "originalReleaseYear": 2024, "fullPath": "/us/movie/dune-part-two-2023", "externalIds": {"tmdbId": "693134"}, "credits": [{"role": "DIRECTOR", "name": "Denis Villeneuve"}]}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.9392c069-96f9-421b-ac7a-275308e1327a", "availableFromTime": "2024-05-21T07:01:00Z", "package": {"clearName": "HBO Max Amazon Channel", "technicalName": "amazonhbomax"}}, {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://tv.youtube.com/browse/UCaA-mkSqDa03ajlTEJzHa5w", "availableFromTime": null, "package": {"clearName": "YouTube TV", "technicalName": "youtubetv"}}]}],
 "Verity": [{"id": "tm1562625", "objectId": 1562625, "objectType": "MOVIE", "content": {"title": "Verity", "originalReleaseYear": 2026, "fullPath": "/us/movie/verity", "externalIds": {"tmdbId": "1283515"}, "credits": []}, "offers": [{"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.atomtickets.com/movies/verity/380866", "availableFromTime": null, "dateCreated": "2026-09-29", "package": {"clearName": "Atom Tickets", "technicalName": "atomtickets"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "http://www.cinemark.com/movies/verity", "availableFromTime": null, "dateCreated": "2026-09-04", "package": {"clearName": "Cinemark", "technicalName": "cinemark"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.cinepolisusa.com/movie/verity", "availableFromTime": null, "dateCreated": "2026-09-05", "package": {"clearName": "Cinepolis Cinemas", "technicalName": "cinepoliscinema"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.regmovies.com/movies/verity-ho00018457", "availableFromTime": null, "dateCreated": "2026-11-12", "package": {"clearName": "Regal Cinemas", "technicalName": "regalcinemas"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.bbtheatres.com/showtimes/1000015739-verity", "availableFromTime": null, "dateCreated": "2026-09-01", "package": {"clearName": "B&B Theatres", "technicalName": "bbtheatres"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.marcustheatres.com/movies/verity-HO00007803", "availableFromTime": null, "dateCreated": "2026-07-21", "package": {"clearName": "Marcus Theatres", "technicalName": "marcustheatres"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.746c6f90-08b9-4af4-a7b2-5472064b00d2", "availableFromTime": "2026-10-27T04:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.746c6f90-08b9-4af4-a7b2-5472064b00d2", "availableFromTime": "2026-10-27T04:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.746c6f90-08b9-4af4-a7b2-5472064b00d2", "availableFromTime": "2026-10-27T04:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/verity/umc.cmc.x0464dtyg3c7i761fobbe4sc?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6808034868", "availableFromTime": "2026-10-02T07:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/verity/umc.cmc.x0464dtyg3c7i761fobbe4sc?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6808034868", "availableFromTime": "2026-10-02T07:00:00Z", "dateCreated": "2026-11-12", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/verity/umc.cmc.x0464dtyg3c7i761fobbe4sc?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6808034868", "availableFromTime": "2026-10-02T07:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Verity/5209189", "availableFromTime": null, "dateCreated": "2026-10-27", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Verity/5209189", "availableFromTime": null, "dateCreated": "2026-10-27", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Verity/5209189", "availableFromTime": null, "dateCreated": "2026-10-27", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$24.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.746c6f90-08b9-4af4-a7b2-5472064b00d2", "availableFromTime": "2026-10-27T04:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.746c6f90-08b9-4af4-a7b2-5472064b00d2", "availableFromTime": "2026-10-27T04:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$24.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.746c6f90-08b9-4af4-a7b2-5472064b00d2", "availableFromTime": "2026-10-27T04:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "standardWebURL": "https://tv.apple.com/us/movie/verity/umc.cmc.x0464dtyg3c7i761fobbe4sc?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6808034868", "availableFromTime": "2026-10-02T07:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$24.99", "standardWebURL": "https://tv.apple.com/us/movie/verity/umc.cmc.x0464dtyg3c7i761fobbe4sc?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6808034868", "availableFromTime": "2026-10-02T07:00:00Z", "dateCreated": "2026-11-12", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$24.99", "standardWebURL": "https://tv.apple.com/us/movie/verity/umc.cmc.x0464dtyg3c7i761fobbe4sc?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6808034868", "availableFromTime": "2026-10-02T07:00:00Z", "dateCreated": "2026-10-27", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$24.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Verity/5209189", "availableFromTime": null, "dateCreated": "2000-07-14", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Verity/5209189", "availableFromTime": null, "dateCreated": "2000-07-14", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$24.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Verity/5209189", "availableFromTime": null, "dateCreated": "2000-07-14", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "DVD", "retailPrice": "$25.99", "standardWebURL": "https://www.amazon.com/dp/B0HK233ZVT?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "dateCreated": "2026-10-08", "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}, {"monetizationType": "BUY", "presentationType": "BLURAY", "retailPrice": "$31.99", "standardWebURL": "https://www.amazon.com/dp/B0HK2L9H9W?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "dateCreated": "2026-10-08", "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}]}, {"id": "tm170337", "objectId": 170337, "objectType": "MOVIE", "content": {"title": "Verity's Summer", "originalReleaseYear": 2013, "fullPath": "/us/movie/veritys-summer", "externalIds": {"tmdbId": "175014"}, "credits": []}, "offers": []}, {"id": "tm1320087", "objectId": 1320087, "objectType": "MOVIE", "content": {"title": "The Secret Kingdom", "originalReleaseYear": 2023, "fullPath": "/us/movie/the-secret-kingdom-2024", "externalIds": {"tmdbId": "893345"}, "credits": []}, "offers": []}],
 "Sense and Sensibility": [{"id": "tm1918108", "objectId": 1918108, "objectType": "MOVIE", "content": {"title": "Sense and Sensibility", "originalReleaseYear": 2026, "fullPath": "/us/movie/sense-and-sensibility-2026", "externalIds": {"tmdbId": "1503762"}, "credits": []}, "offers": [{"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.atomtickets.com/movies/sense-and-sensibility-2026/395156", "availableFromTime": null, "dateCreated": "2026-09-29", "package": {"clearName": "Atom Tickets", "technicalName": "atomtickets"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "http://www.cinemark.com/movies/sense-and-sensibility", "availableFromTime": null, "dateCreated": "2026-09-29", "package": {"clearName": "Cinemark", "technicalName": "cinemark"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.cinepolisusa.com/movie/sense-and-sensibility", "availableFromTime": null, "dateCreated": "2026-09-30", "package": {"clearName": "Cinepolis Cinemas", "technicalName": "cinepoliscinema"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.regmovies.com/movies/sense-and-sensibility-ho00021990", "availableFromTime": null, "dateCreated": "2026-11-12", "package": {"clearName": "Regal Cinemas", "technicalName": "regalcinemas"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.harkins.com/movies/sense-and-sensibility", "availableFromTime": null, "dateCreated": "2026-09-29", "package": {"clearName": "Harkins Theatres", "technicalName": "harkinstheaters"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.marcustheatres.com/movies/sense-and-sensibility-HO00007823", "availableFromTime": null, "dateCreated": "2026-07-21", "package": {"clearName": "Marcus Theatres", "technicalName": "marcustheatres"}}, {"monetizationType": "BUY", "presentationType": "DVD", "retailPrice": "$17.95", "standardWebURL": "https://www.amazon.com/dp/B0HKMFS3VK?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "dateCreated": "2026-11-06", "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884", "availableFromTime": "2026-10-16T07:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884", "availableFromTime": "2026-10-16T07:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884", "availableFromTime": "2026-10-16T07:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "dateCreated": "2026-11-03", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "dateCreated": "2026-11-03", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "dateCreated": "2026-11-03", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "BLURAY", "retailPrice": "$22.95", "standardWebURL": "https://www.amazon.com/dp/B0HKMP275J?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "dateCreated": "2026-11-06", "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$24.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$24.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$24.99", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884", "availableFromTime": "2026-10-16T07:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884", "availableFromTime": "2026-10-16T07:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$24.99", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884", "availableFromTime": "2026-10-16T07:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$24.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "dateCreated": "2026-11-03", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "dateCreated": "2026-11-03", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$24.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "dateCreated": "2026-11-03", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}]}, {"id": "tm15925", "objectId": 15925, "objectType": "MOVIE", "content": {"title": "Sense and Sensibility", "originalReleaseYear": 1995, "fullPath": "/us/movie/sense-and-sensibility", "externalIds": {"tmdbId": "4584"}, "credits": []}, "offers": []}, {"id": "tm1440625", "objectId": 1440625, "objectType": "MOVIE", "content": {"title": "Sense and Sensibility", "originalReleaseYear": 2024, "fullPath": "/us/movie/sense-and-sensibility-2024", "externalIds": {"tmdbId": "1221680"}, "credits": []}, "offers": []}],
 "Avatar: Fire and Ash": [{"id": "tm358", "objectId": 358, "objectType": "MOVIE", "content": {"title": "Avatar: Fire and Ash", "originalReleaseYear": 2025, "fullPath": "/us/movie/avatar-3", "externalIds": {"tmdbId": "83533"}, "credits": []}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "standardWebURL": "https://www.disneyplus.com/browse/entity-3135b0cb-a002-438d-a9fd-60d86284c93f", "availableFromTime": "2026-06-24T07:00:00Z", "dateCreated": "2026-06-24", "package": {"clearName": "Disney Plus", "technicalName": "disneyplus"}}, {"monetizationType": "FLATRATE", "presentationType": "_4K", "retailPrice": null, "standardWebURL": "https://www.disneyplus.com/browse/entity-3135b0cb-a002-438d-a9fd-60d86284c93f", "availableFromTime": "2026-06-24T07:00:00Z", "dateCreated": "2026-06-24", "package": {"clearName": "Disney Plus", "technicalName": "disneyplus"}}, {"monetizationType": "FLATRATE", "presentationType": "SD", "retailPrice": null, "standardWebURL": "https://www.disneyplus.com/browse/entity-3135b0cb-a002-438d-a9fd-60d86284c93f", "availableFromTime": "2026-06-24T07:00:00Z", "dateCreated": "2026-06-24", "package": {"clearName": "Disney Plus", "technicalName": "disneyplus"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.fandango.com/avatar-fire-and-ash-2025-241479/movie-overview", "availableFromTime": null, "dateCreated": "2025-12-14", "package": {"clearName": "Fandango", "technicalName": "fandango"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$3.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.1485dfef-7a6e-413e-a1a6-e20beafae3e8", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$3.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.1485dfef-7a6e-413e-a1a6-e20beafae3e8", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$3.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.1485dfef-7a6e-413e-a1a6-e20beafae3e8", "availableFromTime": "2026-11-03T05:00:00Z", "dateCreated": "2026-11-03", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$3.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Avatar-Fire-and-Ash/4729491", "availableFromTime": null, "dateCreated": "2026-07-09", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$3.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Avatar-Fire-and-Ash/4729491", "availableFromTime": null, "dateCreated": "2026-07-09", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$3.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Avatar-Fire-and-Ash/4729491", "availableFromTime": null, "dateCreated": "2026-07-09", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$5.99", "standardWebURL": "https://tv.apple.com/us/movie/avatar-fire-and-ash/umc.cmc.35prcxyp27datpeaiernpez2x?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A1885912118", "availableFromTime": "2025-12-19T08:00:00Z", "dateCreated": "2026-07-07", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "_4K", "retailPrice": "$5.99", "standardWebURL": "https://tv.apple.com/us/movie/avatar-fire-and-ash/umc.cmc.35prcxyp27datpeaiernpez2x?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A1885912118", "availableFromTime": "2025-12-19T08:00:00Z", "dateCreated": "2026-07-07", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$5.99", "standardWebURL": "https://tv.apple.com/us/movie/avatar-fire-and-ash/umc.cmc.35prcxyp27datpeaiernpez2x?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A1885912118", "availableFromTime": "2025-12-19T08:00:00Z", "dateCreated": "2026-07-07", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$9.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.1485dfef-7a6e-413e-a1a6-e20beafae3e8", "availableFromTime": "2026-09-30T04:01:00Z", "dateCreated": "2026-09-30", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$9.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.1485dfef-7a6e-413e-a1a6-e20beafae3e8", "availableFromTime": "2026-09-30T04:01:00Z", "dateCreated": "2026-09-30", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$9.99", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.1485dfef-7a6e-413e-a1a6-e20beafae3e8", "availableFromTime": "2026-09-30T04:01:00Z", "dateCreated": "2026-09-30", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}, {"monetizationType": "BUY", "presentationType": "DVD", "retailPrice": "$19.96", "standardWebURL": "https://www.amazon.com/dp/B0GVBB59VX?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "dateCreated": "2026-04-10", "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/avatar-fire-and-ash/umc.cmc.35prcxyp27datpeaiernpez2x?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A1885912118", "availableFromTime": "2025-12-19T08:00:00Z", "dateCreated": "2026-03-31", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/avatar-fire-and-ash/umc.cmc.35prcxyp27datpeaiernpez2x?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A1885912118", "availableFromTime": "2025-12-19T08:00:00Z", "dateCreated": "2026-03-31", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://tv.apple.com/us/movie/avatar-fire-and-ash/umc.cmc.35prcxyp27datpeaiernpez2x?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A1885912118", "availableFromTime": "2025-12-19T08:00:00Z", "dateCreated": "2026-03-31", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}}, {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Avatar-Fire-and-Ash/4729491", "availableFromTime": null, "dateCreated": "2000-07-14", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "_4K", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Avatar-Fire-and-Ash/4729491", "availableFromTime": null, "dateCreated": "2000-07-14", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$19.99", "standardWebURL": "https://athome.fandango.com/content/browse/details/Avatar-Fire-and-Ash/4729491", "availableFromTime": null, "dateCreated": "2000-07-14", "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}, {"monetizationType": "BUY", "presentationType": "BLURAY_4K", "retailPrice": "$24.99", "standardWebURL": "https://www.amazon.com/dp/B0GVB75HNC?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "dateCreated": "2026-06-04", "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}, {"monetizationType": "BUY", "presentationType": "DVD", "retailPrice": "$27.79", "standardWebURL": "https://www.barnesandnoble.com/w/dvd-avatar-fire-and-ash-james-cameron/1149781459", "availableFromTime": null, "dateCreated": "2026-10-20", "package": {"clearName": "Barnes & Noble", "technicalName": "barnesandnoble"}}, {"monetizationType": "BUY", "presentationType": "BLURAY", "retailPrice": "$41.79", "standardWebURL": "https://www.amazon.com/dp/B0GVB7TPVJ?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "dateCreated": "2026-04-10", "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}}]}, {"id": "tm59118", "objectId": 59118, "objectType": "MOVIE", "content": {"title": "Fire and Ice", "originalReleaseYear": 1983, "fullPath": "/us/movie/fire-and-ice", "externalIds": {"tmdbId": "15035"}, "credits": []}, "offers": []}, {"id": "tm1282106", "objectId": 1282106, "objectType": "MOVIE", "content": {"title": "Avatar Aang: The Last Airbender", "originalReleaseYear": 2026, "fullPath": "/us/movie/aang-the-last-airbender-2026", "externalIds": {"tmdbId": "980431"}, "credits": []}, "offers": []}],
 "Once Upon a Time in Harlem": [{"id": "tm1931207", "objectId": 1931207, "objectType": "MOVIE", "content": {"title": "Once Upon a Time in Harlem", "originalReleaseYear": 2026, "fullPath": "/us/movie/once-upon-a-time-in-harlem", "externalIds": {"tmdbId": "1596300"}, "credits": []}, "offers": [{"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.atomtickets.com/movies/once-upon-a-time-in-harlem/408240", "availableFromTime": null, "dateCreated": "2000-07-14", "package": {"clearName": "Atom Tickets", "technicalName": "atomtickets"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "http://www.cinemark.com/movies/once-upon-a-time-in-harlem", "availableFromTime": null, "dateCreated": "2026-11-06", "package": {"clearName": "Cinemark", "technicalName": "cinemark"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.regmovies.com/movies/once-upon-a-time-in-harlem-ho00023198", "availableFromTime": null, "dateCreated": "2026-11-12", "package": {"clearName": "Regal Cinemas", "technicalName": "regalcinemas"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.harkins.com/movies/once-upon-a-time-in-harlem", "availableFromTime": null, "dateCreated": "2026-11-04", "package": {"clearName": "Harkins Theatres", "technicalName": "harkinstheaters"}}, {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "standardWebURL": "https://www.marcustheatres.com/movies/once-upon-a-time-in-harlem-HO00007955", "availableFromTime": null, "dateCreated": "2026-11-10", "package": {"clearName": "Marcus Theatres", "technicalName": "marcustheatres"}}]}, {"id": "tm327097", "objectId": 327097, "objectType": "MOVIE", "content": {"title": "Once Upon a Time in… Hollywood", "originalReleaseYear": 2019, "fullPath": "/us/movie/once-upon-a-time-in-hollywood", "externalIds": {"tmdbId": "466272"}, "credits": []}, "offers": []}, {"id": "tm76202", "objectId": 76202, "objectType": "MOVIE", "content": {"title": "Once Upon a Time in the West", "originalReleaseYear": 1968, "fullPath": "/us/movie/once-upon-a-time-in-the-west", "externalIds": {"tmdbId": "335"}, "credits": []}, "offers": []}],
 "Wildcards": [{"id": "tm2949112", "objectId": 2949112, "objectType": "MOVIE", "content": {"title": "Wildcards", "originalReleaseYear": 2026, "fullPath": "/us/movie/wildcards", "externalIds": {"tmdbId": "1396875"}, "credits": [{"role": "DIRECTOR", "name": "Wes Miller"}]}, "offers": []}],
 "Wildcards (other films only)": [{"id": "tm1679179", "objectId": 1679179, "objectType": "MOVIE", "content": {"title": "Tilda Swinton: The Wildcards", "originalReleaseYear": 2025, "fullPath": "/us/movie/tilda-swinton-the-wildcards", "externalIds": {"tmdbId": null}, "credits": []}, "offers": [{"monetizationType": "FREE", "presentationType": "SD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://fawesome.tv/movies/10760375/tilda-swinton-the-wildcards?utm_source=justwatch&utm_medium=feed", "availableFromTime": "2026-02-11T05:00:00Z", "package": {"clearName": "Fawesome", "technicalName": "fawesometv"}}]}, {"id": "tm1868659", "objectId": 1868659, "objectType": "MOVIE", "content": {"title": "Jack Nicholson: The Wildcards", "originalReleaseYear": 2025, "fullPath": "/us/movie/jack-nicholson-the-wildcards", "externalIds": {"tmdbId": null}, "credits": []}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "SD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.fubo.tv/welcome/program/SH060923190000", "availableFromTime": "2025-12-01T00:00:00Z", "package": {"clearName": "fuboTV", "technicalName": "fubotv"}}]}]
}
''')

WALL_78303fd6 = json.loads(r'''
{
 "1746615": {"id": "1746615", "title": "Love - Love", "digital_date": "2026-10-08", "bootstrap_date": false, "manually_corrected": false, "synopsis": "LOVE - LOVE is the story of two brothers : Andy, who suffers from schizophrenia, and Jeff, an actor in search of success and meaning in his life. After the death of their grandmother, Andy is left without a « caretaker ». Refusing to live in a group home, he insists on moving in with their father, Bruce, whom they lost touch with after he fled his responsibilities. The two brothers then set out on a road trip to find their father, a disgraced former professional tennis player, now living in seclusion near the Salton Sea, in the California desert.", "genres": ["Drama"], "runtime": 96, "year": 2026, "rt_score": null, "providers": {"rent": [], "buy": [], "streaming": []}, "links": {"wikipedia": null, "trailer": "https://www.youtube.com/watch?v=fBGs3dMnVg4", "rt": null, "justwatch": "https://www.justwatch.com/us/movie/love-love-2026", "cast_wiki": {"Beck Bennett": "https://en.wikipedia.org/wiki/Beck_Bennett", "Haley Joel Osment": "https://en.wikipedia.org/wiki/Haley_Joel_Osment", "Chris Elliott": "https://en.wikipedia.org/wiki/Chris_Elliott"}, "imdb": "https://www.imdb.com/title/tt39169187/", "letterboxd": "https://letterboxd.com/film/love-love-2026", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1746615.mp4"}, "watch_links": {"vod": [{"service": "Eventive", "link": "https://watch.eventive.org/heartlandfilmfestival/play/6a8caa0d26f98166f0238cae", "rent_price": "$15.00", "price": "$15.00"}]}, "pre_order_links": [{"service": "Amazon", "link": "https://www.amazon.com/gp/video/detail/B0GWM7QP6L", "type": "pre_order"}], "_enrichment_status": "completed", "_discovered_at": "2026-10-09T15:02:23.222524", "_tmdb_fetch_failed": false, "_minimal_entry": false, "poster": "https://image.tmdb.org/t/p/w500/AixsRdqW6LbIEVdVx41P7hy51Pu.jpg", "studio": "Stormlight Productions", "budget": 0, "country": "United States of America", "original_language": "en", "original_title": "Love - Love", "display_title": "Love - Love", "crew": {"director": "Thomas Leisten Schneider", "cast": ["Beck Bennett", "Haley Joel Osment", "Chris Elliott", "Abby Elliott", "Penelope Ann Miller"]}, "_discovery_source": "tmdb_type4", "_enrichment_attempts": 1, "_last_enrichment_attempt": "2026-10-09", "imdb_rating": null, "letterboxd_score": null, "keywords": ["road trip", "family", "death in family", "drama", "schizophrenic", "comedy"], "_trailer_source": "gemini_playwright", "_imdb_votes": null, "_digital_date_source": "tmdb_type4", "_needs_review": false, "is_slop": true, "_slop_reason": "score:7(no_wiki,no_rt,no_imdb,no_rt_link)", "_slop_confidence": "weak", "status": "available", "_enrichment_gaps": ["rt_score", "wikipedia", "imdb_rating", "metacritic_score", "letterboxd_score"], "reissue_label": null, "_reissue": false, "virtual_screening_info": {"platform": "Eventive", "screening_slug": "heartlandfilmfestival", "screening_name": "Heartland Film Festival", "available_start": "2026-10-08", "available_end": "2026-10-26", "discovered": "2026-10-09", "last_checked": "2026-10-26", "status": "expired"}, "filters": {"is_indie": false, "is_foreign": false, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": true, "is_series": false, "is_documentary": false, "auto_categorized": true, "manual_override": null}, "featured": false, "_rt_retry_count": 3, "_rt_last_retry": "2026-10-10T03:11:42.230702", "hidden": true}
}
''')

ARCHIVE_78303fd6 = json.loads(r'''
{
 "1178620": {"id": "1178620", "title": "Montreal, My Beautiful", "digital_date": "2026-05-04", "bootstrap_date": false, "manually_corrected": false, "synopsis": "At 53 years old, Feng Xia, a Chinese immigrant in Montreal, finally confronts her repressed desire for women and begins a secret affair with a young Québécoise.", "genres": ["Drama", "Romance"], "runtime": 117, "year": 2026, "rt_score": "95%", "providers": {"rent": ["Eventive"], "buy": [], "streaming": []}, "links": {"wikipedia": "https://en.wikipedia.org/wiki/Montreal,_My_Beautiful", "trailer": "https://www.youtube.com/watch?v=0A9_uxkwWng", "rt": "https://www.rottentomatoes.com/m/my_beautiful_laundrette", "imdb": "https://www.imdb.com/title/tt38503727/", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1178620.mp4", "letterboxd": "https://letterboxd.com/film/montreal-my-beautiful", "director_wiki": "https://en.wikipedia.org/wiki/Xiaodan_He", "trailer_hosted_subs": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1178620.en.vtt", "cast_wiki": {"Joan Chen": "https://en.wikipedia.org/wiki/Joan_Chen"}}, "watch_links": {"vod": [{"service": "Eventive", "link": "https://watch.eventive.org/outshinespring2026/play/69c6da4b3c6b0999464afcaa"}]}, "_enrichment_status": "completed", "_discovered_at": "2026-05-06T12:13:55.129975", "_tmdb_fetch_failed": false, "_minimal_entry": false, "poster": "https://image.tmdb.org/t/p/w500/7yK7d7dngyx2YTWlbyHHOZeLlUJ.jpg", "studio": "Red Dawn Productions", "budget": 0, "country": "Canada", "original_language": "fr", "original_title": "Montréal, ma belle", "display_title": "Montreal, My Beautiful (Montréal, ma belle)", "crew": {"director": "Xiaodan He", "cast": ["Joan Chen", "Charlotte Aubin", "John Xu", "Anzhe Angelo Zhang", "Pei Yao Xu"]}, "_discovery_source": "provider_availability_check", "_enrichment_attempts": 1, "_last_enrichment_attempt": "2026-05-06", "imdb_rating": "6.9", "_trailer_source": "tmdb_official", "_digital_date_source": "detection", "_needs_review": false, "status": "available", "_enrichment_gaps": ["metacritic_score"], "virtual_screening_info": {"platform": "Eventive", "screening_slug": "outshinespring2026", "screening_name": "Welcome to the 28th Annual OUTshine LGBTQ+ Film Festival, Spring Edition", "available_start": "2026-05-04", "available_end": "2026-05-11", "discovered": "2026-05-06", "last_checked": "2026-05-11", "status": "expired"}, "featured": false, "hidden": true, "letterboxd_score": "3.6", "distributor": "Filmoption International", "reissue_label": null, "is_slop": false, "_slop_reason": "score:1(mid_imdb)", "_slop_confidence": "weak", "filters": {"is_indie": false, "is_foreign": true, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": true, "is_series": false, "is_documentary": false, "auto_categorized": true, "manual_override": null}, "keywords": ["coming out", "immigration", "chinese woman", "montreal, canada", "lesbian relationship", "desire", "lgbt", "secret"], "_reissue": false, "capsule": "53-year-old Chinese immigrant in Montreal discovers her queer identity\nStarring screen icon **[Joan Chen](https://en.wikipedia.org/wiki/Joan_Chen)** (*The Last Emperor*, *Twin Peaks*).", "pull_quotes": [], "_tmdb_popularity": null, "buzz_score": 10, "notability": {"buzz_score": 10, "quadrant": "Hidden gem", "festival": "Festival du nouveau cinéma (premiere), Windsor International Film Festival (won Best Canadian Film), Toronto Reel Asian International Film Festival (won RBC Best Canadian Feature Film Award), Reelworld Film Festival (won Outstanding Feature Actress), Frameline, BFI Flare", "awards": "WIFF Prize in Canadian Film, RBC Best Canadian Feature Film Award (Toronto Reel Asian), Outstanding Feature Film Actress (Reelworld), Jay Scott Prize (Toronto Film Critics Association)", "yearend_lists": "CBC News (Top 25 movies of 2025)"}}
}
''')

AVATAR_HEAD_20261113 = json.loads(r'''{"title": "Avatar: Fire and Ash", "status": "tracking", "first_seen": "2025-12-17", "digital_date": "2026-03-31", "providers": {"rent": [], "buy": [], "streaming": []}, "discovery_pass": "B", "has_providers": true, "year": 2025, "_discovery_source": "tmdb_type4", "enriched": true, "enrichment_date": "2026-03-31", "_restored_from": {"removed_reason": "theatrical_pvod_audit", "removed_date": "2026-05-28", "restored_date": "2026-11-13"}}''')
