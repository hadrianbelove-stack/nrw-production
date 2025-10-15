#!/usr/bin/env python3
"""One-time bootstrap script to populate RT cache for existing movies"""

import json
import time
from datetime import datetime
from rt_scraper import RTScraper

def bootstrap_rt_cache():
    """Bootstrap RT cache for all existing movies with longer delays"""
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
    
    print(f"BOOTSTRAP: Scraping RT data for {len(movies_to_scrape)} movies")
    print(f"Estimated time: {len(movies_to_scrape) * 10 / 60:.1f} minutes")
    print("Using 10-second delays to be extra respectful during bootstrap")
    
    # Initialize scraper
    scraper = RTScraper(headless=True)
    
    # Scrape each movie with longer delays
    for i, movie in enumerate(movies_to_scrape):
        print(f"[{i+1}/{len(movies_to_scrape)}] Fetching: {movie['title']} ({movie.get('year', 'Unknown')})")
        
        url, score = scraper.get_movie_data(
            movie['title'], 
            movie.get('year')
        )
        
        # Cache the results (even if None)
        rt_cache['movies'][movie['id']] = {
            'url': url,
            'score': score,
            'title': movie['title'],
            'year': movie.get('year'),
            'scraped_at': datetime.now().isoformat()
        }
        
        # Save cache after each movie (in case of crash)
        rt_cache['last_updated'] = datetime.now().isoformat()
        with open('rt_cache.json', 'w') as f:
            json.dump(rt_cache, f, indent=2)
        
        # Extra respectful delay for bootstrap
        time.sleep(10)
    
    scraper.close()
    print(f"BOOTSTRAP COMPLETE: RT cache populated with {len(movies_to_scrape)} entries")

if __name__ == "__main__":
    print("=== RT CACHE BOOTSTRAP ===")
    print("This will take ~20 minutes for 107 movies with 10-second delays")
    print("Run this ONCE to populate the initial cache")
    print()
    bootstrap_rt_cache()