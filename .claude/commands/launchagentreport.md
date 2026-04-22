---
description: Check today's launchagent run — git pull + trailer hosting results
---

Show the result of today's local launchagent run:

1. Read the last 100 lines of `logs/launchagent.log`
2. Report:
   - Did it run today? (look for today's date in the log)
   - Git pull result: was CI data current, or did it pull new commits?
   - Trailer hosting results: how many hosted / failed / skipped?
   - For each failure or skip: movie title + reason (e.g. "paywalled", "region locked", "timed out")
   - For each success: movie title
   - Final status line and timestamp

Format as a short summary (not raw log). Flag any failures clearly.
