---
description: Check today's launchagent run — git pull + trailer hosting results
---

Show the result of today's local launchagent run:

1. Read the last 50 lines of `logs/launchagent.log`
2. Report:
   - Did it run today? (look for today's date in the log)
   - Git pull result: was CI data current, or did it pull new commits?
   - Trailer hosting results: how many hosted / failed / skipped?
   - Any failures — include the movie title and reason
   - Final status line and timestamp

Format as a short summary (not raw log). Flag any failures clearly.
