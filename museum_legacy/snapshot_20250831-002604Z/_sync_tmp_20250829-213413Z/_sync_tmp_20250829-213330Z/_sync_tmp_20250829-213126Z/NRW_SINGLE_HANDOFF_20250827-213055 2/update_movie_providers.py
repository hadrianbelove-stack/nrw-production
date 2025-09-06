#!/usr/bin/env python3
"""
Update provider data for specific movies
"""

import json
import requests
import yaml
from datetime import datetime

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_movie_providers(movie_id, api_key):
    """Get current provider availability for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    try:
        response = requests.get(url, params={'api_key': api_key})
        us_providers = response.json().get('results', {}).get('US', {})
        
        providers = {
            'rent': [p['provider_name'] for p in us_providers.get('rent', [])],
            'buy': [p['provider_name'] for p in us_providers.get('buy', [])],
            'stream': [p['provider_name'] for p in us_providers.get('flatrate', [])]
        }
        
        total_count = len(providers['rent']) + len(providers['buy']) + len(providers['stream'])
        has_providers = total_count > 0
        
        return {
            'providers': providers,
            'provider_count': total_count,
            'has_providers': has_providers
        }
    except Exception as e:
        print(f"Error getting providers: {e}")
        return {'providers': {'rent': [], 'buy': [], 'stream': []}, 'provider_count': 0, 'has_providers': False}

def update_movie_provider_data(movie_title_search):
    """Update provider data for movies matching the search term"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Load tracking database
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)
    
    print(f"Searching for movies containing: {movie_title_search}")
    
    updated_movies = []
    
    for movie_id, movie_data in db['movies'].items():
        title = movie_data.get('title', '')
        if movie_title_search.lower() in title.lower():
            print(f"\nUpdating providers for: {title}")
            
            # Get current provider data
            provider_info = get_movie_providers(int(movie_id), api_key)
            
            # Update movie data
            old_count = movie_data.get('provider_count', 0)
            old_has_providers = movie_data.get('has_providers', False)
            
            movie_data.update({
                'provider_count': provider_info['provider_count'],
                'has_providers': provider_info['has_providers'],
                'providers': provider_info['providers'],
                'last_provider_check': datetime.now().isoformat()[:10]
            })
            
            # If movie now has providers but didn't before, mark as resolved
            if provider_info['has_providers'] and not old_has_providers:
                if not movie_data.get('digital_date'):
                    movie_data['digital_date'] = datetime.now().isoformat()[:10]
                movie_data['status'] = 'resolved'
                movie_data['detected_via_providers'] = True
                print(f"  ✅ Movie now has providers! Marked as resolved")
            
            print(f"  Providers: {provider_info['provider_count']} ({old_count} → {provider_info['provider_count']})")
            print(f"  Rent: {len(provider_info['providers']['rent'])} platforms")
            print(f"  Buy: {len(provider_info['providers']['buy'])} platforms") 
            print(f"  Stream: {len(provider_info['providers']['stream'])} platforms")
            
            updated_movies.append(title)
    
    # Save updated database
    if updated_movies:
        with open('movie_tracking.json', 'w') as f:
            json.dump(db, f, indent=2)
        print(f"\n✅ Updated {len(updated_movies)} movies")
        print(f"📁 Saved to movie_tracking.json")
    else:
        print(f"❌ No movies found matching '{movie_title_search}'")
    
    return updated_movies

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        search_term = sys.argv[1]
        update_movie_provider_data(search_term)
    else:
        print("Usage: python update_movie_providers.py <search_term>")
        print("Example: python update_movie_providers.py 'Ebony'")