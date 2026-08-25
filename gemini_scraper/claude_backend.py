"""
Shared Claude-on-Max backend for GeminiFinderBase subclasses.

Every Gemini call in these finders routes through GeminiFinderBase._generate(),
and the finders build inert genai *config objects* (GenerateContentConfig /
ThinkingConfig / grounding Tool) that only need the type module imported — no
API key, no client. So a finder can be switched to a local headless Claude Code
run (`claude -p`, billed to the owner's flat Max plan, ~$0) by mixing in this
class, which overrides just two low-level methods:

  * _init_gemini() — import the google.genai type objects the callers construct,
    set up a grounding Tool placeholder, but create NO client and require NO key.
  * _generate()    — shell out to `claude -p` with WebSearch/WebFetch enabled and
    return a `.text` shim (also `.candidates == []` so any Gemini
    grounding-metadata caller degrades to empty instead of crashing).

Put the mixin FIRST in the MRO so its overrides win:
    class ClaudeX(ClaudeBackendMixin, GeminiX): ...

Requires: `claude` CLI on PATH, logged into a Max/Pro plan, and NO
ANTHROPIC_API_KEY in the environment (a key would bill per-token instead of using
the subscription). See plan: ~/.claude/plans/goofy-booping-canyon.md.
"""

import os
import shutil
import subprocess
import logging

logger = logging.getLogger('gemini_scraper')

# Default model for MECHANICAL Claude finders (URL/ID/date lookups, e.g.
# ClaudeYouTubeFinder). Sonnet is plenty for fact-fetching and lighter on the Max
# plan's rate limits. The TASTE finders — ClaudeCapsuleWriter and
# ClaudeLetterboxdQuoteScraper — pin _claude_model = 'opus' on their own classes.
DEFAULT_CLAUDE_MODEL = os.environ.get('NRW_CLAUDE_MODEL', 'sonnet')
CLAUDE_TIMEOUT_SECONDS = int(os.environ.get('NRW_CLAUDE_TIMEOUT', '300'))


class _ClaudeResponse:
    """Minimal stand-in for a genai response. Callers read `.text`; a few
    grounding-aware callers read `.candidates` (kept empty so they degrade
    gracefully to the text path)."""
    __slots__ = ('text', 'candidates', 'usage_metadata')

    def __init__(self, text):
        self.text = text
        self.candidates = []
        self.usage_metadata = None


class ClaudeBackendMixin:
    """Route a GeminiFinderBase subclass's generation to local `claude -p`."""

    _claude_model = DEFAULT_CLAUDE_MODEL
    _claude_timeout = CLAUDE_TIMEOUT_SECONDS
    _claude_tools = ('WebSearch', 'WebFetch')

    def _init_gemini(self) -> bool:
        if self._initialized:
            # Base returns `self.client is not None`; we run clientless, so key
            # readiness off the type objects instead.
            return self.types is not None
        self._initialized = True

        if not shutil.which('claude'):
            logger.error(f"{self._finder_name}: `claude` CLI not found on PATH.")
            return False
        if os.environ.get('ANTHROPIC_API_KEY'):
            logger.warning("ANTHROPIC_API_KEY is set — claude -p may bill per-token "
                           "instead of using the Max subscription.")
        try:
            from google.genai import types  # import only — no client, no key
            self.types = types
            self.grounding_tool = types.Tool(google_search=types.GoogleSearch())
        except Exception as e:
            logger.error(f"{self._finder_name}: google-genai types needed: {e}")
            return False

        self.model_name = self._claude_model
        self.client = None
        logger.info(f"{self._finder_name}: Claude backend ready "
                    f"(local `claude -p`, model={self._claude_model})")
        return True

    def _generate(self, contents, config=None):
        """Send the prompt to `claude -p` and return a `.text` shim.

        The genai `config` (grounding/thinking) is Gemini-specific and ignored;
        Claude runs its own adaptive thinking, and WebSearch/WebFetch cover the
        grounding intent.
        """
        self._enforce_rate_limit()  # gentle pacing between Max calls
        cmd = ['claude', '-p', '--model', self._claude_model,
               '--allowedTools', *self._claude_tools]
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
