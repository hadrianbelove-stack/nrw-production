#!/usr/bin/env python3
"""
LetterboxdScoreScraper — HTTP-based scraper for Letterboxd average ratings.

STAR RATINGS ONLY — this module does not touch reviews or quotes. For
Letterboxd pull quotes see gemini_scraper/letterboxd_quotes.py
(LetterboxdQuoteScraper).

Fetches the film page HTML and extracts the aggregateRating from JSON-LD
structured data. No browser required — pure HTTP requests.

Score format: Decimal 0-5 (stored as string, e.g. "3.8")
"""

import json
import re
import time
import unicodedata
from datetime import datetime

import requests


class LetterboxdScoreScraper:
    """Finds Letterboxd scores via HTML page scraping + JSON-LD extraction."""

    LB_URL_BASE = 'https://letterboxd.com/film/'

    def __init__(self, cache_file='cache/letterboxd_score_cache.json', config=None, logger=None):
        self.cache_file = cache_file
        self.config = config or {}
        self.logger = logger
        self.cache = self._load_cache()
        self.stats = {'attempts': 0, 'successes': 0, 'failures': 0, 'cache_hits': 0}
        self.last_request_time = 0

        # Config
        lb_config = self.config.get('letterboxd_scraper', {})
        self.rate_limit = lb_config.get('rate_limit', 1.0)
        self.timeout = lb_config.get('timeout', 10)
        self.cache_ttl_days = lb_config.get('cache_ttl_days', 30)
        self.enabled = lb_config.get('enabled', True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    def scrape_letterboxd_score(self, title, year, tmdb_id=None):
        """Public interface: find Letterboxd page and average rating for a movie.

        Args:
            title: Movie title
            year: Release year (int)
            tmdb_id: TMDB movie ID (int or str). If provided, uses Letterboxd's
                     TMDB redirect (letterboxd.com/tmdb/{id}/) as primary lookup —
                     bypasses slug construction and year verification entirely.

        Returns:
            dict: {'url': str, 'score': str or None} or None if not found
        """
        cache_key = f"{title}_{year}"

        # Cache check (with TTL enforcement for "not found" entries)
        cached = self.cache.get(cache_key)
        if cached:
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

        # Primary: TMDB redirect (reliable, handles all slug/year edge cases)
        result = None
        if tmdb_id:
            result = self._try_tmdb_redirect(tmdb_id)

        # Fallback: slug-based URL construction
        if not result:
            result = self._try_candidate_urls(title, year)

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

    def _try_tmdb_redirect(self, tmdb_id):
        """Look up Letterboxd film page via TMDB ID redirect.

        Letterboxd maintains a TMDB-to-film mapping: requesting
        letterboxd.com/tmdb/{id}/ redirects to the canonical film page.
        This bypasses slug construction and year verification entirely.

        Returns:
            dict with url and score, or None if not found
        """
        # Strip 'tv_' prefix — Letterboxd is film-only, TV IDs will 404
        clean_id = str(tmdb_id).replace('tv_', '')
        if not clean_id.isdigit():
            return None

        url = f'https://letterboxd.com/tmdb/{clean_id}/'
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout,
                                allow_redirects=True)
            if resp.status_code != 200 or '/film/' not in resp.url:
                return None

            score = self._extract_rating_from_html(resp.text)
            final_url = resp.url.rstrip('/')
            return {'url': final_url, 'score': score}

        except requests.exceptions.Timeout:
            self._log(f"Timeout for TMDB redirect {url}", level='debug')
            self.record_error('timeout')
            return None
        except Exception as e:
            self._log(f"Error with TMDB redirect {url}: {e}", level='debug')
            return None

    def _try_candidate_urls(self, title, year):
        """Try candidate Letterboxd URLs via HTTP GET.

        Slug logic reused from gemini_scraper/pull_quotes.py:524-535.

        Returns:
            dict with url and score, or None if not found
        """
        slug = self._make_slug(title)
        # Try year-suffixed slugs first (more specific), then bare slug
        candidate_urls = [
            f'{self.LB_URL_BASE}{slug}-{year}/',
            f'{self.LB_URL_BASE}{slug}-{year - 1}/',
            f'{self.LB_URL_BASE}{slug}/',
        ]

        for url in candidate_urls:
            try:
                resp = requests.get(url, headers=self.headers, timeout=self.timeout,
                                    allow_redirects=True)
                if resp.status_code != 200:
                    continue

                # Verify year from page title to avoid wrong-film matches
                title_match = re.search(r'<title>(.*?)</title>', resp.text, re.IGNORECASE)
                if title_match:
                    page_title = title_match.group(1)
                    if f'({year})' not in page_title and f'({year - 1})' not in page_title:
                        self._log(f"Year mismatch for {url}: page title '{page_title}'", level='debug')
                        continue

                # Extract rating from JSON-LD
                score = self._extract_rating_from_html(resp.text)
                if score is not None:
                    # Use the final URL (after redirects) as canonical
                    final_url = resp.url.rstrip('/')
                    return {'url': final_url, 'score': score}
                else:
                    # Page exists but no rating (too new/obscure) — still store the URL
                    final_url = resp.url.rstrip('/')
                    return {'url': final_url, 'score': None}

            except requests.exceptions.Timeout:
                self._log(f"Timeout for {url}", level='debug')
                self.record_error('timeout')
                continue
            except Exception as e:
                self._log(f"Error fetching {url}: {e}", level='debug')
                continue

        self._log(f"No Letterboxd page found for '{title}' ({year})", level='debug')
        return None

    def _extract_rating_from_html(self, html):
        """Extract aggregateRating.ratingValue from JSON-LD in the HTML.

        Handles Letterboxd's CDATA wrapper around JSON-LD blocks.

        Returns:
            str: Rating as string (e.g. "3.8"), or None if not found
        """
        matches = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        for m in matches:
            cleaned = m.strip()
            # Strip Letterboxd's CDATA wrapper if present
            cleaned = re.sub(r'^/\*\s*<!\[CDATA\[\s*\*/', '', cleaned)
            cleaned = re.sub(r'/\*\s*\]\]>\s*\*/$', '', cleaned)
            try:
                data = json.loads(cleaned.strip())
                if 'aggregateRating' in data:
                    rating = data['aggregateRating'].get('ratingValue')
                    if rating is not None:
                        return str(round(float(rating), 1))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _make_slug(title):
        """Convert title to Letterboxd-style URL slug.

        Logic from gemini_scraper/pull_quotes.py:524-535.
        """
        t = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
        t = t.lower()
        t = re.sub(r"'s\b", 's', t)
        t = re.sub(r"['''\u2019]", '', t)
        t = re.sub(r'[^a-z0-9]+', '-', t)
        t = t.strip('-')
        return t

    def _enforce_rate_limit(self):
        """Enforce minimum delay between requests."""
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
            getattr(self.logger, level, self.logger.info)(f"[LetterboxdScoreScraper] {message}")

    def record_error(self, error_type):
        """Record an error by type for diagnostic breadcrumbs."""
        if not hasattr(self, '_error_counts'):
            self._error_counts = {}
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1

    def get_error_counts(self):
        """Return error type breakdown for scraper_health metrics."""
        return getattr(self, '_error_counts', {})

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


    def close(self):
        """No-op for HTTP-based scraper (no browser to close)."""
        pass


# Legacy alias — class renamed from LetterboxdScraper (June 2026) because it
# only scrapes scores, never quotes or reviews.
LetterboxdScraper = LetterboxdScoreScraper
