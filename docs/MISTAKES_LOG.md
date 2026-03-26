# NRW Mistakes Log

When adding entries, consider: should this become a Critical Rule in CLAUDE.md? If the mistake could cause data loss or require significant recovery, promote it.

## Template

```
### [Date] - Brief description
**What went wrong:**
**Correct approach:**
**Rule added:** (if promoted to Critical Rules in CLAUDE.md)
```

---

### 2026-02-02 - Manually launched servers instead of using launch_all.sh
**What went wrong:** Repeatedly launched servers manually with `python3 -m http.server` and `python3 admin.py`, causing stale process issues. Assumed servers were running based on lsof output without verifying they responded.
**Correct approach:** ALWAYS use `./launch_all.sh` - it handles killing stale processes, port conflicts, and verifies servers respond before reporting success.
**Rule added:** Never manually launch servers. The script exists for a reason. Quick reference: Site = 3000, Admin = 5556

### 2026-03-25 - Type 4 discovery removed, then restored with cascading failures
**What went wrong:** Type 4 (digital release date) checking was accidentally removed from the discovery loop on Feb 27 during a pre-order detection overhaul. This silently broke discovery for movies where TMDB's provider endpoint lagged behind its release_dates endpoint. On March 25, this resulted in 0 new arrivals (Pretty Lethal was available on Amazon Prime but invisible to discovery). The fix attempt caused three cascading failures: (1) mass-transitioning 1,258 old movies (no time limit on Type 4 dates), (2) crash on empty provider lists, (3) movies orphaned between tracking and data.json because `add_movie_to_site_immediately` wasn't re-called after the crash fix.
**Correct approach:** Added 14-day limit to Type 4 discovery to prevent mass-transitions. Fixed crash for empty provider lists. Added enrichment catch-up logic so incomplete enrichment is automatically retried (up to 3 attempts). Added tracking database sync after enrichment.
**Rule added:** Enrichment must be self-healing — movies with gaps should be retried automatically. Never remove a discovery trigger without understanding the downstream impact.
