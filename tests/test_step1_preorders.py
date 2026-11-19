#!/usr/bin/env python3
"""
End-to-end tests for Step 1 v2 (branch step1-putback-v2, uncommitted round-2 changes on top
of a5da4f76) -- the PRE-ORDER and BUY-ONLY lanes, put-back side only.

Owner's rules these tests hold the code to:
  (1) a film held as "not out yet" is a WAIT, never a drop;
  (2) every held film is re-checked every daily run;
  (3) JustWatch decides availability (TMDB never);
  (4) a film is dated the day it actually became available, never on a day a check
      proved it unavailable;
  (5) a JustWatch error/outage never counts against a film and never puts an
      unconfirmed film on the wall.
Step 1 scope is put-back only: what counts as a pre-release (PVOD gate, buy-only
detector, rent pre-order page check) stays as production has it.

Ported from the v1 file (~/Downloads/nrw-step1-wt/tests/test_step1_preorders.py):
  * JustWatch offers now carry `dateCreated` (v2 dates put-backs from it): the 2026-11-14
    capture had none (v1 did not query it), so each captured offer mirrors its own
    availableFromTime (null where JustWatch gave none). Scenarios that need a specific
    record date set it explicitly (each says so).
  * v1's pending pre-order re-add is gone in v2 (it looped nightly): the re-add tests are
    inverted (section b). The v1 tests for defects v2 fixed run without xfail; the
    expectations round 2 changed on purpose are updated (each says what changed).
  * The regression guard (section e) runs production code (78303fd6 = a5da4f76^, main
    before Step 1) in a subprocess on the same scenario.
  * New: section d0-d5 (has_live_rent, the tri-state daily buy-only check, both Type-4
    branches, the transition sync of the wall entry), section f (JustWatch trouble).
  * Round 2b (Nov 15): the strict-xfail tests for the defects 2b fixed now run as plain
    tests (Apple's store is 'Apple TV Store' / 'itunes'; enrichment keeps a Type-4
    graduation's date; the buy-only check consults the canary; past-date pre-orders keep
    their flags until JustWatch confirms them). Each was checked to FAIL on the pre-2b code
    and pass on 2b. New: section l (Liberation, a held pre-order with a future TMDB date),
    section r (the owner's Revert action vs Remove).

How the tests run
-----------------
* The REAL pipeline modules run (DataGenerator -> ProviderDiscoverer.check_tracking_movies,
  MovieEnricher.enrich_newly_available_movies, DataGenerator.daily_gap_fill, and the real
  scripts/morning_report.py), each phase with a fresh DataGenerator as in production,
  inside a throw-away sandbox directory holding copies of the real config.yaml / overrides
  and the records under test.
* Every test runs under a write audit: any attempt by this process (or the production-code
  subprocess) to write, create, rename or delete a path inside the worktree, or to open a
  SQLite file there (the real movie_tracking.db), is refused and fails the test. (The v1
  file compared file mtimes instead, which other processes running in the same worktree
  trip.)
* Records are REAL: copied from the production snapshots (git show 78303fd6:
  movie_tracking.json / data.json). TMDB and JustWatch payloads are REAL responses
  captured read-only on 2026-11-14 unless a test says it stages one (it then says what).
* Only the network is faked: requests.get (TMDB), the JustWatch GraphQL POST, Playwright
  store pages. Any other outbound request raises ConnectionError; scrapers stay off
  (DataGenerator(enrichment_enabled=False)); time.sleep is a no-op; the distributor-lookup
  refresh writes into the sandbox. The clock is frozen at 09:00 local on the scenario day.

Run:  cd <worktree> && /usr/bin/python3 -m pytest tests/test_step1_preorders.py -q -p no:cacheprovider
"""

import contextlib
import copy
import datetime as _dt
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import types

import pytest

sys.dont_write_bytecode = True   # never leave __pycache__ in the worktree

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTION = '78303fd6'          # main before Step 1 (a5da4f76^)
# A subprocess sets this to run the same scenario against production's pipeline/.
CODE_ROOT = os.environ.get('NRW_STEP1_TEST_CODE_ROOT') or WT
for _p in (WT, CODE_ROOT):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, WT)              # constants, utils, load_env, scripts ...
if CODE_ROOT != WT:
    sys.path.insert(0, CODE_ROOT)   # production pipeline/ shadows the worktree's

TODAY = '2026-11-14'            # the clock is frozen at 09:00 on this day
_REAL_DATETIME = _dt.datetime


# ----------------------------------------------------------------------------------
# Real data
# ----------------------------------------------------------------------------------

SPA_WEEKEND = '1341138'      # held buy-only pending pre-order stored 2028-09-22; TMDB says 2026-09-22
THE_ODYSSEY = '1368337'      # held pending pre-order (2026-11-17), no data.json entry
I_SWEAR = '1317149'          # TMDB lists 2026-08-22 (Netflix) before 2026-06-02
TOM_AND_JERRY = '1497970'    # buy-only pre-order; TMDB buy: Apple TV Store only
QUEEN_AT_SEA = '1021848'     # buy-only pre-order; TMDB lists no provider at all
WICKER = '1195803'           # buy-only pending pre-order on the wall 2026-12-01; TMDB moved to 2026-11-24
HOW_TO_ROB_A_BANK = '1437511'  # JustWatch: CINEMA + buy-only Fandango At Home $24.99
GALAXYMPHONY = '1559261'     # JustWatch: Barnes & Noble DVD only (+ an Amazon-channel stream)
RESIDENT_EVIL = '1423191'    # JustWatch: CINEMA + rent $19.99 (PVOD)
AN_EYE_FOR_AN_EYE = '1497947'  # real 4-strike permanently-skipped hold (source of the 'skipped' lane)
LIBERATION = '1129188'       # real count-1 'no valid offers' hold (source of the 'held' lane)
RUN_TERRY_RUN = '1578210'    # held pending 2026-11-24, no data.json entry; JustWatch has no listing
RAY_GUNN = '940009'          # held pending 2026-12-18, no data.json entry; JustWatch: no offers yet
BEWARE_BOIUNA = '1244523'    # buy-only pre-order, TMDB Type-4 2026-11-03 (past); wall: PRE-ORDER entry
DREAMQUIL = '1125627'        # Fandango At Home lists its Dec 4 pre-order as a plain RENT offer
HIS_MONSTER = '1563321'      # expired festival screening (Eventive, ended 2026-10-16), real VOD since Oct
I_SWEAR_REMOVED = I_SWEAR    # the same record: status 'removed' (manual_removal 2026-05-28), on Netflix now

# The real Fandango At Home page text for DreamQuil (live page check, Nov 14 review, with
# the browser headers that make Fandango render): a pre-order.
DREAMQUIL_PAGE_TEXT = 'available to watch on dec 4 preorder $14.99'
# A store page that reads as a live rental (staged: the page check's 'available' signals).
LIVE_PAGE_TEXT = 'Rent now $5.99  Buy now $14.99'

_FIXTURES = None


def fixtures():
    global _FIXTURES
    if _FIXTURES is None:
        _FIXTURES = json.loads(_FIXTURES_JSON)
    return _FIXTURES


def offer(mtype, service, tech, url, price=None, available_from=None, created=None, ptype='HD'):
    """One JustWatch offer as the GraphQL API returns it."""
    return {'monetizationType': mtype, 'presentationType': ptype, 'retailPrice': price, 'currency': 'USD',
            'standardWebURL': url, 'availableFromTime': available_from, 'dateCreated': created,
            'package': {'clearName': service, 'technicalName': tech}}


def jw_node(mid, *extra_offers, offers=None):
    """A film's captured JustWatch node, optionally with staged offers added (or replaced)."""
    node = copy.deepcopy(fixtures()['jw'][mid])
    if offers is not None:
        node['offers'] = copy.deepcopy(list(offers))
    node['offers'].extend(copy.deepcopy(list(extra_offers)))
    return node


# Staged offers. Amazon lists a new rental from midnight Eastern (05:00Z), as in the
# captured Spa Weekend / Resident Evil offers.
def amazon_rent(slug, day=TODAY, price='$3.99'):
    return offer('RENT', 'Amazon Video', 'amazon', f'https://www.amazon.com/gp/video/detail/{slug}',
                 price, f'{day}T05:00:00Z', f'{day}T05:00:00Z')


def amazon_preorder_rent(slug, day='2026-12-04', price='$5.99'):
    """Amazon pre-order rental: JustWatch lists it as RENT with a FUTURE offer start."""
    return offer('RENT', 'Amazon Video', 'amazon', f'https://www.amazon.com/gp/video/detail/{slug}',
                 price, f'{day}T05:00:00Z', '2026-11-10T00:00:00Z')


def apple_store_rent(url, day=TODAY, price='$3.99'):
    """Apple's store as JustWatch names it in every captured payload: 'Apple TV Store'."""
    return offer('RENT', 'Apple TV Store', 'itunes', url, price, f'{day}T08:00:00Z', f'{day}T08:00:00Z')


def fandango_preorder_rent(url):
    """DreamQuil's shape: a Fandango At Home RENT with no offer start (a pre-order)."""
    o = copy.deepcopy(fixtures()['jw'][DREAMQUIL]['offers'][0])
    o['standardWebURL'] = url
    return o


def eventive_rent(url='https://watch.eventive.org/somefest2026/play/staged'):
    """A festival's own Eventive page listed as a rental (Disposable Humanity, Nov 2026: $19.39)."""
    return offer('RENT', 'Eventive', 'eventive', url, '$19.39', None, '2026-10-01T00:00:00Z')


def netflix_stream(slug):
    return offer('FLATRATE', 'Netflix', 'nfx', f'https://www.netflix.com/title/{slug}', None,
                 f'{TODAY}T07:00:00Z', f'{TODAY}T07:00:00Z')


def frozen_now_utc(day=TODAY):
    """The frozen clock's 'now' (09:00 local on `day`) in UTC -- the clock has_live_rent
    compares an Amazon offer start against."""
    y, m, d = (int(x) for x in day.split('-'))
    return _REAL_DATETIME(y, m, d, 9, 0, 0).astimezone(_dt.timezone.utc)


def _z(when):
    return when.strftime('%Y-%m-%dT%H:%M:%SZ')


def amazon_rent_from(slug, start, created='2026-11-10T00:00:00Z', price='$3.99'):
    """Amazon Video ('amazon') RENT with an explicit offer start (availableFromTime)."""
    return offer('RENT', 'Amazon Video', 'amazon', f'https://www.amazon.com/gp/video/detail/{slug}',
                 price, start, created)


def fandango_rent_started(url, start='2026-11-01T08:00:00Z'):
    """A Fandango At Home ('vudu') RENT whose offer start has passed -- still not one
    has_live_rent trusts (stores list pre-order rentals as plain RENT offers)."""
    return offer('RENT', 'Fandango At Home', 'vudu', url, '$5.99', start, start)


def apple_tv_named_rent(url, day=TODAY):
    """Apple's store under the shorter clearName 'Apple TV' (technicalName still 'itunes')."""
    return offer('RENT', 'Apple TV', 'itunes', url, '$3.99', f'{day}T08:00:00Z', f'{day}T08:00:00Z')


def shift72_rent(url='https://somefest.shift72.com/film/staged'):
    """A festival's Shift72 page listed as a rental (the other FESTIVAL_PLATFORMS entry)."""
    return offer('RENT', 'Shift72', 'shift72', url, '$12.00', None, '2026-10-01T00:00:00Z')


def sundance_now_stream(slug):
    """The streaming service Sundance Now: a real way to watch it (v2 dropped 'Sundance'
    from FESTIVAL_PLATFORMS because it matched this service)."""
    return offer('FLATRATE', 'Sundance Now', 'sundancenow', f'https://www.sundancenow.com/watch/{slug}', None,
                 f'{TODAY}T08:00:00Z', f'{TODAY}T08:00:00Z')


def tj_apple_url():
    return fixtures()['jw'][TOM_AND_JERRY]['offers'][1]['standardWebURL']


TJ_FANDANGO_URL = 'https://athome.fandango.com/content/browse/details/Tom-and-Jerry-Forbidden-Compass/staged'
QAS_FANDANGO_URL = 'https://athome.fandango.com/content/browse/details/Queen-at-Sea/5287829'  # its pre_order_link


# ----------------------------------------------------------------------------------
# Harness: patches, write audit, fake network, sandbox
# ----------------------------------------------------------------------------------

_MISSING = object()


class Patcher:
    """setattr/setitem with undo, usable outside pytest (the production subprocess uses it)."""

    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append(('attr', obj, name, getattr(obj, name, _MISSING)))
        setattr(obj, name, value)

    def setitem(self, mapping, key, value):
        self._undo.append(('item', mapping, key, mapping.get(key, _MISSING)))
        mapping[key] = value

    def undo(self):
        while self._undo:
            kind, obj, key, old = self._undo.pop()
            if kind == 'attr':
                if old is _MISSING:
                    try:
                        delattr(obj, key)
                    except AttributeError:
                        pass
                else:
                    setattr(obj, key, old)
            else:
                if old is _MISSING:
                    obj.pop(key, None)
                else:
                    obj[key] = old


class WriteAudit:
    """Refuses -- and records -- every write into the worktree made by THIS process: open()
    for writing, os.open with write flags, rename/replace/remove/mkdir, and any SQLite
    connection to a file there (the real movie_tracking.db must never be opened)."""

    _WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.hits = []
        self._p = Patcher()

    def inside(self, path):
        if isinstance(path, int):
            return False
        try:
            p = os.fspath(path)
        except TypeError:
            return False
        if isinstance(p, bytes):
            p = os.fsdecode(p)
        if p in (':memory:', '') or p.startswith('file:'):
            return False
        p = os.path.realpath(p)
        return p == self.root or p.startswith(self.root + os.sep)

    def _deny(self, how, path):
        where = os.path.realpath(os.fsdecode(os.fspath(path)))
        self.hits.append(f'{how} {where}')
        raise PermissionError(f'test write audit: refused {how} of a worktree path: {where}')

    def install(self):
        import builtins
        import io as _io
        audit, p = self, self._p
        real_open, real_os_open = builtins.open, os.open

        def guarded_open(file, mode='r', *a, **k):
            if isinstance(mode, str) and any(c in mode for c in 'wax+') and audit.inside(file):
                audit._deny(f'open({mode!r})', file)
            return real_open(file, mode, *a, **k)

        def guarded_os_open(path, flags, *a, **k):
            # (a path relative to a dir_fd can't be resolved here; those are never ours)
            if flags & audit._WRITE_FLAGS and k.get('dir_fd') is None and audit.inside(path):
                audit._deny('os.open(write)', path)
            return real_os_open(path, flags, *a, **k)

        def wrap(name, n_paths):
            real = getattr(os, name)

            def guarded(*a, **k):
                if not any(v is not None for kk, v in k.items() if kk.endswith('dir_fd')):
                    for path in a[:n_paths]:
                        if audit.inside(path):
                            audit._deny(f'os.{name}', path)
                return real(*a, **k)
            p.setattr(os, name, guarded)

        p.setattr(builtins, 'open', guarded_open)
        p.setattr(_io, 'open', guarded_open)
        p.setattr(os, 'open', guarded_os_open)
        for name, n in (('replace', 2), ('rename', 2), ('remove', 1), ('unlink', 1), ('rmdir', 1),
                        ('mkdir', 1), ('makedirs', 1), ('truncate', 1)):
            wrap(name, n)
        real_connect = sqlite3.connect

        def guarded_connect(database, *a, **k):
            if audit.inside(database):
                audit._deny('sqlite3.connect', database)
            return real_connect(database, *a, **k)
        p.setattr(sqlite3, 'connect', guarded_connect)
        return self

    def uninstall(self):
        self._p.undo()


@pytest.fixture(autouse=True)
def _worktree_write_audit():
    """Every scenario runs in a sandbox: fail the test if it tried to write the worktree."""
    audit = WriteAudit(WT).install()
    try:
        yield audit
    finally:
        audit.uninstall()
    assert not audit.hits, f'test tried to write the worktree: {audit.hits[:10]}'


def make_frozen_datetime(day):
    y, m, d = (int(x) for x in day.split('-'))
    frozen = _REAL_DATETIME(y, m, d, 9, 0, 0)

    class FrozenDatetime(_REAL_DATETIME):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls(frozen.year, frozen.month, frozen.day, frozen.hour, frozen.minute, frozen.second)
            return cls.fromtimestamp(frozen.timestamp(), tz)

        @classmethod
        def today(cls):
            return cls.now()

        @classmethod
        def utcnow(cls):
            return cls.fromtimestamp(frozen.timestamp(), _dt.timezone.utc).replace(tzinfo=None)

    return FrozenDatetime


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self.content = self.text.encode()
        self.ok = 200 <= status_code < 400
        self.headers = {}

    def json(self):
        return copy.deepcopy(self._payload)

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(f'HTTP {self.status_code}')


class FakeNet:
    """TMDB (requests.get), JustWatch (Session.post) and Playwright pages for one scenario.

    spec keys: tmdb {mid: {details, release_dates, watch_providers}}, jw {mid: node|None},
    jw_days {day: {mid: node|None}} (what JustWatch shows that day), jw_throttled [phase]
    (a throttled JustWatch: HTTP 200, no results -- control titles too), jw_outage
    {'day:phase' or 'phase': 'no_results' | 'empty_offers' | 'http_500'}, jw_malformed [mid]
    (the node comes back with offers null), tmdb_fail [[mid, kind]] (HTTP 500 for that
    TMDB endpoint: '' details, '/release_dates', '/watch/providers'), pages [[needle, text]]."""

    TMDB_RE = re.compile(r'^https://api\.themoviedb\.org/3/movie/(\d+)(/release_dates|/watch/providers)?/?$')

    def __init__(self, spec):
        self.spec = spec
        self.phase = 'setup'
        self.tmdb_calls = []
        self.jw_queries = []      # (phase, searchQuery)
        self.pages = []           # (phase, url)
        self.blocked = []         # (phase, url) -- requests the test refused
        self.title_mids = {}
        nodes_by_mid = {}
        for mid, node in (spec.get('jw') or {}).items():
            nodes_by_mid.setdefault(mid, []).append(node)
        for day_nodes in (spec.get('jw_days') or {}).values():
            for mid, node in day_nodes.items():
                nodes_by_mid.setdefault(mid, []).append(node)
        for mid, nodes in nodes_by_mid.items():
            titles = set()
            rec = (spec.get('tracking') or {}).get(mid) or {}
            titles.add(rec.get('title'))
            titles.add((((spec.get('tmdb') or {}).get(mid) or {}).get('details') or {}).get('title'))
            for node in nodes:
                titles.add(((node or {}).get('content') or {}).get('title'))
            for w in spec.get('wall') or []:
                if str(w.get('id')) == mid:
                    titles.add(w.get('title'))
            for t in titles:
                if t and mid not in self.title_mids.setdefault(t, []):
                    self.title_mids[t].append(mid)
        self.canary = fixtures()['jw_canary']

    # -- TMDB -------------------------------------------------------------------
    def get(self, url, params=None, timeout=None, **kw):
        import requests
        m = self.TMDB_RE.match(url or '')
        if not m:
            self.blocked.append((self.phase, url))
            raise requests.ConnectionError(f'network disabled in test: {url}')
        mid, kind = m.group(1), m.group(2) or ''
        self.tmdb_calls.append((self.phase, mid, kind))
        for f_mid, f_kind in self.spec.get('tmdb_fail') or []:
            if f_mid in (mid, '*') and f_kind in (kind, '*'):
                return FakeResponse(500, {'status_code': 11, 'status_message': 'Internal error'})
        fx = (self.spec.get('tmdb') or {}).get(mid)
        if kind == '/release_dates':
            return FakeResponse(200, fx['release_dates'] if fx and fx.get('release_dates') else {'id': int(mid), 'results': []})
        if kind == '/watch/providers':
            return FakeResponse(200, fx['watch_providers'] if fx and fx.get('watch_providers') else {'id': int(mid), 'results': {}})
        if fx and fx.get('details'):
            return FakeResponse(200, fx['details'])
        return FakeResponse(404, {'status_code': 34, 'status_message': 'not found'})

    # -- JustWatch --------------------------------------------------------------
    def _outage(self, day, phase):
        if phase in (self.spec.get('jw_throttled') or ()):
            return 'no_results'
        modes = self.spec.get('jw_outage') or {}
        return modes.get(f'{day}:{phase}') or modes.get(phase)

    def nodes_for(self, query, day):
        out = []
        days = self.spec.get('jw_days') or {}
        for mid in self.title_mids.get(query, []):
            if day in days and mid in days[day]:
                node = days[day][mid]
            else:
                node = (self.spec.get('jw') or {}).get(mid)
            if not node:
                continue
            node = copy.deepcopy(node)
            if mid in (self.spec.get('jw_malformed') or ()):
                node['offers'] = None
            out.append(node)
        if query in self.canary:
            out.append(copy.deepcopy(self.canary[query]))
        return out

    def session_post(self, session, url, json=None, timeout=None, **kw):
        import requests
        if 'apis.justwatch.com' not in (url or ''):
            self.blocked.append((self.phase, url))
            raise requests.ConnectionError(f'network disabled in test: {url}')
        q = ((json or {}).get('variables') or {}).get('searchQuery', '')
        self.jw_queries.append((self.phase, q))
        day, _, phase = self.phase.rpartition(':')
        mode = self._outage(day, phase)
        if mode == 'http_500':
            return FakeResponse(500, {'error': 'unavailable'})
        if mode == 'no_results':
            # How a throttled/blocked JustWatch answers (JW_BREAKER): HTTP 200, no results.
            return FakeResponse(200, {'data': {'popularTitles': {'edges': []}}})
        nodes = self.nodes_for(q, day)
        if mode == 'empty_offers':
            # The other outage shape the pipeline guards against: titles, empty offer lists.
            for n in nodes:
                n['offers'] = []
        return FakeResponse(200, {'data': {'popularTitles': {'edges': [{'node': n} for n in nodes]}}})

    def refuse(self, *a, **kw):
        import requests
        url = kw.get('url') or next((x for x in a if isinstance(x, str) and x.startswith('http')), '?')
        self.blocked.append((self.phase, url))
        raise requests.ConnectionError(f'network disabled in test: {url}')

    # -- Playwright store pages ---------------------------------------------------
    def page_text(self, url):
        for needle, text in self.spec.get('pages') or []:
            if needle in (url or ''):
                return text
        return ''   # page rendered nothing readable -> the page check is inconclusive


class _FakePage:
    def __init__(self, net):
        self.net, self.url = net, None

    def goto(self, url, **kw):
        self.url = url
        self.net.pages.append((self.net.phase, url))

    def wait_for_timeout(self, ms):
        pass

    def text_content(self, selector):
        return self.net.page_text(self.url)

    inner_text = text_content

    def on(self, *a, **k):
        pass

    def close(self):
        pass


class _FakeContext:
    def __init__(self, net):
        self.net = net

    def add_init_script(self, *a, **k):
        pass

    def set_default_timeout(self, *a, **k):
        pass

    def new_page(self):
        return _FakePage(self.net)

    def close(self):
        pass


class _FakeBrowser:
    def __init__(self, net):
        self.net = net

    def new_context(self, **kw):
        return _FakeContext(self.net)


def _fake_playwright_module(net):
    mod = types.ModuleType('playwright_manager')

    class PlaywrightManager:
        _instance = None

        def get_browser(self, **kw):
            return _FakeBrowser(net)

        def cleanup(self):
            pass

    mod.PlaywrightManager = PlaywrightManager
    mod.get_playwright_manager = lambda: PlaywrightManager()
    return mod


def _write_json(path, obj):
    with open(path, 'w') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def build_sandbox(root, spec):
    os.makedirs(root, exist_ok=True)
    shutil.copy(os.path.join(WT, 'config.yaml'), os.path.join(root, 'config.yaml'))
    for d in ('logs', 'metrics', 'cache', 'backups', 'overrides', 'admin'):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    for name in os.listdir(os.path.join(WT, 'overrides')):
        if name.endswith('.json'):
            shutil.copy(os.path.join(WT, 'overrides', name), os.path.join(root, 'overrides', name))
    _write_json(os.path.join(root, 'movie_tracking.json'), {'movies': spec['tracking']})
    wall = spec.get('wall') or []
    _write_json(os.path.join(root, 'data.json'), {
        'generated_at': '2026-11-14T06:00:00', 'count': len(wall), 'movies': wall,
        'staff_picks': [], 'featured': [], 'latest_playlist_url': None,
        '_metadata': {'schema_version': '2.0'}})


def _read_state(ids):
    if os.path.exists('movie_tracking.db'):
        conn = sqlite3.connect('movie_tracking.db')
        trk = {row[0]: json.loads(row[1]) for row in conn.execute('SELECT id, data FROM movies')}
        conn.close()
    else:   # nothing has opened the tracking DB yet (a hook ran first): the JSON it imports from
        with open('movie_tracking.json') as f:
            trk = json.load(f).get('movies', {})
    with open('data.json') as f:
        wall = json.load(f).get('movies', [])
    archive = []
    if os.path.exists('data_archive.json'):
        with open('data_archive.json') as f:
            archive = json.load(f).get('movies', [])
    newly = []
    if os.path.exists('metrics/newly_available.json'):
        with open('metrics/newly_available.json') as f:
            newly = [str(x) for x in json.load(f).get('movie_ids', [])]
    metrics = {}
    if os.path.exists('metrics/discovery_run.json'):
        with open('metrics/discovery_run.json') as f:
            metrics = json.load(f).get('results', {})
    return {
        'tracking': {mid: trk.get(mid) for mid in ids},
        'wall': {mid: [m for m in wall if str(m.get('id')) == mid] for mid in ids},
        'archive': {mid: [m for m in archive if str(m.get('id')) == mid] for mid in ids},
        'newly_available': newly,
        'discovery_metrics': metrics,
    }


_PIPELINE_MODULES = ('pipeline.generator', 'pipeline.discoverer', 'pipeline.enricher', 'pipeline.justwatch',
                     'pipeline.putback', 'pipeline.archive', 'pipeline.display', 'pipeline.enrichment',
                     'pipeline.storage', 'pipeline.validation', 'pipeline.tracking_db', 'pipeline.notability')


@contextlib.contextmanager
def sandbox_and_network(spec, root):
    """Chdir into a fresh sandbox holding the scenario's files; fake every network call."""
    import requests
    import requests.sessions
    import time as _time
    import urllib.request

    net = FakeNet(spec)
    p = Patcher()
    old_cwd = os.getcwd()
    build_sandbox(root, spec)
    os.chdir(root)
    try:
        p.setitem(os.environ, 'TMDB_API_KEY', 'test-key')
        p.setattr(requests, 'get', net.get)
        p.setattr(requests, 'post', net.refuse)
        p.setattr(requests, 'head', net.refuse)
        p.setattr(requests.sessions.Session, 'post', lambda s, url, *a, **k: net.session_post(s, url, *a, **k))
        p.setattr(requests.sessions.Session, 'request', lambda s, method, url, *a, **k: net.refuse(url=url))
        p.setattr(urllib.request, 'urlopen', lambda *a, **k: net.refuse(url=str(a[0]) if a else '?'))
        p.setattr(_time, 'sleep', lambda *_a, **_k: None)
        p.setitem(sys.modules, 'playwright_manager', _fake_playwright_module(net))
        # apply_admin_overrides() refreshes the distributor lookup (Wikipedia + TMDB) and
        # writes it to an ABSOLUTE path inside the worktree: point that write at the sandbox.
        try:
            import importlib
            bdl = importlib.import_module('scripts.build_distributor_lookup')
            p.setattr(bdl, 'OUTPUT_PATH', os.path.join(root, 'cache', 'distributor_lookup.json'))
        except ImportError:
            pass
        lg = logging.getLogger('data_generator')
        if not lg.handlers:          # keep setup_logger from opening a log file
            lg.addHandler(logging.NullHandler())
            lg.propagate = False
        yield net
    finally:
        os.chdir(old_cwd)
        p.undo()


@contextlib.contextmanager
def frozen_clock(day, patches=()):
    """The pipeline modules with the clock frozen at 09:00 on `day` (no DataGenerator, so it
    is safe outside a sandbox). patches: (module name, attr, value) applied meanwhile."""
    import importlib
    for name in _PIPELINE_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:          # pipeline.putback does not exist before Step 1
            pass
    p = Patcher()
    try:
        frozen = make_frozen_datetime(day)
        for name, mod in list(sys.modules.items()):
            if (name == 'pipeline' or name.startswith('pipeline.')) and getattr(mod, 'datetime', None) is _REAL_DATETIME:
                p.setattr(mod, 'datetime', frozen)
        for mod_name, attr, value in patches:
            p.setattr(importlib.import_module(mod_name), attr, value)
        yield
    finally:
        p.undo()


@contextlib.contextmanager
def generator_on(day, patches=()):
    """A fresh DataGenerator (each phase is its own generate_data.py process in production),
    with the clock frozen at 09:00 on `day`. Only inside a sandbox (it opens logs/, the
    tracking DB, data.json relative to the cwd)."""
    import pipeline.tracking_db as tracking_db
    with frozen_clock(day, patches):
        tracking_db._shared_instance = None      # TrackingDB singleton: re-open in this sandbox
        try:
            from pipeline.generator import DataGenerator
            yield DataGenerator(enrichment_enabled=False)
        finally:
            tracking_db._shared_instance = None


@contextlib.contextmanager
def pipeline_sandbox(spec, root):
    with sandbox_and_network(spec, root) as net:
        day = spec.get('today', TODAY)
        net.phase = f'{day}:unit'
        with generator_on(day) as gen:
            yield gen, net


def run_daily(spec, root, hooks=None):
    """Run the requested real daily phases on the scenario; return what the owner would see.
    spec['phases'] items are 'discover' | 'enrich' | 'gap_fill' (the order daily_orchestrator.py
    runs them: --discover, --enrich, --gap-fill), or [day, phase]. spec['phase_patches']
    {phase: [[module, attr, value]]} patches a module attribute for that phase. spec['queue_ahead']
    [ids] puts those films first in enrichment's queue (metrics/newly_available.json) before the
    'enrich' phase -- other arrivals that day, so a small batch limit cuts the scenario's film.
    A phase 'hook:<name>' runs hooks[<name>](day) in the same sandbox between phases (the
    owner acting: the admin panel, a script); its return value is kept in res['hooks']."""
    ids = list(spec['ids'])
    out = {'phases': {}, 'hooks': {}}
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        with sandbox_and_network(spec, root) as net:
            for i, step in enumerate(spec['phases']):
                day, phase = (step if isinstance(step, (list, tuple)) else (spec.get('today', TODAY), step))
                net.phase = f'{day}:{phase}'
                print(f'\n######## {day} {phase} ########')
                if phase.startswith('hook:'):
                    out['hooks'][phase[5:]] = hooks[phase[5:]](day)
                    out['phases'][f'{i}:{day}:{phase}'] = _read_state(ids)
                    continue
                patches = [tuple(x) for x in (spec.get('phase_patches') or {}).get(phase, [])]
                if phase == 'enrich' and spec.get('queue_ahead'):
                    with open(os.path.join('metrics', 'newly_available.json')) as f:
                        _na = json.load(f)
                    _na['movie_ids'] = list(spec['queue_ahead']) + [m for m in _na.get('movie_ids', [])
                                                                     if m not in spec['queue_ahead']]
                    _na['count'] = len(_na['movie_ids'])
                    with open(os.path.join('metrics', 'newly_available.json'), 'w') as f:
                        json.dump(_na, f)
                with generator_on(day, patches) as gen:
                    if phase == 'discover':
                        gen.check_tracking_movies()
                    elif phase == 'enrich':
                        gen.enrich_newly_available_movies()
                    elif phase == 'gap_fill':
                        gen.daily_gap_fill()
                    else:
                        raise ValueError(phase)
                out['phases'][f'{i}:{day}:{phase}'] = _read_state(ids)
            out['jw_queries'] = net.jw_queries
            out['pages'] = net.pages
            out['tmdb_calls'] = net.tmdb_calls
            out['blocked'] = net.blocked
    out['pipeline_dir'] = os.path.dirname(os.path.abspath(sys.modules['pipeline'].__file__))
    out['log'] = log.getvalue()[-30000:]
    return out


@contextlib.contextmanager
def admin_client(day=TODAY):
    """A Flask test client of the REAL admin app (admin.create_app), clock frozen on `day`.
    Only inside a sandbox: its routes read and write data.json, admin/*.json and the tracking
    DB relative to the cwd (admin.logging_setup also makes logs/ there on first import)."""
    assert not os.path.realpath(os.getcwd()).startswith(os.path.realpath(WT)), 'admin app outside a sandbox'
    import importlib
    import pipeline.tracking_db as tracking_db
    lg = logging.getLogger('admin')
    if not lg.handlers:              # keep setup_logger from opening logs/admin.log
        lg.addHandler(logging.NullHandler())
        lg.propagate = False
    importlib.import_module('admin.routes.movies')
    p = Patcher()                    # never log through a handler another test opened elsewhere
    p.setattr(lg, 'handlers', [logging.NullHandler()])
    p.setattr(lg, 'propagate', False)
    try:
        with frozen_clock(day, patches=[('admin.routes.movies', 'datetime', make_frozen_datetime(day))]):
            tracking_db._shared_instance = None      # get_tracking_db(): this sandbox's DB
            try:
                from admin import create_app
                app = create_app()
                app.config['TESTING'] = True
                yield app.test_client()
            finally:
                tracking_db._shared_instance = None
    finally:
        p.undo()


def admin_post(path, payload):
    """A hook: the owner clicks a button in the admin panel (POST path, JSON payload).
    Returns the HTTP status, the JSON reply and whether the 'changes pending' flag is set."""
    def hook(day):
        with admin_client(day) as client:
            r = client.post(path, json=payload)
            return {'status': r.status_code, 'json': r.get_json(),
                    'pending_flag': os.path.exists(os.path.join('admin', '.pending_changes'))}
    return hook


def run_script(script, *args, day=TODAY):
    """Run one of the repo's scripts as the owner does (python3 scripts/x.py ...) with the
    cwd in the current sandbox: a subprocess under the same write audit (see _main_script),
    clock frozen on `day`. Returns {'exit', 'stdout'}."""
    assert not os.path.realpath(os.getcwd()).startswith(os.path.realpath(WT)), 'script run outside a sandbox'
    out_path = os.path.join(os.getcwd(), '..', f'script_result_{os.getpid()}.json')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('NRW_STEP1_TEST_CODE_ROOT', None)
    proc = subprocess.run([sys.executable, '-c', _RUN_SELF, os.path.abspath(__file__), '--run-script', out_path, day,
                           os.path.join(WT, script), *args],
                          cwd=os.getcwd(), env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f'script runner failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-6000:]}'
    with open(out_path) as f:
        res = json.load(f)
    os.remove(out_path)
    assert not res['write_audit'], f'{script} tried to write the worktree: {res["write_audit"][:10]}'
    return {'exit': res['exit'], 'stdout': res['stdout']}


def script_hook(script, *args):
    return lambda day: run_script(script, *args, day=day)


def final(res):
    return res['phases'][list(res['phases'])[-1]]


def after(res, phase, day=None):
    """State after the first `phase` (optionally on `day`)."""
    for k, st in res['phases'].items():
        _i, d, ph = k.split(':', 2)
        if ph == phase and (day is None or d == day):
            return st
    raise KeyError(f'{phase} {day or ""} did not run')


# ----------------------------------------------------------------------------------
# What the site shows (assets/app.js): reverted/hidden/dateless entries are dropped;
# _is_preorder entries appear only in the PRE-ORDER view.
# ----------------------------------------------------------------------------------

def visible(entry):
    return bool(entry) and not entry.get('hidden') and entry.get('_enrichment_status') != 'reverted' \
        and bool(entry.get('digital_date'))


def on_main_wall(entry):
    return visible(entry) and not entry.get('_is_preorder')


def in_preorder_lane(entry):
    return visible(entry) and bool(entry.get('_is_preorder'))


def only(entries):
    assert len(entries) <= 1, f'duplicate wall entries: {[(e.get("id"), e.get("title")) for e in entries]}'
    return entries[0] if entries else None


def jw_titles(res, phase=None, day=None):
    """Titles JustWatch was asked about (optionally only during `phase` / on `day`)."""
    out = []
    for ph, q in res['jw_queries']:
        d, _, p = ph.rpartition(':')
        if (phase is None or p == phase) and (day is None or d == day):
            out.append(q)
    return out


def vod_services(entry):
    wl = ((entry or {}).get('watch_links') or {})
    vod = wl.get('vod') or []
    vod = vod if isinstance(vod, list) else [vod]
    return sorted({(v.get('service') or '') for v in vod if isinstance(v, dict) and v.get('link')})


def brief(entry, *extra):
    keys = ('hidden', '_is_preorder', '_buyonly_preorder', '_jw_unconfirmed', '_enrichment_status', 'digital_date',
            '_digital_date_source') + extra
    return None if entry is None else {k: entry.get(k) for k in keys if k in entry}


def brief_rec(rec, *extra):
    keys = ('status', 'digital_date', '_digital_date_source', '_buyonly_preorder', '_is_preorder', '_type4_pending',
            '_jw_revert_count', '_jw_revert_reason', '_jw_last_checked', '_jw_last_refuted', '_put_back_on') + extra
    return None if rec is None else {k: rec.get(k) for k in keys if k in rec}


def scenario(ids, wall_ids=(), phases=('discover', 'enrich', 'gap_fill'), tracking_over=None, tmdb_over=None,
             jw_over=None, pages=None, today=TODAY, background=True, wall_over=None, jw_days=None,
             jw_outage=None, jw_malformed=(), tmdb_fail=(), phase_patches=None):
    F = fixtures()
    tracking = {mid: copy.deepcopy(F['tracking'][mid]) for mid in ids}
    for mid, fields in (tracking_over or {}).items():
        for k, v in fields.items():
            if v is _MISSING:
                tracking[mid].pop(k, None)
            else:
                tracking[mid][k] = v
    wall = (copy.deepcopy(F['background_wall']) if background else []) + [copy.deepcopy(F['wall'][m]) for m in wall_ids]
    for entry in wall:
        for k, v in ((wall_over or {}).get(str(entry.get('id'))) or {}).items():
            if v is _MISSING:
                entry.pop(k, None)
            else:
                entry[k] = v
    tmdb = {mid: copy.deepcopy(F['tmdb'][mid]) for mid in ids if mid in F['tmdb']}
    tmdb.update(copy.deepcopy(tmdb_over or {}))
    jw = {mid: copy.deepcopy(F['jw'].get(mid)) for mid in ids}
    jw.update(copy.deepcopy(jw_over or {}))
    return {'ids': list(ids), 'tracking': tracking, 'wall': wall, 'tmdb': tmdb, 'jw': jw,
            'jw_days': copy.deepcopy(jw_days or {}), 'jw_outage': dict(jw_outage or {}),
            'jw_malformed': list(jw_malformed), 'tmdb_fail': [list(x) for x in tmdb_fail],
            'pages': [list(x) for x in (pages or [])], 'phases': list(phases), 'today': today,
            'phase_patches': copy.deepcopy(phase_patches or {})}


def two_days(*days, phases=('discover', 'enrich', 'gap_fill')):
    return [(d, p) for d in days for p in phases]


def _json_spec(spec):
    """_MISSING markers never reach a spec; make sure it serialises for the subprocess."""
    return json.loads(json.dumps(spec))


# ----------------------------------------------------------------------------------
# Production code (78303fd6) for the regression guard
# ----------------------------------------------------------------------------------

@pytest.fixture(scope='session')
def head_code_root(tmp_path_factory):
    root = tmp_path_factory.mktemp('production_code')
    names = subprocess.check_output(
        ['git', '-C', WT, 'ls-tree', '-r', '--name-only', PRODUCTION, 'pipeline/'], text=True).split()
    assert 'pipeline/discoverer.py' in names and 'pipeline/putback.py' not in names
    for name in names:
        blob = subprocess.check_output(['git', '-C', WT, 'show', f'{PRODUCTION}:{name}'])
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
    return str(root)


# Start this file in a subprocess through runpy, never as `python3 <this file>`: Python 3.9's
# file tokenizer mis-decodes a multi-byte character that straddles its read buffer in the very
# long fixture line at the end ("SyntaxError: Non-UTF-8 code"); runpy compiles from bytes, as
# an import does.
_RUN_SELF = "import runpy, sys; sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"


def run_daily_with_code(code_root, spec, work):
    """Run the same scenario in a subprocess whose `pipeline` package is `code_root`'s."""
    os.makedirs(work, exist_ok=True)
    spec_path = os.path.join(work, 'spec.json')
    out_path = os.path.join(work, 'result.json')
    _write_json(spec_path, _json_spec(spec))
    env = dict(os.environ, NRW_STEP1_TEST_CODE_ROOT=code_root, PYTHONDONTWRITEBYTECODE='1')
    proc = subprocess.run([sys.executable, '-c', _RUN_SELF, os.path.abspath(__file__), '--run-spec', spec_path,
                           out_path, os.path.join(work, 'sandbox')],
                          env=env, cwd=work, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, f'scenario runner failed ({code_root}):\n{proc.stdout[-3000:]}\n{proc.stderr[-6000:]}'
    with open(out_path) as f:
        res = json.load(f)
    assert not res.get('write_audit'), f'production-code run tried to write the worktree: {res["write_audit"][:10]}'
    return res


# ==================================================================================
# (a) Pending pre-orders re-read TMDB's date every run
# ==================================================================================

def test_a1_moved_tmdb_date_lands_past_due_preorder_on_main_wall_after_justwatch_confirms(tmp_path):
    """Spa Weekend sat in the pending lane on a mistyped 2028-09-22 while TMDB said
    2026-09-22. Discovery re-reads TMDB daily: the date moves into the past. Spa Weekend is
    a HELD buy-only pre-order, so JustWatch decides in discovery: the captured response has
    a live Amazon rental (offer start 2026-11-10), so it graduates and is put back. After the
    daily run it is on the main wall, dated TMDB's corrected date -- the earliest evidence
    after its 2026-09-15 'no valid offers' check (v2 put-back dating)."""
    res = run_daily(scenario([SPA_WEEKEND]), str(tmp_path / 'sbx'))
    disc, end = after(res, 'discover'), final(res)

    assert 'Spa Weekend' in jw_titles(res, 'discover'), 'discovery did not ask JustWatch'
    rec = disc['tracking'][SPA_WEEKEND]
    assert rec['status'] == 'available' and rec['digital_date'] == '2026-09-22', brief_rec(rec)
    entry = only(end['wall'][SPA_WEEKEND])
    assert on_main_wall(entry), f'not on the main wall after the daily run: {brief(entry)}'
    assert entry['digital_date'] == '2026-09-22'
    assert 'Spa Weekend' in jw_titles(res, 'enrich'), "reached the main wall without enrichment's JustWatch check"
    assert {'Amazon', 'Apple TV', 'Fandango'} & set(vod_services(entry)), vod_services(entry)
    assert end['tracking'][SPA_WEEKEND]['status'] == 'available'


def test_a2_moved_tmdb_date_without_a_justwatch_offer_keeps_film_off_the_main_wall(tmp_path):
    """Same record, but the day JustWatch shows Spa Weekend only in cinemas (the CINEMA offer
    of the captured response, no rent/buy/stream): the corrected TMDB date alone must not put
    it on the main wall (rules 3/4); it stays held in tracking for the next run (rule 2).
    Changed in v2 on purpose: its pending date has arrived and it is a buy-only pre-order, so
    the Type-4 branch's buy-only check asks JustWatch IN DISCOVERY (v1 let it through the
    pre-order graduation bypass and only enrichment asked), and today is kept as a 'not out
    yet' day."""
    node = jw_node(SPA_WEEKEND)
    node['offers'] = [o for o in node['offers'] if o['monetizationType'] == 'CINEMA']
    assert node['offers'], 'fixture lost its CINEMA offer'
    res = run_daily(scenario([SPA_WEEKEND], jw_over={SPA_WEEKEND: node}), str(tmp_path / 'sbx'))
    end = final(res)

    assert 'Spa Weekend' in jw_titles(res, 'discover'), 'JustWatch was never asked'
    assert not on_main_wall(only(end['wall'][SPA_WEEKEND])), 'TMDB date alone put it on the main wall'
    rec = end['tracking'][SPA_WEEKEND]
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), f'not held for re-check: {brief_rec(rec)}'
    assert rec.get('digital_date') == '2026-09-22', rec.get('digital_date')
    assert rec.get('_jw_last_checked') == TODAY and rec.get('_jw_last_refuted') == TODAY, brief_rec(rec)


def test_a3_moved_tmdb_date_reaches_the_preorder_lane_of_a_film_already_on_the_wall(tmp_path):
    """Wicker is a pending pre-order already shown in the PRE-ORDER lane for 2026-12-01;
    TMDB has since moved its digital date to 2026-11-24. After the daily run the PRE-ORDER
    lane shows the corrected date. (v1 xfail -- fixed in v2: update_wall_entry_date.)"""
    res = run_daily(scenario([WICKER], wall_ids=[WICKER]), str(tmp_path / 'sbx'))
    end = final(res)

    assert end['tracking'][WICKER]['digital_date'] == '2026-11-24'
    entry = only(end['wall'][WICKER])
    assert in_preorder_lane(entry), brief(entry)
    assert entry['digital_date'] == '2026-11-24', \
        f'PRE-ORDER lane still shows {entry["digital_date"]} (TMDB: 2026-11-24)'
    assert entry.get('_digital_date_source') == 'tmdb_type4'


def test_a4_tmdb_date_moved_later_keeps_the_preorder_entry_off_the_main_wall(tmp_path):
    """Wicker's stored date -- tracking and its PRE-ORDER entry (staged: both set to today,
    2026-11-14) -- has passed, but TMDB has moved it to 2026-11-24 and JustWatch shows
    cinemas only. The entry must move to 2026-11-24 with tracking: a stale 'today' let
    enrichment graduate it onto the main wall unchecked (review S5e). Spa Weekend, an
    unrelated arrival, makes enrichment run and save data.json as on any production day."""
    spec = scenario([WICKER, SPA_WEEKEND], wall_ids=[WICKER], tracking_over={WICKER: {'digital_date': TODAY}},
                    wall_over={WICKER: {'digital_date': TODAY}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    disc, end = after(res, 'discover'), final(res)

    assert disc['tracking'][WICKER]['digital_date'] == '2026-11-24'
    assert only(disc['wall'][WICKER])['digital_date'] == '2026-11-24'
    entry = only(end['wall'][WICKER])
    assert in_preorder_lane(entry) and entry['digital_date'] == '2026-11-24', brief(entry)
    assert end['tracking'][WICKER]['status'] == 'tracking'
    assert on_main_wall(only(end['wall'][SPA_WEEKEND])), 'the control arrival did not land'


# ==================================================================================
# (b) A pending pre-order missing from data.json: no re-add, no loop, checked daily
#     (v1's re-add is gone in v2 -- these are the inverted v1 tests)
# ==================================================================================

def test_b1_pending_preorder_missing_from_data_json_is_not_readded_but_checked_daily(tmp_path):
    """The Odyssey is a held pending pre-order (TMDB digital 2026-11-17, one 'no valid
    offers' check) with no data.json entry. v1 re-added such films to the PRE-ORDER lane
    every run and enrichment purged them again (69 re-adds a day). v2 removed the re-add:
    no entry is created, and the film waits in tracking -- still pending on its TMDB date --
    with JustWatch asked about it in today's discovery (a held film with a future date is
    checked every run, round 2) and today kept as a 'not out yet' day."""
    res = run_daily(scenario([THE_ODYSSEY]), str(tmp_path / 'sbx'))
    end = final(res)

    for name, st in res['phases'].items():
        assert not st['wall'][THE_ODYSSEY], f'{name}: re-added to data.json: {brief(only(st["wall"][THE_ODYSSEY]))}'
        assert not st['archive'][THE_ODYSSEY], f'{name}: archived'
    assert 'The Odyssey' in jw_titles(res, 'discover'), 'held pending pre-order was not checked today'
    rec = end['tracking'][THE_ODYSSEY]
    assert rec['status'] == 'tracking' and rec.get('_type4_pending') and rec.get('digital_date') == '2026-11-17', \
        brief_rec(rec)
    assert rec.get('_jw_last_refuted') == TODAY, brief_rec(rec)


@pytest.mark.parametrize('mid,refuted', [(RUN_TERRY_RUN, None), (RAY_GUNN, '2026-11-15')],
                         ids=['Run_Terry_Run-jw_no_match', 'Ray_Gunn-jw_no_offers'])
def test_b2_held_pending_preorders_have_no_add_purge_loop_and_are_checked_every_run(mid, refuted, tmp_path):
    """Two more real held pending pre-orders with no data.json entry (TMDB 2026-11-24 and
    2026-12-18, still ahead; JustWatch: no listing / a listing with no offers). v1 re-added
    them nightly and enrichment reverted + purged them the same run (v1 xfail). Over two
    daily runs v2 never adds them (no loop), never drops them (still pending in tracking),
    and asks JustWatch about each in every discovery run (rule 2). Only a real 'no valid
    offers' answer is kept as a 'not out yet' day; a no-match proves nothing."""
    res = run_daily(scenario([mid], phases=two_days(TODAY, '2026-11-15')), str(tmp_path / 'sbx'))
    title = fixtures()['tracking'][mid]['title']

    for name, st in res['phases'].items():
        assert not st['wall'][mid] and not st['archive'][mid], \
            f'{name}: on the wall/archive: {brief(only(st["wall"][mid]))} {st["archive"][mid][:1]}'
    for day in (TODAY, '2026-11-15'):
        assert title in jw_titles(res, 'discover', day), f'not checked by discovery on {day}'
    rec = final(res)['tracking'][mid]
    assert rec['status'] == 'tracking' and rec.get('_type4_pending'), brief_rec(rec)
    assert rec.get('digital_date') == fixtures()['tracking'][mid]['digital_date'], brief_rec(rec)
    assert rec.get('_jw_last_refuted') == refuted, brief_rec(rec)


# ==================================================================================
# (c) TMDB date lookups
# ==================================================================================

def test_c1_type4_lookup_returns_the_earliest_us_digital_date(tmp_path):
    """I Swear: TMDB lists its 2026-08-22 Netflix date before its 2026-06-02 rental date.
    DataGenerator.fetch_tmdb_type4_date must return 2026-06-02 (the day it first became
    watchable), not the first one listed."""
    payload = fixtures()['tmdb'][I_SWEAR]['release_dates']
    listed = [r['release_date'][:10] for e in payload['results'] if e['iso_3166_1'] == 'US'
              for r in e['release_dates'] if r['type'] == 4]
    assert listed == ['2026-08-22', '2026-06-02'], f'captured payload changed: {listed}'

    spec = scenario([I_SWEAR], phases=())
    with contextlib.redirect_stdout(io.StringIO()):
        with pipeline_sandbox(spec, str(tmp_path / 'sbx')) as (gen, net):
            got = gen.fetch_tmdb_type4_date(I_SWEAR)
            got_int = gen.fetch_tmdb_type4_date(int(I_SWEAR))
    assert got == '2026-06-02'
    assert got_int == '2026-06-02'


def test_c2_us_release_dates_lookup_returns_the_earliest_pair_or_none_when_tmdb_fails(tmp_path):
    """fetch_tmdb_us_release_dates (put-back dating) on Beware Boiúna's real TMDB payload:
    (earliest US theatrical, earliest US digital) = (2026-10-02, 2026-11-03) -- the Fantastic
    Fest premiere (type 1) is not a theatrical date. A TMDB failure returns None, not
    (None, None): an unknown date is not a missing one (v2). No US dates -> (None, None)."""
    spec = scenario([BEWARE_BOIUNA, QUEEN_AT_SEA, HIS_MONSTER], phases=(),
                    tmdb_fail=[(QUEEN_AT_SEA, '/release_dates')])
    with contextlib.redirect_stdout(io.StringIO()):
        with pipeline_sandbox(spec, str(tmp_path / 'sbx')) as (gen, net):
            got = gen.fetch_tmdb_us_release_dates(BEWARE_BOIUNA)
            failed = gen.fetch_tmdb_us_release_dates(QUEEN_AT_SEA)
            no_us = gen.fetch_tmdb_us_release_dates(HIS_MONSTER)
    assert got == ('2026-10-02', '2026-11-03')
    assert failed is None
    assert no_us == (None, None)


# ==================================================================================
# (d0) JustWatch: what counts as a LIVE rental (has_live_rent) and the dating record
# ==================================================================================

def _excluded_services(gen):
    return gen.config.get('tracking', {}).get('excluded_services', [])


def _verify(spec, root, mid):
    """The real JustWatchClient.verify_availability for one film, network faked."""
    rec = spec['tracking'][mid]
    with contextlib.redirect_stdout(io.StringIO()):
        with pipeline_sandbox(spec, root) as (gen, net):
            from pipeline.justwatch import JustWatchClient
            return JustWatchClient(logger=logging.getLogger('test_step1_preorders')).verify_availability(
                rec['title'], rec.get('year'), excluded_services=_excluded_services(gen), content_type='movie',
                original_title=rec.get('original_title'), tmdb_id=mid)


@pytest.mark.parametrize('extra,rent,live', [
    pytest.param((), False, False, id='captured-BUY_Apple_TV_Store_only'),
    pytest.param(('amazon',), True, True, id='Amazon_Video-amazon_rental_offer_start_today'),
    pytest.param(('amazon_later_today',), True, False, id='Amazon_rental_offer_start_2h_from_now'),
    pytest.param(('amazon_no_start',), True, False, id='Amazon_rental_without_an_offer_start'),
    pytest.param(('amazon_preorder',), True, False, id='Amazon_rental_offer_start_Dec_4'),
    pytest.param(('fandango',), True, False, id='Fandango_At_Home-vudu_RENT_no_offer_start-DreamQuil_shape'),
    pytest.param(('fandango_started',), True, False, id='Fandango_At_Home-vudu_RENT_offer_start_passed'),
    pytest.param(('apple',), True, False, id='Apple_TV_Store-itunes_rental'),
    pytest.param(('apple_tv_name',), True, False, id='Apple_TV-itunes_rental'),
    pytest.param(('fandango', 'amazon_preorder', 'apple'), True, False, id='Apple_next_to_two_preorder_rentals'),
])
def test_d0a_has_live_rent_is_amazon_past_its_offer_start(extra, rent, live, tmp_path):
    """verify_availability's has_live_rent: a RENT offer JustWatch shows as live NOW -- only
    Amazon's ('Amazon Video' / 'amazon') with availableFromTime already passed (round 2c).
    Stores list pre-order rentals as plain RENT offers (Fandango At Home: DreamQuil, 'available
    to watch on dec 4 -- preorder'), so a Fandango At Home ('vudu') RENT is never live -- even
    with an offer start in the past -- nor an Amazon rental whose offer start is still ahead or
    missing, nor Apple's store ('Apple TV Store' / 'itunes'), which lists rentals from the
    theater opening with the theatrical date as offer start (round 2b counted it live). Tom and
    Jerry's captured node plus staged offers."""
    later = _z(frozen_now_utc() + _dt.timedelta(hours=2))
    staged = {'amazon': amazon_rent('B0TJSTAGED'), 'amazon_preorder': amazon_preorder_rent('B0TJSTAGED'),
              'amazon_later_today': amazon_rent_from('B0TJLATER', later),
              'amazon_no_start': amazon_rent_from('B0TJNOSTART', None),
              'fandango': fandango_preorder_rent(TJ_FANDANGO_URL),
              'fandango_started': fandango_rent_started(TJ_FANDANGO_URL),
              'apple': apple_store_rent(tj_apple_url()), 'apple_tv_name': apple_tv_named_rent(tj_apple_url())}
    assert later[:10] == TODAY, f'the 2h-later offer start must still be today: {later}'
    node = jw_node(TOM_AND_JERRY, *[staged[x] for x in extra])
    spec = scenario([TOM_AND_JERRY], phases=(), jw_over={TOM_AND_JERRY: node})
    r = _verify(spec, str(tmp_path / 'sbx'), TOM_AND_JERRY)

    assert r and r['match_confidence'] != 'first_result', r
    assert r['has_rent'] is rent, r
    assert r['has_live_rent'] is live, (r['has_live_rent'], r['provider_names'])
    assert r['buy_only'] is (not rent), r
    assert 'amazon_available_from' not in r, 'v1 field still returned'


def test_d0b_dreamquil_fandango_preorder_rental_is_a_rental_but_not_live(tmp_path):
    """DreamQuil (its own record; JustWatch's real shape: one Fandango At Home RENT with no
    offer start, a Dec 4 pre-order): verified (it has a rental) but has_live_rent False."""
    spec = scenario([DREAMQUIL], phases=())
    r = _verify(spec, str(tmp_path / 'sbx'), DREAMQUIL)
    assert r['verified'] is True and r['has_rent'] is True and r['buy_only'] is False, r
    assert r['has_live_rent'] is False, r
    assert r['offer_dates'] == ['2026-11-10'] and r['first_offer_date'] == '2026-11-10', r


def test_d0c_offer_dates_are_record_days_of_real_ways_to_watch_it(tmp_path):
    """offer_dates (v2's dating evidence, replacing amazon_available_from): the sorted,
    distinct dateCreated days of the qualifying rent/buy/stream offers -- not a cinema
    listing, not a disc, not JustWatch's 2000-07-14 placeholder (before the film's year),
    not a future record; first_offer_date is the earliest. Tom and Jerry's captured node
    (Apple BUY recorded 2026-09-04) plus staged offers of each kind."""
    extra = [offer('CINEMA', 'Regal Cinemas', 'regalcinemas', 'https://www.regmovies.com/movies/tj', None, None,
                   '2026-08-01T00:00:00Z', 'CANVAS'),
             offer('BUY', 'Amazon DVD / Blu-ray', 'amazondvdbr', 'https://www.amazon.com/dp/tj', '$19.95', None,
                   '2026-08-02T00:00:00Z', 'DVD'),
             offer('BUY', 'Barnes & Noble', 'barnesandnoble', 'https://www.barnesandnoble.com/w/tj', '$24.99', None,
                   '2026-08-03T00:00:00Z', 'DVD'),
             offer('RENT', 'Fandango At Home', 'vudu', TJ_FANDANGO_URL, '$4.99', None, '2000-07-14T00:00:00Z'),
             amazon_rent('B0TJFUTURE', day='2026-12-01'),
             amazon_rent('B0TJSTAGED', day='2026-11-12')]
    spec = scenario([TOM_AND_JERRY], phases=(), jw_over={TOM_AND_JERRY: jw_node(TOM_AND_JERRY, *extra)})
    r = _verify(spec, str(tmp_path / 'sbx'), TOM_AND_JERRY)
    assert r['offer_dates'] == ['2026-09-04', '2026-11-12'], r['offer_dates']
    assert r['first_offer_date'] == '2026-09-04'


# ==================================================================================
# (d1) The daily buy-only check: _jw_shows_rent_or_stream is tri-state
# ==================================================================================

def _jw_shows(spec, root, mid, search_override=None):
    """ProviderDiscoverer._jw_shows_rent_or_stream on the real record; returns
    (answer, net, discoverer)."""
    with contextlib.redirect_stdout(io.StringIO()):
        with pipeline_sandbox(spec, root) as (gen, net):
            disc = gen._discoverer
            p = Patcher()
            try:
                if search_override is not None:
                    from pipeline.justwatch import JustWatchClient
                    p.setattr(JustWatchClient, 'search_movie', lambda self, *a, **k: copy.deepcopy(search_override))
                answer = disc._jw_shows_rent_or_stream(mid, copy.deepcopy(spec['tracking'][mid]))
            finally:
                p.undo()
            return answer, net, disc


_D1_CASES = [
    # id, film, staged offers, store pages, expected answer, page visited?
    ('streaming_Netflix', TOM_AND_JERRY, ('netflix',), (), True, False),
    ('live_Amazon_rental', TOM_AND_JERRY, ('amazon',), (), True, True),   # the page is read first (Last Blossom)
    # Its own Apple purchase (real record), out of theaters: buyable, so out (owner, Nov 2026)
    ('Fandango_preorder_rental-page_unreadable', TOM_AND_JERRY, ('fandango',), (), True, True),
    ('Fandango_preorder_rental-page_reads_preorder', TOM_AND_JERRY, ('fandango',),
     ((TJ_FANDANGO_URL, DREAMQUIL_PAGE_TEXT),), False, True),
    ('Fandango_rental-page_reads_rent_now', TOM_AND_JERRY, ('fandango',), ((TJ_FANDANGO_URL, LIVE_PAGE_TEXT),),
     True, True),
    # Its own Apple purchase has already started (real record): out, whatever the Amazon
    # pre-order next to it says (a future start counts only when nothing has started).
    ('Amazon_preorder_rental-offer_start_Dec_4', TOM_AND_JERRY, ('amazon_preorder',), (), True, True),
    ('still_buy_only', TOM_AND_JERRY, (), (), True, True),   # buy-only on Apple, out of theaters: out
    ('festival_Eventive_listing_only', QUEEN_AT_SEA, ('eventive',), (), False, False),
    ('festival_Shift72_listing_only', QUEEN_AT_SEA, ('shift72',), (), False, False),
    ('streaming_Sundance_Now-not_a_festival', TOM_AND_JERRY, ('sundance_now',), (), True, False),
    ('DreamQuil_own_record_and_shape', DREAMQUIL, None, (), False, True),
    ('Apple_TV_Store_rental-page_unreadable', TOM_AND_JERRY, ('apple',), (), True, True),
    ('no_offers_at_all-JustWatch_healthy', TOM_AND_JERRY, 'no_offers', (), False, False),
]


def _d1_params():
    return [pytest.param(*case[1:], id=case[0]) for case in _D1_CASES]


@pytest.mark.parametrize('mid,extra,pages,expected,page_visited', _d1_params())
def test_d1a_daily_buy_only_check_answers_true_only_for_a_way_to_watch_it_now(
        mid, extra, pages, expected, page_visited, tmp_path):
    """The daily JustWatch check for a buy-only pre-order, by the pre-order labeler (owner, Nov
    2026: "buy-only is buyable"). True = out: streaming (Sundance Now included), a live Amazon
    rental, a page reading available, or a digital purchase/rental out of theaters (Tom and
    Jerry's real Apple purchase). False = positive pre-order evidence: a page reading
    'preorder', an Amazon offer whose start is still ahead, a Fandango-only listing whose page
    can't be read (DreamQuil), a festival's own Eventive / Shift72 page (not a store), no offers
    at all (canary healthy). Real records; staged offers (see the ids)."""
    staged = {'netflix': netflix_stream('tj-staged'), 'amazon': amazon_rent('B0TJSTAGED'),
              'amazon_preorder': amazon_preorder_rent('B0TJSTAGED'), 'apple': apple_store_rent(tj_apple_url()),
              'fandango': fandango_preorder_rent(TJ_FANDANGO_URL), 'eventive': eventive_rent(),
              'shift72': shift72_rent(), 'sundance_now': sundance_now_stream('tj-staged')}
    if extra is None:
        jw_over = {}
    elif extra == 'no_offers':
        jw_over = {mid: jw_node(mid, offers=[])}
    else:
        jw_over = {mid: jw_node(mid, *[staged[x] for x in extra])}
    spec = scenario([mid], phases=(), jw_over=jw_over, pages=pages)
    answer, net, disc = _jw_shows(spec, str(tmp_path / 'sbx'), mid)

    assert answer is expected, f'answer {answer!r}, expected {expected!r}; pages visited: {net.pages}'
    assert bool(net.pages) is page_visited, net.pages
    assert disc._jw_lookups == 1 and disc._jw_errors == 0
    if extra == 'no_offers':
        assert disc._jw_healthy is True, 'a no-offers answer must be checked against the canary first'


def _tj_other_film_node():
    """A DIFFERENT film's JustWatch node (another Tom and Jerry title, another TMDB id)."""
    n = jw_node(TOM_AND_JERRY, amazon_rent('B0OTHER'))
    n['content'] = dict(n['content'], title='Tom and Jerry: Cowboy Up!', originalReleaseYear=2022,
                        externalIds={'tmdbId': '903939'}, fullPath='/us/movie/tom-and-jerry-cowboy-up')
    return n


@pytest.mark.parametrize('how', ['malformed_reply_offers_null', 'http_500', 'no_match', 'title_mismatch',
                                 'empty_offers_outage'])
def test_d1b_daily_buy_only_check_answers_none_when_justwatch_cannot_answer(how, tmp_path):
    """None = JustWatch could not answer about this film: a malformed reply (the lookup
    raises), an HTTP error, no match, a different film's result (title mismatch), or an
    outage that returns every title -- the control titles too -- with an empty offer list
    (round 2b: the canary is consulted before a no-offers reply counts). None says nothing
    about availability (rule 5): the caller records nothing. Only an error counts in
    _jw_errors (metrics)."""
    kw, override = {}, None
    if how == 'malformed_reply_offers_null':
        kw['jw_malformed'] = [TOM_AND_JERRY]
    elif how == 'http_500':
        kw['jw_outage'] = {'unit': 'http_500'}
    elif how == 'no_match':
        kw['jw_over'] = {TOM_AND_JERRY: None}
    elif how == 'empty_offers_outage':
        kw['jw_outage'] = {'unit': 'empty_offers'}
    else:
        override = _tj_other_film_node()
    spec = scenario([TOM_AND_JERRY], phases=(), **kw)
    answer, net, disc = _jw_shows(spec, str(tmp_path / 'sbx'), TOM_AND_JERRY, search_override=override)

    assert answer is None, answer
    # Errors (a malformed reply, an HTTP/network error) are counted for /morning (round 2c:
    # API errors were uncounted); a no-match or an outage's empty answer is not an error.
    assert disc._jw_errors == (1 if how in ('malformed_reply_offers_null', 'http_500') else 0)
    assert not net.pages
    if how == 'empty_offers_outage':
        assert disc._jw_healthy is False, 'the canary was not consulted'
        assert 'Oppenheimer' in [q for _ph, q in net.jw_queries], net.jw_queries


# ==================================================================================
# (d2) _buyonly_still_waiting: what a daily check records
# ==================================================================================

@pytest.mark.parametrize('case', ['still_buy_only', 'jw_error', 'live_rental', 'live_rental_date_today',
                                  'tmdb_lists_a_rental', 'not_a_buy_only_preorder'])
def test_d2_buy_only_wait_records_only_real_answers(case, tmp_path):
    """ProviderDiscoverer._buyonly_still_waiting on Beware Boiúna's real record (a buy-only
    pre-order with both flags). Buy-only on JustWatch -- digital purchases on Amazon, Apple and
    Fandango, out of theaters -- is OUT by the pre-order labeler (owner, Nov 2026: "buy-only is
    buyable"; its real Amazon page reads "Buy UHD $14.99"): it graduates, dated by JustWatch's
    first offer record, never a "not out yet" day. A live rental -> graduates the same way. A
    JustWatch error -> waits, nothing recorded (rule 5). TMDB listing a rental graduates it
    without a JustWatch call (the provider path checks next). A film that is not a buy-only
    pre-order never waits here and costs no lookup."""
    kw = {}
    if case == 'jw_error':
        kw['jw_outage'] = {'unit': 'http_500'}
    elif case.startswith('live_rental'):
        kw['jw_over'] = {BEWARE_BOIUNA: jw_node(BEWARE_BOIUNA, amazon_rent('B0BBSTAGED', price='$5.99'))}
    spec = scenario([BEWARE_BOIUNA], phases=(), **kw)
    rec = copy.deepcopy(spec['tracking'][BEWARE_BOIUNA])
    if case == 'not_a_buy_only_preorder':
        rec.pop('_buyonly_preorder')
    with contextlib.redirect_stdout(io.StringIO()):
        with pipeline_sandbox(spec, str(tmp_path / 'sbx')) as (gen, net):
            waits = gen._discoverer._buyonly_still_waiting(
                BEWARE_BOIUNA, rec, tmdb_rent_or_stream=(case == 'tmdb_lists_a_rental'),
                date_today=(case == 'live_rental_date_today'))
    asked = len(net.jw_queries)

    if case in ('still_buy_only', 'live_rental', 'live_rental_date_today'):
        assert waits is False and asked == 1
        assert not rec.get('_buyonly_preorder') and not rec.get('_is_preorder'), brief_rec(rec)
        assert '_jw_last_refuted' not in rec
        dd = rec.get('digital_date')
        assert dd and dd <= TODAY, brief_rec(rec)   # its first offer record, not the check's day
    elif case == 'jw_error':
        assert waits is True and asked >= 1
        assert rec.get('_buyonly_preorder') and rec.get('_is_preorder')
        assert '_jw_last_checked' not in rec and '_jw_last_refuted' not in rec, brief_rec(rec)
    elif case == 'tmdb_lists_a_rental':
        assert waits is False and asked == 0
        assert not rec.get('_buyonly_preorder') and not rec.get('_is_preorder'), brief_rec(rec)
        assert '_jw_last_refuted' not in rec and rec.get('digital_date') is None, brief_rec(rec)
    else:
        assert waits is False and asked == 0 and '_jw_last_checked' not in rec


# ==================================================================================
# (d3) Buy-only pre-orders: the provider path, end to end (Tom and Jerry, real records)
# ==================================================================================

# Tom and Jerry's first JustWatch offer record (its Apple TV Store purchase, recorded 2026-09-04):
# buyable out of theaters is out (owner, Nov 2026), so a graduation is dated that day.
TJ_FIRST_OFFER = '2026-09-04'


def _tj(*extra, **kw):
    return scenario([TOM_AND_JERRY], wall_ids=[TOM_AND_JERRY], jw_over={TOM_AND_JERRY: jw_node(TOM_AND_JERRY, *extra)},
                    **kw)


def test_d3a_live_justwatch_rental_graduates_buy_only_preorder_and_syncs_its_wall_entry(tmp_path):
    """TMDB still lists Tom and Jerry: Forbidden Compass as buy-only (Apple TV Store), but
    JustWatch now shows a live Amazon rental (staged: offer start today 00:00 ET). The daily
    JustWatch check graduates it in discovery: out of the buy-only hold, 'available', dated
    today, queued for enrichment -- and (round 2) its existing PRE-ORDER wall entry is
    brought up to date at the transition: pre-order flags and pre_order_links gone, today's
    date. Changed from v1: v1's fixture added an Apple TV Store rental (test_d3d)."""
    res = run_daily(_tj(amazon_rent('B0TJSTAGED'), phases=('discover',)), str(tmp_path / 'sbx'))
    disc = after(res, 'discover')
    rec = disc['tracking'][TOM_AND_JERRY]

    assert 'Tom and Jerry: Forbidden Compass' in jw_titles(res, 'discover'), 'JustWatch was not checked'
    assert rec['status'] == 'available', f'still held: {brief_rec(rec)}'
    assert not rec.get('_buyonly_preorder') and not rec.get('_is_preorder')
    assert rec.get('digital_date') == TJ_FIRST_OFFER
    assert TOM_AND_JERRY in disc['newly_available']
    entry = only(disc['wall'][TOM_AND_JERRY])
    assert entry and not entry.get('_buyonly_preorder') and not entry.get('_is_preorder') \
        and 'pre_order_links' not in entry, f'wall entry not synced: {brief(entry, "pre_order_links")}'
    assert entry.get('digital_date') == TJ_FIRST_OFFER, brief(entry)


def test_d3b_justwatch_rental_puts_buy_only_preorder_on_the_main_wall_the_same_day(tmp_path):
    """Same scenario through the whole daily run (discovery -> enrichment -> gap fill): Tom
    and Jerry leaves PRE-ORDER and is on the main wall today with its Amazon link.
    (v1 xfail: enrichment wiped the new links of the still-flagged entry and the zero-links
    guard reverted it; fixed by the round-2 transition sync.)"""
    res = run_daily(_tj(amazon_rent('B0TJSTAGED')), str(tmp_path / 'sbx'))
    end = final(res)
    entry = only(end['wall'][TOM_AND_JERRY])

    assert on_main_wall(entry), (
        f'not on the main wall after the daily run: wall={brief(entry, "watch_links")} '
        f'tracking={brief_rec(end["tracking"][TOM_AND_JERRY])}')
    assert entry['digital_date'] == TJ_FIRST_OFFER
    assert 'Amazon' in vod_services(entry), vod_services(entry)
    assert end['tracking'][TOM_AND_JERRY]['status'] == 'available'


def test_d3c_graduated_buy_only_preorder_keeps_the_day_justwatch_first_showed_the_rental(tmp_path):
    """Two real daily runs (2026-11-14, 2026-11-15) with the live rental from the 14th: Tom and
    Jerry is on the main wall dated 2026-11-14 on both days -- no same-day revert, no
    'zero watch links' strike that would have dated it a day late (v1 xfail, fixed)."""
    res = run_daily(_tj(amazon_rent('B0TJSTAGED'), phases=two_days(TODAY, '2026-11-15')), str(tmp_path / 'sbx'))
    for day in (TODAY, '2026-11-15'):
        entry = only(after(res, 'gap_fill', day)['wall'][TOM_AND_JERRY])
        assert on_main_wall(entry) and entry['digital_date'] == TJ_FIRST_OFFER, f'{day}: {brief(entry)}'
    rec = final(res)['tracking'][TOM_AND_JERRY]
    assert rec['status'] == 'available' and not rec.get('_jw_revert_count'), brief_rec(rec)


def test_d3d_apple_store_rental_alone_does_not_graduate_a_buy_only_preorder(tmp_path):
    """v1's original scenario: the captured Apple TV Store BUY plus an Apple TV Store RENT on
    the same page. Out of theaters (no cinema offers, no future TMDB or Amazon date), a film you
    can buy or rent on Apple is out (owner, Nov 2026: "buy-only is buyable"). Apple's
    theater-opening pre-order listings are caught by the in-theaters rule instead. On the main
    wall, dated by its first offer record."""
    res = run_daily(_tj(apple_store_rent(tj_apple_url())), str(tmp_path / 'sbx'))
    end = final(res)
    entry = only(end['wall'][TOM_AND_JERRY])
    rec = end['tracking'][TOM_AND_JERRY]
    assert on_main_wall(entry), f'not on the main wall: wall={brief(entry)} tracking={brief_rec(rec)}'
    assert rec['status'] == 'available' and not rec.get('_buyonly_preorder'), brief_rec(rec)
    assert entry['digital_date'] == TJ_FIRST_OFFER, brief(entry)


def test_d3e_buy_only_preorder_without_a_justwatch_rental_stays_a_preorder(tmp_path):
    """The captured JustWatch response for Tom and Jerry is BUY-only (Apple TV Store $12.99),
    out of theaters. Buy-only is buyable (owner, Nov 2026): checked today, it graduates --
    'available', dated by its first offer record (never a "not out yet" day), its PRE-ORDER
    entry brought onto the main wall, queued as a new arrival."""
    res = run_daily(_tj(), str(tmp_path / 'sbx'))
    end = final(res)
    rec = end['tracking'][TOM_AND_JERRY]

    assert 'Tom and Jerry: Forbidden Compass' in jw_titles(res, 'discover'), 'not checked today'
    assert rec['status'] == 'available' and not rec.get('_buyonly_preorder'), brief_rec(rec)
    assert rec.get('_jw_last_refuted') != TODAY, brief_rec(rec)
    entry = only(end['wall'][TOM_AND_JERRY])
    assert on_main_wall(entry) and entry['digital_date'] == TJ_FIRST_OFFER, brief(entry)
    assert TOM_AND_JERRY in after(res, 'discover')['newly_available']


@pytest.mark.parametrize('mid,url', [(TOM_AND_JERRY, TJ_FANDANGO_URL), (QUEEN_AT_SEA, QAS_FANDANGO_URL)],
                         ids=['Tom_and_Jerry', 'Queen_at_Sea'])
@pytest.mark.parametrize('page', ['unreadable', 'reads_preorder'])
def test_d3f_fandango_preorder_rental_does_not_graduate_a_buy_only_preorder(mid, url, page, tmp_path):
    """DreamQuil's real shape -- a Fandango At Home RENT with no offer start, a pre-order --
    appears for a real buy-only pre-order (Tom and Jerry: TMDB lists its Apple buy; Queen at
    Sea: TMDB lists nothing). The store page renders nothing readable (as Fandango's do under
    the pipeline's browser settings) or reads DreamQuil's real 'available to watch on dec 4
    preorder $14.99'. Over two daily runs it must stay a waiting buy-only pre-order: checked
    on JustWatch every discovery run, its page checked, each day kept as a 'not out yet'
    day, never on the main wall (rule 1; review finding 35)."""
    title = fixtures()['tracking'][mid]['title']
    pages = [(url, DREAMQUIL_PAGE_TEXT)] if page == 'reads_preorder' else []
    spec = scenario([mid], wall_ids=[mid], jw_over={mid: jw_node(mid, fandango_preorder_rent(url))}, pages=pages,
                    phases=two_days(TODAY, '2026-11-15'))
    res = run_daily(spec, str(tmp_path / 'sbx'))
    if mid == TOM_AND_JERRY and page == 'unreadable':
        # Its own Apple purchase (real record), out of theaters: buyable, so out (owner, Nov
        # 2026) -- the Fandango pre-order listing next to it doesn't change that.
        rec = after(res, 'discover', TODAY)['tracking'][mid]
        assert rec['status'] == 'available' and rec['digital_date'] == TJ_FIRST_OFFER, brief_rec(rec)
        return

    for day in (TODAY, '2026-11-15'):
        disc = after(res, 'discover', day)
        rec = disc['tracking'][mid]
        assert title in jw_titles(res, 'discover', day), f'{day}: not checked'
        assert any(ph == f'{day}:discover' and u == url for ph, u in res['pages']), f'{day}: page not checked'
        assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), f'{day}: graduated: {brief_rec(rec)}'
        assert rec.get('_jw_last_refuted') == day, brief_rec(rec)
        assert mid not in disc['newly_available']
        for ph in ('discover', 'enrich', 'gap_fill'):
            entry = only(after(res, ph, day)['wall'][mid])
            assert not on_main_wall(entry), f'{day} {ph}: on the main wall: {brief(entry)}'
            assert entry and entry.get('_buyonly_preorder'), f'{day} {ph}: pre-order entry lost: {brief(entry)}'


def test_d3g_another_stores_rental_graduates_when_its_page_reads_available(tmp_path):
    """The other way a store's rental counts: Tom and Jerry gets a Fandango At Home RENT and
    its page reads 'Rent now' (staged). The daily check graduates it, the rent pre-order
    page check agrees, and it is on the main wall today with the Fandango link."""
    res = run_daily(_tj(fandango_preorder_rent(TJ_FANDANGO_URL), pages=[(TJ_FANDANGO_URL, LIVE_PAGE_TEXT)]),
                    str(tmp_path / 'sbx'))
    disc, end = after(res, 'discover'), final(res)
    assert disc['tracking'][TOM_AND_JERRY]['status'] == 'available', brief_rec(disc['tracking'][TOM_AND_JERRY])
    entry = only(end['wall'][TOM_AND_JERRY])
    assert on_main_wall(entry) and entry['digital_date'] == TJ_FIRST_OFFER, brief(entry)
    assert 'Fandango' in vod_services(entry), vod_services(entry)


def test_d3h_festival_eventive_listing_never_graduates_a_buy_only_preorder(tmp_path):
    """Queen at Sea (real records, TMDB lists nothing) with JustWatch listing a festival's own
    Eventive page as a RENT next to its real cinema offers (the Disposable Humanity shape).
    The daily check excludes festival platforms: over two runs it stays a waiting buy-only
    pre-order -- no graduation, no strike, no page visit for the festival link."""
    spec = scenario([QUEEN_AT_SEA], wall_ids=[QUEEN_AT_SEA], jw_over={QUEEN_AT_SEA: jw_node(QUEEN_AT_SEA, eventive_rent())},
                    phases=two_days(TODAY, '2026-11-15'))
    res = run_daily(spec, str(tmp_path / 'sbx'))
    for day in (TODAY, '2026-11-15'):
        rec = after(res, 'discover', day)['tracking'][QUEEN_AT_SEA]
        assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), f'{day}: {brief_rec(rec)}'
        assert 'Queen at Sea' in jw_titles(res, 'discover', day)
    rec = final(res)['tracking'][QUEEN_AT_SEA]
    assert not rec.get('_jw_revert_count') and rec.get('_jw_last_refuted') == '2026-11-15', brief_rec(rec)
    assert not [u for _ph, u in res['pages'] if 'eventive' in u], res['pages']
    for name, st in res['phases'].items():
        assert not on_main_wall(only(st['wall'][QUEEN_AT_SEA])), name


def test_d3i_buy_only_preorder_is_checked_even_when_tmdb_provider_lookup_fails(tmp_path):
    """TMDB's watch/providers call fails (HTTP 500) for Tom and Jerry on the day JustWatch
    shows a live Amazon rental. Round 2: the provider block still runs for a buy-only
    pre-order -- JustWatch is asked, it graduates today -- and its stored providers are
    kept (a TMDB error is not 'no providers')."""
    spec = _tj(amazon_rent('B0TJSTAGED'), phases=('discover',), tmdb_fail=[(TOM_AND_JERRY, '/watch/providers')])
    res = run_daily(spec, str(tmp_path / 'sbx'))
    rec = after(res, 'discover')['tracking'][TOM_AND_JERRY]
    assert 'Tom and Jerry: Forbidden Compass' in jw_titles(res, 'discover')
    assert rec['status'] == 'available' and rec['digital_date'] == TJ_FIRST_OFFER, brief_rec(rec)
    assert rec.get('providers') == fixtures()['tracking'][TOM_AND_JERRY]['providers'], rec.get('providers')


def test_d4_buy_only_preorder_tmdb_lists_nothing_for_is_still_checked_daily(tmp_path):
    """Queen at Sea is flagged a buy-only pre-order, but TMDB lists no provider for it at all
    (TMDB lags JustWatch). It must still be asked about in every discovery run -- two daily
    runs here -- and, JustWatch showing it only in cinemas, wait. (v1 xfail, fixed in v2.)"""
    res = run_daily(scenario([QUEEN_AT_SEA], wall_ids=[QUEEN_AT_SEA], phases=two_days(TODAY, '2026-11-15')),
                    str(tmp_path / 'sbx'))
    for day in (TODAY, '2026-11-15'):
        assert 'Queen at Sea' in jw_titles(res, 'discover', day), \
            f'no JustWatch check on {day}; asked about: {sorted(set(jw_titles(res)))}'
    rec = final(res)['tracking'][QUEEN_AT_SEA]
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder') and rec.get('_jw_last_refuted') == '2026-11-15', \
        brief_rec(rec)
    assert not on_main_wall(only(final(res)['wall'][QUEEN_AT_SEA]))


# ==================================================================================
# (d5) Buy-only pre-orders in both Type-4 branches (round 2: no graduation bypass)
# ==================================================================================

def _wicker_buyonly_node():
    """Staged: Wicker on JustWatch as buy-only -- a Fandango At Home BUY (TMDB's provider for it)."""
    return jw_node(WICKER, offers=[offer('BUY', 'Fandango At Home', 'vudu',
                                         'https://athome.fandango.com/content/browse/details/Wicker/staged',
                                         '$19.99', None, '2026-11-20T00:00:00Z')])


# branch -> (film, days the film is still buy-only, graduation day, TMDB's date)
_T4 = {
    'fresh_past_date-Beware_Boiuna': (BEWARE_BOIUNA, [TODAY], '2026-11-15', '2026-11-03'),
    'pending_date_arrived-Wicker': (WICKER, ['2026-11-24', '2026-11-25'], '2026-11-26', '2026-11-24'),
}


def _t4_spec(branch, rental='amazon'):
    mid, wait_days, grad_day, _tmdb = _T4[branch]
    base = jw_node(mid) if mid == BEWARE_BOIUNA else _wicker_buyonly_node()
    if rental == 'amazon':
        rent = amazon_rent('B0STAGED' + mid, day=grad_day, price='$5.99')
    else:
        apple_url = (fixtures()['wall'][BEWARE_BOIUNA]['pre_order_links'][1]['link'] if mid == BEWARE_BOIUNA
                     else 'https://tv.apple.com/us/movie/wicker/staged')
        rent = apple_store_rent(apple_url, day=grad_day, price='$5.99')
    rented = copy.deepcopy(base)
    rented['offers'].append(rent)
    jw_days = {grad_day: {mid: rented}}
    return scenario([mid], wall_ids=[mid], jw_over={mid: base}, jw_days=jw_days,
                    phases=two_days(*wait_days, grad_day), today=wait_days[0])


# branch -> (film, the day it is out, the date it gets)
_T4_OUT = {
    # Beware Boiúna: bought on Amazon/Apple/Fandango, out of theaters, TMDB 2026-11-03: out on
    # its first check, dated 2026-11-03 (its real Amazon page reads "Buy UHD $14.99").
    'fresh_past_date-Beware_Boiuna': (TODAY, '2026-11-03'),
    # Wicker: a Fandango-only purchase listed 2026-11-20 (page unreadable), TMDB moved to
    # 2026-11-24: a pre-order until TMDB's date, then out -- dated 2026-11-24, not the earlier
    # Fandango pre-order listing.
    'pending_date_arrived-Wicker': ('2026-11-24', '2026-11-24'),
}


@pytest.mark.parametrize('branch', list(_T4))
def test_d5a_type4_buy_only_preorder_is_out_once_buyable_and_dated_by_evidence(branch, tmp_path):
    """Owner, Nov 2026: "buy-only is buyable". A buy-only pre-order whose TMDB digital date has
    passed goes on the main wall the day JustWatch shows it buyable -- through discovery's
    pre-order labeler, never the old graduation bypass -- dated by its first offer record, not
    before TMDB's digital date, and stays put every later phase and day (no nightly loop)."""
    mid, _wait, _grad, _tmdb = _T4[branch]
    out_day, dated = _T4_OUT[branch]
    res = run_daily(_t4_spec(branch), str(tmp_path / 'sbx'))
    title = fixtures()['tracking'][mid]['title']
    assert title in jw_titles(res, 'discover', out_day), 'JustWatch not asked in discovery'
    rec = after(res, 'discover', out_day)['tracking'][mid]
    assert rec['status'] == 'available' and rec['digital_date'] == dated, brief_rec(rec)
    assert not rec.get('_buyonly_preorder') and not rec.get('_is_preorder'), brief_rec(rec)
    for name, st in res['phases'].items():
        if name.split(':', 1)[1] < out_day:
            continue
        entry = only(st['wall'][mid])
        assert on_main_wall(entry) and entry['digital_date'] == dated, f'{name}: {brief(entry)}'
        assert 'pre_order_links' not in entry, f'{name}: {brief(entry, "pre_order_links")}'


@pytest.mark.parametrize('branch', list(_T4))
def test_d5b_type4_buy_only_preorder_waits_before_its_tmdb_date(branch, tmp_path):
    """Before it is out it waits, checked every day: Wicker on 2026-11-24's eve is a pre-order
    (Fandango-only listing, TMDB's date ahead). (Beware is out on its first check.)"""
    mid, _wait, _grad, _tmdb = _T4[branch]
    if branch != 'pending_date_arrived-Wicker':
        pytest.skip('out on its first check')
    spec = _t4_spec(branch)
    spec['phases'] = two_days('2026-11-23', '2026-11-24')
    spec['today'] = '2026-11-23'
    res = run_daily(spec, str(tmp_path / 'sbx'))
    rec = after(res, 'discover', '2026-11-23')['tracking'][mid]
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)
    assert not on_main_wall(only(after(res, 'gap_fill', '2026-11-23')['wall'][mid]))
    rec = after(res, 'discover', '2026-11-24')['tracking'][mid]
    assert rec['status'] == 'available' and rec['digital_date'] == '2026-11-24', brief_rec(rec)


# ----------------------------------------------------------------------------------
# Round 2d (f5, critic): the daily gap fill graduates a pre-order only when JustWatch
# shows it watchable NOW, dates it the day it does, and sends a buy-only pre-order it flags
# back to discovery's daily checks
# ----------------------------------------------------------------------------------

@pytest.mark.parametrize('rental, graduates', [
    ('apple_store', False),        # Apple's store lists rentals from the theater opening
    ('amazon_preorder', False),    # Amazon's pre-order rental: offer start 12-01, ahead
    ('amazon_live', True),         # Amazon's rental live today
])
def test_g7_gap_fill_graduates_a_future_preorder_only_when_justwatch_shows_it_watchable_now(rental, graduates, tmp_path):
    """Wicker (real records): a buy-only pending pre-order in the PRE-ORDER lane for 2026-12-01 --
    tracking 'tracking', with a stale `_transitioned_at` of 2026-10-24. On 11-14 JustWatch lists
    a rental. The gap fill graduated a pre-order on ANY rental (stores list pre-orders as
    ordinary RENT offers) and dated it by that stale 10-24 -- production too: a not-yet-out
    film on the main wall, dated weeks early. Round 2d: only a live one graduates it there
    (streaming, or an Amazon rental past its offer start -- discovery's rule), dated that day;
    its tracking pre-order flags go too."""
    node = _wicker_buyonly_node()
    node['offers'].append({
        'apple_store': apple_store_rent('https://tv.apple.com/us/movie/wicker/staged', day=TODAY, price='$5.99'),
        'amazon_preorder': amazon_preorder_rent('B0WICKERPRE', day='2026-12-01'),
        'amazon_live': amazon_rent('B0WICKERLIVE', day=TODAY, price='$5.99'),
    }[rental])
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',))
    assert spec['tracking'][WICKER]['_transitioned_at'] == '2026-10-24'
    res = run_daily(spec, str(tmp_path / 'sbx'))
    end = final(res)
    entry, rec = only(end['wall'][WICKER]), end['tracking'][WICKER]
    if graduates:
        assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
        assert rec['status'] == 'available' and rec['digital_date'] == TODAY, brief_rec(rec)
        assert not any(rec.get(k) for k in ('_is_preorder', '_type4_pending', '_buyonly_preorder')), brief_rec(rec)
    else:
        assert not on_main_wall(entry) and entry.get('_is_preorder'), brief(entry)
        assert entry['digital_date'] == '2026-12-01', brief(entry)
        assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)


def test_g8_gap_fill_never_dates_a_graduation_on_or_before_a_day_it_was_proven_not_out(tmp_path):
    """The same graduation (Wicker, Amazon live today), for a record tracking already has as out
    (the Carolina Caroline case: its old wall date is kept) whose last "not out yet" day is
    11-10: the old 10-24 date and transition day are on or before that day -- it is dated
    today, never on a day a check proved it not out (rule 4)."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent('B0WICKERLIVE', day=TODAY, price='$5.99'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'status': 'available', '_jw_last_refuted': '2026-11-10'}},
                    wall_over={WICKER: {'digital_date': '2026-10-24'}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
    assert rec['digital_date'] == TODAY, brief_rec(rec)


def test_g9_buy_only_preorder_the_gap_fill_flags_goes_back_to_daily_checks(tmp_path):
    """Critic: a wall film the gap fill flags a buy-only pre-order kept tracking status 'available'
    -- discovery only checks 'tracking' films, the gap fill only films dated in the last 30
    days, and catch-up skips dateless buy-only pre-orders: nothing ever checked it again (Olmo:
    streaming and an Amazon rental live since 2026-08-28, still an invisible, dateless
    pre-order in November). Wicker (real), here an ordinary wall film dated 11-10 whose TMDB has
    no digital date and whose JustWatch shows only a purchase: the gap fill flags it and sends it
    back to tracking; the next day's discovery checks it on JustWatch."""
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: _wicker_buyonly_node()},
                    phases=('gap_fill', ['2026-11-15', 'discover']),
                    tracking_over={WICKER: {'status': 'available', 'digital_date': '2026-11-10',
                                            '_buyonly_preorder': _MISSING, '_type4_pending': _MISSING,
                                            '_is_preorder': _MISSING}},
                    wall_over={WICKER: {'digital_date': '2026-11-10', '_is_preorder': _MISSING,
                                        'pre_order_links': _MISSING}},
                    tmdb_over={WICKER: {'details': fixtures()['tmdb'][WICKER]['details'],
                                        'release_dates': {'id': int(WICKER), 'results': []}}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    gf = after(res, 'gap_fill')
    rec, entry = gf['tracking'][WICKER], only(gf['wall'][WICKER])
    assert entry.get('_is_preorder') and entry.get('_buyonly_preorder'), brief(entry)
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)
    assert 'Wicker' in jw_titles(res, 'discover', '2026-11-15'), 'not checked on JustWatch the next day'


# ==================================================================================
# (l) Liberation: a HELD pending pre-order whose TMDB date is still ahead. Round 2: no longer
#     skipped until its date -- JustWatch is asked every run, and it goes on early only if
#     JustWatch shows it watchable NOW (streaming, or a live Apple / Amazon rental)
# ==================================================================================

# Liberation's real payloads, captured read-only on 2026-11-14 (scratchpad
# step1_preorders/live_1318467_etc.json; identical in live_1341138_etc.json). JustWatch finds
# it by TMDB id under its US title "The Optimist", with a cinema listing only (dateCreated
# mirrored from availableFromTime: null). TMDB: US limited theatrical 2026-03-11, digital
# 2026-11-17; watch providers only outside the US (16 countries, trimmed here: the pipeline
# reads only 'US'). Its TMDB details were not captured: staged from its tracking record.
LIBERATION_TMDB = {
    'details': {'id': 1129188, 'title': 'Liberation', 'original_title': 'Liberation', 'original_language': 'en',
                'release_date': '2026-03-11', 'runtime': 95, 'overview': '', 'poster_path': None,
                'genres': [], 'origin_country': ['US'],
                'production_countries': [{'iso_3166_1': 'US', 'name': 'United States of America'}],
                'production_companies': [], 'credits': {'cast': [], 'crew': [{'job': 'Director', 'name': 'Finn Taylor'}]},
                'external_ids': {}, 'videos': {'results': []}, 'keywords': {'keywords': []},
                'alternative_titles': {'titles': []}},
    'release_dates': {'id': 1129188, 'results': [
        {'iso_3166_1': 'AU', 'release_dates': [
            {'certification': '', 'descriptors': [], 'iso_639_1': '', 'note': 'The Jewish International Film Festival',
             'release_date': '2025-10-23T00:00:00.000Z', 'type': 1}]},
        {'iso_3166_1': 'GB', 'release_dates': [
            {'certification': '15', 'descriptors': [], 'iso_639_1': '', 'note': '',
             'release_date': '2026-01-19T00:00:00.000Z', 'type': 5}]},
        {'iso_3166_1': 'US', 'release_dates': [
            {'certification': '', 'descriptors': [], 'iso_639_1': '', 'note': 'Hamptons International Film Festival',
             'release_date': '2023-10-06T00:00:00.000Z', 'type': 1},
            {'certification': '', 'descriptors': [], 'iso_639_1': '', 'note': 'Mill Valley Film Festival',
             'release_date': '2023-10-11T00:00:00.000Z', 'type': 1},
            {'certification': '', 'descriptors': [], 'iso_639_1': '', 'note': '',
             'release_date': '2026-03-11T00:00:00.000Z', 'type': 2},
            {'certification': 'NR', 'descriptors': [], 'iso_639_1': '', 'note': '',
             'release_date': '2026-11-17T00:00:00.000Z', 'type': 4},
            {'certification': 'NR', 'descriptors': [], 'iso_639_1': '', 'note': '',
             'release_date': '2026-12-18T00:00:00.000Z', 'type': 5}]}]},
    'watch_providers': {'id': 1129188, 'results': {}},
}
LIBERATION_JW = {
    'id': 'tm1649732', 'objectId': 1649732, 'objectType': 'MOVIE',
    'content': {'title': 'The Optimist', 'originalReleaseYear': 2026, 'fullPath': '/us/movie/avenue-of-the-giants',
                'externalIds': {'tmdbId': '1129188'}, 'credits': [{'role': 'DIRECTOR', 'name': 'Finn Taylor'}]},
    'offers': [offer('CINEMA', 'Fandango', 'fandango',
                     'https://www.fandango.com/the-optimist-the-bravest-act-is-truth-2026-244066/movie-overview',
                     None, None, None, 'CANVAS')],
}
LIB_TMDB_DIGITAL = '2026-11-17'


def _lib_node(*extra):
    node = copy.deepcopy(LIBERATION_JW)
    node['offers'].extend(copy.deepcopy(list(extra)))
    return node


def _lib_spec(*extra, **kw):
    kw.setdefault('jw_over', {LIBERATION: _lib_node(*extra)})
    return scenario([LIBERATION], tmdb_over={LIBERATION: copy.deepcopy(LIBERATION_TMDB)}, **kw)


def test_l1_held_preorder_with_a_future_tmdb_date_is_checked_every_run_and_waits(tmp_path):
    """Liberation (real records: a pending pre-order, TMDB digital 2026-11-17, held since a
    2026-09-15 'no valid offers' check; no wall entry). v1 skipped a held film with a future
    pending date until that date; round 2 sends it to JustWatch EVERY run (rule 2). With
    JustWatch's real Nov 14 answer (cinema only) over two daily runs: asked in each
    discovery, still a pending pre-order on TMDB's date, each day kept as checked and 'not
    out yet', and it never gets a wall entry (no add/purge loop) or is archived."""
    res = run_daily(_lib_spec(phases=two_days(TODAY, '2026-11-15')), str(tmp_path / 'sbx'))
    for day in (TODAY, '2026-11-15'):
        disc = after(res, 'discover', day)
        rec = disc['tracking'][LIBERATION]
        assert 'Liberation' in jw_titles(res, 'discover', day), f'{day}: not checked on JustWatch'
        assert rec['status'] == 'tracking' and rec.get('_type4_pending') and rec.get('_is_preorder'), brief_rec(rec)
        assert rec.get('digital_date') == LIB_TMDB_DIGITAL, brief_rec(rec)
        assert rec.get('_jw_last_checked') == day and rec.get('_jw_last_refuted') == day, brief_rec(rec)
        assert rec.get('_jw_revert_reason') == 'justwatch_no_valid_offers', brief_rec(rec)
        assert LIBERATION not in disc['newly_available']
    for name, st in res['phases'].items():
        assert not st['wall'][LIBERATION] and not st['archive'][LIBERATION], f'{name}: {st["wall"][LIBERATION][:1]}'


def _lib_offer(kind):
    return {'amazon_live': amazon_rent('B0LIBSTAGED'),
            'apple_store_live': apple_store_rent('https://tv.apple.com/us/movie/the-optimist/staged'),
            'netflix': netflix_stream('lib-staged'),
            'fandango_preorder': fandango_preorder_rent('https://athome.fandango.com/content/browse/details/The-Optimist/staged'),
            'amazon_preorder': amazon_preorder_rent('B0LIBSTAGED')}[kind]


@pytest.mark.parametrize('kind,early', [('amazon_live', True), ('apple_store_live', False), ('netflix', True),
                                        ('fandango_preorder', False), ('amazon_preorder', False)],
                         ids=['live_Amazon_Video_rental', 'Apple_TV_Store_rental', 'streaming_Netflix',
                              'Fandango_At_Home_preorder_RENT-DreamQuil_shape', 'Amazon_rental_offer_start_Dec_4'])
def test_l2_held_preorder_goes_on_before_its_tmdb_date_only_if_justwatch_shows_it_watchable_now(kind, early, tmp_path):
    """Liberation, Nov 14 (TMDB still says 11-17), with one staged offer next to its real
    cinema listing. Streaming or a live Amazon rental: it goes on TODAY -- put back, dated
    today from JustWatch's record (not TMDB's future date), on the main wall after the daily
    run, and enrichment keeps that date. A store's pre-order rental (Fandango At Home with no
    offer start; Amazon starting Dec 4; Apple's store, which lists rentals from the theater
    opening -- round 2c): it waits -- today kept as checked and 'not out yet', TMDB's date
    kept, no wall entry."""
    res = run_daily(_lib_spec(_lib_offer(kind)), str(tmp_path / 'sbx'))
    disc, end = after(res, 'discover'), final(res)
    rec = disc['tracking'][LIBERATION]
    assert 'Liberation' in jw_titles(res, 'discover'), 'not checked on JustWatch'
    if early:
        assert rec['status'] == 'available' and rec.get('_put_back_on') == TODAY, brief_rec(rec)
        assert rec['digital_date'] == TODAY and rec['_digital_date_source'] == 'jw_first_offer', brief_rec(rec)
        entry = only(end['wall'][LIBERATION])
        assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
        wl = entry.get('watch_links') or {}
        assert (wl.get('streaming') if kind == 'netflix' else vod_services(entry)), wl
        assert end['tracking'][LIBERATION]['digital_date'] == TODAY, brief_rec(end['tracking'][LIBERATION])
    else:
        assert rec['status'] == 'tracking' and rec.get('_type4_pending'), brief_rec(rec)
        assert rec.get('digital_date') == LIB_TMDB_DIGITAL, brief_rec(rec)
        assert rec.get('_jw_last_checked') == TODAY and rec.get('_jw_last_refuted') == TODAY, brief_rec(rec)
        assert LIBERATION not in disc['newly_available']
        for name, st in res['phases'].items():
            assert not st['wall'][LIBERATION], f'{name}: {brief(only(st["wall"][LIBERATION]))}'


@pytest.mark.parametrize('recorded', ['the_day_it_went_live', 'earlier_as_a_listing'])
def test_l3_held_preorder_is_dated_the_first_day_justwatch_shows_it_live(recorded, tmp_path):
    """Nov 14: JustWatch's real answer (cinema only) -- Liberation waits, the day kept as
    'not out yet'. Nov 15: a live Amazon rental (staged), recorded by JustWatch that day, or
    recorded on Nov 10 as a listing before it went live. Either way it goes on the main wall
    on Nov 15 dated Nov 15 (rule 4): not Nov 14 (checked, not out), not Nov 10 (a listing
    before a 'not out yet' day), not TMDB's 11-17 (never a day it was watchable)."""
    day2 = '2026-11-15'
    created = f'{day2}T05:00:00Z' if recorded == 'the_day_it_went_live' else '2026-11-10T05:00:00Z'
    node2 = _lib_node(amazon_rent_from('B0LIBSTAGED', f'{day2}T05:00:00Z', created=created))
    res = run_daily(_lib_spec(phases=two_days(TODAY, day2), jw_days={day2: {LIBERATION: node2}}),
                    str(tmp_path / 'sbx'))
    first = after(res, 'discover', TODAY)['tracking'][LIBERATION]
    assert first['status'] == 'tracking' and first.get('_jw_last_refuted') == TODAY, brief_rec(first)
    rec = after(res, 'discover', day2)['tracking'][LIBERATION]
    assert rec['status'] == 'available' and rec['digital_date'] == day2, brief_rec(rec)
    assert rec['_digital_date_source'] == ('jw_first_offer' if recorded == 'the_day_it_went_live'
                                           else 'putback_after_hold'), brief_rec(rec)
    assert not rec.get('_date_needs_review'), 'checked daily: no review needed'
    entry = only(final(res)['wall'][LIBERATION])
    assert on_main_wall(entry) and entry['digital_date'] == day2, brief(entry)


# ==================================================================================
# (s) The wall entry is synced when a film comes out (generator._sync_entry_on_transition
#     via add_movie_to_site_immediately)
# ==================================================================================

def _sync(entry, rec):
    from pipeline.generator import DataGenerator
    return DataGenerator._sync_entry_on_transition(entry, rec)


def test_s1_sync_drops_only_the_flags_the_record_dropped(tmp_path):
    """_sync_entry_on_transition on real entries: a graduated buy-only pre-order loses
    _buyonly_preorder / _is_preorder / pre_order_links and gets the record's date; an entry
    whose record still is a pre-order (Wicker: _is_preorder kept, same date) is left as is
    and reports no change."""
    F = fixtures()
    with frozen_clock(TODAY):
        tj = copy.deepcopy(F['wall'][TOM_AND_JERRY])
        rec = dict(copy.deepcopy(F['tracking'][TOM_AND_JERRY]), status='available', digital_date=TODAY)
        rec.pop('_buyonly_preorder')
        assert _sync(tj, rec) is True
        assert not tj.get('_buyonly_preorder') and not tj.get('_is_preorder') and 'pre_order_links' not in tj
        assert tj['digital_date'] == TODAY

        wk = copy.deepcopy(F['wall'][WICKER])
        before = copy.deepcopy(wk)
        _sync(wk, dict(copy.deepcopy(F['tracking'][WICKER]), status='available'))
        # Its pre-order state is untouched; only the old enrichment attempts are forgotten
        # (a transition is a new arrival: the 5-attempt cap counts this one -- round 2c).
        for k in ('_enrichment_attempts', '_last_enrichment_attempt'):
            before.pop(k, None)
        assert wk == before


def _tj_hidden(flags, *extra, **kw):
    return _tj(*extra, wall_over={TOM_AND_JERRY: dict(flags, hidden=True)}, **kw)


@pytest.mark.parametrize('flags,stays_hidden', [({'_jw_unconfirmed': '2026-11-13'}, True), ({}, False)],
                         ids=['hidden_waiting_for_a_JustWatch_check', 'hidden_earlier_presale'])
def test_s2_hidden_entry_waiting_for_justwatch_stays_hidden_at_transition(flags, stays_hidden, tmp_path):
    """Tom and Jerry graduates in discovery (live Amazon rental) while its wall entry is
    hidden (staged). If it carries _jw_unconfirmed -- hidden by enrichment after a JustWatch
    error, waiting for its pre-check -- it stays hidden (round 2); a plain hidden entry (an
    earlier pre-sale) is unhidden as before. Either way the entry is synced: no pre-order
    flags or links, dated by its first offer record (its Apple purchase: buyable is out),
    enrichment pending."""
    res = run_daily(_tj_hidden(flags, amazon_rent('B0TJSTAGED'), phases=('discover',)), str(tmp_path / 'sbx'))
    entry = only(after(res, 'discover')['wall'][TOM_AND_JERRY])

    assert bool(entry.get('hidden')) is stays_hidden, brief(entry)
    assert bool(entry.get('_jw_unconfirmed')) is stays_hidden
    assert not entry.get('_buyonly_preorder') and not entry.get('_is_preorder') and 'pre_order_links' not in entry
    assert entry['digital_date'] == TJ_FIRST_OFFER and entry['_enrichment_status'] == 'pending', brief(entry)


@pytest.mark.parametrize('jw_in_enrichment', ['up', 'down'])
def test_s3_hidden_unconfirmed_entry_is_shown_only_after_its_justwatch_check_passes(jw_in_enrichment, tmp_path):
    """The same hidden, _jw_unconfirmed Tom and Jerry through the whole daily run. With
    JustWatch up in enrichment its pre-check passes and the film is shown on the main wall
    the same day; with JustWatch down (throttled) for enrichment and gap fill it stays hidden
    -- never on the wall unconfirmed (rule 5) -- and is not struck."""
    kw = {'jw_outage': {'enrich': 'no_results', 'gap_fill': 'no_results'}} if jw_in_enrichment == 'down' else {}
    res = run_daily(_tj_hidden({'_jw_unconfirmed': '2026-11-13'}, amazon_rent('B0TJSTAGED'), **kw),
                    str(tmp_path / 'sbx'))
    end = final(res)
    entry = only(end['wall'][TOM_AND_JERRY])
    rec = end['tracking'][TOM_AND_JERRY]

    if jw_in_enrichment == 'up':
        assert on_main_wall(entry) and not entry.get('_jw_unconfirmed'), brief(entry)
        assert 'Amazon' in vod_services(entry)
    else:
        assert entry and entry.get('hidden') and entry.get('_jw_unconfirmed'), brief(entry)
        assert not on_main_wall(entry)
        assert not rec.get('_jw_revert_count'), brief_rec(rec)


def _his_monster_returned():
    """His Monster as v2's screening check leaves it: production records, the tracking record
    returned by the real DataGenerator._return_screening_to_tracking (screening ended
    2026-10-16, its virtual_screening_info.available_end)."""
    with frozen_clock(TODAY):
        from pipeline.generator import DataGenerator
        rec = copy.deepcopy(fixtures()['tracking'][HIS_MONSTER])
        DataGenerator._return_screening_to_tracking(rec, fixtures()['wall'][HIS_MONSTER]['virtual_screening_info']['available_end'])
    return rec


def test_s4_returned_screening_put_back_loses_its_festival_link_and_flags(tmp_path):
    """His Monster: a festival screening (Eventive, MONIFF, ended 2026-10-16) whose entry is
    still on the wall, hidden as an expired screening, with an Eventive link next to its real
    Amazon / Apple / Fandango / Hoopla links. JustWatch (live scan, Nov 14) has it on Amazon
    and Apple since 2026-10-05 and on Hoopla since 2026-09-25. Discovery puts it back; the
    entry must lose the festival link and screening flags at the transition (round 2) --
    otherwise the display step re-hides it under the old screening -- and it ends the daily
    run on the main wall with its real links."""
    spec = scenario([HIS_MONSTER], wall_ids=[HIS_MONSTER], tracking_over={HIS_MONSTER: _his_monster_returned()},
                    tmdb_over={HIS_MONSTER: _his_monster_tmdb()})
    assert spec['tracking'][HIS_MONSTER]['status'] == 'tracking' and spec['tracking'][HIS_MONSTER]['_screening_expired']
    res = run_daily(spec, str(tmp_path / 'sbx'))
    disc, end = after(res, 'discover'), final(res)

    rec = disc['tracking'][HIS_MONSTER]
    assert rec['status'] == 'available' and rec.get('_put_back_on') == TODAY, brief_rec(rec)
    entry = only(disc['wall'][HIS_MONSTER])
    assert not entry.get('hidden'), brief(entry)
    assert 'Eventive' not in vod_services(entry), vod_services(entry)
    assert {'Amazon', 'Apple TV', 'Fandango'} <= set(vod_services(entry)), vod_services(entry)
    assert 'virtual_screening_info' not in entry and not entry.get('_virtual_screening')
    assert entry['filters']['is_virtual_screening'] is False
    assert entry['digital_date'] == rec['digital_date'] and entry.get('_digital_date_source') == rec['_digital_date_source']

    final_entry = only(end['wall'][HIS_MONSTER])
    assert on_main_wall(final_entry), f'not on the main wall after the run: {brief(final_entry)}'
    assert 'Eventive' not in vod_services(final_entry) and not final_entry['filters'].get('is_virtual_screening')
    assert end['tracking'][HIS_MONSTER]['status'] == 'available'


def _his_monster_tmdb(details=True):
    """His Monster's captured TMDB answers, plus (SYNTHETIC, minimal) the /movie/{id} details
    enrichment fetches -- the capture has none, and without them enrichment can't run the film's
    JustWatch check."""
    fx = copy.deepcopy(fixtures()['tmdb'][HIS_MONSTER])
    if details:
        rec = fixtures()['tracking'][HIS_MONSTER]
        fx['details'] = {'id': int(HIS_MONSTER), 'title': rec.get('title'), 'original_title': rec.get('title'),
                         'original_language': 'en', 'release_date': f"{rec.get('year')}-01-01", 'runtime': 95,
                         'overview': 'x', 'genres': [], 'production_companies': [], 'production_countries': [],
                         'origin_country': [], 'poster_path': None, 'budget': 0, 'credits': {'cast': [], 'crew': []},
                         'external_ids': {'imdb_id': None}, 'keywords': {'keywords': []},
                         'alternative_titles': {'results': []}, 'videos': {'results': []}}
    return fx


def test_s4b_put_back_waits_hidden_when_enrichment_cannot_fetch_its_tmdb_details(tmp_path):
    """Round 2d (fix-checker): enrichment marked a film 'failed' when TMDB's details failed and
    left it visible -- its JustWatch pre-check never ran, so a put-back still a pre-order or PVOD
    rental showed unchecked. Now it waits hidden (`_jw_unconfirmed`) for that check, like a film
    the batch limit cuts. His Monster, put back today, with no TMDB details."""
    spec = scenario([HIS_MONSTER], wall_ids=[HIS_MONSTER], tracking_over={HIS_MONSTER: _his_monster_returned()},
                    tmdb_over={HIS_MONSTER: _his_monster_tmdb(details=False)})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    assert after(res, 'discover')['tracking'][HIS_MONSTER].get('_put_back_on') == TODAY
    entry = only(after(res, 'enrich')['wall'][HIS_MONSTER])
    assert entry.get('hidden') is True and entry.get('_jw_unconfirmed') == TODAY, brief(entry)
    assert entry.get('_enrichment_status') == 'failed', brief(entry)


def _wall_file():
    with open('data.json', 'rb') as f:
        raw = f.read()
    return raw, {str(m.get('id')): m for m in json.loads(raw).get('movies', [])}


def test_s5_add_movie_to_site_immediately_syncs_an_existing_entry_only_when_the_film_came_out(tmp_path):
    """DataGenerator.add_movie_to_site_immediately on Tom and Jerry's real PRE-ORDER entry,
    called directly (as _transition_movie_to_available and the pre-order add path do):
      * a record still in tracking (a pre-order add: status 'tracking') never touches the
        existing entry -- data.json is not rewritten;
      * the record of a film that just came out (status 'available', buy-only flag dropped,
        dated today) syncs the entry: no pre-order flags or links, today's date, and
        data.json is saved;
      * the same call again changes nothing and does not rewrite data.json;
      * a hidden entry waiting for its JustWatch check (_jw_unconfirmed) stays hidden, synced
        and pending enrichment; a plain hidden entry (an earlier pre-sale) is shown again."""
    F = fixtures()
    spec = scenario([TOM_AND_JERRY], wall_ids=[TOM_AND_JERRY], phases=())
    graduated = dict(copy.deepcopy(F['tracking'][TOM_AND_JERRY]), status='available', digital_date=TODAY)
    graduated.pop('_buyonly_preorder')
    still_waiting = copy.deepcopy(F['tracking'][TOM_AND_JERRY])
    with contextlib.redirect_stdout(io.StringIO()):
        with pipeline_sandbox(spec, str(tmp_path / 'sbx')) as (gen, net):
            raw0, wall0 = _wall_file()
            assert gen.add_movie_to_site_immediately(TOM_AND_JERRY, copy.deepcopy(still_waiting)) is True
            raw1, wall1 = _wall_file()
            assert gen.add_movie_to_site_immediately(TOM_AND_JERRY, copy.deepcopy(graduated)) is True
            raw2, wall2 = _wall_file()
            assert gen.add_movie_to_site_immediately(TOM_AND_JERRY, copy.deepcopy(graduated)) is True
            raw3, _ = _wall_file()
    assert raw1 == raw0, 'a still-waiting record rewrote data.json'
    assert wall1[TOM_AND_JERRY].get('_buyonly_preorder') and wall1[TOM_AND_JERRY].get('pre_order_links')
    e = wall2[TOM_AND_JERRY]
    assert not e.get('_buyonly_preorder') and not e.get('_is_preorder') and 'pre_order_links' not in e, brief(e)
    assert e['digital_date'] == TODAY and on_main_wall(e), brief(e)
    assert {k: v for k, v in wall2.items() if k != TOM_AND_JERRY} == {k: v for k, v in wall0.items() if k != TOM_AND_JERRY}
    assert raw3 == raw2, 'an entry already in sync was rewritten'

    for flags, stays_hidden in (({'_jw_unconfirmed': '2026-11-13'}, True), ({}, False)):
        spec = scenario([TOM_AND_JERRY], wall_ids=[TOM_AND_JERRY], phases=(),
                        wall_over={TOM_AND_JERRY: dict(flags, hidden=True)})
        with contextlib.redirect_stdout(io.StringIO()):
            with pipeline_sandbox(spec, str(tmp_path / f'sbx_hidden_{stays_hidden}')) as (gen, net):
                gen.add_movie_to_site_immediately(TOM_AND_JERRY, copy.deepcopy(graduated))
                _, wall = _wall_file()
        e = wall[TOM_AND_JERRY]
        assert bool(e.get('hidden')) is stays_hidden and bool(e.get('_jw_unconfirmed')) is stays_hidden, brief(e)
        assert not e.get('_buyonly_preorder') and 'pre_order_links' not in e and e['digital_date'] == TODAY
        assert e['_enrichment_status'] == 'pending', brief(e)


def test_s6_moved_tmdb_date_moves_only_an_existing_wall_entry(tmp_path):
    """DataGenerator.update_wall_entry_date (round 2: a pending pre-order's TMDB date moved):
    Wicker's real PRE-ORDER entry moves to TMDB's 2026-11-24, source 'tmdb_type4', nothing
    else on the wall changes; the same date again is a no-op (data.json not rewritten); The
    Odyssey, a held pending pre-order with no entry, gets NO entry (v1's nightly re-add loop
    is gone); with no data.json at all, none is created."""
    spec = scenario([WICKER, THE_ODYSSEY], wall_ids=[WICKER], phases=())
    with contextlib.redirect_stdout(io.StringIO()):
        with pipeline_sandbox(spec, str(tmp_path / 'sbx')) as (gen, net):
            raw0, wall0 = _wall_file()
            assert gen.update_wall_entry_date(WICKER, '2026-11-24') is True
            raw1, wall1 = _wall_file()
            assert gen.update_wall_entry_date(int(WICKER), '2026-11-24') is False
            assert gen.update_wall_entry_date(THE_ODYSSEY, '2026-11-17') is False
            raw2, wall2 = _wall_file()
            os.remove('data.json')
            assert gen.update_wall_entry_date(WICKER, '2026-11-24') is False
            assert not os.path.exists('data.json')
    assert wall0[WICKER]['digital_date'] == '2026-12-01'
    assert wall1[WICKER]['digital_date'] == '2026-11-24' and wall1[WICKER]['_digital_date_source'] == 'tmdb_type4'
    assert in_preorder_lane(wall1[WICKER]), brief(wall1[WICKER])
    assert {k: v for k, v in wall1.items() if k != WICKER} == {k: v for k, v in wall0.items() if k != WICKER}
    assert raw2 == raw1 and THE_ODYSSEY not in wall2


# ==================================================================================
# (f) JustWatch trouble around pre-orders (rule 5)
# ==================================================================================

def test_f1_offers_outage_is_not_recorded_as_a_not_out_yet_day(tmp_path):
    """Discovery runs while JustWatch returns every title -- the control titles too -- with
    an empty offer list. Tom and Jerry's daily buy-only check gets no real answer: it must
    keep waiting WITHOUT recording the day as checked or as 'not out yet'. (xfail until 2b:
    the buy-only check did not consult the canary.)"""
    res = run_daily(_tj(phases=('discover',), jw_outage={'discover': 'empty_offers'}), str(tmp_path / 'sbx'))
    rec = after(res, 'discover')['tracking'][TOM_AND_JERRY]
    assert 'Tom and Jerry: Forbidden Compass' in jw_titles(res, 'discover')
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)
    assert '_jw_last_refuted' not in rec and '_jw_last_checked' not in rec, \
        f'outage day recorded against the film: {brief_rec(rec)}'
    assert after(res, 'discover')['discovery_metrics'].get('jw_healthy') is False, 'the outage was not detected'


@pytest.mark.parametrize('outage', ['no_results', 'http_500'])
def test_f2_past_date_preorder_is_not_published_when_justwatch_fails_in_enrichment(outage, tmp_path):
    """Beware Boiúna (real records: a buy-only pre-order, PRE-ORDER entry dated TMDB's
    2026-11-03 with its three BUY links). Discovery's JustWatch check finds it buyable on
    Amazon, Apple and Fandango, out of theaters -- out (owner, Nov 2026: "buy-only is buyable";
    its real Amazon page reads "Buy UHD $14.99"), dated 2026-11-03. Then JustWatch fails for
    enrichment and gap fill (throttled / HTTP 500): enrichment can't re-check it, so it waits
    HIDDEN for its check (rule 5: never shown unconfirmed) -- 'available' in tracking, its buy
    links kept, no stale pre-order flags -- and is shown once a check passes."""
    spec = scenario([BEWARE_BOIUNA], wall_ids=[BEWARE_BOIUNA], jw_outage={'enrich': outage, 'gap_fill': outage})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    disc_rec = after(res, 'discover')['tracking'][BEWARE_BOIUNA]
    assert disc_rec['status'] == 'available' and disc_rec['digital_date'] == '2026-11-03', brief_rec(disc_rec)
    end = final(res)
    entry = only(end['wall'][BEWARE_BOIUNA])
    rec = end['tracking'][BEWARE_BOIUNA]
    assert not on_main_wall(entry) and entry.get('hidden') and entry.get('_jw_unconfirmed'), \
        f'shown unconfirmed: {brief(entry)} vod={vod_services(entry)}'
    assert rec['status'] == 'available' and not rec.get('_buyonly_preorder'), brief_rec(rec)
    assert not entry.get('_is_preorder') and set(vod_services(entry)) >= {'Amazon', 'Apple TV'}, \
        f'{brief(entry)} {vod_services(entry)}'


def _galaxymphony_batch_cut(**kw):
    """The 100-film limit cutting Galaxymphony, staged as a cut the pipeline really makes: limit 1,
    one other arrival queued ahead of it (1822148, a real background wall entry -- no tracking
    record in the scenario, so the loop skips it). (Round 2d: a limit of 0 sent enrichment down
    its empty-queue early return, which production never takes with the real limit of 100.)"""
    spec = scenario([GALAXYMPHONY], wall_ids=[GALAXYMPHONY],
                    phase_patches={'enrich': [['pipeline.enricher', 'MAX_ENRICHMENT_BATCH', 1]]}, **kw)
    spec['queue_ahead'] = ['1822148']
    return spec


def test_f3_buyonly_preorder_tmdb_lists_but_justwatch_buyonly_never_reaches_the_main_wall(tmp_path):
    """Galaxymphony (real records: a buy-only pre-order whose JustWatch shows only a Barnes &
    Noble DVD plus an Amazon-channel stream NRW skips; TMDB lists that channel as a stream).
    Through round 2d discovery graduated it on TMDB's listing and the transition sync put its
    entry on the main wall, pending enrichment, which flagged it back -- every night (production's
    loop too: Galaxymphony, Marble Hall Murders, The Last Kiss). With the batch limit cutting it
    (staged: MAX_ENRICHMENT_BATCH = 1, another arrival queued first) only the gap fill caught it.
    Round 2e (R2D PO-3): JustWatch decides -- still purchase-only, so discovery keeps it a buy-only
    pre-order in tracking, and it never reaches the main wall at any point of the day."""
    res = run_daily(_galaxymphony_batch_cut(), str(tmp_path / 'sbx'))
    disc = after(res, 'discover')
    assert disc['tracking'][GALAXYMPHONY]['status'] == 'tracking', brief_rec(disc['tracking'][GALAXYMPHONY])
    assert disc['tracking'][GALAXYMPHONY].get('_buyonly_preorder')
    assert 'still a buy-only pre-order' in res['log']
    for name, st in res['phases'].items():
        entry = only(st['wall'][GALAXYMPHONY])
        assert not on_main_wall(entry), f'{name}: on the main wall: {brief(entry)} vod={vod_services(entry)}'
    entry = only(final(res)['wall'][GALAXYMPHONY])
    assert entry.get('_buyonly_preorder') and final(res)['tracking'][GALAXYMPHONY].get('_buyonly_preorder')


BATCH_CUT_DEFECT = (
    "A buy-only pre-order graduated in discovery on TMDB's listing (Galaxymphony: TMDB lists an Amazon-channel "
    "stream NRW drops; JustWatch answers 'buy_only' -- a Barnes & Noble DVD -- which _verify_before_wall accepts) "
    "has its existing wall entry synced at the transition (generator._sync_entry_on_transition: pre-order flags "
    "dropped, dated today) and so sits on the MAIN WALL until enrichment checks it. When enrichment's batch "
    "limit cuts it, _hide_unchecked_putbacks (enricher.py ~704-723) hides only put-backs (_put_back_on == "
    "today), and when JustWatch is also throttled for the gap fill nothing re-flags it: the run ends -- and CI "
    "commits data.json -- with a DVD-only title on the main wall. Production leaves the entry flagged "
    "(_is_preorder / _buyonly_preorder, dateless: not shown) until enrichment.")


def test_f3b_graduated_preorder_cut_by_the_batch_limit_with_justwatch_down_for_gap_fill(tmp_path, head_code_root):
    """test_f3 with JustWatch throttled (HTTP 200, no results -- the JW_BREAKER shape) for the
    gap fill: nothing checks Galaxymphony after discovery. v2 must not end the run with it
    on the main wall when production (78303fd6, same scenario, same fake network) does not."""
    spec = _galaxymphony_batch_cut(jw_outage={'gap_fill': 'no_results'})
    head = run_daily_with_code(head_code_root, spec, str(tmp_path / 'production'))
    v2 = run_daily(spec, str(tmp_path / 'v2' / 'sandbox'))
    head_entry, v2_entry = only(final(head)['wall'][GALAXYMPHONY]), only(final(v2)['wall'][GALAXYMPHONY])
    assert not on_main_wall(head_entry), f'production publishes it too: {brief(head_entry)}'
    assert not on_main_wall(v2_entry), (
        f'v2 publishes the DVD-only title on the main wall: {brief(v2_entry)}; production: {_where(head_entry)}\n'
        f'  v2: {_summary(v2, GALAXYMPHONY)}\n  production: {_summary(head, GALAXYMPHONY)}')


# ==================================================================================
# (r) The owner's Revert action (round 2b) -- the OPPOSITE of Remove
# ==================================================================================
#
# Owner (Nov 15): Remove = a title the owner never wants on the wall -- status 'removed',
# permanent, set only by the owner's /remove or the admin Remove button. Revert = a film
# wrongly marked new (usually the pre-order problem) -- off the wall now, back to waiting,
# back on the wall the day it's really out. "We don't want to remove reverted titles, and we
# don't want to revert removed titles." Revert: putback.owner_revert + revert_wall_entry,
# behind admin POST /revert-movie and scripts/revert_movie.py.

BACKGROUND_IDS = ('1822148', '1798526')   # the two real background wall entries
_REVERT_KEYS = ('_reverted_by_owner', '_held_since', '_date_needs_review', 'enriched', 'enrichment_date',
                '_jw_reverted_at', '_type4_pending')


def _assert_reverted(rec, day=TODAY, count=1):
    """A record as owner_revert leaves it: waiting, held by the owner's revert, `day` kept as
    checked and 'not out yet' (no put-back can be dated on or before it)."""
    b = brief_rec(rec, *_REVERT_KEYS)
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'owner_revert', b
    assert rec['_jw_revert_count'] == count and rec['_reverted_by_owner'] == day, b
    assert rec['_jw_last_checked'] == day and rec['_jw_last_refuted'] == day, b
    assert rec.get('enriched') is False and not rec.get('enrichment_date'), b
    for k in ('_put_back_on', '_held_since', '_date_needs_review'):
        assert k not in rec, b


def _assert_off_the_wall(entry):
    assert entry and entry.get('hidden') is True and entry.get('_enrichment_status') == 'reverted', brief(entry)
    assert not visible(entry)


def test_r1_owner_revert_sends_a_film_back_to_waiting_and_refuses_a_removed_title():
    """putback.owner_revert / revert_wall_entry on real records, clock frozen on Nov 14:
      * Tom and Jerry as the d3 graduation leaves it (on the main wall since today; say it was
        a pre-order after all): back to waiting, held by the owner's revert, its wrong 'new'
        date dropped, enrichment to be redone;
      * His Monster, a v2 put-back (staged: the put-back stamps v2 leaves, dated Oct 5): the
        stamps and the past date go;
      * An Eye for an Eye, a film already waiting (a real 4-strike hold, not on the wall): its
        count and hold start stay, the owner's revert becomes its reason;
      * Wicker, a pending pre-order dated 2026-12-01: the future date and its pre-order flags
        stay (it still waits for that date and its JustWatch rental);
      * I Swear, REMOVED by the owner (2026-05-28; on Netflix now): refused -- False, the record
        unchanged. Nothing here ever sets 'removed'.
    revert_wall_entry takes only that film's entry off every device (hidden, 'reverted': the
    next run purges it); no entry -> False, nothing changed."""
    F = fixtures()
    with frozen_clock(TODAY):
        from pipeline import putback
        tj = dict(copy.deepcopy(F['tracking'][TOM_AND_JERRY]), status='available', digital_date=TODAY,
                  _transitioned_at=TODAY, enriched=True, enrichment_date=TODAY)
        tj.pop('_buyonly_preorder')
        assert putback.owner_revert(tj) is True
        _assert_reverted(tj)
        assert 'digital_date' not in tj and tj['_jw_reverted_at'] == TODAY

        hm = dict(copy.deepcopy(F['tracking'][HIS_MONSTER]), digital_date='2026-10-05', _put_back_on='2026-11-02',
                  _held_since='2026-10-16', _date_needs_review=True, _digital_date_source='putback_review')
        assert putback.owner_revert(hm) is True
        _assert_reverted(hm)
        assert 'digital_date' not in hm

        eye = copy.deepcopy(F['tracking'][AN_EYE_FOR_AN_EYE])
        held_since, count = eye['_jw_reverted_at'], eye['_jw_revert_count']
        assert count > 1
        assert putback.owner_revert(eye) is True
        _assert_reverted(eye, count=count)
        assert eye['_jw_reverted_at'] == held_since

        wk = copy.deepcopy(F['tracking'][WICKER])
        assert putback.owner_revert(wk) is True
        _assert_reverted(wk)
        assert wk['digital_date'] == '2026-12-01' and wk['_type4_pending'] and wk['_is_preorder'] and wk['_buyonly_preorder']

        removed = copy.deepcopy(F['tracking'][I_SWEAR_REMOVED])
        before = copy.deepcopy(removed)
        assert removed['status'] == 'removed'
        assert putback.owner_revert(removed) is False
        assert removed == before

        site = {'movies': copy.deepcopy(F['background_wall']) + [copy.deepcopy(F['wall'][TOM_AND_JERRY])]}
        others = copy.deepcopy(site['movies'][:-1])
        assert putback.revert_wall_entry(site, int(TOM_AND_JERRY)) is True
        _assert_off_the_wall(site['movies'][-1])
        assert site['movies'][:-1] == others
        snapshot = copy.deepcopy(site)
        assert putback.revert_wall_entry(site, THE_ODYSSEY) is False
        assert site == snapshot


def _graduated_tj_spec(*more_phases, **kw):
    """Tom and Jerry graduates on Nov 14 (staged live Amazon rental, test_d3b): on the main
    wall after the full daily run; then `more_phases`."""
    spec = _tj(amazon_rent('B0TJSTAGED'), **kw)
    spec['ids'] += list(BACKGROUND_IDS)
    spec['phases'] += list(more_phases)
    return spec


def test_r2_admin_revert_takes_a_wrongly_new_film_off_the_wall_and_back_to_waiting(tmp_path):
    """Tom and Jerry is on the main wall today (a live Amazon rental, staged) -- say it was
    wrong. The owner clicks Revert (admin POST /revert-movie, the real admin app): the film is
    back in tracking as a held film -- the owner's revert, checked on JustWatch every run,
    today kept as a 'not out yet' day, its wrong 'new' date dropped -- and its wall entry is
    off every device now (hidden, reverted). The rest of the wall is untouched. Round 2d: the
    route saves and publishes the revert itself ("Save Changes" could not commit it), so no
    'changes pending' flag; outside the site folder (this sandbox) it says nothing was committed."""
    spec = _graduated_tj_spec((TODAY, 'hook:revert'))
    res = run_daily(spec, str(tmp_path / 'sbx'),
                    hooks={'revert': admin_post('/revert-movie', {'movie_id': TOM_AND_JERRY})})
    before, now = after(res, 'gap_fill'), after(res, 'hook:revert')
    assert on_main_wall(only(before['wall'][TOM_AND_JERRY])), 'precondition: on the main wall'
    r = res['hooks']['revert']
    assert r['status'] == 200 and r['json']['success'] is True and not r['pending_flag'], r
    assert 'reverted' in r['json']['message'], r
    assert r['json']['warning'] and 'NOT PUBLISHED YET' in r['json']['message'], r
    _assert_reverted(now['tracking'][TOM_AND_JERRY])
    assert 'digital_date' not in now['tracking'][TOM_AND_JERRY]
    _assert_off_the_wall(only(now['wall'][TOM_AND_JERRY]))
    for mid in BACKGROUND_IDS:
        assert now['wall'][mid] == before['wall'][mid] and on_main_wall(only(now['wall'][mid])), mid


def test_r3_admin_revert_of_a_pending_preorder_keeps_its_future_date_and_it_keeps_waiting(tmp_path):
    """Wicker, a buy-only pending pre-order in the PRE-ORDER lane for 2026-12-01: the owner
    reverts it. Its future date stays (and its pre-order flags); it leaves the PRE-ORDER lane
    now. The next daily run (Nov 15; JustWatch: buy-only, staged) checks it on JustWatch, keeps
    it waiting in tracking -- dated TMDB's moved 2026-11-24, still ahead -- with the day kept
    as 'not out yet'; its reverted entry is purged; it is never 'removed' or on the wall."""
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: _wicker_buyonly_node()},
                    phases=[(TODAY, 'hook:revert')] + two_days('2026-11-15'))
    res = run_daily(spec, str(tmp_path / 'sbx'), hooks={'revert': admin_post('/revert-movie', {'movie_id': WICKER})})
    r = res['hooks']['revert']
    assert r['json']['success'] is True, r
    now = after(res, 'hook:revert')
    rec = now['tracking'][WICKER]
    _assert_reverted(rec)
    assert rec['digital_date'] == '2026-12-01' and rec.get('_type4_pending') and rec.get('_buyonly_preorder'), brief_rec(rec)
    _assert_off_the_wall(only(now['wall'][WICKER]))

    assert 'Wicker' in jw_titles(res, 'discover', '2026-11-15'), 'not checked on JustWatch after the revert'
    end = final(res)
    rec = end['tracking'][WICKER]
    assert rec['status'] == 'tracking' and rec['digital_date'] == '2026-11-24', brief_rec(rec)
    assert rec.get('_jw_last_refuted') == '2026-11-15', brief_rec(rec)
    assert not end['wall'][WICKER], f'reverted entry not purged: {brief(only(end["wall"][WICKER]))}'
    for name, st in res['phases'].items():
        assert st['tracking'][WICKER]['status'] != 'removed', name
        assert not visible(only(st['wall'][WICKER])), name


def test_r4_removed_title_is_never_reverted_and_never_comes_back(tmp_path):
    """Remove and Revert are opposites. Tom and Jerry is on the main wall (staged live
    rental); the owner clicks REMOVE (admin POST /remove-movie, unchanged in v2): status
    'removed' (manual_removal), its date cleared, its entry gone. Revert is then refused --
    by the admin route and by scripts/revert_movie.py -- and changes nothing. The next daily
    run (Nov 15, JustWatch still shows the rental) never asks JustWatch about it and never
    puts it back. I Swear, removed by the owner in May and on Netflix now, likewise."""
    spec = _graduated_tj_spec((TODAY, 'hook:remove'), (TODAY, 'hook:revert'), (TODAY, 'hook:revert_script'),
                              *two_days('2026-11-15'))
    spec['ids'].append(I_SWEAR_REMOVED)
    spec['tracking'][I_SWEAR_REMOVED] = copy.deepcopy(fixtures()['tracking'][I_SWEAR_REMOVED])
    spec['tmdb'][I_SWEAR_REMOVED] = copy.deepcopy(fixtures()['tmdb'][I_SWEAR_REMOVED])
    res = run_daily(spec, str(tmp_path / 'sbx'), hooks={
        'remove': admin_post('/remove-movie', {'movie_id': TOM_AND_JERRY}),
        'revert': admin_post('/revert-movie', {'movie_id': TOM_AND_JERRY}),
        'revert_script': script_hook('scripts/revert_movie.py', TOM_AND_JERRY)})

    assert res['hooks']['remove']['json']['success'] is True, res['hooks']['remove']
    removed = after(res, 'hook:remove')
    rec = removed['tracking'][TOM_AND_JERRY]
    assert rec['status'] == 'removed' and rec['removed_reason'] == 'manual_removal' and rec['removed_date'] == TODAY, \
        brief_rec(rec, 'removed_reason', 'removed_date')
    assert rec['digital_date'] is None and rec['removed_from_wall'] is True
    assert not removed['wall'][TOM_AND_JERRY], 'Remove left the entry on the wall'

    r = res['hooks']['revert']
    assert r['json']['success'] is False and 'removed' in r['json']['error'], r
    s = res['hooks']['revert_script']
    assert s['exit'] == 1 and 'REMOVED' in s['stdout'], s
    for hook in ('hook:revert', 'hook:revert_script'):
        assert after(res, hook)['tracking'][TOM_AND_JERRY] == rec, f'{hook} changed the removed record'
        assert not after(res, hook)['wall'][TOM_AND_JERRY]

    for mid, title in ((TOM_AND_JERRY, 'Tom and Jerry: Forbidden Compass'), (I_SWEAR_REMOVED, 'I Swear')):
        assert title not in jw_titles(res, day='2026-11-15'), f'{title}: removed, yet checked on JustWatch'
        for name, st in res['phases'].items():
            if name.split(':', 2)[1] == '2026-11-15':
                assert st['tracking'][mid]['status'] == 'removed', f'{name}: {brief_rec(st["tracking"][mid])}'
                assert not st['wall'][mid], f'{name}: back on the wall: {brief(only(st["wall"][mid]))}'


def test_r5_admin_revert_reports_a_missing_or_unknown_film(tmp_path):
    """The admin route's guards: no movie id, or a film not in tracking -> an error, and
    nothing changes (tracking and data.json byte-identical)."""
    spec = scenario([TOM_AND_JERRY], wall_ids=[TOM_AND_JERRY], phases=[(TODAY, 'hook:bad')])
    seen = {}

    def bad(day):
        with open('data.json', 'rb') as f:
            wall0 = f.read()
        with open('movie_tracking.json', 'rb') as f:
            trk0 = f.read()
        out = {}
        for name, payload in (('missing', {}), ('blank', {'movie_id': '  '}), ('unknown', {'movie_id': '999999999'})):
            out[name] = admin_post('/revert-movie', payload)(day)['json']
        with open('data.json', 'rb') as f:
            seen['wall_same'] = f.read() == wall0
        conn = sqlite3.connect('movie_tracking.db')
        seen['trk'] = {row[0]: json.loads(row[1]) for row in conn.execute('SELECT id, data FROM movies')}
        conn.close()
        seen['trk0'] = json.loads(trk0)['movies']
        return out

    res = run_daily(spec, str(tmp_path / 'sbx'), hooks={'bad': bad})
    out = res['hooks']['bad']
    assert out['missing'] == {'success': False, 'error': 'Movie ID is required'}, out
    assert out['blank'] == {'success': False, 'error': 'Movie ID is required'}, out
    assert out['unknown']['success'] is False and 'not found' in out['unknown']['error'], out
    assert seen['wall_same'] and seen['trk'] == seen['trk0']


_R6_CASES = {
    # case: (film, how the owner gets it into the state the script sees, expected exit, stdout needle)
    'wrongly_new_on_the_wall': (TOM_AND_JERRY, 'graduated', 0, 'off the wall now'),
    'pending_preorder_future_date': (WICKER, 'as_recorded', 0, 'off the wall now'),
    'waiting_not_on_the_wall': (THE_ODYSSEY, 'as_recorded', 0, 'was not on the wall'),
    'removed_by_the_owner': (I_SWEAR_REMOVED, 'as_recorded', 1, 'REMOVED for good'),
    'not_in_tracking': ('999999999', None, 1, 'not in tracking'),
}


@pytest.mark.parametrize('case', list(_R6_CASES))
def test_r6_revert_script_does_what_the_admin_button_does(case, tmp_path):
    """scripts/revert_movie.py (the new /revert command) on real records, run as the owner
    runs it (python3 scripts/revert_movie.py <id>, cwd = the site checkout -- here a sandbox,
    under the write audit): a wrongly-new film on the wall (Tom and Jerry after its staged
    graduation) and a pending pre-order (Wicker, 2026-12-01 kept) are reverted and taken off
    the wall; a waiting film with no entry (The Odyssey) is reverted in tracking only; a
    REMOVED title (I Swear) and an unknown id are refused (exit 1) with nothing changed. No
    argument prints the usage (exit 2)."""
    mid, state, code, needle = _R6_CASES[case]
    ids = [m for m in (mid,) if m in fixtures()['tracking']]
    if state == 'graduated':
        spec = _graduated_tj_spec((TODAY, 'hook:script'), phases=('discover',))
    else:
        spec = scenario(ids or [TOM_AND_JERRY], wall_ids=[m for m in ids if m in fixtures()['wall']], phases=())
        spec['phases'] = [(TODAY, 'hook:script')]
    spec['phases'].insert(len(spec['phases']) - 1, (TODAY, 'hook:usage'))
    res = run_daily(spec, str(tmp_path / 'sbx'), hooks={'script': script_hook('scripts/revert_movie.py', mid),
                                                         'usage': script_hook('scripts/revert_movie.py')})
    usage = res['hooks']['usage']
    assert usage['exit'] == 2 and 'Usage' in usage['stdout'], usage
    s = res['hooks']['script']
    assert s['exit'] == code and needle in s['stdout'], s
    if not ids:
        return
    before, now = after(res, 'hook:usage'), after(res, 'hook:script')
    if state == 'graduated':
        assert on_main_wall(only(before['wall'][mid])), 'precondition: on the main wall'
    rec = now['tracking'][mid]
    if code == 0:
        _assert_reverted(rec)
        if mid == WICKER:
            assert rec['digital_date'] == '2026-12-01', brief_rec(rec)
        elif mid == TOM_AND_JERRY:
            assert 'digital_date' not in rec, brief_rec(rec)
        if needle == 'off the wall now':
            _assert_off_the_wall(only(now['wall'][mid]))
        else:
            assert not now['wall'][mid]
    else:
        assert rec == before['tracking'][mid] and now['wall'][mid] == before['wall'][mid], brief_rec(rec)
        assert rec['status'] == 'removed'


@pytest.fixture(scope='session')
def revert_e2e(tmp_path_factory):
    """Nov 14: Tom and Jerry graduates (staged live Amazon rental) and ends the day on the
    main wall; the owner reverts it (admin button). Nov 15: JustWatch shows only its real
    Apple BUY offer (the 'rental' was the mistake). Nov 16: a live Amazon rental from Nov 16
    (staged). Run once, shared by test_r7 / test_r7b."""
    d1, d2, d3 = TODAY, '2026-11-15', '2026-11-16'
    spec = scenario([TOM_AND_JERRY], wall_ids=[TOM_AND_JERRY], jw_over={TOM_AND_JERRY: jw_node(TOM_AND_JERRY)},
                    jw_days={d1: {TOM_AND_JERRY: jw_node(TOM_AND_JERRY, amazon_rent('B0TJSTAGED', day=d1))},
                             d3: {TOM_AND_JERRY: jw_node(TOM_AND_JERRY, amazon_rent('B0TJREAL', day=d3))}},
                    phases=two_days(d1) + [(d1, 'hook:revert')] + two_days(d2, d3), today=d1)
    root = str(tmp_path_factory.mktemp('revert_e2e') / 'sbx')
    return run_daily(spec, root, hooks={'revert': admin_post('/revert-movie', {'movie_id': TOM_AND_JERRY})})


def test_r7_reverted_film_comes_back_on_its_own_the_day_it_is_really_out(revert_e2e):
    """The Revert's whole purpose, over three real daily runs (see revert_e2e). After the
    revert it is off the wall. Nov 15 (JustWatch: buy-only): checked on JustWatch, and it
    ends the day NOT on the main wall. Nov 16 (a live rental): it ends the day on the main
    wall, dated Nov 16 -- never on or before the revert day -- with its Amazon link. It is
    never 'removed' and never duplicated on the way."""
    res, mid = revert_e2e, TOM_AND_JERRY
    d1, d2, d3 = TODAY, '2026-11-15', '2026-11-16'
    assert on_main_wall(only(after(res, 'gap_fill', d1)['wall'][mid])), 'precondition: on the main wall'
    assert res['hooks']['revert']['json']['success'] is True, res['hooks']['revert']
    reverted = after(res, 'hook:revert')
    _assert_reverted(reverted['tracking'][mid])
    _assert_off_the_wall(only(reverted['wall'][mid]))

    started = False
    for name, st in res['phases'].items():
        started = started or name.endswith('hook:revert')
        if not started:
            continue
        rec, entry = st['tracking'][mid], only(st['wall'][mid])
        assert rec['status'] != 'removed', f'{name}: a reverted title was removed'
        if visible(entry):
            assert entry['digital_date'] > d1, f'{name}: dated on/before the revert day: {brief(entry)}'

    assert 'Tom and Jerry: Forbidden Compass' in jw_titles(res, 'discover', d2), 'not checked the day after the revert'
    assert not on_main_wall(only(after(res, 'gap_fill', d2)['wall'][mid])), \
        f'{d2}: back on the main wall while JustWatch shows it buy-only: {brief(only(after(res, "gap_fill", d2)["wall"][mid]))}'
    end = final(res)
    entry = only(end['wall'][mid])
    assert on_main_wall(entry) and entry['digital_date'] == d3, brief(entry)
    assert 'Amazon' in vod_services(entry), vod_services(entry)
    assert end['tracking'][mid]['status'] == 'available' and end['tracking'][mid]['digital_date'] == d3


REVERT_BOUNCE_DEFECT = (
    "The morning after an owner Revert, discovery puts the reverted film straight back on the MAIN WALL while "
    "JustWatch still shows it buy-only: the revert's hold makes it a held film, and a held film is put back on "
    "any JustWatch 'verified' result -- verified='buy_only' is truthy in ProviderDiscoverer._verify_before_wall "
    "-- dated the day after the revert (putback_after_hold), its reverted entry unhidden by "
    "add_movie_to_site_immediately; only enrichment's buy-only detector pulls it again. The same mechanism as "
    "test_e1b's exposed cases; it is published when enrichment and the gap fill both miss the film.")


def test_r7b_reverted_film_stays_off_the_main_wall_after_the_next_discovery(revert_e2e):
    """Checkpoint between discovery and enrichment on Nov 15 (data.json as discovery leaves
    it): a film the owner just reverted, still buy-only on JustWatch, must not be back on the
    main wall."""
    entry = only(after(revert_e2e, 'discover', '2026-11-15')['wall'][TOM_AND_JERRY])
    rec = after(revert_e2e, 'discover', '2026-11-15')['tracking'][TOM_AND_JERRY]
    assert not on_main_wall(entry), f'back on the main wall: {brief(entry)}; tracking {brief_rec(rec)}'


def test_r8_only_the_owners_remove_sets_status_removed():
    """No automatic path may set status 'removed' (owner, Nov 15). Every Python file of the
    pipeline, the admin panel, the scripts (scripts/revert_movie.py included) and the repo
    root is parsed: the ONLY code that writes status 'removed' is the admin Remove button's
    route (admin/routes/movies.py remove_movie). (/remove does it from its own instructions.)"""
    import ast
    import glob

    def key(s):
        s = s.value if isinstance(s, getattr(ast, 'Index', ())) else s
        return s.value if isinstance(s, ast.Constant) else None

    def removed(v):
        return isinstance(v, ast.Constant) and v.value == 'removed'

    files = sorted(set(glob.glob(os.path.join(WT, 'pipeline', '*.py'))
                       + glob.glob(os.path.join(WT, 'admin', '**', '*.py'), recursive=True)
                       + glob.glob(os.path.join(WT, 'scripts', '**', '*.py'), recursive=True)
                       + glob.glob(os.path.join(WT, '*.py'))))
    assert os.path.join(WT, 'scripts', 'revert_movie.py') in files and os.path.join(WT, 'pipeline', 'putback.py') in files
    hits = []
    for path in files:
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read(), path)
        stack = []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                stack.append(n.name)
                self.generic_visit(n)
                stack.pop()
            visit_AsyncFunctionDef = visit_FunctionDef

            def hit(self, n):
                hits.append((os.path.relpath(path, WT), stack[-1] if stack else '<module>'))

            def visit_Assign(self, n):
                if removed(n.value) and any((isinstance(t, ast.Subscript) and key(t.slice) == 'status')
                                            or (isinstance(t, ast.Attribute) and t.attr == 'status')
                                            for t in n.targets):
                    self.hit(n)
                self.generic_visit(n)

            def visit_Dict(self, n):
                if any(isinstance(k, ast.Constant) and k.value == 'status' and removed(v)
                       for k, v in zip(n.keys, n.values)):
                    self.hit(n)
                self.generic_visit(n)

            def visit_Call(self, n):
                if any(kw.arg == 'status' and removed(kw.value) for kw in n.keywords):
                    self.hit(n)
                if (isinstance(n.func, ast.Attribute) and n.func.attr in ('setdefault', '__setitem__')
                        and len(n.args) >= 2 and key(n.args[0]) == 'status' and removed(n.args[1])):
                    self.hit(n)
                self.generic_visit(n)
        V().visit(tree)
    assert hits == [('admin/routes/movies.py', 'remove_movie')], hits


# ==================================================================================
# (e) REGRESSION GUARD: what counts as a pre-release is unchanged
# ==================================================================================
#
# Real JustWatch shapes (captured 2026-11-14), each on the film's own real record:
#   FAH        How to Rob a Bank: in cinemas + BUY Fandango At Home $24.99 only (a pre-sale)
#   BN         Galaxymphony: Barnes & Noble DVD only (+ an Amazon-channel stream NRW skips)
#   PVOD       Resident Evil: in cinemas + RENT $19.99 (Amazon / Apple TV / Fandango At Home)
#   PVOD_HELD  Sense and Sensibility: same PVOD shape, held without a pre-order flag
# run through the lanes Step 1 changed:
#   as_recorded  the record exactly as in the production snapshot
#   held_silent  + a real 'no valid offers' hold (Liberation's) on a day TMDB lists
#                nothing for it (Step 1 checks holds without any TMDB signal)
#   skipped      + a real 4-strike permanent skip (An Eye for an Eye's), retired by Step 1
#   buyonly      + flagged a buy-only pre-order (Step 1 adds a daily JustWatch check)
# Same scenario, same fake network (store pages render nothing the pre-order check can
# read, as observed for Barnes & Noble), production code vs v2.

SENSE_AND_SENSIBILITY = '1503762'
E_SHAPES = {'FAH': HOW_TO_ROB_A_BANK, 'BN': GALAXYMPHONY, 'PVOD': RESIDENT_EVIL,
            'PVOD_HELD': SENSE_AND_SENSIBILITY}
E_LANES = ('as_recorded', 'held_silent', 'skipped', 'buyonly')
_HOLD_FIELDS = ('_jw_revert_reason', '_jw_reverted_at', '_jw_revert_count', '_skip_provider_discovery')


def _e_spec(lane, mid):
    F = fixtures()
    tracking_over, tmdb_over = {}, {}
    if lane == 'held_silent':
        src = F['tracking'][LIBERATION]
        tracking_over[mid] = {k: src[k] for k in _HOLD_FIELDS if k in src}
        tracking_over[mid]['_skip_provider_discovery'] = _MISSING
        tmdb_over[mid] = dict(copy.deepcopy(F['tmdb'][mid]),
                              release_dates={'id': int(mid), 'results': []},
                              watch_providers={'id': int(mid), 'results': {}})
    elif lane == 'skipped':
        src = F['tracking'][AN_EYE_FOR_AN_EYE]
        tracking_over[mid] = {k: src[k] for k in _HOLD_FIELDS if k in src}
    elif lane == 'buyonly':
        tracking_over[mid] = {'_buyonly_preorder': True}
    wall_ids = [mid] if mid in F['wall'] else []
    return scenario([mid], wall_ids=wall_ids, phases=('discover', 'enrich', 'gap_fill'),
                    tracking_over=tracking_over, tmdb_over=tmdb_over)


_E_CACHE = {}


@pytest.fixture(scope='session')
def e_root(tmp_path_factory):
    return str(tmp_path_factory.mktemp('regression_guard'))


def _e_results(shape, lane, e_root, head_root, jw_throttled=()):
    """(film id, production result, v2 result, v2 sandbox dir) -- run once per case."""
    key = (shape, lane, tuple(jw_throttled))
    if key not in _E_CACHE:
        mid = E_SHAPES[shape]
        spec = _e_spec(lane, mid)
        spec['jw_throttled'] = list(jw_throttled)
        tag = f'{shape}-{lane}' + (f'-jwdown-{"-".join(jw_throttled)}' if jw_throttled else '')
        head = run_daily_with_code(head_root, spec, os.path.join(e_root, f'{tag}-production'))
        sandbox = os.path.join(e_root, f'{tag}-v2', 'sandbox')
        v2 = run_daily(spec, sandbox)
        assert os.path.realpath(head['pipeline_dir']) == os.path.realpath(os.path.join(head_root, 'pipeline'))
        assert os.path.realpath(v2['pipeline_dir']) == os.path.realpath(os.path.join(WT, 'pipeline'))
        _E_CACHE[key] = (mid, head, v2, sandbox)
    return _E_CACHE[key]


def _where(entry):
    if on_main_wall(entry):
        return 'MAIN WALL'
    if in_preorder_lane(entry):
        return 'pre-order lane'
    return 'not shown' if entry else 'off the wall'


def _summary(res, mid):
    return '; '.join(f"{name.split(':', 2)[2]}: {st['tracking'][mid].get('status')}, {_where(only(st['wall'][mid]))}"
                     for name, st in res['phases'].items())


def _e_params(xfail_cases=(), reason=''):
    out = []
    for shape in E_SHAPES:
        for lane in E_LANES:
            marks = [pytest.mark.xfail(strict=True, reason=reason)] if (shape, lane) in xfail_cases else []
            out.append(pytest.param(shape, lane, id=f'{shape}-{lane}', marks=marks))
    return out


@pytest.mark.parametrize('shape,lane', _e_params())
def test_e1_prerelease_shapes_end_the_daily_run_on_the_main_wall_no_more_than_production(
        shape, lane, e_root, head_code_root):
    """After the whole daily run (discovery, enrichment, gap fill) -- what gets published --
    v2 must not have the pre-sale (Fandango, in theaters) or DVD-only film on the main wall when
    production doesn't (the reverted Nov 13 fix did exactly that). The PVOD shapes (Resident
    Evil, Sense and Sensibility: $19.99 rentals live on Amazon while still in theaters) ARE out
    -- owner, Nov 2026: a $19.99 rental is rentable; production's $15 block held them, the
    owner restored them by hand on Nov 15 -- so v2 must put them on the main wall."""
    mid, head, v2, _ = _e_results(shape, lane, e_root, head_code_root)
    head_main = on_main_wall(only(final(head)['wall'][mid]))
    v2_main = on_main_wall(only(final(v2)['wall'][mid]))
    if shape in ('PVOD', 'PVOD_HELD'):
        assert v2_main, f'{shape}/{lane}: a live $19.99 rental is out, but v2 ends the day without it: {_summary(v2, mid)}'
        return
    assert v2_main <= head_main, (
        f'{shape}/{lane}: v2 ends the day with {mid} on the main wall, production does not.\n'
        f'  v2: {_summary(v2, mid)}\n  production: {_summary(head, mid)}')


# Observed on v2: discovery leaves these on the main wall (data.json, no pre-order flag,
# pending enrichment); the same run's enrichment (PVOD gate / buy-only detector) pulls them,
# and test_e1 holds for every case. v1 had the first four (held / formerly skipped films put
# back in discovery; mirroring the PVOD gate in discovery is Step 2, HANDOFF section 5). Round
# 2 added seven: the put-back now drops _is_preorder ("JustWatch confirmed it: watchable
# now") and the transition sync drops the wall entry's pre-order flags and dates it -- where
# production kept a flagged PRE-ORDER (or dateless) entry until enrichment. The CI job
# commits data.json only after all phases, so this state is published only when enrichment
# AND the gap fill both miss the film (test_f3b: batch limit + JustWatch down for the gap
# fill; test_f3: the gap fill alone catches it). Same mechanism after an owner Revert: test_r7b.
# Round 2e removed the three BN cases (the DVD-only film is a buy-only pre-order): discovery now
# keeps a buy-only pre-order waiting while JustWatch still shows it for purchase only, as
# enrichment's own check would (R2D PO-3: it was the nightly on-the-wall / flagged-back loop).
_DISCOVERY_EXPOSED = {('FAH', 'held_silent'), ('FAH', 'skipped'),
                      ('PVOD_HELD', 'held_silent'), ('PVOD_HELD', 'skipped'),
                      ('PVOD', 'as_recorded'), ('PVOD', 'held_silent'), ('PVOD', 'skipped'), ('PVOD', 'buyonly')}
_DISCOVERY_EXPOSED_WHY = (
    'Between discovery and enrichment v2 has the pre-sale / DVD-only / PVOD film on the MAIN WALL (pending '
    'enrichment) where production had it in the PRE-ORDER lane, dateless, or in tracking: held films are put back '
    'in discovery on any JustWatch "verified" result (buy_only counts) with _is_preorder dropped, and '
    'add_movie_to_site_immediately now syncs an existing entry (pre-order flags dropped, dated). The pre-release '
    'gates run only in enrichment, which pulls them the same run (test_e1 passes); published if enrichment and '
    'the gap fill both miss the film (test_f3b).')


@pytest.mark.parametrize('shape,lane', _e_params(_DISCOVERY_EXPOSED, _DISCOVERY_EXPOSED_WHY))
def test_e1b_after_discovery_prerelease_shapes_are_on_the_main_wall_no_more_than_production(
        shape, lane, e_root, head_code_root):
    """Checkpoint between discovery and enrichment (data.json as discovery leaves it): v2
    must not have put the film on the main wall when production doesn't."""
    mid, head, v2, _ = _e_results(shape, lane, e_root, head_code_root)
    head_main = on_main_wall(only(after(head, 'discover')['wall'][mid]))
    v2_main = on_main_wall(only(after(v2, 'discover')['wall'][mid]))
    assert v2_main <= head_main, (
        f'{shape}/{lane}: after discovery v2 has {mid} on the main wall (as available, pending '
        f'enrichment); production does not.\n  v2: {_summary(v2, mid)}\n  production: {_summary(head, mid)}')


def _put_back_today_lines(sandbox):
    """The real /morning 'overnight' section (scripts/morning_report.py) over the sandbox;
    returns the bullet lines under 'Put back today'."""
    env = dict(os.environ, PYTHONPATH=WT, PYTHONDONTWRITEBYTECODE='1')
    proc = subprocess.run([sys.executable, os.path.join(WT, 'scripts', 'morning_report.py'), '--section', 'overnight'],
                          cwd=sandbox, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    lines, inside = [], False
    for line in proc.stdout.splitlines():
        if line.startswith('Put back today'):
            inside = True
            continue
        if inside:
            if not line.strip():
                break
            lines.append(line)
    return lines, proc.stdout


@pytest.mark.parametrize('shape,lane', _e_params())
def test_e2_morning_report_does_not_announce_a_pulled_prerelease_as_put_back_today(
        shape, lane, e_root, head_code_root):
    """The owner reads /morning's 'Put back today (came out after a hold)'. A film the same
    run kept off the main wall (pulled again as a pre-sale / DVD-only / PVOD title) did not
    come out and must not be listed there. (v1 xfail for six cases -- fixed in v2: the
    put-back happens at the wall move and the report lists only films still available.)"""
    mid, head, v2, sandbox = _e_results(shape, lane, e_root, head_code_root)
    end = final(v2)
    if on_main_wall(only(end['wall'][mid])):
        pytest.skip('film is on the main wall -- listing it is correct')
    title = fixtures()['tracking'][mid]['title']
    lines, report = _put_back_today_lines(sandbox)
    listed = [l for l in lines if title in l]
    assert not listed, (
        f'{shape}/{lane}: /morning says {title} was put back today, but the run left it '
        f'{_where(only(end["wall"][mid]))} with tracking status {end["tracking"][mid].get("status")} '
        f'(reason {end["tracking"][mid].get("_jw_revert_reason")}):\n' + '\n'.join(listed))


# A JustWatch outage that starts after discovery (the JW_BREAKER case: a throttled
# JustWatch answers HTTP 200 with no results, control titles included).
_OUTAGES = {'enrich': ('enrich',), 'enrich+gap_fill': ('enrich', 'gap_fill')}


def _e3_params():
    out = []
    for shape in E_SHAPES:
        for lane in ('as_recorded', 'held_silent'):
            for outage in _OUTAGES:
                out.append(pytest.param(shape, lane, outage, id=f'{shape}-{lane}-jw_down_{outage}'))
    return out


@pytest.mark.parametrize('shape,lane,outage', _e3_params())
def test_e3_justwatch_outage_during_enrichment_does_not_publish_a_prerelease_more_than_production(
        shape, lane, outage, e_root, head_code_root):
    """JustWatch answers discovery normally, then is throttled from enrichment on: the film
    must not end the run on the main wall when production would not. (v1 xfail for seven
    cases -- fixed in v2: an arrival whose JustWatch check fails waits hidden.)"""
    mid, head, v2, _ = _e_results(shape, lane, e_root, head_code_root, jw_throttled=_OUTAGES[outage])
    head_main = on_main_wall(only(final(head)['wall'][mid]))
    v2_main = on_main_wall(only(final(v2)['wall'][mid]))
    assert v2_main <= head_main, (
        f'{shape}/{lane}, JustWatch down for {outage}: v2 publishes {mid} on the main wall, '
        f'production does not.\n  v2: {_summary(v2, mid)}\n  production: {_summary(head, mid)}')


# ----------------------------------------------------------------------------------
# Subprocess entry point (the regression guard runs the scenario on production code)
# ----------------------------------------------------------------------------------

def _main(argv):
    spec_path, out_path, sandbox = argv[2], argv[3], argv[4]
    with open(spec_path) as f:
        spec = json.load(f)
    audit = WriteAudit(WT).install()
    try:
        res = run_daily(spec, sandbox)
    finally:
        audit.uninstall()
    res['write_audit'] = audit.hits
    _write_json(out_path, res)
    return 0


def _main_script(argv):
    """--run-script OUT DAY SCRIPT [ARGS...]: run a repo script (as __main__, cwd = the
    sandbox) under the write audit with the clock frozen on DAY; write its exit code,
    stdout and any refused worktree writes to OUT."""
    import runpy
    out_path, day, script, args = argv[2], argv[3], argv[4], argv[5:]
    audit = WriteAudit(WT).install()
    buf, code = io.StringIO(), 0
    old_argv = sys.argv
    try:
        with frozen_clock(day):
            sys.argv = [script] + list(args)
            try:
                with contextlib.redirect_stdout(buf):
                    runpy.run_path(script, run_name='__main__')
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = old_argv
        audit.uninstall()
    _write_json(out_path, {'exit': code, 'stdout': buf.getvalue(), 'write_audit': audit.hits})
    return 0


# Real records / payloads (see the module docstring; built from the production snapshots and the
# 2026-11-14 captures).
_FIXTURES_JSON = r'''{"_v2_notes":"dateCreated mirrored from availableFromTime on the 2026-11-14 capture; added Beware Boiuna, DreamQuil, His Monster (records from 78303fd6)","background_wall":[{"_digital_date_source":"tmdb_type4","_discovered_at":"2026-11-13T16:08:57.783364","_discovery_source":"tmdb_type4","_enrichment_attempts":1,"_enrichment_gaps":["rt_score","wikipedia","imdb_rating","metacritic_score","letterboxd_score"],"_enrichment_status":"completed","_imdb_votes":null,"_last_enrichment_attempt":"2026-11-13","_minimal_entry":false,"_needs_review":false,"_reissue":false,"_slop_confidence":"weak","_slop_reason":"score:6(no_wiki,no_rt,no_imdb)","_tmdb_fetch_failed":false,"_trailer_source":"gemini_playwright","bootstrap_date":false,"budget":0,"country":"US","crew":{"cast":["Gary Sinise","Tim Allen","Chip Foose","Jay Leno","Joe Mantegna"],"director":"Steve Mitchell Beebe"},"digital_date":"2026-11-11","display_title":"The Ballad of Lieutenant Dan","featured":false,"filters":{"auto_categorized":true,"is_documentary":true,"is_foreign":false,"is_indie":false,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":false,"manual_override":null},"genres":["Documentary"],"id":"1822148","imdb_rating":null,"is_slop":true,"keywords":["first responders","veterans","gary sinise","gold star"],"letterboxd_score":null,"links":{"cast_wiki":{"Chip Foose":"https://en.wikipedia.org/wiki/Chip_Foose","Gary Sinise":"https://en.wikipedia.org/wiki/Gary_Sinise","Tim Allen":"https://en.wikipedia.org/wiki/Tim_Allen"},"imdb":"https://www.imdb.com/title/tt43753986/","justwatch":"https://www.justwatch.com/us/movie/the-ballad-of-lieutenant-dan","letterboxd":"https://letterboxd.com/film/the-ballad-of-lieutenant-dan","metacritic":"https://www.metacritic.com/movie/the-ballad-of-lieutenant-dan/","rt":"https://www.rottentomatoes.com/m/the_ballad_of_lieutenant_dan","trailer":"https://www.youtube.com/watch?v=V5G8yAlLPo0","trailer_hosted":"https://f004.backblazeb2.com/file/NRW-TRAILERS/1822148.mp4","wikipedia":null},"manually_corrected":false,"metacritic_score":null,"original_language":"en","original_title":"The Ballad of Lieutenant Dan","poster":"https://image.tmdb.org/t/p/w500/mvYbWDyOicP6WMYvEPlOJVra3bA.jpg","pre_order_links":[],"providers":{"buy":[],"rent":[],"streaming":[]},"reissue_label":null,"rt_score":null,"runtime":85,"status":"available","studio":"Unknown","synopsis":"Inspired by the character he played and told by those who know him best, Gary Sinise’s story follows his mission to serve injured veterans and Gold Star families while enduring the devastating loss of his son, Mac.","title":"The Ballad of Lieutenant Dan","watch_links":{"streaming":[{"link":"https://www.hoopladigital.com/title/20448957?utm_source=justwatch","service":"Hoopla"}],"vod":[{"buy_price":"$9.99","link":"https://athome.fandango.com/content/browse/details/The-Ballad-of-Lieutenant-Dan/5134793","price":"$3.99","rent_price":"$3.99","service":"Fandango"},{"buy_price":"$12.99","link":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.fde36575-bd58-485c-afde-00d0254d0198&tag=nrw04-20","price":"$4.99","rent_price":"$4.99","service":"Amazon"},{"buy_price":"$12.99","link":"https://tv.apple.com/us/movie/the-ballad-of-lieutenant-dan/umc.cmc.749dp23yswiysjv8f05vst4tz?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6820660520","price":"$4.99","rent_price":"$4.99","service":"Apple TV"}]},"year":2026},{"_digital_date_source":"tmdb_type4","_discovered_at":"2026-11-13T16:08:55.851631","_discovery_source":"tmdb_type4","_enrichment_attempts":1,"_enrichment_gaps":["rt_score","wikipedia","imdb_rating","metacritic_score","letterboxd_score"],"_enrichment_status":"completed","_imdb_votes":null,"_last_enrichment_attempt":"2026-11-13","_minimal_entry":false,"_needs_review":false,"_reissue":false,"_slop_confidence":"weak","_slop_reason":"score:6(no_wiki,no_rt,no_imdb)","_tmdb_fetch_failed":false,"_trailer_source":"tmdb_official","bootstrap_date":false,"budget":0,"country":"Canada","crew":{"cast":["Maxie Dara","Brett Wolfe","Emily Burke","Jordan Cole","Kailey Cutillo"],"director":"Rachelle Zalter"},"digital_date":"2026-11-13","display_title":"Noli & Owen Are Fine","featured":false,"filters":{"auto_categorized":true,"is_documentary":false,"is_foreign":false,"is_indie":false,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":false,"manual_override":null},"genres":["Comedy","Romance"],"id":"1798526","imdb_rating":null,"is_slop":true,"keywords":[],"letterboxd_score":null,"links":{"imdb":"https://www.imdb.com/title/tt34984275/","justwatch":"https://www.justwatch.com/us/movie/noli-and-owen-are-fine","rt":"https://www.rottentomatoes.com/m/noli_and_owen_are_fine","trailer":"https://www.youtube.com/watch?v=dGyLE4XwfXA","trailer_hosted":"https://f004.backblazeb2.com/file/NRW-TRAILERS/1798526.mp4","wikipedia":null},"manually_corrected":false,"original_language":"en","original_title":"Noli & Owen Are Fine","poster":"https://image.tmdb.org/t/p/w500/ezzjK88DqLUZUhmoISawlBpgL.jpg","pre_order_links":[],"providers":{"buy":[],"rent":[],"streaming":[]},"reissue_label":null,"rt_score":null,"runtime":96,"status":"available","studio":"Day10 Films","synopsis":"Noli and Owen have been friends forever, and made a pact in high school that if neither is married when they turn 35, they'll marry each other. With the deadline looming, they set each other up on a series of dates to avoid their true feelings.","title":"Noli & Owen Are Fine","watch_links":{"streaming":[{"link":"https://www.hoopladigital.com/title/20449819?utm_source=justwatch","service":"Hoopla"}],"vod":[{"buy_price":"$9.99","link":"https://athome.fandango.com/content/browse/details/Noli-Owen-Are-Fine/5134787","price":"$3.99","rent_price":"$3.99","service":"Fandango"},{"buy_price":"$9.99","link":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.e6ab5fe2-600d-4015-a9bb-c7f4f8a1b36c&tag=nrw04-20","price":"$4.99","rent_price":"$4.99","service":"Amazon"},{"buy_price":"$9.99","link":"https://tv.apple.com/us/movie/noli--owen-are-fine/umc.cmc.103ctnx04u26m9ppnfnu5w1hm?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6822845255","price":"$4.99","rent_price":"$4.99","service":"Apple TV"}]},"year":null}],"captured":"2026-11-14","jw":{"1021848":{"content":{"credits":[{"name":"Lance Hammer","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1021848"},"fullPath":"/us/movie/queen-at-sea","originalReleaseYear":2026,"title":"Queen at Sea"},"id":"tm1955515","objectId":1955515,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Regal Cinemas","technicalName":"regalcinemas"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.regmovies.com/movies/queen-at-sea-ho00023103"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Harkins Theatres","technicalName":"harkinstheaters"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.harkins.com/movies/queen-at-sea"}]},"1125627":{"content":{"credits":[],"externalIds":{"tmdbId":"1125627"},"fullPath":"/us/movie/dreamquil","originalReleaseYear":2026,"title":"DreamQuil"},"id":"tm1125627","objectId":1125627,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":"2026-11-10T00:00:00Z","monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$14.99","standardWebURL":"https://athome.fandango.com/content/browse/details/DreamQuil/staged"}]},"1195803":{"content":{"credits":[{"name":"Alex Huston Fischer","role":"DIRECTOR"},{"name":"Eleanor Wilson","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1195803"},"fullPath":"/us/movie/wicker","originalReleaseYear":2026,"title":"Wicker"},"id":"tm1933753","objectId":1933753,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Atom Tickets","technicalName":"atomtickets"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.atomtickets.com/movies/wicker/366837"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinemark","technicalName":"cinemark"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"http://www.cinemark.com/movies/wicker"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinepolis Cinemas","technicalName":"cinepoliscinema"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.cinepolisusa.com/movie/wicker"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Regal Cinemas","technicalName":"regalcinemas"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.regmovies.com/movies/wicker-ho00022557"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Harkins Theatres","technicalName":"harkinstheaters"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.harkins.com/movies/wicker"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Marcus Theatres","technicalName":"marcustheatres"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.marcustheatres.com/movies/wicker-HO00007833"}]},"1244523":{"content":{"credits":[],"externalIds":{"tmdbId":"1244523"},"fullPath":"/us/movie/beware-boiuna","originalReleaseYear":2026,"title":"Beware Boiúna"},"id":"tm1244523","objectId":1244523,"objectType":"MOVIE","offers":[{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-10-20T00:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$14.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.a9eb0d4b-efba-4225-a259-caaa18dda9fb"},{"availableFromTime":"2026-11-03T07:00:00Z","currency":"USD","dateCreated":"2026-10-20T00:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$14.99","standardWebURL":"https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6812862855"},{"availableFromTime":null,"currency":"USD","dateCreated":"2026-10-20T00:00:00Z","monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$14.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Beware-Boi-na/5214925"}]},"1341138":{"content":{"credits":[{"name":"Scott Moore","role":"DIRECTOR"},{"name":"Jon Lucas","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1341138"},"fullPath":"/us/movie/spa-weekend","originalReleaseYear":2026,"title":"Spa Weekend"},"id":"tm1928875","objectId":1928875,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Fandango","technicalName":"fandango"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.fandango.com/spa-weekend-2026-245958/movie-overview"},{"availableFromTime":"2026-11-10T05:00:00Z","currency":"USD","dateCreated":"2026-11-10T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$5.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d0edf7df-4dd1-4138-bebd-749bfbfbd72b"},{"availableFromTime":"2026-11-10T05:00:00Z","currency":"USD","dateCreated":"2026-11-10T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"_4K","retailPrice":"$5.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d0edf7df-4dd1-4138-bebd-749bfbfbd72b"},{"availableFromTime":"2026-08-21T07:00:00Z","currency":"USD","dateCreated":"2026-08-21T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"SD","retailPrice":"$5.99","standardWebURL":"https://tv.apple.com/us/movie/spa-weekend/umc.cmc.1xaj7m04c816hrkxvp170di0y?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6801673721"},{"availableFromTime":"2026-08-21T07:00:00Z","currency":"USD","dateCreated":"2026-08-21T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$5.99","standardWebURL":"https://tv.apple.com/us/movie/spa-weekend/umc.cmc.1xaj7m04c816hrkxvp170di0y?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6801673721"},{"availableFromTime":"2026-08-21T07:00:00Z","currency":"USD","dateCreated":"2026-08-21T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"_4K","retailPrice":"$5.99","standardWebURL":"https://tv.apple.com/us/movie/spa-weekend/umc.cmc.1xaj7m04c816hrkxvp170di0y?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6801673721"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$5.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Spa-Weekend/5134956"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$5.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Spa-Weekend/5134956"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"_4K","retailPrice":"$5.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Spa-Weekend/5134956"},{"availableFromTime":"2026-11-10T05:00:00Z","currency":"USD","dateCreated":"2026-11-10T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$14.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d0edf7df-4dd1-4138-bebd-749bfbfbd72b"},{"availableFromTime":"2026-11-10T05:00:00Z","currency":"USD","dateCreated":"2026-11-10T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"_4K","retailPrice":"$14.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d0edf7df-4dd1-4138-bebd-749bfbfbd72b"},{"availableFromTime":"2026-08-21T07:00:00Z","currency":"USD","dateCreated":"2026-08-21T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$14.99","standardWebURL":"https://tv.apple.com/us/movie/spa-weekend/umc.cmc.1xaj7m04c816hrkxvp170di0y?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6801673721"},{"availableFromTime":"2026-08-21T07:00:00Z","currency":"USD","dateCreated":"2026-08-21T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"_4K","retailPrice":"$14.99","standardWebURL":"https://tv.apple.com/us/movie/spa-weekend/umc.cmc.1xaj7m04c816hrkxvp170di0y?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6801673721"},{"availableFromTime":"2026-08-21T07:00:00Z","currency":"USD","dateCreated":"2026-08-21T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"SD","retailPrice":"$14.99","standardWebURL":"https://tv.apple.com/us/movie/spa-weekend/umc.cmc.1xaj7m04c816hrkxvp170di0y?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6801673721"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$14.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Spa-Weekend/5134956"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$14.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Spa-Weekend/5134956"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"_4K","retailPrice":"$14.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Spa-Weekend/5134956"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"DVD","retailPrice":"$17.95","standardWebURL":"https://www.amazon.com/dp/B0HFSQRVLW?tag=justwatch09-20&linkCode=osi&th=1&psc=1"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"BLURAY","retailPrice":"$22.95","standardWebURL":"https://www.amazon.com/dp/B0HFSLSVDQ?tag=justwatch09-20&linkCode=osi&th=1&psc=1"}]},"1368337":{"content":{"credits":[{"name":"Christopher Nolan","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1368337"},"fullPath":"/us/movie/the-odyssey-2026","originalReleaseYear":2026,"title":"The Odyssey"},"id":"tm1544003","objectId":1544003,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinemark","technicalName":"cinemark"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"http://www.cinemark.com/movies/the-odyssey"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Regal Cinemas","technicalName":"regalcinemas"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.regmovies.com/movies/the-odyssey-ho00019072"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Harkins Theatres","technicalName":"harkinstheaters"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.harkins.com/movies/the-odyssey"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"DVD","retailPrice":"$19.95","standardWebURL":"https://www.amazon.com/dp/B0HJBNJD44?tag=justwatch09-20&linkCode=osi&th=1&psc=1"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"BLURAY","retailPrice":"$24.95","standardWebURL":"https://www.amazon.com/dp/B0HJBTGSBX?tag=justwatch09-20&linkCode=osi&th=1&psc=1"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"BLURAY_4K","retailPrice":"$29.95","standardWebURL":"https://www.amazon.com/dp/B0HJBMRJS1?tag=justwatch09-20&linkCode=osi&th=1&psc=1"}]},"1423191":{"content":{"credits":[{"name":"Zach Cregger","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1423191"},"fullPath":"/us/movie/resident-evil-2026","originalReleaseYear":2026,"title":"Resident Evil"},"id":"tm1607195","objectId":1607195,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Atom Tickets","technicalName":"atomtickets"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.atomtickets.com/movies/resident-evil/385364"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinemark","technicalName":"cinemark"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"http://www.cinemark.com/movies/resident-evil"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinepolis Cinemas","technicalName":"cinepoliscinema"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.cinepolisusa.com/movie/resident-evil"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Regal Cinemas","technicalName":"regalcinemas"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.regmovies.com/movies/resident-evil-reissue-ho00023138"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Harkins Theatres","technicalName":"harkinstheaters"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.harkins.com/movies/resident-evil"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Marcus Theatres","technicalName":"marcustheatres"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.marcustheatres.com/movies/resident-evil-HO00007648"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"SD","retailPrice":"$19.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d5d9b990-3bc3-4706-aa19-f30cfb4496f0"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$19.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d5d9b990-3bc3-4706-aa19-f30cfb4496f0"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"_4K","retailPrice":"$19.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d5d9b990-3bc3-4706-aa19-f30cfb4496f0"},{"availableFromTime":"2026-09-18T07:00:00Z","currency":"USD","dateCreated":"2026-09-18T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"SD","retailPrice":"$19.99","standardWebURL":"https://tv.apple.com/us/movie/resident-evil/umc.cmc.1oweeytxhn136fmlgpizbxsc5?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6807575287"},{"availableFromTime":"2026-09-18T07:00:00Z","currency":"USD","dateCreated":"2026-09-18T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"_4K","retailPrice":"$19.99","standardWebURL":"https://tv.apple.com/us/movie/resident-evil/umc.cmc.1oweeytxhn136fmlgpizbxsc5?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6807575287"},{"availableFromTime":"2026-09-18T07:00:00Z","currency":"USD","dateCreated":"2026-09-18T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$19.99","standardWebURL":"https://tv.apple.com/us/movie/resident-evil/umc.cmc.1oweeytxhn136fmlgpizbxsc5?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6807575287"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"_4K","retailPrice":"$19.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Resident-Evil-2026-/5187401"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$19.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Resident-Evil-2026-/5187401"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$19.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Resident-Evil-2026-/5187401"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"SD","retailPrice":"$24.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d5d9b990-3bc3-4706-aa19-f30cfb4496f0"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$24.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d5d9b990-3bc3-4706-aa19-f30cfb4496f0"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"_4K","retailPrice":"$24.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d5d9b990-3bc3-4706-aa19-f30cfb4496f0"},{"availableFromTime":"2026-09-18T07:00:00Z","currency":"USD","dateCreated":"2026-09-18T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$24.99","standardWebURL":"https://tv.apple.com/us/movie/resident-evil/umc.cmc.1oweeytxhn136fmlgpizbxsc5?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6807575287"},{"availableFromTime":"2026-09-18T07:00:00Z","currency":"USD","dateCreated":"2026-09-18T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"_4K","retailPrice":"$24.99","standardWebURL":"https://tv.apple.com/us/movie/resident-evil/umc.cmc.1oweeytxhn136fmlgpizbxsc5?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6807575287"},{"availableFromTime":"2026-09-18T07:00:00Z","currency":"USD","dateCreated":"2026-09-18T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"SD","retailPrice":"$24.99","standardWebURL":"https://tv.apple.com/us/movie/resident-evil/umc.cmc.1oweeytxhn136fmlgpizbxsc5?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6807575287"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"_4K","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Resident-Evil-2026-/5187401"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Resident-Evil-2026-/5187401"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Resident-Evil-2026-/5187401"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"DVD","retailPrice":"$24.99","standardWebURL":"https://www.amazon.com/dp/B0HH134GB5?tag=justwatch09-20&linkCode=osi&th=1&psc=1"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"BLURAY","retailPrice":"$29.99","standardWebURL":"https://www.amazon.com/dp/B0HH134YQ4?tag=justwatch09-20&linkCode=osi&th=1&psc=1"}]},"1437511":{"content":{"credits":[{"name":"David Leitch","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1437511"},"fullPath":"/us/movie/how-to-rob-a-bank-2026","originalReleaseYear":2026,"title":"How to Rob a Bank"},"id":"tm1633156","objectId":1633156,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Atom Tickets","technicalName":"atomtickets"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.atomtickets.com/movies/how-to-rob-a-bank/387229"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinemark","technicalName":"cinemark"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"http://www.cinemark.com/movies/how-to-rob-a-bank"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinepolis Cinemas","technicalName":"cinepoliscinema"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.cinepolisusa.com/movie/how-to-rob-a-bank"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Harkins Theatres","technicalName":"harkinstheaters"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.harkins.com/movies/how-to-rob-a-bank"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"B&B Theatres","technicalName":"bbtheatres"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.bbtheatres.com/showtimes/1000020289-how-to-rob-a-bank"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Marcus Theatres","technicalName":"marcustheatres"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.marcustheatres.com/movies/how-to-rob-a-bank-HO00007686"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/How-to-Rob-a-Bank/5308501"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/How-to-Rob-a-Bank/5308501"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"_4K","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/How-to-Rob-a-Bank/5308501"}]},"1497970":{"content":{"credits":[{"name":"Zhang Gang","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1497970"},"fullPath":"/us/movie/tom-and-jerry-forbidden-compass","originalReleaseYear":2025,"title":"Tom and Jerry: Forbidden Compass"},"id":"tm1648541","objectId":1648541,"objectType":"MOVIE","offers":[{"availableFromTime":"2026-09-04T07:00:00Z","currency":"USD","dateCreated":"2026-09-04T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"SD","retailPrice":"$12.99","standardWebURL":"https://tv.apple.com/us/movie/tom-and-jerry-forbidden-compass/umc.cmc.7clx0uqkqjiuefew4dlizh4k0?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6809456627"},{"availableFromTime":"2026-09-04T07:00:00Z","currency":"USD","dateCreated":"2026-09-04T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$12.99","standardWebURL":"https://tv.apple.com/us/movie/tom-and-jerry-forbidden-compass/umc.cmc.7clx0uqkqjiuefew4dlizh4k0?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6809456627"}]},"1503762":{"content":{"credits":[{"name":"Georgia Oakley","role":"DIRECTOR"}],"externalIds":{"tmdbId":"1503762"},"fullPath":"/us/movie/sense-and-sensibility-2026","originalReleaseYear":2026,"title":"Sense and Sensibility"},"id":"tm1918108","objectId":1918108,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Atom Tickets","technicalName":"atomtickets"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.atomtickets.com/movies/sense-and-sensibility-2026/395156"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinemark","technicalName":"cinemark"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"http://www.cinemark.com/movies/sense-and-sensibility"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Cinepolis Cinemas","technicalName":"cinepoliscinema"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.cinepolisusa.com/movie/sense-and-sensibility"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Regal Cinemas","technicalName":"regalcinemas"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.regmovies.com/movies/sense-and-sensibility-ho00021990"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Harkins Theatres","technicalName":"harkinstheaters"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.harkins.com/movies/sense-and-sensibility"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Marcus Theatres","technicalName":"marcustheatres"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.marcustheatres.com/movies/sense-and-sensibility-HO00007823"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"DVD","retailPrice":"$17.95","standardWebURL":"https://www.amazon.com/dp/B0HKMFS3VK?tag=justwatch09-20&linkCode=osi&th=1&psc=1"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"_4K","retailPrice":"$19.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"SD","retailPrice":"$19.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$19.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3"},{"availableFromTime":"2026-10-16T07:00:00Z","currency":"USD","dateCreated":"2026-10-16T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"_4K","retailPrice":"$19.99","standardWebURL":"https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884"},{"availableFromTime":"2026-10-16T07:00:00Z","currency":"USD","dateCreated":"2026-10-16T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$19.99","standardWebURL":"https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884"},{"availableFromTime":"2026-10-16T07:00:00Z","currency":"USD","dateCreated":"2026-10-16T07:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"SD","retailPrice":"$19.99","standardWebURL":"https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"_4K","retailPrice":"$19.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$19.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$19.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Amazon DVD / Blu-ray","technicalName":"amazondvdbr"},"presentationType":"BLURAY","retailPrice":"$22.95","standardWebURL":"https://www.amazon.com/dp/B0HKMP275J?tag=justwatch09-20&linkCode=osi&th=1&psc=1"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"SD","retailPrice":"$24.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"_4K","retailPrice":"$24.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3"},{"availableFromTime":"2026-11-03T05:00:00Z","currency":"USD","dateCreated":"2026-11-03T05:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$24.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3"},{"availableFromTime":"2026-10-16T07:00:00Z","currency":"USD","dateCreated":"2026-10-16T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"_4K","retailPrice":"$24.99","standardWebURL":"https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884"},{"availableFromTime":"2026-10-16T07:00:00Z","currency":"USD","dateCreated":"2026-10-16T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$24.99","standardWebURL":"https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884"},{"availableFromTime":"2026-10-16T07:00:00Z","currency":"USD","dateCreated":"2026-10-16T07:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"SD","retailPrice":"$24.99","standardWebURL":"https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6825120884"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"_4K","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"SD","retailPrice":"$24.99","standardWebURL":"https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236"}]},"1559261":{"content":{"credits":[],"externalIds":{"tmdbId":"1559261"},"fullPath":"/us/movie/galaxymphony-the-final-odyssey","originalReleaseYear":2025,"title":"Galaxymphony - The Final Odyssey"},"id":"tm1874228","objectId":1874228,"objectType":"MOVIE","offers":[{"availableFromTime":"2026-11-01T04:00:00Z","currency":"USD","dateCreated":"2026-11-01T04:00:00Z","monetizationType":"FLATRATE","package":{"clearName":"Stingray Classica Amazon Channel","technicalName":"amazonstingrayclassica"},"presentationType":"SD","retailPrice":null,"standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.0c9d6c6e-f220-45c8-9889-04f4f7911658"},{"availableFromTime":"2026-11-01T04:00:00Z","currency":"USD","dateCreated":"2026-11-01T04:00:00Z","monetizationType":"FLATRATE","package":{"clearName":"Stingray Classica Amazon Channel","technicalName":"amazonstingrayclassica"},"presentationType":"HD","retailPrice":null,"standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.0c9d6c6e-f220-45c8-9889-04f4f7911658"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Barnes & Noble","technicalName":"barnesandnoble"},"presentationType":"DVD","retailPrice":"$34.99","standardWebURL":"https://www.barnesandnoble.com/w/dvd-galaxymphony-the-final-odyssey-danish-national-symphony-orchestra/1148393344"}]},"1563321":{"content":{"credits":[],"externalIds":{"tmdbId":"1563321"},"fullPath":"/us/movie/his-monster","originalReleaseYear":2025,"title":"His Monster"},"id":"tm1563321","objectId":1563321,"objectType":"MOVIE","offers":[{"availableFromTime":null,"currency":"USD","dateCreated":"2026-10-05T00:00:00Z","monetizationType":"BUY","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$9.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.46c8eda2-bc84-4cdb-b289-1a31de07d467"},{"availableFromTime":null,"currency":"USD","dateCreated":"2026-10-05T00:00:00Z","monetizationType":"BUY","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$9.99","standardWebURL":"https://tv.apple.com/us/movie/his-monster/umc.cmc.6vqkn8vyzgur37grk3t6afcpn?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6805173531"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"BUY","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$9.99","standardWebURL":"https://athome.fandango.com/content/browse/details/His-Monster/5096518"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"CINEMA","package":{"clearName":"Fandango","technicalName":"fandango"},"presentationType":"CANVAS","retailPrice":null,"standardWebURL":"https://www.fandango.com/his-monster-2025/movie-overview"},{"availableFromTime":null,"currency":"USD","dateCreated":"2026-09-25T00:00:00Z","monetizationType":"FREE","package":{"clearName":"Hoopla","technicalName":"hoopla"},"presentationType":"HD","retailPrice":null,"standardWebURL":"https://www.hoopladigital.com/title/20292976?utm_source=justwatch"},{"availableFromTime":null,"currency":"USD","dateCreated":"2026-10-05T00:00:00Z","monetizationType":"RENT","package":{"clearName":"Amazon Video","technicalName":"amazon"},"presentationType":"HD","retailPrice":"$4.99","standardWebURL":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.46c8eda2-bc84-4cdb-b289-1a31de07d467"},{"availableFromTime":null,"currency":"USD","dateCreated":"2026-10-05T00:00:00Z","monetizationType":"RENT","package":{"clearName":"Apple TV Store","technicalName":"itunes"},"presentationType":"HD","retailPrice":"$4.99","standardWebURL":"https://tv.apple.com/us/movie/his-monster/umc.cmc.6vqkn8vyzgur37grk3t6afcpn?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6805173531"},{"availableFromTime":null,"currency":"USD","dateCreated":null,"monetizationType":"RENT","package":{"clearName":"Fandango At Home","technicalName":"vudu"},"presentationType":"HD","retailPrice":"$4.99","standardWebURL":"https://athome.fandango.com/content/browse/details/His-Monster/5096518"}]},"1578210":null,"940009":{"content":{"credits":[{"name":"Brad Bird","role":"DIRECTOR"}],"externalIds":{"tmdbId":"940009"},"fullPath":"/us/movie/ray-gunn","originalReleaseYear":2026,"title":"Ray Gunn"},"id":"tm1527310","objectId":1527310,"objectType":"MOVIE","offers":[]}},"jw_canary":{"Oppenheimer":{"content":{"credits":[{"name":"Christopher Nolan","role":"DIRECTOR"}],"externalIds":{"tmdbId":"872585"},"fullPath":"/us/movie/oppenheimer","originalReleaseYear":2023,"title":"Oppenheimer"},"id":"tm1111989","objectId":1111989,"objectType":"MOVIE","offers":[{"availableFromTime":"2026-08-16T10:00:00Z","currency":"USD","dateCreated":"2026-08-16T10:00:00Z","monetizationType":"FLATRATE","package":{"clearName":"Peacock Premium","technicalName":"peacocktv"},"presentationType":"SD","retailPrice":null,"standardWebURL":"https://www.peacocktv.com/watch/asset/movies/oppenheimer/602fd345-3ad6-33fd-a70d-a0e059b8d38a"},{"availableFromTime":"2026-08-16T10:00:00Z","currency":"USD","dateCreated":"2026-08-16T10:00:00Z","monetizationType":"FLATRATE","package":{"clearName":"Peacock Premium","technicalName":"peacocktv"},"presentationType":"HD","retailPrice":null,"standardWebURL":"https://www.peacocktv.com/watch/asset/movies/oppenheimer/602fd345-3ad6-33fd-a70d-a0e059b8d38a"}]}},"tmdb":{"1021848":{"details":{"alternative_titles":{"titles":[]},"budget":0,"credits":{"cast":[{"name":"Juliette Binoche"},{"name":"Tom Courtenay"},{"name":"Anna Calder-Marshall"},{"name":"Florence Hunt"},{"name":"Steven Cree"}],"crew":[{"job":"Director","name":"Lance Hammer"}]},"external_ids":{"imdb_id":"tt27541205"},"genres":[{"id":18,"name":"Drama"}],"id":1021848,"keywords":{"keywords":[{"name":"dementia"},{"name":"autonomy"},{"name":"consent"}]},"origin_country":["GB"],"original_language":"en","original_title":"Queen at Sea","overview":"As advanced dementia erodes an older woman's ability to communicate her inner life, her husband and daughter struggle to act in her best interests, navigating love and the fragile boundaries between care, protection and autonomy.","poster_path":"/ueYawr1nldKchzyP8Q9KJpn31SK.jpg","production_companies":[{"name":"The Bureau"}],"production_countries":[{"iso_3166_1":"GB","name":"United Kingdom"}],"release_date":"2026-09-18","runtime":121,"title":"Queen at Sea","videos":{"results":[]}},"release_dates":{"id":1021848,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"Aspen Film Festival","release_date":"2026-10-03T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Philadelphia Film Festival","release_date":"2026-10-16T00:00:00.000Z","type":1},{"certification":"NR","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-10-30T00:00:00.000Z","type":2}]}]},"watch_providers":{"id":1021848,"results":{}}},"1195803":{"details":{"alternative_titles":{"titles":[]},"budget":10000000,"credits":{"cast":[{"name":"Olivia Colman"},{"name":"Alexander Skarsgård"},{"name":"Peter Dinklage"},{"name":"Elizabeth Debicki"},{"name":"Marli Siu"}],"crew":[{"job":"Director","name":"Alex Huston Fischer"}]},"external_ids":{"imdb_id":"tt29611136"},"genres":[{"id":10749,"name":"Romance"},{"id":14,"name":"Fantasy"},{"id":35,"name":"Comedy"}],"id":1195803,"keywords":{"keywords":[{"name":"jealousy"},{"name":"based on novel or book"},{"name":"village"},{"name":"romcom"},{"name":"loneliness"}]},"origin_country":["US"],"original_language":"en","original_title":"Wicker","overview":"On the outskirts of a village by the sea, lives a Fisherwoman; smelly, single and perpetually ridiculed. One day, fed up with her stuffy, small-minded neighbours, she commissions herself a husband to be made from wicker. In an otherwise conservative town, this unconventional romance sparks outrage, jealousy and chaos.","poster_path":"/6FcBZOKvyrLCKGCyBG0ySCR4okt.jpg","production_companies":[{"name":"Topic Studios"}],"production_countries":[{"iso_3166_1":"GB","name":"United Kingdom"},{"iso_3166_1":"US","name":"United States of America"}],"release_date":"2026-10-21","runtime":105,"title":"Wicker","videos":{"results":[]}},"release_dates":{"id":1195803,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"Sundance Film Festival","release_date":"2026-01-24T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Beyond Fest","release_date":"2026-10-04T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Mill Valley Film Festival","release_date":"2026-10-10T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Hamptons International Film Festival","release_date":"2026-10-12T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Woodstock Film Festival / Middleburg Film Festival","release_date":"2026-10-17T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Denver Film Festival","release_date":"2026-10-25T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Philadelphia Film Festival","release_date":"2026-10-21T00:00:00.000Z","type":1},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-10-23T00:00:00.000Z","type":3},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-11-24T00:00:00.000Z","type":4}]}]},"watch_providers":{"id":1195803,"results":{}}},"1244523":{"details":{"alternative_titles":{"titles":[{"iso_3166_1":"US","title":"Titan","type":"working title"},{"iso_3166_1":"US","title":"Boiúna: Legend of the Amazon","type":"working title"},{"iso_3166_1":"AR","title":"Terror en el Amazonas","type":""},{"iso_3166_1":"RU","title":"Берегись Боюны","type":""}]},"budget":0,"credits":{"cast":[{"adult":false,"cast_id":1,"character":"Lena","credit_id":"65cba0f312970c0162c5f3ba","gender":1,"id":142115,"known_for_department":"Acting","name":"Kiana Madeira","order":0,"original_name":"Kiana Madeira","popularity":1.6021,"profile_path":"/sw5jTOmdHhAZzVMIzSVEDi5g7lz.jpg"},{"adult":false,"cast_id":2,"character":"Alli","credit_id":"65cba0faa06efe0184770fb0","gender":1,"id":1427680,"known_for_department":"Acting","name":"Jessica Rothe","order":1,"original_name":"Jessica Rothe","popularity":1.5766,"profile_path":"/oItPXy56W0Y5taqIMZilRtnPDMn.jpg"},{"adult":false,"cast_id":12,"character":"Callum","credit_id":"678a152245f296f6011d67b7","gender":2,"id":2427360,"known_for_department":"Acting","name":"Will Close","order":2,"original_name":"Will Close","popularity":0.3869,"profile_path":"/lgsHBbNrY8SEdsOIQEEXMOSqTgY.jpg"},{"adult":false,"cast_id":11,"character":"Miguel","credit_id":"678a14ef55e49bed5e97af4c","gender":2,"id":565373,"known_for_department":"Acting","name":"Juan Pablo Shuk","order":3,"original_name":"Juan Pablo Shuk","popularity":0.4611,"profile_path":"/bUJgufFSqWMpa8gEXPTNun8MP8i.jpg"},{"adult":false,"cast_id":35,"character":"Brennan","credit_id":"67b7ba1e21d4708b60eb2098","gender":2,"id":130253,"known_for_department":"Acting","name":"Logan Marshall-Green","order":4,"original_name":"Logan Marshall-Green","popularity":2.677,"profile_path":"/oogXh2Osxw43bfjMVCcCH8SGsUB.jpg"},{"adult":false,"cast_id":14,"character":"Raúl","credit_id":"678a157e45f296f6011d67e3","gender":2,"id":1681399,"known_for_department":"Acting","name":"Jaime Newball","order":5,"original_name":"Jaime Newball","popularity":0.3463,"profile_path":null},{"adult":false,"cast_id":10,"character":"Shawn","credit_id":"678a14d9102c1794ef1d24eb","gender":2,"id":1502461,"known_for_department":"Acting","name":"Jackson Bews","order":6,"original_name":"Jackson Bews","popularity":0.4873,"profile_path":"/of70BbE1KAq6J1PuUFnEHRyzh3Z.jpg"},{"adult":false,"cast_id":40,"character":"Yaguari Leader","credit_id":"6aea7fb5df93f2f0e6aa290a","gender":0,"id":6598081,"known_for_department":"Acting","name":"Tonfy Andoque","order":7,"original_name":"Tonfy Andoque","popularity":0.3177,"profile_path":null},{"adult":false,"cast_id":41,"character":"Reynaldo","credit_id":"6aea7fe2dbee0d057417d85d","gender":0,"id":6598085,"known_for_department":"Acting","name":"Andres Paier","order":8,"original_name":"Andres Paier","popularity":0.0926,"profile_path":null},{"adult":false,"cast_id":42,"character":"Garimpeiro Leader","credit_id":"6aea8009eb662de4b77d1fb9","gender":0,"id":6598088,"known_for_department":"Acting","name":"Victor Bustos","order":9,"original_name":"Victor Bustos","popularity":0.0966,"profile_path":null},{"adult":false,"cast_id":43,"character":"Jorge","credit_id":"6aea803d51264957f4fae883","gender":0,"id":3380534,"known_for_department":"Acting","name":"Sergio Herrera","order":10,"original_name":"Sergio Herrera","popularity":0.3692,"profile_path":"/sYMwiEOBNg1vRjJrMhtwGcgcLKA.jpg"},{"adult":false,"cast_id":15,"character":"Diego","credit_id":"678a15d645f296f6011d6804","gender":0,"id":5184999,"known_for_department":"Acting","name":"Mateo Moreno","order":11,"original_name":"Mateo Moreno","popularity":0.0891,"profile_path":null},{"adult":false,"cast_id":45,"character":"Alvaro","credit_id":"6aea80be2fb54bc2eb17d8b3","gender":0,"id":6598097,"known_for_department":"Acting","name":"Orlando Diago","order":12,"original_name":"Orlando Diago","popularity":0.1131,"profile_path":null},{"adult":false,"cast_id":44,"character":"Female Miner","credit_id":"6aea80a6eb662de4b77d1fda","gender":0,"id":6598095,"known_for_department":"Acting","name":"Sandra Rodriguez","order":13,"original_name":"Sandra Rodriguez","popularity":0.0558,"profile_path":null},{"adult":false,"cast_id":46,"character":"Boy in Yellow","credit_id":"6aea80e1171287382df2e9a6","gender":0,"id":6598099,"known_for_department":"Acting","name":"Axel Stiven Campos","order":14,"original_name":"Axel Stiven Campos","popularity":0.1405,"profile_path":null},{"adult":false,"cast_id":47,"character":"Fisherman","credit_id":"6aea813f2fb54bc2eb17d8d0","gender":0,"id":4170775,"known_for_department":"Crew","name":"Gueber Raul Ariza","order":15,"original_name":"Gueber Raul Ariza","popularity":0.0662,"profile_path":null},{"adult":false,"cast_id":16,"character":"Guilherme","credit_id":"678a16085e0fbbe3e9ad4199","gender":2,"id":929933,"known_for_department":"Acting","name":"Nelson Camayo","order":16,"original_name":"Nelson Camayo","popularity":0.4961,"profile_path":"/rWlL59TzadOr9jUs73ClyZoM0iO.jpg"},{"adult":false,"cast_id":17,"character":"Proctor","credit_id":"678a16251403701c991d7cc1","gender":0,"id":2410120,"known_for_department":"Acting","name":"Christophe de Geest","order":17,"original_name":"Christophe de Geest","popularity":0.1765,"profile_path":null},{"adult":false,"cast_id":13,"character":"Pedro","credit_id":"678a155e8677bdfadfad551c","gender":0,"id":3692568,"known_for_department":"Acting","name":"Vicente Peña","order":18,"original_name":"Vicente Peña","popularity":0.0703,"profile_path":null},{"adult":false,"cast_id":48,"character":"Young Lena","credit_id":"6aea817cc0820d8fda7d2159","gender":0,"id":6598105,"known_for_department":"Acting","name":"Karla Estefani Diez","order":19,"original_name":"Karla Estefani Diez","popularity":0.0251,"profile_path":null},{"adult":false,"cast_id":49,"character":"Young Jorge","credit_id":"6aea818b7b4b1bac4d78dfd1","gender":0,"id":6598106,"known_for_department":"Acting","name":"Santiago Banguero","order":20,"original_name":"Santiago Banguero","popularity":0.0441,"profile_path":null},{"adult":false,"cast_id":50,"character":"Logger","credit_id":"6aea81b19aa52e7b1517d8c0","gender":0,"id":6598107,"known_for_department":"Acting","name":"Jorge Munoz","order":21,"original_name":"Jorge Munoz","popularity":0.162,"profile_path":null},{"adult":false,"cast_id":51,"character":"Yaguari Warrior","credit_id":"6aea81d95f7fd2b132f2eb07","gender":0,"id":6598108,"known_for_department":"Acting","name":"Alfonso Enrique Vanegas","order":22,"original_name":"Alfonso Enrique Vanegas","popularity":0.1223,"profile_path":null},{"adult":false,"cast_id":52,"character":"Yaguari Warrior","credit_id":"6aea81e90074289526fae97a","gender":0,"id":6598110,"known_for_department":"Acting","name":"Carlos Alberto Matias Moreno","order":23,"original_name":"Carlos Alberto Matias Moreno","popularity":0.0546,"profile_path":null},{"adult":false,"cast_id":53,"character":"Yaguari Warrior","credit_id":"6aea81f6ed607a33d3aa2899","gender":0,"id":2374965,"known_for_department":"Acting","name":"Miguel Dionisio Ramos","order":24,"original_name":"Miguel Dionisio Ramos","popularity":0.1279,"profile_path":null},{"adult":false,"cast_id":54,"character":"Yaguari Warrior","credit_id":"6aea82075f7fd2b132f2eb12","gender":0,"id":6598111,"known_for_department":"Acting","name":"Armando Enrriquez","order":25,"original_name":"Armando Enrriquez","popularity":0.1123,"profile_path":null},{"adult":false,"cast_id":55,"character":"Yaguari Warrior","credit_id":"6aea821420f55baa17fae87a","gender":0,"id":6598112,"known_for_department":"Acting","name":"Hermes Enriquez","order":26,"original_name":"Hermes Enriquez","popularity":0.0361,"profile_path":null},{"adult":false,"cast_id":56,"character":"Yaguari Warrior","credit_id":"6aea8222cc9e94b5ebfae9cb","gender":0,"id":6598114,"known_for_department":"Acting","name":"Silvio Lopez Ahue","order":27,"original_name":"Silvio Lopez Ahue","popularity":0.0567,"profile_path":null},{"adult":false,"cast_id":57,"character":"Yaguari Warrior","credit_id":"6aea822e88bf1a80da7d209b","gender":0,"id":6598116,"known_for_department":"Acting","name":"Arnold Jesus Vasquez","order":28,"original_name":"Arnold Jesus Vasquez","popularity":0.1066,"profile_path":null},{"adult":false,"cast_id":58,"character":"Yaguari Warrior","credit_id":"6aea823d9aa52e7b1517d8db","gender":0,"id":6598117,"known_for_department":"Acting","name":"Martha Luisa Noriega","order":29,"original_name":"Martha Luisa Noriega","popularity":0.0748,"profile_path":null},{"adult":false,"cast_id":59,"character":"Yaguari Warrior","credit_id":"6aea824cdbee0d057417d8bd","gender":0,"id":6598118,"known_for_department":"Acting","name":"Victor Ariel Gutierrez","order":30,"original_name":"Victor Ariel Gutierrez","popularity":0.0504,"profile_path":null},{"adult":false,"cast_id":60,"character":"Yaguari Woman","credit_id":"6aea825eeb662de4b77d200b","gender":0,"id":6598119,"known_for_department":"Acting","name":"Claudia Patricia Lopez","order":31,"original_name":"Claudia Patricia Lopez","popularity":0.0765,"profile_path":null},{"adult":false,"cast_id":61,"character":"Feverish Woman","credit_id":"6aea826c825fbfea6ffae940","gender":0,"id":6598120,"known_for_department":"Acting","name":"Maria Dolores Valencia","order":32,"original_name":"Maria Dolores Valencia","popularity":0.075,"profile_path":null},{"adult":false,"cast_id":62,"character":"Suture Patient","credit_id":"6aea828492892284b7f2ebaf","gender":0,"id":6598121,"known_for_department":"Acting","name":"Jhony Rodriguez","order":33,"original_name":"Jhony Rodriguez","popularity":0.0562,"profile_path":null},{"adult":false,"cast_id":63,"character":"Tavern Owner","credit_id":"6aea82943a7e43a111aa292c","gender":0,"id":6598122,"known_for_department":"Acting","name":"Hernando Burgos","order":34,"original_name":"Hernando Burgos","popularity":0.1286,"profile_path":null},{"adult":false,"cast_id":64,"character":"Radio Hut Operator","credit_id":"6aea82ad7b4b1bac4d78e012","gender":0,"id":6598123,"known_for_department":"Acting","name":"Exilin Pena Araujo","order":35,"original_name":"Exilin Pena Araujo","popularity":0.0806,"profile_path":null}],"crew":[{"adult":false,"credit_id":"65cba1548c0a480149b71b33","department":"Production","gender":2,"id":2226017,"job":"Executive Producer","known_for_department":"Production","name":"Michael J. Rothstein","original_name":"Michael J. Rothstein","popularity":0.1674,"profile_path":null},{"adult":false,"credit_id":"65cba10c8c0a48017cb844ed","department":"Directing","gender":2,"id":1039364,"job":"Director","known_for_department":"Directing","name":"Mike P. Nelson","original_name":"Mike P. Nelson","popularity":0.5216,"profile_path":"/uIYmWGeKMHtoQiGQ5AG2cnjxifu.jpg"},{"adult":false,"credit_id":"65cba17c13af5f0163574e46","department":"Production","gender":0,"id":4534532,"job":"Executive Producer","known_for_department":"Production","name":"Sam Hall","original_name":"Sam Hall","popularity":0.049,"profile_path":null},{"adult":false,"credit_id":"65cba137e194b001304d7914","department":"Production","gender":2,"id":4017,"job":"Producer","known_for_department":"Production","name":"Robert Kulzer","original_name":"Robert Kulzer","popularity":0.5249,"profile_path":"/tzQeiYsq9CJIzGSN2nsmez68TM6.jpg"},{"adult":false,"credit_id":"65cba126f9253200c9bef8af","department":"Writing","gender":2,"id":56452,"job":"Writer","known_for_department":"Writing","name":"Alan B. McElroy","original_name":"Alan B. McElroy","popularity":1.0673,"profile_path":"/uUVDalBQ2kwrlzCcZL9HaN45XsU.jpg"},{"adult":false,"credit_id":"65cba140cffeed0164bff314","department":"Production","gender":2,"id":4016,"job":"Producer","known_for_department":"Production","name":"Jeremy Bolt","original_name":"Jeremy Bolt","popularity":0.2952,"profile_path":"/pqbpSnsM5Ord6t6Fx7AqCb0bGqo.jpg"},{"adult":false,"credit_id":"678a16d61403701c991d7d56","department":"Production","gender":2,"id":1018084,"job":"Executive Producer","known_for_department":"Production","name":"Warren T. Goz","original_name":"Warren T. Goz","popularity":0.1832,"profile_path":null},{"adult":false,"credit_id":"678a16fd29071c36ac976df2","department":"Sound","gender":2,"id":2637546,"job":"Original Music Composer","known_for_department":"Sound","name":"Stephen Lukach","original_name":"Stephen Lukach","popularity":0.2425,"profile_path":"/avxGmXKgZW0g8jZvpCLd6irinlv.jpg"},{"adult":false,"credit_id":"678a1799c2470fc60bad04c4","department":"Camera","gender":2,"id":2897704,"job":"Director of Photography","known_for_department":"Camera","name":"Nick Junkersfeld","original_name":"Nick Junkersfeld","popularity":0.131,"profile_path":null},{"adult":false,"credit_id":"678a17f7b9d1d10ef197a962","department":"Editing","gender":2,"id":51795,"job":"Editor","known_for_department":"Editing","name":"Tom Elkins","original_name":"Tom Elkins","popularity":0.1976,"profile_path":null},{"adult":false,"credit_id":"678a181029071c36ac976e56","department":"Production","gender":1,"id":13585,"job":"Casting","known_for_department":"Production","name":"Nancy Nayor","original_name":"Nancy Nayor","popularity":0.3864,"profile_path":null},{"adult":false,"credit_id":"678a182838920393ad1d6cfc","department":"Art","gender":1,"id":1457443,"job":"Production Design","known_for_department":"Art","name":"Angélica Perea","original_name":"Angélica Perea","popularity":0.1139,"profile_path":null},{"adult":false,"credit_id":"678a184ec2470fc60bad0509","department":"Art","gender":0,"id":5185016,"job":"Art Direction","known_for_department":"Art","name":"Nicolas Franco","original_name":"Nicolas Franco","popularity":0.1273,"profile_path":null},{"adult":false,"credit_id":"678a187e38920393ad1d6d52","department":"Costume & Make-Up","gender":0,"id":1760528,"job":"Makeup Designer","known_for_department":"Costume & Make-Up","name":"Juanita Santamaria","original_name":"Juanita Santamaria","popularity":0.1043,"profile_path":null},{"adult":false,"credit_id":"678a18d738920393ad1d6d93","department":"Directing","gender":0,"id":3899943,"job":"Second Assistant Director","known_for_department":"Directing","name":"Andrés David Orozco Correa","original_name":"Andrés David Orozco Correa","popularity":0.1457,"profile_path":null},{"adult":false,"credit_id":"678a18f7c2470fc60bad0586","department":"Directing","gender":0,"id":2825147,"job":"First Assistant Director","known_for_department":"Production","name":"Lorena Villanueva","original_name":"Lorena Villanueva","popularity":0.0981,"profile_path":null},{"adult":false,"credit_id":"678a191993f742cc29ad0880","department":"Art","gender":0,"id":5185022,"job":"Set Decoration","known_for_department":"Art","name":"Valentina Arnedo","original_name":"Valentina Arnedo","popularity":0.0992,"profile_path":null},{"adult":false,"credit_id":"678a192fb9d1d10ef197a9db","department":"Visual Effects","gender":0,"id":1519786,"job":"Special Effects Supervisor","known_for_department":"Crew","name":"Felipe De La Roche","original_name":"Felipe De La Roche","popularity":0.2151,"profile_path":null},{"adult":false,"credit_id":"678a194493f742cc29ad0890","department":"Lighting","gender":0,"id":1582735,"job":"Gaffer","known_for_department":"Lighting","name":"Juan Manuel Barreto","original_name":"Juan Manuel Barreto","popularity":0.0558,"profile_path":null},{"adult":false,"credit_id":"678a195b93f742cc29ad089e","department":"Production","gender":2,"id":1609146,"job":"Casting","known_for_department":"Production","name":"Juan Pablo Rincón","original_name":"Juan Pablo Rincón","popularity":0.1619,"profile_path":null},{"adult":false,"credit_id":"678a197ac2470fc60bad05bf","department":"Production","gender":0,"id":5185024,"job":"Location Manager","known_for_department":"Production","name":"Julian Camilo Torres","original_name":"Julian Camilo Torres","popularity":0.097,"profile_path":null},{"adult":false,"credit_id":"678a1995c2470fc60bad05d0","department":"Production","gender":0,"id":3752976,"job":"Assistant Location Manager","known_for_department":"Production","name":"Gustavo Borbon","original_name":"Gustavo Borbon","popularity":0.0626,"profile_path":null},{"adult":false,"credit_id":"69659263aa9273016b199937","department":"Art","gender":1,"id":3380829,"job":"Art Department Coordinator","known_for_department":"Production","name":"Laura Rubio Reyes","original_name":"Laura Rubio Reyes","popularity":0.125,"profile_path":"/hHQXDUA122Owjyh6RRnuUj9VD6.jpg"},{"adult":false,"credit_id":"6a67f3fa13ab122f4aed10ae","department":"Production","gender":2,"id":1039364,"job":"Executive Producer","known_for_department":"Directing","name":"Mike P. Nelson","original_name":"Mike P. Nelson","popularity":0.5216,"profile_path":"/uIYmWGeKMHtoQiGQ5AG2cnjxifu.jpg"},{"adult":false,"credit_id":"6ac453ae6c938bbd6bdcd1b1","department":"Writing","gender":2,"id":42712,"job":"Story","known_for_department":"Directing","name":"Tony Giglio","original_name":"Tony Giglio","popularity":0.6503,"profile_path":"/t8lw5COh9EdTQmWwNzWNmAJVrKl.jpg"},{"adult":false,"credit_id":"6ac453b8e04687dd6b45648f","department":"Writing","gender":2,"id":56452,"job":"Story","known_for_department":"Writing","name":"Alan B. McElroy","original_name":"Alan B. McElroy","popularity":1.0673,"profile_path":"/uUVDalBQ2kwrlzCcZL9HaN45XsU.jpg"}]},"external_ids":{"facebook_id":null,"imdb_id":"tt10377864","instagram_id":null,"twitter_id":null,"wikidata_id":"Q141052811"},"genres":[{"id":27,"name":"Horror"},{"id":53,"name":"Thriller"},{"id":28,"name":"Action"}],"id":1244523,"keywords":{"keywords":[{"id":5160,"name":"animal attack"},{"id":3891,"name":"giant snake"},{"id":5968,"name":"amazon rainforest"},{"id":10349,"name":"survival"},{"id":13031,"name":"creature"},{"id":50009,"name":"survival horror"},{"id":158126,"name":"creature feature"},{"id":180550,"name":"rainforest"},{"id":223059,"name":"animal horror"},{"id":227584,"name":"humanitarian work"},{"id":264118,"name":"brazil"},{"id":275204,"name":"brazilian folklore"}]},"origin_country":["US"],"original_language":"en","original_title":"Beware Boiúna","overview":"A medical mission deep in the Amazon becomes a desperate fight for survival when a colossal ancient predator awakens, turning the jungle into a deadly battleground where nature decides who lives and dies.","poster_path":"/7mI13sTZcuwWEIUK9fckAb8Zmba.jpg","production_companies":[{"id":47,"logo_path":"/i7Z9ot2o3N5Sa3HrF09kniFs2y8.png","name":"Constantin Film","origin_country":"DE"},{"id":124233,"logo_path":null,"name":"JB Pictures","origin_country":"US"},{"id":128081,"logo_path":"/c7e41WNx0l9UWKwTEHmFxVwNtCd.png","name":"Jaguar Bite","origin_country":"CO"},{"id":220749,"logo_path":null,"name":"North.Five.Six.","origin_country":"US"}],"production_countries":[{"iso_3166_1":"US","name":"United States of America"},{"iso_3166_1":"DE","name":"Germany"},{"iso_3166_1":"CO","name":"Colombia"}],"release_date":"2026-10-01","runtime":103,"title":"Beware Boiúna","videos":{"results":[{"id":"6acf4658f99ca36f8c70f7a2","iso_3166_1":"US","iso_639_1":"en","key":"2IYeFilBlxc","name":"“Carnival ride of terror.”","official":true,"published_at":"2026-09-29T17:32:56.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6acf468e9d6fcd624ef4e4d4","iso_3166_1":"US","iso_639_1":"en","key":"WInH_jXEG48","name":"Looking fear right in the snake eyes.","official":true,"published_at":"2026-09-28T19:51:55.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6acf4aca9c050cd1ce70f7a8","iso_3166_1":"US","iso_639_1":"en","key":"VJUZ1BMrNtI","name":"Official Clip ‘Do the Honors’","official":true,"published_at":"2026-09-28T16:00:09.000Z","site":"YouTube","size":1080,"type":"Clip"},{"id":"6ab3f98ee5cc407731bffa25","iso_3166_1":"US","iso_639_1":"en","key":"MQKqgFVU4dQ","name":"Final Trailer","official":true,"published_at":"2026-09-23T16:00:13.000Z","site":"YouTube","size":2160,"type":"Trailer"},{"id":"6aab017c32630ddb8c65d854","iso_3166_1":"US","iso_639_1":"en","key":"33Cd8y4BHbM","name":"‘Grab Onto Something’ Official Clip","official":true,"published_at":"2026-09-16T18:00:07.000Z","site":"YouTube","size":1080,"type":"Clip"},{"id":"6aa9b15059e6c608cd6da23a","iso_3166_1":"US","iso_639_1":"en","key":"NVTkIjUlGz8","name":"Touch grass. Get bit.","official":true,"published_at":"2026-09-15T19:37:29.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6aa04d56bd93d474e7ce5e06","iso_3166_1":"US","iso_639_1":"en","key":"WkX1T3ceihM","name":"She IS that powerful.","official":true,"published_at":"2026-09-08T17:49:03.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6a9889f9e93a32c99309f05a","iso_3166_1":"US","iso_639_1":"en","key":"pwXrrrGIeUk","name":"Grab onto something.","official":true,"published_at":"2026-09-02T19:32:44.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6a986da4e80c0284c8e06bfb","iso_3166_1":"US","iso_639_1":"en","key":"qQ8jZHojioM","name":"Humans are her favorite snack.","official":true,"published_at":"2026-09-02T17:16:23.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6a87766083b0ef8c90c3910b","iso_3166_1":"US","iso_639_1":"en","key":"Vet5fESvTO8","name":"Ssssay her name. Say her name.","official":true,"published_at":"2026-08-20T21:45:24.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6a84a9a914192c902d5ef8b2","iso_3166_1":"US","iso_639_1":"en","key":"rrmmrcrt1MQ","name":"Did you hear that?","official":true,"published_at":"2026-08-18T18:00:04.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6a84a95414192c902d5ef899","iso_3166_1":"US","iso_639_1":"en","key":"3oC9ql-ZjNo","name":"HER jungle. HER rules.","official":true,"published_at":"2026-08-18T17:40:15.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6a7f84bdb715bf1133792cde","iso_3166_1":"US","iso_639_1":"en","key":"nAkYQ6hoxw8","name":"The reactions are in…","official":true,"published_at":"2026-08-14T16:22:53.000Z","site":"YouTube","size":1080,"type":"Teaser"},{"id":"6a7dddbaf2eeecc1e3a07ca7","iso_3166_1":"US","iso_639_1":"en","key":"4fn4UcgzRhg","name":"Official Trailer","official":true,"published_at":"2026-08-13T14:05:01.000Z","site":"YouTube","size":2160,"type":"Trailer"}]}},"release_dates":{"id":1244523,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"Fantastic Fest ","release_date":"2026-09-17T00:00:00.000Z","type":1},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-10-02T00:00:00.000Z","type":3},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-11-03T00:00:00.000Z","type":4}]}]},"watch_providers":{"id":1244523,"results":{"US":{"buy":[{"display_priority":10,"logo_path":"/jn6TLbtaTZntTRX9UYucHJvpQx1.png","provider_id":10,"provider_name":"Amazon Video"},{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"},{"display_priority":24,"logo_path":"/aZRENwYILujqs0RVOZutTh0BVGV.png","provider_id":3,"provider_name":"Google Play Movies"},{"display_priority":25,"logo_path":"/5Maob4o5w8oZnNeYpCDyVFD3M7X.png","provider_id":192,"provider_name":"YouTube"},{"display_priority":41,"logo_path":"/wpOt6x0dRxTrIzuBosto4LGd7E9.png","provider_id":7,"provider_name":"Fandango At Home"}],"link":"https://www.themoviedb.org/movie/1244523-beware-boiuna/watch?locale=US"}}}},"1317149":{"release_dates":{"id":1317149,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"Palm Springs International Film Festival","release_date":"2026-01-06T00:00:00.000Z","type":1},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-04-24T00:00:00.000Z","type":3},{"certification":"","descriptors":[],"iso_639_1":"","note":"Netflix","release_date":"2026-08-22T00:00:00.000Z","type":4},{"certification":"","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-06-02T00:00:00.000Z","type":4}]}]}},"1341138":{"details":{"alternative_titles":{"titles":[]},"budget":20000000,"credits":{"cast":[{"name":"Leslie Mann"},{"name":"Michelle Buteau"},{"name":"Anna Faris"},{"name":"Isla Fisher"},{"name":"Adam Demos"}],"crew":[{"job":"Director","name":"Jon Lucas"}]},"external_ids":{"imdb_id":"tt33305867"},"genres":[{"id":35,"name":"Comedy"}],"id":1341138,"keywords":{"keywords":[{"name":"female friendship"}]},"origin_country":["US"],"original_language":"en","original_title":"Spa Weekend","overview":"Four lifelong friends realize that somewhere between careers, relationships, families, and everyday responsibilities, they’ve forgotten how to take care of themselves and each other. Burned out and overdue for a break, the women escape to a luxury spa retreat for an unforgettable weekend dedicated to fun, laughter, and a lot of really bad decisions.","poster_path":"/uhx4YjT9YbSxrKVE7GWJdjI412J.jpg","production_companies":[{"name":"Suzanne Todd Productions"}],"production_countries":[{"iso_3166_1":"US","name":"United States of America"}],"release_date":"2026-08-20","runtime":97,"title":"Spa Weekend","videos":{"results":[]}},"release_dates":{"id":1341138,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"en","note":"Fontainebleau Las Vegas","release_date":"2026-08-10T00:00:00.000Z","type":1},{"certification":"R","descriptors":[],"iso_639_1":"en","note":"","release_date":"2026-08-21T00:00:00.000Z","type":3},{"certification":"R","descriptors":[],"iso_639_1":"en","note":"","release_date":"2026-09-22T00:00:00.000Z","type":4}]}]},"watch_providers":{"id":1341138,"results":{"US":{"buy":[{"display_priority":10,"logo_path":"/jn6TLbtaTZntTRX9UYucHJvpQx1.png","provider_id":10,"provider_name":"Amazon Video"},{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"},{"display_priority":41,"logo_path":"/wpOt6x0dRxTrIzuBosto4LGd7E9.png","provider_id":7,"provider_name":"Fandango At Home"}],"link":"https://www.themoviedb.org/movie/1341138-spa-weekend/watch?locale=US","rent":[{"display_priority":10,"logo_path":"/jn6TLbtaTZntTRX9UYucHJvpQx1.png","provider_id":10,"provider_name":"Amazon Video"},{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"},{"display_priority":41,"logo_path":"/wpOt6x0dRxTrIzuBosto4LGd7E9.png","provider_id":7,"provider_name":"Fandango At Home"}]}}}},"1368337":{"details":{"alternative_titles":{"titles":[]},"budget":250000000,"credits":{"cast":[{"name":"Matt Damon"},{"name":"Tom Holland"},{"name":"Anne Hathaway"},{"name":"Robert Pattinson"},{"name":"Himesh Patel"}],"crew":[{"job":"Director","name":"Christopher Nolan"}]},"external_ids":{"imdb_id":"tt33764258"},"genres":[{"id":12,"name":"Adventure"},{"id":28,"name":"Action"},{"id":14,"name":"Fantasy"}],"id":1368337,"keywords":{"keywords":[{"name":"ship"},{"name":"trojan war"},{"name":"greek mythology"},{"name":"historical fiction"},{"name":"ancient world"}]},"origin_country":["GB","US"],"original_language":"en","original_title":"The Odyssey","overview":"Odysseus, the legendary King of Ithaca, embarks on a long and perilous journey home following the Trojan War. Throughout his voyage, he is forced to confront the whims of gods, mythological monsters, and trials that stretch both his cunning and his humanity to the breaking point.","poster_path":"/5rhTDKUhPYvpdQIijFIs5VoWsON.jpg","production_companies":[{"name":"Universal Pictures"}],"production_countries":[{"iso_3166_1":"GB","name":"United Kingdom"},{"iso_3166_1":"US","name":"United States of America"}],"release_date":"2026-07-15","runtime":173,"title":"The Odyssey","videos":{"results":[]}},"release_dates":{"id":1368337,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"R","descriptors":[],"iso_639_1":"","note":"New York City, New York","release_date":"2026-07-14T00:00:00.000Z","type":1},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-07-17T00:00:00.000Z","type":3},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-11-17T00:00:00.000Z","type":4},{"certification":"R","descriptors":[],"iso_639_1":"","note":"4K Ultra HD / Blu-ray / DVD","release_date":"2026-11-17T00:00:00.000Z","type":5}]}]},"watch_providers":{"id":1368337,"results":{}}},"1423191":{"details":{"alternative_titles":{"titles":[]},"budget":75000000,"credits":{"cast":[{"name":"Austin Abrams"},{"name":"Paul Walter Hauser"},{"name":"Kali Reis"},{"name":"Zach Cherry"},{"name":"Johnno Wilson"}],"crew":[{"job":"Director","name":"Zach Cregger"}]},"external_ids":{"imdb_id":"tt35538033"},"genres":[{"id":27,"name":"Horror"},{"id":878,"name":"Science Fiction"},{"id":12,"name":"Adventure"}],"id":1423191,"keywords":{"keywords":[{"name":"isolation"},{"name":"infection"},{"name":"outbreak"},{"name":"survival"},{"name":"decapitation"}]},"origin_country":["US"],"original_language":"en","original_title":"Resident Evil","overview":"Medical courier Bryan unwittingly finds himself fighting for survival as one fateful, horrifying night collapses around him in chaos.","poster_path":"/gAgWJhUSQWCgtKR8170nMkYlBda.jpg","production_companies":[{"name":"Constantin Film"}],"production_countries":[{"iso_3166_1":"US","name":"United States of America"},{"iso_3166_1":"DE","name":"Germany"}],"release_date":"2026-09-16","runtime":94,"title":"Resident Evil","videos":{"results":[]}},"release_dates":{"id":1423191,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"Fantastic Fest","release_date":"2026-09-17T00:00:00.000Z","type":1},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-09-18T00:00:00.000Z","type":3},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-11-03T00:00:00.000Z","type":4},{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-12-29T00:00:00.000Z","type":5}]}]},"watch_providers":{"id":1423191,"results":{"US":{"buy":[{"display_priority":10,"logo_path":"/jn6TLbtaTZntTRX9UYucHJvpQx1.png","provider_id":10,"provider_name":"Amazon Video"},{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"},{"display_priority":41,"logo_path":"/wpOt6x0dRxTrIzuBosto4LGd7E9.png","provider_id":7,"provider_name":"Fandango At Home"}],"link":"https://www.themoviedb.org/movie/1423191-resident-evil/watch?locale=US","rent":[{"display_priority":10,"logo_path":"/jn6TLbtaTZntTRX9UYucHJvpQx1.png","provider_id":10,"provider_name":"Amazon Video"},{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"},{"display_priority":41,"logo_path":"/wpOt6x0dRxTrIzuBosto4LGd7E9.png","provider_id":7,"provider_name":"Fandango At Home"}]}}}},"1437511":{"details":{"alternative_titles":{"titles":[]},"budget":60000000,"credits":{"cast":[{"name":"Nicholas Hoult"},{"name":"Zoë Kravitz"},{"name":"Pete Davidson"},{"name":"John C. Reilly"},{"name":"Anna Sawai"}],"crew":[{"job":"Director","name":"David Leitch"}]},"external_ids":{"imdb_id":"tt35866986"},"genres":[{"id":28,"name":"Action"},{"id":80,"name":"Crime"},{"id":53,"name":"Thriller"}],"id":1437511,"keywords":{"keywords":[{"name":"heist"},{"name":"bank robbery"},{"name":"armed robbery"},{"name":"action comedy"},{"name":"livestream"}]},"origin_country":["US"],"original_language":"en","original_title":"How to Rob a Bank","overview":"A crew of social media-savvy bank robbers broadcasts their daring heists, unaware that their growing viral fame has put them in the crosshairs of a veteran FBI agent and a brilliant software engineer. Despite the unlikely duo closing in, the crime ring pushes past their limits, putting everything on the line for their most ambitious heist yet.","poster_path":"/ifYDZkr2qkHFz87TNVvlxajOxl5.jpg","production_companies":[{"name":"87North Productions"}],"production_countries":[{"iso_3166_1":"US","name":"United States of America"}],"release_date":"2026-11-10","runtime":122,"title":"How to Rob a Bank","videos":{"results":[]}},"release_dates":{"id":1437511,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"R","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-11-13T00:00:00.000Z","type":3}]}]},"watch_providers":{"id":1437511,"results":{}}},"1497970":{"details":{"alternative_titles":{"titles":[]},"budget":0,"credits":{"cast":[{"name":"John Shang"},{"name":"Ruan Yifei"},{"name":"Jiang Wen"},{"name":"Shun Zi"},{"name":"Lan Long"}],"crew":[{"job":"Director","name":"Zhang Gang"}]},"external_ids":{"imdb_id":"tt37185884"},"genres":[{"id":16,"name":"Animation"},{"id":35,"name":"Comedy"},{"id":10751,"name":"Family"},{"id":12,"name":"Adventure"},{"id":14,"name":"Fantasy"}],"id":1497970,"keywords":{"keywords":[{"name":"museum"},{"name":"time travel"},{"name":"cat and mouse"},{"name":"foreign language adaptation"},{"name":"anthropomorphic animal"}]},"origin_country":["CN"],"original_language":"zh","original_title":"猫和老鼠：星盘奇缘","overview":"During a chase inside a museum, Tom and Jerry find an ancient magical compass and end up being transported through time. Lost in a distant era, they will need to work together to find a way back home.","poster_path":"/5qttWFjsO62k88civZaDMHiBTvy.jpg","production_companies":[{"name":"Original Force Animation"}],"production_countries":[{"iso_3166_1":"CN","name":"China"}],"release_date":"2025-08-02","runtime":99,"title":"Tom and Jerry: Forbidden Compass","videos":{"results":[]}},"release_dates":{"id":1497970,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"PG","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-09-04T00:00:00.000Z","type":3}]}]},"watch_providers":{"id":1497970,"results":{"US":{"buy":[{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"}],"link":"https://www.themoviedb.org/movie/1497970-mao-he-lao-shu-xing-pan-qi-yuan/watch?locale=US"}}}},"1503762":{"details":{"alternative_titles":{"titles":[]},"budget":25000000,"credits":{"cast":[{"name":"Daisy Edgar-Jones"},{"name":"Esmé Creed-Miles"},{"name":"Caitríona Balfe"},{"name":"Frank Dillane"},{"name":"Herbert Nordrum"}],"crew":[{"job":"Director","name":"Georgia Oakley"}]},"external_ids":{"imdb_id":"tt13609648"},"genres":[{"id":18,"name":"Drama"},{"id":10749,"name":"Romance"}],"id":1503762,"keywords":{"keywords":[{"name":"class society"},{"name":"based on novel or book"},{"name":"england"},{"name":"feminism"},{"name":"affectation"}]},"origin_country":["GB"],"original_language":"en","original_title":"Sense and Sensibility","overview":"A charming, witty, and deeply relatable story of love and sisterhood.","poster_path":"/czsyPHosFNbh4PPqXfqWu1aBXnA.jpg","production_companies":[{"name":"Focus Features"}],"production_countries":[{"iso_3166_1":"GB","name":"United Kingdom"},{"iso_3166_1":"US","name":"United States of America"}],"release_date":"2026-09-23","runtime":132,"title":"Sense and Sensibility","videos":{"results":[]}},"release_dates":{"id":1503762,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"FocusFest ","release_date":"2026-10-10T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"United Artists Theatre (Los Angeles, California)","release_date":"2026-10-07T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"SCAD Savannah Film Festival ","release_date":"2026-10-29T00:00:00.000Z","type":1},{"certification":"PG","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-10-16T00:00:00.000Z","type":3},{"certification":"PG","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-11-03T00:00:00.000Z","type":4},{"certification":"PG","descriptors":[],"iso_639_1":"","note":"4K Ultra HD / Blu-ray / DVD","release_date":"2026-12-15T00:00:00.000Z","type":5}]}]},"watch_providers":{"id":1503762,"results":{"US":{"buy":[{"display_priority":10,"logo_path":"/jn6TLbtaTZntTRX9UYucHJvpQx1.png","provider_id":10,"provider_name":"Amazon Video"},{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"},{"display_priority":24,"logo_path":"/aZRENwYILujqs0RVOZutTh0BVGV.png","provider_id":3,"provider_name":"Google Play Movies"},{"display_priority":25,"logo_path":"/5Maob4o5w8oZnNeYpCDyVFD3M7X.png","provider_id":192,"provider_name":"YouTube"},{"display_priority":41,"logo_path":"/wpOt6x0dRxTrIzuBosto4LGd7E9.png","provider_id":7,"provider_name":"Fandango At Home"}],"link":"https://www.themoviedb.org/movie/1503762-sense-and-sensibility/watch?locale=US","rent":[{"display_priority":10,"logo_path":"/jn6TLbtaTZntTRX9UYucHJvpQx1.png","provider_id":10,"provider_name":"Amazon Video"},{"display_priority":11,"logo_path":"/qdEGArH3lKfFnAtYXMkSYk5wxuG.png","provider_id":2,"provider_name":"Apple TV Store"},{"display_priority":24,"logo_path":"/aZRENwYILujqs0RVOZutTh0BVGV.png","provider_id":3,"provider_name":"Google Play Movies"},{"display_priority":25,"logo_path":"/5Maob4o5w8oZnNeYpCDyVFD3M7X.png","provider_id":192,"provider_name":"YouTube"},{"display_priority":41,"logo_path":"/wpOt6x0dRxTrIzuBosto4LGd7E9.png","provider_id":7,"provider_name":"Fandango At Home"}]}}}},"1559261":{"details":{"alternative_titles":{"titles":[]},"budget":0,"credits":{"cast":[{"name":"Jakob Stegelmann"},{"name":"Sinne Eeg"},{"name":"Isabel Schwartzbach"},{"name":"Kristoffer Appel"},{"name":"David Bateson"}],"crew":[]},"external_ids":{"imdb_id":null},"genres":[{"id":10402,"name":"Music"}],"id":1559261,"keywords":{"keywords":[{"name":"concert"}]},"origin_country":["DK"],"original_language":"en","original_title":"Galaxymphony - The Final Odyssey","overview":"The DR Symphony Orchestra breaks the sound barrier and takes you out into the galaxies — to a place between reality and fantasy with soundtracks from Star Wars, The Mandalorian, Star Trek, Dune, and many more.  Join the orchestra on the third and final symphonic journey through musical universes and cinematic galaxies — all the way to the outermost asteroids and back to Earth again..\r 1. A New Hope  2. Raised By Wolves  3. Rebel Moon  4. Dune (1984)  5. Dune (2021)  6. Star Trek Into Darkness  7. War of the Worlds  8. Valerian and the City of a  Thousand Planets  9. Hyperspace  10. Armageddon  11. Rogue One  12. The Book of Boba Fett  13. The Empire Strikes Back  14. Return of the Jedi  15. Revenge of the Sith  16. The Mandalorian  17. The Phantom Menace","poster_path":"/qIF0DwqG3HFjZ7SYDpYNhcruhqS.jpg","production_companies":[],"production_countries":[],"release_date":"2025-06-01","runtime":82,"title":"Galaxymphony - The Final Odyssey","videos":{"results":[]}},"release_dates":{"id":1559261,"results":[]},"watch_providers":{"id":1559261,"results":{"US":{"flatrate":[{"display_priority":218,"logo_path":"/A5RE4UD6pzWoqVx9pZd9DrvFddv.png","provider_id":2273,"provider_name":"Stingray Classica Amazon Channel"}],"link":"https://www.themoviedb.org/movie/1559261-galaxymphony-the-final-odyssey/watch?locale=US"}}}},"1563321":{"release_dates":{"id":1563321,"results":[]},"watch_providers":{"id":1563321,"results":{"US":{"buy":[{"provider_name":"Amazon Video"},{"provider_name":"Apple TV Store"},{"provider_name":"Google Play Movies"},{"provider_name":"YouTube"},{"provider_name":"Fandango At Home"}],"free":[{"provider_name":"Hoopla"}],"rent":[{"provider_name":"Amazon Video"},{"provider_name":"Apple TV Store"},{"provider_name":"Google Play Movies"},{"provider_name":"YouTube"},{"provider_name":"Fandango At Home"}]}}}},"1578210":{"details":{"alternative_titles":{"titles":[]},"budget":0,"credits":{"cast":[{"name":"Terry Fox"},{"name":"Doug Alward"},{"name":"Darrell Fox"},{"name":"Leslie Scrivener"},{"name":"Darryl Sittler"}],"crew":[{"job":"Director","name":"Sean Menard"}]},"external_ids":{"imdb_id":"tt39130015"},"genres":[{"id":99,"name":"Documentary"}],"id":1578210,"keywords":{"keywords":[]},"origin_country":["CA"],"original_language":"en","original_title":"Run Terry Run","overview":"The extraordinary story of Canadian icon Terry Fox will be told like never before in Run Terry Run, a new feature-length documentary directed by acclaimed filmmaker Sean Menard. The film offers an intimate, behind-the-scenes look at Terry’s legendary 1980 Marathon of Hope, drawing from 96 reels of never-before-seen footage and unheard audio interviews that have remained untouched for 45 years.","poster_path":"/sSstsc561xip9s5FKereo1r1I9i.jpg","production_companies":[{"name":"Sean Menard Productions"}],"production_countries":[{"iso_3166_1":"CA","name":"Canada"}],"release_date":"2026-10-08","runtime":111,"title":"Run Terry Run","videos":{"results":[]}},"release_dates":{"id":1578210,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-11-24T00:00:00.000Z","type":4}]}]},"watch_providers":{"id":1578210,"results":{}}},"940009":{"details":{"alternative_titles":{"titles":[]},"budget":150000000,"credits":{"cast":[{"name":"Sam Rockwell"},{"name":"Scarlett Johansson"},{"name":"Tom Waits"},{"name":"Matt Berry"},{"name":"Kathryn Hunter"}],"crew":[{"job":"Director","name":"Brad Bird"}]},"external_ids":{"imdb_id":"tt18270542"},"genres":[{"id":16,"name":"Animation"},{"id":878,"name":"Science Fiction"},{"id":80,"name":"Crime"},{"id":9648,"name":"Mystery"}],"id":940009,"keywords":{"keywords":[{"name":"infidelity"},{"name":"flying car"},{"name":"laser gun"},{"name":"pop star"},{"name":"photographer"}]},"origin_country":["US"],"original_language":"en","original_title":"Ray Gunn","overview":"In Metropia, a gigantic city in an alternate future as seen from 1939, private eye Raymond Gunn is drawn into a case involving aliens, murder and a multimedia star named Venus Nova.","poster_path":"/rpP29aOKpHy1FhX8OZQdUICEs2j.jpg","production_companies":[{"name":"Skydance Animation"}],"production_countries":[{"iso_3166_1":"US","name":"United States of America"}],"release_date":"2026-12-02","runtime":119,"title":"Ray Gunn","videos":{"results":[]}},"release_dates":{"id":940009,"results":[{"iso_3166_1":"US","release_dates":[{"certification":"","descriptors":[],"iso_639_1":"","note":"Montclair Film Festival","release_date":"2026-10-17T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Chicago International Film Festival ","release_date":"2026-10-18T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Paris Theater (New York City, New York)","release_date":"2026-09-23T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Philadelphia Film Festival","release_date":"2026-10-23T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"AFI Fest ","release_date":"2026-10-25T00:00:00.000Z","type":1},{"certification":"","descriptors":[],"iso_639_1":"","note":"Austin Film Festival","release_date":"2026-10-31T00:00:00.000Z","type":1},{"certification":"PG","descriptors":[],"iso_639_1":"","note":"","release_date":"2026-12-04T00:00:00.000Z","type":2},{"certification":"PG","descriptors":[],"iso_639_1":"","note":"Netflix","release_date":"2026-12-18T00:00:00.000Z","type":4}]}]},"watch_providers":{"id":940009,"results":{}}}},"tracking":{"1021848":{"_buyonly_preorder":true,"_discovery_source":"provider_availability_check","_transitioned_at":"2026-10-31","enriched":true,"enrichment_date":"2026-10-31","festival":"Berlin/Berlinale","first_seen":"2026-02-09","has_providers":false,"intake_pass":"C","providers":{"buy":["Fandango At Home"],"rent":[],"streaming":[]},"status":"tracking","title":"Queen at Sea","year":2026},"1125627":{"digital_date":null,"festival":"SXSW","first_seen":"2026-03-10","has_providers":false,"intake_pass":"C","providers":{},"status":"tracking","title":"DreamQuil","year":2026},"1129188":{"_discovery_source":"tmdb_type4","_is_preorder":true,"_jw_revert_count":1,"_jw_revert_reason":"justwatch_no_valid_offers","_jw_reverted_at":"2026-09-15","_type4_pending":true,"digital_date":"2026-11-17","first_seen":"2026-01-21","has_providers":false,"intake_pass":"B","providers":{},"status":"tracking","title":"Liberation","year":2026},"1195803":{"_buyonly_preorder":true,"_discovery_source":"tmdb_type4","_is_preorder":true,"_transitioned_at":"2026-10-24","_type4_pending":true,"digital_date":"2026-12-01","enriched":true,"enrichment_date":"2026-11-05","festival":"Sundance","first_seen":"2026-01-20","has_providers":true,"intake_pass":"C","providers":{"buy":["Fandango At Home"],"rent":[],"streaming":[]},"status":"tracking","title":"Wicker","year":2026},"1244523":{"_buyonly_preorder":true,"_discovery_source":"tmdb_type4","_is_preorder":true,"_transitioned_at":"2026-11-13","enriched":true,"enrichment_date":"2026-11-13","festival":"Fantastic Fest","has_providers":true,"intake_date":"2026-09-15","intake_pass":"C","is_slop":true,"providers":{"buy":["Fandango At Home"],"rent":[],"streaming":[]},"status":"tracking","title":"Beware Boiúna","year":2026},"1317149":{"_discovery_source":"provider_availability_check","_transitioned_at":"2026-05-28","digital_date":"2026-05-28","enriched":true,"enrichment_date":"2026-05-28","festival":"Toronto/TIFF","first_seen":"2026-01-06","has_providers":true,"intake_pass":"C","providers":{"buy":[],"rent":["Amazon Video"],"streaming":[]},"removed_date":"2026-05-28","removed_reason":"manual_removal","status":"removed","title":"I Swear","year":2025},"1341138":{"_buyonly_preorder":true,"_discovery_source":"tmdb_type4","_is_preorder":true,"_jw_revert_count":1,"_jw_revert_reason":"justwatch_no_valid_offers","_jw_reverted_at":"2026-09-15","_transitioned_at":"2026-08-23","_type4_pending":true,"digital_date":"2028-09-22","enriched":true,"enrichment_date":"2026-08-23","has_providers":false,"intake_date":"2026-08-20","intake_pass":"B","providers":{"buy":["Fandango At Home"],"rent":[],"streaming":[]},"status":"tracking","title":"Spa Weekend","year":2026},"1368337":{"_discovery_source":"tmdb_type4","_is_preorder":true,"_jw_revert_count":1,"_jw_revert_reason":"justwatch_no_valid_offers","_jw_reverted_at":"2026-08-22","_type4_pending":true,"digital_date":"2026-11-17","has_providers":false,"intake_date":"2026-07-15","intake_pass":"B","providers":{},"status":"tracking","title":"The Odyssey","year":2026},"1423191":{"_discovery_source":"tmdb_type4","_is_preorder":true,"_jw_revert_count":1,"_jw_revert_reason":"justwatch_theatrical_pvod","_jw_reverted_at":"2026-11-13","_transitioned_at":"2026-11-13","digital_date":"2026-11-03","enriched":false,"enrichment_date":null,"festival":"Fantastic Fest","has_providers":true,"intake_date":"2026-09-15","intake_pass":"C","providers":{"buy":[],"rent":[],"streaming":[]},"status":"tracking","title":"Resident Evil","year":2026},"1437511":{"digital_date":null,"has_providers":false,"intake_date":"2026-09-03","intake_pass":"B","providers":{},"status":"tracking","title":"How to Rob a Bank","year":2026},"1497947":{"_discovery_source":"provider_availability_check","_jw_revert_count":4,"_jw_revert_reason":"justwatch_no_match","_jw_reverted_at":"2026-08-17","_skip_provider_discovery":true,"digital_date":"2026-08-17","festival":"CPH:DOX","first_seen":"2026-03-09","has_providers":true,"intake_pass":"C","providers":{"buy":[],"rent":["Jolt Film"],"streaming":[]},"status":"tracking","title":"An Eye for an Eye","year":2026},"1497970":{"_buyonly_preorder":true,"_discovery_source":"provider_availability_check","_transitioned_at":"2026-10-04","added":"2025-09-06T16:47:57.482408","enriched":true,"enrichment_date":"2026-10-04","has_providers":true,"premiere_date":"2025-08-02","providers":{"buy":["Apple TV Store"],"rent":[],"streaming":[]},"status":"tracking","title":"Tom and Jerry: Forbidden Compass","year":2025},"1503762":{"_discovery_source":"tmdb_type4","_jw_revert_count":1,"_jw_revert_reason":"justwatch_theatrical_pvod","_jw_reverted_at":"2026-11-13","_transitioned_at":"2026-11-13","digital_date":"2026-11-03","enriched":false,"enrichment_date":null,"has_providers":true,"intake_date":"2026-09-22","intake_pass":"B","providers":{"buy":[],"rent":[],"streaming":[]},"status":"tracking","title":"Sense and Sensibility","year":2026},"1559261":{"_buyonly_preorder":true,"_discovery_source":"provider_availability_check","_transitioned_at":"2026-11-13","enriched":true,"enrichment_date":"2026-11-13","first_seen":"2026-01-04","has_providers":true,"intake_pass":"backfill","is_slop":true,"premiere_date":"2025-06-01","providers":{"buy":[],"rent":[],"streaming":["Stingray Classica Amazon Channel"]},"status":"tracking","title":"Galaxymphony - The Final Odyssey","year":2025},"1563321":{"_discovery_source":"provider_availability_check","_is_preorder":true,"_transitioned_at":"2026-09-29","_virtual_screening":true,"digital_date":"2026-09-29","discovery_pass":"B","enriched":true,"enrichment_date":"2026-09-29","first_seen":"2025-11-10","has_providers":true,"providers":{"buy":[],"rent":["Eventive"],"streaming":[]},"status":"available","title":"His Monster","year":2025},"1578210":{"_discovery_source":"tmdb_type4","_is_preorder":true,"_jw_revert_count":1,"_jw_revert_reason":"justwatch_no_match","_jw_reverted_at":"2026-10-24","_type4_pending":true,"digital_date":"2026-11-24","discovery_pass":"B","first_seen":"2025-11-11","has_providers":false,"providers":{},"status":"tracking","title":"Run Terry Run","year":2025},"940009":{"_discovery_source":"tmdb_type4","_is_preorder":true,"_jw_revert_count":1,"_jw_revert_reason":"justwatch_no_valid_offers","_jw_reverted_at":"2026-09-25","_type4_pending":true,"digital_date":"2026-12-18","festival":"NYFF","intake_date":"2026-09-25","intake_pass":"C","providers":{},"status":"tracking","title":"Ray Gunn","year":2026}},"wall":{"1021848":{"_buyonly_preorder":true,"_digital_date_source":"detection","_discovered_at":"2026-10-31T14:16:33.364329","_discovery_source":"provider_availability_check","_enrichment_attempts":1,"_enrichment_gaps":["watch_links"],"_enrichment_status":"completed","_imdb_votes":824,"_is_preorder":true,"_last_enrichment_attempt":"2026-10-31","_minimal_entry":false,"_needs_review":false,"_reissue":false,"_slop_confidence":"weak","_slop_reason":"score:-1(good_imdb)","_tmdb_fetch_failed":false,"_trailer_source":"gemini_playwright","_wiki_language_count":6,"bootstrap_date":false,"budget":0,"country":"United Kingdom","crew":{"cast":["Juliette Binoche","Tom Courtenay","Anna Calder-Marshall","Florence Hunt","Steven Cree"],"director":"Lance Hammer"},"display_title":"Queen at Sea","featured":false,"filters":{"auto_categorized":true,"is_documentary":false,"is_foreign":false,"is_indie":true,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":false,"manual_override":null},"genres":["Drama"],"id":"1021848","imdb_rating":"7.6","keywords":["dementia","autonomy","consent"],"letterboxd_score":"3.8","links":{"cast_wiki":{"Anna Calder-Marshall":"https://en.wikipedia.org/wiki/Anna_Calder-Marshall","Juliette Binoche":"https://en.wikipedia.org/wiki/Juliette_Binoche","Tom Courtenay":"https://en.wikipedia.org/wiki/Tom_Courtenay"},"imdb":"https://www.imdb.com/title/tt27541205/","justwatch":"https://www.justwatch.com/us/movie/queen-at-sea","letterboxd":"https://letterboxd.com/film/queen-at-sea","metacritic":"https://www.metacritic.com/movie/queen-at-sea/","rt":"https://www.rottentomatoes.com/m/queen_at_sea","trailer":"https://www.youtube.com/watch?v=zOd6fouRRcc","wikipedia":"https://en.wikipedia.org/wiki/Queen_at_Sea"},"manually_corrected":false,"metacritic_score":"85","original_language":"en","original_title":"Queen at Sea","poster":"https://image.tmdb.org/t/p/w500/ueYawr1nldKchzyP8Q9KJpn31SK.jpg","pre_order_links":[{"buy_price":"$14.99","link":"https://athome.fandango.com/content/browse/details/Queen-at-Sea/5287829","price":"$14.99","service":"Fandango At Home"}],"providers":{"buy":["Fandango At Home"],"rent":[],"streaming":[]},"reissue_label":null,"rt_score":"91%","runtime":121,"status":"available","studio":"The Bureau","synopsis":"As advanced dementia erodes an older woman's ability to communicate her inner life, her husband and daughter struggle to act in her best interests, navigating love and the fragile boundaries between care, protection and autonomy.","title":"Queen at Sea","watch_links":{},"year":2026},"1195803":{"_digital_date_source":"tmdb_type4","_discovered_at":"2026-11-05T16:13:51.147613","_discovery_source":"tmdb_type4","_enrichment_attempts":1,"_enrichment_status":"completed","_imdb_votes":5109,"_is_preorder":true,"_last_enrichment_attempt":"2026-11-05","_minimal_entry":false,"_needs_review":true,"_quality_warnings":["Service 'Amazon' not in TMDB providers for this title (TMDB has: ['fandango at home'])"],"_reissue":false,"_slop_confidence":"weak","_slop_reason":"score:-1(good_imdb)","_tmdb_fetch_failed":false,"_trailer_source":"gemini_playwright","_wiki_language_count":14,"bootstrap_date":false,"budget":10000000,"country":"United States of America","crew":{"cast":["Olivia Colman","Alexander Skarsgård","Peter Dinklage","Elizabeth Debicki","Marli Siu"],"director":"Eleanor Wilson"},"digital_date":"2026-12-01","display_title":"Wicker","featured":false,"filters":{"auto_categorized":true,"is_documentary":false,"is_foreign":false,"is_indie":false,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":false,"manual_override":null},"genres":["Romance","Fantasy","Comedy"],"id":"1195803","imdb_rating":"7.4","keywords":["jealousy","based on novel or book","village","romcom","based on short story","ostracism","feudality","interspecies romance","single woman","social scandal","desperate woman","seeking love","unconventional love","absurd","romantic fantasy","fisherwoman","romantic"],"letterboxd_score":"3.7","links":{"cast_wiki":{"Alexander Skarsgård":"https://en.wikipedia.org/wiki/Alexander_Skarsg%C3%A5rd","Olivia Colman":"https://en.wikipedia.org/wiki/Olivia_Colman","Peter Dinklage":"https://en.wikipedia.org/wiki/Peter_Dinklage"},"imdb":"https://www.imdb.com/title/tt29611136/","letterboxd":"https://letterboxd.com/film/wicker","metacritic":"https://www.metacritic.com/movie/wicker/","rt":"https://www.rottentomatoes.com/m/wicker","trailer":"https://www.youtube.com/watch?v=JH25LjG7R7k","trailer_hosted":"https://f004.backblazeb2.com/file/NRW-TRAILERS/1195803.mp4","wikipedia":"https://en.wikipedia.org/wiki/Wicker_(film)"},"manually_corrected":false,"metacritic_score":"70","original_language":"en","original_title":"Wicker","poster":"https://image.tmdb.org/t/p/w500/6FcBZOKvyrLCKGCyBG0ySCR4okt.jpg","pre_order_links":[{"link":"https://www.amazon.com/gp/video/detail/B0HBM4YD96?tag=nrw04-20","service":"Amazon"}],"providers":{"buy":["Fandango At Home"],"rent":[],"streaming":[]},"reissue_label":null,"rt_score":"94%","runtime":105,"status":"available","studio":"Topic Studios","synopsis":"On the outskirts of a village by the sea, lives a Fisherwoman; smelly, single and perpetually ridiculed. One day, fed up with her stuffy, small-minded neighbours, she commissions herself a husband to be made from wicker. In an otherwise conservative town, this unconventional romance sparks outrage, jealousy and chaos.","title":"Wicker","watch_links":{"vod":[{"link":"https://www.amazon.com/gp/video/detail/B0HBM4YD96?tag=nrw04-20","service":"Amazon"}]},"year":2026},"1244523":{"_buyonly_preorder":true,"_digital_date_source":"tmdb_type4","_discovered_at":"2026-11-05T16:14:02.415462","_discovery_source":"tmdb_type4","_enrichment_attempts":8,"_enrichment_gaps":["watch_links","rt_score"],"_enrichment_status":"completed","_imdb_votes":3048,"_is_preorder":true,"_last_enrichment_attempt":"2026-11-13","_minimal_entry":false,"_needs_review":false,"_reissue":false,"_rt_last_retry":"2026-11-06T07:00:44.098058","_rt_retry_count":3,"_slop_confidence":"weak","_slop_reason":"score:5(no_rt,low_imdb,no_rt_link)","_tmdb_fetch_failed":false,"_trailer_source":"gemini_playwright","_watch_links_verified":"2026-11-13T16:43:29.139704","_wiki_language_count":5,"bootstrap_date":false,"budget":0,"country":"United States of America","crew":{"cast":["Kiana Madeira","Jessica Rothe","Will Close","Juan Pablo Shuk","Logan Marshall-Green"],"director":"Mike P. Nelson"},"digital_date":"2026-11-03","display_title":"Beware Boiúna","featured":false,"filters":{"auto_categorized":true,"is_documentary":false,"is_foreign":false,"is_indie":false,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":false,"manual_override":null},"genres":["Horror","Thriller","Action"],"id":"1244523","imdb_rating":"5.7","is_slop":true,"keywords":["animal attack","giant snake","amazon rainforest","survival","creature","survival horror","creature feature","rainforest","animal horror","humanitarian work","brazil","brazilian folklore"],"letterboxd_score":"2.8","links":{"cast_wiki":{"Jessica Rothe":"https://en.wikipedia.org/wiki/Jessica_Rothe","Kiana Madeira":"https://en.wikipedia.org/wiki/Kiana_Madeira"},"director_wiki":"https://en.wikipedia.org/wiki/Mike_P._Nelson","imdb":"https://www.imdb.com/title/tt10377864/","justwatch":"https://www.justwatch.com/us/movie/titan-2024","letterboxd":"https://letterboxd.com/film/beware-boiuna","metacritic":"https://www.metacritic.com/movie/beware-boiuna/","rt":null,"trailer":"https://www.youtube.com/watch?v=4fn4UcgzRhg","trailer_hosted":"https://f004.backblazeb2.com/file/NRW-TRAILERS/1244523.mp4","wikipedia":"https://en.wikipedia.org/wiki/Beware_Boi%C3%BAna"},"manually_corrected":false,"metacritic_score":"49","original_language":"en","original_title":"Beware Boiúna","poster":"https://image.tmdb.org/t/p/w500/uW5YMPxJUzT9bkafrCKHXjPTCoQ.jpg","pre_order_links":[{"buy_price":"$14.99","link":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.a9eb0d4b-efba-4225-a259-caaa18dda9fb&tag=nrw04-20","price":"$14.99","service":"Amazon Video"},{"buy_price":"$14.99","link":"https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6812862855","price":"$14.99","service":"Apple TV Store"},{"buy_price":"$14.99","link":"https://athome.fandango.com/content/browse/details/Beware-Boi-na/5214925","price":"$14.99","service":"Fandango At Home"}],"providers":{"buy":["Fandango At Home"],"rent":[],"streaming":[]},"reissue_label":null,"rt_score":null,"runtime":104,"status":"available","studio":"Constantin Film","synopsis":"A medical mission deep in the Amazon becomes a desperate fight for survival when a colossal ancient predator awakens, turning the jungle into a deadly battleground where nature decides who lives and dies.","title":"Beware Boiúna","watch_links":{"vod":[{"buy_price":"$14.99","link":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.a9eb0d4b-efba-4225-a259-caaa18dda9fb&tag=nrw04-20","price":"$14.99","service":"Amazon"},{"buy_price":"$14.99","link":"https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6812862855","price":"$14.99","service":"Apple TV"},{"buy_price":"$14.99","link":"https://athome.fandango.com/content/browse/details/Beware-Boi-na/5214925","price":"$14.99","service":"Fandango"}]},"year":2026},"1497970":{"_buyonly_preorder":true,"_digital_date_source":"detection","_discovered_at":"2026-10-04T04:55:54.053905","_discovery_source":"provider_availability_check","_enrichment_attempts":1,"_enrichment_gaps":["watch_links"],"_enrichment_status":"completed","_imdb_votes":1033,"_is_preorder":true,"_last_enrichment_attempt":"2026-10-04","_minimal_entry":false,"_needs_review":false,"_reissue":false,"_slop_confidence":"weak","_slop_reason":"score:2(low_imdb)","_tmdb_fetch_failed":false,"_trailer_source":"gemini_playwright","_wiki_language_count":14,"bootstrap_date":false,"budget":0,"country":"China","crew":{"cast":["John Shang","Ruan Yifei","Jiang Wen","Shun Zi","Lan Long"],"director":"Zhang Gang"},"display_title":"Tom and Jerry: Forbidden Compass","featured":false,"filters":{"auto_categorized":true,"is_documentary":false,"is_foreign":true,"is_indie":false,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":false,"manual_override":null},"genres":["Animation","Comedy","Family","Adventure","Fantasy"],"id":"1497970","imdb_rating":"3.3","keywords":["museum","time travel","cat and mouse","foreign language adaptation","anthropomorphic animal"],"letterboxd_score":"1.8","links":{"cast_wiki":{"Jiang Wen":"https://en.wikipedia.org/wiki/Jiang_Wen"},"imdb":"https://www.imdb.com/title/tt37185884/","justwatch":"https://www.justwatch.com/us/movie/tom-and-jerry-forbidden-compass","letterboxd":"https://letterboxd.com/film/tom-and-jerry-forbidden-compass","metacritic":"https://www.metacritic.com/movie/tom-and-jerry-forbidden-compass/","rt":"https://www.rottentomatoes.com/m/tom_and_jerry_forbidden_compass","trailer":"https://www.youtube.com/watch?v=lScTuXgrf4k","wikipedia":"https://en.wikipedia.org/wiki/Tom_and_Jerry:_Forbidden_Compass"},"manually_corrected":false,"metacritic_score":"24","original_language":"zh","original_title":"猫和老鼠：星盘奇缘","poster":"https://image.tmdb.org/t/p/w500/5qttWFjsO62k88civZaDMHiBTvy.jpg","pre_order_links":[{"buy_price":"$12.99","link":"https://tv.apple.com/us/movie/tom-and-jerry-forbidden-compass/umc.cmc.7clx0uqkqjiuefew4dlizh4k0?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6809456627","price":"$12.99","service":"Apple TV Store"}],"providers":{"buy":["Apple TV Store"],"rent":[],"streaming":[]},"reissue_label":null,"rt_score":"0%","runtime":99,"status":"available","studio":"Original Force Animation","synopsis":"During a chase inside a museum, Tom and Jerry find an ancient magical compass and end up being transported through time. Lost in a distant era, they will need to work together to find a way back home.","title":"Tom and Jerry: Forbidden Compass","watch_links":{"streaming":[],"vod":[]},"year":2025},"1559261":{"_buyonly_preorder":true,"_digital_date_source":"detection","_discovered_at":"2026-11-02T17:51:21.047958","_discovery_source":"provider_availability_check","_enrichment_attempts":10,"_enrichment_gaps":["watch_links","rt_score","trailer","wikipedia","imdb_rating","metacritic_score","letterboxd_score"],"_enrichment_status":"completed","_is_preorder":true,"_last_enrichment_attempt":"2026-11-13","_minimal_entry":false,"_needs_review":false,"_reissue":false,"_slop_confidence":"weak","_slop_reason":"score:6(no_wiki,no_rt,no_imdb)","_tmdb_fetch_failed":false,"_trailer_last_retry":"2026-11-09T18:52:35.710528","_trailer_retry_count":2,"bootstrap_date":false,"budget":0,"country":"DK","crew":{"cast":["Jakob Stegelmann","Sinne Eeg","Isabel Schwartzbach","Kristoffer Appel","David Bateson"],"director":"Unknown"},"display_title":"Galaxymphony - The Final Odyssey","featured":false,"filters":{"auto_categorized":true,"is_documentary":false,"is_foreign":false,"is_indie":false,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":false,"manual_override":null},"genres":["Music"],"id":"1559261","imdb_rating":null,"is_slop":true,"keywords":["concert"],"letterboxd_score":null,"links":{"cast_wiki":{"Jakob Stegelmann":"https://en.wikipedia.org/wiki/Jakob_Stegelmann"},"justwatch":"https://www.justwatch.com/us/movie/galaxymphony-the-final-odyssey","letterboxd":"https://letterboxd.com/film/galaxymphony-the-final-odyssey","rt":"https://www.rottentomatoes.com/m/ultraman_tiga_the_final_odyssey","trailer":null,"wikipedia":null},"manually_corrected":false,"original_language":"en","original_title":"Galaxymphony - The Final Odyssey","poster":"https://image.tmdb.org/t/p/w500/qIF0DwqG3HFjZ7SYDpYNhcruhqS.jpg","pre_order_links":[{"buy_price":"$34.99","link":"https://www.barnesandnoble.com/w/dvd-galaxymphony-the-final-odyssey-danish-national-symphony-orchestra/1148393344","price":"$34.99","service":"Barnes & Noble"}],"providers":{"buy":[],"rent":[],"streaming":["Stingray Classica Amazon Channel"]},"reissue_label":null,"rt_score":null,"runtime":82,"status":"available","studio":"Unknown","synopsis":"The DR Symphony Orchestra breaks the sound barrier and takes you out into the galaxies — to a place between reality and fantasy with soundtracks from Star Wars, The Mandalorian, Star Trek, Dune, and many more.  Join the orchestra on the third and final symphonic journey through musical universes and cinematic galaxies — all the way to the outermost asteroids and back to Earth again..\r 1. A New Hope  2. Raised By Wolves  3. Rebel Moon  4. Dune (1984)  5. Dune (2021)  6. Star Trek Into Darkness  7. War of the Worlds  8. Valerian and the City of a  Thousand Planets  9. Hyperspace  10. Armageddon  11. Rogue One  12. The Book of Boba Fett  13. The Empire Strikes Back  14. Return of the Jedi  15. Revenge of the Sith  16. The Mandalorian  17. The Phantom Menace","title":"Galaxymphony - The Final Odyssey","watch_links":{},"year":2025},"1563321":{"_digital_date_source":"detection","_discovered_at":"2026-09-29T14:44:09.103060","_discovery_source":"provider_availability_check","_enrichment_attempts":1,"_enrichment_gaps":["rt_score","wikipedia","metacritic_score","letterboxd_score"],"_enrichment_status":"completed","_imdb_votes":14,"_last_enrichment_attempt":"2026-09-29","_minimal_entry":false,"_needs_review":false,"_reissue":false,"_slop_confidence":"weak","_slop_reason":"score:3(no_wiki,no_rt,good_imdb)","_tmdb_fetch_failed":false,"_trailer_source":"gemini_playwright","_watch_links_verified":"2026-11-02T18:23:50.125121","bootstrap_date":false,"budget":0,"country":"United States of America","crew":{"cast":["Gabriel Casdorph","Ashley Song","Brace Evans","Meranda Long","Miette Blanche"],"director":"Erich Cannon"},"digital_date":"2026-10-06","display_title":"His Monster","featured":false,"filters":{"auto_categorized":true,"is_documentary":false,"is_foreign":false,"is_indie":false,"is_restoration":false,"is_series":false,"is_staff_pick":false,"is_virtual_screening":true,"manual_override":null},"genres":["Thriller","Mystery","Horror"],"hidden":true,"id":"1563321","imdb_rating":"8.8","keywords":["monster","supernatural creature"],"letterboxd_score":null,"links":{"imdb":"https://www.imdb.com/title/tt28595505/","letterboxd":"https://letterboxd.com/film/his-monster","rt":"https://www.rottentomatoes.com/m/his_monster","trailer":"https://www.youtube.com/watch?v=ZzbYgVfV46U","trailer_hosted":"https://f004.backblazeb2.com/file/NRW-TRAILERS/1563321.mp4","wikipedia":null},"manually_corrected":false,"original_language":"en","original_title":"His Monster","poster":"https://image.tmdb.org/t/p/w500/v6UbYmHpNrS9W6D6PhAzo4PI23P.jpg","providers":{"buy":[],"rent":[],"streaming":[]},"reissue_label":null,"rt_score":null,"runtime":87,"status":"available","studio":"Compassionate Disaster Films","synopsis":"When his young daughter is mysteriously swept out to sea, a struggling alcoholic believes it to be a monster that attacked her. James remains alone, searching the woods and finding nothing. But when people around him start dying, only he believes what it is that’s killing them.","title":"His Monster","virtual_screening_info":{"available_end":"2026-10-16","available_start":"2026-10-06","discovered":"2026-09-29","last_checked":"2026-10-16","platform":"Eventive","screening_name":"MONIFF 2026 Film Festival","screening_slug":"moniff2026","status":"expired"},"watch_links":{"streaming":[{"link":"https://www.hoopladigital.com/title/20292976?utm_source=justwatch","service":"Hoopla"}],"vod":[{"link":"https://watch.eventive.org/moniff2026/play/6abb17d4ca2f16db70432293","service":"Eventive"},{"buy_price":"$9.99","link":"https://watch.amazon.com/detail?gti=amzn1.dv.gti.46c8eda2-bc84-4cdb-b289-1a31de07d467&tag=nrw04-20","price":"$4.99","rent_price":"$4.99","service":"Amazon"},{"buy_price":"$9.99","link":"https://tv.apple.com/us/movie/his-monster/umc.cmc.6vqkn8vyzgur37grk3t6afcpn?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6805173531","price":"$4.99","rent_price":"$4.99","service":"Apple TV"},{"buy_price":"$9.99","link":"https://athome.fandango.com/content/browse/details/His-Monster/5096518","price":"$4.99","rent_price":"$4.99","service":"Fandango"}]},"year":2025}}}'''


if __name__ == '__main__' and len(sys.argv) >= 5 and sys.argv[1] == '--run-spec':
    sys.exit(_main(sys.argv))
if __name__ == '__main__' and len(sys.argv) >= 5 and sys.argv[1] == '--run-script':
    sys.exit(_main_script(sys.argv))
