"""
Festival auto-feeder — scans each wall film's Wikipedia article for a premiere at
a prestige festival and writes movie_id -> festival into admin/festival_films.json.

This is the "auto" half of the festival signal; manual entries in the same file are
preserved (never overwritten). The slop classifier reads the file for a -1 signal.

Usage:
  /usr/bin/python3 scripts/detect_festivals.py            # all films with a wiki link
  /usr/bin/python3 scripts/detect_festivals.py --dry-run  # report, don't write
"""
import json
import re
import sys
import time
from urllib.parse import unquote

import requests

OUT_PATH = 'admin/festival_films.json'

# canonical name -> regex alternatives matched in the article text
FESTIVALS = {
    'Cannes': r'Cannes Film Festival',
    'Berlinale': r'Berlin International Film Festival|Berlinale',
    'Rotterdam': r'International Film Festival Rotterdam',
    'Sundance': r'Sundance Film Festival',
    'Telluride': r'Telluride Film Festival',
    'NYFF': r'New York Film Festival',
    'Venice': r'Venice Film Festival|Venice International Film Festival',
    'Locarno': r'Locarno Film Festival|Locarno International Film Festival',
}

# Require a premiere/selection context word within ~80 chars of the festival name,
# so a passing mention ("distributor near Cannes") doesn't trigger a match.
CONTEXT = r'(premier|in competition|official selection|screened|selected|debut|world premiere|competed|competition)'


def _article_title(wiki_url):
    # Strip trailing slash, take the /wiki/<title> segment, drop any ?query / #frag.
    seg = wiki_url.rstrip('/').split('/wiki/')[-1]
    seg = seg.split('?')[0].split('#')[0]
    return unquote(seg)


def _fetch_extract(wiki_url, retries=4):
    """Full plain-text article extract via the MediaWiki API, with 429 backoff."""
    title = _article_title(wiki_url)
    for attempt in range(retries):
        r = requests.get(
            'https://en.wikipedia.org/w/api.php',
            params={
                'action': 'query', 'prop': 'extracts', 'explaintext': 1,
                'redirects': 1, 'format': 'json', 'titles': title,
            },
            headers={'User-Agent': 'NRW-festival-detector/1.0 (nrw curation)'},
            timeout=15,
        )
        if r.status_code == 429:
            time.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s
            continue
        r.raise_for_status()
        pages = r.json().get('query', {}).get('pages', {})
        for p in pages.values():
            return p.get('extract', '') or ''
        return ''
    raise requests.HTTPError('429 after retries')


def detect(text):
    """Return the first prestige festival named with premiere context, else None."""
    for canon, pat in FESTIVALS.items():
        for m in re.finditer(pat, text, re.IGNORECASE):
            window = text[max(0, m.start() - 80): m.end() + 80]
            if re.search(CONTEXT, window, re.IGNORECASE):
                return canon
    return None


def main():
    dry = '--dry-run' in sys.argv
    data = json.load(open('data.json'))
    try:
        existing = json.load(open(OUT_PATH))
    except (OSError, ValueError):
        existing = {}

    films = [m for m in data['movies'] if m.get('links', {}).get('wikipedia')]
    print(f'Scanning {len(films)} films with a Wikipedia link...')
    found = 0
    for i, m in enumerate(films, 1):
        mid = str(m.get('id'))
        if mid in existing:  # manual or already-detected entry wins
            continue
        try:
            text = _fetch_extract(m['links']['wikipedia'])
        except Exception as e:
            print(f'  [{i}] {m.get("title")}: fetch error ({e})')
            continue
        fest = detect(text)
        if fest:
            found += 1
            existing[mid] = fest
            print(f'  ✓ {m.get("title")} ({m.get("year")}) -> {fest}')
        time.sleep(0.5)  # be polite to the API (avoid 429s)

    print(f'\nDetected {found} new festival film(s).')
    if dry:
        print('(dry run — not written)')
        return
    json.dump(existing, open(OUT_PATH, 'w'), indent=2, ensure_ascii=False)
    print(f'Wrote {len(existing)} total entries to {OUT_PATH}')


if __name__ == '__main__':
    main()
