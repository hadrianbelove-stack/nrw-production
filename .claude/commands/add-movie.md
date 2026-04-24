---
description: Add a movie to the NRW wall immediately with enrichment
argument-hint: [tmdb-id or title]
allowed-tools: Bash, Read, Grep, Edit, WebSearch
---

Add a movie to the NRW wall with immediate enrichment and CI sync. This is an AUTHORIZED override of the CLAUDE.md data rule — the user is explicitly requesting addition via this command.

**Argument**: $ARGUMENTS (TMDB ID or movie title)

Steps:

1. If argument is not a numeric TMDB ID, search TMDB for the title and confirm the correct match with the user
2. Pull latest from CI first: `git pull origin main`
3. Verify the TMDB ID exists by fetching from TMDB API (use config.yaml tmdb_api_key)
4. Check if movie already exists in data.json or movie_tracking.json — warn if duplicate
5. Once confirmed, run a Python script (`/usr/bin/python3`) that:
   - Adds movie to `movie_tracking.json` with `status: "available"`, `digital_date: today`
   - Uses `DataGenerator.add_movie_to_site_immediately()` to create a minimal data.json entry (fetches TMDB details for poster, overview, genres)
   - Prints what was done
6. Run single-movie enrichment: `/usr/bin/python3 generate_data.py --enrich-id [TMDB_ID]`
   - This enriches just this one movie (~30-60 seconds): RT score, Wikipedia, trailer, watch links
7. Commit and push BOTH files:
   - `git add data.json movie_tracking.json`
   - Commit with message: `"Add [movie title] to NRW wall"`
   - `git push origin main`
8. Report: movie title, enrichment results (what was found: RT score, wiki, trailer, watch links), push status
