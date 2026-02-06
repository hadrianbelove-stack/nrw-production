"""
Letterboxd Video Store scraper - simple HTTP-based scraper.
"""

import json
import logging
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
from bs4 import BeautifulSoup

# Module-level logger
logger = logging.getLogger(__name__)


class LetterboxdScraper:
    """Scrapes Letterboxd Video Store for exclusive rental films."""

    SECTIONS = {
        'unreleased-gems': 'https://letterboxd.com/video-store/unreleased-gems/',
        'lost-and-found': 'https://letterboxd.com/video-store/lost-and-found/',
        'new-releases': 'https://letterboxd.com/video-store/new-releases/',
    }

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    def __init__(self, cache_file: str = "cache/letterboxd_cache.json", config: dict = None, headless: bool = True):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.tmdb_api_key = self._get_tmdb_api_key()
        self.rate_limit_delay = 1.0
        self.last_request = 0

    def _get_tmdb_api_key(self) -> str:
        import os
        return os.getenv("TMDB_API_KEY", "99b122ce7fa3e9065d7b7dc6e660772d")

    def _load_cache(self) -> dict:
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _save_cache(self):
        import os
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def _enforce_rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request = time.time()

    def _scrape_section(self, section_name: str, url: str) -> List[Dict]:
        """Scrape a Letterboxd Video Store section."""
        logger.info(f"Fetching {section_name}: {url}")
        self._enforce_rate_limit()

        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        films = []

        # Find film posters/cards - Letterboxd uses data-film-slug on poster elements
        for poster in soup.select('[data-film-slug]'):
            slug = poster.get('data-film-slug')
            if not slug:
                continue

            # Get title from img alt or data attributes
            img = poster.select_one('img')
            title = img.get('alt') if img else None
            if not title:
                title = slug.replace('-', ' ').title()

            films.append({
                'title': title,
                'letterboxd_slug': slug,
                'letterboxd_url': f"https://letterboxd.com/film/{slug}/",
                'section': section_name,
                'discovery_date': datetime.now().strftime('%Y-%m-%d')
            })

        # Also check for film links as backup
        if not films:
            for link in soup.select('a[href*="/film/"]'):
                href = link.get('href', '')
                match = re.search(r'/film/([^/]+)/', href)
                if match:
                    slug = match.group(1)
                    title = link.get_text(strip=True) or slug.replace('-', ' ').title()
                    if slug and not any(f['letterboxd_slug'] == slug for f in films):
                        films.append({
                            'title': title,
                            'letterboxd_slug': slug,
                            'letterboxd_url': f"https://letterboxd.com/film/{slug}/",
                            'section': section_name,
                            'discovery_date': datetime.now().strftime('%Y-%m-%d')
                        })

        logger.info(f"Found {len(films)} films in {section_name}")
        return films

    def _get_film_details(self, slug: str) -> Optional[Dict]:
        """Get details from a film's Letterboxd page."""
        cache_key = f"film_{slug}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        self._enforce_rate_limit()
        url = f"https://letterboxd.com/film/{slug}/"

        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')
        details = {'letterboxd_slug': slug, 'letterboxd_url': url}

        # Title
        title_elem = soup.select_one('h1.headline-1, .film-title-wrapper h1')
        if title_elem:
            details['title'] = title_elem.get_text(strip=True)

        # Year
        year_elem = soup.select_one('.releaseyear a, [href*="/films/year/"]')
        if year_elem:
            year_text = year_elem.get_text(strip=True)
            if year_text.isdigit():
                details['year'] = int(year_text)

        # Director
        director_elem = soup.select_one('a[href*="/director/"]')
        if director_elem:
            details['director'] = director_elem.get_text(strip=True)

        # Runtime
        runtime_match = re.search(r'(\d+)\s*mins?', resp.text)
        if runtime_match:
            details['runtime'] = int(runtime_match.group(1))

        self.cache[cache_key] = details
        self._save_cache()
        return details

    def _match_with_tmdb(self, title: str, year: Optional[int] = None) -> Tuple[Optional[Dict], str]:
        """Match film with TMDB."""
        cache_key = f"tmdb_{title.lower()}_{year or 'noyear'}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            return cached.get('data'), cached.get('confidence', 'none')

        try:
            params = {'api_key': self.tmdb_api_key, 'query': title}
            if year:
                params['year'] = year

            time.sleep(0.1)
            resp = requests.get('https://api.themoviedb.org/3/search/movie', params=params, timeout=10)
            results = resp.json().get('results', [])

            if not results:
                self.cache[cache_key] = {'data': None, 'confidence': 'none'}
                self._save_cache()
                return None, 'none'

            # Simple matching - first result with reasonable title match
            best = results[0]
            title_lower = title.lower()
            result_title = best.get('title', '').lower()

            if title_lower == result_title:
                confidence = 'high'
            elif title_lower in result_title or result_title in title_lower:
                confidence = 'medium'
            else:
                confidence = 'low'

            self.cache[cache_key] = {'data': best, 'confidence': confidence}
            self._save_cache()
            return best, confidence

        except Exception as e:
            logger.error(f"TMDB error for '{title}': {e}")
            return None, 'none'

    def discover_films(self, sections: List[str] = None) -> List[Dict]:
        """Discover films from Video Store sections."""
        if sections is None:
            sections = list(self.SECTIONS.keys())

        logger.info(f"Letterboxd Video Store Discovery")
        logger.info(f"Sections: {sections}")

        all_films = []
        seen_slugs = set()

        for section in sections:
            if section not in self.SECTIONS:
                logger.warning(f"Unknown section: {section}")
                continue

            films = self._scrape_section(section, self.SECTIONS[section])
            for film in films:
                slug = film.get('letterboxd_slug')
                if slug and slug not in seen_slugs:
                    seen_slugs.add(slug)
                    all_films.append(film)

        logger.info(f"Total unique films: {len(all_films)}")
        logger.info("Matching with TMDB...")

        # Enrich with TMDB
        for i, film in enumerate(all_films, 1):
            logger.info(f"  [{i}/{len(all_films)}] {film['title']}")

            # Get more details from Letterboxd page
            details = self._get_film_details(film['letterboxd_slug'])
            if details:
                film.update({k: v for k, v in details.items() if k not in film})

            # Match with TMDB
            tmdb_data, confidence = self._match_with_tmdb(film['title'], film.get('year'))
            film['tmdb_match_confidence'] = confidence
            film['discovery_source'] = 'letterboxd_video_store'
            film['rent_link'] = film['letterboxd_url']

            if tmdb_data and confidence in ['high', 'medium']:
                film['tmdb_id'] = str(tmdb_data['id'])
                if tmdb_data.get('release_date'):
                    film['year'] = int(tmdb_data['release_date'][:4])
                film['tmdb_overview'] = tmdb_data.get('overview')
                film['tmdb_poster'] = tmdb_data.get('poster_path')

        return all_films


# CLI wrapper for standalone use
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Discover indie films on Letterboxd Video Store")
    parser.add_argument("--sections", nargs='+', default=None, help="Sections to scrape")
    parser.add_argument("--output", type=str, default="letterboxd_discoveries.json", help="Output file")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    scraper = LetterboxdScraper()
    films = scraper.discover_films(sections=args.sections)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(films, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(films)} films to {args.output}")
