---
description: Full diagnostic on a movie — NRW state, tracking flags, TMDB details, discovery signals, JustWatch, IMDb cache, wall data
argument-hint: [movie title or partial title]
allowed-tools: Bash, Read
---

Run a full diagnostic on a movie and present the findings as a clean report. Read-only — nothing is modified.

**Argument**: $ARGUMENTS

---

## Instructions

Run the data collection script below, then write a clear report for the user based on the output. Do NOT just paste the raw terminal output — synthesize it into a readable summary with plain-language interpretation.

### Step 1 — Collect all data

```bash
/usr/bin/python3 - << 'PROBE_EOF'
import json, sys, os, requests, logging
from dotenv import load_dotenv
load_dotenv("/Users/hadrianbelove/Downloads/nrw-production/.env")

TITLE_QUERY = """$ARGUMENTS"""
TMDB_KEY = os.environ.get('TMDB_API_KEY', '')
EXCLUDED = ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play', 'Shahid VIP', 'Viki', 'Futo']
EXCLUDED_LOWER = [e.lower() for e in EXCLUDED]

sys.path.insert(0, '.')
from pipeline.tracking_db import get_tracking_db

all_movies = get_tracking_db().load_all().get('movies', {})
wall_lookup = {}
if os.path.exists('data.json'):
    for m in json.load(open('data.json')).get('movies', []):
        wall_lookup[str(m.get('id',''))] = m

imdb_cache = {}
if os.path.exists('cache/imdb_rating_cache.json'):
    imdb_cache = json.load(open('cache/imdb_rating_cache.json'))

query_lower = TITLE_QUERY.lower().strip()
matches = []
for mid, m in all_movies.items():
    if query_lower in m.get('title', '').lower():
        matches.append((mid, m))
if not matches:
    for mid, m in wall_lookup.items():
        if query_lower in m.get('title', '').lower():
            if not any(x[0] == mid for x in matches):
                matches.append((mid, m))

if not matches:
    print(f"NO_MATCH: '{TITLE_QUERY}'")
    sys.exit(0)
if len(matches) > 4:
    print(f"AMBIGUOUS: {len(matches)} matches")
    for mid, m in matches[:8]:
        print(f"  {m.get('title')} ({m.get('year','?')}) — {m.get('status','?')} — id={mid}")
    sys.exit(0)

for movie_id, tracking_data in matches:
    is_tv = str(movie_id).startswith('tv_')
    numeric_id = str(movie_id).replace('tv_', '')
    title = tracking_data.get('title', str(movie_id))
    year  = str(tracking_data.get('year', '?'))
    status = tracking_data.get('status', '?')
    wall = wall_lookup.get(str(movie_id), {})

    print(f"MOVIE: {title} | {year} | id={movie_id} | status={status}")

    # All tracking flags
    flag_keys = ['digital_date','_discovery_source','_enrichment_status','_enrichment_attempts',
                 '_enrichment_gaps','_skip_provider_discovery','_type4_false_positive',
                 '_providers_false_positive','_reverted_from_available','_false_positive_source',
                 '_jw_revert_count','_jw_revert_reason','_jw_reverted_at','_type4_pending',
                 '_is_preorder','_buyonly_preorder','_added_manually','manually_corrected']
    for k in flag_keys:
        v = tracking_data.get(k) or wall.get(k)
        if v is not None and v is not False and v != [] and v != '':
            print(f"FLAG: {k}={v}")

    # Wall data
    if wall:
        vod = wall.get('watch_links',{}).get('vod',[])
        stream = wall.get('watch_links',{}).get('streaming',[])
        print(f"WALL_RT: {wall.get('rt_score','none')}")
        print(f"WALL_IMDB: {wall.get('imdb_id','none')} rating={wall.get('imdb_rating','none')}")
        print(f"WALL_WIKI: {wall.get('links',{}).get('wikipedia') or 'none'}")
        print(f"WALL_TRAILER: {wall.get('links',{}).get('trailer') or 'none'}")
        print(f"WALL_HOSTED: {wall.get('links',{}).get('trailer_hosted') or 'none'}")
        for v in vod:
            print(f"WALL_VOD: {v.get('service')} rent={v.get('rent_price','?')} buy={v.get('buy_price','?')}")
        for s in stream:
            print(f"WALL_STREAM: {s.get('service')}")

    # TMDB details
    try:
        ep = 'tv' if is_tv else 'movie'
        r = requests.get(f"https://api.themoviedb.org/3/{ep}/{numeric_id}",
            params={'api_key': TMDB_KEY, 'append_to_response': 'credits,external_ids'}, timeout=12)
        if r.status_code == 200:
            d = r.json()
            directors = [p['name'] for p in d.get('credits',{}).get('crew',[]) if p.get('job')=='Director']
            if is_tv: directors = [p['name'] for p in d.get('created_by',[])]
            imdb_id = d.get('imdb_id') or d.get('external_ids',{}).get('imdb_id','')
            genres = ', '.join(g['name'] for g in d.get('genres',[]))
            cast = [p['name'] for p in d.get('credits',{}).get('cast',[])[:5]]
            print(f"TMDB_STATUS: {d.get('status','?')}")
            print(f"TMDB_DIRECTOR: {', '.join(directors) or 'unknown'}")
            print(f"TMDB_RUNTIME: {d.get('runtime','?')}")
            print(f"TMDB_GENRES: {genres}")
            print(f"TMDB_VOTE: {d.get('vote_average','?')}/10 ({d.get('vote_count','?')} votes)")
            print(f"TMDB_CAST: {', '.join(cast)}")
            if d.get('tagline'): print(f"TMDB_TAGLINE: {d['tagline']}")
            if imdb_id:
                print(f"TMDB_IMDB_ID: {imdb_id}")
                if imdb_id in imdb_cache:
                    c = imdb_cache[imdb_id]
                    print(f"IMDB_CACHED: rating={c.get('rating','none')} source={c.get('source')} date={c.get('scraped_at','?')[:10]}")
    except Exception as e:
        print(f"TMDB_ERROR: {e}")

    # Type 4
    if not is_tv:
        try:
            r4 = requests.get(f"https://api.themoviedb.org/3/movie/{numeric_id}/release_dates",
                              params={'api_key': TMDB_KEY}, timeout=10)
            type4_date = None
            if r4.status_code == 200:
                for entry in r4.json().get('results', []):
                    if entry.get('iso_3166_1') == 'US':
                        for rel in entry.get('release_dates', []):
                            if rel.get('type') == 4:
                                type4_date = rel.get('release_date', '')[:10]
            if type4_date:
                from datetime import date
                past = type4_date <= str(date.today())
                print(f"TYPE4: {type4_date} past={past}")
            else:
                print("TYPE4: none")
        except Exception as e:
            print(f"TYPE4_ERROR: {e}")
    else:
        print("TYPE4: tv_skipped")

    # Providers
    try:
        ep2 = 'tv' if is_tv else 'movie'
        rp = requests.get(f"https://api.themoviedb.org/3/{ep2}/{numeric_id}/watch/providers",
                          params={'api_key': TMDB_KEY}, timeout=10)
        us = rp.json().get('results',{}).get('US',{}) if rp.status_code == 200 else {}
        rent   = [p.get('provider_name') for p in us.get('rent',[])]
        buy    = [p.get('provider_name') for p in us.get('buy',[])]
        stream = [p.get('provider_name') for p in us.get('flatrate',[])]
        print(f"PROVIDERS_STREAM: {', '.join(stream) or 'none'}")
        print(f"PROVIDERS_RENT: {', '.join(rent) or 'none'}")
        print(f"PROVIDERS_BUY: {', '.join(buy) or 'none'}")
    except Exception as e:
        print(f"PROVIDERS_ERROR: {e}")

    # JustWatch
    try:
        from pipeline.justwatch import JustWatchClient
        jw = JustWatchClient(logger=logging.getLogger('probe'))
        yr = int(year) if str(year).isdigit() else None
        res = jw.verify_availability(title=title, year=yr,
                                     content_type='tv' if is_tv else 'movie',
                                     tmdb_id=str(numeric_id))
        if res:
            pnames = res.get('provider_names',{})
            s_p = pnames.get('streaming',[])
            r_p = pnames.get('rent',[])
            b_p = pnames.get('buy',[])
            all_jw = s_p + r_p + b_p
            excl  = [p for p in all_jw if p.lower() in EXCLUDED_LOWER]
            valid = [p for p in all_jw if p.lower() not in EXCLUDED_LOWER]
            print(f"JW_MATCH: {res.get('jw_title')} ({res.get('jw_year')}) conf={res.get('match_confidence')}")
            print(f"JW_STREAM: {', '.join(s_p) or 'none'}")
            print(f"JW_RENT: {', '.join(r_p) or 'none'}")
            print(f"JW_BUY: {', '.join(b_p) or 'none'}")
            print(f"JW_EXCLUDED: {', '.join(excl) or 'none'}")
            print(f"JW_VALID: {', '.join(valid) or 'none'}")
        else:
            print("JW_MATCH: none")
    except Exception as e:
        print(f"JW_ERROR: {e}")

PROBE_EOF
```

### Step 2 — Write the report

Take the output above and write a clean markdown report with these sections. Use plain English throughout — the user is a non-technical Creative Director.

**Header**: Movie title, year, TMDB ID, NRW status (tracking/available/on wall)

**Pipeline Flags** (only if any exist): Explain what each flag means in plain terms. Flag `_skip_provider_discovery=True` means "provider discovery is permanently blocked — the pipeline will never check this again." `_jw_revert_count=10` means "JustWatch rejected this movie 10 times." Be specific about consequences.

**What's on the Wall** (only if status=available): RT score, IMDb rating, Wikipedia link, trailer status, all watch links with prices.

**Movie Info**: Director, runtime, genres, cast, TMDB vote score, IMDb rating (cached or live), tagline if interesting.

**Discovery Signals** (the most important section for tracking movies): Explain in plain English what each signal returned. "TMDB thinks it's on Netflix" not "PROVIDERS_STREAM: Netflix." Then say whether it would actually be discovered today and why/why not.

**Verdict**: One clear paragraph. What is the situation with this movie right now? Is it discoverable? Is it stuck? Does it need manual intervention? What should the user do if anything?

Keep the report tight — if a section has nothing interesting, skip it or keep it to one line.
