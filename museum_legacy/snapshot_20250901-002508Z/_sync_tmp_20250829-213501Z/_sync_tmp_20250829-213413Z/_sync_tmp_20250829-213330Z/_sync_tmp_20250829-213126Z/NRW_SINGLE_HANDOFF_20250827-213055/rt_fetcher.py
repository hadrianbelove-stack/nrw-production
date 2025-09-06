#!/usr/bin/env python3
"""
Consolidated RT Score Fetcher
Combines OMDb API, web scraping, and audience scores
Best features from all 5 RT fetcher implementations
"""

import requests
import yaml
import re
import json
import time
from urllib.parse import quote
from bs4 import BeautifulSoup
from typing import Optional, Dict, Tuple

class RTFetcher:
    """Unified RT score fetcher with multiple methods"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        try:
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                self.omdb_key = config.get('omdb_api_key')
        except:
            self.omdb_key = None
            print("Warning: No OMDb API key found in config.yaml")
    
    def get_scores(self, title: str, year: Optional[int] = None) -> Dict:
        """
        Get both critic and audience RT scores
        Returns: {'critic_score': int, 'audience_score': int, 'method': str}
        """
        result = {
            'critic_score': None,
            'audience_score': None,
            'method': None
        }
        
        # Try OMDb first (fastest, most reliable)
        if self.omdb_key:
            critic = self._get_omdb_score(title, year)
            if critic:
                result['critic_score'] = critic
                result['method'] = 'omdb'
                # OMDb doesn't provide audience scores, try scraping for that
                _, audience = self._scrape_rt_scores(title, year)
                result['audience_score'] = audience
                return result
        
        # Fallback to web scraping for both scores
        critic, audience = self._scrape_rt_scores_with_fallbacks(title, year)
        if critic or audience:
            result['critic_score'] = critic
            result['audience_score'] = audience
            result['method'] = 'scraping'
            
        return result
    
    def _get_omdb_score(self, title: str, year: Optional[int]) -> Optional[int]:
        """Get RT critic score from OMDb API (from simple_rt_fetcher.py)"""
        try:
            params = {'apikey': self.omdb_key, 't': title}
            if year:
                params['y'] = str(year)
                
            response = requests.get('http://www.omdbapi.com/', params=params, timeout=5)
            data = response.json()
            
            if data.get('Response') == 'True':
                for rating in data.get('Ratings', []):
                    if rating['Source'] == 'Rotten Tomatoes':
                        return int(rating['Value'].rstrip('%'))
        except Exception as e:
            print(f"OMDb error for {title}: {e}")
        return None
    
    def _build_rt_url(self, title: str, year: Optional[int]) -> str:
        """Build RT URL (from rt_score_collector.py)"""
        # Clean title for URL
        clean_title = re.sub(r'[^\w\s]', '', title).lower()
        clean_title = re.sub(r'\s+', '_', clean_title)
        
        if year:
            return f"https://www.rottentomatoes.com/m/{clean_title}_{year}"
        return f"https://www.rottentomatoes.com/m/{clean_title}"
    
    def _scrape_rt_scores(self, title: str, year: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        """
        Scrape both critic and audience scores from RT
        From rt_score_collector.py - unique audience score feature
        """
        url = self._build_rt_url(title, year)
        
        try:
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract critic score (Tomatometer)
                critic = None
                tomatometer = soup.find('score-board')
                if tomatometer:
                    critic_str = tomatometer.get('tomatometerscore')
                    if critic_str and critic_str.isdigit():
                        critic = int(critic_str)
                
                # Extract audience score (unique feature!)
                audience = None
                if tomatometer:
                    audience_str = tomatometer.get('audiencescore')
                    if audience_str and audience_str.isdigit():
                        audience = int(audience_str)
                
                # Fallback patterns
                if not critic:
                    critic_match = re.search(r'tomatometer[^>]*>(\d+)%', response.text, re.IGNORECASE)
                    critic = int(critic_match.group(1)) if critic_match else None
                
                if not audience:
                    audience_match = re.search(r'audience[^>]*score[^>]*>(\d+)%', response.text, re.IGNORECASE)
                    audience = int(audience_match.group(1)) if audience_match else None
                
                return critic, audience
        except Exception as e:
            pass
            
        return None, None
    
    def _scrape_rt_scores_with_fallbacks(self, title: str, year: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        """
        Try multiple scraping strategies (from rt_score_fetcher.py)
        """
        # Strategy 1: Try with year
        if year:
            critic, audience = self._scrape_rt_scores(title, year)
            if critic or audience:
                return critic, audience
        
        # Strategy 2: Try without year
        critic, audience = self._scrape_rt_scores(title, None)
        if critic or audience:
            return critic, audience
        
        # Strategy 3: Search and follow first result
        return self._search_and_scrape(title, year)
    
    def _search_and_scrape(self, title: str, year: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        """Search RT and follow first result (from rt_score_fetcher.py)"""
        search_url = f"https://www.rottentomatoes.com/search?search={quote(title)}"
        
        try:
            response = self.session.get(search_url, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find first movie result
                first_result = soup.find('search-page-media-row')
                if first_result:
                    link = first_result.find('a', href=True)
                    if link:
                        movie_url = f"https://www.rottentomatoes.com{link['href']}"
                        response = self.session.get(movie_url, timeout=5)
                        if response.status_code == 200:
                            return self._extract_scores_from_html(response.text)
        except:
            pass
            
        return None, None
    
    def _extract_scores_from_html(self, html: str) -> Tuple[Optional[int], Optional[int]]:
        """Extract scores from HTML with multiple patterns"""
        soup = BeautifulSoup(html, 'html.parser')
        
        critic = None
        audience = None
        
        # Try score-board element first
        score_board = soup.find('score-board')
        if score_board:
            critic_str = score_board.get('tomatometerscore')
            audience_str = score_board.get('audiencescore')
            critic = int(critic_str) if critic_str and critic_str.isdigit() else None
            audience = int(audience_str) if audience_str and audience_str.isdigit() else None
        
        # Fallback patterns
        if not critic:
            patterns = [
                r'tomatometer[^>]*>(\d+)%',
                r'"tomatometer"[^>]*>(\d+)',
                r'critics[^>]*score[^>]*>(\d+)%'
            ]
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    critic = int(match.group(1))
                    break
        
        if not audience:
            patterns = [
                r'audience[^>]*score[^>]*>(\d+)%',
                r'"audiencescore"[^>]*>(\d+)',
                r'popcorn[^>]*score[^>]*>(\d+)%'
            ]
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    audience = int(match.group(1))
                    break
        
        return critic, audience
    
    def bulk_update(self, filepath: str = 'output/data.json', 
                   limit: Optional[int] = None, 
                   show_progress: bool = True) -> int:
        """
        Bulk update scores for movies in data.json
        From fix_rt_scores.py with enhancements
        """
        try:
            with open(filepath, 'r') as f:
                movies = json.load(f)
        except FileNotFoundError:
            print(f"Error: {filepath} not found")
            return 0
        
        updated = 0
        failed = []
        
        movies_to_process = movies[:limit] if limit else movies
        total = len(movies_to_process)
        
        for i, movie in enumerate(movies_to_process, 1):
            if show_progress:
                print(f"[{i}/{total}] Processing {movie['title']}...", end=" ")
            
            # Skip if already has scores
            if movie.get('rt_score') and movie.get('rt_audience'):
                if show_progress:
                    print("⏭️  Already has scores")
                continue
            
            # Get scores
            scores = self.get_scores(movie['title'], movie.get('year'))
            
            # Update movie data
            if scores['critic_score'] or scores['audience_score']:
                if scores['critic_score']:
                    movie['rt_score'] = scores['critic_score']
                if scores['audience_score']:
                    movie['rt_audience'] = scores['audience_score']
                movie['rt_method'] = scores['method']
                updated += 1
                
                if show_progress:
                    critic = scores['critic_score'] or '—'
                    audience = scores['audience_score'] or '—'
                    print(f"✅ Critic: {critic}% | Audience: {audience}%")
            else:
                failed.append(movie['title'])
                if show_progress:
                    print("❌ No scores found")
            
            # Rate limiting
            time.sleep(0.5)
        
        # Save updated data
        with open(filepath, 'w') as f:
            json.dump(movies, f, indent=2)
        
        # Summary
        print(f"\n{'='*50}")
        print(f"✅ Updated: {updated} movies")
        print(f"❌ Failed: {len(failed)} movies")
        if failed and show_progress:
            print(f"Failed titles: {', '.join(failed[:5])}")
            if len(failed) > 5:
                print(f"... and {len(failed)-5} more")
        
        return updated

# Standalone functions for backward compatibility
def get_rt_score(title: str, year: Optional[int] = None) -> Optional[int]:
    """Simple function to get just critic score (backward compatible)"""
    fetcher = RTFetcher()
    scores = fetcher.get_scores(title, year)
    return scores['critic_score']

def test_fetcher():
    """Test the consolidated fetcher"""
    fetcher = RTFetcher()
    
    test_movies = [
        ("The Godfather", 1972),
        ("Barbie", 2023),
        ("Oppenheimer", 2023),
        ("The Smurfs", 2025),
        ("A Fake Movie That Doesn't Exist", 2024)
    ]
    
    print("Testing RT Fetcher...")
    print("="*50)
    
    for title, year in test_movies:
        scores = fetcher.get_scores(title, year)
        critic = scores['critic_score'] or '—'
        audience = scores['audience_score'] or '—'
        method = scores['method'] or 'none'
        print(f"{title} ({year})")
        print(f"  Critic: {critic}% | Audience: {audience}% | Method: {method}")
    
    print("="*50)
    print("Test complete!")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_fetcher()
        elif sys.argv[1] == "bulk":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
            fetcher = RTFetcher()
            fetcher.bulk_update(limit=limit)
    else:
        print("Usage:")
        print("  python rt_fetcher.py test        # Test the fetcher")
        print("  python rt_fetcher.py bulk [N]    # Update scores (N = limit)")