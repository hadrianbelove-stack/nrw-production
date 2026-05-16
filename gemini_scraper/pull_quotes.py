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

Quotes that can't be verified still display — they just won't have a
clickable link. Manual curation (admin UI) is the final filter.
"""

import re
import time
import logging
import urllib.parse
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

    def _scrape_rt_reviews(self, rt_url: str) -> list:
        """Scrape critic quotes directly from the RT reviews page.

        Loads {rt_url}/reviews with Playwright and parses the review blocks.
        Returns ground-truth quotes with verified review URLs.
        """
        reviews_url = rt_url.rstrip('/') + '/reviews'
        quotes = []

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                resp = page.goto(reviews_url, timeout=15000, wait_until='domcontentloaded')
                if not resp or resp.status >= 400:
                    logger.info(f"RT reviews page returned {resp.status if resp else 'no response'}: {reviews_url}")
                    browser.close()
                    return []

                time.sleep(2)

                html = page.content()
                body = page.inner_text('body')

                # Extract full review URLs from HTML
                review_urls = re.findall(
                    r'href="(https?://[^"]+)"[^>]*>\s*(?:[^<]*Go to Full Review|[^<]*Full Review)',
                    html
                )

                # Parse text structure: CriticName, Outlet, Date, [Score], QuoteText, 'Go to Full Review'
                lines = [l.strip() for l in body.split('\n') if l.strip()]
                url_idx = 0

                for i, line in enumerate(lines):
                    if 'Go to Full Review' not in line:
                        continue

                    # Quote text is right before 'Go to Full Review'
                    quote_text = lines[i - 1] if i > 0 else ''

                    # Score might be before quote (like '9/10' or 'Fresh')
                    j = i - 2
                    if j >= 0 and re.match(r'^[\d./]+$|^Fresh$|^Rotten$', lines[j]):
                        j -= 1

                    # Date
                    j -= 0  # date line
                    date = lines[j] if j >= 0 else ''
                    j -= 1

                    # Outlet
                    outlet = lines[j] if j >= 0 else ''
                    j -= 1

                    # Critic name
                    critic = lines[j] if j >= 0 else ''

                    review_url = review_urls[url_idx] if url_idx < len(review_urls) else ''
                    url_idx += 1

                    # Skip very short quotes or obvious non-quotes
                    if len(quote_text) < 15:
                        continue

                    # Skip if critic/outlet look like navigation elements
                    if any(nav in critic.lower() for nav in ['all critics', 'top critics', 'audience', 'login']):
                        continue

                    quotes.append({
                        'text': quote_text,
                        'critic': critic,
                        'outlet': outlet,
                        'source': 'rt_critic',
                        'review_url': review_url,
                        'selected': False,
                        'added_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                    })

                browser.close()

        except Exception as e:
            logger.warning(f"Error scraping RT reviews from {reviews_url}: {e}")

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

    def _dedupe_quotes(self, quotes: list) -> list:
        """Deduplicate quotes from RT and MC by critic name.

        When the same critic appears in both sources, prefer whichever
        has a review_url. If both have URLs, prefer MC (tends to have
        cleaner URLs).
        """
        seen = {}
        for q in quotes:
            critic_key = q.get('critic', '').lower().strip()
            if not critic_key:
                # No critic name — keep it
                seen[id(q)] = q
                continue

            if critic_key in seen:
                existing = seen[critic_key]
                # Prefer the one with a review URL
                if q.get('review_url') and not existing.get('review_url'):
                    seen[critic_key] = q
                elif q.get('review_url') and existing.get('review_url') and q.get('source') == 'mc_critic':
                    seen[critic_key] = q
            else:
                seen[critic_key] = q

        return list(seen.values())

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

    def _validate_lb_urls(self, quotes: list) -> list:
        """Validate Letterboxd quote URLs with Playwright.

        Loads each review_url and checks that the quote text appears on the page.
        Clears URLs that fail but keeps the quote itself.
        """
        to_validate = [q for q in quotes if q.get('review_url')]
        if not to_validate:
            return quotes

        # Filter out Google grounding redirect URLs
        for q in to_validate[:]:
            if 'vertexaisearch.cloud.google.com' in q.get('review_url', ''):
                q['review_url'] = ''
                to_validate.remove(q)

        if not to_validate:
            return quotes

        validated = 0
        cleared = 0

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                for q in to_validate:
                    url = q['review_url']

                    # Use a multi-word fragment from the quote for matching
                    words = q.get('text', '').split()
                    if len(words) >= 4:
                        mid = len(words) // 2
                        search_fragment = ' '.join(words[max(0, mid - 2):mid + 2]).lower()
                    else:
                        search_fragment = q.get('text', '').lower()

                    try:
                        resp = page.goto(url, timeout=10000, wait_until='domcontentloaded')
                        if resp and resp.status >= 400:
                            logger.info(f"LB URL returned {resp.status}: {url}")
                            q['review_url'] = ''
                            cleared += 1
                            continue

                        page_text = page.inner_text('body').lower()
                        if search_fragment and search_fragment in page_text:
                            validated += 1
                        else:
                            logger.info(f"LB quote text not found on page: {url}")
                            q['review_url'] = ''
                            cleared += 1
                    except Exception as e:
                        logger.info(f"LB URL validation error for {url}: {e}")
                        q['review_url'] = ''
                        cleared += 1

                browser.close()
        except Exception as e:
            logger.warning(f"Playwright LB validation failed: {e}")

        if validated or cleared:
            logger.info(f"LB URL validation: {validated} verified, {cleared} cleared")
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
        to_verify = [q for q in quotes if not q.get('review_url') and q.get('critic')]
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
        mc_url: str = None
    ) -> list:
        """
        Find pull quotes for a movie.

        Primary: Gemini discovers critic quotes, web search verifies and attaches URLs.
        Supplemental: RT/MC scraping for additional quotes with guaranteed URLs.
        Letterboxd: Gemini with URL validation.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for context
            num_quotes: Number of quotes to request (default 8)
            rt_url: Rotten Tomatoes URL (e.g. https://www.rottentomatoes.com/m/the_brutalist)
            mc_url: Metacritic URL (e.g. https://www.metacritic.com/movie/the-brutalist/)

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

        # --- Step 1: Gemini discovers critic quotes ---
        gemini_quotes = self._gemini_critic_quotes(title, year, director, num_quotes)

        # --- Step 2: Web search verifies and attaches real URLs ---
        if gemini_quotes:
            gemini_quotes = self._verify_quotes_via_web_search(gemini_quotes, title, year)
        all_quotes.extend(gemini_quotes)

        # --- Step 3: RT/MC scraping for supplemental quotes (already have URLs) ---
        existing_critics = {q.get('critic', '').lower().strip() for q in all_quotes if q.get('critic')}

        if rt_url:
            rt_quotes = self._scrape_rt_reviews(rt_url)
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

        # --- Step 4: Letterboxd quotes via Gemini ---
        if not self._init_gemini():
            logger.info(f"Gemini not available, skipping Letterboxd quotes for {title} ({year})")
        else:
            context = f'"{title}" ({year})'
            if director:
                context += f" directed by {director}"

            letterboxd_prompt = f"""Find 3 notable Letterboxd user reviews for the movie {context}.

Requirements:
- Only reviews with significant engagement (popular/liked reviews)
- Include the Letterboxd username (with @ prefix)
- Do NOT fabricate reviews - only real Letterboxd reviews
- If no notable reviews exist, respond with: NO_REVIEWS

What makes a GREAT Letterboxd pull quote:
- Genre-comparison one-liners are GOLD. Examples: "12 angry men for catholic people", "Barbie for people who listen to Charli xcx", "a cinderella story for girls on SSRIs"
- Vibe/experience quotes that convey what it FEELS like to watch the movie. Example: "This made me want to light a cigarette and stare at a wall for two hours. Five stars."
- Contrasting opinions in one quote — loving AND hating. Example: "i really loved the gore effects, they're all awesomely nasty. unfortunately this is the dumbest movie of the year i think."
- Sharp humor that also describes the film, not just random jokes
- Shorter ALWAYS wins. If a review is long, extract only the punchiest line.

Format each as:
QUOTE: "review text" -- @username, Letterboxd | URL: https://letterboxd.com/username/film/...

The URL must be the direct link to the Letterboxd review. This is critical for verification.

Response:"""

            def _fetch_letterboxd_quotes():
                api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
                response = self._generate(letterboxd_prompt, config=api_config)
                return response.text.strip()

            try:
                self._enforce_rate_limit()
                lb_text = self._retry_with_backoff(_fetch_letterboxd_quotes)

                if lb_text and 'NO_REVIEWS' not in lb_text:
                    lb_quotes = self._parse_quotes(lb_text, source_type='letterboxd')
                    lb_quotes = self._validate_lb_urls(lb_quotes)
                    all_quotes.extend(lb_quotes)
                    logger.info(f"Found {len(lb_quotes)} Letterboxd quotes for {title} ({year})")
                    self.stats['gemini_successes'] += 1

            except Exception as e:
                logger.warning(f"Error fetching Letterboxd quotes for {title} ({year}): {e}")
                self.stats['gemini_failures'] += 1

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
