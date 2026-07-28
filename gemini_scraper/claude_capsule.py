"""
Claude-on-Max capsule writer — a drop-in for GeminiCapsuleWriter that generates
capsules via a local headless Claude Code call (`claude -p`) instead of the paid
Gemini API.

WHY: capsule generation was NRW's single biggest Gemini cost (Gemini 2.5 Pro at a
32k thinking budget × N variants). Claude Code run locally uses the owner's flat
**Max subscription** — ~$0 marginal per capsule — and writes at least as well.
See plan: ~/.claude/plans/goofy-booping-canyon.md.

HOW IT STAYS A DROP-IN: every Gemini call in the capsule pipeline routes through
GeminiCapsuleWriter._generate(), and every fact-gathering step (_build_context,
_fetch_wikipedia/rt/letterboxd/amazon/imdb, _verify_wikipedia_entity) is plain
HTTP — no Gemini. So this subclass overrides only two low-level methods:
  * _init_gemini() — set up the google.genai *type objects* the caller methods
    construct (GenerateContentConfig / ThinkingConfig / grounding Tool are inert
    data classes), WITHOUT creating a client or needing a GEMINI_API_KEY.
  * _generate()    — shell out to `claude -p` (with WebSearch/WebFetch enabled so
    Claude can research + verify facts, per owner's "Both" choice) and return a
    shim whose `.text` is Claude's answer.
Everything else — write_capsule(), the NOTABILITY/SUGGESTED_LINKS parsing, cache
writes, the approved-capsule bank, approve_capsule/_publish_to_data_json — is
inherited unchanged, so the output contract (cache entry shape + return dict) is
byte-identical to the Gemini path and the rest of the pipeline is untouched.

Requires: `claude` CLI on PATH, logged in to a Max/Pro plan, and NO ANTHROPIC_API_KEY
in the environment (a key would bill per-token instead of using the subscription).
"""

import os
import shutil
import subprocess
import logging

from gemini_scraper.capsule import GeminiCapsuleWriter

logger = logging.getLogger('gemini_scraper')

# Model for the local Claude Code capsule run. Sonnet balances quality vs the
# Max plan's rate limits; override with NRW_CLAUDE_CAPSULE_MODEL (e.g. "opus").
DEFAULT_CLAUDE_MODEL = os.environ.get('NRW_CLAUDE_CAPSULE_MODEL', 'sonnet')
# Web search can make a call run a while; bound it so a hang can't wedge a batch.
CLAUDE_TIMEOUT_SECONDS = int(os.environ.get('NRW_CLAUDE_CAPSULE_TIMEOUT', '300'))


class _ClaudeResponse:
    """Minimal stand-in for a genai response — callers only read `.text`."""
    __slots__ = ('text', 'usage_metadata')

    def __init__(self, text):
        self.text = text
        self.usage_metadata = None


class ClaudeCapsuleWriter(GeminiCapsuleWriter):
    """GeminiCapsuleWriter that generates via local `claude -p` on the Max plan."""

    _finder_name = 'ClaudeCapsule'

    def __init__(self, cache_file: str = 'cache/capsule_cache.json', model: str = None):
        super().__init__(cache_file=cache_file)
        self._claude_model = model or DEFAULT_CLAUDE_MODEL
        self._claude_timeout = CLAUDE_TIMEOUT_SECONDS

    # -- Set up the type objects the caller methods build, without a Gemini key --
    def _init_gemini(self) -> bool:
        if self._initialized:
            # Base returns `self.client is not None`; we run clientless, so answer
            # on whether the type objects are ready instead.
            return self.types is not None
        self._initialized = True

        if not shutil.which('claude'):
            logger.error("ClaudeCapsuleWriter: `claude` CLI not found on PATH.")
            return False
        if os.environ.get('ANTHROPIC_API_KEY'):
            # Not fatal, but warn: a key means claude -p may bill per-token rather
            # than draw on the Max subscription we're trying to use for free.
            logger.warning("ANTHROPIC_API_KEY is set — claude -p may bill per-token "
                           "instead of using the Max subscription.")
        try:
            from google.genai import types  # import only — no client, no key
            self.types = types
            self.grounding_tool = types.Tool(google_search=types.GoogleSearch())
        except Exception as e:
            logger.error(f"ClaudeCapsuleWriter needs google-genai types installed: {e}")
            return False

        self.model_name = self._claude_model
        self.client = None
        logger.info(f"Claude capsule writer ready (local `claude -p`, model={self._claude_model})")
        return True

    # -- Route generation to a local headless Claude Code call (Max plan, ~$0) --
    def _generate(self, contents, config=None):
        """Send the prompt to `claude -p` and return a `.text` shim.

        `config` (a genai GenerateContentConfig the caller built) is ignored —
        its grounding/thinking settings are Gemini-specific. Claude runs its own
        adaptive thinking; WebSearch/WebFetch cover the grounding intent.
        """
        self._enforce_rate_limit()  # gentle pacing between Max calls
        cmd = [
            'claude', '-p',
            '--model', self._claude_model,
            # Pre-allow read-only research tools so the headless run never blocks
            # on a permission prompt (it can't answer one).
            '--allowedTools', 'WebSearch', 'WebFetch',
        ]
        try:
            proc = subprocess.run(
                cmd, input=str(contents), capture_output=True, text=True,
                cwd='/tmp',  # keep the nested call lean — no project context load
                timeout=self._claude_timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"claude -p timed out after {self._claude_timeout}s")
            return _ClaudeResponse(None)
        except Exception as e:
            logger.warning(f"claude -p invocation failed: {e}")
            return _ClaudeResponse(None)

        out = (proc.stdout or '').strip()
        if proc.returncode != 0 or not out:
            logger.warning(f"claude -p returned nothing (rc={proc.returncode}): "
                           f"{(proc.stderr or '')[:200]}")
            return _ClaudeResponse(None)
        return _ClaudeResponse(out)
