"""
Eventive Virtual Screening Scanner — shared scanning logic.

Used by both the standalone scanner (scripts/eventive_scanner.py) and
the pipeline integration (pipeline/generator.py --scan-eventive).
"""

import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

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
# Fetching
# ---------------------------------------------------------------------------
def fetch_festival_slugs():
    """Fetch the Eventive festival directory and extract slugs."""
    resp = requests.get(FESTIVAL_DIRECTORY_URL, timeout=HTTP_TIMEOUT, headers=HEADERS)
    resp.raise_for_status()

    slugs = re.findall(r'href="/([a-z0-9_-]+)"', resp.text)
    skip = {'find', 'login', 'signup', 'about', 'help', 'terms', 'privacy',
            'faq', 'contact', 'careers', 'press', 'blog', 'search'}
    slugs = list(dict.fromkeys(s for s in slugs if s not in skip and len(s) > 2))
    return slugs


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
# Expiry filtering
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
# Title index building and matching
# ---------------------------------------------------------------------------
def build_title_indexes(tracking_movies, wall_movies):
    """Build normalized title indexes from tracking and wall data.

    Args:
        tracking_movies: dict of {id: movie_dict} from movie_tracking.json
        wall_movies: list of movie dicts from data.json

    Returns:
        (tier1_index, tier2_index) — each maps normalized_title -> [(id, title, source, status)]
    """
    tier1_index = {}
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

    return tier1_index, tier2_index


def match_film(film, tier1_index, tier2_index):
    """Try to match an Eventive film against NRW data. Returns match info or None."""
    name = film['name']

    # Tier 1: basic normalization
    n1 = normalize_title(name)
    if n1 in tier1_index:
        return {'tier': 1, 'matches': tier1_index[n1]}

    # Tier 2: strict normalization (strip punctuation)
    n2 = normalize_title_strict(name)
    if n2 in tier2_index:
        return {'tier': 2, 'matches': tier2_index[n2]}

    return None


# ---------------------------------------------------------------------------
# Full scan orchestrator
# ---------------------------------------------------------------------------
def scan_all_festivals(logger=None):
    """Scan all Eventive festivals and return active/upcoming films.

    Args:
        logger: optional logging.Logger for pipeline integration

    Returns:
        dict with keys:
            'films': list of active/unique film dicts (deduplicated)
            'stats': dict of scan statistics
    """
    def log(msg):
        if logger:
            logger.info(msg)
        print(msg)

    log("Fetching Eventive festival directory...")
    slugs = fetch_festival_slugs()
    log(f"  Found {len(slugs)} festival slugs")

    all_films = []
    festivals_scanned = 0
    festivals_with_films = 0
    festivals_failed = 0

    log(f"Scanning {len(slugs)} festivals for catalogs...")
    for i, slug in enumerate(slugs):
        time.sleep(RATE_LIMIT)

        try:
            event_bucket, display_name = fetch_event_bucket(slug)
            if not event_bucket:
                festivals_failed += 1
                continue

            festivals_scanned += 1

            time.sleep(RATE_LIMIT)
            films = fetch_catalog(event_bucket, slug)

            if films:
                festivals_with_films += 1
                for f in films:
                    f['festival_name'] = display_name
                all_films.extend(films)

            if (i + 1) % 25 == 0:
                log(f"  Progress: {i + 1}/{len(slugs)} slugs | "
                    f"{festivals_scanned} scanned | "
                    f"{len(all_films)} films indexed")

        except requests.RequestException:
            festivals_failed += 1
            continue

    log(f"  Done: {festivals_scanned} festivals, "
        f"{festivals_with_films} with films, "
        f"{festivals_failed} failed, "
        f"{len(all_films)} total films")

    # Filter expired
    active_films = []
    expired_count = 0
    for film in all_films:
        status = screening_status(film)
        film['status'] = status
        if status == 'expired':
            expired_count += 1
        else:
            active_films.append(film)

    # Deduplicate: keep film with latest end_time per normalized title
    seen_titles = {}
    for film in active_films:
        key = normalize_title(film['name'])
        if key in seen_titles:
            existing = seen_titles[key]
            if (film.get('end_time', '') or '') > (existing.get('end_time', '') or ''):
                seen_titles[key] = film
        else:
            seen_titles[key] = film

    unique_films = list(seen_titles.values())
    log(f"  Active: {len(active_films)} | Expired: {expired_count} | "
        f"Unique: {len(unique_films)}")

    stats = {
        'festivals_scanned': festivals_scanned,
        'festivals_with_films': festivals_with_films,
        'festivals_failed': festivals_failed,
        'total_films_indexed': len(all_films),
        'expired_filtered': expired_count,
        'unique_active': len(unique_films),
    }

    return {'films': unique_films, 'stats': stats}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def format_date(iso_str):
    """Format ISO datetime to readable date in US Eastern time."""
    if not iso_str:
        return '?'
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        dt_eastern = dt.astimezone(ZoneInfo('America/New_York'))
        return dt_eastern.strftime('%b %d, %Y')
    except (ValueError, TypeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str
