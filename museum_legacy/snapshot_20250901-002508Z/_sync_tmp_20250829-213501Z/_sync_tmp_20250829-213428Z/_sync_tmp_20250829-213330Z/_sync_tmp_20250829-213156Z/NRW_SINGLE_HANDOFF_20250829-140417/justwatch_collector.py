#!/usr/bin/env python3
"""
JustWatch Integration for Movie Tracker
Collects streaming availability and pricing data from JustWatch
"""

import json
import re
import time
from urllib.parse import quote

class JustWatchCollector:
    def __init__(self):
        pass
    
    def get_justwatch_url_candidates(self, title, year=None):
        """Generate possible JustWatch URLs for a movie"""
        # Clean title for URL
        title_slug = re.sub(r'[^\w\s-]', '', title.lower())
        title_slug = re.sub(r'[-\s]+', '-', title_slug)
        
        candidates = []
        if year:
            candidates.extend([
                f"https://www.justwatch.com/us/movie/{title_slug}-{year}",
                f"https://www.justwatch.com/us/movie/{title_slug}-{int(year)+1}",  # Sometimes release year differs
                f"https://www.justwatch.com/us/movie/{title_slug}-{int(year)-1}",
            ])
        
        candidates.extend([
            f"https://www.justwatch.com/us/movie/{title_slug}",
            f"https://www.justwatch.com/us/movie/{title_slug.replace('-', '_')}",
        ])
        
        return candidates
    
    def search_justwatch(self, title, year=None):
        """Search for movie on JustWatch using web search"""
        try:
            # Try web search first
            search_query = f'site:justwatch.com "{title}"'
            if year:
                search_query += f" {year}"
            
            return search_query
        except Exception as e:
            print(f"Error searching JustWatch for {title}: {e}")
            return None
    
    def load_movies_needing_streaming_data(self):
        """Load movies from database that need streaming data"""
        try:
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
            
            movies_needing_data = []
            for movie_id, movie in db['movies'].items():
                if not movie.get('streaming_info') and movie['status'] == 'resolved':
                    # Only check resolved movies (available digitally)
                    year = None
                    if movie.get('release_date'):
                        year = movie['release_date'][:4]
                    
                    movies_needing_data.append({
                        'id': movie_id,
                        'title': movie['title'],
                        'year': year
                    })
            
            return movies_needing_data
        except Exception as e:
            print(f"Error loading movies: {e}")
            return []
    
    def update_movie_streaming_info(self, movie_id, streaming_info):
        """Update movie with streaming information"""
        try:
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
            
            if movie_id in db['movies']:
                db['movies'][movie_id]['streaming_info'] = streaming_info
                db['movies'][movie_id]['streaming_updated'] = time.strftime('%Y-%m-%d')
                
                with open('movie_tracking.json', 'w') as f:
                    json.dump(db, f, indent=2)
                
                return True
        except Exception as e:
            print(f"Error updating streaming info: {e}")
            return False

def main():
    """Test the JustWatch collector"""
    collector = JustWatchCollector()
    
    # Test with a few known movies
    test_movies = [
        ("Weapons", 2025),
        ("The Pickup", 2025),
        ("Hostile Takeover", 2025)
    ]
    
    for title, year in test_movies:
        print(f"\n🔍 Testing JustWatch search for: {title} ({year})")
        
        # Generate URL candidates
        urls = collector.get_justwatch_url_candidates(title, year)
        print(f"JustWatch URL candidates:")
        for url in urls[:3]:  # Show first 3
            print(f"  - {url}")
        
        # Generate search query
        search_query = collector.search_justwatch(title, year)
        print(f"Web search query: {search_query}")

if __name__ == "__main__":
    main()