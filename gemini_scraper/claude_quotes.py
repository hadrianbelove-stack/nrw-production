"""
Claude-on-Max Letterboxd pull-quote scraper — a drop-in for LetterboxdQuoteScraper
that runs the Gemini parts (review-quote extraction + the rare LB-URL discovery)
on a local headless Claude Code call (`claude -p`, Max plan, ~$0) instead of the
paid Gemini API.

The valuable step — reading scraped Letterboxd reviews and picking the punchiest
verbatim pull quote — is pure text analysis (no grounding), which Claude does at
least as well. The review SCRAPING itself is Playwright (already free) and is
inherited unchanged. The one grounded path (LB-URL discovery, letterboxd_quotes.py
~L120) is a rare fallback (the URL is usually pre-found in data.json); it tries a
text regex on the model's answer first, so Claude's web-searched URL still works,
and the mixin's empty `.candidates` makes it skip the Gemini-metadata branch
without crashing.

See gemini_scraper/claude_backend.py and plan ~/.claude/plans/goofy-booping-canyon.md.
"""

import os

from gemini_scraper.claude_backend import ClaudeBackendMixin
from gemini_scraper.letterboxd_quotes import LetterboxdQuoteScraper


class ClaudeLetterboxdQuoteScraper(ClaudeBackendMixin, LetterboxdQuoteScraper):
    """LetterboxdQuoteScraper whose Gemini calls run via local `claude -p` on Max."""

    _finder_name = 'ClaudeLetterboxdQuotes'

    def __init__(self):
        super().__init__()
        override = os.environ.get('NRW_CLAUDE_QUOTES_MODEL')
        if override:
            self._claude_model = override
