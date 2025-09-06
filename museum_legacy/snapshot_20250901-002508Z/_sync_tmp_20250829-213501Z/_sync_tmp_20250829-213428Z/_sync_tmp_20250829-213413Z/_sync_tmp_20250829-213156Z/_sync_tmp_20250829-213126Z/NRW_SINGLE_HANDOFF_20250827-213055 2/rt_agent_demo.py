#!/usr/bin/env python3
"""
RT Agent Fetcher Demo - Shows how to use rt_agent_fetcher.py with Claude Code
This demonstrates the actual web search and fetch functionality.
"""

import json
from rt_agent_fetcher import get_rt_scores_via_search, get_rt_scores_batch


def demo_rt_fetcher():
    """Demo the RT score fetcher with real web searches"""
    print("RT Agent Fetcher Demo")
    print("=" * 50)
    print("Note: This demo requires Claude Code's WebSearch and WebFetch tools")
    print()
    
    # Test movies
    test_movies = [
        ("Barbie", "2023"),
        ("Oppenheimer", "2023"),
        ("John Wick Chapter 4", "2023")
    ]
    
    results = []
    
    for title, year in test_movies:
        print(f"Testing: {title} ({year})")
        print("-" * 30)
        
        # This would use the actual Claude Code tools when run in that environment
        # For now, it will show the structure
        scores = get_rt_scores_via_search(title, year)
        
        results.append({
            'title': title,
            'year': year,
            'scores': scores
        })
        
        # Display results
        if scores.get('error'):
            print(f"❌ Error: {scores['error']}")
        else:
            critic = scores.get('critic_score')
            audience = scores.get('audience_score')
            url = scores.get('rt_url', 'Unknown')
            
            print(f"🍅 Critic Score: {critic}%" if critic else "🍅 Critic Score: Not found")
            print(f"🍿 Audience Score: {audience}%" if audience else "🍿 Audience Score: Not found")
            print(f"🔗 RT URL: {url}")
        
        print()
    
    # Save results
    with open('rt_demo_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("Results saved to rt_demo_results.json")
    return results


if __name__ == "__main__":
    demo_rt_fetcher()