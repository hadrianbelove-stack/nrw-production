# YouTube Playlist Workflow

**Status:** Active (restored December 4, 2025 after Google account suspension)

## Schedule

- **Weekly Playlist:** Every Monday at 10:00 UTC (2/3 AM Pacific)
- **Monthly Playlist:** 1st of each month at 10:00 UTC (2/3 AM Pacific)
- **Manual Trigger:** Available via GitHub Actions UI

## Related Files

- `.github/workflows/youtube-playlists.yml` — Workflow configuration
- `youtube_playlist_manager.py` — Playlist manager script
- `scripts/diagnose_youtube_auth.py` — Token generation/diagnostics tool
- `docs/features/YOUTUBE_PLAYLIST_SETUP.md` — Full setup guide

## Troubleshooting

If playlists stop being created:
1. Check GitHub Actions for workflow failures
2. Token may need refreshing — run `python3 scripts/diagnose_youtube_auth.py`
3. Update GitHub secret `YOUTUBE_TOKEN` with new base64-encoded token

## History

- **Oct 25, 2025:** Google account suspended (automated detection false positive)
- **Dec 4, 2025:** Account restored via appeal, new token generated, workflow re-enabled
