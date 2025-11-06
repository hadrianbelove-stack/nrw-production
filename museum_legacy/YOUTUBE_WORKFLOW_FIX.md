# YouTube Workflow Pickle Error - Fixed

## Problem
The YouTube playlist workflow was failing with:
```
_pickle.UnpicklingError: Memo value not found at index 148
```

## Root Cause
The workflow was using `tr -d '\n\r\t '` to strip whitespace from the base64-encoded token, but **base64 strings can contain newlines** as part of valid encoding. Stripping these newlines corrupted the pickle file when it was decoded.

## Solution

### 1. Added Error Handling in Python Code
**File**: `youtube_playlist_manager.py`

Added try/except to catch corrupted pickle files and automatically regenerate:
```python
if token_path.exists():
    try:
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    except (pickle.UnpicklingError, EOFError, ValueError) as e:
        self.logger.warning(f"⚠️  Corrupted token file: {e}")
        self.logger.info("🗑️  Removing corrupted token.pickle...")
        token_path.unlink()
        creds = None
```

### 2. Fixed Workflow Base64 Decoding
**File**: `.github/workflows/youtube-playlists.yml`

**Before** (incorrect):
```yaml
echo "$YOUTUBE_TOKEN" | tr -d '\n\r\t ' | base64 -d > youtube_credentials/token.pickle
```

**After** (correct):
```yaml
echo "$YOUTUBE_TOKEN" | base64 -d > youtube_credentials/token.pickle
```

### 3. Created Helper Script
**File**: `scripts/encode_youtube_token.sh`

Properly encodes the local token.pickle for GitHub Secrets:
```bash
#!/bin/bash
base64 < youtube_credentials/token.pickle
```

## How to Update GitHub Secret

1. Run the encoder script locally:
   ```bash
   ./scripts/encode_youtube_token.sh
   ```

2. Copy the ENTIRE base64 output (including newlines)

3. Go to GitHub Settings → Secrets → Actions:
   https://github.com/hadrianbelove-stack/nrw-production/settings/secrets/actions

4. Edit secret `YOUTUBE_TOKEN`

5. Paste the base64 string and save

## Current Base64 Token
```
gASVCAQAAAAAAACMGWdvb2dsZS5vYXV0aDIuY3JlZGVudGlhbHOUjAtDcmVkZW50aWFsc5STlCmBlH2UKIwFdG9rZW6UjP55YTI5LmEwQVRpNksyc2lBQV8ybEZYX25YaEs1T1pVNTYtV2dfbVhkaGtLVEpUekFHdVl5c25Gb1d6TW0xRzhjMmZXQll6VmY5dEtTRFdSajlRZ2YzYlYwelJKSXhrTTZkOXZMaGhaLWtSVHlRRU53c3hHZXJndmdVVUdveEdmZnlWdUlLa1B6Um9naVJkSTg5cU5vMF83SVg4OTZJNDZUYUZrbVRfT2RTOWJBUnprbk9CNTBjZmNRbFdFWmtNa1g2WEhsajNVMFptT1ZTQkphQ2dZS0FXd1NBUklTRlFIR1gyTWlFdS1zaGtveF9MSDZMWXVXaGJ3SzFnMDIwN5SMBmV4cGlyeZSMCGRhdGV0aW1llIwIZGF0ZXRpbWWUk5RDCgfpChcGEzIGe9iUhZRSlIwOX3JlZnJlc2hfdG9rZW6UjGcxLy8wNmVLSURHV2FYQWUwQ2dZSUFSQUFHQVlTTndGLUw5SXJ6WTVuMHhDdVpnSDA5YjlnaWxpMVE0NmNNb3hOeWExd1AxQXd0RUxxTXlxc0xLSDd4MTRTRnZjV3oxRThrWEtjSjY4lIwJX2lkX3Rva2VulE6MB19zY29wZXOUXZSMMWh0dHBzOi8vd3d3Lmdvb2dsZWFwaXMuY29tL2F1dGgveW91dHViZS5mb3JjZS1zc2yUYYwPX2RlZmF1bHRfc2NvcGVzlE6MD19ncmFudGVkX3Njb3Blc5RdlIwxaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vYXV0aC95b3V0dWJlLmZvcmNlLXNzbJRhjApfdG9rZW5fdXJplIwjaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW6UjApfY2xpZW50X2lklIxGOTY3MTY2ODE2NS02NXFlOHI1dTZodDVwcHBjY3NwNGU2ajhvN3BncTM4NS5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbZSMDl9jbGllbnRfc2VjcmV0lIwjR09DU1BYLWJNQkZva1NxWXdGS25rMVViSkxTZ0Z1V2NaV1qUjBFfcXVvdGFfcHJvamVjdF9pZJROjAtfcmFwdF90b2tlbpROjBZfZW5hYmxlX3JlYXV0aF9yZWZyZXNolImMD190cnVzdF9ib3VuZGFyeZROjBBfdW5pdmVyc2VfZG9tYWlulIwOZ29vZ2xlYXBpcy5jb22UjA5fY3JlZF9maWxlX3BhdGiUTowZX3VzZV9ub25fYmxvY2tpbmdfcmVmcmVzaJSJjAhfYWNjb3VudJSMAJR1Yi4=
```

**⚠️ Important**: Copy this EXACT string and paste it into the GitHub secret `YOUTUBE_TOKEN`

## Testing

After updating the secret, test the workflow:
```bash
# Trigger manually via GitHub Actions UI
# Or wait for scheduled run (Monday 10:00 UTC)
```

Expected output:
```
✅ YouTube API authenticated
📅 Creating weekly playlist...
✅ Playlist created successfully
```

## Files Changed
- `youtube_playlist_manager.py` - Added error handling for corrupted tokens
- `.github/workflows/youtube-playlists.yml` - Removed whitespace stripping from base64 decode
- `scripts/encode_youtube_token.sh` - New helper script for encoding tokens

## Commit
Commit 482c945: "Fix YouTube workflow pickle error - handle corrupted tokens"
