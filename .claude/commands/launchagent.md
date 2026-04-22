---
description: Manually run the local launchagent (git pull + trailer hosting)
---

Run the local launchagent script manually. Use this when the scheduled run was missed.

## Steps

1. Check if today's sentinel exists:
   ```bash
   ls /var/tmp/nrw_daily_$(date +%Y%m%d) 2>/dev/null && echo "SENTINEL EXISTS" || echo "No sentinel"
   ```

2. If the sentinel exists, warn the user: "The launchagent already ran today (sentinel exists). Running again will re-upload trailers and re-pull from GitHub. Delete the sentinel and continue?"
   - Wait for confirmation before proceeding.

3. Delete the sentinel so the script will run:
   ```bash
   rm -f /var/tmp/nrw_daily_$(date +%Y%m%d)
   ```

4. Run the script:
   ```bash
   bash scripts/local_daily.sh
   ```

5. Then run `/launchagentreport` to summarize the results.
