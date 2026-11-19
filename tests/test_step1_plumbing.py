"""Step 1 v2 plumbing -- end-to-end tests for the put-back work on branch step1-putback-v2
(round-1 + round-2 + round-2b changes on top of a5da4f76).

Owner rules these protect (Nov 2026):
  1. a film held as "not out yet" is a WAIT, never a drop;
  2. every held film is re-checked every daily run;
  3. JustWatch decides availability (TMDB never does);
  4. a film is dated the day it actually became available, never on a day a check
     proved it unavailable;
  5. a JustWatch error or outage never counts against a film and never puts an
     unconfirmed film on the wall;
  and (Nov 15) Remove and Revert are OPPOSITES: Remove = a title the owner never wants
  on the wall (status 'removed', set only by the owner's /remove or the admin Remove
  button); Revert = a film wrongly marked new, back to waiting and back on the wall the
  day it's really out. No automatic path sets 'removed'; no path brings a removed title
  back (section i).

Each test drives a REAL NRW entry point -- DataGenerator / ProviderDiscoverer (discovery,
screening check, archive), the JustWatch client's own offer parsing, the admin Flask app,
the git pre-commit hook, the /curate and /morning scripts -- on REAL records read from
production's data files at 78303fd6 (`git show`, read-only) into a temp directory.
Only the outside world is faked:
  * TMDB (requests.get): payloads marked "captured" were read from the live API on
    2026-11-14; anything marked "scenario" is the change a test needs (e.g. TMDB starts
    listing a store) and says so;
  * JustWatch (requests.Session.post, the GraphQL title search): film nodes with the
    offer fields JustWatch really returns (dateCreated, availableFromTime, the package
    clearName -- e.g. Apple's store is "Apple TV Store"); the JustWatchClient code that
    turns them into answers is the real one;
  * Playwright (the store-page pre-order check): a fake browser with fixed page text;
  * git, for the hook tests only: a stand-in `git` on PATH (no repository is touched).
Nothing here reads or writes the checkout's own data files (a guard checks).

Run:  /usr/bin/python3 -m pytest tests/test_step1_plumbing.py -q -p no:cacheprovider
"""

import ast
import collections
import copy
import datetime as _dt
import io
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import types
from contextlib import redirect_stdout
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]   # the code under test
REPO = ROOT                                   # the git repository holding production's commit
PROD = '78303fd6'   # production main before Step 1 (its data files = the Step 1 base's)

for _p in (str(ROOT / 'scripts'), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The pipeline's loggers add a file handler (logs/admin.log, relative to the current
# directory) and a console handler unless they already have one. A NullHandler keeps
# every test from writing a log file anywhere.
for _name in ('data_generator', 'admin'):
    logging.getLogger(_name).addHandler(logging.NullHandler())


def _git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    return env


def git_show(path):
    """A file as it is in production's commit (read-only `git show`)."""
    r = subprocess.run(['git', '-C', str(REPO), 'show', f'{PROD}:{path}'],
                       capture_output=True, env=_git_env())
    return r.stdout.decode('utf-8') if r.returncode == 0 else None


if subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', f'{PROD}:movie_tracking.json'],
                  capture_output=True, env=_git_env()).returncode != 0:
    pytest.skip(f'production commit {PROD} is not in this repository', allow_module_level=True)

import requests  # noqa: E402

from pipeline import archive as archive_mod  # noqa: E402
from pipeline import discoverer as discoverer_mod  # noqa: E402
from pipeline import enricher as enricher_mod  # noqa: E402
from pipeline import generator as generator_mod  # noqa: E402
from pipeline import justwatch as justwatch_mod  # noqa: E402
from pipeline import putback as putback_mod  # noqa: E402
from pipeline import storage as storage_mod  # noqa: E402
from pipeline import tracking_db as tdb_mod  # noqa: E402
from pipeline.discoverer import ProviderDiscoverer  # noqa: E402
from pipeline.justwatch import JustWatchClient  # noqa: E402

import curate_list  # noqa: E402
_sigpipe = signal.getsignal(signal.SIGPIPE)
import morning_report  # noqa: E402  (sets SIGPIPE=SIG_DFL at import -- restored below)
signal.signal(signal.SIGPIPE, _sigpipe)

for _mod in (archive_mod, discoverer_mod, enricher_mod, generator_mod, justwatch_mod, putback_mod,
             storage_mod, tdb_mod, curate_list, morning_report):
    assert Path(_mod.__file__).resolve().is_relative_to(ROOT), f'{_mod.__name__} not from {ROOT}'


# --------------------------------------------------------------------------
# Real records (ids and fields verified in production's 78303fd6 data files)
# --------------------------------------------------------------------------

MEETING_MARSHA = '1578447'       # wall, digital 2026-09-21, landed 2026-11-13; archive holds a 'reverted' shell
DISPOSABLE_HUMANITY = '1376929'  # wall + a REAL ('retired') archive entry; expired Eventive screening (ended 11-01)
LIVING_CORPSE = '1634820'        # wall, digital 2026-09-01, landed 2026-09-21; never archived
JIMMY = '1241478'                # wall, digital 2026-11-12 (an ordinary in-window arrival)
THE_SECOND_ACT = '1161108'       # wall, tracking 'available'
HIS_MONSTER = '1563321'          # expired screening (ended 10-16); tracking has _virtual_screening + _is_preorder
STEAL_THIS_STORY = '1492865'     # expired screening (ended 10-20); tracking has _type4_pending + _is_preorder
FOREIGNER = '1496770'            # expired screening (11-01..11-07); TMDB still lists only 'Eventive' (rent)
RIVER = '1520592'                # ACTIVE Eventive screening, ends 2026-11-27
MONTREAL_MY_BEAUTIFUL, DIVINE_TRAGEDY = '1178620', '1621342'  # screenings ended 2026-05-11, already archived
# Held in tracking (status 'tracking' + _jw_revert_reason)
MISTLETOE = '1033671'            # Christmas at Mistletoe Manor: no_valid_offers x1 on 2026-11-13
CONCORDE = '1526508'             # old permanent skip (no match x10), TMDB digital date 2026-01-06
EPREUVE = '1303356'              # L'Epreuve du feu: old permanent skip (no offer x4), no TMDB digital date
DARWISH, PRETTY_CRAZY, LIBAN = '1316409', '873797', '1539724'  # old skips; JustWatch still has nothing
LIFE_GOES_THIS_WAY = '1397375'   # old permanent skip, no offer x4 since 2026-07-10; TMDB lists rent/buy
HARLEM = '1596300'               # Once Upon a Time in Harlem: no offer x2 since 2026-10-30; in theaters
LIBERATION = '1129188'           # held (no offer x1) pre-order, TMDB digital date 2026-11-17 (future)
ENSURANCE_TRAP = '772557'        # held (no match x5) pre-order, 2027-07-22, NOT on the wall
# No hold history
WICKER = '1195803'               # buy-only pre-order on the PRE-ORDER lane, TMDB date 2026-12-01
QUEEN_AT_SEA = '1021848'         # buy-only pre-order, no date, TMDB lists only a Fandango purchase
TRACES_OF_JUSTICE = '1439171'    # no date; in theaters (TMDB type 2 2026-11-13)
ACCURSED = '1671305'             # no date, no TMDB data
# Remove / Revert (section i)
A_MAN_WITH_SOLE = '1330406'      # REMOVED by the owner 2026-06-09 (manual_removal); a manual add (_added_manually);
                                 # its expired Eventive screening (ended 2026-01-29) is in the archive
TEKKONKINKREET = '13754'         # wall: a manual add (/add-movie, 2026-06-20), reissue dated 2026-09-01

PREORDER_MARKERS = ('digital_date', '_virtual_screening', '_is_preorder', '_type4_pending')
PUTBACK_SOURCES = putback_mod.PROTECTED_SOURCES

# TMDB US payloads captured read-only 2026-11-14 ("results" of release_dates, watch/providers "US").
TMDB = {
    HIS_MONSTER: {
        'release_dates': [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': '2025-11-08T00:00:00.000Z', 'type': 2, 'note': ''}]}],
        'providers': {
            'free': [{'provider_id': 212, 'provider_name': 'Hoopla'}],
            'rent': [{'provider_id': 10, 'provider_name': 'Amazon Video'},
                     {'provider_id': 2, 'provider_name': 'Apple TV Store'},
                     {'provider_id': 3, 'provider_name': 'Google Play Movies'},
                     {'provider_id': 192, 'provider_name': 'YouTube'},
                     {'provider_id': 7, 'provider_name': 'Fandango At Home'}],
            'buy': [{'provider_id': 10, 'provider_name': 'Amazon Video'},
                    {'provider_id': 2, 'provider_name': 'Apple TV Store'},
                    {'provider_id': 3, 'provider_name': 'Google Play Movies'},
                    {'provider_id': 192, 'provider_name': 'YouTube'},
                    {'provider_id': 7, 'provider_name': 'Fandango At Home'}]}},
    STEAL_THIS_STORY: {
        'release_dates': [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': '2025-06-12T00:00:00.000Z', 'type': 1, 'note': 'DC/DOX Film Festival'},
            {'release_date': '2026-04-10T00:00:00.000Z', 'type': 3, 'note': ''},
            {'release_date': '2026-10-20T00:00:00.000Z', 'type': 4, 'note': ''}]}],
        'providers': {
            'rent': [{'provider_id': 10, 'provider_name': 'Amazon Video'},
                     {'provider_id': 2, 'provider_name': 'Apple TV Store'},
                     {'provider_id': 7, 'provider_name': 'Fandango At Home'}],
            'buy': [{'provider_id': 10, 'provider_name': 'Amazon Video'},
                    {'provider_id': 2, 'provider_name': 'Apple TV Store'},
                    {'provider_id': 7, 'provider_name': 'Fandango At Home'}]}},
    FOREIGNER: {
        'release_dates': [],
        'providers': {'rent': [{'provider_id': 677, 'provider_name': 'Eventive'}]}},
    DISPOSABLE_HUMANITY: {
        'release_dates': [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': '2025-02-20T00:00:00.000Z', 'type': 1, 'note': ''},
            {'release_date': '2025-10-10T00:00:00.000Z', 'type': 1,
             'note': 'Heartland International Film Festival'},
            {'release_date': '2026-08-28T00:00:00.000Z', 'type': 3, 'note': ''}]}],
        'providers': {'rent': [{'provider_id': 677, 'provider_name': 'Eventive'}]}},
    MISTLETOE: {
        'release_dates': [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': '2025-12-07T00:00:00.000Z', 'type': 6, 'note': 'Great American Family'}]}],
        'providers': {'flatrate': [{'provider_id': 257, 'provider_name': 'fuboTV'}]}},
    CONCORDE: {
        'release_dates': [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': '2025-08-16T00:00:00.000Z', 'type': 3, 'note': ''},
            {'release_date': '2026-01-06T00:00:00.000Z', 'type': 4, 'note': ''}]}],
        'providers': {}},
    EPREUVE: {
        'release_dates': [],
        'providers': {'flatrate': [{'provider_id': 257, 'provider_name': 'fuboTV'}]}},
    DARWISH: {
        'release_dates': [],
        'providers': {'flatrate': [{'provider_id': 1715, 'provider_name': 'Shahid VIP'}]}},
    PRETTY_CRAZY: {
        'release_dates': [],
        'providers': {'flatrate': [{'provider_id': 344, 'provider_name': 'Rakuten Viki'}]}},
    LIBAN: {
        'release_dates': [],
        'providers': {'buy': [{'provider_id': 10, 'provider_name': 'Amazon Video'}],
                      'rent': [{'provider_id': 10, 'provider_name': 'Amazon Video'}],
                      'free': [{'provider_id': 2409, 'provider_name': 'Fawesome'}]}},
    LIFE_GOES_THIS_WAY: {
        'release_dates': [],
        'providers': {
            'rent': [{'provider_id': 10, 'provider_name': 'Amazon Video'},
                     {'provider_id': 2, 'provider_name': 'Apple TV Store'},
                     {'provider_id': 3, 'provider_name': 'Google Play Movies'},
                     {'provider_id': 192, 'provider_name': 'YouTube'},
                     {'provider_id': 7, 'provider_name': 'Fandango At Home'}],
            'buy': [{'provider_id': 10, 'provider_name': 'Amazon Video'},
                    {'provider_id': 2, 'provider_name': 'Apple TV Store'},
                    {'provider_id': 3, 'provider_name': 'Google Play Movies'},
                    {'provider_id': 192, 'provider_name': 'YouTube'},
                    {'provider_id': 7, 'provider_name': 'Fandango At Home'}]}},
    TRACES_OF_JUSTICE: {
        'release_dates': [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': '2026-11-13T00:00:00.000Z', 'type': 2, 'note': ''}]}],
        'providers': {}},
    HARLEM: {   # trimmed: 22 festival premieres (type 1) in the live answer, 3 kept
        'release_dates': [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': '2026-01-25T00:00:00.000Z', 'type': 1, 'note': 'Sundance Film Festival'},
            {'release_date': '2026-09-29T00:00:00.000Z', 'type': 1, 'note': 'New York Film Festival'},
            {'release_date': '2026-11-07T00:00:00.000Z', 'type': 1, 'note': 'Indie Memphis Film Festival'},
            {'release_date': '2026-10-16T00:00:00.000Z', 'type': 2, 'note': ''}]}],
        'providers': {}},
}


# --------------------------------------------------------------------------
# Production data (read-only)
# --------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _prod_json(name):
    text = git_show(name)
    assert text is not None, f'git show {PROD}:{name} failed'
    return json.loads(text)


def prod_wall():
    return copy.deepcopy(_prod_json('data.json')['movies'])


def prod_archive():
    return copy.deepcopy(_prod_json('data_archive.json')['movies'])


def wall_rec(mid):
    return copy.deepcopy(next(m for m in _prod_json('data.json')['movies'] if str(m.get('id')) == str(mid)))


def archive_rec(mid):
    return copy.deepcopy(next(m for m in _prod_json('data_archive.json')['movies'] if str(m.get('id')) == str(mid)))


def tracking_rec(mid):
    return copy.deepcopy(_prod_json('movie_tracking.json')['movies'][str(mid)])


def is_shell(m):
    """The archive's own definition of a stale 'reverted' copy (pipeline/archive.py)."""
    return m.get('_enrichment_status') == 'reverted' or m.get('status') == 'tracking'


def ids_of(movies):
    return [str(m.get('id')) for m in movies]


# --------------------------------------------------------------------------
# Guard: the checkout's own data files are never written by these tests
# --------------------------------------------------------------------------

_GUARDED = ('data.json', 'data_archive.json', 'movie_tracking.json', 'movie_tracking.db')


def _fingerprint():
    out = {}
    for name in _GUARDED:
        p = ROOT / name
        if p.exists():
            st = p.stat()
            out[name] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(scope='module', autouse=True)
def _checkout_data_untouched():
    before = _fingerprint()
    yield
    assert _fingerprint() == before, 'a test changed a data file in the checkout itself'


# --------------------------------------------------------------------------
# Frozen clock (the pipeline modules import `datetime` / `date` by name)
# --------------------------------------------------------------------------

CLOCK_MODULES = (generator_mod, discoverer_mod, putback_mod, justwatch_mod, archive_mod, storage_mod,
                 enricher_mod, curate_list, morning_report)


def _frozen_classes(iso):
    now = _dt.datetime.fromisoformat(iso)

    class FrozenDatetime(_dt.datetime):
        _nrw_frozen = True

        @classmethod
        def now(cls, tz=None):
            base = cls(now.year, now.month, now.day, now.hour, now.minute, now.second)
            return base.replace(tzinfo=tz) if tz is not None else base

        @classmethod
        def today(cls):
            return cls.now()

    class FrozenDate(_dt.date):
        _nrw_frozen = True

        @classmethod
        def today(cls):
            return cls(now.year, now.month, now.day)

    return FrozenDatetime, FrozenDate


def freeze(monkeypatch, iso):
    """Every pipeline/report module sees `iso` as now (can be called again: a later day)."""
    fdt, fd = _frozen_classes(iso)
    for mod in CLOCK_MODULES:
        cur = getattr(mod, 'datetime', None)
        if cur is _dt.datetime or getattr(cur, '_nrw_frozen', False):
            monkeypatch.setattr(mod, 'datetime', fdt)
        cur = getattr(mod, 'date', None)
        if cur is _dt.date or getattr(cur, '_nrw_frozen', False):
            monkeypatch.setattr(mod, 'date', fd)


# --------------------------------------------------------------------------
# Network fakes: TMDB (requests.get), JustWatch GraphQL (Session.post), Playwright
# --------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 400
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else '')
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError('response has no JSON body')
        return copy.deepcopy(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} Error', response=self)


_TMDB_URL = re.compile(r'^https://api\.themoviedb\.org/3/movie/(\d+)(?:/(release_dates|watch/providers))?$')


class FakeTMDB:
    """api.themoviedb.org/3/movie/{id}[/release_dates|/watch/providers]. Films not in TMDB{}
    have no dates and no providers; /movie/{id} details answer 404 (the pipeline then
    writes its minimal wall entry)."""

    def __init__(self, unexpected):
        self.data = copy.deepcopy(TMDB)
        self.failures = {}   # (mid, 'release_dates' | 'watch/providers') -> HTTP status
        self.calls = []
        self.unexpected = unexpected

    def set_type4(self, mid, *days):
        """Scenario: TMDB lists these US digital (Type 4) dates."""
        self.data.setdefault(str(mid), {'providers': {}})['release_dates'] = [{'iso_3166_1': 'US', 'release_dates': [
            {'release_date': f'{d}T00:00:00.000Z', 'type': 4, 'note': ''} for d in days]}]

    def set_providers(self, mid, flatrate=(), rent=(), buy=()):
        """Scenario: TMDB lists these US providers."""
        us = {}
        for kind, names in (('flatrate', flatrate), ('rent', rent), ('buy', buy)):
            if names:
                us[kind] = [{'provider_name': n} for n in names]
        self.data.setdefault(str(mid), {'release_dates': []})['providers'] = us

    def get(self, url, params=None, **kwargs):
        m = _TMDB_URL.match(url)
        if not m:
            self.unexpected.append(f'GET {url}')
            raise requests.exceptions.ConnectionError(f'network disabled in tests: GET {url}')
        mid, endpoint = m.group(1), m.group(2) or 'details'
        self.calls.append((mid, endpoint))
        if (mid, endpoint) in self.failures:
            return FakeResponse(self.failures[(mid, endpoint)], {'status_message': 'Internal error.'})
        film = self.data.get(mid, {})
        if endpoint == 'release_dates':
            return FakeResponse(200, {'id': int(mid), 'results': film.get('release_dates', [])})
        if endpoint == 'watch/providers':
            us = film.get('providers')
            return FakeResponse(200, {'id': int(mid), 'results': {'US': us} if us else {}})
        return FakeResponse(404, {'success': False, 'status_code': 34})


TECH = {'Amazon Video': 'amazon', 'Apple TV Store': 'itunes', 'Fandango At Home': 'vudu', 'Hoopla': 'hoopla',
        'MUBI': 'mubi', 'Eventive': 'eventive', 'Hulu': 'hulu', 'Sundance Now': 'sundancenow',
        'Kanopy': 'kanopy', 'Peacock Premium': 'peacocktv', 'TNT': 'tnt', 'YouTube TV': 'youtubetv',
        'Atom Tickets': 'atomtickets'}


def jw_offer(kind, service, url, price=None, created=None, live_from=None, ptype='HD'):
    """One JustWatch offer as the GraphQL API returns it (dateCreated = JustWatch's record day)."""
    return {'monetizationType': kind, 'presentationType': ptype, 'retailPrice': price, 'currency': 'USD',
            'standardWebURL': url, 'availableFromTime': live_from, 'dateCreated': created,
            'package': {'clearName': service, 'technicalName': TECH.get(service, service.lower().replace(' ', ''))}}


def amazon(mid, created, live_from=None):
    url = f'https://watch.amazon.com/detail?gti=amzn1.dv.gti.test-{mid}'
    return [jw_offer('RENT', 'Amazon Video', url, '$5.99', created, live_from or f'{created}T07:00:00Z'),
            jw_offer('BUY', 'Amazon Video', url, '$14.99', created, live_from or f'{created}T07:00:00Z')]


def apple(mid, created, live_from=None):
    url = f'https://tv.apple.com/us/movie/test/umc.cmc.test{mid}'
    return [jw_offer('RENT', 'Apple TV Store', url, '$5.99', created, live_from),
            jw_offer('BUY', 'Apple TV Store', url, '$14.99', created, live_from)]


def fandango(mid, created):
    url = f'https://athome.fandango.com/content/browse/details/test/{mid}'
    return [jw_offer('RENT', 'Fandango At Home', url, '$5.99', created),
            jw_offer('BUY', 'Fandango At Home', url, '$14.99', created)]


def streaming(service, url, created, kind='FLATRATE'):
    return [jw_offer(kind, service, url, None, created)]


def jw_node(mid, title, year, offers):
    return {'id': f'tm{mid}', 'objectId': int(mid), 'objectType': 'MOVIE',
            'content': {'title': title, 'originalReleaseYear': year, 'fullPath': f'/us/movie/test-{mid}',
                        'externalIds': {'tmdbId': str(mid)}, 'credits': []},
            'offers': offers}


# The health canary's control titles (ProviderDiscoverer._JW_CANARY_TITLES), with offers
# as captured live on 2026-11-14 (trimmed to one streaming offer each).
CANARY_NODES = {
    'Oppenheimer': [jw_node('872585', 'Oppenheimer', 2023, streaming(
        'Peacock Premium', 'https://www.peacocktv.com/watch/asset/movies/oppenheimer/602fd345', None))],
    'Barbie': [jw_node('346698', 'Barbie', 2023, streaming('TNT', 'https://www.tntdrama.com/movies/barbie', None))],
    'Dune: Part Two': [jw_node('693134', 'Dune: Part Two', 2024, streaming(
        'YouTube TV', 'https://tv.youtube.com/browse/UCboqvWjW9JKlu2d2LiB0YHg', None))],
}
CANARY_TITLES = {t for t, _ in ProviderDiscoverer._JW_CANARY_TITLES}
assert CANARY_TITLES == set(CANARY_NODES)


class FakeJustWatch:
    """apis.justwatch.com/graphql popularTitles search, keyed by searchQuery (the title).
    A title with no node gets zero results (a genuine "no match")."""

    def __init__(self, unexpected):
        self.nodes = {}
        self.errors = {}      # title -> 'connection_error' | 'timeout' | 'http_429' | 'graphql_error'
        self.down = None      # None | 'offers' (titles come back, offer lists empty) | 'blocked' (no results)
        self.queries = []     # every searchQuery, in order (canary included)
        self.unexpected = unexpected

    def film(self, mid, title, year, offers):
        """JustWatch's node for one film. Same-title films all come back for that title's
        search (several real films are called 'The Doll'); the client picks by TMDB id."""
        others = [n for n in self.nodes.get(title, []) if n['content']['externalIds']['tmdbId'] != str(mid)]
        self.nodes[title] = others + [jw_node(mid, title, year, offers)]

    def film_queries(self):
        return [q for q in self.queries if q not in CANARY_TITLES]

    def post(self, url, **kwargs):
        if url != JustWatchClient.API_URL:
            self.unexpected.append(f'POST {url}')
            raise requests.exceptions.ConnectionError(f'network disabled in tests: POST {url}')
        q = ((kwargs.get('json') or {}).get('variables') or {}).get('searchQuery')
        self.queries.append(q)
        kind = self.errors.get(q)
        if kind == 'connection_error':
            raise requests.exceptions.ConnectionError('Connection aborted: RemoteDisconnected')
        if kind == 'timeout':
            raise requests.exceptions.Timeout('Read timed out. (read timeout=15)')
        if kind == 'http_429':
            return FakeResponse(429, None, text='Too Many Requests')
        if kind == 'graphql_error':
            return FakeResponse(200, {'errors': [{'message': 'Internal server error'}], 'data': None})
        if self.down == 'blocked':
            return FakeResponse(200, {'data': {'popularTitles': {'edges': []}}})
        nodes = copy.deepcopy(self.nodes.get(q) or CANARY_NODES.get(q) or [])
        if self.down == 'offers':
            for n in nodes:
                n['offers'] = []
        return FakeResponse(200, {'data': {'popularTitles': {'edges': [{'node': n} for n in nodes]}}})


class FakeStorePages:
    """Stands in for Playwright (playwright_manager) in ProviderDiscoverer._check_preorder_page."""

    AVAILABLE = 'Rent HD $5.99  Buy HD $14.99  Rent now  Buy now'
    PREORDER = 'Available to pre-order. This video will be released soon. Pre-order HD $14.99'

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


# --------------------------------------------------------------------------
# A throwaway NRW working copy (cwd = tmp_path)
# --------------------------------------------------------------------------

def quiet(fn, *args, **kwargs):
    """Run fn with stdout captured; return (result, printed text)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = fn(*args, **kwargs)
    return result, buf.getvalue()


class NRW:
    def __init__(self, root, monkeypatch):
        self.root = root
        self.mp = monkeypatch
        self.tdb = None
        self.unexpected = []
        self.tmdb = FakeTMDB(self.unexpected)
        self.jw = FakeJustWatch(self.unexpected)
        self.pages = FakeStorePages()
        self.head_status = 200

    # -- network --
    def install(self):
        def blocked(*args, **kwargs):
            self.unexpected.append(f'blocked call {args[:3]}')
            raise requests.exceptions.ConnectionError('network disabled in tests')

        self.mp.setattr(requests, 'get', self.tmdb.get)
        self.mp.setattr(requests, 'head', lambda url, **kw: FakeResponse(self.head_status))
        self.mp.setattr(requests, 'post', blocked)
        self.mp.setattr(requests.Session, 'post', lambda session, url, *a, **kw: self.jw.post(url, **kw))
        self.mp.setattr(requests.Session, 'request', blocked)
        self.mp.setitem(sys.modules, 'playwright_manager', self.pages.module())

    # -- clock --
    def at(self, iso):
        freeze(self.mp, iso)

    # -- files --
    def write_json(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')

    def read_json(self, name):
        return json.loads((self.root / name).read_text(encoding='utf-8'))

    def write_wall(self, movies):
        meta = {k: copy.deepcopy(v) for k, v in _prod_json('data.json').items() if k != 'movies'}
        self.write_json('data.json', {**meta, 'count': len(movies), 'movies': movies})

    def wall(self):
        return self.read_json('data.json')['movies']

    def wall_entry(self, mid):
        return next((m for m in self.wall() if str(m.get('id')) == str(mid)), None)

    def write_archive(self, movies):
        self.write_json('data_archive.json', {'archived_at': '2026-11-13T23:00:00', 'count': len(movies),
                                              'movies': movies})

    def archive(self):
        return self.read_json('data_archive.json')['movies']

    def write_tracking(self, records):
        self.write_json('movie_tracking.json', {'movies': records})
        self.tdb = tdb_mod.TrackingDB(db_path=str(self.root / 'movie_tracking.db'),
                                      json_path=str(self.root / 'movie_tracking.json'))
        self.mp.setattr(tdb_mod, '_shared_instance', self.tdb)

    def tracking(self):
        return self.tdb.load_all()['movies']

    def seed(self, ids, wall=None, records=None):
        """Tracking = the real records of `ids` (or `records`); wall = `wall` (default: empty)."""
        recs = records if records is not None else {str(i): tracking_rec(i) for i in ids}
        self.write_tracking(recs)
        self.write_wall(list(wall or []))
        return recs

    def jw_has(self, mid, offers, title=None, year=None):
        """JustWatch's node for a seeded film (its title + year from tracking)."""
        rec = self.tracking().get(str(mid)) or tracking_rec(mid)
        self.jw.film(mid, title or rec['title'], year if year is not None else rec.get('year'), offers)

    # -- pipeline --
    def generator(self):
        """A new pipeline process (fresh JustWatch client, canary and run counters)."""
        if self.tdb is None:
            self.write_tracking({})
        from pipeline.generator import DataGenerator
        gen = DataGenerator(enrichment_enabled=False)
        assert gen.storage.tracking_db is self.tdb
        return gen

    def discover(self, gen=None):
        """One discovery run (generate_data.py --discover) through the real entry point."""
        gen = gen or self.generator()
        _, out = quiet(gen.check_tracking_movies)
        # check_tracking_movies swallows any exception raised inside its loop: a crash
        # must never pass for a quiet run.
        assert 'Unexpected error during provider checking' not in out, out[-3000:]
        return gen, out

    def metrics(self):
        return self.read_json('metrics/discovery_run.json')

    def queued(self):
        return self.read_json('metrics/newly_available.json')['movie_ids']


@pytest.fixture
def nrw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TMDB_API_KEY', 'test-key-not-real')
    monkeypatch.delenv('NRW_ENV', raising=False)
    shutil.copy(ROOT / 'config.yaml', tmp_path / 'config.yaml')   # its api keys are blank; env has the dummy
    monkeypatch.setattr(tdb_mod, '_shared_instance', None)
    env = NRW(tmp_path, monkeypatch)
    env.install()
    yield env
    assert not env.unexpected, f'the pipeline made network calls the test did not fake: {env.unexpected}'


DAY = '2026-11-14T06:30:00'        # the morning after the production snapshot
NEXT_DAY = '2026-11-15T06:30:00'
TODAY, TOMORROW = DAY[:10], NEXT_DAY[:10]


# ==========================================================================
# (a) archive_old_movies: stale 'reverted' shells vs real entries
# ==========================================================================

ARCHIVE_DAY = '2026-12-21T09:00:00'  # 90 days later Meeting Marsha (2026-09-21) has aged out


def _archive_cutoff():
    return (_dt.datetime.fromisoformat(ARCHIVE_DAY) - _dt.timedelta(days=90)).strftime('%Y-%m-%d')


def _age_out(nrw, wall, archive):
    nrw.write_wall(wall)
    nrw.write_archive(archive)
    nrw.at(ARCHIVE_DAY)
    quiet(nrw.generator().archive_old_movies, days=90)
    return nrw.wall(), nrw.archive()


def test_archive_replaces_a_stale_reverted_shell_with_the_films_real_entry(nrw):
    wall, archive = prod_wall(), prod_archive()
    archived = {str(m['id']): m for m in archive}
    cutoff = _archive_cutoff()
    real_mm = next(m for m in wall if str(m['id']) == MEETING_MARSHA)
    assert is_shell(archived[MEETING_MARSHA]) and not is_shell(real_mm)  # production: archive only has the shell
    expected = {str(m['id']): copy.deepcopy(m) for m in wall
                if m.get('digital_date') and m['digital_date'] < cutoff
                and str(m['id']) in archived and is_shell(archived[str(m['id'])]) and not is_shell(m)}
    assert MEETING_MARSHA in expected and len(expected) >= 40   # the real backlog of lost copies

    new_wall, new_archive = _age_out(nrw, wall, archive)

    copies = collections.defaultdict(list)
    for m in new_archive:
        copies[str(m['id'])].append(m)
    still_shell = [mid for mid, real in expected.items() if copies[mid] != [real]]
    assert not still_shell, f'archive still holds the stale shell (or a duplicate) for {still_shell}'
    assert MEETING_MARSHA not in ids_of(new_wall)


def test_archive_never_replaces_a_real_archived_entry_with_a_shell(nrw):
    wall, archive = prod_wall(), prod_archive()
    original = next(m for m in archive if str(m['id']) == DISPOSABLE_HUMANITY)
    assert not is_shell(original)                      # a real ('retired') archived copy
    for m in wall:                                     # enrichment's JustWatch pull, verbatim (enricher.py)
        if str(m['id']) == DISPOSABLE_HUMANITY:
            m['_jw_reverted'] = True
            m['_jw_revert_reason'] = 'justwatch_no_valid_offers'
            m['_enrichment_status'] = 'reverted'
            m['status'] = 'tracking'
            assert m['digital_date'] < _archive_cutoff()

    new_wall, new_archive = _age_out(nrw, wall, archive)

    assert [m for m in new_archive if str(m['id']) == DISPOSABLE_HUMANITY] == [original]
    assert DISPOSABLE_HUMANITY not in ids_of(new_wall)


def test_archive_still_appends_films_it_has_never_archived(nrw):
    wall, archive = prod_wall(), prod_archive()
    archived_ids = set(ids_of(archive))
    cutoff = _archive_cutoff()
    new_ids = [str(m['id']) for m in wall
               if m.get('digital_date') and m['digital_date'] < cutoff and str(m['id']) not in archived_ids]
    assert LIVING_CORPSE in new_ids

    new_wall, new_archive = _age_out(nrw, wall, archive)

    counts = collections.Counter(ids_of(new_archive))
    assert [i for i in new_ids if counts[i] != 1] == []
    assert len(new_archive) == len(archive) + len(new_ids)
    assert max(counts.values()) == 1
    assert not set(new_ids) & set(ids_of(new_wall))


@pytest.mark.parametrize('attempts', [1, 4, 5], ids=lambda n: f'{n}-enrichment-attempts')
def test_archive_keeps_an_entry_still_waiting_for_its_justwatch_check(nrw, attempts):
    """Round 2: an entry enrichment hid because JustWatch couldn't check it (`_jw_unconfirmed`)
    is not archived, however old its date -- archived unchecked, nothing would check it again.
    Round 2b: only while enrichment still retries it (attempts < MAX_ENRICHMENT_ATTEMPTS = 5);
    once its retries ran out it ages out as usual (/morning lists it as stuck)."""
    wall, archive = prod_wall(), prod_archive()
    for m in wall:
        if str(m['id']) == LIVING_CORPSE:      # 2026-09-01: past the 90-day cutoff; 1 attempt in production
            m['hidden'] = True
            m['_jw_unconfirmed'] = '2026-12-20'
            m['_enrichment_attempts'] = attempts

    new_wall, new_archive = _age_out(nrw, wall, archive)

    if attempts < 5:
        kept = next(m for m in new_wall if str(m['id']) == LIVING_CORPSE)
        assert kept['_jw_unconfirmed'] == '2026-12-20' and kept['hidden'] is True
        assert LIVING_CORPSE not in ids_of(new_archive)
    else:
        assert LIVING_CORPSE not in ids_of(new_wall)
        assert ids_of(new_archive).count(LIVING_CORPSE) == 1
    assert MEETING_MARSHA not in ids_of(new_wall)            # everything else aged out as usual


# ==========================================================================
# (b) + (c) expired virtual screenings: returned once, then JustWatch decides
# ==========================================================================

def _screenings_on_wall(nrw, only=None):
    """The real wall's virtual-screening entries + their real tracking records."""
    wall = [m for m in prod_wall() if m.get('filters', {}).get('is_virtual_screening')
            and (only is None or str(m['id']) in only)]
    records = {str(m['id']): tracking_rec(m['id']) for m in wall}
    nrw.write_wall(wall)
    nrw.write_tracking(records)
    nrw.at(DAY)
    return wall, records


def _return_then_discover(nrw, mid, offers=None):
    """Morning run: the screening check returns the expired screening, then discovery checks
    it (TMDB + JustWatch; `offers` = JustWatch's offers, None = JustWatch can't find it).
    Returns (generator, record right after the return, discovery output)."""
    _screenings_on_wall(nrw, only={mid})
    gen = nrw.generator()
    quiet(gen.check_virtual_screening_expirations)
    returned = nrw.tracking()[mid]
    if offers is not None:
        nrw.jw_has(mid, offers)
    _, out = nrw.discover(gen)
    return gen, returned, out


def test_expired_screenings_return_to_tracking_with_their_preorder_markers_dropped(nrw):
    wall, before = _screenings_on_wall(nrw)
    by_id = {str(m['id']): m for m in wall}
    def _stale(v):   # marked expired for an EARLIER screening; the newer window is still ahead (round 2f+)
        return ((v.get('available_end') or '') >= DAY[:10] and (v.get('available_start') or '')
                and (v.get('last_checked') or '')[:10] and v['available_start'] > v['last_checked'][:10])
    expired = [str(m['id']) for m in wall
               if (m.get('virtual_screening_info') or {}).get('status') == 'expired'
               and not _stale(m.get('virtual_screening_info') or {})
               and before[str(m['id'])]['status'] == 'available']
    assert {HIS_MONSTER, STEAL_THIS_STORY, FOREIGNER} <= set(expired) and len(expired) >= 150
    assert before[HIS_MONSTER].get('_virtual_screening') and before[HIS_MONSTER].get('_is_preorder')
    assert before[STEAL_THIS_STORY].get('_type4_pending') and before[STEAL_THIS_STORY].get('_is_preorder')

    quiet(nrw.generator().check_virtual_screening_expirations)

    after = nrw.tracking()
    wrong = {mid: {k: after[mid].get(k) for k in ('status', '_screening_expired', *PREORDER_MARKERS)}
             for mid in expired
             if after[mid]['status'] != 'tracking' or after[mid].get('_screening_expired') is not True
             or any(k in after[mid] for k in PREORDER_MARKERS)}
    assert not wrong, f'{len(wrong)} expired screening(s) not cleanly returned: {dict(list(wrong.items())[:5])}'
    # Round 2: each remembers when its screening ended (put-back dating ignores a TMDB
    # "digital" date on/before it -- the festival screening) and when it was returned.
    ended_wrong = [mid for mid in expired
                   if after[mid].get('_screening_ended') != (
                       ((by_id[mid].get('virtual_screening_info') or {}).get('available_end') or '')[:10] or None)
                   or after[mid].get('_screening_returned_at') != TODAY]
    assert not ended_wrong, ended_wrong[:5]
    assert (after[HIS_MONSTER]['_screening_ended'], after[STEAL_THIS_STORY]['_screening_ended'],
            after[FOREIGNER]['_screening_ended']) == ('2026-10-16', '2026-10-20', '2026-11-07')
    exported = nrw.read_json('movie_tracking.json')['movies']        # the export CI commits
    assert all(exported[mid]['status'] == 'tracking' for mid in expired)


def test_expired_screening_already_in_the_archive_is_returned_to_tracking(nrw):
    """Fixed in v2 (v1 xfail): a screening whose wall entry already aged into the archive was
    never re-checked, so its regular release was never found (Montreal, My Beautiful and The
    Divine Tragedy are on Amazon since 2026-11-03/04)."""
    archived = [archive_rec(MONTREAL_MY_BEAUTIFUL), archive_rec(DIVINE_TRAGEDY)]
    assert all(m['virtual_screening_info']['status'] == 'expired' for m in archived)
    wall = [m for m in prod_wall() if m.get('filters', {}).get('is_virtual_screening')]
    assert not {MONTREAL_MY_BEAUTIFUL, DIVINE_TRAGEDY} & set(ids_of(wall))
    records = {str(m['id']): tracking_rec(m['id']) for m in wall + archived}
    assert records[MONTREAL_MY_BEAUTIFUL]['status'] == records[DIVINE_TRAGEDY]['status'] == 'available'
    nrw.write_wall(wall)
    nrw.write_archive(prod_archive())
    nrw.write_tracking(records)
    nrw.at(DAY)

    quiet(nrw.generator().check_virtual_screening_expirations)

    after = nrw.tracking()
    stuck = [mid for mid in (MONTREAL_MY_BEAUTIFUL, DIVINE_TRAGEDY)
             if after[mid]['status'] != 'tracking' or not after[mid].get('_screening_expired')]
    assert not stuck, f'expired screenings never re-checked: {stuck}'
    # their screening's last day comes from the ARCHIVED entry (round 2)
    assert after[MONTREAL_MY_BEAUTIFUL]['_screening_ended'] == after[DIVINE_TRAGEDY]['_screening_ended'] == '2026-05-11'
    assert 'digital_date' not in after[MONTREAL_MY_BEAUTIFUL]   # the screening date is not a release date


def test_a_screening_that_runs_out_is_returned_with_its_last_day(nrw):
    """Round 2, the date-based expiry path: River's Eventive screening ends 2026-11-27; on the
    28th the check hides it and returns it to tracking with `_screening_ended` = 11-27."""
    _screenings_on_wall(nrw, only={RIVER})
    assert tracking_rec(RIVER)['status'] == 'available'
    nrw.at('2026-11-28T06:30:00')

    quiet(nrw.generator().check_virtual_screening_expirations)

    rec = nrw.tracking()[RIVER]
    assert rec['status'] == 'tracking' and rec['_screening_expired'] is True
    assert (rec['_screening_ended'], rec['_screening_returned_at']) == ('2026-11-27', '2026-11-28')
    entry = nrw.wall_entry(RIVER)
    assert entry['hidden'] is True and entry['virtual_screening_info']['status'] == 'expired'


def test_active_screening_still_gets_the_virtual_screening_bypass(nrw):
    rec = tracking_rec(RIVER)
    assert 'Eventive' in rec['providers']['rent'] and not rec.get('_screening_expired')
    nrw.write_tracking({RIVER: rec})
    nrw.at(DAY)
    gen = nrw.generator()

    result, _ = quiet(gen._discoverer._verify_before_wall, RIVER, rec)

    assert result == {'verified': True, '_bypass': 'virtual_screening'}
    assert nrw.jw.queries == []


def test_verify_gate_gives_a_returned_screening_listing_eventive_no_bypass(nrw):
    _screenings_on_wall(nrw, only={FOREIGNER})
    gen = nrw.generator()
    quiet(gen.check_virtual_screening_expirations)
    rec = nrw.tracking()[FOREIGNER]
    assert rec['_screening_expired'] and 'Eventive' in rec['providers']['rent']
    # live JustWatch: no listing for it

    result, _ = quiet(gen._discoverer._verify_before_wall, FOREIGNER, rec)

    assert nrw.jw.film_queries() == ['Foreigner'], 'returned screening was not checked on JustWatch'
    assert result is None
    assert rec['_jw_revert_reason'] == 'justwatch_no_match' and rec['_jw_revert_count'] == 1
    assert '_jw_last_refuted' not in rec       # "can't find it" proves nothing about availability


def test_returned_screening_stays_held_through_discovery_while_justwatch_lacks_it(nrw):
    gen, returned, out = _return_then_discover(nrw, FOREIGNER, None)

    rec = nrw.tracking()[FOREIGNER]
    assert 'Foreigner' in nrw.jw.film_queries()
    assert rec['status'] == 'tracking'
    assert rec['_jw_revert_reason'] == 'justwatch_no_match' and rec['_jw_revert_count'] == 1
    assert 'digital_date' not in rec                      # a hold never invents a date
    assert nrw.wall_entry(FOREIGNER).get('hidden') is True  # still off the visible wall


def _his_monster_jw():
    """JustWatch for His Monster (modelled on the live answer of 2026-11-14): Amazon/Apple/
    Fandango rent+buy, Hoopla free; Amazon's offer recorded and live since 2026-10-05."""
    return (amazon(HIS_MONSTER, '2026-10-05') + apple(HIS_MONSTER, '2026-10-06')
            + fandango(HIS_MONSTER, '2026-10-07')
            + streaming('Hoopla', 'https://www.hoopladigital.com/movie/his-monster/1', '2026-10-20', 'FREE'))


def _steal_this_story_jw():
    """JustWatch for Steal This Story, Please! (modelled on the live answer of 2026-11-14):
    Amazon/Fandango/Apple rent+buy, Amazon recorded and live since 2026-10-20 (= TMDB's Type 4)."""
    return (amazon(STEAL_THIS_STORY, '2026-10-20') + fandango(STEAL_THIS_STORY, '2026-10-20')
            + apple(STEAL_THIS_STORY, '2026-10-21'))


@pytest.mark.parametrize('mid, jw_answer, came_out', [
    (HIS_MONSTER, _his_monster_jw, '2026-10-05'),             # TMDB providers path
    (STEAL_THIS_STORY, _steal_this_story_jw, '2026-10-20'),   # TMDB Type 4 path
], ids=['his-monster-providers-path', 'steal-this-story-type4-path'])
def test_returned_screening_goes_back_on_the_wall_dated_when_it_came_out(nrw, mid, jw_answer, came_out):
    gen, returned, out = _return_then_discover(nrw, mid, jw_answer())

    rec = nrw.tracking()[mid]
    assert rec['status'] == 'available'
    # dated by JustWatch's own first record of a way to watch it (v2): Amazon's offer start
    # field is gone. For Steal This Story TMDB's Type 4 (10-20) falls on the screening's
    # last day (_screening_ended), so only JustWatch's record could date it.
    assert (rec['digital_date'], rec['_digital_date_source']) == (came_out, 'jw_first_offer')
    assert rec['_put_back_on'] == TODAY and rec['_held_since'] == TODAY
    assert not rec.get('_date_needs_review')
    entry = nrw.wall_entry(mid)
    assert not entry.get('hidden') and entry['digital_date'] == came_out
    # round 2: the wall entry is synced at the transition -- no festival link or flag left
    # for the display step to re-hide it under the screening's date
    assert entry['filters'].get('is_virtual_screening') is False
    assert 'virtual_screening_info' not in entry and '_virtual_screening' not in entry
    assert 'Eventive' not in [v.get('service') for v in entry['watch_links'].get('vod', [])]
    assert entry['_digital_date_source'] == 'jw_first_offer'


def test_put_back_screening_is_not_pulled_back_by_the_next_screening_check(nrw):
    gen, *_ = _return_then_discover(nrw, HIS_MONSTER, _his_monster_jw())
    assert nrw.tracking()[HIS_MONSTER]['status'] == 'available'   # it came back

    _, out = quiet(gen.check_virtual_screening_expirations)       # next run

    rec = nrw.tracking()[HIS_MONSTER]
    assert rec['status'] == 'available' and rec['digital_date'] == '2026-10-05'
    assert not nrw.wall_entry(HIS_MONSTER).get('hidden')
    assert 'His Monster' not in out


def test_returned_screening_whose_only_justwatch_rental_is_its_own_festival_page_stays_held(nrw):
    """v1 put Disposable Humanity back on JustWatch's single 'rental': its own (ended) Eventive
    screening page. v2 leaves festival platforms out when JustWatch decides for a held film."""
    eventive = [jw_offer('RENT', 'Eventive',
                         'https://watch.eventive.org/disposablehumanity/play/6a7868d1bdb10f0bb45affc6',
                         '$19.39', '2026-09-04')]
    gen, returned, out = _return_then_discover(nrw, DISPOSABLE_HUMANITY, eventive)

    rec = nrw.tracking()[DISPOSABLE_HUMANITY]
    assert nrw.jw.film_queries() == ['Disposable Humanity']
    assert rec['status'] == 'tracking' and '_put_back_on' not in rec
    assert (rec['_jw_revert_reason'], rec['_jw_revert_count']) == ('justwatch_no_valid_offers', 1)
    assert rec['_jw_last_refuted'] == TODAY     # JustWatch has it, with no real way to watch it
    assert nrw.wall_entry(DISPOSABLE_HUMANITY).get('hidden') is True


def test_returned_screening_confirmed_without_date_evidence_is_flagged_for_date_review(nrw):
    """Fixed in v2 (v1 xfail): a returned screening JustWatch confirms with no date evidence (no
    TMDB digital date; JustWatch's record date is its 2000-07-14 placeholder) is dated today
    and FLAGGED -- it went unchecked, so 'today' is a guess (v1 called it 'checked daily')."""
    gen, returned, out = _return_then_discover(nrw, DISPOSABLE_HUMANITY,
                                               amazon(DISPOSABLE_HUMANITY, '2000-07-14', '2026-11-10T08:00:00Z'))

    rec = nrw.tracking()[DISPOSABLE_HUMANITY]
    assert rec['status'] == 'available' and rec['_put_back_on'] == TODAY   # it was put back
    assert (rec['digital_date'], rec['_digital_date_source']) == (TODAY, 'putback_review')
    assert rec['_date_needs_review'] is True
    assert 'date flagged for review' in out


# ==========================================================================
# (d) .githooks/pre-commit: blocks data-file commits; no auto-staging any more
# ==========================================================================

HOOK = ROOT / '.githooks' / 'pre-commit'

# A stand-in for `git` on PATH: the hook's own queries get canned answers, every call is
# logged. No repository is read or written.
_GIT_SHIM = r'''#!/bin/bash
echo "$*" >> "$NRW_GIT_LOG"
case "$*" in
  "diff --cached --name-only --diff-filter=A") exit 0 ;;
  "diff --cached --name-only") for f in $NRW_GIT_STAGED; do echo "$f"; done; exit 0 ;;
  "diff --cached") exit 0 ;;
  "diff --quiet -- "*) f="${*#diff --quiet -- }"; for m in $NRW_GIT_MODIFIED; do [ "$m" = "$f" ] && exit 1; done; exit 0 ;;
  *) exit 0 ;;
esac
'''


def _run_hook(tmp_path, staged, modified=(), allow=False):
    shim = tmp_path / 'shim'
    shim.mkdir(exist_ok=True)
    (shim / 'git').write_text(_GIT_SHIM)
    os.chmod(shim / 'git', 0o755)
    log = tmp_path / 'git_calls.log'
    log.write_text('')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k != 'NRW_ALLOW_DATA_COMMIT'}
    env.update(PATH=f'{shim}{os.pathsep}{env.get("PATH", "")}', NRW_GIT_LOG=str(log),
               NRW_GIT_STAGED=' '.join(staged), NRW_GIT_MODIFIED=' '.join(modified))
    if allow:
        env['NRW_ALLOW_DATA_COMMIT'] = '1'
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    r = subprocess.run(['bash', str(HOOK)], cwd=work, env=env, capture_output=True, text=True)
    return r, log.read_text().splitlines()


def test_hook_still_blocks_a_data_json_commit_without_the_override(tmp_path):
    r, calls = _run_hook(tmp_path, staged=['data.json'], modified=['data_archive.json'])

    assert r.returncode != 0
    assert 'BLOCKED: data.json is staged for commit.' in r.stdout + r.stderr
    assert not [c for c in calls if c.startswith('add')]


def test_hook_no_longer_stages_the_archive_or_tracking_export_on_its_own(tmp_path):
    """Inverted v1 test. v1's hook `git add`-ed data_archive.json / movie_tracking.json whenever
    data.json was committed; inside a pathspec commit (/flow's `git commit -- data.json`,
    local_daily.sh) that only reached git's temporary index, and the next launchagent reset
    restored the OLD archive -- archived films vanished. v2 restores production's hook; the
    archive/commit sync is fixed at the commit sites in a later step."""
    assert HOOK.read_text() == git_show('.githooks/pre-commit'), 'v2 hook differs from production'

    r, calls = _run_hook(tmp_path, staged=['data.json'],
                         modified=['data_archive.json', 'movie_tracking.json'], allow=True)

    assert r.returncode == 0, r.stdout + r.stderr
    assert not [c for c in calls if c.startswith('add')], calls
    assert 'auto-staged' not in r.stdout


# ==========================================================================
# (e) /curate window: films that landed this week, even with an older digital date
# ==========================================================================

CURATE_DAY = '2026-11-14T08:00:00'


def _curate_rows(stage):
    _, out = quiet(curate_list.build, stage, 7)
    return [line.split('|||')[-1] for line in out.splitlines()[1:] if '|||' in line]


@pytest.fixture
def curate_wall(nrw):
    mm, lc = wall_rec(MEETING_MARSHA), wall_rec(LIVING_CORPSE)
    assert (mm['digital_date'], mm['_discovered_at'][:10]) == ('2026-09-21', '2026-11-13')
    assert (lc['digital_date'], lc['_discovered_at'][:10]) == ('2026-09-01', '2026-09-21')
    nrw.write_wall([mm, lc, wall_rec(JIMMY)])
    nrw.at(CURATE_DAY)
    return nrw


@pytest.mark.parametrize('stage', ['selects', 'sections', 'slop', 'capsule'])
def test_curate_lists_a_film_that_landed_this_week_with_an_older_digital_date(curate_wall, stage):
    rows = _curate_rows(stage)
    assert JIMMY in rows                 # ordinary in-window arrival (sanity)
    assert MEETING_MARSHA in rows


@pytest.mark.parametrize('stage', ['selects', 'sections', 'slop', 'capsule'])
def test_curate_skips_a_film_that_landed_long_ago(curate_wall, stage):
    assert LIVING_CORPSE not in _curate_rows(stage)


def test_morning_backlog_counts_a_film_put_back_this_week_like_curate(curate_wall):
    """Fixed in v2 (v1 xfail): /morning's backlog uses /curate's window (curate_list._in_window)."""
    assert MEETING_MARSHA in _curate_rows('capsule')
    _, out = quiet(morning_report.backlog)
    assert 'Meeting Marsha' in out, out
    assert 'Living Corpse' not in out


# ==========================================================================
# (f) /morning: held count, every film put back today, JustWatch trouble
# ==========================================================================

REPORT_DAY = '2026-11-14T07:00:00'


def test_morning_report_counts_held_films_and_lists_every_film_put_back_today(nrw):
    held_ids = [MISTLETOE, CONCORDE, EPREUVE, DARWISH, PRETTY_CRAZY, LIBAN]
    records = {mid: tracking_rec(mid) for mid in held_ids}
    assert all(r['status'] == 'tracking' and r.get('_jw_revert_reason') for r in records.values())
    assert records[CONCORDE].get('_skip_provider_discovery') and records[EPREUVE].get('_skip_provider_discovery')
    nrw.write_tracking(records)
    nrw.write_wall(prod_wall())
    nrw.write_archive(prod_archive())
    # Release day for three of them (JustWatch now has offers); the other three are still not out.
    nrw.jw_has(MISTLETOE, amazon(MISTLETOE, '2026-11-14'))            # recorded today
    nrw.jw_has(CONCORDE, amazon(CONCORDE, '2026-03-02'))              # a later re-listing: TMDB's 01-06 is earlier
    nrw.jw_has(EPREUVE, streaming('MUBI', 'https://mubi.com/films/test', '2000-07-14'))  # placeholder record date
    nrw.jw_has(DARWISH, [])                                           # JustWatch has it, no offer
    nrw.jw_has(PRETTY_CRAZY, [])                                      # JustWatch has it, no offer
    # LIBAN: JustWatch can't find it
    nrw.at(REPORT_DAY)
    gen = nrw.generator()

    nrw.discover(gen)                        # discovery (writes metrics/discovery_run.json)
    quiet(gen.archive_old_movies, days=90)   # 90-day archive
    _, out = quiet(morning_report.overnight)

    titles = {mid: records[mid]['title'] for mid in held_ids}
    assert sorted(nrw.jw.film_queries()) == sorted(titles.values())   # every held film checked today
    assert "Held, checked daily until they come out: 3 (2 JustWatch has it, no offer yet, " \
           "1 JustWatch can't find it)" in out, out
    assert 'Put back today (came out after a hold): 3 — 1 need a date check (→ Concerns)' in out, out
    lines = out.splitlines()
    put_back = [line for line in lines if ' | held since ' in line]
    assert len(put_back) == 3, out
    epreuve = next(line for line in put_back if line.startswith("  • L'Épreuve du feu (2025) — "))
    # no date evidence and unchecked for months: dated today, flagged (v1 "kept 2026-11-07"),
    # in plain English (round 2b: the raw source key '(putback_review)' was printed)
    assert epreuve == ("  • L'Épreuve du feu (2025) — DATE NEEDS REVIEW — dated 2026-11-14 (no date evidence "
                       "— the day JustWatch confirmed it): weak evidence — the hold went unchecked, or TMDB "
                       "couldn't be reached | held since 2026-11-07 | wall"), epreuve
    assert 'putback_review' not in out
    assert ("  • Concorde (2025) — dated 2026-01-06 (TMDB's digital release date) "
            "| held since 2026-05-19 | archive (out more than 90 days)") in lines, out
    assert ("  • Christmas at Mistletoe Manor (2025) — dated 2026-11-14 (the day JustWatch first listed "
            "a way to watch it) | held since 2026-11-13 | wall") in lines, out
    assert put_back[0] == epreuve                 # the one to review is listed first
    assert CONCORDE in ids_of(nrw.archive()) and CONCORDE not in ids_of(nrw.wall())
    assert 'JustWatch trouble' not in out     # nothing went wrong this run


def test_morning_report_has_a_plain_english_label_for_every_put_back_date_source():
    """Fixed in round 2b (was a strict xfail): DATE_SOURCES had no label for putback.REVIEW
    ('putback_review'), so a DATE NEEDS REVIEW line showed the raw code name. Every put-back
    source and the owner's Revert hold reason now read as plain English."""
    missing = sorted(PUTBACK_SOURCES - set(morning_report.DATE_SOURCES))
    assert not missing, f'no plain-English label for {missing}'
    assert putback_mod.OWNER_REVERT in morning_report.HOLD_LABELS


def test_morning_report_shows_justwatch_trouble_during_discovery(nrw):
    """Round 2: discovery's JustWatch errors reach metrics/discovery_run.json and /morning
    (a JustWatch error leaves the film waiting; the owner must see that it happened)."""
    nrw.seed([LIFE_GOES_THIS_WAY, MISTLETOE], wall=prod_wall())
    nrw.jw.errors['Life Goes This Way'] = 'connection_error'
    nrw.jw.errors['Christmas at Mistletoe Manor'] = 'graphql_error'
    nrw.at(REPORT_DAY)
    nrw.discover()

    _, out = quiet(morning_report.overnight)

    assert ('⚠ JustWatch trouble during discovery (→ Concerns): 2 lookup error(s) — those films '
            'wait for the next run (no strike)') in out, out


def test_morning_report_flags_put_backs_that_are_hidden_or_missing(nrw):
    """Round 2 'where' column: a put-back hidden by enrichment for a JustWatch check is shown as
    waiting (and counted), one that is nowhere is a Concern -- never 'wall'. Round 2b: New
    Releases no longer calls such a film 'shown' (nor a pre-order arrival). (Report input built
    by hand: the morning report is read-only over these files.)"""
    mm, cc = tracking_rec(MISTLETOE), tracking_rec(CONCORDE)
    for rec, day in ((mm, '2026-11-14'), (cc, '2026-01-06')):
        rec.update(status='available', digital_date=day, _digital_date_source='jw_first_offer',
                   _put_back_on=TODAY, _held_since=rec['_jw_reverted_at'])
        for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at', '_skip_provider_discovery'):
            rec.pop(k, None)
    hidden = {'id': MISTLETOE, 'title': mm['title'], 'year': mm['year'], 'digital_date': '2026-11-14',
              'hidden': True, '_jw_unconfirmed': TODAY, '_enrichment_status': 'pending',
              '_discovered_at': '2026-11-14T06:40:00'}
    wall = prod_wall()
    for m in wall:
        if str(m['id']) == WICKER:            # a pre-order that reached the wall this morning (scenario)
            m['_discovered_at'] = '2026-11-14T06:41:00'
    nrw.write_tracking({MISTLETOE: mm, CONCORDE: cc})
    nrw.write_wall(wall + [hidden])
    nrw.write_archive(prod_archive())
    nrw.write_json('metrics/discovery_run.json', {'timestamp': REPORT_DAY, 'results': {}})
    nrw.at(REPORT_DAY)

    _, out = quiet(morning_report.overnight)

    lines = out.splitlines()
    assert 'New Releases: 2' in lines, out
    assert '  • Christmas at Mistletoe Manor (2025) — hidden — waiting for a JustWatch check' in lines, out
    assert '  • Wicker (2026) — pre-order' in lines, out
    assert ' — shown' not in out
    assert 'Waiting hidden for a JustWatch check (error or enrichment limit): 1 — re-checked first next run' in out
    assert ('  • Christmas at Mistletoe Manor (2025) — dated 2026-11-14 (the day JustWatch first listed a way '
            'to watch it) | held since 2026-11-13 | hidden — waiting for a JustWatch check') in out, out
    assert ('  • Concorde (2025) — dated 2026-01-06 (the day JustWatch first listed a way to watch it) '
            '| held since 2026-05-19 | NOT on the wall or archive — check (→ Concerns)') in out, out


# ==========================================================================
# (g) admin panel remove: status 'removed', so the purge treats it as one
#     (route unchanged in v2; owner decision Nov 15: Remove is for good -- a film that just
#     isn't out yet gets the new Revert instead, section i)
# ==========================================================================

def _admin_remove(nrw, mid):
    nrw.write_wall(prod_wall())
    nrw.write_tracking({i: tracking_rec(i) for i in (mid, JIMMY, MEETING_MARSHA)})
    from admin import create_app
    app = create_app()
    app.testing = True
    with app.test_client() as client:
        resp = client.post('/remove-movie', json={'movie_id': int(mid)})
    return resp.get_json()


def test_admin_remove_marks_the_film_removed_in_tracking(nrw):
    assert tracking_rec(THE_SECOND_ACT)['status'] == 'available'

    body = _admin_remove(nrw, THE_SECOND_ACT)

    assert body['success'] is True, body
    rec = nrw.tracking()[THE_SECOND_ACT]
    assert rec['status'] == 'removed' and rec['removed_reason'] == 'manual_removal'
    assert rec['removed_date'] == _dt.date.today().isoformat() and rec['digital_date'] is None
    assert THE_SECOND_ACT not in ids_of(nrw.wall())
    assert nrw.read_json('movie_tracking.json')['movies'][THE_SECOND_ACT]['status'] == 'removed'
    assert nrw.tracking()[JIMMY] == tracking_rec(JIMMY)


def test_admin_removed_film_is_purged_from_a_stale_in_memory_wall(nrw):
    stale = prod_wall()   # a display run that loaded data.json before the curator removed the film
    _admin_remove(nrw, THE_SECOND_ACT)

    kept, _ = quiet(nrw.generator().purge_removed_movies, stale)

    assert THE_SECOND_ACT not in ids_of(kept)
    assert THE_SECOND_ACT in ids_of(nrw.archive())
    assert len(kept) == len(stale) - 1


# ==========================================================================
# (h) round 2 -- discovery plumbing: JustWatch errors, canary, ordering, held pre-orders
# ==========================================================================

def _malformed_node(mid, title, year, how):
    """JustWatch answers HTTP 200 but the node is malformed, so verify_availability raises
    AFTER search_movie returned (last_error unset)."""
    if how == 'offers_null':
        return [jw_node(mid, title, year, None)]                      # TypeError
    offers = amazon(mid, '2026-11-14')
    offers[0]['package'] = None                                        # AttributeError
    return [jw_node(mid, title, year, offers)]


@pytest.mark.parametrize('failure', ['offers_null', 'package_null', 'connection_error', 'graphql_error',
                                     'outage'])
def test_a_justwatch_failure_on_a_held_film_is_no_strike_and_it_keeps_waiting(nrw, failure):
    """Rule 5. Life Goes This Way: held since 2026-07-10 under the old permanent skip; TMDB lists
    rent/buy. Whatever goes wrong with JustWatch -- an exception in the lookup (was: fail-OPEN
    onto the wall), an API error, or an outage the canary sees -- it stays held, no strike, and
    keeps the old skip flag (dating needs to know it went unchecked)."""
    before = tracking_rec(LIFE_GOES_THIS_WAY)
    assert before['_skip_provider_discovery'] and before['_jw_revert_count'] == 4
    nrw.seed([LIFE_GOES_THIS_WAY], wall=prod_wall())
    title = before['title']
    if failure in ('offers_null', 'package_null'):
        nrw.jw.nodes[title] = _malformed_node(LIFE_GOES_THIS_WAY, title, before['year'], failure)
    elif failure == 'outage':
        nrw.jw.down = 'blocked'          # HTTP 200, zero results for every title (blocked IP)
    else:
        nrw.jw.errors[title] = failure
    nrw.at(DAY)

    _, out = nrw.discover()

    rec = nrw.tracking()[LIFE_GOES_THIS_WAY]
    assert title in nrw.jw.film_queries()
    assert rec['status'] == 'tracking'
    assert (rec['_jw_revert_count'], rec['_jw_revert_reason']) == (4, 'justwatch_no_valid_offers')
    assert rec['_skip_provider_discovery'] is True
    assert '_jw_last_checked' not in rec and '_jw_last_refuted' not in rec   # nothing was learned
    assert rec['digital_date'] == '2026-07-10'
    assert LIFE_GOES_THIS_WAY not in ids_of(nrw.wall()) and nrw.queued() == []
    m = nrw.metrics()['results']
    if failure == 'outage':
        assert 'JW unreachable, leaving in tracking (no strike)' in out
        assert (m['jw_lookups'], m['jw_errors'], m['jw_healthy']) == (1, 0, False)
    else:
        assert f'{title} — JustWatch error' in out and 'leaving in tracking (no strike)' in out
        assert (m['jw_lookups'], m['jw_errors']) == (1, 1)


def test_a_justwatch_exception_never_puts_a_new_film_on_the_wall(nrw):
    """Rule 5, a film with no hold history. Traces of Justice: TMDB starts listing an Amazon
    rental (scenario) and JustWatch's node is malformed. v1 / round 1 failed OPEN here
    ({'verified': True, '_fail_open': True}) and put it on the wall unchecked."""
    nrw.seed([TRACES_OF_JUSTICE], wall=prod_wall())
    nrw.tmdb.set_providers(TRACES_OF_JUSTICE, rent=['Amazon Video'], buy=['Amazon Video'])
    nrw.jw.nodes['Traces of Justice'] = _malformed_node(TRACES_OF_JUSTICE, 'Traces of Justice', 2026, 'offers_null')
    nrw.at(DAY)

    _, out = nrw.discover()

    rec = nrw.tracking()[TRACES_OF_JUSTICE]
    assert rec['status'] == 'tracking' and '_jw_revert_count' not in rec
    assert TRACES_OF_JUSTICE not in ids_of(nrw.wall()) and nrw.queued() == []
    assert nrw.pages.visited == []                       # nothing went on to the store-page check
    assert rec['digital_date'] == TODAY                  # its first-signal day is kept (no hold)
    assert nrw.metrics()['results']['jw_errors'] == 1


def test_first_signal_date_survives_a_justwatch_error_for_a_film_with_no_hold(nrw):
    """Rule 4. Accursed: on day D TMDB first lists an Amazon rental (scenario) but JustWatch
    errors; on D+1 JustWatch confirms. It is dated D, the day it came out -- not D+1, the
    day JustWatch recovered (round 1 undid the date for every film)."""
    nrw.seed([ACCURSED], wall=prod_wall())
    nrw.tmdb.set_providers(ACCURSED, rent=['Amazon Video'], buy=['Amazon Video'])
    nrw.jw.errors['Accursed'] = 'connection_error'
    nrw.at(DAY)
    nrw.discover()
    d0 = nrw.tracking()[ACCURSED]
    assert d0['status'] == 'tracking' and d0['digital_date'] == TODAY and '_jw_revert_count' not in d0

    nrw.at(NEXT_DAY)                                     # next day, a new pipeline process
    del nrw.jw.errors['Accursed']
    nrw.jw_has(ACCURSED, amazon(ACCURSED, TODAY))
    nrw.discover()

    rec = nrw.tracking()[ACCURSED]
    assert rec['status'] == 'available' and rec['digital_date'] == TODAY
    assert '_put_back_on' not in rec and rec.get('_digital_date_source') not in PUTBACK_SOURCES
    assert nrw.wall_entry(ACCURSED)['digital_date'] == TODAY


def test_a_justwatch_error_undoes_a_held_films_speculative_date_and_evidence_dates_it_later(nrw):
    """Rules 4+5, a held film. Foreigner (returned screening): on day D TMDB's Eventive listing
    sends it to JustWatch, which errors -- the provider path's speculative 'today' is undone
    (a hold never moves the date). On D+1 JustWatch confirms; JustWatch's own record (D)
    dates the put-back."""
    _screenings_on_wall(nrw, only={FOREIGNER})           # day D
    gen = nrw.generator()
    quiet(gen.check_virtual_screening_expirations)
    nrw.jw.errors['Foreigner'] = 'connection_error'
    nrw.discover(gen)
    d0 = nrw.tracking()[FOREIGNER]
    assert d0['status'] == 'tracking' and 'digital_date' not in d0 and '_jw_revert_count' not in d0

    nrw.at(NEXT_DAY)
    del nrw.jw.errors['Foreigner']
    nrw.jw_has(FOREIGNER, amazon(FOREIGNER, TODAY))
    nrw.discover()

    after = nrw.tracking()[FOREIGNER]
    assert after['status'] == 'available'
    assert (after['digital_date'], after['_digital_date_source']) == (TODAY, 'jw_first_offer')
    assert after['_put_back_on'] == TOMORROW and not after.get('_date_needs_review')


def test_the_health_canary_needs_real_offers_for_a_control_title(nrw):
    """Round 2: JustWatch counts as healthy only if a control title comes back WITH offers --
    an outage can return titles with empty offer lists (every answer then reads 'no offer')."""
    nrw.at(DAY)
    disc = nrw.generator()._discoverer

    def canary(down):
        nrw.jw.down = down
        disc._jw_healthy, disc._jw_healthy_at = None, 0.0
        healthy, _ = quiet(disc._check_jw_health)
        return healthy

    assert canary('offers') is False
    assert canary('blocked') is False
    assert canary(None) is True
    assert set(nrw.jw.queries) == CANARY_TITLES


@pytest.mark.parametrize('justwatch', ['healthy', 'offers_outage'])
def test_a_no_offer_answer_counts_only_when_the_canary_says_justwatch_works(nrw, justwatch):
    """Round 2: the canary is consulted for EVERY unverified answer, not only 'no match'.
    Mistletoe (no offer on 11-13) gets 'no offer' again: with JustWatch healthy that is a
    real 'not out yet' day; during an offers outage it is no strike and records nothing."""
    nrw.seed([MISTLETOE], wall=prod_wall())
    nrw.jw_has(MISTLETOE, [])
    if justwatch == 'offers_outage':
        nrw.jw.down = 'offers'
    nrw.at(DAY)

    nrw.discover()

    rec = nrw.tracking()[MISTLETOE]
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'justwatch_no_valid_offers'
    assert 'Oppenheimer' in nrw.jw.queries                           # the canary ran
    if justwatch == 'healthy':
        assert rec['_jw_revert_count'] == 2
        assert rec['_jw_last_checked'] == rec['_jw_last_refuted'] == TODAY
        assert nrw.metrics()['results']['jw_healthy'] is True
    else:
        assert rec['_jw_revert_count'] == 1
        assert '_jw_last_checked' not in rec and '_jw_last_refuted' not in rec
        assert nrw.metrics()['results']['jw_healthy'] is False


def test_a_title_mismatch_is_recorded_as_no_match_not_as_no_offer(nrw):
    """Round 2: when the title search hands back ANOTHER film (verify_availability's
    match_confidence 'first_result'), JustWatch didn't find ours: 'no match', which proves
    nothing about availability -- not 'no valid offers', and no 'not out yet' day."""
    nrw.seed([MISTLETOE], wall=prod_wall())
    other = jw_node('9999999', 'Christmas at Mistletoe Farm', 2025, amazon('9999999', '2026-11-01'))
    real_search = JustWatchClient.search_movie

    def search_movie(self, title, *args, **kwargs):
        if title == 'Christmas at Mistletoe Manor':
            return copy.deepcopy(other)
        return real_search(self, title, *args, **kwargs)

    nrw.mp.setattr(JustWatchClient, 'search_movie', search_movie)
    nrw.at(DAY)

    nrw.discover()

    rec = nrw.tracking()[MISTLETOE]
    assert rec['status'] == 'tracking' and MISTLETOE not in ids_of(nrw.wall())
    assert (rec['_jw_revert_reason'], rec['_jw_revert_count']) == ('justwatch_no_match', 2)
    assert rec['_jw_last_checked'] == TODAY and rec.get('_jw_last_refuted') != TODAY


def test_a_legacy_no_offer_day_survives_a_later_no_match(nrw):
    """Christmas at Mistletoe Manor: JustWatch had it with no offer on 2026-11-13 (production
    record); TMDB lists 11-13 as its digital date (scenario). 11-14: JustWatch can't find it.
    11-15: JustWatch confirms it, first recorded that day. 11-13 was proven 'not out yet', so
    the put-back must be dated after it: 11-15."""
    assert putback_mod.last_refuted_day(tracking_rec(MISTLETOE), TODAY) == '2026-11-13'
    nrw.seed([MISTLETOE], wall=prod_wall())
    nrw.tmdb.set_type4(MISTLETOE, '2026-11-13')
    nrw.at(DAY)
    nrw.discover()                                      # 11-14: no match (no JustWatch node)
    assert nrw.tracking()[MISTLETOE]['_jw_revert_reason'] == 'justwatch_no_match'

    nrw.at(NEXT_DAY)
    nrw.jw_has(MISTLETOE, amazon(MISTLETOE, TOMORROW))
    nrw.discover()

    rec = nrw.tracking()[MISTLETOE]
    assert rec['status'] == 'available'
    assert rec['digital_date'] > '2026-11-13', f"dated {rec['digital_date']} ({rec['_digital_date_source']})"


def test_held_films_are_checked_after_every_other_film(nrw):
    """Round 2: held films (~600 JustWatch lookups a run) go after everything else, so today's
    releases reach JustWatch first; date order is kept inside each group."""
    nrw.seed([MISTLETOE, HARLEM, ACCURSED, TRACES_OF_JUSTICE], wall=prod_wall())
    for mid in (ACCURSED, TRACES_OF_JUSTICE):           # scenario: TMDB lists a rental for both today
        nrw.tmdb.set_providers(mid, rent=['Amazon Video'])
    nrw.at(DAY)                                         # JustWatch finds none of them

    nrw.discover()

    order = nrw.jw.film_queries()
    assert sorted(order[:2]) == ['Accursed', 'Traces of Justice']          # no hold: first
    assert order[2:] == ['Christmas at Mistletoe Manor', 'Once Upon a Time in Harlem']  # held: 11-13, 10-30


@pytest.mark.parametrize('case, offers, goes_on, dated', [
    ('fandango-rental', lambda m: fandango(m, '2026-11-10'), False, None),
    ('amazon-rental-starts-on-tmdb-date', lambda m: amazon(m, '2026-11-10', '2026-11-17T08:00:00Z'), False, None),
    ('amazon-rental-live', lambda m: amazon(m, '2026-11-10', '2026-11-10T08:00:00Z'), True, '2026-11-10'),
    ('streaming', lambda m: streaming('Hulu', 'https://www.hulu.com/movie/liberation-test', '2026-11-12'),
     True, '2026-11-12'),
], ids=lambda v: v if isinstance(v, str) else None)
def test_a_held_film_with_a_future_tmdb_date_is_checked_daily_and_goes_on_early_only_when_watchable(
        nrw, case, offers, goes_on, dated):
    """Round 2 (rules 2+3): Liberation is held (no offer, 2026-09-15) with TMDB's date 11-17
    still ahead. It is no longer skipped: JustWatch checks it every run. It goes on early only if
    JustWatch shows it watchable NOW (streaming, or a live rental); a store's listing that isn't
    live yet waits for its date -- remembered as a 'not out yet' day."""
    before = tracking_rec(LIBERATION)
    assert before['_type4_pending'] and before['digital_date'] == '2026-11-17' and before['_jw_revert_count'] == 1
    nrw.seed([LIBERATION], wall=prod_wall())
    nrw.tmdb.set_type4(LIBERATION, '2026-11-17')        # scenario: TMDB still says 11-17
    nrw.jw_has(LIBERATION, offers(LIBERATION))
    nrw.at(DAY)

    _, out = nrw.discover()

    rec = nrw.tracking()[LIBERATION]
    assert nrw.jw.film_queries() == ['Liberation']
    if not goes_on:
        assert rec['status'] == 'tracking' and rec['digital_date'] == '2026-11-17'
        assert rec['_type4_pending'] and rec['_is_preorder'] and rec['_jw_revert_count'] == 1
        assert rec['_jw_last_checked'] == rec['_jw_last_refuted'] == TODAY
        assert '_put_back_on' not in rec and LIBERATION not in ids_of(nrw.wall())
        assert "but nothing is live yet; waiting" in out
    else:
        assert rec['status'] == 'available' and rec['_put_back_on'] == TODAY
        assert (rec['digital_date'], rec['_digital_date_source']) == (dated, 'jw_first_offer')
        assert '_type4_pending' not in rec and '_is_preorder' not in rec
        entry = nrw.wall_entry(LIBERATION)
        assert entry['digital_date'] == dated and not entry.get('_is_preorder') and not entry.get('hidden')


def test_a_apple_store_rental_does_not_let_a_held_film_with_a_future_tmdb_date_go_on(nrw):
    """Round 2c: Apple's store lists rentals from the theater opening (its offer start is the
    theatrical date), so it is not proof a film is out. Liberation (held, TMDB still says 11-17)
    with only an Apple store rental waits for its TMDB date, as before Step 1 (2b put it on
    early, dated by the listing's record: the skeptic's Liberation case)."""
    nrw.seed([LIBERATION], wall=prod_wall())
    nrw.tmdb.set_type4(LIBERATION, '2026-11-17')
    nrw.jw_has(LIBERATION, apple(LIBERATION, '2026-11-10', '2026-11-10T08:00:00Z'))
    nrw.at(DAY)

    _, out = nrw.discover()

    rec = nrw.tracking()[LIBERATION]
    assert rec['status'] == 'tracking' and rec['digital_date'] == '2026-11-17'
    assert rec.get('_type4_pending') and 'nothing is live yet' in out
    assert '_put_back_on' not in rec


# The offer JustWatch returns for each case (package clearName / technicalName as in its raw
# replies; 'Apple iTunes' is the store's older clearName, 'Apple TV' + 'atp' the former Apple TV+).
_LIVE_RENT_CASES = {
    'apple-store-rent': (lambda m: [apple(m, '2026-11-10')[0]], False),
    'apple-store-by-technical-name': (lambda m: [dict(apple(m, '2026-11-10')[0], package={
        'clearName': 'Apple iTunes', 'technicalName': 'itunes'})], False),
    'amazon-rent-live': (lambda m: [amazon(m, '2026-11-10', '2026-11-10T08:00:00Z')[0]], True),
    'amazon-rent-starts-later': (lambda m: [amazon(m, '2026-11-10', '2026-11-17T08:00:00Z')[0]], False),
    'amazon-rent-no-start': (lambda m: [dict(amazon(m, '2026-11-10')[0], availableFromTime=None)], False),
    'fandango-rent': (lambda m: [fandango(m, '2026-11-10')[0]], False),
    'apple-store-buy-only': (lambda m: [apple(m, '2026-11-10')[1]], False),
    'apple-tv-plus-streaming': (lambda m: [dict(jw_offer('FLATRATE', 'Apple TV', 'https://tv.apple.com/us/movie/x',
                                                         None, '2026-11-10'),
                                                package={'clearName': 'Apple TV', 'technicalName': 'atp'})], False),
}


@pytest.mark.parametrize('case', list(_LIVE_RENT_CASES))
def test_has_live_rent_reads_justwatchs_own_store_names(nrw, case):
    """The JustWatch client's own parsing: a rental counts as live NOW only for Amazon once its
    offer start has passed (round 2c). Other stores list pre-order rentals as plain RENT offers,
    Apple's store included (from the theater opening, its offer start the theatrical date)."""
    offers, live = _LIVE_RENT_CASES[case]
    nrw.jw.film(LIBERATION, 'Liberation', 2026, offers(LIBERATION))
    nrw.at(DAY)

    r = JustWatchClient().verify_availability('Liberation', 2026, tmdb_id=LIBERATION)

    assert r['match_confidence'] == 'exact_year'
    assert r['has_live_rent'] is live
    assert r['has_streaming'] is (case == 'apple-tv-plus-streaming')


@pytest.mark.parametrize('justwatch', ['confirms', 'no-offer'])
def test_a_held_film_is_checked_even_when_tmdbs_provider_lookup_fails_and_keeps_its_providers(
        nrw, justwatch):
    """Round 2: Once Upon a Time in Harlem is held (no offer x2); today TMDB's watch/providers
    lookup fails (HTTP 500). JustWatch still decides for it, and the providers on record are
    kept, not wiped by the failed TMDB call."""
    before = tracking_rec(HARLEM)
    nrw.seed([HARLEM], wall=prod_wall())
    nrw.tmdb.failures[(HARLEM, 'watch/providers')] = 500
    cinema = [jw_offer('CINEMA', 'Atom Tickets', 'https://www.atomtickets.com/movies/harlem/408240')]
    nrw.jw_has(HARLEM, cinema + (amazon(HARLEM, '2026-11-12') if justwatch == 'confirms' else []))
    nrw.at(DAY)

    nrw.discover()

    rec = nrw.tracking()[HARLEM]
    assert nrw.jw.film_queries() == ['Once Upon a Time in Harlem']
    assert rec['providers'] == before['providers'] == {'rent': [], 'buy': ['Fandango At Home'], 'streaming': []}
    errors = nrw.metrics()['api_errors']
    assert [(e['movie_id'], e['error_type'], e['status_code']) for e in errors] == [(HARLEM, 'http_error', 500)]
    if justwatch == 'confirms':
        assert rec['status'] == 'available'
        assert (rec['digital_date'], rec['_digital_date_source']) == ('2026-11-12', 'jw_first_offer')
    else:
        assert rec['status'] == 'tracking' and rec['_jw_revert_count'] == 3
        assert rec['digital_date'] == before['digital_date']


def test_backlog_limit_is_25_put_backs_a_run_returned_screenings_included(nrw):
    """Round 2: at most 25 long-held films (old permanent skips, 4+ strikes, AND returned
    festival screenings) are put back per run, so enrichment's 100-film cap goes to the day's
    releases. The rest wait -- no strike, no date -- and keep landing on later runs (rule 1)."""
    assert ProviderDiscoverer.MAX_BACKLOG_PUTBACKS_PER_RUN >= 10 ** 5   # no trickle (owner, Nov 2026)
    wall, _ = _screenings_on_wall(nrw)
    gen = nrw.generator()
    quiet(gen.check_virtual_screening_expirations)
    trk = nrw.tracking()
    returned = [mid for mid, r in trk.items() if r['status'] == 'tracking' and r.get('_screening_expired')]
    assert len(returned) >= 150
    for mid in returned:                                  # scenario: every one now streams on Kanopy
        nrw.jw_has(mid, streaming('Kanopy', f'https://www.kanopy.com/en/product/{mid}', '2026-11-10'))
    # plus one of today's releases, which no backlog limit may hold up
    trk[ACCURSED] = tracking_rec(ACCURSED)
    nrw.write_tracking(trk)
    nrw.tmdb.set_providers(ACCURSED, rent=['Amazon Video'])
    nrw.jw_has(ACCURSED, amazon(ACCURSED, TODAY))

    _, out = nrw.discover(gen)

    after = nrw.tracking()
    back = [m for m in returned if after[m]['status'] == 'available']
    assert len(back) == len(returned), f'{len(back)} of {len(returned)} put back in one run'
    assert all(after[m]['_put_back_on'] == TODAY for m in back)
    assert 'queued for the next run' not in out
    assert after[ACCURSED]['status'] == 'available'
    assert nrw.queued()[0] == ACCURSED                    # today's release first in enrichment's queue


def test_a_moved_tmdb_date_moves_the_pre_order_entry_and_never_creates_one(nrw):
    """Round 2: Wicker's TMDB date moved 12-01 -> 11-24 (finding from the dry run): its
    PRE-ORDER lane entry moves too (a stale later date let enrichment graduate it unchecked).
    Ensurance Trap (held, not on the wall) gets the new date in tracking only: no wall entry
    is ever created for it (v1 re-added such pre-orders nightly; removed in v2)."""
    assert wall_rec(WICKER)['digital_date'] == '2026-12-01' and wall_rec(WICKER)['_is_preorder']
    assert ENSURANCE_TRAP not in ids_of(prod_wall())
    nrw.seed([WICKER, ENSURANCE_TRAP], wall=prod_wall())
    nrw.tmdb.set_type4(WICKER, '2026-11-24')             # scenario: TMDB moved both dates
    nrw.tmdb.set_type4(ENSURANCE_TRAP, '2027-06-01')
    nrw.at(DAY)

    gen, out = nrw.discover()

    wicker, trap = nrw.tracking()[WICKER], nrw.tracking()[ENSURANCE_TRAP]
    assert (wicker['status'], wicker['digital_date'], wicker['_type4_pending']) == ('tracking', '2026-11-24', True)
    entry = nrw.wall_entry(WICKER)
    assert (entry['digital_date'], entry['_digital_date_source'], entry['_is_preorder']) == (
        '2026-11-24', 'tmdb_type4', True)
    # a date-only update: nothing else in that entry, and no other entry, changed
    before = {str(m['id']): m for m in prod_wall()}
    assert {k: v for k, v in entry.items() if k not in ('digital_date', '_digital_date_source')} == {
        k: v for k, v in before[WICKER].items() if k not in ('digital_date', '_digital_date_source')}
    assert [m for m in nrw.wall() if str(m['id']) != WICKER] == [m for m in prod_wall() if str(m['id']) != WICKER]
    assert 'Wicker — TMDB digital date moved 2026-12-01 → 2026-11-24' in out
    assert 'Wicker' not in nrw.jw.film_queries()          # not held: its pre-order lane needs no JustWatch
    assert trap['digital_date'] == '2027-06-01' and trap['status'] == 'tracking'
    assert ENSURANCE_TRAP not in ids_of(nrw.wall())
    assert 'Ensurance Trap' in nrw.jw.film_queries()      # held: checked every run regardless
    assert nrw.queued() == []
    assert gen.update_wall_entry_date(WICKER, '2026-11-24') is False          # nothing to move
    assert gen.update_wall_entry_date(ENSURANCE_TRAP, '2027-06-01') is False  # never creates one
    assert ENSURANCE_TRAP not in ids_of(nrw.wall())


def test_a_returned_screenings_festival_date_on_tmdb_is_not_its_release_date(nrw):
    """Round 2: TMDB sometimes lists the festival screening itself as a digital release
    (scenario: Foreigner's Type 4 = 2026-11-01, its Eventive opening). A TMDB date on or before
    the screening's last day (_screening_ended 11-07) is ignored: JustWatch's first record of a
    real rental (11-12) dates the put-back."""
    _screenings_on_wall(nrw, only={FOREIGNER})
    nrw.tmdb.set_type4(FOREIGNER, '2026-11-01')
    gen = nrw.generator()
    quiet(gen.check_virtual_screening_expirations)
    assert nrw.tracking()[FOREIGNER]['_screening_ended'] == '2026-11-07'
    nrw.jw_has(FOREIGNER, amazon(FOREIGNER, '2026-11-12'))

    nrw.discover(gen)

    rec = nrw.tracking()[FOREIGNER]
    assert rec['status'] == 'available' and rec['_discovery_source'] == 'tmdb_type4'
    assert (rec['digital_date'], rec['_digital_date_source']) == ('2026-11-12', 'jw_first_offer')
    assert rec['_date_before_putback'] == '2026-11-01'


@pytest.mark.parametrize('jw_record, source', [('2000-07-14', 'jw_first_verified'), (TODAY, 'jw_first_offer')],
                         ids=['dated-by-check-day', 'dated-by-justwatch-record'])
@pytest.mark.parametrize('tmdb', ['answers', 'fails'])
def test_a_tmdb_release_dates_failure_flags_the_put_back_for_review_whatever_its_source(
        nrw, tmdb, jw_record, source):
    """Round 2: fetch_tmdb_us_release_dates returns None (not a pair of Nones) when TMDB can't
    answer, so an unknown TMDB date isn't read as 'none'. Mistletoe (checked daily, no offer on
    11-13) is confirmed today: dated by JustWatch's record of the offer, or -- with no record
    date (JustWatch's 2000-07-14 placeholder) -- today as a daily-check day. Round 2b: flagged
    for review whenever TMDB couldn't be asked, whatever the source (a JustWatch record date
    is unguarded too: the theater-week check needs TMDB's dates); never when TMDB answered."""
    nrw.seed([MISTLETOE], wall=prod_wall())
    if tmdb == 'fails':
        nrw.tmdb.failures[(MISTLETOE, 'release_dates')] = 500
    nrw.jw_has(MISTLETOE, amazon(MISTLETOE, jw_record, '2026-11-14T05:00:00Z'))
    nrw.at(DAY)

    _, out = nrw.discover()

    rec = nrw.tracking()[MISTLETOE]
    assert rec['status'] == 'available' and rec['_put_back_on'] == TODAY
    assert (rec['digital_date'], rec['_digital_date_source']) == (TODAY, source)
    assert rec.get('_date_needs_review') is (True if tmdb == 'fails' else None)
    assert ('date flagged for review' in out) is (tmdb == 'fails')


def test_a_held_film_streaming_on_sundance_now_is_not_taken_for_a_festival_screening(nrw):
    """Round 2: the festival platforms left out of a held film's JustWatch check are Eventive
    and Shift72 only. 'Sundance' matched (as a substring) the streaming service Sundance Now,
    so a held film streaming there was never confirmed."""
    assert discoverer_mod.FESTIVAL_PLATFORMS == ['Eventive', 'Shift72']
    nrw.seed([HARLEM], wall=prod_wall())
    nrw.jw_has(HARLEM, streaming('Sundance Now', 'https://www.sundancenow.com/movies/harlem-test', '2026-11-12'))
    nrw.at(DAY)

    nrw.discover()

    rec = nrw.tracking()[HARLEM]
    assert rec['status'] == 'available'
    assert (rec['digital_date'], rec['_digital_date_source']) == ('2026-11-12', 'jw_first_offer')


def test_the_last_not_out_yet_day_survives_the_put_back(nrw):
    """Round 2: the transition clears the hold fields, so the last 'not out yet' day is stored
    first (_jw_last_refuted) -- a later pull can never date the film on or before it."""
    nrw.seed([MISTLETOE], wall=prod_wall())
    nrw.jw_has(MISTLETOE, amazon(MISTLETOE, TODAY))
    nrw.at(DAY)

    nrw.discover()

    rec = nrw.tracking()[MISTLETOE]
    assert rec['status'] == 'available' and rec['digital_date'] == TODAY
    assert not any(k in rec for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'))
    assert rec['_jw_last_refuted'] == '2026-11-13'
    assert putback_mod.last_refuted_day(rec, TOMORROW) == '2026-11-13'


def test_a_store_pre_order_page_holds_a_confirmed_film_and_that_day_is_never_its_release_date(nrw):
    """Round 2 (rules 1+4): JustWatch confirms Mistletoe (held, no offer on 11-13) with an Amazon
    rental it recorded 11-14, but the store page reads "Pre-order": it stays held (its hold
    history intact, the pending put-back dropped) and 11-14 is remembered as a 'not out yet'
    day. On 11-15 the page reads available: it goes on dated 11-15, the day after -- not 11-14,
    JustWatch's record of what was then a pre-order listing."""
    nrw.seed([MISTLETOE], wall=prod_wall())
    before = tracking_rec(MISTLETOE)
    nrw.jw_has(MISTLETOE, amazon(MISTLETOE, TODAY))
    nrw.pages.text = FakeStorePages.PREORDER
    nrw.at(DAY)

    nrw.discover()

    rec = nrw.tracking()[MISTLETOE]
    assert nrw.pages.visited and 'amazon.com' in nrw.pages.visited[0]
    assert rec['status'] == 'tracking' and '_put_back_on' not in rec
    assert rec['_rent_preorder_held'] == rec['_jw_last_refuted'] == TODAY
    assert (rec['_jw_revert_count'], rec['_jw_revert_reason'], rec['digital_date']) == (
        before['_jw_revert_count'], before['_jw_revert_reason'], before['digital_date'])
    assert nrw.metrics()['results']['rent_preorders_held'] == 1 and nrw.queued() == []

    nrw.at(NEXT_DAY)
    nrw.pages.text = FakeStorePages.AVAILABLE
    nrw.discover()

    rec = nrw.tracking()[MISTLETOE]
    assert rec['status'] == 'available' and rec['_put_back_on'] == TOMORROW
    assert (rec['digital_date'], rec['_digital_date_source']) == (TOMORROW, 'putback_after_hold')
    assert not rec.get('_date_needs_review') and '_rent_preorder_held' not in rec
    assert rec['_jw_last_refuted'] == TODAY
    assert nrw.wall_entry(MISTLETOE)['digital_date'] == TOMORROW


def test_justwatch_lookups_and_errors_are_counted_in_the_discovery_metrics(nrw):
    """Round 2 metrics: every JustWatch lookup (incl. the buy-only daily check) and every lookup
    that failed (left waiting, no strike) reach metrics/discovery_run.json."""
    nrw.seed([LIFE_GOES_THIS_WAY, MISTLETOE, HARLEM, QUEEN_AT_SEA], wall=prod_wall())
    nrw.jw.nodes['Life Goes This Way'] = _malformed_node(LIFE_GOES_THIS_WAY, 'Life Goes This Way', 2025, 'package_null')
    nrw.jw.errors['Christmas at Mistletoe Manor'] = 'timeout'
    nrw.jw_has(HARLEM, [])                                          # answered: no offer (a strike)
    nrw.tmdb.set_providers(QUEEN_AT_SEA, buy=['Fandango At Home'])  # its record's provider, as TMDB lists it
    nrw.jw_has(QUEEN_AT_SEA, [fandango(QUEEN_AT_SEA, '2026-11-01')[1]])  # still buy-only on JustWatch
    nrw.pages.text = ''   # Fandango's page can't be read: a Fandango-only listing waits (no extra lookup)
    nrw.at(DAY)

    nrw.discover()

    m = nrw.metrics()['results']
    assert (m['jw_lookups'], m['jw_errors'], m['jw_healthy']) == (4, 2, True)
    trk = nrw.tracking()
    assert trk[HARLEM]['_jw_revert_count'] == 3
    assert trk[QUEEN_AT_SEA]['_buyonly_preorder'] and trk[QUEEN_AT_SEA]['_jw_last_checked'] == TODAY
    assert trk[MISTLETOE]['_jw_revert_count'] == 1 and trk[LIFE_GOES_THIS_WAY]['_jw_revert_count'] == 4


# --- the buy-only daily check (_jw_shows_rent_or_stream / _buyonly_still_waiting) ---

QUEEN_TITLE = 'Queen at Sea'


def _queen_on_justwatch(nrw, how):
    """JustWatch's answer for Queen at Sea (a buy-only pre-order on the PRE-ORDER lane, no
    date) in each case."""
    mid = QUEEN_AT_SEA
    buy = [fandango(mid, '2026-11-01')[1]]          # its Fandango purchase, still its only offer
    if how in ('still-buy-only', 'tmdb-providers-down'):
        nrw.jw_has(mid, buy)
    elif how == 'no-offer':
        nrw.jw_has(mid, [])
    elif how == 'offers-outage':
        nrw.jw_has(mid, buy)
        nrw.jw.down = 'offers'                      # every title, canary included, comes back offer-less
    elif how == 'title-mismatch':
        other = jw_node('9999998', 'Queen of the Sea', 2026, apple('9999998', '2026-11-01'))
        real_search = JustWatchClient.search_movie

        def search_movie(self, title, *args, **kwargs):
            if title != QUEEN_TITLE:
                return real_search(self, title, *args, **kwargs)
            nrw.jw.queries.append(title)               # the lookup happened (another film came back)
            return copy.deepcopy(other)

        nrw.mp.setattr(JustWatchClient, 'search_movie', search_movie)
    elif how == 'malformed':
        nrw.jw.nodes[QUEEN_TITLE] = _malformed_node(mid, QUEEN_TITLE, 2026, 'offers_null')
    elif how in ('connection_error', 'graphql_error'):
        nrw.jw.errors[QUEEN_TITLE] = how
    else:
        assert how == 'no-match'                    # JustWatch can't find it


@pytest.mark.parametrize('how', ['still-buy-only', 'no-offer', 'tmdb-providers-down', 'offers-outage',
                                 'no-match', 'title-mismatch', 'malformed', 'connection_error', 'graphql_error'])
def test_the_buy_only_daily_check_records_a_not_out_yet_day_only_on_a_real_answer(nrw, how):
    """Round 2 + 2b: a buy-only pre-order is checked on JustWatch every run. Only a real answer
    ('still buy-only', or 'no offer' while the canary says JustWatch works) stamps the check
    and records the day as 'not out yet' (no later put-back is dated on it). An offers outage
    (round 2b: the canary is consulted for a no-offer reply here too), a no-match, a title
    mismatch, or a JustWatch error records nothing. It waits on the PRE-ORDER lane either way;
    with TMDB's provider lookup down it is still checked, and its providers are kept."""
    before = tracking_rec(QUEEN_AT_SEA)
    assert before['_buyonly_preorder'] and not before.get('digital_date')
    nrw.seed([QUEEN_AT_SEA], wall=prod_wall())
    nrw.pages.text = ''   # Fandango At Home's pages can't be read (real): a Fandango-only listing waits
    if how == 'tmdb-providers-down':
        nrw.tmdb.failures[(QUEEN_AT_SEA, 'watch/providers')] = 500
    _queen_on_justwatch(nrw, how)
    nrw.at(DAY)

    nrw.discover()

    rec = nrw.tracking()[QUEEN_AT_SEA]
    assert nrw.jw.film_queries() == [QUEEN_TITLE]                     # checked today
    assert rec['status'] == 'tracking' and rec['_buyonly_preorder'] is True and 'digital_date' not in rec
    answered = how in ('still-buy-only', 'no-offer', 'tmdb-providers-down')
    if answered:
        assert rec['_jw_last_checked'] == rec['_jw_last_refuted'] == TODAY
    else:
        assert '_jw_last_checked' not in rec and '_jw_last_refuted' not in rec   # nothing was learned
    assert ('Oppenheimer' in nrw.jw.queries) is (how in ('no-offer', 'offers-outage'))  # canary only for no offers
    assert nrw.metrics()['results']['jw_healthy'] is {'no-offer': True, 'offers-outage': False}.get(how)
    assert rec['providers'] == before['providers'] and '_jw_revert_count' not in rec
    assert nrw.wall_entry(QUEEN_AT_SEA) == wall_rec(QUEEN_AT_SEA)    # still the same pre-order entry
    # The pre-order labeler reads the store page for a Fandango purchase (unreadable: it waits).
    listed = how in ('still-buy-only', 'tmdb-providers-down', 'offers-outage')
    assert nrw.queued() == [] and bool(nrw.pages.visited) is (listed and how != 'offers-outage'), nrw.pages.visited


_BUYONLY_API_ERRORS_UNCOUNTED = (
    "DEFECT (reporting): ProviderDiscoverer._jw_shows_rent_or_stream counts a JustWatch error in "
    "_jw_errors only when verify_availability RAISES. An API/network error (search_movie returns None "
    "with last_error set: connection error, timeout, HTTP 429, GraphQL error) returns None uncounted -- "
    "_verify_before_wall counts the same case. Those failed lookups never reach metrics jw_errors, so "
    "a run in which the buy-only checks (28 buy-only pre-orders in tracking at 78303fd6) hit API errors "
    "shows no 'JustWatch trouble' line in /morning unless some other lookup failed too.")


@pytest.mark.parametrize('failure', [
    'malformed',
    'connection_error',  # (round 2b: strict xfail -- API errors were uncounted; fixed in 2c)
    'graphql_error',  # (round 2b: strict xfail -- API errors were uncounted; fixed in 2c)
])
def test_a_justwatch_error_in_the_buy_only_check_reaches_the_metrics_and_the_morning_report(nrw, failure):
    """Round 2: every JustWatch lookup that failed (the film left waiting, no strike) is counted
    in metrics/discovery_run.json jw_errors -- the buy-only daily check's included -- so /morning
    can tell the owner that JustWatch had trouble."""
    nrw.seed([QUEEN_AT_SEA], wall=prod_wall())
    _queen_on_justwatch(nrw, failure)
    nrw.at(DAY)
    nrw.discover()

    m = nrw.metrics()['results']
    assert (m['jw_lookups'], m['jw_errors']) == (1, 1)
    _, out = quiet(morning_report.overnight)
    assert 'JustWatch trouble during discovery' in out


# ==========================================================================
# (i) owner rules (Nov 15): Remove and Revert are OPPOSITES
#     Remove = a title the owner never wants on the wall: status 'removed', set only
#     by his /remove or the admin Remove button. Revert = a film wrongly marked new:
#     back to waiting, back on the wall the day it's really out. Nothing automatic
#     sets 'removed'; nothing brings a removed title back.
# ==========================================================================

def _admin_post(route, mid, daily_update_running=False, behind_github=None):
    """An admin-panel button (the real Flask route) on the tmp working copy. GitHub is never asked
    whether today's update is running, and git never fetches (no network in a test): the test
    says (behind_github: what the catch-up reports, None = up to date)."""
    from admin import create_app
    import admin.routes.movies as admin_movies
    real_check, real_catch_up = admin_movies._daily_update_running, admin_movies._catch_up_with_github
    admin_movies._daily_update_running = lambda: daily_update_running
    admin_movies._catch_up_with_github = lambda: behind_github
    try:
        app = create_app()
        app.testing = True
        with app.test_client() as client:
            return client.post(route, json={'movie_id': int(mid)}).get_json()
    finally:
        admin_movies._daily_update_running = real_check
        admin_movies._catch_up_with_github = real_catch_up


@pytest.mark.parametrize('path', ['runs-out', 'already-expired', 'archived'])
def test_the_screening_check_never_returns_a_removed_title_and_discovery_never_checks_it(nrw, path):
    """No path brings a removed title back. The screening check returns an ended festival
    screening to tracking (JustWatch then puts it back on the wall). Round 2b:
    _return_screening_to_tracking never touches a status 'removed' record -- the date-based
    expiry ('runs-out': River's screening ends 11-27, checked 11-28) called it with no status
    check; the other two paths look for status 'available' first. A removed title's entry can
    outlive the Remove: a running process that loaded data.json before it writes it back
    (section g's purge case). 'archived': A Man with Sole, removed by the owner in June, whose
    expired screening is in the archive -- a manual add, so if it were ever returned to
    tracking the manual-add bypass would put it on the wall without JustWatch."""
    if path == 'archived':
        mid, check_day = A_MAN_WITH_SOLE, DAY
        removed = tracking_rec(mid)
        assert (removed['status'], removed['removed_reason'], removed['_added_manually']) == (
            'removed', 'manual_removal', True)
        assert archive_rec(mid)['virtual_screening_info']['status'] == 'expired'
        _, records = _screenings_on_wall(nrw, only={RIVER})
        nrw.write_tracking({**records, mid: removed})
        nrw.write_archive(prod_archive())
    else:
        mid, check_day = (RIVER, '2026-11-28T06:30:00') if path == 'runs-out' else (HIS_MONSTER, DAY)
        _screenings_on_wall(nrw, only={mid})
        stale = nrw.wall()                          # loaded by a running process ...
        body = _admin_post('/remove-movie', mid)    # ... the owner removes the film ...
        assert body['success'] is True and mid not in ids_of(nrw.wall()), body
        nrw.write_wall(stale)                       # ... and that process writes its copy back
    before = nrw.tracking()[mid]
    assert before['status'] == 'removed'
    nrw.at(check_day)

    _, out = quiet(nrw.generator().check_virtual_screening_expirations)

    assert nrw.tracking()[mid] == before
    assert nrw.read_json('movie_tracking.json')['movies'][mid]['status'] == 'removed'
    if path == 'runs-out':
        assert 'Expired: River' in out                # the check did reach it

    # Discovery never looks at it, whatever TMDB and JustWatch say (one ordinary release
    # alongside makes it a real run).
    trk = nrw.tracking()
    trk[ACCURSED] = tracking_rec(ACCURSED)
    nrw.write_tracking(trk)
    for m in (mid, ACCURSED):
        nrw.tmdb.set_providers(m, flatrate=['Kanopy'], rent=['Amazon Video'])
        nrw.jw_has(m, streaming('Kanopy', f'https://www.kanopy.com/en/product/{m}', '2026-11-10')
                   + amazon(m, '2026-11-10'))
    nrw.tmdb.set_type4(mid, '2026-11-10')

    gen, _ = nrw.discover()

    assert nrw.jw.film_queries() == ['Accursed']
    assert nrw.tracking()[mid] == before and nrw.queued() == [ACCURSED]
    quiet(gen.purge_removed_movies)                   # enrichment's purge
    assert mid not in ids_of(nrw.wall())


def test_a_held_film_is_never_removed_however_long_it_waits(nrw):
    """Nothing automatic sets 'removed' -- a hold is a wait, never a drop. The old ceiling (4
    strikes, then a permanent skip: 443 films silently dropped) is gone. Six daily runs of
    every kind of JustWatch answer later, every held film is still waiting and was checked on
    every run; strikes are counted only on the days JustWatch really answered."""
    films = [CONCORDE, MISTLETOE, HARLEM, DARWISH, LIBAN]
    start = {m: tracking_rec(m)['_jw_revert_count'] for m in films}
    titles = sorted(tracking_rec(m)['title'] for m in films)
    nrw.seed(films)
    days = ['no-match', 'no-offer', 'error', 'outage', 'no-offer', 'no-match']

    for i, kind in enumerate(days):
        nrw.jw.nodes, nrw.jw.errors, nrw.jw.down = {}, {}, None
        for m in films:
            if kind == 'no-offer':
                nrw.jw_has(m, [])
            elif kind == 'outage':
                nrw.jw_has(m, amazon(m, '2026-11-01'))       # emptied by the outage
            elif kind == 'error':
                nrw.jw.errors[tracking_rec(m)['title']] = 'connection_error'
        if kind == 'outage':
            nrw.jw.down = 'offers'
        nrw.at(f'2026-11-{14 + i}T06:30:00')
        seen = len(nrw.jw.film_queries())

        nrw.discover()

        trk = nrw.tracking()
        assert sorted(nrw.jw.film_queries()[seen:]) == titles, kind      # every one checked this run
        assert {m: trk[m]['status'] for m in films} == {m: 'tracking' for m in films}, kind

    answered = sum(k in ('no-match', 'no-offer') for k in days)
    trk = nrw.tracking()
    assert {m: trk[m]['_jw_revert_count'] for m in films} == {m: start[m] + answered for m in films}
    assert not any(trk[m].get('_skip_provider_discovery') for m in films)
    assert {trk[m]['_jw_revert_reason'] for m in films} == {'justwatch_no_match'}
    assert {trk[m]['_jw_last_checked'] for m in films} == {'2026-11-19'}
    assert {trk[m]['_jw_last_refuted'] for m in films} == {'2026-11-18'}  # the last no-offer day


_REMOVED_SQL = re.compile(r"\bset\b[^;]*\bstatus\s*=\s*['\"]removed['\"]", re.I | re.S)


def _code_that_sets_status_removed():
    """(file, function) of every place in the checkout's Python code (tests and
    museum_legacy/ aside) that writes status 'removed': an assignment, a dict literal or
    keyword, setdefault/__setitem__, or SQL."""
    listed = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '--cached', '--others',
                             '--exclude-standard', '--', '*.py'], capture_output=True, text=True, env=_git_env())
    assert listed.returncode == 0, listed.stderr
    files = [f for f in listed.stdout.split('\0')
             if f and not f.startswith(('tests/', 'museum_legacy/')) and (ROOT / f).is_file()]
    assert 'pipeline/discoverer.py' in files and 'scripts/revert_movie.py' in files and len(files) > 50

    def removed(n):
        return isinstance(n, ast.Constant) and n.value == 'removed'

    def status(n):
        return isinstance(n, ast.Constant) and n.value == 'status'

    found = []
    for f in files:
        tree = ast.parse((ROOT / f).read_text(encoding='utf-8', errors='replace'), filename=f)
        where = ['<module>']

        class Scan(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                where.append(node.name)
                self.generic_visit(node)
                where.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Assign(self, node):
                if removed(node.value) and any(
                        (isinstance(t, ast.Subscript) and status(t.slice))
                        or (isinstance(t, ast.Attribute) and t.attr == 'status') or isinstance(t, ast.Name)
                        for t in node.targets):
                    found.append((f, where[-1]))
                self.generic_visit(node)

            def visit_Dict(self, node):
                if any(k is not None and status(k) and removed(v) for k, v in zip(node.keys, node.values)):
                    found.append((f, where[-1]))
                self.generic_visit(node)

            def visit_keyword(self, node):
                if node.arg == 'status' and removed(node.value):
                    found.append((f, where[-1]))
                self.generic_visit(node)

            def visit_Call(self, node):
                if len(node.args) >= 2 and status(node.args[0]) and removed(node.args[1]):
                    found.append((f, where[-1]))
                self.generic_visit(node)

            def visit_Constant(self, node):
                if isinstance(node.value, str) and _REMOVED_SQL.search(node.value):
                    found.append((f, where[-1]))

        Scan().visit(tree)
    return found


def test_only_the_owners_remove_sets_status_removed_anywhere_in_the_code():
    """'removed' is the owner's decision alone: his /remove (a command he runs by hand,
    .claude/commands/remove.md) or the admin Remove button -- never the pipeline, a script or
    a sweep (production's tracking still carries 52 'no_watch_links_stale' and 28
    'theatrical_pvod_audit' removals from past clean-ups). Every Python file in the checkout
    is scanned for code that writes it."""
    assert _code_that_sets_status_removed() == [('admin/routes/movies.py', 'remove_movie')]


def test_admin_revert_refuses_a_removed_title_and_changes_nothing(nrw):
    """'We don't want to revert removed titles': Revert would send it back to waiting, and back
    on the wall once JustWatch lists it. The admin Revert button refuses a removed title
    (putback.owner_revert returns False) and touches neither tracking nor the wall."""
    removed = tracking_rec(A_MAN_WITH_SOLE)
    assert removed['status'] == 'removed'
    nrw.write_tracking({A_MAN_WITH_SOLE: removed, JIMMY: tracking_rec(JIMMY)})
    nrw.write_wall(prod_wall())
    wall_before = nrw.read_json('data.json')
    nrw.at(DAY)

    body = _admin_post('/revert-movie', A_MAN_WITH_SOLE)

    assert body['success'] is False and 'removed for good' in body['error'], body
    assert nrw.tracking() == {A_MAN_WITH_SOLE: removed, JIMMY: tracking_rec(JIMMY)}
    assert nrw.read_json('data.json') == wall_before


def test_admin_revert_saves_and_publishes_both_files_itself(nrw, monkeypatch):
    """Round 2d (critic): the admin's Revert only marked "changes pending" for "Save Changes",
    which commits data.json alone -- the pre-commit hook blocks that (movie_tracking.json must go
    with it) -- and the next local sync resets uncommitted data files: the revert never reached
    the site. The route now commits and pushes data.json + movie_tracking.json itself, with the
    /flow save helper, when the admin runs in the site folder."""
    import admin.config as admin_config
    import admin.routes.curate_flow as curate_flow
    calls = []
    monkeypatch.setattr(curate_flow, '_git_commit_push', lambda files, message: calls.append((files, message)))
    monkeypatch.setattr(admin_config, 'SITE_ROOT', os.getcwd())      # the admin in the site folder
    nrw.write_wall(prod_wall())
    nrw.write_tracking({JIMMY: tracking_rec(JIMMY)})
    nrw.at(DAY)

    body = _admin_post('/revert-movie', JIMMY)

    assert body['success'] is True and body['warning'] is None and 'Saved and published' in body['message'], body
    assert calls == [(['data.json', 'movie_tracking.json'], 'Revert Jimmy — not out yet, back on its own when it is')]
    assert nrw.tracking()[JIMMY]['_reverted_by_owner'] == TODAY
    assert not os.path.exists(os.path.join('admin', '.pending_changes'))


def test_admin_revert_says_so_when_it_could_not_publish(nrw, monkeypatch):
    """A failed commit or push is shown, never "saved": the revert is done in the files but not
    on the site yet. Outside the site folder (a copy, this test) nothing is committed at all."""
    import admin.config as admin_config
    import admin.routes.curate_flow as curate_flow
    calls = []
    monkeypatch.setattr(curate_flow, '_git_commit_push',
                        lambda files, message: calls.append(files) or 'push failed — committed locally')
    nrw.write_wall(prod_wall())
    nrw.write_tracking({JIMMY: tracking_rec(JIMMY), TEKKONKINKREET: tracking_rec(TEKKONKINKREET)})
    nrw.at(DAY)

    body = _admin_post('/revert-movie', JIMMY)       # SITE_ROOT is the worktree, not this folder
    assert body['success'] is True and 'NOT PUBLISHED YET' in body['message'] and calls == [], body

    monkeypatch.setattr(admin_config, 'SITE_ROOT', os.getcwd())
    body = _admin_post('/revert-movie', TEKKONKINKREET)
    assert body['warning'] == 'push failed — committed locally' and 'NOT PUBLISHED YET' in body['message'], body
    # A reissue (Tekkonkinkreet, 20th Anniversary): the note says the original film's listing
    # can bring it back (it is checked daily and comes back by itself).
    assert 'A reissue' in body['message'] and 'original film' in body['message'], body


def test_admin_revert_and_remove_buttons_pass_any_title_to_the_page_script(tmp_path):
    """Critic: the buttons put the title in a single-quoted JavaScript string; a title with an
    apostrophe (49 on the wall: Blue Road: The Edna O'Brien Story, A Dog's Perfect Christmas...)
    broke the script, so Revert did nothing. Every onclick in the real template that passes a
    title is rendered by the admin's own template engine and run in Node."""
    from html.parser import HTMLParser
    if not shutil.which('node'):
        pytest.skip('node is not installed')
    from admin import create_app
    lines = [ln for ln in open(ROOT / 'admin' / 'templates' / 'index.html')
             if 'onclick=' in ln and ('revertMovie(' in ln or 'removeMovie(' in ln)]
    assert len(lines) == 3, lines

    class _P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            self.onclick = dict(attrs).get('onclick')

    app = create_app()
    for title in ("Blue Road: The Edna O'Brien Story", 'He said "hi" & <left>', 'Back\\slash'):
        for ln in lines:
            with app.app_context():
                html = app.jinja_env.from_string(ln).render(movie_id='123', movie={'title': title})
            p = _P()
            p.feed(html)
            js = ("var got = null; var event = {stopPropagation: function () {}};\n"
                  "function revertMovie(a, b) { got = b; }\nfunction removeMovie(a, b) { got = b; }\n"
                  + p.onclick + "\nif (got !== " + json.dumps(title) + ") { throw new Error('got ' + got); }")
            script = tmp_path / 'onclick.js'
            script.write_text(js)
            r = subprocess.run(['node', str(script)], capture_output=True, text=True)
            assert r.returncode == 0, (title, ln.strip(), r.stderr[-400:])


def test_a_reverted_film_waits_for_justwatch_and_is_dated_after_the_revert(nrw):
    """Revert = the film isn't really out yet: off the wall now, back on its own the day it's
    really out, never removed. Jimmy (on the wall, dated 11-12): the owner presses 'Revert (not
    out yet)' on 11-14. 11-15: JustWatch has it with no offer -- it waits, checked again next
    run. 11-16: JustWatch lists the rentals it first recorded 11-10 (what put it on the wall by
    mistake): it keeps waiting. 11-17: Apple lists it (a record dated after the revert) -- a new
    store listing alone, which can be a pre-order, so it still waits (round 2d; 2c put it back).
    11-18: it lands on a streaming service (a record dated 11-18): back on the wall, dated 11-18
    -- never on or before a day it was known not to be out."""
    nrw.write_wall(prod_wall())
    nrw.write_tracking({JIMMY: tracking_rec(JIMMY), MEETING_MARSHA: tracking_rec(MEETING_MARSHA)})
    nrw.at(DAY)

    body = _admin_post('/revert-movie', JIMMY)

    assert body['success'] is True, body
    rec = nrw.tracking()[JIMMY]
    assert (rec['status'], rec['_jw_revert_reason'], rec['_jw_revert_count']) == ('tracking', 'owner_revert', 1)
    assert rec['_jw_last_refuted'] == rec['_reverted_by_owner'] == TODAY and 'digital_date' not in rec
    entry = nrw.wall_entry(JIMMY)
    assert entry['hidden'] is True and entry['_enrichment_status'] == 'reverted'
    assert nrw.tracking()[MEETING_MARSHA] == tracking_rec(MEETING_MARSHA)

    nrw.at(NEXT_DAY)                                  # the next run: discovery first ...
    nrw.jw_has(JIMMY, [])
    gen, _ = nrw.discover()

    rec = nrw.tracking()[JIMMY]
    assert nrw.jw.film_queries() == ['Jimmy']
    assert (rec['status'], rec['_jw_revert_count'], rec['_jw_last_refuted']) == ('tracking', 2, TOMORROW)
    assert nrw.wall_entry(JIMMY)['hidden'] is True and nrw.queued() == []
    quiet(gen.purge_removed_movies)                   # ... then enrichment's purge
    assert JIMMY not in ids_of(nrw.wall())

    nrw.at('2026-11-16T06:30:00')
    nrw.jw_has(JIMMY, amazon(JIMMY, '2026-11-10') + fandango(JIMMY, '2026-11-10'))
    nrw.discover()

    rec = nrw.tracking()[JIMMY]
    # Nothing dated after the revert: the stores' 11-10 pre-order listings are what put it on the
    # wall by mistake, so it keeps waiting (round 2c -- 2b put it back dated 11-16).
    assert rec['status'] == 'tracking' and rec['_jw_last_checked'] == '2026-11-16'
    assert rec['_jw_last_refuted'] == TOMORROW and nrw.queued() == []

    nrw.at('2026-11-17T06:30:00')       # Apple lists it: a record dated after the revert
    jimmy_offers = amazon(JIMMY, '2026-11-10') + fandango(JIMMY, '2026-11-10') + apple(JIMMY, '2026-11-17')
    nrw.jw_has(JIMMY, jimmy_offers)
    nrw.discover()

    rec = nrw.tracking()[JIMMY]
    assert rec['status'] == 'tracking' and rec['_jw_last_checked'] == '2026-11-17' and nrw.queued() == []

    nrw.at('2026-11-18T06:30:00')       # it lands on a streaming service: watchable now, new since the revert
    nrw.jw_has(JIMMY, jimmy_offers + streaming('Peacock', 'https://www.peacocktv.com/watch/jimmy', '2026-11-18'))
    nrw.discover()

    rec = nrw.tracking()[JIMMY]
    assert rec['status'] == 'available' and rec['_put_back_on'] == '2026-11-18'
    assert (rec['digital_date'], rec['_digital_date_source']) == ('2026-11-18', 'jw_first_offer')
    assert not rec.get('_date_needs_review') and '_reverted_by_owner' not in rec
    entry = nrw.wall_entry(JIMMY)
    assert entry['digital_date'] == '2026-11-18' and not entry.get('hidden')
    assert nrw.queued() == [JIMMY]


def test_a_reverted_manual_add_waits_for_justwatch_like_any_reverted_film(nrw):
    """A reverted film comes back the day it's really out: JustWatch checks it every run, no
    shortcut (putback.owner_revert). Tekkonkinkreet is a manual add (/add-movie); the owner
    reverts it on 11-14. On 11-15 JustWatch has it with no way to watch it: it keeps
    waiting, off the wall."""
    rec0 = tracking_rec(TEKKONKINKREET)
    assert rec0['status'] == 'available' and rec0['_added_manually'] and TEKKONKINKREET in ids_of(prod_wall())
    # Its real record is a reissue (20th Anniversary), and a reverted reissue isn't looked up at
    # all (round 2e: JustWatch can't tell the restoration from the original). Here: the hand-add.
    for k in ('_reissue', 'reissue_label'):
        rec0.pop(k, None)
    _wall = prod_wall()
    for _e in _wall:   # the wall entry too: the revert reads the wall's restoration flags (round 2f)
        if str(_e.get('id')) == TEKKONKINKREET:
            _e.pop('_reissue', None)
            _e.pop('reissue_label', None)
            (_e.get('filters') or {}).pop('is_restoration', None)
    nrw.write_wall(_wall)
    nrw.write_tracking({TEKKONKINKREET: rec0})
    nrw.at(DAY)
    assert _admin_post('/revert-movie', TEKKONKINKREET)['success'] is True
    assert nrw.wall_entry(TEKKONKINKREET)['hidden'] is True

    nrw.at(NEXT_DAY)
    nrw.jw_has(TEKKONKINKREET, [])                    # JustWatch has it, no way to watch it
    nrw.discover()                                    # the next run: discovery, before enrichment's purge

    rec = nrw.tracking()[TEKKONKINKREET]
    assert 'Tekkonkinkreet' in nrw.jw.film_queries()
    assert rec['status'] == 'tracking' and TEKKONKINKREET not in nrw.queued()
    assert nrw.wall_entry(TEKKONKINKREET).get('hidden') is True
