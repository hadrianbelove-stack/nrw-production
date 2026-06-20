#!/bin/bash
# NRW Local Daily Script
# Runs via launchd every 30 min; keeps retrying until today's CI data is pulled.
# 1. Pulls latest data from GitHub
# 2. Uploads new trailers to B2
# 3. Stamps hosted trailer URLs into data.json and pushes to GitHub
# Sentinel is only created after we confirm CI has run today (via run_diagnostics.json).

export PATH="/opt/homebrew/bin:$PATH"
PROJECT_DIR="/Users/hadrianbelove/Downloads/nrw-production"
LOG="$PROJECT_DIR/logs/launchagent.log"

# Already pulled today's CI data? Done.
SENTINEL="/var/tmp/nrw_daily_$(date +%Y%m%d)"
if [ -f "$SENTINEL" ]; then
    exit 0
fi

echo "" >> "$LOG"
echo "=== NRW Local Daily: $(date) ===" >> "$LOG"

cd "$PROJECT_DIR" || { echo "ERROR: Cannot cd to $PROJECT_DIR" >> "$LOG"; exit 1; }

# Step 1: Pull latest from GitHub
# Strategy: discard local data.json changes (CI version is authoritative),
# stash everything else, pull, then restore stash.
echo "Pulling latest from GitHub..." >> "$LOG"

# Always reset CI-regenerated files before pulling (CI versions are authoritative)
/usr/bin/git checkout -- data.json data_archive.json movie_tracking.json metrics/ cache/wikipedia_cache.json >> "$LOG" 2>&1
# Clean untracked files in metrics/ so they don't block git pull
/usr/bin/git clean -f metrics/ >> "$LOG" 2>&1

# Stash any other local changes
STASHED=false
if ! /usr/bin/git diff --quiet || ! /usr/bin/git diff --cached --quiet; then
    /usr/bin/git stash >> "$LOG" 2>&1
    STASHED=true
    echo "  Stashed local changes" >> "$LOG"
fi

/usr/bin/git pull --rebase origin main >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
    echo "WARNING: git pull failed" >> "$LOG"
fi

if [ "$STASHED" = true ]; then
    /usr/bin/git stash pop >> "$LOG" 2>&1 || echo "WARNING: stash pop had conflicts — resolve manually" >> "$LOG"
    echo "  Restored local changes" >> "$LOG"
fi

# Step 2a: Refresh YouTube cookies from Safari (Aqua session has keychain access)
echo "Refreshing YouTube cookies..." >> "$LOG"
/opt/homebrew/bin/yt-dlp --cookies-from-browser safari \
    --cookies cache/yt_cookies.txt --skip-download \
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ' >> "$LOG" 2>&1 \
    && echo "  Cookies refreshed" >> "$LOG" \
    || echo "  Cookie refresh failed — will use existing file" >> "$LOG"

# Step 2b: Upload new trailers to B2 (download from YouTube + upload, no data.json writes)
echo "Hosting new trailers..." >> "$LOG"
/usr/bin/perl -e 'alarm(3600); exec @ARGV' -- \
    /opt/homebrew/bin/python3.11 scripts/trailer_pipeline.py host >> "$LOG" 2>&1

# Step 3: Stamp hosted trailer URLs into data.json and push to GitHub
# This eliminates the ~19-hour gap where trailers show as YouTube fallbacks.
# Safe: CI finishes 5+ hours before this runs. Stamp is idempotent.
echo "Stamping hosted trailer URLs..." >> "$LOG"
/opt/homebrew/bin/python3.11 scripts/trailer_pipeline.py stamp >> "$LOG" 2>&1

if ! /usr/bin/git diff --quiet data.json 2>/dev/null; then
    echo "  Pushing stamped trailers to GitHub..." >> "$LOG"
    if NRW_ALLOW_DATA_COMMIT=1 /usr/bin/git commit data.json -m "Local trailer stamp — APPROVED: DELETE" >> "$LOG" 2>&1; then
        if /usr/bin/git push origin main >> "$LOG" 2>&1; then
            echo "  Pushed successfully" >> "$LOG"
        else
            echo "  WARNING: Push failed — CI will stamp tomorrow" >> "$LOG"
        fi
    else
        echo "  WARNING: Commit failed — CI will stamp tomorrow" >> "$LOG"
    fi
else
    echo "  No new trailers to stamp" >> "$LOG"
fi

# Only create sentinel if we have today's CI data
CI_DATE=$(/usr/bin/python3 -c "import json; print(json.load(open('metrics/run_diagnostics.json'))['timestamp'][:10])" 2>/dev/null)
TODAY=$(date +%Y-%m-%d)
if [ "$CI_DATE" = "$TODAY" ]; then
    # Step 4: Scrape pull quotes for new movies (ready for morning curation)
    # alarm(3600) hard-kills after 1 hour — same backstop as the trailer step.
    # Without it, one hung scrape froze this script (and all runs behind it)
    # for 3 days in June 2026.
    echo "Scraping pull quotes for new arrivals..." >> "$LOG"
    /usr/bin/perl -e 'alarm(3600); exec @ARGV' -- \
        /usr/bin/python3 scripts/batch_pull_quotes.py >> "$LOG" 2>&1 \
        || echo "  WARNING: pull quotes exited non-zero (timeout or error)" >> "$LOG"
    echo "  Pull quotes done" >> "$LOG"

    # Step 5: Pre-generate capsules (3 variants) for new arrivals so curation
    # reads them from cache/capsule_cache.json instead of waiting on live LLM calls.
    # Skips already-cached movies; alarm(3600) hard-kills a hung run.
    echo "Pre-generating capsules for new arrivals..." >> "$LOG"
    /usr/bin/perl -e 'alarm(3600); exec @ARGV' -- \
        /usr/bin/python3 scripts/write_capsule.py --batch --days 7 --variants 3 --skip-verify >> "$LOG" 2>&1 \
        || echo "  WARNING: capsule batch exited non-zero (timeout or error)" >> "$LOG"
    echo "  Capsules done" >> "$LOG"

    touch "$SENTINEL"
    echo "  CI data is current ($CI_DATE) — sentinel created, done for today" >> "$LOG"
else
    echo "  CI data is stale ($CI_DATE) — will retry next cycle" >> "$LOG"
fi
echo "=== Done: $(date) ===" >> "$LOG"
