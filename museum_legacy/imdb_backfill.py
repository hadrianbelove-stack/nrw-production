#!/usr/bin/env python3
"""
IMDB Rating Backfill Script

Populates IMDB ratings for existing movies using a 4-tier waterfall:
  1. Check cache (cache/imdb_rating_cache.json)
  2. TMDB external_ids → get IMDB ID → OMDb rating by ID
  3. Playwright scrape IMDB page directly (for OMDb "N/A" movies)
  4. OMDb title+year search (last resort)

Results persist to cache/imdb_rating_cache.json (NOT data.json).
Run generate_data.py after to rebuild data.json from cache.

Usage:
    python3 scripts/imdb_backfill.py --dry-run          # Preview
    python3 scripts/imdb_backfill.py --limit 10         # First 10
    python3 scripts/imdb_backfill.py --no-playwright    # Skip scraping
    python3 scripts/imdb_backfill.py                    # Full run

Created: 2026-03-24
"""

import json
import sys
import os
import re
import argparse
import logging
import time
import yaml
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import load_env  # Load .env into os.environ

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

CACHE_PATH = project_root / 'cache' / 'imdb_rating_cache.json'
TRACKING_PATH = project_root / 'movie_tracking.json'


def load_cache():
    """Load IMDB rating cache."""
    try:
        with open(CACHE_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache):
    """Save IMDB rating cache."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache, f, indent=2)


def load_tracking():
    """Load movie_tracking.json."""
    with open(TRACKING_PATH, 'r') as f:
        return json.load(f)


def save_tracking(data):
    """Save movie_tracking.json."""
    with open(TRACKING_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def get_tmdb_api_key():
    """Get TMDB API key from environment or config.yaml."""
    api_key = os.environ.get('TMDB_API_KEY')
    if api_key:
        return api_key
    config_path = project_root / 'config.yaml'
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        api_key = config.get('api', {}).get('tmdb_api_key')
        if api_key:
            return api_key
    return None


def get_imdb_id_from_tmdb(tmdb_id, tmdb_api_key):
    """Get IMDB ID from TMDB's external_ids endpoint."""
    if not tmdb_id or not tmdb_api_key:
        return None
    # Skip non-numeric IDs (tv_, manual_)
    if isinstance(tmdb_id, str) and not tmdb_id.isdigit():
        return None
    try:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        params = {'api_key': tmdb_api_key, 'append_to_response': 'external_ids'}
        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return None
        data = response.json()
        imdb_id = data.get('external_ids', {}).get('imdb_id')
        if imdb_id and imdb_id.startswith('tt'):
            return imdb_id
        return None
    except Exception as e:
        logger.debug(f"TMDB error for {tmdb_id}: {e}")
        return None


def get_imdb_rating_omdb(imdb_id, omdb_key):
    """Fetch IMDB rating by IMDB ID from OMDb."""
    try:
        url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return None
        data = response.json()
        if data.get('Response') == 'False':
            return None
        rating = data.get('imdbRating')
        if rating and rating != 'N/A':
            return rating
        return None
    except Exception as e:
        logger.debug(f"OMDb error for {imdb_id}: {e}")
        return None


def get_imdb_by_title(title, year, omdb_key):
    """Fetch IMDB ID and rating by title search from OMDb (last resort)."""
    try:
        url = f"http://www.omdbapi.com/?t={quote(title)}&apikey={omdb_key}"
        if year:
            url += f"&y={year}"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return None, None
        data = response.json()
        if data.get('Response') == 'False':
            return None, None
        imdb_id = data.get('imdbID')
        rating = data.get('imdbRating')
        if rating == 'N/A':
            rating = None
        return imdb_id, rating
    except Exception as e:
        logger.debug(f"OMDb title search error for '{title}': {e}")
        return None, None


_playwright_browser = None
_playwright_context = None
_playwright_pw = None

def _get_playwright_page():
    """Get a reusable Playwright page (lazy init, shared browser)."""
    global _playwright_browser, _playwright_context, _playwright_pw
    if _playwright_browser is None:
        from playwright.sync_api import sync_playwright
        _playwright_pw = sync_playwright().start()
        _playwright_browser = _playwright_pw.chromium.launch(headless=True)
        _playwright_context = _playwright_browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
    return _playwright_context.new_page()


def scrape_imdb_rating_playwright(imdb_id):
    """Scrape IMDB rating directly from IMDB page using Playwright.

    Extracts rating from JSON-LD structured data embedded in the page.
    Falls back to CSS selector if JSON-LD not found.
    """
    page = None
    try:
        page = _get_playwright_page()

        url = f"https://www.imdb.com/title/{imdb_id}/"
        page.goto(url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

        # Method 1: JSON-LD structured data (most reliable)
        scripts = page.query_selector_all('script[type="application/ld+json"]')
        for script in scripts:
            try:
                text = script.text_content()
                if not text:
                    continue
                data = json.loads(text)
                if 'aggregateRating' in data:
                    rating_value = data['aggregateRating'].get('ratingValue')
                    if rating_value:
                        page.close()
                        return str(rating_value)
            except (json.JSONDecodeError, AttributeError):
                continue

        # Method 2: CSS selector fallback
        rating_el = page.query_selector('[data-testid="hero-rating-bar__aggregate-rating__score"] span')
        if rating_el:
            text = rating_el.text_content()
            if text:
                try:
                    val = float(text.strip())
                    if 0 < val <= 10:
                        page.close()
                        return str(val)
                except ValueError:
                    pass

        page.close()
        return None

    except Exception as e:
        logger.debug(f"Playwright scrape error for {imdb_id}: {e}")
        if page:
            try:
                page.close()
            except Exception:
                pass
        return None


def search_imdb_by_title_playwright(title, year=None):
    """Search IMDB by title using Playwright, return (imdb_id, rating) or (None, None).

    Visits IMDB search page, finds the best match, then scrapes its rating.
    This catches movies that TMDB and OMDb can't find (manual entries, etc.).
    """
    page = None
    try:
        page = _get_playwright_page()

        # Search IMDB for feature films matching title
        search_query = f"{title} {year}" if year else title
        search_url = f"https://www.imdb.com/find/?q={quote(search_query)}&s=tt&ttype=ft"
        page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

        # Find first result link — search results have links to /title/tt.../
        results = page.query_selector_all('a[href*="/title/tt"]')
        imdb_id = None
        for result in results:
            href = result.get_attribute('href') or ''
            match = re.search(r'/title/(tt\d+)', href)
            if match:
                imdb_id = match.group(1)
                break

        if not imdb_id:
            page.close()
            return None, None

        # Now scrape the rating from the movie page
        page.close()
        rating = scrape_imdb_rating_playwright(imdb_id)
        return imdb_id, rating

    except Exception as e:
        logger.debug(f"Playwright IMDB search error for '{title}': {e}")
        if page:
            try:
                page.close()
            except Exception:
                pass
        return None, None


def main():
    parser = argparse.ArgumentParser(description='Backfill IMDB ratings')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    parser.add_argument('--limit', type=int, default=0, help='Max movies to process (0 = all)')
    parser.add_argument('--no-playwright', action='store_true', help='Skip Playwright scraping tier')
    args = parser.parse_args()

    omdb_key = os.environ.get('OMDB_API_KEY')
    if not omdb_key:
        logger.error("OMDB_API_KEY not found. Check .env file.")
        sys.exit(1)

    tmdb_key = get_tmdb_api_key()
    if tmdb_key:
        logger.info("TMDB API key found")
    else:
        logger.warning("TMDB_API_KEY not found — skipping TMDB tier")

    # Load data sources
    cache = load_cache()
    tracking = load_tracking()
    tracking_movies = tracking.get('movies', {})

    # Build movie list from data.json (only movies that are displayed)
    data_path = project_root / 'data.json'
    with open(data_path, 'r') as f:
        data_json = json.load(f)

    movies = []
    for m in data_json.get('movies', []):
        tmdb_id = str(m.get('id', ''))
        # Check if tracking has an imdb_id already
        tracking_imdb = tracking_movies.get(tmdb_id, {}).get('imdb_id')
        movies.append({
            'tmdb_id': tmdb_id,
            'title': m.get('title', 'Unknown'),
            'year': m.get('year'),
            'imdb_id': tracking_imdb,
        })

    logger.info(f"Movies in data.json: {len(movies)}")
    logger.info(f"IMDB cache entries: {len(cache)}")

    # Filter to movies needing processing
    movies_to_process = []
    for m in movies:
        # Check if already in cache with a rating
        existing_imdb_id = m.get('imdb_id')
        if existing_imdb_id and existing_imdb_id in cache and cache[existing_imdb_id].get('rating'):
            continue
        movies_to_process.append(m)

    logger.info(f"Movies needing processing: {len(movies_to_process)}")

    if args.limit > 0:
        movies_to_process = movies_to_process[:args.limit]
        logger.info(f"Limited to first {args.limit}")

    if args.dry_run:
        logger.info("DRY RUN — no changes will be written")

    if args.no_playwright:
        logger.info("Playwright scraping DISABLED")

    # Stats
    stats = {
        'cache_hits': 0,
        'tmdb_lookups': 0,
        'omdb_calls': 0,
        'playwright_scrapes': 0,
        'ratings_found': 0,
        'ids_found': 0,
        'not_found': 0,
    }

    for idx, movie in enumerate(movies_to_process):
        title = movie['title']
        year = movie.get('year')
        tmdb_id = movie['tmdb_id']
        imdb_id = movie.get('imdb_id')
        rating = None

        # ── Tier 1: Check cache ──
        if imdb_id and imdb_id in cache:
            cached = cache[imdb_id]
            if cached.get('rating'):
                stats['cache_hits'] += 1
                continue  # Already have it

        # ── Tier 2: TMDB → IMDB ID → OMDb rating ──
        if not imdb_id and tmdb_key:
            imdb_id = get_imdb_id_from_tmdb(tmdb_id, tmdb_key)
            stats['tmdb_lookups'] += 1
            time.sleep(0.25)

        if imdb_id:
            rating = get_imdb_rating_omdb(imdb_id, omdb_key)
            stats['omdb_calls'] += 1

        # ── Tier 3: Playwright scrape IMDB page ──
        if not rating and imdb_id and not args.no_playwright:
            rating = scrape_imdb_rating_playwright(imdb_id)
            stats['playwright_scrapes'] += 1
            if rating:
                logger.info(f"  [{idx+1}/{len(movies_to_process)}] {title} ({year}) -> IMDb {rating} [scraped]")
            time.sleep(2)  # IMDB rate limit

        # ── Tier 4: OMDb title search ──
        if not rating and not imdb_id:
            found_id, rating = get_imdb_by_title(title, year, omdb_key)
            stats['omdb_calls'] += 1
            if found_id:
                imdb_id = found_id

        # ── Tier 5: Playwright IMDB search by title (for manual/tv entries with no IMDB ID) ──
        if not imdb_id and not args.no_playwright:
            found_id, found_rating = search_imdb_by_title_playwright(title, year)
            stats['playwright_scrapes'] += 1
            if found_id:
                imdb_id = found_id
                if found_rating:
                    rating = found_rating
                    logger.info(f"  [{idx+1}/{len(movies_to_process)}] {title} ({year}) -> IMDb {rating} [search+scraped]")
                time.sleep(2)

        # ── Save results ──
        if rating:
            if not (imdb_id and imdb_id in cache and cache[imdb_id].get('rating')):
                logger.info(f"  [{idx+1}/{len(movies_to_process)}] {title} ({year}) -> IMDb {rating}")
            stats['ratings_found'] += 1

            if not args.dry_run and imdb_id:
                cache[imdb_id] = {
                    'imdb_id': imdb_id,
                    'rating': rating,
                    'title': title,
                    'scraped_at': datetime.now().isoformat(),
                    'source': 'playwright' if stats['playwright_scrapes'] > 0 else 'omdb'
                }
                # Store IMDB ID in tracking
                if str(tmdb_id) in tracking_movies:
                    tracking_movies[str(tmdb_id)]['imdb_id'] = imdb_id
        elif imdb_id:
            # Have ID but no rating — still save the ID
            stats['ids_found'] += 1
            if not args.dry_run:
                if imdb_id not in cache:
                    cache[imdb_id] = {
                        'imdb_id': imdb_id,
                        'rating': None,
                        'title': title,
                        'scraped_at': datetime.now().isoformat(),
                        'source': 'tmdb_id_only'
                    }
                if str(tmdb_id) in tracking_movies:
                    tracking_movies[str(tmdb_id)]['imdb_id'] = imdb_id
        else:
            stats['not_found'] += 1

        # Rate limit
        time.sleep(0.3)

        # OMDb daily limit warning
        if stats['omdb_calls'] == 900:
            logger.warning("Approaching OMDb daily limit (900/1000)")

    # Print summary
    logger.info(f"\n{'DRY RUN ' if args.dry_run else ''}Results:")
    logger.info(f"  Ratings found: {stats['ratings_found']}")
    logger.info(f"  IDs found (no rating): {stats['ids_found']}")
    logger.info(f"  Not found: {stats['not_found']}")
    logger.info(f"  Cache hits: {stats['cache_hits']}")
    logger.info(f"  API calls: {stats['tmdb_lookups']} TMDB, {stats['omdb_calls']} OMDb, {stats['playwright_scrapes']} Playwright")

    if not args.dry_run:
        save_cache(cache)
        logger.info(f"Saved cache: {len(cache)} total entries")
        save_tracking(tracking)
        logger.info("Updated movie_tracking.json with IMDB IDs")
        logger.info("\nRun 'python3 generate_data.py' to rebuild data.json with ratings from cache.")


if __name__ == '__main__':
    main()
