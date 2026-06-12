"""
Gemini-based scrapers for movie metadata discovery.

Split from monolithic gemini_scraper.py for maintainability (May 2026).
Each finder lives in its own module; this __init__.py re-exports them all
so existing `from gemini_scraper import X` imports work unchanged.

Pull-quote flow (June 2026 naming cleanup):
  - pull_quotes.py / PullQuoteFinder — orchestrator: RT + Metacritic + Letterboxd
  - letterboxd_quotes.py / LetterboxdQuoteScraper — Letterboxd reviews + Gemini
    verbatim quote extraction (absorbed the old quote_extractor.py)
  - letterboxd_scraper.py (repo root) / LetterboxdScoreScraper — star ratings only
"""

from gemini_scraper.base import GeminiFinderBase
from gemini_scraper.youtube import GeminiYouTubeFinder, HybridYouTubeFinder
from gemini_scraper.rotten_tomatoes import GeminiRTFinder, HybridRTFinder
from gemini_scraper.wikipedia import GeminiWikipediaFinder
from gemini_scraper.vod_date import GeminiVODDateFinder
from gemini_scraper.pull_quotes import PullQuoteFinder, GeminiPullQuoteFinder
from gemini_scraper.letterboxd_quotes import LetterboxdQuoteScraper, LetterboxdGeminiQuoteExtractor
from gemini_scraper.imdb import GeminiIMDbFinder
from gemini_scraper.capsule import GeminiCapsuleWriter

__all__ = [
    'GeminiFinderBase',
    'GeminiYouTubeFinder',
    'HybridYouTubeFinder',
    'GeminiRTFinder',
    'HybridRTFinder',
    'GeminiWikipediaFinder',
    'GeminiVODDateFinder',
    'PullQuoteFinder',
    'LetterboxdQuoteScraper',
    'GeminiIMDbFinder',
    'GeminiCapsuleWriter',
    # Legacy aliases (pre-June-2026 names)
    'GeminiPullQuoteFinder',
    'LetterboxdGeminiQuoteExtractor',
]
