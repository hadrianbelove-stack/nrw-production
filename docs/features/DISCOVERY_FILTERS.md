# Discovery Filters Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-046, AMENDMENT-047
**Date:** 2025-10-21 to 2025-10-22
**Maintainer:** Development Team

## Overview

The discovery filters system controls how the NRW movie tracking system discovers new theatrical releases from TMDB. The system evolved from restrictive filtering (vote_count requirements) to a wider discovery approach that relies on provider availability as the primary filter.

## Problem Context

Discovery rate was too low (2 movies in 3 days). Analysis revealed the `vote_count.gte: 1` filter in `movie_tracker.py` was blocking brand-new releases with 0 TMDB votes, preventing discovery of movies that would later become available on streaming platforms.

## Filter Evolution

### Original Approach (Before Oct 21, 2025)
```python
# In movie_tracker.py (DEPRECATED)
discover_params = {
    'vote_count.gte': 1,  # Blocked new releases
    'sort_by': 'primary_release_date.desc',
    'primary_release_date.gte': start_date,
    'primary_release_date.lte': end_date
}
```

**Problems:**
- Movies often have 0 votes for 1-3 days after premiere
- Blocked legitimate theatrical releases
- Discovery rate: ~2 movies/day (too low)

### Current Approach (Oct 21, 2025+)
```python
# In generate_data.py (CURRENT)
discover_params = {
    'sort_by': 'primary_release_date.desc',  # Chronological order
    'primary_release_date.gte': start_date,
    'primary_release_date.lte': end_date
    # vote_count filter REMOVED
}
```

**Benefits:**
- Discovery rate: 10-20 movies/day (5-10x increase)
- Provider availability acts as natural filter
- No missed releases due to vote timing

## Filtering Philosophy

### Primary Filter: Provider Availability
The system uses **provider availability** as the main quality filter rather than TMDB vote counts:

1. **Wide Discovery:** Track all theatrical releases (no vote filter)
2. **Provider Filter:** Only movies with distribution deals get providers
3. **Wall Display:** Only movies with providers appear on public wall
4. **Natural Quality:** Movies without distribution deals never reach users

### Secondary Filters Considered (Rejected)

**Alternative filters evaluated but not implemented:**

1. **`popularity.desc` sorting** - User prefers chronological discovery
2. **`region: 'US'` filter** - Would reduce results (user wants wider discovery)
3. **`with_release_type: '2|3'` filter** - Would reduce results (user wants wider discovery)

**Future considerations:**
- If spam/fake movies appear: Consider adding `vote_average.gte: 4.0` or popularity threshold
- If too many irrelevant movies: Consider adding region or release_type filters
- If discovery rate is still low: Investigate TMDB API parameters or date range

## Current Implementation

### Discovery Architecture
The discovery system was consolidated into `generate_data.py` as part of AMENDMENT-047:

```
daily_orchestrator.py
  ↓
generate_data.py --discover  (find new theatrical releases)
  ↓
generate_data.py --check     (monitor tracking movies for digital availability)
  ↓
generate_data.py             (generate enriched display data)
```

### Legacy System Status
- `movie_tracker.py` → **ARCHIVED** to `museum_legacy/legacy_movie_tracker.py`
- Use ONLY for historical reference and debugging
- **NEVER use in production pipeline**

### Configuration
Discovery settings are controlled via `config.yaml`:

```yaml
discovery:
  max_pages: 10  # Maximum TMDB pages to process
  days_back: 30  # Look back N days for releases
  min_movies: 5  # Minimum movies to discover per run
  timeout: 30    # API timeout in seconds
```

**Deprecated:**
- `api.max_pages_daily` (use `discovery.max_pages`)

## Performance Metrics

### Target Metrics
- **Discovery rate:** 10-20 movies/day (3-day average)
- **Digital conversion:** 2-5 movies/day become available
- **Total tracking:** 600-900 movies after 1 month
- **Wall display:** 250-350 movies (limited by 90-day window)

### Monitoring
- **Baseline script:** `scripts/baseline_metrics.py`
- **Daily tracking:** Discovery count, newly-digital count, total tracking/available
- **Metrics storage:** `metrics/daily.jsonl` for 3-day baselining

### Success Criteria
- 3-day average discovery: 10-20 movies/day
- Quality maintained: No spam movies appearing on wall
- Provider filtering working: Only movies with distribution deals appear on wall

## Testing

### Manual Testing
```bash
# Test discovery
python3 generate_data.py --discover --debug

# Test provider monitoring
python3 generate_data.py --check

# View metrics
python3 scripts/baseline_metrics.py

# Full pipeline
python3 daily_orchestrator.py
```

## Decision Rationale

### Vote Count Filter Removal
1. **Vote count is unreliable for new releases:** Movies often have 0 votes for 1-3 days after premiere
2. **Provider availability is the real filter:** Movies without distribution deals never get providers, so they never appear on the wall
3. **90-day window is based on digital_date:** Long premiere-to-provider gaps don't cause movies to be missed
4. **Empirical approach:** Start wider, narrow later if needed based on actual results

### Provider-First Filtering
- More accurate than vote counts for quality assessment
- Aligns with user goal: movies people can actually watch
- Prevents spam without blocking legitimate releases
- Natural business logic: no distribution = no relevance

## Implementation Status

- ✅ Vote count filter removed from discovery
- ✅ Consolidated discovery into generate_data.py (AMENDMENT-047)
- ✅ Provider monitoring implemented
- ✅ Configuration-driven discovery settings
- ✅ Baseline metrics tracking
- ✅ Legacy movie_tracker.py archived

## Monitoring Plan

### Day 1-3: Initial Testing
- Run discovery, document new movie count
- Monitor discovery rates and quality
- Calculate 3-day average

### Ongoing Monitoring
- **If spam/fake movies appear:** Consider adding `vote_average.gte: 4.0` or popularity threshold
- **If too many irrelevant movies:** Consider adding region or release_type filters
- **If discovery rate is still low:** Investigate TMDB API parameters or date range

## Related Amendments
- AMENDMENT-046: Remove TMDB vote_count Filter for Discovery
- AMENDMENT-047: Production Discovery Architecture
- AMENDMENT-025: Database Update Cadence (original discovery system)