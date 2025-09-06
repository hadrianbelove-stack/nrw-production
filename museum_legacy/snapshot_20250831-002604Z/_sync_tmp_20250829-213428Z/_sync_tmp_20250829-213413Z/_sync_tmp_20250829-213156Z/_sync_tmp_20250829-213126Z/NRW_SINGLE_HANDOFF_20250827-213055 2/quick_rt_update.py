#!/usr/bin/env python3
"""
Quick RT score update for testing
"""

import json
import time
from rt_score_fetcher import get_rt_score_with_fallbacks

def update_rt_scores(limit=5):
    """Update RT scores for first N movies"""
    
    # Load current data
    with open('output/data.json', 'r') as f:
        movies = json.load(f)
    
    print(f"Updating RT scores for first {limit} movies...")
    
    updated_count = 0
    for i, movie in enumerate(movies[:limit]):
        title = movie.get('title', '')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2024'
        
        if not movie.get('rt_score'):
            print(f"\n{i+1}. Fetching RT score for: {title} ({year})")
            rt_score = get_rt_score_with_fallbacks(title, year)
            
            if rt_score:
                movie['rt_score'] = rt_score
                updated_count += 1
                print(f"   ✅ Found: {rt_score}%")
            else:
                print(f"   ❌ Not found")
            
            time.sleep(1)  # Rate limiting
        else:
            print(f"{i+1}. {title} already has RT score: {movie['rt_score']}%")
    
    # Save updated data
    with open('output/data.json', 'w') as f:
        json.dump(movies, f, indent=2)
    
    print(f"\n✅ Updated {updated_count} movies with RT scores")
    return updated_count

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    update_rt_scores(limit)