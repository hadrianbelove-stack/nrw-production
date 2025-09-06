#!/usr/bin/env python3
"""
Fix tracking dates using better fallback logic
"""

import json
import requests
import time
from datetime import datetime, timedelta

def fix_digital_dates():
    api_key = "99b122ce7fa3e9065d7b7dc6e660772d"
    
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)
    
    print("Fixing digital dates with better logic...")
    fixed = 0
    
    for movie_id, movie in db['movies'].items():
        # Skip if manually corrected
        if movie.get('manually_corrected'):
            continue
            
        # If has providers but digital_date is today or recent
        if movie.get('has_digital'):
            digital_date = movie.get('digital_date', '')
            
            # Check if suspiciously recent (last 3 days)
            if digital_date:
                date_obj = datetime.fromisoformat(digital_date.split('T')[0])
                days_ago = (datetime.now() - date_obj).days
                
                if days_ago <= 3:
                    print(f"\nChecking {movie['title']}...")
                    
                    # Try to get better date
                    better_date = None
                    
                    # 1. Check for Type 4 date
                    response = requests.get(
                        f'https://api.themoviedb.org/3/movie/{movie_id}/release_dates',
                        params={'api_key': api_key}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        for country in data.get('results', []):
                            if country['iso_3166_1'] == 'US':
                                for release in country['release_dates']:
                                    if release['type'] == 4:
                                        better_date = release['release_date'][:10]
                                        print(f"  Found Type 4 date: {better_date}")
                                        break
                    
                    # 2. If no Type 4, use Limited Theatrical (Type 2) if it exists
                    if not better_date:
                        for country in data.get('results', []):
                            if country['iso_3166_1'] == 'US':
                                for release in country['release_dates']:
                                    if release['type'] == 2:  # Limited theatrical often = VOD
                                        better_date = release['release_date'][:10]
                                        print(f"  Using Limited Theatrical date: {better_date}")
                                        break
                    
                    # 3. If still no date, estimate from theatrical + 45 days
                    if not better_date and movie.get('release_date'):
                        theatrical = datetime.fromisoformat(movie['release_date'].split('T')[0])
                        estimated = theatrical + timedelta(days=45)
                        if estimated < datetime.now():
                            better_date = estimated.strftime('%Y-%m-%d')
                            print(f"  Estimated from theatrical + 45 days: {better_date}")
                    
                    # Apply the better date
                    if better_date and better_date != digital_date[:10]:
                        movie['digital_date'] = better_date
                        movie['date_source'] = 'estimated'
                        fixed += 1
                        print(f"  Fixed: {digital_date[:10]} → {better_date}")
                    
                    time.sleep(0.5)  # Rate limit
    
    # Save fixes
    with open('movie_tracking.json', 'w') as f:
        json.dump(db, f, indent=2)
    
    print(f"\n✅ Fixed {fixed} movie dates")
    return fixed

if __name__ == "__main__":
    fix_digital_dates()
