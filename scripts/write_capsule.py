#!/usr/bin/env python3
"""
Capsule Writer CLI — generate and approve editorial movie descriptions.

Generate a capsule:
    python3 scripts/write_capsule.py "The Brutalist"
    python3 scripts/write_capsule.py "The Brutalist" --show-sources
    python3 scripts/write_capsule.py "The Brutalist" --force --skip-verify

Approve a capsule (adds to training bank):
    python3 scripts/write_capsule.py approve "The Brutalist"
    python3 scripts/write_capsule.py approve "The Brutalist" --file rewrite.txt

Batch generate:
    python3 scripts/write_capsule.py --batch
    python3 scripts/write_capsule.py --batch --limit 10 --skip-verify

Show training bank:
    python3 scripts/write_capsule.py bank
"""

import sys
import os
import json
import argparse
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import load_env
from gemini_scraper import GeminiCapsuleWriter

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def load_movies():
    """Load movies from data.json."""
    try:
        with open('data.json', 'r') as f:
            data = json.load(f)
        if isinstance(data, dict) and 'movies' in data:
            return data['movies']
        elif isinstance(data, list):
            return data
    except Exception as e:
        logger.error(f"Could not load data.json: {e}")
    return []


def find_movie(movies, query):
    """Find a movie by title (case-insensitive, partial match)."""
    query_lower = query.lower()

    # Exact match first
    for m in movies:
        if m.get('title', '').lower() == query_lower:
            return m

    # Partial match
    matches = [m for m in movies if query_lower in m.get('title', '').lower()]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        logger.info(f"Multiple matches for '{query}':")
        for m in matches[:10]:
            logger.info(f"  - {m['title']} ({m.get('year', '?')})")
        logger.info("Be more specific.")
        return None
    else:
        logger.error(f"No movie found matching '{query}'")
        return None


def extract_capsule_args(movie):
    """Extract capsule writer arguments from a data.json movie entry."""
    import re as _re
    crew = movie.get('crew', {}) or {}
    cats = movie.get('categories', {}) or {}
    links = movie.get('links', {}) or {}

    # Derive Amazon product page URL from watch_links if available
    amazon_url = ''
    watch_links = movie.get('watch_links', {}) or {}
    for vod in (watch_links.get('vod') or []):
        if vod.get('service') == 'Amazon' and vod.get('link'):
            gti_match = _re.search(r'gti=([^&]+)', vod['link'])
            if gti_match:
                amazon_url = f"https://www.amazon.com/gp/video/detail/{gti_match.group(1)}"
            break

    return {
        'title': movie.get('title', ''),
        'year': movie.get('year', 0),
        'director': crew.get('director') if isinstance(crew, dict) else None,
        'cast': crew.get('cast') if isinstance(crew, dict) else None,
        'genres': movie.get('genres'),
        'runtime': movie.get('runtime'),
        'synopsis': movie.get('synopsis'),
        'rt_score': movie.get('rt_score'),
        'imdb_rating': movie.get('imdb_rating'),
        'metacritic_score': movie.get('metacritic_score'),
        'country': movie.get('country'),
        'original_language': movie.get('original_language'),
        'original_title': movie.get('original_title'),
        'studio': movie.get('studio'),
        'is_restoration': cats.get('is_restoration', False),
        'is_documentary': cats.get('is_documentary', False),
        'is_foreign': cats.get('is_foreign', False),
        'is_exploitation': cats.get('is_exploitation', False),
        'is_indie': cats.get('is_indie', False),
        'wiki_url': links.get('wikipedia', ''),
        'rt_url': links.get('rt', ''),
        'mc_url': links.get('metacritic', ''),
        'amazon_url': amazon_url,
        'imdb_url': links.get('imdb', ''),
    }


def print_capsule_result(result, movie, show_sources=False):
    """Pretty-print a capsule result (single or multi-variant)."""
    title = movie.get('title', '?')
    year = movie.get('year', '?')
    crew = movie.get('crew', {}) or {}
    director = crew.get('director', 'Unknown') if isinstance(crew, dict) else 'Unknown'

    print(f"\n{'='*60}")
    print(f"{title} ({year}) — {director}")
    print(f"{'='*60}\n")

    if show_sources:
        sources = result.get('sources_used', {})
        if sources.get('wikipedia'):
            print(f"WIKIPEDIA INTRO:\n{sources['wikipedia'][:500]}\n")

        wiki_sections = sources.get('wiki_sections', {})
        if wiki_sections:
            for key in ['production', 'development', 'filming', 'reception', 'cast']:
                if wiki_sections.get(key):
                    print(f"WIKIPEDIA — {key.upper()}:\n{wiki_sections[key][:500]}\n")
            quotes = wiki_sections.get('quotes', [])
            if quotes:
                print("QUOTES:")
                for q in quotes:
                    print(f'  "{q}"')
                print()

        if sources.get('rt_consensus'):
            print(f"RT CONSENSUS:\n{sources['rt_consensus']}\n")
        if sources.get('mc_summary'):
            print(f"METACRITIC:\n{sources['mc_summary']}\n")
        if any(v for v in sources.values() if v):
            print(f"{'- '*30}\n")

    capsules = result.get('capsules', [result['capsule']])

    if len(capsules) > 1:
        for i, cap in enumerate(capsules, 1):
            print(f"--- VARIANT {i} ({len(cap.split())} words) ---\n")
            print(cap)
            print()
    else:
        print(result['capsule'])
        print(f"\n({len(result['capsule'].split())} words)")

    # Factoid primer
    factoid_primer = result.get('factoid_primer', '')
    if factoid_primer:
        print(f"{'- '*30}")
        print("FACTOID PRIMER:")
        print(factoid_primer)

    # Suggested Wikipedia links (pre-verified overnight — no live searching)
    suggested_links = result.get('suggested_links', [])
    if suggested_links:
        print(f"{'- '*30}")
        print("SUGGESTED LINKS:")
        for i, link in enumerate(suggested_links, 1):
            desc = f" — {link['wiki_description']}" if link.get('wiki_description') else ""
            print(f"  {i}. [{link['name']}]({link['url']}){desc}")

    # Show verification
    verification = result.get('verification', [])
    if verification:
        print(f"{'- '*30}")
        print("FACT CHECK:")
        for v in verification:
            status_icon = {
                'VERIFIED': '+',
                'UNVERIFIABLE': '?',
                'CONTRADICTED': '!'
            }.get(v['status'], '?')
            print(f"  [{status_icon}] {v['claim']}")
            if v['status'] != 'VERIFIED':
                print(f"      {v['status']} — {v['source']}")

    print(f"\n{'='*60}\n")


def cmd_generate(args):
    """Generate a capsule for a single movie."""
    movies = load_movies()
    if not movies:
        return

    movie = find_movie(movies, args.title)
    if not movie:
        return

    writer = GeminiCapsuleWriter()
    kwargs = extract_capsule_args(movie)
    kwargs['force'] = args.force
    kwargs['skip_verify'] = args.skip_verify
    kwargs['variants'] = args.variants

    title = kwargs['title']
    year = kwargs['year']
    variant_str = f" ({args.variants} variants)" if args.variants > 1 else ""
    logger.info(f"Writing capsule for: {title} ({year}){variant_str}...")

    result = writer.write_capsule(**kwargs)

    if result:
        print_capsule_result(result, movie, show_sources=args.show_sources)
    else:
        logger.error("Failed to generate capsule.")


def cmd_batch(args):
    """Batch generate capsules for all movies."""
    movies = load_movies()
    if not movies:
        return

    # Sort by most recent digital_date
    movies.sort(key=lambda m: m.get('digital_date', '') or '', reverse=True)

    # Optional window: only process films whose digital_date is within --days
    # of today (matches the /curate 7-day window — no need to capsule the whole wall).
    from_date = None
    if args.days:
        from datetime import date, timedelta
        from_date = str(date.today() - timedelta(days=args.days))
        today = str(date.today())

    writer = GeminiCapsuleWriter()

    to_process = []
    for m in movies:
        title = m.get('title', '')
        year = m.get('year', 0)
        if not title or not year:
            continue

        if from_date is not None:
            dd = m.get('digital_date', '') or ''
            if not (from_date <= dd <= today):
                continue

        cache_key = f"{title}_{year}"

        # Skip if already cached (unless --force)
        if not args.force and cache_key in writer.cache:
            cached = writer.cache[cache_key]
            if isinstance(cached, dict) and cached.get('capsule'):
                continue

        to_process.append(m)
        if args.limit and len(to_process) >= args.limit:
            break

    if not to_process:
        logger.info("No movies to process (all cached). Use --force to re-generate.")
        return

    print(f"\n{'='*60}")
    print(f"Batch Capsule Writer — {len(to_process)} movies")
    print(f"{'='*60}\n")

    from datetime import datetime
    review_file = 'cache/capsule_review.txt'
    review_lines = [
        f"CAPSULE REVIEW — Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"{'='*70}\n\n"
    ]

    stats = {'written': 0, 'failed': 0}
    failures = []  # [{title, year, reason}] — surfaced in the morning report

    for i, movie in enumerate(to_process, 1):
        kwargs = extract_capsule_args(movie)
        kwargs['force'] = args.force
        kwargs['skip_verify'] = args.skip_verify
        kwargs['variants'] = args.variants
        title = kwargs['title']
        year = kwargs['year']

        logger.info(f"[{i}/{len(to_process)}] {title} ({year})...")

        try:
            result = writer.write_capsule(**kwargs)

            if result:
                stats['written'] += 1
                capsule = result['capsule']
                logger.info(f"  -> {len(capsule.split())} words")

                director = kwargs.get('director', 'Unknown')
                review_lines.append(f"{title} ({year}) -- {director}\n")
                review_lines.append(f"{capsule}\n")

                # Add verification summary
                verification = result.get('verification', [])
                if verification:
                    unverified = [v for v in verification if v['status'] != 'VERIFIED']
                    if unverified:
                        review_lines.append(f"  [!] {len(unverified)} unverified claim(s)\n")

                review_lines.append(f"\n---\n\n")
            else:
                stats['failed'] += 1
                failures.append({'title': title, 'year': year,
                                 'reason': 'no capsule produced (empty/verification)'})
                logger.info(f"  -> FAILED")

        except Exception as e:
            stats['failed'] += 1
            failures.append({'title': title, 'year': year, 'reason': str(e)})
            logger.error(f"  -> Error: {e}")

    # Write review file
    os.makedirs(os.path.dirname(review_file) or '.', exist_ok=True)
    with open(review_file, 'w') as f:
        f.writelines(review_lines)

    # Persist a run metric so the morning report can surface failures (only when
    # there are any). metrics/ is committed by CI and pulled to the local Mac.
    from datetime import datetime
    os.makedirs('metrics', exist_ok=True)
    with open('metrics/capsule_run.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'written': stats['written'],
            'failed': stats['failed'],
            'failures': failures,
        }, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Done! Written: {stats['written']}, Failed: {stats['failed']}")
    print(f"Review file: {review_file}")
    print(f"{'='*60}\n")


def cmd_approve(args):
    """Approve a capsule (original or rewritten) into the training bank."""
    movies = load_movies()
    if not movies:
        return

    movie = find_movie(movies, args.title)
    if not movie:
        return

    title = movie['title']
    year = movie.get('year', 0)
    crew = movie.get('crew', {}) or {}
    director = crew.get('director', 'Unknown') if isinstance(crew, dict) else 'Unknown'

    writer = GeminiCapsuleWriter()

    if args.file:
        # Read rewritten capsule from file
        try:
            with open(args.file, 'r') as f:
                capsule_text = f.read().strip()
            if not capsule_text:
                logger.error(f"File {args.file} is empty.")
                return
            logger.info(f"Read rewritten capsule from {args.file}")
        except FileNotFoundError:
            logger.error(f"File not found: {args.file}")
            return
    else:
        # Approve the cached capsule as-is
        cache_key = f"{title}_{year}"
        if cache_key not in writer.cache:
            logger.error(f"No cached capsule for {title} ({year}). Generate one first.")
            return
        cached = writer.cache[cache_key]
        capsule_text = cached.get('capsule', '')
        if not capsule_text:
            logger.error(f"Cached capsule is empty for {title} ({year}).")
            return

    writer.approve_capsule(title, year, capsule_text, director=director)

    print(f"\n{'='*60}")
    print(f"APPROVED: {title} ({year})")
    print(f"{'='*60}")
    print(f"\n{capsule_text}\n")

    bank = writer._load_approved_bank()
    print(f"Training bank now has {len(bank)} approved capsule(s).")
    print(f"{'='*60}\n")


def cmd_bank(args):
    """Show the contents of the approved capsule bank."""
    bank_path = 'admin/approved_capsules.json'
    if not os.path.exists(bank_path):
        print("No approved capsules yet. Generate and approve some first.")
        return

    try:
        with open(bank_path, 'r') as f:
            bank = json.load(f)
    except Exception as e:
        logger.error(f"Could not load bank: {e}")
        return

    if not bank:
        print("Approved capsule bank is empty.")
        return

    print(f"\n{'='*60}")
    print(f"APPROVED CAPSULE BANK — {len(bank)} entries")
    print(f"{'='*60}\n")

    for entry in bank:
        title = entry.get('title', '?')
        year = entry.get('year', '?')
        director = entry.get('director', 'Unknown')
        capsule = entry.get('capsule', '')
        approved_at = entry.get('approved_at', '?')

        print(f"{title} ({year}) -- {director}")
        print(f"Approved: {approved_at}")
        print(f"{capsule}")
        print(f"\n---\n")


def main():
    # Manual argument routing to avoid argparse subcommand conflicts.
    # "approve" and "bank" are subcommands; everything else is generate mode.
    argv = sys.argv[1:]

    if not argv:
        print(__doc__)
        return

    if argv[0] == 'approve':
        # approve "Title" [--file rewrite.txt]
        parser = argparse.ArgumentParser(description='Approve a capsule')
        parser.add_argument('title', help='Movie title')
        parser.add_argument('--file', help='Path to file with rewritten capsule text')
        args = parser.parse_args(argv[1:])
        cmd_approve(args)
        return

    if argv[0] == 'bank':
        cmd_bank(None)
        return

    # Generate mode (default)
    parser = argparse.ArgumentParser(
        description='Generate editorial capsule descriptions'
    )
    parser.add_argument('title', nargs='?', help='Movie title to generate capsule for')
    parser.add_argument('--batch', action='store_true', help='Batch process all movies')
    parser.add_argument('--limit', type=int, default=0, help='Limit batch to N movies')
    parser.add_argument('--days', type=int, default=0, help='Batch only films with digital_date within N days (0 = whole wall)')
    parser.add_argument('--force', action='store_true', help='Regenerate even if cached')
    parser.add_argument('--skip-verify', action='store_true', help='Skip fact verification pass')
    parser.add_argument('--show-sources', action='store_true', help='Print source material alongside capsule')
    parser.add_argument('--variants', type=int, default=3, help='Number of capsule variants to generate (default 3)')
    args = parser.parse_args(argv)

    if args.batch:
        cmd_batch(args)
    elif args.title:
        cmd_generate(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
