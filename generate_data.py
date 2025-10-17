#!/usr/bin/env python3
"""
Generate display data from tracking database with enriched links
"""

import json
import requests
import yaml
from datetime import datetime, timedelta
import time
import os
import re
from urllib.parse import quote
import argparse

class DataGenerator:
    def __init__(self):
        self.config = self.load_config()
        self.tmdb_key = self.config['tmdb_api_key']
        self.watchmode_key = "bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp"  # Watchmode API
        self.wikipedia_cache = self.load_cache('wikipedia_cache.json')
        self.rt_cache = self.load_cache('rt_cache.json')
        self.wikipedia_overrides = self.load_cache('overrides/wikipedia_overrides.json')
        self.rt_overrides = self.load_cache('overrides/rt_overrides.json')
        self.watch_links_cache = self.load_cache('cache/watch_links_cache.json')

        # Watchmode usage statistics
        self.watchmode_stats = {
            'search_calls': 0,
            'source_calls': 0,
            'cache_hits': 0,
            'watchmode_successes': 0
        }
    
    def load_config(self):
        """Load configuration from config.yaml and environment variables"""
        config = {}

        # Load from config.yaml if it exists
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config and 'api' in yaml_config:
                    config.update(yaml_config['api'])

        # Environment variable takes precedence
        tmdb_key = os.environ.get('TMDB_API_KEY')
        if tmdb_key:
            config['tmdb_api_key'] = tmdb_key

        # Validate that we have a key
        if not config.get('tmdb_api_key'):
            raise ValueError(
                "TMDB API key not found. Please set the TMDB_API_KEY environment variable "
                "or add 'tmdb_api_key' to the 'api' section in config.yaml"
            )

        return config
    
    def load_cache(self, filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return {}
    
    def save_cache(self, data, filename):
        os.makedirs(os.path.dirname(filename) if '/' in filename else '.', exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_movie_details(self, movie_id):
        """Get full movie details from TMDB"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {
            'api_key': self.tmdb_key,
            'append_to_response': 'credits,videos,external_ids'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching details for {movie_id}: {e}")
        return None
    
    def find_wikipedia_url(self, title, year, imdb_id, movie_id=None):
        """Find Wikipedia URL using waterfall approach"""
        # 1. Check overrides first
        if imdb_id and imdb_id in self.wikipedia_overrides:
            return f"https://en.wikipedia.org/wiki/{self.wikipedia_overrides[imdb_id]}"

        # 2. Check cache
        cache_key = f"{title}_{year}"
        if cache_key in self.wikipedia_cache:
            cached_data = self.wikipedia_cache[cache_key]
            if isinstance(cached_data, dict):
                return cached_data.get('url')
            return cached_data

        # 3. Try Wikipedia API search
        try:
            # Try exact match with (year film) suffix
            search_title = f"{title} ({year} film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    self.wikipedia_cache[cache_key] = {'url': wiki_url, 'title': title, 'cached_at': datetime.now().isoformat()}
                    return wiki_url

            # Try without year
            search_title = f"{title} (film)"
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(search_title)}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page')
                if wiki_url:
                    self.wikipedia_cache[cache_key] = {'url': wiki_url, 'title': title, 'cached_at': datetime.now().isoformat()}
                    return wiki_url

        except Exception as e:
            print(f"Wikipedia search error for {title}: {e}")

        # 4. Log as missing and return null (only if movie_id is provided)
        if movie_id:
            self.log_missing_wikipedia(movie_id, title, year, imdb_id)
        return None
    
    def log_missing_wikipedia(self, movie_id, title, year, imdb_id):
        """Log missing Wikipedia links for manual review"""
        try:
            missing_file = 'missing_wikipedia.json'
            if os.path.exists(missing_file):
                with open(missing_file, 'r') as f:
                    missing = json.load(f)
            else:
                missing = {"missing": []}
            
            entry = {
                "tmdb_id": movie_id,
                "title": title,
                "year": year,
                "imdb_id": imdb_id,
                "timestamp": datetime.now().isoformat()
            }
            
            # Avoid duplicates
            if not any(m['tmdb_id'] == movie_id for m in missing['missing']):
                missing['missing'].append(entry)
                with open(missing_file, 'w') as f:
                    json.dump(missing, f, indent=2)
        except Exception as e:
            print(f"Failed to log missing Wikipedia: {e}")
    
    def find_trailer_url(self, movie_details):
        """Extract trailer URL from TMDB movie details"""
        videos = movie_details.get('videos', {}).get('results', [])
        
        # Prioritize official trailers
        for video in videos:
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"
        
        # Fall back to any YouTube video
        for video in videos:
            if video['site'] == 'YouTube':
                return f"https://www.youtube.com/watch?v={video['key']}"
        
        # Generate YouTube search as fallback
        title = movie_details.get('title', '')
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''
        search_query = quote(f"{title} {year} trailer")
        return f"https://www.youtube.com/results?search_query={search_query}"
    
    def find_rt_url(self, title, year, imdb_id):
        """Find Rotten Tomatoes URL"""
        # 1. Check overrides first
        if imdb_id and imdb_id in self.rt_overrides:
            return self.rt_overrides[imdb_id]
        
        # 2. Check cache
        cache_key = f"{title}_{year}"
        if cache_key in self.rt_cache:
            cached_data = self.rt_cache[cache_key]
            if isinstance(cached_data, dict):
                return cached_data.get('url')
            return cached_data
        
        # 3. Fall back to search
        search_query = quote(f"{title} {year}")
        return f"https://www.rottentomatoes.com/search?search={search_query}"

    def get_watch_links(self, movie_id, title, year, providers, force_refresh=False):
        """Get deep links with canonical streaming/rent/buy structure

        Returns: {
            'streaming': {'service': 'Netflix', 'link': 'https://...'},  # subscription streaming
            'rent': {'service': 'Amazon', 'link': 'https://...'},        # rental
            'buy': {'service': 'Apple TV', 'link': 'https://...'}        # purchase
        }
        """
        # Check cache first (unless force refresh)
        cache_key = str(movie_id)
        if not force_refresh and cache_key in self.watch_links_cache:
            cached = self.watch_links_cache[cache_key]
            if cached.get('links'):
                self.watchmode_stats['cache_hits'] += 1
                # Migrate legacy cache format if needed
                migrated_links = self._migrate_legacy_cache_format(cached['links'])
                if migrated_links != cached['links']:
                    # Update cache with migrated format
                    self.watch_links_cache[cache_key]['links'] = migrated_links
                    self.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                return migrated_links

        # Service priority hierarchies
        STREAMING_PRIORITY = ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max',
                              'Hulu', 'Amazon Prime Video', 'Prime Video', 'Apple TV+',
                              'Paramount+', 'Paramount Plus', 'Peacock', 'MUBI', 'Shudder', 'Criterion Channel']

        PAID_PRIORITY = ['Amazon Video', 'Amazon', 'Prime Video', 'Apple TV', 'Vudu',
                         'Google Play Movies', 'Google Play', 'Microsoft Store']

        def build_platform_link(service_name):
            """Build best possible direct link for each platform"""
            search_term = quote(f'{title} {year}')

            if 'Amazon' in service_name or service_name == 'Prime Video':
                return f"https://www.amazon.com/s?k={search_term}&i=instant-video"
            elif 'Apple' in service_name:
                return f"https://tv.apple.com/search?term={quote(title)}"
            elif 'Vudu' in service_name:
                return f"https://www.vudu.com/content/movies/search/{quote(title)}"
            elif 'Google Play' in service_name:
                return f"https://play.google.com/store/search?q={search_term}&c=movies"
            elif 'Microsoft' in service_name:
                return f"https://www.microsoft.com/en-us/search?q={search_term}"
            else:
                # For Netflix, Disney+, etc - can't build direct links, return null
                return None

        def select_best_service(service_list, priority_list):
            """Select best service from list based on priority"""
            for priority_service in priority_list:
                for available_service in service_list:
                    if priority_service.lower() in available_service.lower():
                        return available_service
            # If no priority match, return first available
            return service_list[0] if service_list else None

        # Collect sources from Watchmode API
        watchmode_streaming = []
        watchmode_rent = []
        watchmode_buy = []

        try:
            # Step 1: Search by TMDB ID
            search_url = "https://api.watchmode.com/v1/search/"
            search_params = {
                "apiKey": self.watchmode_key,
                "search_field": "tmdb_movie_id",
                "search_value": movie_id
            }

            self.watchmode_stats['search_calls'] += 1
            search_response = requests.get(search_url, params=search_params, timeout=10)

            if search_response.status_code == 200:
                search_data = search_response.json()

                if search_data.get('title_results'):
                    watchmode_id = search_data['title_results'][0]['id']

                    # Step 2: Get sources
                    sources_url = f"https://api.watchmode.com/v1/title/{watchmode_id}/details/"
                    sources_params = {
                        "apiKey": self.watchmode_key,
                        "append_to_response": "sources"
                    }

                    self.watchmode_stats['source_calls'] += 1
                    sources_response = requests.get(sources_url, params=sources_params, timeout=10)

                    if sources_response.status_code == 200:
                        sources_data = sources_response.json()
                        sources = sources_data.get('sources', [])

                        if sources:
                            self.watchmode_stats['watchmode_successes'] += 1

                        # Collect US sources by type
                        for source in sources:
                            if source.get('region') != 'US':
                                continue

                            service_name = source.get('name', '')
                            web_url = source.get('web_url', '')
                            source_type = source.get('type', '')

                            if not service_name or not web_url:
                                continue

                            if source_type == 'sub':
                                watchmode_streaming.append({'service': service_name, 'link': web_url})
                            elif source_type == 'rent':
                                watchmode_rent.append({'service': service_name, 'link': web_url})
                            elif source_type == 'buy':
                                watchmode_buy.append({'service': service_name, 'link': web_url})

        except Exception as e:
            print(f"  Warning: Watchmode API failed for {title}: {e}")

        # Build final watch_links with canonical streaming/rent/buy structure
        watch_links = {}

        # STREAMING: Prefer Watchmode, fallback to TMDB providers with smart Amazon handling
        if watchmode_streaming:
            # Use Watchmode streaming data
            best_service = select_best_service([s['service'] for s in watchmode_streaming], STREAMING_PRIORITY)
            for source in watchmode_streaming:
                if source['service'] == best_service:
                    watch_links['streaming'] = source
                    break
        elif providers.get('streaming'):
            # Fallback to TMDB provider data
            service = select_best_service(providers['streaming'], STREAMING_PRIORITY)

            # SMART FALLBACK: If TMDB says "Amazon Prime Video" but Watchmode didn't find subscription,
            # reuse any Amazon rent/buy link we have (it's the same detail page on Amazon)
            if 'Amazon Prime Video' in service and (watchmode_rent or watchmode_buy):
                # Find any Amazon link in rent or buy sources
                amazon_link = None
                for source in watchmode_rent + watchmode_buy:
                    if 'Amazon' in source['service'] and source.get('link'):
                        amazon_link = source['link']
                        break

                if amazon_link:
                    watch_links['streaming'] = {
                        'service': service,
                        'link': amazon_link  # Same page shows both Prime (free) and rent/buy options
                    }
                else:
                    # No Amazon link available, use search fallback
                    search_link = self._build_streaming_search_link(service, title, year)
                    watch_links['streaming'] = {
                        'service': service,
                        'link': search_link
                    }
            else:
                # For other services (Netflix, Disney+, etc), use search fallback
                search_link = self._build_streaming_search_link(service, title, year)
                watch_links['streaming'] = {
                    'service': service,
                    'link': search_link
                }

        # RENT: Use Watchmode or fallback to platform links
        if watchmode_rent:
            best_service = select_best_service([s['service'] for s in watchmode_rent], PAID_PRIORITY)
            for source in watchmode_rent:
                if source['service'] == best_service:
                    watch_links['rent'] = source
                    break
        elif providers.get('rent'):
            # Fallback to TMDB providers with platform-specific links
            rent_service = select_best_service(providers.get('rent', []), PAID_PRIORITY)
            if rent_service:
                platform_link = build_platform_link(rent_service)
                if platform_link:
                    watch_links['rent'] = {
                        'service': rent_service,
                        'link': platform_link
                    }

        # BUY: Use Watchmode or fallback to platform links
        if watchmode_buy:
            best_service = select_best_service([s['service'] for s in watchmode_buy], PAID_PRIORITY)
            for source in watchmode_buy:
                if source['service'] == best_service:
                    watch_links['buy'] = source
                    break
        elif providers.get('buy'):
            # Fallback to TMDB providers with platform-specific links
            buy_service = select_best_service(providers.get('buy', []), PAID_PRIORITY)
            if buy_service:
                platform_link = build_platform_link(buy_service)
                if platform_link:
                    watch_links['buy'] = {
                        'service': buy_service,
                        'link': platform_link
                    }

        # DEFAULT: If no streaming or paid options available, provide Amazon search
        if not watch_links.get('streaming') and not watch_links.get('rent') and not watch_links.get('buy'):
            search_term = quote(f'{title} {year}')
            watch_links['default'] = {
                'service': 'Amazon',
                'link': f"https://www.amazon.com/s?k={search_term}&i=instant-video"
            }

        # Cache result with canonical schema
        if watch_links:
            source_type = 'watchmode_api'
            if watchmode_streaming or watchmode_rent or watchmode_buy:
                source_type = 'watchmode_api'
            elif any(link.get('link') and 'google.com/search' in link['link'] for link in watch_links.values()):
                source_type = 'google_fallback'
            elif watch_links.get('default'):
                source_type = 'amazon_fallback'
            else:
                source_type = 'tmdb_fallback'

            self.watch_links_cache[cache_key] = {
                'links': watch_links,
                'cached_at': datetime.now().isoformat(),
                'source': source_type
            }
            self.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

        return watch_links

    def _build_streaming_search_link(self, service, title, year):
        """Build search links for streaming services that don't have deep links"""
        search_term = quote(f'{title} {year} watch {service}')
        return f"https://www.google.com/search?q={search_term}"

    def _migrate_legacy_cache_format(self, links):
        """Migrate legacy free/paid cache format to streaming/rent/buy"""
        if not isinstance(links, dict):
            return links

        # Already in new format
        if any(key in links for key in ['streaming', 'rent', 'buy', 'default']):
            return links

        # Migrate from old free/paid format
        migrated = {}
        if 'free' in links:
            migrated['streaming'] = links['free']
        if 'paid' in links:
            # Default paid to rent category
            migrated['rent'] = links['paid']

        return migrated if migrated else links

    def process_movie(self, movie_id, movie_data, movie_details, force_refresh=False):
        """Process a single movie into display format"""
        if not movie_details:
            return None
        
        title = movie_details['title']
        year = movie_details.get('release_date', '')[:4] if movie_details.get('release_date') else ''
        imdb_id = movie_details.get('external_ids', {}).get('imdb_id')
        
        # Extract key people
        credits = movie_details.get('credits', {})
        director = "Unknown"
        cast = []
        
        for crew in credits.get('crew', []):
            if crew['job'] == 'Director':
                director = crew['name']
                break
        
        for actor in credits.get('cast', [])[:2]:  # Top 2 actors
            cast.append(actor['name'])
        
        # Extract additional metadata
        genres = [g['name'] for g in movie_details.get('genres', [])]
        studio = None
        production_companies = movie_details.get('production_companies', [])
        if production_companies:
            studio = production_companies[0]['name']
        
        runtime = movie_details.get('runtime')
        
        # Country from production countries
        country = None
        production_countries = movie_details.get('production_countries', [])
        if production_countries:
            country = production_countries[0]['name']
        
        # Build links object with waterfall approach
        links = {}

        # Wikipedia link
        wiki_url = self.find_wikipedia_url(title, year, imdb_id, movie_id)
        if wiki_url:
            links['wikipedia'] = wiki_url
        
        # Trailer link
        trailer_url = self.find_trailer_url(movie_details)
        if trailer_url:
            links['trailer'] = trailer_url
        
        # RT link
        rt_url = self.find_rt_url(title, year, imdb_id)
        if rt_url:
            links['rt'] = rt_url

        # Watch links (deep links to streaming platforms)
        watch_links_raw = self.get_watch_links(movie_id, title, year, movie_data.get('providers', {}), force_refresh)

        # Use canonical streaming/rent/buy schema directly
        watch_links = watch_links_raw

        return {
            'id': movie_id,
            'title': title,
            'digital_date': movie_data.get('digital_date'),
            'poster': f"https://image.tmdb.org/t/p/w500{movie_details['poster_path']}" if movie_details.get('poster_path') else None,
            'synopsis': movie_details.get('overview', 'No synopsis available.'),
            'crew': {
                'director': director,
                'cast': cast
            },
            'genres': genres,
            'studio': studio,
            'runtime': runtime,
            'year': int(year) if year else None,
            'country': country,
            'rt_score': None,  # Will be filled by RT cache if available
            'providers': movie_data.get('providers', {}),
            'links': links,
            'watch_links': watch_links
        }
    
    def generate_display_data(self, days_back=90, incremental=True, force_refresh=False):
        """Generate display data from tracking database

        Args:
            days_back: How many days back to look for available movies
            incremental: If True, only process NEW movies not already in data.json (default)
                        If False, regenerate entire data.json from scratch
        """

        # Load tracking database
        if not os.path.exists('movie_tracking.json'):
            print("❌ No tracking database found. Run 'python movie_tracker.py daily' first")
            return

        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)

        # Load existing data.json if incremental mode
        existing_movies = []
        existing_ids = set()
        if incremental and os.path.exists('data.json'):
            with open('data.json', 'r') as f:
                existing_data = json.load(f)
                existing_movies = existing_data.get('movies', [])
                existing_ids = {str(m['id']) for m in existing_movies}
            print(f"📂 Incremental mode: Found {len(existing_movies)} existing movies in data.json")

        # Filter to recently available movies
        cutoff_date = datetime.now() - timedelta(days=days_back)
        new_movies = []

        if incremental:
            print(f"🎬 Processing NEW movies that went digital in last {days_back} days...")
        else:
            print(f"🎬 Processing ALL movies that went digital in last {days_back} days...")

        for movie_id, movie_data in db['movies'].items():
            # Skip if already in data.json (incremental mode)
            if incremental and movie_id in existing_ids:
                continue

            if movie_data['status'] == 'available' and movie_data.get('digital_date'):
                try:
                    digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                    if digital_date >= cutoff_date:
                        # Get full movie details (movie_id is the TMDB ID)
                        movie_details = self.get_movie_details(movie_id)
                        if movie_details:
                            processed = self.process_movie(movie_id, movie_data, movie_details, force_refresh)
                            if processed:
                                new_movies.append(processed)
                                print(f"  ✓ {processed['title']} - Links: {len(processed['links'])}")

                        time.sleep(0.2)  # Rate limiting

                except Exception as e:
                    print(f"  ✗ Error processing {movie_data.get('title')}: {e}")

        # Merge with existing movies if incremental
        if incremental:
            print(f"\n📋 Adding {len(new_movies)} new movies to {len(existing_movies)} existing movies")
            display_movies = existing_movies + new_movies
        else:
            display_movies = new_movies
        
        # Sort by digital release date (newest first)
        display_movies.sort(key=lambda x: x['digital_date'], reverse=True)
        
        # Apply admin panel overrides (hide/feature movies)
        display_movies = self.apply_admin_overrides(display_movies)
        
        # Save display data
        output_data = {
            'generated_at': datetime.now().isoformat(),
            'count': len(display_movies),
            'movies': display_movies
        }
        
        with open('data.json', 'w') as f:
            json.dump(output_data, f, indent=2)
        
        # Save caches
        self.save_cache(self.wikipedia_cache, 'wikipedia_cache.json')
        self.save_cache(self.rt_cache, 'rt_cache.json')
        
        print(f"\n✅ Generated data.json with {len(display_movies)} movies")
        print(f"Wikipedia links found: {len([m for m in display_movies if m['links'].get('wikipedia')])}")
        print(f"Direct trailers found: {len([m for m in display_movies if m['links'].get('trailer') and 'watch?v=' in m['links']['trailer']])}")
        print(f"RT scores cached: {len([m for m in display_movies if m['rt_score']])}")

        # Watchmode usage statistics
        total_calls = self.watchmode_stats['search_calls'] + self.watchmode_stats['source_calls']
        cache_hit_rate = (self.watchmode_stats['cache_hits'] / (self.watchmode_stats['cache_hits'] + total_calls) * 100) if (self.watchmode_stats['cache_hits'] + total_calls) > 0 else 0
        success_rate = (self.watchmode_stats['watchmode_successes'] / self.watchmode_stats['search_calls'] * 100) if self.watchmode_stats['search_calls'] > 0 else 0

        print(f"\n📊 Watchmode API Usage:")
        print(f"  Search calls: {self.watchmode_stats['search_calls']}")
        print(f"  Source calls: {self.watchmode_stats['source_calls']}")
        print(f"  Cache hits: {self.watchmode_stats['cache_hits']}")
        print(f"  Cache hit rate: {cache_hit_rate:.1f}%")
        print(f"  Watchmode success rate: {success_rate:.1f}%")

    def apply_admin_overrides(self, display_movies):
        """Apply admin panel decisions to final output"""
        
        # Load admin decisions if they exist
        hidden = []
        featured = []
        
        if os.path.exists('admin/hidden_movies.json'):
            with open('admin/hidden_movies.json', 'r') as f:
                hidden = json.load(f)
        
        if os.path.exists('admin/featured_movies.json'):
            with open('admin/featured_movies.json', 'r') as f:
                featured = json.load(f)
        
        # Filter out hidden movies
        filtered_movies = [m for m in display_movies 
                          if str(m['id']) not in hidden]
        
        # Mark featured movies
        for movie in filtered_movies:
            if str(movie['id']) in featured:
                movie['featured'] = True
        
        hidden_count = len(display_movies) - len(filtered_movies)
        featured_count = len([m for m in filtered_movies if m.get('featured')])
        
        print(f"📝 Admin overrides applied:")
        print(f"  Hidden movies: {hidden_count}")
        print(f"  Featured movies: {featured_count}")
        
        return filtered_movies

def main():
    parser = argparse.ArgumentParser(description="Generate display data from tracking database with enriched links")
    parser.add_argument('--full', action='store_true', help='Regenerate entire data.json from scratch (default: incremental mode - only process new movies)')

    args = parser.parse_args()
    incremental = not args.full
    force_refresh = args.full  # Force refresh cache on full runs

    generator = DataGenerator()
    generator.generate_display_data(incremental=incremental, force_refresh=force_refresh)

if __name__ == "__main__":
    main()