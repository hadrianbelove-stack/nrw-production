#!/usr/bin/env python3
"""
Sandbox audit: scan all NRW wall movies for JustWatch CINEMA offers.
For any movie with a CINEMA offer, also HTTP-verify its existing rental URL.

Usage: /usr/bin/python3 scripts/cinema_link_audit.py [--verify-links]
"""

import json
import sys
import time
import requests
import concurrent.futures
from datetime import datetime

sys.path.insert(0, '.')
from pipeline.justwatch import JustWatchClient

WALL_FILE = 'data.json'
MAX_WORKERS = 4          # JustWatch rate limit buffer
REQUEST_DELAY = 0.2      # seconds between JW queries per thread

PREORDER_SIGNALS = [
    'pre-order', 'preorder', 'pre order',
    'coming soon', 'not yet available', 'available on ',
    'release date', 'notify me', 'add to watchlist',
]
AVAILABLE_SIGNALS = [
    'rent', 'buy', 'watch now', 'stream now', '$',
]


def check_rental_url(url, title):
    """HTTP-check a rental URL. Returns (status, detail)."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        body = r.text.lower()

        if r.status_code != 200:
            return 'http_error', f'HTTP {r.status_code}'

        final_url = r.url.lower()

        # Strong pre-order/unavailable signals in URL or body
        for sig in PREORDER_SIGNALS:
            if sig in body[:8000]:   # only check top of page
                return 'preorder_signal', f'found "{sig}" in page'

        # Check redirect landed somewhere unexpected (search page, homepage)
        if any(x in final_url for x in ['search', '/s?', 'results', '/home']):
            return 'bad_redirect', f'redirected to {r.url[:80]}'

        # Positive signals
        for sig in AVAILABLE_SIGNALS:
            if sig in body[:8000]:
                return 'available', f'found "{sig}" in page'

        return 'inconclusive', f'no clear signals (HTTP 200, final={r.url[:60]})'

    except requests.exceptions.Timeout:
        return 'timeout', 'request timed out'
    except Exception as e:
        return 'error', str(e)[:80]


def scan_movie(movie, client, verify_links=False):
    """Query JustWatch for one movie, return result dict."""
    title = movie['title']
    year = movie.get('year')
    tmdb_id = str(movie.get('id'))
    existing_vod = movie.get('watch_links', {}).get('vod', [])

    try:
        time.sleep(REQUEST_DELAY)
        jw = client.search_movie(title, year)
    except Exception as e:
        return {'id': tmdb_id, 'title': title, 'error': str(e), 'cinema_offers': [], 'rent_offers': []}

    if not jw:
        return {'id': tmdb_id, 'title': title, 'no_jw_match': True, 'cinema_offers': [], 'rent_offers': []}

    offers = jw.get('offers', [])
    cinema_offers = [o for o in offers if o.get('monetizationType') == 'CINEMA']
    rent_offers   = [o for o in offers if o.get('monetizationType') in ('RENT', 'BUY')]

    result = {
        'id': tmdb_id,
        'title': title,
        'year': year,
        'cinema_offers': [{'service': o.get('package',{}).get('clearName'), 'url': o.get('standardWebURL','')} for o in cinema_offers],
        'rent_offers':   [{'service': o.get('package',{}).get('clearName'), 'price': o.get('retailPrice'), 'url': o.get('standardWebURL','')} for o in rent_offers],
        'has_cinema': len(cinema_offers) > 0,
    }

    if result['has_cinema'] and verify_links and existing_vod:
        link_checks = []
        for vod in existing_vod:
            url = vod.get('link') or vod.get('url')
            if url:
                status, detail = check_rental_url(url, title)
                link_checks.append({'service': vod.get('service'), 'url': url[:80], 'status': status, 'detail': detail})
        result['link_checks'] = link_checks

    return result


def main():
    verify_links = '--verify-links' in sys.argv

    with open(WALL_FILE) as f:
        data = json.load(f)
    movies = data['movies']

    print(f"NRW Cinema Link Audit — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Wall: {len(movies)} movies | verify-links: {verify_links}")
    print("=" * 60)

    client = JustWatchClient()
    results = []
    errors = []
    no_match = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scan_movie, m, client, verify_links): m for m in movies}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            done += 1
            r = fut.result()
            results.append(r)
            if done % 50 == 0 or done == len(movies):
                cinema_so_far = sum(1 for x in results if x.get('has_cinema'))
                print(f"  [{done}/{len(movies)}] cinema hits so far: {cinema_so_far}", flush=True)
            if r.get('error'):
                errors.append(r)
            if r.get('no_jw_match'):
                no_match.append(r)

    cinema_hits = [r for r in results if r.get('has_cinema')]
    clean       = [r for r in results if not r.get('has_cinema') and not r.get('error') and not r.get('no_jw_match')]

    print()
    print("=" * 60)
    print(f"RESULTS SUMMARY")
    print(f"  Total scanned:        {len(movies)}")
    print(f"  JW no match:          {len(no_match)}")
    print(f"  JW errors:            {len(errors)}")
    print(f"  Clean (no cinema):    {len(clean)}")
    print(f"  CINEMA offer present: {len(cinema_hits)}")

    if cinema_hits:
        print()
        print("MOVIES WITH CINEMA OFFERS (would trigger link verification):")
        print("-" * 60)
        for r in sorted(cinema_hits, key=lambda x: x['title']):
            cinema_svcs = ', '.join(o['service'] for o in r['cinema_offers'] if o['service'])
            rent_svcs   = ', '.join(f"{o['service']} {o['price'] or ''}" for o in r['rent_offers'] if o['service'])
            print(f"  {r['title']} ({r['year']})  [ID:{r['id']}]")
            print(f"    Cinema: {cinema_svcs or '—'}")
            print(f"    Rent:   {rent_svcs or 'none'}")
            if r.get('link_checks'):
                for lc in r['link_checks']:
                    flag = '✓' if lc['status'] == 'available' else '✗'
                    print(f"    Link check [{lc['service']}]: {flag} {lc['status']} — {lc['detail']}")
            print()

    if verify_links and cinema_hits:
        would_block  = [r for r in cinema_hits if any(lc['status'] != 'available' for lc in r.get('link_checks', []))]
        would_pass   = [r for r in cinema_hits if all(lc['status'] == 'available' for lc in r.get('link_checks', [{'status':'available'}]))]
        print(f"LINK VERIFICATION OUTCOME (for {len(cinema_hits)} cinema-flagged movies):")
        print(f"  Would block (revert to tracking): {len(would_block)}")
        print(f"  Would pass  (admit anyway):       {len(would_pass)}")

    # Save full results
    out_file = 'metrics/cinema_audit_results.json'
    with open(out_file, 'w') as f:
        json.dump({'run_at': datetime.now().isoformat(), 'total': len(movies),
                   'cinema_hits': cinema_hits, 'no_match': no_match, 'errors': errors}, f, indent=2)
    print(f"\nFull results saved to {out_file}")


if __name__ == '__main__':
    main()
