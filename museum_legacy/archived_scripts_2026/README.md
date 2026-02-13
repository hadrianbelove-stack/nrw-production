# Archived Scripts (February 2026)

These scripts were moved from `scripts/` during Priority 3.4 cleanup.

## One-Time Migrations (completed)
- `backfill_original_language.py` - Backfilled original_language from TMDB
- `flag_bootstrap_dates.py` - Fixed Sept 6, 2025 bootstrap date issue
- `migrate_approvals_to_drafts.py` - Converted approval.json to drafts system
- `migrate_categories.py` - Added categories to existing movies

## Unused Utilities (never called by pipeline)
- `baseline_metrics.py` - Computed 3-day baseline metrics (manual tool)
- `check_immediate_write_failures.py` - Monitored immediate write failures log
- `generate_missing_links_report.py` - Generated missing links report
- `link_manual_to_tmdb.py` - Linked manual entries to TMDB IDs

## Occasional Utilities (archived per user request)
- `cleanup_no_date_movies.py` - Removed movies without digital_date
- `enrich_wikipedia_only.py` - Backfilled Wikipedia URLs

## YouTube Auth (rarely needed, for fixing YouTube playlist feature)
- `diagnose_youtube_auth.py` - Comprehensive YouTube OAuth diagnostics
- `manual_youtube_auth.py` - Simple YouTube OAuth flow
- `encode_youtube_token.sh` - Encode token for GitHub secrets

## Still Active in scripts/
- `youtube_trailer_scraper.py` - Used by pipeline/generator.py
