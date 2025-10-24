#!/usr/bin/env python3
"""
Movie Digital Release Tracker - Core Logic
Tracks ALL movie premieres and detects digital availability via providers
"""

import json
import os
import random
import requests
import time
import yaml
from datetime import datetime, timedelta

class MovieTracker:
    def __init__(self, db_file='movie_tracking.json'):
        self.db_file = db_file

        # Load config with fallbacks
        self.config = self.load_config()
        self.api_key = self.get_api_key()
        self.max_pages_daily = self.config.get('api', {}).get('max_pages_daily', 9)
        self.max_pages_bootstrap = self.config.get('api', {}).get('max_pages_bootstrap', 49)

        # Discovery parameters
        self.discovery_days_back = self.config.get('discovery', {}).get('days_back', 7)
        self.discovery_max_pages = self.config.get('discovery', {}).get('max_pages', 10)

        self.db = self.load_database()

    def load_config(self):
        """Load configuration from config.yaml with fallbacks"""
        try:
            with open('config.yaml', 'r') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}
        except yaml.YAMLError:
            return {}

    def get_api_key(self):
        """Get TMDB API key from environment variable or config file"""
        # First check environment variable
        api_key = os.environ.get('TMDB_API_KEY')
        if api_key:
            return api_key

        # Fallback to config file
        api_key = self.config.get('api', {}).get('tmdb_api_key')
        if api_key:
            return api_key

        # Error if not found
        raise ValueError(
            "TMDB API key not found. Set TMDB_API_KEY environment variable or "
            "add 'tmdb_api_key' under 'api' section in config.yaml"
        )

    def make_tmdb_request(self, url, params=None, max_retries=3, timeout=15):
        """Make TMDB API request with timeout and retry logic"""
        import requests.exceptions

        if params is None:
            params = {}

        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:  # Rate limited
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"  Rate limited, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"  HTTP {response.status_code} error from TMDB API")
                    return None
            except requests.exceptions.Timeout:
                print(f"  Request timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                else:
                    print(f"  Failed after {max_retries} attempts due to timeout")
                    return None
            except requests.exceptions.RequestException as e:
                print(f"  Request error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                else:
                    print(f"  Failed after {max_retries} attempts due to request error")
                    return None

        return None
    
    def load_database(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r') as f:
                return json.load(f)
        return {'movies': {}, 'last_update': None}
    
    def save_database(self):
        self.db['last_update'] = datetime.now().isoformat()
        with open(self.db_file, 'w') as f:
            json.dump(self.db, f, indent=2)
    
    def discover_new_premieres(self, days_back=None, debug=False):
        """Discover movies that premiered in the past N days (any format: festival, theatrical, streaming)

        Uses primary_release_date which captures the first premiere worldwide.
        Provider detection happens separately in check_tracking_movies().
        """
        # Use config value if days_back not provided
        if days_back is None:
            days_back = self.discovery_days_back

        print(f"Discovering new premieres from past {days_back} days...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        new_movies = 0
        total_results = 0
        skipped_duplicates = 0

        for page in range(1, self.discovery_max_pages + 1):  # Use discovery config for pages
            url = f"https://api.themoviedb.org/3/discover/movie"
            params = {
                'api_key': self.api_key,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'page': page,
                'sort_by': 'primary_release_date.desc'
            }

            data = self.make_tmdb_request(url, params)
            if not data:
                print(f"  Failed to fetch page {page}, stopping discovery")
                break
            movies = data.get('results', [])

            if not movies:
                break

            total_results += len(movies)
            page_new = 0
            page_skipped = 0

            # Debug: Print per-page results and first 3 titles/IDs
            if debug:
                print(f"  Page {page}: {len(movies)} results")
                for i, movie in enumerate(movies[:3]):
                    print(f"    [{i+1}] {movie['title']} (ID: {movie['id']})")
                if len(movies) > 3:
                    print(f"    ... and {len(movies) - 3} more")

            for movie in movies:
                movie_id = str(movie['id'])
                if movie_id not in self.db['movies']:
                    self.db['movies'][movie_id] = {
                        'title': movie['title'],
                        'premiere_date': movie.get('release_date'),
                        'digital_date': None,
                        'has_providers': False,
                        'status': 'tracking',
                        'added': datetime.now().isoformat()
                    }
                    new_movies += 1
                    page_new += 1
                else:
                    page_skipped += 1
                    skipped_duplicates += 1

            if debug:
                print(f"    New: {page_new}, Skipped duplicates: {page_skipped}")

            time.sleep(0.2)

        print(f"  Added {new_movies} new movies to tracking")
        if debug:
            print(f"  Debug summary: {total_results} total results, {skipped_duplicates} duplicates skipped")
        return new_movies

    def bootstrap(self, days_back=730):
        """Initial population of tracking database with movies from past N days

        Populates database with all movies that premiered in the lookback window.
        Uses primary_release_date to catch first premiere (festival, theatrical, streaming, etc).
        Provider checking happens separately via check_tracking_movies().
        """
        print(f"Bootstrapping database with {days_back} days of premieres...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        for page in range(1, self.max_pages_bootstrap + 1):  # Configurable pages for bootstrap
            url = f"https://api.themoviedb.org/3/discover/movie"
            params = {
                'api_key': self.api_key,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'page': page,
                'sort_by': 'primary_release_date.desc'
            }

            data = self.make_tmdb_request(url, params)
            if not data:
                print(f"  Failed to fetch page {page}, stopping bootstrap")
                break
            movies = data.get('results', [])
            
            if not movies:
                break
                
            for movie in movies:
                movie_id = str(movie['id'])
                if movie_id not in self.db['movies']:
                    self.db['movies'][movie_id] = {
                        'title': movie['title'],
                        'premiere_date': movie.get('release_date'),
                        'digital_date': None,
                        'has_providers': False,
                        'status': 'tracking',
                        'added': datetime.now().isoformat()
                    }
            
            time.sleep(0.5)
            print(f"  Page {page}: {len(movies)} movies")
        
        self.save_database()
        print(f"Database initialized with {len(self.db['movies'])} movies")
    
    def check_tracking_movies(self, max_to_check=None, priority_days=180):
        """Check tracking movies for provider availability (monitoring component)

        Args:
            max_to_check: Maximum number of movies to check (None = all)
            priority_days: Prioritize movies released within this many days (default 180)
        """
        import random
        import requests.exceptions

        # Get all tracking movies with their IDs
        tracking_movies = [(movie_id, movie) for movie_id, movie in self.db['movies'].items()
                          if movie['status'] == 'tracking']

        print(f"Found {len(tracking_movies)} movies in tracking status")

        # Sort by premiere_date (most recent first) for smart prioritization
        def get_sort_key(item):
            movie_id, movie = item
            premiere = movie.get('premiere_date')
            if premiere:
                try:
                    return datetime.strptime(premiere, '%Y-%m-%d')
                except:
                    pass
            return datetime.min  # Put movies with no date at the end

        tracking_movies.sort(key=get_sort_key, reverse=True)

        # Apply priority window if specified
        if priority_days:
            cutoff_date = datetime.now() - timedelta(days=priority_days)
            priority_movies = []
            older_movies = []

            for movie_id, movie in tracking_movies:
                premiere = movie.get('premiere_date')
                if premiere:
                    try:
                        premiere_dt = datetime.strptime(premiere, '%Y-%m-%d')
                        if premiere_dt >= cutoff_date:
                            priority_movies.append((movie_id, movie))
                        else:
                            older_movies.append((movie_id, movie))
                    except:
                        older_movies.append((movie_id, movie))
                else:
                    older_movies.append((movie_id, movie))

            # Check priority movies first, then older ones
            tracking_movies = priority_movies + older_movies
            print(f"  Priority queue (last {priority_days} days): {len(priority_movies)} movies")
            print(f"  Older movies: {len(older_movies)} movies")

        # Limit if max_to_check specified
        if max_to_check:
            tracking_movies = tracking_movies[:max_to_check]
            print(f"  Limiting check to first {len(tracking_movies)} movies")

        newly_digital = 0
        checked = 0
        failed = 0
        total_to_check = len(tracking_movies)

        print(f"\nChecking {total_to_check} movies for providers...\n")

        try:
            for movie_id, movie in tracking_movies:
                checked += 1

                # Progress indicator every 50 movies
                if checked % 50 == 0 or checked == total_to_check:
                    progress_pct = (checked / total_to_check) * 100
                    print(f"  Progress: {checked}/{total_to_check} ({progress_pct:.1f}%) - Found {newly_digital} newly digital, {failed} failed")

                # Check providers with retry logic
                url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
                params = {'api_key': self.api_key}

                data = None
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = requests.get(url, params=params, timeout=(5, 15))
                        if response.status_code == 200:
                            data = response.json()
                            break
                        elif response.status_code == 429:  # Rate limited
                            wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                            print(f"  Rate limited on {movie['title']}, waiting {wait_time:.1f}s")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"  HTTP {response.status_code} for {movie['title']}")
                            break
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                        if attempt < max_retries - 1:
                            print(f"  Timeout/connection error for {movie['title']}, retrying in {wait_time:.1f}s")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"  Failed after {max_retries} attempts for {movie['title']}: {type(e).__name__}")
                            failed += 1
                            break
                    except requests.exceptions.RequestException as e:
                        print(f"  Request error for {movie['title']}: {type(e).__name__}")
                        failed += 1
                        break

                if data:
                    us = data.get('results', {}).get('US', {})

                    # Get all provider types
                    rent_providers = us.get('rent', [])
                    buy_providers = us.get('buy', [])
                    stream_providers = us.get('flatrate', [])  # This includes Netflix, MUBI, Shudder, etc.

                    # Extract provider names
                    rent_names = [p.get('provider_name', '') for p in rent_providers]
                    buy_names = [p.get('provider_name', '') for p in buy_providers]
                    stream_names = [p.get('provider_name', '') for p in stream_providers]

                    # Check if ANY providers exist
                    has_providers = bool(rent_names or buy_names or stream_names)

                    if has_providers and not movie['has_providers']:
                        movie['has_providers'] = True
                        movie['digital_date'] = datetime.now().isoformat()[:10]
                        movie['status'] = 'available'
                        movie['providers'] = {
                            'rent': rent_names,
                            'buy': buy_names,
                            'streaming': stream_names
                        }

                        newly_digital += 1
                        # Show which service it appeared on
                        first_service = stream_names[0] if stream_names else rent_names[0] if rent_names else buy_names[0]
                        print(f"  ✓ {movie['title']} now on {first_service}!")

                # Incremental save every 100 movies (atomic write pattern)
                if checked % 100 == 0:
                    self.save_database()
                    print(f"  💾 Progress saved (batch {checked//100})")

                time.sleep(0.2)

        except Exception as e:
            print(f"\n⚠️  Unexpected error during provider checking: {e}")
            print(f"  Processed {checked}/{total_to_check} movies before error")
        finally:
            # Always save database before exiting
            try:
                self.save_database()
                print(f"  💾 Final database save completed")
            except Exception as save_error:
                print(f"  ❌ Failed to save database: {save_error}")

        print(f"\n✅ Check complete: Found {newly_digital} newly digital movies out of {checked} checked ({failed} failed)")
        return newly_digital

    def daily(self, debug=None):
        """Complete daily update: discover new premieres + monitor for digital availability"""
        # Check debug flag from environment variable if not provided
        if debug is None:
            debug = os.environ.get('DEBUG', '').lower() in ('1', 'true', 'yes')

        print(f"=== NRW Daily Update - {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

        # Phase 1: Discover new movie premieres using config parameters
        new_movies = self.discover_new_premieres(debug=debug)

        # Phase 2: Check all tracking movies for digital availability (rent/buy/streaming)
        newly_digital = self.check_tracking_movies()

        # Phase 3: Save database
        self.save_database()

        print(f"\n📊 Summary:")
        print(f"  New premieres discovered: {new_movies}")
        print(f"  Newly digital: {newly_digital}")
        print(f"  Total tracking: {len([m for m in self.db['movies'].values() if m['status'] == 'tracking'])}")
        print(f"  Total available: {len([m for m in self.db['movies'].values() if m['status'] == 'available'])}")

        return new_movies, newly_digital

    def add_new_theatrical_releases(self, days_back=7):
        """Legacy alias - use discover_new_premieres() instead"""
        return self.discover_new_premieres(days_back)

    def check_providers(self):
        """Legacy alias - use daily() instead"""
        return self.check_tracking_movies()

# Usage
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='Movie Digital Release Tracker')
    parser.add_argument('command', nargs='?', default='daily',
                       choices=['daily', 'bootstrap', 'check', 'discovery-only', 'monitor-only'],
                       help='Command to run')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--days-back', type=int,
                       help='Override discovery window (for testing)')

    args = parser.parse_args()

    tracker = MovieTracker()

    if args.command == 'daily':
        # Full daily run: discovery + monitoring
        tracker.daily(debug=args.debug)
    elif args.command == 'discovery-only':
        # Only discover new premieres
        days_back = args.days_back if args.days_back else None
        new_movies = tracker.discover_new_premieres(days_back=days_back, debug=args.debug)
        tracker.save_database()
        print(f"\n📊 Discovery Summary: {new_movies} new movies added to tracking")
    elif args.command == 'monitor-only':
        # Only check tracking movies for providers
        newly_digital = tracker.check_tracking_movies()
        print(f"\n📊 Monitor Summary: {newly_digital} newly digital movies found")
    elif args.command == 'bootstrap':
        tracker.bootstrap()
    elif args.command == 'check':
        tracker.check_providers()  # Legacy support
    else:
        parser.print_help()
