"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Fix RT scores using working OMDb API
"""

import json
import time
from simple_rt_fetcher import get_rt_score_omdb

def fix_rt_scores(limit=10):
    """Fix RT scores using working OMDb API"""
    
    # Load current data
    with open('output/data.json', 'r') as f:
        movies_dict = json.load(f)
    
    print(f"Fixing RT scores using OMDb API for first {limit} movies...")
    
    updated_count = 0
    processed = 0
    
    for movie_id, movie in movies_dict.items():
        if processed >= limit:
            break
            
        title = movie.get('title', '')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2024'
        
        processed += 1
        print(f"\n{processed}. Fetching RT score for: {title} ({year})")
        rt_score = get_rt_score_omdb(title, year)
        
        if rt_score:
            movie['rt_score'] = rt_score
            updated_count += 1
            print(f"   ✅ Found: {rt_score}%")
        else:
            print(f"   ❌ Not found")
        
        time.sleep(0.2)  # Rate limiting
    
    # Save updated data
    with open('output/data.json', 'w') as f:
        json.dump(movies_dict, f, indent=2)
    
    print(f"\n✅ Fixed {updated_count} RT scores using OMDb API")
    return updated_count

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    fix_rt_scores(limit)
