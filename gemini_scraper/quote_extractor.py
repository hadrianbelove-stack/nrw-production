"""
Quote extractor — selects the punchiest pull-quote line from Letterboxd reviews.

NOT a generator — Gemini selects from existing text.
Every extraction is verified as a verbatim substring of the original.
"""

import re
import logging
from typing import Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.quote_extractor')


class LetterboxdGeminiQuoteExtractor(GeminiFinderBase):
    """
    Extracts the punchiest pull-quote line from Letterboxd reviews.

    NOT a generator — Gemini selects from existing text.
    Every extraction is verified as a verbatim substring of the original.
    """

    _finder_name = 'QuoteExtractor'

    def __init__(self):
        super().__init__(cache_file='cache/quote_extractions_cache.json')

    def _get_extra_stats(self) -> Dict[str, int]:
        return {
            'reviews_processed': 0,
            'quotes_extracted': 0,
            'quotes_skipped': 0,
            'verification_failures': 0
        }

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
        pattern = r'\[(\d+)\]\s*(?:"([^"]+)"|[\u201c]([^\u201d]+)[\u201d]|SKIP)'

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
