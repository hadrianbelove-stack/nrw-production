#!/usr/bin/env python3
"""
Comprehensive indie and foreign film finder
Uses multiple search strategies to find everything
"""

import json
import requests
import time
from datetime import datetime, timedelta

class IndiFilmFinder:
    def __init__(self):
        self.api_key = "99b122ce7fa3e9065d7b7dc6e660772d"
        self.found_movies = set()
        self.new_additions = 0
        
    def load_database(self):
        with open('movie_tracking.json', 'r') as f:
            self.db = json.load(f)
        print(f"Loaded database with {len(self.db['movies'])} movies")
        
    def save_database(self):
        with open('movie_tracking.json', 'w') as f:
            json.dump(self.db, f, indent=2)
        print(f"Saved database with {len(self.db['movies'])} movies")
    
    def check_providers(self, movie_id):
        """Check if movie has any digital providers"""
        try:
            response = requests.get(
                f'https://api.themoviedb.org/3/movie/{movie_id}/watch/providers',
                params={'api_key': self.api_key}
            )
            if response.status_code == 200:
                us_providers = response.json().get('results', {}).get('US', {})
                return any([
                    us_providers.get('rent'),
                    us_providers.get('buy'),
                    us_providers.get('flatrate')
                ])
        except:
            pass
        return False
    
    def add_movie(self, movie):
        """Add movie to database if not exists"""
        movie_id = str(movie['id'])
        
        if movie_id in self.db['movies'] or movie_id in self.found_movies:
            return False
        
        # Check if it has digital availability
        time.sleep(0.3)  # Rate limit
        has_providers = self.check_providers(movie_id)
        
        if has_providers:
            print(f"  + Adding: {movie['title']} ({movie.get('release_date', 'No date')[:4]})")
            
            # Get release dates
            release_response = requests.get(
                f'https://api.themoviedb.org/3/movie/{movie_id}/release_dates',
                params={'api_key': self.api_key}
            )
            
            digital_date = None
            if release_response.status_code == 200:
                for country in release_response.json().get('results', []):
                    if country['iso_3166_1'] == 'US':
                        for release in country['release_dates']:
                            if release['type'] == 4:  # Digital
                                digital_date = release['release_date'][:10]
                                break
                            elif release['type'] == 2 and not digital_date:  # Limited theatrical
                                digital_date = release['release_date'][:10]
            
            self.db['movies'][movie_id] = {
                'title': movie['title'],
                'tmdb_id': movie_id,
                'release_date': movie.get('release_date'),
                'digital_date': digital_date,
                'has_digital': True,
                'poster_path': movie.get('poster_path'),
                'overview': movie.get('overview', '')[:200],
                'original_language': movie.get('original_language'),
                'added_date': datetime.now().isoformat(),
                'source': 'indie_finder'
            }
            
            self.found_movies.add(movie_id)
            self.new_additions += 1
            return True
        return False
    
    def search_by_company(self, company_name, company_id):
        """Search for films by production company (great for indie studios)"""
        print(f"\n🎬 Searching {company_name} films...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        params = {
            'api_key': self.api_key,
            'with_companies': company_id,
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'release_date.desc'
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        if response.status_code == 200:
            movies = response.json().get('results', [])
            for movie in movies:
                self.add_movie(movie)
    
    def search_festival_winners(self):
        """Search for festival films"""
        print("\n🏆 Searching festival and award winners...")
        
        # Search by keywords related to festivals
        festival_keywords = ['sundance', 'cannes', 'venice', 'toronto', 'sxsw', 'tribeca']
        
        for keyword in festival_keywords:
            params = {
                'api_key': self.api_key,
                'query': keyword,
                'primary_release_year': 2024
            }
            
            response = requests.get('https://api.themoviedb.org/3/search/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])
                for movie in movies:
                    self.add_movie(movie)
    
    def search_foreign_films(self):
        """Search foreign language films"""
        print("\n🌍 Searching foreign language films...")
        
        languages = ['fr', 'es', 'de', 'it', 'ja', 'ko', 'zh', 'ru', 'pt', 'hi', 'ar']
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)
        
        for lang in languages:
            params = {
                'api_key': self.api_key,
                'with_original_language': lang,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc',
                'page': 1
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])[:10]  # Top 10 per language
                for movie in movies:
                    self.add_movie(movie)
    
    def search_limited_releases(self):
        """Search for limited theatrical releases"""
        print("\n📽️ Searching limited theatrical releases...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        params = {
            'api_key': self.api_key,
            'with_release_type': '2|1',  # Limited theatrical and premieres
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'region': 'US',
            'sort_by': 'popularity.desc'
        }
        
        for page in range(1, 4):  # First 3 pages
            params['page'] = page
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])
                for movie in movies:
                    self.add_movie(movie)
    
    def search_streaming_originals(self):
        """Search for streaming platform originals"""
        print("\n📺 Searching streaming originals...")
        
        # Platform provider IDs
        platforms = {
            '8': 'Netflix',
            '337': 'Disney Plus',
            '350': 'Apple TV+',
            '9': 'Amazon Prime',
            '384': 'HBO Max',
            '531': 'Paramount+',
            '387': 'Peacock'
        }
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        for provider_id, name in platforms.items():
            print(f"  Checking {name}...")
            params = {
                'api_key': self.api_key,
                'with_watch_providers': provider_id,
                'watch_region': 'US',
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc'
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])[:5]  # Top 5 per platform
                for movie in movies:
                    self.add_movie(movie)
    
    def run_comprehensive_search(self):
        """Run all search methods"""
        print("🔍 Starting comprehensive indie/foreign film search...\n")
        
        self.load_database()
        
        # Run all search methods
        self.search_limited_releases()
        self.search_foreign_films()
        self.search_festival_winners()
        self.search_streaming_originals()
        
        # Search specific indie studios
        indie_studios = [
            ('A24', '41077'),
            ('Neon', '90733'),
            ('IFC Films', '307'),
            ('Focus Features', '10146'),
            ('Magnolia Pictures', '1030'),
            ('Bleecker Street', '19414'),
            ('Searchlight Pictures', '127928')
        ]
        
        for studio_name, studio_id in indie_studios:
            self.search_by_company(studio_name, studio_id)
        
        self.save_database()
        
        print(f"\n✅ Complete! Added {self.new_additions} new indie/foreign films")
        print(f"Total database size: {len(self.db['movies'])} movies")

if __name__ == "__main__":
    finder = IndiFilmFinder()
    finder.run_comprehensive_search()
