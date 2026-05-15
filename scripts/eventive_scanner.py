#!/usr/bin/env python3
"""
Eventive Virtual Screening Scanner — Standalone Prototype

Scans Eventive's festival directory for active virtual screenings,
cross-references against NRW tracking/wall movies, and reports results.

Report-only — does NOT modify cache or tracking files.

Usage:
    python3 scripts/eventive_scanner.py
"""

import json
import os
import re
import time
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FESTIVAL_DIRECTORY_URL = 'https://watch.eventive.org/find/film_festival'
CATALOG_API_URL = 'https://api.eventive.org/watch/catalog'
RATE_LIMIT = 1.0  # seconds between requests
HTTP_TIMEOUT = 15
HEADERS = {'User-Agent': 'Mozilla/5.0 (NRW Scanner)'}


# ---------------------------------------------------------------------------
# Title normalization
# ---------------------------------------------------------------------------
def normalize_title(title):
    """Tier 1: lowercase, strip 'the ' prefix and year suffixes."""
    t = title.strip().lower()
    t = re.sub(r'\s*\(\d{4}\)\s*$', '', t)  # strip "(2026)"
    t = re.sub(r'^the\s+', '', t)
    return t.strip()


def normalize_title_strict(title):
    """Tier 2: also strip punctuation and collapse whitespace."""
    t = normalize_title(title)
    t = re.sub(r'[^\w\s]', '', t)  # strip punctuation
    t = re.sub(r'\s+', ' ', t).strip()
    return t


# ---------------------------------------------------------------------------
# Step 1: Fetch festival directory
# ---------------------------------------------------------------------------
def fetch_festival_slugs():
    """Fetch the Eventive festival directory and extract slugs."""
    print("Step 1: Fetching festival directory...")
    resp = requests.get(FESTIVAL_DIRECTORY_URL, timeout=HTTP_TIMEOUT, headers=HEADERS)
    resp.raise_for_status()

    # Extract slugs from href="/slug" links in the directory
    slugs = re.findall(r'href="/([a-z0-9_-]+)"', resp.text)
    # Deduplicate and filter out common non-festival slugs
    skip = {'find', 'login', 'signup', 'about', 'help', 'terms', 'privacy',
            'faq', 'contact', 'careers', 'press', 'blog', 'search'}
    slugs = list(dict.fromkeys(s for s in slugs if s not in skip and len(s) > 2))
    print(f"  Found {len(slugs)} festival slugs")
    return slugs


# ---------------------------------------------------------------------------
# Step 2: Get event_bucket IDs from festival pages
# ---------------------------------------------------------------------------
def fetch_event_bucket(slug):
    """Fetch a festival page and extract the event_bucket ID from __NEXT_DATA__."""
    url = f'https://watch.eventive.org/{slug}'
    resp = requests.get(url, timeout=HTTP_TIMEOUT, headers=HEADERS)
    if not resp.ok:
        return None, None

    nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text)
    if not nd_match:
        return None, None

    try:
        nd = json.loads(nd_match.group(1))
        tenant = nd.get('props', {}).get('pageProps', {}).get('initialTenant', {})
        event_bucket = tenant.get('event_bucket')
        display_name = tenant.get('display_name', slug)
        return event_bucket, display_name
    except (json.JSONDecodeError, KeyError, AttributeError):
        return None, None


# ---------------------------------------------------------------------------
# Step 3: Fetch catalog for a festival
# ---------------------------------------------------------------------------
def fetch_catalog(event_bucket, slug):
    """Fetch the film catalog for a festival via the Eventive API."""
    url = f'{CATALOG_API_URL}?event_bucket={event_bucket}'
    resp = requests.get(url, timeout=HTTP_TIMEOUT, headers=HEADERS)
    if not resp.ok:
        return []

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return []

    films = []
    sections = data.get('sections', [])
    if not isinstance(sections, list):
        sections = [sections]

    for section in sections:
        if not isinstance(section, dict):
            continue
        items = section.get('items', [])
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get('name', '').strip()
            film_id = item.get('id', '')
            start_time = item.get('start_time', '')
            end_time = item.get('end_time', '')
            if name and film_id:
                films.append({
                    'name': name,
                    'film_id': film_id,
                    'slug': slug,
                    'link': f'https://watch.eventive.org/{slug}/play/{film_id}',
                    'start_time': start_time,
                    'end_time': end_time,
                    'is_available': item.get('isAvailable', None),
                })
    return films


# ---------------------------------------------------------------------------
# Step 4: Filter expired screenings
# ---------------------------------------------------------------------------
def is_expired(film):
    """Check if a screening has expired based on end_time only.
    Note: isAvailable from the catalog API means 'user has purchased',
    NOT 'screening window is open'. Do not use it for expiry filtering."""
    end_time = film.get('end_time', '')
    if not end_time:
        return False  # No end time = assume still active
    try:
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        return end_dt < datetime.now(end_dt.tzinfo)
    except (ValueError, TypeError):
        return False


def screening_status(film):
    """Return 'active', 'upcoming', or 'expired'."""
    if is_expired(film):
        return 'expired'
    start_time = film.get('start_time', '')
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if start_dt > datetime.now(start_dt.tzinfo):
                return 'upcoming'
        except (ValueError, TypeError):
            pass
    return 'active'


# ---------------------------------------------------------------------------
# Step 5: Load NRW data and build title indexes
# ---------------------------------------------------------------------------
def load_nrw_data():
    """Load tracking and wall data, build normalized title indexes."""
    # Load tracking
    tracking_movies = {}
    if os.path.exists('movie_tracking.json'):
        with open('movie_tracking.json') as f:
            db = json.load(f)
        tracking_movies = db.get('movies', db)

    # Load wall
    wall_movies = []
    if os.path.exists('data.json'):
        with open('data.json') as f:
            data = json.load(f)
        wall_movies = data.get('movies', []) if isinstance(data, dict) else data

    # Build title indexes: normalized_title -> [(id, original_title, source)]
    # Tier 1 index (basic normalization)
    tier1_index = {}
    # Tier 2 index (strict normalization)
    tier2_index = {}

    for mid, m in tracking_movies.items():
        title = m.get('title', '')
        if not title:
            continue
        entry = (str(mid), title, 'tracking', m.get('status', 'tracking'))

        n1 = normalize_title(title)
        tier1_index.setdefault(n1, []).append(entry)

        n2 = normalize_title_strict(title)
        tier2_index.setdefault(n2, []).append(entry)

    for m in wall_movies:
        title = m.get('title', '')
        mid = str(m.get('id', ''))
        if not title or not mid:
            continue
        entry = (mid, title, 'wall', 'available')

        n1 = normalize_title(title)
        tier1_index.setdefault(n1, []).append(entry)

        n2 = normalize_title_strict(title)
        tier2_index.setdefault(n2, []).append(entry)

    return tier1_index, tier2_index, len(tracking_movies), len(wall_movies)


# ---------------------------------------------------------------------------
# Step 6: Match films against NRW
# ---------------------------------------------------------------------------
def match_film(film, tier1_index, tier2_index):
    """Try to match an Eventive film against NRW data. Returns match info or None."""
    name = film['name']

    # Tier 1: basic normalization
    n1 = normalize_title(name)
    if n1 in tier1_index:
        matches = tier1_index[n1]
        return {'tier': 1, 'matches': matches}

    # Tier 2: strict normalization (strip punctuation)
    n2 = normalize_title_strict(name)
    if n2 in tier2_index:
        matches = tier2_index[n2]
        return {'tier': 2, 'matches': matches}

    return None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def format_date(iso_str):
    """Format ISO datetime to readable date."""
    if not iso_str:
        return '?'
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime('%b %d, %Y')
    except (ValueError, TypeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("EVENTIVE VIRTUAL SCREENING SCANNER")
    print("=" * 70)
    print()

    # Load NRW data
    tier1_index, tier2_index, tracking_count, wall_count = load_nrw_data()
    print(f"NRW data loaded: {tracking_count} tracking, {wall_count} on wall")
    print()

    # Step 1: Get festival slugs
    try:
        slugs = fetch_festival_slugs()
    except Exception as e:
        print(f"ERROR: Could not fetch festival directory: {e}")
        return

    # Steps 2-3: Scan each festival
    all_films = []
    festivals_scanned = 0
    festivals_with_films = 0
    festivals_failed = 0
    festival_names = {}

    print(f"\nStep 2-3: Scanning {len(slugs)} festivals for catalogs...")
    for i, slug in enumerate(slugs):
        time.sleep(RATE_LIMIT)

        try:
            event_bucket, display_name = fetch_event_bucket(slug)
            if not event_bucket:
                festivals_failed += 1
                continue

            festival_names[slug] = display_name
            festivals_scanned += 1

            time.sleep(RATE_LIMIT)
            films = fetch_catalog(event_bucket, slug)

            if films:
                festivals_with_films += 1
                # Tag each film with the festival display name
                for f in films:
                    f['festival_name'] = display_name
                all_films.extend(films)

            if (i + 1) % 25 == 0:
                print(f"  Progress: {i + 1}/{len(slugs)} slugs | "
                      f"{festivals_scanned} scanned | "
                      f"{len(all_films)} films indexed")

        except requests.RequestException as e:
            festivals_failed += 1
            continue

    print(f"\n  Done: {festivals_scanned} festivals scanned, "
          f"{festivals_with_films} with films, "
          f"{festivals_failed} failed")
    print(f"  Total films indexed: {len(all_films)}")

    # Step 4: Filter expired
    active_films = []
    expired_count = 0
    for film in all_films:
        status = screening_status(film)
        film['status'] = status
        if status == 'expired':
            expired_count += 1
        else:
            active_films.append(film)

    print(f"  Active/upcoming: {len(active_films)} | Expired (filtered out): {expired_count}")

    # Step 5-6: Match against NRW
    tracking_matches = []  # Films matched to tracking movies
    wall_matches = []      # Films matched to wall movies
    unmatched = []         # Films not in NRW at all

    # Deduplicate: if same film appears in multiple festivals, keep the one
    # with the latest end_time
    seen_titles = {}  # normalized_title -> film (keep best)
    for film in active_films:
        key = normalize_title(film['name'])
        if key in seen_titles:
            existing = seen_titles[key]
            # Keep the one with later end_time
            if (film.get('end_time', '') or '') > (existing.get('end_time', '') or ''):
                seen_titles[key] = film
        else:
            seen_titles[key] = film

    unique_films = list(seen_titles.values())
    print(f"  Unique active films (deduplicated): {len(unique_films)}")

    for film in unique_films:
        match = match_film(film, tier1_index, tier2_index)
        if match:
            # Determine if tracking or wall match
            for mid, orig_title, source, status in match['matches']:
                entry = {
                    'movie_id': mid,
                    'nrw_title': orig_title,
                    'eventive_title': film['name'],
                    'festival': film.get('festival_name', film['slug']),
                    'link': film['link'],
                    'start': film.get('start_time', ''),
                    'end': film.get('end_time', ''),
                    'status': film['status'],
                    'match_tier': match['tier'],
                    'nrw_status': status,
                }
                if source == 'wall':
                    wall_matches.append(entry)
                else:
                    tracking_matches.append(entry)
        else:
            unmatched.append({
                'eventive_title': film['name'],
                'festival': film.get('festival_name', film['slug']),
                'link': film['link'],
                'start': film.get('start_time', ''),
                'end': film.get('end_time', ''),
                'status': film['status'],
            })

    # ---------------------------------------------------------------------------
    # Print Report
    # ---------------------------------------------------------------------------
    print()
    print("=" * 70)
    print("SCAN RESULTS")
    print("=" * 70)

    # Section 1: Tracking matches
    print(f"\n{'─' * 70}")
    print(f"MATCHES IN NRW TRACKING — {len(tracking_matches)} films")
    print(f"{'─' * 70}")
    if tracking_matches:
        for m in sorted(tracking_matches, key=lambda x: x['festival']):
            status_tag = f"[{m['status'].upper()}]"
            tier_tag = f"(tier {m['match_tier']})" if m['match_tier'] > 1 else ""
            print(f"  {m['nrw_title']:<45} {status_tag:<10} {tier_tag}")
            print(f"    Festival: {m['festival']}")
            print(f"    Link: {m['link']}")
            print(f"    Dates: {format_date(m['start'])} — {format_date(m['end'])}")
            print(f"    TMDB ID: {m['movie_id']} | NRW status: {m['nrw_status']}")
            print()
    else:
        print("  None")

    # Section 2: Wall matches
    print(f"\n{'─' * 70}")
    print(f"MATCHES ALREADY ON WALL — {len(wall_matches)} films")
    print(f"{'─' * 70}")
    if wall_matches:
        for m in sorted(wall_matches, key=lambda x: x['festival']):
            status_tag = f"[{m['status'].upper()}]"
            print(f"  {m['nrw_title']:<45} {status_tag}")
            print(f"    Festival: {m['festival']}")
            print(f"    Link: {m['link']}")
            print(f"    Dates: {format_date(m['start'])} — {format_date(m['end'])}")
            print()
    else:
        print("  None")

    # Section 3: Unmatched (not in NRW)
    print(f"\n{'─' * 70}")
    print(f"UNMATCHED ACTIVE FILMS (not in NRW) — {len(unmatched)} films")
    print(f"{'─' * 70}")
    if unmatched:
        # Group by festival
        by_festival = {}
        for u in unmatched:
            by_festival.setdefault(u['festival'], []).append(u)
        for fest in sorted(by_festival.keys()):
            films_list = by_festival[fest]
            print(f"\n  {fest} ({len(films_list)} films):")
            for u in sorted(films_list, key=lambda x: x['eventive_title']):
                status_tag = f"[{u['status'].upper()}]"
                dates = f"{format_date(u['start'])} — {format_date(u['end'])}"
                print(f"    {u['eventive_title']:<40} {status_tag:<10} {dates}")
    else:
        print("  None")

    # Section 4: Summary
    print(f"\n{'─' * 70}")
    print("SUMMARY")
    print(f"{'─' * 70}")
    print(f"  Festivals scanned:     {festivals_scanned}")
    print(f"  Festivals with films:  {festivals_with_films}")
    print(f"  Festivals failed:      {festivals_failed}")
    print(f"  Total films indexed:   {len(all_films)}")
    print(f"  Expired (filtered):    {expired_count}")
    print(f"  Unique active films:   {len(unique_films)}")
    print(f"  Matched (tracking):    {len(tracking_matches)}")
    print(f"  Matched (wall):        {len(wall_matches)}")
    print(f"  Unmatched:             {len(unmatched)}")

    # Save results to metrics
    results = {
        'timestamp': datetime.now().isoformat(),
        'operation': 'eventive_scan',
        'stats': {
            'festivals_scanned': festivals_scanned,
            'festivals_with_films': festivals_with_films,
            'festivals_failed': festivals_failed,
            'total_films_indexed': len(all_films),
            'expired_filtered': expired_count,
            'unique_active': len(unique_films),
            'tracking_matches': len(tracking_matches),
            'wall_matches': len(wall_matches),
            'unmatched': len(unmatched),
        },
        'tracking_matches': tracking_matches,
        'wall_matches': wall_matches,
        'unmatched_sample': unmatched[:50],  # First 50 to keep file size sane
    }

    metrics_path = 'metrics/eventive_scan_run.json'
    os.makedirs('metrics', exist_ok=True)
    with open(metrics_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Full results saved to {metrics_path}")
    print("=" * 70)


if __name__ == '__main__':
    main()
