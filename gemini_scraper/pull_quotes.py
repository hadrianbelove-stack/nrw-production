"""
Pull quote finder — discovers critic and Letterboxd quotes via Gemini + Google Search grounding.

Returns 5-10 quotes per movie for curator selection. All quotes default to
unselected — nothing displays on the site until manually approved.
"""

import re
import time
import logging
from typing import Optional, Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.pull_quotes')


class GeminiPullQuoteFinder(GeminiFinderBase):
    """
    Finds real critic quotes and Letterboxd reviews using Gemini with Google Search grounding.

    Usage:
        finder = GeminiPullQuoteFinder()
        quotes = finder.find_pull_quotes("The Brutalist", 2024, director="Brady Corbet")
        # Returns: list of quote dicts, or empty list
    """

    _finder_name = 'PullQuotes'

    def __init__(self, cache_file: str = 'cache/pull_quotes_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'quotes_found': 0, 'insufficient_quotes': 0}

    def _parse_quotes(self, text: str, source_type: str = 'critic') -> list:
        """Parse quote lines from Gemini response text."""
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

    def find_pull_quotes(
        self,
        title: str,
        year: int,
        director: str = None,
        num_quotes: int = 8
    ) -> list:
        """
        Find pull quotes for a movie using Gemini with Google Search grounding.

        Args:
            title: Movie title
            year: Release year
            director: Optional director name for context
            num_quotes: Number of quotes to request (default 8)

        Returns:
            List of quote dicts with keys: text, critic, outlet, source, selected, added_at
            Returns empty list if not enough quotes found.
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

        # Initialize Gemini
        if not self._init_gemini():
            return []

        self.stats['gemini_attempts'] += 1

        # Build context
        context = f'"{title}" ({year})'
        if director:
            context += f" directed by {director}"

        # --- Critic quotes prompt ---
        critic_prompt = f"""Find {num_quotes} real critic pull quotes for the movie {context}.

Requirements:
- Return ONLY real quotes from published professional reviews
- Each quote must include: the exact quote text, critic name, and publication name
- Do NOT fabricate or paraphrase quotes - only real published quotes
- If fewer than 3 real quotes exist, respond with: INSUFFICIENT_QUOTES

Source priority (mix these):
- Top tier: NYT, The New Yorker, Sight & Sound, Variety, IndieWire, The Guardian, RogerEbert.com, Hollywood Reporter
- Good indie: The Playlist, Little White Lies, Film Stage, Vulture, Associated Press
- A quote from a lesser-known outlet must be exceptionally well-written to justify inclusion

What makes a GREAT pull quote (follow these strictly):
- TRIM to the punchiest fragment. "artistic and social negligence" is better than the full sentence it came from. Strip the movie title from the front if the quote starts with it.
- Vivid specific adjectives over vague generic praise. "swoony, funny, panicky and sad" beats "a brilliant exploration of love and connection."
- Quotes that tell you WHAT THE FILM IS: genre descriptions ("dark screwball comedy"), tone/feel ("intimate, awkward, and loaded with possibility"), comparisons to other films.
- Sharp writing matters regardless of sentiment. A well-crafted negative quote is better than a bland positive one.
- Quotes that SELL the experience of watching the movie. Create curiosity in the reader.
- Look at the FIRST and LAST sentences of reviews — that's where the sharpest lines live (thesis + summary). The middle is usually evidence that doesn't stand alone.

What to AVOID:
- Academic jargon ("indicts the burden of proof placed upon personhood")
- Generic superlative stacking ("a masterful, stunning, powerful achievement")
- Sentences that don't stand alone without context
- Quotes that just summarize plot
- Awkward or clunky phrasing

Format each quote as:
QUOTE: "exact quote text" -- Critic Name, Publication Name | URL: https://full-review-url

The URL must be the direct link to the published review. This is critical for verification.

Response:"""

        all_quotes = []

        # Fetch critic quotes
        def _fetch_critic_quotes():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self._generate(critic_prompt, config=api_config)
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_fetch_critic_quotes)

            if result_text and 'INSUFFICIENT_QUOTES' not in result_text:
                critic_quotes = self._parse_quotes(result_text, source_type='critic')
                all_quotes.extend(critic_quotes)
                logger.info(f"Found {len(critic_quotes)} critic quotes for {title} ({year})")
            else:
                logger.info(f"Insufficient critic quotes for {title} ({year})")
                self.stats['insufficient_quotes'] += 1

        except Exception as e:
            logger.warning(f"Error fetching critic quotes for {title} ({year}): {e}")

        # --- Letterboxd quotes prompt ---
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
                all_quotes.extend(lb_quotes)
                logger.info(f"Found {len(lb_quotes)} Letterboxd quotes for {title} ({year})")

        except Exception as e:
            logger.warning(f"Error fetching Letterboxd quotes for {title} ({year}): {e}")

        # Cache results (even if empty, to avoid re-fetching)
        if all_quotes:
            self.stats['gemini_successes'] += 1
            self.stats['quotes_found'] += len(all_quotes)
        else:
            self.stats['gemini_failures'] += 1

        self.cache[cache_key] = {
            'quotes': all_quotes,
            'title': title,
            'year': year,
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S')
        }
        self._save_cache()

        return all_quotes
