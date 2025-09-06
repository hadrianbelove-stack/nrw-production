#!/usr/bin/env python3
"""
Concurrent daily scraper to bypass TMDB API pagination limits
Scrapes each day individually and aggregates results
"""
import json
import os
import requests
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set
from collections import defaultdict

class ConcurrentDailyScraper:
    def __init__(self):
        self.tmdb_key = os.getenv('TMDB_API_KEY', '8de2836bb5d0aa68de7b9c81e5b62c2c')
        self.base_url = "https://api.themoviedb.org/3"
        self.session = requests.Session()
    
    def fetch_movies_for_date(self, date_str: str, max_pages: int = 10) -> Dict:
        """Fetch all movies for a specific date"""
        movies = {}
        page_count = 0
        
        print(f"  Scraping {date_str}...")
        
        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/discover/movie"
            params = {
                'api_key': self.tmdb_key,
                'region': 'US',
                'primary_release_date.gte': date_str,
                'primary_release_date.lte': date_str,
                'sort_by': 'popularity.desc',
                'page': page
            }
            
            try:
                response = self.session.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    page_movies = data.get('results', [])
                    
                    if not page_movies:
                        break
                    
                    page_count += 1
                    for movie in page_movies:
                        movie_id = movie.get('id')
                        if movie_id:
                            movies[movie_id] = movie
                    
                    # Longer delay to respect rate limits
                    time.sleep(0.5)
                else:
                    print(f"    Error {response.status_code} for {date_str} page {page}")
                    break
            except Exception as e:
                print(f"    Exception for {date_str} page {page}: {e}")
                break
        
        print(f"    {date_str}: {len(movies)} unique movies from {page_count} pages")
        return {
            'date': date_str,
            'movies': movies,
            'page_count': page_count
        }
    
    def fetch_sequential_by_date(self, days: int = 45) -> List[Dict]:
        """Fetch movies sequentially by date to avoid rate limits"""
        print(f"=== SEQUENTIAL DAILY SCRAPER ===")
        print(f"Fetching movies from last {days} days (sequential to avoid rate limits)")
        
        # Generate date list
        end_date = datetime.now()
        dates = []
        for i in range(days):
            date = end_date - timedelta(days=i)
            dates.append(date.strftime('%Y-%m-%d'))
        
        all_movies = {}
        date_stats = {}
        
        # Sequential execution with better rate limiting
        for i, date in enumerate(dates):
            print(f"Progress: {i+1}/{len(dates)} dates")
            try:
                result = self.fetch_movies_for_date(date, max_pages=5)
                date_movies = result['movies']
                date_stats[date] = {
                    'movie_count': len(date_movies),
                    'page_count': result['page_count']
                }
                
                # Merge movies (avoid duplicates)
                for movie_id, movie in date_movies.items():
                    if movie_id not in all_movies:
                        all_movies[movie_id] = movie
                
                # Longer delay between dates to avoid rate limits
                if i < len(dates) - 1:  # Don't sleep after last iteration
                    time.sleep(2)
                            
            except Exception as e:
                print(f"Error processing {date}: {e}")
        
        print(f"\n=== COLLECTION SUMMARY ===")
        total_unique = len(all_movies)
        total_across_dates = sum(stats['movie_count'] for stats in date_stats.values())
        print(f"Total unique movies: {total_unique}")
        print(f"Total across all dates: {total_across_dates}")
        print(f"Deduplication saved: {total_across_dates - total_unique} duplicates")
        
        # Show top dates by movie count
        sorted_dates = sorted(date_stats.items(), key=lambda x: x[1]['movie_count'], reverse=True)
        print(f"\nTop 10 dates by movie count:")
        for date, stats in sorted_dates[:10]:
            print(f"  {date}: {stats['movie_count']} movies ({stats['page_count']} pages)")
        
        return list(all_movies.values())
    
    def check_release_types_batch(self, movies: List[Dict]) -> List[Dict]:
        """Check release types for all movies (same as original)"""
        print(f"\n=== CHECKING RELEASE TYPES ===")
        digital_movies = []
        
        for i, movie in enumerate(movies):
            if (i + 1) % 50 == 0:
                print(f"  Checked {i + 1}/{len(movies)} movies...")
            
            movie_id = movie.get('id')
            if not movie_id:
                continue
            
            # Get release dates
            url = f"{self.base_url}/movie/{movie_id}/release_dates"
            params = {'api_key': self.tmdb_key}
            
            try:
                response = self.session.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    us_releases = []
                    
                    for result in data.get('results', []):
                        if result.get('iso_3166_1') == 'US':
                            us_releases.extend(result.get('release_dates', []))
                    
                    # Check for digital releases (types 4, 6)
                    has_digital = any(rel.get('type') in [4, 6] for rel in us_releases)
                    has_theatrical = any(rel.get('type') in [1, 2, 3] for rel in us_releases)
                    
                    if has_digital:
                        movie['has_digital'] = True
                        movie['release_info'] = us_releases
                        digital_movies.append(movie)
                    elif has_theatrical and self._likely_digital_now(movie):
                        movie['likely_digital'] = True
                        movie['release_info'] = us_releases
                        digital_movies.append(movie)
                        
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                print(f"    Error checking movie {movie_id}: {e}")
                continue
        
        print(f"\nFound {len(digital_movies)} movies with digital releases")
        return digital_movies
    
    def _likely_digital_now(self, movie: Dict) -> bool:
        """Check if theatrical movie is likely digital now"""
        release_date = movie.get('release_date')
        if not release_date:
            return False
        
        try:
            release = datetime.strptime(release_date, '%Y-%m-%d')
            weeks_since_release = (datetime.now() - release).days / 7
            return weeks_since_release >= 12  # 3+ months
        except:
            return False
    
    def enrich_movies(self, movies: List[Dict]) -> List[Dict]:
        """Add additional data to movies (same as original)"""
        print(f"\n=== ENRICHING {len(movies)} MOVIES ===")
        
        enriched = []
        for i, movie in enumerate(movies):
            if (i + 1) % 20 == 0:
                print(f"  Enriched {i + 1}/{len(movies)} movies...")
            
            # Get digital release date
            digital_date = self._get_digital_release_date(movie)
            movie['digital_date'] = digital_date
            
            # Get streaming providers
            providers = self._get_watch_providers(movie.get('id'))
            movie['providers'] = providers
            
            enriched.append(movie)
            time.sleep(0.1)
        
        return enriched
    
    def _get_digital_release_date(self, movie: Dict) -> str:
        """Extract digital release date from release info"""
        releases = movie.get('release_info', [])
        
        # Look for digital release (type 4, 6)
        for release in releases:
            if release.get('type') in [4, 6]:
                return release.get('release_date', '')
        
        # Fallback to primary release date
        return movie.get('release_date', '')
    
    def _get_watch_providers(self, movie_id: int) -> List[str]:
        """Get watch providers for movie"""
        if not movie_id:
            return []
        
        url = f"{self.base_url}/movie/{movie_id}/watch/providers"
        params = {'api_key': self.tmdb_key}
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                us_data = data.get('results', {}).get('US', {})
                
                providers = []
                for key in ['flatrate', 'rent', 'buy']:
                    if key in us_data:
                        providers.extend([p.get('provider_name', '') for p in us_data[key]])
                
                return list(set(providers))  # Remove duplicates
        except:
            pass
        
        return []
    
    def save_output(self, movies: List[Dict]) -> str:
        """Save movies to JSON file"""
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, "data.json")
        
        # Format for consistency with existing system
        formatted = []
        for movie in movies:
            formatted_movie = {
                movie.get('title', 'Unknown'): {
                    'title': movie.get('title', 'Unknown'),
                    'year': movie.get('release_date', '')[:4] if movie.get('release_date') else '2025',
                    'digital_date': movie.get('digital_date', ''),
                    'poster': f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else '',
                    'overview': movie.get('overview', ''),
                    'tmdb_id': movie.get('id'),
                    'popularity': movie.get('popularity', 0),
                    'vote_average': movie.get('vote_average', 0),
                    'providers': movie.get('providers', []),
                    'has_digital': movie.get('has_digital', False),
                    'likely_digital': movie.get('likely_digital', False),
                }
            }
            formatted.append(formatted_movie)
        
        with open(filename, 'w') as f:
            json.dump(formatted, f, indent=2)
        
        print(f"\n✓ Saved {len(formatted)} movies to {filename}")
        return filename

def main():
    """Run the sequential daily scraper"""
    scraper = ConcurrentDailyScraper()
    
    # Step 1: Fetch movies sequentially by date
    all_movies = scraper.fetch_sequential_by_date(days=45)
    
    # Step 2: Filter for digital releases
    digital_movies = scraper.check_release_types_batch(all_movies)
    
    # Step 3: Enrich with additional data
    enriched_movies = scraper.enrich_movies(digital_movies)
    
    # Step 4: Save results
    output_file = scraper.save_output(enriched_movies)
    
    print(f"\n=== FINAL SUMMARY ===")
    print(f"Total movies collected: {len(all_movies)}")
    print(f"Digital movies found: {len(digital_movies)}")
    print(f"Movies saved: {len(enriched_movies)}")
    print(f"Output file: {output_file}")

if __name__ == "__main__":
    main()