#!/usr/bin/env python3
"""Update RT data for movies missing scores/URLs"""

import json
import time
from datetime import datetime
from rt_scraper import RTScraper

def update_rt_cache():
    # Load current movie data
    with open('data.json', 'r') as f:
        data = json.load(f)
    
    # Load RT cache
    try:
        with open('rt_cache.json', 'r') as f:
            rt_cache = json.load(f)
    except:
        rt_cache = {"movies": {}, "last_updated": ""}
    
    # Find movies needing RT data
    movies_to_scrape = []
    for movie in data['movies']:
        movie_id = movie['id']
        
        # Skip if we already have RT data cached
        if movie_id in rt_cache['movies']:
            continue
            
        # Skip if no good metadata to search with
        if not movie.get('title'):
            continue
            
        movies_to_scrape.append(movie)
    
    if not movies_to_scrape:
        print("All movies have RT data cached")
        return
    
    if len(movies_to_scrape) > 20:
        print(f"WARNING: {len(movies_to_scrape)} movies to scrape - this seems high")
        print("Limiting to 20 to avoid detection")
        movies_to_scrape = movies_to_scrape[:20]
    
    print(f"Scraping RT data for {len(movies_to_scrape)} movies")
    
    # Initialize scraper
    scraper = RTScraper(headless=True)
    
    # Process ALL movies that need scraping (usually <10)
    for i, movie in enumerate(movies_to_scrape):
        print(f"[{i+1}/{len(movies_to_scrape)}] Fetching: {movie['title']}")
        
        url, score = scraper.get_movie_data(
            movie['title'], 
            movie.get('year')
        )
        
        # Cache the results (even if None)
        rt_cache['movies'][movie['id']] = {
            'url': url,
            'score': score,
            'title': movie['title'],
            'scraped_at': datetime.now().isoformat()
        }
        
        # Save cache after each movie (in case of crash)
        rt_cache['last_updated'] = datetime.now().isoformat()
        with open('rt_cache.json', 'w') as f:
            json.dump(rt_cache, f, indent=2)
        
        # Adaptive delay - longer for larger batches
        if len(movies_to_scrape) > 10:
            time.sleep(5)  # Extra careful
        else:
            time.sleep(3)  # Normal pace
    
    scraper.close()
    print(f"RT cache updated with {len(movies_to_scrape)} entries")

if __name__ == "__main__":
    update_rt_cache()