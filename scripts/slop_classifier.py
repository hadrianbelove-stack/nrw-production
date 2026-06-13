"""
Slop classifier — determines whether a film on the NRW wall is "slop"
(low-quality direct-to-digital content) or a legitimate film.

Three-tier logic:
  1. Prestige streaming platform → instant NOT SLOP
  2. Studio/distributor veto lists → instant SLOP or NOT SLOP
  3. Score-based signals → SLOP if score >= 5 (or 4 when no Wikipedia)

Run directly to apply is_slop to all films in data.json:
  python3 scripts/slop_classifier.py

Or import classify_slop() for use in the enricher.
"""

import json
import sys

# ── Manual overrides (TMDB ID → bool) ────────────────────────────────────────
# Films the classifier gets wrong that require human judgment.
# is_slop: False = confirmed NOT slop regardless of signals.
MANUAL_OVERRIDES = {
    # Prestige/indie picked up by quality distributors, but studio field misleads
    1422120: False,   # Mermaid (Bad Grey prod. / Utopia dist.)
    # Documentaries by respected directors with low metadata coverage
    1585266: False,   # Clairtone (Ron Mann)
    1463432: False,   # Steve Schapiro: Being Everywhere
    # Comedy specials — major comedians
    1222518: False,   # Josh Johnson: Symphony (not slop despite Irwin Entertainment)
    # Documentary series
    1693906: False,   # Behind Bars - Shot in the Spotlight (Untold UK series)
    1684240: False,   # Untold UK: Jamie Vardy
    1684246: False,   # Untold UK: Vinnie Jones
    # Art-house / festival films without RT/wiki yet
    1303370: False,   # Ways to Traverse a Territory
    1422627: False,   # Snow Leopard Sisters
    1303498: False,   # $POSITIONS
    1207622: False,   # Salt Along the Tongue (Yellow Veil)
    # Films with Wikipedia pages that still score poorly
    1368881: False,   # Ladies First
    1425373: False,   # The Golden Spurtle (7.6 IMDb, no RT/wiki yet)
    1535130: False,   # Kylie: Tension Tour Live
    1380291: False,   # Tom Clancy's Jack Ryan: Ghost War
    # HBO/PBS/MAX docs with sparse metadata
    1559776: False,   # The A List: 15 Stories from Asian and Pacific Diasporas
    1541658: False,   # One Golden Summer (MAX doc)
    1620034: False,   # Marty, Life Is Short (Imagine Documentaries)
    1658982: False,   # The Roast of Kevin Hart
    1249271: False,   # Powwow People (6 RT critic reviews, real doc)
    1265340: False,   # The Second Coming of John Cooper (curator call)
    1556616: False,   # Summer House (curator call)
    # TV-movie mill thrillers — confirmed slop by curator (June 2026)
    1708839: True,    # Her Husband's Double Life
    1409853: True,    # Neglected
    # Human-confirmed slop
    1686326: True,    # Emi Martínez: The Kid Who Stops Time
    934584:  True,    # Rich Flu (La fiebre de los ricos)
    1424649: True,    # Sampung Utos Kay Josh
    1174334: True,    # A Foggy Tale
    1433117: True,    # Kara
}

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
    'lionsgate', 'lions gate',
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
    'hallmark channel', 'hallmark movies', 'crown media',
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
    numeric_id = int(str(tmdb_id).replace('tv_', '')) if tmdb_id and str(tmdb_id).replace('tv_', '').isdigit() else None

    # Tier 0: Manual overrides
    if numeric_id in MANUAL_OVERRIDES:
        verdict = MANUAL_OVERRIDES[numeric_id]
        return verdict, 'manual_override', 'strong'

    # Tier 1: Prestige streaming platform → NOT SLOP
    for svc in _get_streaming_services(movie):
        for prestige in PRESTIGE_STREAMING:
            if prestige in svc:
                return False, f'prestige_streaming:{svc}', 'strong'

    studio = (movie.get('studio') or '').lower().strip()

    # Tier 2a: Slop studio → SLOP
    for s in SLOP_STUDIOS:
        if s and s in studio:
            return True, f'slop_studio:{studio[:40]}', 'strong'

    # Tier 2b: Prestige studio → NOT SLOP
    for s in PRESTIGE_STUDIOS:
        if s and len(s) > 3 and s in studio:
            return False, f'prestige_studio:{studio[:40]}', 'strong'

    # Tier 3: Score-based signals
    score = 0
    reasons = []
    links = movie.get('links') or {}
    has_wiki = bool(links.get('wikipedia'))

    if not has_wiki:
        score += 2
        reasons.append('no_wiki')
    if not movie.get('rt_score'):
        score += 2
        reasons.append('no_rt')
    imdb = movie.get('imdb_rating')
    if not imdb:
        score += 1
        reasons.append('no_imdb')
    elif float(imdb) < 6:
        score += 1
        reasons.append('low_imdb')
    elif float(imdb) >= 6.5:
        score -= 1
        reasons.append('good_imdb')
    if movie.get('content_type') == 'tv_movie':
        score += 3
        reasons.append('tv_movie')
    if not links.get('rt') and not links.get('rotten_tomatoes'):
        score += 1
        reasons.append('no_rt_link')

    # Higher threshold when Wikipedia is present (film has critical attention)
    threshold = 5 if has_wiki else 4

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
