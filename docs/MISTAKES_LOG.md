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

### 2026-03-26 - JustWatch verification gate contradicted wide-net philosophy
**What went wrong:** A JustWatch verification layer was added to the discovery phase (Feb 2026) that could reject movies TMDB flagged as available. On March 26 metrics: JustWatch was "unavailable" for 42 of 44 discoveries (95%), verified only 2, and rejected 1 legitimate movie. The gate added ~30 lines of code complexity while actively blocking valid transitions. Additionally, Type 4 digital dates were labeled "fallback" in code comments, misrepresenting their role as a primary discovery mechanism.
**Correct approach:** Removed JustWatch verification from discovery. JustWatch's valuable role is in enrichment — providing actual rent/buy deep links (Amazon, Apple TV URLs) that TMDB doesn't give us. Discovery should only use TMDB signals (providers + Type 4 dates) with a wide-net approach: if either signal fires, the movie transitions. The admin curates the wall; the pipeline stocks it.
**Rule added:** Discovery gates must be justified by data. A verification layer that fails 95% of the time and blocks 1 legitimate movie per run does more harm than good. Keep discovery wide; curate in admin.

### 2026-04-01 - Lost 7 discoveries during rebase (data file conflict)
**What went wrong:** During a rebase, blindly took the local version of movie_tracking.json instead of comparing it with CI's version. CI had 7 new discoveries that the local version didn't have. Those discoveries were silently lost.
**Correct approach:** Data file conflicts (data.json, movie_tracking.json) require comparing both versions. Prefer CI's movie_tracking.json (it has discoveries from automated runs). Never use `checkout --ours/--theirs` blindly.
**Rule added:** CLAUDE.md Data Rules now explicitly prohibit blind checkout during conflicts.

### 2026-04 - Movie ID comparison bug (recurring, 3+ incidents)
**What went wrong:** Code used bare `==` comparison (`m.get('id') == 1654730`) to find movies in data.json. data.json has mixed ID types (~915 string IDs + ~33 integer IDs). Bare `==` silently fails when comparing int to string. Caused failed removals at least 3 times (Qashmoo, etc.).
**Correct approach:** ALWAYS use `str(m.get('id'))` when comparing movie IDs. Pattern: `[m for m in movies if str(m.get('id')) not in remove_set]`
**Rule added:** CLAUDE.md Data Rules and MEMORY.md both flag this as CRITICAL.

### 2026-04 - AI theorized without running code (Sheng Wang: Purple)
**What went wrong:** Built multi-message theory that "JustWatch can't find Sheng Wang: Purple" and "Type 4 discovery loses provider names" — without running `client.verify_availability()`, which would have returned a perfect match + Netflix URL in seconds. Multiple messages wasted on a fictional root cause.
**Correct approach:** Before claiming "X fails for movie Y," RUN THE ACTUAL CODE on movie Y first. One test call beats ten minutes of code-reading speculation.
**Rule added:** CLAUDE.md Diagnosis Rules: "Run code before theorizing."

### 2026-04 - AI concluded system behavior without checking all passes (Captain Tsunami)
**What went wrong:** Concluded "Dances With Films isn't a tracked festival" as the sole explanation for why a movie wasn't intaken, without checking that Passes A and B intake ALL movies from TMDB regardless of festival. Presented a single hypothesis as fact.
**Correct approach:** Never conclude how a system works without reading the actual code for ALL relevant passes/phases. Multiple hypotheses are mandatory.
**Rule added:** CLAUDE.md Diagnosis Rules: "Verify system behavior before concluding."
