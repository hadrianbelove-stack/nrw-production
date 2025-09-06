#!/usr/bin/env python3
"""
Rotten Tomatoes Score Fetcher using Web Search and Web Scraping
Finds RT pages via web search and extracts critic/audience scores
"""

import re
import time
import json
from typing import Dict, Optional, List
from urllib.parse import urljoin, urlparse


def get_rt_scores_via_search(title: str, year: str = None, web_search_func=None, web_fetch_func=None) -> Dict:
    """
    Get RT scores by searching the web for the movie's RT page
    Returns: {'critic_score': int, 'audience_score': int, 'rt_url': str, 'method': 'web_search'}
    
    Args:
        title: Movie title
        year: Release year (optional)
        web_search_func: Function to perform web search (for testing/external use)
        web_fetch_func: Function to fetch web pages (for testing/external use)
    """
    try:
        # Build search query
        if year:
            search_query = f'"{title}" {year} rotten tomatoes site:rottentomatoes.com'
        else:
            search_query = f'"{title}" rotten tomatoes site:rottentomatoes.com'
        
        print(f"Searching for: {search_query}")
        
        # Search for RT page - use provided function or return placeholder
        if web_search_func:
            search_results = web_search_func(search_query)
        else:
            print("Note: No web search function provided. This is a standalone module.")
            return {
                'critic_score': None,
                'audience_score': None,
                'rt_url': None,
                'method': 'web_search',
                'error': 'No web search function provided. Use with Claude Code tools.'
            }
        
        # Extract RT URLs from search results
        rt_urls = extract_rt_urls_from_search(search_results)
        
        if not rt_urls:
            print(f"No RT URLs found for {title}")
            return {
                'critic_score': None,
                'audience_score': None,
                'rt_url': None,
                'method': 'web_search',
                'error': 'No RT page found in search results'
            }
        
        # Try each RT URL until we find scores
        for rt_url in rt_urls:
            print(f"Fetching RT page: {rt_url}")
            scores = extract_scores_from_rt_page(rt_url, web_fetch_func)
            
            if scores.get('critic_score') is not None or scores.get('audience_score') is not None:
                scores['rt_url'] = rt_url
                scores['method'] = 'web_search'
                return scores
            
            # Rate limiting between requests
            time.sleep(2)
        
        return {
            'critic_score': None,
            'audience_score': None,
            'rt_url': rt_urls[0] if rt_urls else None,
            'method': 'web_search',
            'error': 'No scores found on RT pages'
        }
        
    except Exception as e:
        print(f"Error getting RT scores for {title}: {str(e)}")
        return {
            'critic_score': None,
            'audience_score': None,
            'rt_url': None,
            'method': 'web_search',
            'error': str(e)
        }


def extract_rt_urls_from_search(search_results) -> List[str]:
    """Extract Rotten Tomatoes URLs from search results"""
    rt_urls = []
    
    # Convert search results to string if needed
    results_text = str(search_results)
    
    # Look for RT URLs in the search results
    rt_url_pattern = r'https?://(?:www\.)?rottentomatoes\.com/m/[^\s\)\"\'<>]+'
    matches = re.findall(rt_url_pattern, results_text)
    
    # Deduplicate and filter
    seen = set()
    for url in matches:
        # Clean up URL (remove trailing punctuation)
        url = re.sub(r'[,\.\!\?\)\]\}]+$', '', url)
        
        if url not in seen and '/m/' in url:
            rt_urls.append(url)
            seen.add(url)
    
    return rt_urls[:3]  # Return top 3 URLs max


def extract_scores_from_rt_page(rt_url: str, web_fetch_func=None) -> Dict:
    """Extract critic and audience scores from RT page"""
    try:
        if web_fetch_func:
            # Use provided web fetch function
            page_content = web_fetch_func(
                rt_url,
                "Extract the Rotten Tomatoes critic score (Tomatometer) and audience score from this page. Look for percentages like '85%' or '72%'. The critic score is usually called Tomatometer and the audience score is usually called Audience Score or Popcornmeter. Return the exact percentages found."
            )
        else:
            print(f"Note: No web fetch function provided for {rt_url}")
            return {'critic_score': None, 'audience_score': None, 'error': 'No web fetch function provided'}
        
        return parse_scores_from_content(str(page_content))
        
    except Exception as e:
        print(f"Error fetching RT page {rt_url}: {str(e)}")
        return {'critic_score': None, 'audience_score': None, 'error': str(e)}


def parse_scores_from_content(content: str) -> Dict:
    """Parse RT scores from page content"""
    scores = {'critic_score': None, 'audience_score': None}
    
    # Look for percentage patterns in the content
    percentage_pattern = r'(\d{1,3})%'
    percentages = re.findall(percentage_pattern, content)
    
    # Convert to integers
    percentages = [int(p) for p in percentages if 0 <= int(p) <= 100]
    
    # Look for specific score indicators in the content
    content_lower = content.lower()
    
    # Try to identify critic vs audience scores from context
    critic_keywords = ['tomatometer', 'critics', 'critic score', 'fresh']
    audience_keywords = ['audience', 'popcorn', 'audience score', 'users']
    
    # Look for critic score patterns
    critic_patterns = [
        r'tomatometer[^\d]*(\d{1,3})%',
        r'critics?[^\d]*(\d{1,3})%',
        r'critic score[^\d]*(\d{1,3})%',
        r'(\d{1,3})%[^%]*tomatometer',
    ]
    
    for pattern in critic_patterns:
        match = re.search(pattern, content_lower)
        if match:
            critic_score = int(match.group(1))
            if 0 <= critic_score <= 100:
                scores['critic_score'] = critic_score
                break
    
    # Look for audience score patterns
    audience_patterns = [
        r'audience[^\d]*(\d{1,3})%',
        r'popcorn[^\d]*(\d{1,3})%',
        r'audience score[^\d]*(\d{1,3})%',
        r'(\d{1,3})%[^%]*audience',
    ]
    
    for pattern in audience_patterns:
        match = re.search(pattern, content_lower)
        if match:
            audience_score = int(match.group(1))
            if 0 <= audience_score <= 100:
                scores['audience_score'] = audience_score
                break
    
    # If we couldn't identify specific scores but found percentages,
    # make educated guesses based on common RT page structure
    if scores['critic_score'] is None and scores['audience_score'] is None and percentages:
        if len(percentages) >= 2:
            # Usually critic score appears first, then audience
            scores['critic_score'] = percentages[0]
            scores['audience_score'] = percentages[1]
        elif len(percentages) == 1:
            # If only one score, it's likely the critic score
            scores['critic_score'] = percentages[0]
    
    return scores


def test_rt_fetcher():
    """Test the RT score fetcher with known movies"""
    test_movies = [
        ("Barbie", "2023"),
        ("The Smurfs", "2025"),
        ("Superman", "2025"),
        ("Oppenheimer", "2023"),
        ("John Wick Chapter 4", "2023")
    ]
    
    print("Testing RT Score Fetcher")
    print("=" * 50)
    
    results = []
    
    for title, year in test_movies:
        print(f"\nTesting: {title} ({year})")
        print("-" * 30)
        
        # Get scores
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
        
        # Rate limiting between tests
        time.sleep(3)
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    
    for result in results:
        title = result['title']
        year = result['year']
        scores = result['scores']
        
        status = "✅" if (scores.get('critic_score') or scores.get('audience_score')) else "❌"
        print(f"{status} {title} ({year})")
    
    return results


def get_rt_scores_batch(movies: List[Dict]) -> List[Dict]:
    """
    Get RT scores for a batch of movies
    movies: List of dicts with 'title' and optional 'year' keys
    """
    results = []
    
    for i, movie in enumerate(movies):
        title = movie.get('title', '')
        year = movie.get('year', movie.get('release_year', ''))
        
        print(f"\nProcessing {i+1}/{len(movies)}: {title}")
        
        scores = get_rt_scores_via_search(title, str(year) if year else None)
        
        result = {
            'title': title,
            'year': year,
            'rt_scores': scores
        }
        
        results.append(result)
        
        # Rate limiting
        if i < len(movies) - 1:  # Don't sleep after the last item
            time.sleep(3)
    
    return results


if __name__ == "__main__":
    # Import tools here to avoid import errors when using as module
    import sys
    import os
    
    # Add the current directory to the Python path so we can import tools
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Run tests
    test_results = test_rt_fetcher()
    
    # Save test results to file
    with open('rt_fetcher_test_results.json', 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"\nTest results saved to rt_fetcher_test_results.json")