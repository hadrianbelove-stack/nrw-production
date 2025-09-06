#!/usr/bin/env python3
"""
Enhanced Movie Tracker that captures:
- Type 1 (Premiere/Festival)
- Type 2 (Limited Theatrical)  
- Type 3 (Wide Theatrical)
- Type 4 (Digital)
- Direct-to-streaming releases
"""

import json
import os
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yaml

class EnhancedMovieTracker:
    """Enhanced tracker that captures all release types"""
    
    RELEASE_TYPES = {
        1: "Premiere",
        2: "Theatrical (limited)",
        3: "Theatrical",
        4: "Digital",
        5: "Physical",
        6: "TV"
    }
    
    def __init__(self, db_file="movie_tracking_enhanced.json"):
        self.db_file = db_file
        self.db = self.load_database()
        
        # Load API keys
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        self.tmdb_key = config.get("tmdb_api_key", "99b122ce7fa3e9065d7b7dc6e660772d")
        self.omdb_key = config.get("omdb_api_key", "539723d9")
        
    def load_database(self) -> Dict:
        """Load or create tracking database"""
        if os.path.exists(self.db_file):
            with open(self.db_file, "r") as f:
                return json.load(f)
        return {
            "movies": {},
            "last_update": None,
            "last_check": None,
            "last_bootstrap": None
        }
    
    def save_database(self):
        """Save tracking database"""
        with open(self.db_file, "w") as f:
            json.dump(self.db, f, indent=2)
        print(f"✓ Database saved to {self.db_file}")
    
    def tmdb_get(self, path, params=None):
        """Make TMDB API request"""
        url = f"https://api.themoviedb.org/3{path}"
        params = params or {}
        params["api_key"] = self.tmdb_key
        
        try:
            response = requests.get(url, params=params, timeout=10)
            time.sleep(0.5)  # Rate limiting
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"  Error: {e}")
        return None
    
    def get_enhanced_release_info(self, movie_id):
        """
        Get comprehensive release info including premieres and limited releases
        Returns earliest primary date globally and digital availability
        """
        data = self.tmdb_get(f"/movie/{movie_id}/release_dates")
        if not data:
            return {}
        
        result = {
            'primary_date': None,  # Earliest premiere/limited/theatrical anywhere
            'digital_date': None,
            'has_digital': False,
            'release_types': [],
            'us_releases': {}
        }
        
        earliest_primary = None
        digital_dates = []
        
        # Process all countries
        for country in data.get('results', []):
            country_code = country['iso_3166_1']
            
            for release in country.get('release_dates', []):
                release_type = release.get('type')
                release_date = release.get('release_date', '')[:10]
                
                if not release_date:
                    continue
                
                # Track all release types
                if release_type not in result['release_types']:
                    result['release_types'].append(release_type)
                
                # Find earliest primary release (Types 1, 2, 3)
                if release_type in [1, 2, 3]:
                    if not earliest_primary or release_date < earliest_primary:
                        earliest_primary = release_date
                
                # Collect all digital releases
                if release_type == 4:
                    digital_dates.append(release_date)
                
                # Track US releases specifically
                if country_code == 'US':
                    type_name = self.RELEASE_TYPES.get(release_type, f"Type {release_type}")
                    result['us_releases'][type_name] = release_date
        
        # Set results
        result['primary_date'] = earliest_primary
        if digital_dates:
            result['digital_date'] = min(digital_dates)
            result['has_digital'] = True
        
        return result
    
    def check_streaming_providers(self, movie_id):
        """
        Check if movie has streaming/rental providers even without Type 4 flag
        This catches movies that are available but not properly flagged
        """
        data = self.tmdb_get(f"/movie/{movie_id}/watch/providers")
        if not data:
            return False, []
        
        providers = []
        us_data = data.get('results', {}).get('US', {})
        
        # Check all provider types
        for provider_type in ['flatrate', 'rent', 'buy']:
            if provider_type in us_data:
                for provider in us_data[provider_type]:
                    providers.append({
                        'name': provider.get('provider_name'),
                        'type': provider_type
                    })
        
        # If movie has ANY providers, it's digitally available
        return len(providers) > 0, providers
    
    def should_track_movie(self, movie):
        """
        Determine if a movie should be tracked
        Now includes direct-to-streaming and festival releases
        """
        # Get release info
        movie_id = str(movie['id'])
        release_info = self.get_enhanced_release_info(movie_id)
        
        # Track if it has ANY primary release (premiere, limited, or theatrical)
        if release_info.get('primary_date'):
            return True
        
        # Also track if it has providers (direct-to-streaming)
        has_providers, _ = self.check_streaming_providers(movie_id)
        if has_providers:
            return True
        
        # Track if release date exists (catch-all)
        if movie.get('release_date'):
            return True
        
        return False
    
    def process_movie(self, movie):
        """Process a movie with enhanced tracking"""
        movie_id = str(movie['id'])
        
        # Get comprehensive release info
        release_info = self.get_enhanced_release_info(movie_id)
        has_providers, providers = self.check_streaming_providers(movie_id)
        
        # Determine if digitally available (Type 4 OR has providers)
        is_digital = release_info.get('has_digital', False) or has_providers
        
        # Use earliest date as primary
        primary_date = release_info.get('primary_date') or movie.get('release_date')
        
        movie_data = {
            "title": movie.get("title"),
            "tmdb_id": movie_id,
            "primary_date": primary_date,
            "release_date": movie.get("release_date"),
            "digital_date": release_info.get('digital_date'),
            "has_digital": is_digital,
            "providers": providers,
            "release_types": release_info.get('release_types', []),
            "us_releases": release_info.get('us_releases', {}),
            "tracking": not is_digital,
            "first_seen": datetime.now().isoformat(),
            "last_checked": datetime.now().isoformat(),
            "poster_path": movie.get("poster_path"),
            "overview": movie.get("overview", "")[:200]
        }
        
        # Status for logging
        if is_digital:
            status = "✓ Digital"
        elif 1 in release_info.get('release_types', []):
            status = "🎬 Festival"
        elif 2 in release_info.get('release_types', []):
            status = "🎭 Limited"
        else:
            status = "⏳ Tracking"
        
        print(f"  {status}: {movie.get('title')} ({primary_date or 'No date'})")
        
        return movie_data
    
    def enhanced_bootstrap(self, days_back=730, include_upcoming=True):
        """
        Enhanced bootstrap that captures more movies
        - Includes all release types
        - Searches upcoming movies too
        - Checks direct-to-streaming
        """
        print(f"🚀 Enhanced Bootstrap: Scanning {days_back} days of releases...")
        
        end_date = datetime.now() + timedelta(days=30) if include_upcoming else datetime.now()
        start_date = end_date - timedelta(days=days_back + 30)
        
        all_movies = {}
        page = 1
        total_pages = 999
        
        while page <= min(total_pages, 100):  # Limit for testing
            print(f"  Page {page}/{min(total_pages, 100)}...")
            
            # Search with broader criteria
            params = {
                "sort_by": "popularity.desc",
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page,
                "include_adult": False
            }
            
            data = self.tmdb_get("/discover/movie", params)
            if not data:
                break
            
            movies = data.get('results', [])
            if not movies:
                break
            
            # Process each movie
            for movie in movies:
                if self.should_track_movie(movie):
                    movie_id = str(movie['id'])
                    if movie_id not in all_movies and movie_id not in self.db["movies"]:
                        movie_data = self.process_movie(movie)
                        all_movies[movie_id] = movie_data
            
            total_pages = min(data.get('total_pages', 1), 500)
            page += 1
            
            # Save periodically
            if page % 10 == 0:
                self.db["movies"].update(all_movies)
                self.save_database()
                all_movies = {}
        
        # Final save
        self.db["movies"].update(all_movies)
        self.db["last_bootstrap"] = datetime.now().isoformat()
        self.save_database()
        
        # Summary
        total = len(self.db["movies"])
        digital = sum(1 for m in self.db["movies"].values() if m.get("has_digital"))
        festival = sum(1 for m in self.db["movies"].values() if 1 in m.get("release_types", []))
        limited = sum(1 for m in self.db["movies"].values() if 2 in m.get("release_types", []))
        
        print(f"\n✅ Enhanced Bootstrap Complete!")
        print(f"  Total movies: {total}")
        print(f"  Digital available: {digital}")
        print(f"  Festival releases: {festival}")
        print(f"  Limited theatrical: {limited}")
    
    def find_missing_titles(self):
        """Check for specific missing titles like Harvest and Familiar Touch"""
        print("\n🔍 Checking for known missing titles...")
        
        missing_titles = [
            ("Harvest", 2024),
            ("Familiar Touch", 2024),
            ("Familiar Touch", 2025)
        ]
        
        for title, year in missing_titles:
            # Search TMDB
            params = {"query": title, "year": year}
            data = self.tmdb_get("/search/movie", params)
            
            if data and data.get('results'):
                movie = data['results'][0]
                movie_id = str(movie['id'])
                
                if movie_id in self.db["movies"]:
                    status = "✓ In database"
                    if self.db["movies"][movie_id].get("has_digital"):
                        status += " (Digital)"
                else:
                    # Add to database
                    movie_data = self.process_movie(movie)
                    self.db["movies"][movie_id] = movie_data
                    status = "➕ Added to database"
                
                print(f"  {title} ({year}): {status}")
            else:
                print(f"  {title} ({year}): ❌ Not found in TMDB")
        
        self.save_database()

def run_full_update():
    """Function to run full automated update"""
    from colorama import init, Fore
    init()
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    NC = Fore.RESET
    
    print(f"{GREEN}🎬 Running full update...{NC}")
    
    tracker = EnhancedMovieTracker()
    
    # First, update tracking database automatically
    print(f"{YELLOW}Updating tracking database...{NC}")
    tracker.enhanced_bootstrap(days_back=30)  # Look back 30 days
    
    # Check for new digital releases from tracking
    print(f"{YELLOW}Checking for new digital releases...{NC}")
    tracker.find_missing_titles()
    
    # Generate from tracker (last 14 days default)
    print(f"{YELLOW}Generating current releases...{NC}")
    os.system("python3 generate_from_tracker.py 14")
    
    print(f"{GREEN}✓ Full update complete{NC}")

def main():
    """CLI interface"""
    import sys
    
    tracker = EnhancedMovieTracker()
    
    if len(sys.argv) < 2:
        print("Usage: python movie_tracker.py [bootstrap|check-missing|status|update|check|daily]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "bootstrap":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 730
        tracker.enhanced_bootstrap(days)
        tracker.find_missing_titles()
    
    elif command == "check-missing":
        tracker.find_missing_titles()
    
    elif command == "status":
        total = len(tracker.db["movies"])
        digital = sum(1 for m in tracker.db["movies"].values() if m.get("has_digital"))
        print(f"\n📊 Enhanced Database Status:")
        print(f"  Total movies: {total}")
        print(f"  Digital available: {digital}")
        print(f"  Database file: {tracker.db_file}")
    
    elif command in ["update", "check", "daily"]:
        run_full_update()

if __name__ == "__main__":
    main()