#!/usr/bin/env python3
"""
Fixed TMDB scraper that properly handles movies with multiple release types
Key insight: Movies can have BOTH theatrical (3) and digital (4) releases
We should include any movie that has type 4, regardless of other types
"""

import json
import requests
import time
import argparse
import constants
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any

class ProperTMDBScraper:
    """TMDB scraper that correctly handles multi-type releases"""
    
    RELEASE_TYPES = {
        1: "Premiere",
        2: "Theatrical (limited)",
        3: "Theatrical",
        4: "Digital",
        5: "Physical",
        6: "TV"
    }
    
    def __init__(self, api_key="99b122ce7fa3e9065d7b7dc6e660772d", omdb_key="8eb019b"):
        self.tmdb_key = api_key
        self.omdb_key = omdb_key
        self.base_url = "https://api.themoviedb.org/3"
        
    def fetch_recent_movies(self, days=30, max_pages=10) -> List[Dict]:
        """
        Fetch ALL recent movies, then filter by release type presence
        Instead of using release_type in query, we check each movie's actual releases
        """
        print(f"Fetching movies from last {days} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        all_movies = {}
        
        # Step 1: Get ALL movies from the time period (no release_type filter)
        print("\nStep 1: Fetching all recent movies (no type filter)...")
        
        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/discover/movie"
            params = {
                'api_key': self.tmdb_key,
                'region': 'US',
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc',
                'page': page
            }
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                movies = data.get('results', [])
                
                if not movies:
                    break
                
                for movie in movies:
                    all_movies[movie['id']] = movie
                
                print(f"  Page {page}: Found {len(movies)} movies (total: {len(all_movies)})")
            
            time.sleep(0.25)  # Rate limiting
        
        print(f"\nTotal movies found: {len(all_movies)}")
        
        # Step 2: Check each movie's actual release types
        print("\nStep 2: Checking release types for each movie...")
        
        movies_with_digital = []
        movies_theatrical_only = []
        movies_unknown = []
        
        for i, (movie_id, movie) in enumerate(all_movies.items(), 1):
            if i % 10 == 0:
                print(f"  Checked {i}/{len(all_movies)} movies...")
            
            # Get detailed release information
            release_info = self.get_release_types(movie_id)
            
            movie['us_release_types'] = release_info['types']
            movie['us_releases'] = release_info['releases']
            movie['digital_date'] = release_info['digital_date']
            movie['theatrical_date'] = release_info['theatrical_date']
            movie['has_digital'] = 4 in release_info['types'] or 6 in release_info['types']
            movie['has_theatrical'] = 2 in release_info['types'] or 3 in release_info['types']
            
            # Categorize
            if movie['has_digital']:
                movies_with_digital.append(movie)
            elif movie['has_theatrical']:
                movies_theatrical_only.append(movie)
            else:
                movies_unknown.append(movie)
            
            time.sleep(0.1)  # Rate limiting
        
        print(f"\nRelease type breakdown:")
        print(f"  Digital available: {len(movies_with_digital)}")
        print(f"  Theatrical only: {len(movies_theatrical_only)}")
        print(f"  Unknown/Other: {len(movies_unknown)}")
        
        # Step 3: Include theatrical movies that are old enough to likely be digital
        print("\nStep 3: Including likely-digital theatrical releases...")
        
        likely_digital = []
        digital_window_days = 30  # Theatrical usually goes digital after 30 days
        
        for movie in movies_theatrical_only:
            theatrical_date = movie.get('theatrical_date')
            if theatrical_date:
                try:
                    release_dt = datetime.strptime(theatrical_date[:10], '%Y-%m-%d')
                    days_since_theatrical = (datetime.now() - release_dt).days
                    
                    if days_since_theatrical >= digital_window_days:
                        movie['likely_digital'] = True
                        movie['days_since_theatrical'] = days_since_theatrical
                        likely_digital.append(movie)
                except:
                    pass
        
        print(f"  Added {len(likely_digital)} theatrical releases likely digital now")
        
        # Step 4: Combine and enrich all qualifying movies
        final_movies = movies_with_digital + likely_digital
        
        print(f"\nStep 4: Enriching {len(final_movies)} movies with additional data...")
        
        enriched = []
        for movie in final_movies:
            enriched_movie = self.enrich_movie(movie)
            enriched.append(enriched_movie)
        
        # Sort by relevance
        enriched.sort(key=self.calculate_priority, reverse=True)
        
        return enriched
    
    def get_release_types(self, movie_id: int) -> Dict:
        """Get all US release types for a movie"""
        url = f"{self.base_url}/movie/{movie_id}/release_dates"
        params = {'api_key': self.tmdb_key}
        
        result = {
            'types': [],
            'releases': [],
            'digital_date': None,
            'theatrical_date': None
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                
                # Find US releases
                for country in data.get('results', []):
                    if country['iso_3166_1'] == 'US':
                        for release in country['release_dates']:
                            release_type = release['type']
                            release_date = release['release_date']
                            
                            result['types'].append(release_type)
                            result['releases'].append({
                                'type': release_type,
                                'type_name': self.RELEASE_TYPES.get(release_type, f"Type {release_type}"),
                                'date': release_date,
                                'note': release.get('note', '')
                            })
                            
                            # Track earliest digital and theatrical dates
                            if release_type in [4, 6]:  # Digital or TV
                                if not result['digital_date'] or release_date < result['digital_date']:
                                    result['digital_date'] = release_date
                            elif release_type in [2, 3]:  # Theatrical
                                if not result['theatrical_date'] or release_date < result['theatrical_date']:
                                    result['theatrical_date'] = release_date
                        
                        break
        except Exception as e:
            print(f"    Error getting release types for movie {movie_id}: {e}")
        
        return result
    
    def enrich_movie(self, movie: Dict) -> Dict:
        """Add streaming providers, scores, and other data"""
        movie_id = movie['id']
        
        # Get watch providers
        url = f"{self.base_url}/movie/{movie_id}/watch/providers"
        params = {'api_key': self.tmdb_key}
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                us_providers = response.json().get('results', {}).get('US', {})
                
                all_providers = []
                provider_categories = {}
                
                if 'flatrate' in us_providers:
                    providers = [p['provider_name'] for p in us_providers['flatrate']]
                    all_providers.extend(providers)
                    provider_categories['streaming'] = providers
                
                if 'rent' in us_providers:
                    providers = [p['provider_name'] for p in us_providers['rent']]
                    all_providers.extend(providers)
                    provider_categories['rent'] = providers
                
                if 'buy' in us_providers:
                    providers = [p['provider_name'] for p in us_providers['buy']]
                    all_providers.extend(providers)
                    provider_categories['buy'] = providers
                
                movie['providers'] = list(set(all_providers))
                movie['provider_categories'] = provider_categories
                movie['justwatch_url'] = us_providers.get('link', '')
        except:
            movie['providers'] = []
            movie['provider_categories'] = {}
        
        # Try to get RT score from OMDb
        if self.omdb_key:
            try:
                url = "http://www.omdbapi.com/"
                params = {
                    'apikey': self.omdb_key,
                    't': movie['title'],
                    'y': movie.get('release_date', '')[:4] if movie.get('release_date') else None,
                    'type': 'movie'
                }
                
                response = requests.get(url, params=params, timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('Response') == 'True':
                        for rating in data.get('Ratings', []):
                            if rating['Source'] == 'Rotten Tomatoes':
                                rt_score = rating['Value'].replace('%', '')
                                movie['rt_score'] = int(rt_score) if rt_score.isdigit() else None
                                break
                        
                        movie['imdb_rating'] = data.get('imdbRating')
            except:
                pass
        
        # Get detailed movie information
        details = self.tmdb_movie_details(movie_id)
        movie.update(details)
        
        # Format data
        movie['poster'] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get('poster_path') else ''
        movie['year'] = movie.get('release_date', '')[:4] if movie.get('release_date') else ''
        
        # Add additional URLs
        movie['tmdb_url'] = f"https://www.themoviedb.org/movie/{movie_id}"
        movie['rt_url'] = f"https://www.rottentomatoes.com/search?search={movie['title'].replace(' ', '%20')}"
        movie['wikipedia_url'] = self.get_wikipedia_url(movie['title'], movie['year'])
        
        # Get studio (first production company)
        if details['production_companies']:
            movie['studio'] = details['production_companies'][0].get('name')
        else:
            movie['studio'] = None
            
        # Create inclusion reason
        movie['inclusion_reason'] = self.get_inclusion_reason(movie)
        
        return movie
    
    def get_inclusion_reason(self, movie: Dict) -> str:
        """Generate clear reason for inclusion"""
        reasons = []
        
        # Release type info
        if movie.get('has_digital'):
            if movie.get('digital_date'):
                date = movie['digital_date'][:10]
                reasons.append(f"Digital release: {date}")
            else:
                reasons.append("Digital release available")
        elif movie.get('likely_digital'):
            days = movie.get('days_since_theatrical', 0)
            reasons.append(f"Theatrical {days} days ago (likely digital)")
        
        # Provider info
        if movie.get('providers'):
            count = len(movie['providers'])
            categories = movie.get('provider_categories', {})
            
            if 'rent' in categories:
                reasons.append(f"Rentable on {len(categories['rent'])} platforms")
            if 'streaming' in categories:
                reasons.append(f"Streaming on {len(categories['streaming'])} platforms")
        
        # Popularity indicators
        if movie.get('popularity', 0) > 100:
            reasons.append("High popularity")
        elif movie.get('vote_average', 0) > 7.5 and movie.get('vote_count', 0) > 50:
            reasons.append(f"Highly rated ({movie['vote_average']}/10)")
        
        return " • ".join(reasons) if reasons else "Recent release"

    def tmdb_movie_details(self, tmdb_id: int) -> Dict:
        """Get director, cast, and other details."""
        try:
            # Get credits
            credits_url = f"{self.base_url}/movie/{tmdb_id}/credits"
            credits_response = requests.get(credits_url, params={'api_key': self.tmdb_key})
            credits = credits_response.json()
            
            # Find director
            director = None
            for crew in credits.get("crew", []):
                if crew.get("job") == "Director":
                    director = crew.get("name")
                    break
            
            # Get top 3 cast
            cast_list = []
            for actor in credits.get("cast", [])[:3]:
                cast_list.append(actor.get("name"))
            cast = ", ".join(cast_list) if cast_list else None
            
            # Get movie details
            details_url = f"{self.base_url}/movie/{tmdb_id}"
            details_response = requests.get(details_url, params={'api_key': self.tmdb_key})
            details = details_response.json()
            
            # Get content rating
            release_info_url = f"{self.base_url}/movie/{tmdb_id}/release_dates"
            release_response = requests.get(release_info_url, params={'api_key': self.tmdb_key})
            release_info = release_response.json()
            
            rating = None
            for country in release_info.get("results", []):
                if country["iso_3166_1"] == "US":
                    for release in country["release_dates"]:
                        if release.get("certification"):
                            rating = release["certification"]
                            break
                    break
            
            time.sleep(0.1)  # Rate limiting
            
            return {
                "director": director,
                "cast": cast,
                "runtime": details.get("runtime"),
                "overview": details.get("overview"),
                "production_companies": details.get("production_companies", []),
                "rating": rating or "NR"
            }
        except Exception as e:
            print(f"Error getting details for movie {tmdb_id}: {e}")
            return {
                "director": None,
                "cast": None,
                "runtime": None,
                "overview": None,
                "production_companies": [],
                "rating": "NR"
            }

    def get_wikipedia_url(self, title: str, year: str) -> str:
        """Generate Wikipedia URL (basic approach)."""
        # This is simplified - in production you'd use Wikipedia API
        search_title = title.replace(" ", "_")
        return f"https://en.wikipedia.org/wiki/{search_title}_(film)"
    
    def calculate_priority(self, movie: Dict) -> float:
        """Calculate sort priority for display order"""
        score = 0
        
        # Confirmed digital release is highest priority
        if movie.get('has_digital'):
            score += 1000
            # More recent digital releases score higher
            if movie.get('digital_date'):
                days_since = (datetime.now() - datetime.strptime(movie['digital_date'][:10], '%Y-%m-%d')).days
                score += max(0, 100 - days_since)
        
        # Likely digital is next priority
        if movie.get('likely_digital'):
            score += 500
            # Longer since theatrical = more likely to be digital
            score += min(movie.get('days_since_theatrical', 0), 90)
        
        # Has providers is important
        if movie.get('providers'):
            score += 200 + (len(movie['providers']) * 10)
        
        # Popularity and ratings
        score += min(movie.get('popularity', 0), 200)
        score += movie.get('vote_average', 0) * 10
        score += min(movie.get('vote_count', 0) / 10, 100)
        
        return score
    
    def save_output(self, movies: List[Dict], filename='output/data.json'):
        """Save in format compatible with existing pipeline"""
        # Format for adapter.py compatibility
        formatted = []
        for movie in movies:
            formatted_movie = {
                'title': movie.get('title', ''),
                'year': movie.get('year', ''),
                'release_date': movie.get('release_date', ''),
                'poster': movie.get('poster', ''),
                'tmdb_id': movie.get('id', 0),
                'tmdb_vote': movie.get('vote_average', 0),
                'rt_score': movie.get('rt_score'),
                'providers': movie.get('providers', []),
                'overview': movie.get('overview', ''),
                'inclusion_reason': movie.get('inclusion_reason', ''),
                'has_digital': movie.get('has_digital', False),
                'digital_date': movie.get('digital_date', ''),
                'theatrical_date': movie.get('theatrical_date', ''),
                'justwatch_url': movie.get('justwatch_url', ''),
                # Enhanced data fields
                'director': movie.get('director'),
                'cast': movie.get('cast'),
                'runtime': movie.get('runtime'),
                'studio': movie.get('studio'),
                'rating': movie.get('rating', 'NR'),
                'tmdb_url': movie.get('tmdb_url', ''),
                'rt_url': movie.get('rt_url', ''),
                'wikipedia_url': movie.get('wikipedia_url', ''),
                'review_data': {
                    'rt_score': str(movie['rt_score']) if movie.get('rt_score') else None,
                    'imdb_rating': movie.get('imdb_rating')
                }
            }
            formatted.append(formatted_movie)
        
        with open(filename, 'w') as f:
            json.dump(formatted, f, indent=2)
        
        print(f"\nSaved {len(formatted)} movies to {filename}")
        return filename


def main():
    """Run the fixed TMDB scraper"""
    parser = argparse.ArgumentParser(description='TMDB scraper with proper release type handling')
    parser.add_argument("--region", default="US", help="Region code (default: US)")
    parser.add_argument("--days", type=int, default=45, help="Days to look back (default: 45)")
    parser.add_argument("--max-pages", type=int, default=15, help="Max pages to fetch (default: 15)")
    parser.add_argument("--use-core", action="store_true", help="Use scraper_core helpers for providers/details/credits")
    parser.add_argument("--core-limit", type=int, default=100, help="When --use-core, enrich at most this many movies")
    parser.add_argument("--providers-only", action="store_true", help="Use core enrichment for providers only (fast path)")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("="*60)
    print("FIXED TMDB SCRAPER - Proper Release Type Handling")
    print("="*60)
    print(f"Region: {args.region}, Days: {args.days}, Max Pages: {args.max_pages}")
    if args.use_core:
        print(f"Using scraper_core enrichment (limit: {args.core_limit})")
    
    scraper = ProperTMDBScraper()
    
    # Fetch movies with proper type checking
    movies = scraper.fetch_recent_movies(days=args.days, max_pages=args.max_pages)
    
    # Save output
    output_file = scraper.save_output(movies)
    
    # Core enrichment if requested
    if args.use_core:
        try:
            from scraper_core import get_release_types, get_providers, get_details, get_credits, normalize_record
            tmdb = None
            region = args.region.upper()
            enriched: list[Dict[str, Any]] = []
            to_enrich = movies[: args.core_limit]
            logging.info("Core-enrichment starting for %d of %d movies (limit=%d)", len(to_enrich), len(movies), args.core_limit)
            
            for idx, m in enumerate(to_enrich, 1):
                try:
                    if "id" not in m:
                        continue
                    rtypes = get_release_types(tmdb, int(m["id"]), region)
                    prov = get_providers(tmdb, int(m["id"]), region)
                    det = get_details(tmdb, int(m["id"]))
                    cre = get_credits(tmdb, int(m["id"]))
                    rec = normalize_record(m, prov, rtypes, det, cre)
                    enriched.append(rec)
                except Exception as e:
                    logging.warning("enrich failed for %s: %s", m.get("id"), e)
                if idx % 10 == 0:
                    logging.info("Core-enrichment progress: %d/%d", idx, len(to_enrich))
            
            # Write core-enriched output
            try:
                import os
                os.makedirs("output", exist_ok=True)
                with open("output/data_core.json", "w", encoding="utf-8") as f:
                    json.dump(enriched, f, ensure_ascii=False, indent=2)
                logging.info("Wrote output/data_core.json using core helpers (%d items)", len(enriched))
            except Exception as e:
                logging.error("Failed writing output/data_core.json: %s", e)
        except ImportError as e:
            logging.error("Cannot import scraper_core: %s", e)
        except Exception as e:
            logging.error("Core enrichment failed: %s", e)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total movies found: {len(movies)}")
    
    # Breakdown by status
    with_digital = [m for m in movies if m.get('has_digital')]
    likely_digital = [m for m in movies if m.get('likely_digital')]
    with_providers = [m for m in movies if m.get('providers')]
    
    print(f"\nBy release status:")
    print(f"  Confirmed digital: {len(with_digital)}")
    print(f"  Likely digital: {len(likely_digital)}")
    print(f"  With providers: {len(with_providers)}")
    
    # Show top 10
    print(f"\nTop 10 movies:")
    for i, movie in enumerate(movies[:10], 1):
        providers = movie.get('providers', [])
        provider_str = f" ({', '.join(providers[:3])})" if providers else " (No providers yet)"
        
        print(f"\n{i}. {movie['title']} ({movie.get('year', 'Unknown')})")
        print(f"   {movie['inclusion_reason']}")
        if providers:
            print(f"   Available on: {provider_str}")
        
        # Show release types
        if movie.get('us_release_types'):
            types = [f"{t}:{scraper.RELEASE_TYPES.get(t, t)}" for t in movie['us_release_types']]
            print(f"   Release types: {', '.join(types)}")
    
    # Check for specific movies
    print(f"\n" + "="*60)
    print("CHECKING FOR KNOWN MISSING MOVIES")
    print("="*60)
    
    target_titles = ["Eddington", "Ebony & Ivory", "Elio", "Wicked", "Gladiator II", "Red One"]
    found_titles = {m['title'].lower(): m for m in movies}
    
    for target in target_titles:
        if target.lower() in found_titles:
            movie = found_titles[target.lower()]
            print(f"✓ {target} - FOUND")
            print(f"  Types: {movie.get('us_release_types', [])}")
            print(f"  Digital: {movie.get('has_digital', False)}")
        else:
            print(f"✗ {target} - NOT FOUND")


if __name__ == "__main__":
    main()


# PROVIDERS_ONLY_FASTPATH
try:
    import builtins
    args = builtins.__NRW_ARGS__
    if args.use_core and args.providers_only:
        from scraper_core import get_providers, get_details, get_credits, get_release_types, normalize_record
        region = args.region.upper()
        try:
            to_enrich = movies[: args.core_limit]
        except Exception:
            to_enrich = []
        enriched = []
        for m in to_enrich:
            try:
                mid = int(m.get("id"))
                # Only providers + minimal release types; skip heavy details/credits to save calls
                prov = get_providers(None, mid, region)
                rtypes = get_release_types(None, mid, region)
                det = {}
                cre = {}
                enriched.append(normalize_record(m, prov, rtypes, det, cre))
            except Exception as e:
                import logging; logging.warning("providers-only enrich failed: %s", e)
        import json, os; os.makedirs("output", exist_ok=True)
        with open("output/data_core.json", "w", encoding="utf-8") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)
except Exception:
    pass
