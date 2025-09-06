"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Final diagnostic using the exact same parameters as our original scripts
to prove the API filter issue
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

def test_original_parameters():
    """Test with the exact parameters from new_release_wall.py"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Use 45 days like our working script
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    
    print("="*60)
    print("FINAL DIAGNOSIS - EXACT ORIGINAL PARAMETERS")
    print("="*60)
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Test the OLD way (with filter) - exactly like new_release_wall.py
    print("\\n1. OLD METHOD - With release_type filter (like new_release_wall.py)")
    print("-" * 50)
    
    old_movies = []
    for page in range(1, 6):  # 5 pages like our test
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            'with_release_type': '2|3|4|6',  # Exactly like the old script
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
    
    print(f"  Total movies with filter: {len(old_movies)}")
    
    # Now check how many actually have digital types
    print("\\n  Checking actual release types...")
    actually_digital = []
    false_positives = []
    
    for i, movie in enumerate(old_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(old_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        has_digital = 4 in release_types or 6 in release_types
        
        if has_digital:
            actually_digital.append(movie)
        else:
            false_positives.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies that actually have digital types: {len(actually_digital)}")
    print(f"  False positives (no digital types): {len(false_positives)}")
    
    # Test the NEW way (without filter) - like new_release_wall_balanced.py  
    print("\\n2. NEW METHOD - Without filter, then check types")
    print("-" * 50)
    
    all_movies = []
    for page in range(1, 6):  # 5 pages
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            # NO release_type filter
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
    
    print(f"  Total movies without filter: {len(all_movies)}")
    
    # Check release types for each
    print("\\n  Checking release types for each...")
    new_digital = []
    
    for i, movie in enumerate(all_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(all_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        has_digital = 4 in release_types or 6 in release_types
        
        if has_digital:
            new_digital.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies with digital types: {len(new_digital)}")
    
    # Compare the results
    print("\\n" + "="*60)
    print("FINAL COMPARISON")
    print("="*60)
    
    old_ids = {movie['id'] for movie in actually_digital}
    new_ids = {movie['id'] for movie in new_digital}
    
    only_in_old = old_ids - new_ids
    only_in_new = new_ids - old_ids
    in_both = old_ids & new_ids
    
    print(f"Movies found with OLD method (actually digital): {len(old_ids)}")
    print(f"Movies found with NEW method: {len(new_ids)}")
    print(f"Movies in both: {len(in_both)}")
    print(f"Only in OLD: {len(only_in_old)}")
    print(f"Only in NEW: {len(only_in_new)}")
    
    if len(false_positives) > 0:
        print(f"\\n🚨 API FILTER ISSUE CONFIRMED:")
        print(f"   The filter returned {len(false_positives)} movies without digital release types")
        print(f"   False positive rate: {len(false_positives)/len(old_movies)*100:.1f}%")
        
        print(f"\\n   Examples of false positives:")
        for movie in false_positives[:5]:
            print(f"     • {movie['title']} ({movie.get('release_date', '')[:4]})")
    
    if len(only_in_new) > 0:
        print(f"\\n✅ NEW METHOD FOUND {len(only_in_new)} ADDITIONAL MOVIES:")
        for movie in new_digital:
            if movie['id'] in only_in_new:
                print(f"     • {movie['title']} ({movie.get('release_date', '')[:4]})")
        
        improvement = len(new_ids) / len(old_ids) * 100 - 100 if len(old_ids) > 0 else 0
        print(f"\\n   Improvement: {improvement:.1f}% more movies found")
    
    print(f"\\n🎯 BOTTOM LINE:")
    if len(new_ids) > len(old_ids):
        print(f"   NEW method finds {len(new_ids) - len(old_ids)} more digitally available movies")
        print(f"   This proves the API filter was indeed problematic")
    else:
        print(f"   Both methods find similar numbers of movies")
        print(f"   The API filter works correctly for this dataset")

if __name__ == "__main__":
    test_original_parameters()
