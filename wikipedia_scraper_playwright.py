from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import random
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from playwright_manager import get_playwright_manager


class WikipediaScraperPlaywright:
    """Wikipedia scraper using Playwright for finding movie pages."""

    def __init__(self, cache_file='wikipedia_cache.json', config=None, logger=None):
        """Initialize the Wikipedia scraper with configuration.

        Args:
            cache_file: Path to cache file for Wikipedia URLs
            config: Configuration dict with wikipedia_scraper settings
            logger: Logger instance for output
        """
        self.cache_file = cache_file
        self.config = config or {}
        self.logger = logger

        # Browser components (lazy initialization)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Shared manager reference
        self.manager = get_playwright_manager()

        # Rate limiting
        self.last_scrape_time = 0
        self.rate_limit = self.config.get('wikipedia_scraper', {}).get('rate_limit', 1.0)

        # Cache
        self.cache = self._load_cache()

        # Screenshots for diagnostics
        self.screenshot_dir = 'cache/screenshots/wikipedia'
        self.screenshots_enabled = self.config.get('wikipedia_scraper', {}).get('screenshots_enabled', True)

        # Clean up old screenshots on initialization
        if self.screenshots_enabled:
            self._cleanup_old_screenshots()

        # Stats
        self.stats = {
            'attempts': 0,
            'successes': 0,
            'cache_hits': 0,
            'failures': 0,
            'wikidata_attempts': 0,
            'wikidata_successes': 0,
            'api_successes': 0,
            'scraper_successes': 0
        }

        self._log(f"Wikipedia Scraper initialized with Playwright, cache_file={cache_file}")
        self._log(f"Cache loaded: {len(self.cache)} entries")
        self._log(f"Screenshots: {'enabled' if self.screenshots_enabled else 'disabled'}")

    def _log(self, message, level='info'):
        """Log message using logger if available, otherwise print."""
        if self.logger:
            if level == 'debug':
                self.logger.debug(message)
            elif level == 'warning':
                self.logger.warning(message)
            elif level == 'error':
                self.logger.error(message)
            else:
                self.logger.info(message)
        else:
            print(f"[WikipediaScraperPlaywright] {message}")

    def _load_cache(self):
        """Load Wikipedia cache from disk."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                self._log(f"Failed to load cache: {e}", level='warning')
        return {}

    def _save_cache(self):
        """Save Wikipedia cache to disk."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            self._log(f"Cache saved: {len(self.cache)} entries", level='debug')
        except Exception as e:
            self._log(f"Failed to save cache: {e}", level='error')

    def _cleanup_old_screenshots(self):
        """Delete old screenshots based on retention policy."""
        if not self.screenshots_enabled or not os.path.exists(self.screenshot_dir):
            return

        try:
            retention_days = self.config.get('wikipedia_scraper', {}).get('screenshot_retention_days', 7)
            cutoff_time = datetime.now() - timedelta(days=retention_days)
            cutoff_timestamp = cutoff_time.timestamp()

            deleted_count = 0
            for filename in os.listdir(self.screenshot_dir):
                file_path = os.path.join(self.screenshot_dir, filename)
                if os.path.isfile(file_path):
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_timestamp:
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except OSError as e:
                            self._log(f"Failed to delete old screenshot {filename}: {e}", level='warning')

            if deleted_count > 0:
                self._log(f"Cleaned up {deleted_count} old screenshots (older than {retention_days} days)")

        except Exception as e:
            self._log(f"Failed to cleanup old screenshots: {e}", level='warning')

    def _init_browser(self):
        """Initialize Playwright browser with context."""
        if self.browser is not None:
            self._log("Browser already initialized, reusing...", level='debug')
            return

        self._log("Initializing Playwright browser...")

        try:
            # Get shared Playwright instance
            self.playwright = self.manager.get_playwright()

            # Launch browser
            headless = self.config.get('wikipedia_scraper', {}).get('headless', True)
            self.browser = self.playwright.chromium.launch(headless=headless)

            # Create context with viewport and user agent
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Set default timeout
            timeout_ms = self.config.get('wikipedia_scraper', {}).get('timeout', 10) * 1000
            self.context.set_default_timeout(timeout_ms)

            # Create page
            self.page = self.context.new_page()

            self._log("Playwright browser initialized successfully")

        except Exception as e:
            self._log(f"Browser initialization failed: {e}", level='error')
            self._cleanup_browser()
            raise

    def _cleanup_browser(self):
        """Clean up browser resources."""
        if self.page:
            try:
                self.page.close()
            except:
                pass
            self.page = None

        # Shared manager reference
        self.manager = get_playwright_manager()

        if self.context:
            try:
                self.context.close()
            except:
                pass
            self.context = None

        if self.browser:
            try:
                self.browser.close()
            except:
                pass
            self.browser = None

        if self.playwright:
            try:
                self.manager.release()
            except:
                pass
            self.playwright = None

    def _rate_limit(self):
        """Enforce minimum delay between scrapes."""
        current_time = time.time()
        time_since_last = current_time - self.last_scrape_time

        if time_since_last < self.rate_limit:
            sleep_time = self.rate_limit - time_since_last
            self._log(f"Rate limiting: sleeping {sleep_time:.1f}s", level='debug')
            time.sleep(sleep_time)

        self.last_scrape_time = time.time()

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

            except (PlaywrightTimeoutError, Exception) as e:
                last_error = e
                self._log(f"Attempt {attempt + 1} error: {e}", level='debug')
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

    def _scrape_wikipedia_page(self, title, year):
        """Scrape Wikipedia search page to find movie URL using Playwright.

        Args:
            title: Movie title
            year: Release year

        Returns:
            str: Wikipedia URL or None if not found
        """
        # Initialize browser if needed
        self._init_browser()

        # Apply rate limiting
        self._rate_limit()

        # Increment attempts counter
        self.stats['attempts'] += 1

        try:
            # Build search URL
            search_query = f"{title} ({year} film)"
            search_url = f"https://en.wikipedia.org/w/index.php?search={quote(search_query)}"

            self._log(f"Searching Wikipedia: {title} ({year})", level='debug')

            # Navigate to search page
            self.page.goto(search_url, wait_until='domcontentloaded')
            time.sleep(1)  # Wait for dynamic content

            # Check if we landed directly on an article (exact match)
            current_url = self.page.url
            if "/wiki/" in current_url and "Special:Search" not in current_url:
                self._log(f"Direct hit: {current_url}", level='debug')
                return current_url

            # Look for search results
            search_selectors = [
                ".mw-search-result-heading a",  # Primary
                ".mw-search-result a",  # Fallback 1
                ".searchresult a",  # Fallback 2
            ]

            for selector in search_selectors:
                try:
                    results = self.page.query_selector_all(selector)
                    if results:
                        # Check first few results for film-specific match
                        for result in results[:5]:
                            href = result.get_attribute('href')
                            result_text = result.text_content().lower()

                            # Prefer results with year or "film" in title
                            if title.lower() in result_text:
                                if str(year) in result_text or 'film' in result_text:
                                    # Make absolute URL
                                    if href.startswith('/'):
                                        wiki_url = f"https://en.wikipedia.org{href}"
                                    else:
                                        wiki_url = href
                                    self._log(f"Found match with selector {selector}: {wiki_url}", level='debug')
                                    return wiki_url

                        # If no year/film match, take first result if title matches
                        if results and title.lower() in results[0].text_content().lower():
                            href = results[0].get_attribute('href')
                            if href.startswith('/'):
                                wiki_url = f"https://en.wikipedia.org{href}"
                            else:
                                wiki_url = href
                            self._log(f"Found title match: {wiki_url}", level='debug')
                            return wiki_url

                except Exception as e:
                    self._log(f"Selector {selector} failed: {e}", level='debug')
                    continue

            # No results found
            self._log(f"No Wikipedia page found for {title} ({year})", level='warning')
            self.stats['failures'] += 1

            # Capture diagnostics
            self._capture_failure_diagnostics(title, year, "No Wikipedia page found")
            return None

        except Exception as e:
            self._log(f"Wikipedia scraping error for {title} ({year}): {e}", level='error')
            self.stats['failures'] += 1

            # Capture diagnostics
            self._capture_failure_diagnostics(title, year, str(e))
            return None

    def find_wikipedia_url(self, title, year, imdb_id=None, use_api=True, use_wikidata=True):
        """Find Wikipedia URL with waterfall approach.

        Priority waterfall:
        1. Cache check
        2. Wikidata SPARQL (if IMDb ID available and enabled)
        3. Wikipedia REST API (if enabled)
        4. Playwright scraper (fallback)

        Args:
            title: Movie title
            year: Release year
            imdb_id: IMDb ID for Wikidata lookup (optional)
            use_api: Whether to use Wikipedia REST API (default: True)
            use_wikidata: Whether to use Wikidata SPARQL (default: True)

        Returns:
            str: Wikipedia URL or None if not found
        """
        cache_key = f"{title}_{year}"

        # 1. Check cache
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict):
                url = cached_data.get('url')
                # Skip search fallbacks - try scraping instead
                if url and 'index.php?search=' not in url:
                    self.stats['cache_hits'] += 1
                    self._log(f"Cache hit for {title} ({year})", level='debug')
                    return url
                else:
                    self._log(f"Cache contains search fallback for {title}, will re-scrape", level='debug')
            elif cached_data and 'index.php?search=' not in cached_data:
                self.stats['cache_hits'] += 1
                return cached_data

        # 2. Try Wikidata if IMDb ID available
        if use_wikidata and imdb_id:
            wiki_url = self._query_wikidata(imdb_id)
            if wiki_url:
                self._cache_result(cache_key, wiki_url, title, 'wikidata')
                self.stats['wikidata_successes'] += 1
                self.stats['successes'] += 1
                return wiki_url

        # 3. Try Wikipedia REST API
        if use_api:
            wiki_url = self._try_wikipedia_api(title, year)
            if wiki_url:
                self._cache_result(cache_key, wiki_url, title, 'wikipedia_api')
                self.stats['api_successes'] += 1
                self.stats['successes'] += 1
                return wiki_url

        # 4. Fallback to Playwright scraper
        wiki_url = self._retry_with_backoff(lambda: self._scrape_wikipedia_page(title, year))
        if wiki_url:
            self._cache_result(cache_key, wiki_url, title, 'playwright_scraper')
            self.stats['scraper_successes'] += 1
            self.stats['successes'] += 1
            return wiki_url

        # Failed - cache the failure as search fallback
        search_fallback_url = f"https://en.wikipedia.org/w/index.php?search={quote(title + ' (' + year + ' film)')}"
        self._cache_result(cache_key, search_fallback_url, title, 'search_fallback')
        return search_fallback_url

    def _query_wikidata(self, imdb_id):
        """Query Wikidata SPARQL endpoint for Wikipedia URL."""
        import requests

        self.stats['wikidata_attempts'] += 1

        try:
            sparql_query = f"""
            SELECT ?article WHERE {{
              ?item wdt:P345 "{imdb_id}" .
              ?article schema:about ?item .
              ?article schema:isPartOf <https://en.wikipedia.org/> .
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

            wikipedia_url = results[0]['article']['value']

            if not wikipedia_url or not wikipedia_url.startswith('https://en.wikipedia.org/wiki/'):
                return None

            self._log(f"Wikidata found Wikipedia link for IMDb {imdb_id}", level='debug')
            return wikipedia_url

        except Exception as e:
            self._log(f"Wikidata query error: {e}", level='debug')
            return None

    def _try_wikipedia_api(self, title, year):
        """Try Wikipedia REST API for finding article."""
        import requests

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
                    return wiki_url

            # Try without year
            search_title = f"{title} (film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    return wiki_url

        except Exception as e:
            self._log(f"Wikipedia API error: {e}", level='debug')

        return None

    def _cache_result(self, cache_key, url, title, source):
        """Cache the Wikipedia URL result."""
        self.cache[cache_key] = {
            'url': url,
            'title': title,
            'cached_at': datetime.now().isoformat(),
            'source': source
        }
        self._save_cache()

    def get_stats(self):
        """Get scraper statistics."""
        return self.stats.copy()

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
        self._log("Wikipedia Scraper closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
