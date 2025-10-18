from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import random
from datetime import datetime, timedelta
from urllib.parse import quote


class AgentLinkScraper:
    """Agent-based link scraper using Playwright to find direct watch links from streaming platforms."""

    def __init__(self, cache_file='cache/agent_links_cache.json', config=None):
        """Initialize the agent scraper with configuration."""
        self.cache_file = cache_file
        self.config = config or {}

        # Browser components (lazy initialization)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Rate limiting
        self.last_scrape_time = 0
        self.rate_limit = self.config.get('rate_limit', 2.0)

        # Cache
        self.cache = self._load_cache()

        # Screenshots
        self.screenshot_dir = 'cache/screenshots'
        self.screenshots_enabled = self.config.get('screenshots_enabled', True)

        # Clean up old screenshots on initialization
        if self.screenshots_enabled:
            self._cleanup_old_screenshots()

        print(f"[AgentLinkScraper] Initialized with Playwright, cache_file={cache_file}")
        print(f"[AgentLinkScraper] Cache loaded: {len(self.cache.get('movies', {}))} entries")
        print(f"[AgentLinkScraper] Screenshots: {'enabled' if self.screenshots_enabled else 'disabled'}")

        # Supported platforms mapping
        self.platform_scrapers = {
            'Netflix': NetflixScraper,
            'Disney+': DisneyPlusScraper,
            'Disney Plus': DisneyPlusScraper,
            'HBO Max': HBOMaxScraper,
            'Max': HBOMaxScraper,
            'Hulu': HuluScraper
        }
        print(f"[AgentLinkScraper] Supported platforms: {list(self.platform_scrapers.keys())}")

    def _load_cache(self):
        """Load agent links cache from disk."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return {'movies': {}, 'last_updated': datetime.now().isoformat()}

    def _save_cache(self):
        """Save agent links cache to disk."""
        try:
            print(f"[AgentLinkScraper] Creating cache directory: {os.path.dirname(self.cache_file)}")
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            self.cache['last_updated'] = datetime.now().isoformat()
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            print(f"[AgentLinkScraper] ✓ Cache saved: {len(self.cache.get('movies', {}))} entries to {self.cache_file}")
        except Exception as e:
            print(f"[AgentLinkScraper] ✗ Failed to save cache: {e}")
            raise

    def _cleanup_old_screenshots(self):
        """Delete old screenshots based on retention policy."""
        if not self.screenshots_enabled or not os.path.exists(self.screenshot_dir):
            return

        try:
            retention_days = self.config.get('screenshot_retention_days', 7)
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
                            print(f"[AgentLinkScraper] Failed to delete old screenshot {filename}: {e}")

            if deleted_count > 0:
                print(f"[AgentLinkScraper] 🧹 Cleaned up {deleted_count} old screenshots (older than {retention_days} days)")

        except Exception as e:
            print(f"[AgentLinkScraper] Failed to cleanup old screenshots: {e}")

    def _init_browser(self):
        """Initialize Playwright browser with context."""
        if self.browser is not None:
            print("[AgentLinkScraper] Browser already initialized, reusing...")
            return

        print("[AgentLinkScraper] Initializing Playwright browser...")

        try:
            self.playwright = sync_playwright().start()

            # Launch browser
            headless = self.config.get('headless', True)
            self.browser = self.playwright.chromium.launch(headless=headless)

            # Create context with viewport and user agent
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Set default timeout
            timeout_ms = self.config.get('timeout', 10) * 1000
            self.context.set_default_timeout(timeout_ms)

            # Create page
            self.page = self.context.new_page()

            print("[AgentLinkScraper] ✓ Playwright browser initialized successfully")

        except Exception as e:
            print(f"[AgentLinkScraper] ✗ Browser initialization failed: {e}")
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
                self.playwright.stop()
            except:
                pass
            self.playwright = None

    def _retry_with_backoff(self, fn, max_attempts=None, base_delay=None, max_delay=None, jitter_ratio=None):
        """Retry function with exponential backoff."""
        if max_attempts is None:
            max_attempts = self.config.get('max_retries', 3)

        # Get exponential backoff config values
        backoff_config = self.config.get('exponential_backoff', {})
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
                    # Return result with diagnostic metadata
                    if isinstance(result, dict):
                        result['retry_count'] = attempt + 1
                        if last_error:
                            result['last_error'] = str(last_error)
                        return result
                    else:
                        # For non-dict results, wrap in a dict with metadata
                        return {
                            'link': result,
                            'retry_count': attempt + 1,
                            'last_error': str(last_error) if last_error else None
                        }

                # If function returned None, continue to retry
                if attempt < max_attempts - 1:
                    delay = min(max_delay, base_delay * (2 ** attempt))
                    jitter = random.uniform(-jitter_ratio * delay, jitter_ratio * delay)
                    sleep_time = delay + jitter
                    print(f"[AgentLinkScraper] Attempt {attempt + 1} failed, retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

            except (PlaywrightTimeoutError, Exception) as e:
                last_error = e
                print(f"[AgentLinkScraper] Attempt {attempt + 1} error: {e}")
                if attempt < max_attempts - 1:
                    delay = min(max_delay, base_delay * (2 ** attempt))
                    jitter = random.uniform(-jitter_ratio * delay, jitter_ratio * delay)
                    sleep_time = delay + jitter
                    print(f"[AgentLinkScraper] Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

        # All attempts failed, return metadata about the failure
        return {
            'link': None,
            'retry_count': max_attempts,
            'last_error': str(last_error) if last_error else "No link found after retries"
        }

    def _capture_failure_diagnostics(self, movie_id, title, service, error_msg):
        """Capture screenshot and HTML on failure for debugging."""
        if not self.screenshots_enabled or not self.page:
            return {}

        try:
            # Create screenshot directory
            os.makedirs(self.screenshot_dir, exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_base = f"{movie_id}_{service}_{timestamp}"

            # Capture screenshot
            screenshot_path = os.path.join(self.screenshot_dir, f"{filename_base}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)

            # Save HTML
            html_path = os.path.join(self.screenshot_dir, f"{filename_base}.html")
            html_content = self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"[AgentLinkScraper] 📸 Screenshot saved: {screenshot_path}")

            # Clean up old screenshots after saving a new one
            self._cleanup_old_screenshots()

            return {
                'screenshot': screenshot_path,
                'html': html_path,
                'error': error_msg
            }

        except Exception as e:
            print(f"[AgentLinkScraper] Failed to capture diagnostics: {e}")
            return {'error': error_msg}

    def _rate_limit(self):
        """Enforce rate limiting between scrapes."""
        current_time = time.time()
        time_since_last = current_time - self.last_scrape_time

        if time_since_last < self.rate_limit:
            sleep_time = self.rate_limit - time_since_last
            print(f"[AgentLinkScraper] Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)

        self.last_scrape_time = time.time()

    def _is_cache_expired(self, cached_entry):
        """Check if cache entry has expired."""
        if 'expires_at' not in cached_entry:
            # Handle legacy entries without expires_at
            if 'scraped_at' in cached_entry:
                try:
                    scraped_at = datetime.fromisoformat(cached_entry['scraped_at'])
                    cache_ttl_days = self.config.get('cache_ttl_days', 30)
                    expires_at = scraped_at + timedelta(days=cache_ttl_days)
                    return datetime.now() > expires_at
                except (ValueError, KeyError):
                    pass
            # If both expires_at and scraped_at are missing, preserve old entries (not expired)
            return False

        try:
            expires_at = datetime.fromisoformat(cached_entry['expires_at'])
            return datetime.now() > expires_at
        except (ValueError, KeyError):
            return True

    def find_watch_link(self, movie_id, title, year, service_name):
        """Main entry point to find watch link for a movie on a specific service."""
        print(f"[AgentLinkScraper] Finding link for {title} ({year}) on {service_name}...")
        movie_id_str = str(movie_id)

        # Check cache first
        if movie_id_str in self.cache['movies']:
            cached_entry = self.cache['movies'][movie_id_str]
            if 'streaming' in cached_entry and not self._is_cache_expired(cached_entry):
                cached_streaming = cached_entry['streaming']
                if cached_streaming.get('service') == service_name:
                    print(f"[AgentLinkScraper] ✓ Cache hit for {title} on {service_name}")
                    result_dict = {
                        'service': service_name,
                        'link': cached_streaming.get('link'),
                        'cached': True
                    }

                    # Add diagnostic fields from cache if available
                    if 'selector_used' in cached_entry:
                        result_dict['selector_used'] = cached_entry['selector_used']
                    if 'last_error' in cached_entry:
                        result_dict['last_error'] = cached_entry['last_error']
                    if 'retry_count' in cached_entry:
                        result_dict['retry_count'] = cached_entry['retry_count']

                    return result_dict

        # Check if service is supported
        if service_name not in self.platform_scrapers:
            print(f"[AgentLinkScraper] Service '{service_name}' not supported, returning null")
            result_dict = {'service': service_name, 'link': None, 'cached': False}
            result_dict['last_error'] = f"Service '{service_name}' not supported"
            result_dict['retry_count'] = 0
            return result_dict

        try:
            # Initialize browser if needed
            print(f"[AgentLinkScraper] Initializing browser for {title}...")
            self._init_browser()

            # Rate limit
            print(f"[AgentLinkScraper] Applying rate limit...")
            self._rate_limit()

            # Get appropriate scraper class and create instance
            scraper_class = self.platform_scrapers[service_name]
            print(f"[AgentLinkScraper] Using {scraper_class.__name__} for {service_name}")
            scraper = scraper_class(self.page, self.config)

            # Attempt to find link with retry
            def scrape_attempt():
                return scraper.find_watch_link(title, year)

            # Get exponential backoff config for this retry
            backoff_config = self.config.get('exponential_backoff', {})
            result = self._retry_with_backoff(
                scrape_attempt,
                base_delay=backoff_config.get('base_delay', 0.5),
                max_delay=backoff_config.get('max_delay', 5.0),
                jitter_ratio=backoff_config.get('jitter_ratio', 0.2)
            )
            print(f"[AgentLinkScraper] Scraper returned: {result}")

            # Extract data from result
            if isinstance(result, dict):
                link = result.get('link')
                retry_count = result.get('retry_count')
                last_error = result.get('last_error')
                selector_used = result.get('selector_used')
            else:
                link = result
                retry_count = None
                last_error = None
                selector_used = None

            # Cache result
            print(f"[AgentLinkScraper] Caching result for {title}...")
            success = link is not None
            diagnostics = {}

            if not success:
                diagnostics = self._capture_failure_diagnostics(
                    movie_id_str, title, service_name, last_error or "No link found after retries"
                )

            self._cache_result(
                movie_id_str, service_name, link, success, diagnostics,
                retry_count=retry_count, last_error=last_error, selector_used=selector_used
            )

            result_dict = {
                'service': service_name,
                'link': link,
                'cached': False
            }

            # Add diagnostic fields when available
            if selector_used is not None:
                result_dict['selector_used'] = selector_used
            if last_error is not None:
                result_dict['last_error'] = last_error
            if retry_count is not None:
                result_dict['retry_count'] = retry_count

            return result_dict

        except Exception as e:
            print(f"[AgentLinkScraper] ✗ Agent scraper error for {title} on {service_name}: {e}")

            # Capture diagnostics for error
            diagnostics = self._capture_failure_diagnostics(
                movie_id_str, title, service_name, str(e)
            )

            # Cache failure
            self._cache_result(
                movie_id_str, service_name, None, False, diagnostics,
                retry_count=1, last_error=str(e), selector_used=None
            )

            result_dict = {'service': service_name, 'link': None, 'cached': False}
            result_dict['last_error'] = str(e)
            result_dict['retry_count'] = 1
            return result_dict

    def _cache_result(self, movie_id, service_name, link, success, diagnostics=None, retry_count=None, last_error=None, selector_used=None):
        """Cache the scraping result with enhanced metadata."""
        if movie_id not in self.cache['movies']:
            self.cache['movies'][movie_id] = {}

        # Calculate expiration date
        cache_ttl_days = self.config.get('cache_ttl_days', 30)
        expires_at = datetime.now() + timedelta(days=cache_ttl_days)

        entry = {
            'streaming': {
                'service': service_name,
                'link': link
            },
            'scraped_at': datetime.now().isoformat(),
            'expires_at': expires_at.isoformat(),
            'source': 'agent_scraper',
            'success': success
        }

        # Add diagnostic metadata
        if retry_count is not None:
            entry['retry_count'] = retry_count
        if last_error is not None:
            entry['last_error'] = last_error
        if selector_used is not None:
            entry['selector_used'] = selector_used

        # Add diagnostics if provided (for backward compatibility)
        if diagnostics:
            # Rename 'error' field to 'last_error' if present
            if 'error' in diagnostics:
                diagnostics['last_error'] = diagnostics.pop('error')
            entry.update(diagnostics)

        self.cache['movies'][movie_id] = entry

    def close(self):
        """Cleanup method to quit browser and save cache."""
        print("[AgentLinkScraper] Closing browser and saving cache...")

        self._cleanup_browser()
        print("[AgentLinkScraper] ✓ Browser closed")

        self._save_cache()
        print("[AgentLinkScraper] ✓ Cleanup complete")


class BasePlatformScraper:
    """Base class for platform-specific scrapers."""

    def __init__(self, page, config):
        self.page = page
        self.config = config

    def find_watch_link(self, title, year):
        """Override in subclasses to implement platform-specific logic."""
        raise NotImplementedError


class NetflixScraper(BasePlatformScraper):
    """Scraper for Netflix watch links using Playwright."""

    SELECTORS = [
        ".title-card a",
        "[data-uia='title-card'] a",
        ".search-result a",
        "a[href*='/title/']",
        "[data-testid='movie-card'] a",
        ".gallery-lockups a"
    ]

    def find_watch_link(self, title, year):
        """Find Netflix watch link by searching for the movie."""
        try:
            search_url = f"https://www.netflix.com/search?q={quote(title)}"
            print(f"[NetflixScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short initial wait for dynamic content
            self.page.wait_for_timeout(500)

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    print(f"[NetflixScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        print(f"[NetflixScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            # Check first few elements for valid Netflix links
                            for j, element in enumerate(elements[:3]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and 'netflix.com/title/' in href:
                                        print(f"[NetflixScraper] ✓ Found Netflix link for {title} using selector {selector}")
                                        return {
                                            'link': href,
                                            'selector_used': selector
                                        }
                                except Exception as e:
                                    print(f"[NetflixScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        print(f"[NetflixScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    print(f"[NetflixScraper] Error with selector {selector}: {e}")
                    continue

            print(f"[NetflixScraper] ✗ No valid Netflix links found for: {title}")
            return None

        except Exception as e:
            print(f"[NetflixScraper] ✗ Netflix scraping error for {title}: {e}")
            return None


class DisneyPlusScraper(BasePlatformScraper):
    """Scraper for Disney+ watch links using Playwright."""

    SELECTORS = [
        "[data-testid='search-result'] a",
        ".search-result a",
        "[data-testid='movie-card'] a",
        "a[href*='/movies/']",
        "a[href*='/video/']"
    ]

    def find_watch_link(self, title, year):
        """Find Disney+ watch link by searching for the movie."""
        try:
            search_url = f"https://www.disneyplus.com/search?q={quote(title)}"
            print(f"[DisneyPlusScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short initial wait for dynamic content
            self.page.wait_for_timeout(500)

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    print(f"[DisneyPlusScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        print(f"[DisneyPlusScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            for j, element in enumerate(elements[:3]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and ('disneyplus.com/movies/' in href or 'disneyplus.com/video/' in href):
                                        print(f"[DisneyPlusScraper] ✓ Found Disney+ link for {title} using selector {selector}")
                                        return {
                                            'link': href,
                                            'selector_used': selector
                                        }
                                except Exception as e:
                                    print(f"[DisneyPlusScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        print(f"[DisneyPlusScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    print(f"[DisneyPlusScraper] Error with selector {selector}: {e}")
                    continue

            print(f"[DisneyPlusScraper] ✗ No valid Disney+ links found for: {title}")
            return None

        except Exception as e:
            print(f"[DisneyPlusScraper] ✗ Disney+ scraping error for {title}: {e}")
            return None


class HBOMaxScraper(BasePlatformScraper):
    """Scraper for HBO Max/Max watch links using Playwright."""

    SELECTORS = [
        ".search-result a",
        "[data-testid='tile'] a",
        "[data-testid='movie-card'] a",
        "a[href*='/movies/']",
        ".content-card a"
    ]

    def find_watch_link(self, title, year):
        """Find HBO Max/Max watch link by searching for the movie."""
        try:
            search_url = f"https://www.max.com/search?q={quote(title)}"
            print(f"[HBOMaxScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short initial wait for dynamic content
            self.page.wait_for_timeout(500)

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    print(f"[HBOMaxScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        print(f"[HBOMaxScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            for j, element in enumerate(elements[:3]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and 'max.com/movies/' in href:
                                        print(f"[HBOMaxScraper] ✓ Found Max link for {title} using selector {selector}")
                                        return {
                                            'link': href,
                                            'selector_used': selector
                                        }
                                except Exception as e:
                                    print(f"[HBOMaxScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        print(f"[HBOMaxScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    print(f"[HBOMaxScraper] Error with selector {selector}: {e}")
                    continue

            print(f"[HBOMaxScraper] ✗ No valid Max links found for: {title}")
            return None

        except Exception as e:
            print(f"[HBOMaxScraper] ✗ Max scraping error for {title}: {e}")
            return None


class HuluScraper(BasePlatformScraper):
    """Scraper for Hulu watch links using Playwright."""

    SELECTORS = [
        ".entity-card a",
        ".search-results a",
        "[data-testid='movie-card'] a",
        "a[href*='/movie/']",
        "a[href*='/watch/']"
    ]

    def find_watch_link(self, title, year):
        """Find Hulu watch link by searching for the movie."""
        try:
            search_url = f"https://www.hulu.com/search?q={quote(title)}"
            print(f"[HuluScraper] Navigating to: {search_url}")
            self.page.goto(search_url, wait_until='networkidle')

            # Short initial wait for dynamic content
            self.page.wait_for_timeout(500)

            # Try each selector sequentially
            for i, selector in enumerate(self.SELECTORS):
                try:
                    print(f"[HuluScraper] Trying selector {i+1}/{len(self.SELECTORS)}: {selector}")

                    # Use configurable timeout for selector wait
                    timeout_ms = self.config.get('timeout', 10) * 1000
                    try:
                        self.page.wait_for_selector(selector, timeout=timeout_ms)
                        elements = self.page.locator(selector).all()
                        print(f"[HuluScraper] Found {len(elements)} elements with selector: {selector}")

                        if elements:
                            for j, element in enumerate(elements[:3]):
                                try:
                                    href = element.get_attribute('href')
                                    if href and ('hulu.com/movie/' in href or 'hulu.com/watch/' in href):
                                        print(f"[HuluScraper] ✓ Found Hulu link for {title} using selector {selector}")
                                        return {
                                            'link': href,
                                            'selector_used': selector
                                        }
                                except Exception as e:
                                    print(f"[HuluScraper] Error checking element {j}: {e}")
                                    continue

                    except PlaywrightTimeoutError:
                        print(f"[HuluScraper] Selector not found within timeout: {selector}")
                        continue

                except Exception as e:
                    print(f"[HuluScraper] Error with selector {selector}: {e}")
                    continue

            print(f"[HuluScraper] ✗ No valid Hulu links found for: {title}")
            return None

        except Exception as e:
            print(f"[HuluScraper] ✗ Hulu scraping error for {title}: {e}")
            return None