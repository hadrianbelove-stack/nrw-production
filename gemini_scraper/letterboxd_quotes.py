"""
LetterboxdQuoteScraper — the whole "get quotes from Letterboxd" job in one class.

How pull quotes flow (three modules):
  - pull_quotes.py / PullQuoteFinder — orchestrator: RT + Metacritic + Letterboxd
  - letterboxd_quotes.py / LetterboxdQuoteScraper (this file) — scrapes Letterboxd
    reviews with Playwright, then uses Gemini to pick the punchiest verbatim
    quote from each review
  - letterboxd_scraper.py / LetterboxdScoreScraper — star ratings only (not quotes)

The Gemini step is NOT a generator — it selects from existing review text, and
every extraction is verified as a verbatim substring of the original.
"""

import re
import time
import logging
from typing import Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.letterboxd_quotes')


class LetterboxdQuoteScraper(GeminiFinderBase):
    """Scrapes Letterboxd reviews and extracts pull quotes from them.

    Public API:
        scrape_quotes(title, year, lb_url=None) -> list of quote dicts
        extract_quotes(reviews, title, year)    -> reviews with 'pull_quote' added
    """

    _finder_name = 'LetterboxdQuotes'

    def __init__(self):
        super().__init__(cache_file='cache/quote_extractions_cache.json')

    def _get_extra_stats(self) -> Dict[str, int]:
        return {
            'reviews_processed': 0,
            'quotes_extracted': 0,
            'quotes_skipped': 0,
            'verification_failures': 0
        }

    # ------------------------------------------------------------------
    # Review scraping (Playwright)
    # ------------------------------------------------------------------

    def scrape_quotes(self, title: str, year: int, lb_url: str = None) -> list:
        """Scrape popular reviews from Letterboxd and extract pull quotes.

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
            from letterboxd_scraper import LetterboxdScoreScraper

            slug = LetterboxdScoreScraper._make_slug(title)
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
                        gemini_url = None
                        try:
                            self._enforce_rate_limit()
                            prompt = f'What is the Letterboxd URL for the film "{title}" ({year})? Return only the URL.'
                            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
                            response = self._generate(prompt, config=api_config)
                            text = response.text.strip()

                            url_match = re.search(r'https://letterboxd\.com/film/[a-z0-9-]+/?', text)
                            if url_match:
                                gemini_url = url_match.group(0).rstrip('/')
                            elif response.candidates:
                                gm = response.candidates[0].grounding_metadata
                                if gm and gm.grounding_chunks:
                                    for chunk in gm.grounding_chunks:
                                        if chunk.web and chunk.web.uri and 'letterboxd.com/film/' in chunk.web.uri:
                                            resolved = self._resolve_grounding_url(chunk.web.uri)
                                            if resolved and 'letterboxd.com/film/' in resolved:
                                                gemini_url = resolved.rstrip('/')
                                                break
                        except Exception as e:
                            logger.debug(f"Gemini couldn't find Letterboxd URL for {title}: {e}")

                        # Verify Gemini's URL actually points at this film before trusting
                        # it. Gemini hallucinates an unrelated film for obscure/foreign
                        # titles (returned a Bix Beiderbecke doc for Japanese "Chloe et Emma").
                        if gemini_url:
                            try:
                                resp = page.goto(gemini_url, timeout=15000, wait_until='domcontentloaded')
                                page_title = page.title() if resp and resp.status == 200 else ''
                                if f'({year})' in page_title or f'({year - 1})' in page_title:
                                    lb_url = gemini_url
                                    logger.info(f"Found Letterboxd page via Gemini at {lb_url}")
                                else:
                                    logger.info(f"Rejected Gemini Letterboxd URL for {title} ({year}) — wrong film/year: {gemini_url} [{page_title!r}]")
                            except Exception as e:
                                logger.debug(f"Could not verify Gemini Letterboxd URL {gemini_url}: {e}")
                    browser.close()

            except Exception as e:
                logger.warning(f"Error finding Letterboxd URL for {title}: {e}")
                return []

        if not lb_url:
            logger.info(f"No Letterboxd URL found for {title} ({year})")
            return []

        # --- Step 2: Load reviews page with stealth Playwright ---
        reviews_url = lb_url + '/reviews/by/popular/'
        # Extract film slug from lb_url for constructing review permalinks
        film_slug = lb_url.rstrip('/').split('/film/')[-1].rstrip('/')
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
                if not resp or resp.status >= 400:
                    logger.info(f"Letterboxd reviews page returned {resp.status if resp else 'none'}: {reviews_url}")
                    browser.close()
                    return []
                # Wait for reviews to appear, then scroll 6x to load lazy content
                try:
                    page.wait_for_selector('article.production-viewing', timeout=5000)
                except Exception:
                    pass
                for _ in range(6):
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    time.sleep(1.5)

                # --- Step 3: Extract reviews via DOM ---
                extracted = page.evaluate('''() => {
                    let results = [];
                    let articles = document.querySelectorAll("article.production-viewing");
                    for (let art of articles) {
                        let r = {};
                        // Username
                        let name = art.querySelector("strong.displayname, strong.name");
                        r.username = name ? name.textContent.trim() : null;
                        if (!r.username) {
                            let link = art.querySelector("a.avatar, a.name");
                            if (link) r.username = link.getAttribute("href").replace(/\\//g, "");
                        }
                        if (!r.username) continue;
                        // Review text
                        let body = art.querySelector(".js-review-body, .body-text");
                        r.text = body ? body.textContent.trim() : "";
                        if (!r.text || r.text.length < 10) continue;
                        // Avatar link gives the real account slug (not display name)
                        let avatarLink = art.querySelector("a.avatar, a[href^='/'][href$='/']");
                        r.slug = avatarLink ? avatarLink.getAttribute("href").replace(/^\\/|\\/$/g, "") : null;
                        results.push(r);
                    }
                    return results;
                }''')

                browser.close()

                now = time.strftime('%Y-%m-%dT%H:%M:%S')

                # Filter non-English reviews — require at least 3 common English words
                # (1-word threshold let German/Spanish reviews through, e.g. German "was" matching English "was")
                english_reviews = []
                for item in extracted:
                    text = item.get('text', '')
                    english_words = {'the', 'a', 'an', 'and', 'this', 'that', 'with', 'for', 'was',
                                     'but', 'not', 'you', 'film', 'movie', 'is', 'it', 'i', 'of',
                                     'to', 'in', 'are', 'be', 'at', 'as', 'its', 'on', 'by'}
                    words = set(text.lower().split()[:30])
                    if len(words & english_words) < 3:
                        continue
                    english_reviews.append(item)

                # Build review dicts for batch quote extraction
                capped_reviews = english_reviews[:20]  # Extract from top 20 to find up to 10 good quotes
                review_dicts = []
                for item in capped_reviews:
                    username = item['username']
                    slug = item.get('slug')
                    review_url = f'https://letterboxd.com/{slug}/film/{film_slug}/' if slug else ''
                    review_dicts.append({
                        'text': item['text'],
                        'critic': '@' + username if not username.startswith('@') else username,
                        'review_url': review_url,
                    })

                # Batched, verbatim-verified extraction via Gemini
                try:
                    review_dicts = self.extract_quotes(review_dicts, title=title, year=year)
                except Exception as e:
                    logger.warning(f"Quote extraction failed for {title}, using raw text: {e}")

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

                # Cap at 10 Letterboxd quotes
                quotes = quotes[:10]

        except Exception as e:
            logger.warning(f"Error scraping Letterboxd reviews for {title}: {e}")

        logger.info(f"Scraped {len(quotes)} Letterboxd reviews for {title} ({year})")
        return quotes

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

    # ------------------------------------------------------------------
    # Quote extraction (Gemini selects verbatim lines from review text)
    # ------------------------------------------------------------------

    def _verify_verbatim(self, extracted: str, original: str) -> bool:
        """Verify extracted quote exists verbatim in original review text."""
        # Normalize whitespace for comparison (reviews may have odd spacing)
        norm_extracted = ' '.join(extracted.split()).strip()
        norm_original = ' '.join(original.split()).strip()
        return norm_extracted.lower() in norm_original.lower()

    def _build_prompt(self, reviews: list) -> str:
        """Build the extraction prompt for a batch of reviews."""
        review_block = []
        for i, review in enumerate(reviews):
            text = review.get('text', '').strip()
            word_count = len(text.split())
            review_block.append(f"[{i+1}] ({word_count} words) \"{text}\"")

        reviews_text = '\n\n'.join(review_block)

        return f"""You are extracting pull quotes from Letterboxd movie reviews.

For each numbered review below, extract the SINGLE most quotable sentence or phrase.

RULES:
- Copy the text EXACTLY as written. Do not change, rephrase, or "improve" ANY words.
- Maximum 50 words for the extracted quote.
- If the review is already short (under 50 words) and punchy, return it exactly as-is.
- If the review has no quotable material (boring, generic, or incoherent), return SKIP.
- Look for: wit, humor, sharp observations, vivid imagery, memorable one-liners, personality.
- Avoid: generic praise ("great movie"), vague feelings ("it made me feel things"), plot summaries.

FORMAT (one per line):
[1] "exact extracted text here"
[2] SKIP
[3] "exact extracted text here"

REVIEWS:
{reviews_text}"""

    def _parse_response(self, response_text: str, reviews: list) -> Dict[int, str]:
        """Parse Gemini response into index -> extracted quote mapping."""
        results = {}
        pattern = r'\[(\d+)\]\s*(?:"([^"]+)"|[“]([^”]+)[”]|SKIP)'

        for match in re.finditer(pattern, response_text):
            idx = int(match.group(1)) - 1  # Convert to 0-based
            quote = match.group(2) or match.group(3)  # ASCII or smart quotes

            if idx < 0 or idx >= len(reviews):
                continue

            if quote:  # Not SKIP
                results[idx] = quote.strip()
            # SKIP entries are intentionally omitted

        return results

    def extract_quotes(self, reviews: list, title: str = '', year: int = 0) -> list:
        """
        Extract punchy pull quotes from a list of Letterboxd reviews.

        Args:
            reviews: List of review dicts (from letterboxd_reviews_cache.json)
            title: Movie title (for cache key)
            year: Movie year (for cache key)

        Returns:
            The same list with 'pull_quote' field added to each review.
            pull_quote = extracted line, or None if skipped/failed.
        """
        if not reviews:
            return reviews

        # Check cache
        cache_key = f"{title}_{year}" if title else None
        if cache_key and cache_key in self.cache:
            cached = self.cache[cache_key]
            cached_at = cached.get('extracted_at', '')
            # Check TTL
            if cached_at:
                try:
                    from datetime import datetime, timedelta
                    cached_time = datetime.fromisoformat(cached_at)
                    if datetime.now() - cached_time < timedelta(days=self.cache_ttl_days):
                        logger.info(f"Using cached extractions for {title} ({year})")
                        self.stats['cache_hits'] += 1
                        return cached.get('reviews', reviews)
                except (ValueError, TypeError):
                    pass

        if not self._init_gemini():
            logger.error("Cannot extract quotes - Gemini not available")
            return reviews

        # Process in batches of 10 (to stay within prompt limits)
        batch_size = 10
        all_results = {}

        for batch_start in range(0, len(reviews), batch_size):
            batch = reviews[batch_start:batch_start + batch_size]
            prompt = self._build_prompt(batch)

            self.stats['gemini_attempts'] += 1
            self._enforce_rate_limit()

            def _make_request():
                # No grounding needed — we're analyzing provided text, not searching
                config = self.types.GenerateContentConfig()
                response = self._generate(prompt, config=config)
                return response.text.strip()

            response_text = self._retry_with_backoff(_make_request)

            if not response_text:
                self.stats['gemini_failures'] += 1
                logger.warning(f"No response from Gemini for batch starting at {batch_start}")
                continue

            self.stats['gemini_successes'] += 1
            batch_results = self._parse_response(response_text, batch)

            # Map batch indices back to global indices
            for batch_idx, quote in batch_results.items():
                all_results[batch_start + batch_idx] = quote

        # Apply results to reviews with verbatim verification
        for i, review in enumerate(reviews):
            self.stats['reviews_processed'] += 1
            original_text = review.get('text', '')
            word_count = len(original_text.split())

            if i in all_results:
                extracted = all_results[i]

                # Verify verbatim
                if self._verify_verbatim(extracted, original_text):
                    review['pull_quote'] = extracted
                    self.stats['quotes_extracted'] += 1
                    logger.debug(f"  Extracted: \"{extracted[:60]}...\"")
                else:
                    # Verification failed — Gemini modified the text
                    self.stats['verification_failures'] += 1
                    logger.warning(
                        f"  Verification FAILED for review {i+1} by {review.get('critic', '?')}: "
                        f"extracted text not found verbatim in original"
                    )
                    # Fallback: use full text if short, otherwise None
                    if word_count <= 50:
                        review['pull_quote'] = original_text
                    else:
                        review['pull_quote'] = None
            else:
                # Gemini returned SKIP or didn't include this review
                self.stats['quotes_skipped'] += 1
                # For very short reviews, keep them anyway — they're already punchy
                if word_count <= 20:
                    review['pull_quote'] = original_text
                else:
                    review['pull_quote'] = None

        # Cache results
        if cache_key:
            from datetime import datetime
            self.cache[cache_key] = {
                'reviews': reviews,
                'title': title,
                'year': year,
                'extracted_at': datetime.now().isoformat()
            }
            self._save_cache()

        extracted_count = sum(1 for r in reviews if r.get('pull_quote'))
        logger.info(
            f"Quote extraction for {title}: {extracted_count}/{len(reviews)} reviews → pull quotes"
        )

        return reviews


# Legacy alias — the extraction half of this class previously lived in
# quote_extractor.py as LetterboxdGeminiQuoteExtractor (merged June 2026).
LetterboxdGeminiQuoteExtractor = LetterboxdQuoteScraper
