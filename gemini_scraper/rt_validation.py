"""
Playwright-based validation utilities for Rotten Tomatoes pages.

Extracted from HybridRTFinder to keep rotten_tomatoes.py focused on
the finder logic. These are pure functions — no class state needed.
"""

import json
import re
import logging
from typing import Optional

logger = logging.getLogger('gemini_scraper.rt_validation')


def page_title_matches(page_title: str, expected_title: str) -> bool:
    """Check if an RT page title matches the expected movie title.

    Uses word overlap comparison with minimum threshold to prevent
    false matches on common words.
    """
    if not page_title or not expected_title:
        return False

    def normalize(s):
        s = s.lower()
        s = re.sub(r'^(the|a|an)\s+', '', s)
        s = re.sub(r'[^a-z0-9\s]', '', s)
        words = set(s.split())
        words -= {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'and', 'or', 'is', 'it'}
        # Keep numeric tokens (e.g. "30", "8") as they're distinctive in titles
        return {w for w in words if len(w) > 2 or w.isdigit()}

    page_words = normalize(page_title)
    expected_words = normalize(expected_title)

    if not expected_words:
        return True

    overlap = page_words & expected_words

    # For single-word titles, require the word to be present
    if len(expected_words) == 1:
        return expected_words <= page_words

    # Guard: if expected is a strict subset of page (page has extra words),
    # it's likely a different, longer-titled movie (e.g. "30 Minutes" vs "30 Minutes or Less").
    # Exception: RT TV pages append subtitle-like words ("Limited Series", "Season 1", etc.)
    # that don't indicate a different title.
    if overlap == expected_words and len(page_words) > len(expected_words):
        _subtitle_words = {'limited', 'series', 'season', 'miniseries', 'complete', 'collection'}
        extra_words = page_words - expected_words
        if not extra_words.issubset(_subtitle_words):
            return False

    # For multi-word titles, require majority overlap (>= 50% of expected words)
    overlap_ratio = len(overlap) / len(expected_words)
    if overlap_ratio >= 0.5:
        return True

    # Exact full-string match only (prevents partial containment false positives)
    page_flat = re.sub(r'[^a-z0-9]', '', page_title.lower())
    expected_flat = re.sub(r'[^a-z0-9]', '', expected_title.lower())
    if expected_flat == page_flat:
        return True

    return False


def extract_score_from_loaded_page(playwright_scraper) -> Optional[str]:
    """Extract RT critic score from an already-loaded Playwright page.

    Waterfall: JSON-LD -> CSS selectors -> text regex.
    """
    page = playwright_scraper.page

    # 1. JSON-LD structured data (most reliable)
    try:
        json_ld_scripts = page.query_selector_all('script[type="application/ld+json"]')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.text_content() or '{}')
                if 'aggregateRating' in data:
                    rating = data['aggregateRating'].get('ratingValue')
                    if rating:
                        score = str(int(float(rating)))
                        logger.debug(f"Found score via JSON-LD: {score}%")
                        return f"{score}%"
            except (json.JSONDecodeError, ValueError):
                continue
    except Exception:
        pass

    # 2. media-scorecard (current RT layout since ~2025)
    try:
        scorecard = page.query_selector('media-scorecard')
        if scorecard:
            text = (scorecard.text_content() or "").strip()
            # First percentage in scorecard is the critics score
            score_match = re.search(r'(\d{1,3})%', text)
            if score_match:
                score = int(score_match.group(1))
                if 0 <= score <= 100:
                    logger.debug(f"Found score via media-scorecard: {score}%")
                    return f"{score}%"
    except Exception:
        pass

    # 3. CSS selectors (current and legacy layouts)
    score_selectors = [
        'media-scorecard rt-text.critics-score',  # current RT layout (2025+)
        'rt-text.critics-score',
        '[slot="criticsScore"]',
        'rt-text[slot="criticsScore"]',
        '[data-testid="critic-score"] .percentage',
        '[data-testid="critics-score"] .percentage',
        '[class*="criticsScore"]',
        'score-board',
        '.scoreboard__critic .percentage',
        '.mop-ratings-wrap__percentage',
        '.meter-value',
        '.critic-score .percentage',
        '[class*="percentage"]',
    ]

    for selector in score_selectors:
        try:
            elements = page.query_selector_all(selector)
            for element in elements:
                text = (element.text_content() or "").strip()
                score_match = re.search(r'(\d+)%?', text)
                if score_match:
                    return f"{score_match.group(1)}%"
        except Exception:
            continue

    # 4. Text regex patterns (fallback)
    try:
        body = page.query_selector('body')
        if body:
            page_text = body.text_content() or ""
            for pattern in [r'(\d+)%\s*Tomatometer', r'(\d+)%\s*(?:Critics|Critic)', r'Tomatometer.*?(\d+)%']:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return f"{match.group(1)}%"
    except Exception:
        pass

    return None
