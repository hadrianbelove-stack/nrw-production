#!/usr/bin/env python3
"""
Test suite for pipeline/provider_names.py — the canonical watch-links
normalization boundary — plus the duplicate-service guard in validation.py.

Regression anchor: JustWatch lists ad tiers as separate offers
("Netflix" + "Netflix Standard with Ads", same URL). Deduping on RAW names
let both through; simplification then collapsed both to "Netflix" and the
site showed two identical Netflix buttons (Jul 2026).
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.provider_names import simplify_provider_name, normalize_watch_links
from pipeline.validation import ValidationService

GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

failures = []


def check(name, passed, details=""):
    status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"{status} - {name}")
    if details and not passed:
        print(f"      {details}")
    if not passed:
        failures.append(name)


def test_simplify():
    print("\n=== simplify_provider_name ===")
    cases = [
        ('Netflix Standard with Ads', 'Netflix'),
        ('Netflix Basic with Ads', 'Netflix'),
        ('Netflix', 'Netflix'),
        ('Amazon Prime Video with Ads', 'Amazon Prime Video'),
        ('Amazon Video', 'Amazon'),
        ('Shudder Amazon Channel', 'Shudder'),
        ('AMC Plus Apple TV Channel', 'AMC+'),
        ('DocuramaFilms Amazon Channel', 'DocuramaFilms'),
        ('Fawesome', 'Fawesome'),          # unknown name passes through
        ('Fawesome with Ads', 'Fawesome'),  # tier strip is table-independent
        ('Paramount+ with Showtime', 'Paramount+'),  # bundle: via table, not tier strip
        ('', ''),
        (None, None),
    ]
    for raw, want in cases:
        got = simplify_provider_name(raw)
        check(f"simplify {raw!r} -> {want!r}", got == want, f"got {got!r}")


def test_normalize_two_tier_netflix():
    print("\n=== normalize: the two-tier Netflix bug input ===")
    url = 'https://www.netflix.com/title/81605886'
    result = normalize_watch_links({'streaming': [
        {'service': 'Netflix', 'link': url},
        {'service': 'Netflix Standard with Ads', 'link': url},
    ]})
    check("one Netflix entry survives", result['streaming'] == [{'service': 'Netflix', 'link': url}],
          f"got {result['streaming']}")


def test_normalize_keep_first_prices():
    print("\n=== normalize: keep-first preserves VOD merged prices ===")
    result = normalize_watch_links({'vod': [
        {'service': 'Amazon Video', 'link': 'https://a', 'rent_price': '$4.99', 'buy_price': '$9.99'},
        {'service': 'Amazon', 'link': 'https://b'},  # same simplified name, later -> dropped
        {'service': 'Apple TV', 'link': 'https://c', 'buy_price': '$12.99'},
    ]})
    check("first Amazon entry (with prices) wins",
          result['vod'][0] == {'service': 'Amazon', 'link': 'https://a',
                               'rent_price': '$4.99', 'buy_price': '$9.99'},
          f"got {result['vod'][0]}")
    check("Apple TV entry intact",
          result['vod'][1] == {'service': 'Apple TV', 'link': 'https://c', 'buy_price': '$12.99'},
          f"got {result['vod'][1]}")


def test_normalize_shapes_and_fields():
    print("\n=== normalize: shape coercion + field whitelist ===")
    result = normalize_watch_links({'streaming': {'service': 'Tubi TV', 'link': 'https://t'}})
    check("legacy dict coerced to one-element list",
          result['streaming'] == [{'service': 'Tubi TV', 'link': 'https://t'}],
          f"got {result['streaming']}")

    result = normalize_watch_links({'streaming': [
        {'service': 'Netflix', 'link': 'https://n', '_ptype': 'HD'},
    ]})
    check("internal fields (_ptype) dropped", '_ptype' not in result['streaming'][0],
          f"got {result['streaming'][0]}")

    result = normalize_watch_links({
        'streaming': [{'service': 'Amazon Prime Video', 'link': 'https://s'}],
        'vod': [{'service': 'Amazon Video', 'link': 'https://v'}],
    })
    check("no cross-category collapse (Prime streaming vs Amazon VOD)",
          len(result['streaming']) == 1 and len(result['vod']) == 1,
          f"got {result}")

    check("non-dict input passes through", normalize_watch_links(None) is None)
    result = normalize_watch_links({'streaming': [{'service': None, 'link': 'https://x'}, 'garbage']})
    check("service-less + non-dict entries pass through untouched",
          result['streaming'][1] == 'garbage' and result['streaming'][0]['service'] is None,
          f"got {result['streaming']}")


def test_normalize_link_backfill():
    print("\n=== normalize: link-less first entry never shadows a real link ===")
    url = 'https://www.netflix.com/title/81605886'
    result = normalize_watch_links({'streaming': [
        {'service': 'Netflix', 'link': None},
        {'service': 'Netflix Standard with Ads', 'link': url},
    ]})
    check("one entry, real link backfilled",
          result['streaming'] == [{'service': 'Netflix', 'link': url}],
          f"got {result['streaming']}")

    # display-cache poisoned-row shape (31 live cache rows like this)
    result = normalize_watch_links({'streaming': [
        {'service': 'Amazon Prime Video', 'link': None},
        {'service': 'Amazon Prime Video with Ads', 'link': None},
    ]})
    check("poisoned cache row collapses to one entry",
          len(result['streaming']) == 1, f"got {result['streaming']}")


class _WarnCounter(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_validation_guard():
    print("\n=== validation guard: warn-only, at the data.json boundary ===")
    url = 'https://www.netflix.com/title/81605886'

    # 1. validate_watch_links_schema must NOT strip pre-normalize tier
    #    variants (it runs inside the waterfall, before normalize)
    logging.disable(logging.WARNING)
    validator = ValidationService(logger=logging.getLogger('test.schema'))
    validated = validator.validate_watch_links_schema({'streaming': [
        {'service': 'Netflix', 'link': url},
        {'service': 'Netflix Standard with Ads', 'link': url},
    ]}, 'Test Movie')
    logging.disable(logging.NOTSET)
    check("schema validator passes tier variants through (pre-normalize stage)",
          len(validated['streaming']) == 2, f"got {validated['streaming']}")

    # 2. _warn_duplicate_services warns on a movie whose data.json record
    #    holds two entries collapsing to one simplified name
    logger = logging.getLogger('test.guard')
    logger.propagate = False
    counter = _WarnCounter()
    logger.addHandler(counter)
    guard = ValidationService(logger=logger)
    guard._warn_duplicate_services({'id': 1, 'title': 'Dup Movie', 'watch_links': {
        'streaming': [{'service': 'Netflix', 'link': url},
                      {'service': 'Netflix Standard with Ads', 'link': url}],
    }})
    check("guard warns on duplicate simplified service",
          len(counter.messages) == 1 and 'DUPLICATE' in counter.messages[0],
          f"messages: {counter.messages}")

    counter.messages.clear()
    guard._warn_duplicate_services({'id': 2, 'title': 'Clean Movie', 'watch_links': {
        'streaming': [{'service': 'Netflix', 'link': url}],
        'vod': [{'service': 'Amazon', 'link': 'https://a'}, {'service': 'Apple TV', 'link': 'https://b'}],
    }})
    check("guard silent on clean movie", counter.messages == [], f"messages: {counter.messages}")

    counter.messages.clear()
    guard._warn_duplicate_services({'id': 3, 'title': 'Legacy Dict', 'watch_links': {
        'streaming': {'service': 'Tubi TV', 'link': 'https://t'},
    }})
    check("guard tolerates legacy dict shape", counter.messages == [], f"messages: {counter.messages}")


if __name__ == '__main__':
    test_simplify()
    test_normalize_two_tier_netflix()
    test_normalize_keep_first_prices()
    test_normalize_shapes_and_fields()
    test_normalize_link_backfill()
    test_validation_guard()
    print(f"\n{'='*60}")
    if failures:
        print(f"{RED}{len(failures)} FAILURE(S):{RESET} {failures}")
        sys.exit(1)
    print(f"{GREEN}ALL TESTS PASSED{RESET}")
