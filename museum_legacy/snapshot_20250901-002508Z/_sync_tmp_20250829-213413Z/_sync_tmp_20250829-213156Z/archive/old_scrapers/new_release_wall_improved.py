"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
import argparse, os, sys, json, datetime, time
from typing import Optional
import requests, yaml
from datetime import datetime as dt, timedelta
from jinja2 import Template

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_digital_releases_improved(region="US", days=7, max_pages=5):
    """Improved version using TMDB Discover API"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Calculate date range
    today = dt.now()
    start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    
    print(f"Fetching movies from {start_date} to {end_date}")
    
    all_results = []
    
    for page in range(1, max_pages + 1):
        print(f"Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': region,
            'with_release_type': '4|6',  # Digital and TV
            'primary_release_date.gte': start_date,
            'primary_release_date.lte': end_date,
            'sort_by': 'release_date.desc',
            'page': page
        }
        
        response = requests.get(
            'https://api.themoviedb.org/3/discover/movie',
            params=params
        )
        
        data = response.json()
        results = data.get('results', [])
        
        if not results:
            break
            
        all_results.extend(results)
        time.sleep(0.5)  # Be nice to the API
    
    print(f"Found {len(all_results)} total movies")
    return all_results

# Copy the rest of your existing functions here
# We'll add them in the next step

def fetch_poster(title: str, year: Optional[int], api_key: str):
    """Fetch poster from TMDB"""
    params = {"query": title, "api_key": api_key}
    if year:
        params["year"] = year
    try:
        response = requests.get("https://api.themoviedb.org/3/search/movie", params=params)
        data = response.json()
        results = data.get("results", [])
        if results:
            poster_path = results[0].get("poster_path")
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"
    except Exception:
        pass
    return None

def process_movies(movies, config):
    """Process raw movie data into final format"""
    processed = []
    
    for movie in movies:
        title = movie.get('title', '')
        release_date = movie.get('release_date', '')
        year = release_date[:4] if release_date else None
        
        # Get poster
        poster_url = None
        poster_path = movie.get('poster_path')
        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        else:
            poster_url = fetch_poster(title, int(year) if year and year.isdigit() else None, config['tmdb_api_key'])
        
        item = {
            "title": title,
            "year": year,
            "poster": poster_url,
            "tmdb_vote": movie.get("vote_average"),
            "rt_score": None,  # Could add OMDb integration here
            "providers": [],   # Could add streaming provider data
            "tmdb_url": f"https://www.themoviedb.org/movie/{movie['id']}",
            "tmdb_watch_link": f"https://www.themoviedb.org/movie/{movie['id']}/watch",
            "justwatch_search_link": f"https://www.justwatch.com/us/search?q={title.replace(' ', '%20')}"
        }
        
        processed.append(item)
    
    return processed

def generate_html(items, config):
    """Generate HTML from template"""
    template_path = "templates/site.html"
    
    with open(template_path, "r", encoding="utf-8") as f:
        template = Template(f.read())
    
    html = template.render(
        site_title=config.get('site_title', 'New Release Wall'),
        window_label="Last 7 days",
        region="US", 
        store_names=[],
        items=items,
        generated_at=dt.now().strftime("%Y-%m-%d %H:%M")
    )
    
    # Ensure output directory exists
    os.makedirs("output/site", exist_ok=True)
    
    with open("output/site/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"Generated HTML with {len(items)} movies")

def main():
    """Main function"""
    # Get movies using improved API
    movies = get_digital_releases_improved(days=7, max_pages=5)
    
    # Load config
    config = load_config()
    
    # Process movies
    processed_movies = process_movies(movies, config)
    
    # Generate HTML
    generate_html(processed_movies, config)
    
    print("Done!")

if __name__ == "__main__":
    main()

def omdb_rt_score(title, year, omdb_api_key, imdb_id=None):
    """Get Rotten Tomatoes score from OMDb API"""
    try:
        params = {'apikey': omdb_api_key, 't': title}
        if year:
            params['y'] = str(year)
        if imdb_id:
            params['i'] = imdb_id
            
        response = requests.get('http://www.omdbapi.com/', params=params)
        data = response.json()
        
        if data.get('Response') == 'True':
            for rating in data.get('Ratings', []):
                if rating['Source'] == 'Rotten Tomatoes':
                    return int(rating['Value'].rstrip('%'))
    except:
        pass
    return None

def movie_watch_providers(tmdb_id, region, api_key):
    """Get streaming providers for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers"
    params = {'api_key': api_key}
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'results' in data and region in data['results']:
            providers = []
            region_data = data['results'][region]
            
            # Check different provider types
            for provider_type in ['flatrate', 'rent', 'buy']:
                if provider_type in region_data:
                    for provider in region_data[provider_type]:
                        if provider['provider_name'] not in providers:
                            providers.append(provider['provider_name'])
            
            return providers
    except:
        pass
    return []

def process_movies(movies, region="US", stores=None):
    """Process movies with providers and ratings"""
    config = load_config()
    processed = []
    
    for movie in movies:
        # Get streaming providers
        providers = movie_watch_providers(
            movie['id'], 
            region, 
            config['tmdb_api_key']
        )
        
        # Filter by requested stores if specified
        if stores:
            if not any(store in providers for store in stores):
                continue  # Skip movies not on requested platforms
        
        # Get RT score
        rt_score = omdb_rt_score(
            movie['title'],
            movie.get('release_date', '')[:4] if movie.get('release_date') else None,
            config['omdb_api_key']
        )
        
        # Build movie data
        movie_data = {
            'title': movie['title'],
            'year': movie.get('release_date', '')[:4] if movie.get('release_date') else '',
            'release_date': movie.get('release_date', ''),
            'poster': f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get('poster_path') else None,
            'tmdb_id': movie['id'],
            'tmdb_vote': movie.get('vote_average'),
            'rt_score': rt_score,
            'providers': providers,
            'overview': movie.get('overview', '')
        }
        
        processed.append(movie_data)
    
    return processed

def generate_output(movies):
    """Generate HTML and markdown output"""
    # Create output directory
    os.makedirs('output/site', exist_ok=True)
    
    # Generate HTML
    with open('templates/site.html', 'r') as f:
        template = Template(f.read())
    
    html = template.render(items=movies)
    
    with open('output/site/index.html', 'w') as f:
        f.write(html)
    
    # Generate markdown
    with open('output/list.md', 'w') as f:
        f.write("# New Release Wall\n\n")
        for movie in movies:
            f.write(f"- **{movie['title']}** ({movie['year']})\n")
            if movie['rt_score']:
                f.write(f"  RT: {movie['rt_score']}%\n")
            if movie['providers']:
                f.write(f"  Available on: {', '.join(movie['providers'])}\n")
            f.write("\n")

def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', default='US')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--max-pages', type=int, default=5)
    parser.add_argument('--stores', help='Comma-separated list of stores')
    args = parser.parse_args()
    
    # Parse stores
    stores = args.stores.split(',') if args.stores else None
    
    # Get movies using improved API
    movies = get_digital_releases_improved(
        region=args.region,
        days=args.days,
        max_pages=args.max_pages
    )
    
    # Process with providers and ratings
    processed = process_movies(movies, args.region, stores)
    
    # Generate output files
    generate_output(processed)
    
    print(f"\nGenerated output for {len(processed)} movies")
    print("View at: http://localhost:8080")

if __name__ == "__main__":
    main()
