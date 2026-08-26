#!/usr/bin/env python3
"""Local trailer gap sweep — find YouTube trailers CI missed.

WHY LOCAL: since the Aug 2026 Gemini master-switch-off, CI's trailer waterfall
is Playwright-only. This sweep re-runs the misses with the Claude-on-Max
backend (NRW_YOUTUBE_BACKEND=claude → local `claude -p` with WebSearch, ~$0)
plus the Playwright fallback, from this Mac. Runs from local_daily.sh BEFORE
trailer hosting, so a found trailer is downloaded, uploaded to B2, and
committed the same night by the existing stamp step.

Rules (mirrors rt_gap_sweep.py):
  - wall films with digital_date in the last --days (default 30), no
    links.trailer (a search_query placeholder counts as missing)
  - overrides/trailer_suppress.json respected (curator says: no trailer)
  - overrides/trailer_overrides.json respected (a pending override wins;
    don't burn a lookup on it)
  - attempt cap (--max-attempts, default 3) + cooldown (--cooldown-hours,
    default 20 — a miss here means Claude AND Playwright both failed, so
    retry daily, not hourly) via _trailer_retry_count / _trailer_last_retry
  - batch cap per run (--batch, default 10 — each Claude lookup is ~30-90s)
  - oEmbed title identity check before stamping (the scrapers have grabbed
    wrong-film teasers on title collisions — e.g. Marvel "Vision Quest")
  - writes via pipeline.json_io.json_edit (flock + atomic) — safe alongside
    open /flow curation windows and concurrent /curate sessions
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import load_env  # noqa: F401
from pipeline.json_io import json_edit


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _sig_words(text):
    """Significant lowercase words of a title (len>1, minus stopwords)."""
    words = re.sub(r'[^a-z0-9 ]', ' ', (text or '').lower()).split()
    return [w for w in words
            if w not in ('the', 'a', 'an', 'of', 'and', 'in', 'on', 'to') and len(w) > 1]


def _title_sane(url, title, original_title):
    """Wrong-film guard: the YouTube video's real title (via oEmbed) must share
    at least one significant word with the film's title or original title.
    Titles with no significant words (e.g. CJK, single letters) skip the check.
    A rejected film just counts as a miss (retry cap applies)."""
    try:
        import requests
        resp = requests.get(
            f"https://www.youtube.com/oembed?url={url}&format=json", timeout=10)
        video_title = (resp.json().get('title') or '').lower()
    except Exception:
        return True, ''  # oEmbed flaky — don't block on the guard itself
    if not video_title:
        return True, ''
    # Fan/recap/collision content that word-matching alone lets through
    # (Aug 2026 backfill caught: NFT project, review channels, 'Preview, Plot
    # & What to Expect' recaps, news clips about a premiere)
    for bad in ('review', 'reaction', 'explained', 'what to expect',
                'full movie', 'nft', 'premiers at', 'premieres at'):
        if bad in video_title:
            return False, video_title
    for source in (title, original_title):
        words = _sig_words(source)
        if words and any(w in video_title for w in words):
            return True, video_title
    if not _sig_words(title) and not _sig_words(original_title):
        return True, video_title
    return False, video_title


def eligible(m, window_start, today, max_attempts, cooldown_cutoff, suppress, overrides):
    dd = m.get('digital_date') or ''
    if not (window_start <= dd <= today):
        return False
    trailer = (m.get('links') or {}).get('trailer') or ''
    if trailer and 'search_query=' not in trailer:
        return False
    if str(m.get('id', '')) in suppress:
        return False
    if f"{m.get('title')}_{m.get('year')}" in overrides:
        return False
    if m.get('_trailer_retry_count', 0) >= max_attempts:
        return False
    if (m.get('_trailer_last_retry') or '') > cooldown_cutoff:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=90)  # match the 90-day wall — don't abandon on-wall films at 30d
    ap.add_argument('--max-attempts', type=int, default=3)
    ap.add_argument('--cooldown-hours', type=float, default=20)
    ap.add_argument('--batch', type=int, default=10)
    ap.add_argument('--dry-run', action='store_true',
                    help='find + report (cache still fills) but do not touch data.json')
    args = ap.parse_args()

    today = str(date.today())
    window_start = str(date.today() - timedelta(days=args.days))
    cooldown_cutoff = (datetime.now() - timedelta(hours=args.cooldown_hours)).isoformat()

    suppress = _load_json('overrides/trailer_suppress.json', {})
    overrides = _load_json('overrides/trailer_overrides.json', {})
    data = json.load(open('data.json'))
    targets = [m for m in data.get('movies', [])
               if eligible(m, window_start, today, args.max_attempts,
                           cooldown_cutoff, suppress, overrides)]
    if not targets:
        print("Trailer sweep: no eligible films (all found, suppressed, capped, or cooling down)")
        return 0
    total_eligible = len(targets)
    targets = targets[:args.batch]
    print(f"Trailer sweep: {len(targets)} of {total_eligible} eligible film(s) this run "
          f"(backend={os.environ.get('NRW_YOUTUBE_BACKEND', 'gemini')}):")
    for m in targets:
        print(f"  • {m.get('title')} ({m.get('year')})")

    from gemini_scraper.youtube import HybridYouTubeFinder
    finder = HybridYouTubeFinder()

    found = {}
    tried = []
    for m in targets:
        title, year = m.get('title'), m.get('year')
        mid = str(m.get('id'))
        tried.append(mid)
        # Clear a cached MISS (null) from both cache layers so the lookup
        # actually re-queries instead of echoing the old miss; never clobber
        # a real hit. (Same two-layer situation as rt_gap_sweep.)
        _key = f"{title}_{year}"
        _pw = finder._get_playwright_finder()
        for _c in (finder.gemini_finder.cache, getattr(_pw, 'cache', None)):
            if _c is not None and _key in _c and not _c.get(_key):
                _c.pop(_key, None)
        try:
            url = finder.find_trailer(
                title, int(year),
                director=(m.get('crew') or {}).get('director'))
        except Exception as e:
            print(f"  ✗ {title} — finder error: {type(e).__name__}: {str(e)[:150]}")
            continue
        if not url:
            print(f"  ○ {title} — no trailer found")
            continue
        ok, video_title = _title_sane(url, title, m.get('original_title'))
        if ok:
            found[mid] = url
            print(f"  ✓ {title} → {url}" + (f'  [\"{video_title}\"]' if video_title else ''))
        else:
            print(f"  ✗ {title} — rejected wrong-film match {url} [\"{video_title}\"]")

    if args.dry_run:
        print(f"Trailer sweep (dry run): {len(found)} found, "
              f"{len(tried) - len(found)} miss(es) — data.json untouched")
        return 0

    # One locked write for everything: links + retry bookkeeping.
    with json_edit('data.json') as d:
        for m in d.get('movies', []):
            mid = str(m.get('id'))
            if mid in found:
                m.setdefault('links', {})['trailer'] = found[mid]
                m.pop('_trailer_retry_count', None)
                m.pop('_trailer_last_retry', None)
            elif mid in tried:
                m['_trailer_retry_count'] = m.get('_trailer_retry_count', 0) + 1
                m['_trailer_last_retry'] = datetime.now().isoformat()

    print(f"Trailer sweep done: {len(found)} trailer(s) stamped, "
          f"{len(tried) - len(found)} miss(es) marked for retry")
    return 0


if __name__ == '__main__':
    sys.exit(main())
