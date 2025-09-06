#!/usr/bin/env python3
"""
Convert movie_tracking.json to VHS site format (output/data.json)
Transforms the comprehensive tracking database to the format expected by generate_site.py
"""
import json
import os
from datetime import datetime

def convert_tracking_to_vhs_format():
    """Convert tracking database to VHS site format"""
    
    # Load the comprehensive tracking database
    with open('movie_tracking.json', 'r') as f:
        tracking_db = json.load(f)
    
    movies = tracking_db.get('movies', {})
    print(f"📊 Loading {len(movies)} movies from tracking database...")
    
    # Filter to only resolved movies (that went digital) from last 30 days
    vhs_movies = []
    cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for movie_id, movie_data in movies.items():
        # Only include resolved movies with digital dates
        if movie_data.get('status') != 'resolved' or not movie_data.get('digital_date'):
            continue
            
        # Check if digital release is recent (last 30 days)
        try:
            digital_date = datetime.fromisoformat(movie_data['digital_date'])
            days_since_digital = (cutoff_date - digital_date).days
            
            # Include movies that went digital in the last 30 days
            if days_since_digital > 30:
                continue
        except:
            continue  # Skip if date parsing fails
        
        # Convert to VHS format
        vhs_movie = {
            "title": movie_data.get('title', 'Unknown'),
            "tmdb_id": movie_data.get('tmdb_id'),
            "theatrical_date": movie_data.get('theatrical_date'),
            "digital_date": movie_data.get('digital_date'),
            "status": "resolved",
            "added_to_db": movie_data.get('added_to_db'),
            "last_checked": movie_data.get('last_checked'),
            "providers": {
                "rent": [],
                "buy": [],
                "stream": []
            }
        }
        
        # Add RT score if available
        if movie_data.get('rt_score'):
            vhs_movie['rt_score'] = movie_data['rt_score']
        else:
            vhs_movie['rt_score'] = None
            
        vhs_movies.append(vhs_movie)
    
    # Sort by digital date (newest first)
    vhs_movies.sort(key=lambda x: x['digital_date'] if x['digital_date'] else '1900-01-01', reverse=True)
    
    # Save to output directory
    os.makedirs('output', exist_ok=True)
    with open('output/data.json', 'w') as f:
        json.dump(vhs_movies, f, indent=2)
    
    print(f"✅ Converted {len(vhs_movies)} recent movies to VHS format")
    print(f"   Movies from last 30 days with digital releases")
    print(f"   Saved to: output/data.json")
    
    # Show sample of what was included
    if vhs_movies:
        print(f"\n📽️  Recent digital releases (sample):")
        for movie in vhs_movies[:5]:
            rt_text = f" (RT: {movie.get('rt_score')}%)" if movie.get('rt_score') else ""
            print(f"   • {movie['title']} - Digital: {movie['digital_date']}{rt_text}")
    
    return len(vhs_movies)

if __name__ == '__main__':
    convert_tracking_to_vhs_format()