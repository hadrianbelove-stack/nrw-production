#!/usr/bin/env python3
"""Generate data.json from movie_tracking.json"""

import json
import requests
import time
from datetime import datetime, timedelta

# Load tracking database
with open('movie_tracking.json', 'r') as f:
    db = json.load(f)

# Filter to movies with digital dates in last 30 days
cutoff = (datetime.now() - timedelta(days=30)).isoformat()[:10]
recent = []
api_key = "99b122ce7fa3e9065d7b7dc6e660772d"

for movie_id, movie in db['movies'].items():
    if not movie.get('digital_date') or movie['digital_date'] < cutoff:
        continue
    
    # Fetch full details from TMDB
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    params = {'api_key': api_key, 'append_to_response': 'credits'}
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        details = response.json()
        
        # Extract director and cast
        director = "Unknown"
        cast = []
        credits = details.get('credits', {})
        for crew in credits.get('crew', []):
            if crew['job'] == 'Director':
                director = crew['name']
                break
        cast = [c['name'] for c in credits.get('cast', [])[:2]]
        
        recent.append({
            'id': movie_id,
            'title': movie['title'],
            'digital_date': movie['digital_date'],
            'poster': f"https://image.tmdb.org/t/p/w500{details.get('poster_path', '')}",
            'synopsis': details.get('overview', 'No synopsis available.'),
            'crew': {
                'director': director,
                'cast': cast
            },
            'links': {}
        })
        time.sleep(0.2)

# Sort by digital date (newest first)
recent.sort(key=lambda x: x['digital_date'], reverse=True)

# Write data.json
output = {
    'generated_at': datetime.now().isoformat(),
    'count': len(recent),
    'movies': recent[:30]  # Limit to 30 most recent
}

with open('data.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"Generated data.json with {len(recent)} recent releases (showing top 30)")
