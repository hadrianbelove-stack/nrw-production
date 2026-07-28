"""
PullQuoteFinder — orchestrates pull-quote gathering from all three sources.

Pipeline (per movie, results combined):
  1. RT scraping: intercepts RT's internal reviews API for clean critic quotes
  2. MC scraping: loads Metacritic critic-reviews page via Playwright
  3. Letterboxd: delegated to LetterboxdQuoteScraper (letterboxd_quotes.py)

How pull quotes flow (three modules):
  - pull_quotes.py / PullQuoteFinder (this file) — orchestrator: RT + MC + Letterboxd
  - letterboxd_quotes.py / LetterboxdQuoteScraper — scrapes Letterboxd reviews,
    Gemini picks the punchiest verbatim quote from each
  - letterboxd_scraper.py / LetterboxdScoreScraper — star ratings only (not quotes)

Despite living in the gemini_scraper package, this class itself does not call
Gemini — RT and MC are pure Playwright scraping.
"""

import html as html_module
import os
import re
import time
import logging
from typing import Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.pull_quotes')


class PullQuoteFinder(GeminiFinderBase):
    """
    Scrapes critic quotes from RT and Metacritic, plus Letterboxd popular reviews.

    Usage:
        finder = PullQuoteFinder()
        quotes = finder.find_pull_quotes("The Brutalist", 2024,
            rt_url="https://www.rottentomatoes.com/m/the_brutalist",
            mc_url="https://www.metacritic.com/movie/the-brutalist/critic-reviews/")
        # Returns: list of quote dicts, or empty list
    """

    _finder_name = 'PullQuotes'

    def __init__(self, cache_file: str = 'cache/pull_quotes_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'quotes_found': 0, 'rt_scraped': 0, 'mc_scraped': 0}

    def _scrape_rt_reviews(self, rt_url: str, expected_title: str = '') -> list:
        """Scrape critic quotes directly from the RT reviews page.

        PRIMARY: Intercepts RT's internal napi/rtcf/v1/movies/{UUID}/reviews API
        call which fires when the page loads — returns clean JSON with critic,
        outlet, quote, and review URL for every review.
        FALLBACK: Text parser for when the API intercept returns nothing.

        Args:
            rt_url: The RT movie URL (e.g. https://www.rottentomatoes.com/m/the_brutalist)
            expected_title: Movie title for page verification. If provided and the RT
                page title doesn't match, returns empty list (safety net against
                wrong-movie URLs).
        """
        # Normalise URL — accept either base URL or /reviews URL
        base_url = rt_url.rstrip('/')
        if base_url.endswith('/reviews'):
            base_url = base_url[:-len('/reviews')]
        reviews_url = base_url + '/reviews'
        quotes = []

        try:
            from playwright.sync_api import sync_playwright
            from gemini_scraper.rt_validation import page_title_matches

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                # Intercept RT's internal reviews API — collect all paginated responses
                api_responses = []
                def handle_response(response):
                    if ('napi/rtcf/v1/movies' in response.url and
                            '/reviews' in response.url):
                        try:
                            api_responses.append(response.json())
                        except Exception:
                            pass

                page.on('response', handle_response)

                resp = page.goto(reviews_url, timeout=20000, wait_until='domcontentloaded')
                if not resp or resp.status >= 400:
                    logger.info(f"RT reviews page returned {resp.status if resp else 'no response'}: {reviews_url}")
                    browser.close()
                    return []

                page.wait_for_timeout(3000)

                # Safety net: verify RT page is for the right movie
                # Strip RT boilerplate ("| Audience Reviews | Rotten Tomatoes" etc.)
                # so the validator only compares the movie title portion.
                if expected_title:
                    page_title = re.sub(r'\s*\|.*$', '', page.title() or '').strip()
                    if not page_title_matches(page_title, expected_title):
                        logger.warning(
                            f"RT page title mismatch: '{page_title}' vs expected '{expected_title}' "
                            f"— skipping review scraping for {reviews_url}"
                        )
                        browser.close()
                        return []

                # Click "Load More" up to 4 times to paginate through all reviews
                for _ in range(4):
                    load_more = page.query_selector('rt-button[data-qa="load-more-btn"], button[data-qa="load-more-btn"]')
                    if not load_more:
                        break
                    try:
                        load_more.click()
                        page.wait_for_timeout(2000)
                    except Exception:
                        break

                # --- PRIMARY: parse all RT internal API responses ---
                seen_critics = set()
                for payload in api_responses:
                    for r in payload.get('reviews', []):
                        quote_text = html_module.unescape(r.get('reviewQuote', '') or '').strip()
                        if not quote_text or len(quote_text) < 15:
                            continue
                        critic_obj = r.get('critic') or {}
                        pub_obj = r.get('publication') or {}
                        critic_name = critic_obj.get('displayName', '')
                        if critic_name in seen_critics:
                            continue
                        seen_critics.add(critic_name)
                        quotes.append({
                            'text': quote_text,
                            'critic': critic_name,
                            'outlet': pub_obj.get('name', ''),
                            'source': 'rt_critic',
                            'review_url': r.get('publicationReviewUrl', ''),
                            'selected': False,
                            'added_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                        })
                if quotes:
                    logger.info(f"RT API intercepted {len(quotes)} reviews across {len(api_responses)} response(s)")

                if not quotes:
                    logger.info(f"RT API intercept returned no reviews for {reviews_url} — no RT quotes for this film")

                browser.close()

        except Exception as e:
            logger.warning(f"Error scraping RT reviews from {reviews_url}: {e}")

        if not quotes:
            logger.warning(f"RT reviews scraper returned 0 quotes for {reviews_url}")
        else:
            logger.info(f"Scraped {len(quotes)} critic quotes from RT reviews page")
        return quotes

    def _scrape_mc_reviews(self, mc_url: str) -> list:
        """Scrape critic quotes from the Metacritic critic reviews page.

        Loads the MC critic-reviews page with Playwright and parses review blocks.
        Returns ground-truth quotes with verified review URLs.
        """
        # Ensure URL ends with /critic-reviews/
        if '/critic-reviews' not in mc_url:
            mc_url = mc_url.rstrip('/') + '/critic-reviews/'
        quotes = []

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                resp = page.goto(mc_url, timeout=15000, wait_until='domcontentloaded')
                if not resp or resp.status >= 400:
                    logger.info(f"MC reviews page returned {resp.status if resp else 'no response'}: {mc_url}")
                    browser.close()
                    return []

                time.sleep(2)

                html = page.content()
                body = page.inner_text('body')

                # Extract external review URLs from HTML (skip metacritic internal links)
                review_urls = re.findall(
                    r'href="(https?://(?!www\.metacritic)[^"]+)"',
                    html
                )
                # Filter to likely review URLs (skip ads, tracking, etc.)
                review_urls = [u for u in review_urls if not any(skip in u for skip in [
                    'doubleclick', 'fandom.com/icbm', 'seg.ad.gt', 'zendesk',
                    'google', 'facebook', 'twitter', 'instagram', 'youtube',
                    'amazon.com', 'apps.apple', 'play.google'
                ])]

                # Parse text: Score, Outlet, QuoteText, [Read More], By CriticName, FULL REVIEW
                lines = [l.strip() for l in body.split('\n') if l.strip()]
                url_idx = 0

                for i, line in enumerate(lines):
                    if line != 'FULL REVIEW':
                        continue

                    # Walk backwards: "By CriticName" is right before FULL REVIEW
                    critic = ''
                    j = i - 1
                    if j >= 0 and lines[j].startswith('By '):
                        critic = lines[j][3:].strip()
                        j -= 1
                    elif j >= 0:
                        # Sometimes "Read More" is between critic and FULL REVIEW
                        if lines[j] == 'Read More':
                            j -= 1
                        if j >= 0 and lines[j].startswith('By '):
                            critic = lines[j][3:].strip()
                            j -= 1

                    # "Read More" might appear before "By" line too
                    if j >= 0 and lines[j] == 'Read More':
                        j -= 1

                    # Quote text (may be multi-line, grab everything back to the outlet)
                    quote_end = j
                    # Find outlet line (preceded by score and date)
                    # Walk back to find a line that looks like a score (number)
                    quote_start = j
                    for k in range(j, max(j - 8, -1), -1):
                        # Outlet is right after a score number or date
                        if k > 0 and re.match(r'^\d{1,3}$', lines[k - 1]):
                            quote_start = k + 1  # quote starts after outlet
                            break
                        # Also check for date pattern (MON DD, YYYY)
                        if k > 0 and re.match(r'^[A-Z]{3}\s+\d{1,2},\s+\d{4}$', lines[k - 1]):
                            quote_start = k + 1
                            break

                    # Outlet is at quote_start - 1
                    outlet = lines[quote_start - 1] if quote_start > 0 else ''

                    # Quote text is from quote_start to quote_end
                    quote_text = ' '.join(lines[quote_start:quote_end + 1]).strip()

                    # Match to review URL
                    review_url = review_urls[url_idx] if url_idx < len(review_urls) else ''
                    url_idx += 1

                    # Skip very short quotes
                    if len(quote_text) < 15:
                        continue

                    # Skip navigation elements
                    if any(nav in outlet.lower() for nav in ['showing', 'all reviews', 'metascore', 'advertisement']):
                        continue

                    quotes.append({
                        'text': quote_text,
                        'critic': critic,
                        'outlet': outlet,
                        'source': 'mc_critic',
                        'review_url': review_url,
                        'selected': False,
                        'added_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                    })

                browser.close()

        except Exception as e:
            logger.warning(f"Error scraping MC reviews from {mc_url}: {e}")

        logger.info(f"Scraped {len(quotes)} critic quotes from MC reviews page")
        return quotes

    def find_pull_quotes(
        self,
        title: str,
        year: int,
        director: str = None,
        rt_url: str = None,
        mc_url: str = None,
        lb_url: str = None
    ) -> list:
        """
        Find pull quotes for a movie by scraping RT, MC, and Letterboxd directly.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name (kept for caller compatibility; unused)
            rt_url: Rotten Tomatoes URL (e.g. https://www.rottentomatoes.com/m/the_brutalist)
            mc_url: Metacritic URL (e.g. https://www.metacritic.com/movie/the-brutalist/)
            lb_url: Pre-found Letterboxd URL (skips URL discovery if provided)

        Returns:
            List of quote dicts with keys: text, critic, outlet, source, review_url, selected, added_at
        """
        cache_key = f"{title}_{year}"

        # Check cache
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict):
                scraped_at = cached_data.get('scraped_at', '')
                if scraped_at:
                    try:
                        from datetime import datetime, timedelta
                        cached_dt = datetime.fromisoformat(scraped_at)
                        if datetime.now() - cached_dt < timedelta(days=self.cache_ttl_days):
                            cached_quotes = cached_data.get('quotes', [])
                            if cached_quotes:
                                self.stats['cache_hits'] += 1
                                logger.debug(f"Pull quotes cache hit for {title} ({year}): {len(cached_quotes)} quotes")
                                return cached_quotes
                    except (ValueError, TypeError):
                        pass

        all_quotes = []

        # --- Step 1: RT scraping ---
        # Only RT URLs verified by enrichment are used; Gemini URL guessing was
        # removed (June 2026) — it returned wrong/dead URLs on indie films.
        existing_critics = set()

        if rt_url:
            rt_quotes = self._scrape_rt_reviews(rt_url, expected_title=title)
            all_quotes.extend(rt_quotes)
            existing_critics.update(q.get('critic', '').lower().strip() for q in rt_quotes)
            if rt_quotes:
                self.stats['rt_scraped'] += 1
        else:
            logger.info(f"No RT URL for {title} ({year}), skipping RT")

        # --- Step 2: MC scraping ---
        if mc_url:
            mc_quotes = self._scrape_mc_reviews(mc_url)
            mc_new = [q for q in mc_quotes
                      if q.get('critic', '').lower().strip() not in existing_critics]
            all_quotes.extend(mc_new)
            if mc_quotes:
                self.stats['mc_scraped'] += 1
        else:
            logger.info(f"No MC URL for {title} ({year}), skipping MC")

        # --- Step 3: Letterboxd quotes ---
        # NRW_QUOTES_BACKEND=claude routes the Gemini parts (quote extraction +
        # the rare LB-URL discovery) to a local `claude -p` on the Max plan (~$0);
        # the Playwright review scrape is unchanged either way. Default = Gemini.
        if os.environ.get('NRW_QUOTES_BACKEND') == 'claude':
            from gemini_scraper.claude_quotes import ClaudeLetterboxdQuoteScraper as _LBScraper
        else:
            from gemini_scraper.letterboxd_quotes import LetterboxdQuoteScraper as _LBScraper
        lb_quotes = _LBScraper().scrape_quotes(title, year, lb_url=lb_url)
        if lb_quotes:
            all_quotes.extend(lb_quotes)
            logger.info(f"Found {len(lb_quotes)} Letterboxd quotes for {title} ({year})")

        if all_quotes:
            self.stats['quotes_found'] += len(all_quotes)

        self.cache[cache_key] = {
            'quotes': all_quotes,
            'title': title,
            'year': year,
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
        }
        self._save_cache()

        return all_quotes


def verify_quote_url(url: str, movie_title: str, critic: str) -> str:
    """Verify a review URL actually leads to a review of this movie by this critic.

    Loads the page with Playwright and checks that both the movie title and
    critic name appear somewhere on the page (headline, byline, meta — works
    even on paywalled pages). Does not look for the quote text.

    Returns:
        "ok"      — title and critic both found on page
        "bad_link" — page loaded but title or critic missing
        "no_url"  — url is empty or None
        "error"   — page failed to load (timeout, 4xx, 5xx)
    """
    if not url:
        return "no_url"

    # Normalize for loose matching
    def _norm(s):
        import re
        s = s.lower()
        s = re.sub(r'[^a-z0-9\s]', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    # Strip Letterboxd @-prefix from critic name
    critic_clean = critic.lstrip('@').strip()

    # Build word sets — need significant words (>3 chars) to appear
    title_words = [w for w in _norm(movie_title).split() if len(w) > 3]
    critic_words = [w for w in _norm(critic_clean).split() if len(w) > 2]

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/125.0.0.0 Safari/537.36'
            )
            page = ctx.new_page()
            try:
                resp = page.goto(url, timeout=12000, wait_until='domcontentloaded')
                if not resp or resp.status >= 400:
                    browser.close()
                    return "error"
                page_text = _norm(page.inner_text('body'))
                browser.close()
            except Exception:
                try:
                    browser.close()
                except Exception:
                    pass
                return "error"

        if title_words:
            title_found = any(w in page_text for w in title_words)
        else:
            # Title has no word >3 chars (e.g. "Eno"). The >3 filter left
            # nothing to match, which would fail every URL. Fall back to
            # exact-token matching on the full title — avoids substring
            # false-positives ("eno" inside "phenomenon").
            tokens = set(page_text.split())
            title_found = all(w in tokens for w in _norm(movie_title).split())
        critic_found = any(w in page_text for w in critic_words)

        if title_found and critic_found:
            return "ok"
        return "bad_link"

    except Exception as e:
        logger.warning(f"verify_quote_url failed for {url}: {e}")
        return "error"


# Legacy alias — class renamed from GeminiPullQuoteFinder (June 2026): despite
# the old name, this class never called Gemini itself.
GeminiPullQuoteFinder = PullQuoteFinder
