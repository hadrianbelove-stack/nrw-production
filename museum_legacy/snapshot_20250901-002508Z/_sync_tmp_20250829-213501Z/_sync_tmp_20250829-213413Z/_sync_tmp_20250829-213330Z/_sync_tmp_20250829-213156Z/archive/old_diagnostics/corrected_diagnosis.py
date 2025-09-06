"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
CORRECTED diagnosis: Compare the actual approaches used
1. OLD: with_release_type='2|3|4|6' filter (new_release_wall.py)
2. NEW: NO filter, get ALL movies, then check each (new_release_wall_balanced.py)
"""

import requests
import time
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_release_types(movie_id, api_key):
    """Get release types for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
    try:
        response = requests.get(url, params={'api_key': api_key})
        data = response.json()
        
        us_types = []
        if 'results' in data:
            for country_data in data['results']:
                if country_data['iso_3166_1'] == 'US':
                    for release in country_data.get('release_dates', []):
                        release_type = release.get('type')
                        if release_type and release_type not in us_types:
                            us_types.append(release_type)
                    break
        
        return us_types
    except Exception:
        return []

def main():
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Use 45 days like our test
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    
    print("="*70)
    print("CORRECTED DIAGNOSIS - ACTUAL APPROACHES COMPARED")
    print("="*70)
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Method 1: OLD approach - with_release_type filter
    print("\\n1. OLD APPROACH - with_release_type='2|3|4|6' filter")
    print("-" * 50)
    
    old_movies = []
    for page in range(1, 6):  # 5 pages
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            'with_release_type': '2|3|4|6',  # OLD approach
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        old_movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Total movies found: {len(old_movies)}")
    
    # Check which ones actually have digital
    old_digital = []
    for i, movie in enumerate(old_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(old_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        if 4 in release_types or 6 in release_types:
            old_digital.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies with digital availability: {len(old_digital)}")
    
    # Method 2: NEW approach - NO filter, get ALL movies
    print("\\n2. NEW APPROACH - NO release_type filter (get ALL movies)")
    print("-" * 50)
    
    all_movies = []
    for page in range(1, 6):  # 5 pages
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            # NO with_release_type filter - this is the key difference!
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        all_movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Total movies found: {len(all_movies)}")
    
    # Check which ones have digital
    new_digital = []
    for i, movie in enumerate(all_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(all_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        if 4 in release_types or 6 in release_types:
            new_digital.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies with digital availability: {len(new_digital)}")
    
    # Compare results
    print("\\n" + "="*70)
    print("COMPARISON RESULTS")
    print("="*70)
    
    old_ids = {movie['id'] for movie in old_digital}
    new_ids = {movie['id'] for movie in new_digital}
    
    only_in_old = old_ids - new_ids
    only_in_new = new_ids - old_ids
    in_both = old_ids & new_ids
    
    print(f"Digital movies found by OLD approach: {len(old_ids)}")
    print(f"Digital movies found by NEW approach: {len(new_ids)}")
    print(f"Movies found by both: {len(in_both)}")
    print(f"Only found by OLD approach: {len(only_in_old)}")
    print(f"Only found by NEW approach: {len(only_in_new)}")
    
    if len(only_in_new) > 0:
        print(f"\\n🎯 NEW APPROACH FOUND {len(only_in_new)} ADDITIONAL DIGITAL MOVIES:")
        for movie in new_digital:
            if movie['id'] in only_in_new:
                print(f"  • {movie['title']} ({movie.get('release_date', '')[:4]})")
        
        improvement = ((len(new_ids) - len(old_ids)) / len(old_ids) * 100) if len(old_ids) > 0 else 0
        print(f"\\n  📈 Improvement: {improvement:.1f}% more digital movies found")
    
    if len(only_in_old) > 0:
        print(f"\\n❌ OLD APPROACH FOUND {len(only_in_old)} MOVIES NOT IN NEW:")
        for movie in old_digital:
            if movie['id'] in only_in_old:
                print(f"  • {movie['title']} ({movie.get('release_date', '')[:4]})")
    
    # Show total movie pool difference
    total_old = len(old_movies)
    total_new = len(all_movies)
    
    print(f"\\n📊 TOTAL MOVIE POOL COMPARISON:")
    print(f"  OLD approach total movies: {total_old}")
    print(f"  NEW approach total movies: {total_new}")
    print(f"  Difference: {total_new - total_old} more movies to check")
    
    if total_new > total_old:
        pool_increase = ((total_new - total_old) / total_old * 100) if total_old > 0 else 0
        print(f"  Pool increase: {pool_increase:.1f}%")
        print(f"\\n✅ The NEW approach casts a wider net!")
        print(f"   By removing the release_type filter, we search {total_new - total_old} more movies")
        print(f"   and find {len(new_ids) - len(old_ids)} more digital releases")
    else:
        print(f"\\n⚠️  Both approaches search the same number of movies")
        print(f"   The benefit comes from more accurate digital detection")

if __name__ == "__main__":
    main()
