# Discovery Filters Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-046, AMENDMENT-047
**Date:** 2025-10-21 to 2025-10-22
**Maintainer:** Development Team

## Overview

The discovery filters system controls how the NRW movie tracking system intakes new theatrical releases from TMDB and discovers provider availability. The system evolved from restrictive filtering (vote_count requirements) to a wider intake approach that relies on provider availability as the primary filter.

## Problem Context

Intake rate was too low (2 movies in 3 days). Analysis revealed the `vote_count.gte: 1` filter in `movie_tracker.py` was blocking brand-new releases with 0 TMDB votes, preventing intake of movies that would later become available on streaming platforms.

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
- Intake rate: ~2 movies/day (too low)

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
- Intake rate: 10-20 movies/day (5-10x increase)
- Provider availability acts as natural filter
- No missed releases due to vote timing

## Filtering Philosophy

### Primary Filter: Provider Availability
The system uses **provider availability** as the main quality filter rather than TMDB vote counts:

1. **Wide Intake:** Track all theatrical releases (no vote filter)
2. **Provider Filter:** Only movies with distribution deals get providers
3. **Wall Display:** Only movies with providers appear on public wall
4. **Natural Quality:** Movies without distribution deals never reach users

### Secondary Filters Considered (Rejected)

**Alternative filters evaluated but not implemented:**

1. **`popularity.desc` sorting** - User prefers chronological intake
2. **`region: 'US'` filter** - Would reduce results (user wants wider intake)
3. **`with_release_type: '2|3'` filter** - Would reduce results (user wants wider intake)

**Future considerations:**
- If spam/fake movies appear: Consider adding `vote_average.gte: 4.0` or popularity threshold
- If too many irrelevant movies: Consider adding region or release_type filters
- If intake rate is still low: Investigate TMDB API parameters or date range

## Current Implementation

### Discovery Architecture
The discovery system was consolidated into `generate_data.py` as part of AMENDMENT-047:

```
daily_orchestrator.py
  ↓
generate_data.py --intake    (intake new premieres from TMDB into tracking database)
  ↓
generate_data.py --discover  (discover provider availability for tracking movies)
  ↓
generate_data.py             (generate enriched display data)
```

### Legacy System Status
- `movie_tracker.py` → **ARCHIVED** to `museum_legacy/legacy_movie_tracker.py`
- Use ONLY for historical reference and debugging
- **NEVER use in production pipeline**

### Configuration
Intake settings are controlled via `config.yaml` (discovery key name preserved for backward compatibility):

```yaml
discovery:
  max_pages: 10  # Maximum TMDB pages to process during intake
  days_back: 30  # Look back N days for releases during intake
  min_movies: 5  # Minimum movies to intake per run
  timeout: 30    # API timeout in seconds
```

**Deprecated:**
- `api.max_pages_daily` (use `discovery.max_pages`)

## Performance Metrics

### Target Metrics
- **Intake rate:** 10-20 movies/day (3-day average)
- **Digital conversion:** 2-5 movies/day become available
- **Total tracking:** 600-900 movies after 1 month
- **Wall display:** 250-350 movies (limited by 90-day window)

### Monitoring
- **Baseline script:** `scripts/baseline_metrics.py`
- **Daily tracking:** Intake count, newly-digital count, total tracking/available
- **Metrics storage:** `metrics/daily.jsonl` for 3-day baselining

### Success Criteria
- 3-day average intake: 10-20 movies/day
- Quality maintained: No spam movies appearing on wall
- Provider filtering working: Only movies with distribution deals appear on wall

## Testing

### Manual Testing
```bash
# Test intake
python3 generate_data.py --intake --debug

# Test provider monitoring
python3 generate_data.py --discover

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
4. **Empirical approach:** Start with wider intake, narrow later if needed based on actual results

### Provider-First Filtering
- More accurate than vote counts for quality assessment
- Aligns with user goal: movies people can actually watch
- Prevents spam without blocking legitimate releases
- Natural business logic: no distribution = no relevance

## Implementation Status

- ✅ Vote count filter removed from intake
- ✅ Consolidated intake/discovery into generate_data.py (AMENDMENT-047)
- ✅ Provider monitoring implemented
- ✅ Configuration-driven intake settings
- ✅ Baseline metrics tracking
- ✅ Legacy movie_tracker.py archived

## Monitoring Plan

### Day 1-3: Initial Testing
- Run intake, document new movie count
- Monitor intake rates and quality
- Calculate 3-day average

### Ongoing Monitoring
- **If spam/fake movies appear:** Consider adding `vote_average.gte: 4.0` or popularity threshold
- **If too many irrelevant movies:** Consider adding region or release_type filters
- **If intake rate is still low:** Investigate TMDB API parameters or date range

## Related Amendments
- AMENDMENT-046: Remove TMDB vote_count Filter for Discovery
- AMENDMENT-047: Production Discovery Architecture
- Amendment 012: Database Update Cadence (original discovery system)