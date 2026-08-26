#!/usr/bin/env python3
"""One-off: regenerate factoid primers in the short paste-ready format
(plus notability + suggested_links, which come from the same Gemini call)
for films still in the capsule queue. Preserves capsules/variants/bank_size
in each cache entry; never overwrites an existing primer on failure.

    /usr/bin/python3 scripts/backfill_primers.py --dry-run
    /usr/bin/python3 scripts/backfill_primers.py --limit 1
    /usr/bin/python3 scripts/backfill_primers.py
"""
import sys
import os
import time
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)  # data.json / cache paths are relative

import load_env  # noqa: F401
from gemini_scraper import GeminiCapsuleWriter
from curate_list import capsule_queue
from write_capsule import extract_capsule_args

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# _build_context kwargs — extract_capsule_args also carries urls the
# context builder doesn't accept.
CONTEXT_KEYS = (
    'director', 'cast', 'genres', 'runtime', 'synopsis', 'rt_score',
    'imdb_rating', 'metacritic_score', 'country', 'original_language',
    'original_title', 'studio', 'is_restoration', 'is_documentary',
    'is_foreign', 'is_exploitation', 'is_indie',
)


def fetch_sources(writer, kwargs):
    """Mirror write_capsule's Phase 1 — cached sources_used is truncated
    to 200 chars, so a fresh fetch is the only usable source material."""
    title, year = kwargs['title'], kwargs['year']
    jobs = {
        'wikipedia': lambda: writer._fetch_wikipedia_summary(kwargs['wiki_url']),
        'wiki_sections': lambda: writer._fetch_wikipedia_sections(kwargs['wiki_url']),
        'letterboxd': lambda: writer._fetch_letterboxd_reactions(title, year),
        'rt_consensus': lambda: writer._fetch_rt_consensus(kwargs['rt_url']),
        'amazon': lambda: writer._fetch_amazon_synopsis(kwargs['amazon_url']),
        'imdb_trivia': lambda: writer._fetch_imdb_trivia(kwargs['imdb_url']),
    }
    sources = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(fn) for name, fn in jobs.items()}
        for name, fut in futures.items():
            try:
                sources[name] = fut.result()
            except Exception as e:
                logger.warning(f"  {name} fetch failed: {e}")
                sources[name] = {} if name == 'wiki_sections' else ''
    return sources


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true',
                    help='List targets, change nothing')
    ap.add_argument('--limit', type=int, default=0,
                    help='Stop after N films (0 = all)')
    args = ap.parse_args()

    writer = GeminiCapsuleWriter()
    targets = [m for m, needs in capsule_queue() if 'capsule' in needs]
    if args.limit:
        targets = targets[:args.limit]

    done = failed = skipped = 0
    for i, m in enumerate(targets, 1):
        title, year = m.get('title'), m.get('year')
        entry = writer.cache.get(f"{title}_{year}")
        if not isinstance(entry, dict) or not entry.get('capsules'):
            # No cached entry to upgrade — the nightly run generates these
            # fresh with the new prompt anyway.
            print(f"[{i}/{len(targets)}] skip (no cache entry): {title} ({year})")
            skipped += 1
            continue
        if entry.get('primer_refreshed_at'):
            print(f"[{i}/{len(targets)}] skip (already refreshed): {title} ({year})")
            skipped += 1
            continue
        if args.dry_run:
            print(f"[{i}/{len(targets)}] would regenerate: {title} ({year})")
            continue

        print(f"[{i}/{len(targets)}] {title} ({year})...")
        try:
            kwargs = extract_capsule_args(m)
            sources = fetch_sources(writer, kwargs)
            context = writer._build_context(
                title, year, **{k: kwargs[k] for k in CONTEXT_KEYS})
            primer, notability, slinks = writer._generate_factoid_primer(
                sources, context, title, year,
                director=kwargs['director'], cast=kwargs['cast'])
        except Exception as e:
            print(f"  FAILED ({e}) — old primer kept")
            failed += 1
            continue
        if not primer:
            print("  FAILED (empty primer) — old primer kept")
            failed += 1
            continue

        # In-place update: capsule/capsules/bank_size/verification/word_count/
        # scraped_at untouched (scraped_at drives the cache TTL).
        entry['factoid_primer'] = primer
        entry['notability'] = notability
        entry['suggested_links'] = slinks
        entry['primer_refreshed_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        writer._save_cache()  # save per film — a crash loses nothing
        bullets = primer.count('\n') + 1
        longest = max(len(b.split()) for b in primer.split('\n'))
        print(f"  done: {bullets} bullets, longest {longest} words")
        done += 1

    print(f"\nRegenerated {done}, failed {failed}, skipped {skipped} "
          f"of {len(targets)} targets")


if __name__ == '__main__':
    main()
