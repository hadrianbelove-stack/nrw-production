#!/usr/bin/env python3
"""
Add a movie or miniseries to the NRW wall immediately.

Usage:
    /usr/bin/python3 scripts/add_movie.py <tmdb_id> [--date YYYY-MM-DD] [--series]

Arguments:
    tmdb_id:   TMDB movie ID (numeric) or TV series ID (prefix with "tv_", e.g. "tv_12345")
    --date:    Override digital_date (default: today). Use for recovery of older films.
    --series:  Mark as limited_series/miniseries (auto-detected for tv_ IDs)

What this does:
  1. Fetches full TMDB metadata (title, poster, genres, cast/crew, etc.)
  2. Writes entry to movie_tracking.json with status=available
  3. Writes minimal entry to data.json via add_movie_to_site_immediately()
  4. Exits successfully so the caller can run --enrich-id next

Does NOT:
  - Run enrichment (caller must run: python3 generate_data.py --enrich-id <id>)
  - Commit or push (caller handles git)
"""

import sys
import os
import json
import argparse
import requests
from datetime import date as date_cls

# Ensure we can import from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.generator import DataGenerator


def main():
    parser = argparse.ArgumentParser(description='Add a movie to the NRW wall')
    parser.add_argument('tmdb_id', help='TMDB ID (numeric) or tv_NNNN for TV series')
    parser.add_argument('--date', default=None, help='Digital date YYYY-MM-DD (default: today)')
    parser.add_argument('--series', action='store_true', help='Mark as limited series/miniseries')
    args = parser.parse_args()

    tmdb_id = str(args.tmdb_id).strip()
    is_tv = tmdb_id.startswith('tv_')
    digital_date = args.date or date_cls.today().isoformat()
    is_series = args.series or is_tv

    print(f"\n🎬 Adding {'TV series' if is_tv else 'movie'}: {tmdb_id}")
    print(f"   Digital date: {digital_date}")
    print(f"   Content type: {'limited_series' if is_series else 'movie'}")

    # Initialize generator (reads config, sets up TMDB key)
    gen = DataGenerator(enrichment_enabled=False)

    # Fetch TMDB metadata
    print(f"\n📡 Fetching TMDB metadata...")
    if is_tv:
        numeric_id = tmdb_id.replace('tv_', '')
        tmdb_data = gen.get_tv_details(numeric_id)
    else:
        tmdb_data = gen.get_movie_details(tmdb_id)

    if not tmdb_data:
        print(f"❌ Could not fetch TMDB data for {tmdb_id}")
        sys.exit(1)

    title = tmdb_data.get('title') or tmdb_data.get('name', f'Unknown ({tmdb_id})')
    year = None
    release = tmdb_data.get('release_date') or tmdb_data.get('first_air_date', '')
    if release:
        year = int(release[:4])

    poster = None
    if tmdb_data.get('poster_path'):
        poster = f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}"

    genres = [g['name'] for g in tmdb_data.get('genres', [])]
    overview = tmdb_data.get('overview', '')

    # Build providers from TMDB watch/providers
    print(f"   Title: {title} ({year})")
    print(f"   Genres: {', '.join(genres) if genres else 'unknown'}")

    # Fetch current TMDB providers (for tracking entry)
    try:
        if is_tv:
            prov_url = f"https://api.themoviedb.org/3/tv/{numeric_id}/watch/providers"
        else:
            prov_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers"

        prov_resp = requests.get(prov_url, params={'api_key': gen.tmdb_key, 'language': 'en-US'})
        prov_data = prov_resp.json().get('results', {}).get('US', {}) if prov_resp.ok else {}

        rent_providers = [p['provider_name'] for p in prov_data.get('rent', [])]
        buy_providers = [p['provider_name'] for p in prov_data.get('buy', [])]
        stream_providers = [p['provider_name'] for p in prov_data.get('flatrate', [])]
    except Exception as e:
        print(f"   ⚠️  Could not fetch providers: {e}")
        rent_providers, buy_providers, stream_providers = [], [], []

    providers = {
        'rent': rent_providers,
        'buy': buy_providers,
        'streaming': stream_providers,
    }
    print(f"   Providers → rent:{rent_providers}, buy:{buy_providers}, stream:{stream_providers}")

    # Build the tracking entry
    tracking_entry = {
        'title': title,
        'status': 'available',
        'digital_date': digital_date,
        'enriched': False,
        'enrichment_date': None,
        'has_providers': bool(rent_providers or buy_providers or stream_providers),
        'providers': providers,
        'poster': poster,
        'year': year,
        'genres': genres,
        '_discovery_source': 'manual_add',
        '_added_manually': True,
        '_added_at': date_cls.today().isoformat(),
    }
    if is_series:
        tracking_entry['content_type'] = 'limited_series'
    if is_tv:
        tracking_entry['is_tv'] = True

    # Write to movie_tracking.json
    print(f"\n📝 Writing to movie_tracking.json...")
    storage = gen.storage
    tracking_data = storage.load_all_movies() or {'movies': {}, 'schema_version': '2.0'}

    if 'movies' not in tracking_data:
        tracking_data['movies'] = {}

    if tmdb_id in tracking_data['movies']:
        existing = tracking_data['movies'][tmdb_id]
        existing_status = existing.get('status', 'tracking')
        print(f"   ⚠️  Already in tracking: status={existing_status}")
        # Update to available and reset enrichment
        tracking_data['movies'][tmdb_id].update({
            'status': 'available',
            'digital_date': digital_date,
            'enriched': False,
            'enrichment_date': None,
            '_enrichment_attempts': 0,
            '_added_manually': True,
            '_added_at': date_cls.today().isoformat(),
        })
        # Clear any revert flags
        for key in ['_jw_revert_reason', '_jw_reverted_at', '_jw_reverted', '_reverted_from_available']:
            tracking_data['movies'][tmdb_id].pop(key, None)
    else:
        tracking_data['movies'][tmdb_id] = tracking_entry

    storage.atomic_write_json(tracking_data, 'movie_tracking.json', backup=True)
    print(f"   ✅ Saved to tracking")

    # Write to data.json: update existing entry or add new one
    print(f"\n📺 Updating data.json...")
    with open('data.json') as f:
        data = json.load(f)

    # Check if movie already exists in data.json
    existing_index = None
    for i, m in enumerate(data['movies']):
        if str(m.get('id')) == str(tmdb_id):
            existing_index = i
            break

    if existing_index is not None:
        # Movie exists — clean revert flags and reset for re-enrichment
        movie = data['movies'][existing_index]
        revert_keys = ['_jw_reverted', '_jw_revert_reason', '_enrichment_status',
                        '_jw_reverted_at', '_reverted_from_available']
        for key in revert_keys:
            if key in movie:
                print(f"   Cleared {key}")
                del movie[key]
        # Remove status=tracking (available movies shouldn't have this)
        if movie.get('status') == 'tracking':
            del movie['status']
            print(f"   Cleared status=tracking")
        movie['_added_manually'] = True
        movie['_enrichment_attempts'] = 0
        print(f"   ✅ Existing entry cleaned for re-enrichment")
    else:
        # New movie — add minimal entry
        from datetime import datetime
        minimal = {
            'id': tmdb_id,
            'title': title,
            'digital_date': digital_date,
            'year': year,
            'poster': poster,
            'genres': genres,
            'synopsis': overview or None,
            'providers': providers,
            'watch_links': {},
            'links': {'wikipedia': None, 'trailer': None, 'rt': None},
            'bootstrap_date': False,
            'manually_corrected': False,
            'runtime': None,
            'rt_score': None,
            'studio': None,
            'budget': 0,
            'country': None,
            'original_language': None,
            'original_title': title,
            'crew': {'director': None, 'cast': []},
            '_enrichment_status': 'pending',
            '_minimal_entry': True,
            '_added_manually': True,
            '_discovered_at': datetime.utcnow().isoformat(),
            '_discovery_source': 'manual_add',
            '_tmdb_fetch_failed': False,
            'categories': {
                'tier': None, 'is_big_time': False, 'is_indie': False,
                'is_foreign': False, 'is_staff_pick': False, 'is_restoration': False,
                'is_virtual_screening': False, 'is_series': is_series,
                'is_documentary': False, 'auto_categorized': True, 'manual_override': None
            },
            'featured': False,
        }
        if is_series:
            minimal['content_type'] = 'limited_series'

        data['movies'].append(minimal)
        print(f"   ✅ New entry added to data.json")

    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done! Next steps:")
    print(f"   Run:  /usr/bin/python3 generate_data.py --enrich-id {tmdb_id}")
    print(f"   Then: git add data.json movie_tracking.json && NRW_ALLOW_DATA_COMMIT=1 git commit ...")
    return 0


if __name__ == '__main__':
    sys.exit(main())
