from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import random
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from difflib import SequenceMatcher
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
        self.rate_limit = self.scraper_config.get('rate_limit') or 1.5  # Default to 1.5s if not configured

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

    def _fuzzy_match_title(self, candidate_text, expected_title, threshold=0.8):
        """Fuzzy match candidate text against expected title.

        Args:
            candidate_text: Text from search result
            expected_title: Expected movie title
            threshold: Minimum similarity ratio (default: 0.6)

        Returns:
            bool: True if similarity ratio meets threshold
        """
        if not candidate_text or not expected_title:
            return False

        # Normalize both strings for comparison
        candidate_normalized = candidate_text.lower().strip()
        expected_normalized = expected_title.lower().strip()

        # Calculate similarity ratio
        similarity = SequenceMatcher(None, candidate_normalized, expected_normalized).ratio()

        return similarity >= threshold

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

            # Create context with viewport and user agent
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

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

            # Create context with viewport and user agent
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

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

    def _scrape_rt_page(self, title, year):
        """Scrape RT search page to find movie URL and score using Playwright.

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

        try:
            # Build search URL
            search_query = f"{title} {year}"
            search_url = f"https://www.rottentomatoes.com/search?search={quote(search_query)}"

            self._log(f"Searching RT: {title} ({year})", level='debug')

            # Navigate to search page
            self.page.goto(search_url, wait_until='domcontentloaded')
            time.sleep(2)  # Wait for dynamic content

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
                    elements = self.page.query_selector_all(selector)
                    if elements:
                        # Iterate through first 5-8 anchors and verify each candidate
                        for element in elements[:8]:
                            href = element.get_attribute('href')
                            if not href or '/m/' not in href:
                                continue

                            # Get anchor text and nearby title text
                            anchor_text = element.text_content() or ""

                            # Try to find surrounding title text
                            parent_element = element.evaluate_handle("el => el.closest('search-page-media-row') || el.parentElement")
                            surrounding_text = ""
                            try:
                                surrounding_text = parent_element.as_element().text_content() or ""
                            except:
                                surrounding_text = anchor_text

                            # Require fuzzy match against title at ~0.8 similarity
                            if not self._fuzzy_match_title(anchor_text, title, threshold=0.8):
                                self._log(f"Skipping candidate - title mismatch: {anchor_text[:50]}", level='debug')
                                continue

                            # Prefer candidates whose surrounding text contains the year
                            year_str = str(year)
                            has_year = year_str in surrounding_text

                            if has_year:
                                self._log(f"Found candidate with year match: {anchor_text[:50]}", level='debug')

                            # Ensure absolute URL
                            if href.startswith('http'):
                                candidate_url = href
                            else:
                                candidate_url = f"https://www.rottentomatoes.com{href}"

                            # Navigate to candidate movie page to validate
                            self._log(f"Validating candidate: {candidate_url}", level='debug')
                            self.page.goto(candidate_url, wait_until='domcontentloaded')
                            time.sleep(1)

                            # Read og:title meta or score-board data-qa-title to verify
                            validated = False
                            try:
                                # Try og:title meta tag
                                og_title_element = self.page.query_selector('meta[property="og:title"]')
                                if og_title_element:
                                    og_title = og_title_element.get_attribute('content') or ""
                                    if self._fuzzy_match_title(og_title, title, threshold=0.8):
                                        validated = True
                                        self._log(f"Validated via og:title: {og_title}", level='debug')

                                # Try score-board data-qa-title attribute
                                if not validated:
                                    score_board = self.page.query_selector('score-board')
                                    if score_board:
                                        qa_title = score_board.get_attribute('data-qa-title') or ""
                                        if self._fuzzy_match_title(qa_title, title, threshold=0.8):
                                            validated = True
                                            self._log(f"Validated via score-board: {qa_title}", level='debug')
                            except Exception as e:
                                self._log(f"Validation check error: {e}", level='debug')

                            if validated:
                                movie_url = candidate_url
                                self._log(f"Found validated match with selector: {selector}", level='debug')
                                break
                            else:
                                self._log(f"Validation failed for {candidate_url}, trying next", level='debug')
                                # Go back to search page for next candidate
                                self.page.goto(search_url, wait_until='domcontentloaded')
                                time.sleep(1)

                        if movie_url:
                            break
                except Exception as e:
                    self._log(f"Selector {selector} error: {e}", level='debug')
                    continue

            if not movie_url:
                self._log(f"No RT page found for {title} ({year})", level='warning')
                # Cache the failure
                cache_key = f"{title}_{year}"
                cached_failure = {
                    'url': None,
                    'score': None,
                    'title': title,
                    'scraped_at': datetime.now().isoformat()
                }
                self.cache[cache_key] = cached_failure
                self._save_cache()
                self.stats['failures'] += 1

                # Capture diagnostics
                self._capture_failure_diagnostics(title, year, "No RT page found")
                return None

            # Ensure we're on the movie page (may be redundant if validated during search)
            if self.page.url != movie_url:
                self.page.goto(movie_url, wait_until='domcontentloaded')
                time.sleep(2)  # Wait for dynamic content

            # Add readiness wait for score elements to avoid racing hydration
            try:
                self.page.wait_for_selector("score-board", timeout=2000)
            except:
                try:
                    self.page.wait_for_selector("[data-qa='tomatometer']", timeout=2000)
                except:
                    pass  # Continue if neither selector is found

            # Extract score - try attribute-based reading first
            score = None

            # Attempt 1: Try score-board attributes (preferred method)
            try:
                score_board = self.page.query_selector("score-board")
                if score_board:
                    # Try tomatometerscore attribute
                    tomatometer_score = score_board.get_attribute('tomatometerscore')
                    if tomatometer_score and tomatometer_score.isdigit():
                        score = f"{tomatometer_score}%"
                        self._log(f"Found score via score-board tomatometerscore attribute: {score}", level='debug')

                    # Fallback to audiencescore if tomatometer not found
                    if not score:
                        audience_score = score_board.get_attribute('audiencescore')
                        if audience_score and audience_score.isdigit():
                            score = f"{audience_score}%"
                            self._log(f"Found score via score-board audiencescore attribute: {score}", level='debug')
            except Exception as e:
                self._log(f"Attribute-based score extraction error: {e}", level='debug')

            # Attempt 2: Fallback to text/regex approach if attributes not available
            if not score:
                score_selectors = [
                    "rt-text[slot='criticsScore']",  # Primary
                    "score-board",  # Fallback 1
                    "[data-qa='tomatometer']",  # Fallback 2
                    "[data-qa='tomatometer-value']",  # Fallback 3
                    ".tomatometer-score",  # Fallback 4
                    "score-icon-critic"  # Fallback 5
                ]

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
                        element = self.page.query_selector(selector)
                        if element:
                            # Get text from multiple sources
                            text_sources = [
                                element.text_content() or "",
                                element.get_attribute('textContent') or "",
                                element.get_attribute('aria-label') or "",
                                element.get_attribute('data-score') or "",
                                element.inner_html() or ""
                            ]

                            # Concatenate all text sources for matching
                            combined_text = " ".join(text_sources).lower()

                            # Try each regex pattern until one matches
                            for pattern in regex_patterns:
                                match = re.search(pattern, combined_text, re.IGNORECASE)
                                if match:
                                    score = match.group(1) + "%"
                                    self._log(f"Found score with selector: {selector}, pattern: {pattern}", level='debug')
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

            self._log(f"RT scraping successful: {movie_url} (Score: {score or 'N/A'})", level='debug')

            # Cache the result
            cache_key = f"{title}_{year}"
            cached_result = {
                'url': result['url'],
                'score': result['score'],
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self.cache[cache_key] = cached_result
            self._save_cache()
            self.stats['successes'] += 1

            return result

        except Exception as e:
            self._log(f"RT scraping error for {title} ({year}): {e}", level='error')
            # Cache the failure
            cache_key = f"{title}_{year}"
            cached_failure = {
                'url': None,
                'score': None,
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self.cache[cache_key] = cached_failure
            self._save_cache()
            self.stats['failures'] += 1

            # Capture diagnostics
            self._capture_failure_diagnostics(title, year, str(e))
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
