#!/usr/bin/env python3
"""Validate the news-title Gemini fallback (Pass F's read-the-article step).

Two modes, both hit the live API (cached afterward):
  default        canned hard cases with soft assertions (multi-film headline,
                 keyword-noise headline)
  --live N       collect the real feed, take N headlines the HEURISTICS could
                 not resolve, print Gemini's resolution for each — eyeball run

Usage:
    python3 scripts/validate_news_title.py
    python3 scripts/validate_news_title.py --live 5
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gemini_scraper.news_title import GeminiNewsTitleFinder  # noqa: E402

CANNED = [
    {
        # Multi-film headline — the first quoted phrase is a subculture, not the film.
        'headline': 'UK "suedehead" subculture film \'Bronco Bullfrog\' gets new '
                    '2K restoration, in theaters this fall',
        'source': 'Far Out Magazine',
        'expect_title_contains': 'bronco bullfrog',
        'expect_restoration': 'yes',
    },
    {
        # Keyword noise — "restoration" but not film-restoration news.
        'headline': 'City council approves $4M film restoration grant for the '
                    'historic Paramount Theatre building facade',
        'source': 'Local News',
        'expect_restoration': 'no',
    },
]


def run_canned(finder):
    passed = 0
    for case in CANNED:
        res = finder.resolve_headline(case['headline'], case.get('source', ''))
        if res is None:
            print(f"FAIL (API): {case['headline'][:60]}")
            continue
        ok = True
        if 'expect_title_contains' in case:
            ok &= case['expect_title_contains'] in (res['film_title'] or '').lower()
        if 'expect_restoration' in case:
            ok &= res['is_restoration_news'] == case['expect_restoration']
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}: {case['headline'][:60]}...")
        print(f"      -> {res['film_title']!r} ({res['film_year']}) "
              f"restoration={res['is_restoration_news']} vod={res['vod_mention']} "
              f"[{res['confidence']}] {res['basis'][:80]}")
    print(f"\ncanned: {passed}/{len(CANNED)} passed")
    return passed == len(CANNED)


def run_live(finder, n):
    from pipeline.distributors import googlenews, tmdb_match
    key = tmdb_match._tmdb_key()
    if not key:
        print("No TMDB key — cannot pre-filter with heuristics.")
        return
    by_title, _ = googlenews.collect(googlenews.CLEAN_KEYWORDS)
    shown = 0
    for it in by_title.values():
        if shown >= n:
            break
        highs = set()
        for g in it.get('guesses', [it['guess']]):
            status, payload = tmdb_match.match_title_no_year(key, g)
            if status == 'high':
                highs.add(payload['tmdb_id'])
        if len(highs) == 1:
            continue        # heuristics handled it — not fallback territory
        shown += 1
        res = finder.resolve_headline(it['headline'], it.get('source', ''), it.get('date', ''))
        print(f"\n[{shown}] {it['headline'][:90]}")
        if res is None:
            print("    -> API failed")
        else:
            print(f"    -> {res['film_title']!r} ({res['film_year']}) "
                  f"restoration={res['is_restoration_news']} vod={res['vod_mention']} "
                  f"[{res['confidence']}]")
            print(f"       {res['basis'][:120]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--live', type=int, default=0, metavar='N',
                    help='Resolve N real unresolved headlines from the live feed')
    args = ap.parse_args()
    finder = GeminiNewsTitleFinder()
    if args.live:
        run_live(finder, args.live)
    else:
        ok = run_canned(finder)
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
