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
CAPSULE_LOG="$PROJECT_DIR/logs/claude_capsules.log"

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

# Step 3a2: RT-link gap sweep — find Rotten Tomatoes pages CI missed.
# RT's search page bot-walls datacenter IPs (~half of CI's lookups fail
# silently; verified Jul 2026), so this runs HERE for the same reason trailer
# hosting does: the Mac's IP works. Capped (15/run, 3 attempts/film, 2-day
# cooldown) so most days it's a few seconds. Once a link lands, CI's nightly
# quote scrape + the merge side-fill pick up the critic quotes automatically.
echo "RT-link gap sweep..." >> "$LOG"
/usr/bin/perl -e 'alarm(1200); exec @ARGV' -- \
    /usr/bin/python3 scripts/rt_gap_sweep.py >> "$LOG" 2>&1 \
    || echo "  WARNING: RT sweep failed" >> "$LOG"

if ! /usr/bin/git diff --quiet data.json 2>/dev/null; then
    echo "  Pushing RT stamps to GitHub..." >> "$LOG"
    if NRW_ALLOW_DATA_COMMIT=1 /usr/bin/git commit data.json -m "Local RT stamp — APPROVED: DELETE" >> "$LOG" 2>&1; then
        if /usr/bin/git push origin main >> "$LOG" 2>&1; then
            echo "  Pushed successfully" >> "$LOG"
        else
            echo "  WARNING: Push failed — CI will carry it tomorrow" >> "$LOG"
        fi
    else
        echo "  WARNING: Commit failed" >> "$LOG"
    fi
else
    echo "  No RT stamps to push" >> "$LOG"
fi

# Step 3b: Back up the hand-curated curation banks to B2.
# admin/approved_capsules.json is git-tracked (CI reads it for house-style
# generation), but B2 stays as belt-and-suspenders; taste_profile_pullquotes
# is still local-only. Uploads only when file content changed (sha256 check),
# so most cycles are a no-op.
echo "Backing up curation banks..." >> "$LOG"
/opt/homebrew/bin/python3.11 scripts/backup_curation_banks.py >> "$LOG" 2>&1 \
    || echo "  WARNING: curation bank backup failed" >> "$LOG"

# Only create sentinel if we have today's CI data
CI_DATE=$(/usr/bin/python3 -c "import json; print(json.load(open('metrics/run_diagnostics.json'))['timestamp'][:10])" 2>/dev/null)
TODAY=$(date +%Y-%m-%d)
if [ "$CI_DATE" = "$TODAY" ]; then
    # Steps 4+5: Curation caches (pull quotes + capsule drafts).
    # These now run in CI (daily-check.yml) — off this battery-dependent Mac —
    # and are shipped back as the "curation-caches" artifact. We just download
    # and merge them in (merge is add-new-only, so it never clobbers the user's
    # `selected` picks or curated capsules). If the artifact can't be fetched,
    # we FALL BACK to generating locally so curation is never left empty.
    echo "Fetching curation caches from CI artifact..." >> "$LOG"
    ARTIFACT_OK=false
    TMP_ART="$PROJECT_DIR/cache/_ci_artifact"
    rm -rf "$TMP_ART" && mkdir -p "$TMP_ART"
    # Find the newest run that actually HAS a non-expired curation-caches
    # artifact — NOT the newest "successful" run. The daily workflow uploads
    # this artifact before the commit/push step, so a run can ship a perfectly
    # good artifact yet still be marked "failure" on a data.json push conflict
    # (which happens routinely). Filtering on run success would skip those and
    # needlessly fall back to local generation.
    RUN_ID=$(gh api "repos/hadrianbelove-stack/nrw-production/actions/artifacts?name=curation-caches&per_page=10" \
        -q 'first(.artifacts[] | select(.expired==false)).workflow_run.id' 2>>"$LOG")
    if [ -n "$RUN_ID" ] && gh run download "$RUN_ID" \
            --repo hadrianbelove-stack/nrw-production \
            --name curation-caches --dir "$TMP_ART" >> "$LOG" 2>&1; then
        if /usr/bin/python3 scripts/merge_curation_caches.py "$TMP_ART" >> "$LOG" 2>&1; then
            ARTIFACT_OK=true
            echo "  Curation caches merged from CI run $RUN_ID" >> "$LOG"
        fi
    fi
    rm -rf "$TMP_ART"

    if [ "$ARTIFACT_OK" = false ]; then
        # Fallback: CI artifact unavailable — generate the whole curate window
        # locally (the old path). alarm(3600) hard-kills a hung run.
        echo "  Artifact unavailable — falling back to local generation" >> "$LOG"
        echo "Scraping pull quotes for new arrivals (Claude/Max)..." >> "$LOG"
        NRW_QUOTES_BACKEND=claude /usr/bin/perl -e 'alarm(3600); exec @ARGV' -- \
            /usr/bin/python3 scripts/batch_pull_quotes.py >> "$LOG" 2>&1 \
            || echo "  WARNING: pull quotes exited non-zero (timeout or error)" >> "$LOG"
        echo "Pre-generating capsules for new arrivals (Claude/Max)..." >> "$LOG"
        NRW_CAPSULE_BACKEND=claude /usr/bin/perl -e 'alarm(3600); exec @ARGV' -- \
            /usr/bin/python3 scripts/write_capsule.py --batch --days 7 --variants 2 >> "$LOG" 2>&1 \
            || echo "  WARNING: capsule batch exited non-zero (timeout or error)" >> "$LOG"
    else
        # CI's Gemini capsule pre-gen is gated OFF (ENABLE_GEMINI_CURATION) to
        # stop Gemini spend, so the merged artifact no longer carries fresh
        # capsules. Generate them locally with Claude on the Max plan (~$0)
        # instead — DETACHED (nohup) so the ~4-min-per-film run can't trip
        # launchd's 30-min ExitTimeOut. Fills cache/capsule_cache.json for the
        # morning /curate flow, then recomputes Buzz once notability exists.
        if pgrep -f "write_capsule.py --batch" >/dev/null 2>&1 \
                || pgrep -f "batch_pull_quotes.py" >/dev/null 2>&1; then
            echo "  Local Claude curation pre-gen already running; skipping" >> "$LOG"
        else
            echo "  Starting local Claude curation pre-gen (quotes+capsules, detached, Claude/Max)..." >> "$LOG"
            NRW_QUOTES_BACKEND=claude NRW_CAPSULE_BACKEND=claude nohup /bin/bash -c \
                '/usr/bin/python3 scripts/batch_pull_quotes.py --days 7 && /usr/bin/python3 scripts/write_capsule.py --batch --days 7 --variants 2 && /usr/bin/python3 scripts/inject_notability.py' \
                >> "$CAPSULE_LOG" 2>&1 &
            disown
        fi
    fi
    # Buzz (Selects guesser) — recompute into data.json now that the capsule
    # research has produced notability facts.
    echo "Computing Buzz (Selects guesser)..." >> "$LOG"
    /usr/bin/python3 scripts/inject_notability.py >> "$LOG" 2>&1 \
        || echo "  WARNING: Buzz injection exited non-zero" >> "$LOG"
    echo "  Curation caches ready" >> "$LOG"

    touch "$SENTINEL"
    echo "  CI data is current ($CI_DATE) — sentinel created, done for today" >> "$LOG"
else
    echo "  CI data is stale ($CI_DATE) — will retry next cycle" >> "$LOG"
fi
echo "=== Done: $(date) ===" >> "$LOG"
