#!/usr/bin/env python3
"""
Unified Hidden Gems Scraper
---------------------------
Finds indie films with digital release dates (Type 4) but not on major streaming/rental platforms.
These are self-distributed films on Vimeo, YouTube, Patreon, personal sites, etc.

🎬 UNIFIED SCRAPER - All platforms in one tool!

Features:
- TMDB discovery (Type 4 release, no providers)
- Live scraping from Vimeo On Demand, YouTube Movies, Patreon creators
- File-based discovery integration
- Curation-optimized exports
- Cross-platform deduplication

Usage Examples:
    # Standard TMDB discovery
    python3 hidden_gems_scraper.py --days 30
    python3 hidden_gems_scraper.py --month 2025-12

    # Live scraping (new unified approach)
    python3 hidden_gems_scraper.py --scrape-all --min-runtime 60
    python3 hidden_gems_scraper.py --scrape-vimeo --scrape-patreon --max-creators 15
    python3 hidden_gems_scraper.py --scrape-youtube --max-pages 5 --no-headless

    # Hybrid: TMDB + Live scraping
    python3 hidden_gems_scraper.py --days 7 --scrape-vimeo --export-for-curation

    # File-based integration (legacy method)
    python3 hidden_gems_scraper.py --include-vimeo --include-youtube --include-patreon

    # Curation workflow
    python3 hidden_gems_scraper.py --scrape-all --export-for-curation --output my_gems
"""

import argparse
import csv
import json
import os
import time
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse
import requests
from functools import wraps
import unicodedata

# TMDB API
TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
if not TMDB_API_KEY:
    # Fallback to config.yaml
    try:
        import yaml
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
            TMDB_API_KEY = config.get('api', {}).get('tmdb_api_key', '')
    except:
        pass
TMDB_BASE = 'https://api.themoviedb.org/3'

# Import playwright manager for direct scraping
try:
    from playwright_manager import get_playwright_manager
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    print("Warning: playwright_manager not available. Direct scraping disabled.")
    PLAYWRIGHT_AVAILABLE = False


def retry_with_exponential_backoff(max_retries: int = 3, base_delay: float = 0.5, max_delay: float = 5.0, jitter_ratio: float = 0.2):
    """Decorator for retrying functions with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e

                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = delay * jitter_ratio * (0.5 - time.time() % 1)  # Random jitter
                    actual_delay = delay + jitter

                    print(f"Attempt {attempt + 1} failed: {str(e)[:100]}... Retrying in {actual_delay:.1f}s")
                    time.sleep(actual_delay)

            return None
        return wrapper
    return decorator


def discover_movies_from_tmdb(month: Optional[str] = None, days: Optional[int] = None) -> list:
    """Query TMDB directly for movies with premiere dates in the specified period."""
    movies = []

    # Calculate date range
    if month:
        # e.g., "2025-12" -> 2025-12-01 to 2025-12-31
        year, mon = month.split('-')
        start_date = f"{month}-01"
        # Get last day of month
        if mon == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(mon)+1:02d}-01"
    elif days:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    else:
        # Default to last 30 days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    print(f"   Querying TMDB for premieres: {start_date} to {end_date}")

    page = 1
    total_pages = 1

    while page <= total_pages and page <= 500:  # TMDB max 500 pages
        try:
            resp = requests.get(f"{TMDB_BASE}/discover/movie", params={
                'api_key': TMDB_API_KEY,
                'primary_release_date.gte': start_date,
                'primary_release_date.lte': end_date,
                'sort_by': 'primary_release_date.desc',
                'page': page
            }, timeout=15)

            if resp.status_code != 200:
                print(f"   Warning: TMDB returned {resp.status_code}")
                break

            data = resp.json()
            total_pages = data.get('total_pages', 1)

            for movie in data.get('results', []):
                movies.append((str(movie['id']), movie.get('release_date', '')))

            if page == 1:
                print(f"   Found {data.get('total_results', 0)} movies across {total_pages} pages")

            page += 1
            time.sleep(0.05)  # Rate limiting

        except Exception as e:
            print(f"   Error on page {page}: {e}")
            break

    return movies


def get_release_dates(tmdb_id: str) -> dict:
    """Get release dates from TMDB API."""
    if not TMDB_API_KEY:
        return {}

    try:
        url = f"{TMDB_BASE}/movie/{tmdb_id}/release_dates"
        resp = requests.get(url, params={'api_key': TMDB_API_KEY}, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}


def get_watch_providers(tmdb_id: str) -> dict:
    """Get watch providers from TMDB API."""
    if not TMDB_API_KEY:
        return {}

    try:
        url = f"{TMDB_BASE}/movie/{tmdb_id}/watch/providers"
        resp = requests.get(url, params={'api_key': TMDB_API_KEY}, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}


def get_movie_details(tmdb_id: str) -> dict:
    """Get movie details including credits."""
    if not TMDB_API_KEY:
        return {}

    try:
        url = f"{TMDB_BASE}/movie/{tmdb_id}"
        resp = requests.get(url, params={
            'api_key': TMDB_API_KEY,
            'append_to_response': 'credits'
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}


def has_type4_release(release_data: dict) -> tuple[bool, str]:
    """Check if movie has Type 4 (Digital) release. Returns (has_type4, date)."""
    results = release_data.get('results', [])

    for country in results:
        for release in country.get('release_dates', []):
            if release.get('type') == 4:  # Digital release
                return True, release.get('release_date', '')[:10]

    return False, ''


def has_watch_providers(provider_data: dict) -> bool:
    """Check if movie has any watch providers (streaming, rent, buy)."""
    results = provider_data.get('results', {})

    # Check US first, then any country
    for country_code in ['US'] + list(results.keys()):
        if country_code not in results:
            continue
        country_data = results[country_code]
        if country_data.get('flatrate') or country_data.get('rent') or country_data.get('buy'):
            return True

    return False


def get_director(details: dict) -> str:
    """Extract director from credits."""
    credits = details.get('credits', {})
    crew = credits.get('crew', [])

    for person in crew:
        if person.get('job') == 'Director':
            return person.get('name', '')

    return ''


def is_wrestling(movie: dict) -> bool:
    """Check if movie is a wrestling event (to filter out)."""
    title_lower = movie.get('title', '').lower()
    overview_lower = movie.get('overview', '').lower()
    return any(term in title_lower or term in overview_lower for term in
               ['wrestling', 'wwe', 'aew', 'njpw', 'stardom', 'ddt', 'roh'])


def classify_drc_platform(homepage_url: str) -> str:
    """Classify DRC platform type from homepage URL.

    Returns 'EXCLUDED_<platform>' for major platforms we want to filter out.
    Returns platform name for valid DRC platforms (vimeo, patreon, etc.)
    """
    if not homepage_url:
        return ''

    try:
        parsed = urlparse(homepage_url)
        domain = parsed.netloc.lower()

        # Remove 'www.' prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]

        # MAJOR PLATFORMS TO EXCLUDE - these are NOT hidden gems
        # Netflix
        if 'netflix.com' in domain:
            return 'EXCLUDED_netflix'
        # Apple TV / iTunes
        if 'tv.apple.com' in domain or 'apple.com/tv' in domain or 'itunes.apple.com' in domain:
            return 'EXCLUDED_apple'
        # Amazon / Prime Video
        if 'amazon.com' in domain or 'primevideo.com' in domain or 'amazon.co' in domain:
            return 'EXCLUDED_amazon'
        # Hulu
        if 'hulu.com' in domain:
            return 'EXCLUDED_hulu'
        # Disney+
        if 'disneyplus.com' in domain or 'disney.com' in domain:
            return 'EXCLUDED_disney'
        # HBO / Max
        if 'hbomax.com' in domain or 'max.com' in domain or 'hbo.com' in domain:
            return 'EXCLUDED_hbo'
        # Paramount+
        if 'paramountplus.com' in domain or 'paramount.com' in domain:
            return 'EXCLUDED_paramount'
        # Peacock
        if 'peacocktv.com' in domain:
            return 'EXCLUDED_peacock'
        # Vudu / Fandango
        if 'vudu.com' in domain or 'fandangonow.com' in domain:
            return 'EXCLUDED_vudu'
        # Google Play
        if 'play.google.com' in domain:
            return 'EXCLUDED_google'
        # Microsoft Store
        if 'microsoft.com' in domain:
            return 'EXCLUDED_microsoft'

        # VALID DRC PLATFORMS - these are what we're looking for
        if 'vimeo.com' in domain:
            return 'vimeo'
        elif 'youtube.com' in domain or 'youtu.be' in domain:
            return 'youtube'
        elif 'patreon.com' in domain:
            return 'patreon'
        elif 'substack.com' in domain:
            return 'substack'
        elif 'gumroad.com' in domain:
            return 'gumroad'
        elif 'fourthwall.com' in domain:
            return 'fourthwall'
        elif 'filmhub.com' in domain:
            return 'filmhub'
        elif 'vhx.tv' in domain:
            return 'vhx'
        elif 'uscreen.io' in domain or 'uscreen.tv' in domain:
            return 'uscreen'
        elif 'eventive.org' in domain:
            return 'eventive'
        elif 'seed-spark.com' in domain or 'seedandspark.com' in domain:
            return 'seed_and_spark'
        else:
            return 'filmmaker_site'
    except Exception:
        return 'unknown'


def categorize_movie(movie: dict) -> str:
    """Categorize movie by runtime only."""
    runtime = movie.get('runtime')

    if runtime is None:
        return 'Unknown Runtime'
    if runtime >= 70:
        return 'Feature Films (70+ min)'
    if runtime >= 30:
        return 'Medium (30-69 min)'
    if runtime >= 10:
        return 'Shorts (10-29 min)'
    return 'Micro (<10 min)'


def sort_by_platform_and_runtime(gems: list) -> list:
    """Sort gems by platform priority then runtime (descending)."""
    platform_priority = {
        'vimeo': 1,
        'youtube': 2,
        'patreon': 3,
        'substack': 4,
        'gumroad': 5,
        'fourthwall': 6,
        'filmhub': 7,
        'filmmaker_site': 8,
        'unknown': 9,
        '': 10  # No platform/homepage
    }

    def sort_key(gem):
        platform = gem.get('drc_platform', '')
        priority = platform_priority.get(platform, 99)
        runtime = gem.get('runtime') or 0
        return (priority, -runtime)  # Negative runtime for descending order

    return sorted(gems, key=sort_key)


def find_hidden_gems(movies: list, verbose: bool = True) -> list:
    """Find movies with Type 4 release but no watch providers."""
    hidden_gems = []
    total = len(movies)

    for i, (tmdb_id, intake_date) in enumerate(movies):
        if verbose and (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{total}...")

        # Get release dates
        release_data = get_release_dates(tmdb_id)
        has_type4, type4_date = has_type4_release(release_data)

        if not has_type4:
            time.sleep(0.05)  # Rate limiting
            continue

        # Check watch providers
        provider_data = get_watch_providers(tmdb_id)
        if has_watch_providers(provider_data):
            time.sleep(0.05)
            continue

        # This is a hidden gem! Get full details
        details = get_movie_details(tmdb_id)

        if not details:
            time.sleep(0.05)
            continue

        genre_names = [g.get('name', '') for g in details.get('genres', [])]

        gem = {
            'id': tmdb_id,
            'title': details.get('title', 'Unknown'),
            'intake_date': intake_date,
            'type4_date': type4_date,
            'runtime': details.get('runtime'),
            'overview': details.get('overview', ''),
            'homepage': details.get('homepage', ''),
            'genres': genre_names,
            'director': get_director(details),
            'imdb': details.get('imdb_id')
        }

        # Add DRC platform classification
        gem['drc_platform'] = classify_drc_platform(gem['homepage'])

        # Filter out films on major platforms (Netflix, Apple, Amazon, etc.)
        if gem['drc_platform'].startswith('EXCLUDED_'):
            time.sleep(0.05)
            continue

        # Filter out wrestling events
        if is_wrestling(gem):
            time.sleep(0.05)
            continue

        # Filter to features only (70+ min)
        if gem.get('runtime') is None or gem.get('runtime') < 70:
            time.sleep(0.05)
            continue

        gem['category'] = categorize_movie(gem)
        gem['add_to_nrw'] = False  # Default to false for curator flagging
        hidden_gems.append(gem)

        time.sleep(0.05)  # Rate limiting

    return hidden_gems


# ===== DATE PARSING UTILITIES =====

def parse_relative_date(text: str) -> Optional[str]:
    """Parse relative date strings like '2 days ago', '1 week ago' into YYYY-MM-DD format."""
    if not text:
        return None

    text = text.lower().strip()
    now = datetime.now()

    # Handle patterns like "2 days ago", "1 week ago", "3 hours ago"
    patterns = [
        (r'(\d+)\s*seconds?\s*ago', 'seconds'),
        (r'(\d+)\s*minutes?\s*ago', 'minutes'),
        (r'(\d+)\s*hours?\s*ago', 'hours'),
        (r'(\d+)\s*days?\s*ago', 'days'),
        (r'(\d+)\s*weeks?\s*ago', 'weeks'),
        (r'(\d+)\s*months?\s*ago', 'months'),
        (r'(\d+)\s*years?\s*ago', 'years'),
        (r'yesterday', 'yesterday'),
        (r'today', 'today'),
    ]

    for pattern, unit in patterns:
        match = re.search(pattern, text)
        if match:
            if unit == 'today':
                return now.strftime('%Y-%m-%d')
            elif unit == 'yesterday':
                return (now - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                count = int(match.group(1))
                if unit == 'seconds':
                    target_date = now - timedelta(seconds=count)
                elif unit == 'minutes':
                    target_date = now - timedelta(minutes=count)
                elif unit == 'hours':
                    target_date = now - timedelta(hours=count)
                elif unit == 'days':
                    target_date = now - timedelta(days=count)
                elif unit == 'weeks':
                    target_date = now - timedelta(weeks=count)
                elif unit == 'months':
                    target_date = now - timedelta(days=count * 30)  # Approximate
                elif unit == 'years':
                    target_date = now - timedelta(days=count * 365)  # Approximate

                return target_date.strftime('%Y-%m-%d')

    # Try to parse absolute dates like "Dec 29, 2024" or "2024-12-29"
    try:
        # Common date formats
        date_formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%m-%d-%Y',
            '%B %d, %Y',
            '%b %d, %Y',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
        ]

        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(text, fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue
    except:
        pass

    return None


def is_within_date_range(date_str: str, start_date: str, end_date: str) -> bool:
    """Check if a date string falls within the specified range."""
    if not date_str:
        return False

    try:
        target = datetime.strptime(date_str, '%Y-%m-%d')
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        return start <= target <= end
    except ValueError:
        return False


def calculate_date_range(month: Optional[str] = None, days: Optional[int] = None) -> Tuple[str, str]:
    """Calculate start and end dates for filtering."""
    if month:
        # e.g., "2025-12" -> 2025-12-01 to 2025-12-31
        year, mon = month.split('-')
        start_date = f"{month}-01"
        # Get last day of month
        if mon == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(mon)+1:02d}-01"
        # Adjust end_date to last day of target month
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=1)
        end_date = end_dt.strftime('%Y-%m-%d')
    elif days:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    else:
        # Default to last 30 days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    return start_date, end_date


# ===== CLEAN INTEGRATED SCRAPING =====

def discover_from_patreon(max_creators: int = 20, min_runtime: int = 10, headless: bool = True,
                         start_date: str = None, end_date: str = None) -> List[Dict]:
    """Discover films from Patreon creators."""
    if not PLAYWRIGHT_AVAILABLE:
        print("⚠️  Playwright not available, skipping Patreon discovery")
        return []

    print(f"🎬 Discovering films from Patreon...")

    # Known film creators from research
    known_film_creators = [
        "FilmmakerIQ", "onemonthmovies", "happenfilms", "lundahl",
        "wemakemovies", "AlexProyas", "mfox", "DocumentaryFirst"
    ]

    search_terms = ["film", "movie", "documentary", "short film", "indie film", "filmmaker"]
    rate_limit = 3.0  # Patreon rate limiting
    last_request_time = 0

    def _rate_limit():
        nonlocal last_request_time
        elapsed = time.time() - last_request_time
        if elapsed < rate_limit:
            time.sleep(rate_limit - elapsed)
        last_request_time = time.time()

    @retry_with_exponential_backoff()
    def _scrape_creator_page(username: str) -> List[Dict]:
        """Scrape a Patreon creator page for film content."""
        _rate_limit()

        creator_url = f"https://www.patreon.com/{username}"
        print(f"  Scraping Patreon creator: {username}")

        playwright_manager = get_playwright_manager()
        browser = playwright_manager.get_browser(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        films = []
        try:
            page.goto(creator_url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # Extract creator info
            creator_name = ""
            try:
                name_elem = page.locator('h1[data-tag="creator-page-title"]').first
                creator_name = name_elem.text_content() if name_elem.count() > 0 else username
            except:
                creator_name = username

            # Extract posts
            try:
                page.wait_for_selector('[data-tag="post-card"]', timeout=10000)
                post_cards = page.locator('[data-tag="post-card"]').all()

                for card in post_cards[:20]:  # Limit to first 20 posts
                    try:
                        # Extract title
                        title_elem = card.locator('h3, h2, [data-tag="post-title"]').first
                        title = title_elem.text_content().strip() if title_elem.count() > 0 else ""

                        if not title:
                            continue

                        # Check if it's film content
                        content = title.lower()
                        film_keywords = ['film', 'movie', 'short', 'documentary', 'trailer',
                                       'cinema', 'screening', 'premiere', 'video', 'watch']

                        if not any(keyword in content for keyword in film_keywords):
                            continue

                        # Extract description
                        desc_elem = card.locator('[data-tag="post-content"], .post-content, p').first
                        description = desc_elem.text_content().strip() if desc_elem.count() > 0 else ""

                        # Extract post URL
                        post_url = ""
                        link_elem = card.locator('a[href*="/posts/"]').first
                        if link_elem.count() > 0:
                            post_url = "https://www.patreon.com" + link_elem.get_attribute('href')

                        # Extract post date
                        post_date = None
                        date_selectors = [
                            '[data-published-at]',  # data attribute
                            '.timestamp',           # timestamp class
                            '.published-at',        # published class
                            'time',                 # time element
                            '[title*="ago"]',       # title with "ago"
                            '.date'                 # generic date class
                        ]

                        for selector in date_selectors:
                            date_elem = card.locator(selector).first
                            if date_elem.count() > 0:
                                # Try data attributes first
                                date_attr = date_elem.get_attribute('data-published-at')
                                if date_attr:
                                    post_date = parse_relative_date(date_attr)
                                    break

                                # Try title attribute
                                title_attr = date_elem.get_attribute('title')
                                if title_attr:
                                    post_date = parse_relative_date(title_attr)
                                    break

                                # Try text content
                                date_text = date_elem.text_content().strip()
                                if date_text:
                                    post_date = parse_relative_date(date_text)
                                    break

                        # Apply date filtering if dates are provided
                        if start_date and end_date and post_date:
                            if not is_within_date_range(post_date, start_date, end_date):
                                continue

                        # Extract runtime if mentioned
                        runtime = None
                        runtime_text = title + ' ' + description
                        runtime_patterns = [
                            r'(\d+)\s*(?:minute|min|minutes)',
                            r'(\d+)\s*(?:hour|hr|hours)',
                            r'(\d+):(\d+)'
                        ]

                        for pattern in runtime_patterns:
                            match = re.search(pattern, runtime_text.lower())
                            if match:
                                if len(match.groups()) == 1:
                                    runtime = int(match.group(1))
                                    break
                                elif len(match.groups()) == 2:
                                    hours = int(match.group(1))
                                    minutes = int(match.group(2))
                                    runtime = hours * 60 + minutes
                                    break

                        if runtime and runtime < min_runtime:
                            continue

                        film_data = {
                            'title': title,
                            'description': description,
                            'creator_name': creator_name,
                            'creator_username': username,
                            'post_url': post_url,
                            'platform': 'patreon',
                            'discovery_date': datetime.now().isoformat()[:10],
                            'post_date': post_date or datetime.now().isoformat()[:10],  # Actual post date
                            'runtime': runtime,
                            'is_subscription': True,
                            'access_type': 'subscription'
                        }

                        films.append(film_data)

                    except Exception as e:
                        continue

            except Exception as e:
                print(f"    No posts found for {username}")

        except Exception as e:
            print(f"    Error scraping {username}: {str(e)[:50]}...")
        finally:
            context.close()

        return films

    # Discover from known creators
    all_films = []
    processed = 0

    for creator in known_film_creators[:max_creators]:
        try:
            films = _scrape_creator_page(creator)
            all_films.extend(films)
            processed += 1
            print(f"    Found {len(films)} films from {creator}")
        except Exception as e:
            print(f"    Error with {creator}: {e}")
            continue

    print(f"📊 Patreon discovery: {len(all_films)} films from {processed} creators")
    return all_films


def discover_from_justwatch_vimeo(max_items: int = 50, min_runtime: int = 70, headless: bool = True) -> List[Dict]:
    """
    Discover new films on Vimeo via JustWatch's "New on Vimeo" page.

    JustWatch tracks new releases by provider, so this is more reliable than
    scraping Vimeo directly (which has deprecated its discovery features).
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("⚠️  Playwright not available, skipping JustWatch/Vimeo discovery")
        return []

    print(f"🎬 Discovering new films on Vimeo via JustWatch...")

    url = "https://www.justwatch.com/us/provider/vimeo/new/movies"

    playwright_manager = get_playwright_manager()
    browser = playwright_manager.get_browser(headless=headless)
    context = browser.new_context()
    page = context.new_page()

    films = []
    try:
        page.goto(url, timeout=30000)
        page.wait_for_selector('body', timeout=10000)
        time.sleep(3)  # Let JS render

        # Scroll to load more content
        for _ in range(3):
            page.keyboard.press('End')
            time.sleep(1)

        # JustWatch uses title-card elements for movie listings
        # Look for movie cards in the timeline/new releases section
        selectors = [
            '[data-testid="title-card"]',
            '.title-card',
            'a[href*="/us/movie/"]',
            '.timeline-card',
            '[class*="TitleCard"]'
        ]

        film_elements = []
        for selector in selectors:
            elements = page.locator(selector).all()
            if elements:
                print(f"  Found {len(elements)} elements with selector: {selector}")
                film_elements = elements[:max_items]
                break

        if not film_elements:
            # Fallback: find all movie links
            film_elements = page.locator('a[href*="/movie/"]').all()[:max_items]
            print(f"  Fallback: found {len(film_elements)} movie links")

        for element in film_elements:
            try:
                # Extract title
                title = ""
                title_selectors = ['h3', 'h2', '.title', '[class*="title"]', 'span']
                for sel in title_selectors:
                    title_elem = element.locator(sel).first
                    if title_elem.count() > 0:
                        title = title_elem.text_content().strip()
                        if title and len(title) > 2:
                            break

                if not title:
                    # Try element text directly
                    title = element.text_content().strip()[:100]

                if not title or len(title) < 3:
                    continue

                # Extract URL
                href = element.get_attribute('href') or ""
                if not href:
                    link_elem = element.locator('a').first
                    if link_elem.count() > 0:
                        href = link_elem.get_attribute('href') or ""

                jw_url = href if href.startswith('http') else f"https://www.justwatch.com{href}" if href else ""

                # Extract year if visible
                year = None
                text = element.text_content()
                year_match = re.search(r'\((\d{4})\)', text)
                if year_match:
                    year = int(year_match.group(1))

                films.append({
                    'title': title,
                    'justwatch_url': jw_url,
                    'year': year,
                    'platform': 'vimeo',
                    'source': 'justwatch_vimeo_new',
                    'discovery_date': datetime.now().isoformat()[:10]
                })

            except Exception as e:
                continue

        print(f"  Scraped {len(films)} films from JustWatch/Vimeo")

    except Exception as e:
        print(f"  Error scraping JustWatch: {str(e)[:100]}")
    finally:
        context.close()

    # Deduplicate by title
    seen = set()
    unique_films = []
    for f in films:
        key = f['title'].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_films.append(f)

    print(f"📊 JustWatch/Vimeo discovery: {len(unique_films)} unique films")
    return unique_films


def discover_from_vimeo(max_pages: int = 5, categories: List[str] = None, min_runtime: int = 70, headless: bool = True,
                       start_date: str = None, end_date: str = None) -> List[Dict]:
    """Discover films from Vimeo On Demand. (DEPRECATED - use discover_from_justwatch_vimeo instead)"""
    if not PLAYWRIGHT_AVAILABLE:
        print("⚠️  Playwright not available, skipping Vimeo discovery")
        return []

    if categories is None:
        categories = ["drama", "documentary", "comedy", "thriller"]

    print(f"🎬 Discovering films from Vimeo On Demand...")

    rate_limit = 2.0
    last_request_time = 0

    def _rate_limit():
        nonlocal last_request_time
        elapsed = time.time() - last_request_time
        if elapsed < rate_limit:
            time.sleep(rate_limit - elapsed)
        last_request_time = time.time()

    @retry_with_exponential_backoff()
    def _scrape_vimeo_browse_page(url: str) -> List[Dict]:
        """Scrape a single Vimeo browse page for film listings."""
        _rate_limit()

        print(f"  Scraping Vimeo page: {url}")

        playwright_manager = get_playwright_manager()
        browser = playwright_manager.get_browser(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        films = []
        try:
            page.goto(url, timeout=30000)
            page.wait_for_selector('body', timeout=10000)
            time.sleep(2)

            # Look for film cards
            selectors = ['.ondemand-card', '.vod-card', '.browse-item', '[data-testid*="film"]',
                        '.film-card', 'article[data-item-id]', '.grid-item']

            film_elements = []
            for selector in selectors:
                elements = page.locator(selector).all()
                if elements:
                    film_elements = elements
                    break

            if not film_elements:
                # Fallback
                film_elements = page.locator('a[href*="/ondemand/"]').all()

            for element in film_elements:
                try:
                    # Extract title
                    title_selectors = ['h3', 'h2', '.title', '[data-testid*="title"]', 'a']
                    title = ""
                    for selector in title_selectors:
                        title_elem = element.locator(selector).first
                        if title_elem.count() > 0:
                            title = title_elem.text_content().strip()
                            if title:
                                break

                    if not title:
                        continue

                    # Extract URL
                    url_elem = element.locator('a').first
                    film_url = ""
                    if url_elem.count() > 0:
                        href = url_elem.get_attribute('href')
                        if href:
                            film_url = href if href.startswith('http') else f"https://vimeo.com{href}"

                    # Extract price info
                    price_elem = element.locator('.price, [data-testid*="price"], .cost').first
                    price_text = price_elem.text_content() if price_elem.count() > 0 else ""

                    # Extract description
                    desc_elem = element.locator('.description, .summary, p').first
                    description = desc_elem.text_content().strip() if desc_elem.count() > 0 else ""

                    # Extract upload/release date
                    upload_date = None
                    date_selectors = [
                        '[data-upload-date]',    # data attribute
                        '[data-release-date]',   # release date attribute
                        '.upload-date',          # upload date class
                        '.release-date',         # release date class
                        '.date',                 # generic date class
                        'time',                  # time element
                        '[title*="ago"]',        # title with "ago"
                        '.published'             # published class
                    ]

                    for selector in date_selectors:
                        date_elem = element.locator(selector).first
                        if date_elem.count() > 0:
                            # Try data attributes first
                            date_attr = date_elem.get_attribute('data-upload-date') or date_elem.get_attribute('data-release-date')
                            if date_attr:
                                upload_date = parse_relative_date(date_attr)
                                break

                            # Try title attribute
                            title_attr = date_elem.get_attribute('title')
                            if title_attr:
                                upload_date = parse_relative_date(title_attr)
                                break

                            # Try text content
                            date_text = date_elem.text_content().strip()
                            if date_text:
                                upload_date = parse_relative_date(date_text)
                                break

                    # Apply date filtering if dates are provided
                    if start_date and end_date and upload_date:
                        if not is_within_date_range(upload_date, start_date, end_date):
                            continue

                    # Basic runtime extraction
                    runtime = None
                    runtime_text = title + ' ' + description + ' ' + price_text
                    runtime_match = re.search(r'(\d+)\s*(?:min|minutes)', runtime_text.lower())
                    if runtime_match:
                        runtime = int(runtime_match.group(1))

                    if runtime and runtime < min_runtime:
                        continue

                    films.append({
                        'title': title,
                        'vimeo_url': film_url,
                        'description': description,
                        'price_text': price_text,
                        'runtime': runtime,
                        'platform': 'vimeo',
                        'upload_date': upload_date,
                        'discovery_date': datetime.now().isoformat()[:10]
                    })

                except Exception:
                    continue

        except Exception as e:
            print(f"    Error scraping page: {str(e)[:50]}...")
        finally:
            context.close()

        return films

    # Browse categories
    all_films = []
    base_urls = [
        "https://vimeo.com/ondemand/browse/sort:date",
        "https://vimeo.com/ondemand/browse/sort:featured",
        "https://vimeo.com/ondemand"
    ]

    for category in categories:
        for base_url in base_urls:
            try:
                if "browse" in base_url:
                    url = f"{base_url}/genre:{category}"
                else:
                    url = f"{base_url}?genre={category}"

                films = _scrape_vimeo_browse_page(url)
                all_films.extend(films)
                print(f"    Found {len(films)} films in {category}")

                if len(all_films) >= max_pages * 20:  # Approximate limit
                    break
            except Exception as e:
                print(f"    Error with category {category}: {e}")
                continue

    print(f"📊 Vimeo discovery: {len(all_films)} films")
    return all_films


def discover_from_youtube(max_searches: int = 5, search_terms: List[str] = None, min_runtime: int = 70, headless: bool = True,
                         start_date: str = None, end_date: str = None) -> List[Dict]:
    """Discover films from YouTube Movies."""
    if not PLAYWRIGHT_AVAILABLE:
        print("⚠️  Playwright not available, skipping YouTube discovery")
        return []

    if search_terms is None:
        search_terms = ["independent film", "indie movie", "documentary", "short film"]

    print(f"🎬 Discovering films from YouTube...")

    rate_limit = 3.0
    last_request_time = 0

    def _rate_limit():
        nonlocal last_request_time
        elapsed = time.time() - last_request_time
        if elapsed < rate_limit:
            time.sleep(rate_limit - elapsed)
        last_request_time = time.time()

    @retry_with_exponential_backoff()
    def _search_youtube_films(search_term: str) -> List[Dict]:
        """Search YouTube for films."""
        _rate_limit()

        search_url = f"https://www.youtube.com/results?search_query={search_term.replace(' ', '+')}"
        print(f"  Searching YouTube: {search_term}")

        playwright_manager = get_playwright_manager()
        browser = playwright_manager.get_browser(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        films = []
        try:
            page.goto(search_url, timeout=30000)
            page.wait_for_selector('body', timeout=10000)
            time.sleep(3)

            # Look for video elements
            selectors = ['.ytd-video-renderer', '.ytd-movie-renderer', '.ytd-grid-video-renderer']

            video_elements = []
            for selector in selectors:
                elements = page.locator(selector).all()
                if elements:
                    video_elements = elements[:20]  # Limit results
                    break

            for element in video_elements:
                try:
                    # Extract title
                    title_elem = element.locator('#video-title, .title, a[href*="/watch"]').first
                    title = title_elem.text_content().strip() if title_elem.count() > 0 else ""

                    if not title:
                        continue

                    # Extract URL
                    link_elem = element.locator('a[href*="/watch"]').first
                    video_url = ""
                    if link_elem.count() > 0:
                        href = link_elem.get_attribute('href')
                        if href:
                            video_url = href if href.startswith('http') else f"https://www.youtube.com{href}"

                    # Extract channel
                    channel_elem = element.locator('.channel-name, .ytd-channel-name, a[href*="/channel"], a[href*="/@"]').first
                    channel = channel_elem.text_content().strip() if channel_elem.count() > 0 else ""

                    # Extract duration
                    duration_elem = element.locator('.duration, .badge').first
                    duration_text = duration_elem.text_content() if duration_elem.count() > 0 else ""

                    # Parse runtime
                    runtime = None
                    if duration_text:
                        # Parse MM:SS or HH:MM:SS
                        time_parts = duration_text.split(':')
                        if len(time_parts) == 2:  # MM:SS
                            runtime = int(time_parts[0])
                        elif len(time_parts) == 3:  # HH:MM:SS
                            runtime = int(time_parts[0]) * 60 + int(time_parts[1])

                    if runtime and runtime < min_runtime:
                        continue

                    # Extract upload date
                    upload_date = None
                    date_selectors = [
                        '[data-published-time]',  # data attribute
                        '.published-time',        # published time class
                        '.upload-date',          # upload date class
                        '.date',                 # generic date class
                        'time',                  # time element
                        '[title*="ago"]',        # title with "ago"
                        '.metadata-line'         # metadata line
                    ]

                    for selector in date_selectors:
                        date_elem = element.locator(selector).first
                        if date_elem.count() > 0:
                            # Try data attributes first
                            date_attr = date_elem.get_attribute('data-published-time')
                            if date_attr:
                                upload_date = parse_relative_date(date_attr)
                                break

                            # Try title attribute
                            title_attr = date_elem.get_attribute('title')
                            if title_attr:
                                upload_date = parse_relative_date(title_attr)
                                break

                            # Try text content
                            date_text = date_elem.text_content().strip()
                            if date_text:
                                upload_date = parse_relative_date(date_text)
                                break

                    # Apply date filtering if dates are provided
                    if start_date and end_date and upload_date:
                        if not is_within_date_range(upload_date, start_date, end_date):
                            continue

                    # Check if it's likely a film
                    film_indicators = ['film', 'movie', 'documentary', 'feature', 'full movie']
                    if not any(indicator in title.lower() for indicator in film_indicators):
                        continue

                    films.append({
                        'title': title,
                        'youtube_url': video_url,
                        'channel_name': channel,
                        'duration_text': duration_text,
                        'runtime': runtime,
                        'platform': 'youtube',
                        'upload_date': upload_date,
                        'discovery_date': datetime.now().isoformat()[:10]
                    })

                except Exception:
                    continue

        except Exception as e:
            print(f"    Error searching YouTube: {str(e)[:50]}...")
        finally:
            context.close()

        return films

    # Search with different terms
    all_films = []
    for term in search_terms[:max_searches]:
        try:
            films = _search_youtube_films(term)
            all_films.extend(films)
            print(f"    Found {len(films)} films for '{term}'")
        except Exception as e:
            print(f"    Error with search term '{term}': {e}")
            continue

    print(f"📊 YouTube discovery: {len(all_films)} films")
    return all_films


def save_csv(gems: list, output_path: str):
    """Save hidden gems to CSV."""
    category_order = [
        'Feature Films (70+ min)',
        'Medium (30-69 min)',
        'Shorts (10-29 min)',
        'Micro (<10 min)',
        'Unknown Runtime'
    ]

    # Sort by category then title
    def sort_key(g):
        cat_idx = category_order.index(g['category']) if g['category'] in category_order else 99
        return (cat_idx, g.get('title', '').lower())

    sorted_gems = sorted(gems, key=sort_key)

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Title', 'Category', 'DRC Platform', 'Runtime', 'Genres', 'Director',
                        'Watch Link', 'IMDB', 'TMDB', 'Overview', 'Price (Rent)', 'Price (Buy)', 'TMDB Confidence'])

        for gem in sorted_gems:
            imdb_url = f"https://www.imdb.com/title/{gem['imdb']}/" if gem.get('imdb') else ""
            tmdb_id = gem.get('id', '')
            tmdb_url = f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else ""

            writer.writerow([
                gem.get('title', ''),
                gem.get('category', ''),
                gem.get('drc_platform', ''),
                gem.get('runtime', ''),
                ', '.join(gem.get('genres', [])),
                gem.get('director', ''),
                gem.get('homepage', ''),
                imdb_url,
                tmdb_url,
                gem.get('overview', '')[:150],
                gem.get('price_rent', ''),
                gem.get('price_buy', ''),
                gem.get('tmdb_match_confidence', '')
            ])

    print(f"✅ Saved {len(gems)} hidden gems to {output_path}")


def save_curation_csv(gems: list, output_path: str):
    """Save hidden gems in curation-ready CSV format."""
    # Sort by platform and runtime
    sorted_gems = sort_by_platform_and_runtime(gems)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Simplified header for curation workflow
        writer.writerow([
            'Add to NRW', 'Title', 'Platform', 'Runtime', 'Director/Channel',
            'Watch Link', 'Price (Rent)', 'Price (Buy)', 'TMDB ID', 'IMDB',
            'Genres', 'Overview', 'Discovery Source', 'TMDB Confidence'
        ])

        for gem in sorted_gems:
            # Determine discovery source
            discovery_source = 'TMDB'
            if gem.get('vimeo_url'):
                discovery_source = 'Vimeo Scraper'
            elif gem.get('youtube_url'):
                discovery_source = 'YouTube Scraper'
            elif gem.get('patreon_url'):
                discovery_source = 'Patreon Scraper'

            # Get director/channel name
            director = gem.get('director', '') or gem.get('channel_name', '') or gem.get('filmmaker', '')

            # Format platform name
            platform_names = {
                'vimeo': 'Vimeo',
                'youtube': 'YouTube',
                'patreon': 'Patreon',
                'substack': 'Substack',
                'gumroad': 'Gumroad',
                'fourthwall': 'Fourthwall',
                'filmhub': 'FilmHub',
                'filmmaker_site': 'Filmmaker Site',
                'unknown': 'Unknown',
                '': 'No Homepage'
            }
            platform = platform_names.get(gem.get('drc_platform', ''), gem.get('drc_platform', ''))

            # Get watch link (prefer platform-specific URLs)
            watch_link = gem.get('vimeo_url') or gem.get('youtube_url') or gem.get('patreon_url') or gem.get('homepage', '')

            # Get TMDB and IMDB links
            tmdb_id = gem.get('id', '')
            tmdb_url = f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else ""
            imdb_id = gem.get('imdb', '')
            imdb_url = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else ""

            # Handle free films
            price_rent = gem.get('price_rent', '')
            price_buy = gem.get('price_buy', '')
            if gem.get('is_free'):
                price_rent = 'Free'
                price_buy = 'Free'

            writer.writerow([
                'FALSE',  # add_to_nrw - curator will change to TRUE
                gem.get('title', ''),
                platform,
                gem.get('runtime', ''),
                director,
                watch_link,
                price_rent,
                price_buy,
                tmdb_url,
                imdb_url,
                ', '.join(gem.get('genres', [])),
                gem.get('overview', '')[:200],  # Truncate for readability
                discovery_source,
                gem.get('tmdb_match_confidence', '')
            ])

    print(f"✅ Saved curation CSV to {output_path}")


def save_curation_json(gems: list, output_path: str):
    """Save hidden gems in curation-ready JSON format."""
    # Sort by platform and runtime
    sorted_gems = sort_by_platform_and_runtime(gems)

    # Create curation-optimized structure
    curation_data = {
        'generated_at': datetime.now().isoformat(),
        'total_films': len(sorted_gems),
        'films': []
    }

    for gem in sorted_gems:
        # Determine discovery source
        discovery_source = 'TMDB'
        if gem.get('vimeo_url'):
            discovery_source = 'Vimeo Scraper'
        elif gem.get('youtube_url'):
            discovery_source = 'YouTube Scraper'
        elif gem.get('patreon_url'):
            discovery_source = 'Patreon Scraper'

        # Get director/channel name
        director = gem.get('director', '') or gem.get('channel_name', '') or gem.get('filmmaker', '')

        # Get watch link
        watch_link = gem.get('vimeo_url') or gem.get('youtube_url') or gem.get('patreon_url') or gem.get('homepage', '')

        curation_film = {
            'add_to_nrw': False,
            'title': gem.get('title', ''),
            'tmdb_id': gem.get('id'),
            'platform': gem.get('drc_platform', ''),
            'watch_url': watch_link,
            'runtime': gem.get('runtime'),
            'director': director,
            'description': gem.get('overview', ''),
            'price': {
                'rent': gem.get('price_rent'),
                'buy': gem.get('price_buy'),
                'is_free': gem.get('is_free', False)
            },
            'discovery_source': discovery_source,
            'tmdb_confidence': gem.get('tmdb_match_confidence', 'none'),
            'genres': gem.get('genres', []),
            'release_year': gem.get('release_year'),
            'imdb_id': gem.get('imdb'),
            'metadata': {
                'intake_date': gem.get('intake_date', ''),
                'type4_date': gem.get('type4_date', ''),
                'discovery_date': gem.get('discovery_date', ''),
                'category': gem.get('category', '')
            }
        }

        curation_data['films'].append(curation_film)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(curation_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved curation JSON to {output_path}")


def save_markdown(gems: list, output_path: str):
    """Save hidden gems to markdown."""
    category_order = [
        'Feature Films (70+ min)',
        'Medium (30-69 min)',
        'Shorts (10-29 min)',
        'Micro (<10 min)',
        'Unknown Runtime'
    ]

    # Group by category
    by_category = {}
    for gem in gems:
        cat = gem.get('category', 'Unknown')
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(gem)

    md = f"# Hidden Gems - {datetime.now().strftime('%Y-%m-%d')}\n"
    md += f"{len(gems)} indie films with digital releases not on major platforms\n\n"
    md += "🔗 = Direct watch link · 📄 = IMDB\n\n"
    md += "---\n\n"

    for cat_name in category_order:
        if cat_name not in by_category:
            continue

        cat_gems = sorted(by_category[cat_name], key=lambda x: x.get('title', '').lower())
        md += f"## {cat_name} ({len(cat_gems)})\n\n"

        for gem in cat_gems:
            title = gem.get('title', 'Unknown')
            tmdb_id = gem.get('id', '')
            runtime = gem.get('runtime')
            runtime_str = f"{runtime}min" if runtime else ""
            genres = gem.get('genres', [])[:2]
            genre_str = ', '.join(genres) if genres else ''
            director = gem.get('director', '')
            homepage = gem.get('homepage', '')
            imdb = gem.get('imdb')
            drc_platform = gem.get('drc_platform', '')

            # Add platform emoji/label
            platform_label = ''
            if drc_platform == 'vimeo':
                platform_label = '🎬 Vimeo'
            elif drc_platform == 'youtube':
                platform_label = '📺 YouTube'
            elif drc_platform == 'patreon':
                platform_label = '💰 Patreon'
            elif drc_platform == 'substack':
                platform_label = '📰 Substack'
            elif drc_platform == 'gumroad':
                platform_label = '💳 Gumroad'
            elif drc_platform == 'fourthwall':
                platform_label = '🛒 Fourthwall'
            elif drc_platform == 'filmhub':
                platform_label = '🎞️ FilmHub'
            elif drc_platform == 'filmmaker_site':
                platform_label = '🎥 Filmmaker Site'
            elif drc_platform == 'unknown':
                platform_label = '❓ Unknown'

            info_parts = [p for p in [platform_label, runtime_str, genre_str, director] if p]
            info = " · ".join(info_parts) if info_parts else ""

            links = []
            if homepage:
                links.append(f"[🔗 Watch]({homepage})")
            if imdb:
                links.append(f"[📄 IMDB](https://www.imdb.com/title/{imdb}/)")
            if tmdb_id:
                links.append(f"[TMDB](https://www.themoviedb.org/movie/{tmdb_id})")
            link_str = " · ".join(links)

            # Add pricing info for Vimeo and YouTube films
            price_info = []
            if gem.get('is_free'):
                price_info.append("Free")
            else:
                if gem.get('price_rent') and gem['price_rent'] != 'Free':
                    price_info.append(f"Rent: {gem['price_rent']}")
                if gem.get('price_buy') and gem['price_buy'] != 'Free':
                    price_info.append(f"Buy: {gem['price_buy']}")
            if price_info:
                info_parts.append(" | ".join(price_info))

            if info:
                md += f"- **{title}** — {info}\n  {link_str}\n"
            else:
                md += f"- **{title}**\n  {link_str}\n"

        md += "\n"

    with open(output_path, 'w') as f:
        f.write(md)

    print(f"✅ Saved markdown to {output_path}")


def save_json(gems: list, output_path: str):
    """Save raw JSON for future use."""
    with open(output_path, 'w') as f:
        json.dump(gems, f, indent=2)
    print(f"✅ Saved JSON to {output_path}")


def print_summary(gems: list, curation_mode: bool = False):
    """Print category summary."""
    by_category = {}
    for gem in gems:
        cat = gem.get('category', 'Unknown')
        by_category[cat] = by_category.get(cat, 0) + 1

    print(f"\n📊 Found {len(gems)} hidden gems:")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"   {cat}: {count}")

    with_watch = len([g for g in gems if g.get('homepage')])
    with_imdb = len([g for g in gems if g.get('imdb')])
    print(f"\n   {with_watch} have direct watch links")
    print(f"   {with_imdb} have IMDB pages")

    # Platform breakdown
    by_platform = {}
    for gem in gems:
        platform = gem.get('drc_platform', 'unknown')
        if platform == '':
            platform = 'no_homepage'
        by_platform[platform] = by_platform.get(platform, 0) + 1

    print(f"\nPlatform breakdown:")
    for platform, count in sorted(by_platform.items(), key=lambda x: -x[1]):
        platform_name = {
            'vimeo': 'Vimeo',
            'youtube': 'YouTube',
            'patreon': 'Patreon',
            'substack': 'Substack',
            'gumroad': 'Gumroad',
            'fourthwall': 'Fourthwall',
            'filmhub': 'FilmHub',
            'filmmaker_site': 'Filmmaker sites',
            'unknown': 'Unknown',
            'no_homepage': 'No homepage'
        }.get(platform, platform)
        print(f"   {platform_name}: {count}")

    if curation_mode:
        print("\n📋 Curation Workflow:")
        print("   1. Open the *_curation.csv file")
        print("   2. Review each film's watch link and metadata")
        print("   3. Change 'FALSE' to 'TRUE' in 'Add to NRW' column for films to add")
        print("   4. Use the TMDB ID to add approved films to your NRW database")


def main():
    parser = argparse.ArgumentParser(description='Find hidden gem indie films')
    parser.add_argument('--month', help='Filter by month (e.g., 2025-12)')
    parser.add_argument('--days', type=int, default=30, help='Last N days (default: 30)')
    parser.add_argument('--output', default='hidden_gems', help='Output filename prefix')
    parser.add_argument('--quiet', action='store_true', help='Suppress progress output')

    # Live scraping options
    parser.add_argument('--scrape-vimeo', action='store_true', help='Directly scrape Vimeo On Demand (live scraping)')
    parser.add_argument('--scrape-youtube', action='store_true', help='Directly scrape YouTube Movies (live scraping)')
    parser.add_argument('--scrape-patreon', action='store_true', help='Directly scrape Patreon creators (live scraping)')
    parser.add_argument('--scrape-all', action='store_true', help='Directly scrape all platforms (Vimeo, YouTube, Patreon)')

    # Scraping configuration
    parser.add_argument('--max-creators', type=int, default=10, help='Max Patreon creators to scrape (default: 10)')
    parser.add_argument('--max-pages', type=int, default=3, help='Max pages to scrape per platform (default: 3)')
    parser.add_argument('--min-runtime', type=int, default=70, help='Minimum runtime for discovered films (default: 70)')
    parser.add_argument('--headless', action='store_true', default=True, help='Run browser in headless mode (default: true)')
    parser.add_argument('--no-headless', action='store_false', dest='headless', help='Run browser with GUI')

    parser.add_argument('--export-for-curation', action='store_true',
                       help='Export in curation-ready format with add_to_nrw field')
    args = parser.parse_args()

    if not TMDB_API_KEY:
        print("❌ TMDB_API_KEY environment variable not set")
        return 1

    print("🎬 Hidden Gems Scraper")
    print("=" * 40)

    # Query TMDB directly for movies with premiere dates
    if args.month:
        print(f"🔍 Discovering movies from {args.month}...")
        movies = discover_movies_from_tmdb(month=args.month)
    else:
        print(f"🔍 Discovering movies from last {args.days} days...")
        movies = discover_movies_from_tmdb(days=args.days)

    print(f"   Found {len(movies)} movies to check")

    if not movies:
        print("⚠️  No movies found matching filter")
        return 0

    # Find hidden gems
    print(f"\n🔎 Checking for hidden gems (Type 4 release, no providers)...")
    gems = find_hidden_gems(movies, verbose=not args.quiet)


    # DIRECT SCRAPING (New unified approach)
    # Consolidate direct scraping flags
    scrape_vimeo = args.scrape_vimeo or args.scrape_all
    scrape_youtube = args.scrape_youtube or args.scrape_all
    scrape_patreon = args.scrape_patreon or args.scrape_all

    # Direct scraping from platforms
    if scrape_vimeo or scrape_youtube or scrape_patreon:
        print(f"\n🚀 LIVE SCRAPING MODE")
        print("=" * 40)

        # Calculate date range for platform scraping
        start_date, end_date = calculate_date_range(month=args.month, days=args.days)

        # Create list to store directly scraped films
        scraped_films = []

        if scrape_vimeo:
            try:
                vimeo_films = discover_from_vimeo(
                    max_pages=args.max_pages,
                    min_runtime=args.min_runtime,
                    headless=args.headless,
                    start_date=start_date,
                    end_date=end_date
                )
                # Convert to gems format
                for film in vimeo_films:
                    scraped_films.append({
                        'id': None,
                        'title': film['title'],
                        'intake_date': film['discovery_date'],
                        'type4_date': '',
                        'runtime': film.get('runtime'),
                        'overview': film.get('description', ''),
                        'homepage': film.get('vimeo_url', ''),
                        'genres': [],
                        'director': '',
                        'imdb': None,
                        'drc_platform': 'vimeo',
                        'category': 'Feature Films (70+ min)' if film.get('runtime', 0) >= 70 else 'Shorts (10-69 min)',
                        'vimeo_url': film.get('vimeo_url', ''),
                        'price_text': film.get('price_text', ''),
                        'add_to_nrw': False
                    })
            except Exception as e:
                print(f"⚠️  Error scraping Vimeo: {e}")

        if scrape_youtube:
            try:
                youtube_films = discover_from_youtube(
                    max_searches=args.max_pages,
                    min_runtime=args.min_runtime,
                    headless=args.headless,
                    start_date=start_date,
                    end_date=end_date
                )
                # Convert to gems format
                for film in youtube_films:
                    scraped_films.append({
                        'id': None,
                        'title': film['title'],
                        'intake_date': film['discovery_date'],
                        'type4_date': '',
                        'runtime': film.get('runtime'),
                        'overview': '',
                        'homepage': film.get('youtube_url', ''),
                        'genres': [],
                        'director': film.get('channel_name', ''),
                        'imdb': None,
                        'drc_platform': 'youtube',
                        'category': 'Feature Films (70+ min)' if film.get('runtime', 0) >= 70 else 'Shorts (10-69 min)',
                        'youtube_url': film.get('youtube_url', ''),
                        'channel_name': film.get('channel_name', ''),
                        'duration_text': film.get('duration_text', ''),
                        'add_to_nrw': False
                    })
            except Exception as e:
                print(f"⚠️  Error scraping YouTube: {e}")

        if scrape_patreon:
            try:
                patreon_films = discover_from_patreon(
                    max_creators=args.max_creators,
                    min_runtime=args.min_runtime,
                    headless=args.headless,
                    start_date=start_date,
                    end_date=end_date
                )
                # Convert to gems format
                for film in patreon_films:
                    scraped_films.append({
                        'id': None,
                        'title': film['title'],
                        'intake_date': film['discovery_date'],
                        'type4_date': '',
                        'runtime': film.get('runtime'),
                        'overview': film.get('description', ''),
                        'homepage': film.get('post_url', ''),
                        'genres': [],
                        'director': film.get('creator_name', ''),
                        'imdb': None,
                        'drc_platform': 'patreon',
                        'category': 'Feature Films (70+ min)' if film.get('runtime', 0) >= 70 else 'Shorts (10-69 min)',
                        'patreon_url': film.get('post_url', ''),
                        'creator_username': film.get('creator_username', ''),
                        'is_subscription': film.get('is_subscription', True),
                        'access_type': film.get('access_type', 'subscription'),
                        'add_to_nrw': False
                    })
            except Exception as e:
                print(f"⚠️  Error scraping Patreon: {e}")

        # Merge scraped films with existing gems
        if scraped_films:
            print(f"\n🎬 Adding {len(scraped_films)} directly scraped films...")
            gems.extend(scraped_films)

            # Deduplicate by title (basic deduplication)
            seen_titles = set()
            unique_gems = []
            for gem in gems:
                title_key = gem.get('title', '').lower().strip()
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    unique_gems.append(gem)

            gems = unique_gems
            print(f"   After deduplication: {len(gems)} total films")

    if not gems:
        print("😢 No hidden gems found")
        return 0

    # Save outputs
    print()
    if args.export_for_curation:
        # Curation-optimized exports
        save_curation_csv(gems, f"{args.output}_curation.csv")
        save_curation_json(gems, f"{args.output}_curation.json")
        print("\n📋 Curation exports generated!")
        print("   Review the CSV, change 'FALSE' to 'TRUE' in 'Add to NRW' column for films to add")
    else:
        # Standard exports
        save_csv(gems, f"{args.output}.csv")
        save_markdown(gems, f"{args.output}.md")
        save_json(gems, f"{args.output}.json")

    # Print summary
    print_summary(gems, curation_mode=args.export_for_curation)

    return 0


if __name__ == '__main__':
    exit(main())
