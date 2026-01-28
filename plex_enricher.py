#!/usr/bin/env python3
"""
Plex Enricher for NRW
Matches NRW movies with your personal Plex library and adds plex links
directly to data.json for use by the website and Apple TV app.

Usage:
    python3 plex_enricher.py           # Refresh and add Plex links to data.json
    python3 plex_enricher.py --dry-run # Show matches without writing file
"""

import json
import os
import sys
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'plex_config.json')
DATA_PATH = os.path.join(SCRIPT_DIR, 'data.json')


def load_config():
    """Load Plex configuration."""
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: {CONFIG_PATH} not found. Create it with your Plex token.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def fetch_plex_library(config):
    """Fetch all movies from Plex library with GUIDs."""
    url = f"{config['server_url']}/library/sections/{config['library_key']}/all?includeGuids=1"
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'X-Plex-Token': config['token']
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('MediaContainer', {}).get('Metadata', [])
    except urllib.error.URLError as e:
        print(f"Error fetching Plex library: {e}")
        sys.exit(1)


def build_plex_mapping(plex_movies):
    """Build TMDB ID -> Plex movie mapping."""
    mapping = {}
    for movie in plex_movies:
        guids = movie.get('Guid', [])
        tmdb_id = None
        imdb_id = None

        for g in guids:
            gid = g.get('id', '')
            if gid.startswith('tmdb://'):
                tmdb_id = gid.replace('tmdb://', '')
            elif gid.startswith('imdb://'):
                imdb_id = gid.replace('imdb://', '')

        if tmdb_id:
            mapping[tmdb_id] = {
                'title': movie.get('title'),
                'year': movie.get('year'),
                'ratingKey': movie.get('ratingKey'),
                'imdb_id': imdb_id,
                'thumb': movie.get('thumb'),
                'duration': movie.get('duration')
            }

    return mapping


def load_nrw_data():
    """Load NRW data.json."""
    if not os.path.exists(DATA_PATH):
        print(f"Error: {DATA_PATH} not found.")
        sys.exit(1)
    with open(DATA_PATH) as f:
        return json.load(f)


def enrich_movies_with_plex(nrw_data, plex_mapping, config):
    """Add Plex links directly to NRW movies that match Plex library."""
    server_id = config.get('client_identifier', '')
    matched_titles = []

    for movie in nrw_data.get('movies', []):
        tmdb_id = str(movie.get('id'))
        if tmdb_id in plex_mapping:
            plex_info = plex_mapping[tmdb_id]
            rating_key = plex_info['ratingKey']

            # Generate URLs for different platforms
            # Web: opens in Plex Web
            web_url = f"https://app.plex.tv/desktop/#!/server/{server_id}/details?key=%2Flibrary%2Fmetadata%2F{rating_key}"
            # Deep link: opens in Plex apps (iOS, tvOS, Android)
            deep_link = f"plex://play/?metadataKey=%2Flibrary%2Fmetadata%2F{rating_key}&server={server_id}"

            # Add plex info directly to movie object
            movie['plex'] = {
                'web_url': web_url,
                'deep_link': deep_link,
                'ratingKey': rating_key
            }
            matched_titles.append(movie.get('title'))
        else:
            # Remove stale plex data if movie no longer in Plex
            if 'plex' in movie:
                del movie['plex']

    return matched_titles


def main():
    dry_run = '--dry-run' in sys.argv

    print("Plex Enricher for NRW")
    print("=" * 40)

    # Load config
    print("Loading config...")
    config = load_config()
    print(f"  Server: {config.get('server_name', 'unknown')}")

    # Fetch Plex library
    print("Fetching Plex library...")
    plex_movies = fetch_plex_library(config)
    print(f"  Found {len(plex_movies)} movies in Plex")

    # Build mapping
    print("Building TMDB mapping...")
    plex_mapping = build_plex_mapping(plex_movies)
    print(f"  {len(plex_mapping)} movies have TMDB IDs")

    # Load NRW data
    print("Loading NRW data...")
    nrw_data = load_nrw_data()
    nrw_count = len(nrw_data.get('movies', []))
    print(f"  Found {nrw_count} movies in NRW")

    # Enrich movies with Plex links
    print("Adding Plex links to movies...")
    matched_titles = enrich_movies_with_plex(nrw_data, plex_mapping, config)
    print(f"  {len(matched_titles)} NRW movies found in your Plex library")

    # Show matches
    if matched_titles:
        print("\nMatched movies:")
        for title in matched_titles:
            print(f"  - {title}")

    # Write output directly to data.json
    if not dry_run:
        with open(DATA_PATH, 'w') as f:
            json.dump(nrw_data, f, indent=2)
        print(f"\nUpdated {DATA_PATH} with Plex links")
    else:
        print("\n[Dry run - no file written]")


if __name__ == '__main__':
    main()
