#!/usr/bin/env python3
"""
Trailer Pipeline — Orchestrates trailer hosting for NRW in-app playback.

Ties together downloading (trailer_downloader.py), uploading (trailer_uploader.py),
URL stamping into data.json, and rotation (storage cap enforcement).

Usage:
    python3 scripts/trailer_pipeline.py stamp              # Backfill: stamp URLs for uploaded trailers
    python3 scripts/trailer_pipeline.py stamp --dry-run     # Preview what would be stamped
    python3 scripts/trailer_pipeline.py host --limit 5      # Download+upload for 5 missing trailers
    python3 scripts/trailer_pipeline.py rotate --dry-run     # Preview rotation deletions
    python3 scripts/trailer_pipeline.py full                 # Full pass: host new -> stamp -> rotate

Requires: B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME in .env
Requires Python 3.10+ (matches trailer_downloader.py requirement).
"""

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_JSON = os.path.join(PROJECT_ROOT, 'data.json')
CONFIG_YAML = os.path.join(PROJECT_ROOT, 'config.yaml')
MEDIA_DIR = os.path.join(PROJECT_ROOT, 'media', 'trailers')

# Add project root to path for imports
sys.path.insert(0, SCRIPT_DIR)

from trailer_uploader import load_env, get_b2_api, get_remote_files, upload_file, get_bucket_url
from trailer_downloader import download_trailer, extract_youtube_id

BAD_URLS_FILE = os.path.join(PROJECT_ROOT, 'cache', 'bad_trailer_urls.json')


def load_bad_urls():
    """Load the bad trailer URL blocklist."""
    if os.path.exists(BAD_URLS_FILE):
        with open(BAD_URLS_FILE, 'r') as f:
            return json.load(f)
    return {}


def record_bad_url(youtube_url, title, year, reason):
    """Record a YouTube URL that failed download in the blocklist."""
    video_id = extract_youtube_id(youtube_url)
    if not video_id:
        return
    bad_urls = load_bad_urls()
    existing = bad_urls.get(video_id, {})
    bad_urls[video_id] = {
        'title': title,
        'year': str(year),
        'reason': reason,
        'url': youtube_url,
        'recorded_at': existing.get('recorded_at', datetime.now().isoformat()),
        'last_failed': datetime.now().isoformat(),
    }
    os.makedirs(os.path.dirname(BAD_URLS_FILE), exist_ok=True)
    with open(BAD_URLS_FILE, 'w') as f:
        json.dump(bad_urls, f, indent=2)


def rediscover_trailer_url(title, year, bad_url):
    """Try to find an alternative trailer URL using Gemini/YouTube search.
    Returns a new YouTube URL different from bad_url, or None."""
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from gemini_scraper import HybridYouTubeFinder
        finder = HybridYouTubeFinder(cache_file=os.path.join(PROJECT_ROOT, 'cache', 'youtube_trailer_cache.json'))
        new_url = finder.find_trailer(title, year)
        if new_url and new_url != bad_url:
            return new_url
        # If Gemini returned the same URL or nothing, try broad Playwright search
        scraper = finder._get_playwright_finder()
        if scraper and hasattr(scraper, 'find_trailer_broad'):
            broad_url = scraper.find_trailer_broad(title, year)
            if broad_url and broad_url != bad_url:
                return broad_url
    except Exception as e:
        print(f'    Re-discovery error: {e}')
    return None


def update_trailer_url_in_data(movie_id, new_url):
    """Update links.trailer in data.json for a specific movie."""
    with open(DATA_JSON, 'r') as f:
        data = json.load(f)
    for movie in data.get('movies', []):
        if str(movie.get('id', '')) == str(movie_id):
            movie.setdefault('links', {})['trailer'] = new_url
            safe_write_json(DATA_JSON, data)
            print(f'    Updated data.json trailer URL for {movie.get("title", movie_id)}')
            return True
    return False


def load_config():
    """Load trailer_hosting config from config.yaml."""
    import yaml
    with open(CONFIG_YAML, 'r') as f:
        config = yaml.safe_load(f)
    return config.get('trailer_hosting', {})


def safe_write_json(filepath, data):
    """Write JSON with atomic backup (same pattern as generator.py)."""
    backup_path = f"{filepath}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if os.path.exists(filepath):
        shutil.copy2(filepath, backup_path)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    # Clean up backup on success
    if os.path.exists(backup_path):
        os.remove(backup_path)


def get_b2_connection():
    """Authenticate with B2, return (api, bucket, bucket_url)."""
    load_env()
    api, bucket = get_b2_api()
    bucket_url = get_bucket_url(api, bucket)
    return api, bucket, bucket_url


def get_hosted_trailer_ids(bucket):
    """Get set of TMDB IDs that have trailers in B2."""
    remote_files = get_remote_files(bucket)
    ids = set()
    for filename in remote_files:
        if filename.endswith('.mp4'):
            ids.add(filename[:-4])  # Strip .mp4 suffix
    return ids


def stamp_trailer_hosted_urls(dry_run=False):
    """
    Stamp trailer_hosted URLs into data.json for all movies with trailers in B2.
    Idempotent — safe to run repeatedly.

    Returns: {'stamped': int, 'already_had': int, 'no_trailer_in_b2': int}
    """
    config = load_config()
    bucket_url = config.get('bucket_url', '')

    if not bucket_url:
        print('ERROR: No bucket_url in config.yaml trailer_hosting section')
        return {'stamped': 0, 'already_had': 0, 'no_trailer_in_b2': 0}

    # Connect to B2 and get hosted IDs
    print('Connecting to B2...')
    try:
        api, bucket, _ = get_b2_connection()
        hosted_ids = get_hosted_trailer_ids(bucket)
    except Exception as e:
        print(f'WARNING: B2 connection failed ({type(e).__name__}: {str(e)[:100]})')
        print('Skipping stamp — YouTube trailer URLs remain as fallback.')
        return {'stamped': 0, 'already_had': 0, 'no_trailer_in_b2': 0}
    print(f'Found {len(hosted_ids)} trailers in B2 bucket')

    # Load data.json
    with open(DATA_JSON, 'r') as f:
        data = json.load(f)

    stats = {'stamped': 0, 'already_had': 0, 'no_trailer_in_b2': 0, 'stale_cleaned': 0}

    for movie in data.get('movies', []):
        movie_id = str(movie.get('id', ''))
        links = movie.get('links', {})

        if links.get('trailer_hosted'):
            # Verify existing URL — clean up if the B2 file was rotated out
            if movie_id in hosted_ids:
                stats['already_had'] += 1
            else:
                if dry_run:
                    print(f'  Would clean stale URL: {movie.get("title", movie_id)}')
                else:
                    links.pop('trailer_hosted', None)
                stats['stale_cleaned'] += 1
            continue

        # Check if this movie's trailer is in B2
        if movie_id in hosted_ids:
            hosted_url = f'{bucket_url}/{movie_id}.mp4'
            if dry_run:
                print(f'  Would stamp: {movie.get("title", movie_id)} -> {hosted_url}')
            else:
                if 'links' not in movie:
                    movie['links'] = {}
                movie['links']['trailer_hosted'] = hosted_url
            stats['stamped'] += 1
        else:
            stats['no_trailer_in_b2'] += 1

    # Save data.json
    changes = stats['stamped'] + stats['stale_cleaned']
    if not dry_run and changes > 0:
        safe_write_json(DATA_JSON, data)
        print(f'Saved data.json: {stats["stamped"]} stamped, {stats["stale_cleaned"]} stale cleaned')

    return stats


def download_and_upload_trailer(movie_id, title, year, youtube_url, bucket, bucket_url, clean_after_upload=False, cookies_browser=None, rediscover_on_failure=True):
    """
    Download a trailer from YouTube and upload to B2.
    Returns (hosted_url, new_trailer_url) on success, (None, None) on failure.
    new_trailer_url is set only if re-discovery found a different URL.
    """
    video_id = extract_youtube_id(youtube_url)
    if not video_id:
        print(f'    Could not extract YouTube ID from {youtube_url}')
        return None, None

    # Build the dict that download_trailer() expects
    movie_dict = {
        'id': str(movie_id),
        'title': title,
        'year': year,
        'trailer_url': youtube_url,
        'video_id': video_id,
    }

    # Download
    result = download_trailer(movie_dict, cookies_browser=cookies_browser)
    status = result['status']

    if status == 'skipped_exists':
        # Already downloaded locally, just need to upload
        pass
    elif status == 'downloaded':
        pass
    else:
        print(f'    Download: {status} ({result["detail"]})')
        # Only blocklist content-specific failures (not bot detection or transient errors)
        # skipped_age_restricted covers both real age gates AND bot detection, so skip it
        blocklist_statuses = ('skipped_region_locked', 'skipped_unavailable')
        if status in blocklist_statuses:
            record_bad_url(youtube_url, title, year, status)
        if rediscover_on_failure:
            print(f'    Re-discovering trailer for {title} ({year})...')
            new_url = rediscover_trailer_url(title, year, youtube_url)
            if new_url:
                print(f'    Found alternative: {new_url}')
                hosted_url, _ = download_and_upload_trailer(
                    movie_id, title, year, new_url, bucket, bucket_url,
                    clean_after_upload=clean_after_upload,
                    cookies_browser=cookies_browser,
                    rediscover_on_failure=False,  # Prevent recursion
                )
                if hosted_url:
                    return hosted_url, new_url
            else:
                print(f'    No alternative found for {title} ({year})')
        return None, None

    # Upload to B2
    local_path = os.path.join(MEDIA_DIR, f'{movie_id}.mp4')
    if not os.path.exists(local_path):
        print(f'    No local file at {local_path}')
        return None, None

    remote_name = f'{movie_id}.mp4'
    try:
        upload_file(bucket, local_path, remote_name)
        hosted_url = f'{bucket_url}/{remote_name}'
        if clean_after_upload and os.path.exists(local_path):
            os.remove(local_path)
            print(f'    Cleaned local: {local_path}')
        return hosted_url, None
    except Exception as e:
        print(f'    Upload failed: {str(e)[:100]}')
        return None, None


def host_new_trailers(movie_ids=None, limit=0, dry_run=False, cookies_browser=None):
    """
    Download and upload trailers for movies that have links.trailer but no links.trailer_hosted.

    Args:
        movie_ids: Optional list of specific TMDB IDs to process. None = all missing.
        limit: Max number to process (0 = all).
        dry_run: Preview without downloading/uploading.

    Returns: {'hosted': int, 'failed': int, 'skipped': int}
    """
    config = load_config()
    bucket_url = config.get('bucket_url', '')
    max_hosted = config.get('max_hosted', 200)
    # Default to Safari cookies for age-restricted content (overridable via CLI --cookies)
    if cookies_browser is None:
        cookies_browser = config.get('cookies_browser', 'safari')

    # Load data.json
    with open(DATA_JSON, 'r') as f:
        data = json.load(f)

    # Only consider the most recent N movies (matches rotation cap).
    all_movies = data.get('movies', [])
    if movie_ids:
        scope = all_movies
    else:
        # Sort by digital_date descending — data.json order is NOT guaranteed
        # (editorial overrides can reorder it)
        sorted_movies = sorted(all_movies, key=lambda m: m.get('digital_date', ''), reverse=True)
        scope = sorted_movies[:max_hosted]

    # Find movies needing hosting
    to_host = []
    for movie in scope:
        movie_id = str(movie.get('id', ''))
        links = movie.get('links', {})
        trailer_url = links.get('trailer', '')

        # Skip if no YouTube trailer or already hosted
        if not trailer_url or links.get('trailer_hosted'):
            continue

        # Skip YouTube search URLs (not actual trailers)
        if 'search_query=' in trailer_url:
            continue

        # Filter to specific IDs if provided
        if movie_ids and movie_id not in [str(mid) for mid in movie_ids]:
            continue

        to_host.append({
            'id': movie_id,
            'title': movie.get('title', 'Unknown'),
            'year': movie.get('year', ''),
            'trailer_url': trailer_url,
        })

    if limit > 0:
        to_host = to_host[:limit]

    print(f'Movies to host: {len(to_host)}')

    if dry_run:
        for m in to_host:
            print(f'  Would host: {m["title"]} ({m["year"]}) - {m["trailer_url"]}')
        return {'hosted': 0, 'failed': 0, 'skipped': len(to_host)}

    # Connect to B2
    print('Connecting to B2...')
    try:
        api, bucket, b2_bucket_url = get_b2_connection()
    except Exception as e:
        print(f'WARNING: B2 connection failed ({type(e).__name__}: {str(e)[:100]})')
        print('Skipping hosting — YouTube trailer URLs remain as fallback.')
        return {'hosted': 0, 'failed': 0, 'skipped': len(to_host)}
    # Use config bucket_url if available, else B2 native URL
    url_base = bucket_url or b2_bucket_url
    clean_after = config.get('clean_local_after_upload', False)

    stats = {'hosted': 0, 'failed': 0, 'skipped': 0}
    total = len(to_host)
    bad_urls = load_bad_urls()
    BLACKLIST_GRACE_DAYS = 3

    for i, movie in enumerate(to_host, 1):
        print(f'[{i}/{total}] {movie["title"]} ({movie["year"]})...')

        # Skip URLs blacklisted for more than 3 days (transient issues resolve sooner)
        video_id = extract_youtube_id(movie['trailer_url'])
        if video_id and video_id in bad_urls:
            recorded = bad_urls[video_id].get('recorded_at', '')
            if recorded:
                days_ago = (datetime.now() - datetime.fromisoformat(recorded)).days
                if days_ago >= BLACKLIST_GRACE_DAYS:
                    print(f'    Skipped: blacklisted {days_ago} days ago ({bad_urls[video_id].get("reason", "unknown")})')
                    stats['skipped'] += 1
                    continue

        hosted_url, new_trailer_url = download_and_upload_trailer(
            movie['id'], movie['title'], movie['year'],
            movie['trailer_url'], bucket, url_base,
            clean_after_upload=clean_after,
            cookies_browser=cookies_browser
        )

        if hosted_url:
            stats['hosted'] += 1
            print(f'    Hosted: {hosted_url}')
            # If re-discovery found a better URL, update data.json
            if new_trailer_url:
                update_trailer_url_in_data(movie['id'], new_trailer_url)
        else:
            stats['failed'] += 1

        # Rate limit between downloads
        if i < total:
            time.sleep(2)

    # Note: data.json is NOT modified here. CI's `stamp` command handles
    # writing trailer_hosted URLs into data.json based on what's in B2.
    # This avoids merge conflicts when host runs locally and CI runs remotely.

    return stats


def rotate_trailers(dry_run=False):
    """
    Enforce the max_hosted cap by deleting oldest trailers from B2.

    Returns: {'deleted': int, 'current_count': int, 'max_hosted': int}
    """
    config = load_config()
    max_hosted = config.get('max_hosted', 200)

    # Connect to B2
    print('Connecting to B2...')
    try:
        api, bucket, bucket_url = get_b2_connection()
    except Exception as e:
        print(f'WARNING: B2 connection failed ({type(e).__name__}: {str(e)[:100]})')
        print('Skipping rotation — cannot reach B2.')
        return {'deleted': 0, 'current_count': 0, 'max_hosted': max_hosted}

    # Get all files in bucket (with file version info for deletion)
    remote_files = {}
    for file_version, _ in bucket.ls(latest_only=True):
        if file_version.file_name.endswith('.mp4'):
            tmdb_id = file_version.file_name[:-4]
            remote_files[tmdb_id] = file_version

    current_count = len(remote_files)
    print(f'Current trailers in B2: {current_count}')
    print(f'Max hosted: {max_hosted}')

    if current_count <= max_hosted:
        print('Under cap — nothing to rotate.')
        return {'deleted': 0, 'current_count': current_count, 'max_hosted': max_hosted}

    excess = current_count - max_hosted
    print(f'Over cap by {excess} — need to delete {excess} trailers')

    # Load data.json to get digital_date for sorting
    with open(DATA_JSON, 'r') as f:
        data = json.load(f)

    # Build map: tmdb_id -> digital_date
    date_map = {}
    for movie in data.get('movies', []):
        movie_id = str(movie.get('id', ''))
        digital_date = movie.get('digital_date', '')
        if movie_id in remote_files:
            date_map[movie_id] = digital_date or '1900-01-01'  # No date = very old

    # Sort by digital_date ascending (oldest first)
    sorted_ids = sorted(date_map.keys(), key=lambda mid: date_map[mid])

    # Select the oldest ones for deletion
    to_delete = sorted_ids[:excess]

    if dry_run:
        print(f'\nWould delete {len(to_delete)} trailers:')
        for tmdb_id in to_delete:
            title = 'Unknown'
            for m in data.get('movies', []):
                if str(m.get('id', '')) == tmdb_id:
                    title = m.get('title', 'Unknown')
                    break
            print(f'  {tmdb_id} - {title} (digital_date: {date_map.get(tmdb_id, "?")})')
        return {'deleted': 0, 'current_count': current_count, 'max_hosted': max_hosted}

    # Delete from B2
    deleted = 0
    for tmdb_id in to_delete:
        file_version = remote_files[tmdb_id]
        try:
            bucket.delete_file_version(file_version.id_, file_version.file_name)
            deleted += 1
            print(f'  Deleted: {tmdb_id}.mp4 (date: {date_map.get(tmdb_id, "?")})')
        except Exception as e:
            print(f'  Failed to delete {tmdb_id}.mp4: {str(e)[:100]}')

    # Remove trailer_hosted from data.json for deleted trailers
    deleted_set = set(to_delete[:deleted])
    for movie in data.get('movies', []):
        if str(movie.get('id', '')) in deleted_set:
            movie.get('links', {}).pop('trailer_hosted', None)

    if deleted > 0:
        safe_write_json(DATA_JSON, data)
        print(f'Saved data.json — removed trailer_hosted from {deleted} movies')

    return {'deleted': deleted, 'current_count': current_count - deleted, 'max_hosted': max_hosted}


def clean_local_trailers(dry_run=False):
    """
    Delete ALL local MP4 files in media/trailers/.
    Local files are staging copies — no reason to keep them after upload.

    Returns: {'deleted': int, 'total_local': int}
    """
    if not os.path.isdir(MEDIA_DIR):
        print('No media/trailers/ directory found.')
        return {'deleted': 0, 'total_local': 0}

    local_files = [f for f in os.listdir(MEDIA_DIR) if f.endswith('.mp4')]
    if not local_files:
        print('No local MP4 files to clean.')
        return {'deleted': 0, 'total_local': 0}

    print(f'Local trailer files: {len(local_files)}')

    stats = {'deleted': 0, 'total_local': len(local_files)}
    total_bytes = 0

    for filename in sorted(local_files):
        local_path = os.path.join(MEDIA_DIR, filename)
        file_size = os.path.getsize(local_path)
        if dry_run:
            print(f'  Would delete: {filename} ({file_size / 1024 / 1024:.1f} MB)')
        else:
            os.remove(local_path)
            print(f'  Deleted: {filename} ({file_size / 1024 / 1024:.1f} MB)')
        total_bytes += file_size
        stats['deleted'] += 1

    action = 'Would free' if dry_run else 'Freed'
    print(f'\n{action}: {total_bytes / 1024 / 1024 / 1024:.2f} GB')

    return stats


def main():
    parser = argparse.ArgumentParser(description='Trailer hosting pipeline')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # stamp
    stamp_parser = subparsers.add_parser('stamp', help='Stamp trailer_hosted URLs into data.json')
    stamp_parser.add_argument('--dry-run', action='store_true', help='Preview without writing')

    # host
    host_parser = subparsers.add_parser('host', help='Download and upload missing trailers')
    host_parser.add_argument('--limit', type=int, default=0, help='Max trailers to process (0 = all)')
    host_parser.add_argument('--movie-ids', nargs='+', help='Specific TMDB IDs to process')
    host_parser.add_argument('--dry-run', action='store_true', help='Preview without downloading/uploading')
    host_parser.add_argument('--cookies', type=str, default=None, metavar='BROWSER',
                             help='Browser for YouTube cookies (e.g. chrome, safari)')

    # rotate
    rotate_parser = subparsers.add_parser('rotate', help='Delete oldest trailers to stay under cap')
    rotate_parser.add_argument('--dry-run', action='store_true', help='Preview without deleting')

    # clean_local
    clean_parser = subparsers.add_parser('clean_local', help='Delete local MP4s confirmed in B2')
    clean_parser.add_argument('--dry-run', action='store_true', help='Preview without deleting')

    # full
    full_parser = subparsers.add_parser('full', help='Full pipeline: host -> stamp -> rotate -> clean')
    full_parser.add_argument('--dry-run', action='store_true', help='Preview all steps')
    full_parser.add_argument('--limit', type=int, default=0, help='Max new trailers to host (0 = all)')
    full_parser.add_argument('--cookies', type=str, default=None, metavar='BROWSER',
                             help='Browser for YouTube cookies (e.g. chrome, safari)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    print(f'=== Trailer Pipeline: {args.command} ===')
    print()

    if args.command == 'stamp':
        stats = stamp_trailer_hosted_urls(dry_run=args.dry_run)
        print(f'\nStamp results:')
        print(f'  Stamped:          {stats["stamped"]}')
        print(f'  Already had URL:  {stats["already_had"]}')
        print(f'  Stale cleaned:    {stats["stale_cleaned"]}')
        print(f'  Not in B2:        {stats["no_trailer_in_b2"]}')

    elif args.command == 'host':
        stats = host_new_trailers(
            movie_ids=args.movie_ids,
            limit=args.limit,
            dry_run=args.dry_run,
            cookies_browser=args.cookies,
        )
        print(f'\nHost results:')
        print(f'  Hosted:   {stats["hosted"]}')
        print(f'  Failed:   {stats["failed"]}')
        print(f'  Skipped:  {stats["skipped"]}')

    elif args.command == 'rotate':
        stats = rotate_trailers(dry_run=args.dry_run)
        print(f'\nRotation results:')
        print(f'  Deleted:        {stats["deleted"]}')
        print(f'  Current count:  {stats["current_count"]}')
        print(f'  Max hosted:     {stats["max_hosted"]}')

    elif args.command == 'clean_local':
        stats = clean_local_trailers(dry_run=args.dry_run)
        print(f'\nClean local results:')
        print(f'  Deleted:      {stats["deleted"]}')
        print(f'  Total local:  {stats["total_local"]}')

    elif args.command == 'full':
        # Step 1: Host new trailers
        print('--- Step 1: Host new trailers ---')
        host_stats = host_new_trailers(limit=args.limit, dry_run=args.dry_run, cookies_browser=args.cookies)
        print()

        # Step 2: Stamp any uploaded-but-not-stamped trailers
        print('--- Step 2: Stamp URLs ---')
        stamp_stats = stamp_trailer_hosted_urls(dry_run=args.dry_run)
        print()

        # Step 3: Rotate if over cap
        print('--- Step 3: Rotate ---')
        rotate_stats = rotate_trailers(dry_run=args.dry_run)
        print()

        # Step 4: Clean local files confirmed in B2
        print('--- Step 4: Clean local ---')
        clean_stats = clean_local_trailers(dry_run=args.dry_run)
        print()

        # Summary
        print('=' * 60)
        print('FULL PIPELINE SUMMARY')
        print('=' * 60)
        print(f'  New trailers hosted:  {host_stats["hosted"]}')
        print(f'  URLs stamped:         {stamp_stats["stamped"]}')
        print(f'  Stale URLs cleaned:   {stamp_stats["stale_cleaned"]}')
        print(f'  Trailers rotated:     {rotate_stats["deleted"]}')
        print(f'  Local files cleaned:  {clean_stats["deleted"]}')
        print(f'  Current in B2:        {rotate_stats["current_count"]}')
        print('=' * 60)


if __name__ == '__main__':
    main()
