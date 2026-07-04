"""
Capsule writer — Gemini-powered first-draft editorial movie descriptions.

Generates capsules grounded in real facts from Wikipedia, Letterboxd audience
reactions, RT consensus, and Metacritic. Supports a training loop: user rewrites
capsules, approves them, and approved rewrites become few-shot examples for
future generations.

Three-phase pipeline:
  1. FACT GATHERING — Wikipedia + Letterboxd reviews + RT consensus + MC summary
  2. CAPSULE WRITING — Gemini with Google Search grounding + style guide + examples
     (variants use different angles: filmmaker, premise/genre, context/moment)
  3. FACT VERIFICATION — second Gemini call cross-checks claims against sources
"""

import re
import os
import json
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from urllib.parse import quote

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.capsule')

APPROVED_BANK_PATH = 'admin/approved_capsules.json'

class GeminiCapsuleWriter(GeminiFinderBase):
    """
    Writes editorial capsule descriptions for movies.

    Usage:
        writer = GeminiCapsuleWriter()
        result = writer.write_capsule(
            "The Brutalist", 2024,
            director="Brady Corbet",
            genres=["Drama"],
            runtime=215,
            rt_score="89%",
            wiki_url="https://en.wikipedia.org/wiki/The_Brutalist_(film)",
            rt_url="https://www.rottentomatoes.com/m/the_brutalist",
            mc_url="https://www.metacritic.com/movie/the-brutalist/"
        )
        # result = {
        #     'capsule': "Brady Corbet spent seven years...",
        #     'verification': [...],
        #     'sources_used': {'wikipedia': '...', 'rt_consensus': '...', ...}
        # }
    """

    _finder_name = 'Capsule'

    def __init__(self, cache_file: str = 'cache/capsule_cache.json'):
        super().__init__(cache_file=cache_file)
        self._style_guide = None
        self._examples = None
        self._anti_examples = None
        self._approved_bank = None

    def _get_extra_stats(self) -> Dict[str, int]:
        return {
            'capsules_written': 0,
            'too_short': 0,
            'too_long': 0,
            'wiki_fetched': 0,
            'rt_consensus_fetched': 0,
            'mc_summary_fetched': 0,
            'verifications_run': 0,
        }

    # -------------------------------------------------------------------------
    # Training file loaders
    # -------------------------------------------------------------------------

    def _load_text_file(self, filename: str) -> str:
        """Load a text file from the gemini_scraper directory."""
        path = Path(__file__).parent / filename
        if not path.exists():
            logger.warning(f"Training file not found: {path}")
            return ''
        try:
            return path.read_text().strip()
        except Exception as e:
            logger.warning(f"Could not load {filename}: {e}")
            return ''

    def _load_style_guide(self) -> str:
        if self._style_guide is None:
            self._style_guide = self._load_text_file('capsule_style_guide.txt')
        return self._style_guide

    def _load_examples(self) -> str:
        if self._examples is None:
            self._examples = self._load_text_file('capsule_examples.txt')
        return self._examples

    def _load_anti_examples(self) -> str:
        if self._anti_examples is None:
            self._anti_examples = self._load_text_file('capsule_anti_examples.txt')
        return self._anti_examples

    def _load_approved_bank(self) -> List[Dict]:
        """Load approved capsules from the bank. Always read fresh from disk."""
        try:
            if os.path.exists(APPROVED_BANK_PATH):
                with open(APPROVED_BANK_PATH, 'r') as f:
                    bank = json.load(f)
                if isinstance(bank, list):
                    return bank
        except Exception as e:
            logger.warning(f"Could not load approved bank: {e}")
        return []

    def _format_approved_examples(self) -> str:
        """Format approved capsules as few-shot examples for the prompt."""
        bank = self._load_approved_bank()
        if not bank:
            return ''

        # Use only the 30 most recent — keeps training signal on current style
        bank = sorted(bank, key=lambda x: x.get('approved_at', ''), reverse=True)[:30]

        lines = ['YOUR APPROVED CAPSULES (match this voice):']
        for entry in bank:
            title = entry.get('title', '?')
            year = entry.get('year', '?')
            director = entry.get('director', 'Unknown')
            capsule = entry.get('capsule', '')
            lines.append(f'\n{title} ({year}) -- {director}')
            lines.append(capsule)
            lines.append('---')

        return '\n'.join(lines)

    # -------------------------------------------------------------------------
    # Fact gathering
    # -------------------------------------------------------------------------

    def _extract_article_title(self, wiki_url: str) -> str:
        """Extract article title from a Wikipedia URL."""
        if not wiki_url:
            return ''
        return wiki_url.rstrip('/').split('/wiki/')[-1] or ''

    def _fetch_wikipedia_summary(self, wiki_url: str) -> str:
        """Fetch Wikipedia article intro via REST API. Returns intro text."""
        if not wiki_url:
            return ''

        try:
            article_title = self._extract_article_title(wiki_url)
            if not article_title:
                return ''

            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{article_title}"
            headers = {'User-Agent': 'NewReleaseWall/1.0 (capsule-writer)'}
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                extract = data.get('extract', '')
                if extract:
                    logger.info(f"Fetched Wikipedia summary: {len(extract)} chars")
                    return extract
        except Exception as e:
            logger.warning(f"Wikipedia summary fetch failed: {e}")

        return ''

    def _clean_wikitext(self, text: str) -> str:
        """Strip wikitext markup to plain text."""
        # Remove references like <ref>...</ref> and <ref ... />
        text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
        text = re.sub(r'<ref[^/]*/>', '', text)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Convert [[link|display]] to display, [[link]] to link
        text = re.sub(r'\[\[[^\]]*\|([^\]]+)\]\]', r'\1', text)
        text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
        # Remove external links [url text] -> text
        text = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', text)
        text = re.sub(r'\[https?://\S+\]', '', text)
        # Remove templates {{...}} (simple, non-nested)
        text = re.sub(r'\{\{[^}]*\}\}', '', text)
        # Remove bold/italic markers
        text = re.sub(r"'{2,}", '', text)
        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _fetch_wikipedia_sections(self, wiki_url: str) -> Dict[str, str]:
        """Fetch specific Wikipedia article sections via MediaWiki API.

        Returns a dict with keys: intro, production, filming, development,
        reception, cast, quotes. Each value is cleaned plain text, capped
        at ~800 chars per section to manage prompt size.
        """
        result = {}
        if not wiki_url:
            return result

        article_title = self._extract_article_title(wiki_url)
        if not article_title:
            return result

        headers = {'User-Agent': 'NewReleaseWall/1.0 (capsule-writer)'}

        # Sections we care about (lowercase for matching)
        TARGET_SECTIONS = {
            'production': 'production',
            'filming': 'filming',
            'development': 'development',
            'production history': 'production',
            'background': 'production',
            'making': 'production',
            'reception': 'reception',
            'critical reception': 'reception',
            'critical response': 'reception',
            'cast': 'cast',
            'cast and crew': 'cast',
        }
        MAX_SECTION_CHARS = 800

        try:
            # Step 1: Get section index
            sections_url = (
                f"https://en.wikipedia.org/w/api.php?action=parse&page={article_title}"
                f"&prop=sections&format=json"
            )
            resp = requests.get(sections_url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return result

            data = resp.json()
            sections = data.get('parse', {}).get('sections', [])

            # Map section names to their index numbers
            section_map = {}
            for sec in sections:
                name_lower = sec.get('line', '').lower().strip()
                if name_lower in TARGET_SECTIONS:
                    key = TARGET_SECTIONS[name_lower]
                    if key not in section_map:  # first match wins
                        section_map[key] = sec['index']

            # Step 2: Fetch each target section's wikitext
            for key, index in section_map.items():
                try:
                    sec_url = (
                        f"https://en.wikipedia.org/w/api.php?action=parse&page={article_title}"
                        f"&section={index}&prop=wikitext&format=json"
                    )
                    sec_resp = requests.get(sec_url, headers=headers, timeout=5)
                    if sec_resp.status_code != 200:
                        continue

                    wikitext = sec_resp.json().get('parse', {}).get('wikitext', {}).get('*', '')
                    if not wikitext:
                        continue

                    clean = self._clean_wikitext(wikitext)
                    # Remove the section header itself
                    clean = re.sub(r'^=+[^=]+=+\s*', '', clean).strip()

                    if len(clean) > 20:
                        result[key] = clean[:MAX_SECTION_CHARS]

                except Exception as e:
                    logger.debug(f"Failed to fetch wiki section {key}: {e}")
                    continue

            # Step 3: Extract quotes (look for quotation patterns in production/filming)
            quotes = []
            for section_key in ['production', 'filming', 'development']:
                text = result.get(section_key, '')
                # Match common quote patterns: "...", said Director
                found = re.findall(
                    r'"([^"]{20,200})"',
                    text
                )
                quotes.extend(found[:3])  # max 3 quotes per section

            if quotes:
                result['quotes'] = quotes

            if result:
                self.stats['wiki_fetched'] += 1
                section_names = [k for k in result if k != 'quotes']
                quote_count = len(result.get('quotes', []))
                logger.info(
                    f"Fetched Wikipedia sections: {', '.join(section_names)}"
                    + (f" + {quote_count} quote(s)" if quote_count else "")
                )

        except Exception as e:
            logger.warning(f"Wikipedia sections fetch failed: {e}")

        return result

    def _fetch_letterboxd_reactions(self, title: str, year: int) -> str:
        """Fetch popular Letterboxd reviews to capture audience reactions.

        Returns a condensed string of top audience reactions — what real
        viewers are responding to, what's resonating, what the vibe is.
        """
        import unicodedata

        def _make_slug(t):
            t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('ascii')
            t = t.lower()
            t = re.sub(r"'s\b", 's', t)
            t = re.sub(r"[''']", '', t)
            t = re.sub(r'[^a-z0-9]+', '-', t)
            t = t.strip('-')
            return t

        slug = _make_slug(title)
        # Try most specific first (year-suffixed), then bare slug
        candidate_urls = [
            f'https://letterboxd.com/film/{slug}-{year - 1}/reviews/by/popular/',
            f'https://letterboxd.com/film/{slug}-{year}/reviews/by/popular/',
            f'https://letterboxd.com/film/{slug}/reviews/by/popular/',
        ]

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                try:
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

                    reviews_url = None
                    valid_years = [str(year), str(year - 1), str(year + 1)]
                    for url in candidate_urls:
                        try:
                            resp = page.goto(url, timeout=15000, wait_until='domcontentloaded')
                            if resp and resp.status == 200:
                                page_title = page.title()
                                if any(f'({y})' in page_title for y in valid_years):
                                    reviews_url = url
                                    break
                        except Exception:
                            continue

                    if not reviews_url:
                        return ''

                    time.sleep(1)

                    # Extract review text via DOM (same selectors as pull_quotes)
                    extracted = page.evaluate('''() => {
                        let results = [];
                        let articles = document.querySelectorAll("li.film-detail");
                        if (!articles.length) {
                            articles = document.querySelectorAll("article.production-viewing");
                        }
                        for (let art of articles) {
                            let r = {};
                            let name = art.querySelector("strong.name, strong.displayname, a.context strong");
                            r.username = name ? name.textContent.trim() : "anon";
                            let body = art.querySelector(".body-text, .js-review-body");
                            r.text = body ? body.textContent.trim() : "";
                            if (r.text && r.text.length >= 20) results.push(r);
                        }
                        return results;
                    }''')
                finally:
                    browser.close()

                # Filter to English reviews
                english_reviews = []
                english_words = {'the', 'and', 'this', 'that', 'with', 'for', 'was', 'but', 'not', 'you', 'film', 'movie'}
                for item in extracted:
                    words = set(item['text'].lower().split()[:30])
                    if len(words & english_words) >= 3:
                        english_reviews.append(item)

                if not english_reviews:
                    return ''

                # Take top 6, cap each at 300 chars
                capped = english_reviews[:6]
                lines = []
                for r in capped:
                    text = r['text'][:300]
                    if len(r['text']) > 300:
                        text = text.rsplit(' ', 1)[0] + '...'
                    lines.append(f"@{r['username']}: {text}")

                result = '\n\n'.join(lines)
                logger.info(f"Fetched {len(capped)} Letterboxd reactions for {title}")
                return result

        except Exception as e:
            logger.warning(f"Letterboxd reactions fetch failed for {title}: {e}")

        return ''

    def _fetch_amazon_synopsis(self, amazon_url: str) -> str:
        """Fetch editorial synopsis from Amazon product page.

        Amazon occasionally has a different editorial synopsis than TMDB,
        especially for indie/arthouse films where the distributor provides copy.
        """
        if not amazon_url:
            return ''

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                                   'Chrome/125.0.0.0 Safari/537.36'
                    )

                    resp = page.goto(amazon_url, timeout=15000, wait_until='domcontentloaded')
                    if not resp or resp.status >= 400:
                        return ''

                    time.sleep(1)

                    synopsis = ''

                    # Try synopsis/description selectors
                    for selector in [
                        '[data-automation-id="synopsis"]',
                        '.dv-dp-node-synopsis',
                        '#btf-product-details .dv-simple-synopsis',
                        '.TitleSynopsis',
                        '[class*="Synopsis"]',
                        '[class*="synopsis"]',
                    ]:
                        try:
                            el = page.query_selector(selector)
                            if el:
                                text = el.inner_text().strip()
                                if text and len(text) > 20:
                                    synopsis = text
                                    break
                        except Exception:
                            continue

                    # Fallback: regex on page body
                    if not synopsis:
                        try:
                            body = page.inner_text('body')
                            # Look for synopsis-like blocks between known Amazon UI elements
                            match = re.search(
                                r'(?:Synopsis|About this movie|About)\s*[:\-—]?\s*(.+?)(?:\n\n|Customers|Directors?:|Starring:)',
                                body, re.DOTALL
                            )
                            if match:
                                synopsis = match.group(1).strip()
                        except Exception:
                            pass
                finally:
                    browser.close()

                if synopsis and len(synopsis) > 20:
                    # Cap at 600 chars
                    if len(synopsis) > 600:
                        synopsis = synopsis[:600].rsplit(' ', 1)[0] + '...'
                    logger.info(f"Fetched Amazon synopsis: {len(synopsis)} chars")
                    return synopsis

        except Exception as e:
            logger.warning(f"Amazon synopsis fetch failed: {e}")

        return ''

    def _fetch_imdb_trivia(self, imdb_url: str) -> str:
        """Fetch trivia/production facts from IMDb trivia page.

        Returns top trivia items as a numbered list — concrete production
        details that make capsules interesting.
        """
        if not imdb_url:
            return ''

        # Construct trivia URL
        trivia_url = imdb_url.rstrip('/') + '/trivia/'

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                                   'Chrome/125.0.0.0 Safari/537.36'
                    )

                    resp = page.goto(trivia_url, timeout=15000, wait_until='domcontentloaded')
                    if not resp or resp.status >= 400:
                        return ''

                    time.sleep(1)

                    # Extract trivia items from DOM
                    items = page.evaluate('''() => {
                        let results = [];
                        // IMDb trivia: each item is an .ipc-list-card--border-line
                        // with content in .ipc-html-content-inner-div
                        let cards = document.querySelectorAll('.ipc-list-card--border-line');
                        for (let card of cards) {
                            let content = card.querySelector('.ipc-html-content-inner-div');
                            if (!content) continue;
                            let text = content.textContent.trim();
                            if (text && text.length > 30 && text.length < 1000) {
                                results.push(text);
                            }
                            if (results.length >= 5) break;
                        }
                        return results;
                    }''')
                finally:
                    browser.close()

                if not items:
                    return ''

                # Cap each at 200 chars, format as numbered list
                lines = []
                for i, item in enumerate(items[:5], 1):
                    text = item[:200]
                    if len(item) > 200:
                        text = text.rsplit(' ', 1)[0] + '...'
                    lines.append(f"{i}. {text}")

                result = '\n'.join(lines)
                logger.info(f"Fetched {len(items)} IMDb trivia items")
                return result

        except Exception as e:
            logger.warning(f"IMDb trivia fetch failed: {e}")

        return ''

    def _fetch_rt_consensus(self, rt_url: str) -> str:
        """Fetch RT Critics Consensus text by loading the movie page with Playwright."""
        if not rt_url:
            return ''

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                resp = page.goto(rt_url, timeout=15000, wait_until='domcontentloaded')
                if not resp or resp.status >= 400:
                    browser.close()
                    return ''

                time.sleep(1)

                # Try multiple selectors for consensus text
                consensus = ''

                # Modern RT layout: data-qa="score-panel-subtitle"
                try:
                    el = page.query_selector('[data-qa="critics-consensus"]')
                    if el:
                        consensus = el.inner_text().strip()
                except Exception:
                    pass

                # Fallback: look for consensus in the page text
                if not consensus:
                    try:
                        body = page.inner_text('body')
                        # Pattern: "Critics Consensus" followed by the text
                        match = re.search(
                            r"Critics Consensus\s*[:\-—]?\s*(.+?)(?:\n|Tomatometer|Audience Score)",
                            body, re.DOTALL
                        )
                        if match:
                            consensus = match.group(1).strip()
                            # Clean up: take first sentence/paragraph only
                            consensus = consensus.split('\n')[0].strip()
                    except Exception:
                        pass

                browser.close()

                if consensus and len(consensus) > 10:
                    self.stats['rt_consensus_fetched'] += 1
                    logger.info(f"Fetched RT consensus: {len(consensus)} chars")
                    return consensus

        except Exception as e:
            logger.warning(f"RT consensus fetch failed: {e}")

        return ''

    # -------------------------------------------------------------------------
    # Prompt building
    # -------------------------------------------------------------------------

    def _build_context(self, title, year, director=None, cast=None,
                       genres=None, runtime=None, synopsis=None,
                       rt_score=None, imdb_rating=None, metacritic_score=None,
                       country=None, original_language=None,
                       original_title=None, studio=None,
                       is_restoration=False, is_documentary=False,
                       is_foreign=False, is_exploitation=False,
                       is_indie=False) -> str:
        """Build structured metadata context for the prompt."""
        lines = [f'Title: {title} ({year})']

        if director:
            lines.append(f'Director: {director}')
        if cast:
            cast_str = ', '.join(cast[:5]) if isinstance(cast, list) else str(cast)
            lines.append(f'Cast: {cast_str}')
        if genres:
            genre_str = ', '.join(genres) if isinstance(genres, list) else str(genres)
            lines.append(f'Genres: {genre_str}')
        if runtime:
            lines.append(f'Runtime: {runtime} min')
        if country:
            lines.append(f'Country: {country}')
        if original_language and original_language != 'en':
            lines.append(f'Language: {original_language}')
        if original_title and original_title != title:
            lines.append(f'Original title: {original_title}')
        if studio:
            lines.append(f'Studio: {studio}')
        if rt_score:
            lines.append(f'RT score: {rt_score}')
        if imdb_rating:
            lines.append(f'IMDb: {imdb_rating}')
        if metacritic_score:
            lines.append(f'Metacritic: {metacritic_score}')

        tags = []
        if is_restoration:
            tags.append('RESTORATION/REISSUE')
        if is_documentary:
            tags.append('DOCUMENTARY')
        if is_foreign:
            tags.append('FOREIGN LANGUAGE')
        if is_exploitation:
            tags.append('GENRE/EXPLOITATION')
        if is_indie:
            tags.append('INDEPENDENT')
        if tags:
            lines.append(f'Tags: {", ".join(tags)}')

        if synopsis:
            lines.append(f'\nTMDB synopsis (for factual reference only, do NOT rephrase):\n{synopsis}')

        return '\n'.join(lines)

    # Variant angles — each gives Gemini a different entry point into the material
    # Three punchy entry points — none leads with a director bio (the editor
    # just wants three options to choose from, all premise-forward).
    VARIANT_ANGLES = [
        (
            "ANGLE: Lead with the PREMISE & GENRE. Your first sentence must describe "
            "what kind of movie this is and what it's about — tone, genre, setup. "
            "Do NOT open with the director's name or a filmmaker bio."
        ),
        (
            "ANGLE: Lead with a CONCRETE DETAIL — a production fact, a festival moment, "
            "a number, a quote, an anecdote, the cultural context. Something specific "
            "and surprising. Do NOT open with a filmmaker bio or a plain plot summary."
        ),
        (
            "ANGLE: Lead with RECEPTION or the CULTURAL MOMENT — what critics or "
            "audiences are actually responding to, or the moment/movement the film "
            "captures. Do NOT open with the director's name or a filmmaker bio."
        ),
    ]

    def _build_prompt(self, context: str, sources: Dict[str, str],
                      angle: str = None) -> str:
        """Build the full capsule-writing prompt with all training material."""

        style_guide = self._load_style_guide()
        approved_examples = self._format_approved_examples()
        seed_examples = self._load_examples()
        anti_examples = self._load_anti_examples()

        # Build source material block
        source_lines = []
        if sources.get('wikipedia'):
            source_lines.append(f"WIKIPEDIA ARTICLE SUMMARY:\n{sources['wikipedia']}")

        # Rich Wikipedia sections (production, filming, reception, etc.)
        wiki_sections = sources.get('wiki_sections', {})
        if wiki_sections:
            for key in ['production', 'development', 'filming', 'reception', 'cast']:
                if wiki_sections.get(key):
                    label = key.upper()
                    source_lines.append(f"WIKIPEDIA — {label}:\n{wiki_sections[key]}")

            # Director/filmmaker quotes — especially useful for capsules
            quotes = wiki_sections.get('quotes', [])
            if quotes:
                quote_text = '\n'.join(f'- "{q}"' for q in quotes)
                source_lines.append(f"NOTABLE QUOTES FROM PRODUCTION:\n{quote_text}")

        if sources.get('rt_consensus'):
            source_lines.append(f"RT CRITICS CONSENSUS:\n{sources['rt_consensus']}")

        if sources.get('amazon'):
            source_lines.append(f"AMAZON SYNOPSIS:\n{sources['amazon']}")

        if sources.get('imdb_trivia'):
            source_lines.append(f"IMDB TRIVIA & PRODUCTION FACTS:\n{sources['imdb_trivia']}")

        if sources.get('letterboxd'):
            source_lines.append(
                f"LETTERBOXD AUDIENCE REACTIONS (what real viewers are responding to):\n{sources['letterboxd']}"
            )

        source_block = ''
        if source_lines:
            source_block = '\n\nVERIFIED FACTS — draw from these sources for factual claims:\n' + '\n\n'.join(source_lines)

        # Build examples block — approved bank takes priority
        examples_block = ''
        if approved_examples:
            examples_block += f'\n\n{approved_examples}\n'
        if seed_examples:
            examples_block += f'\n\nSEED EXAMPLES (reference voice/style):\n{seed_examples}\n'

        anti_block = ''
        if anti_examples:
            anti_block = f'\n\n{anti_examples}\n'

        angle_block = ''
        if angle:
            angle_block = f'\n{angle}\n'

        return f"""{style_guide}
{anti_block}
{examples_block}

MOVIE METADATA:
{context}
{source_block}

Use Google Search to look up anything interesting about this film — the director's
other work, festival history, press coverage, interviews, distributor background,
comparable films, cultural context, production backstory, audience reception.
Research widely — but that breadth feeds your fact-finding, not the capsule's length.
The capsule itself stays tight; surplus facts belong in the factoid primer, not here.
{angle_block}
HARD LENGTH RULE (overrides any urge to be thorough): 40–70 words, never exceed 80.
Telegraphic — sentence fragments, facts stacked, no connective tissue ("Additionally",
"What makes this remarkable…"). A hard, surprising 45-word capsule always beats a
thorough 110-word one. If you wrote a flowing paragraph, cut it back to fragments.

Write a capsule. Return ONLY the capsule text, no labels or formatting.

CAPSULE:"""

    # -------------------------------------------------------------------------
    # Fact verification
    # -------------------------------------------------------------------------

    def _verify_capsule(self, capsule: str, sources: Dict[str, str],
                        metadata: Dict) -> List[Dict]:
        """Verify factual claims in the capsule against pre-fetched sources.

        Makes a second Gemini call to extract claims and cross-check them.
        Returns list of {claim, status, source} dicts.
        """
        if not self._init_gemini():
            return []

        # Build the verification context
        source_text = ''
        if sources.get('wikipedia'):
            source_text += f"\nWikipedia: {sources['wikipedia']}"
        if sources.get('rt_consensus'):
            source_text += f"\nRT Consensus: {sources['rt_consensus']}"
        if sources.get('mc_summary'):
            source_text += f"\nMetacritic: {sources['mc_summary']}"

        meta_text = f"Title: {metadata.get('title', '?')} ({metadata.get('year', '?')})"
        if metadata.get('director'):
            meta_text += f"\nDirector: {metadata['director']}"
        if metadata.get('cast'):
            meta_text += f"\nCast: {', '.join(metadata['cast'][:5]) if isinstance(metadata['cast'], list) else metadata['cast']}"
        if metadata.get('rt_score'):
            meta_text += f"\nRT Score: {metadata['rt_score']}"

        verify_prompt = f"""Extract every factual claim from this capsule and verify each against the provided sources.

CAPSULE:
{capsule}

AVAILABLE SOURCES:
{meta_text}
{source_text}

For each factual claim (director credits, festival mentions, year references, cast mentions, awards, production facts), respond with:
CLAIM: [the specific claim]
STATUS: VERIFIED | UNVERIFIABLE | CONTRADICTED
SOURCE: [which source confirms/contradicts it, or "none" if unverifiable]

Only flag actual factual claims (names, dates, credits, events). Do not flag subjective opinions or stylistic descriptions.

VERIFICATION:"""

        def _make_verify_request():
            self._enforce_rate_limit()
            config = self.types.GenerateContentConfig(temperature=0.1)
            response = self._generate(verify_prompt, config=config)
            return response.text.strip() if response.text else None

        try:
            result = self._retry_with_backoff(_make_verify_request)
            if not result:
                return []

            # Parse verification results
            claims = []
            for block in re.split(r'\n(?=CLAIM:)', result):
                claim_match = re.search(r'CLAIM:\s*(.+)', block)
                status_match = re.search(r'STATUS:\s*(VERIFIED|UNVERIFIABLE|CONTRADICTED)', block, re.IGNORECASE)
                source_match = re.search(r'SOURCE:\s*(.+)', block)

                if claim_match and status_match:
                    claims.append({
                        'claim': claim_match.group(1).strip(),
                        'status': status_match.group(1).upper(),
                        'source': source_match.group(1).strip() if source_match else 'none'
                    })

            self.stats['verifications_run'] += 1
            return claims

        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return []

    # -------------------------------------------------------------------------
    # Main public method
    # -------------------------------------------------------------------------

    def _generate_single_capsule(self, prompt: str, title: str, year: int) -> Optional[str]:
        """Generate a single capsule from the prompt. Returns cleaned text or None."""
        def _make_request():
            self._enforce_rate_limit()
            config = self.types.GenerateContentConfig(
                tools=[self.grounding_tool],
                temperature=0.9,
                # Maximal effort: run Pro's reasoning at the full 32768-token
                # thinking budget for the capsule write (the marquee output).
                # Default leaves thinking dynamic/low; this is the explicit "best
                # model at max effort" the capsule deserves.
                thinking_config=self.types.ThinkingConfig(thinking_budget=32768),
            )
            response = self._generate(prompt, config=config)
            return response.text.strip() if response.text else None

        try:
            capsule = self._retry_with_backoff(_make_request)
        except Exception as e:
            logger.error(f"Capsule API error for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1
            return None

        if not capsule:
            self.stats['gemini_failures'] += 1
            return None

        # Clean up response
        capsule = re.sub(r'^CAPSULE:\s*', '', capsule, flags=re.IGNORECASE).strip()
        capsule = capsule.strip('"').strip()

        # Validate length
        word_count = len(capsule.split())
        if word_count < 20:
            logger.warning(f"Capsule too short for {title} ({word_count} words)")
            self.stats['too_short'] += 1
        elif word_count > 200:
            logger.warning(f"Capsule too long for {title} ({word_count} words)")
            self.stats['too_long'] += 1

        self.stats['gemini_successes'] += 1
        self.stats['capsules_written'] += 1
        return capsule

    def _generate_factoid_primer(self, sources: Dict, context: str,
                                title: str, year: int, director: str = None) -> Tuple[str, dict]:
        """Generate a rich factoid primer — bullet list of production context,
        interview quotes, and behind-the-scenes details for the capsule editor.

        Uses already-fetched sources + Google Search grounding for interviews
        and press coverage not captured by the scraping phase.

        Returns (primer_text, notability) where notability is the parsed
        {festival, awards, yearend_lists, press_volume} block (reused for the
        notability Buzz score) — or {} if absent/unparseable.
        """
        if not self._init_gemini():
            return '', {}

        source_lines = []
        if sources.get('wikipedia'):
            source_lines.append(f"WIKIPEDIA SUMMARY:\n{sources['wikipedia']}")
        wiki_sections = sources.get('wiki_sections', {})
        if wiki_sections:
            for key in ['production', 'development', 'filming', 'reception', 'cast']:
                if wiki_sections.get(key):
                    source_lines.append(f"WIKIPEDIA — {key.upper()}:\n{wiki_sections[key]}")
            quotes = wiki_sections.get('quotes', [])
            if quotes:
                source_lines.append("WIKIPEDIA QUOTES:\n" + '\n'.join(f'- "{q}"' for q in quotes))
        if sources.get('imdb_trivia'):
            source_lines.append(f"IMDB TRIVIA:\n{sources['imdb_trivia']}")
        if sources.get('rt_consensus'):
            source_lines.append(f"RT CONSENSUS:\n{sources['rt_consensus']}")
        if sources.get('letterboxd'):
            source_lines.append(f"LETTERBOXD REACTIONS:\n{sources['letterboxd']}")

        source_block = '\n\n'.join(source_lines)
        director_str = f" directed by {director}" if director else ""

        prompt = f"""You are a film researcher preparing a detailed factoid primer for an editor who will write a short capsule description of "{title}" ({year}){director_str}.

MOVIE METADATA:
{context}

{("SOURCE MATERIAL:" + chr(10) + source_block) if source_block else ""}

Using the sources above AND Google Search, dig up everything interesting and useful about this film. Go deep — the editor wants enough material to make informed choices. Cover ALL of the following that apply:

- Director's full track record: previous films, style, career arc, notable collaborators, why this project
- Cast: each principal actor's relevant credits, why they're interesting in this role, any notable casting story
- Production: how was it made, where shot, budget scale, production company, any unusual conditions or creative choices
- Development and script: source material, how long in development, who wrote it, any interesting origin story
- Direct quotes from interviews with the director, writer, or cast — include the speaker, the outlet, and the year when known. Go find them.
- Festival run: every significant festival, awards won or nominated, how it performed critically at premiere, and any year-end critic "best of <year>" list inclusions
- Distribution: who acquired it, theatrical run details, how it's being released, any interesting release strategy
- Cultural, historical, or social context the film engages with — what's the film in conversation with?
- Anything surprising, counterintuitive, or that a well-read cinephile would find genuinely interesting
- COMPARABLES (required): One dedicated bullet identifying 2–3 specific films, TV shows, books, bands, or other cultural works this film resembles in tone, style, subject, or sensibility — and briefly why. Ground these in what critics or audiences have actually said where possible. Start this bullet with "COMPARABLES:"

Output the bullet list using • characters. Write 10–15 bullets. This is a research dump — go long. Each bullet should be as detailed as the material warrants: 2–4 sentences is normal, more if needed. Do NOT truncate interesting information into a terse one-liner. If you have a direct quote, include it verbatim and in full with attribution. Prioritize specific, surprising, or non-obvious details over generic biography. Do not number the bullets. No headers, no sections — just the bullets.

Then, after the bullets, output ONE machine-readable block on its own line and nothing after it, exactly:
<NOTABILITY>{{"festival": "major festivals played + prizes, or 'none found'", "awards": "named awards/nominations, or 'none found'", "yearend_lists": "critic year-end 'best of <year>' inclusions, or 'none found'", "press_volume": "heavy|moderate|light|minimal"}}</NOTABILITY>
Use "none found" rather than guessing; never invent an award, festival, or list. press_volume = your read of how much trade/news/online coverage this film has.

FACTOID PRIMER:"""

        def _make_request():
            self._enforce_rate_limit()
            config = self.types.GenerateContentConfig(
                tools=[self.grounding_tool],
                temperature=0.5
            )
            response = self._generate(prompt, config=config)
            return response.text.strip() if response.text else None

        notability = {}
        try:
            raw = self._retry_with_backoff(_make_request)
            if raw:
                # Extract the machine-readable notability block, then strip it
                # from the primer so it never renders as a bullet.
                m = re.search(r'<NOTABILITY>\s*(\{.*?\})\s*</NOTABILITY>', raw, re.DOTALL)
                if m:
                    try:
                        notability = json.loads(m.group(1))
                    except Exception:
                        notability = {}
                    raw = raw[:m.start()] + raw[m.end():]
                lines = [l.strip() for l in raw.split('\n') if l.strip()]
                bullets = []
                for line in lines:
                    # Skip header/label lines (e.g. "FACTOID PRIMER:")
                    if line.endswith(':') and line == line.upper():
                        continue
                    if line.startswith(('•', '-', '*')):
                        bullets.append('• ' + line.lstrip('•-* ').strip())
                    elif line and not line.startswith(('#', '<')):
                        bullets.append('• ' + line)
                return '\n'.join(bullets), notability
        except Exception as e:
            logger.warning(f"Factoid primer failed for {title}: {e}")

        return '', notability

    def write_capsule(
        self,
        title: str,
        year: int,
        director: str = None,
        cast: list = None,
        genres: list = None,
        runtime: int = None,
        synopsis: str = None,
        rt_score: str = None,
        imdb_rating: str = None,
        metacritic_score: str = None,
        country: str = None,
        original_language: str = None,
        original_title: str = None,
        studio: str = None,
        is_restoration: bool = False,
        is_documentary: bool = False,
        is_foreign: bool = False,
        is_exploitation: bool = False,
        is_indie: bool = False,
        wiki_url: str = None,
        rt_url: str = None,
        mc_url: str = None,
        amazon_url: str = None,
        imdb_url: str = None,
        force: bool = False,
        skip_verify: bool = False,
        variants: int = 1
    ) -> Optional[Dict]:
        """
        Write an editorial capsule for a movie.

        Args:
            variants: Number of capsule variants to generate (default 1).
                      Facts are fetched once, then Gemini is called N times.

        Returns dict with keys:
            capsule — the first (or best) capsule text
            capsules — list of all variant texts (when variants > 1)
            verification — fact-check results for the first capsule
            sources_used — dict of fetched source material
        Or None on failure.
        """
        cache_key = f"{title}_{year}"

        # Check cache (unless force)
        if not force and cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and cached_data.get('capsule'):
                scraped_at = cached_data.get('scraped_at', '')
                if scraped_at:
                    try:
                        from datetime import datetime, timedelta
                        cached_dt = datetime.fromisoformat(scraped_at)
                        if datetime.now() - cached_dt < timedelta(days=self.cache_ttl_days):
                            self.stats['cache_hits'] += 1
                            logger.debug(f"Capsule cache hit for {title} ({year})")
                            return {
                                'capsule': cached_data['capsule'],
                                'capsules': cached_data.get('capsules', [cached_data['capsule']]),
                                'verification': cached_data.get('verification', []),
                                'factoid_primer': cached_data.get('factoid_primer', ''),
                                'notability': cached_data.get('notability', {}),
                                'sources_used': cached_data.get('sources_used', {})
                            }
                    except (ValueError, TypeError):
                        pass

        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # --- Phase 1: Fact Gathering (once) ---
        # The six fetches are independent (each Playwright fetch opens its own
        # sync_playwright in its own thread), so run them concurrently —
        # sequentially they dominated wall-clock at 30-60s per capsule.
        fetch_jobs = {
            'wikipedia': lambda: self._fetch_wikipedia_summary(wiki_url),
            'wiki_sections': lambda: self._fetch_wikipedia_sections(wiki_url),
            'letterboxd': lambda: self._fetch_letterboxd_reactions(title, year),
            'rt_consensus': lambda: self._fetch_rt_consensus(rt_url),
            'amazon': lambda: self._fetch_amazon_synopsis(amazon_url),
            'imdb_trivia': lambda: self._fetch_imdb_trivia(imdb_url),
        }
        sources = {}
        with ThreadPoolExecutor(max_workers=len(fetch_jobs)) as pool:
            futures = {name: pool.submit(fn) for name, fn in fetch_jobs.items()}
            for name, fut in futures.items():
                try:
                    sources[name] = fut.result()
                except Exception as e:
                    logger.warning(f"{name} fetch failed for {title} ({year}): {e}")
                    sources[name] = {} if name == 'wiki_sections' else ''

        # --- Phase 2: Capsule Writing ---
        context = self._build_context(
            title, year, director=director, cast=cast, genres=genres,
            runtime=runtime, synopsis=synopsis, rt_score=rt_score,
            imdb_rating=imdb_rating, metacritic_score=metacritic_score,
            country=country, original_language=original_language,
            original_title=original_title, studio=studio,
            is_restoration=is_restoration, is_documentary=is_documentary,
            is_foreign=is_foreign, is_exploitation=is_exploitation,
            is_indie=is_indie
        )

        # Log few-shot provenance — bank_size 0 means a bank-less generation
        # (no admin/approved_capsules.json in this checkout), which produces
        # long off-style capsules. Stamped into the cache entry below.
        bank_size = len(self._load_approved_bank())
        if bank_size:
            logger.info(f"  Approved bank: {bank_size} entries "
                        f"({min(bank_size, 30)} injected as few-shot examples)")
        else:
            logger.warning("  Approved bank: EMPTY — generating without house-style examples")

        # Generate N variants — each with a different angle for real variation
        capsules = []
        for i in range(variants):
            angle = self.VARIANT_ANGLES[i % len(self.VARIANT_ANGLES)] if variants > 1 else None
            if variants > 1:
                logger.info(f"  Generating variant {i + 1}/{variants}...")
            prompt = self._build_prompt(context, sources, angle=angle)
            capsule = self._generate_single_capsule(prompt, title, year)
            if capsule:
                capsules.append(capsule)

        if not capsules:
            return None

        # Use the first capsule as the primary
        primary = capsules[0]
        word_count = len(primary.split())

        # --- Phase 3: Fact Verification (first capsule only) ---
        verification = []
        if not skip_verify:
            metadata = {
                'title': title, 'year': year, 'director': director,
                'cast': cast, 'rt_score': rt_score
            }
            verification = self._verify_capsule(primary, sources, metadata)

        # --- Phase 4: Factoid Primer ---
        logger.info(f"  Generating factoid primer...")
        factoid_primer, notability = self._generate_factoid_primer(
            sources, context, title, year, director=director
        )

        # Cache result
        self.cache[cache_key] = {
            'capsule': primary,
            'capsules': capsules,
            'title': title,
            'year': year,
            'director': director,
            'word_count': word_count,
            'verification': verification,
            'factoid_primer': factoid_primer,
            'notability': notability,
            'sources_used': {
                k: (v[:200] if isinstance(v, str) else v) if v else ''
                for k, v in sources.items()
            },
            'bank_size': bank_size,  # 0/missing = bank-less draft (off-style)
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
        }
        self._save_cache()

        logger.info(f"Capsule written for {title} ({year}): {word_count} words")

        return {
            'capsule': primary,
            'capsules': capsules,
            'verification': verification,
            'factoid_primer': factoid_primer,
            'notability': notability,
            'sources_used': sources
        }

    # -------------------------------------------------------------------------
    # Approve workflow
    # -------------------------------------------------------------------------

    def approve_capsule(self, title: str, year: int, capsule_text: str,
                        director: str = None):
        """Add an approved capsule to the training bank AND update data.json.

        Args:
            title: Movie title
            year: Release year
            capsule_text: The approved capsule text (may be user-rewritten)
            director: Director name (for context in few-shot examples)
        """
        capsule_text = capsule_text.strip()

        # Warn (don't block) on unbalanced markdown markers before publishing.
        # Renderers degrade gracefully, but a dropped asterisk is usually a typo.
        # See docs/STYLE_GUIDE.md "Synopsis / Capsule Text Formatting".
        if capsule_text.count('**') % 2 != 0:
            logger.warning(f"Capsule for {title} ({year}) has an odd number of '**' "
                           f"(unbalanced bold). Markdown may render wrong. Approving anyway.")
        if capsule_text.replace('**', '').count('*') % 2 != 0:
            logger.warning(f"Capsule for {title} ({year}) has an unmatched '*' "
                           f"(unbalanced italic). Markdown may render wrong. Approving anyway.")

        # 1. Add to approved bank (training data). Load-append-save happens
        # under the shared lock — concurrent windows approve at the same time.
        from pipeline.json_io import data_lock, atomic_dump
        try:
            os.makedirs(os.path.dirname(APPROVED_BANK_PATH) or '.', exist_ok=True)
            with data_lock():
                bank = self._load_approved_bank()
                bank.append({
                    'title': title,
                    'year': year,
                    'director': director or 'Unknown',
                    'capsule': capsule_text,
                    'approved_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                })
                atomic_dump(bank, APPROVED_BANK_PATH)
            logger.info(f"Approved capsule for {title} ({year}) — bank now has {len(bank)} entries")
        except Exception as e:
            logger.error(f"Failed to save approved capsule: {e}")

        # 2. Update data.json capsule field (goes live on site; synopsis stays as TMDB fallback)
        self._publish_to_data_json(title, year, capsule_text)

    def _publish_to_data_json(self, title: str, year: int, capsule_text: str):
        """Write approved capsule into data.json's capsule field (not synopsis — that's the TMDB fallback)."""
        from pipeline.json_io import data_lock, load_json, atomic_dump
        data_path = 'data.json'
        try:
            # Locked read-modify-write: another window saving from a stale copy
            # was erasing freshly approved capsules (Jul 3 2026).
            with data_lock():
                data = load_json(data_path)

                movies = data.get('movies', data) if isinstance(data, dict) else data
                updated = False

                for m in movies:
                    if (m.get('title', '').lower() == title.lower() and
                            m.get('year') == year):
                        m['capsule'] = capsule_text
                        updated = True
                        break

                if updated:
                    atomic_dump(data, data_path)

            if updated:
                logger.info(f"Published capsule to data.json: {title} ({year})")
            else:
                logger.warning(f"Could not find {title} ({year}) in data.json to publish capsule")

        except Exception as e:
            logger.error(f"Failed to publish capsule to data.json: {e}")
