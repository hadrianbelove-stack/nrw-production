"""
Claude-on-Max YouTube trailer finder — a drop-in for GeminiYouTubeFinder that
resolves trailers via a local headless Claude Code call (`claude -p` with
WebSearch) on the owner's flat Max subscription (~$0 marginal) instead of the
paid Gemini API.

Mixes in ClaudeBackendMixin, which overrides only the two low-level model
methods (_init_gemini / _generate); the trailer prompt, URL extraction,
liveness validation, and cache handling are inherited unchanged, so the cache
shape (cache/youtube_trailer_cache.json) stays byte-identical to the Gemini
path and HybridYouTubeFinder's Playwright fallback still applies.

Selected via NRW_YOUTUBE_BACKEND=claude (see HybridYouTubeFinder.__init__).
See gemini_scraper/claude_backend.py and gemini_scraper/claude_capsule.py.
"""

import os

from gemini_scraper.claude_backend import ClaudeBackendMixin
from gemini_scraper.youtube import GeminiYouTubeFinder


class ClaudeYouTubeFinder(ClaudeBackendMixin, GeminiYouTubeFinder):
    """GeminiYouTubeFinder that resolves via local `claude -p` on the Max plan."""

    _finder_name = 'ClaudeYouTube'

    def __init__(self, cache_file: str = 'cache/youtube_trailer_cache.json', model: str = None):
        super().__init__(cache_file=cache_file)
        override = model or os.environ.get('NRW_CLAUDE_YOUTUBE_MODEL')
        if override:
            self._claude_model = override
