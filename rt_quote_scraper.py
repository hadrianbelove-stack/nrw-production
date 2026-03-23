#!/usr/bin/env python3
"""
Rotten Tomatoes Critic Quote Scraper

Extracts real, verbatim pull quotes from RT review pages.
These are quotes submitted by publications themselves (NYT, Variety, IndieWire, etc.)
— the gold standard for accuracy.

Uses Playwright to render the JS-heavy RT review pages, then extracts quotes
from the DOM after rendering.

Created: 2026-03-08
"""

import json
import os
import re
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from scraper_base import PlaywrightScraperBase

logger = logging.getLogger(__name__)


class RTQuoteScraper(PlaywrightScraperBase):
    """Scrapes verbatim critic pull quotes from Rotten Tomatoes review pages.

    Each RT movie page has a /reviews subpage with short pull quotes
    submitted by critics/publications. These are real, verbatim quotes.
    """

    def __init__(self, cache_file='cache/rt_quotes_cache.json', config=None, logger_inst=None):
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger_inst,
            config_key='rt_scraper',
            log_prefix='RTQuoteScraper',
            screenshot_subdir='rt_quotes'
        )
        # Slower rate limit for quote scraping (separate from score scraping)
        self.rate_limit = 3.0

    def _init_browser_shared(self):
        """Initialize browser with RT-specific stealth scripts."""
        try:
            self.playwright = self.manager.get_playwright()
            headless = self.config.get('rt_scraper', {}).get('headless', True)
            self.browser = self.manager.get_browser(headless=headless, browser_type='chromium')

            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Anti-bot stealth scripts (same as RT score scraper)
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(window, 'chrome', { get: () => ({ runtime: {} }) });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            timeout_ms = self.scraper_config.get('timeout', 15) * 1000
            self.context.set_default_timeout(timeout_ms)
            self.page = self.context.new_page()

            self._log("Browser initialized with stealth scripts")
            self.counters['start_count'] += 1

        except Exception as e:
            self._log(f"Browser initialization failed: {e}", level='error')
            self.counters['error_count'] += 1
            self._cleanup_browser()
            raise

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached quotes are still fresh (90-day TTL)."""
        if cache_key not in self.cache:
            return False
        entry = self.cache[cache_key]
        if 'scraped_at' not in entry:
            return False
        try:
            scraped_at = datetime.fromisoformat(entry['scraped_at'])
            return datetime.now() < scraped_at + timedelta(days=90)
        except (ValueError, KeyError):
            return False

    def _extract_quotes_from_page(self) -> List[Dict]:
        """Extract critic quotes from rendered RT review-card elements.

        RT uses custom <review-card> web components with slot-based children:
        - <rt-link slot="name"> → critic name
        - <rt-link slot="publication"> → publication
        - <div slot="review"> → quote text
        - <score-icon-critics sentiment="positive|negative"> → fresh/rotten
        - top-critic attribute on review-card → is top critic
        """
        quotes = []

        cards = self.page.query_selector_all('review-card')
        if not cards:
            self._log("No review-card elements found, trying fallback")
            return self._extract_quotes_from_text()

        self._log(f"Found {len(cards)} review-card elements")

        for card in cards:
            try:
                # Quote text
                review_el = card.query_selector('[slot="review"]')
                if not review_el:
                    continue
                quote_text = review_el.text_content().strip()
                if not quote_text or len(quote_text) < 15:
                    continue

                # Critic name
                name_el = card.query_selector('[slot="name"]')
                critic_name = name_el.text_content().strip() if name_el else 'Unknown'

                # Publication
                pub_el = card.query_selector('[slot="publication"]')
                publication = pub_el.text_content().strip() if pub_el else 'Unknown'

                # Fresh/rotten from score-icon-critics sentiment attribute
                score_icon = card.query_selector('score-icon-critics')
                freshness = None
                if score_icon:
                    sentiment = score_icon.get_attribute('sentiment')
                    if sentiment == 'positive':
                        freshness = 'fresh'
                    elif sentiment == 'negative':
                        freshness = 'rotten'

                # Top critic from card attribute
                is_top_critic = card.get_attribute('top-critic') is not None

                quotes.append({
                    'text': quote_text,
                    'critic': critic_name,
                    'outlet': publication,
                    'source': 'rt_critic',
                    'verbatim': True,
                    'selected': False,
                    'fresh': freshness,
                    'is_top_critic': is_top_critic,
                    'added_at': datetime.now().isoformat()
                })

            except Exception as e:
                self._log(f"Error extracting from review-card: {e}", level='debug')
                continue

        return quotes

    def _extract_quotes_from_text(self) -> List[Dict]:
        """Fallback: extract quotes from raw page text using patterns."""
        quotes = []
        try:
            # Get all text content from the page
            page_content = self.page.content()

            # Look for JSON data embedded in the page (RT often embeds review data)
            # Pattern: review objects in script tags or data attributes
            json_patterns = [
                r'"quote"\s*:\s*"([^"]{20,300})"[^}]*?"critic"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"[^}]*?\}[^}]*?"publication"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"',
                r'"reviewQuote"\s*:\s*"([^"]{20,300})"',
            ]

            for pattern in json_patterns:
                matches = re.finditer(pattern, page_content)
                for match in matches:
                    if len(match.groups()) >= 3:
                        quotes.append({
                            'text': match.group(1),
                            'critic': match.group(2),
                            'outlet': match.group(3),
                            'source': 'rt_critic',
                            'verbatim': True,
                            'selected': False,
                            'fresh': None,
                            'added_at': datetime.now().isoformat()
                        })

        except Exception as e:
            self._log(f"Text extraction fallback failed: {e}", level='debug')

        return quotes

    def _extract_quotes_via_api(self, rt_url: str) -> List[Dict]:
        """Navigate to reviews page, extract emsId, call RT API directly.

        This is the most reliable method:
        1. Navigate to the reviews page
        2. Extract the emsId from the embedded reviewsData JSON
        3. Call the RT napi endpoint via fetch() in the browser context
        4. Parse the structured JSON response (includes review URLs)
        """
        try:
            reviews_url = rt_url.rstrip('/') + '/reviews'
            self._log(f"Navigating to: {reviews_url}")
            self.page.goto(reviews_url, wait_until='domcontentloaded', timeout=20000)
            time.sleep(3)

            # Extract emsId from the embedded script tag
            ems_id = self.page.evaluate('''() => {
                let script = document.querySelector('script[data-json="reviewsData"]');
                if (!script) return null;
                try {
                    let data = JSON.parse(script.textContent);
                    return data.media ? data.media.emsId : null;
                } catch(e) { return null; }
            }''')

            if not ems_id:
                self._log("Could not extract emsId from page", level='warning')
                return []

            self._log(f"Found emsId: {ems_id}")

            # Call the RT API directly from the browser context
            api_data = self.page.evaluate('''async (emsId) => {
                try {
                    let resp = await fetch(`/napi/rtcf/v1/movies/${emsId}/reviews?pageCount=50`);
                    if (!resp.ok) return null;
                    return await resp.json();
                } catch(e) { return null; }
            }''', ems_id)

            if not api_data:
                self._log("API call returned no data", level='warning')
                return []

            return self._parse_api_response(api_data)

        except Exception as e:
            self._log(f"Direct API extraction failed: {e}", level='warning')
            return []

    def _extract_quotes_via_network(self, rt_url: str) -> List[Dict]:
        """Navigate to reviews page and intercept API responses for structured data.

        This is the most reliable method — captures the JSON API response
        that RT's frontend uses to populate the review list.
        """
        quotes = []
        api_responses = []

        def capture_response(response):
            """Capture review API responses from RT's napi endpoint."""
            url = response.url
            # RT fetches reviews from: /napi/rtcf/v1/movies/{emsId}/reviews
            if '/napi/' in url and 'reviews' in url:
                try:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        body = response.json()
                        api_responses.append(body)
                except Exception:
                    pass

        try:
            # Set up network interception
            self.page.on('response', capture_response)

            # Navigate to reviews page
            reviews_url = rt_url.rstrip('/') + '/reviews'
            self._log(f"Navigating to: {reviews_url}")
            self.page.goto(reviews_url, wait_until='domcontentloaded', timeout=20000)
            time.sleep(5)  # Wait for JS to fire API calls and render

            # Remove listener
            self.page.remove_listener('response', capture_response)

            # Parse any captured API responses
            for response_data in api_responses:
                self._log(f"Processing API response with keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'non-dict'}", level='debug')
                extracted = self._parse_api_response(response_data)
                quotes.extend(extracted)

        except Exception as e:
            self._log(f"Network interception failed: {e}", level='warning')
            try:
                self.page.remove_listener('response', capture_response)
            except Exception:
                pass

        return quotes

    def _parse_api_response(self, data: Any) -> List[Dict]:
        """Parse RT napi review API response to extract quotes.

        RT API format (napi/rtcf/v1/movies/{emsId}/reviews):
        {
            "reviews": [
                {
                    "reviewQuote": "...",
                    "scoreSentiment": "POSITIVE" | "NEGATIVE",
                    "critic": {"displayName": "...", "isTopCritic": true},
                    "publication": {"name": "..."}
                }
            ],
            "pageInfo": {...}
        }
        """
        import html as html_mod
        quotes = []

        if not isinstance(data, dict):
            return quotes

        reviews_list = data.get('reviews')
        if not reviews_list or not isinstance(reviews_list, list):
            return quotes

        self._log(f"Found {len(reviews_list)} reviews in API response")

        for review in reviews_list:
            if not isinstance(review, dict):
                continue

            quote_text = review.get('reviewQuote', '').strip()
            if not quote_text or len(quote_text) < 15:
                continue

            # Decode HTML entities (RT encodes some chars like &#46; &apos;)
            quote_text = html_mod.unescape(quote_text)

            critic_name = 'Unknown'
            if isinstance(review.get('critic'), dict):
                critic_name = review['critic'].get('displayName', 'Unknown')

            publication = 'Unknown'
            if isinstance(review.get('publication'), dict):
                publication = review['publication'].get('name', 'Unknown')

            sentiment = review.get('scoreSentiment', '')
            freshness = 'fresh' if sentiment == 'POSITIVE' else ('rotten' if sentiment == 'NEGATIVE' else None)

            is_top_critic = False
            if isinstance(review.get('critic'), dict):
                is_top_critic = review['critic'].get('isTopCritic', False)

            review_url = review.get('publicationReviewUrl', '')

            quotes.append({
                'text': quote_text,
                'critic': critic_name,
                'outlet': publication,
                'source': 'rt_critic',
                'verbatim': True,
                'selected': False,
                'fresh': freshness,
                'is_top_critic': is_top_critic,
                'review_url': review_url,
                'added_at': datetime.now().isoformat()
            })

        return quotes

    def scrape_quotes(self, rt_url: str, title: str = '', year: int = 0) -> List[Dict]:
        """Scrape critic pull quotes from an RT movie page.

        Args:
            rt_url: Rotten Tomatoes movie URL (e.g., https://www.rottentomatoes.com/m/brutalist)
            title: Movie title (for cache key and logging)
            year: Release year (for cache key)

        Returns:
            List of quote dicts, or empty list if scraping fails
        """
        cache_key = f"{title}_{year}" if title else rt_url

        # Check cache
        if self._is_cache_valid(cache_key):
            cached = self.cache[cache_key]
            self.stats['cache_hits'] += 1
            self._log(f"Cache hit for {title or rt_url}: {len(cached.get('quotes', []))} quotes")
            return cached.get('quotes', [])

        self.stats['attempts'] += 1
        self._init_browser()
        self._enforce_rate_limit()

        all_quotes = []

        try:
            # Method 1: Navigate and call RT API directly (most reliable, gives URLs)
            api_quotes = self._extract_quotes_via_api(rt_url)
            if api_quotes:
                self._log(f"Got {len(api_quotes)} quotes via direct API call")
                all_quotes.extend(api_quotes)

            # Method 2: DOM extraction fallback
            if len(all_quotes) < 5:
                dom_quotes = self._extract_quotes_from_page()
                if dom_quotes:
                    self._log(f"Got {len(dom_quotes)} quotes via DOM extraction")
                    existing_texts = {q['text'][:50] for q in all_quotes}
                    for q in dom_quotes:
                        if q['text'][:50] not in existing_texts:
                            all_quotes.append(q)
                            existing_texts.add(q['text'][:50])

            # Cache results (even empty — avoids re-scraping known failures)
            self.cache[cache_key] = {
                'quotes': all_quotes,
                'rt_url': rt_url,
                'title': title,
                'year': year,
                'scraped_at': datetime.now().isoformat(),
                'count': len(all_quotes)
            }
            self._save_cache()

            if all_quotes:
                self.stats['successes'] += 1
                self._log(f"Scraped {len(all_quotes)} quotes for {title or rt_url}")
            else:
                self.stats['failures'] += 1
                self._log(f"No quotes found for {title or rt_url}", level='warning')

        except Exception as e:
            self._log(f"Error scraping quotes for {title or rt_url}: {e}", level='error')
            self.stats['failures'] += 1
            # Cache the failure too
            self.cache[cache_key] = {
                'quotes': [],
                'rt_url': rt_url,
                'title': title,
                'year': year,
                'scraped_at': datetime.now().isoformat(),
                'count': 0,
                'error': str(e)
            }
            self._save_cache()

        return all_quotes

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
        self._log("RTQuoteScraper closed")


# =============================================================================
# Standalone test
# =============================================================================
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.DEBUG)

    scraper = RTQuoteScraper()
    try:
        # Test with a known movie
        test_url = sys.argv[1] if len(sys.argv) > 1 else 'https://www.rottentomatoes.com/m/brutalist'
        test_title = sys.argv[2] if len(sys.argv) > 2 else 'The Brutalist'

        print(f"\nScraping RT quotes for: {test_title}")
        print(f"URL: {test_url}\n")

        quotes = scraper.scrape_quotes(test_url, test_title, 2024)

        if quotes:
            print(f"Found {len(quotes)} quotes:\n")
            for i, q in enumerate(quotes, 1):
                fresh_indicator = ''
                if q.get('fresh') == 'fresh':
                    fresh_indicator = ' [FRESH]'
                elif q.get('fresh') == 'rotten':
                    fresh_indicator = ' [ROTTEN]'
                top = ' (Top Critic)' if q.get('is_top_critic') else ''
                print(f"  {i}. \"{q['text']}\"")
                print(f"     — {q['critic']}, {q['outlet']}{fresh_indicator}{top}\n")
        else:
            print("No quotes found.")

        print(f"\nStats: {scraper.get_stats()}")
    finally:
        scraper.close()
