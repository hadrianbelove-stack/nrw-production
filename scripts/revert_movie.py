#!/usr/bin/env python3
"""Revert a film: it isn't really out yet (wrongly marked new, usually the pre-order problem).

The OPPOSITE of /remove. Remove = a title the owner never wants on the wall (gone for good).
Revert = take it off now so it comes back on its own the day it's really out: back to
tracking as a held film, checked on JustWatch every run, never dated on or before today.
A removed title is never reverted.

Usage: /usr/bin/python3 scripts/revert_movie.py <tmdb_id>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import putback  # noqa: E402
from pipeline.json_io import json_edit  # noqa: E402
from pipeline.tracking_db import get_tracking_db  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    movie_id = str(sys.argv[1]).strip()
    db = get_tracking_db()
    tracking = db.load_all()
    rec = tracking.get('movies', {}).get(movie_id)
    if not rec:
        print(f"❌ {movie_id} is not in tracking — nothing to revert")
        return 1
    title = rec.get('title', movie_id)
    try:   # the wall knows a restoration its tracking record may not (display.py's year gap)
        with open('data.json') as f:
            entry = next((m for m in json.load(f).get('movies', []) if str(m.get('id')) == movie_id), None)
    except (OSError, ValueError):
        entry = None
    if not putback.owner_revert(rec, wall_entry=entry):
        print(f"❌ {title} ({movie_id}) was REMOVED for good — removed titles are never reverted")
        return 1
    if not db.save_all(tracking) or getattr(db, 'last_export_error', None):
        print(f"❌ {title} ({movie_id}): the tracking file could not be saved "
              f"({getattr(db, 'last_export_error', None) or 'database write failed'}) — nothing changed "
              f"on the wall. Try again.")
        return 1
    with json_edit('data.json') as site:
        on_wall = putback.revert_wall_entry(site, movie_id)
    print(f"↩ {title} ({movie_id}) reverted — {'off the wall now' if on_wall else 'was not on the wall'}; "
          f"back to waiting, checked on JustWatch every run, back on the wall the day it's really out")
    try:
        with open('overrides/watch_links_overrides.json') as f:
            has_override = movie_id in (json.load(f) or {})
    except (OSError, ValueError):
        has_override = False
    caveat = putback.revert_caveat(rec, has_override=has_override)
    if caveat:
        print(f"⚠ Note: {caveat}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
