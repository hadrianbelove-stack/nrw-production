#!/usr/bin/env python3
"""
Watchmode API Wrapper with Quota Management (Phase 3.1)

Provides:
- Quota tracking to prevent exceeding free tier (1000 calls/month)
- Automatic monthly reset detection
- Call history logging for analytics
- Graceful degradation when quota exhausted

Free tier: 1000 calls/month
Paid tier: $249/month (Startup plan)

With Phase 2.1 optimization, free tier should be sustainable indefinitely.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any


class WatchmodeAPI:
    """Watchmode API client with quota management"""

    def __init__(self, api_key: str, quota_limit: int = 1000):
        """
        Initialize Watchmode API client with quota tracking

        Args:
            api_key: Watchmode API key
            quota_limit: Monthly quota limit (default: 1000 for free tier)
        """
        self.api_key = api_key
        self.quota_limit = quota_limit
        self.base_url = "https://api.watchmode.com/v1"

        # Load or initialize quota tracker
        self.quota_tracker = self._load_quota_tracker()

        # Check if month has rolled over and reset quota
        self._check_monthly_reset()

    def _load_quota_tracker(self) -> Dict[str, Any]:
        """Load quota tracker from watchmode_quota.json"""
        quota_file = 'watchmode_quota.json'

        if os.path.exists(quota_file):
            try:
                with open(quota_file, 'r') as f:
                    tracker = json.load(f)
                    # Validate structure
                    if all(k in tracker for k in ['calls_this_month', 'quota_limit', 'reset_date']):
                        return tracker
            except Exception as e:
                print(f"⚠️  Warning: Failed to load {quota_file}: {e}")

        # Initialize new tracker
        return self._create_new_tracker()

    def _create_new_tracker(self) -> Dict[str, Any]:
        """Create new quota tracker with fresh state"""
        now = datetime.now()
        # Reset on 1st of next month
        if now.day == 1:
            reset_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Next month
            if now.month == 12:
                reset_date = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                reset_date = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

        return {
            'calls_this_month': 0,
            'quota_limit': self.quota_limit,
            'reset_date': reset_date.isoformat(),
            'last_reset': datetime.now().isoformat(),
            'call_history': []
        }

    def _check_monthly_reset(self):
        """Check if we've passed reset date and reset quota if needed"""
        reset_date_str = self.quota_tracker.get('reset_date')
        if not reset_date_str:
            return

        try:
            reset_date = datetime.fromisoformat(reset_date_str)
            now = datetime.now()

            if now >= reset_date:
                print(f"🔄 Watchmode quota reset detected (crossed {reset_date.strftime('%Y-%m-%d')})")
                print(f"   Previous usage: {self.quota_tracker['calls_this_month']}/{self.quota_tracker['quota_limit']}")

                # Reset tracker
                old_calls = self.quota_tracker['calls_this_month']
                self.quota_tracker = self._create_new_tracker()
                self._save_quota_tracker()

                print(f"   ✅ Quota reset to 0/{self.quota_limit}")

        except Exception as e:
            print(f"⚠️  Warning: Failed to check monthly reset: {e}")

    def _save_quota_tracker(self):
        """Save quota tracker to watchmode_quota.json"""
        quota_file = 'watchmode_quota.json'
        try:
            with open(quota_file, 'w') as f:
                json.dump(self.quota_tracker, f, indent=2)
        except Exception as e:
            print(f"⚠️  Warning: Failed to save quota tracker: {e}")

    def check_quota_available(self) -> bool:
        """
        Check if quota is available for API call

        Returns:
            True if quota available, False if exhausted
        """
        calls = self.quota_tracker['calls_this_month']
        limit = self.quota_tracker['quota_limit']

        if calls >= limit:
            reset_date = self.quota_tracker.get('reset_date', 'unknown')
            print(f"⚠️  Watchmode quota exhausted ({calls}/{limit})")
            print(f"   Resets on: {reset_date}")
            print(f"   Falling back to platform scrapers...")
            return False

        return True

    def get_quota_status(self) -> Dict[str, Any]:
        """
        Get current quota status

        Returns:
            Dict with quota information
        """
        calls = self.quota_tracker['calls_this_month']
        limit = self.quota_tracker['quota_limit']
        remaining = max(0, limit - calls)
        percentage_used = (calls / limit * 100) if limit > 0 else 0

        return {
            'calls_used': calls,
            'quota_limit': limit,
            'remaining': remaining,
            'percentage_used': percentage_used,
            'reset_date': self.quota_tracker.get('reset_date'),
            'exhausted': calls >= limit
        }

    def _track_call(self, title: str, tmdb_id: str, call_type: str, success: bool):
        """Track an API call in history"""
        self.quota_tracker['calls_this_month'] += 1

        # Add to call history (keep last 100 calls)
        call_record = {
            'timestamp': datetime.now().isoformat(),
            'title': title,
            'tmdb_id': tmdb_id,
            'type': call_type,  # 'search' or 'details'
            'success': success
        }

        self.quota_tracker['call_history'].append(call_record)

        # Keep only last 100 calls to prevent file bloat
        if len(self.quota_tracker['call_history']) > 100:
            self.quota_tracker['call_history'] = self.quota_tracker['call_history'][-100:]

        self._save_quota_tracker()

    def search_by_tmdb_id(self, tmdb_id: str, title: str = "Unknown") -> Optional[Dict[str, Any]]:
        """
        Search for a movie by TMDB ID

        Args:
            tmdb_id: TMDB movie ID
            title: Movie title (for logging)

        Returns:
            Search results or None if quota exhausted or error
        """
        # Check quota before making call
        if not self.check_quota_available():
            return None

        try:
            search_url = f"{self.base_url}/search/"
            search_params = {
                "apiKey": self.api_key,
                "search_field": "tmdb_movie_id",
                "search_value": tmdb_id
            }

            response = requests.get(search_url, params=search_params, timeout=10)

            # Track the call
            success = response.status_code == 200
            self._track_call(title, tmdb_id, 'search', success)

            if response.status_code == 200:
                data = response.json()

                # Check for quota error in response
                if not data.get('success', True) and 'quota' in data.get('errorMessage', '').lower():
                    print(f"⚠️  Watchmode API quota error: {data.get('errorMessage')}")
                    # Mark as exhausted
                    self.quota_tracker['calls_this_month'] = self.quota_tracker['quota_limit']
                    self._save_quota_tracker()
                    return None

                return data
            elif response.status_code == 429:
                # 429 = Too Many Requests (quota exhausted)
                print(f"⚠️  Watchmode quota exhausted (429 Too Many Requests)")
                # Mark as exhausted
                self.quota_tracker['calls_this_month'] = self.quota_tracker['quota_limit']
                self._save_quota_tracker()
                return None
            else:
                print(f"⚠️  Watchmode search failed for {title} (status {response.status_code})")
                return None

        except Exception as e:
            print(f"⚠️  Watchmode search error for {title}: {e}")
            self._track_call(title, tmdb_id, 'search', False)
            return None

    def get_title_details(self, watchmode_id: int, title: str = "Unknown", tmdb_id: str = "Unknown") -> Optional[Dict[str, Any]]:
        """
        Get detailed information including sources for a Watchmode title ID

        Args:
            watchmode_id: Watchmode title ID
            title: Movie title (for logging)
            tmdb_id: TMDB ID (for logging)

        Returns:
            Title details with sources or None if quota exhausted or error
        """
        # Check quota before making call
        if not self.check_quota_available():
            return None

        try:
            details_url = f"{self.base_url}/title/{watchmode_id}/details/"
            details_params = {
                "apiKey": self.api_key,
                "append_to_response": "sources"
            }

            response = requests.get(details_url, params=details_params, timeout=10)

            # Track the call
            success = response.status_code == 200
            self._track_call(title, tmdb_id, 'details', success)

            if response.status_code == 200:
                data = response.json()

                # Check for quota error in response
                if not data.get('success', True) and 'quota' in data.get('errorMessage', '').lower():
                    print(f"⚠️  Watchmode API quota error: {data.get('errorMessage')}")
                    # Mark as exhausted
                    self.quota_tracker['calls_this_month'] = self.quota_tracker['quota_limit']
                    self._save_quota_tracker()
                    return None

                return data
            elif response.status_code == 429:
                # 429 = Too Many Requests (quota exhausted)
                print(f"⚠️  Watchmode quota exhausted (429 Too Many Requests)")
                # Mark as exhausted
                self.quota_tracker['calls_this_month'] = self.quota_tracker['quota_limit']
                self._save_quota_tracker()
                return None
            else:
                print(f"⚠️  Watchmode details failed for {title} (status {response.status_code})")
                return None

        except Exception as e:
            print(f"⚠️  Watchmode details error for {title}: {e}")
            self._track_call(title, tmdb_id, 'details', False)
            return None

    def get_watch_links(self, tmdb_id: str, title: str) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """
        Get watch links for a movie (convenience method combining search + details)

        Args:
            tmdb_id: TMDB movie ID
            title: Movie title

        Returns:
            Dict with streaming/rent/buy lists or None if not found or quota exhausted
            Example: {
                'streaming': [{'service': 'Netflix', 'link': 'https://...'}],
                'rent': [{'service': 'Amazon', 'link': 'https://...'}],
                'buy': [{'service': 'iTunes', 'link': 'https://...'}]
            }
        """
        # Step 1: Search for movie
        search_results = self.search_by_tmdb_id(tmdb_id, title)

        if not search_results or not search_results.get('title_results'):
            return None

        watchmode_id = search_results['title_results'][0]['id']

        # Step 2: Get details with sources
        details = self.get_title_details(watchmode_id, title, tmdb_id)

        if not details:
            return None

        sources = details.get('sources', [])

        if not sources:
            return None

        # Organize by type (US only)
        watch_links = {
            'streaming': [],
            'rent': [],
            'buy': []
        }

        for source in sources:
            if source.get('region') != 'US':
                continue

            service_name = source.get('name', '')
            web_url = source.get('web_url', '')
            source_type = source.get('type', '')

            if not service_name or not web_url:
                continue

            link_obj = {'service': service_name, 'link': web_url}

            if source_type == 'sub':
                watch_links['streaming'].append(link_obj)
            elif source_type == 'rent':
                watch_links['rent'].append(link_obj)
            elif source_type == 'buy':
                watch_links['buy'].append(link_obj)

        # Return None if no links found (don't waste the API calls)
        if not any(watch_links.values()):
            return None

        return watch_links

    def print_quota_report(self):
        """Print a detailed quota usage report"""
        status = self.get_quota_status()

        print(f"\n📊 Watchmode API Quota Report:")
        print(f"   Calls used: {status['calls_used']}/{status['quota_limit']}")
        print(f"   Remaining: {status['remaining']}")
        print(f"   Usage: {status['percentage_used']:.1f}%")
        print(f"   Reset date: {status['reset_date']}")

        if status['exhausted']:
            print(f"   ⚠️  STATUS: EXHAUSTED (falling back to scrapers)")
        elif status['percentage_used'] >= 90:
            print(f"   ⚠️  STATUS: WARNING (>90% used)")
        elif status['percentage_used'] >= 75:
            print(f"   ℹ️  STATUS: MODERATE (>75% used)")
        else:
            print(f"   ✅ STATUS: OK")

        # Show recent call history (last 5)
        if self.quota_tracker.get('call_history'):
            print(f"\n   Recent calls (last 5):")
            for call in self.quota_tracker['call_history'][-5:]:
                timestamp = datetime.fromisoformat(call['timestamp']).strftime('%Y-%m-%d %H:%M')
                success_icon = "✓" if call['success'] else "✗"
                print(f"     {success_icon} {timestamp} - {call['title']} ({call['type']})")


# Convenience function for backwards compatibility
def create_watchmode_client(api_key: Optional[str] = None, quota_limit: int = 1000) -> Optional[WatchmodeAPI]:
    """
    Create a Watchmode API client with quota management

    Args:
        api_key: Watchmode API key (defaults to WATCHMODE_API_KEY env var)
        quota_limit: Monthly quota limit (default: 1000)

    Returns:
        WatchmodeAPI instance or None if no API key available
    """
    if not api_key:
        api_key = os.environ.get('WATCHMODE_API_KEY')

    if not api_key or api_key == "REPLACE_WITH_NEW_API_KEY":
        print("⚠️  WATCHMODE_API_KEY not set, Watchmode features disabled")
        return None

    return WatchmodeAPI(api_key, quota_limit)


if __name__ == "__main__":
    # Test/demo script
    client = create_watchmode_client()

    if client:
        client.print_quota_report()

        # Test with a movie
        print("\n🎬 Testing with 'The Matrix' (TMDB ID: 603)...")
        links = client.get_watch_links("603", "The Matrix")

        if links:
            print("\n✅ Found watch links:")
            for category, items in links.items():
                if items:
                    print(f"   {category.upper()}: {len(items)} options")
                    for item in items[:2]:  # Show first 2
                        print(f"     - {item['service']}: {item['link'][:50]}...")
        else:
            print("\n⚠️  No watch links found (quota exhausted or movie not available)")

        client.print_quota_report()
