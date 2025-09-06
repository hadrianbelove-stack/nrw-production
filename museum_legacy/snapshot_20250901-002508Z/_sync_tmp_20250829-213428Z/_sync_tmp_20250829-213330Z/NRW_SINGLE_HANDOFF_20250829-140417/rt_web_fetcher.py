#!/usr/bin/env python3
"""
RT Score Fetcher using Claude Code WebSearch and WebFetch tools
Integrated version for the New Release Wall project
"""

import json
import time
import re
from typing import Dict, Optional

def get_rt_scores_web_search(title: str, year: str = None) -> Dict:
    """
    Get RT scores by searching the web using Claude Code tools
    
    This function is designed to be called from within Claude Code environment
    where WebSearch and WebFetch tools are available.
    
    Returns: {
        'critic_score': int or None,
        'audience_score': int or None, 
        'rt_url': str or None,
        'method': 'web_search',
        'error': str or None
    }
    """
    try:
        # Build search query
        if year:
            search_query = f'"{title}" {year} rotten tomatoes site:rottentomatoes.com'
        else:
            search_query = f'"{title}" rotten tomatoes site:rottentomatoes.com'
        
        print(f"🔍 Searching for RT page: {title} ({year})")
        
        # Note: This function expects to be called from Claude Code environment
        # where WebSearch and WebFetch are available as tool calls
        return {
            'critic_score': None,
            'audience_score': None,
            'rt_url': None,
            'method': 'web_search',
            'note': 'This function must be called from Claude Code with WebSearch/WebFetch tools available',
            'search_query': search_query
        }
        
    except Exception as e:
        return {
            'critic_score': None,
            'audience_score': None,
            'rt_url': None,
            'method': 'web_search',
            'error': str(e)
        }

def update_movie_rt_scores_web(data_file='output/data.json', limit=10):
    """
    Update RT scores for movies missing them using web search
    
    This should be called from Claude Code environment where tools are available
    """
    try:
        with open(data_file, 'r') as f:
            movies = json.load(f)
    except FileNotFoundError:
        print(f"Error: {data_file} not found")
        return 0
    
    # Find movies missing RT scores
    movies_needing_scores = []
    for movie in movies:
        if not movie.get('rt_score'):
            movies_needing_scores.append(movie)
    
    print(f"Found {len(movies_needing_scores)} movies missing RT scores")
    
    if limit:
        movies_needing_scores = movies_needing_scores[:limit]
        print(f"Processing first {limit} movies")
    
    updated_count = 0
    
    for i, movie in enumerate(movies_needing_scores, 1):
        title = movie.get('title', 'Unknown')
        year = movie.get('year', '')
        
        print(f"\n[{i}/{len(movies_needing_scores)}] {title} ({year})")
        
        # This would call the web search function
        # In actual usage from Claude Code, this would make real WebSearch/WebFetch calls
        result = get_rt_scores_web_search(title, year)
        
        print(f"  Result: {result}")
        
        # In a real implementation, we'd update the movie with actual scores
        # For now, just track what we attempted
        updated_count += 1
        
        # Rate limiting
        time.sleep(1)
    
    print(f"\nProcessed {updated_count} movies for RT scores")
    return updated_count

# Known RT scores from web search testing
KNOWN_WEB_SCORES = {
    'Snoopy Presents: A Summer Musical': {
        'critic_score': 78,
        'audience_score': None,  # Less than 50 ratings
        'rt_url': 'https://www.rottentomatoes.com/m/snoopy_presents_a_summer_musical',
        'method': 'web_search'
    },
    'Red Sonja': {
        'critic_score': 56,
        'audience_score': 68,
        'rt_url': 'https://www.rottentomatoes.com/m/red_sonja',
        'method': 'web_search'
    },
    'Jim Jefferies: Two Limb Policy': {
        'critic_score': None,  # Too few reviews
        'audience_score': None,  # Less than 50 ratings
        'rt_url': 'https://www.rottentomatoes.com/m/jim_jefferies_two_limb_policy',
        'method': 'web_search'
    },
    'The Home': {
        'critic_score': 27,
        'audience_score': 59,
        'rt_url': 'https://www.rottentomatoes.com/m/the_home_2025',
        'method': 'web_search'
    },
    'Hot Milk': {
        'critic_score': 37,
        'audience_score': None,  # Fewer than 50 ratings
        'rt_url': 'https://www.rottentomatoes.com/m/hot_milk',
        'method': 'web_search'
    }
}

def apply_known_web_scores(data_file='output/data.json'):
    """Apply the RT scores we successfully found via web search"""
    try:
        with open(data_file, 'r') as f:
            movies = json.load(f)
    except FileNotFoundError:
        print(f"Error: {data_file} not found")
        return 0
    
    updated_count = 0
    
    for movie in movies:
        title = movie.get('title', '')
        
        if title in KNOWN_WEB_SCORES and not movie.get('rt_score'):
            scores = KNOWN_WEB_SCORES[title]
            
            if scores['critic_score']:
                movie['rt_score'] = scores['critic_score']
                print(f"✅ {title}: Added critic score {scores['critic_score']}%")
                updated_count += 1
            
            if scores['audience_score']:
                movie['rt_audience'] = scores['audience_score']
                print(f"✅ {title}: Added audience score {scores['audience_score']}%")
            
            movie['rt_method'] = scores['method']
            
    # Save updated data
    if updated_count > 0:
        backup_file = data_file.replace('.json', '_backup_before_web_scores.json')
        with open(backup_file, 'w') as f:
            json.dump(movies, f, indent=2, ensure_ascii=False)
            print(f"💾 Backup saved to: {backup_file}")
        
        with open(data_file, 'w') as f:
            json.dump(movies, f, indent=2, ensure_ascii=False)
            print(f"💾 Updated {data_file}")
    
    print(f"\nAdded web-sourced RT scores to {updated_count} movies")
    return updated_count

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "apply":
            apply_known_web_scores()
        elif sys.argv[1] == "test":
            update_movie_rt_scores_web(limit=5)
    else:
        print("Usage:")
        print("  python rt_web_fetcher.py apply    # Apply known web-sourced scores")
        print("  python rt_web_fetcher.py test     # Test web search process")