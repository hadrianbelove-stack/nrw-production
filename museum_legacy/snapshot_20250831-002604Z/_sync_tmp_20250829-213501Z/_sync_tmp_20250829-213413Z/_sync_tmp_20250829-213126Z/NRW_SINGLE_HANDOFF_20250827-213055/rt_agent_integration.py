#!/usr/bin/env python3
"""
RT Agent Integration - Demonstrates using rt_agent_fetcher.py with Claude Code tools
This shows how to integrate the RT score fetching functionality into the movie tracking system.
"""

import json
import time
from typing import Dict, List
from rt_agent_fetcher import (
    get_rt_scores_via_search, 
    extract_rt_urls_from_search, 
    parse_scores_from_content
)


def claude_code_web_search(query: str):
    """
    Wrapper for Claude Code WebSearch tool
    In actual Claude Code environment, this would call the WebSearch function
    """
    print(f"Would search for: {query}")
    # This is a placeholder - in real usage, this would call Claude Code's WebSearch
    return f"Mock search results for: {query}"


def claude_code_web_fetch(url: str, prompt: str):
    """
    Wrapper for Claude Code WebFetch tool
    In actual Claude Code environment, this would call the WebFetch function
    """
    print(f"Would fetch: {url} with prompt: {prompt}")
    # This is a placeholder - in real usage, this would call Claude Code's WebFetch
    return f"Mock page content for: {url}"


def fetch_rt_scores_for_movies(movies: List[Dict]) -> List[Dict]:
    """
    Fetch RT scores for a list of movies using the Claude Code integration
    
    Args:
        movies: List of movie dictionaries with 'title' and optional 'year' keys
        
    Returns:
        List of movie dictionaries with added RT score information
    """
    results = []
    
    for i, movie in enumerate(movies):
        title = movie.get('title', '')
        year = str(movie.get('year', movie.get('release_year', ''))) if movie.get('year') or movie.get('release_year') else None
        
        print(f"\nProcessing {i+1}/{len(movies)}: {title} ({year})")
        
        # Get RT scores using the web search method
        scores = get_rt_scores_via_search(
            title=title,
            year=year,
            web_search_func=claude_code_web_search,
            web_fetch_func=claude_code_web_fetch
        )
        
        # Add RT scores to movie data
        movie_with_scores = movie.copy()
        movie_with_scores['rt_scores'] = scores
        
        # Display results
        if scores.get('error'):
            print(f"❌ Error: {scores['error']}")
        else:
            critic = scores.get('critic_score')
            audience = scores.get('audience_score')
            rt_url = scores.get('rt_url', 'N/A')
            
            print(f"🍅 Critic Score: {critic}%" if critic else "🍅 Critic Score: Not found")
            print(f"🍿 Audience Score: {audience}%" if audience else "🍿 Audience Score: Not found")
            print(f"🔗 RT URL: {rt_url}")
        
        results.append(movie_with_scores)
        
        # Rate limiting between requests
        if i < len(movies) - 1:
            time.sleep(2)
    
    return results


def demo_integration_with_existing_data():
    """
    Demo integration with existing movie tracking data
    """
    print("RT Agent Integration Demo")
    print("=" * 50)
    
    # Sample movie data (similar to what might be in current_releases.json)
    sample_movies = [
        {
            "title": "Barbie",
            "year": 2023,
            "digital_release_date": "2023-09-12",
            "tmdb_id": 346698
        },
        {
            "title": "Oppenheimer", 
            "year": 2023,
            "digital_release_date": "2023-11-21",
            "tmdb_id": 872585
        },
        {
            "title": "The Flash",
            "year": 2023,
            "digital_release_date": "2023-08-29",
            "tmdb_id": 298618
        }
    ]
    
    # Process movies to get RT scores
    movies_with_scores = fetch_rt_scores_for_movies(sample_movies)
    
    # Save results
    output_file = "rt_integration_results.json"
    with open(output_file, 'w') as f:
        json.dump(movies_with_scores, f, indent=2)
    
    print(f"\nResults saved to {output_file}")
    
    # Display summary
    print("\nSummary:")
    print("-" * 30)
    for movie in movies_with_scores:
        title = movie['title']
        year = movie['year']
        scores = movie['rt_scores']
        
        critic = scores.get('critic_score')
        audience = scores.get('audience_score')
        
        status = "✅" if (critic or audience) else "❌"
        print(f"{status} {title} ({year}) - Critic: {critic}%, Audience: {audience}%")
    
    return movies_with_scores


def create_rt_score_update_script():
    """
    Create a script that can be used to update existing movie data with RT scores
    """
    script_content = '''#!/usr/bin/env python3
"""
RT Score Updater - Updates movie tracking database with RT scores
Usage: python rt_score_updater.py [--limit N] [--year YYYY] [--test]
"""

import json
import argparse
from rt_agent_integration import fetch_rt_scores_for_movies


def load_current_releases():
    """Load current releases data"""
    try:
        with open('output/current_releases.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: output/current_releases.json not found")
        return []


def save_updated_data(movies, output_file):
    """Save updated movie data"""
    with open(output_file, 'w') as f:
        json.dump(movies, f, indent=2)
    print(f"Updated data saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Update movie data with RT scores')
    parser.add_argument('--limit', type=int, help='Limit number of movies to process')
    parser.add_argument('--year', type=int, help='Only process movies from specific year')
    parser.add_argument('--test', action='store_true', help='Test mode - save to separate file')
    parser.add_argument('--output', help='Output file path')
    
    args = parser.parse_args()
    
    # Load current movies
    movies = load_current_releases()
    print(f"Loaded {len(movies)} movies from current releases")
    
    # Filter by year if specified
    if args.year:
        movies = [m for m in movies if m.get('year') == args.year or m.get('release_year') == args.year]
        print(f"Filtered to {len(movies)} movies from {args.year}")
    
    # Limit number if specified
    if args.limit:
        movies = movies[:args.limit]
        print(f"Limited to first {len(movies)} movies")
    
    # Process movies to get RT scores
    print("\\nFetching RT scores...")
    movies_with_scores = fetch_rt_scores_for_movies(movies)
    
    # Save results
    if args.test:
        output_file = args.output or 'rt_scores_test.json'
    else:
        output_file = args.output or 'output/current_releases_with_rt.json'
    
    save_updated_data(movies_with_scores, output_file)
    
    # Display summary
    successful = len([m for m in movies_with_scores 
                     if m['rt_scores'].get('critic_score') or m['rt_scores'].get('audience_score')])
    
    print(f"\\nProcessed {len(movies_with_scores)} movies")
    print(f"Successfully found RT scores for {successful} movies")
    print(f"Success rate: {successful/len(movies_with_scores)*100:.1f}%")


if __name__ == "__main__":
    main()
'''
    
    with open('rt_score_updater.py', 'w') as f:
        f.write(script_content)
    
    print("Created rt_score_updater.py - a script to update movie data with RT scores")


if __name__ == "__main__":
    # Run the demo
    demo_integration_with_existing_data()
    
    # Create the updater script
    create_rt_score_update_script()