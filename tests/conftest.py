"""Shared test settings.

The Step 1 put-back tests exercise holds, dating and enrichment with real records whose release
dates are often weeks before the harness's fixed clock. The owner's "more than 30 days old never
goes on the wall" rule (ProviderDiscoverer.PUTBACK_MAX_AGE_DAYS) is pinned on its own in
tests/test_step1_age_cutoff.py; everywhere else it is lifted so those mechanics stay tested.
Subprocess harnesses inherit the environment variable.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _putback_age_cutoff_off(request, monkeypatch):
    name = os.path.basename(str(getattr(request, 'fspath', '')))
    if name.startswith('test_step1_') and name != 'test_step1_age_cutoff.py':
        monkeypatch.setenv('NRW_PUTBACK_MAX_AGE_DAYS', '100000')
