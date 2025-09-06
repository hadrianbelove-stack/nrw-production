"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Rotten Tomatoes Score Fetcher
Fetches RT scores by scraping RT search results
"""

import requests
import re
import urllib.parse
import time
from bs4 import BeautifulSoup

def get_rt_score_from_search(title, year=None):
    """Get RT score by searching Rotten Tomatoes"""
    try:
        # Create search query
        search_query = f"{title} {year}" if year else title
        search_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(search_query)}"
        
        # Headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Look for tomatometer score in the HTML
            html_content = response.text
            
            # Multiple patterns to find RT scores
            patterns = [
                r'tomatometer-score["\s>]+(\d+)',
                r'critics-score["\s>]+(\d+)',
                r'data-tomatometer["\s]*=["\s]*(\d+)',
                r'"tomatometer":(\d+)',
                r'score-number["\s>]+(\d+)%',
                r'(\d+)%\s*</span>.*?tomatometer',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                if matches:
                    score = int(matches[0])
                    if 0 <= score <= 100:  # Valid RT score range
                        return score
            
            # If no score found in search results, try to find movie link and follow it
            soup = BeautifulSoup(html_content, 'html.parser')
            movie_links = soup.find_all('a', href=re.compile(r'/m/'))
            
            if movie_links:
                movie_url = 'https://www.rottentomatoes.com' + movie_links[0]['href']
                return get_rt_score_from_movie_page(movie_url, headers)
        
        return None
        
    except Exception as e:
        print(f"Error getting RT score for {title}: {e}")
        return None

def get_rt_score_from_movie_page(movie_url, headers):
    """Get RT score from a specific movie page"""
    try:
        response = requests.get(movie_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html_content = response.text
            
            # Look for score in movie page
            patterns = [
                r'data-tomatometer["\s]*=["\s]*"(\d+)"',
                r'"tomatometer"\s*:\s*(\d+)',
                r'tomatometer-score["\s>]+(\d+)',
                r'critics_score["\s]*:\s*(\d+)',
                r'(\d+)%.*?tomatometer',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                if matches:
                    score = int(matches[0])
                    if 0 <= score <= 100:
                        return score
        
        return None
        
    except Exception as e:
        print(f"Error getting RT score from movie page: {e}")
        return None

def get_rt_score_with_fallbacks(title, year=None):
    """Get RT score with multiple fallback methods"""
    
    # Method 1: Search-based scraping
    score = get_rt_score_from_search(title, year)
    if score is not None:
        return score
    
    # Method 2: Try without year
    if year:
        score = get_rt_score_from_search(title)
        if score is not None:
            return score
    
    # Method 3: Try with simplified title (remove articles, special chars)
    simplified_title = title.lower()
    for article in ['the ', 'a ', 'an ']:
        if simplified_title.startswith(article):
            simplified_title = simplified_title[len(article):]
    
    simplified_title = re.sub(r'[^\w\s]', '', simplified_title).strip()
    if simplified_title != title.lower():
        score = get_rt_score_from_search(simplified_title, year)
        if score is not None:
            return score
    
    return None

def test_rt_fetcher():
    """Test the RT score fetcher with known movies"""
    test_movies = [
        ("Deadpool & Wolverine", 2024),
        ("Inside Out 2", 2024),
        ("The Wild Robot", 2024),
        ("Beetlejuice Beetlejuice", 2024),
        ("Joker: Folie à Deux", 2024)
    ]
    
    print("Testing RT Score Fetcher:")
    print("=" * 40)
    
    for title, year in test_movies:
        print(f"\nFetching score for: {title} ({year})")
        score = get_rt_score_with_fallbacks(title, year)
        if score is not None:
            print(f"✅ {title}: {score}%")
        else:
            print(f"❌ {title}: No score found")
        
        time.sleep(1)  # Rate limiting

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_rt_fetcher()
        else:
            title = sys.argv[1]
            year = int(sys.argv[2]) if len(sys.argv) > 2 else None
            score = get_rt_score_with_fallbacks(title, year)
            if score is not None:
                print(f"{title}: {score}%")
            else:
                print(f"{title}: No RT score found")
    else:
        print("Usage: python rt_score_fetcher.py <title> [year]")
        print("       python rt_score_fetcher.py test")
