#!/usr/bin/env python3
"""
Export movie tracking data to format expected by admin panel
"""

import json
import os
from datetime import datetime

def export_movie_data():
    """Convert movie_tracking.json to admin panel format"""
    
    # Load existing tracking database
    with open('movie_tracking.json', 'r') as f:
        tracking_db = json.load(f)
    
    # Create output directory
    os.makedirs('output', exist_ok=True)
    
    # Convert to admin panel format
    admin_data = {}
    
    for movie_id, movie in tracking_db['movies'].items():
        # Only include resolved movies (available digitally)
        if movie.get('status') == 'resolved':
            admin_data[movie_id] = {
                'title': movie['title'],
                'year': movie.get('release_date', '2025-01-01')[:4] if movie.get('release_date') else '2025',
                'director': movie.get('director', 'Unknown Director'),
                'runtime': movie.get('runtime'),
                'studio': movie.get('studio'),
                'synopsis': movie.get('synopsis'),
                'rt_score': movie.get('rt_score'),
                'rt_url': movie.get('rt_url'),
                'poster_url': movie.get('poster_url'),
                'trailer_url': movie.get('trailer_url'),
                'tmdb_id': movie.get('tmdb_id'),
                'digital_date': movie.get('digital_date'),
                'provider_list': movie.get('provider_list'),
                'streaming_info': movie.get('streaming_info'),
                'status': movie['status']
            }
    
    # Save to admin format
    with open('output/data.json', 'w') as f:
        json.dump(admin_data, f, indent=2)
    
    print(f"✓ Exported {len(admin_data)} movies to output/data.json")
    print("✓ Admin panel data ready!")
    
    # Create empty files for admin features if they don't exist
    admin_files = [
        'output/hidden_movies.json',
        'output/featured_movies.json', 
        'output/movie_reviews.json'
    ]
    
    for filepath in admin_files:
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                json.dump([], f)
            print(f"✓ Created {filepath}")

if __name__ == "__main__":
    export_movie_data()