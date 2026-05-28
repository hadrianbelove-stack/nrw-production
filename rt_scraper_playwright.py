#!/usr/bin/env python3
"""
Rotten Tomatoes Scraper — Playwright-based RT score and URL finder.

Inherits from PlaywrightScraperBase for shared browser management.
RT-specific: stealth scripts (anti-bot), search + URL construction,
score extraction waterfall (JSON-LD → media-scorecard → CSS → regex).
"""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import time
import json
import os
import random
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from scraper_base import PlaywrightScraperBase
from gemini_scraper.rt_validation import page_title_matches


class RTScraperPlaywright(PlaywrightScraperBase):
    """Rotten Tomatoes scraper using Playwright for scores and URLs."""

    def __init__(self, cache_file='cache/rt_cache.json', config=None, logger=None):
        """Initialize the RT scraper with configuration.

        Args:
            cache_file: Path to cache file for RT scores
            config: Configuration dict with rt_scraper settings
            logger: Logger instance for output
        """
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger,
            config_key='rt_scraper',
            log_prefix='RTScraperPlaywright',
            screenshot_subdir='rt'
        )

        # RT uses a shorter default rate limit
        if self.rate_limit == 2.0:  # Base class default
            self.rate_limit = 1.5  # RT default

        self._log(f"RT Scraper initialized with cache_file={cache_file}")

    def _init_browser_shared(self):
        """Initialize browser using shared manager with RT-specific stealth scripts.

        Overrides base to add anti-bot detection scripts.
        """
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

            # RT-SPECIFIC: Hide automation signals to avoid bot detection
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
            timeout_ms = self.scraper_config.get('timeout', 15) * 1000
            self.context.set_default_timeout(timeout_ms)

            # Create page
            self.page = self.context.new_page()

            self._log("Playwright browser initialized successfully via shared manager")
            self.counters['start_count'] += 1

        except Exception as e:
            self._log(f"Browser initialization failed: {e}", level='error')
            self.counters['error_count'] += 1
            self._cleanup_browser()
            raise

    def _cleanup_browser(self):
        """Clean up browser resources with RT-specific metrics logging."""
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
        if self.browser:
            self.browser = None

        # Cleanup Playwright via shared manager
        if self.playwright:
            try:
                self.manager.release()
            except:
                pass
            self.playwright = None

    def _retry_with_backoff(self, fn, max_attempts=None, base_delay=None, max_delay=None, jitter_ratio=None):
        """Retry function with exponential backoff and RT-specific metrics."""
        if max_attempts is None:
            max_attempts = self.scraper_config.get('max_retries', 3)

        # Get exponential backoff config values
        backoff_config = self.scraper_config.get('exponential_backoff', {})
        if base_delay is None:
            base_delay = backoff_config.get('base_delay', 0.5)
        if max_delay is None:
            max_delay = backoff_config.get('max_delay', 5.0)
        if jitter_ratio is None:
            jitter_ratio = backoff_config.get('jitter_ratio', 0.2)

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
            os.makedirs(self.screenshot_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:50]
            filename_base = f"{safe_title}_{year}_{timestamp}"

            screenshot_path = os.path.join(self.screenshot_dir, f"{filename_base}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)

            html_path = os.path.join(self.screenshot_dir, f"{filename_base}.html")
            html_content = self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self._log(f"Screenshot saved: {screenshot_path}")
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

    def _extract_score_from_rt_page(self, rt_url):
        """Navigate to RT page and extract the actual score.

        Extraction waterfall:
        1. JSON-LD structured data (most reliable — deterministic)
        2. CSS selectors (deterministic)
        3. Text regex patterns (deterministic fallback)

        Args:
            rt_url: The Rotten Tomatoes URL to scrape

        Returns:
            str: The score (e.g., "85%") or None if not found
        """
        try:
            self._log(f"Navigating to RT page: {rt_url}", level='debug')
            self.page.goto(rt_url, wait_until='domcontentloaded')
            time.sleep(2)  # Wait for dynamic content to load

            # 1. JSON-LD structured data (most reliable)
            try:
                json_ld_scripts = self.page.query_selector_all('script[type="application/ld+json"]')
                for script in json_ld_scripts:
                    try:
                        data = json.loads(script.text_content() or '{}')
                        if 'aggregateRating' in data:
                            rating = data['aggregateRating'].get('ratingValue')
                            if rating:
                                score = str(int(float(rating)))
                                self._log(f"Found score via JSON-LD: {score}% on {rt_url}", level='debug')
                                return f"{score}%"
                    except (json.JSONDecodeError, ValueError):
                        continue
            except Exception as e:
                self._log(f"JSON-LD extraction error: {e}", level='debug')

            # 2. media-scorecard (current RT layout since ~2025)
            try:
                scorecard = self.page.query_selector('media-scorecard')
                if scorecard:
                    text = (scorecard.text_content() or "").strip()
                    score_match = re.search(r'(\d{1,3})%', text)
                    if score_match:
                        score = int(score_match.group(1))
                        if 0 <= score <= 100:
                            self._log(f"Found score via media-scorecard: {score}%", level='debug')
                            return f"{score}%"
            except Exception:
                pass

            # 3. CSS selectors (legacy layouts)
            score_selectors = [
                '[slot="criticsScore"]',
                'rt-text[slot="criticsScore"]',
                '[data-testid="critic-score"] .percentage',
                '[data-testid="critics-score"] .percentage',
                '[class*="criticsScore"]',
                'score-board',
                '.scoreboard__critic .percentage',
                '.mop-ratings-wrap__percentage',
                '.meter-value',
                '.critic-score .percentage',
                '[class*="percentage"]',
            ]

            for selector in score_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        text = (element.text_content() or "").strip()
                        score_match = re.search(r'(\d+)%?', text)
                        if score_match:
                            self._log(f"Found score on RT page: {score_match.group(1)}% (selector: {selector})", level='debug')
                            return f"{score_match.group(1)}%"
                except Exception as e:
                    self._log(f"Error with selector {selector}: {e}", level='debug')
                    continue

            # 4. Text regex patterns (fallback)
            try:
                body_element = self.page.query_selector('body')
                if body_element:
                    page_text = body_element.text_content()
                    score_patterns = [
                        r'(\d+)%\s*Tomatometer',
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

    def _construct_rt_url(self, title, year):
        """Construct likely RT URLs directly without Google search.

        Args:
            title: Movie title
            year: Release year

        Returns:
            list: List of candidate RT URLs to try
        """
        # Normalize title for RT URL format
        normalized = title.lower()

        # Remove common prefixes/suffixes that RT might not include
        normalized = re.sub(r'^(the|a|an)\s+', '', normalized)

        # Replace problematic characters
        normalized = re.sub(r'[:\'".,!?;]', '', normalized)
        normalized = re.sub(r'\s+', '_', normalized)
        normalized = re.sub(r'[^a-z0-9_]', '', normalized)

        # Generate candidate URLs
        candidates = [
            f"https://www.rottentomatoes.com/m/{normalized}_{year}",
            f"https://www.rottentomatoes.com/m/{normalized}",
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
        URL construction (which guesses wrong slugs).

        Args:
            title: Movie title
            year: Release year

        Returns:
            str: RT movie URL if found, None otherwise
        """
        try:
            search_url = f"https://www.rottentomatoes.com/search?search={quote(title)}"
            self._log(f"RT search: {search_url}", level='debug')

            self.page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(2)

            movie_links = self.page.query_selector_all('a[href*="/m/"]')

            if not movie_links:
                self._log(f"No movie links found in RT search for {title}", level='debug')
                return None

            self._log(f"Found {len(movie_links)} movie links in RT search", level='debug')

            candidates = []
            _stop_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'and', 'or', 'is', 'it'}
            title_words = set(re.sub(r'[^a-z0-9\s]', '', title.lower()).split()) - _stop_words
            title_slug = re.sub(r'[^a-z0-9]', '', title.lower())

            for link in movie_links:
                href = link.get_attribute('href')
                if href and '/m/' in href:
                    if href.startswith('/m/'):
                        full_url = f"https://www.rottentomatoes.com{href}"
                    else:
                        full_url = href

                    slug = href.split('/m/')[-1].split('/')[0].split('?')[0]
                    slug_normalized = re.sub(r'[^a-z0-9]', '', slug.lower())

                    if full_url in [c[0] for c in candidates]:
                        continue

                    try:
                        parent = link.evaluate('el => el.closest("search-page-media-row")?.textContent || ""')
                    except:
                        parent = ''

                    slug_words = set(slug.lower().replace('_', ' ').split()) - _stop_words
                    word_matches = len(title_words & slug_words)

                    candidates.append((full_url, parent, word_matches, slug_normalized))

            if not candidates:
                return None

            candidates.sort(key=lambda x: x[2], reverse=True)

            # For short titles (1-2 words), require full slug substring match
            # to avoid "Boss" matching "Boss Baby" or "Others" matching "Lives of Others"
            title_word_count = len(title_words)

            def is_good_match(word_matches, slug_normalized):
                if title_slug in slug_normalized:
                    return True  # Full title is substring of slug — always good
                if title_word_count <= 2:
                    return False  # Short titles need exact substring match
                return word_matches >= 2  # Longer titles: 2+ word overlap OK

            year_str = str(year)
            for url, context, word_matches, slug_normalized in candidates:
                if is_good_match(word_matches, slug_normalized):
                    if year_str in context or year_str in url:
                        self._log(f"RT search found year+title match: {url}", level='debug')
                        return url

            for url, context, word_matches, slug_normalized in candidates:
                if is_good_match(word_matches, slug_normalized):
                    # Reject if context shows a year that's clearly wrong
                    context_years = re.findall(r'\b(19\d{2}|20\d{2})\b', context)
                    if context_years:
                        best_year = min(context_years, key=lambda y: abs(int(y) - year))
                        if abs(int(best_year) - year) > 1:
                            self._log(f"RT search skipping year mismatch: {url} (context year {best_year}, expected {year})", level='debug')
                            continue
                    # Reject substring matches where slug has extra non-year content
                    # e.g. "30minutes" in "30minutesorless" — the "orless" means different movie
                    if title_slug in slug_normalized and title_slug != slug_normalized:
                        extra = slug_normalized.replace(title_slug, '', 1)
                        if not re.match(r'^\d{4}$', extra):
                            self._log(f"RT search skipping partial slug match: {url} (extra content: '{extra}')", level='debug')
                            continue
                    self._log(f"RT search found title match: {url}", level='debug')
                    return url

            self._log(f"RT search: no good matches found among {len(candidates)} links", level='debug')
            return None

        except Exception as e:
            self._log(f"RT search error for {title}: {e}", level='error')
            return None

    def _scrape_rt_page(self, title, year):
        """Find RT page URL and extract score.

        Strategy order:
        1. RT search page (most reliable)
        2. Direct URL construction (fallback)

        Args:
            title: Movie title
            year: Release year

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        self._init_browser()
        self._enforce_rate_limit()
        self.stats['attempts'] += 1

        rt_link = None
        rt_score = None

        try:
            # Primary method: Search RT directly
            rt_link = self._search_rt_directly(title, year)

            if rt_link:
                self._log(f"RT search found: {rt_link}", level='debug')
            else:
                # Fallback: Try direct URL construction
                self._log(f"RT search failed, trying URL construction for {title} ({year})", level='debug')
                candidate_urls = self._construct_rt_url(title, year)

                for candidate_url in candidate_urls:
                    self._log(f"Trying direct URL: {candidate_url}", level='debug')

                    response = self.page.goto(candidate_url, wait_until='domcontentloaded')
                    time.sleep(1)

                    # Check HTTP status code first
                    if response and response.status >= 400:
                        continue

                    page_title_raw = self.page.title() or ''
                    page_title_lower = page_title_raw.lower()
                    if ('rotten tomatoes' in page_title_lower and
                        'not found' not in page_title_lower and
                        '404' not in page_title_lower):
                        # Extract movie title from RT format: "Movie Name (YYYY) | Rotten Tomatoes"
                        movie_part = page_title_raw.split('|')[0].strip() if '|' in page_title_raw else page_title_raw.strip()
                        # Year check: reject if page year is >1 year off
                        page_year_match = re.search(r'\((\d{4})\)', movie_part)
                        if page_year_match and year:
                            page_year = int(page_year_match.group(1))
                            if abs(page_year - int(year)) > 1:
                                self._log(f"URL construction: year mismatch {page_year} vs {year} for {candidate_url}", level='debug')
                                continue
                        # Title check: extract movie name and verify
                        page_movie_title = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_part).strip()
                        if page_title_matches(page_movie_title, title):
                            rt_link = candidate_url
                            self._log(f"URL construction: title+year verified for {candidate_url}", level='debug')
                            break
                        else:
                            self._log(f"URL construction: title mismatch - page='{page_movie_title}', expected='{title}'", level='debug')

            if not rt_link:
                self._log(f"No RT link found for {title} ({year})", level='warning')
                cache_key = f"{title}_{year}"
                self.cache[cache_key] = {
                    'url': None,
                    'score': None,
                    'title': title,
                    'scraped_at': datetime.now().isoformat()
                }
                self._save_cache()
                self.stats['failures'] += 1
                self.record_error('not_found')
                return None

            rt_score = self._extract_score_from_rt_page(rt_link)

            # Year verification: reject wrong-year matches (e.g. "30 Minutes" 2025 → "30 Minutes or Less" 2011)
            try:
                page_year = None
                # Try 1: Page title often has "(YYYY)" for newer movies
                page_title = self.page.title() or ""
                year_match = re.search(r'\((\d{4})\)', page_title)
                if year_match:
                    page_year = int(year_match.group(1))
                # Try 2: JSON-LD releasedEvent or year from page content
                # NOTE: dateCreated is unreliable — it's the RT page creation date,
                # not the movie release year (e.g. Son-In-Law 1993 shows dateCreated: 2026-05-01)
                if page_year is None:
                    try:
                        json_ld_scripts = self.page.query_selector_all('script[type="application/ld+json"]')
                        for script in json_ld_scripts:
                            try:
                                data = json.loads(script.text_content() or '{}')
                                # Check releasedEvent.startDate if present
                                released = data.get('releasedEvent', {})
                                if isinstance(released, dict):
                                    start_date = released.get('startDate', '')
                                    if start_date:
                                        ym = re.search(r'(\d{4})', str(start_date))
                                        if ym:
                                            page_year = int(ym.group(1))
                                            break
                            except (json.JSONDecodeError, ValueError):
                                continue
                    except Exception:
                        pass
                if page_year is None:
                    self._log(f"Year verification failed: could not extract year from RT page — rejecting {rt_link}", level='warning')
                    rt_link = None
                    rt_score = None
                elif abs(page_year - year) > 1:
                    self._log(f"Year mismatch: page has {page_year}, expected {year} — rejecting {rt_link}", level='warning')
                    rt_link = None
                    rt_score = None
            except Exception as e:
                self._log(f"Year verification error: {e} — rejecting {rt_link}", level='warning')
                rt_link = None
                rt_score = None

            if not rt_link:
                self._log(f"No RT link found for {title} ({year})", level='warning')
                cache_key = f"{title}_{year}"
                self.cache[cache_key] = {
                    'url': None,
                    'score': None,
                    'title': title,
                    'scraped_at': datetime.now().isoformat()
                }
                self._save_cache()
                self.stats['failures'] += 1
                self.record_error('year_mismatch')
                return None

            result = {
                'url': rt_link,
                'score': rt_score
            }

            self._log(f"Success: {rt_link} (Score: {rt_score or 'N/A'})", level='debug')

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

            cache_key = f"{title}_{year}"
            self.cache[cache_key] = {
                'url': None,
                'score': None,
                'title': title,
                'scraped_at': datetime.now().isoformat()
            }
            self._save_cache()
            self.stats['failures'] += 1
            self.record_error(type(e).__name__)
            return None

    def scrape_rt_score(self, title, year):
        """Public wrapper function to scrape RT score with caching and retry logic.

        Args:
            title: Movie title
            year: Release year

        Returns:
            dict: {'url': ..., 'score': ...} or None if not found
        """
        cache_key = f"{title}_{year}"
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]

            if not self._is_cache_expired(cached_data):
                self.stats['cache_hits'] += 1
                self._log(f"Cache hit for {title} ({year})", level='debug')

                return {
                    'url': cached_data.get('url'),
                    'score': cached_data.get('score')
                } if cached_data.get('url') or cached_data.get('score') else None

        result = self._retry_with_backoff(lambda: self._scrape_rt_page(title, year))
        return result

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
        self._log("RT Scraper closed")


