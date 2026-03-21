#!/usr/bin/env python3
"""
Trailer Uploader — Phase 2 of In-App Trailer Playback
Uploads downloaded trailer MP4 files to Backblaze B2 for CDN delivery.

Usage:
    python3 scripts/trailer_uploader.py                # Upload all local trailers
    python3 scripts/trailer_uploader.py --limit 5      # Upload first 5 only (test)
    python3 scripts/trailer_uploader.py --dry-run       # Show what would be uploaded

Requires: B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME in .env
Requires Python 3.10+ (matches trailer_downloader.py requirement).
"""

import argparse
import json
import os
import sys
import time

from b2sdk.v2 import B2Api, InMemoryAccountInfo

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
MEDIA_DIR = os.path.join(PROJECT_ROOT, 'media', 'trailers')
ENV_FILE = os.path.join(PROJECT_ROOT, '.env')


def load_env():
    """Load .env file into environment variables (skips if not found — CI uses env vars directly)."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


def get_b2_api():
    """Authenticate with Backblaze B2 and return API + bucket."""
    key_id = os.environ.get('B2_KEY_ID')
    app_key = os.environ.get('B2_APPLICATION_KEY')
    bucket_name = os.environ.get('B2_BUCKET_NAME')

    if not all([key_id, app_key, bucket_name]):
        raise RuntimeError('Missing B2 credentials. Set B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME as env vars or in .env')

    info = InMemoryAccountInfo()
    api = B2Api(info)
    api.authorize_account('production', key_id, app_key)
    bucket = api.get_bucket_by_name(bucket_name)

    return api, bucket


def get_remote_files(bucket):
    """Get set of filenames already in the B2 bucket."""
    remote_files = set()
    for file_version, _ in bucket.ls(latest_only=True):
        remote_files.add(file_version.file_name)
    return remote_files


def get_local_files():
    """Get list of local MP4 files ready for upload."""
    if not os.path.exists(MEDIA_DIR):
        return []
    files = []
    for f in sorted(os.listdir(MEDIA_DIR)):
        if f.endswith('.mp4'):
            path = os.path.join(MEDIA_DIR, f)
            size = os.path.getsize(path)
            files.append({'name': f, 'path': path, 'size': size})
    return files


def get_bucket_url(api, bucket):
    """Get the base URL for public file access."""
    # B2 native URL format: https://f005.backblazeb2.com/file/BUCKET_NAME/
    download_url = api.account_info.get_download_url()
    return f'{download_url}/file/{bucket.name}'


def upload_file(bucket, local_path, remote_name):
    """Upload a single file to B2. Returns the file URL."""
    file_info = bucket.upload_local_file(
        local_file=local_path,
        file_name=remote_name,
        content_type='video/mp4',
    )
    return file_info


def main():
    parser = argparse.ArgumentParser(description='Upload trailer MP4s to Backblaze B2')
    parser.add_argument('--limit', type=int, default=0, help='Max files to upload (0 = all)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be uploaded')
    args = parser.parse_args()

    # Load credentials
    load_env()

    # Get local files
    local_files = get_local_files()
    if not local_files:
        print(f'No MP4 files found in {MEDIA_DIR}')
        return

    print(f'Found {len(local_files)} local trailer files')

    if args.dry_run:
        total_size = sum(f['size'] for f in local_files)
        print(f'Dry run: would upload {len(local_files)} files ({total_size / (1024**3):.2f} GB)')
        return

    # Connect to B2
    print('Connecting to Backblaze B2...')
    api, bucket = get_b2_api()
    bucket_url = get_bucket_url(api, bucket)
    print(f'Bucket: {bucket.name}')
    print(f'URL: {bucket_url}')

    # Check what's already uploaded
    print('Checking existing files in bucket...')
    remote_files = get_remote_files(bucket)
    print(f'Already in bucket: {len(remote_files)} files')

    # Filter to files that need uploading
    to_upload = [f for f in local_files if f['name'] not in remote_files]
    print(f'New files to upload: {len(to_upload)}')

    if args.limit > 0:
        to_upload = to_upload[:args.limit]
        print(f'Limiting to {args.limit}')

    if not to_upload:
        print('Nothing to upload — all files already in bucket.')
        return

    # Upload loop
    uploaded = 0
    failed = 0
    total = len(to_upload)

    for i, file_info in enumerate(to_upload, 1):
        size_mb = file_info['size'] / (1024 * 1024)
        print(f'[{i}/{total}] Uploading {file_info["name"]} ({size_mb:.1f}MB)...', end=' ', flush=True)

        try:
            upload_file(bucket, file_info['path'], file_info['name'])
            print('done')
            uploaded += 1
        except Exception as e:
            print(f'FAILED: {str(e)[:100]}')
            failed += 1

    # Summary
    print('\n' + '=' * 60)
    print('UPLOAD REPORT')
    print('=' * 60)
    print(f'  Uploaded:         {uploaded}')
    print(f'  Already existed:  {len(local_files) - len(to_upload)}')
    print(f'  Failed:           {failed}')
    print(f'  Bucket URL:       {bucket_url}')
    print('=' * 60)

    # Show example URL
    if uploaded > 0:
        example = to_upload[0]['name']
        print(f'\nExample trailer URL:')
        print(f'  {bucket_url}/{example}')


if __name__ == '__main__':
    main()
