#!/usr/bin/env python3
"""
Render the "Confirm Reissues" table from admin/reissue_candidates.json.

Shows EVERY pending candidate, pre-sorted by Gemini confidence (likely → maybe → unlikely),
each row link-dense to speed up human confirmation: a pre-filled Google search, the evidence
article Gemini cited, plus Wikipedia / IMDb / TMDB / trailer links.

Used by the /curate and /morning "Confirm Reissues" stage. Read-only — confirming/rejecting
is done by scripts/confirm_reissue.py.

Usage:
    python3 scripts/reissue_table.py [--file PATH]
"""

import os
import sys
import json
import argparse
import urllib.parse

CANDIDATES_FILE = 'admin/reissue_candidates.json'
_ORDER = {'likely': 0, 'maybe': 1, 'unlikely': 2}


def _q(s):
    return urllib.parse.quote_plus(str(s))


def _google(c):
    """Pre-filled Google search URL for the film — used to hyperlink the title."""
    title, year = c.get('title', ''), c.get('year', '') or ''
    return f"https://www.google.com/search?q={_q(f'{title} {year} restoration re-release')}"


def _links(c):
    title, year = c.get('title', ''), c.get('year', '') or ''
    tid = c.get('tmdb_id', '')
    research = c.get('research') or {}
    wiki = f"https://en.wikipedia.org/w/index.php?search={_q(f'{title} {year} film')}"
    imdb = f"https://www.imdb.com/find/?q={_q(f'{title} {year}')}"
    tmdb = f"https://www.themoviedb.org/movie/{tid}"
    trailer = f"https://www.youtube.com/results?search_query={_q(f'{title} {year} trailer')}"
    evidence = research.get('source_url') or ''
    parts = [f"[W]({wiki})"]
    if evidence:
        parts.append(f"[📰 Evidence]({evidence})")
    parts += [f"[IMDb]({imdb})", f"[TMDB]({tmdb})", f"[▶]({trailer})"]
    return " · ".join(parts)


# Words that make a phrase a REAL poster-badge descriptor (vs. generic decision data
# like "theatrical run", which belongs in the evidence column, not on the badge).
_BADGE_WORDS = ('restoration', 'restored', '4k', 'remaster', 'anniversary',
                'director', 'extended cut', 'assembly cut')

import re as _re


def _short_badge(text):
    """Reduce a verbose release description to a SHORT poster badge.
    "4K restoration, theatrical re-release, 4K UHD Blu-ray" -> "4K Restoration"
    "40th anniversary re-release, theatrical run" -> "40th Anniversary"
    Returns '' if no clean short descriptor can be extracted."""
    if not text:
        return ''
    full = text.lower()
    # Prefer a canonical short form when a known badge word appears anywhere in the text
    m = _re.search(r'(\d+(?:st|nd|rd|th))\s+anniversary', full)
    if m:
        return f"{m.group(1)} Anniversary"
    for kw, label in (('4k restoration', '4K Restoration'), ('4k remaster', '4K Remaster'),
                      ('2k restoration', '2K Restoration'), ('restoration', 'Restoration'),
                      ('remaster', '4K Remaster'), ('assembly cut', 'Assembly Cut'),
                      ('director', "Director's Cut"), ('extended cut', 'Extended Cut'),
                      ('restored', 'Restoration')):
        if kw in full:
            return label
    # First clause is already short and has a badge word → title-case it
    clause = text.split(',')[0].split('/')[0].strip()
    if len(clause.split()) <= 3 and any(w in clause.lower() for w in _BADGE_WORDS):
        return clause.title()
    return ''


def _suggested_label(c):
    """Short poster-badge text — ONLY when there's a real descriptor. Returns '' (blank)
    when nothing clean is available, so the user fills it in rather than getting a
    meaningless or verbose badge. Generic phrases like "theatrical run" are decision data
    (shown in other columns), never a badge."""
    research = c.get('research') or {}
    return (_short_badge(research.get('release_kind'))
            or _short_badge((c.get('recent_release') or {}).get('note', '')))


def sorted_pending(queue):
    """Return pending candidates in the canonical display order (verdict, green-flag,
    keyword hit, title). Shared by render() and the confirm script so table row numbers
    map to the same candidates."""
    pending = [c for c in queue.values() if c.get('status') == 'pending']

    def sort_key(c):
        r = c.get('research') or {}
        return (
            _ORDER.get(r.get('verdict', 'maybe'), 1),
            not r.get('distributor_greenflag', False),
            not c.get('note_keyword_hit', False),
            c.get('title', ''),
        )
    pending.sort(key=sort_key)
    return pending


def render(candidates_file=CANDIDATES_FILE):
    if not os.path.exists(candidates_file):
        print("Confirm Reissues: no candidate queue yet (run intake Pass D first).")
        return
    with open(candidates_file) as f:
        data = json.load(f)
    queue = data.get('candidates', {})
    pending = sorted_pending(queue)

    if not pending:
        print("Confirm Reissues: all caught up — no pending candidates.")
        return

    unresearched = sum(1 for c in pending if not c.get('research'))
    print(f"Confirm Reissues — {len(pending)} pending candidate(s), pre-sorted by confidence:")
    if unresearched:
        print(f"  ⚠ {unresearched} not yet researched — run: GEMINI_API_KEY=… python3 pipeline/reissue_research.py\n")

    print("| # | Title (Year) | Recent release | Verdict | Gemini evidence (why) | Badge text | Links |")
    print("|---|---|---|---|---|---|---|")
    for i, c in enumerate(pending, 1):
        r = c.get('research') or {}
        rr = c.get('recent_release') or {}
        title = c.get('title', '?')
        year = c.get('year', '?')
        recent = f"{rr.get('type', '?')}"
        if rr.get('note'):
            recent += f" — “{rr['note']}”"
        verdict = r.get('verdict', '—')
        vmark = {'likely': '🟢 likely', 'maybe': '🟡 maybe', 'unlikely': '⚪ unlikely'}.get(verdict, '— not researched')
        if r.get('distributor_greenflag'):
            vmark += " ⭐DIST"
        summary = (r.get('summary') or '').replace('\n', ' ').replace('|', '∕')
        if len(summary) > 160:
            summary = summary[:157] + '…'
        label = _suggested_label(c).replace('|', '∕') or '— *(you set)*'
        title_link = f"[{title} ({year})]({_google(c)})"  # title hyperlinks to its Google search
        print(f"| {i} | {title_link} | {recent} | {vmark} | {summary} | {label} | {_links(c)} |")

    print(f"\nTo confirm: reply with the numbers to add (e.g. \"1, 3, 5\") and any label edits.")
    print(f"Each confirmed film enters tracking with its reissue badge; the rest are marked rejected so they don't re-appear.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default=CANDIDATES_FILE)
    args = ap.parse_args()
    render(args.file)


if __name__ == '__main__':
    main()
