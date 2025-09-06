#!/usr/bin/env python3
"""
Generate movie list from tracking database
"""

import json
import requests
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_movie_providers(movie_id, api_key):
    """Get provider availability for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    try:
        response = requests.get(url, params={'api_key': api_key})
        us_providers = response.json().get('results', {}).get('US', {})
        
        return {
            'rent': [p['provider_name'] for p in us_providers.get('rent', [])],
            'buy': [p['provider_name'] for p in us_providers.get('buy', [])],
            'stream': [p['provider_name'] for p in us_providers.get('flatrate', [])]
        }
    except Exception:
        return {'rent': [], 'buy': [], 'stream': []}

def generate_current_releases(days_back=30):
    """Generate list of currently available movies from tracking database"""
    
    # Load tracking database
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)
    
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Get movies that went digital recently
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    current_releases = []
    
    print(f"🎬 Finding movies that went digital in last {days_back} days...")
    
    for movie_id, movie_data in db['movies'].items():
        if movie_data['status'] == 'resolved' and movie_data.get('digital_date'):
            try:
                digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                if digital_date >= cutoff_date:
                    # Get current provider info
                    providers = get_movie_providers(int(movie_id), api_key)
                    
                    # Only include if actually has providers
                    if providers['rent'] or providers['buy'] or providers['stream']:
                        movie_data['providers'] = providers
                        current_releases.append(movie_data)
                        
                        provider_summary = []
                        if providers['rent']: provider_summary.append(f"Rent: {len(providers['rent'])}")
                        if providers['buy']: provider_summary.append(f"Buy: {len(providers['buy'])}")
                        if providers['stream']: provider_summary.append(f"Stream: {len(providers['stream'])}")
                        
                        print(f"  ✅ {movie_data['title']} - {' | '.join(provider_summary)}")
                        
            except Exception as e:
                continue
    
    # Sort by digital date (most recent first)
    current_releases.sort(key=lambda x: x['digital_date'], reverse=True)
    
    print(f"\n🎯 Found {len(current_releases)} currently available movies")
    return current_releases

def export_to_json(movies, filename='current_releases.json'):
    """Export current releases to JSON"""
    with open(filename, 'w') as f:
        json.dump(movies, f, indent=2)
    print(f"💾 Exported to {filename}")

if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    
    movies = generate_current_releases(days)
    export_to_json(movies)
    
    print(f"\n📊 SUMMARY:")
    print(f"Movies that went digital in last {days} days: {len(movies)}")
    
    if movies:
        print(f"\nTop 5 recent digital releases:")
        for movie in movies[:5]:
            days_ago = (datetime.now() - datetime.strptime(movie['digital_date'], '%Y-%m-%d')).days
            print(f"  • {movie['title']} - {days_ago} days ago")