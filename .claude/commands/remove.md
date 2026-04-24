---
description: Remove a movie from the NRW wall by title or TMDB ID
allowed-tools: Bash, Read, Grep, Edit
---

Remove a movie from data.json and archive it safely. This is an AUTHORIZED override of the CLAUDE.md data rule — the user is explicitly requesting removal via this command.

**Argument**: $ARGUMENTS (movie title or TMDB ID)

Steps:

1. Pull latest from CI first: `git pull origin main`
2. Search data.json for the movie by title (case-insensitive partial match) or by TMDB ID
2. If multiple matches, show them and ask which one to remove
3. If exactly one match, confirm the title, TMDB ID, and digital_date with the user before proceeding
4. Once confirmed, run a Python script (`/usr/bin/python3`) that:
   - Removes the movie from data.json
   - Appends it to data_archive.json (deduped by ID, using `str(m.get('id'))`)
   - Sets `status: "removed"` and `removed_date` in movie_tracking.json. If the movie ID is NOT already in movie_tracking.json, CREATE a minimal entry: `{title, year, status: "removed", removed_date}`
   - Prints what was done
5. Sync with CI: commit and push movie_tracking.json so the pipeline knows about the removal:
   - `git add movie_tracking.json`
   - Commit with message: `"Remove [movie title] from NRW wall"`
   - `git push origin main`
   - Do NOT commit data.json (CI regenerates it; pushing would cause merge conflicts)
6. Report the result: movie title, old movie count, new movie count, and confirm push succeeded
