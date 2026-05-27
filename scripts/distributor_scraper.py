"""
Distributor scraper — fetches "distributed by" for films in data.json.

Sources (in order):
  1. Wikidata P750 via wikibase_item from Wikipedia REST summary
  2. Wikipedia infobox wikitext fallback (| distributor = ...)

Writes `distributor` field directly to data.json.
Safe to re-run — skips films that already have a distributor.
"""

import json
import re
import time
import sys
import requests

HEADERS = {'User-Agent': 'NRW-DistributorScraper/1.0 (hadrianbelove@gmail.com)'}
DATA_FILE = 'data.json'


def get_wikibase_item(wiki_url: str) -> None:
    """Get Wikidata entity ID from a Wikipedia URL."""
    title = wiki_url.rstrip('/').split('/wiki/')[-1]
    try:
        r = requests.get(
            f'https://en.wikipedia.org/api/rest_v1/page/summary/{title}',
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            return r.json().get('wikibase_item')
    except Exception:
        pass
    return None


def get_distributor_from_wikidata(qid: str) -> None:
    """Query Wikidata P750 (distributed by) for a given entity ID."""
    try:
        r = requests.get(
            'https://www.wikidata.org/w/api.php',
            params={
                'action': 'wbgetentities',
                'ids': qid,
                'props': 'claims',
                'format': 'json'
            },
            headers=HEADERS, timeout=10
        )
        if r.status_code != 200:
            return None
        entity = r.json().get('entities', {}).get(qid, {})
        claims = entity.get('claims', {})
        p750 = claims.get('P750', [])
        if not p750:
            return None
        # Get all distributor entity IDs
        dist_ids = []
        for claim in p750:
            val = claim.get('mainsnak', {}).get('datavalue', {}).get('value', {})
            if isinstance(val, dict) and val.get('id'):
                dist_ids.append(val['id'])
        if not dist_ids:
            return None
        # Resolve labels
        r2 = requests.get(
            'https://www.wikidata.org/w/api.php',
            params={
                'action': 'wbgetentities',
                'ids': '|'.join(dist_ids),
                'props': 'labels',
                'languages': 'en',
                'format': 'json'
            },
            headers=HEADERS, timeout=10
        )
        if r2.status_code != 200:
            return None
        entities = r2.json().get('entities', {})
        labels = []
        for did in dist_ids:
            label = entities.get(did, {}).get('labels', {}).get('en', {}).get('value')
            if label:
                labels.append(label)
        return ' / '.join(labels) if labels else None
    except Exception:
        return None


def get_distributor_from_infobox(wiki_url: str) -> None:
    """Parse Wikipedia infobox wikitext for | distributor = ..."""
    title = wiki_url.rstrip('/').split('/wiki/')[-1]
    try:
        r = requests.get(
            'https://en.wikipedia.org/w/api.php',
            params={
                'action': 'parse',
                'page': title,
                'prop': 'wikitext',
                'format': 'json'
            },
            headers=HEADERS, timeout=15
        )
        if r.status_code != 200:
            return None
        wikitext = r.json().get('parse', {}).get('wikitext', {}).get('*', '')
        # Match | distributor = ... up to next | or }}
        match = re.search(r'\|\s*distributor\s*=\s*(.+?)(?=\n\s*\||\n\s*\}\})', wikitext, re.DOTALL)
        if not match:
            return None
        raw = match.group(1).strip()
        # Strip wiki markup: [[X|Y]] -> Y, [[X]] -> X, {{...}} -> removed
        raw = re.sub(r'\{\{[^}]*\}\}', '', raw)
        raw = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', raw)
        raw = re.sub(r"'''?|''?", '', raw)
        raw = re.sub(r'<br\s*/?>', ' / ', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s+', ' ', raw).strip().strip('*').strip()
        return raw if raw else None
    except Exception:
        return None


def main():
    with open(DATA_FILE) as f:
        data = json.load(f)

    movies = data if isinstance(data, list) else data.get('movies', [])
    is_list = isinstance(data, list)

    candidates = [
        m for m in movies
        if (m.get('links') or {}).get('wikipedia') and not m.get('distributor')
    ]

    print(f"Films with Wikipedia URL: {len(candidates)}")
    print(f"Already have distributor: {sum(1 for m in movies if m.get('distributor'))}")
    print(f"To scrape: {len(candidates)}\n")

    found = 0
    not_found = 0

    for i, movie in enumerate(candidates, 1):
        title = movie.get('title', '?')
        wiki_url = movie['links']['wikipedia']

        sys.stdout.write(f"[{i}/{len(candidates)}] {title[:50]:<50} ")
        sys.stdout.flush()

        # Method 1: Wikidata P750
        distributor = None
        qid = get_wikibase_item(wiki_url)
        time.sleep(0.3)

        if qid:
            distributor = get_distributor_from_wikidata(qid)
            time.sleep(0.3)

        # Method 2: Infobox fallback
        if not distributor:
            distributor = get_distributor_from_infobox(wiki_url)
            time.sleep(0.5)

        if distributor:
            movie['distributor'] = distributor
            found += 1
            print(f"→ {distributor}")
        else:
            not_found += 1
            print("→ (not found)")

        # Save every 25 films
        if i % 25 == 0:
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            print(f"  [saved at {i}]")

    # Final save
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    print(f"\nDone. Found: {found} / {len(candidates)} ({not_found} not found)")


if __name__ == '__main__':
    main()
