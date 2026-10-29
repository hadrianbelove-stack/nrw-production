#!/usr/bin/env python3
"""Copy a downloaded movie file onto the CCCNas Plex library, trigger a scan,
verify Plex picked it up, and (optionally) delete the local original.

Usage:
    python3 scripts/add_to_plex.py <source_file> --title "Title" --year 2026 [--delete-source]

This is the engine behind the /addtoplex command. It does the mechanical
file/API work; picking the right source file and confirming title/year with
the user happens in the command itself.
"""
import argparse
import os
import shutil
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv('.env')

MOVIES_ROOT = '/Volumes/Media/MOVIES'


def die(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    sys.exit(1)


def plex_get(server, token, path, **params):
    params['X-Plex-Token'] = token
    r = requests.get(server.rstrip('/') + path, params=params,
                      headers={'Accept': 'application/json'}, timeout=15)
    r.raise_for_status()
    return r.json()['MediaContainer']


def movie_section_keys(server, token):
    data = plex_get(server, token, '/library/sections')
    return [d['key'] for d in data.get('Directory', []) if d.get('type') == 'movie']


def find_in_library(server, token, keys, title):
    title_lower = title.lower()
    for key in keys:
        data = plex_get(server, token, f'/library/sections/{key}/all')
        for item in data.get('Metadata', []):
            if item.get('title', '').lower() == title_lower:
                return item
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', help='Path to the downloaded movie file')
    ap.add_argument('--title', required=True, help='Clean title, e.g. "Tiny Fugitives"')
    ap.add_argument('--year', required=True, type=int)
    ap.add_argument('--delete-source', action='store_true',
                     help='Delete the local original once Plex confirms it has the file')
    args = ap.parse_args()

    token = os.environ.get('PLEX_TOKEN')
    server = os.environ.get('PLEX_SERVER')
    if not token or not server:
        die('PLEX_TOKEN / PLEX_SERVER not set in .env')

    src = args.source
    if not os.path.isfile(src):
        die(f'source file not found: {src}')

    if not os.path.isdir(MOVIES_ROOT):
        die(f'{MOVIES_ROOT} not mounted — mount the NAS share first')

    ext = os.path.splitext(src)[1]
    folder_name = f'{args.title} ({args.year})'
    dest_dir = os.path.join(MOVIES_ROOT, folder_name)
    dest_path = os.path.join(dest_dir, folder_name + ext)

    if os.path.exists(dest_dir):
        die(f'"{folder_name}" already exists on the NAS — not overwriting. '
            f'Remove it manually first if this is intentional.')

    print(f'Copying to {dest_path} ...')
    os.makedirs(dest_dir)
    shutil.copy2(src, dest_path)

    src_size = os.path.getsize(src)
    dst_size = os.path.getsize(dest_path)
    if src_size != dst_size:
        shutil.rmtree(dest_dir)
        die(f'size mismatch after copy: src={src_size} dst={dst_size}. '
            f'Removed the bad copy from the NAS — source is untouched, nothing to clean up.')
    print(f'OK — {dst_size} bytes, verified.')

    print('Triggering Plex library scan...')
    keys = movie_section_keys(server, token)
    for key in keys:
        plex_get(server, token, f'/library/sections/{key}/refresh')

    print('Waiting for Plex to pick it up (up to 60s)...')
    found = None
    for _ in range(12):
        time.sleep(5)
        found = find_in_library(server, token, keys, args.title)
        if found:
            break

    if not found:
        print('Not showing up in Plex yet after 60s. The file is safely on the NAS at '
              f'{dest_path} — check the Plex app in a minute. Once you see it there, '
              f'delete the source yourself ({src}); this script will not do it blind.')
        return

    print(f'Confirmed in Plex: "{found["title"]}" (ratingKey={found["ratingKey"]})')

    if args.delete_source:
        os.remove(src)
        print(f'Deleted local original: {src}')
    else:
        print('--delete-source not passed; local original left in place.')


if __name__ == '__main__':
    main()
