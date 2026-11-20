#!/usr/bin/env python3
"""
The one pre-order rule (owner, Nov 2026): every day, test the store page (Amazon first) of
every new movie before it goes on the wall. Available to rent or buy -> main wall that day.
Listed as pre-order -> not on the main wall: PRE-ORDER view only (TMDB's future date, if any,
is its display date), re-tested every night until it's available, then the main wall dated
that night. Nothing else labels or releases a pre-order.

These run the real nightly discovery loop and the real site writer in a temp folder, with
TMDB, JustWatch and the store page faked. The tracking database is an in-memory fake.
"""
import json
import os
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.generator import DataGenerator  # noqa: E402

TODAY = datetime.now().strftime('%Y-%m-%d')
AMAZON = 'https://www.amazon.com/gp/video/detail/B0TEST'
APPLE = 'https://tv.apple.com/us/movie/test/umc.cmc.test'


def _days(n):
    return (datetime.now() + timedelta(days=n)).strftime('%Y-%m-%d')


def offers(rent=False, buy=False, stream=False, cinema=False, price=None, links=(AMAZON,)):
    """A JustWatch verify_availability() result."""
    watch_links = {}
    if rent or buy:
        watch_links['vod'] = [{'service': 'Amazon' if 'amazon' in link else 'Apple TV', 'link': link}
                              for link in links]
    if stream:
        watch_links['streaming'] = [{'service': 'Netflix', 'link': 'https://www.netflix.com/title/1'}]
    return {
        'verified': True if (rent or stream) else ('buy_only' if buy else False),
        'has_rent': rent, 'has_buy': buy, 'has_streaming': stream,
        'buy_only': buy and not rent and not stream,
        'has_cinema': cinema, 'min_rent_price': price,
        'watch_links': watch_links,
        'provider_names': {'streaming': [], 'rent': [], 'buy': []},
    }


def tmdb(rent=(), buy=(), stream=()):
    """A TMDB watch/providers payload."""
    return {'results': {'US': {'rent': [{'provider_name': n} for n in rent],
                               'buy': [{'provider_name': n} for n in buy],
                               'flatrate': [{'provider_name': n} for n in stream]}}}


NO_SERVICES = {'results': {}}


def film(title, **extra):
    movie = {'title': title, 'year': 2026, 'status': 'tracking', 'providers': {}}
    movie.update(extra)
    return movie


class FakeTrackingDB:
    def __init__(self, movies):
        self.db = {'movies': movies}

    def load_all(self):
        return self.db

    def save_all(self, data, export_json=True):
        self.db = data
        return True


@pytest.fixture
def night(tmp_path, monkeypatch):
    """Run one night of discovery. Returns (tracking movies, wall entries by id, calls)."""
    monkeypatch.chdir(tmp_path)
    for d in ('backups', 'metrics', 'cache', 'overrides', 'logs'):
        (tmp_path / d).mkdir()

    def _run(movies, type4=None, providers=None, jw=None, page=None, site=None, overrides=None):
        (tmp_path / 'data.json').write_text(json.dumps({'movies': site or []}))
        cfg = {'api': {'tmdb_api_key': 'test_key', 'tmdb_max_workers': 2},
               'tracking': {'poll_all_tracking': True, 'excluded_services': []},
               'preorder_overrides': overrides or {}}
        with patch.object(DataGenerator, 'load_config', return_value=cfg):
            gen = DataGenerator()
        gen.storage.tracking_db = FakeTrackingDB(movies)
        gen.fetch_tmdb_type4_date = lambda mid: (type4 or {}).get(str(mid))
        gen.get_movie_details = lambda mid: None
        gen.get_tv_details = lambda mid: None

        calls = {'jw': [], 'page': []}

        class FakeJW:
            def verify_availability(self, title, year, **kw):
                calls['jw'].append(title)
                result = (jw or {}).get(title)
                if isinstance(result, Exception):
                    raise result
                return result

        def fake_page(jw_result, title):
            calls['page'].append(title)
            return (page or {}).get(title)

        d = gen._discoverer
        d.enrichment = None
        d._jw_client = FakeJW()
        d._check_jw_health = lambda: True
        d._fetch_providers = lambda mid, movie: ((providers or {}).get(str(mid), NO_SERVICES), [], 0)
        d._check_preorder_page = fake_page

        gen.check_tracking_movies()
        wall = {str(m['id']): m for m in json.loads((tmp_path / 'data.json').read_text())['movies']}
        return movies, wall, calls

    return _run


# --- the test itself -------------------------------------------------------------------

def test_a_rental_whose_page_says_preorder_waits_in_the_preorder_view(night):
    movies, wall, _ = night({'1': film('Rental Preorder')},
                            providers={'1': tmdb(rent=['Amazon Video'])},
                            jw={'Rental Preorder': offers(rent=True)},
                            page={'Rental Preorder': 'pre-order'})
    assert movies['1']['status'] == 'tracking'
    assert movies['1']['_rent_preorder_held'] == TODAY
    assert wall['1']['_is_preorder'] is True, 'listed only in the PRE-ORDER view'
    assert not wall['1'].get('digital_date'), 'no TMDB date: undated, not today'


def test_a_buy_only_film_whose_page_says_preorder_waits_too(night):
    movies, wall, _ = night({'1': film('Buy Preorder')},
                            providers={'1': tmdb(buy=['Amazon Video'])},
                            jw={'Buy Preorder': offers(buy=True)},
                            page={'Buy Preorder': 'pre-order'})
    assert movies['1']['status'] == 'tracking' and movies['1']['_rent_preorder_held'] == TODAY
    assert wall['1']['_is_preorder'] is True


@pytest.mark.parametrize('verdict', ['available', None])
def test_buy_only_is_buyable_main_wall_today(night, verdict):
    movies, wall, _ = night({'1': film('Buyable')},
                            providers={'1': tmdb(buy=['Amazon Video'])},
                            jw={'Buyable': offers(buy=True)},
                            page={'Buyable': verdict})
    assert movies['1']['status'] == 'available'
    assert movies['1']['digital_date'] == TODAY
    assert not wall['1'].get('_is_preorder')


def test_a_rental_is_a_rental_at_any_price_even_still_in_theaters(night):
    movies, wall, _ = night({'1': film('Pricey Rental')},
                            providers={'1': tmdb(rent=['Amazon Video'])},
                            jw={'Pricey Rental': offers(rent=True, cinema=True, price=19.99)},
                            page={'Pricey Rental': 'available'})
    assert movies['1']['status'] == 'available'
    assert not wall['1'].get('_is_preorder')


def test_streaming_is_out_without_a_page_test(night):
    movies, wall, calls = night({'1': film('Streamer')},
                                providers={'1': tmdb(stream=['Netflix'])},
                                jw={'Streamer': offers(stream=True)})
    assert movies['1']['status'] == 'available'
    assert calls['page'] == []


def test_the_manual_override_still_wins(night):
    movies, _, calls = night({'1': film('Forced')},
                             providers={'1': tmdb(rent=['Amazon Video'])},
                             jw={'Forced': offers(rent=True)},
                             page={'Forced': 'available'},
                             overrides={'1': True})
    assert movies['1']['status'] == 'tracking' and movies['1'].get('_rent_preorder_held')
    assert calls['page'] == [], 'override decides without reading the page'


# --- every night until it's out ---------------------------------------------------------

def _held(title, **extra):
    yesterday = _days(-1)
    return film(title, _rent_preorder_held=yesterday, _preorder_listed=yesterday, _is_preorder=True, **extra)


def test_a_held_preorder_is_retested_with_no_tmdb_signal_and_released_dated_that_night(night):
    site = [{'id': '1', 'title': 'Held', '_is_preorder': True, 'digital_date': '', 'status': 'available'}]
    movies, wall, calls = night({'1': _held('Held')},
                                providers={'1': NO_SERVICES},
                                jw={'Held': offers(rent=True)},
                                page={'Held': 'available'},
                                site=site)
    assert calls['jw'] == ['Held'] and calls['page'] == ['Held'], 'tested even though TMDB lists nothing'
    assert movies['1']['status'] == 'available'
    assert movies['1']['digital_date'] == TODAY
    assert '_rent_preorder_held' not in movies['1'] and '_is_preorder' not in movies['1']
    assert not wall['1'].get('_is_preorder'), 'moved to the main wall'
    assert wall['1']['digital_date'] == TODAY


def test_a_held_preorder_still_listed_as_preorder_keeps_waiting(night):
    site = [{'id': '1', 'title': 'Still Held', '_is_preorder': True, 'digital_date': ''}]
    movies, wall, _ = night({'1': _held('Still Held')},
                            jw={'Still Held': offers(rent=True)},
                            page={'Still Held': 'pre-order'},
                            site=site)
    assert movies['1']['status'] == 'tracking' and movies['1']['_rent_preorder_held'] == TODAY
    assert wall['1']['_is_preorder'] is True


def test_a_held_preorder_never_hits_the_4_check_stop(night):
    movies, _, calls = night({'1': _held('Old Hold', _jw_revert_count=9, _skip_provider_discovery=True)},
                             jw={'Old Hold': None})
    assert calls['jw'] == ['Old Hold'], 'still tested'
    assert movies['1']['status'] == 'tracking' and movies['1'].get('_rent_preorder_held')


def test_justwatch_unreachable_keeps_a_known_preorder_waiting(night):
    movies, wall, _ = night({'1': _held('Outage')},
                            providers={'1': tmdb(rent=['Amazon Video'])},
                            jw={'Outage': RuntimeError('403 Forbidden')},
                            site=[{'id': '1', 'title': 'Outage', '_is_preorder': True, 'digital_date': ''}])
    assert movies['1']['status'] == 'tracking' and movies['1'].get('_rent_preorder_held')
    assert wall['1']['_is_preorder'] is True


# --- TMDB dates are only a display date ------------------------------------------------

def test_a_future_tmdb_date_alone_puts_nothing_on_the_wall(night):
    movies, wall, calls = night({'1': film('Future Date')},
                                type4={'1': _days(20)},
                                providers={'1': NO_SERVICES})
    assert movies['1']['status'] == 'tracking'
    assert '1' not in wall
    assert calls['jw'] == []


def test_a_future_tmdb_date_is_the_display_date_of_a_confirmed_preorder(night):
    movies, wall, calls = night({'1': film('Dated Preorder')},
                                type4={'1': _days(12)},
                                providers={'1': tmdb(rent=['Amazon Video'])},
                                jw={'Dated Preorder': offers(rent=True)},
                                page={'Dated Preorder': 'pre-order'})
    assert calls['page'] == ['Dated Preorder'], 'the page made it a pre-order, not the TMDB date'
    assert movies['1']['status'] == 'tracking'
    assert wall['1']['_is_preorder'] is True and wall['1']['digital_date'] == _days(12)


def test_an_arrived_tmdb_date_still_needs_the_page_test(night):
    movies, wall, _ = night({'1': film('Date Arrived')},
                            type4={'1': TODAY},
                            jw={'Date Arrived': offers(rent=True)},
                            page={'Date Arrived': 'pre-order'})
    assert movies['1']['status'] == 'tracking', 'TMDB said today; the page says pre-order'
    assert wall['1']['_is_preorder'] is True


def test_old_labels_come_off_when_a_film_is_released(night):
    """Films labeled by the retired labelers (TMDB-date and buy-only pre-orders)."""
    site = [{'id': '1', 'title': 'Legacy', '_is_preorder': True, '_buyonly_preorder': True,
             'digital_date': '', 'pre_order_links': [{'service': 'Amazon', 'link': AMAZON}]}]
    movies, wall, _ = night({'1': film('Legacy', _type4_pending=True, _is_preorder=True, _buyonly_preorder=True)},
                            providers={'1': tmdb(buy=['Amazon Video'])},
                            jw={'Legacy': offers(buy=True)},
                            page={'Legacy': None},
                            site=site)
    assert movies['1']['status'] == 'available'
    for flag in ('_type4_pending', '_is_preorder', '_buyonly_preorder'):
        assert flag not in movies['1']
    assert not wall['1'].get('_is_preorder') and not wall['1'].get('pre_order_links')


def test_a_robot_check_or_a_disc_only_store_waits_without_a_listing(night):
    movies, wall, _ = night({'1': film('Robot Check'), '2': film('Discs Only')},
                            providers={'1': tmdb(rent=['Amazon Video']), '2': tmdb(buy=['Barnes & Noble'])},
                            jw={'Robot Check': offers(rent=True), 'Discs Only': offers(buy=True)},
                            page={'Robot Check': 'captcha', 'Discs Only': 'disc_only'})
    for mid in ('1', '2'):
        assert movies[mid]['status'] == 'tracking'
        assert not movies[mid].get('_rent_preorder_held') and not movies[mid].get('digital_date')
        assert mid not in wall


# --- the page reader: what real Amazon pages looked like on Nov 19, 2026 ---------------------

# Every Amazon page carries this in its hidden data, pre-order or not.
HIDDEN_FALSE = '{\\"offerType\\":\\"RENTAL\\",\\"price\\":null,\\"isPreorder\\":false,\\"messageType\\":null}'
HIDDEN_TRUE = '{\\"offerType\\":\\"PURCHASE\\",\\"price\\":null,\\"isPreorder\\":true,\\"messageType\\":null}'


@pytest.fixture
def reader(tmp_path, monkeypatch):
    """Run the real _check_preorder_page against a fake browser. Returns (verdict, urls loaded)."""
    def _read(hidden, visible, links=(AMAZON,)):
        seen = []

        class Page:
            def goto(self, url, **kw):
                seen.append(url)

            def wait_for_timeout(self, ms):
                pass

            def text_content(self, sel):
                return f'{visible} {hidden}'  # page code includes the hidden data

            def inner_text(self, sel):
                return visible

            def close(self):
                pass

        class Context:
            def add_init_script(self, s):
                pass

            def set_default_timeout(self, t):
                pass

            def new_page(self):
                return Page()

            def close(self):
                pass

        class Manager:
            def get_browser(self, **kw):
                return types.SimpleNamespace(new_context=lambda **k: Context())

        monkeypatch.setitem(sys.modules, 'playwright_manager',
                            types.SimpleNamespace(get_playwright_manager=lambda: Manager()))
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'backups').mkdir(exist_ok=True)
        with patch.object(DataGenerator, 'load_config', return_value={'api': {'tmdb_api_key': 'x'}}):
            gen = DataGenerator()
        return gen._discoverer._check_preorder_page(offers(rent=True, links=links), 'A Film'), seen

    return _read


def test_amazons_hidden_ispreorder_false_is_not_a_preorder(reader):
    """The bug: the bare word 'preorder' in the page code held every Amazon rental."""
    assert reader(HIDDEN_FALSE, 'Prime Video Spa Weekend Rent UHD $5.99 Buy UHD $19.99 rent or buy')[0] == 'available'
    assert reader(HIDDEN_FALSE, 'Prime Video Dear England Episodes Details')[0] is None


def test_a_visible_preorder_or_amazons_own_flag_is_a_preorder(reader):
    assert reader(HIDDEN_FALSE, 'Prime Video Pre-order UHD $24.99 Release date: December 8')[0] == 'pre-order'
    assert reader(HIDDEN_TRUE, 'Prime Video Coming soon')[0] == 'pre-order'


def test_visible_rent_or_buy_buttons_mean_out_even_with_a_preorder_elsewhere_on_the_page(reader):
    assert reader(HIDDEN_TRUE, 'Rent HD $3.99 Buy HD $14.99 More like this: Pre-order Sequel')[0] == 'available'


def test_a_robot_check_is_unreadable_not_a_preorder(reader):
    assert reader('', "Sorry, we just need to make sure you're not a robot.")[0] == 'captcha'


def test_the_reader_uses_the_amazon_link_and_skips_disc_stores(reader):
    verdict, seen = reader(HIDDEN_FALSE, 'Rent HD $3.99', links=(APPLE, AMAZON))
    assert seen == [AMAZON] and verdict == 'available'
    verdict, seen = reader(HIDDEN_FALSE, 'Add to Cart Blu-ray DVD',
                           links=('https://www.barnesandnoble.com/w/film-blu-ray/123',))
    assert verdict == 'disc_only' and seen == [], 'no page load for a disc store'
