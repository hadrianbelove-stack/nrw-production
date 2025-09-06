#!/usr/bin/env python3
"""
Hybrid approach: Use current_releases.json for full movie list + transfer RT scores from data.json
"""
import json
import urllib.parse
import requests
import yaml
import time
from jinja2 import Template
from collections import defaultdict
from datetime import datetime

def get_tmdb_poster(tmdb_id):
    """Get poster URL from TMDB"""
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        api_key = config.get('tmdb_api_key')
        
        if not api_key or not tmdb_id:
            return 'https://via.placeholder.com/160x240'
            
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        response = requests.get(url, params={'api_key': api_key})
        
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"
        
        return 'https://via.placeholder.com/160x240'
    except:
        return 'https://via.placeholder.com/160x240'

def hybrid_restore():
    """Restore full site using current_releases.json + RT scores from output/data.json"""
    
    # Load full movie list
    with open('current_releases.json', 'r') as f:
        current_movies = json.load(f)
    
    # Load RT scores from our previous work
    with open('output/data.json', 'r') as f:
        rt_data = json.load(f)
    
    # Create RT score lookup by title (case-insensitive)
    rt_by_title = {}
    for movie_id, movie in rt_data.items():
        if movie.get('rt_score'):
            title = movie.get('title', '').lower().strip()
            if title:
                rt_by_title[title] = movie['rt_score']
    
    print(f"Processing {len(current_movies)} movies with {len(rt_by_title)} RT scores available...")
    print(f"RT scores available for: {list(rt_by_title.keys())}")
    
    # Find movies with RT scores
    movies_with_rt = []
    for movie in current_movies:
        title = movie.get('title', '').lower().strip()
        if title in rt_by_title:
            movies_with_rt.append(movie)
            print(f"✅ Found RT score for: {movie.get('title')} = {rt_by_title[title]}%")
    
    # Get posters for movies with RT scores (limited batch)
    priority_movies = movies_with_rt[:10]  # Limit to avoid timeout
    print(f"Fetching posters for {len(priority_movies)} priority movies...")
    
    items = []
    
    # Process all movies
    for i, movie in enumerate(current_movies):
        title = movie.get('title', 'Unknown')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2025'
        
        # Get RT score by title match
        rt_score = rt_by_title.get(title.lower().strip())
        
        # Get poster (only for priority movies)
        if movie in priority_movies and i < 10:
            print(f"  {i+1}/10: Fetching poster for {title}")
            poster_url = get_tmdb_poster(movie.get('tmdb_id'))
            time.sleep(0.1)
        else:
            poster_url = movie.get('poster_url', 'https://via.placeholder.com/160x240')
            if not poster_url or poster_url == 'null':
                poster_url = 'https://via.placeholder.com/160x240'
        
        # Create URLs
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        watch_link = f"https://www.justwatch.com/us/search?q={urllib.parse.quote(title)}"
        
        item = {
            'title': title,
            'year': year,
            'poster_url': poster_url,
            'director': movie.get('director', 'Director N/A'),
            'cast': movie.get('cast', []),
            'synopsis': movie.get('synopsis', 'Synopsis not available.'),
            'digital_date': movie.get('digital_date', ''),
            'trailer_url': movie.get('trailer_url'),
            'rt_url': rt_url,
            'watch_link': watch_link,
            'rt_score': rt_score,
            'runtime': movie.get('runtime'),
            'studio': movie.get('studio', 'Studio N/A'),
            'rating': movie.get('rating', 'NR'),
            'providers': []
        }
        items.append(item)
    
    # Group by date and render
    grouped = defaultdict(list)
    for item in items:
        date = item['digital_date'][:10] if item['digital_date'] else '2025-08-21'
        grouped[date].append(item)
    
    # Sort dates and create template data
    sorted_dates = sorted(grouped.keys(), reverse=True)
    template_data = []
    for date_str in sorted_dates:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_info = {
                'month_short': date_obj.strftime('%b').upper(),
                'day': date_obj.strftime('%d').lstrip('0'),
                'year': date_obj.strftime('%Y')
            }
        except:
            date_info = {
                'month_short': 'AUG',
                'day': '21', 
                'year': '2025'
            }
        template_data.append((date_info, grouped[date_str]))
    
    # Render template
    with open('templates/site_enhanced.html', 'r') as f:
        template = Template(f.read())
    
    html = template.render(
        movies_by_date=template_data,
        site_title="New Release Wall",
        window_label="Digital Releases",
        region="US",
        store_names=["iTunes", "Vudu", "Amazon", "Google Play"],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    # Save
    with open('output/site/index.html', 'w') as f:
        f.write(html)
    
    # Stats
    rt_count = sum(1 for item in items if item['rt_score'])
    poster_count = sum(1 for item in items if 'image.tmdb.org' in item['poster_url'])
    
    print(f"✅ Hybrid restore complete: {len(items)} movies")
    print(f"📊 {rt_count} movies have RT scores")
    print(f"🖼️ {poster_count} movies have real posters")

if __name__ == '__main__':
    hybrid_restore()