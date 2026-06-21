#!/usr/bin/env python3
"""
NOTABILITY SANDBOX — two-axis (Acclaim / Buzz) scorer for NRW films.

SANDBOX / read-only: reads data.json + public APIs, writes ONLY to
cache/notability_dossier_SANDBOX.json. Touches nothing in the pipeline.

Numeric signals (free / keys you already have):
  - scores from data.json (imdb_rating, rt_score, metacritic_score)
  - Wikipedia language-edition count  (MediaWiki API, no key) -- the anti-bias buzz anchor
  - TMDB popularity + vote_count       (TMDB_API_KEY)
  - IMDb vote count                    (OMDb imdbVotes, OMDB_API_KEY)
  - YouTube trailer views              (slot; needs YouTube Data API v3 enabled -> n/a for now)
Qualitative signals (Gemini 2.5 Flash + Google Search grounding -- same engine the
pipeline already uses for capsules/quotes):
  - festival selection, awards, year-end critic lists, reception summary, explanation

Quadrant is computed deterministically from the signals (acclaim gates, buzz only adds):
  high acclaim + high buzz -> Consensus must-watch
  high acclaim + low  buzz -> Hidden gem
  low  acclaim + high buzz -> Talked-about / divisive
  low  acclaim + low  buzz -> Obscure - skip
"""
import argparse, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "cache" / "notability_dossier_SANDBOX.json"

# ---- keys -------------------------------------------------------------------
def load_env():
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env
ENV = load_env()
TMDB_KEY = ENV.get("TMDB_API_KEY", "")
OMDB_KEY = ENV.get("OMDB_API_KEY", "")
GEMINI_KEY = ENV.get("GEMINI_API_KEY", "")

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "NRW-notability-sandbox/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

# ---- numeric signals --------------------------------------------------------
def wiki_language_count(wiki_url):
    """Count interlanguage links on the en.wiki article (incl. English itself)."""
    if not wiki_url:
        return None
    try:
        title = urllib.parse.unquote(wiki_url.rstrip("/").split("/wiki/")[-1])
        api = ("https://en.wikipedia.org/w/api.php?action=query&prop=langlinks"
               "&lllimit=500&format=json&titles=" + urllib.parse.quote(title))
        data = _get(api)
        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        if "missing" in page:
            return 0
        return len(page.get("langlinks", [])) + 1  # +1 for English
    except Exception:
        return None

def tmdb_signals(movie_id):
    if not TMDB_KEY or not movie_id:
        return {}
    is_tv = str(movie_id).startswith("tv_")
    mid = str(movie_id).replace("tv_", "")
    kind = "tv" if is_tv else "movie"
    try:
        d = _get(f"https://api.themoviedb.org/3/{kind}/{mid}?api_key={TMDB_KEY}")
        return {"tmdb_popularity": d.get("popularity"),
                "tmdb_vote_count": d.get("vote_count"),
                "tmdb_vote_average": d.get("vote_average")}
    except Exception:
        return {}

def omdb_votes(imdb_url):
    if not OMDB_KEY or not imdb_url:
        return {}
    m = re.search(r"(tt\d+)", imdb_url)
    if not m:
        return {}
    try:
        d = _get(f"http://www.omdbapi.com/?i={m.group(1)}&apikey={OMDB_KEY}")
        votes = d.get("imdbVotes", "N/A").replace(",", "")
        return {"imdb_votes": int(votes) if votes.isdigit() else None,
                "omdb_awards": None if d.get("Awards") in (None, "N/A") else d.get("Awards")}
    except Exception:
        return {}

# ---- qualitative (Gemini + grounding) --------------------------------------
def gemini_research(title, year, numeric):
    """One grounded call: festival/awards/year-end + reception + explanation, sourced."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"error": "google-genai not installed"}
    client = genai.Client(api_key=GEMINI_KEY, http_options=types.HttpOptions(timeout=120000))
    grounding = types.Tool(google_search=types.GoogleSearch())
    prompt = f"""You are researching the NOTABILITY of a film for a customer who wants to know
"what's supposed to be good" and "are there hidden gems". Be ORIGIN-BLIND: never penalize a
foreign film for quiet English-language chatter. Use Google Search; cite a source URL for every
factual claim. Do NOT invent awards, festivals, or reviews — if you cannot confirm something,
say "unverified". Known failure mode: confusing a same-title film — verify identity by year/plot.

FILM: "{title}" ({year})
Known numeric signals already gathered: {json.dumps(numeric)}

Research and return ONLY a JSON object (no prose, no markdown fence) with exactly these keys:
{{
 "festival": "festivals it screened/competed at with prizes, or 'none found' / 'unverified'",
 "awards": "named awards/nominations, or 'none found' / 'unverified'",
 "yearend_lists": "any critic year-end 'best of' list inclusions, or 'none found'",
 "reception": "1-2 sentence summary of how critics/audiences received it",
 "press_volume": "one of: heavy / moderate / light / minimal — how much trade/news/Reddit coverage exists",
 "explanation": "3-4 sentences for the customer: what this film IS, why it's notable or not, what people say. Plain, specific, no marketing language.",
 "sources": ["url", "url", ...]
}}"""
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(tools=[grounding]),
        )
        text = resp.text or ""
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {"error": "no json", "raw": text[:300]}
        return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)[:200]}

# ---- quadrant logic (acclaim gates, buzz only adds) ------------------------
def num(x):
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    m = re.search(r"[\d.]+", str(x))
    return float(m.group(0)) if m else None

import math
MAJOR_FESTS = ("cannes", "venice", "venezia", "orizzonti", "berlin", "berlinale", "sundance",
               "toronto", "tiff", "locarno", "sxsw", "south by", "tribeca", "telluride",
               "new york film festival", "nyff", "sheffield", "rotterdam", "iffr",
               "san sebastian", "karlovy", "guadalajara", "annecy", "sitges", "fantastic fest",
               "true/false", "cph:dox", "hot docs", "docfest", "amman")

def buzz_score(rec, q):
    """One composite 0-100 'how much is the internet paying attention' score.
    Inputs (hidden from the user): IMDb votes, TMDB popularity, Wikipedia language
    reach, press volume. Long-tailed signals are log-scaled. Never shown raw."""
    votes = rec.get("_imdb_votes") or num(rec.get("_tmdb_vote_count")) or 0
    langs = rec.get("_wiki_langs") or 0
    pop   = num(rec.get("_tmdb_popularity")) or 0
    pv    = (q.get("press_volume") or "").lower()
    votes_sub = min(45, math.log10(votes + 1) * 9)       # 1k≈27, 10k≈36, 100k≈45
    langs_sub = min(25, langs * 2.5)                     # 10+ languages = full
    pop_sub   = min(15, pop * 0.75)                      # TMDB popularity, capped
    press_sub = 15 if "heavy" in pv else 10 if "moderate" in pv else 5 if "light" in pv else 0
    return int(round(votes_sub + langs_sub + pop_sub + press_sub))

def score_film(rec, q):
    rt, mc, imdb = num(rec.get("rt_score")), num(rec.get("metacritic_score")), num(rec.get("imdb_rating"))
    votes = rec.get("_imdb_votes")
    fest = (q.get("festival") or "").lower()
    awards = (q.get("awards") or "").lower()
    has_fest  = any(f in fest for f in MAJOR_FESTS)                       # major festivals only
    has_award = awards not in ("", "none found", "unverified", "n/a") and "none" not in awards[:12] \
                and "not " not in awards[:12]
    imdb_ok = imdb is not None and votes is not None and votes >= 500      # ignore vote-starved ratings
    # acclaim
    acclaim_high = (rt is not None and rt >= 70) or (mc is not None and mc >= 65) \
                   or (imdb_ok and imdb >= 7.2) or has_fest or has_award
    acclaim_low  = (not acclaim_high) and (
                   (rt is not None and rt < 50) or (imdb_ok and imdb < 6.0)
                   or (rt is None and mc is None and not has_fest and not has_award))
    # buzz
    bscore = buzz_score(rec, q)
    buzz_high = bscore >= 60
    # quadrant
    if acclaim_high and buzz_high: quad = "Consensus must-watch"
    elif acclaim_high:             quad = "Hidden gem"
    elif buzz_high:                quad = "Talked-about / divisive"
    elif acclaim_low:              quad = "Obscure - skip"
    else:                          quad = "Minor / unproven"
    return quad, bscore, {"acclaim_high": acclaim_high, "acclaim_low": acclaim_low,
                          "major_festival": has_fest, "imdb_counted": imdb_ok, "buzz_high": buzz_high}

# ---- sample selection -------------------------------------------------------
def pick_sample(movies, n=20):
    has = lambda m, k: m.get(k) not in (None, "", "N/A")
    scored = [m for m in movies if has(m, "rt_score") or has(m, "metacritic_score")]
    scored.sort(key=lambda m: num(m.get("rt_score")) or num(m.get("metacritic_score")) or 0, reverse=True)
    imdb_only = [m for m in movies if has(m, "imdb_rating") and not has(m, "rt_score")]
    imdb_only.sort(key=lambda m: num(m.get("imdb_rating")) or 0, reverse=True)
    thin = [m for m in movies if not has(m, "imdb_rating") and not has(m, "rt_score")]
    thin.sort(key=lambda m: (m.get("digital_date") or ""), reverse=True)
    out, seen = [], set()
    for bucket, k in ((scored, 9), (imdb_only, 7), (thin, 4)):
        for m in bucket[:k]:
            if str(m.get("id")) not in seen:
                out.append(m); seen.add(str(m.get("id")))
    return out[:n]

# ---- main -------------------------------------------------------------------
def selects_queue_ids():
    """IDs of the live Stage-1 Selects queue (last field of each curate_list row)."""
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "curate_list.py"),
                          "--stage", "selects"], capture_output=True, text=True).stdout
    return [ln.rsplit("|||", 1)[-1].strip() for ln in out.splitlines() if "|||" in ln]

def main():
    ap = argparse.ArgumentParser(description="Notability sandbox scorer")
    ap.add_argument("--from-selects", action="store_true",
                    help="score the live /curate Selects queue (real candidates)")
    ap.add_argument("--ids", help="comma-separated movie ids to score")
    ap.add_argument("--limit", type=int, default=20, help="demo-sample size (default mode)")
    args = ap.parse_args()
    data = json.load(open(ROOT / "data.json"))
    by_id = {str(m.get("id")): m for m in data["movies"]}
    if args.ids:
        sample = [by_id[i] for i in (x.strip() for x in args.ids.split(",")) if i in by_id]
    elif args.from_selects:
        sample = [by_id[i] for i in selects_queue_ids() if i in by_id]
    else:
        sample = pick_sample(data["movies"], args.limit)
    print(f"Selected {len(sample)} films. Gathering signals...\n")
    results = []
    for i, m in enumerate(sample, 1):
        title, year = m.get("title"), (m.get("release_date") or m.get("digital_date") or "")[:4]
        links = m.get("links") or {}
        print(f"[{i:>2}/{len(sample)}] {title} ({year})")
        m["_wiki_langs"]      = wiki_language_count(links.get("wikipedia"))
        tm = tmdb_signals(m.get("id")); m["_tmdb_popularity"] = tm.get("tmdb_popularity")
        ov = omdb_votes(links.get("imdb")); m["_imdb_votes"] = ov.get("imdb_votes")
        numeric = {"imdb_rating": m.get("imdb_rating"), "rt_score": m.get("rt_score"),
                   "metacritic": m.get("metacritic_score"), "wiki_language_count": m["_wiki_langs"],
                   "tmdb_popularity": m["_tmdb_popularity"], "imdb_votes": m["_imdb_votes"],
                   "tmdb_vote_count": tm.get("tmdb_vote_count")}
        m["_tmdb_vote_count"] = tm.get("tmdb_vote_count")
        q = gemini_research(title, year, numeric)
        quad, bscore, dbg = score_film(m, q)
        results.append({
            "id": str(m.get("id")), "title": title, "year": year, "quadrant": quad,
            "buzz_score": bscore,
            "acclaim": {"rt": m.get("rt_score"), "metacritic": m.get("metacritic_score"),
                        "imdb": m.get("imdb_rating"), "festival": q.get("festival"),
                        "awards": q.get("awards") or ov.get("omdb_awards"),
                        "yearend_lists": q.get("yearend_lists")},
            "buzz": {"score": bscore, "_wiki_language_count": m["_wiki_langs"], "_imdb_votes": m["_imdb_votes"],
                     "_tmdb_popularity": m["_tmdb_popularity"], "_tmdb_vote_count": tm.get("tmdb_vote_count"),
                     "_press_volume": q.get("press_volume"), "_youtube_trailer_views": "n/a (API not enabled)"},
            "reception": q.get("reception"), "explanation": q.get("explanation"),
            "sources": q.get("sources", []), "_debug": dbg, "_error": q.get("error"),
            "letterboxd": links.get("letterboxd"), "wikipedia": links.get("wikipedia"),
        })
        time.sleep(0.5)
    OUT.write_text(json.dumps({"generated": time.strftime("%Y-%m-%d %H:%M"),
                               "model": "gemini-2.5-flash", "count": len(results),
                               "films": results}, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUT}")

if __name__ == "__main__":
    main()
