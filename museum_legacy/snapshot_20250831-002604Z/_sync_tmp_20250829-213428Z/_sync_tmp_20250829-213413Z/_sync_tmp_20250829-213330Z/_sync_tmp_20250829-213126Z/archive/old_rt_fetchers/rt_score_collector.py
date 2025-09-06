"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Rotten Tomatoes Score Collector
Direct web scraping fallback for when OMDb doesn't have RT scores
"""

import json
import re
import requests
from urllib.parse import quote
import time

class RTScoreCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def search_rt_movie(self, title, year=None):
        """Search for movie on RT and return URL if found"""
        try:
            # Try direct URL construction first (most common pattern)
            title_slug = re.sub(r'[^\w\s-]', '', title.lower())
            title_slug = re.sub(r'[-\s]+', '_', title_slug)
            
            if year:
                direct_url = f"https://www.rottentomatoes.com/m/{title_slug}_{year}"
            else:
                direct_url = f"https://www.rottentomatoes.com/m/{title_slug}"
            
            response = self.session.get(direct_url)
            if response.status_code == 200 and 'tomatometer' in response.text.lower():
                return direct_url
                
            # Try without year
            if year:
                alt_url = f"https://www.rottentomatoes.com/m/{title_slug}"
                response = self.session.get(alt_url)
                if response.status_code == 200 and 'tomatometer' in response.text.lower():
                    return alt_url
            
            return None
        except Exception as e:
            print(f"Error searching for {title}: {e}")
            return None
    
    def extract_rt_scores(self, url):
        """Extract RT scores from movie page"""
        try:
            response = self.session.get(url)
            html = response.text
            
            scores = {}
            
            # Extract Tomatometer score
            tomatometer_match = re.search(r'"score":"(\d+)"%.*?"state":"certified-fresh|fresh|rotten"', html)
            if tomatometer_match:
                scores['tomatometer'] = int(tomatometer_match.group(1))
            else:
                # Alternative pattern
                tomatometer_match = re.search(r'tomatometer.*?(\d+)%', html, re.IGNORECASE)
                if tomatometer_match:
                    scores['tomatometer'] = int(tomatometer_match.group(1))
            
            # Extract Audience score  
            audience_match = re.search(r'"audienceScore":"(\d+)"', html)
            if audience_match:
                scores['audience'] = int(audience_match.group(1))
            else:
                # Alternative pattern
                audience_match = re.search(r'audience.*?score.*?(\d+)%', html, re.IGNORECASE)
                if audience_match:
                    scores['audience'] = int(audience_match.group(1))
            
            return scores
            
        except Exception as e:
            print(f"Error extracting scores from {url}: {e}")
            return {}
    
    def get_rt_scores(self, title, year=None):
        """Get RT scores for a movie"""
        print(f"🍅 Searching RT for: {title} ({year})")
        
        url = self.search_rt_movie(title, year)
        if not url:
            print(f"❌ No RT page found for {title}")
            return None
        
        print(f"✓ Found RT page: {url}")
        scores = self.extract_rt_scores(url)
        
        if scores:
            tomatometer = scores.get('tomatometer', 'N/A')
            audience = scores.get('audience', 'N/A')
            print(f"✓ Scores: {tomatometer}% critics, {audience}% audience")
            return scores.get('tomatometer')  # Return tomatometer score
        else:
            print(f"❌ Could not extract scores from page")
            return None

def test_collector():
    """Test the RT collector with known movies"""
    collector = RTScoreCollector()
    
    test_movies = [
        ("Weapons", 2025),
        ("Hostile Takeover", 2025),
        ("The Pickup", 2025)
    ]
    
    for title, year in test_movies:
        score = collector.get_rt_scores(title, year)
        print(f"{title} ({year}): {score}%\n")

if __name__ == "__main__":
    test_collector()
