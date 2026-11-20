"""Shared test settings.

The Step 1 put-back tests exercise holds, dating and enrichment with real records whose release
dates are often weeks before the harness's fixed clock. The owner's "more than 30 days old never
goes on the wall" rule (ProviderDiscoverer.PUTBACK_MAX_AGE_DAYS) is pinned on its own in
tests/test_step1_age_cutoff.py; everywhere else it is lifted so those mechanics stay tested.
Subprocess harnesses inherit the environment variable.
"""
import builtins
import io
import os
import sqlite3

import pytest

# The real file / database functions, captured before any test module loads. The Step 1 write
# guards patch them per test; if one ever leaks (it did, via imported helpers), every later test
# would be refused its writes -- so other tests always start from the real ones.
_REAL_IO = {(builtins, 'open'): builtins.open, (io, 'open'): io.open, (sqlite3, 'connect'): sqlite3.connect}
for _name in ('open', 'replace', 'rename', 'remove', 'unlink', 'rmdir', 'mkdir', 'makedirs', 'truncate'):
    _REAL_IO[(os, _name)] = getattr(os, _name)


@pytest.fixture(autouse=True)
def _putback_age_cutoff_off(request, monkeypatch):
    name = os.path.basename(str(getattr(request, 'fspath', '')))
    if name.startswith('test_step1_') and name != 'test_step1_age_cutoff.py':
        monkeypatch.setenv('NRW_PUTBACK_MAX_AGE_DAYS', '100000')


@pytest.fixture(autouse=True)
def _real_io_outside_step1(request):
    name = os.path.basename(str(getattr(request, 'fspath', '')))
    if not name.startswith('test_step1_'):
        for (mod, attr), real in _REAL_IO.items():
            if getattr(mod, attr) is not real:
                setattr(mod, attr, real)


@pytest.fixture(autouse=True)
def _justwatch_unpaced(monkeypatch):
    """Tests fake JustWatch: no pacing between requests, no back-off waits (pipeline/justwatch.py),
    and a fresh breaker state for every test."""
    monkeypatch.setenv('NRW_JW_MIN_INTERVAL', '0')
    monkeypatch.setenv('NRW_JW_RETRY', '0')
    try:
        from pipeline import justwatch as _jw
        _jw._PACE.update(last=0.0, refusals_in_a_row=0, paused_once=False, given_up=False)
    except Exception:
        pass
