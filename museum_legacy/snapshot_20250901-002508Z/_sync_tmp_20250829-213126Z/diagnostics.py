#!/usr/bin/env python3
"""
Consolidated Diagnostic Tool
Combines all diagnostic functions from various scripts
"""

import requests
import yaml
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class TMDBDiagnostics:
    """Unified diagnostic tool for TMDB API testing"""
    
    def __init__(self):
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
            self.api_key = config['tmdb_api_key']
            self.omdb_key = config.get('omdb_api_key')
    
    def diagnose_api_filter(self, days: int = 45, pages: int = 5):
        """
        Compare OLD vs NEW API approaches (from corrected_diagnosis.py)
        Proves the API filter issue
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        print("="*70)
        print("API FILTER DIAGNOSIS")
        print("="*70)
        print(f"Date range: {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}")
        
        # OLD approach with filter
        print("\n1. OLD METHOD - with_release_type='2|3|4|6' filter")
        print("-" * 50)
        
        old_movies = self._fetch_movies_with_filter(start_date, end_date, pages)
        old_digital = self._check_digital_availability(old_movies)
        
        print(f"  Total with filter: {len(old_movies)}")
        print(f"  Actually digital: {len(old_digital)}")
        print(f"  False positives: {len(old_movies) - len(old_digital)}")
        
        # NEW approach without filter
        print("\n2. NEW METHOD - No filter, check each movie")
        print("-" * 50)
        
        all_movies = self._fetch_movies_no_filter(start_date, end_date, pages)
        new_digital = self._check_digital_availability(all_movies)
        
        print(f"  Total without filter: {len(all_movies)}")
        print(f"  Actually digital: {len(new_digital)}")
        
        # Comparison
        print("\n" + "="*70)
        print("COMPARISON")
        print("="*70)
        
        old_ids = {m['id'] for m in old_digital}
        new_ids = {m['id'] for m in new_digital}
        
        only_new = new_ids - old_ids
        improvement = (len(new_ids) / len(old_ids) * 100 - 100) if old_ids else 0
        
        print(f"OLD method found: {len(old_ids)} movies")
        print(f"NEW method found: {len(new_ids)} movies")
        print(f"Additional movies with NEW: {len(only_new)}")
        print(f"Improvement: {improvement:.1f}%")
        
        if only_new:
            print("\nExamples of movies OLD method missed:")
            for movie in new_digital:
                if movie['id'] in only_new:
                    print(f"  • {movie['title']} ({movie.get('release_date', '')[:4]})")
                    if len(list(only_new)) >= 5:
                        break
    
    def check_movie(self, title: str, year: Optional[int] = None):
        """
        Deep dive into a specific movie's data
        """
        print(f"\n{'='*60}")
        print(f"MOVIE DIAGNOSTIC: {title} ({year or 'any year'})")
        print(f"{'='*60}")
        
        # Search for movie
        search_url = "https://api.themoviedb.org/3/search/movie"
        params = {'api_key': self.api_key, 'query': title}
        if year:
            params['year'] = year
        
        response = requests.get(search_url, params=params)
        results = response.json().get('results', [])
        
        if not results:
            print("❌ Movie not found in TMDB")
            return
        
        movie = results[0]
        movie_id = movie['id']
        print(f"✅ Found: {movie['title']} (ID: {movie_id})")
        print(f"   Release Date: {movie.get('release_date', 'Unknown')}")
        print(f"   Overview: {movie.get('overview', '')[:100]}...")
        
        # Get release types
        print("\n📅 Release Types:")
        release_types = self._get_release_types(movie_id)
        
        type_names = {
            1: 'Premiere',
            2: 'Limited Theatrical',
            3: 'Wide Theatrical',
            4: 'Digital',
            5: 'Physical',
            6: 'TV'
        }
        
        for country, types in release_types.items():
            if country == 'US' or len(release_types) == 1:
                print(f"   {country}:")
                for t in types:
                    type_num = t['type']
                    date = t['release_date'][:10] if t.get('release_date') else 'No date'
                    print(f"     Type {type_num} ({type_names.get(type_num, 'Unknown')}): {date}")
        
        # Check providers
        print("\n🎬 Streaming Providers (US):")
        providers = self._get_providers(movie_id)
        
        if providers:
            for category, provider_list in providers.items():
                if provider_list:
                    names = [p['provider_name'] for p in provider_list[:5]]
                    print(f"   {category}: {', '.join(names)}")
        else:
            print("   No providers found")
        
        # Check RT scores
        if self.omdb_key:
            print("\n⭐ Review Scores:")
            scores = self._get_review_scores(movie['title'], year)
            if scores:
                for source, score in scores.items():
                    print(f"   {source}: {score}")
            else:
                print("   No scores found")
    
    def verify_tracking(self, db_path: str = 'movie_tracking.json'):
        """
        Verify tracking database integrity
        """
        print(f"\n{'='*60}")
        print("TRACKING DATABASE VERIFICATION")
        print(f"{'='*60}")
        
        try:
            with open(db_path, 'r') as f:
                db = json.load(f)
        except FileNotFoundError:
            print(f"❌ Database not found: {db_path}")
            return
        
        movies = db.get('movies', {})
        print(f"Total movies tracked: {len(movies)}")
        
        # Analyze by status
        stats = {
            'has_digital': 0,
            'has_providers': 0,
            'has_rt_score': 0,
            'hidden': 0,
            'featured': 0
        }
        
        for movie_id, data in movies.items():
            if data.get('has_digital'):
                stats['has_digital'] += 1
            if data.get('providers'):
                stats['has_providers'] += 1
            if data.get('rt_score'):
                stats['has_rt_score'] += 1
            if data.get('hidden'):
                stats['hidden'] += 1
            if data.get('featured'):
                stats['featured'] += 1
        
        print("\n📊 Statistics:")
        for key, value in stats.items():
            pct = value / len(movies) * 100 if movies else 0
            print(f"  {key}: {value} ({pct:.1f}%)")
        
        # Recent additions
        recent = sorted(
            movies.items(),
            key=lambda x: x[1].get('added_date', ''),
            reverse=True
        )[:10]
        
        print("\n🆕 Recently Added:")
        for movie_id, data in recent:
            added = data.get('added_date', 'Unknown')[:10]
            title = data.get('title', 'Unknown')[:30]
            print(f"  {added}: {title}")
    
    def check_providers(self, region: str = 'US'):
        """
        List all available providers in region
        """
        print(f"\n{'='*60}")
        print(f"PROVIDERS IN {region}")
        print(f"{'='*60}")
        
        url = "https://api.themoviedb.org/3/watch/providers/movie"
        params = {'api_key': self.api_key, 'watch_region': region}
        
        response = requests.get(url, params=params)
        providers = response.json().get('results', [])
        
        # Group by type
        streaming = []
        rental = []
        
        for p in providers:
            name = p['provider_name']
            # This is approximate - TMDB doesn't clearly distinguish
            if any(x in name.lower() for x in ['netflix', 'prime', 'disney', 'hulu', 'max', 'paramount']):
                streaming.append(name)
            else:
                rental.append(name)
        
        print(f"\n📺 Major Streaming ({len(streaming)}):")
        for name in sorted(streaming)[:20]:
            print(f"  • {name}")
        
        print(f"\n💰 Rental/Purchase ({len(rental)}):")
        for name in sorted(rental)[:20]:
            print(f"  • {name}")
        
        print(f"\nTotal providers: {len(providers)}")
    
    # Helper methods
    def _fetch_movies_with_filter(self, start_date, end_date, pages):
        """Fetch with release type filter (OLD method)"""
        movies = []
        for page in range(1, pages + 1):
            params = {
                'api_key': self.api_key,
                'region': 'US',
                'with_release_type': '2|3|4|6',
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc',
                'page': page
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            page_movies = response.json().get('results', [])
            movies.extend(page_movies)
            time.sleep(0.2)
            
        return movies
    
    def _fetch_movies_no_filter(self, start_date, end_date, pages):
        """Fetch without filter (NEW method)"""
        movies = []
        for page in range(1, pages + 1):
            params = {
                'api_key': self.api_key,
                'region': 'US',
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc',
                'page': page
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            page_movies = response.json().get('results', [])
            movies.extend(page_movies)
            time.sleep(0.2)
            
        return movies
    
    def _check_digital_availability(self, movies):
        """Check which movies have digital release types"""
        digital_movies = []
        
        for movie in movies:
            types = self._get_us_release_types(movie['id'])
            if 4 in types or 6 in types:
                digital_movies.append(movie)
            time.sleep(0.1)
            
        return digital_movies
    
    def _get_us_release_types(self, movie_id):
        """Get US release types for a movie"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            for country_data in data.get('results', []):
                if country_data['iso_3166_1'] == 'US':
                    return [r['type'] for r in country_data.get('release_dates', [])]
        except:
            pass
            
        return []
    
    def _get_release_types(self, movie_id):
        """Get all release types by country"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            result = {}
            for country_data in data.get('results', []):
                country = country_data['iso_3166_1']
                result[country] = country_data.get('release_dates', [])
            
            return result
        except:
            return {}
    
    def _get_providers(self, movie_id):
        """Get streaming providers"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
        
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            us_data = data.get('results', {}).get('US', {})
            return {
                'rent': us_data.get('rent', []),
                'buy': us_data.get('buy', []),
                'flatrate': us_data.get('flatrate', [])
            }
        except:
            return {}
    
    def _get_review_scores(self, title, year):
        """Get review scores from OMDb"""
        try:
            params = {'apikey': self.omdb_key, 't': title}
            if year:
                params['y'] = str(year)
            
            response = requests.get('http://www.omdbapi.com/', params=params)
            data = response.json()
            
            if data.get('Response') == 'True':
                scores = {}
                
                # IMDB
                if data.get('imdbRating') and data['imdbRating'] != 'N/A':
                    scores['IMDB'] = data['imdbRating']
                
                # Other ratings
                for rating in data.get('Ratings', []):
                    scores[rating['Source']] = rating['Value']
                
                return scores
        except:
            pass
            
        return {}

def main():
    parser = argparse.ArgumentParser(description='TMDB Diagnostic Tool')
    parser.add_argument('command', choices=['filter', 'movie', 'tracking', 'providers'],
                       help='Diagnostic command to run')
    parser.add_argument('--title', help='Movie title for movie command')
    parser.add_argument('--year', type=int, help='Movie year')
    parser.add_argument('--days', type=int, default=45, help='Days to look back')
    parser.add_argument('--region', default='US', help='Region code')
    
    args = parser.parse_args()
    
    diag = TMDBDiagnostics()
    
    if args.command == 'filter':
        diag.diagnose_api_filter(days=args.days)
    elif args.command == 'movie':
        if not args.title:
            print("Error: --title required for movie command")
        else:
            diag.check_movie(args.title, args.year)
    elif args.command == 'tracking':
        diag.verify_tracking()
    elif args.command == 'providers':
        diag.check_providers(args.region)

if __name__ == "__main__":
    main()