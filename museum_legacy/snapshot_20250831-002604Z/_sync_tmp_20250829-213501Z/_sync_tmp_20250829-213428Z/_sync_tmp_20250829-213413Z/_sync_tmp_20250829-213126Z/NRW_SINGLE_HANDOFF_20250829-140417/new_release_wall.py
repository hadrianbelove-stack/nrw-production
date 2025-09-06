import argparse, os, sys, json, time
from datetime import datetime, timedelta
import requests, yaml
from jinja2 import Template

def load_config():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    # Initialize cache directory
    cache_dir = "cache"
    os.makedirs(cache_dir, exist_ok=True)
    config['cache_dir'] = cache_dir
    
    return config

# Global cache variables
_review_cache = None
_provider_cache = None
_release_cache = None

def load_cache(cache_dir):
    """Load all caches"""
    global _review_cache, _provider_cache, _release_cache
    
    # Load review cache
    review_cache_file = f"{cache_dir}/review_cache.json"
    if os.path.exists(review_cache_file):
        with open(review_cache_file, 'r') as f:
            _review_cache = json.load(f)
    else:
        _review_cache = {}
    
    # Load provider cache
    provider_cache_file = f"{cache_dir}/provider_cache.json"
    if os.path.exists(provider_cache_file):
        with open(provider_cache_file, 'r') as f:
            _provider_cache = json.load(f)
    else:
        _provider_cache = {}
    
    # Load release types cache
    release_cache_file = f"{cache_dir}/release_types.json"
    if os.path.exists(release_cache_file):
        with open(release_cache_file, 'r') as f:
            _release_cache = json.load(f)
    else:
        _release_cache = {}

def save_cache(cache_dir):
    """Save all caches"""
    global _review_cache, _provider_cache, _release_cache
    
    # Save review cache
    review_cache_file = f"{cache_dir}/review_cache.json"
    with open(review_cache_file, 'w') as f:
        json.dump(_review_cache, f)
    
    # Save provider cache
    provider_cache_file = f"{cache_dir}/provider_cache.json"
    with open(provider_cache_file, 'w') as f:
        json.dump(_provider_cache, f)
    
    # Save release types cache
    release_cache_file = f"{cache_dir}/release_types.json"
    with open(release_cache_file, 'w') as f:
        json.dump(_release_cache, f)

def is_cache_valid(cached_data, max_days=7):
    """Check if cached data is still valid"""
    if not cached_data or 'cached_at' not in cached_data:
        return False
    
    cache_time = datetime.fromisoformat(cached_data['cached_at'])
    return (datetime.now() - cache_time).days < max_days

def get_release_types(movie_id, api_key):
    """Get release types for a movie with caching"""
    global _release_cache
    
    # Create cache key
    cache_key = str(movie_id)
    
    # Check cache first
    if _release_cache and cache_key in _release_cache:
        cached_data = _release_cache[cache_key]
        if is_cache_valid(cached_data):
            return cached_data['data']
    
    # Fetch fresh data
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
    try:
        response = requests.get(url, params={'api_key': api_key})
        data = response.json()
        
        result = {'types': [], 'us_releases': [], 'digital_date': None}
        
        if 'results' in data:
            for country_data in data['results']:
                if country_data['iso_3166_1'] == 'US':
                    us_releases = country_data.get('release_dates', [])
                    result['us_releases'] = us_releases
                    
                    for release in us_releases:
                        release_type = release.get('type')
                        if release_type and release_type not in result['types']:
                            result['types'].append(release_type)
                        
                        # Capture digital release date (type 4)
                        if release_type == 4 and not result['digital_date']:
                            result['digital_date'] = release.get('release_date', '')
                    break
        
        # Cache the result
        if _release_cache is not None:
            _release_cache[cache_key] = {
                'data': result,
                'cached_at': datetime.now().isoformat()
            }
        
        return result
        
    except Exception:
        return {'types': [], 'us_releases': [], 'digital_date': None}

def tmdb_get(endpoint, params, api_key):
    """Generic TMDB API GET request"""
    url = f"https://api.themoviedb.org/3{endpoint}"
    params['api_key'] = api_key
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception:
        return {}

def get_movie_credits(tmdb_id, api_key):
    data = tmdb_get(f"/movie/{tmdb_id}/credits", {}, api_key)
    director = None
    cast = []
    
    for crew in data.get("crew", []):
        if crew.get("job") == "Director":
            director = crew.get("name")
            break
    
    for actor in data.get("cast", [])[:5]:  # Top 5 cast
        cast.append(actor.get("name"))
    
    return director, cast

def get_movie_details(tmdb_id, api_key):
    data = tmdb_get(f"/movie/{tmdb_id}", {}, api_key)
    return {
        "synopsis": data.get("overview"),
        "runtime": data.get("runtime"),
        "studio": (data.get("production_companies") or [{}])[0].get("name")
    }

def check_has_reviews(title, year, config):
    """Quick check if movie has any critical reviews via OMDb"""
    global _review_cache
    
    # Create cache key
    cache_key = f"{title}_{year}" if year else title
    
    # Check cache first
    if _review_cache and cache_key in _review_cache:
        cached_data = _review_cache[cache_key]
        if is_cache_valid(cached_data):
            return cached_data['has_reviews'], cached_data['review_info']
    
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
            
            # Check for any review data (more lenient than smart version)
            if data.get('Metascore', 'N/A') != 'N/A':
                review_info['metacritic'] = data['Metascore']
            
            for rating in data.get('Ratings', []):
                if rating['Source'] == 'Rotten Tomatoes':
                    review_info['rt_score'] = rating['Value'].rstrip('%')
            
            # More lenient IMDB threshold (10+ votes instead of 50+)
            votes_str = data.get('imdbVotes', '0').replace(',', '').replace('N/A', '0')
            if votes_str and votes_str != '0':
                votes = int(votes_str)
                if votes > 10:  # Lowered from 50 to 10
                    review_info['imdb_votes'] = votes
                    review_info['imdb_rating'] = data.get('imdbRating', 'N/A')
            
            result = bool(review_info), review_info
        else:
            result = False, None
        
        # Cache the result
        if _review_cache is not None:
            _review_cache[cache_key] = {
                'has_reviews': result[0],
                'review_info': result[1],
                'cached_at': datetime.now().isoformat()
            }
        
        return result
                
    except Exception:
        return False, None

def fetch_recent_movies(region="US", days_back=180, digital_window=45, max_pages=10):
    """
    Fetch movies that went DIGITAL in the last 'digital_window' days
    by looking back 'days_back' days for theatrical releases
    """
    config = load_config()
    api_key = config['tmdb_api_key']
    
    print(f"Looking for movies digital in last {digital_window} days...")
    print(f"Checking movies from last {days_back} days...")
    
    # Cast wider net - go back specified days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    print(f"Fetching releases from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
    
    all_movies = []
    
    for page in range(1, max_pages + 1):
        print(f"Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': region,
            'with_release_type': '2|3|4|6',  # All relevant types for US
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        movies = response.json().get('results', [])
        
        if not movies:
            break
            
        all_movies.extend(movies)
        time.sleep(0.3)
    
    print(f"\nFound {len(all_movies)} total movies. Applying balanced filtering...")
    
    curated = []
    included_count = 0
    
    for movie in all_movies:
        title = movie.get('title', '')
        year = movie.get('release_date', '')[:4] if movie.get('release_date') else None
        
        include = False
        reason = ""
        review_data = {}
        
        # Tier 1: Auto-include popular movies (lowered thresholds)
        if movie.get('vote_count', 0) >= 20:  # Lowered from 50 to 20
            include = True
            reason = f"TMDB popular ({movie['vote_count']} votes)"
        
        # Tier 2: Auto-include trending movies (lowered threshold)
        elif movie.get('popularity', 0) >= 10:  # Lowered from 20 to 10
            include = True
            reason = f"Trending (pop: {movie['popularity']:.1f})"
        
        # Tier 3: Include English films with minimal activity
        elif movie.get('original_language') in ['en'] and movie.get('vote_count', 0) >= 3:  # Lowered from 5 to 3
            include = True
            reason = f"English film ({movie['vote_count']} votes)"
        
        # Tier 4: Check for reviews (but don't require them)
        elif title:
            time.sleep(0.15)  # Faster rate limit
            has_review, review_info = check_has_reviews(title, year, config)
            
            if has_review:
                include = True
                review_data = review_info
                parts = []
                if 'rt_score' in review_info:
                    parts.append(f"RT: {review_info['rt_score']}%")
                if 'metacritic' in review_info:
                    parts.append(f"Meta: {review_info['metacritic']}")
                if 'imdb_votes' in review_info:
                    parts.append(f"IMDB: {review_info['imdb_votes']} votes")
                reason = " | ".join(parts)
            else:
                # Tier 5: Very lenient catch-all for any movie with basic data
                if movie.get('title') and movie.get('release_date'):  # Has title and release date
                    include = True
                    reason = "Recent release"
        
        if include:
            included_count += 1
            movie['inclusion_reason'] = reason
            movie['review_data'] = review_data
            curated.append(movie)
            print(f"  ✓ {title[:40]:40} | {reason}")
        else:
            print(f"  ✗ {title[:40]:40} | No qualifying criteria")
    
    print(f"\n{'='*60}")
    print(f"BALANCED RESULTS: {included_count} movies included")
    print(f"Inclusion rate: {included_count/len(all_movies)*100:.1f}%")
    
    # Check digital availability using enhanced classification
    print(f"\nChecking digital availability for {len(curated)} movies...")
    digitally_available = []
    uncertain_movies = []
    
    for i, movie in enumerate(curated):
        if i % 10 == 0 and i > 0:
            print(f"  Checked {i}/{len(curated)} movies...")
        
        # Get release type info first
        release_info = get_release_types(movie['id'], api_key)
        movie['us_release_types'] = release_info['types']
        if release_info['digital_date']:
            movie['digital_date'] = release_info['digital_date'][:10]
        
        # Check actual availability via providers
        availability = check_digital_availability(movie['id'], api_key)
        
        # Classify the movie (handles edge cases)
        movie = classify_digital_movie(movie, availability)
        movie['providers'] = availability['providers']
        movie['justwatch_url'] = availability['justwatch_url']
        
        # More inclusive decision logic
        confirmed_statuses = ['confirmed_available', 'early_pvod', 'standard_pvod', 
                            'standard_digital', 'streaming_exclusive']
        
        # Include high confidence movies
        if movie['digital_status'] in confirmed_statuses:
            days_since = movie.get('days_since_digital')
            if digital_window == 0 or (days_since is not None and days_since <= digital_window):
                digitally_available.append(movie)
                
                providers_str = ', '.join(availability['providers']['rent'][:2]) or \
                               ', '.join(availability['providers']['buy'][:2]) or \
                               ', '.join(availability['providers']['stream'][:2]) or 'Available'
                
                status = movie['digital_status'].replace('_', ' ').title()
                days_text = f" | {days_since}d ago" if days_since is not None else ""
                confidence_marker = "✓" if movie['digital_confidence'] == 'high' else "○"
                
                print(f"  {confidence_marker} {movie['title'][:30]:30} | {status} | {providers_str}{days_text}")
        
        # ALSO include medium confidence movies with reasonable criteria
        elif movie['digital_confidence'] == 'medium' and movie['digital_status'] == 'marked_digital_no_providers':
            # Include if it's a popular/major release that likely has digital availability
            is_major_release = (
                movie.get('vote_count', 0) >= 100 or  # Popular on TMDB
                movie.get('popularity', 0) >= 50 or   # Trending
                4 in movie.get('us_release_types', [])  # Has digital release type
            )
            
            if is_major_release:
                # Estimate digital availability based on release date
                days_since = None
                if movie.get('release_date'):
                    try:
                        release_dt = datetime.strptime(movie['release_date'][:10], '%Y-%m-%d')
                        days_since_release = (datetime.now() - release_dt).days
                        # Assume 35-day window for digital availability
                        days_since = max(0, days_since_release - 35)
                        movie['days_since_digital'] = days_since
                        movie['digital_date'] = (release_dt + timedelta(days=35)).strftime('%Y-%m-%d')
                        movie['digital_status'] = 'likely_available'
                        movie['digital_confidence'] = 'medium'
                    except ValueError:
                        pass
                
                # Include if within digital window or no window specified
                if digital_window == 0 or (days_since is not None and days_since <= digital_window):
                    digitally_available.append(movie)
                    
                    status = 'Likely Available'
                    days_text = f" | {days_since}d ago" if days_since is not None else ""
                    print(f"  ○ {movie['title'][:30]:30} | {status} | Estimated{days_text}")
            else:
                uncertain_movies.append(movie)
                print(f"  ? {movie['title'][:30]:30} | Uncertain: {movie['digital_status']}")
        
        # All other cases go to uncertain
        else:
            uncertain_movies.append(movie)
            print(f"  ? {movie['title'][:30]:30} | Uncertain: {movie['digital_status']}")
        
        time.sleep(0.1)  # Rate limiting
    
    print(f"\nFound {len(digitally_available)} digitally available movies")
    
    # Show breakdown by confidence
    high_conf = [m for m in digitally_available if m.get('digital_confidence') == 'high']
    medium_conf = [m for m in digitally_available if m.get('digital_confidence') == 'medium']
    
    print(f"  {len(high_conf)} confirmed with providers, {len(medium_conf)} estimated based on release data")
    
    if uncertain_movies:
        print(f"Found {len(uncertain_movies)} uncertain movies (excluded)")
    
    # Sort by confidence and recency
    digitally_available.sort(
        key=lambda x: (
            x['digital_confidence'] == 'high',      # High confidence first
            -x.get('days_since_digital', 999),      # Most recent first (negative for reverse)
            x.get('popularity', 0)                  # Then by popularity
        ),
        reverse=True
    )
    
    return digitally_available

def check_digital_availability(movie_id, api_key):
    """Check if movie is actually available digitally via providers"""
    global _provider_cache
    
    # Initialize default result
    result = {
        'is_digital': False,
        'digital_confirmed_date': None,
        'providers': {'rent': [], 'buy': [], 'stream': []},
        'justwatch_url': None
    }
    
    # Create cache key
    cache_key = f"{movie_id}_US"
    
    # Check cache first
    if _provider_cache and cache_key in _provider_cache:
        cached_data = _provider_cache[cache_key]
        if is_cache_valid(cached_data):
            return cached_data.get('availability', cached_data.get('data', result))
    
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    params = {'api_key': api_key}
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            us_providers = response.json().get('results', {}).get('US', {})
            
            # Get providers
            result['providers']['rent'] = [p['provider_name'] for p in us_providers.get('rent', [])]
            result['providers']['buy'] = [p['provider_name'] for p in us_providers.get('buy', [])]
            result['providers']['stream'] = [p['provider_name'] for p in us_providers.get('flatrate', [])]
            
            # If rentable/buyable, it's digital
            result['is_digital'] = bool(result['providers']['rent'] or result['providers']['buy'])
            result['justwatch_url'] = us_providers.get('link', '')
            
        # Cache the result
        if _provider_cache is not None:
            _provider_cache[cache_key] = {
                'availability': result,
                'cached_at': datetime.now().isoformat()
            }
            
    except Exception as e:
        print(f"Error checking providers for {movie_id}: {e}")
    
    return result

def get_watch_providers(movie_id, region, api_key):
    """Get streaming providers for a movie - wrapper for backwards compatibility"""
    availability = check_digital_availability(movie_id, api_key)
    
    # Convert to old format for backwards compatibility
    providers = {
        'flatrate': availability['providers']['stream'],
        'rent': availability['providers']['rent'],
        'buy': availability['providers']['buy'],
        'all': availability['providers']['rent'] + availability['providers']['buy'] + availability['providers']['stream']
    }
    
    return providers

def classify_digital_movie(movie, availability):
    """Classify how/when movie became digital - handles edge cases"""
    
    movie['digital_status'] = 'unknown'
    movie['digital_confidence'] = 'low'
    
    # Case 1: Has rental providers - definitely digital
    if availability['providers']['rent'] or availability['providers']['buy']:
        movie['digital_status'] = 'confirmed_available'
        movie['digital_confidence'] = 'high'
        
        # Try to determine when it went digital
        if movie.get('digital_date'):
            # Best case: we have the actual date
            try:
                digital_dt = datetime.strptime(movie['digital_date'][:10], '%Y-%m-%d')
                movie['days_since_digital'] = (datetime.now() - digital_dt).days
            except ValueError:
                pass
        elif movie.get('release_date'):
            # Estimate based on theatrical release (use release_date as theatrical_date)
            try:
                theatrical_dt = datetime.strptime(movie['release_date'][:10], '%Y-%m-%d')
                days_since_theatrical = (datetime.now() - theatrical_dt).days
                
                if days_since_theatrical < 21:
                    movie['digital_status'] = 'early_pvod'  # Premium VOD (early digital)
                    movie['estimated_digital_days'] = 0  # Probably day-and-date or very recent
                elif days_since_theatrical < 45:
                    movie['digital_status'] = 'standard_pvod'
                    movie['estimated_digital_days'] = max(0, days_since_theatrical - 30)
                else:
                    movie['digital_status'] = 'standard_digital'
                    movie['estimated_digital_days'] = days_since_theatrical - 45
                    
                movie['days_since_digital'] = movie.get('estimated_digital_days', days_since_theatrical - 35)
            except ValueError:
                pass
        else:
            # No date info but has providers - include it but flag as uncertain
            movie['digital_status'] = 'available_no_date'
            movie['digital_confidence'] = 'medium'
    
    # Case 2: Streaming only (Netflix, etc) - different rules
    elif availability['providers']['stream'] and not movie.get('release_date'):
        movie['digital_status'] = 'streaming_exclusive'
        movie['digital_confidence'] = 'high'
        # Use release_date as digital date for streaming exclusives
        if movie.get('release_date'):
            try:
                release_dt = datetime.strptime(movie['release_date'][:10], '%Y-%m-%d')
                movie['days_since_digital'] = (datetime.now() - release_dt).days
            except ValueError:
                pass
    
    # Case 3: Has type 4 but no providers - data lag
    elif 4 in movie.get('us_release_types', []):
        movie['digital_status'] = 'marked_digital_no_providers'
        movie['digital_confidence'] = 'medium'
    
    return movie

def analyze_date_spread(movies):
    """Show the spread between premiere and digital dates"""
    print("\n=== DATE SPREAD ANALYSIS ===")
    
    large_gaps = []
    for movie in movies[:20]:  # Check first 20
        if movie.get('digital_date') and movie.get('release_date'):
            premiere = datetime.strptime(movie['release_date'][:10], '%Y-%m-%d')
            digital = datetime.strptime(movie['digital_date'][:10], '%Y-%m-%d')
            gap_days = (digital - premiere).days
            
            if gap_days > 60:  # More than 2 months
                large_gaps.append({
                    'title': movie['title'],
                    'gap': gap_days,
                    'premiere': movie['release_date'][:10],
                    'digital': movie['digital_date'][:10]
                })
    
    if large_gaps:
        print("\nMovies with large premiere->digital gaps:")
        for m in sorted(large_gaps, key=lambda x: x['gap'], reverse=True)[:5]:
            print(f"  {m['title']}: {m['gap']} days ({m['premiere']} → {m['digital']})")
    else:
        print("\nNo movies found with large premiere->digital gaps (>60 days)")
    
    # Also show general stats
    if movies:
        gaps = []
        for movie in movies:
            if movie.get('digital_date') and movie.get('release_date'):
                premiere = datetime.strptime(movie['release_date'][:10], '%Y-%m-%d')
                digital = datetime.strptime(movie['digital_date'][:10], '%Y-%m-%d')
                gaps.append((digital - premiere).days)
        
        if gaps:
            avg_gap = sum(gaps) / len(gaps)
            print(f"\nGeneral stats for {len(gaps)} movies:")
            print(f"  Average premiere->digital gap: {avg_gap:.1f} days")
            print(f"  Range: {min(gaps)}-{max(gaps)} days")
    
    return large_gaps

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
        
        # Add premiere date for display
        if movie.get('release_date'):
            movie['premiere_date'] = movie['release_date'][:10]
        
        # Calculate gap between premiere and digital if both exist
        if movie.get('digital_date') and movie.get('release_date'):
            try:
                premiere = datetime.strptime(movie['release_date'][:10], '%Y-%m-%d')
                digital = datetime.strptime(movie['digital_date'][:10], '%Y-%m-%d')
                movie['premiere_to_digital_days'] = (digital - premiere).days
            except ValueError:
                pass
        
        # TMDB vote
        movie['tmdb_vote'] = movie.get('vote_average')
        
        # Add URL fields for template
        movie['tmdb_url'] = f"https://www.themoviedb.org/movie/{movie['id']}"
        movie['tmdb_watch_link'] = f"https://www.themoviedb.org/movie/{movie['id']}/watch"
        movie['justwatch_search_link'] = f"https://www.justwatch.com/us/search?q={movie['title'].replace(' ', '%20')}"
    
    html = template.render(
        items=movies,
        site_title="Digitally Available Movies",
        window_label=f"Available for rent/purchase",
        region=args.region,
        store_names=[],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    with open('output/site/index.html', 'w') as f:
        f.write(html)
    
    print(f"Generated HTML with {len(movies)} movies")

def main():
    global args
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', default='US')
    parser.add_argument('--days-back', type=int, default=180, help='Days to look back for movies')
    parser.add_argument('--digital-window', type=int, default=45, help='Digital release window in days')
    parser.add_argument('--max-pages', type=int, default=10)
    args = parser.parse_args()
    
    # Load config and initialize cache
    config = load_config()
    load_cache(config['cache_dir'])
    
    # Get movies that went digital recently
    movies = fetch_recent_movies(
        region=args.region,
        days_back=args.days_back,
        digital_window=args.digital_window,
        max_pages=args.max_pages
    )
    
    # Analyze date spread between premiere and digital releases
    if movies:
        analyze_date_spread(movies)
    
    # Provider information already gathered during digital checking
    print(f"\nSummarizing provider information for {len(movies)} movies...")
    for movie in movies:
        providers = movie.get('providers', {})
        
        if providers:
            rent_buy = providers.get('rent', []) + providers.get('buy', [])
            stream = providers.get('stream', [])
            
            if rent_buy:
                print(f"  {movie['title'][:30]:30} | Rent/Buy: {', '.join(rent_buy[:2])}")
            elif stream:
                print(f"  {movie['title'][:30]:30} | Stream: {', '.join(stream[:2])}")
            else:
                print(f"  {movie['title'][:30]:30} | Available but no details")
        else:
            print(f"  {movie['title'][:30]:30} | No providers")
    
    # Save cache before generating output
    save_cache(config['cache_dir'])
    
    # Generate output
    generate_html(movies)
    
    # Save JSON data for analysis
    os.makedirs('output', exist_ok=True)
    with open('output/data.json', 'w') as f:
        json.dump(movies, f, indent=2, default=str)
    
    print(f"\n✓ Complete! View at http://localhost:8080")
    print(f"  Found {len(movies)} digitally available movies")
    
    # Show breakdown by provider type
    rent_count = sum(1 for m in movies if m.get('providers', {}).get('rent'))
    buy_count = sum(1 for m in movies if m.get('providers', {}).get('buy'))
    stream_count = sum(1 for m in movies if m.get('providers', {}).get('stream'))
    
    print(f"  {rent_count} available for rent, {buy_count} for purchase, {stream_count} streaming")

if __name__ == "__main__":
    main()