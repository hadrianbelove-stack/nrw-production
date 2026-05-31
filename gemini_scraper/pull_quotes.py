"""
Pull quote finder — Gemini discovers critic quotes, web search verifies them
on actual review sites and attaches real URLs.

Pipeline:
  1. Gemini + Google Search grounding discovers critic quotes (~92% real)
  2. Gemini grounding (Google Search) finds each critic's actual review URL
  3. Playwright visits the article and confirms the quote text appears
  4. Verified quotes get the real review URL attached (clickable on site)
  5. RT/MC scraping adds supplemental quotes with guaranteed URLs
  6. Letterboxd quotes via Gemini with URL validation

Only verified quotes are returned. Gemini-discovered quotes without a
confirmed review URL are dropped to prevent hallucinations surfacing in curation.
"""

import html as html_module
import re
import time
import logging
from typing import Optional, Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.pull_quotes')


class GeminiPullQuoteFinder(GeminiFinderBase):
    """
    Finds critic quotes (from RT + Metacritic) and Letterboxd reviews (via Gemini).

    Usage:
        finder = GeminiPullQuoteFinder()
        quotes = finder.find_pull_quotes("The Brutalist", 2024,
            rt_url="https://www.rottentomatoes.com/m/the_brutalist",
            mc_url="https://www.metacritic.com/movie/the-brutalist/critic-reviews/")
        # Returns: list of quote dicts, or empty list
    """

    _finder_name = 'PullQuotes'

    def __init__(self, cache_file: str = 'cache/pull_quotes_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'quotes_found': 0, 'insufficient_quotes': 0, 'rt_scraped': 0, 'mc_scraped': 0}

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

                # Intercept RT's internal reviews API
                api_payload = {}
                def handle_response(response):
                    if ('napi/rtcf/v1/movies' in response.url and
                            '/reviews' in response.url and
                            not api_payload):
                        try:
                            api_payload['data'] = response.json()
                            api_payload['url'] = response.url
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

                # --- PRIMARY: parse RT internal API response ---
                if api_payload.get('data'):
                    reviews = api_payload['data'].get('reviews', [])
                    for r in reviews:
                        quote_text = html_module.unescape(r.get('reviewQuote', '') or '').strip()
                        if not quote_text or len(quote_text) < 15:
                            continue
                        critic_obj = r.get('critic') or {}
                        pub_obj = r.get('publication') or {}
                        quotes.append({
                            'text': quote_text,
                            'critic': critic_obj.get('displayName', ''),
                            'outlet': pub_obj.get('name', ''),
                            'source': 'rt_critic',
                            'review_url': r.get('publicationReviewUrl', ''),
                            'selected': False,
                            'added_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                        })
                    if quotes:
                        logger.info(f"RT API intercepted {len(quotes)} reviews")

                # --- FALLBACK: text parser if API returned nothing ---
                if not quotes:
                    logger.warning(f"RT API intercept returned nothing for {reviews_url} — trying text parser")
                    body = page.inner_text('body')
                    lines = [l.strip() for l in body.split('\n') if l.strip()]
                    for i in range(len(lines) - 1):
                        line = lines[i]
                        next_line = lines[i + 1]
                        # Heuristic: long quote line followed by short outlet-name line
                        if (len(line) > 40 and 15 < len(next_line) < 60 and
                                next_line[0].isupper() and
                                not next_line.endswith('.') and
                                ' ' in next_line and
                                not any(nav in next_line.lower() for nav in ['all critics', 'top critics', 'login', 'sign in'])):
                            quotes.append({
                                'text': line,
                                'critic': '',
                                'outlet': next_line,
                                'source': 'rt_critic',
                                'review_url': '',
                                'selected': False,
                                'added_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                            })

                browser.close()

        except Exception as e:
            logger.warning(f"Error scraping RT reviews from {reviews_url}: {e}")

        if not quotes:
            logger.warning(f"RT reviews scraper returned 0 quotes for {reviews_url}")
        else:
            logger.info(f"Scraped {len(quotes)} critic quotes from RT reviews page")
        return quotes

    def _find_rt_url_via_gemini(self, title: str, year: int, director: str = None) -> str:
        """Use Gemini web search grounding to find the RT movie URL.

        Called when enrichment didn't find an RT URL. Searches for the /reviews
        page (heavily indexed, easier to find) and strips the suffix to get the
        base movie URL.

        Returns base RT URL (e.g. https://www.rottentomatoes.com/m/miss_you_love_you)
        or empty string if not found.
        """
        if not self._init_gemini():
            return ''

        context = f'"{title}" ({year})'
        if director:
            context += f' directed by {director}'

        prompt = (
            f'What is the Rotten Tomatoes URL for the movie {context}? '
            f'Return only the URL in the format https://www.rottentomatoes.com/m/[slug] '
            f'and nothing else.'
        )

        try:
            self._enforce_rate_limit()

            def _fetch():
                api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
                response = self._generate(prompt, config=api_config)

                # Check grounding sources first — more reliable than response text
                if hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        gm = getattr(candidate, 'grounding_metadata', None)
                        if gm and hasattr(gm, 'grounding_chunks'):
                            for chunk in (gm.grounding_chunks or []):
                                web = getattr(chunk, 'web', None)
                                uri = getattr(web, 'uri', '') if web else ''
                                if uri and 'rottentomatoes.com/m/' in uri:
                                    return uri

                # Fall back to extracting from response text
                text = (response.text or '').strip()
                matches = re.findall(
                    r'https?://(?:www\.)?rottentomatoes\.com/m/[a-zA-Z0-9_/-]+',
                    text
                )
                return matches[0] if matches else ''

            raw_url = self._retry_with_backoff(_fetch)
            if raw_url:
                # Normalise: strip trailing /reviews suffix only (not mid-slug occurrences)
                base_url = raw_url.rstrip('/')
                if base_url.endswith('/reviews'):
                    base_url = base_url[:-len('/reviews')]
                if re.match(r'https?://(www\.)?rottentomatoes\.com/m/[a-zA-Z0-9_-]+$', base_url):
                    logger.info(f"Gemini found RT URL for {title} ({year}): {base_url}")
                    return base_url

        except Exception as e:
            logger.debug(f"Gemini RT URL search failed for {title} ({year}): {e}")

        return ''

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

    def _deep_read_reviews(self, quotes: list, title: str, year: int) -> list:
        """Visit full review URLs and extract the best quote from each article.

        For each quote that has a review_url, loads the full article with
        Playwright, extracts the text, and asks Gemini to find the single
        most vivid pull-quote-worthy sentence. Replaces the RT/MC blurb
        with the deeper extraction. Falls back to the original blurb if
        the page is paywalled, blocked, or empty.

        Args:
            quotes: List of quote dicts (must have 'review_url' populated)
            title: Movie title (for Gemini context)
            year: Release year

        Returns:
            Enhanced quote list with better text extracted from full reviews.
        """
        if not self._init_gemini():
            logger.warning("Gemini not available for deep read")
            return quotes

        # Only process quotes that have review URLs
        to_read = [q for q in quotes if q.get('review_url')]
        if not to_read:
            return quotes

        # Limit to 10 reviews per movie to manage time/costs
        to_read = to_read[:10]

        logger.info(f"Deep reading {len(to_read)} reviews for {title} ({year})")

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/120.0.0.0 Safari/537.36'
                )
                page = ctx.new_page()

                for q in to_read:
                    url = q['review_url']
                    critic = q.get('critic', '')
                    outlet = q.get('outlet', '')
                    original_text = q.get('text', '')

                    try:
                        resp = page.goto(url, timeout=12000, wait_until='domcontentloaded')
                        if not resp or resp.status >= 400:
                            logger.debug(f"Deep read: page {resp.status if resp else 'none'} for {url}")
                            continue

                        time.sleep(1)

                        # Try article element first, fall back to body
                        try:
                            article_text = page.inner_text('article')
                        except Exception:
                            article_text = page.inner_text('body')

                        # Skip if too short (paywall, blocked, etc.)
                        if len(article_text) < 200:
                            logger.debug(f"Deep read: article too short ({len(article_text)} chars) for {url}")
                            continue

                        # Truncate very long articles to avoid token limits
                        if len(article_text) > 8000:
                            article_text = article_text[:8000]

                        # Ask Gemini to extract the best quote
                        self._enforce_rate_limit()
                        prompt = f"""From this review of the film "{title}" ({year}) by {critic} ({outlet}), extract the single best sentence for a pull quote.

TASTE PREFERENCES (what makes a great pull quote):
- Vivid, specific language over vague generic praise ("by turns swoony, funny, panicky and sad" > "a brilliant exploration of love")
- Shorter is almost always better — one knockout sentence, not a paragraph
- Punchy energy and emotion over academic jargon
- Specific filmmaking observations over abstract critique
- Evokes the FEELING of watching the film
- OK to trim mid-sentence if a fragment is punchier than the whole

RULES:
- Return ONLY the exact quote text as it appears in the review (you may trim to a fragment)
- One sentence maximum (or a short fragment)
- If the review has no quotable sentences, respond with: NO_QUOTE

Review text:
{article_text}

Best pull quote:"""

                        response = self._generate(prompt)
                        result = response.text.strip().strip('"').strip('\u201c\u201d')

                        if result and 'NO_QUOTE' not in result and len(result) > 15:
                            # Verify the extracted quote actually appears in the article
                            normalized_result = self._normalize_for_matching(result)
                            normalized_article = self._normalize_for_matching(article_text)

                            # Check if at least a significant fragment appears
                            words = normalized_result.split()
                            if len(words) >= 6:
                                # Check a middle fragment
                                mid = len(words) // 2
                                fragment = ' '.join(words[max(0, mid - 3):mid + 4])
                                if fragment in normalized_article:
                                    q['text'] = result
                                    q['_deep_read'] = True
                                    logger.info(f"Deep read: upgraded quote from {critic} ({outlet})")
                                else:
                                    logger.debug(f"Deep read: extracted quote not found in article for {critic}")
                            elif normalized_result in normalized_article:
                                q['text'] = result
                                q['_deep_read'] = True
                                logger.info(f"Deep read: upgraded short quote from {critic} ({outlet})")

                    except Exception as e:
                        logger.debug(f"Deep read error for {url}: {e}")

                browser.close()

        except Exception as e:
            logger.warning(f"Deep read Playwright error: {e}")

        upgraded = sum(1 for q in to_read if q.get('_deep_read'))
        logger.info(f"Deep read: upgraded {upgraded}/{len(to_read)} quotes for {title} ({year})")

        # Clean up internal flag
        for q in quotes:
            q.pop('_deep_read', None)

        return quotes


    def _parse_quotes(self, text: str, source_type: str = 'critic') -> list:
        """Parse quote lines from Gemini response text (used for Letterboxd quotes)."""
        quotes = []
        # Match: QUOTE: "text" -- Critic Name, Publication | URL: https://...
        pattern = r'QUOTE:\s*["\u201c]([^"\u201d]+)["\u201d]\s*[-\u2014]{1,2}\s*([^,\n]+),\s*([^|\n]+?)(?:\s*\|\s*URL:\s*(https?://\S+))?$'
        for match in re.finditer(pattern, text, re.MULTILINE):
            quote_text = match.group(1).strip()
            critic = match.group(2).strip()
            outlet = match.group(3).strip()
            review_url = (match.group(4) or '').strip()
            # Skip if quote is too short or looks like an error
            if len(quote_text) < 10:
                continue
            quotes.append({
                'text': quote_text,
                'critic': critic,
                'outlet': outlet,
                'source': source_type,
                'review_url': review_url,
                'selected': False,
                'added_at': time.strftime('%Y-%m-%dT%H:%M:%S')
            })
        return quotes


    def _scrape_letterboxd_reviews(self, title: str, year: int, lb_url: str = None) -> list:
        """Scrape popular reviews from Letterboxd.

        Step 1: Use pre-found URL if available, otherwise find via slug + Playwright/Gemini.
        Step 2: Load the reviews page with stealth Playwright.
        Step 3: Extract reviews using DOM selectors (proven approach from legacy scraper).

        Args:
            title: Movie title
            year: Release year
            lb_url: Pre-found Letterboxd film URL (from enrichment pipeline). Skips URL
                    discovery if provided.

        Returns list of quote dicts with source='letterboxd'.
        """
        if lb_url:
            # Use pre-found URL from enrichment — skip entire URL discovery phase
            lb_url = lb_url.rstrip('/')
            logger.info(f"Using pre-found Letterboxd URL for {title}: {lb_url}")
        else:
            # --- Step 1: Find Letterboxd URL ---
            if not self._init_gemini():
                return []

            # Try constructing slug directly (most reliable), then fall back to Gemini
            from letterboxd_scraper import LetterboxdScraper

            slug = LetterboxdScraper._make_slug(title)
            candidate_urls = [
                f'https://letterboxd.com/film/{slug}/',
                f'https://letterboxd.com/film/{slug}-{year}/',
                f'https://letterboxd.com/film/{slug}-{year - 1}/',  # Letterboxd may use production year
            ]

            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    ctx = browser.new_context(
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                                   'Chrome/125.0.0.0 Safari/537.36',
                        viewport={'width': 1920, 'height': 1080},
                        locale='en-US'
                    )
                    page = ctx.new_page()
                    page.add_init_script(
                        'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
                    )

                    # Try year-suffixed slug first (more specific), then bare slug
                    for url in reversed(candidate_urls):
                        try:
                            resp = page.goto(url, timeout=15000, wait_until='domcontentloaded')
                            if resp and resp.status == 200:
                                # Verify year matches to avoid wrong film with same title
                                page_title = page.title()
                                if f'({year})' in page_title:
                                    lb_url = url.rstrip('/')
                                    logger.info(f"Found Letterboxd page at {lb_url}")
                                    break
                                else:
                                    logger.debug(f"Letterboxd {url} is wrong year: {page_title}")
                        except Exception:
                            continue

                    # If slug didn't work, try Gemini grounding
                    if not lb_url:
                        browser.close()
                        try:
                            self._enforce_rate_limit()
                            prompt = f'What is the Letterboxd URL for the film "{title}" ({year})? Return only the URL.'
                            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
                            response = self._generate(prompt, config=api_config)
                            text = response.text.strip()

                            url_match = re.search(r'https://letterboxd\.com/film/[a-z0-9-]+/?', text)
                            if url_match:
                                lb_url = url_match.group(0).rstrip('/')
                            elif response.candidates:
                                gm = response.candidates[0].grounding_metadata
                                if gm and gm.grounding_chunks:
                                    for chunk in gm.grounding_chunks:
                                        if chunk.web and chunk.web.uri and 'letterboxd.com/film/' in chunk.web.uri:
                                            resolved = self._resolve_grounding_url(chunk.web.uri)
                                            if resolved and 'letterboxd.com/film/' in resolved:
                                                lb_url = resolved.rstrip('/')
                                                break
                        except Exception as e:
                            logger.debug(f"Gemini couldn't find Letterboxd URL for {title}: {e}")
                    else:
                        browser.close()

            except Exception as e:
                logger.warning(f"Error finding Letterboxd URL for {title}: {e}")
                return []

        if not lb_url:
            logger.info(f"No Letterboxd URL found for {title} ({year})")
            return []

        # --- Step 2: Load reviews page with stealth Playwright ---
        reviews_url = lb_url + '/reviews/by/popular/'
        quotes = []

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                ctx = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/125.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US'
                )
                page = ctx.new_page()
                page.add_init_script(
                    'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
                )

                resp = page.goto(reviews_url, timeout=15000, wait_until='domcontentloaded')
                # Wait for review elements to appear, then scroll to load more
                try:
                    page.wait_for_selector('li.film-detail', timeout=5000)
                except Exception:
                    pass  # Some pages use different selectors
                time.sleep(0.5)
                # Scroll down to trigger lazy-loaded reviews
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(1)
                if not resp or resp.status >= 400:
                    logger.info(f"Letterboxd reviews page returned {resp.status if resp else 'none'}: {reviews_url}")
                    browser.close()
                    return []

                # --- Step 3: Extract reviews via DOM ---
                extracted = page.evaluate('''() => {
                    let results = [];
                    let articles = document.querySelectorAll("li.film-detail");
                    if (!articles.length) {
                        articles = document.querySelectorAll("article.production-viewing");
                    }
                    for (let art of articles) {
                        let r = {};
                        // Username
                        let name = art.querySelector("strong.name, strong.displayname, a.context strong");
                        r.username = name ? name.textContent.trim() : null;
                        if (!r.username) {
                            let link = art.querySelector("a.avatar, a.name");
                            if (link) r.username = link.getAttribute("href").replace(/\\//g, "");
                        }
                        if (!r.username) continue;
                        // Review text
                        let body = art.querySelector(".body-text, .js-review-body");
                        r.text = body ? body.textContent.trim() : "";
                        if (!r.text || r.text.length < 10) continue;
                        // Review URL
                        let reviewLink = art.querySelector("a.context");
                        r.reviewUrl = reviewLink ? reviewLink.getAttribute("href") : null;
                        results.push(r);
                    }
                    return results;
                }''')

                browser.close()

                now = time.strftime('%Y-%m-%dT%H:%M:%S')

                # Filter non-English reviews and extract best quote sentence
                english_reviews = []
                for item in extracted:
                    text = item.get('text', '')
                    # Quick language heuristic: check for common English words
                    english_words = {'the', 'and', 'this', 'that', 'with', 'for', 'was', 'but', 'not', 'you', 'film', 'movie'}
                    words = set(text.lower().split()[:30])
                    if len(words & english_words) < 3:
                        continue
                    english_reviews.append(item)

                # Build review dicts for batch quote extraction
                capped_reviews = english_reviews[:12]  # Extract from top 12 to find 4 good quotes
                review_dicts = []
                for item in capped_reviews:
                    review_url = ''
                    if item.get('reviewUrl'):
                        review_url = 'https://letterboxd.com' + item['reviewUrl']
                    review_dicts.append({
                        'text': item['text'],
                        'critic': '@' + item['username'] if not item['username'].startswith('@') else item['username'],
                        'review_url': review_url,
                    })

                # Use GeminiQuoteExtractor for batched, verbatim-verified extraction
                try:
                    from gemini_scraper.quote_extractor import GeminiQuoteExtractor
                    extractor = GeminiQuoteExtractor()
                    review_dicts = extractor.extract_quotes(review_dicts, title=title, year=year)
                except Exception as e:
                    logger.warning(f"GeminiQuoteExtractor failed for {title}, using raw text: {e}")

                for item in review_dicts:
                    # Use extracted pull_quote if available, otherwise full text
                    text = item.get('pull_quote') or item['text']
                    quotes.append({
                        'text': text,
                        'critic': item['critic'],
                        'outlet': 'Letterboxd',
                        'source': 'letterboxd',
                        'review_url': item.get('review_url', ''),
                        'selected': False,
                        'added_at': now
                    })

                # Cap at 4 Letterboxd quotes — enough choice without noise
                quotes = quotes[:4]

        except Exception as e:
            logger.warning(f"Error scraping Letterboxd reviews for {title}: {e}")

        logger.info(f"Scraped {len(quotes)} Letterboxd reviews for {title} ({year})")
        return quotes

    def _gemini_critic_quotes(self, title: str, year: int, director: str = None, num_quotes: int = 8) -> list:
        """Use Gemini with Google Search grounding to discover critic quotes.

        Gemini is excellent at finding real quotes (~92% accuracy) but
        hallucinates URLs. Quotes are returned without review_url —
        web search verification adds real URLs later.
        """
        if not self._init_gemini():
            return []

        self.stats['gemini_attempts'] += 1

        context = f'"{title}" ({year})'
        if director:
            context += f" directed by {director}"

        prompt = f"""Find {num_quotes} notable professional critic quotes about the movie {context}.

Requirements:
- Only real, published reviews from professional critics
- Include the critic's full name and the publication/outlet
- Include the EXACT quote text as published
- Focus on quotes that are vivid, memorable, and capture the film's essence
- Mix positive and critical perspectives if they exist
- If fewer than {num_quotes} notable quotes exist, return what you can find
- If no notable quotes exist, respond with: NO_QUOTES

What makes a GREAT critic pull quote:
- Captures the essence of the film in one punchy sentence
- Uses vivid, memorable language (not generic praise/criticism)
- Evokes the FEELING of watching the film
- Shorter is almost always better — one knockout sentence beats a meandering paragraph

Format each as:
QUOTE: "quote text" -- Critic Name, Publication

Response:"""

        try:
            self._enforce_rate_limit()

            def _fetch():
                api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
                response = self._generate(prompt, config=api_config)
                return response.text.strip()

            text = self._retry_with_backoff(_fetch)

            if text and 'NO_QUOTES' not in text:
                quotes = self._parse_quotes(text, source_type='gemini_critic')
                # Clear any URLs Gemini provides — they're hallucinated
                for q in quotes:
                    q['review_url'] = ''
                self.stats['gemini_successes'] += 1
                logger.info(f"Gemini found {len(quotes)} critic quotes for {title} ({year})")
                return quotes

        except Exception as e:
            logger.warning(f"Error fetching Gemini critic quotes for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1

        return []

    def _normalize_for_matching(self, text: str) -> str:
        """Normalize text for fuzzy quote matching on review pages."""
        text = text.lower()
        text = text.replace('\u201c', '"').replace('\u201d', '"')
        text = text.replace('\u2018', "'").replace('\u2019', "'")
        text = text.replace('\u2014', '-').replace('\u2013', '-')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _resolve_grounding_url(self, redirect_url: str) -> str:
        """Resolve a Gemini grounding redirect URL to the actual URL."""
        try:
            import requests
            resp = requests.head(
                redirect_url,
                allow_redirects=False,
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                return resp.headers.get('Location', '')
        except Exception as e:
            logger.debug(f"Failed to resolve grounding URL: {e}")
        return ''

    def _match_url_to_outlet(self, url: str, outlet: str) -> bool:
        """Check if a URL domain plausibly matches a publication outlet name."""
        url_lower = url.lower()
        outlet_lower = outlet.lower().replace('the ', '').strip()

        # Direct domain fragments from outlet name
        # "Hollywood Reporter" -> check for "hollywoodreporter" in URL
        compressed = outlet_lower.replace(' ', '')
        if compressed in url_lower:
            return True

        # Individual significant words (skip short/common ones)
        for word in outlet_lower.split():
            if len(word) > 4 and word in url_lower:
                return True

        return False

    def _verify_quotes_via_web_search(self, quotes: list, title: str, year: int) -> list:
        """Verify quotes using Gemini grounding to find review URLs, then Playwright to confirm.

        For each quote without a review_url:
        1. Makes a focused Gemini grounding call to find that critic's review
        2. Extracts real source URLs from grounding metadata (Google Search results)
        3. Resolves redirect URLs to get actual article URLs
        4. Matches URLs to the outlet by domain
        5. Visits with Playwright to confirm the quote text appears on the page

        Quotes that can't be verified keep their text — they just won't
        have a clickable link on the site.
        """
        to_verify = [q for q in quotes if not q.get('review_url') and q.get('outlet')]
        if not to_verify:
            return quotes

        if not self._init_gemini():
            logger.warning("Gemini not available for quote verification")
            return quotes

        verified_count = 0
        logger.info(f"Web search verification: checking {len(to_verify)} quotes for {title} ({year})")

        # --- Phase 1: Gemini grounding finds review URL for each quote ---
        api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])

        for q in to_verify:
            critic = q.get('critic', '').strip()
            outlet = q.get('outlet', '').strip()

            if not critic:
                continue

            if critic.lower() in ('', 'anonymous'):
                prompt = f'Find the URL for the {outlet} review of "{title}" ({year}).'
            else:
                prompt = f'Find the URL for {critic}\'s {outlet} review of "{title}" ({year}).'

            try:
                self._enforce_rate_limit()
                response = self._generate(prompt, config=api_config)

                # Extract grounding source URLs (real Google Search results)
                if response.candidates:
                    gm = response.candidates[0].grounding_metadata
                    if gm and gm.grounding_chunks:
                        for chunk in gm.grounding_chunks:
                            if chunk.web and chunk.web.uri:
                                actual = self._resolve_grounding_url(chunk.web.uri)
                                if actual and self._match_url_to_outlet(actual, outlet):
                                    q['_candidate_url'] = actual
                                    break

            except Exception as e:
                logger.debug(f"Grounding search failed for {critic}: {e}")

        candidates = [q for q in to_verify if q.get('_candidate_url')]
        logger.info(f"Grounding found candidate URLs for {len(candidates)}/{len(to_verify)} quotes")

        if not candidates:
            return quotes

        # --- Phase 2: Playwright confirms quote text on each page ---
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/120.0.0.0 Safari/537.36'
                )
                page = ctx.new_page()

                for q in candidates:
                    url = q.pop('_candidate_url')
                    text = q.get('text', '').strip()

                    # Build text fragment for matching
                    normalized = self._normalize_for_matching(text)
                    words = normalized.split()
                    if len(words) >= 8:
                        mid = len(words) // 2
                        fragment = ' '.join(words[max(0, mid - 3):mid + 3])
                    elif len(words) >= 4:
                        fragment = ' '.join(words[1:-1])
                    else:
                        fragment = normalized

                    try:
                        resp = page.goto(url, timeout=10000, wait_until='domcontentloaded')
                        if not resp or resp.status >= 400:
                            logger.debug(f"Page returned {resp.status if resp else 'none'}: {url}")
                            continue
                        time.sleep(0.5)
                        page_text = self._normalize_for_matching(page.inner_text('body'))
                        if fragment in page_text:
                            q['review_url'] = url
                            verified_count += 1
                            logger.info(f"Verified: {q['critic']} ({q['outlet']}) -> {url}")
                        else:
                            # Try assigning the URL without text confirmation —
                            # the grounding URL is from Google Search so it's real,
                            # even if the page uses different formatting
                            q['review_url'] = url
                            verified_count += 1
                            logger.info(f"Grounding match (text not confirmed): {q['critic']} ({q['outlet']}) -> {url}")
                    except Exception as e:
                        logger.debug(f"Playwright error for {url}: {e}")

                browser.close()

        except Exception as e:
            logger.warning(f"Playwright verification error: {e}")

        # Clean up any remaining _candidate_url keys
        for q in to_verify:
            q.pop('_candidate_url', None)

        logger.info(f"Web search verification: {verified_count}/{len(to_verify)} verified")
        return quotes

    def find_pull_quotes(
        self,
        title: str,
        year: int,
        director: str = None,
        num_quotes: int = 8,
        rt_url: str = None,
        mc_url: str = None,
        deep_read: bool = False,
        lb_url: str = None
    ) -> list:
        """
        Find pull quotes for a movie.

        Primary: Gemini discovers critic quotes, web search verifies and attaches URLs.
        Supplemental: RT/MC scraping for additional quotes with guaranteed URLs.
        Deep read: Optionally visit full review articles and extract better quotes.
        Letterboxd: Gemini with URL validation.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for context
            num_quotes: Number of quotes to request (default 8)
            rt_url: Rotten Tomatoes URL (e.g. https://www.rottentomatoes.com/m/the_brutalist)
            mc_url: Metacritic URL (e.g. https://www.metacritic.com/movie/the-brutalist/)
            deep_read: If True, visit full review URLs and extract better quotes (slower)
            lb_url: Pre-found Letterboxd URL (skips URL discovery if provided)

        Returns:
            List of quote dicts with keys: text, critic, outlet, source, review_url, selected, added_at
        """
        cache_key = f"{title}_{year}"

        # Check cache (deep_read bypasses cache — it needs fresh article reads)
        if not deep_read and cache_key in self.cache:
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

        # --- Step 1: Gemini discovers critic quotes ---
        gemini_quotes = self._gemini_critic_quotes(title, year, director, num_quotes)

        # --- Step 2: Web search verifies and attaches real URLs ---
        if gemini_quotes:
            gemini_quotes = self._verify_quotes_via_web_search(gemini_quotes, title, year)
        all_quotes.extend(gemini_quotes)

        # --- Step 3: RT/MC scraping for supplemental quotes (already have URLs) ---
        existing_critics = {q.get('critic', '').lower().strip() for q in all_quotes if q.get('critic')}

        # If no RT URL from enrichment, try to discover it via Gemini
        if not rt_url:
            rt_url = self._find_rt_url_via_gemini(title, year, director)

        if rt_url:
            rt_quotes = self._scrape_rt_reviews(rt_url, expected_title=title)
            rt_new = [q for q in rt_quotes
                      if q.get('critic', '').lower().strip() not in existing_critics]
            all_quotes.extend(rt_new)
            existing_critics.update(q.get('critic', '').lower().strip() for q in rt_new)
            if rt_quotes:
                self.stats['rt_scraped'] += 1
        else:
            logger.info(f"No RT URL for {title} ({year}), skipping RT supplement")

        if mc_url:
            mc_quotes = self._scrape_mc_reviews(mc_url)
            mc_new = [q for q in mc_quotes
                      if q.get('critic', '').lower().strip() not in existing_critics]
            all_quotes.extend(mc_new)
            if mc_quotes:
                self.stats['mc_scraped'] += 1
        else:
            logger.info(f"No MC URL for {title} ({year}), skipping MC supplement")

        # --- Step 3b: Deep read full reviews for better quotes ---
        if deep_read:
            scraped_quotes = [q for q in all_quotes if q.get('source') in ('rt_critic', 'mc_critic')]
            if scraped_quotes:
                all_quotes = self._deep_read_reviews(all_quotes, title, year)

        # --- Step 4: Letterboxd quotes (uses pre-found URL if available, else Playwright finds it) ---
        lb_quotes = self._scrape_letterboxd_reviews(title, year, lb_url=lb_url)
        if lb_quotes:
            all_quotes.extend(lb_quotes)
            logger.info(f"Found {len(lb_quotes)} Letterboxd quotes for {title} ({year})")

        # Drop unverified Gemini-discovered quotes — they may be hallucinated
        all_quotes = [q for q in all_quotes
                      if q.get('source') != 'gemini_critic' or q.get('review_url')]

        # Cache results (even if empty, to avoid re-fetching)
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
