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

Present the output as a formatted report. The script outputs a table for today's arrivals showing enrichment coverage (RT/MC/Wiki/Trailer/IMDb/Links) — present it directly as-is. Key sections:

- **ZERO WATCH LINKS** is the most critical section. Each movie shows its digital date, days on wall, and a detailed status explaining WHY it has no links (JW revert reason, which excluded platform, TMDB platform info, revert count). Zero watch links on a wall movie is NEVER normal — it signals enrichment failure. A CRITICAL alert means the pipeline is likely broken.

- **JW REVERTED (tracking only)** shows movies that were discovered and reverted but are NOT on the wall — these are safely in tracking and just FYI.

- Movies reverted for "excluded platforms" should always name which platform (fuboTV, Philo, etc.). If the platform name wasn't recorded in tracking, the report says so explicitly.
