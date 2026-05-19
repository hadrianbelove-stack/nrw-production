#!/usr/bin/env python3
"""
Wikipedia Scraper v2 - Migrated to use PlaywrightScraperBase.

This is a WALLED GARDEN version for testing. Do not use in production
until comparison tests pass.

Changes from v1 (wikipedia_scraper_playwright.py):
- Inherits from PlaywrightScraperBase instead of duplicating code
- Removes ~200 lines of duplicated methods
- All Wikipedia-specific logic preserved exactly

Inherited from base class:
- _log(), _log_metrics()
- _load_cache(), _save_cache()
- _cleanup_old_screenshots()
- _init_browser(), _init_browser_shared(), _init_browser_local()
- _enforce_rate_limit()
- stats and counters initialization
- get_stats()
- Context manager (__enter__, __exit__)
"""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import random
import re
import requests
from datetime import datetime
from urllib.parse import quote

from scraper_base import PlaywrightScraperBase

# Import Gemini finder with graceful fallback
try:
    from gemini_scraper import GeminiWikipediaFinder
    GEMINI_WIKIPEDIA_AVAILABLE = True
except ImportError as e:
    GeminiWikipediaFinder = None
    GEMINI_WIKIPEDIA_AVAILABLE = False


class WikipediaNoResults(Exception):
    """Raised when Wikipedia search returns no matching results (don't retry)."""
    pass


class WikipediaScraperPlaywright(PlaywrightScraperBase):
    """Wikipedia scraper using Playwright for finding movie pages.

    v2: Now inherits from PlaywrightScraperBase for shared functionality.
    """

    def __init__(self, cache_file='cache/wikipedia_cache.json', config=None, logger=None):
        """Initialize the Wikipedia scraper with configuration.

        Args:
            cache_file: Path to cache file for Wikipedia URLs
            config: Configuration dict with wikipedia_scraper settings
            logger: Logger instance for output
        """
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key='wikipedia_scraper',
            log_prefix='WikipediaScraperPlaywright',
            screenshot_subdir='wikipedia'
        )

        # Wikipedia-specific stats (extend base stats)
        self.stats.update({
            'wikidata_attempts': 0,
            'wikidata_successes': 0,
            'gemini_attempts': 0,
            'gemini_successes': 0,
            'api_successes': 0,
            'scraper_successes': 0
        })

        # Wikidata distributor results (populated by _query_wikidata)
        self.last_wikidata_distributors = []

        # Gemini finder (lazy loaded)
        self._gemini_finder = None
        self._gemini_enabled = self._check_gemini_enabled()

        self._log(f"Wikipedia Scraper initialized with cache_file={cache_file}")

    def _check_gemini_enabled(self) -> bool:
        """Check if Gemini Wikipedia is enabled via config."""
        if not GEMINI_WIKIPEDIA_AVAILABLE:
            return False
        if self.config:
            gemini_config = self.config.get('gemini_scraper', {})
            if not gemini_config.get('enabled', True):
                return False
            if not gemini_config.get('wikipedia_enabled', True):
                return False
        return True

    def _get_gemini_finder(self):
        """Lazy load Gemini Wikipedia finder."""
        if self._gemini_finder is None and self._gemini_enabled:
            try:
                self._gemini_finder = GeminiWikipediaFinder(cache_file=self.cache_file)
                self._log("Gemini Wikipedia finder initialized", level='debug')
            except Exception as e:
                self._log(f"Failed to initialize Gemini finder: {e}", level='warning')
                self._gemini_enabled = False
        return self._gemini_finder

    def _cleanup_browser(self):
        """Clean up browser resources - Wikipedia-specific override.

        Overrides base to call manager.release() for reference counting.
        """
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None

        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None

        # Wikipedia scraper specifically calls manager.release()
        if self.playwright and self.manager:
            try:
                self.manager.release()
                self._log("Released shared browser reference", level='debug')
            except Exception:
                pass
            self.playwright = None
            self.browser = None

        self.counters['stop_count'] += 1

    def _retry_with_backoff(self, fn, max_attempts=None, base_delay=None, max_delay=None, jitter_ratio=None):
        """Retry function with exponential backoff."""
        if max_attempts is None:
            max_attempts = self.config.get('wikipedia_scraper', {}).get('max_retries', 3)

        # Get exponential backoff config values
        backoff_config = self.config.get('wikipedia_scraper', {}).get('exponential_backoff', {})
        if base_delay is None:
            base_delay = backoff_config.get('base_delay', 0.5)
        if max_delay is None:
            max_delay = backoff_config.get('max_delay', 5.0)
        if jitter_ratio is None:
            jitter_ratio = backoff_config.get('jitter_ratio', 0.2)

        last_error = None
        for attempt in range(max_attempts):
            try:
                result = fn()
                if result is not None:
                    return result

                # If function returned None, continue to retry
                if attempt < max_attempts - 1:
                    delay = min(max_delay, base_delay * (2 ** attempt))
                    jitter = random.uniform(-jitter_ratio * delay, jitter_ratio * delay)
                    sleep_time = delay + jitter
                    self._log(f"Attempt {attempt + 1} failed, retrying in {sleep_time:.1f}s...", level='debug')
                    time.sleep(sleep_time)

            except WikipediaNoResults:
                # Clean miss — retrying won't help
                self.record_error('not_found')
                return None
            except (PlaywrightTimeoutError, Exception) as e:
                last_error = e
                self._log(f"Attempt {attempt + 1} error: {e}", level='debug')
                if isinstance(e, PlaywrightTimeoutError):
                    self.record_error('timeout')
                else:
                    self.record_error(type(e).__name__)
                if attempt < max_attempts - 1:
                    delay = min(max_delay, base_delay * (2 ** attempt))
                    jitter = random.uniform(-jitter_ratio * delay, jitter_ratio * delay)
                    sleep_time = delay + jitter
                    self._log(f"Retrying in {sleep_time:.1f}s...", level='debug')
                    time.sleep(sleep_time)

        # All attempts failed
        return None

    def _capture_failure_diagnostics(self, title, year, error_msg):
        """Capture screenshot and HTML on failure for debugging."""
        if not self.screenshots_enabled or not self.page:
            return {}

        try:
            # Create screenshot directory
            os.makedirs(self.screenshot_dir, exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:50]
            filename_base = f"{safe_title}_{year}_{timestamp}"

            # Capture screenshot
            screenshot_path = os.path.join(self.screenshot_dir, f"{filename_base}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)

            # Save HTML
            html_path = os.path.join(self.screenshot_dir, f"{filename_base}.html")
            html_content = self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self._log(f"Screenshot saved: {screenshot_path}")

            # Clean up old screenshots after saving a new one
            self._cleanup_old_screenshots()

            return {
                'screenshot': screenshot_path,
                'html': html_path,
                'error': error_msg
            }

        except Exception as e:
            self._log(f"Failed to capture diagnostics: {e}", level='warning')
            return {'error': error_msg}

    def _title_matches(self, title, result_text):
        """Check if search result likely matches the film title.

        Strips parenthetical disambiguation from result first
        (e.g. "Dune (2024 film)" → "Dune"), then requires the core
        titles to match exactly or as identical significant-word sets.

        Args:
            title: Original movie title
            result_text: Text from search result link

        Returns:
            bool: True if result appears to match the title
        """
        def normalize(s):
            """Normalize string for comparison."""
            s = s.lower()
            s = s.replace('&', 'and').replace('&amp;', 'and')
            for c in '.,!?:;\'"()-':
                s = s.replace(c, '')
            return ' '.join(s.split())

        norm_title = normalize(title)

        # Strip parenthetical disambiguation before normalizing result
        # "The Matrix (1999 film)" → "The Matrix"
        result_core = re.sub(r'\s*\([^)]*\)\s*$', '', result_text).strip()
        norm_result = normalize(result_core)

        # Exact core match
        if norm_title == norm_result:
            return True

        # Word-based: significant words must match bidirectionally
        stopwords = {'the', 'a', 'an', 'of', 'and', 'in', 'on', 'at', 'to', 'for'}
        title_sig = set(norm_title.split()) - stopwords
        result_sig = set(norm_result.split()) - stopwords

        if not title_sig:
            return norm_title == norm_result

        return title_sig == result_sig

    def _scrape_wikipedia_page(self, title, year):
        """Find Wikipedia article using Playwright browser.

        Uses a click-through approach:
        1. Navigate to Wikipedia search
        2. If auto-redirected to article, use that
        3. If on search results, click first matching result
        4. Never return a search URL - either find article or return None

        Args:
            title: Movie title
            year: Release year

        Returns:
            str: Wikipedia article URL or None if not found
        """
        # Initialize browser if needed
        self._init_browser()

        # Apply rate limiting (using inherited method)
        self._enforce_rate_limit()

        # Increment attempts counter
        self.stats['attempts'] += 1

        try:
            # Build search URL
            search_query = f"{title} ({year} film)"
            search_url = f"https://en.wikipedia.org/w/index.php?search={quote(search_query)}"

            self._log(f"Playwright searching: {title} ({year})", level='debug')

            # Navigate to search page
            self.page.goto(search_url, wait_until='domcontentloaded')
            time.sleep(1)  # Wait for dynamic content

            current_url = self.page.url

            # Check if we landed directly on an article (Wikipedia auto-redirected)
            if "/wiki/" in current_url and "Special:Search" not in current_url and "index.php" not in current_url:
                # Check for disambiguation page
                is_disambiguation = False
                for selector in ["#disambigbox", ".hatnote a[href*='disambiguation']", "body.mw-disambig"]:
                    if self.page.query_selector(selector):
                        is_disambiguation = True
                        self._log(f"Disambiguation page detected: {current_url}", level='debug')
                        break

                if not is_disambiguation:
                    self._log(f"Auto-redirected to article: {current_url}", level='debug')
                    return current_url

                # Handle disambiguation page - look for film link
                disambig_links = self.page.query_selector_all("#mw-content-text ul li a")
                for link in disambig_links:
                    try:
                        href = link.get_attribute('href')
                        link_text = link.text_content().lower()

                        if not href or not href.startswith('/wiki/') or ':' in href:
                            continue

                        # Look for film-related links with year preference
                        if 'film' in link_text or 'movie' in link_text:
                            if str(year) in link_text or str(year) in href:
                                wiki_url = f"https://en.wikipedia.org{href}"
                                self._log(f"Disambiguation: Found film+year: {wiki_url}", level='debug')
                                return wiki_url
                    except Exception:
                        continue

            # We're on search results page - find and click first matching result
            first_result = self.page.query_selector(".mw-search-result-heading a")

            if first_result:
                result_text = first_result.text_content()

                if self._title_matches(title, result_text):
                    # Click through to the article
                    self._log(f"Clicking search result: '{result_text}'", level='debug')
                    first_result.click()
                    self.page.wait_for_load_state('domcontentloaded')

                    final_url = self.page.url
                    self._log(f"Clicked through to: {final_url}", level='debug')

                    # Post-click year verification: reject if article is about a different year's film
                    if year:
                        first_para = self.page.query_selector('#mw-content-text p')
                        if first_para:
                            para_text = first_para.text_content()
                            if str(year) not in para_text:
                                self._log(f"Year {year} not found in article for {title}, rejecting {final_url}", level='debug')
                                return None

                    return final_url
                else:
                    self._log(f"First result '{result_text}' doesn't match '{title}'", level='debug')

            # No matching results found — don't retry, don't screenshot
            self._log(f"No Wikipedia article found for {title} ({year})", level='warning')
            self.stats['failures'] += 1
            raise WikipediaNoResults(f"No matching article for {title} ({year})")

        except WikipediaNoResults:
            raise  # Let _retry_with_backoff handle this (no retry for clean misses)
        except Exception as e:
            self._log(f"Playwright scraping error for {title} ({year}): {e}", level='error')
            self.stats['failures'] += 1
            self._capture_failure_diagnostics(title, year, str(e))
            return None

    def find_wikipedia_url(self, title, year, imdb_id=None, use_api=True, use_wikidata=True,
                           director=None, original_title=None, skip_playwright=False,
                           skip_gemini=False):
        """Find Wikipedia URL with waterfall approach.

        Priority waterfall:
        1. Cache check (valid article URLs only)
        2. Wikidata SPARQL (if IMDb ID available and enabled)
        2.5. Gemini with Google Search grounding (uses director for disambiguation)
        3. Wikipedia REST API (if enabled) - now includes plain title fallback
        4. Playwright scraper with click-through
        5. If all fail and original_title differs, retry waterfall with original_title

        IMPORTANT: Never returns a search URL. Returns None if no article found.

        Args:
            title: Movie title
            year: Release year
            imdb_id: IMDb ID for Wikidata lookup (optional)
            use_api: Whether to use Wikipedia REST API (default: True)
            use_wikidata: Whether to use Wikidata SPARQL (default: True)
            director: Director name for Gemini disambiguation (optional)
            original_title: Original-language title for fallback search (optional)

        Returns:
            str: Wikipedia article URL or None if not found
        """
        cache_key = f"{title}_{year}"

        # 1. Check cache - only return valid article URLs
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict):
                url = cached_data.get('url')
                source = cached_data.get('source', '')

                # Skip old search fallback entries - always re-scrape these
                if source == 'search_fallback' or cached_data.get('is_search_fallback'):
                    self._log(f"Skipping old search_fallback cache for {title}, will re-scrape", level='debug')
                # Skip any URL that looks like a search page
                elif url and 'index.php?search=' in url:
                    self._log(f"Skipping search URL in cache for {title}, will re-scrape", level='debug')
                # Negative cache: no Wikipedia article exists (expires after 30 days)
                elif cached_data.get('negative') and source == 'no_article':
                    cached_at = cached_data.get('cached_at', '')
                    if cached_at:
                        try:
                            cache_age = (datetime.now() - datetime.fromisoformat(cached_at)).days
                            if cache_age < 30:
                                self.stats['cache_hits'] += 1
                                self._log(f"Negative cache hit for {title} ({year}): no article ({cache_age}d old)", level='debug')
                                # Restore cached Wikidata distributors even for negative cache
                                self.last_wikidata_distributors = cached_data.get('wikidata_distributors', [])
                                return None
                            else:
                                self._log(f"Negative cache expired for {title} ({year}): {cache_age}d old, retrying", level='debug')
                        except (ValueError, TypeError):
                            pass
                # Valid article URL - return it
                elif url and '/wiki/' in url:
                    self.stats['cache_hits'] += 1
                    self._log(f"Cache hit for {title} ({year}): {source}", level='debug')
                    # Restore cached Wikidata distributors
                    self.last_wikidata_distributors = cached_data.get('wikidata_distributors', [])
                    return url
            # Handle old string-only cache entries
            elif cached_data and 'index.php?search=' not in cached_data and '/wiki/' in cached_data:
                self.stats['cache_hits'] += 1
                self.last_wikidata_distributors = []
                return cached_data

        # 2. Try Wikidata if IMDb ID available
        if use_wikidata and imdb_id:
            wiki_url = self._query_wikidata(imdb_id)
            if wiki_url:
                self._cache_result(cache_key, wiki_url, title, 'wikidata')
                self.stats['wikidata_successes'] += 1
                self.stats['successes'] += 1
                return wiki_url

        # 2.5. Try Gemini with Google Search grounding (faster than REST API)
        gemini_finder = self._get_gemini_finder() if not skip_gemini else None
        if gemini_finder:
            wiki_url = gemini_finder.find_wikipedia_url(title, year, director=director)
            # Sync stats from child finder (single source of truth)
            gemini_stats = gemini_finder.get_stats()
            self.stats['gemini_attempts'] = gemini_stats.get('gemini_attempts', 0)
            self.stats['gemini_successes'] = gemini_stats.get('gemini_successes', 0)
            if wiki_url:
                self._cache_result(cache_key, wiki_url, title, 'gemini')
                self.stats['successes'] += 1
                return wiki_url

        # 3. Try Wikipedia REST API (includes plain title fallback)
        if use_api:
            wiki_url = self._try_wikipedia_api(title, year)
            if wiki_url:
                self._cache_result(cache_key, wiki_url, title, 'wikipedia_api')
                self.stats['api_successes'] += 1
                self.stats['successes'] += 1
                return wiki_url

        # 4. Fallback to Playwright scraper with click-through (skip in gap-fill mode)
        if skip_playwright:
            self._log(f"Skipping Playwright fallback for {title} (skip_playwright=True)", level='debug')
        else:
            wiki_url = self._retry_with_backoff(lambda: self._scrape_wikipedia_page(title, year))
            if wiki_url:
                self._cache_result(cache_key, wiki_url, title, 'playwright_scraper')
                self.stats['scraper_successes'] += 1
                self.stats['successes'] += 1
                return wiki_url

        # 5. If original_title differs from title, retry waterfall with it
        if original_title and original_title != title:
            self._log(f"Retrying with original title: {original_title}", level='debug')
            return self.find_wikipedia_url(original_title, year, imdb_id,
                                           use_api=use_api, use_wikidata=False,
                                           director=director, original_title=None,
                                           skip_playwright=skip_playwright,
                                           skip_gemini=skip_gemini)

        # No article found - cache negative result to avoid re-querying daily
        self._log(f"No Wikipedia article found for {title} ({year})", level='warning')
        self.stats['failures'] += 1
        neg_entry = {
            'url': None,
            'title': title,
            'cached_at': datetime.now().isoformat(),
            'source': 'no_article',
            'negative': True
        }
        # Preserve Wikidata distributors even when no Wikipedia article exists
        if self.last_wikidata_distributors:
            neg_entry['wikidata_distributors'] = self.last_wikidata_distributors
        self.cache[cache_key] = neg_entry
        self._save_cache()
        return None

    def _query_wikidata(self, imdb_id):
        """Query Wikidata SPARQL endpoint for Wikipedia URL and distributor (P750)."""
        self.stats['wikidata_attempts'] += 1
        self.last_wikidata_distributors = []

        try:
            sparql_query = f"""
            SELECT ?article ?distributorLabel WHERE {{
              ?item wdt:P345 "{imdb_id}" .
              OPTIONAL {{
                ?article schema:about ?item .
                ?article schema:isPartOf <https://en.wikipedia.org/> .
              }}
              OPTIONAL {{ ?item wdt:P750 ?distributor . }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
            }}
            """

            url = "https://query.wikidata.org/sparql"
            headers = {
                'User-Agent': 'NewReleaseWall/1.0 (https://github.com/hadrianbelove-stack/nrw-production; hadrianbelove@gmail.com)',
                'Accept': 'application/sparql-results+json'
            }

            response = requests.get(url, params={'query': sparql_query}, headers=headers, timeout=10)

            if response.status_code != 200:
                self._log(f"Wikidata query error: HTTP {response.status_code}", level='debug')
                return None

            data = response.json()
            results = data.get('results', {}).get('bindings', [])

            if not results:
                return None

            # Extract Wikipedia URL from first result that has one
            wikipedia_url = None
            for r in results:
                article = r.get('article', {}).get('value', '')
                if article and article.startswith('https://en.wikipedia.org/wiki/'):
                    wikipedia_url = article
                    break

            # Extract all unique distributor names
            distributors = []
            seen = set()
            for r in results:
                dist_label = r.get('distributorLabel', {}).get('value', '')
                if dist_label and dist_label not in seen:
                    distributors.append(dist_label)
                    seen.add(dist_label)

            self.last_wikidata_distributors = distributors
            if distributors:
                self._log(f"Wikidata found distributors for IMDb {imdb_id}: {distributors}", level='debug')

            if not wikipedia_url:
                return None

            self._log(f"Wikidata found Wikipedia link for IMDb {imdb_id}", level='debug')
            return wikipedia_url

        except Exception as e:
            self._log(f"Wikidata query error: {e}", level='debug')
            return None

    def _try_wikipedia_api(self, title, year):
        """Try Wikipedia REST API for finding article.

        Attempts three variations in order:
        1. "Title (YEAR film)" - most specific
        2. "Title (film)" - common disambiguation
        3. "Title" - plain title for unique names
        """
        try:
            headers = {
                'User-Agent': 'NewReleaseWall/1.0 (https://github.com/hadrianbelove-stack/nrw-production; hadrianbelove@gmail.com)'
            }

            # Try with year
            search_title = f"{title} ({year} film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    self._log(f"REST API found: {title} ({year} film)", level='debug')
                    return wiki_url

            # Try with (film) suffix only
            search_title = f"{title} (film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Reject disambiguation pages (e.g., "Blackout (film)" lists multiple films)
                if data.get('type') == 'disambiguation':
                    self._log(f"REST API: {title} (film) is disambiguation page, skipping", level='debug')
                else:
                    wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                    if wiki_url:
                        self._log(f"REST API found: {title} (film)", level='debug')
                        return wiki_url

            # Try plain title (no suffix) - for films with unique names
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Reject disambiguation pages
                if data.get('type') == 'disambiguation':
                    self._log(f"REST API: {title} is disambiguation page, skipping", level='debug')
                else:
                    # Verify it's actually a film article by checking extract
                    extract = data.get('extract', '').lower()
                    wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                    # Only accept if it mentions film/movie in the extract
                    if wiki_url and ('film' in extract or 'movie' in extract):
                        self._log(f"REST API found: {title} (plain title)", level='debug')
                        return wiki_url

        except Exception as e:
            self._log(f"Wikipedia API error: {e}", level='debug')

        return None

    def _cache_result(self, cache_key, url, title, source):
        """Cache the Wikipedia article URL.

        Only caches valid article URLs (containing /wiki/).
        Never caches search URLs.
        """
        # Safety check - never cache search URLs
        if 'index.php?search=' in url or '/wiki/' not in url:
            self._log(f"Refusing to cache non-article URL: {url}", level='warning')
            return

        entry = {
            'url': url,
            'title': title,
            'cached_at': datetime.now().isoformat(),
            'source': source
        }
        # Include Wikidata distributors if available (from P750 query)
        if self.last_wikidata_distributors:
            entry['wikidata_distributors'] = self.last_wikidata_distributors
        self.cache[cache_key] = entry
        self._save_cache()

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
        self._log("Wikipedia Scraper closed")
