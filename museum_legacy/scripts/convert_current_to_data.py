#!/usr/bin/env python3
"""Convert current_releases.json to standardized assets/data.json format"""
import json
import sys
from pathlib import Path

def convert_current_to_data():
    """Convert current_releases.json to assets/data.json format"""
    current_file = Path("current_releases.json")
    if not current_file.exists():
        print("No current_releases.json found")
        return False
    
    output_file = Path("assets/data.json")
    output_file.parent.mkdir(exist_ok=True)
    
    with current_file.open('r', encoding='utf-8') as f:
        current_data = json.load(f)
    
    # Handle both array and object formats
    if isinstance(current_data, list):
        movies = current_data
    elif isinstance(current_data, dict):
        movies = list(current_data.values())
    else:
        print("Invalid current_releases.json format")
        return False
    
    # Convert to standardized format
    converted = []
    for movie in movies:
        # Extract poster URL
        poster_path = movie.get('poster_path', '') or movie.get('poster', '')
        if poster_path and not poster_path.startswith('http'):
            poster = f"https://image.tmdb.org/t/p/w500{poster_path}"
        else:
            poster = poster_path
        
        # Build conversion
        converted_movie = {
            "title": movie.get('title', ''),
            "year": str(movie.get('year', movie.get('release_year', ''))),
            "release_date": movie.get('release_date', ''),
            "digital_date": movie.get('digital_date', ''),
            "poster": poster,
            "overview": movie.get('overview', ''),
            "runtime": movie.get('runtime', 0),
            "studio": movie.get('studio', ''),
            "providers": movie.get('providers', []),
            "rt_url": movie.get('rt_url', ''),
            "rt_score": movie.get('rt_score'),
            "trailer": movie.get('trailer', ''),
            "wiki": movie.get('wiki', ''),
            "sale": movie.get('sale', '')
        }
        converted.append(converted_movie)
    
    # Write converted data
    with output_file.open('w', encoding='utf-8') as f:
        json.dump(converted, f, indent=2, ensure_ascii=False)
    
    print(f"Converted {len(converted)} movies to assets/data.json")
    return True

if __name__ == '__main__':
    success = convert_current_to_data()
    sys.exit(0 if success else 1)