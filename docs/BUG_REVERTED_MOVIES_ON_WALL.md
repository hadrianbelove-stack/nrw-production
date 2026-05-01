# Bug: Reverted Movies Remain on the Wall

## The Problem

When the JustWatch pre-verification step fails during enrichment, movies are correctly reverted to `status=tracking` in movie_tracking.json — but they **remain in data.json with zero watch links**, visible on the NRW wall. Users see movies they can't watch.

As of April 30, 2026, there are 5 stranded movies on the wall with zero watch links:
- The Mohican (reverted: fuboTV only)
- The True Beauty of Being Bitten by a Tick (reverted: no JustWatch match)
- Vindication: Search and Rescue (reverted: no JustWatch match)
- The Adventure (reverted: Rakuten Viki only)
- I Can't Write (reverted: no JustWatch match)
- LOVED ONE (different issue — `status=available` but zero links since April 8)

---

## How the Pipeline Works (Correct Terminology)

The pipeline runs in sequential phases. Discovery has **two co-equal mechanisms** — both use TMDB:

### Phase 2: Discovery

Discovery checks each `status=tracking` movie for two signals:

**Signal 1: TMDB Type 4 digital release date** — checks TMDB's `/release_dates` endpoint for a Type 4 (Digital) entry. Binary: either it exists or it doesn't. No platform/provider info in this check. Sets `digital_date` if found. Code at `generator.py:1806-1833`.

**Signal 2: TMDB watch/providers** — calls TMDB's `/watch/providers` endpoint, which returns provider names (Apple TV, Fandango, etc.). Discovery is binary: `has_providers = True` if ANY provider exists at all. No excluded_services filtering at this stage. Code at `generator.py:991`.

If either signal fires for a `status=tracking` movie, the movie transitions to `status=available`. At this point, `add_movie_to_site_immediately()` is called (line 1025), which **writes the movie into data.json immediately** with `_enrichment_status: 'pending'`. The movie is now on the wall.

### Phase 3: Enrichment

Before running expensive enrichment (Rotten Tomatoes, Wikipedia, trailers, etc.), JustWatch is queried as a **pre-verification step** (code at `generator.py:3513-3574`).

JustWatch pre-verification checks whether the movie is available on platforms NRW actually wants to link to (excludes fuboTV, Google Play, Philo, Rakuten Viki, etc.). Two failure modes:

1. `justwatch_no_match` — JustWatch can't find the movie at all
2. `justwatch_no_valid_offers` — JustWatch finds the movie but it's only on excluded platforms

If pre-verification fails, the code reverts:
- `movie_tracking.json`: sets `status=tracking`, adds `_jw_revert_reason` and `_jw_reverted_at`
- `data.json` (the in-memory copy): sets `status=tracking` and `_enrichment_status=reverted`

**BUT it does NOT remove the movie from the data.json movies array.** The movie stays in data.json and is saved back to disk at line 3694.

---

## The Gap

```
Phase 2 (Discovery)        Phase 3 (Enrichment)
       |                          |
  Movie discovered          JW pre-check fails
       |                          |
  Written to data.json      Status set to 'tracking'
  (visible on wall!)        in data.json, BUT...
       |                          |
       |                   NOT REMOVED from data.json
       |                          |
       ▼                          ▼
  Movie on wall ──────────► Still on wall, zero links
```

The movie is added to data.json in Phase 2 (line 1025) but the JustWatch check doesn't happen until Phase 3 (line 3537). When JW fails and the movie is reverted, lines 3568-3571 update the movie's metadata in the array but never remove it:

```python
# generator.py lines 3563-3574 — the revert block
if not _jw_verified and not _is_manual and not _has_override:
    _today_iso = datetime.now().strftime('%Y-%m-%d')
    tracking_data['movies'][movie_id]['status'] = 'tracking'          # tracking DB ✓
    tracking_data['movies'][movie_id]['_jw_revert_reason'] = _revert_reason
    tracking_data['movies'][movie_id].setdefault('_jw_reverted_at', _today_iso)
    existing_movies[movie_index]['_jw_reverted'] = True               # data.json copy
    existing_movies[movie_index]['_jw_revert_reason'] = _revert_reason
    existing_movies[movie_index]['_enrichment_status'] = 'reverted'
    existing_movies[movie_index]['status'] = 'tracking'               # ← sets status but DOESN'T remove
    print(f"  🔄 {_title} — JW pre-check: {_revert_reason} → reverted to tracking")
    signal.alarm(0)
    continue                                                           # ← skips enrichment, movie stays
```

There IS a `purge_removed_movies()` function at line 4140 that removes movies from data.json — but it only handles `status='removed'` (manual `/remove` deletions). It does NOT check for `_enrichment_status='reverted'` or `status='tracking'`.

---

## What Needs to Change

The reverted movie needs to be **removed from data.json**, not just have its status field updated. Two approaches:

### Option A: Remove in the revert block itself
After lines 3568-3571 (where the revert flags are set), remove the movie from `existing_movies`:

```python
# After setting revert flags, remove from data.json
existing_movies.pop(movie_index)
# Adjust movie_index tracking if iterating by index
```

Caveat: since the code iterates over `newly_available_ids` with index lookups into `existing_movies`, removing by index mid-loop could cause off-by-one issues. Would need careful handling.

### Option B: Filter during save (simpler)
At the point where `existing_movies` is saved back to data.json (line 3694), filter out any movie with `_enrichment_status == 'reverted'`:

```python
# Before saving, strip reverted movies
existing_movies = [m for m in existing_movies if m.get('_enrichment_status') != 'reverted']
```

### Option C: Extend purge_removed_movies()
Extend the existing `purge_removed_movies()` function (line 4140) to also purge movies with `_enrichment_status='reverted'`. This runs during display generation, so it would catch reverted movies on the next pipeline run.

---

## Key Files and Line Numbers

| File | Line | What's there |
|------|------|-------------|
| `pipeline/generator.py` | 991 | `has_providers` check (discovery Signal 2) |
| `pipeline/generator.py` | 1002-1025 | Discovery transition: status → available, `add_movie_to_site_immediately()` |
| `pipeline/generator.py` | 1835-1958 | `add_movie_to_site_immediately()` — writes to data.json |
| `pipeline/generator.py` | 3513-3574 | JustWatch pre-verification and revert block |
| `pipeline/generator.py` | 3563-3574 | The revert: sets status/flags but doesn't remove from array |
| `pipeline/generator.py` | ~3694 | `_safe_save_data_json()` — saves existing_movies back to disk |
| `pipeline/generator.py` | 4140-4174 | `purge_removed_movies()` — only handles `status='removed'`, not reverted |

---

## One-Time Cleanup Needed

After the fix is deployed, the 5 currently-stranded movies need to be cleaned out. Either:
- Run the pipeline with the fix, which will filter them on save
- Or manually remove them (they're already `status=tracking` in tracking, so they won't be re-discovered unless TMDB/JW data changes)
