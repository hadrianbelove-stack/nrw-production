# Bootstrap Date Accuracy Issue

## Overview

During the initial bootstrap on September 6, 2025, approximately 50 movies were marked as "digitally available" with the bootstrap date (2025-09-06) rather than their actual digital release dates. This occurred because the legacy tracking system set `digital_date = today` when providers were first detected.

## Impact

Movies with August 2025 premiere dates showing September 6 digital dates are inaccurate by days or weeks. This affects the chronological ordering and date-based filtering on the public site.

## Resolution

All affected movies are flagged with `bootstrap_date: true` in the database. Multiple correction mechanisms are in place:

- **Website Display**: Visual indicator ("~" prefix or tooltip) for bootstrap dates
- **Admin Panel**: Highlights these movies for manual correction
- **Manual Correction**: High-profile titles are being corrected manually over time
- **Future Prevention**: New movies use TMDB's release date field for accuracy

## For Users

If you see a "~" symbol or approximate date indicator, this means the exact digital release date is uncertain. The movie was discovered on that date but may have been available earlier.

**What This Means:**
- The date shown is when we first detected the movie, not necessarily when it became available
- The actual release date could be earlier (by days or weeks)
- High-profile movies are being corrected manually as we verify accurate dates

## For Developers

See the following documentation for full technical details and implementation:
- `IMPLEMENTATION_ROADMAP.md` - CRITICAL-001: Bootstrap Date Accuracy
- `PROJECT_CHARTER.md` - AMENDMENT-049: Bootstrap Date Handling

**Technical Details:**
- Database field: `bootstrap_date: true` flag in `movie_tracking.json`
- Display logic: Frontend checks this flag and adds visual indicators
- Admin panel: Filter for `bootstrap_date: true` to find affected movies

## Correction Tools

Multiple tools are available for correcting bootstrap dates:

**Admin Panel** (Recommended for individual corrections):
```bash
./launch_all.sh
# Navigate to http://localhost:5556
# Use /update-date endpoint for manual corrections
```

**CLI Tool** (For batch corrections):
```bash
# Single movie correction
python3 date_verification.py

# Batch corrections from CSV
python3 date_verification.py --csv corrections.csv
```

**CSV Format:**
```csv
tmdb_id,correct_digital_date,source
507244,2025-08-15,TMDB release_date field
12345,2025-08-20,Manual verification
```

## Prevention

The current provider discovery system (integrated into `generate_data.py --discover`) uses TMDB's `release_date` field and no longer sets dates to "today" when providers are detected. This issue will not recur for new movies.

**How It Works Now:**
1. Intake finds new theatrical releases via TMDB API
2. System checks TMDB's `release_date` field for digital release date
3. If digital release date is available, use it (not today's date)
4. If not available, mark as "not yet digital" and monitor for provider availability
5. When providers appear, use the earliest known date (not detection date)

**Code Reference:**
- `pipeline/generator.py` — `intake_new_premieres()` and `_run_intake_pass()` handle TMDB release_date integration
- `pipeline/generator.py` — `check_tracking_movies()` handles provider monitoring without date override

## Related Documentation

- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) - Tactical roadmap
- [PROJECT_CHARTER.md](PROJECT_CHARTER.md) - AMENDMENT-049 governance