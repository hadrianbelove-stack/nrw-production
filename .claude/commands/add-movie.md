---
description: Add a movie to tracking by TMDB ID
argument-hint: [tmdb-id]
---

Add a movie to NRW tracking by TMDB ID.

Ask user for the TMDB ID if not provided as argument: $ARGUMENTS

Steps:
1. Verify the TMDB ID exists by checking TMDB API
2. Check if movie already exists in movie_tracking.json
3. If not exists, add to tracking with status="tracking"
4. Report: movie title, release date, current status

IMPORTANT: This only adds to tracking. The movie will appear in data.json
after discovery phase detects it's available for digital purchase/streaming.
