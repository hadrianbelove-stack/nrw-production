"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Deep dive on missing titles: provider info and release dates
"""

import requests
import json

api_key = "99b122ce7fa3e9065d7b7dc6e660772d"

print('🔍 Deep dive on missing titles: provider info and release dates...\n')

titles_to_check = [
    ('Pavements', 1063307),
    ('Blue Sun Palace', 1274751)
]

for title, movie_id in titles_to_check:
    print(f'📽️ {title} (TMDB ID: {movie_id})')
    print('=' * 50)
    
    # Get detailed movie info
    movie_response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}',
        params={'api_key': api_key}
    )
    
    if movie_response.status_code == 200:
        movie = movie_response.json()
        print(f'Title: {movie.get("title")}')
        print(f'Release Date: {movie.get("release_date")}')
        print(f'Runtime: {movie.get("runtime")} min')
        print(f'Budget: ${movie.get("budget"):,}' if movie.get('budget') else 'Budget: Unknown')
        print(f'Revenue: ${movie.get("revenue"):,}' if movie.get('revenue') else 'Revenue: Unknown')
        
        # Production companies
        companies = [c['name'] for c in movie.get('production_companies', [])]
        print(f'Production Companies: {", ".join(companies) if companies else "Unknown"}')
    
    # Get release dates with types
    release_response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}/release_dates',
        params={'api_key': api_key}
    )
    
    if release_response.status_code == 200:
        release_data = release_response.json()
        print(f'\n📅 US Release Types:')
        
        for country in release_data.get('results', []):
            if country['iso_3166_1'] == 'US':
                for release in country['release_dates']:
                    type_num = release['type']
                    date = release['release_date'][:10]  # Just the date part
                    certification = release.get('certification', '')
                    note = release.get('note', '')
                    
                    type_names = {
                        1: 'Premiere',
                        2: 'Limited Theatrical', 
                        3: 'Wide Theatrical',
                        4: 'Digital',
                        5: 'Physical',
                        6: 'TV'
                    }
                    
                    type_name = type_names.get(type_num, f'Type {type_num}')
                    print(f'  Type {type_num} ({type_name}): {date}', end='')
                    if certification:
                        print(f' [{certification}]', end='')
                    if note:
                        print(f' - {note}', end='')
                    print()
    
    # Get detailed provider info
    provider_response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}/watch/providers',
        params={'api_key': api_key}
    )
    
    if provider_response.status_code == 200:
        provider_data = provider_response.json()
        us_providers = provider_data.get('results', {}).get('US', {})
        
        print(f'\n💰 US Streaming/Rental Options:')
        
        if us_providers.get('flatrate'):
            print(f'  Streaming (Free with subscription):')
            for provider in us_providers['flatrate']:
                print(f'    - {provider["provider_name"]}')
        
        if us_providers.get('rent'):
            print(f'  Rental:')
            for provider in us_providers['rent']:
                print(f'    - {provider["provider_name"]}')
        
        if us_providers.get('buy'):
            print(f'  Purchase:')
            for provider in us_providers['buy']:
                print(f'    - {provider["provider_name"]}')
        
        if not any([us_providers.get('flatrate'), us_providers.get('rent'), us_providers.get('buy')]):
            print(f'  No US providers found')
    
    print('\n' + '='*70 + '\n')
