# ================================================================
# NEW RELEASE WALL - ALL CODE CONCATENATED
# Generated: Fri Aug 22 18:46:07 PDT 2025
# Purpose: Complete codebase for syncing with other AI systems
# ================================================================

# ================================================================
# FILE: ./adapter.py
# ================================================================
# adapter.py
from datetime import datetime

# Map store names to short platform codes the UI shows
PLATFORM_MAP = {
    "Apple TV": "itunes",
    "iTunes": "itunes",
    "Amazon Prime Video": "amazon",
    "Amazon": "amazon",
    "Netflix": "other",
    "YouTube": "youtube",
    "Google Play Movies": "google",
    "Vudu": "vudu",
    "Max": "other",
    "Hulu": "other",
    "Disney Plus": "other",
    "MUBI": "mubi",
    "Criterion Channel": "other",
}

def to_iso(d):
    # Accepts: datetime, 'YYYY-MM-DD', or already ISO; returns ISO string
    if isinstance(d, datetime):
        return d.isoformat()
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d).isoformat()
        except Exception:
            try:
                return datetime.strptime(d, "%Y-%m-%d").isoformat()
            except Exception:
                return datetime.utcnow().isoformat()
    return datetime.utcnow().isoformat()

def platform_entry(store_name, url=None, rent=None, buy=None):
    p = PLATFORM_MAP.get(store_name, "other")
    entry = {"platform": p, "url": url or ""}
    if rent is not None:
        entry["rent"] = {"price": float(rent)}  # price as number
    if buy is not None:
        entry["buy"] = {"price": float(buy)}
    return entry

def normalize_title(item):
    """
    Convert ONE scraped item into the UI schema.

    Expected incoming keys (examples):
      item["title"], item["year"], item["genres"] (list or comma string),
      item["availability_date"] (home-viewing date),
      item["stores"] -> list of dicts like:
         {"name": "Apple TV", "url": "...", "rent": 5.99, "buy": 14.99}
      item["id"] or any unique key (fallback: title+year)
      item["poster"] (optional)
    """
    title = item.get("title", "").strip()
    year = item.get("year")
    genres = item.get("genres") or []
    if isinstance(genres, str):
        genres = [g.strip() for g in genres.split(",") if g.strip()]
    availability = to_iso(item.get("availability_date") or item.get("date") or "")
    poster = item.get("poster_url") or item.get("poster") or ""

    stores = item.get("stores") or []
    platforms = []
    for s in stores:
        platforms.append(
            platform_entry(
                store_name=s.get("name", ""),
                url=s.get("url") or "",
                rent=s.get("rent"),
                buy=s.get("buy"),
            )
        )

    # Ensure a stable id
    uid = item.get("id") or f"{title.lower()}:{year or ''}"

    return {
        "id": uid,
        "title": title,
        "poster": poster,
        "year": year if isinstance(year, int) else (int(year) if str(year).isdigit() else None),
        "genres": genres,
        "availabilityDate": availability,
        "platforms": platforms,
    }


# ================================================================
# FILE: ./admin.py
# ================================================================
#!/usr/bin/env python3
"""
Admin panel for curating movie selections.
Simple Flask app for editing movie data and controlling visibility.
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import json
import os
from datetime import datetime

app = Flask(__name__)

# Configuration
DATA_FILE = 'output/data.json'
HIDDEN_FILE = 'output/hidden_movies.json'
FEATURED_FILE = 'output/featured_movies.json'
REVIEWS_FILE = 'output/movie_reviews.json'

# HTML Template for admin interface
ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Release Wall - Admin Panel</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a1a;
            color: #fff;
            padding: 2rem;
        }
        
        .header {
            background: #2a2a2a;
            padding: 2rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            border: 1px solid #3a3a3a;
        }
        
        h1 {
            font-size: 2rem;
            margin-bottom: 0.5rem;
            color: #ff6b6b;
        }
        
        .stats {
            display: flex;
            gap: 2rem;
            margin-top: 1rem;
            color: #999;
        }
        
        .stat-item {
            display: flex;
            gap: 0.5rem;
        }
        
        .stat-value {
            color: #fff;
            font-weight: bold;
        }
        
        .filters {
            background: #2a2a2a;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            border: 1px solid #3a3a3a;
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .filter-btn {
            padding: 0.5rem 1rem;
            background: #4a4a6a;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .filter-btn:hover {
            background: #5a5a7a;
        }
        
        .filter-btn.active {
            background: #ff6b6b;
        }
        
        .movie-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
        }
        
        .movie-card {
            background: #2a2a2a;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #3a3a3a;
            transition: transform 0.3s;
        }
        
        .movie-card:hover {
            transform: translateY(-2px);
            border-color: #4a4a6a;
        }
        
        .movie-card.hidden {
            opacity: 0.5;
            border-color: #ff4444;
        }
        
        .movie-card.featured {
            border-color: #ffd700;
            box-shadow: 0 0 10px rgba(255, 215, 0, 0.3);
        }
        
        .movie-poster {
            width: 100%;
            height: 200px;
            object-fit: cover;
            background: #1a1a1a;
        }
        
        .movie-info {
            padding: 1rem;
        }
        
        .movie-title {
            font-size: 1.1rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
            color: #fff;
        }
        
        .movie-meta {
            font-size: 0.9rem;
            color: #999;
            margin-bottom: 0.5rem;
        }
        
        .movie-score {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            background: #333;
            border-radius: 4px;
            margin-right: 0.5rem;
        }
        
        .score-high {
            background: #28a745;
            color: white;
        }
        
        .score-medium {
            background: #ffc107;
            color: black;
        }
        
        .score-low {
            background: #dc3545;
            color: white;
        }
        
        .movie-providers {
            font-size: 0.85rem;
            color: #66b3ff;
            margin-bottom: 0.5rem;
        }
        
        .movie-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: 1rem;
            flex-wrap: wrap;
        }
        
        .action-btn {
            padding: 0.4rem 0.8rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.3s;
            text-decoration: none;
        }
        
        .btn-hide {
            background: #dc3545;
            color: white;
        }
        
        .btn-show {
            background: #28a745;
            color: white;
        }
        
        .btn-feature {
            background: #ffc107;
            color: black;
        }
        
        .btn-unfeature {
            background: #6c757d;
            color: white;
        }
        
        .btn-rt {
            background: #ff6b6b;
            color: white;
        }
        
        .btn-tmdb {
            background: #01d277;
            color: white;
        }
        
        .action-btn:hover {
            opacity: 0.8;
        }
        
        .search-box {
            flex: 1;
            padding: 0.5rem 1rem;
            background: #1a1a1a;
            border: 1px solid #3a3a3a;
            color: white;
            border-radius: 4px;
            max-width: 300px;
        }
        
        .success-msg {
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: #28a745;
            color: white;
            padding: 1rem 2rem;
            border-radius: 4px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎬 New Release Wall - Admin Panel</h1>
        <div class="stats">
            <div class="stat-item">
                <span>Total Movies:</span>
                <span class="stat-value">{{ movies|length }}</span>
            </div>
            <div class="stat-item">
                <span>Visible:</span>
                <span class="stat-value" id="visible-count">{{ visible_count }}</span>
            </div>
            <div class="stat-item">
                <span>Hidden:</span>
                <span class="stat-value" id="hidden-count">{{ hidden_count }}</span>
            </div>
            <div class="stat-item">
                <span>Featured:</span>
                <span class="stat-value" id="featured-count">{{ featured_count }}</span>
            </div>
        </div>
    </div>
    
    <div class="filters">
        <button class="filter-btn active" onclick="filterMovies('all')">All Movies</button>
        <button class="filter-btn" onclick="filterMovies('visible')">Visible Only</button>
        <button class="filter-btn" onclick="filterMovies('hidden')">Hidden Only</button>
        <button class="filter-btn" onclick="filterMovies('featured')">Featured</button>
        <button class="filter-btn" onclick="filterMovies('no-score')">No RT Score</button>
        <input type="text" class="search-box" placeholder="Search movies..." onkeyup="searchMovies(this.value)">
    </div>
    
    <div class="movie-grid" id="movie-grid">
        {% for movie_id, movie in movies.items() %}
        <div class="movie-card {% if movie_id in hidden %}hidden{% endif %} {% if movie_id in featured %}featured{% endif %}" 
             data-movie-id="{{ movie_id }}"
             data-title="{{ movie.title|lower }}"
             data-has-score="{{ 'yes' if movie.rt_score else 'no' }}">
            {% if movie.poster_url %}
            <img src="{{ movie.poster_url }}" alt="{{ movie.title }}" class="movie-poster">
            {% else %}
            <div class="movie-poster" style="display: flex; align-items: center; justify-content: center; color: #666;">
                No Poster
            </div>
            {% endif %}
            
            <div class="movie-info">
                <div class="movie-title">{{ movie.title }}</div>
                <div class="movie-meta">
                    {{ movie.year or '2025' }} • {{ movie.director or 'Unknown Director' }}
                </div>
                
                {% if movie.rt_score %}
                <span class="movie-score {% if movie.rt_score >= 80 %}score-high{% elif movie.rt_score >= 60 %}score-medium{% else %}score-low{% endif %}">
                    🍅 {{ movie.rt_score }}%
                </span>
                {% else %}
                <span class="movie-score">No RT Score</span>
                {% endif %}
                
                {% if movie.runtime %}
                <span class="movie-meta">{{ movie.runtime }} min</span>
                {% endif %}
                
                {% if movie.provider_list %}
                <div class="movie-providers">{{ movie.provider_list }}</div>
                {% endif %}
                
                <div class="movie-actions">
                    {% if movie_id in hidden %}
                    <button class="action-btn btn-show" onclick="toggleHidden('{{ movie_id }}', false)">👁️ Show</button>
                    {% else %}
                    <button class="action-btn btn-hide" onclick="toggleHidden('{{ movie_id }}', true)">🚫 Hide</button>
                    {% endif %}
                    
                    {% if movie_id in featured %}
                    <button class="action-btn btn-unfeature" onclick="toggleFeatured('{{ movie_id }}', false)">⭐ Unfeature</button>
                    {% else %}
                    <button class="action-btn btn-feature" onclick="toggleFeatured('{{ movie_id }}', true)">⭐ Feature</button>
                    {% endif %}
                    
                    {% if movie.rt_url %}
                    <a href="{{ movie.rt_url }}" target="_blank" class="action-btn btn-rt">RT →</a>
                    {% else %}
                    <a href="https://www.rottentomatoes.com/search?search={{ movie.title }}" target="_blank" class="action-btn btn-rt">RT Search</a>
                    {% endif %}
                    
                    <a href="https://www.themoviedb.org/movie/{{ movie.tmdb_id or movie_id }}" target="_blank" class="action-btn btn-tmdb">TMDB →</a>
                </div>
                
                <div class="date-editor" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #3a3a3a;">
                    <div style="font-size: 0.85rem; color: #999; margin-bottom: 0.5rem;">
                        Digital Release: {{ movie.digital_date or 'Unknown' }}
                    </div>
                    <div style="display: flex; gap: 0.5rem; align-items: center;">
                        <input type="date" 
                               class="date-input" 
                               style="flex: 1; padding: 0.3rem; background: #1a1a1a; border: 1px solid #3a3a3a; color: white; border-radius: 4px; font-size: 0.8rem;"
                               value="{{ movie.digital_date }}"
                               id="date-{{ movie_id }}">
                        <button class="action-btn" 
                                style="background: #007bff; color: white; font-size: 0.7rem; padding: 0.3rem 0.6rem;"
                                onclick="updateDate('{{ movie_id }}')">
                            📅 Update
                        </button>
                    </div>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    
    <div class="success-msg" id="success-msg">Changes saved!</div>
    
    <script>
        function toggleHidden(movieId, hide) {
            fetch('/toggle-hidden', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({movie_id: movieId, hidden: hide})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                }
            });
        }
        
        function toggleFeatured(movieId, feature) {
            fetch('/toggle-featured', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({movie_id: movieId, featured: feature})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                }
            });
        }
        
        function showSuccess(message = 'Changes saved!') {
            const msg = document.getElementById('success-msg');
            msg.textContent = message;
            msg.style.display = 'block';
            setTimeout(() => {
                msg.style.display = 'none';
            }, 3000);
        }
        
        function filterMovies(filter) {
            const cards = document.querySelectorAll('.movie-card');
            const buttons = document.querySelectorAll('.filter-btn');
            
            // Update active button
            buttons.forEach(btn => {
                btn.classList.remove('active');
                if (btn.textContent.toLowerCase().includes(filter) || 
                    (filter === 'all' && btn.textContent === 'All Movies')) {
                    btn.classList.add('active');
                }
            });
            
            // Filter cards
            cards.forEach(card => {
                switch(filter) {
                    case 'all':
                        card.style.display = 'block';
                        break;
                    case 'visible':
                        card.style.display = card.classList.contains('hidden') ? 'none' : 'block';
                        break;
                    case 'hidden':
                        card.style.display = card.classList.contains('hidden') ? 'block' : 'none';
                        break;
                    case 'featured':
                        card.style.display = card.classList.contains('featured') ? 'block' : 'none';
                        break;
                    case 'no-score':
                        card.style.display = card.dataset.hasScore === 'no' ? 'block' : 'none';
                        break;
                }
            });
        }
        
        function searchMovies(query) {
            const cards = document.querySelectorAll('.movie-card');
            const searchTerm = query.toLowerCase();
            
            cards.forEach(card => {
                const title = card.dataset.title;
                if (title.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }
        
        function updateDate(movieId) {
            const dateInput = document.getElementById(`date-${movieId}`);
            const newDate = dateInput.value;
            
            if (!newDate) {
                alert('Please select a date');
                return;
            }
            
            fetch('/update-date', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    movie_id: movieId,
                    digital_date: newDate
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showSuccess(data.message || 'Date updated successfully!');
                    // Update the displayed date
                    const dateDisplay = dateInput.closest('.date-editor').querySelector('div');
                    dateDisplay.textContent = `Digital Release: ${newDate}`;
                } else {
                    alert(data.error || 'Failed to update date');
                }
            })
            .catch(error => {
                alert('Error updating date: ' + error);
            });
        }
    </script>
</body>
</html>
'''

def load_json(filepath, default=None):
    """Load JSON file with fallback"""
    if default is None:
        default = {}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return default

def get_poster_url(tmdb_id):
    """Get poster URL from TMDB ID"""
    if not tmdb_id:
        return None
    
    try:
        import requests
        api_key = "99b122ce7fa3e9065d7b7dc6e660772d"
        response = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": api_key}
        )
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w300{poster_path}"
    except:
        pass
    return None

def save_json(filepath, data):
    """Save JSON file"""
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def index():
    """Main admin panel"""
    movies = load_json(DATA_FILE)
    hidden = load_json(HIDDEN_FILE, [])
    featured = load_json(FEATURED_FILE, [])
    reviews = load_json(REVIEWS_FILE)
    
    # Add poster URLs for first 20 movies (for performance)
    movie_items = list(movies.items()) if isinstance(movies, dict) else [(str(i), m) for i, m in enumerate(movies)]
    limited_movies = {}
    
    for i, (movie_id, movie) in enumerate(movie_items[:20]):  # Limit to first 20 for demo
        movie_copy = movie.copy()
        if not movie_copy.get('poster_url') and movie_copy.get('tmdb_id'):
            movie_copy['poster_url'] = get_poster_url(movie_copy['tmdb_id'])
        limited_movies[movie_id] = movie_copy
    
    # Calculate stats
    visible_count = len([m for m in movies if m not in hidden])
    hidden_count = len(hidden)
    featured_count = len(featured)
    
    return render_template_string(
        ADMIN_TEMPLATE,
        movies=limited_movies,
        hidden=hidden,
        featured=featured,
        reviews=reviews,
        visible_count=visible_count,
        hidden_count=hidden_count,
        featured_count=featured_count
    )

@app.route('/toggle-hidden', methods=['POST'])
def toggle_hidden():
    """Toggle movie visibility"""
    data = request.json
    movie_id = data.get('movie_id')
    is_hidden = data.get('hidden', False)
    
    hidden = load_json(HIDDEN_FILE, [])
    
    if is_hidden and movie_id not in hidden:
        hidden.append(movie_id)
    elif not is_hidden and movie_id in hidden:
        hidden.remove(movie_id)
    
    save_json(HIDDEN_FILE, hidden)
    return jsonify({'success': True})

@app.route('/toggle-featured', methods=['POST'])
def toggle_featured():
    """Toggle movie featured status"""
    data = request.json
    movie_id = data.get('movie_id')
    is_featured = data.get('featured', False)
    
    featured = load_json(FEATURED_FILE, [])
    
    if is_featured and movie_id not in featured:
        featured.append(movie_id)
    elif not is_featured and movie_id in featured:
        featured.remove(movie_id)
    
    save_json(FEATURED_FILE, featured)
    return jsonify({'success': True})

@app.route('/update-date', methods=['POST'])
def update_date():
    """Update movie's digital release date"""
    data = request.json
    movie_id = data.get('movie_id')
    new_date = data.get('digital_date')
    
    # Update in tracking database
    try:
        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)
        
        if movie_id in db['movies']:
            db['movies'][movie_id]['digital_date'] = new_date
            db['movies'][movie_id]['manually_corrected'] = True
            
            with open('movie_tracking.json', 'w') as f:
                json.dump(db, f, indent=2)
            
            # Also update the admin data
            admin_data = load_json(DATA_FILE)
            if movie_id in admin_data:
                admin_data[movie_id]['digital_date'] = new_date
                save_json(DATA_FILE, admin_data)
            
            return jsonify({'success': True, 'message': f'Date updated to {new_date}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Movie not found'})

if __name__ == '__main__':
    print("\n🎬 New Release Wall Admin Panel")
    print("================================")
    print("Starting server at http://localhost:5555")
    print("Press Ctrl+C to stop\n")
    
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5555)


# ================================================================
# FILE: ./concurrent_scraper.py
# ================================================================
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

# ================================================================
# FILE: ./convert_tracking_to_vhs.py
# ================================================================
#!/usr/bin/env python3
"""
Convert movie_tracking.json to VHS site format (output/data.json)
Transforms the comprehensive tracking database to the format expected by generate_site.py
"""
import json
import os
from datetime import datetime

def convert_tracking_to_vhs_format():
    """Convert tracking database to VHS site format"""
    
    # Load the comprehensive tracking database
    with open('movie_tracking.json', 'r') as f:
        tracking_db = json.load(f)
    
    movies = tracking_db.get('movies', {})
    print(f"📊 Loading {len(movies)} movies from tracking database...")
    
    # Filter to only resolved movies (that went digital) from last 30 days
    vhs_movies = []
    cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for movie_id, movie_data in movies.items():
        # Only include resolved movies with digital dates
        if movie_data.get('status') != 'resolved' or not movie_data.get('digital_date'):
            continue
            
        # Check if digital release is recent (last 30 days)
        try:
            digital_date = datetime.fromisoformat(movie_data['digital_date'])
            days_since_digital = (cutoff_date - digital_date).days
            
            # Include movies that went digital in the last 30 days
            if days_since_digital > 30:
                continue
        except:
            continue  # Skip if date parsing fails
        
        # Convert to VHS format
        vhs_movie = {
            "title": movie_data.get('title', 'Unknown'),
            "tmdb_id": movie_data.get('tmdb_id'),
            "theatrical_date": movie_data.get('theatrical_date'),
            "digital_date": movie_data.get('digital_date'),
            "status": "resolved",
            "added_to_db": movie_data.get('added_to_db'),
            "last_checked": movie_data.get('last_checked'),
            "providers": {
                "rent": [],
                "buy": [],
                "stream": []
            }
        }
        
        # Add RT score if available
        if movie_data.get('rt_score'):
            vhs_movie['rt_score'] = movie_data['rt_score']
        else:
            vhs_movie['rt_score'] = None
            
        vhs_movies.append(vhs_movie)
    
    # Sort by digital date (newest first)
    vhs_movies.sort(key=lambda x: x['digital_date'] if x['digital_date'] else '1900-01-01', reverse=True)
    
    # Save to output directory
    os.makedirs('output', exist_ok=True)
    with open('output/data.json', 'w') as f:
        json.dump(vhs_movies, f, indent=2)
    
    print(f"✅ Converted {len(vhs_movies)} recent movies to VHS format")
    print(f"   Movies from last 30 days with digital releases")
    print(f"   Saved to: output/data.json")
    
    # Show sample of what was included
    if vhs_movies:
        print(f"\n📽️  Recent digital releases (sample):")
        for movie in vhs_movies[:5]:
            rt_text = f" (RT: {movie.get('rt_score')}%)" if movie.get('rt_score') else ""
            print(f"   • {movie['title']} - Digital: {movie['digital_date']}{rt_text}")
    
    return len(vhs_movies)

if __name__ == '__main__':
    convert_tracking_to_vhs_format()

# ================================================================
# FILE: ./diagnostics.py
# ================================================================
#!/usr/bin/env python3
"""
Consolidated Diagnostic Tool
Combines all diagnostic functions from various scripts
"""

import requests
import yaml
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class TMDBDiagnostics:
    """Unified diagnostic tool for TMDB API testing"""
    
    def __init__(self):
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
            self.api_key = config['tmdb_api_key']
            self.omdb_key = config.get('omdb_api_key')
    
    def diagnose_api_filter(self, days: int = 45, pages: int = 5):
        """
        Compare OLD vs NEW API approaches (from corrected_diagnosis.py)
        Proves the API filter issue
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        print("="*70)
        print("API FILTER DIAGNOSIS")
        print("="*70)
        print(f"Date range: {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}")
        
        # OLD approach with filter
        print("\n1. OLD METHOD - with_release_type='2|3|4|6' filter")
        print("-" * 50)
        
        old_movies = self._fetch_movies_with_filter(start_date, end_date, pages)
        old_digital = self._check_digital_availability(old_movies)
        
        print(f"  Total with filter: {len(old_movies)}")
        print(f"  Actually digital: {len(old_digital)}")
        print(f"  False positives: {len(old_movies) - len(old_digital)}")
        
        # NEW approach without filter
        print("\n2. NEW METHOD - No filter, check each movie")
        print("-" * 50)
        
        all_movies = self._fetch_movies_no_filter(start_date, end_date, pages)
        new_digital = self._check_digital_availability(all_movies)
        
        print(f"  Total without filter: {len(all_movies)}")
        print(f"  Actually digital: {len(new_digital)}")
        
        # Comparison
        print("\n" + "="*70)
        print("COMPARISON")
        print("="*70)
        
        old_ids = {m['id'] for m in old_digital}
        new_ids = {m['id'] for m in new_digital}
        
        only_new = new_ids - old_ids
        improvement = (len(new_ids) / len(old_ids) * 100 - 100) if old_ids else 0
        
        print(f"OLD method found: {len(old_ids)} movies")
        print(f"NEW method found: {len(new_ids)} movies")
        print(f"Additional movies with NEW: {len(only_new)}")
        print(f"Improvement: {improvement:.1f}%")
        
        if only_new:
            print("\nExamples of movies OLD method missed:")
            for movie in new_digital:
                if movie['id'] in only_new:
                    print(f"  • {movie['title']} ({movie.get('release_date', '')[:4]})")
                    if len(list(only_new)) >= 5:
                        break
    
    def check_movie(self, title: str, year: Optional[int] = None):
        """
        Deep dive into a specific movie's data
        """
        print(f"\n{'='*60}")
        print(f"MOVIE DIAGNOSTIC: {title} ({year or 'any year'})")
        print(f"{'='*60}")
        
        # Search for movie
        search_url = "https://api.themoviedb.org/3/search/movie"
        params = {'api_key': self.api_key, 'query': title}
        if year:
            params['year'] = year
        
        response = requests.get(search_url, params=params)
        results = response.json().get('results', [])
        
        if not results:
            print("❌ Movie not found in TMDB")
            return
        
        movie = results[0]
        movie_id = movie['id']
        print(f"✅ Found: {movie['title']} (ID: {movie_id})")
        print(f"   Release Date: {movie.get('release_date', 'Unknown')}")
        print(f"   Overview: {movie.get('overview', '')[:100]}...")
        
        # Get release types
        print("\n📅 Release Types:")
        release_types = self._get_release_types(movie_id)
        
        type_names = {
            1: 'Premiere',
            2: 'Limited Theatrical',
            3: 'Wide Theatrical',
            4: 'Digital',
            5: 'Physical',
            6: 'TV'
        }
        
        for country, types in release_types.items():
            if country == 'US' or len(release_types) == 1:
                print(f"   {country}:")
                for t in types:
                    type_num = t['type']
                    date = t['release_date'][:10] if t.get('release_date') else 'No date'
                    print(f"     Type {type_num} ({type_names.get(type_num, 'Unknown')}): {date}")
        
        # Check providers
        print("\n🎬 Streaming Providers (US):")
        providers = self._get_providers(movie_id)
        
        if providers:
            for category, provider_list in providers.items():
                if provider_list:
                    names = [p['provider_name'] for p in provider_list[:5]]
                    print(f"   {category}: {', '.join(names)}")
        else:
            print("   No providers found")
        
        # Check RT scores
        if self.omdb_key:
            print("\n⭐ Review Scores:")
            scores = self._get_review_scores(movie['title'], year)
            if scores:
                for source, score in scores.items():
                    print(f"   {source}: {score}")
            else:
                print("   No scores found")
    
    def verify_tracking(self, db_path: str = 'movie_tracking.json'):
        """
        Verify tracking database integrity
        """
        print(f"\n{'='*60}")
        print("TRACKING DATABASE VERIFICATION")
        print(f"{'='*60}")
        
        try:
            with open(db_path, 'r') as f:
                db = json.load(f)
        except FileNotFoundError:
            print(f"❌ Database not found: {db_path}")
            return
        
        movies = db.get('movies', {})
        print(f"Total movies tracked: {len(movies)}")
        
        # Analyze by status
        stats = {
            'has_digital': 0,
            'has_providers': 0,
            'has_rt_score': 0,
            'hidden': 0,
            'featured': 0
        }
        
        for movie_id, data in movies.items():
            if data.get('has_digital'):
                stats['has_digital'] += 1
            if data.get('providers'):
                stats['has_providers'] += 1
            if data.get('rt_score'):
                stats['has_rt_score'] += 1
            if data.get('hidden'):
                stats['hidden'] += 1
            if data.get('featured'):
                stats['featured'] += 1
        
        print("\n📊 Statistics:")
        for key, value in stats.items():
            pct = value / len(movies) * 100 if movies else 0
            print(f"  {key}: {value} ({pct:.1f}%)")
        
        # Recent additions
        recent = sorted(
            movies.items(),
            key=lambda x: x[1].get('added_date', ''),
            reverse=True
        )[:10]
        
        print("\n🆕 Recently Added:")
        for movie_id, data in recent:
            added = data.get('added_date', 'Unknown')[:10]
            title = data.get('title', 'Unknown')[:30]
            print(f"  {added}: {title}")
    
    def check_providers(self, region: str = 'US'):
        """
        List all available providers in region
        """
        print(f"\n{'='*60}")
        print(f"PROVIDERS IN {region}")
        print(f"{'='*60}")
        
        url = "https://api.themoviedb.org/3/watch/providers/movie"
        params = {'api_key': self.api_key, 'watch_region': region}
        
        response = requests.get(url, params=params)
        providers = response.json().get('results', [])
        
        # Group by type
        streaming = []
        rental = []
        
        for p in providers:
            name = p['provider_name']
            # This is approximate - TMDB doesn't clearly distinguish
            if any(x in name.lower() for x in ['netflix', 'prime', 'disney', 'hulu', 'max', 'paramount']):
                streaming.append(name)
            else:
                rental.append(name)
        
        print(f"\n📺 Major Streaming ({len(streaming)}):")
        for name in sorted(streaming)[:20]:
            print(f"  • {name}")
        
        print(f"\n💰 Rental/Purchase ({len(rental)}):")
        for name in sorted(rental)[:20]:
            print(f"  • {name}")
        
        print(f"\nTotal providers: {len(providers)}")
    
    # Helper methods
    def _fetch_movies_with_filter(self, start_date, end_date, pages):
        """Fetch with release type filter (OLD method)"""
        movies = []
        for page in range(1, pages + 1):
            params = {
                'api_key': self.api_key,
                'region': 'US',
                'with_release_type': '2|3|4|6',
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc',
                'page': page
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            page_movies = response.json().get('results', [])
            movies.extend(page_movies)
            time.sleep(0.2)
            
        return movies
    
    def _fetch_movies_no_filter(self, start_date, end_date, pages):
        """Fetch without filter (NEW method)"""
        movies = []
        for page in range(1, pages + 1):
            params = {
                'api_key': self.api_key,
                'region': 'US',
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc',
                'page': page
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            page_movies = response.json().get('results', [])
            movies.extend(page_movies)
            time.sleep(0.2)
            
        return movies
    
    def _check_digital_availability(self, movies):
        """Check which movies have digital release types"""
        digital_movies = []
        
        for movie in movies:
            types = self._get_us_release_types(movie['id'])
            if 4 in types or 6 in types:
                digital_movies.append(movie)
            time.sleep(0.1)
            
        return digital_movies
    
    def _get_us_release_types(self, movie_id):
        """Get US release types for a movie"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            for country_data in data.get('results', []):
                if country_data['iso_3166_1'] == 'US':
                    return [r['type'] for r in country_data.get('release_dates', [])]
        except:
            pass
            
        return []
    
    def _get_release_types(self, movie_id):
        """Get all release types by country"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            result = {}
            for country_data in data.get('results', []):
                country = country_data['iso_3166_1']
                result[country] = country_data.get('release_dates', [])
            
            return result
        except:
            return {}
    
    def _get_providers(self, movie_id):
        """Get streaming providers"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
        
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            us_data = data.get('results', {}).get('US', {})
            return {
                'rent': us_data.get('rent', []),
                'buy': us_data.get('buy', []),
                'flatrate': us_data.get('flatrate', [])
            }
        except:
            return {}
    
    def _get_review_scores(self, title, year):
        """Get review scores from OMDb"""
        try:
            params = {'apikey': self.omdb_key, 't': title}
            if year:
                params['y'] = str(year)
            
            response = requests.get('http://www.omdbapi.com/', params=params)
            data = response.json()
            
            if data.get('Response') == 'True':
                scores = {}
                
                # IMDB
                if data.get('imdbRating') and data['imdbRating'] != 'N/A':
                    scores['IMDB'] = data['imdbRating']
                
                # Other ratings
                for rating in data.get('Ratings', []):
                    scores[rating['Source']] = rating['Value']
                
                return scores
        except:
            pass
            
        return {}

def main():
    parser = argparse.ArgumentParser(description='TMDB Diagnostic Tool')
    parser.add_argument('command', choices=['filter', 'movie', 'tracking', 'providers'],
                       help='Diagnostic command to run')
    parser.add_argument('--title', help='Movie title for movie command')
    parser.add_argument('--year', type=int, help='Movie year')
    parser.add_argument('--days', type=int, default=45, help='Days to look back')
    parser.add_argument('--region', default='US', help='Region code')
    
    args = parser.parse_args()
    
    diag = TMDBDiagnostics()
    
    if args.command == 'filter':
        diag.diagnose_api_filter(days=args.days)
    elif args.command == 'movie':
        if not args.title:
            print("Error: --title required for movie command")
        else:
            diag.check_movie(args.title, args.year)
    elif args.command == 'tracking':
        diag.verify_tracking()
    elif args.command == 'providers':
        diag.check_providers(args.region)

if __name__ == "__main__":
    main()

# ================================================================
# FILE: ./enhanced_discovery.py
# ================================================================
#!/usr/bin/env python3
"""
Enhanced discovery system that includes low-popularity indie films
"""

import requests
import json
import time
from datetime import datetime, timedelta

class EnhancedDiscovery:
    def __init__(self):
        with open('config.yaml', 'r') as f:
            import yaml
            config = yaml.safe_load(f)
        self.api_key = config['tmdb_api_key']
        
    def tmdb_get(self, endpoint, params=None):
        """Make TMDB API request"""
        if params is None:
            params = {}
        params['api_key'] = self.api_key
        
        url = f"https://api.themoviedb.org/3{endpoint}"
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            return response.json()
        return {}
    
    def discover_with_multiple_approaches(self, start_date, end_date):
        """Use multiple discovery approaches to catch indie films"""
        all_movies = set()
        
        print("🔍 Enhanced Discovery: Multiple approaches to find ALL films...")
        
        # Approach 1: Standard discovery (catches mainstream films)
        print("  📈 Approach 1: Standard popularity-based discovery")
        movies = self.standard_discovery(start_date, end_date)
        all_movies.update([str(m['id']) for m in movies])
        print(f"    Found {len(movies)} mainstream films")
        
        # Approach 2: Company-based discovery (catches studio indies)
        print("  🎭 Approach 2: Studio/company-based discovery")
        indie_companies = [
            41077,   # A24
            2,       # Neon
            491,     # Focus Features  
            25,      # IFC Films
            61,      # Magnolia Pictures
            11072,   # Searchlight Pictures
            7505,    # Bleecker Street
            1632,    # Lionsgate
            33,      # Universal Pictures (includes Focus)
        ]
        
        company_movies = self.discover_by_companies(indie_companies, start_date, end_date)
        new_company_movies = [m for m in company_movies if str(m['id']) not in all_movies]
        all_movies.update([str(m['id']) for m in company_movies])
        print(f"    Found {len(new_company_movies)} additional studio films")
        
        # Approach 3: Genre-based discovery (catches documentaries, foreign films)
        print("  🎬 Approach 3: Genre-based discovery")
        indie_genres = [99, 18, 10749, 53, 37]  # Documentary, Drama, Romance, Thriller, Western
        genre_movies = self.discover_by_genres(indie_genres, start_date, end_date)
        new_genre_movies = [m for m in genre_movies if str(m['id']) not in all_movies]
        all_movies.update([str(m['id']) for m in genre_movies])
        print(f"    Found {len(new_genre_movies)} additional genre films")
        
        # Approach 4: Sort by different criteria (catches overlooked films)
        print("  📊 Approach 4: Alternative sorting methods")
        sort_methods = ['release_date.desc', 'vote_average.desc', 'vote_count.desc']
        
        for sort_method in sort_methods:
            sorted_movies = self.discover_by_sort(sort_method, start_date, end_date)
            new_sorted_movies = [m for m in sorted_movies if str(m['id']) not in all_movies]
            all_movies.update([str(m['id']) for m in sorted_movies])
            if new_sorted_movies:
                print(f"    {sort_method}: Found {len(new_sorted_movies)} additional films")
        
        # Convert back to movie objects
        final_movies = []
        for movie_id in all_movies:
            # Get movie details
            movie_data = self.tmdb_get(f"/movie/{movie_id}")
            if movie_data:
                final_movies.append(movie_data)
        
        print(f"\n✅ Total unique films discovered: {len(final_movies)}")
        return final_movies
    
    def standard_discovery(self, start_date, end_date):
        """Standard TMDB discovery"""
        all_movies = []
        
        for page in range(1, 11):  # First 10 pages
            params = {
                "sort_by": "primary_release_date.desc",
                "region": "US",
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page
            }
            
            data = self.tmdb_get("/discover/movie", params)
            movies = data.get("results", [])
            all_movies.extend(movies)
            
            if not movies or page >= data.get("total_pages", 1):
                break
            
            time.sleep(0.1)
        
        return all_movies
    
    def discover_by_companies(self, company_ids, start_date, end_date):
        """Discover films by production companies"""
        all_movies = []
        
        for company_id in company_ids:
            for page in range(1, 6):  # First 5 pages per company
                params = {
                    "with_companies": str(company_id),
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "sort_by": "release_date.desc",
                    "page": page
                }
                
                data = self.tmdb_get("/discover/movie", params)
                movies = data.get("results", [])
                all_movies.extend(movies)
                
                if not movies or page >= data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        return all_movies
    
    def discover_by_genres(self, genre_ids, start_date, end_date):
        """Discover films by genres"""
        all_movies = []
        
        for genre_id in genre_ids:
            for page in range(1, 4):  # First 3 pages per genre
                params = {
                    "with_genres": str(genre_id),
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "sort_by": "release_date.desc",
                    "page": page
                }
                
                data = self.tmdb_get("/discover/movie", params)
                movies = data.get("results", [])
                all_movies.extend(movies)
                
                if not movies or page >= data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        return all_movies
    
    def discover_by_sort(self, sort_method, start_date, end_date):
        """Discover films using different sorting methods"""
        all_movies = []
        
        for page in range(1, 6):  # First 5 pages
            params = {
                "sort_by": sort_method,
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page
            }
            
            data = self.tmdb_get("/discover/movie", params)
            movies = data.get("results", [])
            all_movies.extend(movies)
            
            if not movies or page >= data.get("total_pages", 1):
                break
            
            time.sleep(0.1)
        
        return all_movies
    
    def test_missing_films(self):
        """Test if our enhanced discovery finds the previously missing films"""
        print("\n🎯 Testing enhanced discovery on known missing films...")
        
        missing_films = [
            ('Pavements', 1063307),
            ('Blue Sun Palace', 1274751)
        ]
        
        # Get their release dates
        for title, movie_id in missing_films:
            movie_data = self.tmdb_get(f"/movie/{movie_id}")
            if movie_data:
                release_date = movie_data.get('release_date')
                if release_date:
                    release_dt = datetime.strptime(release_date, '%Y-%m-%d')
                    start_test = release_dt - timedelta(days=30)
                    end_test = release_dt + timedelta(days=30)
                    
                    print(f"\n  Testing {title} around {release_date}...")
                    discovered_movies = self.discover_with_multiple_approaches(start_test, end_test)
                    
                    found = any(str(m['id']) == str(movie_id) for m in discovered_movies)
                    if found:
                        print(f"    ✅ {title} FOUND with enhanced discovery!")
                    else:
                        print(f"    ❌ {title} still not found - need more approaches")

if __name__ == "__main__":
    discovery = EnhancedDiscovery()
    discovery.test_missing_films()

# ================================================================
# FILE: ./export_for_admin.py
# ================================================================
#!/usr/bin/env python3
"""
Export movie tracking data to format expected by admin panel
"""

import json
import os
from datetime import datetime

def export_movie_data():
    """Convert movie_tracking.json to admin panel format"""
    
    # Load existing tracking database
    with open('movie_tracking.json', 'r') as f:
        tracking_db = json.load(f)
    
    # Create output directory
    os.makedirs('output', exist_ok=True)
    
    # Convert to admin panel format
    admin_data = {}
    
    for movie_id, movie in tracking_db['movies'].items():
        # Only include resolved movies (available digitally)
        if movie.get('status') == 'resolved':
            admin_data[movie_id] = {
                'title': movie['title'],
                'year': movie.get('release_date', '2025-01-01')[:4] if movie.get('release_date') else '2025',
                'director': movie.get('director', 'Unknown Director'),
                'runtime': movie.get('runtime'),
                'studio': movie.get('studio'),
                'synopsis': movie.get('synopsis'),
                'rt_score': movie.get('rt_score'),
                'rt_url': movie.get('rt_url'),
                'poster_url': movie.get('poster_url'),
                'trailer_url': movie.get('trailer_url'),
                'tmdb_id': movie.get('tmdb_id'),
                'digital_date': movie.get('digital_date'),
                'provider_list': movie.get('provider_list'),
                'streaming_info': movie.get('streaming_info'),
                'status': movie['status']
            }
    
    # Save to admin format
    with open('output/data.json', 'w') as f:
        json.dump(admin_data, f, indent=2)
    
    print(f"✓ Exported {len(admin_data)} movies to output/data.json")
    print("✓ Admin panel data ready!")
    
    # Create empty files for admin features if they don't exist
    admin_files = [
        'output/hidden_movies.json',
        'output/featured_movies.json', 
        'output/movie_reviews.json'
    ]
    
    for filepath in admin_files:
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                json.dump([], f)
            print(f"✓ Created {filepath}")

if __name__ == "__main__":
    export_movie_data()

# ================================================================
# FILE: ./find_all_indie_films.py
# ================================================================
#!/usr/bin/env python3
"""
Comprehensive indie and foreign film finder
Uses multiple search strategies to find everything
"""

import json
import requests
import time
from datetime import datetime, timedelta

class IndiFilmFinder:
    def __init__(self):
        self.api_key = "99b122ce7fa3e9065d7b7dc6e660772d"
        self.found_movies = set()
        self.new_additions = 0
        
    def load_database(self):
        with open('movie_tracking.json', 'r') as f:
            self.db = json.load(f)
        print(f"Loaded database with {len(self.db['movies'])} movies")
        
    def save_database(self):
        with open('movie_tracking.json', 'w') as f:
            json.dump(self.db, f, indent=2)
        print(f"Saved database with {len(self.db['movies'])} movies")
    
    def check_providers(self, movie_id):
        """Check if movie has any digital providers"""
        try:
            response = requests.get(
                f'https://api.themoviedb.org/3/movie/{movie_id}/watch/providers',
                params={'api_key': self.api_key}
            )
            if response.status_code == 200:
                us_providers = response.json().get('results', {}).get('US', {})
                return any([
                    us_providers.get('rent'),
                    us_providers.get('buy'),
                    us_providers.get('flatrate')
                ])
        except:
            pass
        return False
    
    def add_movie(self, movie):
        """Add movie to database if not exists"""
        movie_id = str(movie['id'])
        
        if movie_id in self.db['movies'] or movie_id in self.found_movies:
            return False
        
        # Check if it has digital availability
        time.sleep(0.3)  # Rate limit
        has_providers = self.check_providers(movie_id)
        
        if has_providers:
            print(f"  + Adding: {movie['title']} ({movie.get('release_date', 'No date')[:4]})")
            
            # Get release dates
            release_response = requests.get(
                f'https://api.themoviedb.org/3/movie/{movie_id}/release_dates',
                params={'api_key': self.api_key}
            )
            
            digital_date = None
            if release_response.status_code == 200:
                for country in release_response.json().get('results', []):
                    if country['iso_3166_1'] == 'US':
                        for release in country['release_dates']:
                            if release['type'] == 4:  # Digital
                                digital_date = release['release_date'][:10]
                                break
                            elif release['type'] == 2 and not digital_date:  # Limited theatrical
                                digital_date = release['release_date'][:10]
            
            self.db['movies'][movie_id] = {
                'title': movie['title'],
                'tmdb_id': movie_id,
                'release_date': movie.get('release_date'),
                'digital_date': digital_date,
                'has_digital': True,
                'poster_path': movie.get('poster_path'),
                'overview': movie.get('overview', '')[:200],
                'original_language': movie.get('original_language'),
                'added_date': datetime.now().isoformat(),
                'source': 'indie_finder'
            }
            
            self.found_movies.add(movie_id)
            self.new_additions += 1
            return True
        return False
    
    def search_by_company(self, company_name, company_id):
        """Search for films by production company (great for indie studios)"""
        print(f"\n🎬 Searching {company_name} films...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        params = {
            'api_key': self.api_key,
            'with_companies': company_id,
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'release_date.desc'
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        if response.status_code == 200:
            movies = response.json().get('results', [])
            for movie in movies:
                self.add_movie(movie)
    
    def search_festival_winners(self):
        """Search for festival films"""
        print("\n🏆 Searching festival and award winners...")
        
        # Search by keywords related to festivals
        festival_keywords = ['sundance', 'cannes', 'venice', 'toronto', 'sxsw', 'tribeca']
        
        for keyword in festival_keywords:
            params = {
                'api_key': self.api_key,
                'query': keyword,
                'primary_release_year': 2024
            }
            
            response = requests.get('https://api.themoviedb.org/3/search/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])
                for movie in movies:
                    self.add_movie(movie)
    
    def search_foreign_films(self):
        """Search foreign language films"""
        print("\n🌍 Searching foreign language films...")
        
        languages = ['fr', 'es', 'de', 'it', 'ja', 'ko', 'zh', 'ru', 'pt', 'hi', 'ar']
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)
        
        for lang in languages:
            params = {
                'api_key': self.api_key,
                'with_original_language': lang,
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc',
                'page': 1
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])[:10]  # Top 10 per language
                for movie in movies:
                    self.add_movie(movie)
    
    def search_limited_releases(self):
        """Search for limited theatrical releases"""
        print("\n📽️ Searching limited theatrical releases...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        params = {
            'api_key': self.api_key,
            'with_release_type': '2|1',  # Limited theatrical and premieres
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'region': 'US',
            'sort_by': 'popularity.desc'
        }
        
        for page in range(1, 4):  # First 3 pages
            params['page'] = page
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])
                for movie in movies:
                    self.add_movie(movie)
    
    def search_streaming_originals(self):
        """Search for streaming platform originals"""
        print("\n📺 Searching streaming originals...")
        
        # Platform provider IDs
        platforms = {
            '8': 'Netflix',
            '337': 'Disney Plus',
            '350': 'Apple TV+',
            '9': 'Amazon Prime',
            '384': 'HBO Max',
            '531': 'Paramount+',
            '387': 'Peacock'
        }
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        for provider_id, name in platforms.items():
            print(f"  Checking {name}...")
            params = {
                'api_key': self.api_key,
                'with_watch_providers': provider_id,
                'watch_region': 'US',
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'popularity.desc'
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            if response.status_code == 200:
                movies = response.json().get('results', [])[:5]  # Top 5 per platform
                for movie in movies:
                    self.add_movie(movie)
    
    def run_comprehensive_search(self):
        """Run all search methods"""
        print("🔍 Starting comprehensive indie/foreign film search...\n")
        
        self.load_database()
        
        # Run all search methods
        self.search_limited_releases()
        self.search_foreign_films()
        self.search_festival_winners()
        self.search_streaming_originals()
        
        # Search specific indie studios
        indie_studios = [
            ('A24', '41077'),
            ('Neon', '90733'),
            ('IFC Films', '307'),
            ('Focus Features', '10146'),
            ('Magnolia Pictures', '1030'),
            ('Bleecker Street', '19414'),
            ('Searchlight Pictures', '127928')
        ]
        
        for studio_name, studio_id in indie_studios:
            self.search_by_company(studio_name, studio_id)
        
        self.save_database()
        
        print(f"\n✅ Complete! Added {self.new_additions} new indie/foreign films")
        print(f"Total database size: {len(self.db['movies'])} movies")

if __name__ == "__main__":
    finder = IndiFilmFinder()
    finder.run_comprehensive_search()


# ================================================================
# FILE: ./fix_tracking_dates.py
# ================================================================
#!/usr/bin/env python3
"""
Fix tracking dates using better fallback logic
"""

import json
import requests
import time
from datetime import datetime, timedelta

def fix_digital_dates():
    api_key = "99b122ce7fa3e9065d7b7dc6e660772d"
    
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)
    
    print("Fixing digital dates with better logic...")
    fixed = 0
    
    for movie_id, movie in db['movies'].items():
        # Skip if manually corrected
        if movie.get('manually_corrected'):
            continue
            
        # If has providers but digital_date is today or recent
        if movie.get('has_digital'):
            digital_date = movie.get('digital_date', '')
            
            # Check if suspiciously recent (last 3 days)
            if digital_date:
                date_obj = datetime.fromisoformat(digital_date.split('T')[0])
                days_ago = (datetime.now() - date_obj).days
                
                if days_ago <= 3:
                    print(f"\nChecking {movie['title']}...")
                    
                    # Try to get better date
                    better_date = None
                    
                    # 1. Check for Type 4 date
                    response = requests.get(
                        f'https://api.themoviedb.org/3/movie/{movie_id}/release_dates',
                        params={'api_key': api_key}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        for country in data.get('results', []):
                            if country['iso_3166_1'] == 'US':
                                for release in country['release_dates']:
                                    if release['type'] == 4:
                                        better_date = release['release_date'][:10]
                                        print(f"  Found Type 4 date: {better_date}")
                                        break
                    
                    # 2. If no Type 4, use Limited Theatrical (Type 2) if it exists
                    if not better_date:
                        for country in data.get('results', []):
                            if country['iso_3166_1'] == 'US':
                                for release in country['release_dates']:
                                    if release['type'] == 2:  # Limited theatrical often = VOD
                                        better_date = release['release_date'][:10]
                                        print(f"  Using Limited Theatrical date: {better_date}")
                                        break
                    
                    # 3. If still no date, estimate from theatrical + 45 days
                    if not better_date and movie.get('release_date'):
                        theatrical = datetime.fromisoformat(movie['release_date'].split('T')[0])
                        estimated = theatrical + timedelta(days=45)
                        if estimated < datetime.now():
                            better_date = estimated.strftime('%Y-%m-%d')
                            print(f"  Estimated from theatrical + 45 days: {better_date}")
                    
                    # Apply the better date
                    if better_date and better_date != digital_date[:10]:
                        movie['digital_date'] = better_date
                        movie['date_source'] = 'estimated'
                        fixed += 1
                        print(f"  Fixed: {digital_date[:10]} → {better_date}")
                    
                    time.sleep(0.5)  # Rate limit
    
    # Save fixes
    with open('movie_tracking.json', 'w') as f:
        json.dump(db, f, indent=2)
    
    print(f"\n✅ Fixed {fixed} movie dates")
    return fixed

if __name__ == "__main__":
    fix_digital_dates()


# ================================================================
# FILE: ./generate_from_tracker.py
# ================================================================
#!/usr/bin/env python3
"""
Generate movie list from tracking database
"""

import json
import requests
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_movie_providers(movie_id, api_key):
    """Get provider availability for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    try:
        response = requests.get(url, params={'api_key': api_key})
        us_providers = response.json().get('results', {}).get('US', {})
        
        return {
            'rent': [p['provider_name'] for p in us_providers.get('rent', [])],
            'buy': [p['provider_name'] for p in us_providers.get('buy', [])],
            'stream': [p['provider_name'] for p in us_providers.get('flatrate', [])]
        }
    except Exception:
        return {'rent': [], 'buy': [], 'stream': []}

def generate_current_releases(days_back=30):
    """Generate list of currently available movies from tracking database"""
    
    # Load tracking database
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)
    
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Get movies that went digital recently
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    current_releases = []
    
    print(f"🎬 Finding movies that went digital in last {days_back} days...")
    
    for movie_id, movie_data in db['movies'].items():
        if movie_data['status'] == 'resolved' and movie_data.get('digital_date'):
            try:
                digital_date = datetime.strptime(movie_data['digital_date'], '%Y-%m-%d')
                if digital_date >= cutoff_date:
                    # Get current provider info
                    providers = get_movie_providers(int(movie_id), api_key)
                    
                    # Only include if actually has providers
                    if providers['rent'] or providers['buy'] or providers['stream']:
                        movie_data['providers'] = providers
                        current_releases.append(movie_data)
                        
                        provider_summary = []
                        if providers['rent']: provider_summary.append(f"Rent: {len(providers['rent'])}")
                        if providers['buy']: provider_summary.append(f"Buy: {len(providers['buy'])}")
                        if providers['stream']: provider_summary.append(f"Stream: {len(providers['stream'])}")
                        
                        print(f"  ✅ {movie_data['title']} - {' | '.join(provider_summary)}")
                        
            except Exception as e:
                continue
    
    # Sort by digital date (most recent first)
    current_releases.sort(key=lambda x: x['digital_date'], reverse=True)
    
    print(f"\n🎯 Found {len(current_releases)} currently available movies")
    return current_releases

def export_to_json(movies, filename='current_releases.json'):
    """Export current releases to JSON"""
    with open(filename, 'w') as f:
        json.dump(movies, f, indent=2)
    print(f"💾 Exported to {filename}")

if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    
    movies = generate_current_releases(days)
    export_to_json(movies)
    
    print(f"\n📊 SUMMARY:")
    print(f"Movies that went digital in last {days} days: {len(movies)}")
    
    if movies:
        print(f"\nTop 5 recent digital releases:")
        for movie in movies[:5]:
            days_ago = (datetime.now() - datetime.strptime(movie['digital_date'], '%Y-%m-%d')).days
            print(f"  • {movie['title']} - {days_ago} days ago")

# ================================================================
# FILE: ./generate_site.py
# ================================================================
#!/usr/bin/env python3
"""
Site generator using new VHS-style template
"""
import json
import os
import requests
import time
from datetime import datetime
from jinja2 import FileSystemLoader, Environment, Template
from collections import defaultdict

def month_name_filter(month_str):
    """Convert month number to name"""
    months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    try:
        return months[int(month_str)]
    except:
        return 'Unknown'

def create_justwatch_url(title):
    """Create direct JustWatch URL from movie title with fallback to search"""
    if not title:
        return "https://www.justwatch.com/us"
    
    # Special cases for known movie URL patterns
    special_cases = {
        'Deadpool & Wolverine': 'deadpool-3',
        'Deadpool 3': 'deadpool-3',
        'Inside Out 2': 'inside-out-2',
        'A Quiet Place: Day One': 'a-quiet-place-day-one',
        'Beetlejuice Beetlejuice': 'beetlejuice-2',
        'The Bad Guys 2': 'the-bad-guys-2',
        'Mission: Impossible - The Final Reckoning': 'mission-impossible-8',
        'Mission Impossible - The Final Reckoning': 'mission-impossible-8',
        'Mission: Impossible 8': 'mission-impossible-8',
    }
    
    if title in special_cases:
        return f"https://www.justwatch.com/us/movie/{special_cases[title]}"
    
    # Convert title to JustWatch URL slug
    slug = title.lower()
    
    # Remove common articles from beginning only
    articles = ['the ', 'a ', 'an ']
    for article in articles:
        if slug.startswith(article):
            slug = slug[len(article):]
    
    # Replace special characters and spaces
    slug = slug.replace('&', 'and')
    slug = slug.replace("'", '')
    slug = slug.replace('"', '')
    slug = slug.replace(':', '')
    slug = slug.replace('.', '')
    slug = slug.replace(',', '')
    slug = slug.replace('!', '')
    slug = slug.replace('?', '')
    slug = slug.replace('(', '')
    slug = slug.replace(')', '')
    slug = slug.replace('[', '')
    slug = slug.replace(']', '')
    slug = slug.replace('/', '')
    slug = slug.replace('\\', '')
    slug = slug.replace('#', '')
    
    # Replace spaces and multiple dashes with single dash
    slug = '-'.join(slug.split())
    slug = '-'.join(filter(None, slug.split('-')))  # Remove empty parts
    
    # If slug is too short or empty, fallback to search
    if len(slug) < 2:
        title_encoded = title.replace(' ', '+').replace('&', '%26')
        return f"https://www.justwatch.com/us/search?q={title_encoded}"
    
    return f"https://www.justwatch.com/us/movie/{slug}"

def get_tmdb_api_key():
    """Get TMDB API key from config"""
    try:
        with open('config.yaml', 'r') as f:
            import yaml
            config = yaml.safe_load(f)
            return config.get('tmdb_api_key')
    except:
        return None

def get_rt_score_direct(title, year):
    """Get RT score by scraping Rotten Tomatoes directly"""
    try:
        import urllib.parse
        # Create search URL for RT
        search_query = f"{title} {year}" if year else title
        search_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(search_query)}"
        
        # Use WebFetch to get RT page and extract score
        from tools import WebFetch  # This won't work in current context
        # For now, return None and we'll use a different approach
        return None
    except Exception as e:
        print(f"Error getting direct RT score for {title}: {e}")
    return None

def get_tmdb_movie_details(tmdb_id):
    """Get comprehensive movie details from TMDB"""
    api_key = get_tmdb_api_key()
    if not api_key:
        return {
            'poster_url': 'https://via.placeholder.com/160x240',
            'director': 'Director N/A',
            'cast': [],
            'synopsis': 'Synopsis not available.',
            'runtime': None,
            'studio': 'Studio N/A',
            'rating': 'NR',
            'trailer_url': None,
            'rt_url': None
        }
    
    # Get basic movie details
    movie_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
    credits_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits"
    videos_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos"
    
    try:
        # Fetch movie details
        movie_response = requests.get(movie_url, params={'api_key': api_key})
        credits_response = requests.get(credits_url, params={'api_key': api_key})
        videos_response = requests.get(videos_url, params={'api_key': api_key})
        
        result = {
            'poster_url': 'https://via.placeholder.com/160x240',
            'director': 'Director N/A',
            'cast': [],
            'synopsis': 'Synopsis not available.',
            'runtime': None,
            'studio': 'Studio N/A',
            'rating': 'NR',
            'trailer_url': None,
            'rt_url': None
        }
        
        if movie_response.status_code == 200:
            movie_data = movie_response.json()
            
            # Poster
            poster_path = movie_data.get('poster_path')
            if poster_path:
                result['poster_url'] = f"https://image.tmdb.org/t/p/w500{poster_path}"
            
            # Synopsis
            result['synopsis'] = movie_data.get('overview', 'Synopsis not available.')
            
            # Runtime
            runtime = movie_data.get('runtime')
            result['runtime'] = runtime if runtime else None
            
            # Studio
            production_companies = movie_data.get('production_companies', [])
            if production_companies:
                result['studio'] = production_companies[0].get('name', 'Studio N/A')
            
            # Create RT search URL using movie title and year
            title = result.get('title', '')
            year = result.get('year', '')
            if title:
                import urllib.parse
                search_query = f"{title} {year}" if year else title
                result['rt_url'] = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(search_query)}"
        
        if credits_response.status_code == 200:
            credits_data = credits_response.json()
            
            # Director
            for crew in credits_data.get('crew', []):
                if crew.get('job') == 'Director':
                    result['director'] = crew.get('name', 'Director N/A')
                    break
            
            # Cast (first 3)
            cast_list = []
            for actor in credits_data.get('cast', [])[:3]:
                name = actor.get('name')
                if name:
                    cast_list.append(name)
            result['cast'] = cast_list
        
        if videos_response.status_code == 200:
            videos_data = videos_response.json()
            
            # Find official trailer
            for video in videos_data.get('results', []):
                if (video.get('type') == 'Trailer' and 
                    video.get('site') == 'YouTube' and 
                    video.get('official', False)):
                    result['trailer_url'] = f"https://www.youtube.com/watch?v={video['key']}"
                    break
            
            # If no official trailer, take the first trailer
            if not result['trailer_url']:
                for video in videos_data.get('results', []):
                    if video.get('type') == 'Trailer' and video.get('site') == 'YouTube':
                        result['trailer_url'] = f"https://www.youtube.com/watch?v={video['key']}"
                        break
        
        return result
        
    except Exception:
        return {
            'poster_url': 'https://via.placeholder.com/160x240',
            'director': 'Director N/A',
            'cast': [],
            'synopsis': 'Synopsis not available.',
            'runtime': None,
            'studio': 'Studio N/A',
            'rating': 'NR',
            'trailer_url': None,
            'rt_url': None
        }

def render_site_enhanced(items, site_title, window_label, region, store_names):
    """Render site with flip cards and date dividers."""
    
    # Group movies by date
    movies_by_date = defaultdict(list)
    for item in items:
        date = item.get('digital_date', '')[:10]
        if date:
            movies_by_date[date].append(item)
    
    # Sort dates descending (newest first)
    sorted_dates = sorted(movies_by_date.keys(), reverse=True)
    
    # Prepare data for template
    template_data = []
    for date_str in sorted_dates:
        # Parse date for display
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        date_info = {
            'month_short': date_obj.strftime('%b').upper(),
            'day': date_obj.strftime('%d').lstrip('0'),
            'year': date_obj.strftime('%Y')
        }
        template_data.append((date_info, movies_by_date[date_str]))
    
    # Load and render template
    tpl_path = os.path.join("templates", "site_enhanced.html")
    with open(tpl_path, "r", encoding="utf-8") as f:
        tpl = Template(f.read())
    
    html = tpl.render(
        site_title=site_title,
        window_label=window_label,
        region=region,
        store_names=store_names,
        movies_by_date=template_data,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    # Write output
    out_dir = os.path.join("output", "site")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

def generate_site():
    """Generate the VHS-style website"""
    
    # Load movie data from current releases (recent movies only)
    try:
        with open('current_releases.json', 'r') as f:
            movies = json.load(f)
    except FileNotFoundError:
        # Fallback to output/data.json if current_releases.json doesn't exist
        with open('output/data.json', 'r') as f:
            movies = json.load(f)
    
    # Load RT scores from main tracking database
    rt_scores = {}
    try:
        with open('movie_tracking.json', 'r') as f:
            tracking_db = json.load(f)
            for movie_id, movie_data in tracking_db.get('movies', {}).items():
                if movie_data.get('rt_score'):
                    rt_scores[movie_id] = movie_data['rt_score']
    except:
        pass
    
    print(f"Loaded {len(movies)} movies with {len(rt_scores)} RT scores")
    
    # Transform tracking data for new template
    items = []
    # Handle both list and dictionary formats
    if isinstance(movies, dict):
        movie_list = list(movies.values())
    else:
        movie_list = movies
    
    for movie in movie_list:
        # Extract year from digital_date if available
        year = '2025'
        if movie.get('digital_date'):
            year = movie['digital_date'][:4]
        elif movie.get('theatrical_date'):
            year = movie['theatrical_date'][:4]
        
        # Get comprehensive movie details from TMDB
        tmdb_details = get_tmdb_movie_details(movie.get('tmdb_id')) if movie.get('tmdb_id') else {}
        
        # Get direct trailer URL from TMDB API
        trailer_url = tmdb_details.get('trailer_url') if tmdb_details else None
        if not trailer_url and movie.get('tmdb_id'):
            # Fallback to search if no direct trailer found
            trailer_url = f"https://www.youtube.com/results?search_query={movie.get('title', '')}+{year}+trailer"
        
        # Create direct JustWatch link
        watch_link = create_justwatch_url(movie.get('title', ''))
        
        # Only show watch link if there are actual providers
        providers = movie.get('providers', {})
        has_providers = bool(providers.get('rent') or providers.get('buy') or providers.get('stream'))
        if not has_providers:
            watch_link = '#'
        
        # Combine all providers for display
        all_providers = []
        if providers.get('stream'):
            all_providers.extend(providers['stream'])
        if providers.get('rent'):
            all_providers.extend(providers['rent'])
        if providers.get('buy'):
            all_providers.extend(providers['buy'])
        
        # Try to get RT score from multiple sources
        rt_score = None
        movie_id = str(movie.get('tmdb_id', ''))
        if movie_id in rt_scores:
            rt_score = rt_scores[movie_id]
        elif movie.get('rt_score'):
            rt_score = movie['rt_score']
        elif movie.get('review_data') and isinstance(movie['review_data'], dict):
            rt_score = movie['review_data'].get('rt_score')
        # else:
        #     # Fetch RT score directly if not in database (disabled for now)
        #     try:
        #         from rt_score_fetcher import get_rt_score_with_fallbacks
        #         rt_score = get_rt_score_with_fallbacks(movie.get('title', ''), year)
        #         if rt_score:
        #             print(f"  🍅 Fetched RT score for {movie.get('title', '')}: {rt_score}%")
        #         time.sleep(0.5)  # Rate limiting
        #     except Exception as e:
        #         print(f"  ❌ Failed to fetch RT score for {movie.get('title', '')}: {e}")
        #         rt_score = None
        
        item = {
            'title': movie.get('title', 'Unknown'),
            'year': year,
            'poster_url': tmdb_details.get('poster_url', 'https://via.placeholder.com/160x240'),
            'director': tmdb_details.get('director', 'Director N/A'),
            'cast': tmdb_details.get('cast', []),
            'synopsis': tmdb_details.get('synopsis', 'Synopsis not available.'),
            'digital_date': movie.get('digital_date', '').split('T')[0] if movie.get('digital_date') else '',
            'trailer_url': trailer_url,
            'rt_url': tmdb_details.get('rt_url'),
            'watch_link': watch_link,
            'rt_score': rt_score,
            'runtime': tmdb_details.get('runtime'),
            'studio': tmdb_details.get('studio', 'Studio N/A'),
            'rating': tmdb_details.get('rating', 'NR'),
            'providers': all_providers[:3]  # Show first 3 platforms
        }
        items.append(item)
    
    # Sort by digital date
    items.sort(key=lambda x: x['digital_date'] if x['digital_date'] else '9999-12-31')
    
    # Use enhanced rendering with flip cards and date dividers
    render_site_enhanced(
        items=items,
        site_title="New Release Wall",
        window_label="Digital Releases",
        region="US",
        store_names=["iTunes", "Vudu", "Amazon", "Google Play"]
    )
    
    print("✓ Generated output/site/index.html with enhanced flip cards and date dividers")

if __name__ == '__main__':
    generate_site()

# ================================================================
# FILE: ./generate_substack.py
# ================================================================
import json
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def generate_substack_newsletter():
    """Generate a Substack-ready newsletter from the latest data"""
    
    # Load the latest movie data (we'll use the HTML as source of truth)
    try:
        with open('output/site/index.html', 'r') as f:
            html_content = f.read()
            # Extract movie count from HTML
            import re
            movie_count = len(re.findall(r'class="card"', html_content))
    except:
        movie_count = 0
    
    # Create the newsletter
    today = datetime.now()
    week_start = (today - timedelta(days=7)).strftime("%B %d")
    week_end = today.strftime("%B %d, %Y")
    
    newsletter = f"""# 🎬 New Release Wall: {week_start} - {week_end}

*Your weekly guide to what's actually new on streaming*

---

## 📊 This Week at a Glance

**{movie_count} new digital releases** hit streaming platforms this week. Here's what's worth your time:

### 🏆 Critics' Picks
Films with 70%+ on Rotten Tomatoes or Metacritic

[PLACEHOLDER - Add 3-5 top reviewed films here]

### 🔥 Trending Now  
What everyone's watching

[PLACEHOLDER - Add 3-5 most popular films here]

### 💎 Hidden Gems
Under-the-radar releases worth discovering

[PLACEHOLDER - Add 2-3 interesting lesser-known films here]

---

## 🎯 Quick Picks by Mood

**Date Night:** [Film Title] - [One line description]
**Family Fun:** [Film Title] - [One line description]  
**Thrill Seeker:** [Film Title] - [One line description]
**Arthouse:** [Film Title] - [One line description]

---

## 📺 By Platform

### Netflix
- Film 1
- Film 2
- Film 3

### Amazon Prime Video
- Film 1
- Film 2

### Apple TV+
- Film 1
- Film 2

### Disney+/Hulu
- Film 1
- Film 2

---

## 🌍 International Corner

This week's best non-English releases:

1. **[Film Title]** (Country) - [Platform]
   *[One sentence description]*

2. **[Film Title]** (Country) - [Platform]
   *[One sentence description]*

---

## 📈 The Numbers

- **Total New Releases:** {movie_count}
- **With Critical Reviews:** [X]
- **Netflix Exclusives:** [X]
- **Foreign Language:** [X]
- **Documentary:** [X]

---

## 🔮 Coming Next Week

Get ready for:
- [Major upcoming release 1]
- [Major upcoming release 2]

---

*How was this week's selection? Reply and let me know what you watched!*

**[View the full New Release Wall →](https://hadrianbelove-stack.github.io/new-release-wall/)**

---

*You're receiving this because you subscribed to New Release Wall. [Unsubscribe]()*
"""
    
    # Save the newsletter
    with open('output/newsletter.md', 'w') as f:
        f.write(newsletter)
    
    # Also create a simplified list version
    simple_list = f"""# New Releases: {week_start} - {week_end}

## All {movie_count} Releases This Week

### With Reviews
- Film Title (RT: X%) - Netflix, Prime
- Film Title (RT: X%) - Apple TV+

### New to Streaming  
- Film Title - Netflix
- Film Title - Prime Video
- Film Title - Hulu

### International
- Film Title (Country) - Platform
- Film Title (Country) - Platform

---
[View Visual Wall](https://hadrianbelove-stack.github.io/new-release-wall/)
"""
    
    with open('output/simple_list.md', 'w') as f:
        f.write(simple_list)
    
    print(f"✓ Generated Substack newsletter: output/newsletter.md")
    print(f"✓ Generated simple list: output/simple_list.md")
    print(f"\nNewsletter includes {movie_count} movies from the past week")
    print("\nNext steps:")
    print("1. Open output/newsletter.md")
    print("2. Fill in the [PLACEHOLDER] sections with actual movies")
    print("3. Copy & paste into Substack")

if __name__ == "__main__":
    generate_substack_newsletter()


# ================================================================
# FILE: ./hybrid_site_restore.py
# ================================================================
#!/usr/bin/env python3
"""
Hybrid approach: Use current_releases.json for full movie list + transfer RT scores from data.json
"""
import json
import urllib.parse
import requests
import yaml
import time
from jinja2 import Template
from collections import defaultdict
from datetime import datetime

def get_tmdb_poster(tmdb_id):
    """Get poster URL from TMDB"""
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        api_key = config.get('tmdb_api_key')
        
        if not api_key or not tmdb_id:
            return 'https://via.placeholder.com/160x240'
            
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        response = requests.get(url, params={'api_key': api_key})
        
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"
        
        return 'https://via.placeholder.com/160x240'
    except:
        return 'https://via.placeholder.com/160x240'

def hybrid_restore():
    """Restore full site using current_releases.json + RT scores from output/data.json"""
    
    # Load full movie list
    with open('current_releases.json', 'r') as f:
        current_movies = json.load(f)
    
    # Load RT scores from our previous work
    with open('output/data.json', 'r') as f:
        rt_data = json.load(f)
    
    # Create RT score lookup by title (case-insensitive)
    rt_by_title = {}
    for movie_id, movie in rt_data.items():
        if movie.get('rt_score'):
            title = movie.get('title', '').lower().strip()
            if title:
                rt_by_title[title] = movie['rt_score']
    
    print(f"Processing {len(current_movies)} movies with {len(rt_by_title)} RT scores available...")
    print(f"RT scores available for: {list(rt_by_title.keys())}")
    
    # Find movies with RT scores
    movies_with_rt = []
    for movie in current_movies:
        title = movie.get('title', '').lower().strip()
        if title in rt_by_title:
            movies_with_rt.append(movie)
            print(f"✅ Found RT score for: {movie.get('title')} = {rt_by_title[title]}%")
    
    # Get posters for movies with RT scores (limited batch)
    priority_movies = movies_with_rt[:10]  # Limit to avoid timeout
    print(f"Fetching posters for {len(priority_movies)} priority movies...")
    
    items = []
    
    # Process all movies
    for i, movie in enumerate(current_movies):
        title = movie.get('title', 'Unknown')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2025'
        
        # Get RT score by title match
        rt_score = rt_by_title.get(title.lower().strip())
        
        # Get poster (only for priority movies)
        if movie in priority_movies and i < 10:
            print(f"  {i+1}/10: Fetching poster for {title}")
            poster_url = get_tmdb_poster(movie.get('tmdb_id'))
            time.sleep(0.1)
        else:
            poster_url = movie.get('poster_url', 'https://via.placeholder.com/160x240')
            if not poster_url or poster_url == 'null':
                poster_url = 'https://via.placeholder.com/160x240'
        
        # Create URLs
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        watch_link = f"https://www.justwatch.com/us/search?q={urllib.parse.quote(title)}"
        
        item = {
            'title': title,
            'year': year,
            'poster_url': poster_url,
            'director': movie.get('director', 'Director N/A'),
            'cast': movie.get('cast', []),
            'synopsis': movie.get('synopsis', 'Synopsis not available.'),
            'digital_date': movie.get('digital_date', ''),
            'trailer_url': movie.get('trailer_url'),
            'rt_url': rt_url,
            'watch_link': watch_link,
            'rt_score': rt_score,
            'runtime': movie.get('runtime'),
            'studio': movie.get('studio', 'Studio N/A'),
            'rating': movie.get('rating', 'NR'),
            'providers': []
        }
        items.append(item)
    
    # Group by date and render
    grouped = defaultdict(list)
    for item in items:
        date = item['digital_date'][:10] if item['digital_date'] else '2025-08-21'
        grouped[date].append(item)
    
    # Sort dates and create template data
    sorted_dates = sorted(grouped.keys(), reverse=True)
    template_data = []
    for date_str in sorted_dates:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_info = {
                'month_short': date_obj.strftime('%b').upper(),
                'day': date_obj.strftime('%d').lstrip('0'),
                'year': date_obj.strftime('%Y')
            }
        except:
            date_info = {
                'month_short': 'AUG',
                'day': '21', 
                'year': '2025'
            }
        template_data.append((date_info, grouped[date_str]))
    
    # Render template
    with open('templates/site_enhanced.html', 'r') as f:
        template = Template(f.read())
    
    html = template.render(
        movies_by_date=template_data,
        site_title="New Release Wall",
        window_label="Digital Releases",
        region="US",
        store_names=["iTunes", "Vudu", "Amazon", "Google Play"],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    # Save
    with open('output/site/index.html', 'w') as f:
        f.write(html)
    
    # Stats
    rt_count = sum(1 for item in items if item['rt_score'])
    poster_count = sum(1 for item in items if 'image.tmdb.org' in item['poster_url'])
    
    print(f"✅ Hybrid restore complete: {len(items)} movies")
    print(f"📊 {rt_count} movies have RT scores")
    print(f"🖼️ {poster_count} movies have real posters")

if __name__ == '__main__':
    hybrid_restore()

# ================================================================
# FILE: ./justwatch_collector.py
# ================================================================
#!/usr/bin/env python3
"""
JustWatch Integration for Movie Tracker
Collects streaming availability and pricing data from JustWatch
"""

import json
import re
import time
from urllib.parse import quote

class JustWatchCollector:
    def __init__(self):
        pass
    
    def get_justwatch_url_candidates(self, title, year=None):
        """Generate possible JustWatch URLs for a movie"""
        # Clean title for URL
        title_slug = re.sub(r'[^\w\s-]', '', title.lower())
        title_slug = re.sub(r'[-\s]+', '-', title_slug)
        
        candidates = []
        if year:
            candidates.extend([
                f"https://www.justwatch.com/us/movie/{title_slug}-{year}",
                f"https://www.justwatch.com/us/movie/{title_slug}-{int(year)+1}",  # Sometimes release year differs
                f"https://www.justwatch.com/us/movie/{title_slug}-{int(year)-1}",
            ])
        
        candidates.extend([
            f"https://www.justwatch.com/us/movie/{title_slug}",
            f"https://www.justwatch.com/us/movie/{title_slug.replace('-', '_')}",
        ])
        
        return candidates
    
    def search_justwatch(self, title, year=None):
        """Search for movie on JustWatch using web search"""
        try:
            # Try web search first
            search_query = f'site:justwatch.com "{title}"'
            if year:
                search_query += f" {year}"
            
            return search_query
        except Exception as e:
            print(f"Error searching JustWatch for {title}: {e}")
            return None
    
    def load_movies_needing_streaming_data(self):
        """Load movies from database that need streaming data"""
        try:
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
            
            movies_needing_data = []
            for movie_id, movie in db['movies'].items():
                if not movie.get('streaming_info') and movie['status'] == 'resolved':
                    # Only check resolved movies (available digitally)
                    year = None
                    if movie.get('release_date'):
                        year = movie['release_date'][:4]
                    
                    movies_needing_data.append({
                        'id': movie_id,
                        'title': movie['title'],
                        'year': year
                    })
            
            return movies_needing_data
        except Exception as e:
            print(f"Error loading movies: {e}")
            return []
    
    def update_movie_streaming_info(self, movie_id, streaming_info):
        """Update movie with streaming information"""
        try:
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)
            
            if movie_id in db['movies']:
                db['movies'][movie_id]['streaming_info'] = streaming_info
                db['movies'][movie_id]['streaming_updated'] = time.strftime('%Y-%m-%d')
                
                with open('movie_tracking.json', 'w') as f:
                    json.dump(db, f, indent=2)
                
                return True
        except Exception as e:
            print(f"Error updating streaming info: {e}")
            return False

def main():
    """Test the JustWatch collector"""
    collector = JustWatchCollector()
    
    # Test with a few known movies
    test_movies = [
        ("Weapons", 2025),
        ("The Pickup", 2025),
        ("Hostile Takeover", 2025)
    ]
    
    for title, year in test_movies:
        print(f"\n🔍 Testing JustWatch search for: {title} ({year})")
        
        # Generate URL candidates
        urls = collector.get_justwatch_url_candidates(title, year)
        print(f"JustWatch URL candidates:")
        for url in urls[:3]:  # Show first 3
            print(f"  - {url}")
        
        # Generate search query
        search_query = collector.search_justwatch(title, year)
        print(f"Web search query: {search_query}")

if __name__ == "__main__":
    main()

# ================================================================
# FILE: ./movie_tracker.py
# ================================================================
#!/usr/bin/env python3
"""
Enhanced Movie Tracker that captures:
- Type 1 (Premiere/Festival)
- Type 2 (Limited Theatrical)  
- Type 3 (Wide Theatrical)
- Type 4 (Digital)
- Direct-to-streaming releases
"""

import json
import os
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yaml

class EnhancedMovieTracker:
    """Enhanced tracker that captures all release types"""
    
    RELEASE_TYPES = {
        1: "Premiere",
        2: "Theatrical (limited)",
        3: "Theatrical",
        4: "Digital",
        5: "Physical",
        6: "TV"
    }
    
    def __init__(self, db_file="movie_tracking_enhanced.json"):
        self.db_file = db_file
        self.db = self.load_database()
        
        # Load API keys
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        self.tmdb_key = config.get("tmdb_api_key", "99b122ce7fa3e9065d7b7dc6e660772d")
        self.omdb_key = config.get("omdb_api_key", "539723d9")
        
    def load_database(self) -> Dict:
        """Load or create tracking database"""
        if os.path.exists(self.db_file):
            with open(self.db_file, "r") as f:
                return json.load(f)
        return {
            "movies": {},
            "last_update": None,
            "last_check": None,
            "last_bootstrap": None
        }
    
    def save_database(self):
        """Save tracking database"""
        with open(self.db_file, "w") as f:
            json.dump(self.db, f, indent=2)
        print(f"✓ Database saved to {self.db_file}")
    
    def tmdb_get(self, path, params=None):
        """Make TMDB API request"""
        url = f"https://api.themoviedb.org/3{path}"
        params = params or {}
        params["api_key"] = self.tmdb_key
        
        try:
            response = requests.get(url, params=params, timeout=10)
            time.sleep(0.5)  # Rate limiting
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"  Error: {e}")
        return None
    
    def get_enhanced_release_info(self, movie_id):
        """
        Get comprehensive release info including premieres and limited releases
        Returns earliest primary date globally and digital availability
        """
        data = self.tmdb_get(f"/movie/{movie_id}/release_dates")
        if not data:
            return {}
        
        result = {
            'primary_date': None,  # Earliest premiere/limited/theatrical anywhere
            'digital_date': None,
            'has_digital': False,
            'release_types': [],
            'us_releases': {}
        }
        
        earliest_primary = None
        digital_dates = []
        
        # Process all countries
        for country in data.get('results', []):
            country_code = country['iso_3166_1']
            
            for release in country.get('release_dates', []):
                release_type = release.get('type')
                release_date = release.get('release_date', '')[:10]
                
                if not release_date:
                    continue
                
                # Track all release types
                if release_type not in result['release_types']:
                    result['release_types'].append(release_type)
                
                # Find earliest primary release (Types 1, 2, 3)
                if release_type in [1, 2, 3]:
                    if not earliest_primary or release_date < earliest_primary:
                        earliest_primary = release_date
                
                # Collect all digital releases
                if release_type == 4:
                    digital_dates.append(release_date)
                
                # Track US releases specifically
                if country_code == 'US':
                    type_name = self.RELEASE_TYPES.get(release_type, f"Type {release_type}")
                    result['us_releases'][type_name] = release_date
        
        # Set results
        result['primary_date'] = earliest_primary
        if digital_dates:
            result['digital_date'] = min(digital_dates)
            result['has_digital'] = True
        
        return result
    
    def check_streaming_providers(self, movie_id):
        """
        Check if movie has streaming/rental providers even without Type 4 flag
        This catches movies that are available but not properly flagged
        """
        data = self.tmdb_get(f"/movie/{movie_id}/watch/providers")
        if not data:
            return False, []
        
        providers = []
        us_data = data.get('results', {}).get('US', {})
        
        # Check all provider types
        for provider_type in ['flatrate', 'rent', 'buy']:
            if provider_type in us_data:
                for provider in us_data[provider_type]:
                    providers.append({
                        'name': provider.get('provider_name'),
                        'type': provider_type
                    })
        
        # If movie has ANY providers, it's digitally available
        return len(providers) > 0, providers
    
    def should_track_movie(self, movie):
        """
        Determine if a movie should be tracked
        Now includes direct-to-streaming and festival releases
        """
        # Get release info
        movie_id = str(movie['id'])
        release_info = self.get_enhanced_release_info(movie_id)
        
        # Track if it has ANY primary release (premiere, limited, or theatrical)
        if release_info.get('primary_date'):
            return True
        
        # Also track if it has providers (direct-to-streaming)
        has_providers, _ = self.check_streaming_providers(movie_id)
        if has_providers:
            return True
        
        # Track if release date exists (catch-all)
        if movie.get('release_date'):
            return True
        
        return False
    
    def process_movie(self, movie):
        """Process a movie with enhanced tracking"""
        movie_id = str(movie['id'])
        
        # Get comprehensive release info
        release_info = self.get_enhanced_release_info(movie_id)
        has_providers, providers = self.check_streaming_providers(movie_id)
        
        # Determine if digitally available (Type 4 OR has providers)
        is_digital = release_info.get('has_digital', False) or has_providers
        
        # Use earliest date as primary
        primary_date = release_info.get('primary_date') or movie.get('release_date')
        
        movie_data = {
            "title": movie.get("title"),
            "tmdb_id": movie_id,
            "primary_date": primary_date,
            "release_date": movie.get("release_date"),
            "digital_date": release_info.get('digital_date'),
            "has_digital": is_digital,
            "providers": providers,
            "release_types": release_info.get('release_types', []),
            "us_releases": release_info.get('us_releases', {}),
            "tracking": not is_digital,
            "first_seen": datetime.now().isoformat(),
            "last_checked": datetime.now().isoformat(),
            "poster_path": movie.get("poster_path"),
            "overview": movie.get("overview", "")[:200]
        }
        
        # Status for logging
        if is_digital:
            status = "✓ Digital"
        elif 1 in release_info.get('release_types', []):
            status = "🎬 Festival"
        elif 2 in release_info.get('release_types', []):
            status = "🎭 Limited"
        else:
            status = "⏳ Tracking"
        
        print(f"  {status}: {movie.get('title')} ({primary_date or 'No date'})")
        
        return movie_data
    
    def enhanced_bootstrap(self, days_back=730, include_upcoming=True):
        """
        Enhanced bootstrap that captures more movies
        - Includes all release types
        - Searches upcoming movies too
        - Checks direct-to-streaming
        """
        print(f"🚀 Enhanced Bootstrap: Scanning {days_back} days of releases...")
        
        end_date = datetime.now() + timedelta(days=30) if include_upcoming else datetime.now()
        start_date = end_date - timedelta(days=days_back + 30)
        
        all_movies = {}
        page = 1
        total_pages = 999
        
        while page <= min(total_pages, 100):  # Limit for testing
            print(f"  Page {page}/{min(total_pages, 100)}...")
            
            # Search with broader criteria
            params = {
                "sort_by": "popularity.desc",
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page,
                "include_adult": False
            }
            
            data = self.tmdb_get("/discover/movie", params)
            if not data:
                break
            
            movies = data.get('results', [])
            if not movies:
                break
            
            # Process each movie
            for movie in movies:
                if self.should_track_movie(movie):
                    movie_id = str(movie['id'])
                    if movie_id not in all_movies and movie_id not in self.db["movies"]:
                        movie_data = self.process_movie(movie)
                        all_movies[movie_id] = movie_data
            
            total_pages = min(data.get('total_pages', 1), 500)
            page += 1
            
            # Save periodically
            if page % 10 == 0:
                self.db["movies"].update(all_movies)
                self.save_database()
                all_movies = {}
        
        # Final save
        self.db["movies"].update(all_movies)
        self.db["last_bootstrap"] = datetime.now().isoformat()
        self.save_database()
        
        # Summary
        total = len(self.db["movies"])
        digital = sum(1 for m in self.db["movies"].values() if m.get("has_digital"))
        festival = sum(1 for m in self.db["movies"].values() if 1 in m.get("release_types", []))
        limited = sum(1 for m in self.db["movies"].values() if 2 in m.get("release_types", []))
        
        print(f"\n✅ Enhanced Bootstrap Complete!")
        print(f"  Total movies: {total}")
        print(f"  Digital available: {digital}")
        print(f"  Festival releases: {festival}")
        print(f"  Limited theatrical: {limited}")
    
    def find_missing_titles(self):
        """Check for specific missing titles like Harvest and Familiar Touch"""
        print("\n🔍 Checking for known missing titles...")
        
        missing_titles = [
            ("Harvest", 2024),
            ("Familiar Touch", 2024),
            ("Familiar Touch", 2025)
        ]
        
        for title, year in missing_titles:
            # Search TMDB
            params = {"query": title, "year": year}
            data = self.tmdb_get("/search/movie", params)
            
            if data and data.get('results'):
                movie = data['results'][0]
                movie_id = str(movie['id'])
                
                if movie_id in self.db["movies"]:
                    status = "✓ In database"
                    if self.db["movies"][movie_id].get("has_digital"):
                        status += " (Digital)"
                else:
                    # Add to database
                    movie_data = self.process_movie(movie)
                    self.db["movies"][movie_id] = movie_data
                    status = "➕ Added to database"
                
                print(f"  {title} ({year}): {status}")
            else:
                print(f"  {title} ({year}): ❌ Not found in TMDB")
        
        self.save_database()

def run_full_update():
    """Function to run full automated update"""
    from colorama import init, Fore
    init()
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    NC = Fore.RESET
    
    print(f"{GREEN}🎬 Running full update...{NC}")
    
    tracker = EnhancedMovieTracker()
    
    # First, update tracking database automatically
    print(f"{YELLOW}Updating tracking database...{NC}")
    tracker.enhanced_bootstrap(days_back=30)  # Look back 30 days
    
    # Check for new digital releases from tracking
    print(f"{YELLOW}Checking for new digital releases...{NC}")
    tracker.find_missing_titles()
    
    # Generate from tracker (last 14 days default)
    print(f"{YELLOW}Generating current releases...{NC}")
    os.system("python3 generate_from_tracker.py 14")
    
    print(f"{GREEN}✓ Full update complete{NC}")

def main():
    """CLI interface"""
    import sys
    
    tracker = EnhancedMovieTracker()
    
    if len(sys.argv) < 2:
        print("Usage: python movie_tracker.py [bootstrap|check-missing|status|update|check|daily]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "bootstrap":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 730
        tracker.enhanced_bootstrap(days)
        tracker.find_missing_titles()
    
    elif command == "check-missing":
        tracker.find_missing_titles()
    
    elif command == "status":
        total = len(tracker.db["movies"])
        digital = sum(1 for m in tracker.db["movies"].values() if m.get("has_digital"))
        print(f"\n📊 Enhanced Database Status:")
        print(f"  Total movies: {total}")
        print(f"  Digital available: {digital}")
        print(f"  Database file: {tracker.db_file}")
    
    elif command in ["update", "check", "daily"]:
        run_full_update()

if __name__ == "__main__":
    main()

# ================================================================
# FILE: ./movie_tracker_basic_backup.py
# ================================================================
#!/usr/bin/env python3
"""
Movie Digital Release Tracker
Maintains a database of movies and tracks when they go digital
"""

import json
import requests
import yaml
from datetime import datetime, timedelta
import time
import os

class MovieTracker:
    def __init__(self, db_file='movie_tracking.json'):
        self.db_file = db_file
        self.db = self.load_database()
        self.config = self.load_config()
        self.api_key = self.config['tmdb_api_key']
        self.omdb_api_key = self.config.get('omdb_api_key')
    
    def load_config(self):
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    
    def load_database(self):
        """Load existing tracking database or create new one"""
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r') as f:
                return json.load(f)
        return {
            'movies': {},
            'last_update': None,
            'stats': {
                'total_tracked': 0,
                'resolved': 0,
                'still_tracking': 0
            }
        }
    
    def save_database(self):
        """Save tracking database to disk"""
        self.db['last_update'] = datetime.now().isoformat()
        
        # Update stats
        movies = self.db['movies']
        self.db['stats'] = {
            'total_tracked': len(movies),
            'resolved': len([m for m in movies.values() if m.get('status') == 'resolved']),
            'still_tracking': len([m for m in movies.values() if m.get('status') == 'tracking'])
        }
        
        with open(self.db_file, 'w') as f:
            json.dump(self.db, f, indent=2)
        
        print(f"💾 Database saved: {self.db['stats']}")
    
    def tmdb_get(self, endpoint, params):
        """Generic TMDB API GET request"""
        url = f"https://api.themoviedb.org/3{endpoint}"
        params['api_key'] = self.api_key
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API error: {e}")
            return {}
    
    def get_release_info(self, movie_id):
        """Get release dates for a movie - enhanced to include premieres and limited releases"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            result = {
                'theatrical_date': None,  # Now represents earliest primary release (premiere/limited/theatrical)
                'digital_date': None,
                'has_digital': False
            }
            
            # Track earliest dates globally for primary releases
            earliest_primary_date = None
            us_digital_date = None
            
            if 'results' in data:
                # First pass: Find earliest primary release date anywhere (Types 1, 2, 3)
                for country_data in data['results']:
                    for release in country_data.get('release_dates', []):
                        release_type = release.get('type')
                        date = release.get('release_date', '')[:10]
                        
                        if date and release_type in [1, 2, 3]:  # Premiere, Limited, Theatrical
                            if not earliest_primary_date or date < earliest_primary_date:
                                earliest_primary_date = date
                
                # Second pass: Find US digital release (Type 4)
                for country_data in data['results']:
                    if country_data['iso_3166_1'] == 'US':
                        for release in country_data.get('release_dates', []):
                            release_type = release.get('type')
                            date = release.get('release_date', '')[:10]
                            
                            if release_type == 4:  # Digital
                                if not us_digital_date or date < us_digital_date:
                                    us_digital_date = date
                        break
                
                # If no US digital, check other countries as fallback
                if not us_digital_date:
                    for country_data in data['results']:
                        for release in country_data.get('release_dates', []):
                            release_type = release.get('type')
                            date = release.get('release_date', '')[:10]
                            
                            if release_type == 4:  # Digital
                                if not us_digital_date or date < us_digital_date:
                                    us_digital_date = date
            
            # Set results
            result['theatrical_date'] = earliest_primary_date
            result['digital_date'] = us_digital_date
            result['has_digital'] = bool(us_digital_date)
            
            return result
        except Exception as e:
            print(f"Error getting release info for {movie_id}: {e}")
            return None
    
    def get_rt_score_direct(self, title, year):
        """Get RT score by searching RT directly via web fetch"""
        try:
            import urllib.parse
            # Create search URL for RT
            search_query = f"{title} {year}" if year else title
            search_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(search_query)}"
            
            # Use WebFetch to get RT scores
            # This is a placeholder - would need WebFetch tool access
            return None
        except Exception as e:
            print(f"Error getting direct RT score for {title}: {e}")
        return None

    def get_omdb_rt_score(self, title, year):
        """Get Rotten Tomatoes score from OMDb API with direct RT fallback"""
        # First try OMDb API
        if self.omdb_api_key:
            try:
                params = {'apikey': self.omdb_api_key, 't': title}
                if year:
                    params['y'] = str(year)
                    
                response = requests.get('http://www.omdbapi.com/', params=params)
                data = response.json()
                
                if data.get('Response') == 'True':
                    for rating in data.get('Ratings', []):
                        if rating['Source'] == 'Rotten Tomatoes':
                            return int(rating['Value'].rstrip('%'))
            except Exception as e:
                print(f"Error getting OMDb RT score for {title}: {e}")
        
        # If OMDb fails, try direct RT lookup (future enhancement)
        # return self.get_rt_score_direct(title, year)
        return None
    
    def bootstrap_database(self, days_back=730):
        """Bootstrap database with movies from past N days"""
        print(f"🚀 Bootstrapping database with movies from last {days_back} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        all_movies = []
        page = 1
        total_pages = 999  # Will be updated from API response
        
        # Standard discovery
        while page <= total_pages:
            print(f"  Scanning page {page} (standard discovery)...")
            
            params = {
                "sort_by": "primary_release_date.desc",
                "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                "page": page
            }
            
            data = self.tmdb_get("/discover/movie", params)
            all_movies.extend(data.get("results", []))
            
            # Update total_pages from API
            total_pages = min(data.get("total_pages", 1), 500)  # TMDB caps at 500
            
            if page >= total_pages:
                break
                
            page += 1
            time.sleep(0.2)
        
        # Enhanced discovery for indie films (no popularity filtering)
        print(f"  Enhanced discovery for indie films...")
        
        # Discover by indie production companies
        indie_companies = [41077, 2, 491, 25, 61, 11072, 7505]  # A24, Neon, Focus, IFC, etc.
        for company_id in indie_companies:
            for comp_page in range(1, 3):  # First 2 pages per company
                params = {
                    "with_companies": str(company_id),
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "sort_by": "release_date.desc",
                    "page": comp_page
                }
                
                comp_data = self.tmdb_get("/discover/movie", params)
                comp_movies = comp_data.get("results", [])
                
                # Filter out duplicates
                existing_ids = {str(m['id']) for m in all_movies}
                new_movies = [m for m in comp_movies if str(m['id']) not in existing_ids]
                all_movies.extend(new_movies)
                
                if new_movies:
                    print(f"    Company {company_id}: +{len(new_movies)} indie films")
                
                if not comp_movies or comp_page >= comp_data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        # Discover by alternative sorting (catches low-popularity films)
        for sort_method in ["vote_average.desc", "vote_count.asc"]:
            for sort_page in range(1, 3):
                params = {
                    "sort_by": sort_method,
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "page": sort_page
                }
                
                sort_data = self.tmdb_get("/discover/movie", params)
                sort_movies = sort_data.get("results", [])
                
                # Filter out duplicates
                existing_ids = {str(m['id']) for m in all_movies}
                new_movies = [m for m in sort_movies if str(m['id']) not in existing_ids]
                all_movies.extend(new_movies)
                
                if new_movies:
                    print(f"    {sort_method}: +{len(new_movies)} additional films")
                
                if not sort_movies or sort_page >= sort_data.get("total_pages", 1):
                    break
                
                time.sleep(0.1)
        
        print(f"  Found {len(all_movies)} movies, checking release status...")
        
        # Add movies to tracking database
        for i, movie in enumerate(all_movies):
            if i % 20 == 0:
                print(f"    Processed {i}/{len(all_movies)} movies...")
            
            movie_id = str(movie['id'])
            if movie_id in self.db['movies']:
                continue  # Already tracking
            
            release_info = self.get_release_info(movie['id'])
            if not release_info:
                continue
            
            # Get RT score
            year = None
            if release_info['theatrical_date']:
                year = release_info['theatrical_date'][:4]
            rt_score = self.get_omdb_rt_score(movie['title'], year)
            
            # Add to database
            self.db['movies'][movie_id] = {
                'title': movie['title'],
                'tmdb_id': movie['id'],
                'theatrical_date': release_info['theatrical_date'],
                'digital_date': release_info['digital_date'],
                'rt_score': rt_score,
                'status': 'resolved' if release_info['has_digital'] else 'tracking',
                'added_to_db': datetime.now().isoformat()[:10],
                'last_checked': datetime.now().isoformat()[:10]
            }
            
            time.sleep(0.1)  # Rate limiting
        
        self.save_database()
        print(f"✅ Bootstrap complete!")
    
    def add_new_theatrical_releases(self, days_back=7):
        """Daily: Add new theatrical releases from last X days (including low-popularity indie films)"""
        print(f"➕ Adding new releases from last {days_back} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        all_movies = []
        
        # Standard discovery by release date (no popularity filtering)
        params = {
            'api_key': self.api_key,
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'primary_release_date.desc',  # Changed from popularity.desc
            'page': 1
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        movies = response.json().get('results', [])
        all_movies.extend(movies)
        
        # Enhanced discovery for indie films
        print(f"  🎭 Also searching indie studios...")
        indie_companies = [41077, 2, 491, 25, 61]  # A24, Neon, Focus, IFC, Magnolia
        for company_id in indie_companies:
            params = {
                'api_key': self.api_key,
                'with_companies': str(company_id),
                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                'sort_by': 'release_date.desc',
                'page': 1
            }
            
            response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
            company_movies = response.json().get('results', [])
            
            # Add unique movies only
            existing_ids = {str(m['id']) for m in all_movies}
            new_movies = [m for m in company_movies if str(m['id']) not in existing_ids]
            all_movies.extend(new_movies)
            
            if new_movies:
                print(f"    Company {company_id}: +{len(new_movies)} indie films")
        
        movies = all_movies  # Use combined results
        
        new_count = 0
        for movie in movies:
            movie_id = str(movie['id'])
            if movie_id not in self.db['movies']:
                release_info = self.get_release_info(movie['id'])
                if release_info and release_info['theatrical_date']:
                    # Get RT score
                    year = release_info['theatrical_date'][:4]
                    rt_score = self.get_omdb_rt_score(movie['title'], year)
                    
                    self.db['movies'][movie_id] = {
                        'title': movie['title'],
                        'tmdb_id': movie['id'],
                        'theatrical_date': release_info['theatrical_date'],
                        'digital_date': release_info['digital_date'],
                        'rt_score': rt_score,
                        'status': 'resolved' if release_info['has_digital'] else 'tracking',
                        'added_to_db': datetime.now().isoformat()[:10],
                        'last_checked': datetime.now().isoformat()[:10]
                    }
                    new_count += 1
                    print(f"  ➕ Added: {movie['title']} (RT: {rt_score}%)" if rt_score else f"  ➕ Added: {movie['title']}")
                
                time.sleep(0.1)
        
        print(f"✅ Added {new_count} new movies")
        return new_count
    
    def check_tracking_movies(self):
        """Check digital status for movies still being tracked"""
        tracking_movies = {k: v for k, v in self.db['movies'].items() 
                          if v['status'] == 'tracking'}
        
        if not tracking_movies:
            print("📭 No movies currently being tracked")
            return 0
        
        print(f"🔍 Checking {len(tracking_movies)} movies for digital availability...")
        
        resolved_count = 0
        for movie_id, movie_data in tracking_movies.items():
            release_info = self.get_release_info(int(movie_id))
            if release_info and release_info['has_digital']:
                # Movie went digital!
                movie_data['digital_date'] = release_info['digital_date']
                movie_data['status'] = 'resolved'
                movie_data['last_checked'] = datetime.now().isoformat()[:10]
                resolved_count += 1
                
                print(f"  ✅ {movie_data['title']} went digital: {release_info['digital_date']}")
            else:
                movie_data['last_checked'] = datetime.now().isoformat()[:10]
            
            time.sleep(0.1)
        
        print(f"✅ Found {resolved_count} newly digital movies")
        return resolved_count
    
    def daily_update(self):
        """Run daily update: add new + check existing"""
        print("📅 Running daily update...")
        new_movies = self.add_new_theatrical_releases()
        newly_digital = self.check_tracking_movies()
        self.save_database()
        
        print(f"\n📊 Daily Summary:")
        print(f"  New movies added: {new_movies}")
        print(f"  Movies that went digital: {newly_digital}")
        print(f"  Still tracking: {self.db['stats']['still_tracking']}")
    
    def backfill_rt_scores(self):
        """Add RT scores to existing movies that don't have them"""
        movies_without_rt = {k: v for k, v in self.db['movies'].items() 
                           if not v.get('rt_score')}
        
        if not movies_without_rt:
            print("✅ All movies already have RT scores")
            return 0
        
        print(f"🍅 Backfilling RT scores for {len(movies_without_rt)} movies...")
        
        updated_count = 0
        for movie_id, movie_data in movies_without_rt.items():
            # Get year from theatrical or digital date
            year = None
            if movie_data.get('theatrical_date'):
                year = movie_data['theatrical_date'][:4]
            elif movie_data.get('digital_date'):
                year = movie_data['digital_date'][:4]
            
            rt_score = self.get_omdb_rt_score(movie_data['title'], year)
            if rt_score:
                movie_data['rt_score'] = rt_score
                updated_count += 1
                print(f"  ✅ {movie_data['title']}: {rt_score}%")
            else:
                movie_data['rt_score'] = None
                print(f"  ❌ {movie_data['title']}: No RT score found")
            
            time.sleep(0.2)  # Rate limiting for OMDb API
        
        print(f"✅ Updated {updated_count} movies with RT scores")
        self.save_database()
        return updated_count

    def show_status(self):
        """Show current database status"""
        stats = self.db['stats']
        print(f"\n📊 TRACKING DATABASE STATUS")
        print(f"{'='*40}")
        print(f"Total movies tracked: {stats['total_tracked']}")
        print(f"Resolved (went digital): {stats['resolved']}")
        print(f"Still tracking: {stats['still_tracking']}")
        print(f"Last update: {self.db.get('last_update', 'Never')}")
        
        # Show some examples
        tracking = {k: v for k, v in self.db['movies'].items() if v['status'] == 'tracking'}
        if tracking:
            print(f"\nCurrently tracking (sample):")
            for movie_id, movie in list(tracking.items())[:5]:
                days_since = (datetime.now() - datetime.fromisoformat(movie['theatrical_date'])).days
                print(f"  • {movie['title']} - {days_since} days since theatrical")
        
        recent_digital = {k: v for k, v in self.db['movies'].items() 
                         if v['status'] == 'resolved' and v.get('digital_date')}
        if recent_digital:
            print(f"\nRecently went digital (sample):")
            for movie_id, movie in list(recent_digital.items())[:5]:
                rt_text = f" (RT: {movie.get('rt_score')}%)" if movie.get('rt_score') else ""
                print(f"  • {movie['title']} - Digital: {movie.get('digital_date')}{rt_text}")

def main():
    tracker = MovieTracker()
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'bootstrap':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 365
            tracker.bootstrap_database(days)
        elif command == 'daily':
            tracker.daily_update()
        elif command == 'status':
            tracker.show_status()
        elif command == 'backfill-rt':
            tracker.backfill_rt_scores()
        else:
            print("Usage: python movie_tracker.py [bootstrap|daily|status|backfill-rt]")
    else:
        tracker.show_status()

if __name__ == "__main__":
    main()

# ================================================================
# FILE: ./new_release_wall.py
# ================================================================
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

# ================================================================
# FILE: ./new_release_wall_balanced.py
# ================================================================
#!/usr/bin/env python3
"""
Fixed TMDB scraper that properly handles movies with multiple release types
Key insight: Movies can have BOTH theatrical (3) and digital (4) releases
We should include any movie that has type 4, regardless of other types
"""

import json
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

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
    print("="*60)
    print("FIXED TMDB SCRAPER - Proper Release Type Handling")
    print("="*60)
    
    scraper = ProperTMDBScraper()
    
    # Fetch movies with proper type checking - increased page limit for more data
    movies = scraper.fetch_recent_movies(days=45, max_pages=15)
    
    # Save output
    output_file = scraper.save_output(movies)
    
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


# ================================================================
# FILE: ./quick_rt_update.py
# ================================================================
#!/usr/bin/env python3
"""
Quick RT score update for testing
"""

import json
import time
from rt_score_fetcher import get_rt_score_with_fallbacks

def update_rt_scores(limit=5):
    """Update RT scores for first N movies"""
    
    # Load current data
    with open('output/data.json', 'r') as f:
        movies = json.load(f)
    
    print(f"Updating RT scores for first {limit} movies...")
    
    updated_count = 0
    for i, movie in enumerate(movies[:limit]):
        title = movie.get('title', '')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2024'
        
        if not movie.get('rt_score'):
            print(f"\n{i+1}. Fetching RT score for: {title} ({year})")
            rt_score = get_rt_score_with_fallbacks(title, year)
            
            if rt_score:
                movie['rt_score'] = rt_score
                updated_count += 1
                print(f"   ✅ Found: {rt_score}%")
            else:
                print(f"   ❌ Not found")
            
            time.sleep(1)  # Rate limiting
        else:
            print(f"{i+1}. {title} already has RT score: {movie['rt_score']}%")
    
    # Save updated data
    with open('output/data.json', 'w') as f:
        json.dump(movies, f, indent=2)
    
    print(f"\n✅ Updated {updated_count} movies with RT scores")
    return updated_count

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    update_rt_scores(limit)

# ================================================================
# FILE: ./quick_site_update.py
# ================================================================
#!/usr/bin/env python3
"""
Quick site update using existing data.json with RT scores
"""
import json
import urllib.parse
import requests
import yaml
from jinja2 import FileSystemLoader, Environment

def get_tmdb_poster(tmdb_id):
    """Get poster URL from TMDB"""
    try:
        # Load TMDB API key
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        api_key = config.get('tmdb_api_key')
        
        if not api_key or not tmdb_id:
            return 'https://via.placeholder.com/160x240'
            
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        response = requests.get(url, params={'api_key': api_key})
        
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"
        
        return 'https://via.placeholder.com/160x240'
    except:
        return 'https://via.placeholder.com/160x240'

def quick_update_site():
    """Update site using existing data.json"""
    
    # Load existing data
    with open('output/data.json', 'r') as f:
        movies_dict = json.load(f)
    
    # First pass: identify movies with RT scores
    movies_with_rt = []
    movies_without_rt = []
    
    for movie_id, movie in movies_dict.items():
        if movie.get('rt_score'):
            movies_with_rt.append((movie_id, movie))
        else:
            movies_without_rt.append((movie_id, movie))
    
    # Limit to movies with RT scores + first 10 without (for speed)
    selected_movies = movies_with_rt + movies_without_rt[:10]
    
    print(f"Fetching posters for {len(selected_movies)} movies...")
    
    items = []
    for i, (movie_id, movie) in enumerate(selected_movies):
        print(f"  {i+1}/{len(selected_movies)}: {movie.get('title', 'Unknown')}")
        
        # Create RT URL
        title = movie.get('title', '')
        year = movie.get('year', '2025')
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        
        # Get poster from TMDB if available
        tmdb_id = movie.get('tmdb_id')
        poster_url = get_tmdb_poster(tmdb_id) if tmdb_id else 'https://via.placeholder.com/160x240'
        
        item = {
            'title': movie.get('title', 'Unknown'),
            'year': year,
            'poster_url': poster_url,
            'director': movie.get('director', 'Director N/A'),
            'cast': movie.get('cast', []),
            'synopsis': movie.get('synopsis', 'Synopsis not available.'),
            'digital_date': movie.get('digital_date', ''),
            'trailer_url': movie.get('trailer_url'),
            'rt_url': rt_url,
            'watch_link': f"https://www.justwatch.com/us/search?q={urllib.parse.quote(title)}",
            'rt_score': movie.get('rt_score'),
            'runtime': movie.get('runtime'),
            'studio': movie.get('studio', 'Studio N/A'),
            'rating': movie.get('rating', 'NR'),
            'providers': []
        }
        items.append(item)
    
    # Sort by title
    items.sort(key=lambda x: x['title'])
    
    # Group by date (simplified)
    from collections import defaultdict
    from datetime import datetime
    grouped = defaultdict(list)
    for item in items:
        date = item['digital_date'][:10] if item['digital_date'] else '2025-08-21'
        grouped[date].append(item)
    
    # Sort dates and create template data
    sorted_dates = sorted(grouped.keys(), reverse=True)
    template_data = []
    for date_str in sorted_dates:
        # Parse date for display
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_info = {
                'month_short': date_obj.strftime('%b').upper(),
                'day': date_obj.strftime('%d').lstrip('0'),
                'year': date_obj.strftime('%Y')
            }
        except:
            date_info = {
                'month_short': 'AUG',
                'day': '21',
                'year': '2025'
            }
        template_data.append((date_info, grouped[date_str]))
    
    # Load template
    from jinja2 import Template
    with open('templates/site_enhanced.html', 'r') as f:
        template = Template(f.read())
    
    # Render
    html = template.render(
        movies_by_date=template_data,
        site_title="New Release Wall",
        window_label="Digital Releases",
        region="US",
        store_names=["iTunes", "Vudu", "Amazon", "Google Play"],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    # Save
    with open('output/site/index.html', 'w') as f:
        f.write(html)
    
    print(f"✅ Quick updated site with {len(items)} movies")
    
    # Count RT scores and posters
    rt_count = sum(1 for item in items if item['rt_score'])
    poster_count = sum(1 for item in items if 'image.tmdb.org' in item['poster_url'])
    print(f"📊 {rt_count} movies have RT scores")
    print(f"🖼️ {poster_count} movies have real posters")

if __name__ == '__main__':
    quick_update_site()

# ================================================================
# FILE: ./restore_full_site.py
# ================================================================
#!/usr/bin/env python3
"""
Restore full site with all current releases + RT scores
"""
import json
import urllib.parse
import requests
import yaml
import time
from jinja2 import Template
from collections import defaultdict
from datetime import datetime

def get_tmdb_poster(tmdb_id):
    """Get poster URL from TMDB"""
    try:
        # Load TMDB API key
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        api_key = config.get('tmdb_api_key')
        
        if not api_key or not tmdb_id:
            return 'https://via.placeholder.com/160x240'
            
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        response = requests.get(url, params={'api_key': api_key})
        
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"
        
        return 'https://via.placeholder.com/160x240'
    except:
        return 'https://via.placeholder.com/160x240'

def restore_full_site():
    """Generate site with all current releases plus our RT scores"""
    
    # Load current releases (the original 201 movies)
    with open('current_releases.json', 'r') as f:
        current_movies = json.load(f)
    
    # Load our RT scores from movie_tracking.json
    with open('movie_tracking.json', 'r') as f:
        tracking_data = json.load(f)
    rt_data = tracking_data.get('movies', {})
    
    # Create lookup for RT scores by TMDB ID and title
    rt_scores_by_id = {}
    rt_scores_by_title = {}
    for movie_id, movie in rt_data.items():
        if movie.get('rt_score'):
            tmdb_id = movie.get('tmdb_id')
            title = movie.get('title')
            score = movie['rt_score']
            
            if tmdb_id:
                rt_scores_by_id[str(tmdb_id)] = score
            if title:
                rt_scores_by_title[title.lower()] = score
    
    def get_rt_score(movie):
        """Get RT score by TMDB ID or title match"""
        tmdb_id = str(movie.get('tmdb_id', ''))
        title = movie.get('title', '').lower()
        
        # Try TMDB ID first
        if tmdb_id in rt_scores_by_id:
            return rt_scores_by_id[tmdb_id]
        
        # Try title match
        if title in rt_scores_by_title:
            return rt_scores_by_title[title]
        
        return None
    
    print(f"Processing {len(current_movies)} movies with {len(rt_scores_by_id)} ID-based + {len(rt_scores_by_title)} title-based RT scores available...")
    
    # Prioritize movies with RT scores for poster fetching
    movies_with_rt = []
    movies_without_rt = []
    
    for movie in current_movies:
        if get_rt_score(movie):
            movies_with_rt.append(movie)
        else:
            movies_without_rt.append(movie)
    
    # Process movies with RT scores first (get posters), then others (no poster fetch)
    priority_movies = movies_with_rt[:20]  # First 20 with RT scores
    remaining_movies = movies_with_rt[20:] + movies_without_rt
    
    print(f"Fetching posters for {len(priority_movies)} priority movies with RT scores...")
    
    items = []
    
    # Process priority movies (with poster fetching)
    for i, movie in enumerate(priority_movies):
        print(f"  {i+1}/{len(priority_movies)}: {movie.get('title', 'Unknown')}")
        
        # Get basic movie info
        title = movie.get('title', 'Unknown')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2025'
        tmdb_id = str(movie.get('tmdb_id', ''))
        
        # Check if we have an RT score for this movie
        rt_score = get_rt_score(movie)
        
        # Create RT URL
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        
        # Fetch poster from TMDB
        poster_url = get_tmdb_poster(movie.get('tmdb_id')) if movie.get('tmdb_id') else 'https://via.placeholder.com/160x240'
        
        # Create JustWatch URL
        watch_link = f"https://www.justwatch.com/us/search?q={urllib.parse.quote(title)}"
        
        item = {
            'title': title,
            'year': year,
            'poster_url': poster_url,
            'director': movie.get('director', 'Director N/A'),
            'cast': movie.get('cast', []),
            'synopsis': movie.get('synopsis', 'Synopsis not available.'),
            'digital_date': movie.get('digital_date', ''),
            'trailer_url': movie.get('trailer_url'),
            'rt_url': rt_url,
            'watch_link': watch_link,
            'rt_score': rt_score,
            'runtime': movie.get('runtime'),
            'studio': movie.get('studio', 'Studio N/A'),
            'rating': movie.get('rating', 'NR'),
            'providers': []
        }
        items.append(item)
        time.sleep(0.1)  # Rate limiting
    
    # Process remaining movies (without poster fetching for speed)
    print(f"Processing remaining {len(remaining_movies)} movies...")
    for movie in remaining_movies:
        title = movie.get('title', 'Unknown')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2025'
        tmdb_id = str(movie.get('tmdb_id', ''))
        
        rt_score = get_rt_score(movie)
        rt_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(f'{title} {year}')}"
        
        # Use existing poster or placeholder (no TMDB fetch)
        poster_url = movie.get('poster_url', 'https://via.placeholder.com/160x240')
        if not poster_url or poster_url == 'null':
            poster_url = 'https://via.placeholder.com/160x240'
        
        watch_link = f"https://www.justwatch.com/us/search?q={urllib.parse.quote(title)}"
        
        item = {
            'title': title,
            'year': year,
            'poster_url': poster_url,
            'director': movie.get('director', 'Director N/A'),
            'cast': movie.get('cast', []),
            'synopsis': movie.get('synopsis', 'Synopsis not available.'),
            'digital_date': movie.get('digital_date', ''),
            'trailer_url': movie.get('trailer_url'),
            'rt_url': rt_url,
            'watch_link': watch_link,
            'rt_score': rt_score,
            'runtime': movie.get('runtime'),
            'studio': movie.get('studio', 'Studio N/A'),
            'rating': movie.get('rating', 'NR'),
            'providers': []
        }
        items.append(item)
    
    # Group by date
    grouped = defaultdict(list)
    for item in items:
        date = item['digital_date'][:10] if item['digital_date'] else '2025-08-21'
        grouped[date].append(item)
    
    # Sort dates and create template data
    sorted_dates = sorted(grouped.keys(), reverse=True)
    template_data = []
    for date_str in sorted_dates:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_info = {
                'month_short': date_obj.strftime('%b').upper(),
                'day': date_obj.strftime('%d').lstrip('0'),
                'year': date_obj.strftime('%Y')
            }
        except:
            date_info = {
                'month_short': 'AUG',
                'day': '21',
                'year': '2025'
            }
        template_data.append((date_info, grouped[date_str]))
    
    # Load and render template
    with open('templates/site_enhanced.html', 'r') as f:
        template = Template(f.read())
    
    html = template.render(
        movies_by_date=template_data,
        site_title="New Release Wall",
        window_label="Digital Releases",
        region="US",
        store_names=["iTunes", "Vudu", "Amazon", "Google Play"],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    # Save
    with open('output/site/index.html', 'w') as f:
        f.write(html)
    
    # Count stats
    rt_count = sum(1 for item in items if item['rt_score'])
    poster_count = sum(1 for item in items if 'image.tmdb.org' in item['poster_url'])
    
    print(f"✅ Restored full site with {len(items)} movies")
    print(f"📊 {rt_count} movies have RT scores")
    print(f"🖼️ {poster_count} movies have real posters")

if __name__ == '__main__':
    restore_full_site()

# ================================================================
# FILE: ./rt_fetcher.py
# ================================================================
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

# ================================================================
# FILE: ./update_movie_providers.py
# ================================================================
#!/usr/bin/env python3
"""
Update provider data for specific movies
"""

import json
import requests
import yaml
from datetime import datetime

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_movie_providers(movie_id, api_key):
    """Get current provider availability for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    try:
        response = requests.get(url, params={'api_key': api_key})
        us_providers = response.json().get('results', {}).get('US', {})
        
        providers = {
            'rent': [p['provider_name'] for p in us_providers.get('rent', [])],
            'buy': [p['provider_name'] for p in us_providers.get('buy', [])],
            'stream': [p['provider_name'] for p in us_providers.get('flatrate', [])]
        }
        
        total_count = len(providers['rent']) + len(providers['buy']) + len(providers['stream'])
        has_providers = total_count > 0
        
        return {
            'providers': providers,
            'provider_count': total_count,
            'has_providers': has_providers
        }
    except Exception as e:
        print(f"Error getting providers: {e}")
        return {'providers': {'rent': [], 'buy': [], 'stream': []}, 'provider_count': 0, 'has_providers': False}

def update_movie_provider_data(movie_title_search):
    """Update provider data for movies matching the search term"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Load tracking database
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)
    
    print(f"Searching for movies containing: {movie_title_search}")
    
    updated_movies = []
    
    for movie_id, movie_data in db['movies'].items():
        title = movie_data.get('title', '')
        if movie_title_search.lower() in title.lower():
            print(f"\nUpdating providers for: {title}")
            
            # Get current provider data
            provider_info = get_movie_providers(int(movie_id), api_key)
            
            # Update movie data
            old_count = movie_data.get('provider_count', 0)
            old_has_providers = movie_data.get('has_providers', False)
            
            movie_data.update({
                'provider_count': provider_info['provider_count'],
                'has_providers': provider_info['has_providers'],
                'providers': provider_info['providers'],
                'last_provider_check': datetime.now().isoformat()[:10]
            })
            
            # If movie now has providers but didn't before, mark as resolved
            if provider_info['has_providers'] and not old_has_providers:
                if not movie_data.get('digital_date'):
                    movie_data['digital_date'] = datetime.now().isoformat()[:10]
                movie_data['status'] = 'resolved'
                movie_data['detected_via_providers'] = True
                print(f"  ✅ Movie now has providers! Marked as resolved")
            
            print(f"  Providers: {provider_info['provider_count']} ({old_count} → {provider_info['provider_count']})")
            print(f"  Rent: {len(provider_info['providers']['rent'])} platforms")
            print(f"  Buy: {len(provider_info['providers']['buy'])} platforms") 
            print(f"  Stream: {len(provider_info['providers']['stream'])} platforms")
            
            updated_movies.append(title)
    
    # Save updated database
    if updated_movies:
        with open('movie_tracking.json', 'w') as f:
            json.dump(db, f, indent=2)
        print(f"\n✅ Updated {len(updated_movies)} movies")
        print(f"📁 Saved to movie_tracking.json")
    else:
        print(f"❌ No movies found matching '{movie_title_search}'")
    
    return updated_movies

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        search_term = sys.argv[1]
        update_movie_provider_data(search_term)
    else:
        print("Usage: python update_movie_providers.py <search_term>")
        print("Example: python update_movie_providers.py 'Ebony'")

