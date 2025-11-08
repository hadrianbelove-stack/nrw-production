# YouTube Workflow Disabled

**Status:** DISABLED as of November 3, 2025
**Reason:** Google account suspension

## Problem

The Google account associated with the YouTube Data API project was disabled by Google on **October 25, 2025**. This is the root cause of all YouTube playlist workflow failures.

### Account Status Message
```
It looks like this account was created or used with multiple other accounts
to violate Google's policies. The account might have been created by a
computer program or bot.

This account became unavailable on Oct 25, 2025.
Starting on Sep 20, 2026, this account will be considered for deletion.
```

### Impact
- ❌ Cannot access Google Cloud Console for "new-release-wall" project
- ❌ Cannot generate new OAuth tokens
- ❌ Existing token.pickle is invalid
- ❌ YouTube channel is inaccessible
- ❌ All YouTube playlist automation is non-functional

## Timeline

- **Oct 25, 2025:** Google account disabled
- **Oct 27, 2025:** First YouTube workflow failure detected
- **Nov 3, 2025:** Root cause identified, workflow disabled

## Recovery Options

### Option 1: Appeal Account Suspension (Recommended)

If you want to preserve the existing YouTube channel and its content:

1. **Submit Appeal:**
   - Visit: https://accounts.google.com/signin/v2/recoveryidentifier
   - Follow the account recovery process
   - Explain this is a legitimate project for a movie review website
   - Provide evidence of legitimate use

2. **Wait for Review:**
   - Google reviews can take 3-7 business days
   - May require additional verification

3. **After Restoration:**
   - Access Google Cloud Console
   - Verify YouTube Data API is still enabled
   - Generate new OAuth token:
     ```bash
     python3 scripts/manual_token_generator.py
     ```
   - Update GitHub secrets:
     ```bash
     gh secret set YOUTUBE_TOKEN < youtube_token_base64.txt
     gh secret set YOUTUBE_CLIENT_SECRET < youtube_client_secret_base64.txt
     ```
   - Re-enable workflow by uncommenting schedule in `.github/workflows/youtube-playlists.yml`

### Option 2: Create New Setup

If appeal fails or you want to start fresh:

1. **Create New Google Account:**
   - Use personal account or create dedicated account for NRW
   - Ensure account has good standing (aged, verified, legitimate use history)

2. **Create New YouTube Channel:**
   - Set up new channel for NRW playlists
   - Manually recreate any important playlists from old channel

3. **Set Up New Google Cloud Project:**
   - Go to: https://console.cloud.google.com/
   - Create new project (e.g., "nrw-production-v2")
   - Enable YouTube Data API v3
   - Create OAuth 2.0 credentials (Desktop application)
   - Configure authorized redirect URIs:
     - `http://localhost:8080/`
     - `http://localhost:8080`
     - `http://127.0.0.1:8080/`
   - Download client_secret.json

4. **Generate Token:**
   ```bash
   # Replace old client_secret.json
   cp ~/Downloads/client_secret.json youtube_credentials/client_secret.json

   # Generate token
   python3 scripts/manual_token_generator.py
   ```

5. **Update GitHub Secrets:**
   ```bash
   # Encode credentials
   base64 youtube_credentials/client_secret.json > client_secret_base64.txt
   base64 youtube_credentials/token.pickle > youtube_token_base64.txt

   # Update secrets
   gh secret set YOUTUBE_CLIENT_SECRET < client_secret_base64.txt
   gh secret set YOUTUBE_TOKEN < youtube_token_base64.txt
   ```

6. **Re-enable Workflow:**
   - Edit `.github/workflows/youtube-playlists.yml`
   - Uncomment the schedule section
   - Commit changes

## Current Workflow State

The YouTube playlist workflow has been modified to:
- ✅ Disable automatic scheduled runs (cron jobs commented out)
- ✅ Keep manual trigger available for testing after recovery
- ✅ Document the issue for future reference

## Testing After Recovery

Once account is restored and new token is generated:

```bash
# Test locally first
python3 youtube_playlist_manager.py weekly --dry-run

# Test in GitHub Actions
gh workflow run youtube-playlists.yml

# Monitor the run
gh run watch

# Check results
gh run list --workflow=youtube-playlists.yml --limit=1
```

## Related Files

- [.github/workflows/youtube-playlists.yml](.github/workflows/youtube-playlists.yml) - Workflow configuration (currently disabled)
- [youtube_playlist_manager.py](youtube_playlist_manager.py) - Playlist manager script
- [scripts/manual_token_generator.py](scripts/manual_token_generator.py) - Token generation tool
- [CURRENT_WORKFLOW_STATUS.md](CURRENT_WORKFLOW_STATUS.md) - Overall workflow status

## Notes

- The daily update workflow is unaffected and continues to run
- YouTube playlist functionality is a nice-to-have feature, not critical to core functionality
- Consider whether automated YouTube playlist management is worth the complexity
- Alternative: Manually curate playlists or use a simpler integration method
