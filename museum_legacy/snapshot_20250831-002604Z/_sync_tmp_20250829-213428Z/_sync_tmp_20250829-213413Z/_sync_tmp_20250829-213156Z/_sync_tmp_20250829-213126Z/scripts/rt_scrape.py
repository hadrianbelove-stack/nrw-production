#!/usr/bin/env python3
"""
RT Score Scraper for missing titles
Reads movie titles from stdin and attempts to find RT scores
"""
import sys
import json
import time
import re
from urllib.parse import quote

def search_rt_score(title, year="2025"):
    """
    Search for RT score for a given title
    This is a placeholder - in the real Claude Code environment,
    this would use WebSearch and WebFetch tools
    """
    print(f"🔍 Searching RT for: {title} ({year})")
    
    # Simulate search process
    search_query = f'"{title}" {year} rotten tomatoes site:rottentomatoes.com'
    print(f"   Query: {search_query}")
    
    # For now, return None since we don't have access to WebSearch/WebFetch here
    # In Claude Code environment, this would make actual web requests
    print(f"   ❌ No RT page found (would need WebSearch/WebFetch tools)")
    return None, None

def load_movie_data():
    """Load current movie data"""
    try:
        with open('output/data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: output/data.json not found")
        return []

def save_movie_data(movies):
    """Save updated movie data"""
    with open('output/data.json', 'w') as f:
        json.dump(movies, f, indent=2, ensure_ascii=False)

def main():
    """Main scraping function"""
    print("RT Score Scraper")
    print("=" * 50)
    
    # Load movie data
    movies = load_movie_data()
    if not movies:
        return
    
    # Create title to movie mapping
    title_to_movie = {movie['title']: movie for movie in movies}
    
    # Read titles from stdin
    missing_titles = []
    for line in sys.stdin:
        title = line.strip()
        if title:
            missing_titles.append(title)
    
    print(f"Processing {len(missing_titles)} missing titles...")
    
    found_count = 0
    
    for i, title in enumerate(missing_titles, 1):
        print(f"\n[{i}/{len(missing_titles)}] {title}")
        
        if title not in title_to_movie:
            print(f"   ❌ Movie not found in data.json")
            continue
        
        movie = title_to_movie[title]
        
        # Try to find RT score
        rt_score, rt_url = search_rt_score(title, movie.get('year', '2025'))
        
        if rt_score:
            movie['rt_score'] = rt_score
            movie['rt_method'] = 'web_scrape'
            if rt_url:
                movie['rt_url'] = rt_url
            
            print(f"   ✅ Found RT score: {rt_score}%")
            found_count += 1
        
        # Rate limiting
        time.sleep(1)
    
    # Save updated data
    if found_count > 0:
        save_movie_data(movies)
        print(f"\n✅ Updated {found_count} movies with RT scores")
    else:
        print(f"\n❌ No RT scores found for any movies")
    
    print(f"📊 Summary: {found_count}/{len(missing_titles)} scores found")

if __name__ == "__main__":
    main()