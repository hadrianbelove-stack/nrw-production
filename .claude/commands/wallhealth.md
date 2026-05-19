---
description: Wall health report — standardized data quality snapshot
---

Run the wall health script:

```bash
python3 scripts/wall_health.py
```

## Presentation Rules

1. **Present the script output as-is in the chat.** Do not reformat into markdown tables — use the script's own spacing and layout.
2. **Every movie row includes its TMDB link.** The script appends a TMDB URL to every row. Never drop it.
3. **Show every table with every movie row.** NEVER collapse a table into a summary count (e.g., don't write "9 missing posters" — show the 9 titles).
4. **Flag concerns** at the end: stalls, critical alerts, trailer failures, enrichment gaps.

## Sections (in order)

1. **Dashboard**: Wall size, pipeline status, coverage percentages.
2. **Today's arrivals**: Movie | RT | MC | Wiki | Trailer | IMDb | Links | Services | TMDB link.
3. **Zero watch links**: Title | Digital date | Days on wall | Status (why no links) | TMDB link. CRITICAL alert if >5%.
4. **JW reverts**: Reason summary, excluded platform breakdown, repeat offenders (2+), then full list: Date | Title | Year | Reason / TMDB Platforms | TMDB link.
5. **Coverage gaps**: Wall-wide missing counts. Two tables: zero enrichment (0/5) and recent arrivals (14d) missing 4/5 — both with TMDB links.
6. **Pre-orders & upcoming**: Date | Title | Links | Pre-order Services | TMDB Platforms | TMDB link. Summary line: how many have links.
7. **Pipeline trend**: 14-day table of daily intake + transitions. Flag stall days.
8. **Enrichment gaps**: Movies missing poster, synopsis, or watch links — every title grouped by gap type, with TMDB links.
9. **Trailer hosting failures**: Date | Title | Reason | TMDB link.
