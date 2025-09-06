#!/usr/bin/env python3
"""
Quick site update using existing data.json with RT scores
"""
import json
import urllib.parse
import requests
import yaml
from jinja2 import FileSystemLoader, Environment

def get_tmdb_poster(tmdb_id):
    """Get poster URL from TMDB"""
    try:
        # Load TMDB API key
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

def quick_update_site():
    """Update site using existing data.json"""
    
    # Load existing data
    with open('output/data.json', 'r') as f:
        movies_dict = json.load(f)
    
    # First pass: identify movies with RT scores
    movies_with_rt = []
    movies_without_rt = []
    
    for movie_id, movie in movies_dict.items():
        if movie.get('rt_score'):
            movies_with_rt.append((movie_id, movie))
        else:
            movies_without_rt.append((movie_id, movie))
    
    # Limit to movies with RT scores + first 10 without (for speed)
    selected_movies = movies_with_rt + movies_without_rt[:10]
    
    print(f"Fetching posters for {len(selected_movies)} movies...")
    
    items = []
    for i, (movie_id, movie) in enumerate(selected_movies):
        print(f"  {i+1}/{len(selected_movies)}: {movie.get('title', 'Unknown')}")
        
        # Create RT URL
        title = movie.get('title', '')
        year = movie.get('year', '2025')
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        
        # Get poster from TMDB if available
        tmdb_id = movie.get('tmdb_id')
        poster_url = get_tmdb_poster(tmdb_id) if tmdb_id else 'https://via.placeholder.com/160x240'
        
        item = {
            'title': movie.get('title', 'Unknown'),
            'year': year,
            'poster_url': poster_url,
            'director': movie.get('director', 'Director N/A'),
            'cast': movie.get('cast', []),
            'synopsis': movie.get('synopsis', 'Synopsis not available.'),
            'digital_date': movie.get('digital_date', ''),
            'trailer_url': movie.get('trailer_url'),
            'rt_url': rt_url,
            'watch_link': f"https://www.justwatch.com/us/search?q={urllib.parse.quote(title)}",
            'rt_score': movie.get('rt_score'),
            'runtime': movie.get('runtime'),
            'studio': movie.get('studio', 'Studio N/A'),
            'rating': movie.get('rating', 'NR'),
            'providers': []
        }
        items.append(item)
    
    # Sort by title
    items.sort(key=lambda x: x['title'])
    
    # Group by date (simplified)
    from collections import defaultdict
    from datetime import datetime
    grouped = defaultdict(list)
    for item in items:
        date = item['digital_date'][:10] if item['digital_date'] else '2025-08-21'
        grouped[date].append(item)
    
    # Sort dates and create template data
    sorted_dates = sorted(grouped.keys(), reverse=True)
    template_data = []
    for date_str in sorted_dates:
        # Parse date for display
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
    
    # Load template
    from jinja2 import Template
    with open('templates/site_enhanced.html', 'r') as f:
        template = Template(f.read())
    
    # Render
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
    
    print(f"✅ Quick updated site with {len(items)} movies")
    
    # Count RT scores and posters
    rt_count = sum(1 for item in items if item['rt_score'])
    poster_count = sum(1 for item in items if 'image.tmdb.org' in item['poster_url'])
    print(f"📊 {rt_count} movies have RT scores")
    print(f"🖼️ {poster_count} movies have real posters")

if __name__ == '__main__':
    quick_update_site()