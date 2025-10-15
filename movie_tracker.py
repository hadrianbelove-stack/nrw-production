#!/usr/bin/env python3
"""
Movie Digital Release Tracker - Core Logic
Tracks ALL movie premieres and detects digital availability via providers
"""

import json
import os
import requests
import time
from datetime import datetime, timedelta

class MovieTracker:
    def __init__(self, db_file='movie_tracking.json'):
        self.db_file = db_file
        self.api_key = "99b122ce7fa3e9065d7b7dc6e660772d"
        self.db = self.load_database()
    
    def load_database(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r') as f:
                return json.load(f)
        return {'movies': {}, 'last_update': None}
    
    def save_database(self):
        self.db['last_update'] = datetime.now().isoformat()
        with open(self.db_file, 'w') as f:
            json.dump(self.db, f, indent=2)
    
    def discover_new_premieres(self, days_back=7):
        """Discover movies that premiered in the past N days (any format: festival, theatrical, streaming)

        Uses primary_release_date which captures the first premiere worldwide.
        Provider detection happens separately in check_tracking_movies().
        """
        print(f"Discovering new premieres from past {days_back} days...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        new_movies = 0

        for page in range(1, 10):  # Fewer pages for daily runs
            url = f"https://api.themoviedb.org/3/discover/movie"
            params = {
                'api_key': self.api_key,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'page': page,
                'sort_by': 'primary_release_date.desc',
                'vote_count.gte': 1
            }
            
            response = requests.get(url, params=params)
            movies = response.json().get('results', [])
            
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
                    new_movies += 1
            
            time.sleep(0.2)
        
        print(f"  Added {new_movies} new movies to tracking")
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

        for page in range(1, 50):  # More pages for bootstrap
            url = f"https://api.themoviedb.org/3/discover/movie"
            params = {
                'api_key': self.api_key,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'page': page,
                'sort_by': 'primary_release_date.desc',
                'vote_count.gte': 1
            }
            
            response = requests.get(url, params=params)
            movies = response.json().get('results', [])
            
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
        total_to_check = len(tracking_movies)

        print(f"\nChecking {total_to_check} movies for providers...\n")

        for movie_id, movie in tracking_movies:
            checked += 1

            # Progress indicator every 50 movies
            if checked % 50 == 0 or checked == total_to_check:
                progress_pct = (checked / total_to_check) * 100
                print(f"  Progress: {checked}/{total_to_check} ({progress_pct:.1f}%) - Found {newly_digital} newly digital")

            # Check providers
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
            response = requests.get(url, params={'api_key': self.api_key})

            if response.status_code == 200:
                us = response.json().get('results', {}).get('US', {})

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

        # Final save
        self.save_database()

        print(f"\n✅ Check complete: Found {newly_digital} newly digital movies out of {checked} checked")
        return newly_digital

    def daily(self):
        """Complete daily update: discover new premieres + monitor for digital availability"""
        print(f"=== NRW Daily Update - {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

        # Phase 1: Discover new movie premieres from past 7 days
        new_movies = self.discover_new_premieres(days_back=7)

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
    tracker = MovieTracker()
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'daily':
            tracker.daily()
        elif command == 'bootstrap':
            tracker.bootstrap()
        elif command == 'check':
            tracker.check_providers()  # Legacy support
        else:
            print("Usage: python movie_tracker.py [daily|bootstrap|check]")
            print("  daily     - Add new releases + check all for providers (recommended)")
            print("  bootstrap - Initial database population (one-time)")
            print("  check     - Legacy command (use 'daily' instead)")
    else:
        # Default to daily if no command specified
        tracker.daily()
