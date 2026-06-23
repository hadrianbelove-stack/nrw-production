"""
Slop classifier — determines whether a film on the NRW wall is "slop"
(low-quality direct-to-digital content) or a legitimate film.

Tiered logic:
  1. Prestige streaming (Max/HBO/MUBI…) → NOT SLOP; slop streaming (Crunchyroll) → SLOP
  2. Studio veto lists → SLOP (Hallmark, True Story, asylum…) or NOT SLOP (A24, Skydance, Factory 25…)
  2c. Indian commercial cinema → SLOP unless a major crossover hit
  3. Score-based signals → SLOP if score >= 4. Signals:
       +2 no Wikipedia, +2 no RT score, +1 no RT link
       IMDb: +2 if <=6.0, +1 if 6.1-6.9, -1 if >=7.0
       -1 prestige festival (admin/festival_films.json)
       -1 major streamer (Netflix/Prime/Disney+/HBO/Max/Shudder; Tubi neutral)

Run directly to apply is_slop to all films in data.json:
  python3 scripts/slop_classifier.py

Or import classify_slop() for use in the enricher.
"""

import json
import os

# ── Prestige festivals → -1 score signal (Tier 3) ────────────────────────────
# Selection at a top festival is a quality signal that offsets the no-RT penalty
# many arthouse/foreign films incur. Membership lives in admin/festival_films.json
# (movie_id -> festival name), seeded manually and auto-fed from Wikipedia.
PRESTIGE_FESTIVALS = {
    'cannes', 'berlinale', 'berlin international film festival',
    'international film festival rotterdam', 'iffr', 'rotterdam',
    'sundance', 'telluride',
    'new york film festival', 'nyff',
    'venice film festival', 'venice international film festival', 'venezia',
    'locarno',
}

_FESTIVAL_FILMS_PATH = 'admin/festival_films.json'
_festival_films_cache = None

def _festival_films():
    """movie_id (str) -> festival name. Cached; tolerates a missing/bad file."""
    global _festival_films_cache
    if _festival_films_cache is None:
        try:
            with open(_FESTIVAL_FILMS_PATH) as f:
                raw = json.load(f)
            _festival_films_cache = {str(k): v for k, v in raw.items()}
        except (OSError, ValueError):
            _festival_films_cache = {}
    return _festival_films_cache

# ── Manual overrides → RETIRED 2026-06-22 ───────────────────────────────────
# Durable slop verdicts now live in admin/overrides.json (one override store,
# applied last in pipeline/display.py). The 82 former entries were migrated there.
MANUAL_OVERRIDES = {}

# ── Prestige streaming platforms → instant NOT SLOP ──────────────────────────
PRESTIGE_STREAMING = {
    'mubi',
    'criterion channel',
    'criterion',
    'pbs documentaries amazon channel',
    'pbs',
    'max',
    'hbo max',
}

# ── Slop streaming platforms → instant SLOP ──────────────────────────────────
# Crunchyroll = anime simulcast/library; never surfaced as curated. Manual override
# (Tier 0) is the escape hatch when the user explicitly intervenes.
SLOP_STREAMING = {
    'crunchyroll',
}

# ── Soft non-slop streamers → -1 score signal (Tier 3) ───────────────────────
# Being licensed onto a major SVOD (or a curated genre service like Shudder) is a
# mild quality/legitimacy signal. -1 point, not an instant pass (Max/HBO already
# get that via PRESTIGE_STREAMING). Matched against streaming services only, so an
# Amazon *rental* (VOD) does not count. Tubi is intentionally absent = neutral.
MAJOR_STREAMING = {
    'netflix',
    'amazon prime video', 'prime video',
    'hbo max', 'hbo', 'max',
    'disney plus', 'disney+',
    'shudder',
}

# ── Prestige studios → NOT SLOP ──────────────────────────────────────────────
PRESTIGE_STUDIOS = {
    'a24', 'neon', 'mubi', 'criterion', 'kino lorber', 'magnolia',
    'film movement', 'music box films', 'music box', 'utopia',
    'oscilloscope', 'grasshopper film', 'sideshow', 'janus films',
    'cohen media', 'well go usa', 'samuel goldwyn', 'bleecker street',
    'roadside attractions', 'sony pictures classics', 'focus features',
    'searchlight', 'fox searchlight', 'strand releasing',
    'quiver distribution', 'abramorama', 'monument releasing',
    'altered innocence', 'dekanalog', 'icarus films', 'first run features',
    'zeitgeist films', 'gkids', 'cinema guild', 'drafthouse films',
    'ifc films', 'ifc', 'sundance selects', 'arrow video', 'severin films',
    'vinegar syndrome', 'curzon', 'bfi', 'dogwoof', 'antenna', 'studiocanal',
    'gaumont', 'universal pictures', 'columbia pictures', 'warner bros',
    'paramount pictures', 'disney', 'mgm', 'united artists', 'dreamworks',
    'miramax', 'new line cinema', '20th century', 'tristar', 'touchstone',
    'bbc films', 'channel 4', 'film4', 'screen australia', 'nfb',
    'telefilm canada', 'nzfc', 'amplify releasing', 'mongrel media',
    'entertainment one', 'kimstim', 'oscilloscope laboratories',
    'lionsgate', 'lions gate', 'skydance', 'factory 25',
    # Documentary / prestige TV labels
    'black public media', 'pbs', 'hbo documentary', 'hbo documentary films',
    'imagine documentaries',
    # Prestige indie horror / art-house
    'yellow veil', 'yellow veil pictures',
}

# ── Slop studios → instant SLOP ──────────────────────────────────────────────
SLOP_STUDIOS = {
    'grindstone', 'grindstone entertainment',
    'lionsgate premiere', 'lionsgate home entertainment',
    'redbox', 'redbox entertainment',
    'saban films',
    'signature entertainment', 'signature releasing',
    'bad grey',
    'highland film group',
    'freestyle digital media', 'freestyle releasing',
    'phase 4 films',
    "uncork'd entertainment", 'uncorkd',
    'terror films',
    'mill creek entertainment',
    'anchor bay entertainment', 'anchor bay films',
    'voltage pictures',
    'dark sky films',
    'the asylum',
    'nu image', 'millennium films',
    'after dark films',
    'cinedigm',
    'screen media ventures',
    'indican pictures',
    'yale entertainment',
    'hallmark', 'hallmark channel', 'hallmark media', 'hallmark movies', 'crown media',
    'true story',  # True Story channel
    'up entertainment', 'up tv',
    'pure flix', 'angel studios', 'affirm films',
    'lifetime', 'lmn',
    'syfy', 'sci fi channel',
    'ion television', 'insp films',
    'entertainment studios',
    'blumhouse productions', 'blumhouse television',
    'johnson production group',  # prolific Hallmark-style producer
}


def _get_streaming_services(movie):
    """Return list of lowercase streaming service names."""
    wl = movie.get('watch_links') or {}
    services = []
    for link in (wl.get('streaming') or []):
        if isinstance(link, dict) and link.get('service'):
            services.append(link['service'].lower().strip())
    return services


def classify_slop(movie):
    """
    Classify a movie as slop or not.

    Returns (is_slop: bool, reason: str, confidence: str)
      confidence: 'strong' (studio/streaming signal) or 'weak' (score-based)
    """
    tmdb_id = movie.get('id')
    # Tier 1: Prestige streaming platform → NOT SLOP
    for svc in _get_streaming_services(movie):
        for prestige in PRESTIGE_STREAMING:
            if prestige in svc:
                return False, f'prestige_streaming:{svc}', 'strong'

    # Tier 1b: Slop streaming platform → SLOP (Crunchyroll). Manual override wins (Tier 0).
    for svc in _get_streaming_services(movie):
        for s in SLOP_STREAMING:
            if s in svc:
                return True, f'slop_streaming:{svc}', 'strong'

    studio = (movie.get('studio') or '').lower().strip()

    # Tier 2a: Slop studio → SLOP
    for s in SLOP_STUDIOS:
        if s and s in studio:
            return True, f'slop_studio:{studio[:40]}', 'strong'

    # Tier 2b: Prestige studio → NOT SLOP
    for s in PRESTIGE_STUDIOS:
        if s and len(s) > 3 and s in studio:
            return False, f'prestige_studio:{studio[:40]}', 'strong'

    links = movie.get('links') or {}

    # Tier 2c: Indian commercial cinema → SLOP unless a major crossover hit.
    # Almost all Bollywood/Tamil/Telugu/Malayalam/etc. is slop; the rare exception
    # (e.g. RRR) clears a high bar: Wikipedia AND Letterboxd AND healthy RT AND healthy IMDb.
    INDIAN_LANGS = {'hi', 'ta', 'te', 'ml', 'kn', 'bn', 'mr', 'pa', 'gu'}
    lang = (movie.get('original_language') or '').lower()
    if lang in INDIAN_LANGS:
        def _num(v):
            try:
                return float(str(v).replace('%', '').strip())
            except (TypeError, ValueError):
                return None
        rt = _num(movie.get('rt_score'))
        imdb = _num(movie.get('imdb_rating'))
        crossover = (
            bool(links.get('wikipedia'))
            and bool(links.get('letterboxd'))
            and rt is not None and rt >= 60
            and imdb is not None and imdb >= 7.0
        )
        if not crossover:
            return True, f'indian_cinema_no_crossover:{lang}', 'strong'
        return False, f'indian_crossover_hit:{lang}', 'strong'

    # Tier 3: Score-based signals
    score = 0
    reasons = []
    has_wiki = bool(links.get('wikipedia'))

    if not has_wiki:
        score += 2
        reasons.append('no_wiki')
    if not movie.get('rt_score'):
        score += 2
        reasons.append('no_rt')
    imdb = movie.get('imdb_rating')
    if not imdb:
        score += 2
        reasons.append('no_imdb')
    elif float(imdb) <= 6.0:
        score += 2
        reasons.append('low_imdb')
    elif float(imdb) < 7.0:  # 6.1 - 6.9
        score += 1
        reasons.append('mid_imdb')
    else:  # imdb >= 7.0
        score -= 1
        reasons.append('good_imdb')
    if movie.get('content_type') == 'tv_movie':
        score += 3
        reasons.append('tv_movie')
    if not links.get('rt') and not links.get('rotten_tomatoes'):
        score += 1
        reasons.append('no_rt_link')

    # Prestige festival selection → -1 (offsets the no-RT penalty arthouse films incur)
    fest = _festival_films().get(str(tmdb_id))
    if fest:
        score -= 1
        reasons.append(f'festival:{fest}')

    # Major streamer (Netflix/Prime/HBO/Max) → -1 (licensing legitimacy signal)
    for svc in _get_streaming_services(movie):
        if any(s in svc for s in MAJOR_STREAMING):
            score -= 1
            reasons.append(f'major_streamer:{svc}')
            break

    # Fixed threshold. Missing Wikipedia is already one signal (+2 above) —
    # it is NOT also used to lower the bar (that double-counted it).
    threshold = 4

    is_slop = score >= threshold
    return is_slop, f'score:{score}({",".join(reasons)})', 'weak'


def main():
    with open('data.json') as f:
        data = json.load(f)
    movies = data if isinstance(data, list) else data.get('movies', [])

    counts = {'slop': 0, 'not_slop': 0, 'strong': 0, 'weak': 0}

    for movie in movies:
        is_slop, reason, confidence = classify_slop(movie)
        movie['is_slop'] = is_slop
        movie['_slop_reason'] = reason
        movie['_slop_confidence'] = confidence

        if is_slop:
            counts['slop'] += 1
        else:
            counts['not_slop'] += 1
        if confidence == 'strong':
            counts['strong'] += 1
        else:
            counts['weak'] += 1

    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    total = counts['slop'] + counts['not_slop']
    print(f"Classified {total} films")
    print(f"  SLOP:     {counts['slop']}")
    print(f"  NOT SLOP: {counts['not_slop']}")
    print(f"  Strong signal: {counts['strong']}")
    print(f"  Weak (guess):  {counts['weak']}")

    # Show weak-confidence slop (curate queue candidates)
    weak_slop = [m for m in movies if m.get('is_slop') and m.get('_slop_confidence') == 'weak']
    print(f"\nWeak-confidence SLOP (curate queue): {len(weak_slop)}")


if __name__ == '__main__':
    main()
