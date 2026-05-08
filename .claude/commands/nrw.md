---
description: Start site (3000) and admin (5556) servers
---

Run the unified launcher script:

```bash
./launch_all.sh
```

This handles everything automatically:
- Kills stale processes
- Verifies servers respond before reporting success
- Opens browsers
- Ctrl+C stops both cleanly

DO NOT manually start servers with `python3 -m http.server` or `python3 admin.py`. Always use the script.

## Post-Launch Report (REQUIRED)

After servers are running, you MUST generate a data quality report in the chat by running the shared wall health script:

```bash
python3 scripts/wall_health.py
```

The script outputs a full structured report — present it as-is. Every section has tables listing individual movies. **Show every table with every movie row. NEVER collapse a table into a summary count** (e.g., don't write "9 missing posters" — show the 9 titles). Sections in order:

1. **Dashboard**: Wall size, pipeline status, coverage percentages.
2. **Today's arrivals**: table with columns: Movie | RT | MC | Wiki | Trailer | IMDb | Links | Services. Uses `yes`/`--` for enrichment fields, `NONE` for missing links, and shows which VOD services each movie links to.
3. **Zero watch links**: Each movie shows its digital date, days on wall, and a detailed status explaining WHY it has no links (JW revert reason, which excluded platform, TMDB platform info, revert count). A CRITICAL alert (>5%) means the pipeline is likely broken. Movies age out of this section after 3 days.
4. **JW REVERTS**: Grouped by reason (summary counts, excluded platform breakdown, repeat offenders reverted 2+ times), then **full list with every movie title** and TMDB platforms. Tracking only — not on wall. Movies reverted for "excluded platforms" should always name which platform.
5. **Coverage gaps**: Wall-wide missing counts, then two tables: completely un-enriched movies (0/5 fields) and recent arrivals (14 days) missing 4/5 fields.
6. **Pre-orders & upcoming**: All future-dated movies sorted by date with link count and service names. Summary line shows how many have links.
7. **Pipeline trend**: 14-day table of daily intake + transitions. Flags stall days.
8. **Enrichment gaps**: Movies missing poster, synopsis, or watch links — show every title grouped by gap type.
9. **Trailer hosting failures**: Recent failures with title and reason.

Flag any failures or concerns clearly at the end.
