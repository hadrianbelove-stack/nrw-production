"""Read-the-article headline resolver via Gemini + Google Search grounding.

Pass F's heuristics (quoted-title + no-year TMDB match) resolve the easy
headlines; this finder owns the flagged-but-unresolved rest — the owner's rule:
"headline cues whether an article is worth reading … we will have to read the
flagged ones." Google News RSS links are JS-redirects a plain fetch can't
follow, so V1 reads the article the validated way (same pattern as
restoration_vod.py): grounded search over the headline + publisher + date.

Answers: which FILM is the subject of this restoration headline, its original
year, whether it's genuinely restoration news (vs. keyword noise), the
distributor if stated, and whether the article mentions digital/VOD — the last
one feeds Stage 2 (vod_announced) of the restoration lifecycle.

NOTE: grounding is incompatible with response_mime_type=json, so the model
returns a labeled-field block that we parse (same as restoration_vod.py).
"""

import re
import time
import logging
from typing import Optional, Dict

from gemini_scraper.base import GeminiFinderBase

logger = logging.getLogger('gemini_scraper.news_title')

_TRI_VALUES = {'yes', 'no', 'unclear'}
_CONFIDENCE_VALUES = {'high', 'medium', 'low'}


class GeminiNewsTitleFinder(GeminiFinderBase):
    """
    Usage:
        finder = GeminiNewsTitleFinder()
        res = finder.resolve_headline(
            'UK "suedehead" subculture film "Bronco Bullfrog" gets new 2K restoration',
            source='Far Out Magazine', date='2026-07-05')
        # res['film_title'] -> 'Bronco Bullfrog', res['film_year'] -> 1969

    Returns a dict:
        {
          'film_title': str or '',
          'film_year': int or None,
          'is_restoration_news': 'yes'|'no'|'unclear',
          'distributor': str,
          'vod_mention': 'yes'|'no'|'unclear',
          'confidence': 'high'|'medium'|'low',
          'basis': str,
        }
    or None if the API could not be reached. Headline resolutions are static,
    so cache entries never expire.
    """

    _finder_name = 'NewsTitle'

    def __init__(self, cache_file: str = 'cache/news_title_cache.json'):
        super().__init__(cache_file=cache_file)

    def _init_gemini(self) -> bool:
        ok = super()._init_gemini()
        if ok:
            # Headline/article extraction doesn't need pro (base pins pro).
            self.model_name = 'gemini-2.5-flash'
        return ok

    def _get_extra_stats(self) -> Dict[str, int]:
        return {'resolved': 0, 'not_restoration': 0, 'unclear': 0}

    # ------------------------------------------------------------------ public

    def resolve_headline(self, headline: str, source: str = '',
                         date: str = '') -> Optional[Dict]:
        cache_key = re.sub(r'\s+', ' ', headline.lower()).strip()[:120]

        entry = self.cache.get(cache_key)
        if isinstance(entry, dict) and isinstance(entry.get('result'), dict):
            self.stats['cache_hits'] += 1
            return entry['result']

        if not self._init_gemini():
            return None

        self.stats['gemini_attempts'] += 1
        prompt = self._build_prompt(headline, source, date)

        def _make_api_request():
            api_config = self.types.GenerateContentConfig(tools=[self.grounding_tool])
            response = self._generate(prompt, config=api_config)
            return response.text.strip()

        try:
            self._enforce_rate_limit()
            result_text = self._retry_with_backoff(_make_api_request)
            if not result_text:
                self.stats['gemini_failures'] += 1
                return None
            result = self._parse(result_text)

            if result['is_restoration_news'] == 'no':
                self.stats['not_restoration'] += 1
            elif result['film_title'] and result['film_year']:
                self.stats['resolved'] += 1
            else:
                self.stats['unclear'] += 1
            self.stats['gemini_successes'] += 1

            self.cache[cache_key] = {
                'result': result,
                'headline': headline,
                'source': 'gemini',
                'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'raw_response': result_text[:500],
            }
            self._save_cache()
            logger.info(f"News-title resolution: {headline[:60]!r} -> "
                        f"{result['film_title']!r} ({result['film_year']}) "
                        f"restoration={result['is_restoration_news']} "
                        f"[{result['confidence']}]")
            return result

        except Exception as e:
            logger.error(f"Gemini news-title API error for {headline[:60]!r}: {e}")
            self.stats['gemini_failures'] += 1
            return None

    # ------------------------------------------------------------------ internals

    def _build_prompt(self, headline: str, source: str, date: str) -> str:
        return f"""You identify which FILM a news headline is about. Use Google Search to find \
and read the article when the headline alone is not enough.

HEADLINE: "{headline}"
PUBLISHER: {source or 'unknown'}    DATE: {date or 'unknown'}

The headline came from a film-restoration news feed. A headline can mention several \
films, people, or subcultures — identify the film that is the SUBJECT of the \
restoration / re-release news.

Respond in EXACTLY this labeled format, one field per line, nothing else:
FILM_TITLE: <the restored film's title, or NONE>
FILM_YEAR: <the film's ORIGINAL release year YYYY, or NONE>
IS_RESTORATION_NEWS: <yes = real restoration/re-release news about a specific film | no = keyword noise, not about a film restoration | unclear>
DISTRIBUTOR: <the distributor/label handling the restoration if stated, or NONE>
VOD_MENTION: <yes = the article mentions digital/VOD/streaming availability for the restoration | no | unclear>
CONFIDENCE: <high | medium | low>
BASIS: <one sentence citing the deciding evidence>

If you cannot identify the film, use NONE / unclear and low confidence rather than guessing."""

    def _parse(self, text: str) -> Dict:
        def raw(label):
            m = re.search(rf'^{label}:\s*(.+?)\s*$', text, re.IGNORECASE | re.MULTILINE)
            return m.group(1).strip() if m else ''

        def tri(label, default='unclear'):
            v = raw(label).lower()
            for token in re.split(r'[^a-z]+', v):
                if token in _TRI_VALUES:
                    return token
            return default

        title = raw('FILM_TITLE')
        if title.strip().lower() in ('none', 'n/a', ''):
            title = ''
        ym = re.search(r'(19|20)\d{2}', raw('FILM_YEAR'))
        year = int(ym.group(0)) if ym else None
        dist = raw('DISTRIBUTOR')
        if dist.strip().lower() in ('none', 'n/a', ''):
            dist = ''
        conf = raw('CONFIDENCE').lower()
        conf = conf if conf in _CONFIDENCE_VALUES else 'low'

        return {
            'film_title': title,
            'film_year': year,
            'is_restoration_news': tri('IS_RESTORATION_NEWS'),
            'distributor': dist,
            'vod_mention': tri('VOD_MENTION'),
            'confidence': conf,
            'basis': raw('BASIS'),
        }


if __name__ == '__main__':
    # Manual smoke test (hits the live API): python -m gemini_scraper.news_title
    import json
    finder = GeminiNewsTitleFinder()
    r = finder.resolve_headline(
        'UK "suedehead" subculture film \'Bronco Bullfrog\' gets new 2K restoration, '
        'in theaters this fall', source='Far Out Magazine', date='2026-07-05')
    print(json.dumps(r, indent=2))
