#!/usr/bin/env python3
"""Local RT-link gap sweep — find Rotten Tomatoes pages CI missed.

WHY LOCAL: RT's search page intermittently bot-walls datacenter IPs, so CI
enrichment misses ~half its RT lookups (verified Jul 2026: ChaO's page had
been live for two months with 25 reviews when CI enriched it and found
nothing; the identical finder succeeds instantly from this Mac). Same reason
trailer hosting runs locally. Once the link is stamped, CI's nightly quote
scrape reads the reviews fine (only the search page is walled) and the cache
merge side-fill folds them in — the chain heals itself.

Runs from local_daily.sh after trailer stamping (the launchagent commits the
result like a trailer stamp). Also runnable by hand.

Rules:
  - wall films with digital_date in the last --days (default 30), no links.rt
  - _lock_rt respected (curator says: deliberately no RT — never re-search)
  - attempt cap (--max-attempts, default 3) + cooldown (--cooldown-days,
    default 2) via _rt_retry_count / _rt_last_retry on the record
  - batch cap per run (--batch, default 15)
  - writes via pipeline.json_io.json_edit (flock + atomic) — safe alongside
    open /flow curation windows and concurrent /curate sessions
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import load_env  # noqa: F401
from pipeline.json_io import json_edit


def eligible(m, window_start, today, max_attempts, cooldown_cutoff):
    dd = m.get('digital_date') or ''
    if not (window_start <= dd <= today):
        return False
    if (m.get('links') or {}).get('rt'):
        return False
    if m.get('_lock_rt'):
        return False
    if m.get('_rt_retry_count', 0) >= max_attempts:
        return False
    if (m.get('_rt_last_retry') or '') > cooldown_cutoff:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=30)
    ap.add_argument('--max-attempts', type=int, default=3)
    ap.add_argument('--cooldown-days', type=int, default=2)
    ap.add_argument('--batch', type=int, default=15)
    args = ap.parse_args()

    today = str(date.today())
    window_start = str(date.today() - timedelta(days=args.days))
    cooldown_cutoff = (datetime.now() - timedelta(days=args.cooldown_days)).isoformat()

    import json
    data = json.load(open('data.json'))
    targets = [m for m in data.get('movies', [])
               if eligible(m, window_start, today, args.max_attempts, cooldown_cutoff)]
    if not targets:
        print("RT sweep: no eligible films (all linked, locked, capped, or cooling down)")
        return 0
    targets = targets[:args.batch]
    print(f"RT sweep: {len(targets)} film(s) to search:")
    for m in targets:
        print(f"  • {m.get('title')} ({m.get('year')})")

    from gemini_scraper.rotten_tomatoes import HybridRTFinder
    finder = HybridRTFinder()

    found = {}
    tried = []
    for m in targets:
        title, year = m.get('title'), m.get('year')
        mid = str(m.get('id'))
        tried.append(mid)
        try:
            r = finder.find_rt_score(
                title, int(year),
                director=(m.get('crew') or {}).get('director'),
                original_language=m.get('original_language'),
                original_title=m.get('original_title'),
                imdb_id=(m.get('links') or {}).get('imdb', '').rstrip('/').rsplit('/', 1)[-1] or None)
        except Exception as e:
            print(f"  ✗ {title} — finder error: {type(e).__name__}: {str(e)[:150]}")
            continue
        if isinstance(r, dict) and r.get('url'):
            found[mid] = {'url': r['url'], 'score': r.get('score')}
            print(f"  ✓ {title} → {r['url']} (score: {r.get('score') or '—'})")
        else:
            print(f"  ○ {title} — no RT page found")

    # One locked write for everything: links + scores + retry bookkeeping.
    with json_edit('data.json') as d:
        for m in d.get('movies', []):
            mid = str(m.get('id'))
            if mid in found:
                m.setdefault('links', {})['rt'] = found[mid]['url']
                if found[mid]['score']:
                    m['rt_score'] = found[mid]['score']
                m.pop('_rt_retry_count', None)
                m.pop('_rt_last_retry', None)
            elif mid in tried:
                m['_rt_retry_count'] = m.get('_rt_retry_count', 0) + 1
                m['_rt_last_retry'] = datetime.now().isoformat()

    print(f"RT sweep done: {len(found)} link(s) stamped, "
          f"{len(tried) - len(found)} miss(es) marked for retry")
    return 0


if __name__ == '__main__':
    sys.exit(main())
