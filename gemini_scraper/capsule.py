"""
Capsule writer — Gemini-powered first-draft editorial movie descriptions.

Generates 3-4 sentence capsules grounded in real facts from Wikipedia, RT, and
Metacritic. Supports a training loop: user rewrites capsules, approves them, and
approved rewrites become few-shot examples for future generations.

Three-phase pipeline:
  1. FACT GATHERING — Wikipedia REST API summary + RT consensus + MC summary
  2. CAPSULE WRITING — Gemini with Google Search grounding + style guide + examples
  3. FACT VERIFICATION — second Gemini call cross-checks claims against sources
"""

import re
import os
import json
import time
import logging
import requests
from typing import Optional, Dict, List
from pathlib import Path
from urllib.parse import quote

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.capsule')

APPROVED_BANK_PATH = 'cache/approved_capsules.json'
MAX_APPROVED_EXAMPLES = 10  # Use the N most recent approved capsules in prompt


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

        # Use the most recent N approved capsules
        recent = bank[-MAX_APPROVED_EXAMPLES:]
        lines = ['YOUR APPROVED CAPSULES (match this voice):']
        for entry in recent:
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

    def _fetch_mc_summary(self, mc_url: str) -> str:
        """Fetch Metacritic critic summary by loading the page with Playwright."""
        if not mc_url:
            return ''

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                resp = page.goto(mc_url, timeout=15000, wait_until='domcontentloaded')
                if not resp or resp.status >= 400:
                    browser.close()
                    return ''

                time.sleep(1)

                summary = ''

                # Try the summary/description element
                try:
                    el = page.query_selector('.c-productionDetailsGame_description, .c-productionDetails_description, .c-movieDetails_description')
                    if el:
                        summary = el.inner_text().strip()
                except Exception:
                    pass

                # Fallback: look for critic summary in page text
                if not summary:
                    try:
                        body = page.inner_text('body')
                        # Look for the critic summary section
                        match = re.search(
                            r"(?:Critic Reviews|Critics Say|Summary)\s*[:\-—]?\s*(.+?)(?:\n\n|User Score|Must-Play)",
                            body, re.DOTALL
                        )
                        if match:
                            summary = match.group(1).strip()
                            summary = summary.split('\n')[0].strip()
                    except Exception:
                        pass

                browser.close()

                if summary and len(summary) > 10:
                    self.stats['mc_summary_fetched'] += 1
                    logger.info(f"Fetched MC summary: {len(summary)} chars")
                    return summary

        except Exception as e:
            logger.warning(f"MC summary fetch failed: {e}")

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

    def _build_prompt(self, context: str, sources: Dict[str, str]) -> str:
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
        if sources.get('mc_summary'):
            source_lines.append(f"METACRITIC SUMMARY:\n{sources['mc_summary']}")

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

        return f"""{style_guide}
{anti_block}
{examples_block}

MOVIE METADATA:
{context}
{source_block}

Use Google Search to look up:
- The director's previous notable films (for "from the director of ___" references)
- Whether this film premiered at any major festivals (Cannes, Venice, TIFF, Sundance, Berlin, etc.)
- Any notable production history, cultural significance, or interesting facts

Write a capsule (3-4 sentences). Return ONLY the capsule text, no labels or formatting.

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
                temperature=0.9
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
        elif word_count > 150:
            logger.warning(f"Capsule too long for {title} ({word_count} words)")
            self.stats['too_long'] += 1

        self.stats['gemini_successes'] += 1
        self.stats['capsules_written'] += 1
        return capsule

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
                                'sources_used': cached_data.get('sources_used', {})
                            }
                    except (ValueError, TypeError):
                        pass

        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # --- Phase 1: Fact Gathering (once) ---
        sources = {
            'wikipedia': self._fetch_wikipedia_summary(wiki_url),
            'wiki_sections': self._fetch_wikipedia_sections(wiki_url),
        }

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
        prompt = self._build_prompt(context, sources)

        # Generate N variants from the same prompt + facts
        capsules = []
        for i in range(variants):
            if variants > 1:
                logger.info(f"  Generating variant {i + 1}/{variants}...")
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

        # Cache result
        self.cache[cache_key] = {
            'capsule': primary,
            'capsules': capsules,
            'title': title,
            'year': year,
            'director': director,
            'word_count': word_count,
            'verification': verification,
            'sources_used': {
                k: (v[:200] if isinstance(v, str) else v) if v else ''
                for k, v in sources.items()
            },
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
        }
        self._save_cache()

        logger.info(f"Capsule written for {title} ({year}): {word_count} words")

        return {
            'capsule': primary,
            'capsules': capsules,
            'verification': verification,
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

        # 1. Add to approved bank (training data)
        bank = self._load_approved_bank()
        bank.append({
            'title': title,
            'year': year,
            'director': director or 'Unknown',
            'capsule': capsule_text,
            'approved_at': time.strftime('%Y-%m-%dT%H:%M:%S')
        })

        try:
            os.makedirs(os.path.dirname(APPROVED_BANK_PATH) or '.', exist_ok=True)
            with open(APPROVED_BANK_PATH, 'w') as f:
                json.dump(bank, f, indent=2)
            logger.info(f"Approved capsule for {title} ({year}) — bank now has {len(bank)} entries")
        except Exception as e:
            logger.error(f"Failed to save approved capsule: {e}")

        # 2. Update data.json synopsis field (goes live on site)
        self._publish_to_data_json(title, year, capsule_text)

    def _publish_to_data_json(self, title: str, year: int, capsule_text: str):
        """Write approved capsule into data.json's synopsis field."""
        data_path = 'data.json'
        try:
            with open(data_path, 'r') as f:
                data = json.load(f)

            movies = data.get('movies', data) if isinstance(data, dict) else data
            updated = False

            for m in movies:
                if (m.get('title', '').lower() == title.lower() and
                        m.get('year') == year):
                    m['synopsis'] = capsule_text
                    updated = True
                    break

            if updated:
                with open(data_path, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"Published capsule to data.json: {title} ({year})")
            else:
                logger.warning(f"Could not find {title} ({year}) in data.json to publish capsule")

        except Exception as e:
            logger.error(f"Failed to publish capsule to data.json: {e}")
