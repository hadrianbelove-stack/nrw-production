#!/usr/bin/env python3
"""
Date Verification System for NRW
Checks bootstrap movies for more accurate digital dates
"""

import json
import requests
import time
from datetime import datetime

def verify_all_digital_dates():
    """Check ALL available movies for more accurate digital dates"""
    
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)
    
    # Find all movies marked as available that haven't been verified recently
    movies_to_verify = []
    for movie_id, movie in db['movies'].items():
        if movie.get('status') == 'available' and not movie.get('verification'):
            movies_to_verify.append((movie_id, movie))
    
    print(f"Found {len(movies_to_verify)} digital movies to verify")
    
    # For now, let's use TMDB's provider history if available
    # This is a placeholder for Reelgood integration
    verified = 0
    for movie_id, movie in movies_to_verify[:20]:  # Verify first 20 per day
        print(f"Checking: {movie['title']}")
        
        # Try Reelgood scraping (will fail gracefully if blocked)
        try:
            from reelgood_scraper import ReelgoodScraper
            scraper = ReelgoodScraper(headless=True)
            reelgood_date = scraper.search_movie(movie['title'])
            scraper.close()
            
            movie['verification'] = {
                'checked_date': datetime.now().isoformat(),
                'tmdb_date': movie.get('digital_date'),
                'reelgood_date': reelgood_date,
                'status': 'verified' if reelgood_date else 'no_reelgood_data'
            }
        except Exception as e:
            # Fallback: just flag bootstrap movies for manual review
            movie['verification'] = {
                'checked_date': datetime.now().isoformat(),
                'status': 'needs_manual_review',
                'error': str(e)
            }
        verified += 1
        time.sleep(0.5)
    
    # Save updates
    with open('movie_tracking.json', 'w') as f:
        json.dump(db, f, indent=2)
    
    print(f"Marked {verified} movies for manual verification")

if __name__ == "__main__":
    verify_all_digital_dates()
