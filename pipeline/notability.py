"""Notability scoring — two-axis (acclaim × buzz), shared by enrichment, the
display pass, and /curate.

Flow:
  - Enrichment stores the cheap NUMERIC signals on the record:
        _imdb_votes, _tmdb_popularity, _wiki_language_count
  - The capsule factoid pass produces the QUALITATIVE facts (festival, awards,
    year-end lists, press_volume) — stored in the capsule cache.
  - This module combines them into a 0-100 Buzz score, a quadrant, and a
    compact `notability` block. Acclaim gates; buzz only adds.
"""
import json
import math
import re
import urllib.parse
import urllib.request

MAJOR_FESTS = (
    "cannes", "venice", "venezia", "orizzonti", "berlin", "berlinale", "sundance",
    "toronto", "tiff", "locarno", "sxsw", "south by", "tribeca", "telluride",
    "new york film festival", "nyff", "sheffield", "rotterdam", "iffr",
    "san sebastian", "karlovy", "guadalajara", "annecy", "sitges", "fantastic fest",
    "true/false", "cph:dox", "hot docs", "docfest", "amman", "idfa",
)


def _num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"[\d.]+", str(x))
    return float(m.group(0)) if m else None


def wikipedia_language_count(wiki_url, timeout=10):
    """Interlanguage-link count on the en.wiki article (incl. English). The
    anti-bias buzz anchor — many languages = globally notable. None on failure."""
    if not wiki_url:
        return None
    try:
        title = urllib.parse.unquote(wiki_url.rstrip("/").split("/wiki/")[-1])
        api = ("https://en.wikipedia.org/w/api.php?action=query&prop=langlinks"
               "&lllimit=500&format=json&titles=" + urllib.parse.quote(title))
        req = urllib.request.Request(api, headers={"User-Agent": "NRW-notability/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        page = next(iter(data.get("query", {}).get("pages", {}).values()), {})
        if "missing" in page:
            return 0
        return len(page.get("langlinks", [])) + 1
    except Exception:
        return None


def buzz_score(imdb_votes=None, tmdb_popularity=None, wiki_language_count=None,
               tmdb_vote_count=None, press_volume=None):
    """Composite 0-100 internet-attention score. Long-tailed signals log-scaled."""
    votes = imdb_votes or tmdb_vote_count or 0
    langs = wiki_language_count or 0
    pop = _num(tmdb_popularity) or 0
    pv = (press_volume or "").lower()
    votes_sub = min(45, math.log10(votes + 1) * 9)   # 1k≈27, 10k≈36, 100k≈45
    langs_sub = min(25, langs * 2.5)                 # 10+ languages = full
    pop_sub = min(15, pop * 0.75)
    press_sub = 15 if "heavy" in pv else 10 if "moderate" in pv else 5 if "light" in pv else 0
    return int(round(votes_sub + langs_sub + pop_sub + press_sub))


def quadrant(rt=None, mc=None, imdb=None, imdb_votes=None,
             festival=None, awards=None, bscore=0):
    """Two-axis label. Acclaim gates (IMDb only counts with enough votes; only
    major festivals/real awards count); buzz can only raise, never demote."""
    rt, mc, imdb = _num(rt), _num(mc), _num(imdb)
    fest = (festival or "").lower()
    awd = (awards or "").lower()
    has_fest = any(f in fest for f in MAJOR_FESTS)
    has_award = awd not in ("", "none found", "unverified", "n/a") \
        and "none" not in awd[:12] and "not " not in awd[:12]
    imdb_ok = imdb is not None and imdb_votes is not None and imdb_votes >= 500
    acclaim_high = (rt is not None and rt >= 70) or (mc is not None and mc >= 65) \
        or (imdb_ok and imdb >= 7.2) or has_fest or has_award
    acclaim_low = (not acclaim_high) and (
        (rt is not None and rt < 50) or (imdb_ok and imdb < 6.0)
        or (rt is None and mc is None and not has_fest and not has_award))
    buzz_high = bscore >= 60
    if acclaim_high and buzz_high:
        return "Consensus must-watch"
    if acclaim_high:
        return "Hidden gem"
    if buzz_high:
        return "Talked-about / divisive"
    if acclaim_low:
        return "Obscure - skip"
    return "Minor / unproven"


def build(record, qual=None):
    """Combine a movie record's numeric signals + the capsule pass's qualitative
    facts into {buzz_score, quadrant, festival, awards, yearend_lists}.

    record: data.json movie (scores + _imdb_votes/_tmdb_popularity/_wiki_language_count).
    qual:   {festival, awards, yearend_lists, press_volume} from the capsule cache (or None).
    """
    qual = qual or {}
    bscore = buzz_score(
        imdb_votes=record.get("_imdb_votes"),
        tmdb_popularity=record.get("_tmdb_popularity"),
        wiki_language_count=record.get("_wiki_language_count"),
        tmdb_vote_count=record.get("_tmdb_vote_count"),
        press_volume=qual.get("press_volume"),
    )
    quad = quadrant(
        rt=record.get("rt_score"), mc=record.get("metacritic_score"),
        imdb=record.get("imdb_rating"), imdb_votes=record.get("_imdb_votes"),
        festival=qual.get("festival"), awards=qual.get("awards"), bscore=bscore,
    )
    return {
        "buzz_score": bscore,
        "quadrant": quad,
        "festival": qual.get("festival"),
        "awards": qual.get("awards"),
        "yearend_lists": qual.get("yearend_lists"),
    }
