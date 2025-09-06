#!/usr/bin/env python3
"""
Test wrapper for RT agent fetcher using Claude Code tools
"""

from rt_agent_fetcher import get_rt_scores_via_search
import json
import time

# Mock the Claude Code tools for this test
# In actual usage, these would be the real WebSearch and WebFetch functions
def mock_web_search(query):
    print(f"WebSearch: {query}")
    # Return mock search results that would contain RT URLs
    return "Mock search results for testing"

def mock_web_fetch(url, prompt):
    print(f"WebFetch: {url}")
    print(f"Prompt: {prompt}")
    # Return mock RT page content
    return "Mock RT page content"

def test_movies():
    """Test RT fetcher on movies missing scores"""
    test_cases = [
        ("Snoopy Presents: A Summer Musical", "2025"),
        ("Tehran", "2025"), 
        ("Jim Jefferies: Two Limb Policy", "2025"),
        ("Sweet Revenge", "2025"),
        ("Red Sonja", "2025")
    ]
    
    results = []
    for title, year in test_cases:
        print(f"\n{'='*60}")
        print(f"Testing: {title} ({year})")
        print(f"{'='*60}")
        
        result = get_rt_scores_via_search(title, year, mock_web_search, mock_web_fetch)
        results.append({
            'title': title,
            'year': year,
            'result': result
        })
        
        # Rate limiting
        time.sleep(1)
    
    print(f"\n{'='*60}")
    print("TEST RESULTS SUMMARY")
    print(f"{'='*60}")
    
    for item in results:
        title = item['title']
        result = item['result']
        critic = result.get('critic_score', 'N/A')
        audience = result.get('audience_score', 'N/A')
        url = result.get('rt_url', 'No URL')
        error = result.get('error', 'No error')
        
        print(f"{title}")
        print(f"  Critic: {critic}% | Audience: {audience}%")
        print(f"  URL: {url}")
        print(f"  Error: {error}")
        print()
    
    return results

if __name__ == "__main__":
    test_movies()