"""
Patreon Film scraper for discovering indie films and cross-referencing with TMDB.

v2: Migrated to use PlaywrightScraperBase for shared functionality.
"""

import json
import time
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
from functools import wraps

from scraper_base import PlaywrightScraperBase
from constants import get_scraper_config

# Module-level logger
logger = logging.getLogger(__name__)


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

                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)[:100]}... Retrying in {actual_delay:.1f}s")
                    time.sleep(actual_delay)

            return None
        return wrapper
    return decorator


class PatreonFilmScraper(PlaywrightScraperBase):
    """Scrapes Patreon for indie films and cross-references with TMDB.

    v2: Now inherits from PlaywrightScraperBase for shared functionality.
    """

    def __init__(self, cache_file: str = "cache/patreon_cache.json", config: dict = None, headless: bool = True):
        """Initialize the Patreon scraper."""
        # Build config if not provided
        if config is None:
            try:
                import yaml
                with open('config.yaml', 'r') as f:
                    full_config = yaml.safe_load(f)
                config = full_config
            except Exception:
                config = {}

        # Store headless preference in config for base class
        config['headless'] = headless

        # Initialize base class
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key='patreon_scraper',
            log_prefix='PatreonFilmScraper',
            screenshot_subdir='patreon'
        )

        # Override rate limit for Patreon (slower)
        self.rate_limit = self.scraper_config.get('rate_limit', 3.0)

        # TMDB API key
        self.tmdb_api_key = self.config.get('api', {}).get('tmdb_api_key') or self._get_tmdb_api_key()

        # Discovery configuration
        self.discovery_config = self.scraper_config.get('discovery', {})
        self.max_creators = self.discovery_config.get('max_creators', 50)
        self.min_runtime = self.discovery_config.get('min_runtime', 10)
        self.search_terms = self.discovery_config.get('search_terms', ["film", "movie", "documentary"])

        # Known film creators from research
        self.known_film_creators = [
            "FilmmakerIQ",
            "onemonthmovies",
            "happenfilms",
            "lundahl",
            "wemakemovies",
            "AlexProyas",
            "mfox",
            "DocumentaryFirst"
        ]

        # Stopwords for title matching
        self.stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'among', 'through'
        }

    def _get_tmdb_api_key(self) -> str:
        """Get TMDB API key from environment."""
        import os
        return os.getenv("TMDB_API_KEY", "")

    @retry_with_exponential_backoff()
    def _scrape_creator_page(self, username: str) -> List[Dict]:
        """Scrape a Patreon creator page for film content."""
        cache_key = f"creator_{username}"
        if cache_key in self.cache:
            self._log(f"Using cached data for creator {username}")
            return self.cache[cache_key]['data']

        self._enforce_rate_limit()

        creator_url = f"https://www.patreon.com/{username}"
        self._log(f"Scraping Patreon creator: {creator_url}")

        # Initialize browser if needed
        self._init_browser()

        films = []
        try:
            # Navigate to creator page
            self.page.goto(creator_url, wait_until='networkidle', timeout=30000)

            # Wait for page to load
            time.sleep(2)

            # Extract creator info
            creator_info = self._extract_creator_info()

            # Extract posts that might be films
            posts = self._extract_creator_posts()

            # Filter posts for film content
            for post in posts:
                if self._is_film_content(post):
                    film_data = self._parse_film_post(post, creator_info, username)
                    if film_data:
                        films.append(film_data)

        except Exception as e:
            self._log(f"Error scraping {username}: {str(e)}", level='error')
            raise e

        # Cache the results
        self.cache[cache_key] = {
            'data': films,
            'timestamp': datetime.now().isoformat()
        }
        self._save_cache()

        self._log(f"Found {len(films)} films from {username}")
        return films

    def _extract_creator_info(self) -> Dict:
        """Extract basic creator information."""
        creator_info = {}
        try:
            # Extract creator name
            name_selector = 'h1[data-tag="creator-page-title"]'
            creator_info['name'] = self.page.locator(name_selector).text_content() if self.page.locator(name_selector).count() > 0 else ""

            # Extract description
            desc_selector = '[data-tag="creator-page-description"]'
            creator_info['description'] = self.page.locator(desc_selector).text_content() if self.page.locator(desc_selector).count() > 0 else ""

            # Extract category/genre info from description
            description = creator_info['description'].lower()
            for term in ['film', 'movie', 'documentary', 'cinema', 'filmmaker']:
                if term in description:
                    creator_info['is_film_creator'] = True
                    break
            else:
                creator_info['is_film_creator'] = False

        except Exception as e:
            self._log(f"Error extracting creator info: {e}", level='warning')

        return creator_info

    def _extract_creator_posts(self) -> List[Dict]:
        """Extract posts from creator page."""
        posts = []
        try:
            # Wait for posts to load
            self.page.wait_for_selector('[data-tag="post-card"]', timeout=10000)

            # Extract post cards
            post_cards = self.page.locator('[data-tag="post-card"]').all()

            for card in post_cards[:20]:  # Limit to first 20 posts
                try:
                    post_data = {}

                    # Extract title
                    title_elem = card.locator('h3, h2, [data-tag="post-title"]').first
                    post_data['title'] = title_elem.text_content().strip() if title_elem.count() > 0 else ""

                    # Extract description/content
                    desc_elem = card.locator('[data-tag="post-content"], .post-content, p').first
                    post_data['description'] = desc_elem.text_content().strip() if desc_elem.count() > 0 else ""

                    # Extract post URL
                    link_elem = card.locator('a[href*="/posts/"]').first
                    if link_elem.count() > 0:
                        post_data['url'] = "https://www.patreon.com" + link_elem.get_attribute('href')

                    # Extract thumbnail/image
                    img_elem = card.locator('img').first
                    if img_elem.count() > 0:
                        post_data['thumbnail'] = img_elem.get_attribute('src')

                    # Extract tier info
                    tier_elem = card.locator('[data-tag="post-tier"]').first
                    post_data['tier'] = tier_elem.text_content().strip() if tier_elem.count() > 0 else "Public"

                    posts.append(post_data)

                except Exception as e:
                    self._log(f"Error extracting post: {e}", level='debug')
                    continue

        except Exception as e:
            self._log(f"Error extracting posts: {e}", level='warning')

        return posts

    def _is_film_content(self, post: Dict) -> bool:
        """Determine if a post contains film content."""
        title = post.get('title', '').lower()
        description = post.get('description', '').lower()

        # Film keywords to look for
        film_keywords = [
            'film', 'movie', 'short', 'documentary', 'trailer', 'teaser',
            'cinema', 'screening', 'premiere', 'festival', 'episode',
            'series', 'video', 'watch', 'stream'
        ]

        # Check if any film keywords are in title or description
        for keyword in film_keywords:
            if keyword in title or keyword in description:
                return True

        return False

    def _parse_film_post(self, post: Dict, creator_info: Dict, username: str) -> Optional[Dict]:
        """Parse a post into film data format."""
        try:
            title = post.get('title', '').strip()
            if not title:
                return None

            film_data = {
                'title': title,
                'description': post.get('description', ''),
                'creator_name': creator_info.get('name', username),
                'creator_username': username,
                'post_url': post.get('url', ''),
                'thumbnail_url': post.get('thumbnail', ''),
                'tier': post.get('tier', 'Public'),
                'platform': 'patreon',
                'discovery_date': datetime.now().isoformat()[:10],

                # Attempt to extract runtime (if mentioned)
                'runtime': self._extract_runtime_from_text(title + ' ' + post.get('description', '')),

                # Categories based on content
                'categories': self._extract_categories(title + ' ' + post.get('description', '')),

                # Pricing info (Patreon is subscription-based)
                'is_subscription': True,
                'access_type': 'subscription' if post.get('tier') != 'Public' else 'free'
            }

            return film_data

        except Exception as e:
            self._log(f"Error parsing film post: {e}", level='warning')
            return None

    def _extract_runtime_from_text(self, text: str) -> Optional[int]:
        """Extract runtime information from text."""
        # Look for common runtime patterns
        runtime_patterns = [
            r'(\d+)\s*(?:minute|min|minutes)',
            r'(\d+)\s*(?:hour|hr|hours)',
            r'(\d+):(\d+)',  # MM:SS or HH:MM format
        ]

        text = text.lower()
        for pattern in runtime_patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 1:  # Single number
                    return int(match.group(1))
                elif len(match.groups()) == 2:  # HH:MM format
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    return hours * 60 + minutes

        return None

    def _extract_categories(self, text: str) -> List[str]:
        """Extract film categories from text."""
        categories = []
        text = text.lower()

        category_keywords = {
            'documentary': ['documentary', 'doc', 'real life', 'true story'],
            'horror': ['horror', 'scary', 'frightening', 'terror'],
            'comedy': ['comedy', 'funny', 'humor', 'laugh'],
            'drama': ['drama', 'dramatic', 'emotional'],
            'thriller': ['thriller', 'suspense', 'tension'],
            'animation': ['animation', 'animated', 'cartoon'],
            'short': ['short film', 'short', 'brief'],
            'experimental': ['experimental', 'art film', 'avant-garde']
        }

        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    categories.append(category)
                    break

        return categories

    @retry_with_exponential_backoff()
    def search_film_creators(self, search_terms: List[str] = None) -> List[str]:
        """Search for film-related creators on Patreon."""
        if search_terms is None:
            search_terms = self.search_terms

        found_creators = set(self.known_film_creators)  # Start with known creators

        # Initialize browser if needed
        self._init_browser()

        try:
            for term in search_terms:
                self._enforce_rate_limit()

                search_url = f"https://www.patreon.com/search?q={term}"
                self._log(f"Searching Patreon for: {term}")

                self.page.goto(search_url, wait_until='networkidle', timeout=30000)
                time.sleep(2)

                # Extract creator usernames from search results
                creator_links = self.page.locator('a[href*="/user?u="], a[href^="/"]').all()

                for link in creator_links[:10]:  # Limit results per search
                    try:
                        href = link.get_attribute('href')
                        if href and href.startswith('/') and not any(x in href for x in ['/posts/', '/search', '/explore']):
                            username = href.strip('/')
                            if self._is_likely_film_creator(link, term):
                                found_creators.add(username)
                    except Exception:
                        continue

        except Exception as e:
            self._log(f"Error during search: {e}", level='error')

        return list(found_creators)

    def _is_likely_film_creator(self, link_element, search_term: str) -> bool:
        """Check if a creator link is likely to be film-related."""
        try:
            # Check link text and surrounding context
            text_content = link_element.text_content().lower()

            film_indicators = [
                'film', 'movie', 'cinema', 'documentary', 'filmmaker',
                'director', 'producer', 'video', 'animation', 'short'
            ]

            for indicator in film_indicators:
                if indicator in text_content:
                    return True

            return False
        except Exception:
            return False

    def discover_films(self, max_creators: int = None) -> List[Dict]:
        """Main discovery method to find films from Patreon creators."""
        if max_creators is None:
            max_creators = self.max_creators

        self._log(f"Starting Patreon film discovery...")

        # Search for film creators
        creators = self.search_film_creators()
        self._log(f"Found {len(creators)} potential film creators")

        all_films = []
        processed_creators = 0

        for creator in creators[:max_creators]:
            try:
                self._log(f"Processing creator {processed_creators + 1}/{min(len(creators), max_creators)}: {creator}")

                films = self._scrape_creator_page(creator)

                # Filter films by runtime if specified
                filtered_films = [f for f in films if not self.min_runtime or
                                f.get('runtime', 0) >= self.min_runtime]

                all_films.extend(filtered_films)
                processed_creators += 1

                self._log(f"Added {len(filtered_films)} films from {creator}")

            except Exception as e:
                self._log(f"Error processing creator {creator}: {e}", level='warning')
                continue

        self._log(f"Discovery complete: Found {len(all_films)} films from {processed_creators} creators")
        return all_films

    def cross_reference_tmdb(self, films: List[Dict]) -> List[Dict]:
        """Cross-reference discovered films with TMDB database."""
        if not self.tmdb_api_key:
            self._log("No TMDB API key provided, skipping cross-reference", level='warning')
            return films

        self._log(f"Cross-referencing {len(films)} films with TMDB...")

        for i, film in enumerate(films):
            try:
                self._log(f"Processing {i+1}/{len(films)}: {film['title'][:50]}...", level='debug')

                tmdb_data = self._search_tmdb(film['title'])
                if tmdb_data:
                    film.update({
                        'tmdb_id': tmdb_data.get('id'),
                        'tmdb_title': tmdb_data.get('title'),
                        'tmdb_year': tmdb_data.get('release_date', '')[:4] if tmdb_data.get('release_date') else '',
                        'tmdb_overview': tmdb_data.get('overview'),
                        'tmdb_genres': [g['name'] for g in tmdb_data.get('genres', [])],
                        'tmdb_runtime': tmdb_data.get('runtime'),
                        'tmdb_match_confidence': self._calculate_match_confidence(film, tmdb_data)
                    })
                else:
                    film['tmdb_match_confidence'] = 'none'

                time.sleep(0.1)  # Rate limit TMDB requests

            except Exception as e:
                self._log(f"Error cross-referencing {film['title']}: {e}", level='warning')
                film['tmdb_match_confidence'] = 'error'

        return films

    def _search_tmdb(self, title: str) -> Optional[Dict]:
        """Search TMDB for a film title."""
        if not self.tmdb_api_key:
            return None

        try:
            url = "https://api.themoviedb.org/3/search/movie"
            params = {
                'api_key': self.tmdb_api_key,
                'query': title,
                'language': 'en-US',
                'page': 1
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            if results:
                # Return the first result (highest relevance)
                return results[0]

        except Exception as e:
            self._log(f"TMDB search error for '{title}': {e}", level='warning')

        return None

    def _calculate_match_confidence(self, film: Dict, tmdb_data: Dict) -> str:
        """Calculate confidence level for TMDB match."""
        title_similarity = self._calculate_title_similarity(
            film['title'],
            tmdb_data.get('title', '')
        )

        if title_similarity > 0.9:
            return 'high'
        elif title_similarity > 0.7:
            return 'medium'
        elif title_similarity > 0.5:
            return 'low'
        else:
            return 'very_low'

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles."""
        def clean_title(title):
            # Remove common words and normalize
            title = title.lower().strip()
            words = [w for w in title.split() if w not in self.stopwords]
            return ' '.join(words)

        clean1 = clean_title(title1)
        clean2 = clean_title(title2)

        if clean1 == clean2:
            return 1.0

        # Simple word overlap similarity
        words1 = set(clean1.split())
        words2 = set(clean2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def close(self):
        """Clean up resources."""
        self._cleanup_browser()
        self._save_cache()
