#!/usr/bin/env python3
"""
Build distributor filmography lookup from Wikipedia + TMDB.

Scrapes Wikipedia filmography pages and TMDB Company API for each indie
distributor listed in admin/distributor_sources.json. Builds
cache/distributor_lookup.json — a reverse lookup of {title_year: distributor_name}.

Usage:
    python3 scripts/build_distributor_lookup.py           # build/refresh
    python3 scripts/build_distributor_lookup.py --force    # force rebuild even if fresh
    python3 scripts/build_distributor_lookup.py --stats    # show stats only
"""

import argparse
import json
import os
import re
import time
from datetime import datetime

import requests

# Paths relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_PATH = os.path.join(PROJECT_ROOT, 'admin', 'distributor_sources.json')
CATEGORY_PATH = os.path.join(PROJECT_ROOT, 'admin', 'category_config.json')
OUTPUT_PATH = os.path.join(PROJECT_ROOT, 'cache', 'distributor_lookup.json')
DATA_PATH = os.path.join(PROJECT_ROOT, 'data.json')

MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
TMDB_API_BASE = "https://api.themoviedb.org/3"
USER_AGENT = "NRWBot/1.0 (nrw-production distributor lookup)"
STALENESS_DAYS = 7
RATE_LIMIT_SECONDS = 2.0

# Module-level quiet flag — suppresses print output when called from pipeline
_quiet = False


def _log(msg=''):
    """Print unless running in quiet mode (pipeline integration)."""
    if not _quiet:
        print(msg)


def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_title(title):
    """Normalize a film title for lookup key generation.

    Lowercases, strips leading 'the ', collapses whitespace.
    """
    t = title.lower().strip()
    t = re.sub(r'^the\s+', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def make_key(title, year):
    """Create a lookup key from title and year."""
    return f"{normalize_title(title)}_{year}"


def get_tmdb_api_key():
    """Load TMDB API key from environment or .env file."""
    key = os.environ.get('TMDB_API_KEY', '')
    if key:
        return key
    # Try .env file
    env_path = os.path.join(PROJECT_ROOT, '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('TMDB_API_KEY='):
                    return line.split('=', 1)[1].strip()
    return ''


# --- MediaWiki helpers ---

def _mediawiki_request(params, retries=2):
    """Make a MediaWiki API request with retry on failure."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries + 1):
        try:
            resp = requests.get(MEDIAWIKI_API, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if 'error' in data:
                _log(f"  [API error] {data['error'].get('info', 'unknown')}")
                return None
            return data
        except Exception as e:
            if attempt < retries:
                wait = RATE_LIMIT_SECONDS * (attempt + 2)
                _log(f"  [RETRY] Request failed ({e}), waiting {wait}s...")
                time.sleep(wait)
            else:
                _log(f"  [ERROR] MediaWiki request failed after {retries + 1} attempts: {e}")
                return None
    return None


def fetch_mediawiki(page, section_index=None):
    """Fetch wikitext from MediaWiki API. Returns wikitext string or None."""
    params = {
        "action": "parse",
        "page": page,
        "prop": "wikitext",
        "format": "json",
    }
    if section_index is not None:
        params["section"] = str(section_index)

    data = _mediawiki_request(params)
    if not data:
        return None
    return data.get('parse', {}).get('wikitext', {}).get('*', '')


def fetch_sections(page):
    """Get section list for a Wikipedia page. Returns list of {index, line, toclevel}."""
    params = {
        "action": "parse",
        "page": page,
        "prop": "sections",
        "format": "json",
    }
    data = _mediawiki_request(params)
    if not data:
        return None
    return data.get('parse', {}).get('sections', [])


def find_filmography_section_index(sections):
    """Find the section index for the filmography on a company page."""
    if not sections:
        return None
    for s in sections:
        name = s.get('line', '').lower().strip()
        if name in ('filmography', 'films', 'selected filmography',
                     'films released', 'released', 'released films',
                     'selected titles', 'select filmography',
                     'selected releases'):
            return s['index']
    return None


def extract_year_from_date(date_str):
    """Extract a 4-digit year from a date string like 'March 6, 2020'."""
    m = re.search(r'\b(19\d{2}|20\d{2})\b', date_str)
    return int(m.group(1)) if m else None


def extract_year_from_section_heading(wikitext):
    """Extract decade/year from section headings like ===2020s===."""
    m = re.search(r'===?\s*((?:19|20)\d{2})s?\s*===?', wikitext)
    return int(m.group(1)) if m else None


def parse_films_from_wikitext(wikitext):
    """Parse film titles and years from wikitable wikitext.

    Handles multiple formats:
    - || ''[[Title]]'' ||  (Utopia, NEON style)
    - |''[[Title]]''       (Magnolia style)
    - ! scope="row" | ''[[Title]]''  (A24 style)
    - ''[[Title (disambig)|Display Title]]''  (with pipe)

    Returns list of (title, year) tuples.
    """
    films = []
    # Track current section year for fallback
    section_year = extract_year_from_section_heading(wikitext)

    # Split into table rows
    rows = re.split(r'\n\|-', wikitext)

    for row in rows:
        # Extract film title — look for italicized wiki links
        # Pattern: ''[[Article name|Display name]]'' or ''[[Article name]]''
        title_matches = re.findall(
            r"''\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]''",
            row
        )

        if not title_matches:
            continue

        # Use display name if available, otherwise article name
        # Filter out non-film links (directors, companies, etc.)
        # Film titles are usually the first or most prominent link in the row
        for article_name, display_name in title_matches:
            title = display_name if display_name else article_name
            # Clean up title — remove "(film)" disambiguation
            title = re.sub(r'\s*\((?:film|.*?film)\)\s*$', '', title)

            # Extract year from the same row
            year = extract_year_from_date(row)
            if not year:
                year = section_year

            if title and year:
                films.append((title.strip(), year))
                break  # Take first film link per row

    return films


# --- Wikipedia scrapers ---

def scrape_list_page(page_name, distributor):
    """Scrape a dedicated list page (e.g., List_of_A24_films)."""
    _log(f"  Fetching list page: {page_name}")
    time.sleep(RATE_LIMIT_SECONDS)

    sections = fetch_sections(page_name)
    if not sections:
        _log(f"  [WARN] Could not fetch sections for {page_name}")
        return []

    time.sleep(RATE_LIMIT_SECONDS)
    wikitext = fetch_mediawiki(page_name)
    if not wikitext:
        _log(f"  [WARN] Could not fetch wikitext for {page_name}")
        return []

    films = parse_films_from_wikitext(wikitext)
    _log(f"  Wikipedia list: {len(films)} films")
    return films


def scrape_company_page(page_name, distributor):
    """Scrape a company page's filmography section."""
    _log(f"  Fetching company page: {page_name}")
    time.sleep(RATE_LIMIT_SECONDS)

    sections = fetch_sections(page_name)
    if not sections:
        _log(f"  [WARN] Could not fetch sections for {page_name}")
        return []

    film_idx = find_filmography_section_index(sections)
    if not film_idx:
        _log(f"  [WARN] No filmography section found on {page_name}")
        return []

    time.sleep(RATE_LIMIT_SECONDS)
    wikitext = fetch_mediawiki(page_name, section_index=film_idx)
    if not wikitext:
        _log(f"  [WARN] Could not fetch filmography section from {page_name}")
        return []

    films = parse_films_from_wikitext(wikitext)
    _log(f"  Wikipedia company page: {len(films)} films")
    return films


# --- TMDB Company API ---

def scrape_tmdb_company(company_id, distributor, tmdb_key):
    """Fetch all films for a TMDB company ID. Returns list of (title, year) tuples.

    Note: TMDB's /company/{id}/movies endpoint has a known bug where it reports
    inflated total_results but returns the same results on every page. We deduplicate
    by TMDB ID and stop paginating when we see repeats.
    """
    if not tmdb_key:
        return []

    films = []
    seen_ids = set()
    page = 1
    total_pages = 1

    while page <= total_pages:
        url = f"{TMDB_API_BASE}/company/{company_id}/movies"
        params = {"api_key": tmdb_key, "page": page}
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            _log(f"  [ERROR] TMDB company fetch failed: {e}")
            break

        total_pages = data.get('total_pages', 1)
        new_on_this_page = 0
        for m in data.get('results', []):
            mid = m.get('id')
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            new_on_this_page += 1

            title = m.get('title', '')
            release_date = m.get('release_date', '')
            year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
            if title and year:
                films.append((title, year))

        # Stop if this page had no new results (TMDB pagination bug)
        if new_on_this_page == 0:
            break

        page += 1

    if films:
        _log(f"  TMDB company API: {len(films)} films")
    return films


# --- Infobox scanner (optional) ---

def scrape_infobox_distributors(data_json_movies):
    """For wall films with Wikipedia URLs, extract distributor from infobox."""
    results = {}

    category_config = load_json(CATEGORY_PATH)
    indie_distributors = category_config.get('indie_distributors', [])

    movies_with_wiki = [
        m for m in data_json_movies
        if m.get('wikipedia_url')
    ]

    if not movies_with_wiki:
        return results

    _log(f"\nChecking Wikipedia infoboxes for {len(movies_with_wiki)} wall films...")

    for movie in movies_with_wiki:
        wiki_url = movie['wikipedia_url']
        title = movie.get('title', '')
        year = movie.get('year', '')

        page_match = re.search(r'wikipedia\.org/wiki/(.+?)(?:\?|#|$)', wiki_url)
        if not page_match:
            continue
        page_name = page_match.group(1)

        time.sleep(RATE_LIMIT_SECONDS)
        wikitext = fetch_mediawiki(page_name)
        if not wikitext:
            continue

        dist_match = re.search(
            r'\|\s*(?:distributed by|distributor|released by)\s*=\s*(.+?)(?:\n\||\n\})',
            wikitext, re.IGNORECASE
        )
        if not dist_match:
            continue

        dist_raw = dist_match.group(1).strip()
        dist_names = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', dist_raw)
        if not dist_names:
            dist_names = [dist_raw]

        for dist_name in dist_names:
            dist_clean = dist_name.strip()
            for indie in indie_distributors:
                if indie.lower() in dist_clean.lower() or dist_clean.lower() in indie.lower():
                    key = make_key(title, year)
                    results[key] = indie
                    _log(f"  Infobox match: {title} ({year}) -> {indie}")
                    break

    return results


# --- Main build ---

def build_lookup(force=False, scan_infoboxes=False, quiet=False):
    """Main build function. Returns the lookup dict."""
    global _quiet
    _quiet = quiet

    # Check staleness
    if not force and os.path.exists(OUTPUT_PATH):
        try:
            existing = load_json(OUTPUT_PATH)
            last_updated = existing.get('last_updated', '')
            if last_updated:
                updated_dt = datetime.fromisoformat(last_updated)
                age_days = (datetime.now() - updated_dt).days
                if age_days < STALENESS_DAYS:
                    _log(f"Lookup is {age_days} days old (threshold: {STALENESS_DAYS}). Use --force to rebuild.")
                    return existing
        except Exception:
            pass

    # Load config
    sources = load_json(SOURCES_PATH)
    tmdb_key = get_tmdb_api_key()
    if tmdb_key:
        _log(f"TMDB API key: found")
    else:
        _log(f"TMDB API key: not found (skipping TMDB company lookups)")

    by_title_year = {}
    stats = {"total_entries": 0, "sources": {}}
    # Per-distributor film lists — populated across both phases
    all_dist_films = {d: [] for d in sources}
    dist_stats_map = {d: {} for d in sources}

    # === PHASE 1: Wikipedia (rate-limited, do all at once) ===
    _log("\n=== PHASE 1: Wikipedia filmographies ===")
    seen_pages = set()

    for distributor, config in sources.items():
        list_page = config.get('wikipedia_list_page')
        company_page = config.get('wikipedia_company_page')

        if list_page and list_page not in seen_pages:
            seen_pages.add(list_page)
            _log(f"\n--- {distributor} ---")
            films = scrape_list_page(list_page, distributor)
            all_dist_films[distributor].extend(films)
            dist_stats_map[distributor]['wiki_list'] = len(films)

        elif company_page:
            _log(f"\n--- {distributor} ---")
            films = scrape_company_page(company_page, distributor)
            all_dist_films[distributor].extend(films)
            dist_stats_map[distributor]['wiki_company'] = len(films)

        elif list_page and list_page in seen_pages:
            _log(f"\n--- {distributor} ---")
            _log(f"  Shares list page {list_page} (already scraped)")
            dist_stats_map[distributor]['shared_list'] = True

        # No Wikipedia source — skip silently, TMDB will handle it

    # === PHASE 2: TMDB Company API (fast, no rate limit issues) ===
    if tmdb_key:
        _log("\n\n=== PHASE 2: TMDB Company API ===")
        for distributor, config in sources.items():
            tmdb_id = config.get('tmdb_company_id')
            if not tmdb_id:
                continue

            _log(f"\n--- {distributor} ---")
            tmdb_films = scrape_tmdb_company(tmdb_id, distributor, tmdb_key)
            dist_stats_map[distributor]['tmdb'] = len(tmdb_films)

            # Add TMDB films not already found via Wikipedia
            wiki_keys = {make_key(t, y) for t, y in all_dist_films[distributor]}
            new_from_tmdb = 0
            for title, year in tmdb_films:
                key = make_key(title, year)
                if key not in wiki_keys:
                    all_dist_films[distributor].append((title, year))
                    new_from_tmdb += 1
            if new_from_tmdb:
                _log(f"  TMDB added {new_from_tmdb} films not on Wikipedia")

    # === Build final lookup ===
    for distributor in sources:
        for title, year in all_dist_films[distributor]:
            key = make_key(title, year)
            if key not in by_title_year:
                by_title_year[key] = distributor
        stats['sources'][distributor] = dist_stats_map[distributor]

    # Optionally check Wikipedia infoboxes for wall films (slow)
    infobox_results = {}
    if scan_infoboxes and os.path.exists(DATA_PATH):
        data_json = load_json(DATA_PATH)
        movies = data_json if isinstance(data_json, list) else data_json.get('movies', [])
        infobox_results = scrape_infobox_distributors(movies)

        for key, dist_name in infobox_results.items():
            if key not in by_title_year:
                by_title_year[key] = dist_name

        if infobox_results:
            stats['sources']['_infobox'] = {'films': len(infobox_results)}

    stats['total_entries'] = len(by_title_year)

    lookup = {
        "last_updated": datetime.now().isoformat(timespec='seconds'),
        "by_title_year": by_title_year,
        "stats": stats,
    }

    save_json(OUTPUT_PATH, lookup)
    _log(f"\n=== DONE ===")
    _log(f"Total lookup entries: {len(by_title_year)}")
    _log(f"Saved to: {OUTPUT_PATH}")

    return lookup


def show_stats():
    """Display stats from existing lookup."""
    if not os.path.exists(OUTPUT_PATH):
        _log("No lookup file found. Run without --stats to build.")
        return

    lookup = load_json(OUTPUT_PATH)
    _log(f"Last updated: {lookup.get('last_updated', 'unknown')}")
    _log(f"Total entries: {lookup['stats']['total_entries']}")
    _log()

    for dist, dist_stats in sorted(lookup['stats']['sources'].items()):
        if isinstance(dist_stats, dict):
            counts = ', '.join(f"{k}: {v}" for k, v in dist_stats.items())
            _log(f"  {dist}: {counts}")


def main():
    parser = argparse.ArgumentParser(description="Build distributor filmography lookup from Wikipedia + TMDB")
    parser.add_argument('--force', action='store_true', help="Force rebuild even if cache is fresh")
    parser.add_argument('--stats', action='store_true', help="Show stats from existing lookup")
    parser.add_argument('--infobox', action='store_true', help="Also scan wall film infoboxes (slow)")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    build_lookup(force=args.force, scan_infoboxes=args.infobox)


if __name__ == '__main__':
    main()
