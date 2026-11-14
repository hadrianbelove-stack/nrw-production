#!/usr/bin/env python3
"""
Regression tests for the Nov 2026 "missed releases" fixes.

Owner's rule: a film waits until you can actually rent / buy / stream it, then it
goes on the wall at that date. A wait must never become a drop.

Anchors (all verified in production data, Nov 13 2026):
  - PVOD gate blocked $19.99 rentals (Verity, Other Mommy, Heart of the Beast...)
  - 4-strike permanent skip dropped 443 films forever
  - leftover pre-order markers looped 66 films on/off the wall every run
  - buy-only films defaulted to "pre-order" (0 of 147 ever confirmed released)
  - JustWatch errors counted as "no match" strikes
Run: /usr/bin/python3 -m pytest -q tests/test_wall_holds.py
"""
import logging
import os
import sys
from datetime import datetime, timedelta
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import holds  # noqa: E402
from pipeline.justwatch import JustWatchClient  # noqa: E402
from pipeline.discoverer import ProviderDiscoverer  # noqa: E402
from pipeline.generator import DataGenerator  # noqa: E402
from pipeline.intake import _title_has_blocked_keyword  # noqa: E402

TODAY = datetime.now().strftime('%Y-%m-%d')


def _ago(days):
    return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')


# ---------------------------------------------------------------- holds.py

def test_hold_is_checked_daily_then_weekly_never_dropped():
    assert holds.due_for_check({})                                   # never held
    assert holds.due_for_check({'_jw_revert_count': 3, '_jw_last_checked': TODAY})
    weekly = {'_jw_revert_count': 4, '_jw_reverted_at': _ago(30)}
    assert holds.due_for_check(dict(weekly, _jw_last_checked=_ago(3))) is False
    assert holds.due_for_check(dict(weekly, _jw_last_checked=_ago(7))) is True
    assert holds.due_for_check(weekly) is True                       # legacy: no last check yet
    assert holds.due_for_check({'_jw_revert_count': 155, '_jw_reverted_at': _ago(400)}) is False


def test_record_hold_clears_preorder_markers_and_legacy_skip():
    rec = {'_is_preorder': True, '_type4_pending': True, '_buyonly_preorder': True,
           '_skip_provider_discovery': True, '_jw_revert_count': 2, '_jw_reverted_at': _ago(5)}
    assert holds.record_hold(rec, 'justwatch_no_match') == 3
    assert rec['_jw_revert_reason'] == 'justwatch_no_match'
    assert rec['_jw_reverted_at'] == _ago(5)                          # first-hold date is stable
    assert rec['_jw_last_checked'] == TODAY
    for k in ('_is_preorder', '_type4_pending', '_buyonly_preorder', '_skip_provider_discovery'):
        assert k not in rec


def test_date_after_hold_only_for_no_offer_holds():
    rec = {'digital_date': '2026-08-01'}
    assert holds.date_after_hold(rec, 'justwatch_no_valid_offers')
    assert rec['digital_date'] == TODAY and rec['_date_before_hold'] == '2026-08-01'
    assert rec['_digital_date_source'] == holds.JW_FIRST_VERIFIED
    pvod = {'digital_date': '2026-10-27'}                            # offers existed: keep date
    assert not holds.date_after_hold(pvod, 'justwatch_theatrical_pvod')
    assert pvod['digital_date'] == '2026-10-27'
    assert not holds.date_after_hold({'digital_date': '2026-08-01'}, None)


# ---------------------------------------------------------------- JustWatch client

def _node(title, year, tmdb=None, offers=()):
    return {'node': {'id': title, 'content': {'title': title, 'originalReleaseYear': year,
                                              'externalIds': {'tmdbId': tmdb} if tmdb else {},
                                              'credits': [], 'fullPath': '/us/movie/x'},
                     'offers': list(offers)}}


def _client():
    return JustWatchClient(logger=logging.getLogger('test'))


def test_match_tolerates_one_year_only_when_unambiguous():
    c = _client()
    want = {c._normalize_title('Colours of Time')}
    one = [_node('Colours of Time', 2025)]
    assert c._best_match(one, want, 2026, None, None) is not None     # festival vs release year
    two = [_node('Colours of Time', 2025), _node('Colours of Time', 2027)]
    assert c._best_match(two, want, 2026, None, None) is None         # ambiguous: no guess
    assert c._best_match(one, want, 2023, None, None) is None         # 3 years off: no
    assert c._best_match(one, want, None, None, None) is not None     # series with no year
    assert c._best_match([_node('Other', 2026)], want, 2026, None, None) is None


def test_tmdb_id_match_wins_and_is_in_cache_key():
    c = _client()
    calls = []

    def fake_edges(q, ot):
        calls.append(q)
        return [_node('Primetime', 2026, tmdb='111'), _node('Primetime', 2026, tmdb='222')]

    with mock.patch.object(c, '_search_edges', side_effect=fake_edges):
        a = c.search_movie('Primetime', 2026, tmdb_id='222')
        b = c.search_movie('Primetime', 2026, tmdb_id='111')
    assert a['content']['externalIds']['tmdbId'] == '222'
    assert b['content']['externalIds']['tmdbId'] == '111'               # not served from a's cache
    assert len(calls) == 2


def test_network_error_sets_last_error_not_a_no_match():
    c = _client()
    with mock.patch.object(c.session, 'post', side_effect=requests.ConnectionError('boom')):
        assert c.search_movie('Verity', 2026, tmdb_id='1283515') is None
    assert c.last_error and c.last_error.startswith('request_failed')
    with mock.patch.object(c, '_search_edges', return_value=[]):
        assert c.search_movie('Nothing Here', 2026) is None
    assert c.last_error is None                                       # genuine no-match


def test_premium_rental_in_theaters_is_verified():
    """Other Mommy: CINEMA offer + $19.99 rentals = watchable today = verified."""
    c = _client()
    offers = [
        {'monetizationType': 'CINEMA', 'presentationType': '', 'retailPrice': None,
         'standardWebURL': 'https://tickets.example/om', 'package': {'clearName': 'Fandango'}},
        {'monetizationType': 'RENT', 'presentationType': 'HD', 'retailPrice': '$19.99',
         'standardWebURL': 'https://www.amazon.com/gp/video/detail/X', 'package': {'clearName': 'Amazon Video'}},
        {'monetizationType': 'RENT', 'presentationType': 'HD', 'retailPrice': '$19.99',
         'standardWebURL': 'https://tv.apple.com/us/movie/x', 'package': {'clearName': 'Apple TV Store'}},
    ]
    node = _node('Other Mommy', 2026, tmdb='1400837', offers=offers)['node']
    with mock.patch.object(c, 'search_movie', return_value=node):
        r = c.verify_availability('Other Mommy', 2026, tmdb_id='1400837')
    assert r['verified'] is True and r['has_rent'] is True
    assert 'has_cinema' not in r and 'min_rent_price' not in r


def test_offer_dated_in_the_future_is_a_preorder_not_a_rental():
    """JustWatch's availableFromTime in the future = store pre-order: not verified."""
    c = _client()
    offers = [{'monetizationType': 'RENT', 'presentationType': 'HD', 'retailPrice': '$19.99',
               'standardWebURL': 'https://www.amazon.com/gp/video/detail/Y',
               'availableFromTime': '2099-12-01T05:00:00Z', 'package': {'clearName': 'Amazon Video'}}]
    node = _node('Street Fighter', 2026, tmdb='1153576', offers=offers)['node']
    with mock.patch.object(c, 'search_movie', return_value=node):
        r = c.verify_availability('Street Fighter', 2026, tmdb_id='1153576')
    assert r['verified'] is False and r['has_rent'] is False


# ---------------------------------------------------------------- discovery gate

class _FakeJW:
    def __init__(self, results, error=None):
        self.results = list(results)
        self.calls = 0
        self.last_error = None
        self._error = error

    def verify_availability(self, *a, **k):
        self.calls += 1
        self.last_error = self._error
        return self.results.pop(0) if self.results else None


def _discoverer(jw, details=None):
    ctx = mock.Mock()
    ctx.config = {'tracking': {'excluded_services': []}}
    ctx.logger = logging.getLogger('test')
    ctx.enrichment_service = None
    host = mock.Mock()
    host.watch_links_overrides = {}
    host.get_movie_details.return_value = details or {
        'original_title': 'Orig', 'popularity': 12.5, 'vote_count': 300,
        'credits': {'crew': [{'job': 'Director', 'name': 'Jane Doe'}]}}
    d = ProviderDiscoverer(ctx, host)
    d._jw_client = jw
    d._jw_healthy, d._jw_healthy_at = True, 1e18   # healthy, cached
    return d


def test_held_film_waits_for_weekly_check_without_calling_justwatch():
    jw = _FakeJW([])
    d = _discoverer(jw)
    rec = {'title': 'Colours of Time', 'year': 2025, '_jw_revert_count': 4,
           '_jw_reverted_at': _ago(90), '_jw_last_checked': _ago(2), '_skip_provider_discovery': True}
    assert d._verify_before_wall('1', rec) is None
    assert jw.calls == 0 and rec['_jw_revert_count'] == 4
    assert '_skip_provider_discovery' not in rec                       # legacy permanent skip retired


def test_legacy_skipped_film_is_checked_again_keeps_date_flagged_for_review():
    """Unchecked for months: we can't tell when it arrived — keep its date, flag it."""
    ok = {'verified': True, 'match_confidence': 'tmdb_id', 'watch_links': {}}
    jw = _FakeJW([ok])
    d = _discoverer(jw)
    rec = {'title': 'Colours of Time', 'year': 2025, 'digital_date': '2026-08-06',
           '_jw_revert_count': 4, '_jw_revert_reason': 'justwatch_no_valid_offers',
           '_jw_reverted_at': '2026-08-07', '_skip_provider_discovery': True}
    assert d._verify_before_wall('1', rec) is ok
    assert rec['digital_date'] == '2026-08-06' and rec['_date_needs_review'] is True
    assert rec['_held_since'] == '2026-08-07'
    assert '_jw_revert_count' not in rec and '_skip_provider_discovery' not in rec


def test_recently_checked_film_lands_dated_the_day_justwatch_confirmed_it():
    ok = {'verified': True, 'match_confidence': 'exact_year', 'watch_links': {}}
    d = _discoverer(_FakeJW([ok]))
    rec = {'title': 'Spa Weekend', 'year': 2026, 'digital_date': _ago(20),
           '_jw_revert_count': 5, '_jw_revert_reason': 'justwatch_no_valid_offers',
           '_jw_reverted_at': _ago(20), '_jw_last_checked': _ago(7)}
    assert d._verify_before_wall('1', rec) is ok
    assert rec['digital_date'] == TODAY and rec['_digital_date_source'] == holds.JW_FIRST_VERIFIED
    assert rec['_date_before_hold'] == _ago(20) and '_date_needs_review' not in rec


def test_justwatch_error_is_not_a_strike():
    jw = _FakeJW([None], error='request_failed: ConnectionError')
    d = _discoverer(jw)
    rec = {'title': 'Verity', 'year': 2026, '_jw_revert_count': 1, '_jw_reverted_at': _ago(1)}
    assert d._verify_before_wall('1283515', rec) is None
    assert rec['_jw_revert_count'] == 1 and '_jw_last_checked' not in rec


def test_no_match_retries_with_tmdb_metadata_then_records_a_hold():
    jw = _FakeJW([None, None])
    d = _discoverer(jw)
    rec = {'title': 'Livestream from Hell', 'year': 2026}
    assert d._verify_before_wall('9', rec) is None
    assert jw.calls == 2                                                # retried once
    assert rec['original_title'] == 'Orig' and rec['_director'] == 'Jane Doe'
    assert rec['_tmdb_votes'] == 300                                     # ranks the Held back list
    assert rec['_jw_revert_count'] == 1 and rec['_jw_last_checked'] == TODAY


def test_preorder_bypass_skipped_once_a_film_has_holds():
    jw = _FakeJW([None])
    d = _discoverer(jw)
    fresh = {'title': 'X', '_is_preorder': True}
    assert d._verify_before_wall('1', fresh)['_bypass'] == 'preorder_graduation'
    looping = {'title': 'The Last Light', '_is_preorder': True, '_jw_revert_count': 155,
               '_jw_reverted_at': _ago(140)}
    assert d._verify_before_wall('1684243', looping) is None            # real check, not a bypass
    assert jw.calls == 2                                                # check + metadata retry
    assert '_is_preorder' not in looping and looping['_jw_revert_count'] == 156


# ---------------------------------------------------------------- buy-only pre-orders

def _bo_discoverer(page_verdict, type4=None):
    d = _discoverer(_FakeJW([]))
    d.host.fetch_tmdb_type4_date.return_value = type4
    d._check_preorder_page = mock.Mock(return_value=page_verdict)
    return d


def test_buy_only_is_released_unless_page_says_preorder():
    assert _bo_discoverer(None)._detect_buyonly_preorder({}, '1', 'T')['is_preorder'] is False
    assert _bo_discoverer('available')._detect_buyonly_preorder({}, '1', 'T')['is_preorder'] is False
    assert _bo_discoverer('pre-order')._detect_buyonly_preorder({}, '1', 'T')['is_preorder'] is True
    future = (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d')
    assert _bo_discoverer(None, type4=future)._detect_buyonly_preorder({}, '1', 'T')['is_preorder'] is True


# ---------------------------------------------------------------- transitions / screenings / intake

def test_transition_clears_preorder_marker_once_date_arrived():
    fake = mock.Mock()
    rec = {'digital_date': _ago(1), '_is_preorder': True, '_type4_pending': True}
    DataGenerator._transition_movie_to_available(fake, '1', rec, 'tmdb_type4', [])
    assert '_is_preorder' not in rec and rec['status'] == 'available'
    future = {'digital_date': (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d'), '_is_preorder': True}
    DataGenerator._transition_movie_to_available(fake, '2', future, 'tmdb_type4', [])
    assert future['_is_preorder'] is True


def test_expired_screening_returns_to_tracking_without_vs_bypass():
    rec = {'status': 'available', 'digital_date': '2026-10-14', '_virtual_screening': True,
           'providers': {'streaming': [], 'rent': ['Eventive'], 'buy': []}}
    DataGenerator._return_screening_to_tracking(rec)
    assert rec['status'] == 'tracking' and 'digital_date' not in rec
    assert '_virtual_screening' not in rec and rec['providers']['rent'] == []


def test_intake_keyword_block_is_whole_word():
    kws = ['ROH', 'WWE', 'HOG:']
    assert not _title_has_blocked_keyword('Prohibition', kws)
    assert not _title_has_blocked_keyword('Rohingya', kws)
    assert _title_has_blocked_keyword('ROH Final Battle', kws)
    assert _title_has_blocked_keyword('HOG: Bloodsport', kws)
