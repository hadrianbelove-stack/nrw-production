# YouTube Playlist Automation Setup

This guide will help you set up automated YouTube playlist creation for New Release Wall trailers.

## Overview

The system automatically creates YouTube playlists based on your `data.json`:
- **Weekly Playlists**: "This Week's New Releases" (auto-updates every Monday)
- **Monthly Playlists**: "October 2025 New Releases" (created on 1st of each month)
- **Curated Playlists**: "Certified Fresh - RT 90%+" (optional)

All playlists are created in a YouTube account you control.

---

## Prerequisites

1. **Google Account** for YouTube (create a new one specifically for NRW if desired)
2. **Python 3.10+** (already have this)
3. **Google API Libraries** (will install below)
4. **10 minutes** for initial setup

---

## Step 1: Install Python Dependencies

```bash
cd ~/Downloads/nrw-production
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

---

## Step 2: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)

2. **Create New Project:**
   - Click "Select a project" → "New Project"
   - Name: `NRW Trailers`
   - Click "Create"

3. **Enable YouTube Data API:**
   - In search bar, type "YouTube Data API v3"
   - Click the result
   - Click "Enable"

4. **Create OAuth Credentials:**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - If prompted, configure consent screen:
     - User Type: "External"
     - App name: "New Release Wall"
     - Support email: Your email
     - Developer contact: Your email
     - Click "Save and Continue" through all screens
   - Application type: "Desktop app"
   - Name: "NRW Playlist Manager"
   - Click "Create"

5. **Download Credentials:**
   - Click the download button (⬇️) next to your new OAuth client
   - This downloads a JSON file named something like `client_secret_XXXXX.json`

6. **Place Credentials:**
   ```bash
   mkdir -p ~/Downloads/nrw-production/youtube_credentials
   mv ~/Downloads/client_secret_*.json ~/Downloads/nrw-production/youtube_credentials/client_secret.json
   ```

---

## Step 3: First-Time Authorization

This is a **one-time setup**. After this, playlists will be created automatically.

```bash
cd ~/Downloads/nrw-production
python3 youtube_playlist_manager.py auth
```

**What happens:**
1. Browser opens to Google sign-in
2. **Sign in with the YouTube account you want playlists created in**
3. Google asks "NRW Playlist Manager wants to access your YouTube account"
4. Click "Allow"
5. You'll see "The authentication flow has completed"
6. Close the browser tab

Your credentials are now saved in `youtube_credentials/token.pickle` and will be used automatically.

---

## Step 4: Test Locally

### Test Trailer Extraction (no playlist created):
```bash
python3 youtube_playlist_manager.py test
```

This shows what trailers are available from your `data.json`.

### Create Weekly Playlist (dry run):
```bash
python3 youtube_playlist_manager.py weekly --dry-run
```

Shows what the playlist would look like without creating it.

### Create Weekly Playlist (live):
```bash
python3 youtube_playlist_manager.py weekly
```

This actually creates the playlist on YouTube! Check your YouTube channel.

### Create Monthly Playlist:
```bash
python3 youtube_playlist_manager.py monthly
```

### Create Certified Fresh Playlist:
```bash
python3 youtube_playlist_manager.py certified --threshold 90
```

---

## Step 5: Set Up GitHub Actions (Automation)

To make playlists update automatically every week:

1. **Encode Credentials for GitHub:**

   Both credentials must be base64-encoded for GitHub Actions:
   ```bash
   cd ~/Downloads/nrw-production
   base64 youtube_credentials/client_secret.json > client_secret_encoded.txt
   base64 youtube_credentials/token.pickle > token_encoded.txt
   ```

2. **Add GitHub Secrets:**
   - Go to your repo: https://github.com/hadrianbelove-stack/nrw-production
   - Click "Settings" → "Secrets and variables" → "Actions"
   - Click "New repository secret"

   **Secret 1:**
   - Name: `YOUTUBE_CLIENT_SECRET`
   - Value: Copy/paste contents of `client_secret_encoded.txt` (base64-encoded JSON)
   - Click "Add secret"

   **Secret 2:**
   - Name: `YOUTUBE_TOKEN`
   - Value: Copy/paste contents of `token_encoded.txt` (base64-encoded pickle file)
   - Click "Add secret"

3. **Clean Up:**
   ```bash
   rm client_secret_encoded.txt token_encoded.txt
   ```

4. **Commit Workflow:**
   ```bash
   git add .github/workflows/youtube-playlists.yml youtube_playlist_manager.py
   git commit -m "Add YouTube playlist automation"
   git push
   ```

5. **Test Automation:**
   - Go to "Actions" tab in GitHub
   - Click "Update YouTube Playlists"
   - Click "Run workflow"
   - Choose playlist type (weekly or monthly) from dropdown
   - Click "Run workflow"
   - Wait ~30 seconds, check your YouTube channel for new playlist!

---

## Automation Schedule

Once set up, GitHub Actions will automatically:

- **Every Monday at 10:00 UTC** (3 AM PDT / 2 AM PST): Rebuild "This Week's New Releases" playlist
- **1st of each month at 10:00 UTC** (3 AM PDT / 2 AM PST): Create monthly "New Releases" playlist

No manual intervention needed!

---

## Managing Playlists

### Update Existing Playlist Manually:
```bash
python3 youtube_playlist_manager.py weekly
```

This creates a NEW playlist. To update the same playlist each week, you'd need to save the playlist ID and use the update methods (advanced).

### View Available Trailers:
```bash
python3 youtube_playlist_manager.py test
```

### Create Custom Playlists:

Edit `youtube_playlist_manager.py` and add your own methods like:

```python
def create_horror_playlist(self):
    """October horror movies"""
    trailers = self.get_trailers_from_nrw_data(days_back=None)
    horror = [t for t in trailers if 'Horror' in t.get('genres', [])]
    # ... create playlist
```

---

## Troubleshooting

### "client_secret.json not found"
- Make sure you downloaded OAuth credentials from Google Cloud Console
- Check file is in `youtube_credentials/client_secret.json`

### "Import Error: google.oauth2"
```bash
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### "Token expired"
- Credentials expire after a while
- Re-run: `python3 youtube_playlist_manager.py auth`

### GitHub Actions fails
- Check that both secrets (`YOUTUBE_CLIENT_SECRET` and `YOUTUBE_TOKEN`) are set correctly
- Make sure base64 encoding included full file contents (no truncation)

### Want to change which YouTube account?
1. Delete `youtube_credentials/token.pickle`
2. Run `python3 youtube_playlist_manager.py auth` again
3. Sign in with different account

---

## API Quota Limits

YouTube Data API has a **free quota of 10,000 units/day**:
- Creating playlist: 50 units
- Adding video: 50 units per video
- **You can create ~200 video additions per day**

For weekly playlist with 60 videos:
- Create playlist: 50 units
- Add 60 videos: 60 × 50 = 3,000 units
- **Total: 3,050 units** (well under the 10,000 daily limit)

You could create **3 full playlists per day** before hitting quota.

---

## File Structure

```
nrw-production/
├── youtube_playlist_manager.py          # Main script
├── youtube_credentials/                  # Your credentials (gitignored)
│   ├── client_secret.json               # OAuth credentials
│   └── token.pickle                     # Auth token
├── .github/workflows/
│   └── youtube-playlists.yml            # Automation workflow
├── data.json                             # Source data (trailers come from here)
└── YOUTUBE_PLAYLIST_SETUP.md            # This file
```

---

## Privacy Options

When creating playlists, you can set privacy:

- `public`: Anyone can see and search for it
- `unlisted`: Only people with the link can view it
- `private`: Only you can see it

Edit `youtube_playlist_manager.py` line with `privacy='public'` to change default.

---

## Example Playlist Created

**Title:** This Week's New Releases (Oct 11 - Oct 18, 2025)

**Description:**
```
🎬 60 movies released digitally this week

Curated by New Release Wall
Updated: October 18, 2025 at 2:30 PM

Featured titles:

1. Little Did I Know
2. Our Fault • 40% RT • Domingo González
3. Night of the Reaper • 79% RT • Henrique Couto
4. The Lost Princess • 97% RT • Éric Omond
5. Nanticoke • 100% RT • A.J. Mattioli
...and 55 more!

🔗 Full list: https://newreleasewall.com
📧 Questions? Contact via GitHub
```

---

## Support

Questions? Issues? Open a GitHub issue or check the script help:

```bash
python3 youtube_playlist_manager.py --help
```

Happy playlist creating! 🎬
