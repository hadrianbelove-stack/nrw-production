---
description: Full movie data report — TMDB + OMDb combined (ratings, credits, cast, release dates, trailers, images, reviews, recommendations)
argument-hint: [title to search, or numeric TMDB ID]
allowed-tools: Bash, Read
---

Pull everything available from TMDB and OMDb and write a single comprehensive report. Do NOT dump raw output — synthesize into a clean readable document in the chat.

**Argument**: $ARGUMENTS

---

## Step 1 — Fetch all data

```bash
/usr/bin/python3 - << 'PULLDATA_EOF'
import json, sys, os, requests, re
from dotenv import load_dotenv
load_dotenv("/Users/hadrianbelove/Downloads/nrw-production/.env")

QUERY = """$ARGUMENTS""".strip()
TMDB_KEY = os.environ.get('TMDB_API_KEY', '')
OMDB_KEY = os.environ.get('OMDB_API_KEY', '')
BASE = 'https://api.themoviedb.org/3'
APPEND = 'credits,videos,images,keywords,recommendations,similar,reviews,release_dates,watch/providers,external_ids,alternative_titles'

def tmdb_get(path, **params):
    params['api_key'] = TMDB_KEY
    r = requests.get(f"{BASE}{path}", params=params, timeout=15)
    return r.json() if r.status_code == 200 else None

def omdb_get(imdb_id=None, title=None, year=None):
    params = {'apikey': OMDB_KEY, 'plot': 'full'}
    if imdb_id:
        params['i'] = imdb_id
    elif title:
        params['t'] = title
        if year: params['y'] = year
    r = requests.get('http://www.omdbapi.com/', params=params, timeout=10)
    if r.status_code == 200:
        d = r.json()
        return d if d.get('Response') == 'True' else None
    return None

def show(movie_id, media_type='movie'):
    is_tv = str(movie_id).startswith('tv_')
    numeric = str(movie_id).replace('tv_', '')
    ep = 'tv' if is_tv else media_type

    d = tmdb_get(f"/{ep}/{numeric}", append_to_response=APPEND)
    if not d:
        print(f"NO_RESULT: {movie_id}")
        return

    # ── IDENTITY ─────────────────────────────────────────────────
    title = d.get('title') or d.get('name', '?')
    orig_title = d.get('original_title') or d.get('original_name', '')
    year_str = (d.get('release_date') or d.get('first_air_date', ''))[:4]
    imdb_id = d.get('imdb_id') or d.get('external_ids', {}).get('imdb_id', '')

    print(f"TITLE: {title}")
    print(f"YEAR: {year_str}")
    print(f"TMDB_ID: {d.get('id')}")
    print(f"IMDB_ID: {imdb_id}")
    ext = d.get('external_ids', {})
    for k in ('wikidata_id','facebook_id','instagram_id','twitter_id'):
        if ext.get(k): print(f"{k.upper()}: {ext[k]}")
    if orig_title and orig_title != title: print(f"ORIG_TITLE: {orig_title}")

    alt_titles = d.get('alternative_titles', {})
    alts = alt_titles.get('titles', alt_titles.get('results', []))
    notable_alts = [a['title'] for a in alts if a['title'] != title][:8]
    if notable_alts: print(f"ALT_TITLES: {' | '.join(notable_alts)}")

    # ── CORE ─────────────────────────────────────────────────────
    print(f"STATUS: {d.get('status','?')}")
    print(f"LANG: {d.get('original_language','?')}")
    spoken = [l['english_name'] for l in d.get('spoken_languages', [])]
    if spoken: print(f"SPOKEN_LANGS: {', '.join(spoken)}")
    print(f"RUNTIME: {d.get('runtime') or (d.get('episode_run_time') or [None])[0]}")
    print(f"GENRES: {', '.join(g['name'] for g in d.get('genres', []))}")
    countries = [c['name'] for c in d.get('production_countries', [])]
    if countries: print(f"COUNTRIES: {', '.join(countries)}")
    if d.get('tagline'): print(f"TAGLINE: {d['tagline']}")
    print(f"OVERVIEW: {d.get('overview','')}")
    if d.get('homepage'): print(f"HOMEPAGE: {d['homepage']}")
    if d.get('budget'):  print(f"BUDGET: ${d['budget']:,}")
    if d.get('revenue'): print(f"REVENUE: ${d['revenue']:,}")
    coll = d.get('belongs_to_collection')
    if coll: print(f"COLLECTION: {coll.get('name')}")
    companies = [c['name'] for c in d.get('production_companies', [])]
    if companies: print(f"PRODUCTION_CO: {', '.join(companies)}")

    # ── TMDB RATINGS ─────────────────────────────────────────────
    print(f"TMDB_VOTE: {d.get('vote_average','?')}/10 ({d.get('vote_count','?')} votes)")
    print(f"TMDB_POPULARITY: {d.get('popularity','?')}")

    # ── OMDB ─────────────────────────────────────────────────────
    omdb = omdb_get(imdb_id=imdb_id) if imdb_id else omdb_get(title=title, year=year_str)
    if omdb:
        print(f"OMDB_RATED: {omdb.get('Rated','?')}")
        print(f"OMDB_PLOT: {omdb.get('Plot','')}")
        if omdb.get('Awards') and omdb['Awards'] != 'N/A':
            print(f"OMDB_AWARDS: {omdb['Awards']}")
        if omdb.get('BoxOffice') and omdb['BoxOffice'] != 'N/A':
            print(f"OMDB_BOXOFFICE: {omdb['BoxOffice']}")
        for rating in omdb.get('Ratings', []):
            src = rating.get('Source','')
            val = rating.get('Value','')
            if 'Internet Movie' in src: print(f"RATING_IMDB: {val}")
            elif 'Rotten' in src:       print(f"RATING_RT: {val}")
            elif 'Metacritic' in src:   print(f"RATING_META: {val}")
        if omdb.get('imdbVotes') and omdb['imdbVotes'] != 'N/A':
            print(f"IMDB_VOTES: {omdb['imdbVotes']}")
    else:
        print("OMDB: no match")

    # ── CREW ─────────────────────────────────────────────────────
    crew = d.get('credits', {}).get('crew', [])
    cast = d.get('credits', {}).get('cast', [])
    directors    = [p['name'] for p in crew if p.get('job') == 'Director']
    if is_tv:    directors = [p['name'] for p in d.get('created_by', [])]
    writers_sp   = list({p['name'] for p in crew if p.get('job') in ('Screenplay','Writer','Story')})
    writers_orig = list({p['name'] for p in crew if 'Original' in p.get('job','')})
    producers    = list({p['name'] for p in crew if p.get('job') == 'Producer'})
    exec_prod    = list({p['name'] for p in crew if p.get('job') == 'Executive Producer'})[:5]
    dop          = next((p['name'] for p in crew if p.get('job') == 'Director of Photography'), None)
    composer     = next((p['name'] for p in crew if p.get('job') == 'Original Music Composer'), None)
    editor       = next((p['name'] for p in crew if p.get('job') == 'Editor'), None)
    casting      = next((p['name'] for p in crew if p.get('job') == 'Casting'), None)
    costume      = next((p['name'] for p in crew if p.get('job') == 'Costume Design'), None)
    prod_design  = next((p['name'] for p in crew if p.get('job') == 'Production Design'), None)
    vfx          = next((p['name'] for p in crew if 'Visual Effects' in p.get('job','') and 'Supervisor' in p.get('job','')), None)

    if directors:    print(f"DIRECTOR: {', '.join(directors)}")
    if writers_sp:   print(f"SCREENPLAY: {', '.join(writers_sp)}")
    if writers_orig: print(f"BASED_ON: {', '.join(writers_orig)}")
    if producers:    print(f"PRODUCERS: {', '.join(producers[:4])}")
    if exec_prod:    print(f"EXEC_PRODUCERS: {', '.join(exec_prod)}")
    if dop:          print(f"DOP: {dop}")
    if composer:     print(f"COMPOSER: {composer}")
    if editor:       print(f"EDITOR: {editor}")
    if casting:      print(f"CASTING: {casting}")
    if costume:      print(f"COSTUME: {costume}")
    if prod_design:  print(f"PROD_DESIGN: {prod_design}")
    if vfx:          print(f"VFX: {vfx}")

    for p in cast:
        char = p.get('character','')
        print(f"CAST: {p['name']} as {char}" if char else f"CAST: {p['name']}")

    # ── RELEASES ─────────────────────────────────────────────────
    TYPE_NAMES = {1:'Premiere',2:'Theatrical (limited)',3:'Theatrical',4:'Digital',5:'Physical',6:'TV'}
    for entry in d.get('release_dates',{}).get('results',[]):
        country = entry.get('iso_3166_1')
        for rel in entry.get('release_dates',[]):
            tag = 'RELEASE_US' if country == 'US' else 'RELEASE_INTL'
            print(f"{tag}: {country} Type{rel['type']} {TYPE_NAMES.get(rel['type'],'')} {rel['release_date'][:10]}")

    # ── VIDEOS ───────────────────────────────────────────────────
    for v in d.get('videos',{}).get('results',[]):
        site = v.get('site','')
        key  = v.get('key','')
        url  = f"https://youtube.com/watch?v={key}" if site == 'YouTube' else f"{site}:{key}"
        print(f"VIDEO: [{v.get('type')}] {v.get('name')} — {url}")

    # ── IMAGES ───────────────────────────────────────────────────
    imgs      = d.get('images',{})
    posters   = imgs.get('posters',[])
    backdrops = imgs.get('backdrops',[])
    logos     = imgs.get('logos',[])
    print(f"IMAGES: {len(posters)} posters, {len(backdrops)} backdrops, {len(logos)} logos")
    for p in posters[:3]:   print(f"POSTER: https://image.tmdb.org/t/p/w500{p['file_path']}")
    for b in backdrops[:2]: print(f"BACKDROP: https://image.tmdb.org/t/p/w1280{b['file_path']}")

    # ── WATCH PROVIDERS ──────────────────────────────────────────
    wp = d.get('watch/providers',{}).get('results',{}).get('US',{})
    for p in wp.get('flatrate',[]): print(f"PROVIDER_STREAM: {p['provider_name']}")
    for p in wp.get('rent',[]):     print(f"PROVIDER_RENT: {p['provider_name']}")
    for p in wp.get('buy',[]):      print(f"PROVIDER_BUY: {p['provider_name']}")
    if not wp: print("PROVIDER: none")
    if wp.get('link'): print(f"JW_LINK: {wp['link']}")

    # ── KEYWORDS ─────────────────────────────────────────────────
    kw_data = d.get('keywords',{})
    kws = [k['name'] for k in kw_data.get('keywords', kw_data.get('results',[]))]
    if kws: print(f"KEYWORDS: {', '.join(kws)}")

    # ── REVIEWS ──────────────────────────────────────────────────
    reviews = d.get('reviews',{}).get('results',[])
    print(f"REVIEW_COUNT: {d.get('reviews',{}).get('total_results',0)}")
    for rv in reviews[:3]:
        snippet = rv.get('content','')[:300].replace('\n',' ')
        rating  = rv.get('author_details',{}).get('rating','?')
        print(f"REVIEW: [{rv.get('author')} ★{rating}] {snippet}")

    # ── RECOMMENDATIONS & SIMILAR ────────────────────────────────
    for r in d.get('recommendations',{}).get('results',[])[:8]:
        t = r.get('title') or r.get('name','?')
        y = (r.get('release_date') or r.get('first_air_date',''))[:4]
        print(f"REC: {t} ({y}) ★{r.get('vote_average','?')} id={r.get('id')}")

    for s in d.get('similar',{}).get('results',[])[:8]:
        t = s.get('title') or s.get('name','?')
        y = (s.get('release_date') or s.get('first_air_date',''))[:4]
        print(f"SIMILAR: {t} ({y}) ★{s.get('vote_average','?')} id={s.get('id')}")

if re.match(r'^(tv_)?\d+$', QUERY):
    show(QUERY)
else:
    results = tmdb_get('/search/multi', query=QUERY, include_adult=False)
    if not results or not results.get('results'):
        print(f"NO_RESULTS: {QUERY}")
        sys.exit(0)
    hits = [h for h in results['results'][:8] if h.get('media_type') != 'person'][:6]
    if len(hits) == 1:
        show(hits[0]['id'], hits[0].get('media_type','movie'))
    else:
        print(f"MULTIPLE_RESULTS: {QUERY}")
        for h in hits:
            mid    = h.get('id')
            mtype  = h.get('media_type','movie')
            t      = h.get('title') or h.get('name','?')
            y      = (h.get('release_date') or h.get('first_air_date',''))[:4]
            vote   = h.get('vote_average','?')
            prefix = 'tv_' if mtype == 'tv' else ''
            print(f"HIT: {prefix}{mid} [{mtype}] {t} ({y}) ★{vote}")

PULLDATA_EOF
```

---

## Step 2 — Write the full report IN THE CHAT

Synthesize everything into one clean markdown report. Include every section, skip nothing that has data. Make it visually easy to scan.

---

# [Title] ([Year])
**TMDB:** [id] · **IMDb:** [id] · [Wikidata/social if present]
*[tagline in italics if exists]*
**[genres] · [runtime] min · [MPAA rating if from OMDb] · [country] · [language]**

---

### Overview
[TMDB full synopsis. Then OMDb's full plot if it adds anything different.]

### Themes
[Read the TMDB keywords and describe what the film is actually about thematically — 1–2 sentences. Don't just list the keywords.]

[Franchise line if belongs_to_collection.]

---

### Ratings
| Source | Score |
|--------|-------|
| IMDb | [rating] / 10 · [votes] votes |
| Rotten Tomatoes | [score] |
| Metacritic | [score] |
| TMDB | [score] / 10 · [votes] votes · Popularity [score] |

[Note if any scores are missing or if vote counts are too low to be meaningful yet.]

[Awards line from OMDb if present.]
[Box office from OMDb if present.]

---

### Behind the Camera

| Role | Name |
|------|------|
| Director | |
| Screenplay | |
| Based on | (if applicable) |
| Producer | |
| Executive Producer | |
| Director of Photography | |
| Composer | |
| Editor | |
| Casting | |
| Costume Design | |
| Production Design | |
| VFX Supervisor | (if present) |

[Only show rows with data.]

---

### Cast
| Actor | Character |
|-------|-----------|
[Every cast member in order.]

---

### Production
**Companies:** [list] · **Countries:** [list]
**Budget:** [if known] · **Revenue:** [if known] · [profit/loss note if both present]

---

### Release Timeline

**US:**
| Type | Date |
|------|------|
[All US releases. Bold the digital date row.]

**International:** [Summarize — e.g. "Simultaneous global Netflix drop May 22, 2026 across ~190 countries." Don't list every country code.]

**Alternative titles:** [list if any] · **Spoken languages:** [list]

---

### Media

**Videos ([count]):**
[Every video grouped by type — Trailers, Teasers, Clips, Featurettes, Behind the Scenes, Bloopers. Each as a clickable link.]

**Image library:** [X] posters · [X] backdrops · [X] logos
[3 poster links + 2 backdrop links]

---

### Where to Watch (US)
**Streaming:** [list] · **Rent:** [list] · **Buy:** [list]
[JustWatch link if present]

---

### TMDB Reviews ([total count])
[Summarize each review: author, star rating, key opinion in one sentence. If 0 reviews, say so.]

---

### If You Liked This, TMDB Also Suggests

**Recommendations:**
[8 films as compact list: Title (Year) ★score]

**Similar titles:**
[8 films as compact list: Title (Year) ★score]

---

If multiple search results, list them and ask which — never auto-select.
