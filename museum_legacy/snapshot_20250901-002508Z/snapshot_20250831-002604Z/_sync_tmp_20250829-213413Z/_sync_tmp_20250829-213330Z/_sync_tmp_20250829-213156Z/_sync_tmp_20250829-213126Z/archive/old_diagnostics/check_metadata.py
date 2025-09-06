"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Check movie metadata that might exclude them from discovery
"""

import requests

api_key = "99b122ce7fa3e9065d7b7dc6e660772d"

print('🔍 Final test: Check movie metadata that might exclude them from discovery...\n')

missing_movies = [
    ('Pavements', 1063307),
    ('Blue Sun Palace', 1274751)
]

for title, movie_id in missing_movies:
    print(f'📽️ {title}:')
    
    response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}',
        params={'api_key': api_key}
    )
    
    if response.status_code == 200:
        movie = response.json()
        
        print(f'  Status: {movie.get("status", "Unknown")}')
        print(f'  Adult content: {movie.get("adult", False)}')
        print(f'  Video: {movie.get("video", False)}')  # True = made-for-TV/video
        print(f'  Popularity: {movie.get("popularity", 0)}')
        print(f'  Vote count: {movie.get("vote_count", 0)}')
        print(f'  Original language: {movie.get("original_language", "Unknown")}')
        
        # Check genres
        genres = [g['name'] for g in movie.get('genres', [])]
        genre_list = ', '.join(genres) if genres else "None"
        print(f'  Genres: {genre_list}')
        
        # Check production countries
        countries = [c['iso_3166_1'] for c in movie.get('production_countries', [])]
        country_list = ', '.join(countries) if countries else "None"
        print(f'  Production countries: {country_list}')
    
    print()

print('💡 Hypothesis: These movies might be:')
print('  1. Flagged as "video" (made-for-TV/streaming) rather than theatrical')
print('  2. Have low popularity scores that push them out of discovery')
print('  3. Missing US production country designation')
print('  4. Documentary/special genre that gets filtered differently')
print('  5. Have "Released" status instead of expected status')
