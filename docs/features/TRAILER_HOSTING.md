# Trailer Hosting System

## How It Works (Plain English)

NRW trailers are **self-hosted video files**, NOT YouTube embeds. Here's the flow:

```
YouTube (source) → yt-dlp (download) → Backblaze B2 (storage) → HTML5 <video> (playback)
```

1. **Download**: `scripts/trailer_downloader.py` uses yt-dlp to download trailers from YouTube as 1080p MP4 files
2. **Upload**: `scripts/trailer_uploader.py` uploads MP4s to Backblaze B2 cloud storage (bucket: `NRW-TRAILERS`)
3. **Stamp**: `scripts/trailer_pipeline.py stamp` writes the B2 URL into each movie's `links.trailer_hosted` field in data.json
4. **Playback**: All 7 devices use HTML5 `<video>` (or native video player) to play the MP4 directly

YouTube is only involved as the *source* for downloading. The actual playback never touches YouTube.

## Two-Stage Pipeline (CI + Local)

Trailer hosting is split between CI (GitHub Actions) and the local Mac:

| Stage | When | What | Command |
|-------|------|------|---------|
| **CI** | 3 AM UTC | Stamps existing B2 URLs into data.json | `scripts/trailer_pipeline.py stamp` |
| **Local** | 10 AM (launchd) | Downloads from YouTube + uploads to B2 | `scripts/trailer_pipeline.py host` |

**Why split?** YouTube downloads require cookies/auth that only work on the local Mac. CI cannot download from YouTube. So CI handles URL stamping, while local handles the actual download and upload to B2.

**Hosting gap (3 AM - 10 AM):** Newly discovered movies have YouTube URLs but no hosted MP4s yet. During this window, desktop/mobile/iOS/tvOS/Android fall back to YouTube embeds. Roku has no trailer available (MP4-only, no YouTube fallback). After 10 AM, the local script hosts the trailers. The next CI run stamps the B2 URLs.

## Data Fields

Each movie in data.json has two trailer-related fields:

| Field | What it is | Example | Used for |
|-------|-----------|---------|----------|
| `links.trailer_hosted` | **Self-hosted MP4 on Backblaze B2** (primary) | `https://f004.backblazeb2.com/file/NRW-TRAILERS/1443940.mp4` | Direct video playback |
| `links.trailer` | **YouTube URL** (fallback only) | `https://www.youtube.com/watch?v=abc123` | Backup if no hosted version exists |

**All devices check `trailer_hosted` first.** If it exists, they play the MP4 directly. Only if `trailer_hosted` is missing do they fall back to the YouTube URL.

## Device Playback

| Device | Primary (trailer_hosted) | Fallback (trailer) |
|----------|-------------------------|-------------------|
| Desktop Website | HTML5 `<video>` element | YouTube iframe embed |
| Mobile Website | HTML5 `<video>` element | YouTube iframe embed |
| iOS App | react-native-video `<Video>` | WebView with YouTube embed |
| tvOS App | react-native-video `<Video>` | WebView with YouTube embed |
| Android TV | ExoPlayer / `Mp4Player()` | WebView `YouTubeEmbed()` |
| Roku | native Video node (MP4 only) | No YouTube fallback |
| Admin Panel | HTML5 `<video>` element | YouTube iframe embed |

## Key Files

| File | Purpose |
|------|---------|
| `scripts/trailer_downloader.py` | Downloads trailers from YouTube via yt-dlp (1080p, 5-min cap) |
| `scripts/trailer_uploader.py` | Uploads MP4s to Backblaze B2 |
| `scripts/trailer_pipeline.py` | Orchestrates: download → upload → stamp URLs → rotate old trailers |
| `config.yaml` (trailer_hosting section) | B2 bucket URL, rotation cap (200), master toggle |

## Configuration

In `config.yaml`:
```yaml
trailer_hosting:
  enabled: true
  bucket_url: "https://f004.backblazeb2.com/file/NRW-TRAILERS"
  max_hosted: 200    # Scope: only the 200 most recent movies get trailers
  pipeline_integration: true
```

**`max_hosted` controls TWO things:**
1. **Hosting scope** — the `host` command only downloads trailers for the most recent 200 movies (by `digital_date`, newest first)
2. **Rotation cap** — the `rotate` command deletes oldest trailers from B2 when over this count

This means trailers are a rolling window: as new movies arrive, old ones rotate out.

Credentials in `.env`: `B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`

## Common Misconception

**YouTube is NOT the delivery platform.** YouTube is only used:
1. As the *source* where yt-dlp downloads from
2. As a *fallback* for the small number of movies that haven't been downloaded yet
3. For *playlist curation* (a separate feature — see `docs/features/YOUTUBE_PLAYLIST_SETUP.md`)

The vast majority of trailers (324+ as of March 2026) are served as self-hosted MP4 files from Backblaze B2.
