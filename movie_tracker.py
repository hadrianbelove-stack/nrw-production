#!/usr/bin/env python3
"""
Movie Digital Release Tracker - Core Logic
Tracks theatrical releases and detects digital availability via providers
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
    
    def bootstrap(self, days_back=730):
        """Initial population with theatrical releases"""
        print(f"Bootstrapping with {days_back} days of releases...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        for page in range(1, 10):  # First 10 pages
            url = f"https://api.themoviedb.org/3/discover/movie"
            params = {
                'api_key': self.api_key,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'page': page
            }
            
            response = requests.get(url, params=params)
            movies = response.json().get('results', [])
            
            for movie in movies:
                movie_id = str(movie['id'])
                if movie_id not in self.db['movies']:
                    self.db['movies'][movie_id] = {
                        'title': movie['title'],
                        'theatrical_date': movie.get('release_date'),
                        'digital_date': None,
                        'has_providers': False,
                        'status': 'tracking',
                        'added': datetime.now().isoformat()
                    }
            
            time.sleep(0.5)
            print(f"  Page {page}: {len(movies)} movies")
        
        self.save_database()
        print(f"Database initialized with {len(self.db['movies'])} movies")
    
    def check_providers(self):
        """Check tracking movies for provider availability"""
        tracking = [m for m in self.db['movies'].values() if m['status'] == 'tracking']
        print(f"Checking {len(tracking)} movies for providers...")
        
        newly_digital = 0
        for movie_id, movie in self.db['movies'].items():
            if movie['status'] != 'tracking':
                continue
            
            # Check providers
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
            response = requests.get(url, params={'api_key': self.api_key})
            
            if response.status_code == 200:
                us = response.json().get('results', {}).get('US', {})
                has_providers = bool(us.get('rent') or us.get('buy'))
                
                if has_providers and not movie['has_providers']:
                    # Movie just became available!
                    movie['has_providers'] = True
                    movie['digital_date'] = datetime.now().isoformat()[:10]
                    movie['status'] = 'available'
                    newly_digital += 1
                    print(f"  ✓ {movie['title']} now available!")
            
            time.sleep(0.2)
        
        self.save_database()
        print(f"Found {newly_digital} newly digital movies")
        return newly_digital

# Usage
if __name__ == "__main__":
    tracker = MovieTracker()
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'bootstrap':
        tracker.bootstrap()
    elif len(sys.argv) > 1 and sys.argv[1] == 'check':
        tracker.check_providers()
    else:
        print("Usage: python movie_tracker.py [bootstrap|check]")