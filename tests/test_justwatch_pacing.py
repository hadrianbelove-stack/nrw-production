"""JustWatch requests are paced and retried (pipeline/justwatch.py, Nov 19 2026: 523 of 623
lookups failed in CI when ~600 held films were asked about in a few minutes)."""
import logging

import pytest

from pipeline import justwatch as jw


class _Resp:
    def __init__(self, code, body=None):
        self.status_code, self._body, self.headers = code, body or {'data': {'popularTitles': {'edges': []}}}, {}
        self.text = '{}'

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f'{self.status_code}')

    def json(self):
        return self._body


class _Session:
    def __init__(self, codes):
        self.codes, self.calls = list(codes), 0

    def post(self, *a, **k):
        self.calls += 1
        return _Resp(self.codes.pop(0) if self.codes else 200)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('NRW_JW_RETRY', '1')                 # back-off on (waits patched below)
    monkeypatch.setenv('NRW_JW_MIN_INTERVAL', '0')
    slept = []
    monkeypatch.setattr(jw.time, 'sleep', lambda s: slept.append(s))
    jw._PACE.update(last=0.0, refusals_in_a_row=0, paused_once=False, given_up=False)
    c = jw.JustWatchClient(logger=logging.getLogger('t'))
    c.slept = slept
    return c


def test_a_throttled_request_is_retried_until_it_succeeds(client):
    client.session = _Session([429, 429, 200])
    assert client.search_movie('X', 2026) is None and client.last_error is None   # an answer, not an error
    assert client.session.calls == 3 and client.slept[:2] == [5, 15]


def test_a_refusal_after_every_retry_is_an_error_not_an_answer(client):
    client.session = _Session([403] * 5)
    assert client.search_movie('X', 2026) is None
    assert client.last_error and client.session.calls == 5


def test_repeated_refusals_pause_once_then_stop_asking_for_the_run(client):
    client.session = _Session([429] * 100)
    for _ in range(3):
        client.search_movie('X', 2026)
    assert 300 in client.slept and not jw._PACE['given_up']          # paused 5 minutes once
    for _ in range(3):
        client.search_movie('Y', 2026)
    assert jw._PACE['given_up']
    calls = client.session.calls
    assert client.search_movie('Z', 2026) is None and client.last_error and client.session.calls == calls
