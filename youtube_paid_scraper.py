"""
YouTube Paid Content scraper for discovering indie films and cross-referencing with TMDB.
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


class YouTubePaidScraper(PlaywrightScraperBase):
    """Scrapes YouTube for paid/free indie films and cross-references with TMDB."""

    def __init__(self, cache_file: str = "cache/youtube_cache.json", config: dict = None, headless: bool = True):
        """Initialize the YouTube scraper."""
        if config is None:
            # Load config from config.yaml
            try:
                import yaml
                with open('config.yaml', 'r') as f:
                    full_config = yaml.safe_load(f)
                config = get_scraper_config(full_config, "youtube_scraper")
            except Exception:
                # Fallback to defaults
                from constants import SCRAPER_DEFAULTS
                config = SCRAPER_DEFAULTS.copy()
                config['discovery'] = {
                    'max_pages': 5,
                    'min_runtime': 70,
                    'search_queries': ["indie film", "independent film", "feature film", "documentary film"],
                    'include_free': True
                }

        config['headless'] = headless

        # Initialize base class
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key='youtube_scraper',
            log_prefix='YouTubePaidScraper',
            screenshot_subdir='youtube'
        )

        self.tmdb_api_key = self.config.get("tmdb_api_key") or self._get_tmdb_api_key()

        # Discovery configuration
        self.discovery_config = self.config.get("discovery", {})
        self.min_runtime = self.discovery_config.get("min_runtime", 70)
        self.search_queries = self.discovery_config.get("search_queries",
            ["indie film", "independent film", "feature film", "documentary film"])
        self.include_free = self.discovery_config.get("include_free", True)

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

    def _scrape_youtube_movies_page(self, url: str) -> List[Dict]:
        """Scrape a YouTube Movies page or search results for film listings."""
        cache_key = f"page_{url}"
        if cache_key in self.cache:
            logger.info(f"Using cached data for {url}")
            return self.cache[cache_key]['data']

        self._enforce_rate_limit()

        logger.info(f"Scraping YouTube page: {url}")

        # Initialize browser if needed
        if not self.page:
            self._init_browser()

        films = []
        try:
            # Navigate to page with timeout
            self.page.goto(url, timeout=self.config.get("timeout", 15) * 1000)

            # Wait for content to load
            self.page.wait_for_selector('body', timeout=10000)
            time.sleep(3)  # Additional wait for dynamic content

            # Look for film cards with multiple selector strategies
            selectors = [
                '.ytd-grid-video-renderer',
                '.ytd-movie-renderer',
                '[data-context-item-id]',
                '.compact-movie-item',
                '.ytd-rich-item-renderer',
                '.ytd-video-renderer',
                'a[href*="/watch?v="]',
                'a[href*="/watch/"]'
            ]

            film_elements = []
            for selector in selectors:
                elements = self.page.locator(selector).all()
                if elements:
                    film_elements = elements
                    logger.info(f"Found {len(elements)} potential films using selector: {selector}")
                    break

            if not film_elements:
                # Fallback: look for any elements with video links
                potential_films = self.page.locator('a[href*="/watch"]').all()
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
            self._take_error_screenshot(f"youtube_error_{int(time.time())}")
            raise e

        logger.info(f"Discovered {len(films)} feature films from {url}")
        return films

    def _extract_film_metadata(self, element, page) -> Optional[Dict]:
        """Extract film metadata from a YouTube video element."""
        try:
            # Try to get the YouTube URL first
            youtube_url = None
            href_selectors = ['a[href*="/watch"]', 'a', '[href]']
            for selector in href_selectors:
                try:
                    link_elem = element.locator(selector).first
                    if link_elem.count() > 0:
                        href = link_elem.get_attribute('href')
                        if href and ('/watch?v=' in href or '/watch/' in href):
                            youtube_url = href if href.startswith('http') else f"https://www.youtube.com{href}"
                            break
                except:
                    continue

            if not youtube_url:
                return None

            # Extract video ID from URL
            video_id_match = re.search(r'(?:watch\?v=|/watch/)([a-zA-Z0-9_-]+)', youtube_url)
            video_id = video_id_match.group(1) if video_id_match else None

            # Extract title
            title = None
            title_selectors = ['#video-title', '.title', 'h3', 'h2', 'h1', 'a[title]', '[aria-label]']
            for selector in title_selectors:
                try:
                    title_elem = element.locator(selector).first
                    if title_elem.count() > 0:
                        title = title_elem.inner_text().strip()
                        if not title:
                            title = title_elem.get_attribute('title')
                        if not title:
                            title = title_elem.get_attribute('aria-label')
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
                    if video_id:
                        title = video_id.replace('-', ' ').title()

            if not title:
                return None

            # Extract runtime
            runtime = None
            runtime_patterns = [
                r'(\d+):(\d+):(\d+)',  # hours:minutes:seconds
                r'(\d+):(\d+)',        # minutes:seconds
                r'(\d+)\s*min',        # X min
                r'Duration:\s*(\d+)',  # Duration: X
                r'Runtime:\s*(\d+)'    # Runtime: X
            ]

            try:
                element_text = element.inner_text()
                for pattern in runtime_patterns:
                    match = re.search(pattern, element_text, re.IGNORECASE)
                    if match:
                        groups = match.groups()
                        if len(groups) == 3:  # hours:minutes:seconds
                            runtime = int(groups[0]) * 60 + int(groups[1])
                        elif len(groups) == 2:  # minutes:seconds
                            runtime = int(groups[0])
                        else:  # single number
                            runtime = int(groups[0])
                        break
            except:
                pass

            # If we can't find runtime, visit the video page briefly
            if not runtime and youtube_url:
                try:
                    runtime = self._get_runtime_from_video_page(youtube_url, page)
                except:
                    pass

            # Extract price information
            price_rent = None
            price_buy = None
            is_free = False
            try:
                price_text = element.inner_text()

                # Check for free indicators
                if re.search(r'free', price_text, re.IGNORECASE):
                    is_free = True

                # Look for rental/purchase prices
                rent_match = re.search(r'Rent.*?\$?(\d+\.?\d*)', price_text, re.IGNORECASE)
                buy_match = re.search(r'Buy.*?\$?(\d+\.?\d*)', price_text, re.IGNORECASE)

                if rent_match:
                    price_rent = f"${rent_match.group(1)}"
                if buy_match:
                    price_buy = f"${buy_match.group(1)}"
            except:
                pass

            # Extract channel name (filmmaker)
            channel_name = None
            channel_selectors = ['.ytd-channel-name', '.channel-name', '[href*="/channel/"]', '[href*="/@"]']
            for selector in channel_selectors:
                try:
                    channel_elem = element.locator(selector).first
                    if channel_elem.count() > 0:
                        channel_name = channel_elem.inner_text().strip()
                        if channel_name:
                            break
                except:
                    continue

            # Extract description
            description = None
            description_selectors = ['.metadata-snippet-text', '.description-snippet', '.description', 'p']
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

            return {
                'title': title,
                'youtube_url': youtube_url,
                'video_id': video_id,
                'runtime': runtime or 80,  # Default to 80 if unknown (assume feature length)
                'price_rent': price_rent,
                'price_buy': price_buy,
                'is_free': is_free,
                'channel_name': channel_name,
                'description': description,
                'discovery_date': datetime.now().strftime('%Y-%m-%d')
            }

        except Exception as e:
            logger.warning(f"Error extracting metadata: {e}")
            return None

    def _get_runtime_from_video_page(self, youtube_url: str, page) -> Optional[int]:
        """Get runtime by visiting the individual video page."""
        try:
            page.goto(youtube_url, timeout=10000)
            page.wait_for_selector('body', timeout=5000)
            time.sleep(2)  # Wait for video metadata to load

            # Look for runtime indicators on the video page
            runtime_patterns = [
                r'(\d+):(\d+):(\d+)',  # hours:minutes:seconds
                r'(\d+):(\d+)',        # minutes:seconds
                r'(\d+)\s*minutes?',   # X minutes
                r'(\d+)\s*mins?',      # X mins
                r'Duration[:\s]*(\d+)', # Duration: X
            ]

            page_text = page.inner_text('body')
            for pattern in runtime_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    if len(groups) == 3:  # hours:minutes:seconds
                        return int(groups[0]) * 60 + int(groups[1])
                    elif len(groups) == 2:  # minutes:seconds
                        return int(groups[0])
                    else:  # single number
                        return int(groups[0])

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

    def discover_films(self, max_pages: int = 5, search_queries: List[str] = None) -> List[Dict]:
        """Main discovery method that browses YouTube Movies and searches."""
        logger.info(f"Starting YouTube discovery (max_pages: {max_pages})")

        all_films = []

        # Base URLs and searches to scrape
        urls_to_scrape = [
            'https://www.youtube.com/channel/UCclkuhbGuJW4kW4UhkIj0eQ',  # YouTube Movies
            'https://www.youtube.com/results?search_query=indie+film+full+movie',
            'https://www.youtube.com/results?search_query=independent+film+full+movie',
            'https://www.youtube.com/results?search_query=feature+film+full+movie',
            'https://www.youtube.com/results?search_query=documentary+film+full+movie',
        ]

        # If custom search queries provided, use those
        if search_queries:
            base_url = 'https://www.youtube.com/results?search_query='
            urls_to_scrape = [f"{base_url}{query.replace(' ', '+')}" for query in search_queries]

        # Limit to max_pages
        urls_to_scrape = urls_to_scrape[:max_pages]

        for i, url in enumerate(urls_to_scrape, 1):
            logger.info(f"Scraping page {i}/{len(urls_to_scrape)}: {url}")

            try:
                films = self._scrape_youtube_movies_page(url)
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

            # Extract year from title
            year = None
            year_match = re.search(r'\b(19|20)\d{2}\b', film['title'])
            if year_match:
                year = int(year_match.group())

            tmdb_data, confidence = self._match_with_tmdb(film['title'], year)

            enhanced_film = {
                **film,
                'tmdb_match_confidence': confidence,
                'drc_platform': 'youtube',
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

    parser = argparse.ArgumentParser(description="Discover indie films on YouTube")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum pages to scrape")
    parser.add_argument("--output", type=str, default="youtube_discoveries.json", help="Output file")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    scraper = YouTubePaidScraper(headless=args.headless)

    try:
        films = scraper.discover_films(max_pages=args.max_pages)

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(films, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(films)} films to {args.output}")

    finally:
        scraper.cleanup()
