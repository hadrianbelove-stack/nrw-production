
# Integration Example: Adding RT scores to existing movie data

import json
from rt_agent_fetcher import get_rt_scores_via_search

def update_movies_with_rt_scores(movies_file='output/current_releases.json'):
    """
    Update existing movie data with RT scores
    """
    # Load existing movies
    with open(movies_file, 'r') as f:
        movies = json.load(f)
    
    print(f"Loaded {len(movies)} movies from {movies_file}")
    
    # Add RT scores
    updated_count = 0
    
    for i, movie in enumerate(movies):
        title = movie.get('title', '')
        year = str(movie.get('year', ''))
        
        print(f"Processing {i+1}/{len(movies)}: {title}")
        
        # Fetch RT scores using the web search method
        # Note: In actual use, this would call Claude Code's WebSearch/WebFetch
        rt_data = get_rt_scores_via_search(title, year)
        
        if rt_data.get('critic_score') or rt_data.get('audience_score'):
            movie['rt_critic_score'] = rt_data.get('critic_score')
            movie['rt_audience_score'] = rt_data.get('audience_score')
            movie['rt_url'] = rt_data.get('rt_url')
            updated_count += 1
        
        # Rate limiting
        time.sleep(2)
    
    # Save updated data
    output_file = movies_file.replace('.json', '_with_rt.json')
    with open(output_file, 'w') as f:
        json.dump(movies, f, indent=2)
    
    print(f"Updated {updated_count} movies with RT scores")
    print(f"Saved to {output_file}")

# Usage:
# update_movies_with_rt_scores()
