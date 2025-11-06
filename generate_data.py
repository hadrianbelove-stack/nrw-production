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
from rt_scraper_playwright import RTScraperPlaywright
from wikipedia_scraper_playwright import WikipediaScraperPlaywright
from constants import PLACEHOLDER_ASINS
try:
    from streaming_platform_scraper import StreamingPlatformScraper
except ImportError:
    StreamingPlatformScraper = None

# Phase 3: Watchmode API with quota management
from watchmode_api import create_watchmode_client


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
        # Get TMDB API key from environment or config.yaml (12-factor app pattern)
        self.tmdb_key = os.environ.get('TMDB_API_KEY')
        if not self.tmdb_key:
            # Fall back to config.yaml for local development
            self.tmdb_key = self.config.get('api', {}).get('tmdb_api_key')

        if not self.tmdb_key:
            self.logger.error(
                "TMDB_API_KEY not found. Please set the TMDB_API_KEY environment variable "
                "or add 'tmdb_api_key' to the 'api' section in config.yaml. "
                "Get a free key from https://www.themoviedb.org/settings/api"
            )
            raise ValueError("TMDB_API_KEY is required")

        # Watchmode API - Get new key from https://api.watchmode.com/ (free tier: 1000 calls/month)
        self.watchmode_key = os.environ.get('WATCHMODE_API_KEY')
        if not self.watchmode_key:
            # Try fallback from config.yaml
            self.watchmode_key = self.config.get('api', {}).get('watchmode_api_key')

        # Phase 3: Initialize Watchmode API with quota management
        self.watchmode_client = create_watchmode_client(self.watchmode_key, quota_limit=1000)
        self.watchmode_enabled = self.watchmode_client is not None

        if not self.watchmode_enabled:
            self.logger.error(
                "WATCHMODE_API_KEY not found or using placeholder value. "
                "Please set the WATCHMODE_API_KEY environment variable or add "
                "'watchmode_api_key' to the 'api' section in config.yaml. "
                "Get a free key from https://api.watchmode.com/"
            )
            self.watchmode_key = None
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
        self.rt_scraper = None  # Lazy initialization for RT scraping with Playwright
        self.wikipedia_scraper = None  # Lazy initialization for Wikipedia scraping with Playwright
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

    def _init_rt_scraper(self):
        """Initialize RT scraper with Playwright (lazy initialization)"""
        if self.rt_scraper is not None:
            return self.rt_scraper is not False

        try:
            self.rt_scraper = RTScraperPlaywright(
                cache_file='rt_cache.json',
                config=self.config,
                logger=self.logger
            )
            self.logger.debug("RT scraper initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize RT scraper: {e}")
            self.rt_scraper = False  # Mark as failed to prevent retries
            return False

    def scrape_rt_score(self, title, year):
        """Public wrapper function to scrape RT score for external consumers

        Args:
            title: Movie title
            year: Release year

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        # Initialize scraper if needed
        if not self._init_rt_scraper():
            return None

        # Check scraper availability
        if self.rt_scraper is False:
            return None

        # Use the new Playwright scraper
        try:
            result = self.rt_scraper.scrape_rt_score(title, year)

            # Update stats from scraper
            scraper_stats = self.rt_scraper.get_stats()
            self.watchmode_stats['rt_attempts'] = scraper_stats['attempts']
            self.watchmode_stats['rt_successes'] = scraper_stats['successes']
            self.watchmode_stats['rt_cache_hits'] = scraper_stats['cache_hits']

            return result
        except Exception as e:
            self.logger.error(f"RT scraping error: {e}")
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
        """Find Wikipedia URL using Playwright-based scraper with waterfall approach

        Priority waterfall:
        1. Overrides (overrides/wikipedia_overrides.json) - Manual curator fixes
        2. Playwright Scraper - Uses cache, Wikidata SPARQL, REST API, and web scraping
        3. Log missing and return None

        Args:
            title: Movie title
            year: Release year
            imdb_id: IMDb ID from TMDB external_ids (e.g., 'tt35076553')
            movie_id: TMDB ID for logging purposes

        Returns:
            Wikipedia URL string or None if not found
        """
        # 1. Check overrides first (manual curator fixes take precedence)
        if imdb_id and imdb_id in self.wikipedia_overrides:
            return f"https://en.wikipedia.org/wiki/{self.wikipedia_overrides[imdb_id]}"

        # 2. Initialize Playwright scraper lazily
        if self.wikipedia_scraper is None:
            self.wikipedia_scraper = WikipediaScraperPlaywright(
                cache_file='wikipedia_cache.json',
                config=self.config,
                logger=self.logger
            )

        # 3. Use Playwright scraper with waterfall approach
        # The scraper internally handles: Cache → Wikidata → REST API → Playwright scraping
        try:
            wiki_url = self.wikipedia_scraper.find_wikipedia_url(
                title=title,
                year=year,
                imdb_id=imdb_id,
                use_api=True,
                use_wikidata=True
            )

            # Update our local cache reference to match scraper's cache
            self.wikipedia_cache = self.wikipedia_scraper.cache

            # Track stats for this attempt
            self.wikipedia_stats['wikidata_attempts'] = self.wikipedia_scraper.stats.get('wikidata_attempts', 0)
            self.wikipedia_stats['wikidata_successes'] = self.wikipedia_scraper.stats.get('wikidata_successes', 0)

            return wiki_url

        except Exception as e:
            print(f"Wikipedia scraper error for {title} ({year}): {e}")
            self.logger.error(f"Wikipedia scraper error for {title} ({year}): {e}")
            return None
    
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

        # 2. Check if RT scraper is enabled
        enabled = self.config.get('rt_scraper', {}).get('enabled', True)
        if not enabled:
            print("  RT scraping disabled via config")
            search_query = quote(f"{title} {year}")
            return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}

        # 3. Use RT scraper (handles caching internally)
        result = self.scrape_rt_score(title, year)
        if result:
            return result

        # 4. Fall back to search
        search_query = quote(f"{title} {year}")
        return {'url': f"https://www.rottentomatoes.com/search?search={search_query}", 'score': None}


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

                # Check for placeholder ASINs in cached links and purge if found
                has_placeholder_asin = False
                detected_asin = None
                for category in ['streaming', 'rent', 'buy']:
                    category_data = cached['links'].get(category, {})
                    if category_data and isinstance(category_data, dict):
                        link = category_data.get('link', '')
                        if link and any(asin in link for asin in PLACEHOLDER_ASINS):
                            detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                            has_placeholder_asin = True
                            break

                if has_placeholder_asin:
                    # Delete the cache entry with placeholder ASIN
                    del self.watch_links_cache[cache_key]
                    self.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                    print(f"  Purged cache entry {cache_key} containing placeholder ASIN {detected_asin}")
                else:
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

        # Services to exclude from the database (niche/low-quality services)
        EXCLUDED_SERVICES = ['fuboTV', 'Philo']


        def is_excluded_service(service_name):
            """Check if a service should be excluded"""
            if not service_name:
                return False
            service_lower = service_name.lower()
            return any(excluded.lower() in service_lower for excluded in EXCLUDED_SERVICES)

        def select_best_service(service_list, priority_list):
            """Select best service from list based on priority, filtering out excluded services"""
            # Filter out excluded services first
            filtered_services = [s for s in service_list if not is_excluded_service(s)]

            if not filtered_services:
                return None

            for priority_service in priority_list:
                for available_service in filtered_services:
                    if priority_service.lower() in available_service.lower():
                        return available_service
            # If no priority match, return first available (from filtered list)
            return filtered_services[0] if filtered_services else None

        # Collect sources from Watchmode API (skip categories that already have overrides)
        watchmode_streaming = []
        watchmode_rent = []
        watchmode_buy = []

        # Skip external API calls for categories that already have overrides
        skip_streaming = 'streaming' in validated_overrides
        skip_rent = 'rent' in validated_overrides
        skip_buy = 'buy' in validated_overrides

        # Phase 3: Quota-aware Watchmode API calls with graceful degradation
        if not self.watchmode_enabled or not self.watchmode_client:
            self.logger.debug(f"Watchmode API disabled, skipping for {title}")
        else:
            try:
                # Use quota-aware API client (automatically checks quota and tracks calls)
                search_results = self.watchmode_client.search_by_tmdb_id(movie_id, title)

                if search_results and search_results.get('title_results'):
                    watchmode_id = search_results['title_results'][0]['id']

                    # Get details with sources (quota-aware)
                    details = self.watchmode_client.get_title_details(watchmode_id, title, movie_id)

                    if details:
                        sources = details.get('sources', [])

                        # Track statistics (maintain backward compatibility)
                        self.watchmode_stats['search_calls'] += 1
                        self.watchmode_stats['source_calls'] += 1

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

                            # Skip excluded services
                            if is_excluded_service(service_name):
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
        # OR when Watchmode returned Google fallback URLs
        # Capture lengths before platform scraper to detect if it added links
        streaming_len_before = len(watchmode_streaming)
        rent_len_before = len(watchmode_rent)
        buy_len_before = len(watchmode_buy)

        # Helper function to check if a list contains Google fallback URLs
        def has_google_fallback(link_list):
            """Check if any links in the list are Google search fallbacks"""
            if not link_list:
                return False
            return any('google.com/search' in item.get('link', '') for item in link_list)

        # Call platform scraper if:
        # 1. No data from Watchmode (original logic), OR
        # 2. Watchmode returned Google fallback URLs (needs real link)
        should_try_platform_scraper = (
            not watchmode_streaming or not watchmode_rent or not watchmode_buy or
            has_google_fallback(watchmode_streaming) or
            has_google_fallback(watchmode_rent) or
            has_google_fallback(watchmode_buy)
        )

        if StreamingPlatformScraper and should_try_platform_scraper:
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
                        # No Amazon link available, leave as null (no Google fallback)
                        watch_links['streaming'] = {
                            'service': service,
                            'link': None
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
                    # Try platform scraper for Amazon/Apple TV before returning null
                    if StreamingPlatformScraper and rent_service in ['Amazon Prime Video', 'Apple TV']:
                        self._try_platform_agent_search(title, year, providers, [], watchmode_rent, [], True, False, True)
                        # Check if platform scraper added rent links
                        if watchmode_rent:
                            best_service = select_best_service([s['service'] for s in watchmode_rent], PAID_PRIORITY)
                            for source in watchmode_rent:
                                if source['service'] == best_service:
                                    watch_links['rent'] = source
                                    break
                        else:
                            # Try agent scraper for supported services
                            agent_result = self._try_agent_scraper(movie_id, title, year, rent_service, 'rent')
                            watch_links['rent'] = agent_result
                    else:
                        # Try agent scraper for supported services
                        agent_result = self._try_agent_scraper(movie_id, title, year, rent_service, 'rent')
                        watch_links['rent'] = agent_result

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
                    # Try platform scraper for Amazon/Apple TV before returning null
                    if StreamingPlatformScraper and buy_service in ['Amazon Prime Video', 'Apple TV']:
                        self._try_platform_agent_search(title, year, providers, [], [], watchmode_buy, True, True, False)
                        # Check if platform scraper added buy links
                        if watchmode_buy:
                            best_service = select_best_service([s['service'] for s in watchmode_buy], PAID_PRIORITY)
                            for source in watchmode_buy:
                                if source['service'] == best_service:
                                    watch_links['buy'] = source
                                    break
                        else:
                            # Try agent scraper for supported services
                            agent_result = self._try_agent_scraper(movie_id, title, year, buy_service, 'buy')
                            watch_links['buy'] = agent_result
                    else:
                        # Try agent scraper for supported services
                        agent_result = self._try_agent_scraper(movie_id, title, year, buy_service, 'buy')
                        watch_links['buy'] = agent_result

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

        # Validate service/link consistency and fix mismatches
        for category in ['streaming', 'rent', 'buy']:
            if category in validated_links and isinstance(validated_links[category], dict):
                link_data = validated_links[category]
                service = link_data.get('service')
                link = link_data.get('link')

                if service and link and not self.validate_service_link_consistency(service, link, title):
                    # Mismatch detected, set to null (no Google fallback)
                    self.logger.warning(f"Replacing mismatched {category} link for {title} with null (admin flag needed)")
                    validated_links[category]['link'] = None

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

    def _enforce_platform_scraper_rate_limit(self):
        """Enforce rate limiting for platform scraper calls"""
        if hasattr(self.platform_scraper, 'rate_limit_seconds') and self.platform_scraper.rate_limit_seconds:
            if not hasattr(self, '_last_platform_scraper_time'):
                self._last_platform_scraper_time = 0

            time_since_last = time.time() - self._last_platform_scraper_time
            if time_since_last < self.platform_scraper.rate_limit_seconds:
                sleep_time = self.platform_scraper.rate_limit_seconds - time_since_last
                print(f"  Rate limiting: sleeping {sleep_time:.1f}s before platform scraper")
                time.sleep(sleep_time)

            self._last_platform_scraper_time = time.time()

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

                # Check for known placeholder ASINs
                if any(asin in link for asin in PLACEHOLDER_ASINS):
                    detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                    self.logger.warning(f"Detected placeholder ASIN {detected_asin} in {category} link for {movie_title}, rejecting")
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
            print(f"  [DEBUG] '{service}' not supported by agent scraper, returning null")
            return {'service': service, 'link': None}

        # Initialize agent scraper if needed
        self._init_agent_scraper()
        print(f"  [DEBUG] Agent scraper state: {type(self.agent_scraper).__name__ if self.agent_scraper else 'None or False'}")
        if self.agent_scraper is False:
            return {'service': service, 'link': None}

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

            # Return found link or null (no Google fallback)
            final_link = result.get('link') or None
            print(f"  [DEBUG] Returning: {{'service': {service}, 'link': {final_link}}}")
            return {'service': service, 'link': final_link}

        except Exception as e:
            print(f"  Error in agent scraper for {title}: {e}")
            return {'service': service, 'link': None}

    def is_actual_amazon_service(self, provider):
        """
        Check if a provider is actual Amazon Prime Video vs Amazon Channel subscription.

        Args:
            provider (str): Provider name from TMDB

        Returns:
            bool: True if genuine Amazon Prime Video, False if Amazon Channel
        """
        if not provider or 'Amazon' not in provider:
            return False

        # Reject Amazon Channel subscriptions
        if 'Channel' in provider or 'Channels' in provider:
            return False

        # Accept genuine Amazon Prime Video services
        genuine_amazon_services = [
            'Amazon Video',
            'Amazon Prime Video',
            'Prime Video',
            'Amazon'
        ]

        return provider in genuine_amazon_services or provider == 'Amazon Video'

    def is_actual_apple_service(self, provider):
        """
        Check if a provider is actual Apple TV vs Apple TV Channel subscription.

        Args:
            provider (str): Provider name from TMDB

        Returns:
            bool: True if genuine Apple TV, False if Apple TV Channel
        """
        if not provider or 'Apple' not in provider:
            return False

        # Reject Apple TV Channel subscriptions
        if 'Channel' in provider or 'Channels' in provider:
            return False

        # Accept genuine Apple TV services
        genuine_apple_services = [
            'Apple TV',
            'Apple iTunes',
            'iTunes',
            'Apple TV Plus'
        ]

        return provider in genuine_apple_services

    def validate_service_link_consistency(self, service, link, title):
        """
        Validate that a service name matches its link domain.

        Args:
            service (str): Service name
            link (str): Watch link URL
            title (str): Movie title for logging

        Returns:
            bool: True if service and link are consistent, False if mismatch
        """
        if not service or not link:
            return True  # Nothing to validate

        # Define expected domains for each service
        service_domains = {
            'Max': ['max.com', 'hbomax.com'],
            'HBO Max': ['max.com', 'hbomax.com'],
            'Netflix': ['netflix.com'],
            'Disney Plus': ['disneyplus.com'],
            'Disney+': ['disneyplus.com'],
            'Hulu': ['hulu.com'],
            'Amazon Prime Video': ['amazon.com'],
            'Amazon Video': ['amazon.com'],
            'Prime Video': ['amazon.com'],
            'Amazon': ['amazon.com'],
            'Apple TV': ['tv.apple.com', 'itunes.apple.com'],
            'Apple iTunes': ['tv.apple.com', 'itunes.apple.com'],
            'iTunes': ['tv.apple.com', 'itunes.apple.com'],
            'Paramount Plus': ['paramountplus.com'],
            'Peacock': ['peacocktv.com'],
            'Crunchyroll': ['crunchyroll.com'],
            'Funimation': ['funimation.com']
        }

        expected_domains = service_domains.get(service, [])
        if not expected_domains:
            # Unknown service, can't validate
            return True

        # Check if link contains any expected domain
        for domain in expected_domains:
            if domain in link.lower():
                return True

        # Check if it's a Google search fallback (always valid)
        if 'google.com/search' in link.lower():
            return True

        # Mismatch detected
        self.logger.warning(f"Service/link mismatch for {title}: service='{service}' but link='{link}'")
        return False

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
                max_retries = platform_config.get('max_retries', 3)
                self.platform_scraper = StreamingPlatformScraper(
                    headless=headless_mode,
                    timeout_seconds=timeout_seconds,
                    rate_limit_seconds=rate_limit_seconds,
                    max_retries=max_retries
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

        # Helper to check if links are Google fallbacks
        def has_google_fallback(link_list):
            if not link_list:
                return False
            return any('google.com/search' in item.get('link', '') for item in link_list)

        # Try streaming providers (if no Watchmode streaming data OR Google fallback, and not skipped)
        if not skip_streaming and (not watchmode_streaming or has_google_fallback(watchmode_streaming)) and providers.get('streaming'):
            for provider in providers['streaming']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} streaming on {provider}...")
                        self._enforce_platform_scraper_rate_limit()
                        deep_link = self.platform_scraper.get_platform_deep_link(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found streaming link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            watchmode_streaming[:] = [s for s in watchmode_streaming if 'google.com/search' not in s.get('link', '')]
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

        # Try rent providers (if no Watchmode rent data OR Google fallback, and not skipped)
        if not skip_rent and (not watchmode_rent or has_google_fallback(watchmode_rent)) and providers.get('rent'):
            for provider in providers['rent']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} rent on {provider}...")
                        self._enforce_platform_scraper_rate_limit()
                        deep_link = self.platform_scraper.get_platform_deep_link(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found rent link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            watchmode_rent[:] = [s for s in watchmode_rent if 'google.com/search' not in s.get('link', '')]
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

        # Try buy providers (if no Watchmode buy data OR Google fallback, and not skipped)
        if not skip_buy and (not watchmode_buy or has_google_fallback(watchmode_buy)) and providers.get('buy'):
            for provider in providers['buy']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} buy on {provider}...")
                        self._enforce_platform_scraper_rate_limit()
                        deep_link = self.platform_scraper.get_platform_deep_link(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found buy link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            watchmode_buy[:] = [s for s in watchmode_buy if 'google.com/search' not in s.get('link', '')]
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

        # Get discovery configuration with CI optimizations
        discovery_config = self.config.get('discovery', {})

        # Use CI-optimized values if running in CI environment
        if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
            days_back = int(os.getenv('CI_DISCOVERY_DAYS', discovery_config.get('ci_days_back', 7)))
            max_pages = int(os.getenv('CI_DISCOVERY_PAGES', discovery_config.get('ci_max_pages', 10)))
        else:
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

    def check_tracking_movies(self, max_to_check=None, priority_days=180):
        """Check tracking movies for provider availability (monitoring component)

        Checks movies in 'tracking' status to see if they have gotten digital releases
        by querying TMDB watch/providers API. Updates status to 'available' when providers found.

        Args:
            max_to_check: Maximum number of movies to check (None = all)
            priority_days: Prioritize movies released within this many days (default 180)

        Returns:
            int: Number of newly digital movies found
        """
        import random
        import requests

        # Load tracking database
        if not os.path.exists('movie_tracking.json'):
            print("⚠️  No movie_tracking.json found")
            return 0

        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)

        # Get all tracking movies with their IDs
        tracking_movies = [(movie_id, movie) for movie_id, movie in db['movies'].items()
                          if movie['status'] == 'tracking']

        print(f"🔍 Found {len(tracking_movies)} movies in tracking status")

        if not tracking_movies:
            return 0

        # Sort by premiere_date/digital_date (most recent first) for smart prioritization
        def get_sort_key(item):
            movie_id, movie = item
            date_str = movie.get('digital_date') or movie.get('premiere_date')
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
            return datetime.min  # Put movies with no date at the end

        tracking_movies.sort(key=get_sort_key, reverse=True)

        # Apply priority window if specified
        if priority_days:
            cutoff_date = datetime.now() - timedelta(days=priority_days)
            priority_movies = []
            older_movies = []

            for movie_id, movie in tracking_movies:
                date_str = movie.get('digital_date') or movie.get('premiere_date')
                if date_str:
                    try:
                        date_dt = datetime.strptime(date_str, '%Y-%m-%d')
                        if date_dt >= cutoff_date:
                            priority_movies.append((movie_id, movie))
                        else:
                            older_movies.append((movie_id, movie))
                    except:
                        older_movies.append((movie_id, movie))
                else:
                    older_movies.append((movie_id, movie))

            # Check priority movies first, then older ones
            tracking_movies = priority_movies + older_movies
            print(f"  Priority queue (last {priority_days} days): {len(priority_movies)} movies")
            print(f"  Older movies: {len(older_movies)} movies")

        # Limit if max_to_check specified
        if max_to_check:
            tracking_movies = tracking_movies[:max_to_check]
            print(f"  Limiting check to first {len(tracking_movies)} movies")

        newly_digital = 0
        checked = 0
        failed = 0
        total_to_check = len(tracking_movies)

        print(f"\n🎬 Checking {total_to_check} movies for digital availability...\n")

        try:
            for movie_id, movie in tracking_movies:
                checked += 1

                # Progress indicator every 50 movies
                if checked % 50 == 0 or checked == total_to_check:
                    progress_pct = (checked / total_to_check) * 100
                    print(f"  Progress: {checked}/{total_to_check} ({progress_pct:.1f}%) - Found {newly_digital} newly digital, {failed} failed")

                # Check providers with retry logic
                url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
                params = {'api_key': self.tmdb_key}

                data = None
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = requests.get(url, params=params, timeout=(5, 15))
                        if response.status_code == 200:
                            data = response.json()
                            break
                        elif response.status_code == 429:  # Rate limited
                            wait_time = (2 ** attempt) + random.uniform(0, 1)
                            print(f"  Rate limited on {movie['title']}, waiting {wait_time:.1f}s")
                            time.sleep(wait_time)
                            continue
                        else:
                            self.logger.warning(f"HTTP {response.status_code} for {movie['title']}")
                            break
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        if attempt < max_retries - 1:
                            print(f"  Timeout/connection error for {movie['title']}, retrying in {wait_time:.1f}s")
                            time.sleep(wait_time)
                            continue
                        else:
                            self.logger.warning(f"Failed after {max_retries} attempts for {movie['title']}: {type(e).__name__}")
                            failed += 1
                            break
                    except requests.exceptions.RequestException as e:
                        self.logger.warning(f"Request error for {movie['title']}: {type(e).__name__}")
                        failed += 1
                        break

                if data:
                    us = data.get('results', {}).get('US', {})

                    # Get all provider types
                    rent_providers = us.get('rent', [])
                    buy_providers = us.get('buy', [])
                    stream_providers = us.get('flatrate', [])

                    # Extract provider names (defined in get_watch_links for consistency)
                    EXCLUDED_SERVICES = ['fuboTV', 'Philo']

                    def is_excluded_service(service_name):
                        """Check if a service should be excluded"""
                        if not service_name:
                            return False
                        service_lower = service_name.lower()
                        return any(excluded.lower() in service_lower for excluded in EXCLUDED_SERVICES)

                    rent_names = [p.get('provider_name', '') for p in rent_providers if not is_excluded_service(p.get('provider_name', ''))]
                    buy_names = [p.get('provider_name', '') for p in buy_providers if not is_excluded_service(p.get('provider_name', ''))]
                    stream_names = [p.get('provider_name', '') for p in stream_providers if not is_excluded_service(p.get('provider_name', ''))]

                    # Check if ANY providers exist (after filtering out excluded services)
                    has_providers = bool(rent_names or buy_names or stream_names)

                    if has_providers and movie['status'] == 'tracking':
                        movie['status'] = 'available'
                        movie['digital_date'] = datetime.now().strftime('%Y-%m-%d')
                        movie['providers'] = {
                            'rent': rent_names,
                            'buy': buy_names,
                            'streaming': stream_names
                        }
                        # Mark for enrichment (Phase 2.1 optimization)
                        movie['enriched'] = False
                        movie['enrichment_date'] = None

                        newly_digital += 1
                        # Show which service it appeared on
                        first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0]
                        print(f"  ✓ {movie['title']} now on {first_service}!")

                # Incremental save every 100 movies
                if checked % 100 == 0:
                    with open('movie_tracking.json', 'w') as f:
                        json.dump(db, f, indent=2)
                    print(f"  💾 Progress saved (batch {checked//100})")

                # Rate limiting
                time.sleep(0.2)

        except Exception as e:
            self.logger.error(f"Unexpected error during provider checking: {e}")
            print(f"\n⚠️  Unexpected error during provider checking: {e}")
            print(f"  Processed {checked}/{total_to_check} movies before error")
        finally:
            # Always save database before exiting
            try:
                with open('movie_tracking.json', 'w') as f:
                    json.dump(db, f, indent=2)
                print(f"  💾 Final database save completed")
            except Exception as save_error:
                self.logger.error(f"Failed to save database: {save_error}")
                print(f"  ❌ Failed to save database: {save_error}")

        print(f"\n✅ Provider check complete: Found {newly_digital} newly digital movies out of {checked} checked ({failed} failed)")
        self.logger.info(f"Provider check complete: {newly_digital} newly digital, {checked} checked, {failed} failed")

        return newly_digital

    def validate_enrichment_consistency(self):
        """Validate enrichment consistency to prevent data/flag mismatches

        Checks for movies marked enriched: true but missing watch_links data.
        Resets enriched flag to false for inconsistent movies.

        Returns:
            int: Number of inconsistencies found and corrected
        """
        try:
            # Load movie tracking database
            if not os.path.exists('movie_tracking.json'):
                self.logger.info("No movie_tracking.json found, skipping enrichment validation")
                return 0

            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)

            inconsistencies_found = 0
            total_available = 0

            for movie_id, movie in db.get('movies', {}).items():
                if movie.get('status') == 'available':
                    total_available += 1

                    # Check if marked as enriched but missing watch_links
                    if movie.get('enriched', False):
                        # Load corresponding data.json to check for watch_links
                        data_file = 'data.json'
                        if os.path.exists(data_file):
                            try:
                                # Validate schema before loading
                                if not self.validate_data_json_schema(data_file):
                                    self.logger.warning(f"data.json schema validation failed during enrichment check for movie {movie.get('title', 'Unknown')}")
                                    continue

                                with open(data_file, 'r') as df:
                                    data_movies = json.load(df).get('movies', [])

                                # Find corresponding movie in data.json
                                data_movie = None
                                for dm in data_movies:
                                    if str(dm.get('id')) == str(movie_id):
                                        data_movie = dm
                                        break

                                if data_movie:
                                    watch_links = data_movie.get('watch_links')

                                    # Check if watch_links is missing, empty, or contains placeholder ASIN
                                    has_placeholder_asin = False
                                    detected_asin = None
                                    placeholder_asins = ['B0FMPYFP9W', 'B0FNDR5BW5']

                                    if watch_links and isinstance(watch_links, dict):
                                        # Check for placeholder ASINs in any category
                                        for category in ['streaming', 'rent', 'buy']:
                                            category_data = watch_links.get(category, {})
                                            if category_data and isinstance(category_data, dict):
                                                link = category_data.get('link', '')
                                                if link:
                                                    for asin in placeholder_asins:
                                                        if asin in link:
                                                            has_placeholder_asin = True
                                                            detected_asin = asin
                                                            break
                                            if has_placeholder_asin:
                                                break

                                    if not watch_links or (isinstance(watch_links, dict) and not any(watch_links.values())) or has_placeholder_asin:
                                        # Inconsistency found: enriched=true but no/bad watch_links
                                        reason = "no watch_links" if not watch_links else "empty watch_links" if not any(watch_links.values()) else f"placeholder ASIN {detected_asin}"
                                        self.logger.warning(f"Enrichment inconsistency: {movie.get('title', 'Unknown')} (ID: {movie_id}) marked enriched=true but has {reason}")
                                        movie['enriched'] = False
                                        # Remove enrichment_date if present
                                        if 'enrichment_date' in movie:
                                            del movie['enrichment_date']
                                        inconsistencies_found += 1

                            except Exception as e:
                                self.logger.warning(f"Error checking data.json for movie {movie.get('title', 'Unknown')}: {e}")

            # Save corrected database if any inconsistencies were found
            if inconsistencies_found > 0:
                with open('movie_tracking.json', 'w') as f:
                    json.dump(db, f, indent=2)
                self.logger.info(f"Corrected {inconsistencies_found} enrichment inconsistencies in movie_tracking.json")

            # Log summary
            consistent_count = total_available - inconsistencies_found
            self.logger.info(f"Enrichment consistency: {consistent_count}/{total_available} valid, {inconsistencies_found} corrected")
            print(f"  🔍 Enrichment consistency: {consistent_count}/{total_available} valid, {inconsistencies_found} corrected")

            return inconsistencies_found

        except Exception as e:
            self.logger.error(f"Error during enrichment consistency validation: {e}")
            print(f"  ❌ Error during enrichment consistency validation: {e}")
            return 0

    def validate_data_json_schema(self, file_path='data.json'):
        """Validate data.json structure before loading

        Checks that:
        - Root object has required keys: generated_at, count, movies
        - Movies is a list of dicts (not strings)
        - Each movie has required keys: id, title, digital_date

        Args:
            file_path (str): Path to data.json file

        Returns:
            bool: True if valid, False if invalid
        """
        try:
            if not os.path.exists(file_path):
                return True  # Valid if file doesn't exist (will be created)

            with open(file_path, 'r') as f:
                data = json.load(f)

            # Check root structure
            if not isinstance(data, dict):
                self.logger.error(f"{file_path} root is not a dict: {type(data)}")
                return False

            # Check required root keys
            required_root_keys = ['generated_at', 'count', 'movies']
            for key in required_root_keys:
                if key not in data:
                    self.logger.error(f"{file_path} missing required key: {key}")
                    return False

            # Check data types
            if not isinstance(data['generated_at'], str):
                self.logger.error(f"{file_path} generated_at must be string, got {type(data['generated_at'])}")
                return False

            if not isinstance(data['count'], int):
                self.logger.error(f"{file_path} count must be int, got {type(data['count'])}")
                return False

            if not isinstance(data['movies'], list):
                self.logger.error(f"{file_path} movies must be list, got {type(data['movies'])}")
                return False

            # Check movies array structure
            movies = data['movies']
            for i, movie in enumerate(movies):
                if not isinstance(movie, dict):
                    self.logger.error(f"{file_path} movie[{i}] is not a dict: {type(movie)}")
                    return False

                # Check required movie keys (digital_date is optional)
                required_movie_keys = ['id', 'title']
                for key in required_movie_keys:
                    if key not in movie:
                        self.logger.error(f"{file_path} movie[{i}] missing required key: {key}")
                        return False

            self.logger.info(f"{file_path} schema validation passed: {len(movies)} movies")
            return True

        except json.JSONDecodeError as e:
            self.logger.error(f"{file_path} is not valid JSON: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error validating {file_path} schema: {e}")
            return False

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

        # Load existing data.json for merging later
        existing_movies = []
        existing_ids = set()
        if os.path.exists('data.json'):
            # Validate schema before loading
            if self.validate_data_json_schema('data.json'):
                with open('data.json', 'r') as f:
                    existing_data = json.load(f)
                    existing_movies = existing_data.get('movies', [])
                    existing_ids = {str(m['id']) for m in existing_movies}
                message = f"Found {len(existing_movies)} existing movies in data.json"
                self.logger.info(message)
                print(f"📂 {message}")
            else:
                self.logger.error("data.json schema validation failed - treating as corrupted, will rebuild from scratch")
                print(f"❌ data.json schema validation failed - treating as corrupted, will rebuild from scratch")
                # Backup corrupted file
                backup_path = f"data.json.corrupted.validation.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.rename('data.json', backup_path)
                self.logger.info(f"Corrupted data.json backed up to {backup_path}")
                print(f"💾 Corrupted data.json backed up to {backup_path}")

        # Validate enrichment consistency before categorization
        print(f"\n🔍 Validating enrichment consistency...")
        self.validate_enrichment_consistency()

        # Filter to recently available movies
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Build lookup of existing movies by ID for watch_links validation
        existing_movies_lookup = {str(m['id']): m for m in existing_movies}

        # Separate movies by enrichment status (Phase 2.1 optimization)
        needs_enrichment = []
        already_enriched = []
        stale_enrichment = []

        for movie_id, movie_data in db['movies'].items():
            if movie_data['status'] == 'available' and movie_data.get('digital_date'):
                try:
                    digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                    if digital_date >= cutoff_date:
                        # Check enrichment status
                        is_enriched = movie_data.get('enriched', False)
                        enrichment_date = movie_data.get('enrichment_date')

                        # Check if enrichment is stale (> 90 days old)
                        is_stale = False
                        if is_enriched and enrichment_date:
                            try:
                                enrich_dt = datetime.fromisoformat(enrichment_date)
                                age_days = (datetime.now() - enrich_dt).days
                                is_stale = age_days > 90
                            except:
                                pass

                        if not is_enriched:
                            needs_enrichment.append((movie_id, movie_data))
                        elif is_stale:
                            stale_enrichment.append((movie_id, movie_data))
                        else:
                            # Before classifying as already_enriched, validate watch_links for placeholders
                            existing_movie = existing_movies_lookup.get(movie_id)
                            has_valid_links = True

                            if existing_movie and 'watch_links' in existing_movie:
                                validated_links = self.validate_watch_links_schema(
                                    existing_movie['watch_links'],
                                    movie_data.get('title', 'Unknown')
                                )
                                # If validation removes all categories or results in empty dict,
                                # don't classify as already_enriched
                                if not validated_links:
                                    has_valid_links = False

                            if has_valid_links:
                                already_enriched.append((movie_id, movie_data))
                            else:
                                # Movie has placeholder ASINs or invalid links, needs re-enrichment
                                needs_enrichment.append((movie_id, movie_data))

                except Exception as e:
                    self.logger.warning(f"Error parsing date for {movie_data.get('title')}: {e}")

        # Phase 2.1 Optimization Report
        total_available = len(needs_enrichment) + len(already_enriched) + len(stale_enrichment)
        print(f"\n📊 Phase 2.1 Enrichment Optimization:")
        print(f"   Total available movies (last {days_back} days): {total_available}")
        print(f"   ✅ Already enriched (cached): {len(already_enriched)}")
        print(f"   🆕 Need enrichment: {len(needs_enrichment)}")
        print(f"   ⏰ Stale (>90 days, will re-enrich): {len(stale_enrichment)}")

        if incremental:
            # Re-enrich stale movies in batches (max 10 per run to avoid quota issues)
            stale_to_process = stale_enrichment[:10]
            if stale_to_process:
                print(f"   📝 Re-enriching {len(stale_to_process)} stale movies (batch of 10)")
            needs_enrichment.extend(stale_to_process)
        else:
            # Full mode: re-enrich everything
            print(f"   🔄 FULL MODE: Re-enriching ALL movies")
            needs_enrichment.extend(already_enriched)
            needs_enrichment.extend(stale_enrichment)

        print(f"\n🎬 Processing {len(needs_enrichment)} movies (enrichment phase)...")
        print(f"   API savings: {len(already_enriched)} movies skipped (95% cost reduction)")

        # Process only movies that need enrichment
        new_movies = []
        enriched_count = 0

        for movie_id, movie_data in needs_enrichment:
            try:
                # Get full movie details (movie_id is the TMDB ID)
                movie_details = self.get_movie_details(movie_id)
                if movie_details:
                    processed = self.process_movie(movie_id, movie_data, movie_details, force_refresh)
                    if processed:
                        new_movies.append(processed)
                        print(f"  ✓ {processed['title']} - Links: {len(processed['links'])}")

                        # Mark as enriched in tracking database
                        movie_data['enriched'] = True
                        movie_data['enrichment_date'] = datetime.now().isoformat()
                        enriched_count += 1

                time.sleep(0.2)  # Rate limiting

            except Exception as e:
                print(f"  ✗ Error processing {movie_data.get('title')}: {e}")

        # Save updated tracking database with enrichment flags
        with open('movie_tracking.json', 'w') as f:
            json.dump(db, f, indent=2)
        print(f"\n💾 Enrichment tracking saved: {enriched_count} movies marked as enriched")

        # Merge with existing movies that are already enriched
        if incremental and already_enriched:
            # Get cached data from existing data.json
            already_enriched_ids = {movie_id for movie_id, _ in already_enriched}
            raw_cached_movies = [m for m in existing_movies if str(m['id']) in already_enriched_ids]

            # Validate and clean cached movies' watch_links
            cached_movies = []
            for movie in raw_cached_movies:
                if 'watch_links' in movie:
                    validated_links = self.validate_watch_links_schema(
                        movie['watch_links'],
                        movie.get('title', 'Unknown')
                    )
                    # Replace watch_links with validated result
                    movie_copy = movie.copy()
                    movie_copy['watch_links'] = validated_links

                    # Only include movie if it has valid links after validation
                    if validated_links:
                        cached_movies.append(movie_copy)
                    # If validated result is empty, drop the movie (it will be re-enriched in next run)
                else:
                    # Movie without watch_links, include as-is
                    cached_movies.append(movie)

            print(f"\n📋 Using {len(cached_movies)} cached movies + {len(new_movies)} newly enriched = {len(cached_movies) + len(new_movies)} total")
            display_movies = cached_movies + new_movies
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

        # Cleanup RT scraper if initialized
        if self.rt_scraper and self.rt_scraper is not False:
            try:
                self.rt_scraper.close()
                self.logger.debug("RT scraper closed")
            except Exception as e:
                self.logger.warning(f"Failed to close RT scraper: {e}")

        # Save caches (RT cache is managed by rt_scraper)
        self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
        
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

        # Phase 3: Print Watchmode quota report
        if self.watchmode_client:
            self.watchmode_client.print_quota_report()

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
    parser.add_argument('--check', action='store_true', help='Check tracking movies for digital availability (provider monitoring)')

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

    # Check tracking movies for digital availability if requested
    newly_digital_count = 0
    if args.check:
        print("\n🔍 Checking tracking movies for digital availability...")
        newly_digital_count = generator.check_tracking_movies()

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