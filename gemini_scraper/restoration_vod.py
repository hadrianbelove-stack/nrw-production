"""
Restoration-on-VOD "catch" finder via Gemini + Google Search grounding.

Answers the version-aware question the structured signals can't: has the *specific
new restoration* of a film reached US home digital (VOD rent/buy or subscription
streaming) — as opposed to an OLDER transfer of the same title that is often
already streaming?

Validated 2026-06-28/30 against hand-labeled hard cases (Gold Rush = old transfer
streaming while restoration is theatrical-only; Fight Club / Yi Yi = restoration on
VOD; Sorcerer = disc-only). Structured JustWatch signals get these wrong ~44% of
the time (see docs/DISTRIBUTOR_TRACKING_PLAN.md "Empirical findings"); this reads
the version the way a person does — runtime, 4K/Dolby specs, credited lab, whether
a digital listing predates the restoration — and returns sources.

NOTE: grounding (Google Search tool) is incompatible with response_mime_type=json,
so the model returns a labeled-field block that we parse (same approach as
gemini_scraper/vod_date.py's DATE:/PREORDER_ONLY parsing).
"""

import re
import time
import logging
from typing import Optional, Dict, List

from gemini_scraper.base import GeminiFinderBase
from utils.datetime_utils import is_cache_fresh

logger = logging.getLogger('gemini_scraper.restoration_vod')

# How long a verdict stays fresh. Availability changes over time (that's the whole
# point of the catch), so keep this short — a parked title is re-checked often.
_CACHE_TTL_DAYS = 14

_AVAILABLE_VALUES = {'yes', 'no', 'theatrical_only', 'disc_only', 'unclear'}
_VERSION_VALUES = {'yes', 'no', 'unclear'}
_CONFIDENCE_VALUES = {'high', 'medium', 'low'}


class GeminiRestorationVODFinder(GeminiFinderBase):
    """
    Version-aware "is this restoration on US VOD?" resolver.

    Usage:
        finder = GeminiRestorationVODFinder()
        verdict = finder.find_restoration_vod_status(
            "The Gold Rush", 1925,
            restoration_note="2025 4K restoration (Cineteca di Bologna/mk2), "
                             "premiered Cannes Classics 2025",
        )
        # verdict['on_vod'] -> False   (theatrical-only; only the old transfer streams)

    Returns a dict:
        {
          'available': 'yes'|'no'|'theatrical_only'|'disc_only'|'unclear',
          'is_restoration_version': 'yes'|'no'|'unclear',
          'on_vod': bool,          # the catch decision: available=yes AND version=yes
          'platforms': [str, ...],
          'since_date': 'YYYY-MM' or 'YYYY-MM-DD' or '',
          'confidence': 'high'|'medium'|'low',
          'basis': str,
          'sources': [str, ...],
        }
    or None if the API could not be reached.
    """

    _finder_name = 'RestorationVOD'

    def __init__(self, cache_file: str = 'cache/restoration_vod_cache.json'):
        super().__init__(cache_file=cache_file)

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'on_vod': 0, 'not_on_vod': 0, 'unclear': 0}

    # ------------------------------------------------------------------ public

    def find_restoration_vod_status(
        self,
        title: str,
        year: int,
        restoration_note: str = '',
    ) -> Optional[Dict]:
        """Resolve whether the film's new restoration is on US VOD, version-aware.

        Args:
            title: Film title.
            year: Film's original release year (identity, not the restoration year).
            restoration_note: What we know about the restoration (lab / year / format /
                festival). Anchors the query so the model checks the RIGHT version.

        Returns:
            Verdict dict (see class docstring), or None if the API failed.
        """
        cache_key = f"{title}_{year}"

        cached = self._cache_get(cache_key)
        if cached is not None:
            self.stats['cache_hits'] += 1
            logger.debug(f"Restoration-VOD cache hit for {title} ({year}): "
                         f"on_vod={cached.get('on_vod')}")
            return cached

        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1
        prompt = self._build_prompt(title, year, restoration_note)

        def _make_api_request():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self._generate(prompt, config=api_config)
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_make_api_request)
            if not result_text:
                logger.error(f"All retries failed for restoration-VOD {title} ({year})")
                self.stats['gemini_failures'] += 1
                return None

            logger.debug(f"Gemini restoration-VOD response for {title}: {result_text[:300]}")
            verdict = self._parse(result_text)

            # tally
            if verdict['on_vod']:
                self.stats['on_vod'] += 1
            elif verdict['is_restoration_version'] == 'unclear' or verdict['available'] == 'unclear':
                self.stats['unclear'] += 1
            else:
                self.stats['not_on_vod'] += 1
            self.stats['gemini_successes'] += 1

            self._cache_put(cache_key, title, year, verdict, result_text)
            logger.info(f"Restoration-VOD verdict for {title} ({year}): "
                        f"available={verdict['available']} "
                        f"version={verdict['is_restoration_version']} "
                        f"on_vod={verdict['on_vod']} ({verdict['confidence']})")
            return verdict

        except Exception as e:
            logger.error(f"Gemini restoration-VOD API error for {title} ({year}): {e}")
            self.stats['gemini_failures'] += 1
            return None

    # ------------------------------------------------------------------ internals

    def _build_prompt(self, title: str, year: int, restoration_note: str) -> str:
        note = restoration_note.strip() or "(no restoration details supplied — identify the most recent restoration yourself)"
        return f"""You determine whether a specific FILM RESTORATION has reached US home digital \
(VOD: rent/buy, or subscription streaming) right now — version-aware. Use Google Search \
(trade news, distributor pages, JustWatch, Blu-ray.com, festival pages).

FILM: "{title}" ({year})
KNOWN RESTORATION: {note}

Answer AS OF today, US market. The hard part: distinguish the NEW restoration from any \
OLDER transfer of the same film that may already stream on the same title. Version cues to \
use — the restored cut's runtime, 4K / Dolby Vision / HDR specs, the distributor or lab \
credited in the listing, and whether a digital listing predates the restoration.

Respond in EXACTLY this labeled format, one field per line, nothing else:
AVAILABLE: <yes = the restoration is on US home digital now | no = not on digital | theatrical_only | disc_only>
IS_RESTORATION_VERSION: <yes = what's on US digital is the new restoration | no = only an older transfer is digital | unclear>
PLATFORMS: <comma-separated US platforms carrying the restoration, or NONE>
SINCE_DATE: <YYYY-MM the restoration reached US digital, or NONE>
CONFIDENCE: <high | medium | low>
BASIS: <one or two sentences citing the deciding evidence>
SOURCES: <2-5 URLs, comma-separated>

If you cannot confirm, use unclear / NONE and low confidence rather than guessing."""

    def _parse(self, text: str) -> Dict:
        available = self._field(text, 'AVAILABLE', _AVAILABLE_VALUES, 'unclear')
        version = self._field(text, 'IS_RESTORATION_VERSION', _VERSION_VALUES, 'unclear')
        confidence = self._field(text, 'CONFIDENCE', _CONFIDENCE_VALUES, 'low')

        platforms = self._list_field(text, 'PLATFORMS')
        since = self._since_date(text)
        basis = self._raw_field(text, 'BASIS')
        sources = self._urls(self._raw_field(text, 'SOURCES'))

        on_vod = (available == 'yes' and version == 'yes')

        return {
            'available': available,
            'is_restoration_version': version,
            'on_vod': on_vod,
            'platforms': platforms,
            'since_date': since,
            'confidence': confidence,
            'basis': basis,
            'sources': sources,
        }

    @staticmethod
    def _raw_field(text: str, label: str) -> str:
        m = re.search(rf'^{label}:\s*(.+?)\s*$', text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ''

    def _field(self, text: str, label: str, allowed: set, default: str) -> str:
        raw = self._raw_field(text, label).lower()
        tokens = [t for t in re.split(r'[^a-z_]+', raw) if t]
        # take the first allowed token that appears (model sometimes adds a gloss)
        for token in tokens:
            if token in allowed:
                return token
        # natural-language forms: "theatrical only" / "disc-only" → underscore token
        for a, b in zip(tokens, tokens[1:]):
            if f'{a}_{b}' in allowed:
                return f'{a}_{b}'
        return default

    def _list_field(self, text: str, label: str) -> List[str]:
        raw = self._raw_field(text, label)
        if not raw or raw.strip().lower() in ('none', 'n/a', ''):
            return []
        parts = [p.strip() for p in raw.split(',')]
        return [p for p in parts if p and p.lower() not in ('none', 'n/a')]

    @staticmethod
    def _since_date(text: str) -> str:
        raw = re.search(r'^SINCE_DATE:\s*(.+?)\s*$', text, re.IGNORECASE | re.MULTILINE)
        if not raw:
            return ''
        m = re.search(r'(\d{4}-\d{2}(?:-\d{2})?)', raw.group(1))
        return m.group(1) if m else ''

    @staticmethod
    def _urls(raw: str) -> List[str]:
        return re.findall(r'https?://[^\s,]+', raw)

    # ------------------------------------------------------------------ cache

    def _cache_get(self, key: str) -> Optional[Dict]:
        entry = self.cache.get(key)
        if not isinstance(entry, dict):
            return None
        if not is_cache_fresh(entry.get('scraped_at', ''), _CACHE_TTL_DAYS):
            return None
        verdict = entry.get('verdict')
        return verdict if isinstance(verdict, dict) else None

    def _cache_put(self, key: str, title: str, year: int, verdict: Dict, raw: str):
        self.cache[key] = {
            'verdict': verdict,
            'title': title,
            'year': year,
            'source': 'gemini',
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'raw_response': raw[:800],
        }
        self._save_cache()


if __name__ == '__main__':
    # Manual smoke test (hits the live API): python -m gemini_scraper.restoration_vod
    import json
    finder = GeminiRestorationVODFinder()
    v = finder.find_restoration_vod_status(
        "The Gold Rush", 1925,
        restoration_note="2025 4K restoration (Cineteca di Bologna/mk2), Cannes Classics 2025, theatrical",
    )
    print(json.dumps(v, indent=2))
