#!/opt/homebrew/bin/python3.11
"""
Trailer Downloader — Phase 1 of In-App Trailer Playback
Downloads movie trailers from YouTube as 1080p MP4 files using yt-dlp.

Usage:
    python3 scripts/trailer_downloader.py                      # Download all trailers
    python3 scripts/trailer_downloader.py --limit 10           # Download first 10 only
    python3 scripts/trailer_downloader.py --dry-run             # Test without downloading
    python3 scripts/trailer_downloader.py --cookies safari      # Use browser cookies (for age-restricted)
    python3 scripts/trailer_downloader.py --retry-failed        # Re-attempt only previously failed/skipped

Requires Python 3.10+ (yt-dlp dropped 3.9 support).
"""

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import time

import yt_dlp

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_JSON = os.path.join(PROJECT_ROOT, 'data.json')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'media', 'trailers')

# Download settings
MAX_DURATION_SECONDS = 300  # 5 minutes — skip anything longer
RATE_LIMIT_SECONDS = 2     # Pause between downloads
DOWNLOAD_TIMEOUT = 60       # Seconds before giving up on a single download
MOVIE_TIMEOUT = 480         # 8 minutes overall per movie (normal runs ~3-4 min)


def extract_youtube_id(url):
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return None
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def load_movies():
    """Load movies from data.json that have trailer URLs."""
    with open(DATA_JSON, 'r') as f:
        data = json.load(f)

    movies = []
    for movie in data.get('movies', []):
        trailer_url = movie.get('links', {}).get('trailer', '')
        tmdb_id = movie.get('id', '')

        # Skip movies without trailers or IDs
        if not trailer_url or not tmdb_id:
            continue

        # Skip YouTube search URLs (not actual trailers)
        if 'search_query=' in trailer_url:
            continue

        # Must have a valid YouTube video ID
        video_id = extract_youtube_id(trailer_url)
        if not video_id:
            continue

        movies.append({
            'id': str(tmdb_id),
            'title': movie.get('title', 'Unknown'),
            'year': movie.get('year', ''),
            'trailer_url': trailer_url,
            'video_id': video_id,
            'original_language': movie.get('original_language', 'en'),
        })

    return movies


def clean_vtt(content):
    """Strip YouTube's word-timing and left-align positioning from auto-caption VTT files."""
    content = re.sub(r'<\d{2}:\d{2}:\d{2}\.\d{3}>', '', content)
    content = re.sub(r'</?c>', '', content)
    content = re.sub(r' align:start position:\d+%', '', content)
    return content


def probe_video_codec(path):
    """Return the video stream codec name (e.g. 'h264', 'av1', 'vp9') or '' if unknown."""
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name', '-of', 'default=nw=1:nk=1', path],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ''


def ensure_h264(path):
    """Guarantee the file is H.264 so it plays on Apple TV / Roku / all devices.

    yt-dlp's format selector prefers H.264 (avc1), but when a YouTube video offers
    no H.264 stream at all it falls back to an AV1/VP9 mp4 — which plays on web but
    renders black on tvOS/Roku. This re-encodes any non-H.264 download to H.264+AAC.
    Returns the final codec ('h264' on success). No-op when already H.264.
    """
    codec = probe_video_codec(path)
    if codec == 'h264' or not codec:
        return codec
    tmp_path = path + '.h264.mp4'
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', path,
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', tmp_path],
            capture_output=True, text=True, timeout=900,
        )
        if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            os.replace(tmp_path, path)
            return 'h264'
        # Re-encode failed — leave the original in place, clean up the temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return codec
    except (subprocess.SubprocessError, OSError):
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return codec


def download_trailer(movie, dry_run=False, cookies_browser=None, cookies_file=None):
    """
    Download a single trailer. Returns a result dict with status and details.

    Statuses: 'downloaded', 'skipped_exists', 'skipped_too_long',
              'skipped_unavailable', 'skipped_age_restricted', 'failed'
    """
    tmdb_id = movie['id']
    title = movie['title']
    output_path = os.path.join(OUTPUT_DIR, f'{tmdb_id}.mp4')
    is_foreign = movie.get('original_language', 'en') != 'en'
    vtt_path = os.path.join(OUTPUT_DIR, f'{tmdb_id}.en.vtt')

    # Skip if already downloaded
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        return {'status': 'skipped_exists', 'detail': f'{size_mb:.1f}MB on disk'}

    if dry_run:
        return {'status': 'dry_run', 'detail': f'Would download {movie["trailer_url"]}'}

    ydl_opts = {
        'format': 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]',
        'merge_output_format': 'mp4',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'socket_timeout': DOWNLOAD_TIMEOUT,
        'retries': 2,
        'fragment_retries': 2,
        # Don't download if longer than 5 minutes
        'match_filter': yt_dlp.utils.match_filter_func(f'duration < {MAX_DURATION_SECONDS}'),
        # YouTube n-parameter challenge solver (required since early 2026)
        'js_runtimes': {'node': {}},
        'remote_components': ['ejs:github'],
    }

    # For foreign-language trailers, attempt English subtitle download
    if is_foreign:
        ydl_opts['writeautomaticsub'] = True
        ydl_opts['writesubtitles'] = True
        ydl_opts['subtitleslangs'] = ['en']
        ydl_opts['subtitlesformat'] = 'vtt'
        ydl_opts['outtmpl'] = {
            'default': output_path,
            'subtitle': os.path.join(OUTPUT_DIR, f'{tmdb_id}.%(ext)s'),
        }

    # Use cookies for age-restricted content.
    # Prefer a cookies file (works from LaunchAgent) over live browser extraction (blocked by macOS sandbox).
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts['cookiefile'] = cookies_file
    elif cookies_browser:
        ydl_opts['cookiesfrombrowser'] = (cookies_browser,)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(ydl.extract_info, movie['trailer_url'], download=True)
            try:
                info = future.result(timeout=MOVIE_TIMEOUT)
            except concurrent.futures.TimeoutError:
                # shutdown(wait=False) abandons the stuck thread instead of blocking forever
                executor.shutdown(wait=False, cancel_futures=True)
                return {'status': 'failed', 'detail': f'Timed out after {MOVIE_TIMEOUT}s'}
            executor.shutdown(wait=False)

            if info is None:
                return {'status': 'skipped_too_long', 'detail': 'Exceeded 5 min duration cap'}

            # Verify the file was created
            if os.path.exists(output_path):
                # Safety net: re-encode to H.264 if yt-dlp fell back to AV1/VP9
                # (those play on web but render black on Apple TV / Roku).
                final_codec = ensure_h264(output_path)
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                duration = info.get('duration', 0)
                # Clean VTT positioning/timing markup if subtitles were downloaded
                if is_foreign and os.path.exists(vtt_path):
                    with open(vtt_path) as f:
                        cleaned = clean_vtt(f.read())
                    with open(vtt_path, 'w') as f:
                        f.write(cleaned)
                detail = f'{size_mb:.1f}MB, {duration}s'
                if final_codec and final_codec != 'h264':
                    detail += f' (WARNING: codec {final_codec}, H.264 re-encode failed)'
                return {'status': 'downloaded', 'detail': detail}
            else:
                return {'status': 'failed', 'detail': 'File not created after download'}

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        if 'sign in' in error_msg or 'age' in error_msg:
            return {'status': 'skipped_age_restricted', 'detail': str(e)[:100]}
        elif 'unavailable' in error_msg or 'removed' in error_msg or 'private' in error_msg:
            return {'status': 'skipped_unavailable', 'detail': str(e)[:100]}
        elif 'geo' in error_msg or 'country' in error_msg:
            return {'status': 'skipped_region_locked', 'detail': str(e)[:100]}
        elif 'filtered' in error_msg:
            return {'status': 'skipped_too_long', 'detail': 'Exceeded 5 min duration cap'}
        else:
            return {'status': 'failed', 'detail': str(e)[:150]}
    except Exception as e:
        return {'status': 'failed', 'detail': str(e)[:150]}


def main():
    parser = argparse.ArgumentParser(description='Download movie trailers from YouTube')
    parser.add_argument('--limit', type=int, default=0, help='Max number of trailers to process (0 = all)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be downloaded without downloading')
    parser.add_argument('--cookies', type=str, default=None, metavar='BROWSER',
                        help='Use cookies from browser for age-restricted content (safari, chrome, firefox)')
    parser.add_argument('--retry-failed', action='store_true',
                        help='Only attempt movies that do NOT already have a downloaded file')
    args = parser.parse_args()

    if args.cookies:
        print(f'Using cookies from {args.cookies} (unlocks age-restricted content)')

    # Load movies
    print(f'Loading movies from {DATA_JSON}...')
    movies = load_movies()
    print(f'Found {len(movies)} movies with valid YouTube trailer URLs')

    if args.retry_failed:
        # Filter to only movies without a downloaded file
        before = len(movies)
        movies = [m for m in movies if not os.path.exists(os.path.join(OUTPUT_DIR, f'{m["id"]}.mp4'))]
        print(f'Retry mode: {before - len(movies)} already downloaded, {len(movies)} remaining')

    if args.limit > 0:
        movies = movies[:args.limit]
        print(f'Limiting to first {args.limit}')

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Track results
    results = {
        'downloaded': [],
        'skipped_exists': [],
        'skipped_too_long': [],
        'skipped_unavailable': [],
        'skipped_age_restricted': [],
        'skipped_region_locked': [],
        'dry_run': [],
        'failed': [],
    }

    # Download loop
    total = len(movies)
    for i, movie in enumerate(movies, 1):
        label = f'[{i}/{total}] {movie["title"]} ({movie["year"]})'
        print(f'{label}...', end=' ', flush=True)

        result = download_trailer(movie, dry_run=args.dry_run, cookies_browser=args.cookies)
        status = result['status']
        detail = result['detail']

        # Collect result
        if status not in results:
            results[status] = []
        results[status].append({'movie': label, 'detail': detail})

        # Print status
        status_labels = {
            'downloaded': '✓ Downloaded',
            'skipped_exists': '→ Already exists',
            'skipped_too_long': '→ Too long (>5min)',
            'skipped_unavailable': '→ Unavailable',
            'skipped_age_restricted': '→ Age-restricted',
            'skipped_region_locked': '→ Region-locked',
            'dry_run': '~ Dry run',
            'failed': '✗ Failed',
        }
        print(f'{status_labels.get(status, status)} ({detail})')

        # Rate limit between actual downloads
        if status == 'downloaded' and i < total:
            time.sleep(RATE_LIMIT_SECONDS)

    # Summary report
    print('\n' + '=' * 60)
    print('TRAILER DOWNLOAD REPORT')
    print('=' * 60)
    print(f'  Downloaded:       {len(results["downloaded"])}')
    print(f'  Already existed:  {len(results["skipped_exists"])}')
    print(f'  Too long (>5min): {len(results["skipped_too_long"])}')
    print(f'  Unavailable:      {len(results["skipped_unavailable"])}')
    print(f'  Age-restricted:   {len(results["skipped_age_restricted"])}')
    print(f'  Region-locked:    {len(results["skipped_region_locked"])}')
    if results['dry_run']:
        print(f'  Dry run:          {len(results["dry_run"])}')
    print(f'  Failed:           {len(results["failed"])}')
    print('=' * 60)

    # Show failures in detail
    if results['failed']:
        print('\nFailed downloads:')
        for item in results['failed']:
            print(f'  - {item["movie"]}: {item["detail"]}')

    # Total disk usage
    if os.path.exists(OUTPUT_DIR):
        total_size = sum(
            os.path.getsize(os.path.join(OUTPUT_DIR, f))
            for f in os.listdir(OUTPUT_DIR)
            if f.endswith('.mp4')
        )
        total_gb = total_size / (1024 ** 3)
        file_count = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.mp4')])
        print(f'\nDisk usage: {file_count} files, {total_gb:.2f} GB total')


if __name__ == '__main__':
    main()
