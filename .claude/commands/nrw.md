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

After servers are running, run `/wallhealth` and present the full report in the chat.

## Curation (REQUIRED)

After the wall health report, run `/curate` to curate new arrivals (staff picks, sections, pull quotes, capsules).

## Session Timestamp (REQUIRED)

After curation is complete, save the current timestamp so `/launchagentreport` knows when you last opened the site:

```python
import json, time
with open('.claude/last_nrw_session.json', 'w') as f:
    json.dump({"timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'), "note": "Last time user opened the site"}, f)
```
