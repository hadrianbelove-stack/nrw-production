"""
Vimeo On Demand scraper for discovering indie films and cross-referencing with TMDB.
"""

import json
import logging
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import unicodedata
import requests

from scraper_base import PlaywrightScraperBase
from constants import get_scraper_config

# Module-level logger
logger = logging.getLogger(__name__)


class VimeoOnDemandScraper(PlaywrightScraperBase):
    """Scrapes Vimeo On Demand for indie films and cross-references with TMDB."""

    def __init__(self, cache_file: str = "cache/vimeo_cache.json", config: dict = None, headless: bool = True):
        """Initialize the Vimeo scraper."""
        if config is None:
            # Load config from config.yaml
            try:
                import yaml
                with open('config.yaml', 'r') as f:
                    full_config = yaml.safe_load(f)
                config = get_scraper_config(full_config, "vimeo_scraper")
            except Exception:
                # Fallback to defaults
                from constants import SCRAPER_DEFAULTS
                config = SCRAPER_DEFAULTS.copy()
                config['discovery'] = {
                    'max_pages': 5,
                    'min_runtime': 70,
                    'categories': ["drama", "documentary", "comedy", "thriller"]
                }

        config['headless'] = headless

        # Initialize base class
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key='vimeo_scraper',
            log_prefix='VimeoOnDemandScraper',
            screenshot_subdir='vimeo'
        )

        self.tmdb_api_key = self.config.get("tmdb_api_key") or self._get_tmdb_api_key()

        # Discovery configuration
        self.discovery_config = self.config.get("discovery", {})
        self.min_runtime = self.discovery_config.get("min_runtime", 70)
        self.categories = self.discovery_config.get("categories", ["drama", "documentary", "comedy", "thriller"])

        # Stopwords for title matching
        self.stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'among', 'through'
        }

    def _get_tmdb_api_key(self) -> str:
        """Get TMDB API key from config or environment."""
        import os
        return os.getenv("TMDB_API_KEY", "")

    def _scrape_vimeo_browse_page(self, url: str) -> List[Dict]:
        """Scrape a single Vimeo browse page for film listings."""
        cache_key = f"page_{url}"
        if cache_key in self.cache:
            logger.info(f"Using cached data for {url}")
            return self.cache[cache_key]['data']

        self._enforce_rate_limit()

        logger.info(f"Scraping Vimeo page: {url}")

        # Initialize browser if needed
        if not self.page:
            self._init_browser()

        films = []
        try:
            # Navigate to page with timeout
            self.page.goto(url, timeout=self.config.get("timeout", 15) * 1000)

            # Wait for content to load
            self.page.wait_for_selector('body', timeout=10000)
            time.sleep(2)  # Additional wait for dynamic content

            # Look for film cards with multiple selector strategies
            selectors = [
                '.ondemand-card',
                '.vod-card',
                '.browse-item',
                '[data-testid*="film"]',
                '.film-card',
                'article[data-item-id]',
                '.grid-item'
            ]

            film_elements = []
            for selector in selectors:
                elements = self.page.locator(selector).all()
                if elements:
                    film_elements = elements
                    logger.info(f"Found {len(elements)} films using selector: {selector}")
                    break

            if not film_elements:
                # Fallback: look for any elements with film-like content
                potential_films = self.page.locator('a[href*="/ondemand/"]').all()
                if potential_films:
                    film_elements = potential_films[:20]  # Limit to reasonable number
                    logger.info(f"Using fallback selector, found {len(film_elements)} potential films")

            for element in film_elements[:20]:  # Limit to 20 per page
                try:
                    film_data = self._extract_film_metadata(element, self.page)
                    if film_data and film_data.get('runtime', 0) >= self.min_runtime:
                        films.append(film_data)
                except Exception as e:
                    logger.warning(f"Error extracting film metadata: {e}")
                    continue

            # Cache the results
            self.cache[cache_key] = {
                'data': films,
                'timestamp': datetime.now().isoformat()
            }
            self._save_cache()

        except Exception as e:
            logger.error(f"Error scraping page {url}: {e}")
            # Take screenshot for debugging if enabled
            self._take_error_screenshot(f"vimeo_error_{int(time.time())}")
            raise e

        logger.info(f"Discovered {len(films)} feature films from {url}")
        return films

    def _extract_film_metadata(self, element, page) -> Optional[Dict]:
        """Extract film metadata from a Vimeo film element."""
        try:
            # Try to get the film URL first
            vimeo_url = None
            href_selectors = ['a', '[href*="/ondemand/"]', 'a[href]']
            for selector in href_selectors:
                try:
                    link_elem = element.locator(selector).first
                    if link_elem.count() > 0:
                        href = link_elem.get_attribute('href')
                        if href and '/ondemand/' in href:
                            vimeo_url = href if href.startswith('http') else f"https://vimeo.com{href}"
                            break
                except:
                    continue

            if not vimeo_url:
                return None

            # Extract vimeo_id from URL
            vimeo_id_match = re.search(r'/ondemand/([^/?]+)', vimeo_url)
            vimeo_id = vimeo_id_match.group(1) if vimeo_id_match else None

            # Extract title
            title = None
            title_selectors = ['h3', 'h2', 'h1', '.title', '[data-title]', 'a[title]']
            for selector in title_selectors:
                try:
                    title_elem = element.locator(selector).first
                    if title_elem.count() > 0:
                        title = title_elem.inner_text().strip()
                        if not title:
                            title = title_elem.get_attribute('title')
                        if title:
                            break
                except:
                    continue

            if not title:
                # Fallback: extract from URL or link text
                try:
                    link_text = element.locator('a').first.inner_text().strip()
                    if link_text and len(link_text) < 100:
                        title = link_text
                except:
                    if vimeo_id:
                        title = vimeo_id.replace('-', ' ').title()

            if not title:
                return None

            # Extract runtime (look for duration indicators)
            runtime = None
            runtime_patterns = [
                r'(\d+)\s*min',
                r'(\d+):\d+',
                r'Duration[:\s]*(\d+)',
                r'Runtime[:\s]*(\d+)'
            ]

            try:
                element_text = element.inner_text()
                for pattern in runtime_patterns:
                    match = re.search(pattern, element_text, re.IGNORECASE)
                    if match:
                        runtime = int(match.group(1))
                        break
            except:
                pass

            # If we can't find runtime, visit the film page briefly
            if not runtime and vimeo_url:
                try:
                    runtime = self._get_runtime_from_film_page(vimeo_url, page)
                except:
                    pass

            # Extract price information
            price_rent = None
            price_buy = None
            try:
                price_text = element.inner_text()
                rent_match = re.search(r'Rent.*?\$?(\d+\.?\d*)', price_text, re.IGNORECASE)
                buy_match = re.search(r'Buy.*?\$?(\d+\.?\d*)', price_text, re.IGNORECASE)

                if rent_match:
                    price_rent = f"${rent_match.group(1)}"
                if buy_match:
                    price_buy = f"${buy_match.group(1)}"
            except:
                pass

            # Extract description
            description = None
            description_selectors = ['.description', '.synopsis', '.summary', 'p']
            for selector in description_selectors:
                try:
                    desc_elem = element.locator(selector).first
                    if desc_elem.count() > 0:
                        desc_text = desc_elem.inner_text().strip()
                        if desc_text and len(desc_text) > 20:
                            description = desc_text[:500]  # Limit length
                            break
                except:
                    continue

            # Extract filmmaker/director
            filmmaker = None
            filmmaker_selectors = ['.filmmaker', '.director', '.creator', '.by']
            for selector in filmmaker_selectors:
                try:
                    filmmaker_elem = element.locator(selector).first
                    if filmmaker_elem.count() > 0:
                        filmmaker = filmmaker_elem.inner_text().strip()
                        if filmmaker:
                            break
                except:
                    continue

            return {
                'title': title,
                'vimeo_url': vimeo_url,
                'vimeo_id': vimeo_id,
                'runtime': runtime or 80,  # Default to 80 if unknown (assume feature length)
                'price_rent': price_rent,
                'price_buy': price_buy,
                'description': description,
                'filmmaker': filmmaker,
                'discovery_date': datetime.now().strftime('%Y-%m-%d')
            }

        except Exception as e:
            logger.warning(f"Error extracting metadata: {e}")
            return None

    def _get_runtime_from_film_page(self, vimeo_url: str, page) -> Optional[int]:
        """Get runtime by visiting the individual film page."""
        try:
            page.goto(vimeo_url, timeout=10000)
            page.wait_for_selector('body', timeout=5000)

            # Look for runtime indicators on the film page
            runtime_patterns = [
                r'(\d+)\s*minutes?',
                r'(\d+)\s*mins?',
                r'Duration[:\s]*(\d+)',
                r'(\d+):\d+',
            ]

            page_text = page.inner_text('body')
            for pattern in runtime_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))

            return None
        except:
            return None

    def _normalize_title(self, title: str) -> str:
        """Normalize title for matching."""
        if not title:
            return ""

        # Remove unicode accents
        title = unicodedata.normalize('NFD', title)
        title = ''.join(c for c in title if unicodedata.category(c) != 'Mn')

        # Convert to lowercase and remove special characters
        title = re.sub(r'[^\w\s]', '', title.lower())

        # Remove extra whitespace
        title = ' '.join(title.split())

        return title

    def _calculate_title_match(self, search_title: str, result_title: str) -> float:
        """Calculate title match percentage using word overlap."""
        search_normalized = self._normalize_title(search_title)
        result_normalized = self._normalize_title(result_title)

        search_words = set(word for word in search_normalized.split() if word not in self.stopwords)
        result_words = set(word for word in result_normalized.split() if word not in self.stopwords)

        if not search_words or not result_words:
            return 0.0

        intersection = search_words.intersection(result_words)
        union = search_words.union(result_words)

        return len(intersection) / len(union) if union else 0.0

    def _match_with_tmdb(self, title: str, year: Optional[int] = None) -> Tuple[Optional[Dict], str]:
        """Cross-reference with TMDB API."""
        cache_key = f"tmdb_{self._normalize_title(title)}_{year or 'no_year'}"

        if cache_key in self.cache:
            cached = self.cache[cache_key]
            return cached.get('data'), cached.get('confidence', 'none')

        if not self.tmdb_api_key:
            logger.warning("No TMDB API key available")
            return None, 'none'

        try:
            # Search TMDB
            search_params = {
                'api_key': self.tmdb_api_key,
                'query': title,
                'language': 'en-US'
            }
            if year:
                search_params['year'] = year

            time.sleep(0.1)  # Rate limit for TMDB
            response = requests.get(
                'https://api.themoviedb.org/3/search/movie',
                params=search_params,
                timeout=10
            )
            response.raise_for_status()

            results = response.json().get('results', [])

            if not results:
                self.cache[cache_key] = {'data': None, 'confidence': 'none', 'timestamp': datetime.now().isoformat()}
                self._save_cache()
                return None, 'none'

            # Find best match
            best_match = None
            best_confidence = 'none'
            best_score = 0.0

            for result in results[:5]:  # Check top 5 results
                result_title = result.get('title', '')
                result_year = None

                if result.get('release_date'):
                    try:
                        result_year = int(result['release_date'][:4])
                    except:
                        pass

                # Calculate title match score
                title_score = self._calculate_title_match(title, result_title)

                # Year validation
                year_match = True
                if year and result_year:
                    year_match = abs(year - result_year) <= 1

                # Determine confidence
                confidence = 'none'
                if title_score >= 0.9 and year_match:
                    confidence = 'high'
                elif title_score >= 0.7 and year_match:
                    confidence = 'medium'
                elif title_score >= 0.6:
                    confidence = 'low'

                if title_score > best_score and confidence != 'none':
                    best_match = result
                    best_confidence = confidence
                    best_score = title_score

            # Cache result
            self.cache[cache_key] = {
                'data': best_match,
                'confidence': best_confidence,
                'timestamp': datetime.now().isoformat()
            }
            self._save_cache()

            return best_match, best_confidence

        except Exception as e:
            logger.error(f"TMDB search error for '{title}': {e}")
            return None, 'none'

    def discover_films(self, max_pages: int = 5) -> List[Dict]:
        """Main discovery method that browses Vimeo On Demand pages."""
        logger.info(f"Starting Vimeo On Demand discovery (max_pages: {max_pages})")

        all_films = []

        # Base URLs to scrape
        urls_to_scrape = [
            'https://vimeo.com/ondemand',
            'https://vimeo.com/ondemand/browse/drama',
            'https://vimeo.com/ondemand/browse/documentary',
            'https://vimeo.com/ondemand/browse/comedy',
            'https://vimeo.com/ondemand/browse/thriller'
        ]

        # Limit to max_pages
        urls_to_scrape = urls_to_scrape[:max_pages]

        for i, url in enumerate(urls_to_scrape, 1):
            logger.info(f"Scraping page {i}/{len(urls_to_scrape)}: {url}")

            try:
                films = self._scrape_vimeo_browse_page(url)
                all_films.extend(films)
                logger.info(f"Found {len(films)} films on page {i}")

            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                continue

        logger.info(f"Total films before TMDB matching: {len(all_films)}")

        # Cross-reference with TMDB
        enhanced_films = []
        for i, film in enumerate(all_films, 1):
            logger.info(f"TMDB matching {i}/{len(all_films)}: {film['title']}")

            # Extract year from title or use current year as fallback
            year = None
            year_match = re.search(r'\b(19|20)\d{2}\b', film['title'])
            if year_match:
                year = int(year_match.group())

            tmdb_data, confidence = self._match_with_tmdb(film['title'], year)

            enhanced_film = {
                **film,
                'tmdb_match_confidence': confidence,
                'drc_platform': 'vimeo',
                'category': 'Feature Films (70+ min)'
            }

            if tmdb_data and confidence in ['high', 'medium']:
                enhanced_film.update({
                    'id': tmdb_data.get('id'),
                    'release_year': int(tmdb_data['release_date'][:4]) if tmdb_data.get('release_date') else year,
                    'genres': [genre['name'] for genre in tmdb_data.get('genres', [])],
                    'tmdb_overview': tmdb_data.get('overview'),
                    'tmdb_rating': tmdb_data.get('vote_average'),
                    'tmdb_poster': tmdb_data.get('poster_path')
                })
            else:
                enhanced_film.update({
                    'id': None,
                    'release_year': year or datetime.now().year,
                    'genres': []
                })

            enhanced_films.append(enhanced_film)

        logger.info(f"Discovery complete. Found {len(enhanced_films)} total films")
        logger.info(f"TMDB matches: {len([f for f in enhanced_films if f['tmdb_match_confidence'] != 'none'])}")

        return enhanced_films


# CLI wrapper for standalone use
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Discover indie films on Vimeo On Demand")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum pages to scrape")
    parser.add_argument("--output", type=str, default="vimeo_discoveries.json", help="Output file")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    scraper = VimeoOnDemandScraper(headless=args.headless)

    try:
        films = scraper.discover_films(max_pages=args.max_pages)

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(films, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(films)} films to {args.output}")

    finally:
        scraper.cleanup()
