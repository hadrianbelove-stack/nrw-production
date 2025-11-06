# Current Workflow Status - Nov 3rd, 2025

## Summary
Both workflows are failing. The YouTube OAuth flow on this local machine is not completing properly, preventing token regeneration.

---

## Workflow Failures

### 1. YouTube Playlist Workflow ❌

**Latest Run:** 2025-11-03 10:13:28 UTC
**Error:** `base64: invalid input`
**Location:** Restore YouTube credentials step

**Root Cause:**
The `YOUTUBE_TOKEN` secret in GitHub is corrupted or invalid. When the workflow tries to base64-decode it, it fails immediately.

**What's NOT the issue:**
- ❌ Newline stripping - You already correctly removed `tr -d '\n'` in commit 61d54ea
- ❌ Workflow configuration - The workflow file is correct

**What IS the issue:**
- ✅ The GitHub secret `YOUTUBE_TOKEN` contains invalid base64 data
- ✅ Need to regenerate token and update the secret

**Problem:** Local OAuth authentication is not completing/saving token.pickle file properly.

---

### 2. Daily Update Workflow ❌

**Latest Run:** 2025-11-03 09:21:28 UTC
**Error:** `No recent movies found - automation may not be discovering new releases`
**Location:** Data quality validation step

**Root Cause:**
The workflow has been failing for 8 days straight, creating a cascading failure:
1. Daily update fails → No new data generated → data.json stays stale → Next day fails validation

**Current State:**
- `data.json` last generated: **2025-10-26 20:44** (8 days ago)
- Latest movie digital_date: **2025-10-26**
- Movies in last 7 days: **0** (validation requires > 0)
- Total movies: 317

**Why It's Failing:**
The `daily_orchestrator.py` validates that there are movies with `digital_date` in the last 7 days.
Since data.json hasn't been regenerated since Oct 26, there are NO movies dated Oct 27-Nov 3.

**This is a Catch-22:**
- Workflow fails validation because data is old
- Data is old because workflow keeps failing
- Need to break the cycle by running a successful update

**Next Steps:**
1. Check why previous daily updates failed (before validation was the issue)
2. Run `python3 generate_data.py --full` locally to get fresh data
3. Commit the updated data.json
4. This will break the cycle and allow daily updates to succeed again

---

## Local OAuth Issue

**Problem:** YouTube playlist manager auth flow not completing.

**Symptoms:**
- `python3 youtube_playlist_manager.py auth` opens browser and completes OAuth
- Shows "✅ Authentication complete!" message
- But `youtube_credentials/token.pickle` file is NOT created
- Log shows "🔐 Starting OAuth authorization flow..." but never "✅ Credentials saved"

**Investigation Needed:**
1. Check if OAuth flow is actually completing successfully
2. Verify file write permissions in youtube_credentials/
3. Check if there's an exception being swallowed
4. Try running with more verbose logging

---

## Immediate Actions Required

### Fix YouTube Workflow
You'll need to regenerate the token manually on a machine where OAuth works:

```bash
# On a working machine:
1. python3 youtube_playlist_manager.py auth
   # Complete the browser OAuth flow

2. Verify token was created:
   ls -la youtube_credentials/token.pickle

3. Test the token works:
   python3 -c "import pickle; pickle.load(open('youtube_credentials/token.pickle', 'rb'))"

4. Encode for GitHub (NO tr -d!):
   base64 -i youtube_credentials/token.pickle -o /tmp/youtube_token.txt

5. Update GitHub secret:
   gh secret set YOUTUBE_TOKEN < /tmp/youtube_token.txt

6. Test workflow:
   gh workflow run youtube-playlists.yml
```

### Fix Daily Update Workflow
```bash
# Check recent movies
python3 -c "
import json
with open('data.json') as f:
    data = json.load(f)
    recent = [m for m in data['movies'] if m.get('digital_date', '') >= '2025-10-01']
    print(f'Recent movies (since Oct 1): {len(recent)}')
    if recent:
        print(f'Latest digital_date: {max(m.get(\"digital_date\", \"\") for m in recent)}')
"

# Check tracking database
python3 -c "
import json
with open('movie_tracking.json') as f:
    db = json.load(f)
    total = len(db)
    tracked = sum(1 for m in db.values() if m.get('status') == 'tracked')
    print(f'Total in DB: {total}, Tracked: {tracked}')
"
```

---

## Workflow Status Table

| Workflow | Status | Last Success | Issue | Action Required |
|----------|--------|--------------|-------|-----------------|
| YouTube Playlists | ❌ Failing | Oct 22 | Invalid token secret | Regenerate token manually |
| Daily Update | ❌ Failing | Unknown | No recent movies found | Debug movie discovery |

---

## Notes

- The `tr -d '\n'` was correctly removed - don't re-add it
- Base64 strings CAN contain newlines as part of valid encoding
- The OAuth issue on this machine is separate from the workflow issue
- Once you get a valid token on another machine, the workflow should work

---

**Last Updated:** 2025-11-03 16:25 PST
**Status:** Awaiting manual token regeneration on working OAuth machine
