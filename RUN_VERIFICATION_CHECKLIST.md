# RUN_VERIFICATION_CHECKLIST.md

## IMMEDIATE ACTION REQUIRED

**Current Situation:**
- PlaywrightManager fix (commit fb271c2d) exists in code ✅
- Test scripts work perfectly ✅
- Production has NEVER run the new code ❌
- All previous runs used cached Python modules from BEFORE the fix ❌
- Multiple stale processes running (PID 68945 generate_data.py, Playwright drivers)

**The Problem:**
Python cached the OLD scraper code in memory. Even though the fix is committed, running processes continue using old modules. Bytecode cache (`__pycache__/*.pyc`) also contains old compiled code.

**The Solution:**
1. Kill all stale processes (force fresh module loading)
2. Clear Python bytecode cache (remove old .pyc files)
3. Run fresh generate_data.py (will load NEW code with PlaywrightManager)

**Expected Outcome:**
- PlaywrightManager messages will appear in logs (proving fix is active)
- Zero asyncio errors
- Scraper success rates jump from 0% to >50%

**Time Required:** ~30 minutes total
- 5 minutes: Process cleanup
- 15-20 minutes: Fresh generate_data.py run
- 5 minutes: Verification

---

## Quick Command Reference

**For users who want to execute immediately:**

```bash
# Prerequisites: Change to repository root
cd /path/to/nrw-production  # Replace with your actual repository path
# Or use: REPO_DIR="/path/to/nrw-production"; cd "$REPO_DIR"

# 1. Kill stale processes
# First, discover and kill generate_data.py processes
pgrep -fl 'generate_data.py'  # List processes first
pkill -f -TERM 'generate_data.py'  # Graceful termination

# Kill Playwright driver processes
pkill -f 'playwright/driver'  # More robust than ps|grep|awk|xargs

# WARNING: Always verify PIDs before killing. Never copy commands with specific PIDs.
# Target Playwright-driven Chromium processes only
pgrep -f 'playwright/driver' | while read driver_pid; do
  if [ -n "$driver_pid" ]; then
    pgrep -P "$driver_pid" | while read child_pid; do
      [ -n "$child_pid" ] && kill "$child_pid"
    done
  fi
done
pkill -f 'playwright/driver'  # Kill Playwright drivers

# Caution: Avoid terminating normal browser sessions

# 2. Clear Python cache
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -type f -delete

# 3. Verify code is current
git log -1 --oneline  # Should show fb271c2d or later
ls -la playwright_manager.py  # Should exist

# 4. Run fresh verification
export TMDB_API_KEY="<your_tmdb_api_key>"
export WATCHMODE_API_KEY="<your_watchmode_api_key>"
export ADMIN_USERNAME="<your_admin_username>"
export ADMIN_PASSWORD="<your_admin_password>"

# Note: Load from .env file using python-dotenv or source .env

python3 generate_data.py --full 2>&1 | tee verify_playwright_fix_$(date +%Y%m%d_%H%M%S).log

# 5. Watch for success indicators (in another terminal)
tail -f verify_playwright_fix_*.log | grep -E "PlaywrightManager|asyncio"
```

**Success Indicators:**
- Within 30 seconds: See "[PlaywrightManager] Initializing shared Playwright instance..."
- Within 1 minute: See "[PlaywrightManager] No event loop detected - safe to proceed"
- Throughout run: NO "Browser initialization failed" errors
- At end: Platform scraper success rate >50%, Agent scraper >30%

**If PlaywrightManager messages DON'T appear within 2 minutes:**
- Stop the process (Ctrl+C)
- Old code is still being used
- Follow detailed troubleshooting in PROCESS_CLEANUP_LOG.md

---

## Purpose
Step-by-step checklist to verify the async fix and scraper improvements are working correctly in production.

## Pre-Flight Checks

**Note:** If you followed the Quick Command Reference above, you've already completed steps 1-3. Skip to step 4 (Run Full Data Generation).

**If you want detailed explanations and troubleshooting:** Follow the comprehensive guide in PROCESS_CLEANUP_LOG.md.

### 1. Verify Code is Up to Date
```bash
# Check current commit
git log -1 --oneline
# Should show: fb271c2d Fix Playwright asyncio event loop conflict

# Check for uncommitted changes
git status
# Should show: clean working tree (or only documentation changes)

# Verify PlaywrightManager exists
ls -la playwright_manager.py
# Should exist and be recently modified
```

### 2. Clear Caches and Stale Processes
```bash
# Kill any running generate_data.py processes
ps aux | grep generate_data.py | grep -v grep
# If any found, kill them: kill <PID>

# Kill any stale Playwright driver processes
ps aux | grep playwright | grep -v grep
# If any found, kill them: kill <PID>

# Clear Python bytecode cache (if exists)
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Optional: Clear agent scraper cache to force fresh scraping
rm -f cache/agent_links_cache.json
```

### 3. Verify Playwright Installation
```bash
# Check Playwright is installed
python3 -c "from playwright.sync_api import sync_playwright; print('✅ Playwright installed')"

# Check browsers are installed
python3 -m playwright install --help
# If browsers not installed: python3 -m playwright install chromium
```

### 4. Verify PlaywrightManager Import Path
```bash
# Confirm PlaywrightManager import path resolves correctly
python3 -c "import playwright_manager,inspect; print(playwright_manager.__file__)"
# Expected: Shows path to playwright_manager.py in current directory
```

## Verification Run

### 5. Run Full Data Generation
```bash
# Set environment variables
export TMDB_API_KEY="<your_tmdb_api_key>"
export WATCHMODE_API_KEY="<your_watchmode_api_key>"
export ADMIN_USERNAME="<your_admin_username>"
export ADMIN_PASSWORD="<your_admin_password>"

# Run full regeneration with logging
python3 generate_data.py --full 2>&1 | tee verify_playwright_fix_$(date +%Y%m%d_%H%M%S).log

# This will take 10-20 minutes depending on how many movies need scraping
```

### Real-Time Monitoring (Critical)

**Open a second terminal while generate_data.py is running:**

```bash
# Terminal 2: Watch for PlaywrightManager messages
tail -f verify_playwright_fix_*.log | grep "PlaywrightManager"
```

**Within 30 seconds, you MUST see:**
```
[PlaywrightManager] Initializing shared Playwright instance...
[PlaywrightManager] No event loop detected - safe to proceed
[PlaywrightManager] Playwright instance created
```

**If you see these: ✅ SUCCESS! The fix is working. Let it continue.**

**If you DON'T see these within 2 minutes:**
```bash
# Terminal 1: Stop the process
Ctrl+C

# Check if PlaywrightManager messages exist at all
grep -c "PlaywrightManager" verify_playwright_fix_*.log
# If returns 0: Old code is still running
```

**Troubleshooting if messages don't appear:**
1. Check for other Python processes: `ps aux | grep python`
2. Kill targeted processes:
   ```bash
   # First try graceful termination
   pkill -f -TERM 'generate_data.py'
   pkill -f -TERM 'playwright/driver'

   # If stubborn processes remain, escalate to -KILL
   pgrep -fl 'generate_data.py|playwright/driver'  # verify before killing
   pkill -f -KILL 'generate_data.py'
   pkill -f -KILL 'playwright/driver'
   ```
3. Clear cache again: `find . -name "__pycache__" -exec rm -rf {} +`
4. Restart terminal application
5. Try running from a completely new terminal session
6. As last resort: Restart computer

### 6. Check Log for PlaywrightManager Messages
```bash
# Check if PlaywrightManager was used
grep "PlaywrightManager" verify_playwright_fix_*.log

# Expected output:
# [PlaywrightManager] Initializing shared Playwright instance...
# [PlaywrightManager] No event loop detected - safe to proceed
# [PlaywrightManager] Playwright instance created

# If NO output: The old code is still running! Restart process and try again.
```

### 7. Check for Asyncio Errors
```bash
# Count asyncio errors (should be 0)
grep -c "Browser initialization failed" verify_playwright_fix_*.log
grep -c "asyncio loop" verify_playwright_fix_*.log

# Expected: Both should return 0
# If > 0: The async fix is not working, investigate further
```

### 8. Check Scraper Success Rates
```bash
# Extract platform scraper statistics
grep -A 10 "Platform Scraper Statistics" verify_playwright_fix_*.log

# Expected:
# Platform scraper attempts: > 0
# Platform scraper successes: > 0
# Platform scraper success rate: > 50%

# Extract agent scraper statistics
grep -A 10 "Agent Scraper Usage" verify_playwright_fix_*.log

# Expected:
# Agent attempts: > 0
# Agent successes: > 0
# Agent success rate: > 30%
```

### 9. Verify Data Quality
```bash
# Count Google fallbacks (should be 0)
grep -c "google.com/search" data.json

# Expected: 0
# If > 0: Google fallback removal not working

# Check for placeholder ASINs
grep -c "B0FMPYFP9W\|B0FNDR5BW5\|B0F935J2FR" data.json

# Expected: 0
# If > 0: Placeholder ASINs still present, need cleanup

# Count unique Amazon ASINs and check for duplicates
grep -o 'amazon.com/gp/video/detail/[^/"]*' data.json | \
  sed 's|.*detail/||' | sort | uniq -c | sort -rn | head -10

# Expected: No ASIN appearing more than 3-4 times
# If any ASIN appears 5+ times: Likely a placeholder, investigate
```

## Test Agent Scraper Improvements

### 10. Run Agent Scraper Tests
```bash
# Run agent scraper test suite
python3 test_agent_scraper_improvements.py 2>&1 | tee test_agent_results_$(date +%Y%m%d_%H%M%S).log

# Expected: At least 4/6 tests PASS (>70% success rate)
```

### 11. Analyze Test Results
```bash
# Check overall success rate
grep "Overall success rate" test_agent_results_*.log

# Check per-platform results
grep -A 20 "PER-PLATFORM RESULTS" test_agent_results_*.log

# Expected:
# Netflix: >50% success rate
# Disney+: >50% success rate
# Max: >50% success rate
# Hulu: >50% success rate
```

## Documentation

### 12. Document Results
```bash
# Update ASYNC_FIX_VERIFICATION.md with actual results
# Update SCRAPER_EFFECTIVENESS_ANALYSIS.md with success rates
# Update AMAZON_ASIN_CLEANUP.md with agent scraper section
# Update DAILY_CONTEXT.md with session summary
```

### 13. Commit and Push
```bash
# Stage all changes
git add -A

# Commit documentation
git commit -m "Document async fix verification and scraper effectiveness analysis

- Added ASYNC_FIX_VERIFICATION.md with verification steps and results
- Added SCRAPER_EFFECTIVENESS_ANALYSIS.md with comprehensive scraper analysis
- Updated AMAZON_ASIN_CLEANUP.md with agent scraper improvements
- Updated DAILY_CONTEXT.md with session summary
- Added RUN_VERIFICATION_CHECKLIST.md for future verification runs

Results:
- Platform scraper: X% success rate (was 0%)
- Agent scraper: Y% success rate (was 0%)
- Google fallbacks: 0 (was 42)
- Asyncio errors: 0 (was 327+)
"

# Push all commits to GitHub
git push origin main

# Verify push succeeded
git log origin/main..HEAD --oneline
# Should show: nothing (all commits pushed)
```

## After Successful Verification

**Once all success criteria are met:**

### 1. Run Agent Scraper Tests
```bash
python3 test_agent_scraper_improvements.py 2>&1 | tee test_agent_results_$(date +%Y%m%d_%H%M%S).log
```

**Expected:** At least 4/6 tests PASS (>70% success rate)

### 2. Document Results

**Update documentation files:**
- ASYNC_FIX_VERIFICATION.md: Add actual success rates
- SCRAPER_EFFECTIVENESS_ANALYSIS.md: Add before/after comparison
- AMAZON_ASIN_CLEANUP.md: Add agent scraper improvements section
- DAILY_CONTEXT.md: Add session summary

**Create verification summary:**
```bash
cat > VERIFICATION_RESULTS_$(date +%Y%m%d).md << 'EOF'
# Verification Results - [DATE]

## Summary
- PlaywrightManager fix: ✅ VERIFIED WORKING
- Platform scraper: 0% → X% success rate
- Agent scraper: 0% → Y% success rate
- Google fallbacks: 42 → 0 movies
- Asyncio errors: 327+ → 0

## Evidence
- Log file: verify_playwright_fix_TIMESTAMP.log
- PlaywrightManager messages: [count] occurrences
- Asyncio errors: 0 occurrences
- Test results: test_agent_results_TIMESTAMP.log

## Conclusion
The Playwright async/sync fix is working correctly. All scrapers now use the shared PlaywrightManager singleton, eliminating event loop conflicts.
EOF
```

### 3. Commit and Push

**Stage all documentation:**
```bash
git add ASYNC_FIX_VERIFICATION.md
git add SCRAPER_EFFECTIVENESS_ANALYSIS.md
git add AMAZON_ASIN_CLEANUP.md
git add DAILY_CONTEXT.md
git add PROCESS_CLEANUP_LOG.md
git add VERIFICATION_RESULTS_*.md
git add RUN_VERIFICATION_CHECKLIST.md
```

**Commit with detailed message:**
```bash
git commit -m "Verify Playwright async fix and document scraper improvements

- Verified PlaywrightManager fix working in production
- Platform scraper: 0% → X% success rate
- Agent scraper: 0% → Y% success rate
- Google fallbacks eliminated: 42 → 0 movies
- Asyncio errors resolved: 327+ → 0
- Documented verification process in PROCESS_CLEANUP_LOG.md
- Updated all analysis and effectiveness documentation

The root cause was cached Python modules from before the fix.
Killing processes and clearing __pycache__ forced fresh module loading.
PlaywrightManager singleton now successfully prevents event loop conflicts.
"
```

**Push to GitHub:**
```bash
git push origin main
```

**Verify push succeeded:**
```bash
git log origin/main..HEAD --oneline
# Should show: nothing (all commits pushed)
```

### 4. Archive Session

**Create diary entry:**
```bash
cp DAILY_CONTEXT.md diary/2025-10-27.md
```

**Update DAILY_CONTEXT.md for next session:**
- Move completed items to "Previous Sessions" section
- Add new "Current Session" section
- Update "Next Priorities" based on results

### 5. Celebrate! 🎉

You've successfully:
- ✅ Fixed the critical Playwright async/sync conflict
- ✅ Improved Amazon scraper validation (position filtering, flexible year, etc.)
- ✅ Applied same improvements to agent scraper (Netflix, Disney+, Max, Hulu)
- ✅ Eliminated all Google fallback URLs
- ✅ Increased scraper success rates from 0% to >50%
- ✅ Documented everything thoroughly

The scrapers are now working correctly and the site will show real deep links instead of Google searches!

## Success Criteria Summary

### ✅ All Checks Must Pass

- [ ] PlaywrightManager messages appear in logs
- [ ] Zero "Browser initialization failed" errors
- [ ] Zero "asyncio loop" errors
- [ ] Platform scraper success rate > 50%
- [ ] Agent scraper success rate > 30%
- [ ] Zero Google fallback URLs in data.json
- [ ] No placeholder ASINs appearing 5+ times
- [ ] test_agent_scraper_improvements.py: >70% pass rate
- [ ] All commits pushed to GitHub
- [ ] Documentation complete and committed

### If Any Check Fails

**PlaywrightManager messages missing:**
- Old code still running
- Restart Python process
- Clear __pycache__ directories
- Verify commit fb271c2d is active: `git log -1`

**Asyncio errors still occurring:**
- PlaywrightManager not being used correctly
- Check all scrapers import and use manager
- Add more diagnostics to pinpoint where loop is created
- Verify no direct sync_playwright().start() calls

**Low scraper success rates (<50%):**
- Platform selectors may be outdated
- Validation logic may be too strict
- Check for rate limiting or captchas
- Review failed searches in logs

**Google fallbacks still present:**
- Google fallback removal not applied
- Check generate_data.py for any remaining fallback generation
- Verify commit 9b3c2ac is active

**Placeholder ASINs still present:**
- Run cleanup scripts:
  - `python3 cleanup_placeholder_asins.py`
  - `python3 clear_cache_for_placeholder_asins.py`
- Add new placeholder to constants.py PLACEHOLDER_ASINS list
- Re-run generate_data.py --full

## Timeline Reference

**Commits (chronological):**
1. 9b3c2ac (epoch 1761508166) - Google fallback removal
2. 7f992e44 (epoch 1761508269) - YouTube workflow fix
3. fb271c2d (epoch 1761522782) - PlaywrightManager fix

**Logs:**
- generate_data_no_fallbacks.log: Started 2025-10-26 13:06:25 (BEFORE fb271c2d)
- verify_playwright_fix_*.log: To be created AFTER fb271c2d (should show PlaywrightManager)

**Key Insight:**
Old logs show failures because they were created before the fix. New runs should show success.