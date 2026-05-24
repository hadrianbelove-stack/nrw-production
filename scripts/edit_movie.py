#!/usr/bin/env python3
"""Surgical, conflict-proof single-movie editor for data.json.

The safe way to make small edits to the wall (trailer, poster, synopsis,
a pull quote, an arbitrary field) WITHOUT running the full pipeline. It:

  1. refuses to run if data.json has uncommitted changes (no mixing),
  2. pulls fresh origin/main first (CI rewrites data.json daily),
  3. changes ONLY the one target movie's record, leaving all others
     byte-identical (re-dump round-trips the rest losslessly),
  4. commits just data.json (with the NRW data-commit token) and pushes,
     retrying once with --rebase if the push is rejected.

It NEVER does a full re-generation, so it can't wipe pull quotes or
re-categorize other movies the way a stale `generate_data.py` run can.

Usage:
    edit_movie.py <title-or-id> --trailer <url>
    edit_movie.py <title-or-id> --synopsis "new synopsis text"
    edit_movie.py <title-or-id> --set rt_score=88%  --set links.wikipedia=<url>
    edit_movie.py <title-or-id> --add-quote "great film" --critic "A. Critic" --outlet "Variety"
    edit_movie.py <title-or-id> --trailer <url> --dry-run     # preview only
    edit_movie.py <title-or-id> --poster <url> --no-push      # commit locally, don't push

Movie ID comparison always uses str() (data.json has mixed int/str IDs).
"""

import argparse
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'data.json')
COMBINED_CACHE = os.path.join(REPO, 'cache', 'pull_quotes_combined.json')


def run(cmd, **kw):
    """Run a git/shell command in the repo, returning CompletedProcess."""
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, **kw)


def die(msg, code=1):
    print('❌ %s' % msg)
    sys.exit(code)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def write_data(data):
    """Write data.json in the canonical format (indent=2, no ascii escaping,
    no trailing newline) so unchanged records round-trip byte-identically."""
    with open(DATA, 'w') as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False))


def find_movie(movies, needle):
    """Resolve a movie by exact str(id) match, else case-insensitive title
    substring. Returns the single match or exits with candidates."""
    needle = needle.strip()
    if needle.isdigit():
        hits = [m for m in movies if str(m.get('id')) == needle]
    else:
        low = needle.lower()
        hits = [m for m in movies if low in (m.get('title') or '').lower()]
    if not hits:
        die('No movie matched %r' % needle)
    if len(hits) > 1:
        print('⚠️  %d movies matched %r — be more specific:' % (len(hits), needle))
        for m in hits[:15]:
            print('    %s  (%s)  id=%s' % (m.get('title'), m.get('year'), m.get('id')))
        sys.exit(1)
    return hits[0]


def set_path(record, dotted_key, value):
    """Set a (possibly dotted) key on the record. e.g. 'links.trailer'.
    Returns (old_value, new_value)."""
    parts = dotted_key.split('.')
    node = record
    for p in parts[:-1]:
        if not isinstance(node.get(p), dict):
            node[p] = {}
        node = node[p]
    old = node.get(parts[-1])
    node[parts[-1]] = value
    return old, value


def coerce(value):
    """Turn a --set string value into int where it's clearly an int."""
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def add_quote(record, combined, text, critic, outlet, review_url):
    """Append a pull quote to the movie's data.json array AND the combined
    cache (selected=true) so a later pipeline run doesn't wipe it."""
    quote_display = {
        'text': text, 'critic': critic or '', 'outlet': outlet or '',
        'source': 'manual', 'review_url': review_url or '',
    }
    record.setdefault('pull_quotes', [])
    record['pull_quotes'].append(quote_display)

    # Keep the cache (inject source of truth) in sync.
    key = '%s_%s' % (record.get('title'), record.get('year'))
    entry = combined.get(key)
    if not entry:
        entry = {'title': record.get('title'), 'year': record.get('year'),
                 'rt_quotes': [], 'lb_quotes': []}
        combined[key] = entry
    entry.setdefault('rt_quotes', []).append({
        'text': text, 'critic': critic or '', 'outlet': outlet or '',
        'source': 'manual', 'review_url': review_url or '', 'selected': True,
    })


def parse_args():
    p = argparse.ArgumentParser(description='Surgical single-movie data.json editor.')
    p.add_argument('movie', help='Movie title (substring) or TMDB id')
    p.add_argument('--trailer', help='Set links.trailer URL')
    p.add_argument('--poster', help='Set poster URL')
    p.add_argument('--synopsis', help='Set synopsis text')
    p.add_argument('--set', action='append', default=[], metavar='KEY=VALUE',
                   help='Set an arbitrary field; dotted keys allowed (repeatable)')
    p.add_argument('--add-quote', metavar='TEXT', help='Add a pull quote (needs --critic)')
    p.add_argument('--critic', help='Critic name for --add-quote')
    p.add_argument('--outlet', help='Outlet for --add-quote')
    p.add_argument('--review-url', help='Review URL for --add-quote')
    p.add_argument('--dry-run', action='store_true', help='Show changes, write nothing')
    p.add_argument('--no-push', action='store_true', help='Commit locally, do not push')
    p.add_argument('--no-git', action='store_true', help='Edit data.json only (no pull/commit/push)')
    return p.parse_args()


def main():
    args = parse_args()
    if args.add_quote and not args.critic:
        die('--add-quote requires --critic')
    has_edit = any([args.trailer, args.poster, args.synopsis, args.set, args.add_quote])
    if not has_edit:
        die('No edit specified (use --trailer/--poster/--synopsis/--set/--add-quote)')

    # 1. Refuse to run on a dirty data.json — never mix edits.
    if not args.no_git:
        st = run(['git', 'status', '--porcelain', 'data.json'])
        if st.stdout.strip():
            die('data.json has uncommitted changes. Commit or discard them first.')

        # 2. Pull fresh so we edit current data.
        pull = run(['git', 'pull', 'origin', 'main'])
        if pull.returncode != 0:
            die('git pull failed:\n%s' % (pull.stderr or pull.stdout))
        print('↪ pulled origin/main')

    data = load_json(DATA)
    movies = data['movies']
    movie = find_movie(movies, args.movie)
    title = movie.get('title')
    changes = []

    if args.trailer:
        old, _ = set_path(movie, 'links.trailer', args.trailer)
        changes.append(('links.trailer', old, args.trailer))
    if args.poster:
        old = movie.get('poster')
        movie['poster'] = args.poster
        changes.append(('poster', old, args.poster))
    if args.synopsis:
        old = movie.get('synopsis')
        movie['synopsis'] = args.synopsis
        changes.append(('synopsis', old, args.synopsis))
    for kv in args.set:
        if '=' not in kv:
            die('--set expects KEY=VALUE, got %r' % kv)
        k, v = kv.split('=', 1)
        old, new = set_path(movie, k.strip(), coerce(v.strip()))
        changes.append((k.strip(), old, new))

    combined = load_json(COMBINED_CACHE, {}) if args.add_quote else None
    if args.add_quote:
        add_quote(movie, combined, args.add_quote, args.critic, args.outlet, args.review_url)
        changes.append(('pull_quotes', '+1 quote', '"%s" — %s' % (args.add_quote[:50], args.critic)))

    # Report the diff.
    print('\n🎬 %s (id=%s)' % (title, movie.get('id')))
    for field, old, new in changes:
        def short(x):
            s = x if isinstance(x, str) else json.dumps(x)
            return (s[:70] + '…') if s and len(s) > 70 else s
        print('   %s:' % field)
        print('     - %s' % short(old))
        print('     + %s' % short(new))

    if args.dry_run:
        print('\n(dry run — nothing written)')
        return

    # 7. Write data.json (and the quote cache, which is gitignored/local).
    write_data(data)
    if args.add_quote:
        os.makedirs(os.path.dirname(COMBINED_CACHE), exist_ok=True)
        with open(COMBINED_CACHE, 'w') as f:
            json.dump(combined, f, indent=2, ensure_ascii=False)
    print('\n✅ data.json updated')

    if args.no_git:
        return

    # 9. Commit ONLY data.json (caches are gitignored local source-of-truth).
    fields = ', '.join(c[0] for c in changes)
    msg = 'Edit %s: %s APPROVED: DELETE' % (title, fields)
    run(['git', 'add', 'data.json'])
    env = dict(os.environ, NRW_ALLOW_DATA_COMMIT='1')
    commit = subprocess.run(['git', 'commit', '-m', msg], cwd=REPO, env=env,
                            capture_output=True, text=True)
    if commit.returncode != 0:
        die('commit failed:\n%s' % (commit.stdout + commit.stderr))
    print('✅ committed: %s' % msg)

    if args.no_push:
        print('(--no-push: not pushing)')
        return

    push = run(['git', 'push', 'origin', 'main'])
    if push.returncode != 0:
        # Origin moved (CI or another writer) — rebase and retry once.
        print('↪ push rejected, rebasing on origin/main…')
        reb = run(['git', 'pull', '--rebase', 'origin', 'main'])
        if reb.returncode != 0:
            die('rebase failed — resolve manually (never --ours/--theirs on data.json):\n%s'
                % (reb.stdout + reb.stderr))
        push = run(['git', 'push', 'origin', 'main'])
        if push.returncode != 0:
            die('push failed after rebase:\n%s' % (push.stdout + push.stderr))
    print('🚀 pushed to origin/main')


if __name__ == '__main__':
    main()
