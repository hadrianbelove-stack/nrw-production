#!/usr/bin/env python3
"""
YouTube Playlist Manager for New Release Wall
Automatically creates and manages trailer playlists

Setup:
1. Create Google Cloud Project: https://console.cloud.google.com
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop app type)
4. Download credentials as client_secret.json
5. Place in youtube_credentials/ directory
6. Run: python3 youtube_playlist_manager.py auth
7. Follow browser prompts to authorize (one-time setup)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import re
import argparse

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import pickle
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False
    print("⚠️  Google API libraries not installed. Run:")
    print("   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")


class YouTubePlaylistManager:
    """Manages YouTube playlists for New Release Wall trailers"""

    SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

    def __init__(self, credentials_dir='youtube_credentials'):
        """Initialize playlist manager with credentials directory"""
        self.credentials_dir = Path(credentials_dir)
        self.credentials_dir.mkdir(exist_ok=True)

        if not GOOGLE_LIBS_AVAILABLE:
            raise ImportError("Google API libraries required. See setup instructions above.")

        self.youtube = None

    def _authenticate(self):
        """Authenticate with YouTube API using OAuth 2.0"""
        creds = None
        token_path = self.credentials_dir / 'token.pickle'

        # Load saved credentials
        if token_path.exists():
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("🔄 Refreshing expired credentials...")
                creds.refresh(Request())
            else:
                client_secret_path = self.credentials_dir / 'client_secret.json'
                if not client_secret_path.exists():
                    raise FileNotFoundError(
                        f"Missing {client_secret_path}\n"
                        "Download OAuth credentials from Google Cloud Console:\n"
                        "https://console.cloud.google.com/apis/credentials"
                    )

                print("🔐 Starting OAuth authorization flow...")
                print("Your browser will open to authorize this app.")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(client_secret_path),
                    self.SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for future runs
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
            print(f"✅ Credentials saved to {token_path}")

        self.youtube = build('youtube', 'v3', credentials=creds)
        print("✅ YouTube API authenticated")

    def _ensure_client(self):
        """Ensure YouTube client is authenticated before API calls"""
        if self.youtube is None:
            self._authenticate()

    def create_playlist(self, title, description, privacy='public'):
        """
        Create a new YouTube playlist

        Args:
            title: Playlist title
            description: Playlist description (max 5000 chars)
            privacy: 'public', 'unlisted', or 'private'

        Returns:
            Playlist ID (string)
        """
        self._ensure_client()
        request = self.youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title[:150],  # Max 150 chars
                    "description": description[:5000],  # Max 5000 chars
                    "defaultLanguage": "en"
                },
                "status": {
                    "privacyStatus": privacy
                }
            }
        )
        response = request.execute()

        playlist_id = response['id']
        print(f"✅ Created playlist: {title}")
        print(f"   🔗 https://youtube.com/playlist?list={playlist_id}")
        return playlist_id

    def add_videos_to_playlist(self, playlist_id, video_ids):
        """
        Add multiple videos to a playlist

        Args:
            playlist_id: Target playlist ID
            video_ids: List of YouTube video IDs

        Returns:
            Number of videos successfully added
        """
        self._ensure_client()
        added = 0
        failed = []

        for i, video_id in enumerate(video_ids, 1):
            try:
                request = self.youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id
                            }
                        }
                    }
                )
                request.execute()
                added += 1
                print(f"   [{i}/{len(video_ids)}] Added video: {video_id}")
            except Exception as e:
                failed.append((video_id, str(e)))
                print(f"   ⚠️  Failed to add video {video_id}: {e}")

        print(f"✅ Added {added}/{len(video_ids)} videos to playlist")
        if failed:
            print(f"⚠️  {len(failed)} videos failed:")
            for vid, err in failed[:5]:  # Show first 5 failures
                print(f"   • {vid}: {err}")

        return added

    def clear_playlist(self, playlist_id):
        """
        Remove all videos from a playlist

        Args:
            playlist_id: Playlist to clear

        Returns:
            Number of videos removed
        """
        self._ensure_client()
        print(f"🗑️  Clearing playlist {playlist_id}...")

        # Get all items in playlist
        items = []
        next_page_token = None

        while True:
            request = self.youtube.playlistItems().list(
                part="id",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            items.extend(response['items'])

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        # Delete each item
        for item in items:
            self.youtube.playlistItems().delete(id=item['id']).execute()

        print(f"✅ Cleared {len(items)} videos from playlist")
        return len(items)

    def update_playlist_metadata(self, playlist_id, title=None, description=None):
        """
        Update playlist title and/or description

        Args:
            playlist_id: Playlist to update
            title: New title (optional)
            description: New description (optional)
        """
        self._ensure_client()
        # Get current playlist
        request = self.youtube.playlists().list(
            part="snippet,status",
            id=playlist_id
        )
        response = request.execute()

        if not response['items']:
            raise ValueError(f"Playlist {playlist_id} not found")

        playlist = response['items'][0]

        # Update fields
        if title:
            playlist['snippet']['title'] = title[:150]
        if description:
            playlist['snippet']['description'] = description[:5000]

        # Save changes
        request = self.youtube.playlists().update(
            part="snippet,status",
            body=playlist
        )
        request.execute()

        print(f"✅ Updated playlist metadata")

    @staticmethod
    def extract_youtube_id(url):
        """Extract YouTube video ID from URL"""
        if not url:
            return None

        # Handle watch?v= format
        match = re.search(r'watch\?v=([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)

        # Handle youtu.be/ format
        match = re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)

        # Handle embed/ format
        match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)

        # Handle shorts/ format
        match = re.search(r'youtube\.com/shorts/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def get_trailers_from_nrw_data(days_back=7, rt_min=None, data_path=None, from_date=None, to_date=None):
        """
        Load trailers from data.json with optional filtering

        Args:
            days_back: Only include movies from last N days (None = all)
            rt_min: Minimum RT score (None = all)
            data_path: Path to data.json (defaults to script directory)
            from_date: Start date for custom range (YYYY-MM-DD string or date object)
            to_date: End date for custom range (YYYY-MM-DD string or date object)

        Returns:
            List of trailer dicts with video_id, title, date, etc.
        """
        if data_path:
            data_file = Path(data_path)
        else:
            # Use stable path relative to script location
            base_dir = Path(__file__).parent
            data_file = base_dir / 'data.json'
        if not data_file.exists():
            raise FileNotFoundError("data.json not found. Run generate_data.py first.")

        with open(data_file) as f:
            data = json.load(f)

        # Handle date filtering
        cutoff = None
        date_range_start = None
        date_range_end = None

        if from_date and to_date:
            # Custom date range
            if isinstance(from_date, str):
                date_range_start = datetime.fromisoformat(from_date).date()
            else:
                date_range_start = from_date

            if isinstance(to_date, str):
                date_range_end = datetime.fromisoformat(to_date).date()
            else:
                date_range_end = to_date
        elif days_back:
            # Last N days
            cutoff = datetime.now().date() - timedelta(days=days_back)

        trailers = []

        for movie in data['movies']:
            # Extract trailer URL
            trailer_url = movie.get('links', {}).get('trailer', '')
            video_id = YouTubePlaylistManager.extract_youtube_id(trailer_url)

            if not video_id:
                continue

            # Get and validate date
            try:
                digital_date = datetime.fromisoformat(movie['digital_date']).date()
                date_str = movie['digital_date']
            except (KeyError, ValueError, TypeError):
                print(f"⚠️  Skipping '{movie.get('title', 'Unknown')}': invalid digital_date")
                continue

            # Apply date filters
            if date_range_start and date_range_end:
                # Custom date range
                if not (date_range_start <= digital_date <= date_range_end):
                    continue
            elif cutoff:
                # Last N days
                if digital_date < cutoff:
                    continue

            # Apply RT score filter
            if rt_min and (not movie.get('rt_score') or movie.get('rt_score') < rt_min):
                continue

            trailers.append({
                'video_id': video_id,
                'title': movie['title'],
                'date': date_str,
                'rt_score': movie.get('rt_score'),
                'director': movie.get('crew', {}).get('director', 'Unknown'),
                'genres': movie.get('genres', []),
                'url': trailer_url
            })

        # Sort by date (newest first)
        trailers.sort(key=lambda x: x['date'], reverse=True)
        return trailers

    def create_weekly_playlist(self, dry_run=False, data_path=None):
        """
        Create/rebuild 'This Week's New Releases' playlist

        Args:
            dry_run: If True, only print what would be done

        Returns:
            Playlist ID or None
        """
        print("\n📅 Creating weekly playlist...")

        trailers = self.get_trailers_from_nrw_data(days_back=7, data_path=data_path)

        if not trailers:
            print("⚠️  No trailers found for this week")
            return None

        # Get date range
        latest_date = datetime.fromisoformat(trailers[0]['date'])
        earliest_date = datetime.fromisoformat(trailers[-1]['date'])

        title = f"This Week's New Releases ({earliest_date.strftime('%b %d')} - {latest_date.strftime('%b %d, %Y')})"

        # Build description
        description = f"""🎬 {len(trailers)} movies released digitally this week

Curated by New Release Wall
Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

Featured titles:
"""
        # Add top movies to description
        for i, trailer in enumerate(trailers[:10], 1):
            rt = f" • {trailer['rt_score']}% RT" if trailer['rt_score'] else ""
            director = f" • {trailer['director']}" if trailer['director'] != 'Unknown' else ""
            description += f"\n{i}. {trailer['title']}{rt}{director}"

        if len(trailers) > 10:
            description += f"\n...and {len(trailers) - 10} more!"

        description += "\n\n🔗 Full list: https://newreleasewall.com"
        description += "\n📧 Questions? Contact via GitHub"

        print(f"\n📝 Playlist details:")
        print(f"   Title: {title}")
        print(f"   Videos: {len(trailers)}")
        print(f"   Date range: {earliest_date.strftime('%b %d')} - {latest_date.strftime('%b %d')}")

        if dry_run:
            print("\n🔍 DRY RUN - No playlist created")
            print(f"\nFirst 5 videos:")
            for t in trailers[:5]:
                print(f"   • {t['title']} - https://youtube.com/watch?v={t['video_id']}")
            return None

        # Create playlist
        playlist_id = self.create_playlist(title, description, privacy='public')

        # Add videos
        video_ids = [t['video_id'] for t in trailers]
        self.add_videos_to_playlist(playlist_id, video_ids)

        return playlist_id

    def create_monthly_playlist(self, year=None, month=None, dry_run=False, data_path=None):
        """
        Create monthly playlist (e.g., 'October 2025 New Releases')

        Args:
            year: Year (defaults to current)
            month: Month 1-12 (defaults to current)
            dry_run: If True, only print what would be done

        Returns:
            Playlist ID or None
        """
        print("\n📅 Creating monthly playlist...")

        if not year or not month:
            now = datetime.now()
            year, month = now.year, now.month

        # Date range for the month
        month_start = f"{year}-{month:02d}-01"
        if month == 12:
            month_end = f"{year+1}-01-01"
        else:
            month_end = f"{year}-{month+1:02d}-01"

        # Load all trailers
        all_trailers = self.get_trailers_from_nrw_data(days_back=None, data_path=data_path)

        # Filter to month
        trailers = [
            t for t in all_trailers
            if month_start <= t['date'] < month_end
        ]

        if not trailers:
            print(f"⚠️  No trailers found for {month}/{year}")
            return None

        month_name = datetime(year, month, 1).strftime('%B %Y')
        title = f"New Releases - {month_name}"

        # Build description
        description = f"""🎬 {len(trailers)} movies released digitally in {month_name}

Curated by New Release Wall
Generated: {datetime.now().strftime('%B %d, %Y')}

Top rated this month:
"""
        # Add top rated movies
        top_rated = sorted(
            [t for t in trailers if t.get('rt_score')],
            key=lambda x: x['rt_score'],
            reverse=True
        )[:10]

        if top_rated:
            for i, trailer in enumerate(top_rated, 1):
                description += f"\n{i}. {trailer['title']} - {trailer['rt_score']}% RT"
        else:
            description += "\n(RT scores being collected)"

        description += f"\n\n📊 Total releases: {len(trailers)}"
        description += "\n🔗 https://newreleasewall.com"

        print(f"\n📝 Playlist details:")
        print(f"   Title: {title}")
        print(f"   Videos: {len(trailers)}")
        print(f"   Month: {month_name}")

        if dry_run:
            print("\n🔍 DRY RUN - No playlist created")
            print(f"\nTop 5 rated:")
            for t in top_rated[:5]:
                print(f"   • {t['title']} - {t['rt_score']}% RT")
            return None

        # Create playlist
        playlist_id = self.create_playlist(title, description, privacy='public')

        # Add videos (sorted by date, newest first)
        video_ids = [t['video_id'] for t in trailers]
        self.add_videos_to_playlist(playlist_id, video_ids)

        return playlist_id

    def create_certified_fresh_playlist(self, rt_threshold=90, dry_run=False, data_path=None):
        """
        Create 'Certified Fresh' playlist with high RT scores

        Args:
            rt_threshold: Minimum RT score (default 90%)
            dry_run: If True, only print what would be done

        Returns:
            Playlist ID or None
        """
        print(f"\n🏆 Creating Certified Fresh playlist (RT ≥ {rt_threshold}%)...")

        trailers = self.get_trailers_from_nrw_data(days_back=90, rt_min=rt_threshold, data_path=data_path)

        if not trailers:
            print(f"⚠️  No trailers found with RT ≥ {rt_threshold}%")
            return None

        title = f"Certified Fresh - RT {rt_threshold}%+ (Last 90 Days)"
        description = f"""🍅 {len(trailers)} critically acclaimed movies from the past 90 days

All films have a Rotten Tomatoes score of {rt_threshold}% or higher.

Curated by New Release Wall
Updated: {datetime.now().strftime('%B %d, %Y')}

Top rated:
"""
        for i, trailer in enumerate(trailers[:15], 1):
            description += f"\n{i}. {trailer['title']} - {trailer['rt_score']}% RT"

        description += "\n\n🔗 https://newreleasewall.com"

        print(f"\n📝 Playlist details:")
        print(f"   Title: {title}")
        print(f"   Videos: {len(trailers)}")
        print(f"   RT threshold: {rt_threshold}%")

        if dry_run:
            print("\n🔍 DRY RUN - No playlist created")
            return None

        # Create playlist
        playlist_id = self.create_playlist(title, description, privacy='public')

        # Add videos (already sorted by date)
        video_ids = [t['video_id'] for t in trailers]
        self.add_videos_to_playlist(playlist_id, video_ids)

        return playlist_id

    def create_custom_playlist(self, days_back=None, from_date=None, to_date=None,
                              title=None, privacy='public', dry_run=False, data_path=None):
        """
        Create a custom playlist with flexible date parameters

        Args:
            days_back: Number of days back from today (None = use date range)
            from_date: Start date for custom range (YYYY-MM-DD)
            to_date: End date for custom range (YYYY-MM-DD)
            title: Custom playlist title (auto-generated if None)
            privacy: 'public', 'unlisted', or 'private'
            dry_run: If True, only print what would be done
            data_path: Path to data.json

        Returns:
            Playlist ID or None
        """
        print("\n📺 Creating custom playlist...")

        # Get trailers based on date parameters
        if from_date and to_date:
            trailers = self.get_trailers_from_nrw_data(
                days_back=None,
                from_date=from_date,
                to_date=to_date,
                data_path=data_path
            )
            date_range_str = f"{from_date} to {to_date}"
        elif days_back:
            trailers = self.get_trailers_from_nrw_data(days_back=days_back, data_path=data_path)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            date_range_str = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
        else:
            print("⚠️  Must specify either days_back or from_date/to_date")
            return None

        if not trailers:
            print(f"⚠️  No trailers found for specified date range")
            return None

        # Auto-generate title if not provided
        if not title:
            if from_date and to_date:
                from_dt = datetime.fromisoformat(from_date)
                to_dt = datetime.fromisoformat(to_date)
                title = f"New Releases ({from_dt.strftime('%b %d')} - {to_dt.strftime('%b %d, %Y')})"
            else:
                title = f"New Releases - Last {days_back} Days"

        # Build description
        description = f"""🎬 {len(trailers)} movies released digitally

Curated by New Release Wall
Created: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
Date Range: {date_range_str}

Featured titles:
"""
        # Add top movies to description
        for i, trailer in enumerate(trailers[:10], 1):
            rt = f" • {trailer['rt_score']}% RT" if trailer['rt_score'] else ""
            director = f" • {trailer['director']}" if trailer['director'] != 'Unknown' else ""
            description += f"\n{i}. {trailer['title']}{rt}{director}"

        if len(trailers) > 10:
            description += f"\n...and {len(trailers) - 10} more!"

        description += "\n\n🔗 Full list: https://newreleasewall.com"

        print(f"\n📝 Playlist details:")
        print(f"   Title: {title}")
        print(f"   Videos: {len(trailers)}")
        print(f"   Date range: {date_range_str}")

        if dry_run:
            print("\n🔍 DRY RUN - No playlist created")
            print(f"\nFirst 5 videos:")
            for t in trailers[:5]:
                print(f"   • {t['title']} - https://youtube.com/watch?v={t['video_id']}")
            return None

        # Create playlist
        playlist_id = self.create_playlist(title, description, privacy=privacy)

        # Add videos
        video_ids = [t['video_id'] for t in trailers]
        self.add_videos_to_playlist(playlist_id, video_ids)

        return playlist_id


def main():
    """CLI interface for YouTube Playlist Manager"""
    parser = argparse.ArgumentParser(
        description='YouTube Playlist Manager for New Release Wall',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First-time setup (authorize with Google)
  python3 youtube_playlist_manager.py auth

  # Test trailer extraction (no playlist created)
  python3 youtube_playlist_manager.py test

  # Create this week's playlist (dry run)
  python3 youtube_playlist_manager.py weekly --dry-run

  # Create this week's playlist (live)
  python3 youtube_playlist_manager.py weekly

  # Create monthly playlist
  python3 youtube_playlist_manager.py monthly --month 10 --year 2025

  # Create certified fresh playlist (RT ≥ 90%)
  python3 youtube_playlist_manager.py certified --threshold 90

  # Create custom playlist - last 14 days
  python3 youtube_playlist_manager.py custom --days-back 14

  # Create custom playlist - specific date range
  python3 youtube_playlist_manager.py custom --from-date 2025-10-01 --to-date 2025-10-15

  # Create custom playlist with custom title
  python3 youtube_playlist_manager.py custom --days-back 30 --title "October Horror Movies" --privacy unlisted
        """
    )

    parser.add_argument(
        'action',
        choices=['auth', 'test', 'weekly', 'monthly', 'certified', 'custom'],
        help='Action to perform'
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without creating playlist')
    parser.add_argument('--month', type=int,
                       help='Month for monthly playlist (1-12)')
    parser.add_argument('--year', type=int,
                       help='Year for monthly playlist')
    parser.add_argument('--threshold', type=int, default=90,
                       help='RT score threshold for certified playlist (default: 90)')
    parser.add_argument('--data-path', type=str,
                       help='Path to data.json file (defaults to script directory)')
    parser.add_argument('--days-back', type=int,
                       help='Number of days back for custom playlist')
    parser.add_argument('--from-date', type=str,
                       help='Start date for custom playlist (YYYY-MM-DD)')
    parser.add_argument('--to-date', type=str,
                       help='End date for custom playlist (YYYY-MM-DD)')
    parser.add_argument('--title', type=str,
                       help='Custom playlist title (auto-generated if not provided)')
    parser.add_argument('--privacy', type=str, default='public',
                       choices=['public', 'unlisted', 'private'],
                       help='Playlist privacy setting (default: public)')

    args = parser.parse_args()

    # Handle auth action separately (doesn't need manager)
    if args.action == 'auth':
        print("🔐 Setting up YouTube API authentication...")
        print("\nThis will open your browser to authorize the app.")
        print("Make sure you're signed in to your NRW YouTube account.\n")
        try:
            manager = YouTubePlaylistManager()
            print("\n✅ Authentication complete!")
            print(f"Credentials saved to youtube_credentials/")
        except Exception as e:
            print(f"\n❌ Authentication failed: {e}")
            sys.exit(1)
        return

    # Test action - just show trailer stats
    if args.action == 'test':
        print("🔍 Testing trailer extraction from data.json...\n")
        try:
            # Don't need authentication for test - use static method
            trailers = YouTubePlaylistManager.get_trailers_from_nrw_data(days_back=7, data_path=args.data_path)

            print(f"📊 Found {len(trailers)} trailers this week:\n")
            for i, t in enumerate(trailers[:15], 1):
                rt = f"🍅 {t['rt_score']}%" if t['rt_score'] else "No score"
                print(f"  {i}. {t['title']} ({t['date']}) - {rt}")
                print(f"     https://youtube.com/watch?v={t['video_id']}")

            if len(trailers) > 15:
                print(f"\n  ...and {len(trailers) - 15} more")

            print(f"\n✅ Trailer extraction working correctly")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
        return

    # All other actions need authenticated manager (except weekly dry-run)
    manager = None
    if not (args.action == 'weekly' and args.dry_run):
        try:
            manager = YouTubePlaylistManager()
        except Exception as e:
            print(f"❌ Failed to initialize: {e}")
            print("\nRun 'python3 youtube_playlist_manager.py auth' first")
            sys.exit(1)

    # Execute requested action
    try:
        if args.action == 'weekly':
            if args.dry_run:
                # Compute trailers before creating manager for dry run
                print("\n📅 Creating weekly playlist...")
                trailers = YouTubePlaylistManager.get_trailers_from_nrw_data(days_back=7, data_path=args.data_path)

                if not trailers:
                    print("⚠️  No trailers found for this week")
                    return

                # Get date range
                latest_date = datetime.fromisoformat(trailers[0]['date'])
                earliest_date = datetime.fromisoformat(trailers[-1]['date'])
                title = f"This Week's New Releases ({earliest_date.strftime('%b %d')} - {latest_date.strftime('%b %d, %Y')})"

                print(f"\n📝 Playlist details:")
                print(f"   Title: {title}")
                print(f"   Videos: {len(trailers)}")
                print(f"   Date range: {earliest_date.strftime('%b %d')} - {latest_date.strftime('%b %d')}")
                print("\n🔍 DRY RUN - No playlist created")
                print(f"\nFirst 5 videos:")
                for t in trailers[:5]:
                    print(f"   • {t['title']} - https://youtube.com/watch?v={t['video_id']}")
            else:
                playlist_id = manager.create_weekly_playlist(dry_run=args.dry_run, data_path=args.data_path)
                if playlist_id:
                    print(f"\n🎬 Success! Playlist created:")
                    print(f"   https://youtube.com/playlist?list={playlist_id}")

        elif args.action == 'monthly':
            playlist_id = manager.create_monthly_playlist(
                args.year, args.month, dry_run=args.dry_run, data_path=args.data_path
            )
            if playlist_id and not args.dry_run:
                print(f"\n🎬 Success! Playlist created:")
                print(f"   https://youtube.com/playlist?list={playlist_id}")

        elif args.action == 'certified':
            playlist_id = manager.create_certified_fresh_playlist(
                rt_threshold=args.threshold, dry_run=args.dry_run, data_path=args.data_path
            )
            if playlist_id and not args.dry_run:
                print(f"\n🎬 Success! Playlist created:")
                print(f"   https://youtube.com/playlist?list={playlist_id}")

        elif args.action == 'custom':
            # Validate parameters
            if args.from_date and args.to_date:
                # Use date range
                playlist_id = manager.create_custom_playlist(
                    from_date=args.from_date,
                    to_date=args.to_date,
                    title=args.title,
                    privacy=args.privacy,
                    dry_run=args.dry_run,
                    data_path=args.data_path
                )
            elif args.days_back:
                # Use days back
                playlist_id = manager.create_custom_playlist(
                    days_back=args.days_back,
                    title=args.title,
                    privacy=args.privacy,
                    dry_run=args.dry_run,
                    data_path=args.data_path
                )
            else:
                print("❌ Error: Must specify either --days-back or both --from-date and --to-date")
                sys.exit(1)

            if playlist_id and not args.dry_run:
                print(f"\n🎬 Success! Playlist created:")
                print(f"   https://youtube.com/playlist?list={playlist_id}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
