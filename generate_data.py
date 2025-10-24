#!/usr/bin/env python3
"""
Generate display data from tracking database with enriched links
"""

import json
import requests
import yaml
from datetime import datetime, timedelta
import time
import os
import re
from urllib.parse import quote
import argparse
import logging
from logging.handlers import RotatingFileHandler
from agent_link_scraper import AgentLinkScraper
from scripts.youtube_trailer_scraper import YouTubeTrailerScraper
try:
    from streaming_platform_scraper import StreamingPlatformScraper
except ImportError:
    StreamingPlatformScraper = None


def setup_logger(name, log_file='logs/admin.log', level=logging.INFO):
    """
    Configure logging with file rotation and console output.

    Args:
        name (str): Logger name (e.g., 'admin', 'data_generator')
        log_file (str): Path to log file (default: 'logs/admin.log')
        level (int): Logging level (default: logging.INFO)

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Get or create logger
    logger = logging.getLogger(name)

    # Prevent duplicate handlers
    if not logger.handlers:
        logger.setLevel(level)

        # Create formatter (no user context for generate_data.py)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler with rotation (10MB, 5 backups)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler for development visibility
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


class DataGenerator:
    def __init__(self):
        # Initialize logger FIRST before any operations that might log
        self.logger = setup_logger('data_generator', 'logs/admin.log', logging.INFO)

        self.config = self.load_config()
        self.tmdb_key = self.config['api']['tmdb_api_key']  # Changed from self.config['tmdb_api_key']

        # Watchmode API - Get new key from https://api.watchmode.com/ (free tier: 1000 calls/month)
        self.watchmode_key = os.environ.get('WATCHMODE_API_KEY')
        if not self.watchmode_key:
            # Try fallback from config.yaml
            self.watchmode_key = self.config.get('api', {}).get('watchmode_api_key')

        # Validate Watchmode API key
        if not self.watchmode_key or self.watchmode_key == "REPLACE_WITH_NEW_API_KEY":
            self.logger.error(
                "WATCHMODE_API_KEY not found or using placeholder value. "
                "Please set the WATCHMODE_API_KEY environment variable or add "
                "'watchmode_api_key' to the 'api' section in config.yaml. "
                "Get a free key from https://api.watchmode.com/"
            )
            # Disable Watchmode usage explicitly
            self.watchmode_enabled = False
            self.watchmode_key = None
        else:
            self.watchmode_enabled = True
        self.wikipedia_cache = self.load_cache('wikipedia_cache.json')
        self.rt_cache = self.load_cache('rt_cache.json')
        self.wikipedia_overrides = self.load_cache('overrides/wikipedia_overrides.json')
        self.rt_overrides = self.load_cache('overrides/rt_overrides.json')
        self.watch_links_overrides = self.load_cache('overrides/watch_links_overrides.json')
        self.trailer_overrides = self.load_cache('overrides/trailer_overrides.json')
        self.watch_links_cache = self.load_cache('cache/watch_links_cache.json')
        self.watch_link_overrides = self.load_cache('admin/watch_link_overrides.json')

        # Load reviews
        self.reviews = {}
        if os.path.exists('admin/movie_reviews.json'):
            try:
                with open('admin/movie_reviews.json', 'r') as f:
                    self.reviews = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load movie reviews from admin/movie_reviews.json: {e}")
                self.reviews = {}

        # Watchmode usage statistics
        self.watchmode_stats = {
            'search_calls': 0,
            'source_calls': 0,
            'cache_hits': 0,
            'watchmode_successes': 0,
            'agent_attempts': 0,
            'agent_successes': 0,
            'agent_cache_hits': 0,
            'override_hits': 0,
            'rt_attempts': 0,
            'rt_successes': 0,
            'rt_cache_hits': 0,
            'schema_validation_warnings': 0,
            'schema_validation_passes': 0
        }

        # Wikipedia usage statistics
        self.wikipedia_stats = {
            'wikidata_attempts': 0,
            'wikidata_successes': 0
        }

        # Discovery statistics
        self.discovery_stats = {
            'pages_fetched': 0,
            'total_results': 0,
            'new_movies_added': 0,
            'duplicates_skipped': 0,
            'api_calls': 0,
            'debug_enabled': False
        }

        self.agent_scraper = None  # Lazy initialization
        self.youtube_scraper = None  # Lazy initialization for YouTube trailer scraping
        self.youtube_trailer_cache = self.load_cache('youtube_trailer_cache.json')
        self.rt_driver = None  # Lazy Selenium driver for RT scraping
        self.rt_last_scrape_time = 0  # Track last scrape for rate limiting
        self.platform_scraper = None  # Lazy initialization for streaming platform scraper
    
    def load_config(self):
        """Load configuration from config.yaml and environment variables"""
        config = {}

        # Load from config.yaml if it exists
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config = yaml_config  # Load entire config, not just 'api' section

        # Environment variable takes precedence for API key
        tmdb_key = os.environ.get('TMDB_API_KEY')
        if tmdb_key:
            if 'api' not in config:
                config['api'] = {}
            config['api']['tmdb_api_key'] = tmdb_key

        # Validate that we have a key
        if not config.get('api', {}).get('tmdb_api_key'):
            raise ValueError(
                "TMDB API key not found. Please set the TMDB_API_KEY environment variable "
                "or add 'tmdb_api_key' to the 'api' section in config.yaml"
            )

        return config

    def append_affiliate_tag(self, url, service_name):
        """
        Append affiliate tags to streaming service URLs.

        Args:
            url (str): The original URL
            service_name (str): The service name (e.g., "Amazon Video", "Apple TV")

        Returns:
            str: URL with affiliate tag appended, or original URL if not applicable
        """
        # Return original URL if None or empty
        if not url or not isinstance(url, str):
            return url

        # Check if affiliate tagging is enabled globally
        affiliate_config = self.config.get('affiliate', {})
        if not affiliate_config.get('enabled', False):
            return url

        # Normalize service name for matching
        service_lower = service_name.lower() if service_name else ''

        # Amazon affiliate tagging
        if 'amazon' in service_lower or 'amazon' in url.lower():
            amazon_config = affiliate_config.get('amazon', {})
            if amazon_config.get('enabled', False):
                tag = amazon_config.get('tag', '')
                # Only add tag if it's not a placeholder
                if tag and tag != 'REPLACE_WITH_YOUR_AMAZON_TAG':
                    # Check if URL already has parameters
                    separator = '&' if '?' in url else '?'
                    # Check if tag already exists in URL
                    if 'tag=' not in url:
                        return f"{url}{separator}tag={tag}"

        # Apple affiliate tagging
        elif 'apple' in service_lower or 'itunes' in url.lower() or 'apple.com' in url.lower():
            apple_config = affiliate_config.get('apple', {})
            if apple_config.get('enabled', False):
                token = apple_config.get('token', '')
                # Only add token if it's not a placeholder
                if token and token != 'REPLACE_WITH_YOUR_APPLE_TOKEN':
                    # Check if URL already has parameters
                    separator = '&' if '?' in url else '?'
                    # Check if token already exists in URL
                    if 'at=' not in url:
                        return f"{url}{separator}at={token}"

        # Return original URL if no affiliate tag was added
        return url

    def _init_agent_scraper(self):
        """Initialize agent scraper if not already initialized"""
        if self.agent_scraper is None:
            # Check if agent scraper is enabled in config
            agent_config = self.config.get('agent_scraper', {})
            enabled = agent_config.get('enabled', True)  # Default to True if not specified

            if not enabled:
                self.logger.debug("Agent scraper disabled in config.yaml")
                self.agent_scraper = False
                return

            # Check if playwright is available
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                self.logger.debug("Playwright not installed, agent scraper disabled")
                self.logger.debug("Install with: pip install playwright && playwright install chromium")
                self.agent_scraper = False
                return

            try:
                # Read config settings
                cache_file = 'cache/agent_links_cache.json'  # Could be configurable

                self.logger.debug("Initializing agent scraper with Playwright...")
                self.agent_scraper = AgentLinkScraper(
                    cache_file=cache_file,
                    config=agent_config  # Pass entire config dict
                )
                self.logger.debug("Agent scraper initialized (Playwright)")
            except Exception as e:
                self.logger.exception(f"Failed to initialize agent scraper: {e}")
                self.agent_scraper = False  # Mark as failed to prevent retries

    def _init_rt_driver(self):
        """Initialize Selenium WebDriver for RT scraping"""
        if self.rt_driver is not None:  # Already initialized (could be False for failed)
            return self.rt_driver is not False

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service

            # Configure Chrome options
            chrome_options = Options()

            # Read headless setting from config
            headless = self.config.get('rt_scraper', {}).get('headless', True)
            if headless:
                chrome_options.add_argument("--headless")

            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            # Use ChromeDriverManager for automatic driver installation
            service = Service(ChromeDriverManager().install())

            # Create WebDriver instance
            self.rt_driver = webdriver.Chrome(service=service, options=chrome_options)

            # Set page load timeout from config
            timeout = self.config.get('rt_scraper', {}).get('timeout', 10)
            self.rt_driver.set_page_load_timeout(timeout)

            self.logger.debug("RT driver initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize RT driver: {e}")
            self.rt_driver = False  # Mark as failed to prevent retries
            return False

    def _rt_rate_limit(self):
        """Enforce minimum delay between RT scrapes to avoid anti-bot detection"""
        # Read rate limit from config, fallback to 2.0 seconds
        rate_limit = self.config.get('rt_scraper', {}).get('rate_limit', 2.0)

        # Calculate time since last scrape
        time_since_last = time.time() - self.rt_last_scrape_time

        # If less than rate limit, sleep for remaining time
        if time_since_last < rate_limit:
            sleep_time = rate_limit - time_since_last
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)

        # Update last scrape time
        self.rt_last_scrape_time = time.time()

    def scrape_rt_score(self, title, year):
        """Public wrapper function to scrape RT score for external consumers

        Args:
            title: Movie title
            year: Release year

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        return self._scrape_rt_page(title, year)

    def _scrape_rt_page(self, title, year):
        """Scrape RT search page to find movie URL and score"""
        # Initialize driver if needed
        if not self._init_rt_driver():
            return None

        # Check driver availability
        if self.rt_driver is False:
            return None

        # Apply rate limiting
        self._rt_rate_limit()

        # Increment attempts counter
        self.watchmode_stats['rt_attempts'] += 1

        try:
            # Build search URL
            search_query = f"{title} {year}"
            search_url = f"https://www.rottentomatoes.com/search?search={quote(search_query)}"

            self.logger.debug(f"Searching RT: {title} ({year})")

            # Navigate to search page
            self.rt_driver.get(search_url)
            time.sleep(2)  # Wait for page load

            # Try selector fallbacks for search results
            search_selectors = [
                "search-page-media-row a[data-qa='info-name']",  # Primary
                "a[data-qa='thumbnail-link']",  # Fallback 1
                "a[href*='/m/'][data-qa='info-name']",  # Fallback 2
                "search-page-result a[href*='/m/']",  # Fallback 3
                "a[href*='/m/']"  # Generic movie link
            ]

            movie_url = None
            for selector in search_selectors:
                try:
                    from selenium.webdriver.common.by import By
                    elements = self.rt_driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        href = elements[0].get_attribute('href')
                        if href and '/m/' in href:
                            movie_url = href
                            self.logger.debug(f"Found with selector: {selector}")
                            break
                except Exception:
                    continue

            if not movie_url:
                self.logger.warning(f"No RT page found for {title} ({year})")
                # Cache the failure with consistent schema
                cache_key = f"{title}_{year}"
                cached_failure = {
                    'url': None,
                    'score': None,
                    'title': title,
                    'scraped_at': datetime.now().isoformat()
                }
                self.rt_cache[cache_key] = cached_failure
                self._save_rt_cache()
                return None

            # Navigate to movie page
            self.rt_driver.get(movie_url)
            time.sleep(2)  # Wait for page load

            # Try selector fallbacks for score
            score_selectors = [
                "rt-text[slot='criticsScore']",  # Primary
                "score-board",  # Fallback 1
                "[data-qa='tomatometer']",  # Fallback 2
                "[data-qa='tomatometer-value']",  # Fallback 3
                ".tomatometer-score",  # Fallback 4
                "score-icon-critic"  # Fallback 5
            ]

            score = None
            # Define multiple regex patterns to try in order
            regex_patterns = [
                r'(\d+)\s*%',                          # Basic pattern: number followed by %
                r'tomatometer\s*:?\s*(\d+)\s*%',       # Pattern with tomatometer prefix
                r'(\d+)\s*percent',                     # Pattern with "percent" instead of %
                r'critics?\s*score\s*:?\s*(\d+)',      # Pattern with "critic score" prefix
                r'fresh\s*:?\s*(\d+)',                 # Pattern with "fresh" prefix
            ]

            for selector in score_selectors:
                try:
                    element = self.rt_driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        # Get text from multiple sources
                        text_sources = [
                            element.text or "",
                            element.get_attribute('textContent') or "",
                            element.get_attribute('aria-label') or "",
                            element.get_attribute('data-score') or "",
                            element.get_attribute('innerHTML') or ""
                        ]

                        # Concatenate all text sources for matching
                        combined_text = " ".join(text_sources).lower()

                        # Try each regex pattern until one matches
                        for pattern in regex_patterns:
                            match = re.search(pattern, combined_text, re.IGNORECASE)
                            if match:
                                score = match.group(1) + "%"
                                self.logger.debug(f"Found score with selector: {selector}, pattern: {pattern}")
                                break

                        if score:
                            break
                except Exception:
                    continue

            # Create result
            result = {
                'url': movie_url,
                'score': score
            }

            self.logger.debug(f"RT scraping successful: {movie_url} (Score: {score or 'N/A'})")

            # Cache the result with consistent schema
            cache_key = f"{title}_{year}"
            cached_result = {
                'url': result['url'],
                'score': result['score'],
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self.rt_cache[cache_key] = cached_result
            self._save_rt_cache()
            self.watchmode_stats['rt_successes'] += 1

            return result

        except Exception as e:
            self.logger.error(f"RT scraping error for {title} ({year}): {e}")
            # Cache the failure with consistent schema
            cache_key = f"{title}_{year}"
            cached_failure = {
                'url': None,
                'score': None,
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self.rt_cache[cache_key] = cached_failure
            self._save_rt_cache()
            return None

    def load_cache(self, filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return {}
    
    def save_cache(self, data, filename):
        os.makedirs(os.path.dirname(filename) if '/' in filename else '.', exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

    def generate_google_search_fallback(self, title, year, service):
        """Generate a Google search URL as fallback when no direct link is available"""
        search_query = quote(f"{title} {year} watch {service}")
        return f"https://www.google.com/search?q={search_query}"

    def simplify_provider_name(self, provider_name):
        """Simplify provider names for display
        Examples:
        - 'Amazon Prime Video' → 'Amazon'
        - 'Viaplay Amazon Channel' → 'Amazon'
        - 'AMC Plus Apple TV Channel' → 'AMC+'
        """
        if not provider_name:
            return provider_name

        # Most specific patterns first (check AMC before Amazon)
        simplifications = [
            ('amc', 'AMC+'),
            ('netflix', 'Netflix'),
            ('disney', 'Disney+'),
            ('hulu', 'Hulu'),
            ('hbo max', 'Max'),
            ('paramount', 'Paramount+'),
            ('peacock', 'Peacock'),
            ('amazon', 'Amazon'),
            ('apple tv', 'Apple TV'),
            ('shudder', 'Shudder'),
            ('mubi', 'MUBI'),
            ('criterion', 'Criterion'),
            ('vudu', 'Vudu'),
            ('google play', 'Google Play'),
            ('youtube', 'YouTube'),
            ('fandango', 'Fandango'),
        ]

        provider_lower = provider_name.lower()
        for pattern, simplified in simplifications:
            if pattern in provider_lower:
                return simplified

        return provider_name

    def get_movie_details(self, movie_id):
        """Get full movie details from TMDB"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {
            'api_key': self.tmdb_key,
            'append_to_response': 'credits,videos,external_ids'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching details for {movie_id}: {e}")
        return None
    
    def find_wikipedia_url(self, title, year, imdb_id, movie_id=None):
        """Find Wikipedia URL using waterfall approach

        Priority waterfall:
        1. Overrides (overrides/wikipedia_overrides.json) - Manual curator fixes
        2. Cache (wikipedia_cache.json) - Previously successful lookups
        3. Wikidata SPARQL - Query by IMDb ID for structured data
        4. Wikipedia REST API - Search by title with (year film) suffix
        5. Log missing and return None

        Args:
            title: Movie title
            year: Release year
            imdb_id: IMDb ID from TMDB external_ids (e.g., 'tt35076553')
            movie_id: TMDB ID for logging purposes

        Returns:
            Wikipedia URL string or None if not found
        """
        # 1. Check overrides first
        if imdb_id and imdb_id in self.wikipedia_overrides:
            return f"https://en.wikipedia.org/wiki/{self.wikipedia_overrides[imdb_id]}"

        # 2. Check cache
        cache_key = f"{title}_{year}"
        if cache_key in self.wikipedia_cache:
            cached_data = self.wikipedia_cache[cache_key]
            if isinstance(cached_data, dict):
                return cached_data.get('url')
            return cached_data

        # 3. Try Wikidata SPARQL query (if IMDb ID available)
        if imdb_id:
            wiki_url = self.find_wikipedia_url_wikidata(imdb_id)
            if wiki_url:
                # Cache the result with source attribution
                self.wikipedia_cache[cache_key] = {
                    'url': wiki_url,
                    'title': title,
                    'cached_at': datetime.now().isoformat(),
                    'source': 'wikidata'
                }
                self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
                return wiki_url
            else:
                print(f"  Wikidata lookup failed for {title}, trying Wikipedia REST API...")

        # 4. Try Wikipedia API search with proper headers
        try:
            headers = {
                'User-Agent': 'NewReleaseWall/1.0 (https://github.com/hadrianbelove-stack/nrw-production; hadrianbelove@gmail.com)'
            }

            # Try exact match with (year film) suffix
            search_title = f"{title} ({year} film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    self.wikipedia_cache[cache_key] = {'url': wiki_url, 'title': title, 'cached_at': datetime.now().isoformat(), 'source': 'wikipedia_api'}
                    self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
                    return wiki_url

            # Try without year
            search_title = f"{title} (film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    self.wikipedia_cache[cache_key] = {'url': wiki_url, 'title': title, 'cached_at': datetime.now().isoformat(), 'source': 'wikipedia_api'}
                    self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
                    return wiki_url

        except Exception as e:
            print(f"Wikipedia search error for {title}: {e}")

        # 5. Fallback to Wikipedia search URL
        search_fallback_url = f"https://en.wikipedia.org/w/index.php?search={quote(title + ' (' + year + ' film)')}"
        self.wikipedia_cache[cache_key] = {
            'url': search_fallback_url,
            'title': title,
            'cached_at': datetime.now().isoformat(),
            'source': 'search_fallback'
        }
        self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
        return search_fallback_url
    
    def log_missing_wikipedia(self, movie_id, title, year, imdb_id):
        """Log missing Wikipedia links for manual review"""
        try:
            missing_file = 'missing_wikipedia.json'
            if os.path.exists(missing_file):
                with open(missing_file, 'r') as f:
                    missing = json.load(f)
            else:
                missing = {"missing": []}
            
            entry = {
                "tmdb_id": movie_id,
                "title": title,
                "year": year,
                "imdb_id": imdb_id,
                "timestamp": datetime.now().isoformat()
            }
            
            # Avoid duplicates
            if not any(m['tmdb_id'] == movie_id for m in missing['missing']):
                missing['missing'].append(entry)
                with open(missing_file, 'w') as f:
                    json.dump(missing, f, indent=2)
        except Exception as e:
            print(f"Failed to log missing Wikipedia: {e}")

    def find_wikipedia_url_wikidata(self, imdb_id):
        """Query Wikidata SPARQL endpoint to find Wikipedia article URL using IMDb ID

        Args:
            imdb_id: IMDb ID from TMDB external_ids (e.g., 'tt35076553')

        Returns:
            Wikipedia URL string or None if not found
        """
        # Validate input
        if not imdb_id:
            return None

        # Increment attempts counter
        self.wikipedia_stats['wikidata_attempts'] += 1

        try:
            # Build SPARQL query to find English Wikipedia article by IMDb ID
            sparql_query = f"""
            SELECT ?article WHERE {{
              ?item wdt:P345 "{imdb_id}" .
              ?article schema:about ?item .
              ?article schema:isPartOf <https://en.wikipedia.org/> .
            }}
            """

            # Query Wikidata SPARQL endpoint
            url = "https://query.wikidata.org/sparql"
            headers = {
                'User-Agent': 'NewReleaseWall/1.0 (https://github.com/hadrianbelove-stack/nrw-production; hadrianbelove@gmail.com)',
                'Accept': 'application/sparql-results+json'
            }
            params = {
                'query': sparql_query,
                'format': 'json'
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)

            # Check response status
            if response.status_code != 200:
                print(f"  Wikidata query error: HTTP {response.status_code}")
                return None

            # Parse JSON response
            data = response.json()
            results = data.get('results', {}).get('bindings', [])

            if not results:
                print(f"  ✗ Wikidata found no Wikipedia link for IMDb {imdb_id}")
                return None

            # Extract Wikipedia URL from first result
            wikipedia_url = results[0]['article']['value']

            # Validate URL format
            if not wikipedia_url or not wikipedia_url.startswith('https://en.wikipedia.org/wiki/'):
                print(f"  Wikidata returned invalid Wikipedia URL: {wikipedia_url}")
                return None

            # Success
            self.wikipedia_stats['wikidata_successes'] += 1
            print(f"  ✓ Wikidata found Wikipedia link for IMDb {imdb_id}")
            return wikipedia_url

        except requests.exceptions.Timeout:
            print(f"  Wikidata query timeout for IMDb {imdb_id}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  Wikidata network error for IMDb {imdb_id}: {e}")
            return None
        except KeyError as e:
            print(f"  Wikidata response parsing error for IMDb {imdb_id}: {e}")
            return None
        except Exception as e:
            print(f"  Wikidata query error for IMDb {imdb_id}: {e}")
            return None

    def find_trailer_url(self, movie_details):
        """Extract trailer URL from TMDB movie details or scrape YouTube"""
        title = movie_details.get('title', '')
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''

        # 1. Check manual overrides first
        override_key = f"{title}_{year}"
        if override_key in self.trailer_overrides:
            return self.trailer_overrides[override_key]

        videos = movie_details.get('videos', {}).get('results', [])

        # 2. Prioritize official trailers from TMDB
        for video in videos:
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"

        # 3. Fall back to any YouTube video from TMDB
        for video in videos:
            if video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"

        # 4. Check YouTube scraper cache
        cache_key = f"{title}_{year}"
        if cache_key in self.youtube_trailer_cache:
            cached_url = self.youtube_trailer_cache[cache_key]
            if cached_url:  # Don't return None from cache, keep trying
                return cached_url

        # 5. Try scraping YouTube for the trailer
        if self.youtube_scraper is None:
            self.youtube_scraper = YouTubeTrailerScraper(
                cache_file='youtube_trailer_cache.json',
                headless=True
            )

        scraped_url = self.youtube_scraper.find_trailer(title, year)
        if scraped_url:
            return scraped_url

        # 6. Final fallback: generate YouTube search URL
        search_query = quote(f"{title} {year} trailer")
        return f"https://www.youtube.com/results?search_query={search_query}"
    
    def find_rt_url(self, title, year, imdb_id):
        """Find Rotten Tomatoes URL and score"""
        # 1. Check overrides first
        if imdb_id and imdb_id in self.rt_overrides:
            override = self.rt_overrides[imdb_id]
            if isinstance(override, dict):
                return override
            return {'url': override, 'score': None}

        # 2. Check cache with TTL enforcement
        cache_key = f"{title}_{year}"
        if cache_key in self.rt_cache:
            cached_data = self.rt_cache[cache_key]

            # Check if cache entry has expired (90-day TTL)
            is_expired = False
            if cached_data is not None and isinstance(cached_data, dict) and 'scraped_at' in cached_data:
                try:
                    scraped_at = datetime.fromisoformat(cached_data['scraped_at'])
                    cache_age = datetime.now() - scraped_at
                    if cache_age > timedelta(days=90):
                        is_expired = True
                        print(f"  RT cache expired for {title} ({year}), age: {cache_age.days} days")
                except Exception as e:
                    print(f"  Warning: Invalid scraped_at timestamp in RT cache: {e}")
                    is_expired = True
            elif cached_data is None:
                # Legacy None entries (failures) - treat as expired to retry failures after 90 days
                is_expired = True
            elif cached_data is not None and not isinstance(cached_data, dict):
                # Legacy cache entries without scraped_at - treat as expired
                is_expired = True

            # If not expired, return cached data
            if not is_expired:
                self.watchmode_stats['rt_cache_hits'] += 1

                # Handle cached failures (new schema: dict with null url/score)
                if isinstance(cached_data, dict) and cached_data.get('url') is None:
                    search_query = quote(f"{title} {year}")
                    return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}

                # Handle cached successes (new schema: dict with url/score)
                if isinstance(cached_data, dict):
                    return {'url': cached_data.get('url'), 'score': cached_data.get('score')}

                # Handle legacy successful cache hits (string values)
                if cached_data:
                    return {'url': cached_data, 'score': None}

                # Legacy None entries (should not reach here due to is_expired check above)
                search_query = quote(f"{title} {year}")
                return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}
            else:
                # Cache expired, continue to scraping logic
                print(f"  RT cache entry expired for {title} ({year}), will re-scrape")

        # 3. Check if RT scraper is enabled
        enabled = self.config.get('rt_scraper', {}).get('enabled', True)
        if not enabled:
            print("  RT scraping disabled via config")
            search_query = quote(f"{title} {year}")
            return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}

        # 4. Try RT scraper (inlined)
        result = self._scrape_rt_page(title, year)
        if result:
            return result

        # 5. Fall back to search
        search_query = quote(f"{title} {year}")
        return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}

    def _save_rt_cache(self):
        """Save RT cache to disk after updates"""
        try:
            with open('rt_cache.json', 'w') as f:
                json.dump(self.rt_cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save RT cache: {e}")

    def get_watch_links(self, movie_id, title, year, providers, force_refresh=False, tracking_data=None):
        """Get deep links with canonical streaming/rent/buy structure

        Priority waterfall:
        1. Manual watch links from movie_tracking.json - highest priority
        2. Admin overrides (admin/watch_link_overrides.json) - backward compatibility
        3. Cache (cache/watch_links_cache.json)
        4. Watchmode API
        5. Agent scraper (Netflix, Disney+, HBO Max, Hulu)
        6. TMDB provider names with null links

        Returns: {
            'streaming': {'service': 'Netflix', 'link': 'https://...'},  # subscription streaming
            'rent': {'service': 'Amazon', 'link': 'https://...'},        # rental
            'buy': {'service': 'Apple TV', 'link': 'https://...'}        # purchase
        }
        """
        # 1. Check manual watch links from tracking data FIRST (highest priority)
        if tracking_data and 'watch_links' in tracking_data and tracking_data.get('manual_watch_links'):
            manual_links = tracking_data['watch_links']
            try:
                validated_manual = self.validate_watch_links_schema(manual_links, title)
                if validated_manual:
                    print(f"  Using manual watch links from tracking data for {title}: {list(validated_manual.keys())}")
                    self.watchmode_stats['manual_tracking_hits'] = self.watchmode_stats.get('manual_tracking_hits', 0) + 1

                    # Cache the validated manual links
                    cache_key = str(movie_id)
                    now = datetime.now().isoformat()
                    self.watch_links_cache[cache_key] = {
                        'links': validated_manual,
                        'cached_at': now,
                        'source': 'manual_tracking'
                    }
                    self.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

                    return validated_manual
            except Exception as e:
                print(f"  Warning: Invalid manual watch links in tracking data for {title}: {e}")

        # 2. Check overrides/watch_links_overrides.json (highest priority after manual tracking)
        cache_key = str(movie_id)
        if cache_key in self.watch_links_overrides:
            override_data = self.watch_links_overrides[cache_key]
            try:
                validated_override = self.validate_watch_links_schema(override_data, title)
                if validated_override:
                    print(f"  Using override from watch_links_overrides.json for {title}: {list(validated_override.keys())}")
                    self.watchmode_stats['override_hits'] = self.watchmode_stats.get('override_hits', 0) + 1
                    return validated_override
            except Exception as e:
                print(f"  Warning: Invalid override in watch_links_overrides.json for {title}: {e}")

        # 3. Check admin overrides (backward compatibility)
        validated_overrides = {}
        if cache_key in self.watch_link_overrides:
            overrides = self.watch_link_overrides[cache_key]
            # Validate overrides but continue with waterfall for non-overridden categories
            for category in ['streaming', 'rent', 'buy']:
                if category in overrides:
                    override_data = overrides[category]
                    # Validate structure
                    if isinstance(override_data, dict) and 'service' in override_data and 'link' in override_data:
                        # Validate service name is non-empty string
                        service = override_data['service']
                        if not service or not isinstance(service, str) or not service.strip():
                            print(f"  Warning: Invalid override service name for {title} {category}: {service}")
                            continue
                        # Validate URL if link is not None/empty
                        link = override_data['link']
                        if link and isinstance(link, str) and (link.startswith('http://') or link.startswith('https://')):
                            validated_overrides[category] = override_data
                        elif not link:  # Empty link means "no override for this category"
                            continue
                        else:
                            print(f"  Warning: Invalid override link for {title} {category}: {link}")

            if validated_overrides:
                print(f"  Using admin overrides for {title}: {list(validated_overrides.keys())}")
                self.watchmode_stats['override_hits'] += 1

        # 2. Check cache (unless force refresh)
        if not force_refresh and cache_key in self.watch_links_cache:
            cached = self.watch_links_cache[cache_key]
            if cached.get('links'):
                self.watchmode_stats['cache_hits'] += 1
                # Migrate legacy cache format if needed
                migrated_links = self._migrate_legacy_cache_format(cached['links'])
                if migrated_links != cached['links']:
                    # Update cache with migrated format
                    self.watch_links_cache[cache_key]['links'] = migrated_links

                    # Recompute source metadata based on whether any category has a non-null link
                    has_links = any(
                        link.get('link') is not None
                        for link in migrated_links.values()
                        if isinstance(link, dict)
                    )
                    source_type = 'watchmode_api' if has_links else 'tmdb_providers'
                    self.watch_links_cache[cache_key]['source'] = source_type
                    self.watch_links_cache[cache_key]['cached_at'] = datetime.now().isoformat()

                    self.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                return migrated_links

        # Service priority hierarchies
        STREAMING_PRIORITY = ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max',
                              'Hulu', 'Amazon Prime Video', 'Prime Video', 'Apple TV+',
                              'Paramount+', 'Paramount Plus', 'Peacock', 'MUBI', 'Shudder', 'Criterion Channel']

        PAID_PRIORITY = ['Amazon Video', 'Amazon', 'Prime Video', 'Apple TV', 'Vudu',
                         'Google Play Movies', 'Google Play', 'Microsoft Store']


        def select_best_service(service_list, priority_list):
            """Select best service from list based on priority"""
            for priority_service in priority_list:
                for available_service in service_list:
                    if priority_service.lower() in available_service.lower():
                        return available_service
            # If no priority match, return first available
            return service_list[0] if service_list else None

        # Collect sources from Watchmode API (skip categories that already have overrides)
        watchmode_streaming = []
        watchmode_rent = []
        watchmode_buy = []

        # Skip external API calls for categories that already have overrides
        skip_streaming = 'streaming' in validated_overrides
        skip_rent = 'rent' in validated_overrides
        skip_buy = 'buy' in validated_overrides

        # Skip Watchmode API if not enabled/configured
        if not self.watchmode_enabled:
            self.logger.debug(f"Watchmode API disabled, skipping for {title}")
        else:
            try:
                # Step 1: Search by TMDB ID
                search_url = "https://api.watchmode.com/v1/search/"
                search_params = {
                    "apiKey": self.watchmode_key,
                    "search_field": "tmdb_movie_id",
                    "search_value": movie_id
                }

                self.watchmode_stats['search_calls'] += 1
                search_response = requests.get(search_url, params=search_params, timeout=10)

                if search_response.status_code == 200:
                    search_data = search_response.json()

                    if search_data.get('title_results'):
                        watchmode_id = search_data['title_results'][0]['id']

                        # Step 2: Get sources
                        sources_url = f"https://api.watchmode.com/v1/title/{watchmode_id}/details/"
                        sources_params = {
                            "apiKey": self.watchmode_key,
                            "append_to_response": "sources"
                        }

                        self.watchmode_stats['source_calls'] += 1
                        sources_response = requests.get(sources_url, params=sources_params, timeout=10)

                        if sources_response.status_code == 200:
                            sources_data = sources_response.json()
                            sources = sources_data.get('sources', [])

                            if sources:
                                self.watchmode_stats['watchmode_successes'] += 1

                            # Collect US sources by type
                            for source in sources:
                                if source.get('region') != 'US':
                                    continue

                                service_name = source.get('name', '')
                                web_url = source.get('web_url', '')
                                source_type = source.get('type', '')

                                if not service_name or not web_url:
                                    continue

                                if source_type == 'sub' and not skip_streaming:
                                    watchmode_streaming.append({'service': service_name, 'link': web_url})
                                elif source_type == 'rent' and not skip_rent:
                                    watchmode_rent.append({'service': service_name, 'link': web_url})
                                elif source_type == 'buy' and not skip_buy:
                                    watchmode_buy.append({'service': service_name, 'link': web_url})

            except Exception as e:
                print(f"  Warning: Watchmode API failed for {title}: {e}")

        # Agent search tier (optional): Try to find deep links for Amazon/Apple TV when Watchmode has no data
        # Capture lengths before platform scraper to detect if it added links
        streaming_len_before = len(watchmode_streaming)
        rent_len_before = len(watchmode_rent)
        buy_len_before = len(watchmode_buy)

        if StreamingPlatformScraper and (not watchmode_streaming or not watchmode_rent or not watchmode_buy):
            self._try_platform_agent_search(title, year, providers, watchmode_streaming, watchmode_rent, watchmode_buy, skip_streaming, skip_rent, skip_buy)

        # Check if platform scraper actually added any links
        platform_scraper_used = (
            len(watchmode_streaming) > streaming_len_before or
            len(watchmode_rent) > rent_len_before or
            len(watchmode_buy) > buy_len_before
        )

        # Build final watch_links with canonical streaming/rent/buy structure
        watch_links = {}

        # STREAMING: Prefer Watchmode, fallback to TMDB providers with smart Amazon handling (skip if overridden)
        if not skip_streaming:
            if watchmode_streaming:
                # Use Watchmode streaming data
                best_service = select_best_service([s['service'] for s in watchmode_streaming], STREAMING_PRIORITY)
                for source in watchmode_streaming:
                    if source['service'] == best_service:
                        watch_links['streaming'] = source
                        break
            elif providers.get('streaming'):
                # Fallback to TMDB provider data
                service = select_best_service(providers['streaming'], STREAMING_PRIORITY)

                # SMART FALLBACK: If TMDB says "Amazon Prime Video" but Watchmode didn't find subscription,
                # reuse any Amazon rent/buy link we have (it's the same detail page on Amazon)
                if 'Amazon Prime Video' in service and (watchmode_rent or watchmode_buy):
                    # Find any Amazon link in rent or buy sources
                    amazon_link = None
                    for source in watchmode_rent + watchmode_buy:
                        if 'Amazon' in source['service'] and source.get('link'):
                            amazon_link = source['link']
                            break

                    if amazon_link:
                        watch_links['streaming'] = {
                            'service': service,
                            'link': amazon_link  # Same page shows both Prime (free) and rent/buy options
                        }
                    else:
                        # No Amazon link available, use Google search fallback
                        watch_links['streaming'] = {
                            'service': service,
                            'link': self.generate_google_search_fallback(title, year, service)
                        }
                else:
                    # Try agent scraper for supported platforms before returning null
                    agent_result = self._try_agent_scraper(movie_id, title, year, service, 'streaming')
                    watch_links['streaming'] = agent_result

        # RENT: Use Watchmode or fallback to platform links (skip if overridden)
        if not skip_rent:
            if watchmode_rent:
                best_service = select_best_service([s['service'] for s in watchmode_rent], PAID_PRIORITY)
                for source in watchmode_rent:
                    if source['service'] == best_service:
                        watch_links['rent'] = source
                        break
            elif providers.get('rent'):
                rent_service = select_best_service(providers.get('rent', []), PAID_PRIORITY)
                if rent_service:
                    watch_links['rent'] = {
                        'service': rent_service,
                        'link': self.generate_google_search_fallback(title, year, rent_service)
                    }

        # BUY: Use Watchmode or fallback to platform links (skip if overridden)
        if not skip_buy:
            if watchmode_buy:
                best_service = select_best_service([s['service'] for s in watchmode_buy], PAID_PRIORITY)
                for source in watchmode_buy:
                    if source['service'] == best_service:
                        watch_links['buy'] = source
                        break
            elif providers.get('buy'):
                buy_service = select_best_service(providers.get('buy', []), PAID_PRIORITY)
                if buy_service:
                    watch_links['buy'] = {
                        'service': buy_service,
                        'link': self.generate_google_search_fallback(title, year, buy_service)
                    }

        # Overlay admin overrides on top of auto-discovered links
        for category, override_data in validated_overrides.items():
            watch_links[category] = override_data

        # Validate schema before caching and returning
        validated_links = self.validate_watch_links_schema(watch_links, title)

        # Apply affiliate tags to all validated links (after validation, before caching)
        for category in ['streaming', 'rent', 'buy']:
            if category in validated_links and isinstance(validated_links[category], dict):
                link_data = validated_links[category]
                if link_data.get('link') and link_data.get('service'):
                    # Append affiliate tag to the link
                    original_link = link_data['link']
                    tagged_link = self.append_affiliate_tag(original_link, link_data['service'])
                    if tagged_link != original_link:
                        validated_links[category]['link'] = tagged_link
                        self.logger.debug(f"Added affiliate tag to {category} link for {title}: {link_data['service']}")

        # Cache result with canonical schema (use validated links)
        if validated_links:
            # Determine source type based on where links came from
            has_links = any(
                link.get('link') is not None
                for link in validated_links.values()
                if isinstance(link, dict)
            )

            # Use platform_scraper_used to accurately determine if platform scraper added links
            if platform_scraper_used:
                source_type = 'agent_search'
            elif has_links:
                source_type = 'watchmode_api'
            else:
                source_type = 'tmdb_providers'

            self.watch_links_cache[cache_key] = {
                'links': validated_links,
                'cached_at': datetime.now().isoformat(),
                'source': source_type
            }
            self.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

        return validated_links

    def validate_watch_links_schema(self, watch_links, movie_title='Unknown'):
        """
        Runtime validation that watch_links conform to canonical streaming/rent/buy schema.

        Args:
            watch_links: Dict to validate (typically from get_watch_links)
            movie_title: String for logging context

        Returns:
            Dict: Validated/cleaned watch_links with invalid entries removed
        """
        import re
        from urllib.parse import urlparse

        # Initialize stats counters if not present
        if 'schema_validation_warnings' not in self.watchmode_stats:
            self.watchmode_stats['schema_validation_warnings'] = 0
        if 'schema_validation_passes' not in self.watchmode_stats:
            self.watchmode_stats['schema_validation_passes'] = 0

        # Type check: Verify watch_links is a dict
        if not isinstance(watch_links, dict):
            self.logger.warning(f"Invalid watch_links type '{type(watch_links).__name__}' for {movie_title}, expected dict")
            self.watchmode_stats['schema_validation_warnings'] += 1
            return {}

        validated_links = {}
        had_warnings = False
        valid_categories = ['streaming', 'rent', 'buy']

        for category, category_data in watch_links.items():
            # Category validation: Check that all keys are in ['streaming', 'rent', 'buy']
            if category not in valid_categories:
                self.logger.warning(f"Invalid watch link category '{category}' for {movie_title}")
                had_warnings = True
                continue

            # Structure validation: For each category, verify it's a dict with 'service' and 'link' keys
            if not isinstance(category_data, dict):
                self.logger.warning(f"Invalid category data type for '{category}' in {movie_title}, expected dict")
                had_warnings = True
                continue

            if 'service' not in category_data or 'link' not in category_data:
                self.logger.warning(f"Missing required keys (service/link) in '{category}' for {movie_title}")
                had_warnings = True
                continue

            # Service validation: Verify service is non-empty string
            if not isinstance(category_data['service'], str) or not category_data['service'].strip():
                self.logger.warning(f"Invalid service in '{category}' for {movie_title}")
                had_warnings = True
                continue

            # Link validation: Verify link is either None or valid HTTP/HTTPS URL string
            link = category_data['link']
            if link is not None:
                if not isinstance(link, str):
                    self.logger.warning(f"Invalid link type in '{category}' for {movie_title}, expected string or None")
                    had_warnings = True
                    continue

                # Basic URL validation
                try:
                    parsed = urlparse(link)
                    if not parsed.scheme or parsed.scheme not in ['http', 'https']:
                        self.logger.warning(f"Invalid URL scheme in '{category}' for {movie_title}")
                        had_warnings = True
                        continue
                    if not parsed.netloc:
                        print(f"Warning: Invalid URL netloc in '{category}' for {movie_title}")
                        had_warnings = True
                        continue
                except Exception:
                    print(f"Warning: Malformed URL in '{category}' for {movie_title}")
                    had_warnings = True
                    continue

            # If we reach here, the category data is valid
            validated_links[category] = category_data

        # Update statistics
        if had_warnings:
            self.watchmode_stats['schema_validation_warnings'] += 1
        else:
            self.watchmode_stats['schema_validation_passes'] += 1

        return validated_links

    def _try_agent_scraper(self, movie_id, title, year, service, category):
        """Try agent scraper for supported platforms"""
        supported_platforms = ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max', 'Hulu']
        print(f"  [DEBUG] Checking if '{service}' is in supported platforms: {supported_platforms}")

        # Check if service is supported
        if service not in supported_platforms:
            print(f"  [DEBUG] '{service}' not supported by agent scraper, returning Google search fallback")
            return {'service': service, 'link': self.generate_google_search_fallback(title, year, service)}

        # Initialize agent scraper if needed
        self._init_agent_scraper()
        print(f"  [DEBUG] Agent scraper state: {type(self.agent_scraper).__name__ if self.agent_scraper else 'None or False'}")
        if self.agent_scraper is False:
            return {'service': service, 'link': self.generate_google_search_fallback(title, year, service)}

        try:
            print(f"  Trying agent scraper for {title} on {service}...")
            self.watchmode_stats['agent_attempts'] += 1

            result = self.agent_scraper.find_watch_link(movie_id, title, year, service)
            print(f"  [DEBUG] Agent result: {result}")

            if result.get('cached'):
                self.watchmode_stats['agent_cache_hits'] += 1

            if result.get('link'):
                self.watchmode_stats['agent_successes'] += 1
                print(f"  ✓ Agent found link for {title} on {service}")
            else:
                print(f"  ✗ Agent could not find link for {title} on {service}")

            # Return found link or fallback to Google search
            final_link = result.get('link') or self.generate_google_search_fallback(title, year, service)
            print(f"  [DEBUG] Returning: {{'service': {service}, 'link': {final_link}}}")
            return {'service': service, 'link': final_link}

        except Exception as e:
            print(f"  Error in agent scraper for {title}: {e}")
            return {'service': service, 'link': self.generate_google_search_fallback(title, year, service)}

    def _try_platform_agent_search(self, title, year, providers, watchmode_streaming, watchmode_rent, watchmode_buy, skip_streaming, skip_rent, skip_buy):
        """Try platform scraper (Selenium) for Amazon/Apple TV when Watchmode API has no data"""

        # Check if platform scraper is enabled in config
        platform_config = self.config.get('platform_scraper', {})
        if not platform_config.get('enabled', True):
            print(f"  Platform scraper disabled in config, skipping {title}")
            return

        # Check if Amazon is enabled
        platforms_config = platform_config.get('platforms', {})
        amazon_enabled = platforms_config.get('amazon', True)
        apple_tv_enabled = platforms_config.get('apple_tv', True)

        if not amazon_enabled and not apple_tv_enabled:
            print(f"  No platforms enabled in config, skipping {title}")
            return

        # Initialize platform scraper if needed (lazy initialization)
        if self.platform_scraper is None:
            try:
                print(f"  Initializing platform scraper for {title}...")
                # Read settings from config
                headless_mode = platform_config.get('headless', True)
                timeout_seconds = platform_config.get('timeout', 30)
                rate_limit_seconds = platform_config.get('rate_limit', None)
                self.platform_scraper = StreamingPlatformScraper(
                    headless=headless_mode,
                    timeout_seconds=timeout_seconds,
                    rate_limit_seconds=rate_limit_seconds
                )
                print(f"  Platform scraper initialized (headless={headless_mode}, timeout={timeout_seconds}s)")
            except Exception as e:
                print(f"  Warning: Could not initialize platform scraper: {e}")
                self.platform_scraper = False
                return

        # Skip if initialization failed
        if self.platform_scraper is False:
            print(f"  Platform scraper initialization failed, skipping {title}")
            return

        # Track platform scraper attempts
        if not hasattr(self, 'watchmode_stats'):
            self.watchmode_stats = {}
        self.watchmode_stats['platform_scraper_attempts'] = self.watchmode_stats.get('platform_scraper_attempts', 0) + 1

        # Enforce rate limiting if configured
        if hasattr(self.platform_scraper, 'rate_limit_seconds') and self.platform_scraper.rate_limit_seconds:
            if not hasattr(self, '_last_platform_scraper_time'):
                self._last_platform_scraper_time = 0

            time_since_last = time.time() - self._last_platform_scraper_time
            if time_since_last < self.platform_scraper.rate_limit_seconds:
                sleep_time = self.platform_scraper.rate_limit_seconds - time_since_last
                print(f"  Rate limiting: sleeping {sleep_time:.1f}s before platform scraper")
                time.sleep(sleep_time)

            self._last_platform_scraper_time = time.time()

        # Try streaming providers (if no Watchmode streaming data and not skipped)
        if not skip_streaming and not watchmode_streaming and providers.get('streaming'):
            for provider in providers['streaming']:
                # Filter platforms based on config
                should_try_provider = False
                if 'Amazon' in provider and amazon_enabled:
                    should_try_provider = True
                elif 'Apple' in provider and apple_tv_enabled:
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} streaming on {provider}...")
                        deep_link = self.platform_scraper.get_platform_deep_link(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found streaming link for {title} on {provider}")
                            watchmode_streaming.append({'service': provider, 'link': deep_link})
                            # Track statistics
                            if not hasattr(self, 'watchmode_stats'):
                                self.watchmode_stats = {}
                            self.watchmode_stats['platform_scraper_successes'] = self.watchmode_stats.get('platform_scraper_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        print(f"  Error in platform scraper for {title} streaming on {provider}: {e}")
                        # Track statistics
                        if not hasattr(self, 'watchmode_stats'):
                            self.watchmode_stats = {}
                        self.watchmode_stats['platform_scraper_failures'] = self.watchmode_stats.get('platform_scraper_failures', 0) + 1
                else:
                    print(f"  Platform {provider} disabled in config, skipping")

        # Try rent providers (if no Watchmode rent data and not skipped)
        if not skip_rent and not watchmode_rent and providers.get('rent'):
            for provider in providers['rent']:
                # Filter platforms based on config
                should_try_provider = False
                if 'Amazon' in provider and amazon_enabled:
                    should_try_provider = True
                elif 'Apple' in provider and apple_tv_enabled:
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} rent on {provider}...")
                        deep_link = self.platform_scraper.get_platform_deep_link(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found rent link for {title} on {provider}")
                            watchmode_rent.append({'service': provider, 'link': deep_link})
                            # Track statistics
                            if not hasattr(self, 'watchmode_stats'):
                                self.watchmode_stats = {}
                            self.watchmode_stats['platform_scraper_successes'] = self.watchmode_stats.get('platform_scraper_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        print(f"  Error in platform scraper for {title} rent on {provider}: {e}")
                        # Track statistics
                        if not hasattr(self, 'watchmode_stats'):
                            self.watchmode_stats = {}
                        self.watchmode_stats['platform_scraper_failures'] = self.watchmode_stats.get('platform_scraper_failures', 0) + 1
                else:
                    print(f"  Platform {provider} disabled in config, skipping")

        # Try buy providers (if no Watchmode buy data and not skipped)
        if not skip_buy and not watchmode_buy and providers.get('buy'):
            for provider in providers['buy']:
                # Filter platforms based on config
                should_try_provider = False
                if 'Amazon' in provider and amazon_enabled:
                    should_try_provider = True
                elif 'Apple' in provider and apple_tv_enabled:
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} buy on {provider}...")
                        deep_link = self.platform_scraper.get_platform_deep_link(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found buy link for {title} on {provider}")
                            watchmode_buy.append({'service': provider, 'link': deep_link})
                            # Track statistics
                            if not hasattr(self, 'watchmode_stats'):
                                self.watchmode_stats = {}
                            self.watchmode_stats['platform_scraper_successes'] = self.watchmode_stats.get('platform_scraper_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        print(f"  Error in platform scraper for {title} buy on {provider}: {e}")
                        # Track statistics
                        if not hasattr(self, 'watchmode_stats'):
                            self.watchmode_stats = {}
                        self.watchmode_stats['platform_scraper_failures'] = self.watchmode_stats.get('platform_scraper_failures', 0) + 1
                else:
                    print(f"  Platform {provider} disabled in config, skipping")

    def _migrate_legacy_cache_format(self, links):
        """Migrate legacy free/paid cache format to streaming/rent/buy and normalize URLs"""
        if not isinstance(links, dict):
            return links

        # Define search URL patterns that should be normalized to null
        search_url_patterns = [
            'google.com/search',
            'amazon.com/s?',
            'play.google.com/store/search',
            'vudu.com/',
            'microsoft.com/store/search'
        ]

        def normalize_link(link_obj):
            """Normalize a link object, setting search URLs to null while preserving service"""
            if not isinstance(link_obj, dict) or 'service' not in link_obj:
                return link_obj

            link_url = link_obj.get('link')
            if link_url and any(pattern in link_url for pattern in search_url_patterns):
                return {'service': link_obj['service'], 'link': None}
            return link_obj

        # Start with a copy to avoid modifying original
        migrated = {}

        # Remove 'default' key entirely if present
        for key, value in links.items():
            if key == 'default':
                continue  # Skip default key entirely
            migrated[key] = value

        # Convert old 'free/paid' keys to 'streaming/rent'
        if 'free' in migrated:
            migrated['streaming'] = migrated.pop('free')
        if 'paid' in migrated:
            migrated['rent'] = migrated.pop('paid')

        # Normalize all link objects to remove search URLs
        for category in ['streaming', 'rent', 'buy']:
            if category in migrated:
                migrated[category] = normalize_link(migrated[category])

        # Ensure we only return canonical categories
        final_migrated = {}
        for category in ['streaming', 'rent', 'buy']:
            if category in migrated:
                final_migrated[category] = migrated[category]

        return final_migrated if final_migrated else {}

    def save_daily_metrics(self, discovered=0, newly_digital=0):
        """Save daily discovery and availability metrics for 3-day baselining"""
        try:
            # Ensure metrics directory exists
            os.makedirs('metrics', exist_ok=True)

            # Load current tracking database for counts
            total_tracking = 0
            total_available = 0
            if os.path.exists('movie_tracking.json'):
                with open('movie_tracking.json', 'r') as f:
                    db = json.load(f)
                    movies = db.get('movies', {})
                    total_tracking = len([m for m in movies.values() if m.get('status') == 'tracking'])
                    total_available = len([m for m in movies.values() if m.get('status') == 'available'])

            # Create metrics entry
            metrics_entry = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'discovered': discovered,
                'newly_digital': newly_digital,
                'total_tracking': total_tracking,
                'total_available': total_available,
                'timestamp': datetime.now().isoformat()
            }

            # Append to daily metrics log (JSONL format)
            metrics_file = 'metrics/daily.jsonl'
            with open(metrics_file, 'a') as f:
                f.write(json.dumps(metrics_entry) + '\n')

            self.logger.info(f"Daily metrics saved: {discovered} discovered, {newly_digital} newly digital")

        except Exception as e:
            self.logger.error(f"Failed to save daily metrics: {e}")

    def get_3_day_baseline(self):
        """Compute 3-day average for discovery and newly-digital counts"""
        try:
            metrics_file = 'metrics/daily.jsonl'
            if not os.path.exists(metrics_file):
                return None

            # Read last 3 days of metrics
            recent_metrics = []
            with open(metrics_file, 'r') as f:
                for line in f:
                    if line.strip():
                        recent_metrics.append(json.loads(line))

            # Get last 3 entries
            if len(recent_metrics) < 3:
                return {
                    'days_available': len(recent_metrics),
                    'discovery_avg': None,
                    'newly_digital_avg': None,
                    'note': f'Need at least 3 days of data, have {len(recent_metrics)}'
                }

            last_3 = recent_metrics[-3:]
            discovery_avg = sum(m['discovered'] for m in last_3) / 3
            newly_digital_avg = sum(m['newly_digital'] for m in last_3) / 3

            return {
                'days_available': 3,
                'discovery_avg': round(discovery_avg, 1),
                'newly_digital_avg': round(newly_digital_avg, 1),
                'dates': [m['date'] for m in last_3]
            }

        except Exception as e:
            self.logger.error(f"Failed to compute 3-day baseline: {e}")
            return None

    def discover_new_premieres(self, debug=False):
        """Discover new movie premieres and add them to movie_tracking.json

        Args:
            debug: Enable detailed logging of discovery process

        Returns:
            Number of new movies added
        """
        self.discovery_stats['debug_enabled'] = debug

        # Get discovery configuration
        discovery_config = self.config.get('discovery', {})
        days_back = discovery_config.get('days_back', 7)
        max_pages = discovery_config.get('max_pages', 10)

        # Get hybrid discovery flags
        enable_pass_a = discovery_config.get('enable_pass_a', True)  # Digital releases (release_date + type=4)
        enable_pass_b = discovery_config.get('enable_pass_b', True)  # Theatrical releases (primary_release_date)

        if debug:
            self.logger.info(f"Starting discovery: days_back={days_back}, max_pages={max_pages}")
            self.logger.info(f"Discovery passes: A={enable_pass_a}, B={enable_pass_b}")

        # Load existing tracking database
        if os.path.exists('movie_tracking.json'):
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
        else:
            db = {'movies': {}, 'last_update': None}

        existing_ids = set(db['movies'].keys())
        if debug:
            self.logger.info(f"Existing database has {len(existing_ids)} movies")

        # Calculate date range for discovery
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        self.logger.info(f"Discovering new premieres from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        new_movies_added = 0
        all_discovered_movies = {}

        # Pass A: Direct-to-digital releases (release_date + type=4)
        if enable_pass_a:
            if debug:
                self.logger.info("Starting Pass A: Direct-to-digital releases")

            pass_a_count = self._run_discovery_pass(
                'A', 'digital', start_date, end_date, max_pages,
                all_discovered_movies, existing_ids, debug
            )

            if debug:
                self.logger.info(f"Pass A completed: {pass_a_count} movies discovered")

        # Pass B: Theatrical releases (primary_release_date)
        if enable_pass_b:
            if debug:
                self.logger.info("Starting Pass B: Theatrical releases")

            pass_b_count = self._run_discovery_pass(
                'B', 'theatrical', start_date, end_date, max_pages,
                all_discovered_movies, existing_ids, debug
            )

            if debug:
                self.logger.info(f"Pass B completed: {pass_b_count} movies discovered")

        # Merge all discovered movies into database
        for movie_id, movie_data in all_discovered_movies.items():
            if movie_id not in existing_ids:
                db['movies'][movie_id] = movie_data
                new_movies_added += 1
                existing_ids.add(movie_id)

        # Save updated database
        if new_movies_added > 0:
            db['last_update'] = datetime.now().isoformat()
            with open('movie_tracking.json', 'w') as f:
                json.dump(db, f, indent=2)

        # Collect sample titles for metrics
        sample_titles = []
        for movie_data in list(all_discovered_movies.values())[:5]:  # Get up to 5 sample titles
            sample_titles.append(movie_data['title'])

        # Write per-run metrics
        self._write_discovery_metrics(
            days_back, new_movies_added, sample_titles
        )

        # Log discovery summary
        self.logger.info(f"Discovery complete: {new_movies_added} new movies added from {self.discovery_stats['pages_fetched']} pages")
        if debug or new_movies_added == 0:
            self.logger.info(f"Discovery stats: {self.discovery_stats['total_results']} total results, {self.discovery_stats['duplicates_skipped']} duplicates")

        return new_movies_added

    def _write_discovery_metrics(self, window_days, new_movies_added, sample_titles):
        """Write per-run discovery metrics to metrics/daily.jsonl"""
        try:
            # Ensure metrics directory exists
            os.makedirs('metrics', exist_ok=True)

            # Create metrics object
            metrics_object = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'timestamp': datetime.now().isoformat(),
                'window_days': window_days,
                'pages_fetched': self.discovery_stats['pages_fetched'],
                'total_results': self.discovery_stats['total_results'],
                'new_movies_added': new_movies_added,
                'duplicates_skipped': self.discovery_stats['duplicates_skipped'],
                'api_calls': self.discovery_stats['api_calls'],
                'sample_titles': sample_titles[:5]  # Limit to 5 samples
            }

            # Append to daily metrics log (JSONL format)
            metrics_file = 'metrics/daily.jsonl'
            with open(metrics_file, 'a') as f:
                f.write(json.dumps(metrics_object) + '\n')

            self.logger.info(f"Discovery metrics written to {metrics_file}")

        except Exception as e:
            self.logger.error(f"Failed to write discovery metrics: {e}")

    def _run_discovery_pass(self, pass_name, pass_type, start_date, end_date, max_pages, discovered_movies, existing_ids, debug):
        """Run a single discovery pass (A or B)

        Args:
            pass_name: 'A' or 'B' for logging
            pass_type: 'digital' or 'theatrical' to determine API parameters
            start_date: Discovery start date
            end_date: Discovery end date
            max_pages: Maximum pages to fetch
            discovered_movies: Dict to accumulate discovered movies
            existing_ids: Set of existing movie IDs to skip
            debug: Enable debug logging

        Returns:
            Number of new movies discovered in this pass
        """
        pass_new_count = 0

        for page in range(1, max_pages + 1):
            try:
                if debug:
                    self.logger.info(f"Pass {pass_name} - Fetching page {page}/{max_pages}")

                # Use bounded timeout and retry logic
                page_results = self._fetch_tmdb_page_with_retry(
                    page, start_date, end_date, debug, pass_type=pass_type
                )

                if not page_results:
                    if debug:
                        self.logger.warning(f"Pass {pass_name} - No results from page {page}, stopping pass")
                    break

                self.discovery_stats['pages_fetched'] += 1
                self.discovery_stats['total_results'] += len(page_results)

                # Process results from this page
                page_new_count = 0
                page_duplicate_count = 0
                sample_titles = []

                for movie in page_results:
                    movie_id = str(movie['id'])
                    title = movie.get('title', 'Unknown')

                    # Collect sample titles for debugging
                    if len(sample_titles) < 3:
                        sample_titles.append(f"{title} (ID: {movie_id})")

                    # Skip if already in existing database or already discovered in this run
                    if movie_id in existing_ids or movie_id in discovered_movies:
                        page_duplicate_count += 1
                        continue

                    # Add new movie with tracking status
                    digital_date = movie.get('release_date') if pass_type == 'digital' else movie.get('primary_release_date')
                    discovered_movies[movie_id] = {
                        'title': title,
                        'status': 'tracking',
                        'first_seen': datetime.now().strftime('%Y-%m-%d'),
                        'digital_date': digital_date,
                        'providers': {},
                        'discovery_pass': pass_name  # Track which pass found this movie
                    }

                    page_new_count += 1
                    pass_new_count += 1

                self.discovery_stats['new_movies_added'] += page_new_count
                self.discovery_stats['duplicates_skipped'] += page_duplicate_count

                # Log page summary
                if debug:
                    self.logger.info(f"Pass {pass_name} - Page {page}: {len(page_results)} results, {page_new_count} new, {page_duplicate_count} duplicates")
                    if sample_titles:
                        self.logger.info(f"Sample titles: {', '.join(sample_titles)}")

                # Rate limiting
                time.sleep(self.config.get('api', {}).get('tmdb_rate_limit', 0.1))

            except Exception as e:
                self.logger.error(f"Pass {pass_name} - Error processing page {page}: {e}")
                continue

        return pass_new_count

    def _fetch_tmdb_page_with_retry(self, page, start_date, end_date, debug=False, pass_type='digital', max_retries=3):
        """Fetch TMDB discover page with bounded timeout and retry logic"""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # Configure session with retry strategy
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        url = "https://api.themoviedb.org/3/discover/movie"

        # Build parameters based on pass type
        if pass_type == 'digital':
            # Pass A: Direct-to-digital releases
            params = {
                'api_key': self.tmdb_key,
                'release_date.gte': start_date.strftime('%Y-%m-%d'),
                'release_date.lte': end_date.strftime('%Y-%m-%d'),
                'with_release_type': '4',  # Digital only
                'region': 'US',
                'language': 'en-US',
                'include_adult': 'false',
                'sort_by': 'release_date.desc',
                'page': page
            }
        else:  # pass_type == 'theatrical'
            # Pass B: Theatrical releases
            params = {
                'api_key': self.tmdb_key,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'region': 'US',
                'language': 'en-US',
                'include_adult': 'false',
                'sort_by': 'primary_release_date.desc',
                'page': page
            }

        self.discovery_stats['api_calls'] += 1

        # Log exact TMDB params (excluding API key)
        if debug:
            log_params = {k: v for k, v in params.items() if k != 'api_key'}
            self.logger.info(f"TMDB API call (pass_type={pass_type}): {log_params}")

        try:
            # Use bounded timeouts: (connect_timeout, read_timeout)
            response = session.get(url, params=params, timeout=(10, 30))
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            if debug and results:
                self.logger.info(f"TMDB API success: page {page} returned {len(results)} results")

            return results

        except requests.exceptions.Timeout as e:
            self.logger.error(f"TMDB API timeout for page {page}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"TMDB API error for page {page}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching page {page}: {e}")
            return None

    def process_movie(self, movie_id, movie_data, movie_details, force_refresh=False):
        """Process a single movie into display format"""
        if not movie_details:
            return None
        
        title = movie_details['title']
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')
        
        # Extract key people
        credits = movie_details.get('credits', {})
        director = "Unknown"
        cast = []
        
        for crew in credits.get('crew', []):
            if crew['job'] == 'Director':
                director = crew['name']
                break
        
        for actor in credits.get('cast', [])[:2]:  # Top 2 actors
            cast.append(actor['name'])
        
        # Extract additional metadata
        genres = [g['name'] for g in movie_details.get('genres', [])]
        studio = None
        production_companies = movie_details.get('production_companies', [])
        if production_companies:
            studio = production_companies[0]['name']
        
        runtime = movie_details.get('runtime')
        
        # Country from production countries
        country = None
        production_countries = movie_details.get('production_countries', [])
        if production_countries:
            country = production_countries[0]['name']
        
        # Build links object with waterfall approach
        links = {}

        # Wikipedia link
        wiki_url = self.find_wikipedia_url(title, year, imdb_id, movie_id)
        if wiki_url:
            links['wikipedia'] = wiki_url
        
        # Trailer link
        trailer_url = self.find_trailer_url(movie_details)
        if trailer_url:
            links['trailer'] = trailer_url
        
        # RT link and score
        rt_data = self.find_rt_url(title, year, imdb_id)
        rt_score = None
        if rt_data:
            if isinstance(rt_data, dict):
                links['rt'] = rt_data.get('url')
                rt_score = rt_data.get('score')
            else:
                links['rt'] = rt_data

        # Watch links (deep links to streaming platforms)
        watch_links_raw = self.get_watch_links(movie_id, title, year, movie_data.get('providers', {}), force_refresh, tracking_data=movie_data)

        # Simplify provider names in watch links
        watch_links = {}
        for category, link_obj in watch_links_raw.items():
            if isinstance(link_obj, dict) and 'service' in link_obj:
                simplified_service = self.simplify_provider_name(link_obj['service'])
                watch_links[category] = {
                    'service': simplified_service,
                    'link': link_obj.get('link')
                }
            else:
                watch_links[category] = link_obj

        # Build movie dict
        movie_dict = {
            'id': movie_id,
            'title': title,
            'digital_date': movie_data.get('digital_date'),
            'bootstrap_date': movie_data.get('bootstrap_date', False),
            'manually_corrected': movie_data.get('manually_corrected', False),
            'poster': f"https://image.tmdb.org/t/p/w500{movie_details['poster_path']}" if movie_details.get('poster_path') else None,
            'synopsis': movie_details.get('overview', 'No synopsis available.'),
            'crew': {
                'director': director,
                'cast': cast
            },
            'genres': genres,
            'studio': studio,
            'runtime': runtime,
            'year': int(year) if year else None,
            'country': country,
            'rt_score': rt_score,
            'providers': movie_data.get('providers', {}),
            'links': links,
            'watch_links': watch_links
        }

        # Only add review key if a review exists
        review = self.reviews.get(str(movie_id))
        if review:
            movie_dict['review'] = review

        return movie_dict
    
    def generate_display_data(self, days_back=90, incremental=True, force_refresh=False):
        """Generate display data from tracking database

        Args:
            days_back: How many days back to look for available movies
            incremental: If True, only process NEW movies not already in data.json (default)
                        If False, regenerate entire data.json from scratch
        """

        # Load tracking database
        if not os.path.exists('movie_tracking.json'):
            self.logger.error("No tracking database found. Run 'python movie_tracker.py daily' first")
            return

        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)

        # Load existing data.json if incremental mode
        existing_movies = []
        existing_ids = set()
        if incremental and os.path.exists('data.json'):
            with open('data.json', 'r') as f:
                existing_data = json.load(f)
                existing_movies = existing_data.get('movies', [])
                existing_ids = {str(m['id']) for m in existing_movies}
            message = f"Incremental mode: Found {len(existing_movies)} existing movies in data.json"
            self.logger.info(message)
            print(f"📂 {message}")

        # Filter to recently available movies
        cutoff_date = datetime.now() - timedelta(days=days_back)
        new_movies = []

        if incremental:
            print(f"🎬 Processing NEW movies that went digital in last {days_back} days...")
            print(f"   Existing movies in data.json: {len(existing_ids)}")
            print(f"   These will be SKIPPED (use --full to reprocess)")
        else:
            print(f"🎬 Processing ALL movies that went digital in last {days_back} days...")
            print(f"   This will regenerate watch links for all movies")

        skipped_count = 0
        for movie_id, movie_data in db['movies'].items():
            # Skip if already in data.json (incremental mode)
            if incremental and movie_id in existing_ids:
                skipped_count += 1
                continue

            if movie_data['status'] == 'available' and movie_data.get('digital_date'):
                try:
                    digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                    if digital_date >= cutoff_date:
                        # Get full movie details (movie_id is the TMDB ID)
                        movie_details = self.get_movie_details(movie_id)
                        if movie_details:
                            processed = self.process_movie(movie_id, movie_data, movie_details, force_refresh)
                            if processed:
                                new_movies.append(processed)
                                print(f"  ✓ {processed['title']} - Links: {len(processed['links'])}")

                        time.sleep(0.2)  # Rate limiting

                except Exception as e:
                    print(f"  ✗ Error processing {movie_data.get('title')}: {e}")

        if incremental and skipped_count > 0:
            print(f"\n⏭️  Skipped {skipped_count} existing movies (incremental mode)")
            print(f"   To reprocess all movies with agent scraper, run: python3 generate_data.py --full")

        # Merge with existing movies if incremental
        if incremental:
            print(f"\n📋 Adding {len(new_movies)} new movies to {len(existing_movies)} existing movies")
            display_movies = existing_movies + new_movies
        else:
            display_movies = new_movies
        
        # Sort by digital release date (newest first)
        display_movies.sort(key=lambda x: x['digital_date'], reverse=True)
        
        # Apply admin panel overrides (hide/feature movies)
        display_movies = self.apply_admin_overrides(display_movies)
        
        # Save display data
        output_data = {
            'generated_at': datetime.now().isoformat(),
            'count': len(display_movies),
            'movies': display_movies
        }
        
        with open('data.json', 'w') as f:
            json.dump(output_data, f, indent=2)
        
        # Cleanup agent scraper if initialized
        if self.agent_scraper and self.agent_scraper != False:
            try:
                self.agent_scraper.close()
            except Exception as e:
                self.logger.warning(f"Failed to close agent scraper: {e}")

        # Cleanup platform scraper if initialized
        if self.platform_scraper and self.platform_scraper != False:
            try:
                self.platform_scraper.close()
            except Exception as e:
                self.logger.warning(f"Failed to close platform scraper: {e}")

        # Cleanup RT driver if initialized
        if self.rt_driver and self.rt_driver is not False:
            try:
                self.rt_driver.quit()
                self.logger.debug("RT driver closed")
            except Exception as e:
                self.logger.warning(f"Failed to close RT driver: {e}")

        # Save caches
        self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
        self.save_cache(self.rt_cache, 'rt_cache.json')
        
        message = f"Generated data.json with {len(display_movies)} movies"
        self.logger.info(message)
        print(f"✅ {message}")  # Also print to console for visibility
        wiki_count = len([m for m in display_movies if m['links'].get('wikipedia')])
        trailer_count = len([m for m in display_movies if m['links'].get('trailer') and 'watch?v=' in m['links']['trailer']])
        rt_count = len([m for m in display_movies if m['rt_score']])
        reviewed_count = len([m for m in display_movies if m.get('review')])

        self.logger.info(f"Wikipedia links found: {wiki_count}")
        self.logger.info(f"Direct trailers found: {trailer_count}")
        self.logger.info(f"RT scores cached: {rt_count}")
        self.logger.info(f"Movies with reviews: {reviewed_count}")

        print(f"Wikipedia links found: {wiki_count}")
        print(f"Direct trailers found: {trailer_count}")
        print(f"RT scores cached: {rt_count}")
        print(f"Movies with reviews: {reviewed_count}")

        # Wikidata usage statistics
        print(f"\n📊 Wikidata Usage:")
        print(f"  Wikidata attempts: {self.wikipedia_stats['wikidata_attempts']}")
        print(f"  Wikidata successes: {self.wikipedia_stats['wikidata_successes']}")
        if self.wikipedia_stats['wikidata_attempts'] > 0:
            wikidata_success_rate = (self.wikipedia_stats['wikidata_successes'] / self.wikipedia_stats['wikidata_attempts'] * 100)
            print(f"  Wikidata success rate: {wikidata_success_rate:.1f}%")
        print(f"  Wikipedia links recovered via Wikidata: {self.wikipedia_stats['wikidata_successes']}")

        # Watchmode usage statistics
        total_calls = self.watchmode_stats['search_calls'] + self.watchmode_stats['source_calls']
        cache_hit_rate = (self.watchmode_stats['cache_hits'] / (self.watchmode_stats['cache_hits'] + total_calls) * 100) if (self.watchmode_stats['cache_hits'] + total_calls) > 0 else 0
        success_rate = (self.watchmode_stats['watchmode_successes'] / self.watchmode_stats['search_calls'] * 100) if self.watchmode_stats['search_calls'] > 0 else 0

        print(f"\n📊 Watchmode API Usage:")
        print(f"  Search calls: {self.watchmode_stats['search_calls']}")
        print(f"  Source calls: {self.watchmode_stats['source_calls']}")
        print(f"  Cache hits: {self.watchmode_stats['cache_hits']}")
        print(f"  Cache hit rate: {cache_hit_rate:.1f}%")
        print(f"  Watchmode success rate: {success_rate:.1f}%")

        print(f"\n📊 Agent Scraper Usage:")
        print(f"  Agent enabled: {self.config.get('agent_scraper', {}).get('enabled', True)}")
        print(f"  Agent initialized: {self.agent_scraper is not None and self.agent_scraper is not False}")
        print(f"  Agent attempts: {self.watchmode_stats['agent_attempts']}")
        print(f"  Agent successes: {self.watchmode_stats['agent_successes']}")
        print(f"  Agent cache hits: {self.watchmode_stats['agent_cache_hits']}")
        if self.watchmode_stats['agent_attempts'] > 0:
            agent_success_rate = (self.watchmode_stats['agent_successes'] / self.watchmode_stats['agent_attempts'] * 100)
            print(f"  Agent success rate: {agent_success_rate:.1f}%")
        else:
            print(f"  ⚠️  Agent scraper was never called (check if movies have Netflix/Disney+/Hulu providers)")

        print(f"\n📊 Platform Scraper Statistics (Amazon/Apple TV):")
        platform_config = self.config.get('platform_scraper', {})
        print(f"  Platform scraper enabled: {platform_config.get('enabled', True)}")
        print(f"  Platform scraper initialized: {self.platform_scraper is not None and self.platform_scraper is not False}")
        platforms_config = platform_config.get('platforms', {})
        print(f"  Amazon enabled: {platforms_config.get('amazon', True)}")
        print(f"  Apple TV enabled: {platforms_config.get('apple_tv', True)}")

        platform_attempts = self.watchmode_stats.get('platform_scraper_attempts', 0)
        platform_successes = self.watchmode_stats.get('platform_scraper_successes', 0)
        platform_failures = self.watchmode_stats.get('platform_scraper_failures', 0)

        print(f"  Platform scraper attempts: {platform_attempts}")
        print(f"  Platform scraper successes: {platform_successes}")
        print(f"  Platform scraper failures: {platform_failures}")

        if platform_attempts > 0:
            platform_success_rate = (platform_successes / platform_attempts * 100)
            print(f"  Platform scraper success rate: {platform_success_rate:.1f}%")

            # Compare with Watchmode success rate
            if success_rate > 0:
                comparison = "higher" if platform_success_rate > success_rate else "lower"
                print(f"  Success rate vs Watchmode API: {platform_success_rate:.1f}% ({comparison} than {success_rate:.1f}%)")
        else:
            print(f"  ⚠️  Platform scraper was never called (check if movies have Amazon/Apple TV providers)")

        # Show maintenance info
        last_update = platform_config.get('maintenance', {}).get('last_selector_update', 'unknown')
        update_freq = platform_config.get('maintenance', {}).get('expected_update_frequency', 'quarterly')
        print(f"  Last selector update: {last_update}")
        print(f"  Expected update frequency: {update_freq}")

        print(f"\n📊 RT Scraper Usage:")
        print(f"  RT attempts: {self.watchmode_stats['rt_attempts']}")
        print(f"  RT successes: {self.watchmode_stats['rt_successes']}")
        print(f"  RT cache hits: {self.watchmode_stats['rt_cache_hits']}")
        if self.watchmode_stats['rt_attempts'] > 0:
            rt_success_rate = (self.watchmode_stats['rt_successes'] / self.watchmode_stats['rt_attempts'] * 100)
            print(f"  RT success rate: {rt_success_rate:.1f}%")

        print(f"\n📊 Admin Override Usage:")
        print(f"  Manual tracking hits: {self.watchmode_stats.get('manual_tracking_hits', 0)}")
        print(f"  Override hits: {self.watchmode_stats['override_hits']}")
        if self.watchmode_stats['override_hits'] > 0:
            print(f"  Movies with manual overrides: {self.watchmode_stats['override_hits']}")

        print(f"\n🔍 Schema Validation:")
        print(f"  Validation passes: {self.watchmode_stats['schema_validation_passes']}")
        print(f"  Validation warnings: {self.watchmode_stats['schema_validation_warnings']}")
        total_validations = self.watchmode_stats['schema_validation_passes'] + self.watchmode_stats['schema_validation_warnings']
        if total_validations > 0:
            pass_rate = (self.watchmode_stats['schema_validation_passes'] / total_validations * 100)
            print(f"  Validation pass rate: {pass_rate:.1f}%")
            if self.watchmode_stats['schema_validation_warnings'] > total_validations * 0.05:  # Alert if warnings > 5%
                print(f"  ⚠️  WARNING: High validation failure rate ({self.watchmode_stats['schema_validation_warnings']}/{total_validations}) - check for systematic schema issues")

        # Discovery statistics (if discovery was run)
        if self.discovery_stats['api_calls'] > 0:
            print(f"\n🔍 Discovery Statistics:")
            print(f"  API calls: {self.discovery_stats['api_calls']}")
            print(f"  Pages fetched: {self.discovery_stats['pages_fetched']}")
            print(f"  Total results: {self.discovery_stats['total_results']}")
            print(f"  New movies added: {self.discovery_stats['new_movies_added']}")
            print(f"  Duplicates skipped: {self.discovery_stats['duplicates_skipped']}")
            if self.discovery_stats['pages_fetched'] > 0:
                avg_results_per_page = self.discovery_stats['total_results'] / self.discovery_stats['pages_fetched']
                print(f"  Average results per page: {avg_results_per_page:.1f}")
            if self.discovery_stats['debug_enabled']:
                print(f"  Debug mode was enabled for this run")

    def apply_admin_overrides(self, display_movies):
        """Apply admin panel decisions to final output"""
        
        # Load admin decisions if they exist
        hidden = []
        featured = []
        
        if os.path.exists('admin/hidden_movies.json'):
            with open('admin/hidden_movies.json', 'r') as f:
                hidden = json.load(f)
        
        if os.path.exists('admin/featured_movies.json'):
            with open('admin/featured_movies.json', 'r') as f:
                featured = json.load(f)
        
        # Filter out hidden movies
        filtered_movies = [m for m in display_movies 
                          if str(m['id']) not in hidden]
        
        # Mark featured movies
        for movie in filtered_movies:
            if str(movie['id']) in featured:
                movie['featured'] = True
        
        hidden_count = len(display_movies) - len(filtered_movies)
        featured_count = len([m for m in filtered_movies if m.get('featured')])
        
        print(f"📝 Admin overrides applied:")
        print(f"  Hidden movies: {hidden_count}")
        print(f"  Featured movies: {featured_count}")
        
        return filtered_movies

def main():
    parser = argparse.ArgumentParser(description="Generate display data from tracking database with enriched links")
    parser.add_argument('--full', action='store_true', help='Regenerate entire data.json from scratch (default: incremental mode - only process new movies)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging for discovery and agent scraper')
    parser.add_argument('--discover', action='store_true', help='Run discovery to find new premieres before generating data')

    args = parser.parse_args()
    incremental = not args.full
    force_refresh = args.full  # Force refresh cache on full runs

    # Set debug mode globally (could be passed to DataGenerator if needed)
    if args.debug:
        os.environ['AGENT_SCRAPER_DEBUG'] = 'true'
        print("🐛 Debug mode enabled for discovery and agent scraper")

    generator = DataGenerator()

    if args.debug:
        generator.logger.setLevel(logging.DEBUG)
        generator.logger.debug("Debug mode enabled - verbose logging active")

    # Run discovery if requested
    discovered_count = 0
    if args.discover:
        print("🔍 Running discovery for new premieres...")
        discovered_count = generator.discover_new_premieres(debug=args.debug)
        print(f"✅ Discovery complete: {discovered_count} new movies added")

    # Get newly digital count by checking status changes (simplified for now)
    newly_digital_count = 0

    # Save daily metrics if discovery was run
    if args.discover:
        generator.save_daily_metrics(discovered=discovered_count, newly_digital=newly_digital_count)

        # Show 3-day baseline
        baseline = generator.get_3_day_baseline()
        if baseline:
            print(f"\n📈 3-Day Baseline:")
            if baseline['discovery_avg'] is not None:
                print(f"  Discovery average: {baseline['discovery_avg']} movies/day")
                print(f"  Newly digital average: {baseline['newly_digital_avg']} movies/day")
                print(f"  Based on: {', '.join(baseline['dates'])}")
            else:
                print(f"  {baseline['note']}")

    generator.generate_display_data(incremental=incremental, force_refresh=force_refresh)

if __name__ == "__main__":
    main()