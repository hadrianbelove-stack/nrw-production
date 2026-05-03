#!/usr/bin/env python3
"""
Metacritic Scraper — API-based scraper for Metacritic movie scores.

Uses the Metacritic backend search API (same endpoint that powers their website search).
No browser required — pure HTTP requests with structured JSON responses.

API endpoint: https://backend.metacritic.com/finder/metacritic/search/{query}/web
Returns: title, slug, premiereYear, criticScoreSummary.score

Score format: Integer 0-100 (stored as string, e.g. "75")
"""

import json
import re
import time
from datetime import datetime

import requests


class MetacriticScraper:
    """Finds Metacritic scores via the backend search API."""

    API_BASE = 'https://backend.metacritic.com/finder/metacritic/search'
    API_KEY = '1MOZgmNFxvmljaQR1X9KAij9Mo4xAY3u'
    MC_URL_BASE = 'https://www.metacritic.com/movie/'

    def __init__(self, cache_file='cache/metacritic_cache.json', config=None, logger=None):
        self.cache_file = cache_file
        self.config = config or {}
        self.logger = logger
        self.cache = self._load_cache()
        self.stats = {'attempts': 0, 'successes': 0, 'failures': 0, 'cache_hits': 0}
        self.last_request_time = 0

        # Config
        mc_config = self.config.get('metacritic_scraper', {})
        self.rate_limit = mc_config.get('rate_limit', 0.5)
        self.timeout = mc_config.get('timeout', 10)
        self.cache_ttl_days = mc_config.get('cache_ttl_days', 90)
        self.enabled = mc_config.get('enabled', True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.metacritic.com/',
            'Origin': 'https://www.metacritic.com',
        }

    def scrape_metacritic_score(self, title, year):
        """Public interface: find Metacritic page and score for a movie.

        Args:
            title: Movie title
            year: Release year (int)

        Returns:
            dict: {'url': str, 'score': str or None} or None if not found
        """
        cache_key = f"{title}_{year}"

        # Cache check (with TTL enforcement for "not found" entries)
        cached = self.cache.get(cache_key)
        if cached:
            # Expired "not found" entries get re-checked
            if not cached.get('url') and self._is_cache_expired(cached):
                del self.cache[cache_key]
            else:
                self.stats['cache_hits'] += 1
                if cached.get('url'):
                    return {'url': cached['url'], 'score': cached.get('score')}
                return None

        if not self.enabled:
            return None

        self._enforce_rate_limit()
        self.stats['attempts'] += 1

        # Search the API
        result = self._search_api(title, year)

        # Cache and return
        if result and result.get('url'):
            self.cache[cache_key] = {
                'url': result['url'],
                'score': result.get('score'),
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self._save_cache()
            self.stats['successes'] += 1
            return result
        else:
            self.cache[cache_key] = {
                'url': None,
                'score': None,
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self._save_cache()
            self.stats['failures'] += 1
            return None

    def _search_api(self, title, year):
        """Search Metacritic's backend API for the movie.

        Returns:
            dict with url and score, or None if not found
        """
        try:
            url = f"{self.API_BASE}/{title}/web"
            params = {
                'apiKey': self.API_KEY,
                'limit': 15,
                'offset': 0,
            }

            resp = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            if resp.status_code != 200:
                self._log(f"API returned {resp.status_code} for '{title}'", level='warning')
                return None

            data = resp.json()
            items = data.get('data', {}).get('items', [])

            if not items:
                self._log(f"No results for '{title}'", level='debug')
                return None

            # Pass 1: Exact year + title match (movies only)
            for item in items:
                if item.get('type') != 'movie':
                    continue
                if item.get('premiereYear') == year and self._title_match(title, item.get('title', '')):
                    return self._build_result(item)

            # Pass 2: +-1 year + title match
            for item in items:
                if item.get('type') != 'movie':
                    continue
                item_year = item.get('premiereYear', 0)
                if item_year and abs(item_year - year) <= 1 and self._title_match(title, item.get('title', '')):
                    return self._build_result(item)

            self._log(f"No title+year match for '{title}' ({year})", level='debug')
            return None

        except requests.exceptions.Timeout:
            self._log(f"API timeout for '{title}'", level='warning')
            return None
        except Exception as e:
            self._log(f"API error for '{title}': {e}", level='error')
            return None

    def _build_result(self, item):
        """Build result dict from API item."""
        slug = item.get('slug', '')
        score_val = item.get('criticScoreSummary', {}).get('score')
        score = str(score_val) if score_val is not None else None
        mc_url = f"{self.MC_URL_BASE}{slug}/"
        return {'url': mc_url, 'score': score}

    def _title_match(self, search_title, api_title):
        """Check if titles match (normalized, article-stripped).

        Handles:
        - Case differences
        - Leading articles (The, A, An)
        - Punctuation differences
        - Minor subtitle variations
        """
        n1 = self._normalize(search_title)
        n2 = self._normalize(api_title)
        if not n1 or not n2:
            return False

        # Exact match after normalization
        if n1 == n2:
            return True

        # One contains the other with high overlap (handles subtitle differences)
        if len(n1) > 4 and len(n2) > 4:
            if n1 in n2 and len(n1) >= len(n2) * 0.85:
                return True
            if n2 in n1 and len(n2) >= len(n1) * 0.85:
                return True

        return False

    def _normalize(self, s):
        """Normalize title for comparison."""
        s = s.lower().strip()
        # Strip leading articles
        s = re.sub(r'^(the|a|an)\s+', '', s)
        # Remove all non-alphanumeric
        s = re.sub(r'[^a-z0-9]', '', s)
        return s

    def _enforce_rate_limit(self):
        """Enforce minimum delay between API requests."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _load_cache(self):
        """Load cache from disk."""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_cache(self):
        """Save cache to disk."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            self._log(f"Failed to save cache: {e}", level='error')

    def _log(self, message, level='info'):
        """Log a message."""
        if self.logger:
            getattr(self.logger, level, self.logger.info)(f"[MetacriticScraper] {message}")

    def get_stats(self):
        """Return scraper stats."""
        return dict(self.stats)

    def _is_cache_expired(self, entry):
        """Check if a cache entry has exceeded its TTL."""
        scraped_at = entry.get('scraped_at')
        if not scraped_at:
            return True
        try:
            scraped_date = datetime.fromisoformat(scraped_at)
            age_days = (datetime.now() - scraped_date).days
            return age_days > self.cache_ttl_days
        except (ValueError, TypeError):
            return True

    def clear_stale_cache(self):
        """Remove expired 'not found' entries so they get re-checked.

        Only clears entries where url=None AND older than cache_ttl_days.
        Entries with valid URLs are kept (scores don't change often).

        Returns:
            int: Number of entries cleared
        """
        cleared = 0
        keys_to_remove = []
        for key, entry in self.cache.items():
            if not entry.get('url') and self._is_cache_expired(entry):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.cache[key]
            cleared += 1

        if cleared:
            self._save_cache()
            self._log(f"Cleared {cleared} stale 'not found' cache entries", level='info')
        return cleared

    def clear_cache_entry(self, title, year):
        """Remove a specific entry from cache (for re-scraping)."""
        cache_key = f"{title}_{year}"
        if cache_key in self.cache:
            del self.cache[cache_key]
            self._save_cache()

    def close(self):
        """No-op for API-based scraper (no browser to close)."""
        pass
