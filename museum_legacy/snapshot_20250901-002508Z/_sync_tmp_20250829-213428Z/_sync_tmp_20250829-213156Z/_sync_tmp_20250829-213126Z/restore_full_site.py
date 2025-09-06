#!/usr/bin/env python3
"""
Restore full site with all current releases + RT scores
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

def restore_full_site():
    """Generate site with all current releases plus our RT scores"""
    
    # Load current releases (the original 201 movies)
    with open('current_releases.json', 'r') as f:
        current_movies = json.load(f)
    
    # Load our RT scores from movie_tracking.json
    with open('movie_tracking.json', 'r') as f:
        tracking_data = json.load(f)
    rt_data = tracking_data.get('movies', {})
    
    # Create lookup for RT scores by TMDB ID and title
    rt_scores_by_id = {}
    rt_scores_by_title = {}
    for movie_id, movie in rt_data.items():
        if movie.get('rt_score'):
            tmdb_id = movie.get('tmdb_id')
            title = movie.get('title')
            score = movie['rt_score']
            
            if tmdb_id:
                rt_scores_by_id[str(tmdb_id)] = score
            if title:
                rt_scores_by_title[title.lower()] = score
    
    def get_rt_score(movie):
        """Get RT score by TMDB ID or title match"""
        tmdb_id = str(movie.get('tmdb_id', ''))
        title = movie.get('title', '').lower()
        
        # Try TMDB ID first
        if tmdb_id in rt_scores_by_id:
            return rt_scores_by_id[tmdb_id]
        
        # Try title match
        if title in rt_scores_by_title:
            return rt_scores_by_title[title]
        
        return None
    
    print(f"Processing {len(current_movies)} movies with {len(rt_scores_by_id)} ID-based + {len(rt_scores_by_title)} title-based RT scores available...")
    
    # Prioritize movies with RT scores for poster fetching
    movies_with_rt = []
    movies_without_rt = []
    
    for movie in current_movies:
        if get_rt_score(movie):
            movies_with_rt.append(movie)
        else:
            movies_without_rt.append(movie)
    
    # Process movies with RT scores first (get posters), then others (no poster fetch)
    priority_movies = movies_with_rt[:20]  # First 20 with RT scores
    remaining_movies = movies_with_rt[20:] + movies_without_rt
    
    print(f"Fetching posters for {len(priority_movies)} priority movies with RT scores...")
    
    items = []
    
    # Process priority movies (with poster fetching)
    for i, movie in enumerate(priority_movies):
        print(f"  {i+1}/{len(priority_movies)}: {movie.get('title', 'Unknown')}")
        
        # Get basic movie info
        title = movie.get('title', 'Unknown')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2025'
        tmdb_id = str(movie.get('tmdb_id', ''))
        
        # Check if we have an RT score for this movie
        rt_score = get_rt_score(movie)
        
        # Create RT URL
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        
        # Fetch poster from TMDB
        poster_url = get_tmdb_poster(movie.get('tmdb_id')) if movie.get('tmdb_id') else 'https://via.placeholder.com/160x240'
        
        # Create JustWatch URL
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
        time.sleep(0.1)  # Rate limiting
    
    # Process remaining movies (without poster fetching for speed)
    print(f"Processing remaining {len(remaining_movies)} movies...")
    for movie in remaining_movies:
        title = movie.get('title', 'Unknown')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2025'
        tmdb_id = str(movie.get('tmdb_id', ''))
        
        rt_score = get_rt_score(movie)
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        
        # Use existing poster or placeholder (no TMDB fetch)
        poster_url = movie.get('poster_url', 'https://via.placeholder.com/160x240')
        if not poster_url or poster_url == 'null':
            poster_url = 'https://via.placeholder.com/160x240'
        
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
    
    # Group by date
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
    
    # Load and render template
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
    
    # Count stats
    rt_count = sum(1 for item in items if item['rt_score'])
    poster_count = sum(1 for item in items if 'image.tmdb.org' in item['poster_url'])
    
    print(f"✅ Restored full site with {len(items)} movies")
    print(f"📊 {rt_count} movies have RT scores")
    print(f"🖼️ {poster_count} movies have real posters")

if __name__ == '__main__':
    restore_full_site()