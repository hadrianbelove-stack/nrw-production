"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
"""
Simple RT Score Fetcher using OMDb API only
"""

import requests
import yaml

def get_rt_score_omdb(title, year=None):
    """Get RT score from OMDb API only"""
    try:
        # Load config
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        omdb_api_key = config.get('omdb_api_key')
        if not omdb_api_key:
            return None
            
        params = {'apikey': omdb_api_key, 't': title}
        if year:
            params['y'] = str(year)
            
        response = requests.get('http://www.omdbapi.com/', params=params)
        data = response.json()
        
        if data.get('Response') == 'True':
            for rating in data.get('Ratings', []):
                if rating['Source'] == 'Rotten Tomatoes':
                    return int(rating['Value'].rstrip('%'))
        return None
        
    except Exception as e:
        print(f"Error getting RT score for {title}: {e}")
        return None

def test_simple_rt():
    """Test with known movies"""
    test_movies = [
        ("Deadpool & Wolverine", 2024),
        ("Inside Out 2", 2024),
        ("Beetlejuice Beetlejuice", 2024),
        ("The Wild Robot", 2024),
        ("Ebony & Ivory", 2024)
    ]
    
    print("Testing Simple RT Fetcher (OMDb only):")
    print("=" * 40)
    
    for title, year in test_movies:
        score = get_rt_score_omdb(title, year)
        if score is not None:
            print(f"✅ {title}: {score}%")
        else:
            print(f"❌ {title}: No score found")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_simple_rt()
        else:
            title = sys.argv[1]
            year = int(sys.argv[2]) if len(sys.argv) > 2 else None
            score = get_rt_score_omdb(title, year)
            if score is not None:
                print(f"{title}: {score}%")
            else:
                print(f"{title}: No RT score found")
    else:
        print("Usage: python simple_rt_fetcher.py <title> [year]")
        print("       python simple_rt_fetcher.py test")
