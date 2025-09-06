"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Enhanced RT Score Collector using WebFetch
Collects RT scores for movies missing them in the database
"""

import json
import re
import sys
import time
from urllib.parse import quote

# This script is designed to be called from Claude with WebFetch access
# It will output JSON data that can be parsed by the movie tracker

def get_rt_url_candidates(title, year=None):
    """Generate possible RT URLs for a movie"""
    # Clean title for URL
    title_slug = re.sub(r'[^\w\s-]', '', title.lower())
    title_slug = re.sub(r'[-\s]+', '_', title_slug)
    
    candidates = [
        f"https://www.rottentomatoes.com/m/{title_slug}_{year}" if year else None,
        f"https://www.rottentomatoes.com/m/{title_slug}",
        f"https://www.rottentomatoes.com/m/{title_slug.replace('_', '-')}",
    ]
    
    return [url for url in candidates if url]

def load_movies_needing_scores():
    """Load movies from database that need RT scores"""
    try:
        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)
        
        movies_needing_scores = []
        for movie_id, movie in db['movies'].items():
            if not movie.get('rt_score'):
                # Extract year from release date
                year = None
                if movie.get('release_date'):
                    year = movie['release_date'][:4]
                
                movies_needing_scores.append({
                    'id': movie_id,
                    'title': movie['title'],
                    'year': year
                })
        
        return movies_needing_scores
    except Exception as e:
        print(f"Error loading movies: {e}")
        return []

def main():
    """Main function to collect RT scores"""
    movies = load_movies_needing_scores()
    print(f"Found {len(movies)} movies needing RT scores")
    
    # Output the first few movies that need scores for testing
    for movie in movies[:10]:
        title = movie['title']
        year = movie['year']
        print(f"Movie: {title} ({year})")
        
        # Generate URL candidates
        urls = get_rt_url_candidates(title, year)
        print(f"RT URL candidates: {urls}")
        print()

if __name__ == "__main__":
    main()
