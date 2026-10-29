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

# Log it AND pop a Mac notification, so a stuck job can't sit unnoticed in
# the log for days (the Oct 26-29 2026 trailer jam went unseen for 3 days).
alert() {
    echo "  ALERT: $1" >> "$LOG"
    /usr/bin/osascript -e "display notification \"$1\" with title \"NRW nightly job\"" >/dev/null 2>&1 || true
}

data_json_ok() {
    /usr/bin/python3 -c "import json; json.load(open('data.json'))" 2>/dev/null
}

# One run at a time. launchd fires every 30 min and runs can also be started
# by hand; two overlapping runs both stash, pull, stamp and push data.json
# (a manual run and the 30-min retry overlapped on Oct 29 2026).
LOCK_DIR="/var/tmp/nrw_daily.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    OTHER_PID=$(cat "$LOCK_DIR/pid" 2>/dev/null)
    if [ -n "$OTHER_PID" ] && kill -0 "$OTHER_PID" 2>/dev/null; then
        echo "=== NRW Local Daily: $(date) — another run (pid $OTHER_PID) is still going; skipping ===" >> "$LOG"
        exit 0
    fi
    echo "=== NRW Local Daily: $(date) — clearing stale lock (pid ${OTHER_PID:-unknown} is gone) ===" >> "$LOG"
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" || exit 1
fi
echo $$ > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

echo "" >> "$LOG"
echo "=== NRW Local Daily: $(date) ===" >> "$LOG"

cd "$PROJECT_DIR" || { echo "ERROR: Cannot cd to $PROJECT_DIR" >> "$LOG"; exit 1; }

# Never run on top of a half-finished rebase left by an earlier run or a
# manual session: it strands data.json with conflict markers and every later
# pull fails. Aborting it here could wipe someone's uncommitted work, so stop
# and leave it for a person.
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    alert "A git rebase is stuck in nrw-production. Skipping tonight's trailer run until it is resolved."
    exit 1
fi

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

PULL_OK=true
if ! /usr/bin/git pull --rebase origin main >> "$LOG" 2>&1; then
    PULL_OK=false
    echo "WARNING: git pull failed" >> "$LOG"
    # Back out THIS run's half-finished rebase (local changes are stashed, so
    # the abort only rewinds to the pre-pull commit) instead of leaving it.
    if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
        /usr/bin/git rebase --abort >> "$LOG" 2>&1
        echo "  Aborted this run's failed rebase" >> "$LOG"
    fi
    alert "Could not sync with GitHub. Trailers still upload, but stamping is skipped this run."
fi

if [ "$STASHED" = true ]; then
    /usr/bin/git stash pop >> "$LOG" 2>&1 || echo "WARNING: stash pop had conflicts — resolve manually" >> "$LOG"
    echo "  Restored local changes" >> "$LOG"
fi

if ! data_json_ok; then
    alert "data.json is not valid JSON after the pull. Skipping this run."
    exit 1
fi

# Step 2a: Refresh YouTube cookies from Safari (Aqua session has keychain access)
# Use python3.11 -m yt_dlp, NOT the /opt/homebrew/bin/yt-dlp CLI: only the
# python3.11 binary holds the macOS Full Disk Access grant needed to read
# Safari's Cookies.binarycookies. The CLI wrapper gets "Operation not permitted"
# and the cookie file goes stale, which 403s every DASH download.
echo "Refreshing YouTube cookies..." >> "$LOG"
/opt/homebrew/bin/python3.11 -m yt_dlp --cookies-from-browser safari \
    --cookies cache/yt_cookies.txt --skip-download \
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ' >> "$LOG" 2>&1 \
    && echo "  Cookies refreshed" >> "$LOG" \
    || echo "  Cookie refresh FAILED (Full Disk Access?) — using stale file, DASH will 403" >> "$LOG"

# Step 2a3: Trailer gap sweep — find YouTube trailers CI missed.
# CI's waterfall is Playwright-only since the Gemini switch-off (Aug 2026);
# this re-runs the misses with Claude on the Max plan (~$0) from this Mac.
# Runs BEFORE hosting so a found trailer is downloaded, uploaded to B2, and
# committed by the stamp step the same night. Capped (10/run, 3 attempts/film,
# 20h cooldown) so most days it's seconds.
if [ "$PULL_OK" = true ]; then
    echo "Trailer gap sweep..." >> "$LOG"
    NRW_YOUTUBE_BACKEND=claude /usr/bin/perl -e 'alarm(2400); exec @ARGV' -- \
        /usr/bin/python3 scripts/trailer_gap_sweep.py >> "$LOG" 2>&1 \
        || echo "  WARNING: trailer sweep failed" >> "$LOG"
else
    echo "Trailer gap sweep skipped (not synced with GitHub)" >> "$LOG"
fi

# Step 2b: Upload new trailers to B2 (download from YouTube + upload, no data.json writes)
echo "Hosting new trailers..." >> "$LOG"
/usr/bin/perl -e 'alarm(3600); exec @ARGV' -- \
    /opt/homebrew/bin/python3.11 scripts/trailer_pipeline.py host >> "$LOG" 2>&1

# Step 3: Stamp hosted trailer URLs into data.json and push to GitHub
# This eliminates the ~19-hour gap where trailers show as YouTube fallbacks.
# Safe: CI finishes 5+ hours before this runs. Stamp is idempotent.
if [ "$PULL_OK" = true ]; then
    echo "Stamping hosted trailer URLs..." >> "$LOG"
    /opt/homebrew/bin/python3.11 scripts/trailer_pipeline.py stamp >> "$LOG" 2>&1
else
    echo "Trailer stamping skipped (not synced with GitHub)" >> "$LOG"
fi

if [ "$PULL_OK" = true ] && ! /usr/bin/git diff --quiet data.json 2>/dev/null && ! data_json_ok; then
    alert "data.json broke during trailer stamping. NOT committing it."
elif [ "$PULL_OK" = true ] && ! /usr/bin/git diff --quiet data.json 2>/dev/null; then
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
if [ "$PULL_OK" = true ]; then
    echo "RT-link gap sweep..." >> "$LOG"
    /usr/bin/perl -e 'alarm(1200); exec @ARGV' -- \
        /usr/bin/python3 scripts/rt_gap_sweep.py >> "$LOG" 2>&1 \
        || echo "  WARNING: RT sweep failed" >> "$LOG"
else
    echo "RT-link gap sweep skipped (not synced with GitHub)" >> "$LOG"
fi

if [ "$PULL_OK" = true ] && ! /usr/bin/git diff --quiet data.json 2>/dev/null && ! data_json_ok; then
    alert "data.json broke during the RT sweep. NOT committing it."
elif [ "$PULL_OK" = true ] && ! /usr/bin/git diff --quiet data.json 2>/dev/null; then
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
