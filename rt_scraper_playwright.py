from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import random
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from constants import get_scraper_config

# Shared manager support (enabled by default)
from playwright_manager import get_playwright_manager


class RTScraperPlaywright:
    """Rotten Tomatoes scraper using Playwright for scores and URLs."""

    def __init__(self, cache_file='cache/rt_cache.json', config=None, logger=None):
        """Initialize the RT scraper with configuration.

        Args:
            cache_file: Path to cache file for RT scores
            config: Configuration dict with rt_scraper settings
            logger: Logger instance for output
        """
        self.cache_file = cache_file
        self.config = config or {}
        self.logger = logger

        # Apply scraper defaults
        self.scraper_config = get_scraper_config(config, 'rt_scraper')

        # Browser components (lazy initialization)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Manager reference
        self.manager = get_playwright_manager()


        # Rate limiting
        self.last_scrape_time = 0
        # Fix: use 'is not None' to allow rate_limit of 0
        rate_limit = self.scraper_config.get('rate_limit')
        self.rate_limit = rate_limit if rate_limit is not None else 1.5

        # Cache
        self.cache = self._load_cache()

        # Screenshots for diagnostics
        self.screenshot_dir = 'cache/screenshots/rt'
        self.screenshots_enabled = self.scraper_config.get('screenshots_enabled')

        # Operational counters for structured logging (integrated with existing stats)
        self.counters = {
            'start_count': 0,
            'stop_count': 0,
            'retry_count': 0,
            'error_count': 0
        }

        # Clean up old screenshots on initialization
        if self.screenshots_enabled:
            self._cleanup_old_screenshots()

        # Stats
        self.stats = {
            'attempts': 0,
            'successes': 0,
            'cache_hits': 0,
            'failures': 0
        }

        self._log(f"RT Scraper initialized with Playwright, cache_file={cache_file}")
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
            print(f"[RTScraperPlaywright] {message}")



    def _log_metrics(self, operation, data):
        """Log structured metrics for operations."""
        metrics_data = {
            'timestamp': datetime.now().isoformat(),
            'component': 'rt_scraper_playwright',
            'operation': operation,
            'counters': self.counters.copy(),
            'stats': getattr(self, 'stats', {}).copy(),
            'data': data
        }

        if self.logger:
            self.logger.info(f"METRICS: {json.dumps(metrics_data)}")
        else:
            print(f"[RTScraperPlaywright] METRICS: {json.dumps(metrics_data)}")

    def _load_cache(self):
        """Load RT cache from disk."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                self._log(f"Failed to load cache: {e}", level='warning')
        return {}

    def _save_cache(self):
        """Save RT cache to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            self._log(f"Cache saved: {len(self.cache)} entries", level='debug')
        except Exception as e:
            self._log(f"Failed to save cache: {e}", level='error')

    def _extract_score_from_rt_page(self, rt_url):
        """Navigate to RT page and extract the actual score.

        Args:
            rt_url: The Rotten Tomatoes URL to scrape

        Returns:
            str: The score (e.g., "85%") or None if not found
        """
        try:
            self._log(f"Navigating to RT page: {rt_url}", level='debug')
            self.page.goto(rt_url, wait_until='domcontentloaded')
            time.sleep(2)  # Wait for dynamic content to load

            # RT score selectors (Rotten Tomatoes uses various formats)
            score_selectors = [
                # Modern RT pages - critic score
                '[data-testid="critic-score"] .percentage',
                '[data-testid="critics-score"] .percentage',
                # Alternative modern selectors
                '.scoreboard__critic .percentage',
                '.scoreboard__critic score-icon-critic-fresh .percentage',
                '.scoreboard__critic score-icon-critic-rotten .percentage',
                # Legacy selectors
                '.mop-ratings-wrap__percentage',
                '.meter-value',
                '.critic-score .percentage',
                # General percentage patterns
                '[class*="percentage"]',
                '[class*="score"] [class*="percentage"]'
            ]

            for selector in score_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        text = element.text_content() or ""
                        text = text.strip()

                        # Look for percentage pattern
                        score_match = re.search(r'(\d+)%?', text)
                        if score_match:
                            score = score_match.group(1)
                            self._log(f"Found score on RT page: {score}% (selector: {selector})", level='debug')
                            return f"{score}%"

                except Exception as e:
                    self._log(f"Error with selector {selector}: {e}", level='debug')
                    continue

            # If no score found with selectors, try extracting from page text
            try:
                # Get the text content of the body element
                body_element = self.page.query_selector('body')
                if body_element:
                    page_text = body_element.text_content()
                    # Look for patterns like "85% Critics" or "Fresh 85%"
                    score_patterns = [
                        r'(\d+)%\s*(?:Critics|Critic)',
                        r'(?:Fresh|Rotten)\s*(\d+)%',
                        r'Tomatometer.*?(\d+)%',
                    ]

                    for pattern in score_patterns:
                        match = re.search(pattern, page_text, re.IGNORECASE)
                        if match:
                            score = match.group(1)
                            self._log(f"Found score in page text: {score}% (pattern: {pattern})", level='debug')
                            return f"{score}%"

            except Exception as e:
                self._log(f"Error extracting score from page text: {e}", level='debug')

            self._log(f"No score found on RT page: {rt_url}", level='warning')
            return None

        except Exception as e:
            self._log(f"Error navigating to RT page {rt_url}: {e}", level='error')
            return None

    def _cleanup_old_screenshots(self):
        """Delete old screenshots based on retention policy."""
        if not self.screenshots_enabled or not os.path.exists(self.screenshot_dir):
            return

        try:
            retention_days = self.config.get('rt_scraper', {}).get('screenshot_retention_days', 7)
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

        self.counters['start_count'] += 1
        self._log_metrics("browser_start", {"start_count": self.counters['start_count']})

        self._log("Initializing Playwright browser via shared manager...")
        self._init_browser_shared()

    def _init_browser_shared(self):
        """Initialize browser using shared manager."""
        try:
            # Get shared Playwright instance
            self.playwright = self.manager.get_playwright()

            # Get shared browser from PlaywrightManager
            headless = self.config.get('rt_scraper', {}).get('headless', True)
            self.browser = self.manager.get_browser(headless=headless, browser_type='chromium')

            # Create context with viewport and user agent (stealth configuration)
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Hide automation signals
            self.context.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                // Add fake chrome runtime
                Object.defineProperty(window, 'chrome', {
                    get: () => ({
                        runtime: {},
                    }),
                });

                // Override plugins length
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });

                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            # Set default timeout
            timeout_ms = self.scraper_config.get('timeout') * 1000
            self.context.set_default_timeout(timeout_ms)

            # Create page
            self.page = self.context.new_page()

            self._log("Playwright browser initialized successfully via shared manager")

        except Exception as e:
            self._log(f"Browser initialization failed: {e}", level='error')
            self._cleanup_browser()
            raise

    def _init_browser_local(self):
        """Initialize browser using local lifecycle."""
        try:
            # Start Playwright locally
            self.playwright = sync_playwright().start()

            # Launch browser
            headless = self.config.get('rt_scraper', {}).get('headless', True)
            self.browser = self.playwright.chromium.launch(headless=headless)

            # Create context with viewport and user agent (stealth configuration)
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Hide automation signals
            self.context.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                // Add fake chrome runtime
                Object.defineProperty(window, 'chrome', {
                    get: () => ({
                        runtime: {},
                    }),
                });

                // Override plugins length
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });

                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            # Set default timeout
            timeout_ms = self.scraper_config.get('timeout') * 1000
            self.context.set_default_timeout(timeout_ms)

            # Create page
            self.page = self.context.new_page()

            self._log("Playwright browser initialized successfully with local lifecycle")

        except Exception as e:
            self._log(f"Browser initialization failed: {e}", level='error')
            self._cleanup_browser()
            raise

    def _cleanup_browser(self):
        """Clean up browser resources."""
        self.counters['stop_count'] += 1
        self._log_metrics("browser_stop", {"stop_count": self.counters['stop_count']})

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

        # Browser is managed by PlaywrightManager - don't close it directly
        # Only release our reference to allow proper cleanup
        if self.browser:
            self.browser = None

        # Cleanup Playwright via shared manager
        if self.playwright:
            try:
                self.manager.release()
            except:
                pass
            self.playwright = None

    def _rate_limit(self):
        """Enforce minimum delay between RT scrapes to avoid anti-bot detection."""
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
            max_attempts = self.scraper_config.get('max_retries')

        # Get exponential backoff config values
        backoff_config = self.scraper_config.get('exponential_backoff', {})
        if base_delay is None:
            base_delay = backoff_config.get('base_delay')
        if max_delay is None:
            max_delay = backoff_config.get('max_delay')
        if jitter_ratio is None:
            jitter_ratio = backoff_config.get('jitter_ratio')

        last_error = None
        for attempt in range(max_attempts):
            if attempt > 0:
                self.counters['retry_count'] += 1
                self._log_metrics("retry_attempt", {"attempt": attempt, "max_attempts": max_attempts})

            try:
                result = fn()
                if result is not None:
                    # Add retry metadata
                    if isinstance(result, dict):
                        result['retry_count'] = attempt + 1
                        if last_error:
                            result['last_error'] = str(last_error)
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
                self.counters['error_count'] += 1
                self._log_metrics("scrape_error", {"attempt": attempt + 1, "error": str(e), "error_type": type(e).__name__})
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

    def _is_cache_expired(self, cached_entry):
        """Check if cache entry has expired (90-day TTL)."""
        if 'scraped_at' not in cached_entry:
            return True

        try:
            scraped_at = datetime.fromisoformat(cached_entry['scraped_at'])
            cache_ttl_days = self.config.get('rt_scraper', {}).get('cache_ttl_days', 90)
            expires_at = scraped_at + timedelta(days=cache_ttl_days)
            return datetime.now() > expires_at
        except (ValueError, KeyError):
            return True

    def _construct_rt_url(self, title, year):
        """Construct likely RT URLs directly without Google search.

        Args:
            title: Movie title
            year: Release year

        Returns:
            list: List of candidate RT URLs to try
        """
        import re

        # Normalize title for RT URL format
        # RT URLs use lowercase, replace spaces/punctuation with underscores
        normalized = title.lower()

        # Remove common prefixes/suffixes that RT might not include
        normalized = re.sub(r'^(the|a|an)\s+', '', normalized)

        # Replace problematic characters
        normalized = re.sub(r'[:\'".,!?;]', '', normalized)  # Remove punctuation
        normalized = re.sub(r'\s+', '_', normalized)  # Spaces to underscores
        normalized = re.sub(r'[^a-z0-9_]', '', normalized)  # Keep only safe chars

        # Generate candidate URLs
        candidates = [
            f"https://www.rottentomatoes.com/m/{normalized}_{year}",  # title_year
            f"https://www.rottentomatoes.com/m/{normalized}",  # title_only
        ]

        # If title has "the" removed, also try with original
        if not title.lower().startswith(('the ', 'a ', 'an ')):
            original_normalized = title.lower()
            original_normalized = re.sub(r'[:\'".,!?;]', '', original_normalized)
            original_normalized = re.sub(r'\s+', '_', original_normalized)
            original_normalized = re.sub(r'[^a-z0-9_]', '', original_normalized)
            candidates.extend([
                f"https://www.rottentomatoes.com/m/{original_normalized}_{year}",
                f"https://www.rottentomatoes.com/m/{original_normalized}",
            ])

        return candidates

    def _search_rt_directly(self, title, year):
        """Search RT's own search page to find movie URL.

        This is more reliable than Google search (which gets blocked) or
        URL construction (which guesses wrong slugs like wicked_2024 vs wicked_for_good).

        Args:
            title: Movie title
            year: Release year

        Returns:
            str: RT movie URL if found, None otherwise
        """
        try:
            # Build RT search URL
            search_url = f"https://www.rottentomatoes.com/search?search={quote(title)}"
            self._log(f"RT search: {search_url}", level='debug')

            # Navigate to RT search page
            self.page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(2)  # Wait for dynamic content to load

            # Find all movie links in search results
            movie_links = self.page.query_selector_all('a[href*="/m/"]')

            if not movie_links:
                self._log(f"No movie links found in RT search for {title}", level='debug')
                return None

            self._log(f"Found {len(movie_links)} movie links in RT search", level='debug')

            # Extract hrefs and filter for valid movie pages
            candidates = []

            # Normalize title for URL matching
            title_words = set(re.sub(r'[^a-z0-9\s]', '', title.lower()).split())
            title_slug = re.sub(r'[^a-z0-9]', '', title.lower())

            for link in movie_links:
                href = link.get_attribute('href')
                if href and '/m/' in href:
                    # Normalize to full URL
                    if href.startswith('/m/'):
                        full_url = f"https://www.rottentomatoes.com{href}"
                    else:
                        full_url = href

                    # Extract slug from URL (e.g., "/m/wicked_for_good" -> "wicked_for_good")
                    slug = href.split('/m/')[-1].split('/')[0].split('?')[0]
                    slug_normalized = re.sub(r'[^a-z0-9]', '', slug.lower())

                    # Skip if already seen
                    if full_url in [c[0] for c in candidates]:
                        continue

                    # Try to get context from surrounding text
                    try:
                        parent = link.evaluate('el => el.closest("search-page-media-row")?.textContent || ""')
                    except:
                        parent = ''

                    # Calculate match score based on title words in URL
                    slug_words = set(slug.lower().replace('_', ' ').split())
                    word_matches = len(title_words & slug_words)

                    candidates.append((full_url, parent, word_matches, slug_normalized))

            if not candidates:
                return None

            # Sort by word matches (highest first)
            candidates.sort(key=lambda x: x[2], reverse=True)

            # Try to find best match by title and year
            year_str = str(year)
            for url, context, word_matches, slug_normalized in candidates:
                # Check if title is in slug
                if title_slug in slug_normalized or word_matches >= 2:
                    if year_str in context or year_str in url:
                        self._log(f"RT search found year+title match: {url}", level='debug')
                        return url

            # Try title match without year requirement
            for url, context, word_matches, slug_normalized in candidates:
                if title_slug in slug_normalized or word_matches >= 2:
                    self._log(f"RT search found title match: {url}", level='debug')
                    return url

            # Fallback to first result with any word matches
            if candidates[0][2] > 0:
                first_url = candidates[0][0]
                self._log(f"RT search using best word match: {first_url}", level='debug')
                return first_url

            self._log(f"RT search: no good matches found among {len(candidates)} links", level='debug')
            return None

        except Exception as e:
            self._log(f"RT search error for {title}: {e}", level='error')
            return None

    def _scrape_rt_page(self, title, year):
        """Find RT page URL and extract score.

        Strategy order:
        1. RT search page (most reliable - uses RT's own search)
        2. Direct URL construction (fallback for when RT search fails)

        Args:
            title: Movie title
            year: Release year

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        # Initialize browser if needed
        self._init_browser()

        # Apply rate limiting
        self._rate_limit()

        # Increment attempts counter
        self.stats['attempts'] += 1

        rt_link = None
        rt_score = None

        try:
            # Primary method: Search RT directly (most reliable)
            rt_link = self._search_rt_directly(title, year)

            if rt_link:
                self._log(f"RT search found: {rt_link}", level='debug')
            else:
                # Fallback: Try direct URL construction
                self._log(f"RT search failed, trying URL construction for {title} ({year})", level='debug')
                candidate_urls = self._construct_rt_url(title, year)

                for candidate_url in candidate_urls:
                    self._log(f"Trying direct URL: {candidate_url}", level='debug')

                    self.page.goto(candidate_url, wait_until='domcontentloaded')
                    time.sleep(1)

                    # Check if page exists (not a 404 or error page)
                    page_title = self.page.title().lower()
                    if ('rotten tomatoes' in page_title and
                        'not found' not in page_title and
                        '404' not in page_title):
                        rt_link = candidate_url
                        break

            if not rt_link:
                self._log(f"No RT link found for {title} ({year})", level='warning')
                # Cache the failure
                cache_key = f"{title}_{year}"
                self.cache[cache_key] = {
                    'url': None,
                    'score': None,
                    'title': title,
                    'scraped_at': datetime.now().isoformat()
                }
                self._save_cache()
                self.stats['failures'] += 1
                return None

            # Extract score from the RT page
            rt_score = self._extract_score_from_rt_page(rt_link)

            result = {
                'url': rt_link,
                'score': rt_score
            }

            self._log(f"Success: {rt_link} (Score: {rt_score or 'N/A'})", level='debug')

            # Cache the result
            cache_key = f"{title}_{year}"
            self.cache[cache_key] = {
                'url': result['url'],
                'score': result['score'],
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self._save_cache()
            self.stats['successes'] += 1

            return result

        except Exception as e:
            self._log(f"RT scrape error for {title} ({year}): {e}", level='error')

            # Cache the failure
            cache_key = f"{title}_{year}"
            self.cache[cache_key] = {
                'url': None,
                'score': None,
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self._save_cache()
            self.stats['failures'] += 1
            return None

    def scrape_rt_score(self, title, year):
        """Public wrapper function to scrape RT score with caching and retry logic.

        Args:
            title: Movie title
            year: Release year

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        # Check cache first
        cache_key = f"{title}_{year}"
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]

            # Check if cache entry has expired
            if not self._is_cache_expired(cached_data):
                self.stats['cache_hits'] += 1
                self._log(f"Cache hit for {title} ({year})", level='debug')

                # Return cached data (even if it's a failure)
                return {
                    'url': cached_data.get('url'),
                    'score': cached_data.get('score')
                } if cached_data.get('url') or cached_data.get('score') else None

        # Not in cache or expired, scrape with retry
        result = self._retry_with_backoff(lambda: self._scrape_rt_page(title, year))
        return result

    def get_stats(self):
        """Get scraper statistics."""
        return self.stats.copy()

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
        self._log("RT Scraper closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
