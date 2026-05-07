"""
Rotten Tomatoes finder — Gemini + Playwright hybrid.

Classes: GeminiRTFinder, HybridRTFinder
"""

import re
import time
import logging
from typing import Optional, Dict, Any

from gemini_scraper.base import GeminiFinderBase
from gemini_scraper.rt_validation import page_title_matches, extract_score_from_loaded_page

logger = logging.getLogger('gemini_scraper.rotten_tomatoes')


class GeminiRTFinder(GeminiFinderBase):
    """
    Finds Rotten Tomatoes URLs and scores using Gemini API with Google Search grounding.

    Usage:
        finder = GeminiRTFinder()
        result = finder.find_rt_score("Conclave", 2024)
        # Returns: {'url': 'https://rottentomatoes.com/m/...', 'score': '93%'} or None
    """

    _finder_name = 'RT'

    def __init__(self, cache_file: str = 'cache/rt_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'invalid_responses': 0}

    def _validate_rt_url(self, url: str) -> bool:
        """Validate that a URL is a valid Rotten Tomatoes movie URL."""
        if not url:
            return False
        # Match rottentomatoes.com/m/ format
        pattern = r'^https?://(www\.)?rottentomatoes\.com/m/[a-zA-Z0-9_-]+'
        return bool(re.match(pattern, url))

    def _validate_rt_url_matches_title(self, url: str, title: str, year: Any = None) -> bool:
        """Validate that an RT URL slug reasonably matches the movie title.

        Catches obvious Gemini hallucinations where the URL is for a completely
        different movie (e.g., 'hachi_a_dogs_tale' for 'Muerta en Vida').

        Args:
            url: The Rotten Tomatoes URL
            title: The expected movie title
            year: The expected movie year (int or str)

        Returns:
            True if the URL plausibly matches the title
        """
        if not url or not title:
            return False

        # Extract slug from URL (e.g., "hachi_a_dogs_tale" from ".../m/hachi_a_dogs_tale")
        slug = url.rstrip('/').split('/m/')[-1].split('?')[0]

        # Year validation: if slug contains a year, it must match the requested year
        slug_year_match = re.search(r'_(\d{4})$', slug)
        if slug_year_match and year:
            slug_year = int(slug_year_match.group(1))
            requested_year = int(year)
            if abs(slug_year - requested_year) > 1:  # Allow ±1 year for release date differences
                logger.warning(f"RT URL year mismatch: slug has {slug_year}, "
                               f"expected ~{requested_year} for '{title}'")
                return False

        # Strip year suffixes from slug (e.g., "movie_name_2025" → "movie_name")
        slug_no_year = re.sub(r'_\d{4}$', '', slug)

        # Normalize title: lowercase, remove articles and punctuation, split to words
        title_normalized = title.lower()
        title_normalized = re.sub(r'^(the|a|an)\s+', '', title_normalized)
        title_normalized = re.sub(r'[^a-z0-9\s]', '', title_normalized)
        title_words = set(title_normalized.split())

        # Normalize slug to words
        slug_words = set(slug_no_year.lower().replace('-', '_').split('_'))

        # Remove common stop words from both
        stop_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'and', 'or', 'is', 'it'}
        title_words -= stop_words
        slug_words -= stop_words

        # Filter to significant words (>2 chars)
        title_significant = {w for w in title_words if len(w) > 2}
        slug_significant = {w for w in slug_words if len(w) > 2}

        if not title_significant:
            # Very short title, can't validate meaningfully
            return True

        # Check for word overlap
        overlap = title_significant & slug_significant
        if overlap:
            return True

        # Also check if title words appear as substrings in the slug
        slug_flat = slug_no_year.lower().replace('_', '').replace('-', '')
        title_flat = re.sub(r'[^a-z0-9]', '', title.lower())

        # Check if the title (without spaces) appears in the slug
        if title_flat in slug_flat or slug_flat in title_flat:
            return True

        logger.warning(f"RT URL mismatch: slug '{slug}' doesn't match title '{title}' "
                       f"(title_words={title_significant}, slug_words={slug_significant})")
        return False

    def _extract_rt_data(self, text: str) -> Optional[Dict[str, str]]:
        """Extract RT URL and score from Gemini response text."""
        if not text:
            return None

        result = {}

        # Extract URL
        url_pattern = r'https?://(www\.)?rottentomatoes\.com/m/[a-zA-Z0-9_-]+'
        url_match = re.search(url_pattern, text)
        if url_match:
            result['url'] = url_match.group(0)
            # Normalize to www version
            if not result['url'].startswith('https://www.'):
                result['url'] = result['url'].replace('https://', 'https://www.')

        # Extract score (look for percentage)
        score_patterns = [
            r'(\d{1,3})%',  # Simple percentage
            r'SCORE:\s*(\d{1,3})%',  # SCORE: XX%
            r'Tomatometer[:\s]+(\d{1,3})%',  # Tomatometer: XX%
        ]
        for pattern in score_patterns:
            score_match = re.search(pattern, text, re.IGNORECASE)
            if score_match:
                score = int(score_match.group(1))
                if 0 <= score <= 100:
                    result['score'] = f"{score}%"
                    break

        # Must have at least URL to be valid
        if 'url' in result:
            return result
        return None

    def find_rt_score(
        self,
        title: str,
        year: int,
        director: str = None,
        original_language: str = None,
        original_title: str = None
    ) -> Optional[Dict[str, str]]:
        """
        Find Rotten Tomatoes URL and score for a movie using Gemini.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for disambiguation
            original_language: ISO 639-1 language code (e.g. 'es', 'fr')
            original_title: Original-language title from TMDB (if different from title)

        Returns:
            Dict with 'url' and 'score' keys, or None if not found
        """
        cache_key = f"{title}_{year}"

        # Check cache first
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            # Handle both old format (just url/score) and new format (with metadata)
            if isinstance(cached_data, dict) and cached_data.get('url') and cached_data.get('score'):
                self.stats['cache_hits'] += 1
                logger.debug(f"RT cache hit for {title} ({year})")
                return {'url': cached_data.get('url'), 'score': cached_data.get('score')}
            # If URL exists but no score, fall through to re-query Gemini
            if isinstance(cached_data, dict) and cached_data.get('url') and not cached_data.get('score'):
                logger.debug(f"RT cache partial hit for {title} ({year}): URL exists but no score, re-querying")

        # Initialize Gemini if needed
        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1

        # Build context for better matching
        context_parts = [f'"{title}" ({year})']
        if director:
            context_parts.append(f"directed by {director}")
        if original_language and original_language != 'en':
            lang_names = {
                'es': 'Spanish', 'fr': 'French', 'ja': 'Japanese',
                'ko': 'Korean', 'he': 'Hebrew', 'ta': 'Tamil',
                'pt': 'Portuguese', 'sv': 'Swedish', 'ml': 'Malayalam',
                'ro': 'Romanian', 'tl': 'Tagalog', 'id': 'Indonesian',
                'th': 'Thai', 'hi': 'Hindi', 'zh': 'Chinese',
                'de': 'German', 'it': 'Italian', 'ar': 'Arabic',
            }
            lang_name = lang_names.get(original_language, original_language)
            context_parts.append(f"(original language: {lang_name})")
        if original_title and original_title != title:
            context_parts.append(f"(original title: {original_title})")
        movie_context = " ".join(context_parts)

        # Construct prompt
        prompt = f"""Find the Rotten Tomatoes page and Tomatometer critic score for the movie {movie_context}.

Requirements:
- The movie MUST be from {year}. Do not return a different movie with a similar title from a different year.
- Return the RT URL in format: https://www.rottentomatoes.com/m/movie_name
- Return the Tomatometer critic score as a percentage
- Format your response as: URL: [url] SCORE: [XX]%
- If no RT page exists for this specific movie, respond with exactly: NO_RT_PAGE
- If you are not confident you found the exact right movie, respond with exactly: NOT_FOUND

Response:"""

        def _make_api_request():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=api_config
            )
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_make_api_request)

            if result_text is None:
                logger.error(f"All retries failed for RT {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            logger.debug(f"Gemini RT response for {title}: {result_text}")

            # Handle explicit "no page" responses
            if 'NO_RT_PAGE' in result_text:
                logger.info(f"No RT page exists for {title} ({year})")
                self.cache[cache_key] = {'url': None, 'score': None, 'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
                self._save_cache()
                self.stats['gemini_successes'] += 1
                return None

            if 'NOT_FOUND' in result_text:
                logger.info(f"Could not find RT page for {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            # Extract data from response
            data = self._extract_rt_data(result_text)

            if data and self._validate_rt_url(data.get('url', '')):
                # Validate that the URL actually matches the requested movie
                if not self._validate_rt_url_matches_title(data['url'], title, year=year):
                    logger.warning(f"RT URL rejected (wrong movie): {data['url']} for '{title}' ({year})")
                    self.stats['invalid_responses'] += 1
                    self.stats['gemini_failures'] += 1
                    return None

                logger.info(f"Found RT for {title} ({year}): {data['url']} ({data.get('score', 'N/A')})")
                self.cache[cache_key] = {
                    'url': data['url'],
                    'score': data.get('score'),
                    'title': title,
                    'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                }
                self._save_cache()
                self.stats['gemini_successes'] += 1
                return data
            else:
                logger.warning(f"Invalid RT response for {title} ({year}): {result_text}")
                self.stats['invalid_responses'] += 1
                self.stats['gemini_failures'] += 1
                return None

        except Exception as e:
            logger.error(f"Gemini RT API error for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1
            return None


    def find_score_for_url(self, url: str, title: str = None, year: int = None) -> Optional[str]:
        """Ask Gemini for the score on a SPECIFIC RT URL (no searching).

        This is fundamentally safer than find_rt_score() because Gemini reads
        a known page rather than searching for a movie (where hallucinations happen).

        Args:
            url: The known-correct Rotten Tomatoes URL
            title: Movie title (for logging only)
            year: Movie year (for logging only)

        Returns:
            Score string (e.g., "85%") or None
        """
        if not self._init_gemini():
            return None

        label = f"{title} ({year})" if title else url

        prompt = (
            f"What is the Tomatometer critic score percentage shown on this exact "
            f"Rotten Tomatoes page: {url}\n\n"
            f"Return ONLY the percentage number (e.g., 85%) or NO_SCORE if no "
            f"Tomatometer score is displayed on the page."
        )

        try:
            from google.genai import types
            api_config = types.GenerateContentConfig(
                tools=[self.grounding_tool],
                temperature=0.0,
            )

            def _make_request():
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=api_config
                )
                return response.text.strip()

            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_make_request)
            if not result_text:
                return None

            if 'NO_SCORE' in result_text.upper():
                logger.info(f"No score on RT page for {label}: {url}")
                return None

            # Extract percentage
            score_match = re.search(r'(\d{1,3})%', result_text)
            if score_match:
                score = int(score_match.group(1))
                if 0 <= score <= 100:
                    logger.info(f"Gemini URL-specific score for {label}: {score}%")
                    return f"{score}%"

            logger.warning(f"Could not parse Gemini URL-specific response for {label}: {result_text}")
            return None

        except Exception as e:
            logger.error(f"Gemini URL-specific query error for {label}: {e}")
            return None


class HybridRTFinder:
    """
    Hybrid RT finder that tries Gemini first, falls back to Playwright.

    Usage:
        finder = HybridRTFinder()
        result = finder.find_rt_score("Conclave", 2024)
    """

    def __init__(self, cache_file: str = 'cache/rt_cache.json', config: Dict = None, logger_instance=None):
        """Initialize hybrid finder with both backends."""
        self.gemini_finder = GeminiRTFinder(cache_file=cache_file)
        self.playwright_scraper = None  # Lazy load
        self.cache_file = cache_file
        self.config = config or {}
        self.logger_instance = logger_instance

        self.stats = {
            'total_requests': 0,
            'gemini_resolved': 0,
            'playwright_resolved': 0,
            'fallback_attempts': 0,
            'total_failures': 0
        }

    def _get_playwright_scraper(self):
        """Lazy-load Playwright RT scraper only when needed."""
        if self.playwright_scraper is None:
            try:
                from rt_scraper_playwright import RTScraperPlaywright
                self.playwright_scraper = RTScraperPlaywright(
                    cache_file=self.cache_file,
                    config=self.config,
                    logger=self.logger_instance
                )
            except ImportError as e:
                logger.warning(f"Could not load Playwright RT fallback: {e}")
        return self.playwright_scraper

    @property
    def cache(self):
        """Expose cache for compatibility with generator.py."""
        return self.gemini_finder.cache

    def _validate_with_playwright(self, gemini_result: Dict, title: str, year: int,
                                    original_language: str = None, original_title: str = None) -> Optional[Dict[str, str]]:
        """Visit a Gemini-returned RT URL with Playwright to verify it's the right movie.

        Navigates to the RT page, extracts the actual movie title, and compares
        it against the expected title. Also extracts the real score from the page.

        Args:
            gemini_result: Dict with 'url' and 'score' from Gemini
            title: The movie title we searched for
            year: The movie release year
            original_language: ISO 639-1 language code; when not 'en' and neither
                             title matches, accept anyway (RT slug may be translated)
            original_title: Original-language title from TMDB (checked as alt match)

        Returns:
            Validated dict with 'url' and 'score', or None if wrong movie
        """
        url = gemini_result.get('url')
        if not url:
            return None

        playwright = self._get_playwright_scraper()
        if not playwright:
            logger.info("Playwright not available for validation, trusting Gemini result")
            return gemini_result

        try:
            # Initialize browser if needed
            playwright._init_browser()
            playwright._enforce_rate_limit()

            logger.info(f"Playwright validating Gemini URL: {url}")
            response = playwright.page.goto(url, wait_until='domcontentloaded')
            time.sleep(2)

            # Check HTTP status code
            if response and response.status >= 400:
                logger.warning(f"RT page returned HTTP {response.status}: {url}")
                return None

            # Extract page title — RT format: "Movie Name (Year) | Rotten Tomatoes"
            page_title = playwright.page.title() or ""

            # Check for 404 / not found (belt and suspenders with status check above)
            if 'page not found' in page_title.lower() or '404' in page_title:
                logger.warning(f"RT page not found: {url}")
                return None

            # Extract movie title from page title
            movie_part = page_title.split('|')[0].strip() if '|' in page_title else page_title.strip()

            # Validate year from page title before accepting match
            page_year_match = re.search(r'\((\d{4})\)', movie_part)
            if page_year_match and year:
                page_year = int(page_year_match.group(1))
                if abs(page_year - int(year)) > 1:  # Allow ±1 year for release date differences
                    logger.warning(
                        f"Playwright validation FAILED: page year {page_year} doesn't match "
                        f"expected ~{year} for '{title}' (page: '{movie_part}')"
                    )
                    return None

            page_movie_title = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_part).strip()

            # Compare titles (check both stored title and original_title)
            title_matches = page_title_matches(page_movie_title, title)
            alt_matches = (original_title and original_title != title and
                           page_title_matches(page_movie_title, original_title))

            if not title_matches and not alt_matches:
                if original_language and original_language != 'en':
                    # Foreign film — RT slug may be a translation we don't have
                    logger.info(
                        f"Accepting foreign-language film despite title mismatch "
                        f"({original_language}): page='{page_movie_title}', expected='{title}'"
                    )
                else:
                    logger.warning(
                        f"Playwright validation FAILED: page shows '{page_movie_title}', "
                        f"expected '{title}'"
                    )
                    return None

            # Title matched — extract actual score from the loaded page
            actual_score = extract_score_from_loaded_page(playwright)

            # If Playwright couldn't extract score, try Gemini URL-specific query
            if not actual_score:
                logger.info(f"Playwright couldn't extract score, trying Gemini URL-specific for {url}")
                actual_score = self.gemini_finder.find_score_for_url(url, title, year)

            logger.info(f"Playwright validated: '{page_movie_title}' matches '{title}', score={actual_score}")

            return {
                'url': url,
                'score': actual_score or gemini_result.get('score')
            }

        except Exception as e:
            logger.warning(f"Playwright validation error for {url}: {e}")
            # Don't trust unvalidated results — better no link than a wrong link
            return None

    def find_rt_score(
        self,
        title: str,
        year: int,
        director: str = None,
        use_fallback: bool = True,
        original_language: str = None,
        original_title: str = None
    ) -> Optional[Dict[str, str]]:
        """
        Find RT score using Playwright-primary search, Gemini score-only fallback.

        Flow:
        1. Check cache (existing entries preserved)
        2. PRIMARY: Playwright searches RT directly for URL + score
        3. If URL found but no score: Gemini reads the known URL for score
        4. OPTIONAL: Gemini search as last resort (disabled by default via config)

        Args:
            title: Movie title
            year: Release year
            director: Optional director for disambiguation
            use_fallback: Whether to try Gemini search as last resort
            original_language: ISO 639-1 language code (e.g. 'es', 'fr')
            original_title: Original-language title from TMDB (if different from title)

        Returns:
            Dict with 'url' and 'score', or None
        """
        self.stats['total_requests'] += 1
        cache_key = f"{title}_{year}"

        # --- Cache check ---
        cached = self.gemini_finder.cache.get(cache_key)
        if isinstance(cached, dict):
            if cached.get('url') and cached.get('score') and cached.get('_playwright_validated'):
                self.stats['playwright_resolved'] += 1
                return {'url': cached['url'], 'score': cached['score']}
            if cached.get('url') is None and cached.get('score') is None:
                # Previously confirmed: no RT page exists
                return None

        # --- PRIMARY: Playwright searches RT directly ---
        playwright = self._get_playwright_scraper()
        if playwright:
            try:
                result = playwright.scrape_rt_score(title, year)
                if result and result.get('url'):
                    # Playwright found the page — score extraction uses JSON-LD,
                    # media-scorecard, CSS selectors, and text regex. If all four
                    # methods found no score, the page genuinely has no Tomatometer
                    # score yet (e.g. new release with insufficient reviews).
                    # Do NOT fall back to Gemini — it returns stale/wrong scores.

                    # Cache the result
                    self.gemini_finder.cache[cache_key] = {
                        'url': result['url'],
                        'score': result.get('score'),
                        'title': title,
                        'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                        '_playwright_validated': True
                    }
                    self.gemini_finder._save_cache()
                    self.stats['playwright_resolved'] += 1
                    return result
            except Exception as e:
                logger.error(f"Playwright RT search error for {title} ({year}): {e}")

        # --- OPTIONAL: Gemini search as last resort (disabled by default) ---
        rt_search_enabled = self.config.get('gemini_scraper', {}).get('rt_search_enabled', False)
        if rt_search_enabled and use_fallback:
            logger.info(f"Trying Gemini RT search for {title} ({year})")
            result = self.gemini_finder.find_rt_score(title, year, director,
                        original_language=original_language, original_title=original_title)
            if result is not None:
                validated = self._validate_with_playwright(result, title, year,
                                original_language=original_language,
                                original_title=original_title)
                if validated:
                    if cache_key in self.gemini_finder.cache:
                        self.gemini_finder.cache[cache_key]['_playwright_validated'] = True
                        if validated.get('score'):
                            self.gemini_finder.cache[cache_key]['score'] = validated['score']
                        self.gemini_finder._save_cache()
                    self.stats['gemini_resolved'] += 1
                    return validated

        self.stats['total_failures'] += 1
        return None

    # Compatibility methods to match RTScraperPlaywright interface
    def scrape_rt_score(self, title: str, year: int, director: str = None) -> Optional[Dict[str, str]]:
        """Compatibility wrapper matching RTScraperPlaywright interface."""
        return self.find_rt_score(title, year, director=director)

    def get_stats(self) -> Dict[str, Any]:
        """Return combined statistics with compatibility aliases for generator.py."""
        gemini_stats = self.gemini_finder.get_stats()
        return {
            **self.stats,
            'gemini_stats': gemini_stats,
            # Compatibility aliases expected by generator.py
            'attempts': self.stats['total_requests'],
            'successes': self.stats['gemini_resolved'] + self.stats['playwright_resolved'],
            'cache_hits': gemini_stats.get('cache_hits', 0)
        }

    def close(self):
        """Clean up resources (compatibility with RTScraperPlaywright)."""
        self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        if self.playwright_scraper:
            try:
                self.playwright_scraper.close()
            except Exception as e:
                logger.warning(f"Failed to cleanup Playwright RT scraper: {e}")
