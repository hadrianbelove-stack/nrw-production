#!/usr/bin/env python3
"""
Enhanced discovery system that includes low-popularity indie films
"""

import requests
import json
import time
from datetime import datetime, timedelta

class EnhancedDiscovery:
    def __init__(self):
        with open('config.yaml', 'r') as f:
            import yaml
            config = yaml.safe_load(f)
        self.api_key = config['tmdb_api_key']
        
    def tmdb_get(self, endpoint, params=None):
        """Make TMDB API request"""
        if params is None:
            params = {}
        params['api_key'] = self.api_key
        
        url = f"https://api.themoviedb.org/3{endpoint}"
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            return response.json()
        return {}
    
    def discover_with_multiple_approaches(self, start_date, end_date):
        """Use multiple discovery approaches to catch indie films"""
        all_movies = set()
        
        print("🔍 Enhanced Discovery: Multiple approaches to find ALL films...")
        
        # Approach 1: Standard discovery (catches mainstream films)
        print("  📈 Approach 1: Standard popularity-based discovery")
        movies = self.standard_discovery(start_date, end_date)
        all_movies.update([str(m['id']) for m in movies])
        print(f"    Found {len(movies)} mainstream films")
        
        # Approach 2: Company-based discovery (catches studio indies)
        print("  🎭 Approach 2: Studio/company-based discovery")
        indie_companies = [
            41077,   # A24
            2,       # Neon
            491,     # Focus Features  
            25,      # IFC Films
            61,      # Magnolia Pictures
            11072,   # Searchlight Pictures
            7505,    # Bleecker Street
            1632,    # Lionsgate
            33,      # Universal Pictures (includes Focus)
        ]
        
        company_movies = self.discover_by_companies(indie_companies, start_date, end_date)
        new_company_movies = [m for m in company_movies if str(m['id']) not in all_movies]
        all_movies.update([str(m['id']) for m in company_movies])
        print(f"    Found {len(new_company_movies)} additional studio films")
        
        # Approach 3: Genre-based discovery (catches documentaries, foreign films)
        print("  🎬 Approach 3: Genre-based discovery")
        indie_genres = [99, 18, 10749, 53, 37]  # Documentary, Drama, Romance, Thriller, Western
        genre_movies = self.discover_by_genres(indie_genres, start_date, end_date)
        new_genre_movies = [m for m in genre_movies if str(m['id']) not in all_movies]
        all_movies.update([str(m['id']) for m in genre_movies])
        print(f"    Found {len(new_genre_movies)} additional genre films")
        
        # Approach 4: Sort by different criteria (catches overlooked films)
        print("  📊 Approach 4: Alternative sorting methods")
        sort_methods = ['release_date.desc', 'vote_average.desc', 'vote_count.desc']
        
        for sort_method in sort_methods:
            sorted_movies = self.discover_by_sort(sort_method, start_date, end_date)
            new_sorted_movies = [m for m in sorted_movies if str(m['id']) not in all_movies]
            all_movies.update([str(m['id']) for m in sorted_movies])
            if new_sorted_movies:
                print(f"    {sort_method}: Found {len(new_sorted_movies)} additional films")
        
        # Convert back to movie objects
        final_movies = []
        for movie_id in all_movies:
            # Get movie details
            movie_data = self.tmdb_get(f"/movie/{movie_id}")
            if movie_data:
                final_movies.append(movie_data)
        
        print(f"\n✅ Total unique films discovered: {len(final_movies)}")
        return final_movies
    
    def standard_discovery(self, start_date, end_date):
        """Standard TMDB discovery"""
        all_movies = []
        
        for page in range(1, 11):  # First 10 pages
            params = {
                "sort_by": "primary_release_date.desc",
                "region": "US",
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page
            }
            
            data = self.tmdb_get("/discover/movie", params)
            movies = data.get("results", [])
            all_movies.extend(movies)
            
            if not movies or page >= data.get("total_pages", 1):
                break
            
            time.sleep(0.1)
        
        return all_movies
    
    def discover_by_companies(self, company_ids, start_date, end_date):
        """Discover films by production companies"""
        all_movies = []
        
        for company_id in company_ids:
            for page in range(1, 6):  # First 5 pages per company
                params = {
                    "with_companies": str(company_id),
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "sort_by": "release_date.desc",
                    "page": page
                }
                
                data = self.tmdb_get("/discover/movie", params)
                movies = data.get("results", [])
                all_movies.extend(movies)
                
                if not movies or page >= data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        return all_movies
    
    def discover_by_genres(self, genre_ids, start_date, end_date):
        """Discover films by genres"""
        all_movies = []
        
        for genre_id in genre_ids:
            for page in range(1, 4):  # First 3 pages per genre
                params = {
                    "with_genres": str(genre_id),
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "sort_by": "release_date.desc",
                    "page": page
                }
                
                data = self.tmdb_get("/discover/movie", params)
                movies = data.get("results", [])
                all_movies.extend(movies)
                
                if not movies or page >= data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        return all_movies
    
    def discover_by_sort(self, sort_method, start_date, end_date):
        """Discover films using different sorting methods"""
        all_movies = []
        
        for page in range(1, 6):  # First 5 pages
            params = {
                "sort_by": sort_method,
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page
            }
            
            data = self.tmdb_get("/discover/movie", params)
            movies = data.get("results", [])
            all_movies.extend(movies)
            
            if not movies or page >= data.get("total_pages", 1):
                break
            
            time.sleep(0.1)
        
        return all_movies
    
    def test_missing_films(self):
        """Test if our enhanced discovery finds the previously missing films"""
        print("\n🎯 Testing enhanced discovery on known missing films...")
        
        missing_films = [
            ('Pavements', 1063307),
            ('Blue Sun Palace', 1274751)
        ]
        
        # Get their release dates
        for title, movie_id in missing_films:
            movie_data = self.tmdb_get(f"/movie/{movie_id}")
            if movie_data:
                release_date = movie_data.get('release_date')
                if release_date:
                    release_dt = datetime.strptime(release_date, '%Y-%m-%d')
                    start_test = release_dt - timedelta(days=30)
                    end_test = release_dt + timedelta(days=30)
                    
                    print(f"\n  Testing {title} around {release_date}...")
                    discovered_movies = self.discover_with_multiple_approaches(start_test, end_test)
                    
                    found = any(str(m['id']) == str(movie_id) for m in discovered_movies)
                    if found:
                        print(f"    ✅ {title} FOUND with enhanced discovery!")
                    else:
                        print(f"    ❌ {title} still not found - need more approaches")

if __name__ == "__main__":
    discovery = EnhancedDiscovery()
    discovery.test_missing_films()