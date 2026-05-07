"""
Gemini-based scrapers for movie metadata discovery.

Split from monolithic gemini_scraper.py for maintainability (May 2026).
Each finder lives in its own module; this __init__.py re-exports them all
so existing `from gemini_scraper import X` imports work unchanged.
"""

from gemini_scraper.base import GeminiFinderBase
from gemini_scraper.youtube import GeminiYouTubeFinder, HybridYouTubeFinder
from gemini_scraper.rotten_tomatoes import GeminiRTFinder, HybridRTFinder
from gemini_scraper.wikipedia import GeminiWikipediaFinder
from gemini_scraper.vod_date import GeminiVODDateFinder
from gemini_scraper.pull_quotes import GeminiPullQuoteFinder
from gemini_scraper.quote_extractor import GeminiQuoteExtractor
from gemini_scraper.imdb import GeminiIMDbFinder
from gemini_scraper.watch_link import GeminiWatchLinkFinder

__all__ = [
    'GeminiFinderBase',
    'GeminiYouTubeFinder',
    'HybridYouTubeFinder',
    'GeminiRTFinder',
    'HybridRTFinder',
    'GeminiWikipediaFinder',
    'GeminiVODDateFinder',
    'GeminiPullQuoteFinder',
    'GeminiQuoteExtractor',
    'GeminiIMDbFinder',
    'GeminiWatchLinkFinder',
]
