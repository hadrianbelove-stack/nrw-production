"""Festival films with real store links (Nov 2026).

A festival screening link (Eventive, Sundance, Shift72) is a temporary extra. A film that is
also rentable or streaming somewhere real is a normal release: on the main wall, never hidden
when its screening ends, never dated or flagged a pre-order by the screening. The History of
Concrete sat in Fests while Amazon, Apple, Plex and Fandango rented it; Steal This Story,
Please! and His Monster were hidden when their screenings ended though Amazon had them.
"""
import logging
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.display import DisplayGenerator, is_festival_link  # noqa: E402

AMAZON = {'service': 'Amazon', 'link': 'https://watch.amazon.com/detail?gti=x', 'price': '$6.99'}
EVENTIVE = {'service': 'Eventive', 'link': 'https://watch.eventive.org/corkfilmfest/play/abc'}


class _TrackingDB:
    def load_all(self):
        return {'movies': {}}


def _display(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)   # no admin/ files: no overrides, picks or ordering
    # never rebuild the distributor lookup (network) in a test
    fake = types.ModuleType('scripts.build_distributor_lookup')
    fake.build_lookup = lambda quiet=True: None
    monkeypatch.setitem(sys.modules, 'scripts.build_distributor_lookup', fake)
    ctx = types.SimpleNamespace(logger=logging.getLogger('test'), config={},
                                storage=types.SimpleNamespace(tracking_db=_TrackingDB()))
    host = types.SimpleNamespace(watch_links_cache={},
                                 _fetch_eventive_screening_info=lambda slug: {},
                                 _fetch_eventive_play_info=lambda link: {})
    return DisplayGenerator(ctx, host)


def _film(**kw):
    m = {'id': '1', 'title': 'A Film', 'year': 2026, 'digital_date': '2026-11-03',
         'genres': ['Documentary'], 'watch_links': {'vod': [dict(EVENTIVE), dict(AMAZON)]}}
    m.update(kw)
    return m


def _run(monkeypatch, tmp_path, movie):
    out, _ = _display(monkeypatch, tmp_path).apply_admin_overrides([movie])
    return out[0]


def test_store_link_beats_festival_link(monkeypatch, tmp_path):
    m = _run(monkeypatch, tmp_path, _film(virtual_screening_info={
        'available_start': '2099-11-21', 'available_end': '2099-11-29', 'status': 'active'}))
    assert m['filters']['is_virtual_screening'] is False      # main wall, not Fests
    assert m['digital_date'] == '2026-11-03'                  # not re-dated to the screening
    assert not m.get('_is_preorder') and not m.get('hidden')
    assert any(e['service'] == 'Eventive' for e in m['watch_links']['vod'])   # still running: kept


def test_expired_festival_link_is_dropped_and_the_film_unhidden(monkeypatch, tmp_path):
    m = _run(monkeypatch, tmp_path, _film(hidden=True, virtual_screening_info={
        'available_start': '2026-10-14', 'available_end': '2026-10-20', 'status': 'expired'}))
    assert m['filters']['is_virtual_screening'] is False
    assert not m.get('hidden')
    assert [e['service'] for e in m['watch_links']['vod']] == ['Amazon']


def test_owner_reverted_film_stays_hidden(monkeypatch, tmp_path):
    m = _run(monkeypatch, tmp_path, _film(hidden=True, _enrichment_status='reverted',
                                          virtual_screening_info={'available_end': '2026-10-20',
                                                                  'status': 'expired'}))
    assert m.get('hidden') is True


def test_festival_only_film_is_still_a_festival_screening(monkeypatch, tmp_path):
    m = _run(monkeypatch, tmp_path, _film(watch_links={'vod': [dict(EVENTIVE)],
                                                       'streaming': [{'service': 'Eventive',
                                                                      'link': EVENTIVE['link']}]}))
    assert m['filters']['is_virtual_screening'] is True


@pytest.mark.parametrize('entry,expected', [
    (EVENTIVE, True), (AMAZON, False), ({'service': None, 'link': None}, False),
    ({'service': 'Sundance', 'link': 'https://festivalplayer.sundance.org/x'}, True), ('junk', False)])
def test_is_festival_link(entry, expected):
    assert is_festival_link(entry) is expected
