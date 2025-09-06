#!/usr/bin/env python3
"""
Movie Digital Release Tracker
Maintains a database of movies and tracks when they go digital
"""

import json
import requests
import yaml
from datetime import datetime, timedelta
import time
import os

class MovieTracker:
    def __init__(self, db_file='movie_tracking.json'):
        self.db_file = db_file
        self.db = self.load_database()
        self.config = self.load_config()
        self.api_key = self.config['tmdb_api_key']
        self.omdb_api_key = self.config.get('omdb_api_key')
    
    def load_config(self):
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    
    def load_database(self):
        """Load existing tracking database or create new one"""
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r') as f:
                return json.load(f)
        return {
            'movies': {},
            'last_update': None,
            'stats': {
                'total_tracked': 0,
                'resolved': 0,
                'still_tracking': 0
            }
        }
    
    def save_database(self):
        """Save tracking database to disk"""
        self.db['last_update'] = datetime.now().isoformat()
        
        # Update stats
        movies = self.db['movies']
        self.db['stats'] = {
            'total_tracked': len(movies),
            'resolved': len([m for m in movies.values() if m.get('status') == 'resolved']),
            'still_tracking': len([m for m in movies.values() if m.get('status') == 'tracking'])
        }
        
        with open(self.db_file, 'w') as f:
            json.dump(self.db, f, indent=2)
        
        print(f"💾 Database saved: {self.db['stats']}")
    
    def tmdb_get(self, endpoint, params):
        """Generic TMDB API GET request"""
        url = f"https://api.themoviedb.org/3{endpoint}"
        params['api_key'] = self.api_key
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API error: {e}")
            return {}
    
    def get_release_info(self, movie_id):
        """Get release dates for a movie - enhanced to include premieres and limited releases"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            result = {
                'theatrical_date': None,  # Now represents earliest primary release (premiere/limited/theatrical)
                'digital_date': None,
                'has_digital': False
            }
            
            # Track earliest dates globally for primary releases
            earliest_primary_date = None
            us_digital_date = None
            
            if 'results' in data:
                # First pass: Find earliest primary release date anywhere (Types 1, 2, 3)
                for country_data in data['results']:
                    for release in country_data.get('release_dates', []):
                        release_type = release.get('type')
                        date = release.get('release_date', '')[:10]
                        
                        if date and release_type in [1, 2, 3]:  # Premiere, Limited, Theatrical
                            if not earliest_primary_date or date < earliest_primary_date:
                                earliest_primary_date = date
                
                # Second pass: Find US digital release (Type 4)
                for country_data in data['results']:
                    if country_data['iso_3166_1'] == 'US':
                        for release in country_data.get('release_dates', []):
                            release_type = release.get('type')
                            date = release.get('release_date', '')[:10]
                            
                            if release_type == 4:  # Digital
                                if not us_digital_date or date < us_digital_date:
                                    us_digital_date = date
                        break
                
                # If no US digital, check other countries as fallback
                if not us_digital_date:
                    for country_data in data['results']:
                        for release in country_data.get('release_dates', []):
                            release_type = release.get('type')
                            date = release.get('release_date', '')[:10]
                            
                            if release_type == 4:  # Digital
                                if not us_digital_date or date < us_digital_date:
                                    us_digital_date = date
            
            # Set results
            result['theatrical_date'] = earliest_primary_date
            result['digital_date'] = us_digital_date
            result['has_digital'] = bool(us_digital_date)
            
            return result
        except Exception as e:
            print(f"Error getting release info for {movie_id}: {e}")
            return None
    
    def get_rt_score_direct(self, title, year):
        """Get RT score by searching RT directly via web fetch"""
        try:
            import urllib.parse
            # Create search URL for RT
            search_query = f"{title} {year}" if year else title
            search_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(search_query)}"
            
            # Use WebFetch to get RT scores
            # This is a placeholder - would need WebFetch tool access
            return None
        except Exception as e:
            print(f"Error getting direct RT score for {title}: {e}")
        return None

    def get_omdb_rt_score(self, title, year):
        """Get Rotten Tomatoes score from OMDb API with direct RT fallback"""
        # First try OMDb API
        if self.omdb_api_key:
            try:
                params = {'apikey': self.omdb_api_key, 't': title}
                if year:
                    params['y'] = str(year)
                    
                response = requests.get('http://www.omdbapi.com/', params=params)
                data = response.json()
                
                if data.get('Response') == 'True':
                    for rating in data.get('Ratings', []):
                        if rating['Source'] == 'Rotten Tomatoes':
                            return int(rating['Value'].rstrip('%'))
            except Exception as e:
                print(f"Error getting OMDb RT score for {title}: {e}")
        
        # If OMDb fails, try direct RT lookup (future enhancement)
        # return self.get_rt_score_direct(title, year)
        return None
    
    def bootstrap_database(self, days_back=730):
        """Bootstrap database with movies from past N days"""
        print(f"🚀 Bootstrapping database with movies from last {days_back} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        all_movies = []
        page = 1
        total_pages = 999  # Will be updated from API response
        
        # Standard discovery
        while page <= total_pages:
            print(f"  Scanning page {page} (standard discovery)...")
            
            params = {
                "sort_by": "primary_release_date.desc",
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page
            }
            
            data = self.tmdb_get("/discover/movie", params)
            all_movies.extend(data.get("results", []))
            
            # Update total_pages from API
            total_pages = min(data.get("total_pages", 1), 500)  # TMDB caps at 500
            
            if page >= total_pages:
                break
                
            page += 1
            time.sleep(0.2)
        
        # Enhanced discovery for indie films (no popularity filtering)
        print(f"  Enhanced discovery for indie films...")
        
        # Discover by indie production companies
        indie_companies = [41077, 2, 491, 25, 61, 11072, 7505]  # A24, Neon, Focus, IFC, etc.
        for company_id in indie_companies:
            for comp_page in range(1, 3):  # First 2 pages per company
                params = {
                    "with_companies": str(company_id),
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "sort_by": "release_date.desc",
                    "page": comp_page
                }
                
                comp_data = self.tmdb_get("/discover/movie", params)
                comp_movies = comp_data.get("results", [])
                
                # Filter out duplicates
                existing_ids = {str(m['id']) for m in all_movies}
                new_movies = [m for m in comp_movies if str(m['id']) not in existing_ids]
                all_movies.extend(new_movies)
                
                if new_movies:
                    print(f"    Company {company_id}: +{len(new_movies)} indie films")
                
                if not comp_movies or comp_page >= comp_data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        # Discover by alternative sorting (catches low-popularity films)
        for sort_method in ["vote_average.desc", "vote_count.asc"]:
            for sort_page in range(1, 3):
                params = {
                    "sort_by": sort_method,
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "page": sort_page
                }
                
                sort_data = self.tmdb_get("/discover/movie", params)
                sort_movies = sort_data.get("results", [])
                
                # Filter out duplicates
                existing_ids = {str(m['id']) for m in all_movies}
                new_movies = [m for m in sort_movies if str(m['id']) not in existing_ids]
                all_movies.extend(new_movies)
                
                if new_movies:
                    print(f"    {sort_method}: +{len(new_movies)} additional films")
                
                if not sort_movies or sort_page >= sort_data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        print(f"  Found {len(all_movies)} movies, checking release status...")
        
        # Add movies to tracking database
        for i, movie in enumerate(all_movies):
            if i % 20 == 0:
                print(f"    Processed {i}/{len(all_movies)} movies...")
            
            movie_id = str(movie['id'])
            if movie_id in self.db['movies']:
                continue  # Already tracking
            
            release_info = self.get_release_info(movie['id'])
            if not release_info:
                continue
            
            # Get RT score
            year = None
            if release_info['theatrical_date']:
                year = release_info['theatrical_date'][:4]
            rt_score = self.get_omdb_rt_score(movie['title'], year)
            
            # Add to database
            self.db['movies'][movie_id] = {
                'title': movie['title'],
                'tmdb_id': movie['id'],
                'theatrical_date': release_info['theatrical_date'],
                'digital_date': release_info['digital_date'],
                'rt_score': rt_score,
                'status': 'resolved' if release_info['has_digital'] else 'tracking',
                'added_to_db': datetime.now().isoformat()[:10],
                'last_checked': datetime.now().isoformat()[:10]
            }
            
            time.sleep(0.1)  # Rate limiting
        
        self.save_database()
        print(f"✅ Bootstrap complete!")
    
    def add_new_theatrical_releases(self, days_back=7):
        """Daily: Add new theatrical releases from last X days (including low-popularity indie films)"""
        print(f"➕ Adding new releases from last {days_back} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        all_movies = []
        
        # Standard discovery by release date (no popularity filtering)
        params = {
            'api_key': self.api_key,
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'primary_release_date.desc',  # Changed from popularity.desc
            'page': 1
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        movies = response.json().get('results', [])
        all_movies.extend(movies)
        
        # Enhanced discovery for indie films
        print(f"  🎭 Also searching indie studios...")
        indie_companies = [41077, 2, 491, 25, 61]  # A24, Neon, Focus, IFC, Magnolia
        for company_id in indie_companies:
            params = {
                'api_key': self.api_key,
                'with_companies': str(company_id),
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'release_date.desc',
                'page': 1
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            company_movies = response.json().get('results', [])
            
            # Add unique movies only
            existing_ids = {str(m['id']) for m in all_movies}
            new_movies = [m for m in company_movies if str(m['id']) not in existing_ids]
            all_movies.extend(new_movies)
            
            if new_movies:
                print(f"    Company {company_id}: +{len(new_movies)} indie films")
        
        movies = all_movies  # Use combined results
        
        new_count = 0
        for movie in movies:
            movie_id = str(movie['id'])
            if movie_id not in self.db['movies']:
                release_info = self.get_release_info(movie['id'])
                if release_info and release_info['theatrical_date']:
                    # Get RT score
                    year = release_info['theatrical_date'][:4]
                    rt_score = self.get_omdb_rt_score(movie['title'], year)
                    
                    self.db['movies'][movie_id] = {
                        'title': movie['title'],
                        'tmdb_id': movie['id'],
                        'theatrical_date': release_info['theatrical_date'],
                        'digital_date': release_info['digital_date'],
                        'rt_score': rt_score,
                        'status': 'resolved' if release_info['has_digital'] else 'tracking',
                        'added_to_db': datetime.now().isoformat()[:10],
                        'last_checked': datetime.now().isoformat()[:10]
                    }
                    new_count += 1
                    print(f"  ➕ Added: {movie['title']} (RT: {rt_score}%)" if rt_score else f"  ➕ Added: {movie['title']}")
                
                time.sleep(0.1)
        
        print(f"✅ Added {new_count} new movies")
        return new_count
    
    def check_tracking_movies(self):
        """Check digital status for movies still being tracked"""
        tracking_movies = {k: v for k, v in self.db['movies'].items() 
                          if v['status'] == 'tracking'}
        
        if not tracking_movies:
            print("📭 No movies currently being tracked")
            return 0
        
        print(f"🔍 Checking {len(tracking_movies)} movies for digital availability...")
        
        resolved_count = 0
        for movie_id, movie_data in tracking_movies.items():
            release_info = self.get_release_info(int(movie_id))
            if release_info and release_info['has_digital']:
                # Movie went digital!
                movie_data['digital_date'] = release_info['digital_date']
                movie_data['status'] = 'resolved'
                movie_data['last_checked'] = datetime.now().isoformat()[:10]
                resolved_count += 1
                
                print(f"  ✅ {movie_data['title']} went digital: {release_info['digital_date']}")
            else:
                movie_data['last_checked'] = datetime.now().isoformat()[:10]
            
            time.sleep(0.1)
        
        print(f"✅ Found {resolved_count} newly digital movies")
        return resolved_count
    
    def daily_update(self):
        """Run daily update: add new + check existing"""
        print("📅 Running daily update...")
        new_movies = self.add_new_theatrical_releases()
        newly_digital = self.check_tracking_movies()
        self.save_database()
        
        print(f"\n📊 Daily Summary:")
        print(f"  New movies added: {new_movies}")
        print(f"  Movies that went digital: {newly_digital}")
        print(f"  Still tracking: {self.db['stats']['still_tracking']}")
    
    def backfill_rt_scores(self):
        """Add RT scores to existing movies that don't have them"""
        movies_without_rt = {k: v for k, v in self.db['movies'].items() 
                           if not v.get('rt_score')}
        
        if not movies_without_rt:
            print("✅ All movies already have RT scores")
            return 0
        
        print(f"🍅 Backfilling RT scores for {len(movies_without_rt)} movies...")
        
        updated_count = 0
        for movie_id, movie_data in movies_without_rt.items():
            # Get year from theatrical or digital date
            year = None
            if movie_data.get('theatrical_date'):
                year = movie_data['theatrical_date'][:4]
            elif movie_data.get('digital_date'):
                year = movie_data['digital_date'][:4]
            
            rt_score = self.get_omdb_rt_score(movie_data['title'], year)
            if rt_score:
                movie_data['rt_score'] = rt_score
                updated_count += 1
                print(f"  ✅ {movie_data['title']}: {rt_score}%")
            else:
                movie_data['rt_score'] = None
                print(f"  ❌ {movie_data['title']}: No RT score found")
            
            time.sleep(0.2)  # Rate limiting for OMDb API
        
        print(f"✅ Updated {updated_count} movies with RT scores")
        self.save_database()
        return updated_count

    def show_status(self):
        """Show current database status"""
        stats = self.db['stats']
        print(f"\n📊 TRACKING DATABASE STATUS")
        print(f"{'='*40}")
        print(f"Total movies tracked: {stats['total_tracked']}")
        print(f"Resolved (went digital): {stats['resolved']}")
        print(f"Still tracking: {stats['still_tracking']}")
        print(f"Last update: {self.db.get('last_update', 'Never')}")
        
        # Show some examples
        tracking = {k: v for k, v in self.db['movies'].items() if v['status'] == 'tracking'}
        if tracking:
            print(f"\nCurrently tracking (sample):")
            for movie_id, movie in list(tracking.items())[:5]:
                days_since = (datetime.now() - datetime.fromisoformat(movie['theatrical_date'])).days
                print(f"  • {movie['title']} - {days_since} days since theatrical")
        
        recent_digital = {k: v for k, v in self.db['movies'].items() 
                         if v['status'] == 'resolved' and v.get('digital_date')}
        if recent_digital:
            print(f"\nRecently went digital (sample):")
            for movie_id, movie in list(recent_digital.items())[:5]:
                rt_text = f" (RT: {movie.get('rt_score')}%)" if movie.get('rt_score') else ""
                print(f"  • {movie['title']} - Digital: {movie.get('digital_date')}{rt_text}")

def main():
    tracker = MovieTracker()
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'bootstrap':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 365
            tracker.bootstrap_database(days)
        elif command == 'daily':
            tracker.daily_update()
        elif command == 'status':
            tracker.show_status()
        elif command == 'backfill-rt':
            tracker.backfill_rt_scores()
        else:
            print("Usage: python movie_tracker.py [bootstrap|daily|status|backfill-rt]")
    else:
        tracker.show_status()

if __name__ == "__main__":
    main()