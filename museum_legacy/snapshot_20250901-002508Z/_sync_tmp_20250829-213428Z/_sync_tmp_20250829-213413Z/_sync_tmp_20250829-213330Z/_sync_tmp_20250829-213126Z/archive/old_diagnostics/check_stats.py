"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
import json
import os
from collections import Counter

def analyze_current_data():
    """Quick analysis of what we have so far"""
    
    # Check for test data from our improved script
    if os.path.exists('test_discover.json'):
        with open('test_discover.json', 'r') as f:
            data = json.load(f)
            movies = data.get('results', [])
            
        print("📊 Current Data Analysis")
        print("=" * 50)
        print(f"Total movies found: {len(movies)}")
        
        # Language breakdown
        languages = Counter(m.get('original_language', 'unknown') for m in movies)
        print(f"\nLanguages:")
        for lang, count in languages.most_common(5):
            print(f"  {lang}: {count}")
        
        # Movies with votes
        with_votes = [m for m in movies if m.get('vote_count', 0) > 0]
        print(f"\nMovies with votes: {len(with_votes)}")
        
        # Average popularity
        avg_pop = sum(m.get('popularity', 0) for m in movies) / len(movies) if movies else 0
        print(f"Average popularity: {avg_pop:.1f}")
        
        # Sample of titles
        print(f"\nSample titles:")
        for m in movies[:5]:
            print(f"  - {m.get('title', 'Unknown')[:40]:40} | Votes: {m.get('vote_count', 0)}")

if __name__ == "__main__":
    analyze_current_data()
