#!/opt/homebrew/bin/python3.11
"""
One-shot backfill: download English subtitles for foreign-language trailers
that are already hosted in B2 but were enriched before the subtitle feature existed.

Saves progress to cache/backfill_subs_progress.json so it's resumable.
Run with --dry-run to preview without uploading anything.
"""

import argparse
import json
import os
import re
import sys
import time

import yt_dlp
from b2sdk.v2 import B2Api, InMemoryAccountInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_JSON = os.path.join(PROJECT_ROOT, 'data.json')
MEDIA_DIR = os.path.join(PROJECT_ROOT, 'media', 'trailers')
ENV_FILE = os.path.join(PROJECT_ROOT, '.env')
PROGRESS_FILE = os.path.join(PROJECT_ROOT, 'cache', 'backfill_subs_progress.json')


def load_env():
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_b2(bucket_name):
    info = InMemoryAccountInfo()
    api = B2Api(info)
    api.authorize_account('production', os.environ['B2_KEY_ID'], os.environ['B2_APPLICATION_KEY'])
    bucket = api.get_bucket_by_name(bucket_name)
    bucket_url = f"{api.account_info.get_download_url()}/file/{bucket_name}"
    return bucket, bucket_url


def clean_vtt(content):
    content = re.sub(r'<\d{2}:\d{2}:\d{2}\.\d{3}>', '', content)
    content = re.sub(r'</?c>', '', content)
    content = re.sub(r' align:start position:\d+%', '', content)
    return content


def find_candidates(movies):
    candidates = []
    for m in movies:
        if not isinstance(m, dict):
            continue
        lang = m.get('original_language', 'en')
        if not lang or lang == 'en':
            continue
        links = m.get('links', {}) or {}
        hosted = links.get('trailer_hosted')
        yt = links.get('trailer')
        subs = links.get('trailer_hosted_subs')
        if hosted and yt and not subs and 'youtube.com' in str(yt):
            candidates.append({
                'id': str(m.get('id', '')),
                'title': m.get('title', ''),
                'year': m.get('year', ''),
                'lang': lang,
                'yt_url': yt,
            })
    return candidates


def download_subs_only(movie_id, yt_url, dry_run=False):
    """Download English subtitles only (skip video). Returns vtt_path or None."""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    canonical_vtt = os.path.join(MEDIA_DIR, f'{movie_id}.en.vtt')

    if os.path.exists(canonical_vtt):
        return canonical_vtt  # already have it locally

    if dry_run:
        return None

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        # catch manual subs, auto-generated CC, and all English regional variants
        'subtitleslangs': ['en', 'en-orig', 'en-US', 'en-GB'],
        'subtitlesformat': 'vtt',
        'outtmpl': {
            'default': os.path.join(MEDIA_DIR, f'{movie_id}.%(ext)s'),
            'subtitle': os.path.join(MEDIA_DIR, f'{movie_id}.%(ext)s'),
        },
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'cookiesfrombrowser': ('safari',),
        'js_runtimes': {'node': {}},
        'remote_components': ['ejs:github'],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([yt_url])
    except Exception:
        pass

    # Find any English VTT variant that was created (en.vtt, en-orig.vtt, en-US.vtt, etc.)
    # Prefer canonical en.vtt; otherwise take the first English variant and rename it
    if os.path.exists(canonical_vtt):
        return canonical_vtt

    for f in sorted(os.listdir(MEDIA_DIR)):
        if f.startswith(f'{movie_id}.') and f.endswith('.vtt') and 'en' in f.lower():
            found = os.path.join(MEDIA_DIR, f)
            os.rename(found, canonical_vtt)
            return canonical_vtt

    return None


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {'done': [], 'failed': [], 'no_subs': []}


def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()

    load_env()

    with open(DATA_JSON) as f:
        data = json.load(f)
    movies = data.get('movies', [])

    candidates = find_candidates(movies)
    print(f'Candidates: {len(candidates)} foreign films missing subs')

    if not candidates:
        print('Nothing to do.')
        return

    if not args.dry_run:
        bucket_name = os.environ.get('B2_BUCKET_NAME', '')
        bucket, bucket_url = get_b2(bucket_name)

    progress = load_progress()
    already_done = set(progress['done'])
    already_failed = set(progress['failed'])
    already_no_subs = set(progress['no_subs'])

    stamped = 0
    processed = 0

    for c in candidates:
        movie_id = c['id']

        if movie_id in already_done:
            continue
        if movie_id in already_no_subs:
            continue

        if args.limit and processed >= args.limit:
            break

        print(f"  [{c['lang']}] {c['title']} ({c['year']}) — {movie_id}")
        processed += 1

        vtt_path = download_subs_only(movie_id, c['yt_url'], dry_run=args.dry_run)

        if not vtt_path:
            print(f'    no subs available')
            progress['no_subs'].append(movie_id)
            save_progress(progress)
            time.sleep(3)
            continue

        # Clean the VTT
        with open(vtt_path) as f:
            cleaned = clean_vtt(f.read())
        with open(vtt_path, 'w') as f:
            f.write(cleaned)

        if args.dry_run:
            print(f'    [dry-run] would upload {movie_id}.en.vtt and stamp data.json')
            progress['done'].append(movie_id)
            save_progress(progress)
            continue

        # Upload to B2
        remote_name = f'{movie_id}.en.vtt'
        try:
            bucket.upload_local_file(
                local_file=vtt_path,
                file_name=remote_name,
                content_type='text/vtt',
            )
            subs_url = f'{bucket_url}/{remote_name}'
            print(f'    uploaded: {subs_url}')
        except Exception as e:
            print(f'    upload failed: {e}')
            progress['failed'].append(movie_id)
            save_progress(progress)
            continue

        # Stamp data.json in memory
        for m in movies:
            if isinstance(m, dict) and str(m.get('id', '')) == movie_id:
                if not isinstance(m.get('links'), dict):
                    m['links'] = {}
                m['links']['trailer_hosted_subs'] = subs_url
                break

        # Clean up local VTT
        try:
            os.remove(vtt_path)
        except Exception:
            pass

        progress['done'].append(movie_id)
        save_progress(progress)
        stamped += 1
        time.sleep(3)

    if not args.dry_run and stamped > 0:
        data['movies'] = movies
        with open(DATA_JSON, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f'\nStamped {stamped} movies in data.json')
    else:
        print(f'\nDone. {stamped} stamped, {processed} processed this run.')

    print(f'Progress: {len(progress["done"])} done, {len(progress["no_subs"])} no subs, {len(progress["failed"])} failed')


if __name__ == '__main__':
    main()
