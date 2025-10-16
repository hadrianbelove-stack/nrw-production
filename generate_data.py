#!/usr/bin/env python3
"""
Generate display data from tracking database with enriched links
"""

import json
import requests
import yaml
from datetime import datetime, timedelta
import time
import os
import re
from urllib.parse import quote

class DataGenerator:
    def __init__(self):
        self.config = self.load_config()
        self.tmdb_key = self.config['tmdb_api_key']
        self.wikipedia_cache = self.load_cache('wikipedia_cache.json')
        self.rt_cache = self.load_cache('rt_cache.json')
        self.wikipedia_overrides = self.load_cache('overrides/wikipedia_overrides.json')
        self.rt_overrides = self.load_cache('overrides/rt_overrides.json')
    
    def load_config(self):
        # API key from PROJECT_CHARTER.md
        return {'tmdb_api_key': '99b122ce7fa3e9065d7b7dc6e660772d'}
    
    def load_cache(self, filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return {}
    
    def save_cache(self, data, filename):
        os.makedirs(os.path.dirname(filename) if '/' in filename else '.', exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_movie_details(self, movie_id):
        """Get full movie details from TMDB"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {
            'api_key': self.tmdb_key,
            'append_to_response': 'credits,videos,external_ids'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching details for {movie_id}: {e}")
        return None
    
    def find_wikipedia_url(self, title, year, imdb_id, movie_id=None):
        """Find Wikipedia URL using waterfall approach"""
        # 1. Check overrides first
        if imdb_id and imdb_id in self.wikipedia_overrides:
            return f"https://en.wikipedia.org/wiki/{self.wikipedia_overrides[imdb_id]}"

        # 2. Check cache
        cache_key = f"{title}_{year}"
        if cache_key in self.wikipedia_cache:
            cached_data = self.wikipedia_cache[cache_key]
            if isinstance(cached_data, dict):
                return cached_data.get('url')
            return cached_data

        # 3. Try Wikipedia API search
        try:
            # Try exact match with (year film) suffix
            search_title = f"{title} ({year} film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    self.wikipedia_cache[cache_key] = {'url': wiki_url, 'title': title, 'cached_at': datetime.now().isoformat()}
                    return wiki_url

            # Try without year
            search_title = f"{title} (film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    self.wikipedia_cache[cache_key] = {'url': wiki_url, 'title': title, 'cached_at': datetime.now().isoformat()}
                    return wiki_url

        except Exception as e:
            print(f"Wikipedia search error for {title}: {e}")

        # 4. Log as missing and return null (only if movie_id is provided)
        if movie_id:
            self.log_missing_wikipedia(movie_id, title, year, imdb_id)
        return None
    
    def log_missing_wikipedia(self, movie_id, title, year, imdb_id):
        """Log missing Wikipedia links for manual review"""
        try:
            missing_file = 'missing_wikipedia.json'
            if os.path.exists(missing_file):
                with open(missing_file, 'r') as f:
                    missing = json.load(f)
            else:
                missing = {"missing": []}
            
            entry = {
                "tmdb_id": movie_id,
                "title": title,
                "year": year,
                "imdb_id": imdb_id,
                "timestamp": datetime.now().isoformat()
            }
            
            # Avoid duplicates
            if not any(m['tmdb_id'] == movie_id for m in missing['missing']):
                missing['missing'].append(entry)
                with open(missing_file, 'w') as f:
                    json.dump(missing, f, indent=2)
        except Exception as e:
            print(f"Failed to log missing Wikipedia: {e}")
    
    def find_trailer_url(self, movie_details):
        """Extract trailer URL from TMDB movie details"""
        videos = movie_details.get('videos', {}).get('results', [])
        
        # Prioritize official trailers
        for video in videos:
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"
        
        # Fall back to any YouTube video
        for video in videos:
            if video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"
        
        # Generate YouTube search as fallback
        title = movie_details.get('title', '')
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''
        search_query = quote(f"{title} {year} trailer")
        return f"https://www.youtube.com/results?search_query={search_query}"
    
    def find_rt_url(self, title, year, imdb_id):
        """Find Rotten Tomatoes URL"""
        # 1. Check overrides first
        if imdb_id and imdb_id in self.rt_overrides:
            return self.rt_overrides[imdb_id]
        
        # 2. Check cache
        cache_key = f"{title}_{year}"
        if cache_key in self.rt_cache:
            cached_data = self.rt_cache[cache_key]
            if isinstance(cached_data, dict):
                return cached_data.get('url')
            return cached_data
        
        # 3. Fall back to search
        search_query = quote(f"{title} {year}")
        return f"https://www.rottentomatoes.com/search?search={search_query}"
    
    def process_movie(self, movie_id, movie_data, movie_details):
        """Process a single movie into display format"""
        if not movie_details:
            return None
        
        title = movie_details['title']
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')
        
        # Extract key people
        credits = movie_details.get('credits', {})
        director = "Unknown"
        cast = []
        
        for crew in credits.get('crew', []):
            if crew['job'] == 'Director':
                director = crew['name']
                break
        
        for actor in credits.get('cast', [])[:2]:  # Top 2 actors
            cast.append(actor['name'])
        
        # Extract additional metadata
        genres = [g['name'] for g in movie_details.get('genres', [])]
        studio = None
        production_companies = movie_details.get('production_companies', [])
        if production_companies:
            studio = production_companies[0]['name']
        
        runtime = movie_details.get('runtime')
        
        # Country from production countries
        country = None
        production_countries = movie_details.get('production_countries', [])
        if production_countries:
            country = production_countries[0]['name']
        
        # Build links object with waterfall approach
        links = {}

        # Wikipedia link
        wiki_url = self.find_wikipedia_url(title, year, imdb_id, movie_id)
        if wiki_url:
            links['wikipedia'] = wiki_url
        
        # Trailer link
        trailer_url = self.find_trailer_url(movie_details)
        if trailer_url:
            links['trailer'] = trailer_url
        
        # RT link
        rt_url = self.find_rt_url(title, year, imdb_id)
        if rt_url:
            links['rt'] = rt_url
        
        return {
            'id': movie_id,
            'title': title,
            'digital_date': movie_data.get('digital_date'),
            'poster': f"https://image.tmdb.org/t/p/w500{movie_details['poster_path']}" if movie_details.get('poster_path') else None,
            'synopsis': movie_details.get('overview', 'No synopsis available.'),
            'crew': {
                'director': director,
                'cast': cast
            },
            'genres': genres,
            'studio': studio,
            'runtime': runtime,
            'year': int(year) if year else None,
            'country': country,
            'rt_score': None,  # Will be filled by RT cache if available
            'providers': movie_data.get('providers', {}),
            'links': links
        }
    
    def generate_display_data(self, days_back=90, incremental=True):
        """Generate display data from tracking database

        Args:
            days_back: How many days back to look for available movies
            incremental: If True, only process NEW movies not already in data.json (default)
                        If False, regenerate entire data.json from scratch
        """

        # Load tracking database
        if not os.path.exists('movie_tracking.json'):
            print("❌ No tracking database found. Run 'python movie_tracker.py daily' first")
            return

        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)

        # Load existing data.json if incremental mode
        existing_movies = []
        existing_ids = set()
        if incremental and os.path.exists('data.json'):
            with open('data.json', 'r') as f:
                existing_data = json.load(f)
                existing_movies = existing_data.get('movies', [])
                existing_ids = {str(m['id']) for m in existing_movies}
            print(f"📂 Incremental mode: Found {len(existing_movies)} existing movies in data.json")

        # Filter to recently available movies
        cutoff_date = datetime.now() - timedelta(days=days_back)
        new_movies = []

        if incremental:
            print(f"🎬 Processing NEW movies that went digital in last {days_back} days...")
        else:
            print(f"🎬 Processing ALL movies that went digital in last {days_back} days...")

        for movie_id, movie_data in db['movies'].items():
            # Skip if already in data.json (incremental mode)
            if incremental and movie_id in existing_ids:
                continue

            if movie_data['status'] == 'available' and movie_data.get('digital_date'):
                try:
                    digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                    if digital_date >= cutoff_date:
                        # Get full movie details (movie_id is the TMDB ID)
                        movie_details = self.get_movie_details(movie_id)
                        if movie_details:
                            processed = self.process_movie(movie_id, movie_data, movie_details)
                            if processed:
                                new_movies.append(processed)
                                print(f"  ✓ {processed['title']} - Links: {len(processed['links'])}")

                        time.sleep(0.2)  # Rate limiting

                except Exception as e:
                    print(f"  ✗ Error processing {movie_data.get('title')}: {e}")

        # Merge with existing movies if incremental
        if incremental:
            print(f"\n📋 Adding {len(new_movies)} new movies to {len(existing_movies)} existing movies")
            display_movies = existing_movies + new_movies
        else:
            display_movies = new_movies
        
        # Sort by digital release date (newest first)
        display_movies.sort(key=lambda x: x['digital_date'], reverse=True)
        
        # Apply admin panel overrides (hide/feature movies)
        display_movies = self.apply_admin_overrides(display_movies)
        
        # Save display data
        output_data = {
            'generated_at': datetime.now().isoformat(),
            'count': len(display_movies),
            'movies': display_movies
        }
        
        with open('data.json', 'w') as f:
            json.dump(output_data, f, indent=2)
        
        # Save caches
        self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
        self.save_cache(self.rt_cache, 'rt_cache.json')
        
        print(f"\n✅ Generated data.json with {len(display_movies)} movies")
        print(f"Wikipedia links found: {len([m for m in display_movies if m['links'].get('wikipedia')])}")
        print(f"Direct trailers found: {len([m for m in display_movies if m['links'].get('trailer') and 'watch?v=' in m['links']['trailer']])}")
        print(f"RT scores cached: {len([m for m in display_movies if m['rt_score']])}")

    def apply_admin_overrides(self, display_movies):
        """Apply admin panel decisions to final output"""
        
        # Load admin decisions if they exist
        hidden = []
        featured = []
        
        if os.path.exists('admin/hidden_movies.json'):
            with open('admin/hidden_movies.json', 'r') as f:
                hidden = json.load(f)
        
        if os.path.exists('admin/featured_movies.json'):
            with open('admin/featured_movies.json', 'r') as f:
                featured = json.load(f)
        
        # Filter out hidden movies
        filtered_movies = [m for m in display_movies 
                          if str(m['id']) not in hidden]
        
        # Mark featured movies
        for movie in filtered_movies:
            if str(movie['id']) in featured:
                movie['featured'] = True
        
        hidden_count = len(display_movies) - len(filtered_movies)
        featured_count = len([m for m in filtered_movies if m.get('featured')])
        
        print(f"📝 Admin overrides applied:")
        print(f"  Hidden movies: {hidden_count}")
        print(f"  Featured movies: {featured_count}")
        
        return filtered_movies

def main():
    generator = DataGenerator()
    generator.generate_display_data()

if __name__ == "__main__":
    main()