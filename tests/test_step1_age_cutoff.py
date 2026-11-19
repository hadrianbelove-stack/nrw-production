"""The owner's age rule for put-backs (Nov 2026): "don't worry about anything more than 30 days old,
and the more recent ones on their actual release dates" -- and no trickle: every confirmed put-back
lands the same run.

A held film confirmed out (or a buy-only film the pre-order labeler finds out, dated by its first
offer) whose real release date is more than PUTBACK_MAX_AGE_DAYS (30) days ago becomes 'available' in
tracking but is NOT added to the wall; a recent one goes on the wall dated that day. An ordinary new
release (dated today) is unaffected.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_step1_holds_and_dates as h  # noqa: E402,F401  (pins the worktree on sys.path)
from pipeline import putback  # noqa: E402
from pipeline.discoverer import ProviderDiscoverer  # noqa: E402


class _Host:
    def __init__(self):
        self.calls = []

    def _transition_movie_to_available(self, movie_id, movie, source, newly_available_ids, add_to_site=True):
        movie['status'] = 'available'
        self.calls.append((movie_id, movie.get('digital_date'), add_to_site))
        if add_to_site:
            newly_available_ids.append(movie_id)


def _disc():
    d = ProviderDiscoverer.__new__(ProviderDiscoverer)
    d.host, d._pending_putbacks, d._backlog_putbacks = _Host(), {}, 0
    return d


def _ago(n):
    return (datetime.now() - timedelta(days=n)).strftime('%Y-%m-%d')


@pytest.fixture(autouse=True)
def _real_cutoff(monkeypatch):
    monkeypatch.delenv('NRW_PUTBACK_MAX_AGE_DAYS', raising=False)


@pytest.mark.parametrize('age, on_wall', [(45, False), (31, False), (30, True), (12, True), (0, True)])
def test_a_put_back_goes_on_the_wall_only_if_it_came_out_in_the_last_30_days(age, on_wall):
    d = _disc()
    movie = {'title': 'A Held Film', 'status': 'tracking', 'digital_date': None}
    d._pending_putbacks['1'] = {'day': _ago(age), 'source': putback.FIRST_OFFER, 'backlog': False, 'review': False,
                                'held_since': _ago(90)}
    ids = []
    d._transition('1', movie, 'provider_availability_check', ids)
    assert d.host.calls == [('1', _ago(age), on_wall)]
    assert movie['digital_date'] == _ago(age), 'dated its actual release day either way'
    assert (ids == ['1']) is on_wall


def test_a_buy_only_film_dated_by_its_first_offer_follows_the_same_rule():
    d = _disc()
    movie = {'title': 'Olmo', 'status': 'tracking', 'digital_date': _ago(102), '_dated_by_first_offer': True}
    d._transition('2', movie, 'provider_availability_check', [])
    assert d.host.calls == [('2', _ago(102), False)]


def test_an_ordinary_new_release_is_unaffected():
    d = _disc()
    movie = {'title': 'New Today', 'status': 'tracking', 'digital_date': _ago(0)}
    d._transition('3', movie, 'provider_availability_check', [])
    assert d.host.calls == [('3', _ago(0), True)]


def test_no_trickle_every_confirmed_put_back_lands_the_same_run():
    assert ProviderDiscoverer.MAX_BACKLOG_PUTBACKS_PER_RUN >= 10 ** 5
    assert ProviderDiscoverer.PUTBACK_MAX_AGE_DAYS == 30
