"""
Claude-on-Max capsule writer — a drop-in for GeminiCapsuleWriter that generates
capsules via a local headless Claude Code call (`claude -p`) on the owner's flat
Max subscription (~$0 marginal) instead of the paid Gemini API.

Capsule generation was NRW's single biggest Gemini cost (Gemini 2.5 Pro at a 32k
thinking budget × N variants). This subclass mixes in ClaudeBackendMixin, which
overrides only the two low-level model methods (_init_gemini / _generate); the
whole orchestrator — write_capsule(), HTTP fact-fetch, NOTABILITY/SUGGESTED_LINKS
parsing, Wikipedia link verification, cache writes, the approved-capsule bank, and
approve_capsule/_publish_to_data_json — is inherited unchanged, so the cache-entry
shape and return dict stay byte-identical to the Gemini path.

See gemini_scraper/claude_backend.py and plan ~/.claude/plans/goofy-booping-canyon.md.
"""

import os

from gemini_scraper.claude_backend import ClaudeBackendMixin
from gemini_scraper.capsule import GeminiCapsuleWriter


class ClaudeCapsuleWriter(ClaudeBackendMixin, GeminiCapsuleWriter):
    """GeminiCapsuleWriter that generates via local `claude -p` on the Max plan."""

    _finder_name = 'ClaudeCapsule'
    # Capsules are the marquee editorial prose — pin to Opus (better writing,
    # stricter fact-verify). Free at the margin on the Max plan, so the only cost
    # is a bit more of the nightly rate-limit budget. Override with
    # NRW_CLAUDE_CAPSULE_MODEL / model= if a run needs a lighter model.
    _claude_model = 'opus'

    def __init__(self, cache_file: str = 'cache/capsule_cache.json', model: str = None):
        super().__init__(cache_file=cache_file)
        override = model or os.environ.get('NRW_CLAUDE_CAPSULE_MODEL')
        if override:
            self._claude_model = override
