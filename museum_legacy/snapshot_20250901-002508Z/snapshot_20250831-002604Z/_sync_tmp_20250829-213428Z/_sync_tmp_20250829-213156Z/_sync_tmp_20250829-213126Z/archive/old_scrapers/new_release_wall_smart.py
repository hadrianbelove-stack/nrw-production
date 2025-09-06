"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
import argparse, os, sys, json, time
from datetime import datetime, timedelta
import requests, yaml
from jinja2 import Template

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def check_has_reviews(title, year, config):
    """Check if movie has critical reviews via OMDb"""
    try:
        params = {
            'apikey': config['omdb_api_key'],
            't': title,
        }
        if year:
            params['y'] = str(year)
            
        response = requests.get('http://www.omdbapi.com/', params=params)
        data = response.json()
        
        if data.get('Response') == 'True':
            review_info = {}
            
            # Check Metacritic
            if data.get('Metascore', 'N/A') != 'N/A':
                review_info['metacritic'] = data['Metascore']
            
            # Check Rotten Tomatoes
            for rating in data.get('Ratings', []):
                if rating['Source'] == 'Rotten Tomatoes':
                    review_info['rt_score'] = rating['Value'].rstrip('%')
            
            # Check IMDB votes
            votes_str = data.get('imdbVotes', '0').replace(',', '').replace('N/A', '0')
            if votes_str and votes_str != '0':
                votes = int(votes_str)
                if votes > 50:  # At least 50 IMDB votes
                    review_info['imdb_votes'] = votes
                    review_info['imdb_rating'] = data.get('imdbRating', 'N/A')
            
            # Return True if ANY review source exists
            if review_info:
                return True, review_info
                
        return False, None
    except Exception as e:
        print(f"  Error checking {title}: {e}")
        return False, None

def get_smart_releases(region="US", days=14, max_pages=5, min_reviews=True):
    """Get releases with smart filtering"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Calculate date range
    today = datetime.now()
    start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    
    print(f"Fetching releases from {start_date} to {end_date}...")
    
    all_movies = []
    
    # Fetch multiple pages
    for page in range(1, max_pages + 1):
        print(f"\nFetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': region,
            'with_release_type': '4|6',  # Digital and TV
            'primary_release_date.gte': start_date,
            'primary_release_date.lte': end_date,
            'sort_by': 'release_date.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        movies = response.json().get('results', [])
        
        if not movies:
            break
            
        all_movies.extend(movies)
        time.sleep(0.3)  # Be nice to API
    
    print(f"\nFound {len(all_movies)} total movies. Filtering...")
    
    # Smart filtering
    curated = []
    skipped_no_reviews = []
    
    for movie in all_movies:
        title = movie.get('title', '')
        year = movie.get('release_date', '')[:4] if movie.get('release_date') else None
        
        # Determine if we should include this movie
        include = False
        reason = ""
        review_data = {}
        
        # Auto-include if already popular on TMDB
        if movie.get('vote_count', 0) >= 50:
            include = True
            reason = f"Popular on TMDB ({movie['vote_count']} votes)"
            print(f"  ✓ {title[:40]:40} | {reason}")
        
        # Auto-include if high popularity score
        elif movie.get('popularity', 0) >= 20:
            include = True
            reason = f"High buzz (popularity: {movie['popularity']:.1f})"
            print(f"  ✓ {title[:40]:40} | {reason}")
        
        # Check for critical reviews
        elif min_reviews and title:
            time.sleep(0.2)  # Rate limit for OMDb
            has_review, review_info = check_has_reviews(title, year, config)
            
            if has_review:
                include = True
                review_data = review_info
                # Create readable reason
                parts = []
                if 'rt_score' in review_info:
                    parts.append(f"RT: {review_info['rt_score']}%")
                if 'metacritic' in review_info:
                    parts.append(f"Meta: {review_info['metacritic']}")
                if 'imdb_votes' in review_info:
                    parts.append(f"IMDB: {review_info['imdb_votes']} votes")
                reason = " | ".join(parts)
                print(f"  ✓ {title[:40]:40} | {reason}")
            else:
                skipped_no_reviews.append(title)
                print(f"  ✗ {title[:40]:40} | No reviews found")
        
        # Include major language films with some activity
        elif movie.get('original_language') in ['en'] and movie.get('vote_count', 0) >= 5:
            include = True
            reason = f"English with {movie['vote_count']} votes"
            print(f"  ✓ {title[:40]:40} | {reason}")
        
        if include:
            # Add our filtering metadata
            movie['inclusion_reason'] = reason
            movie['review_data'] = review_data
            curated.append(movie)
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(curated)} movies passed filters")
    print(f"Skipped {len(skipped_no_reviews)} movies without reviews")
    
    # Sort by combination of date and importance
    curated.sort(key=lambda x: (
        x.get('release_date', ''),
        x.get('popularity', 0),
        x.get('vote_count', 0)
    ), reverse=True)
    
    return curated

def get_watch_providers(movie_id, region, api_key):
    """Get streaming providers for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    try:
        response = requests.get(url, params={'api_key': api_key})
        data = response.json()
        
        providers = []
        if 'results' in data and region in data['results']:
            region_data = data['results'][region]
            for provider_type in ['flatrate', 'rent', 'buy']:
                if provider_type in region_data:
                    for provider in region_data[provider_type]:
                        name = provider['provider_name']
                        if name not in providers:
                            providers.append(name)
        
        return providers
    except:
        return []

def generate_html(movies):
    """Generate HTML output"""
    os.makedirs('output/site', exist_ok=True)
    
    with open('templates/site.html', 'r') as f:
        template = Template(f.read())
    
    # Process movies for display
    for movie in movies:
        # Add poster URL
        if movie.get('poster_path'):
            movie['poster'] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
        
        # Extract RT score if available
        if 'review_data' in movie and 'rt_score' in movie['review_data']:
            movie['rt_score'] = movie['review_data']['rt_score']
        
        # Build display title with year
        year = movie.get('release_date', '')[:4] if movie.get('release_date') else ''
        movie['year'] = year
        
        # TMDB vote
        movie['tmdb_vote'] = movie.get('vote_average')
    
    html = template.render(items=movies)
    
    with open('output/site/index.html', 'w') as f:
        f.write(html)
    
    print(f"Generated HTML with {len(movies)} movies")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', default='US')
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--max-pages', type=int, default=5)
    parser.add_argument('--check-reviews', action='store_true', default=True)
    args = parser.parse_args()
    
    # Get smart filtered movies
    movies = get_smart_releases(
        region=args.region,
        days=args.days,
        max_pages=args.max_pages,
        min_reviews=args.check_reviews
    )
    
    # Add streaming providers
    config = load_config()
    print("\nFetching streaming providers...")
    for movie in movies[:20]:  # Only check first 20 to save time
        providers = get_watch_providers(movie['id'], args.region, config['tmdb_api_key'])
        movie['providers'] = providers
        if providers:
            print(f"  {movie['title'][:30]:30} | {', '.join(providers[:3])}")
    
    # Generate output
    generate_html(movies)
    
    print(f"\n✓ Complete! View at http://localhost:8080")
    print(f"  Found {len(movies)} curated releases")
    print(f"  {sum(1 for m in movies if m.get('providers'))} have streaming info")

if __name__ == "__main__":
    main()
