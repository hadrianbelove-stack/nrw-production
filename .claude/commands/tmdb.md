---
description: Full TMDB report on any movie or show — everything the API has
argument-hint: [title to search, or numeric TMDB ID]
allowed-tools: Bash, Read
---

Fetch everything TMDB has and write one comprehensive report. Do NOT dump raw output — synthesize into a readable document.

**Argument**: $ARGUMENTS

---

## Step 1 — Fetch all data (single API call)

```bash
/usr/bin/python3 - << 'TMDB_EOF'
import json, sys, os, requests, re
from dotenv import load_dotenv
load_dotenv("/Users/hadrianbelove/Downloads/nrw-production/.env")

QUERY = """$ARGUMENTS""".strip()
KEY = os.environ.get('TMDB_API_KEY', '')
BASE = 'https://api.themoviedb.org/3'
APPEND = 'credits,videos,images,keywords,recommendations,similar,reviews,release_dates,watch/providers,external_ids,alternative_titles'

def get(path, **params):
    params['api_key'] = KEY
    r = requests.get(f"{BASE}{path}", params=params, timeout=15)
    return r.json() if r.status_code == 200 else None

def show(movie_id, media_type='movie'):
    is_tv = str(movie_id).startswith('tv_')
    numeric = str(movie_id).replace('tv_', '')
    ep = 'tv' if is_tv else media_type
    d = get(f"/{ep}/{numeric}", append_to_response=APPEND)
    if not d:
        print(f"NO_RESULT: {movie_id}")
        return

    # ── IDENTITY ─────────────────────────────────────────────────
    title = d.get('title') or d.get('name', '?')
    orig_title = d.get('original_title') or d.get('original_name', '')
    print(f"TITLE: {title}")
    print(f"YEAR: {(d.get('release_date') or d.get('first_air_date', ''))[:4]}")
    print(f"TMDB_ID: {d.get('id')}")
    imdb_id = d.get('imdb_id') or d.get('external_ids', {}).get('imdb_id', '')
    print(f"IMDB_ID: {imdb_id}")
    ext = d.get('external_ids', {})
    if ext.get('wikidata_id'):   print(f"WIKIDATA: {ext['wikidata_id']}")
    if ext.get('facebook_id'):   print(f"FACEBOOK: {ext['facebook_id']}")
    if ext.get('instagram_id'):  print(f"INSTAGRAM: {ext['instagram_id']}")
    if ext.get('twitter_id'):    print(f"TWITTER: {ext['twitter_id']}")
    if orig_title and orig_title != title: print(f"ORIG_TITLE: {orig_title}")

    # Alt titles (first 6 notable ones)
    alt_titles = d.get('alternative_titles', {})
    alts = alt_titles.get('titles', alt_titles.get('results', []))
    notable_alts = [a['title'] for a in alts if a.get('iso_3166_1') in ('US','GB','AU','FR','DE','JP','KR','ES','IT','BR') and a['title'] != title][:6]
    if notable_alts: print(f"ALT_TITLES: {' | '.join(notable_alts)}")

    # ── CORE DETAILS ─────────────────────────────────────────────
    print(f"STATUS: {d.get('status', '?')}")
    print(f"LANG: {d.get('original_language', '?')}")
    spoken = [l['english_name'] for l in d.get('spoken_languages', [])]
    if spoken: print(f"SPOKEN_LANGS: {', '.join(spoken)}")
    print(f"RUNTIME: {d.get('runtime') or (d.get('episode_run_time') or [None])[0]}")
    print(f"GENRES: {', '.join(g['name'] for g in d.get('genres', []))}")
    countries = [c['name'] for c in d.get('production_countries', [])]
    if countries: print(f"COUNTRIES: {', '.join(countries)}")
    if d.get('tagline'): print(f"TAGLINE: {d['tagline']}")
    print(f"OVERVIEW: {d.get('overview', '')}")
    if d.get('homepage'): print(f"HOMEPAGE: {d['homepage']}")

    # ── COMMERCIAL ───────────────────────────────────────────────
    print(f"VOTE_AVG: {d.get('vote_average', '?')}")
    print(f"VOTE_CT: {d.get('vote_count', '?')}")
    print(f"POPULARITY: {d.get('popularity', '?')}")
    if d.get('budget'):  print(f"BUDGET: ${d['budget']:,}")
    if d.get('revenue'): print(f"REVENUE: ${d['revenue']:,}")

    # ── FRANCHISE ────────────────────────────────────────────────
    coll = d.get('belongs_to_collection')
    if coll: print(f"COLLECTION: {coll.get('name')}")

    # ── PRODUCTION ───────────────────────────────────────────────
    companies = [c['name'] for c in d.get('production_companies', [])]
    if companies: print(f"PRODUCTION_CO: {', '.join(companies)}")

    # ── CREW (full) ───────────────────────────────────────────────
    crew = d.get('credits', {}).get('crew', [])
    cast = d.get('credits', {}).get('cast', [])
    directors = [p['name'] for p in crew if p.get('job') == 'Director']
    if is_tv: directors = [p['name'] for p in d.get('created_by', [])]
    writers_sp = list({p['name'] for p in crew if p.get('job') in ('Screenplay', 'Writer', 'Story')})
    writers_orig = list({p['name'] for p in crew if 'Original' in p.get('job', '')})
    producers = list({p['name'] for p in crew if p.get('job') == 'Producer'})
    exec_producers = list({p['name'] for p in crew if p.get('job') == 'Executive Producer'})[:4]
    dop = next((p['name'] for p in crew if p.get('job') == 'Director of Photography'), None)
    composer = next((p['name'] for p in crew if p.get('job') == 'Original Music Composer'), None)
    editor = next((p['name'] for p in crew if p.get('job') == 'Editor'), None)
    casting = next((p['name'] for p in crew if p.get('job') == 'Casting'), None)
    costume = next((p['name'] for p in crew if p.get('job') == 'Costume Design'), None)
    prod_design = next((p['name'] for p in crew if p.get('job') == 'Production Design'), None)
    vfx = next((p['name'] for p in crew if 'Visual Effects' in p.get('job', '') and 'Supervisor' in p.get('job', '')), None)

    if directors:     print(f"DIRECTOR: {', '.join(directors)}")
    if writers_sp:    print(f"SCREENPLAY: {', '.join(writers_sp)}")
    if writers_orig:  print(f"BASED_ON: {', '.join(writers_orig)}")
    if producers:     print(f"PRODUCERS: {', '.join(producers[:4])}")
    if exec_producers:print(f"EXEC_PRODUCERS: {', '.join(exec_producers)}")
    if dop:           print(f"DOP: {dop}")
    if composer:      print(f"COMPOSER: {composer}")
    if editor:        print(f"EDITOR: {editor}")
    if casting:       print(f"CASTING: {casting}")
    if costume:       print(f"COSTUME: {costume}")
    if prod_design:   print(f"PROD_DESIGN: {prod_design}")
    if vfx:           print(f"VFX_SUPERVISOR: {vfx}")

    # Cast — all of them
    for p in cast:
        char = p.get('character', '')
        print(f"CAST: {p['name']} as {char}" if char else f"CAST: {p['name']}")

    # ── RELEASE DATES (all countries) ────────────────────────────
    TYPE_NAMES = {1:'Premiere', 2:'Theatrical (limited)', 3:'Theatrical', 4:'Digital', 5:'Physical', 6:'TV'}
    all_releases = []
    for entry in d.get('release_dates', {}).get('results', []):
        country = entry.get('iso_3166_1')
        for rel in entry.get('release_dates', []):
            all_releases.append((country, rel.get('type'), TYPE_NAMES.get(rel.get('type'), '?'), rel.get('release_date', '')[:10]))
    # US first, then others
    us = [(c,t,tn,dt) for c,t,tn,dt in all_releases if c == 'US']
    others = [(c,t,tn,dt) for c,t,tn,dt in all_releases if c != 'US']
    for c,t,tn,dt in sorted(us, key=lambda x: x[1]):
        print(f"RELEASE_US: Type{t} {tn} {dt}")
    for c,t,tn,dt in sorted(others, key=lambda x: (x[3], x[0])):
        print(f"RELEASE_INTL: {c} Type{t} {tn} {dt}")

    # ── VIDEOS (all types) ───────────────────────────────────────
    for v in d.get('videos', {}).get('results', []):
        site = v.get('site', '')
        key = v.get('key', '')
        url = f"https://youtube.com/watch?v={key}" if site == 'YouTube' else f"{site}: {key}"
        print(f"VIDEO: [{v.get('type')}] {v.get('name')} — {url}")

    # ── IMAGES (counts + a few paths) ────────────────────────────
    imgs = d.get('images', {})
    backdrops = imgs.get('backdrops', [])
    posters   = imgs.get('posters', [])
    logos     = imgs.get('logos', [])
    print(f"IMAGES: {len(posters)} posters, {len(backdrops)} backdrops, {len(logos)} logos")
    for p in posters[:3]:   print(f"POSTER_PATH: https://image.tmdb.org/t/p/w500{p['file_path']}")
    for b in backdrops[:2]: print(f"BACKDROP_PATH: https://image.tmdb.org/t/p/w1280{b['file_path']}")

    # ── WATCH PROVIDERS (US) ─────────────────────────────────────
    wp = d.get('watch/providers', {}).get('results', {}).get('US', {})
    for p in wp.get('flatrate', []): print(f"PROVIDER_STREAM: {p['provider_name']}")
    for p in wp.get('rent', []):     print(f"PROVIDER_RENT: {p['provider_name']}")
    for p in wp.get('buy', []):      print(f"PROVIDER_BUY: {p['provider_name']}")
    if not wp: print("PROVIDER: none")
    if wp.get('link'): print(f"JW_LINK: {wp['link']}")

    # ── KEYWORDS ─────────────────────────────────────────────────
    kw_data = d.get('keywords', {})
    kws = [k['name'] for k in kw_data.get('keywords', kw_data.get('results', []))]
    if kws: print(f"KEYWORDS: {', '.join(kws)}")

    # ── REVIEWS ──────────────────────────────────────────────────
    reviews = d.get('reviews', {}).get('results', [])
    print(f"REVIEW_COUNT: {d.get('reviews', {}).get('total_results', 0)}")
    for rv in reviews[:3]:
        snippet = rv.get('content', '')[:300].replace('\n', ' ')
        print(f"REVIEW: [{rv.get('author')} ★{rv.get('author_details',{}).get('rating','?')}] {snippet}...")

    # ── RECOMMENDATIONS ──────────────────────────────────────────
    recs = d.get('recommendations', {}).get('results', [])[:8]
    for r in recs:
        t = r.get('title') or r.get('name','?')
        y = (r.get('release_date') or r.get('first_air_date',''))[:4]
        v = r.get('vote_average','?')
        print(f"REC: {t} ({y}) ★{v} id={r.get('id')}")

    # ── SIMILAR ──────────────────────────────────────────────────
    sims = d.get('similar', {}).get('results', [])[:8]
    for s in sims:
        t = s.get('title') or s.get('name','?')
        y = (s.get('release_date') or s.get('first_air_date',''))[:4]
        v = s.get('vote_average','?')
        print(f"SIMILAR: {t} ({y}) ★{v} id={s.get('id')}")

if re.match(r'^(tv_)?\d+$', QUERY):
    show(QUERY)
else:
    results = get('/search/multi', query=QUERY, include_adult=False)
    if not results or not results.get('results'):
        print(f"NO_RESULTS: {QUERY}")
        sys.exit(0)
    hits = [h for h in results['results'][:8] if h.get('media_type') != 'person'][:6]
    if len(hits) == 1:
        h = hits[0]
        show(h['id'], h.get('media_type', 'movie'))
    else:
        print(f"MULTIPLE_RESULTS: {QUERY}")
        for h in hits:
            mid   = h.get('id')
            mtype = h.get('media_type', 'movie')
            t     = h.get('title') or h.get('name', '?')
            y     = (h.get('release_date') or h.get('first_air_date', ''))[:4]
            vote  = h.get('vote_average', '?')
            prefix = 'tv_' if mtype == 'tv' else ''
            print(f"HIT: {prefix}{mid} [{mtype}] {t} ({y}) ★{vote}")

TMDB_EOF
```

---

## Step 2 — Write the full report IN THE CHAT

Write the report directly as your response to the user — not in a code block, not as terminal output. Use clean markdown with headers and spacing so it's easy to scan. Include every section below, skipping only things that are truly empty. Make it look good.

---

# [Title] ([Year])
**TMDB:** [id] · **IMDb:** [id] · [Wikidata / social handles if present]
> *[tagline — in a blockquote if it exists]*

**[genres] · [runtime] min · [origin country] · [language(s)]**

---

### Overview
[Full synopsis from TMDB. Don't truncate.]

### Themes
[Genres + read the TMDB keywords and describe the themes they suggest in 1–2 sentences. Don't just list them — interpret them.]

---

### Behind the Camera

| Role | Name |
|------|------|
| Director | ... |
| Screenplay | ... |
| Based on | ... (if applicable) |
| Producer | ... |
| Executive Producer | ... |
| Director of Photography | ... |
| Composer | ... |
| Editor | ... |
| Casting | ... |
| Costume Design | ... |
| Production Design | ... |
| VFX Supervisor | ... (if present) |

[Only show rows that have data.]

### Cast
| Actor | Character |
|-------|-----------|
[Every cast member from the data, in order.]

### Production
**Companies:** [list]
**Countries:** [list]
**Budget:** [if available] · **Revenue:** [if available] · **[Profit/loss note if both present]**

[Franchise note if belongs_to_collection.]

---

### Ratings & Reception
**TMDB:** [score]/10 · [vote count] votes · Popularity: [score]
[Note if low vote count means it's early/too soon to judge.]

**Reviews:** [total count] on TMDB.
[For each of the up to 3 reviews: author name, their star rating, and a 1-sentence summary of their take.]

---

### Release Timeline

**US:**
| Type | Date |
|------|------|
[All US release dates, labeled by type. Bold the digital date.]

**International highlights:** [List notable country releases, grouped or condensed if many. Focus on major markets: UK, France, Germany, Australia, Japan, Korea, Brazil.]

**Alternative titles:** [list if any]

---

### Media

**Videos ([total count]):**
[List every video with its type label and a clickable link. Group by type: Trailers first, then Teasers, Clips, Featurettes, Behind the Scenes, Bloopers, other.]

**Image library:** [X] posters · [X] backdrops · [X] logos
Poster samples: [3 TMDB image URLs as markdown links labeled "Poster 1", "Poster 2", "Poster 3"]
Backdrop samples: [2 TMDB image URLs as markdown links]

---

### Where to Watch (US)
**Streaming:** [list or "not streaming"]
**Rent:** [list or "—"]
**Buy:** [list or "—"]
[JustWatch link if present]

---

### TMDB Recommends
[8 recommendations as a compact list: Title (Year) ★score — id=XXXXX]

### Similar Titles
[8 similar films as a compact list: Title (Year) ★score — id=XXXXX]

---

If there are multiple search results, list them clearly and ask the user which one — do not guess or auto-select.
