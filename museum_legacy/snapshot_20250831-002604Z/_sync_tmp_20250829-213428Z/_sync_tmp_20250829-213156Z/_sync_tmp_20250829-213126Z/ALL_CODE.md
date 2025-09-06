# New Release Wall - Complete Codebase
Updated: Fri Aug 22 15:01:55 PDT 2025
Total:       42 Python files

## adapter.py
```python
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
```

## admin.py
```python
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
```

## admin_broken.py
```python
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
    <title>Movie Admin Panel</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            padding: 2rem;
        }
        
        .header {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        h1 {
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }
        
        .stats {
            display: flex;
            gap: 2rem;
            margin-top: 1rem;
            color: #666;
        }
        
        .filters {
            background: white;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            gap: 1rem;
            align-items: center;
        }
        
        .filter-btn {
            padding: 0.5rem 1rem;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        
        .filter-btn:hover {
            background: #0056b3;
        }
        
        .movie-list {
            display: grid;
            gap: 1rem;
        }
        
        .movie-item {
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: grid;
            grid-template-columns: 100px 1fr auto;
            gap: 1.5rem;
            align-items: start;
        }
        
        .movie-item.hidden {
            opacity: 0.5;
            background: #f8f8f8;
        }
        
        .movie-item.featured {
            border-left: 4px solid gold;
        }
        
        .movie-poster {
            width: 100px;
            height: 150px;
            object-fit: cover;
            border-radius: 4px;
            background: #ddd;
        }
        
        .movie-details {
            flex: 1;
        }
        
        .movie-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        
        .movie-meta {
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }
        
        .movie-synopsis {
            margin: 1rem 0;
            padding: 0.5rem;
            background: #f8f8f8;
            border-radius: 4px;
            min-height: 60px;
            border: 1px solid #ddd;
        }
        
        .movie-synopsis[contenteditable="true"]:focus {
            outline: 2px solid #007bff;
            background: white;
        }
        
        .review-section {
            margin-top: 1rem;
        }
        
        .review-input {
            width: 100%;
            padding: 0.5rem;
            margin-top: 0.25rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        
        .movie-actions {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        
        .action-btn {
            padding: 0.5rem 1rem;
            border: 1px solid #ddd;
            background: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.2s;
        }
        
        .action-btn:hover {
            background: #f8f8f8;
        }
        
        .btn-hide {
            background: #dc3545;
            color: white;
            border-color: #dc3545;
        }
        
        .btn-hide:hover {
            background: #c82333;
        }
        
        .btn-show {
            background: #28a745;
            color: white;
            border-color: #28a745;
        }
        
        .btn-show:hover {
            background: #218838;
        }
        
        .btn-feature {
            background: gold;
            border-color: gold;
        }
        
        .btn-feature:hover {
            background: #ffc107;
        }
        
        .links {
            display: flex;
            gap: 0.5rem;
            margin-top: 0.5rem;
        }
        
        .link {
            color: #007bff;
            text-decoration: none;
            font-size: 0.85rem;
        }
        
        .link:hover {
            text-decoration: underline;
        }
        
        .rt-score {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            background: #fa320a;
            color: white;
            border-radius: 4px;
            font-weight: 600;
            text-decoration: none;
        }
        
        .rt-score:hover {
            background: #ff6b4a;
        }
        
        .save-indicator {
            position: fixed;
            top: 1rem;
            right: 1rem;
            padding: 1rem;
            background: #28a745;
            color: white;
            border-radius: 4px;
            display: none;
        }
        
        .save-indicator.show {
            display: block;
            animation: fadeInOut 2s;
        }
        
        @keyframes fadeInOut {
            0% { opacity: 0; }
            20% { opacity: 1; }
            80% { opacity: 1; }
            100% { opacity: 0; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Movie Curation Admin</h1>
        <div class="stats">
            <span>Total: <strong>{{ movies|length }}</strong></span>
            <span>Visible: <strong>{{ movies|selectattr('hidden', 'false')|list|length }}</strong></span>
            <span>Hidden: <strong>{{ movies|selectattr('hidden', 'true')|list|length }}</strong></span>
            <span>Featured: <strong>{{ movies|selectattr('featured', 'true')|list|length }}</strong></span>
        </div>
    </div>
    
    <div class="filters">
        <button class="filter-btn" onclick="showAll()">Show All</button>
        <button class="filter-btn" onclick="showVisible()">Show Visible Only</button>
        <button class="filter-btn" onclick="showHidden()">Show Hidden Only</button>
        <button class="filter-btn" onclick="showFeatured()">Show Featured</button>
        <button class="filter-btn" onclick="sortByRT()">Sort by RT Score</button>
    </div>
    
    <div class="movie-list" id="movieList">
        {% for movie in movies %}
        <div class="movie-item {% if movie.hidden %}hidden{% endif %} {% if movie.featured %}featured{% endif %}" 
             data-id="{{ movie.id }}" data-rt="{{ movie.rtScore or 0 }}">
            <img src="{{ movie.poster }}" alt="{{ movie.title }}" class="movie-poster">
            
            <div class="movie-details">
                <div class="movie-title">{{ movie.title }} ({{ movie.year }})</div>
                <div class="movie-meta">
                    Director: {{ movie.director or 'Unknown' }} | 
                    Cast: {{ movie.cast or 'Unknown' }}
                </div>
                <div class="movie-meta">
                    Runtime: {{ movie.runtime or 'Unknown' }} | 
                    Studio: {{ movie.studio or 'Unknown' }}
                </div>
                
                <div class="movie-synopsis" 
                     contenteditable="true" 
                     data-field="synopsis"
                     onblur="updateField('{{ movie.id }}', 'synopsis', this.innerText)">
                    {{ movie.synopsis or 'No synopsis available. Click to edit.' }}
                </div>
                
                <div class="review-section">
                    <label>Review 1:</label>
                    <input type="text" 
                           class="review-input" 
                           value="{{ movie.review1 or '' }}"
                           placeholder="Paste review excerpt..."
                           onblur="updateField('{{ movie.id }}', 'review1', this.value)">
                    
                    <label>Review 2:</label>
                    <input type="text" 
                           class="review-input" 
                           value="{{ movie.review2 or '' }}"
                           placeholder="Paste review excerpt..."
                           onblur="updateField('{{ movie.id }}', 'review2', this.value)">
                </div>
                
                <div class="links">
                    {% if movie.rtScore %}
                    <a href="{{ movie.rtUrl }}" target="_blank" class="rt-score">
                        🍅 {{ movie.rtScore }}%
                    </a>
                    {% endif %}
                    <a href="https://www.themoviedb.org/movie/{{ movie.tmdbId }}" target="_blank" class="link">TMDB</a>
                    <a href="https://www.justwatch.com/us/search?q={{ movie.title }}" target="_blank" class="link">JustWatch</a>
                    <a href="https://www.youtube.com/results?search_query={{ movie.title }}+{{ movie.year }}+trailer" target="_blank" class="link">Trailer</a>
                </div>
            </div>
            
            <div class="movie-actions">
                {% if movie.hidden %}
                <button class="action-btn btn-show" onclick="toggleVisibility('{{ movie.id }}')">
                    👁 Show
                </button>
                {% else %}
                <button class="action-btn btn-hide" onclick="toggleVisibility('{{ movie.id }}')">
                    🚫 Hide
                </button>
                {% endif %}
                
                <button class="action-btn btn-feature" onclick="toggleFeatured('{{ movie.id }}')">
                    {% if movie.featured %}⭐ Unflag{% else %}⭐ Feature{% endif %}
                </button>
                
                <button class="action-btn" onclick="editDetails('{{ movie.id }}')">
                    ✏️ Edit All
                </button>
            </div>
        </div>
        {% endfor %}
    </div>
    
    <div class="save-indicator" id="saveIndicator">
        ✓ Saved
    </div>
    
    <script>
        function updateField(movieId, field, value) {
            fetch('/admin/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    id: movieId,
                    field: field,
                    value: value
                })
            }).then(() => showSaved());
        }
        
        function toggleVisibility(movieId) {
            fetch('/admin/toggle-visibility', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: movieId})
            }).then(() => location.reload());
        }
        
        function toggleFeatured(movieId) {
            fetch('/admin/toggle-featured', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: movieId})
            }).then(() => location.reload());
        }
        
        function showSaved() {
            const indicator = document.getElementById('saveIndicator');
            indicator.classList.add('show');
            setTimeout(() => indicator.classList.remove('show'), 2000);
        }
        
        function showAll() {
            document.querySelectorAll('.movie-item').forEach(item => {
                item.style.display = 'grid';
            });
        }
        
        function showVisible() {
            document.querySelectorAll('.movie-item').forEach(item => {
                item.style.display = item.classList.contains('hidden') ? 'none' : 'grid';
            });
        }
        
        function showHidden() {
            document.querySelectorAll('.movie-item').forEach(item => {
                item.style.display = item.classList.contains('hidden') ? 'grid' : 'none';
            });
        }
        
        function showFeatured() {
            document.querySelectorAll('.movie-item').forEach(item => {
                item.style.display = item.classList.contains('featured') ? 'grid' : 'none';
            });
        }
        
        function sortByRT() {
            const list = document.getElementById('movieList');
            const items = Array.from(list.children);
            items.sort((a, b) => {
                const rtA = parseInt(a.dataset.rt) || 0;
                const rtB = parseInt(b.dataset.rt) || 0;
                return rtB - rtA;
            });
            items.forEach(item => list.appendChild(item));
        }
    </script>
</body>
</html>
'''

def load_movies():
    """Load movie data from JSON file."""
    if os.path.exists(CURATED_FILE):
        with open(CURATED_FILE, 'r') as f:
            return json.load(f)
    elif os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            movies = json.load(f)
            # Add curation fields if not present
            for movie in movies:
                movie.setdefault('hidden', False)
                movie.setdefault('featured', False)
                movie.setdefault('review1', '')
                movie.setdefault('review2', '')
                movie.setdefault('editedSynopsis', movie.get('synopsis', ''))
            return movies
    return []

def save_movies(movies):
    """Save curated movie data."""
    with open(CURATED_FILE, 'w') as f:
        json.dump(movies, f, indent=2)
    # Also update the main data file for the website
    with open(DATA_FILE, 'w') as f:
        json.dump(movies, f, indent=2)

@app.route('/admin')
def admin():
    """Main admin interface."""
    movies = load_movies()
    return render_template_string(ADMIN_TEMPLATE, movies=movies)

@app.route('/admin/update', methods=['POST'])
def update_field():
    """Update a single field for a movie."""
    data = request.json
    movies = load_movies()
    
    for movie in movies:
        if str(movie.get('id')) == str(data['id']):
            movie[data['field']] = data['value']
            break
    
    save_movies(movies)
    return jsonify({'status': 'success'})

@app.route('/admin/toggle-visibility', methods=['POST'])
def toggle_visibility():
    """Toggle movie visibility."""
    data = request.json
    movies = load_movies()
    
    for movie in movies:
        if str(movie.get('id')) == str(data['id']):
            movie['hidden'] = not movie.get('hidden', False)
            break
    
    save_movies(movies)
    return jsonify({'status': 'success'})

@app.route('/admin/toggle-featured', methods=['POST'])
def toggle_featured():
    """Toggle featured status."""
    data = request.json
    movies = load_movies()
    
    for movie in movies:
        if str(movie.get('id')) == str(data['id']):
            movie['featured'] = not movie.get('featured', False)
            break
    
    save_movies(movies)
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    print("Starting Movie Admin Panel...")
    print("Access at: http://localhost:5000/admin")
    print("Press Ctrl+C to stop")
    app.run(debug=True, port=5000)```

## admin_fixed.py
```python
#!/usr/bin/env python3
"""
Fixed admin panel with date editing functionality
"""

from flask import Flask, render_template_string, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

# Configuration
DATA_FILE = 'output/data.json'
TRACKING_FILE = 'movie_tracking.json'
HIDDEN_FILE = 'output/hidden_movies.json'
FEATURED_FILE = 'output/featured_movies.json'

# Fixed HTML template with proper date editing
ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Movie Admin Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, sans-serif;
            background: #1a1a1a;
            color: #fff;
            padding: 2rem;
        }
        .header {
            background: #2a2a2a;
            padding: 2rem;
            border-radius: 8px;
            margin-bottom: 2rem;
        }
        h1 { color: #ff6b6b; margin-bottom: 1rem; }
        .stats { display: flex; gap: 2rem; color: #999; }
        .stat-value { color: #fff; font-weight: bold; }
        
        .filters {
            background: #2a2a2a;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            display: flex;
            gap: 1rem;
        }
        
        .search-box {
            flex: 1;
            padding: 0.5rem;
            background: #1a1a1a;
            border: 1px solid #3a3a3a;
            color: white;
            max-width: 300px;
        }
        
        .movie-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
        }
        
        .movie-card {
            background: #2a2a2a;
            border-radius: 8px;
            padding: 1rem;
            border: 1px solid #3a3a3a;
        }
        
        .movie-poster {
            width: 100%;
            height: 200px;
            background: #1a1a1a;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #666;
            margin-bottom: 1rem;
        }
        
        .movie-title {
            font-size: 1.2rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
        }
        
        .movie-meta {
            color: #999;
            margin-bottom: 1rem;
        }
        
        .date-editor {
            background: #1a1a1a;
            padding: 0.5rem;
            border-radius: 4px;
            margin: 1rem 0;
        }
        
        .date-input {
            background: #2a2a2a;
            border: 1px solid #3a3a3a;
            color: white;
            padding: 0.5rem;
            margin-right: 0.5rem;
        }
        
        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin-right: 0.5rem;
            color: white;
        }
        
        .btn-update { background: #007bff; }
        .btn-hide { background: #dc3545; }
        .btn-feature { background: #ffc107; color: black; }
        .btn-rt { background: #ff6b6b; }
        .btn-tmdb { background: #01d277; }
        
        .movie-card.hidden { opacity: 0.5; border-color: #dc3545; }
        .movie-card.featured { border-color: #ffc107; box-shadow: 0 0 10px rgba(255,215,0,0.3); }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎬 New Release Wall - Admin Panel</h1>
        <div class="stats">
            <div>Total: <span class="stat-value">{{ movies|length }}</span></div>
            <div>Hidden: <span class="stat-value">{{ hidden|length }}</span></div>
            <div>Featured: <span class="stat-value">{{ featured|length }}</span></div>
        </div>
    </div>
    
    <div class="filters">
        <input type="text" class="search-box" placeholder="Search movies..." 
               onkeyup="filterMovies(this.value)">
    </div>
    
    <div class="movie-grid">
        {% for movie_id, movie in movies.items() %}
        <div class="movie-card {% if movie_id in hidden %}hidden{% endif %} {% if movie_id in featured %}featured{% endif %}"
             data-title="{{ movie.title|lower }}" data-id="{{ movie_id }}">
            
            <div class="movie-poster">
                {% if movie.poster_url %}
                    <img src="{{ movie.poster_url }}" style="width:100%; height:100%; object-fit:cover;">
                {% else %}
                    No Poster
                {% endif %}
            </div>
            
            <div class="movie-title">{{ movie.title }}</div>
            <div class="movie-meta">
                {{ movie.year or '2025' }} • {{ movie.director or 'Unknown Director' }}
            </div>
            
            {% if movie.rt_score %}
                <div class="movie-meta">🍅 {{ movie.rt_score }}%</div>
            {% else %}
                <div class="movie-meta">No RT Score</div>
            {% endif %}
            
            <div class="date-editor">
                <label>Digital Release:</label><br>
                <input type="date" class="date-input" id="date-{{ movie_id }}" 
                       value="{{ movie.digital_date or movie.release_date or '' }}">
                <button class="btn btn-update" onclick="updateDate('{{ movie_id }}')">📅 Update</button>
            </div>
            
            <div style="margin-top: 1rem;">
                {% if movie_id in hidden %}
                    <button class="btn btn-hide" onclick="toggleHidden('{{ movie_id }}', false)">👁️ Show</button>
                {% else %}
                    <button class="btn btn-hide" onclick="toggleHidden('{{ movie_id }}', true)">🚫 Hide</button>
                {% endif %}
                
                {% if movie_id in featured %}
                    <button class="btn btn-feature" onclick="toggleFeatured('{{ movie_id }}', false)">★ Unfeature</button>
                {% else %}
                    <button class="btn btn-feature" onclick="toggleFeatured('{{ movie_id }}', true)">⭐ Feature</button>
                {% endif %}
                
                <a href="https://www.rottentomatoes.com/search?search={{ movie.title }}" 
                   target="_blank" class="btn btn-rt" style="text-decoration:none; display:inline-block;">RT Search</a>
                
                <a href="https://www.themoviedb.org/movie/{{ movie.tmdb_id or movie_id }}" 
                   target="_blank" class="btn btn-tmdb" style="text-decoration:none; display:inline-block;">TMDB →</a>
            </div>
        </div>
        {% endfor %}
    </div>
    
    <script>
        function filterMovies(query) {
            const cards = document.querySelectorAll('.movie-card');
            cards.forEach(card => {
                const title = card.dataset.title;
                card.style.display = title.includes(query.toLowerCase()) ? 'block' : 'none';
            });
        }
        
        function updateDate(movieId) {
            const dateInput = document.getElementById('date-' + movieId);
            const newDate = dateInput.value;
            
            fetch('/update-date', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({movie_id: movieId, digital_date: newDate})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Date updated!');
                    dateInput.style.background = '#28a745';
                    setTimeout(() => dateInput.style.background = '#2a2a2a', 2000);
                }
            });
        }
        
        function toggleHidden(movieId, hide) {
            fetch('/toggle-hidden', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({movie_id: movieId, hidden: hide})
            })
            .then(() => location.reload());
        }
        
        function toggleFeatured(movieId, feature) {
            fetch('/toggle-featured', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({movie_id: movieId, featured: feature})
            })
            .then(() => location.reload());
        }
    </script>
</body>
</html>
'''

def load_json(filepath, default=None):
    if default is None:
        default = {}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return default

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def index():
    movies = load_json(DATA_FILE)
    hidden = load_json(HIDDEN_FILE, [])
    featured = load_json(FEATURED_FILE, [])
    
    return render_template_string(
        ADMIN_TEMPLATE,
        movies=movies,
        hidden=hidden,
        featured=featured
    )

@app.route('/update-date', methods=['POST'])
def update_date():
    data = request.json
    movie_id = data.get('movie_id')
    new_date = data.get('digital_date')
    
    # Update in both files
    movies = load_json(DATA_FILE)
    if movie_id in movies:
        movies[movie_id]['digital_date'] = new_date
        save_json(DATA_FILE, movies)
    
    # Also update tracking database if it exists
    if os.path.exists(TRACKING_FILE):
        tracking = load_json(TRACKING_FILE)
        if 'movies' in tracking and movie_id in tracking['movies']:
            tracking['movies'][movie_id]['digital_date'] = new_date
            tracking['movies'][movie_id]['manually_corrected'] = True
            save_json(TRACKING_FILE, tracking)
    
    return jsonify({'success': True})

@app.route('/toggle-hidden', methods=['POST'])
def toggle_hidden():
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

if __name__ == '__main__':
    print("\n🎬 Movie Admin Panel")
    print("=" * 40)
    print("Starting at http://localhost:5000")
    print("Press Ctrl+C to stop\n")
    
    app.run(debug=True, port=5000)
```

## check_metadata.py
```python
#!/usr/bin/env python3
"""
Check movie metadata that might exclude them from discovery
"""

import requests

api_key = "99b122ce7fa3e9065d7b7dc6e660772d"

print('🔍 Final test: Check movie metadata that might exclude them from discovery...\n')

missing_movies = [
    ('Pavements', 1063307),
    ('Blue Sun Palace', 1274751)
]

for title, movie_id in missing_movies:
    print(f'📽️ {title}:')
    
    response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}',
        params={'api_key': api_key}
    )
    
    if response.status_code == 200:
        movie = response.json()
        
        print(f'  Status: {movie.get("status", "Unknown")}')
        print(f'  Adult content: {movie.get("adult", False)}')
        print(f'  Video: {movie.get("video", False)}')  # True = made-for-TV/video
        print(f'  Popularity: {movie.get("popularity", 0)}')
        print(f'  Vote count: {movie.get("vote_count", 0)}')
        print(f'  Original language: {movie.get("original_language", "Unknown")}')
        
        # Check genres
        genres = [g['name'] for g in movie.get('genres', [])]
        genre_list = ', '.join(genres) if genres else "None"
        print(f'  Genres: {genre_list}')
        
        # Check production countries
        countries = [c['iso_3166_1'] for c in movie.get('production_countries', [])]
        country_list = ', '.join(countries) if countries else "None"
        print(f'  Production countries: {country_list}')
    
    print()

print('💡 Hypothesis: These movies might be:')
print('  1. Flagged as "video" (made-for-TV/streaming) rather than theatrical')
print('  2. Have low popularity scores that push them out of discovery')
print('  3. Missing US production country designation')
print('  4. Documentary/special genre that gets filtered differently')
print('  5. Have "Released" status instead of expected status')```

## check_missing_titles.py
```python
#!/usr/bin/env python3
"""
Deep dive on missing titles: provider info and release dates
"""

import requests
import json

api_key = "99b122ce7fa3e9065d7b7dc6e660772d"

print('🔍 Deep dive on missing titles: provider info and release dates...\n')

titles_to_check = [
    ('Pavements', 1063307),
    ('Blue Sun Palace', 1274751)
]

for title, movie_id in titles_to_check:
    print(f'📽️ {title} (TMDB ID: {movie_id})')
    print('=' * 50)
    
    # Get detailed movie info
    movie_response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}',
        params={'api_key': api_key}
    )
    
    if movie_response.status_code == 200:
        movie = movie_response.json()
        print(f'Title: {movie.get("title")}')
        print(f'Release Date: {movie.get("release_date")}')
        print(f'Runtime: {movie.get("runtime")} min')
        print(f'Budget: ${movie.get("budget"):,}' if movie.get('budget') else 'Budget: Unknown')
        print(f'Revenue: ${movie.get("revenue"):,}' if movie.get('revenue') else 'Revenue: Unknown')
        
        # Production companies
        companies = [c['name'] for c in movie.get('production_companies', [])]
        print(f'Production Companies: {", ".join(companies) if companies else "Unknown"}')
    
    # Get release dates with types
    release_response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}/release_dates',
        params={'api_key': api_key}
    )
    
    if release_response.status_code == 200:
        release_data = release_response.json()
        print(f'\n📅 US Release Types:')
        
        for country in release_data.get('results', []):
            if country['iso_3166_1'] == 'US':
                for release in country['release_dates']:
                    type_num = release['type']
                    date = release['release_date'][:10]  # Just the date part
                    certification = release.get('certification', '')
                    note = release.get('note', '')
                    
                    type_names = {
                        1: 'Premiere',
                        2: 'Limited Theatrical', 
                        3: 'Wide Theatrical',
                        4: 'Digital',
                        5: 'Physical',
                        6: 'TV'
                    }
                    
                    type_name = type_names.get(type_num, f'Type {type_num}')
                    print(f'  Type {type_num} ({type_name}): {date}', end='')
                    if certification:
                        print(f' [{certification}]', end='')
                    if note:
                        print(f' - {note}', end='')
                    print()
    
    # Get detailed provider info
    provider_response = requests.get(
        f'https://api.themoviedb.org/3/movie/{movie_id}/watch/providers',
        params={'api_key': api_key}
    )
    
    if provider_response.status_code == 200:
        provider_data = provider_response.json()
        us_providers = provider_data.get('results', {}).get('US', {})
        
        print(f'\n💰 US Streaming/Rental Options:')
        
        if us_providers.get('flatrate'):
            print(f'  Streaming (Free with subscription):')
            for provider in us_providers['flatrate']:
                print(f'    - {provider["provider_name"]}')
        
        if us_providers.get('rent'):
            print(f'  Rental:')
            for provider in us_providers['rent']:
                print(f'    - {provider["provider_name"]}')
        
        if us_providers.get('buy'):
            print(f'  Purchase:')
            for provider in us_providers['buy']:
                print(f'    - {provider["provider_name"]}')
        
        if not any([us_providers.get('flatrate'), us_providers.get('rent'), us_providers.get('buy')]):
            print(f'  No US providers found')
    
    print('\n' + '='*70 + '\n')```

## check_stats.py
```python
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
```

## concurrent_scraper.py
```python
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
    main()```

## convert_tracking_to_vhs.py
```python
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
    convert_tracking_to_vhs_format()```

## corrected_diagnosis.py
```python
#!/usr/bin/env python3
"""
CORRECTED diagnosis: Compare the actual approaches used
1. OLD: with_release_type='2|3|4|6' filter (new_release_wall.py)
2. NEW: NO filter, get ALL movies, then check each (new_release_wall_balanced.py)
"""

import requests
import time
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_release_types(movie_id, api_key):
    """Get release types for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
    try:
        response = requests.get(url, params={'api_key': api_key})
        data = response.json()
        
        us_types = []
        if 'results' in data:
            for country_data in data['results']:
                if country_data['iso_3166_1'] == 'US':
                    for release in country_data.get('release_dates', []):
                        release_type = release.get('type')
                        if release_type and release_type not in us_types:
                            us_types.append(release_type)
                    break
        
        return us_types
    except Exception:
        return []

def main():
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Use 45 days like our test
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    
    print("="*70)
    print("CORRECTED DIAGNOSIS - ACTUAL APPROACHES COMPARED")
    print("="*70)
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Method 1: OLD approach - with_release_type filter
    print("\\n1. OLD APPROACH - with_release_type='2|3|4|6' filter")
    print("-" * 50)
    
    old_movies = []
    for page in range(1, 6):  # 5 pages
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            'with_release_type': '2|3|4|6',  # OLD approach
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        old_movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Total movies found: {len(old_movies)}")
    
    # Check which ones actually have digital
    old_digital = []
    for i, movie in enumerate(old_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(old_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        if 4 in release_types or 6 in release_types:
            old_digital.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies with digital availability: {len(old_digital)}")
    
    # Method 2: NEW approach - NO filter, get ALL movies
    print("\\n2. NEW APPROACH - NO release_type filter (get ALL movies)")
    print("-" * 50)
    
    all_movies = []
    for page in range(1, 6):  # 5 pages
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            # NO with_release_type filter - this is the key difference!
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        all_movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Total movies found: {len(all_movies)}")
    
    # Check which ones have digital
    new_digital = []
    for i, movie in enumerate(all_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(all_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        if 4 in release_types or 6 in release_types:
            new_digital.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies with digital availability: {len(new_digital)}")
    
    # Compare results
    print("\\n" + "="*70)
    print("COMPARISON RESULTS")
    print("="*70)
    
    old_ids = {movie['id'] for movie in old_digital}
    new_ids = {movie['id'] for movie in new_digital}
    
    only_in_old = old_ids - new_ids
    only_in_new = new_ids - old_ids
    in_both = old_ids & new_ids
    
    print(f"Digital movies found by OLD approach: {len(old_ids)}")
    print(f"Digital movies found by NEW approach: {len(new_ids)}")
    print(f"Movies found by both: {len(in_both)}")
    print(f"Only found by OLD approach: {len(only_in_old)}")
    print(f"Only found by NEW approach: {len(only_in_new)}")
    
    if len(only_in_new) > 0:
        print(f"\\n🎯 NEW APPROACH FOUND {len(only_in_new)} ADDITIONAL DIGITAL MOVIES:")
        for movie in new_digital:
            if movie['id'] in only_in_new:
                print(f"  • {movie['title']} ({movie.get('release_date', '')[:4]})")
        
        improvement = ((len(new_ids) - len(old_ids)) / len(old_ids) * 100) if len(old_ids) > 0 else 0
        print(f"\\n  📈 Improvement: {improvement:.1f}% more digital movies found")
    
    if len(only_in_old) > 0:
        print(f"\\n❌ OLD APPROACH FOUND {len(only_in_old)} MOVIES NOT IN NEW:")
        for movie in old_digital:
            if movie['id'] in only_in_old:
                print(f"  • {movie['title']} ({movie.get('release_date', '')[:4]})")
    
    # Show total movie pool difference
    total_old = len(old_movies)
    total_new = len(all_movies)
    
    print(f"\\n📊 TOTAL MOVIE POOL COMPARISON:")
    print(f"  OLD approach total movies: {total_old}")
    print(f"  NEW approach total movies: {total_new}")
    print(f"  Difference: {total_new - total_old} more movies to check")
    
    if total_new > total_old:
        pool_increase = ((total_new - total_old) / total_old * 100) if total_old > 0 else 0
        print(f"  Pool increase: {pool_increase:.1f}%")
        print(f"\\n✅ The NEW approach casts a wider net!")
        print(f"   By removing the release_type filter, we search {total_new - total_old} more movies")
        print(f"   and find {len(new_ids) - len(old_ids)} more digital releases")
    else:
        print(f"\\n⚠️  Both approaches search the same number of movies")
        print(f"   The benefit comes from more accurate digital detection")

if __name__ == "__main__":
    main()```

## curator_admin.py
```python
#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify
import json
from datetime import datetime, timedelta

app = Flask(__name__)

@app.route('/')
def index():
    """Admin grid view for curation"""
    # Load current releases
    with open('current_releases.json', 'r') as f:
        releases = json.load(f)
    
    # Load any existing curation decisions
    try:
        with open('curated_selections.json', 'r') as f:
            curated = json.load(f)
    except:
        curated = {}
    
    return render_template('admin.html', 
                         movies=releases, 
                         curated=curated)

@app.route('/curate', methods=['POST'])
def curate():
    """Save curation decision"""
    movie_id = request.json['movie_id']
    decision = request.json['decision']  # 'approve', 'reject', 'feature'
    
    # Load existing decisions
    try:
        with open('curated_selections.json', 'r') as f:
            curated = json.load(f)
    except:
        curated = {}
    
    curated[movie_id] = {
        'decision': decision,
        'timestamp': datetime.now().isoformat()
    }
    
    with open('curated_selections.json', 'w') as f:
        json.dump(curated, f, indent=2)
    
    return jsonify({'status': 'success'})

@app.route('/publish', methods=['POST'])
def publish():
    """Generate final curated list"""
    # This would filter releases based on curation decisions
    # and regenerate the website with only approved films
    pass

if __name__ == '__main__':
    app.run(debug=True, port=5000)```

## diagnose_api_filter.py
```python
#!/usr/bin/env python3
"""
Diagnostic script to compare TMDB discover endpoint behavior:
1. WITH release_type filter vs WITHOUT filter
2. Show which movies appear in one approach but not the other
3. Prove whether API filtering was actually the problem
"""

import requests
import time
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_release_types(movie_id, api_key):
    """Get release types for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
    try:
        response = requests.get(url, params={'api_key': api_key})
        data = response.json()
        
        us_types = []
        if 'results' in data:
            for country_data in data['results']:
                if country_data['iso_3166_1'] == 'US':
                    for release in country_data.get('release_dates', []):
                        release_type = release.get('type')
                        if release_type and release_type not in us_types:
                            us_types.append(release_type)
                    break
        
        return us_types
    except Exception as e:
        print(f"Error getting release types for {movie_id}: {e}")
        return []

def fetch_movies_with_filter(api_key, start_date, end_date, max_pages=3):
    """Fetch movies WITH release_type filter"""
    print("=== METHOD 1: WITH release_type=4|6 filter ===")
    
    movies = []
    for page in range(1, max_pages + 1):
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            'with_release_type': '4|6',  # Digital or TV
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Found {len(movies)} movies with filter")
    return movies

def fetch_movies_without_filter(api_key, start_date, end_date, max_pages=3):
    """Fetch movies WITHOUT filter, then check types"""
    print("\\n=== METHOD 2: WITHOUT filter, then check types ===")
    
    all_movies = []
    for page in range(1, max_pages + 1):
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            # NO release_type filter
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        all_movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Found {len(all_movies)} total movies")
    print(f"  Checking release types for each...")
    
    # Check release types for each movie
    digital_movies = []
    for i, movie in enumerate(all_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(all_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        movie['us_release_types'] = release_types
        
        # Include if has digital (4) or TV (6) release type
        if 4 in release_types or 6 in release_types:
            digital_movies.append(movie)
        
        time.sleep(0.1)  # Rate limiting
    
    print(f"  Found {len(digital_movies)} movies with digital/TV types")
    return digital_movies

def compare_results(filtered_movies, unfiltered_movies):
    """Compare the two sets of results"""
    print("\\n" + "="*60)
    print("COMPARISON RESULTS")
    print("="*60)
    
    # Create sets of movie IDs for comparison
    filtered_ids = {movie['id'] for movie in filtered_movies}
    unfiltered_ids = {movie['id'] for movie in unfiltered_movies}
    
    # Movies only found with filter
    only_in_filtered = filtered_ids - unfiltered_ids
    # Movies only found without filter  
    only_in_unfiltered = unfiltered_ids - filtered_ids
    # Movies found in both
    in_both = filtered_ids & unfiltered_ids
    
    print(f"Movies found with filter only: {len(only_in_filtered)}")
    print(f"Movies found without filter only: {len(only_in_unfiltered)}")
    print(f"Movies found in both approaches: {len(in_both)}")
    
    print(f"\\nTotal unique movies:")
    print(f"  With filter: {len(filtered_ids)}")
    print(f"  Without filter: {len(unfiltered_ids)}")
    print(f"  Combined unique: {len(filtered_ids | unfiltered_ids)}")
    
    # Show specific movies that differ
    if only_in_filtered:
        print(f"\\n🔍 Movies ONLY found with filter ({len(only_in_filtered)}):")
        for movie in filtered_movies:
            if movie['id'] in only_in_filtered:
                print(f"  • {movie['title']} ({movie.get('release_date', 'No date')[:4]})")
    
    if only_in_unfiltered:
        print(f"\\n🎯 Movies ONLY found without filter ({len(only_in_unfiltered)}):")
        for movie in unfiltered_movies:
            if movie['id'] in only_in_unfiltered:
                types_str = ', '.join(map(str, movie.get('us_release_types', [])))
                print(f"  • {movie['title']} ({movie.get('release_date', 'No date')[:4]}) - Types: [{types_str}]")
    
    # Analyze release type patterns
    print(f"\\n📊 RELEASE TYPE ANALYSIS")
    print("-" * 30)
    
    # For unfiltered movies, show release type distribution
    type_counts = {}
    multi_type_movies = []
    
    for movie in unfiltered_movies:
        types = movie.get('us_release_types', [])
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1
        
        # Track movies with multiple types including digital
        if len(types) > 1 and (4 in types or 6 in types):
            multi_type_movies.append(movie)
    
    print("Release type frequency in unfiltered results:")
    type_names = {1: 'Premiere', 2: 'Theatrical (Limited)', 3: 'Theatrical', 
                  4: 'Digital', 5: 'Physical', 6: 'TV'}
    for type_num in sorted(type_counts.keys()):
        name = type_names.get(type_num, f'Type {type_num}')
        print(f"  {type_num} ({name}): {type_counts[type_num]} movies")
    
    if multi_type_movies:
        print(f"\\n🎬 Movies with MULTIPLE release types including digital ({len(multi_type_movies)}):")
        for movie in multi_type_movies[:10]:  # Show first 10
            types_str = ', '.join(map(str, movie.get('us_release_types', [])))
            in_filtered = "✓" if movie['id'] in filtered_ids else "✗"
            print(f"  {in_filtered} {movie['title']} - Types: [{types_str}]")
        if len(multi_type_movies) > 10:
            print(f"  ... and {len(multi_type_movies) - 10} more")
    
    return {
        'filtered_count': len(filtered_ids),
        'unfiltered_count': len(unfiltered_ids), 
        'only_filtered': len(only_in_filtered),
        'only_unfiltered': len(only_in_unfiltered),
        'both': len(in_both),
        'multi_type_count': len(multi_type_movies)
    }

def main():
    print("TMDB API Filter Diagnostic Tool")
    print("="*60)
    
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Use a 30-day window for comparison
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Using 3 pages max for faster comparison\\n")
    
    # Method 1: With filter
    filtered_movies = fetch_movies_with_filter(api_key, start_date, end_date, max_pages=3)
    
    # Method 2: Without filter
    unfiltered_movies = fetch_movies_without_filter(api_key, start_date, end_date, max_pages=3)
    
    # Compare results
    stats = compare_results(filtered_movies, unfiltered_movies)
    
    # Final verdict
    print("\\n" + "="*60)
    print("VERDICT")
    print("="*60)
    
    if stats['only_unfiltered'] > 0:
        print("🚨 FILTER PROBLEM CONFIRMED!")
        print(f"   The API filter missed {stats['only_unfiltered']} movies that have digital release types.")
        print(f"   These movies likely have MULTIPLE release types (e.g., both theatrical AND digital).")
        if stats['multi_type_count'] > 0:
            print(f"   Found {stats['multi_type_count']} movies with multiple release types including digital.")
    else:
        print("✅ No significant difference found.")
        print("   The API filter appears to work correctly for this time period.")
    
    print(f"\\nSummary:")
    print(f"  • Method 1 (with filter): {stats['filtered_count']} movies")
    print(f"  • Method 2 (without filter): {stats['unfiltered_count']} movies") 
    print(f"  • Difference: {abs(stats['unfiltered_count'] - stats['filtered_count'])} movies")
    
    if stats['unfiltered_count'] > stats['filtered_count']:
        improvement = ((stats['unfiltered_count'] - stats['filtered_count']) / stats['filtered_count'] * 100)
        print(f"  • Improvement: {improvement:.1f}% more movies found without filter")

if __name__ == "__main__":
    main()```

## diagnose_detailed.py
```python
#!/usr/bin/env python3
"""
Detailed diagnostic to understand why manual approach finds fewer movies
"""

import requests
import time
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_release_types_detailed(movie_id, api_key):
    """Get detailed release types for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
    try:
        response = requests.get(url, params={'api_key': api_key})
        data = response.json()
        
        us_types = []
        all_releases = []
        
        if 'results' in data:
            for country_data in data['results']:
                if country_data['iso_3166_1'] == 'US':
                    releases = country_data.get('release_dates', [])
                    all_releases = releases
                    for release in releases:
                        release_type = release.get('type')
                        if release_type and release_type not in us_types:
                            us_types.append(release_type)
                    break
        
        return {
            'types': us_types,
            'releases': all_releases,
            'has_digital': 4 in us_types or 6 in us_types
        }
    except Exception as e:
        print(f"Error getting release types for {movie_id}: {e}")
        return {'types': [], 'releases': [], 'has_digital': False}

def analyze_filtered_movies():
    """Analyze a subset of movies found WITH the filter"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print("Analyzing movies found WITH release_type=4|6 filter...")
    
    params = {
        'api_key': api_key,
        'region': 'US',
        'with_release_type': '4|6',  # Digital or TV
        'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
        'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
        'sort_by': 'popularity.desc',
        'page': 1
    }
    
    response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
    movies = response.json().get('results', [])
    
    print(f"Found {len(movies)} movies with filter")
    print("\\nChecking actual release types for first 10 movies:")
    print("-" * 60)
    
    digital_found = 0
    no_digital_found = 0
    
    for i, movie in enumerate(movies[:15]):  # Check first 15
        release_info = get_release_types_detailed(movie['id'], api_key)
        
        status = "✓ HAS" if release_info['has_digital'] else "✗ NO"
        types_str = ', '.join(map(str, release_info['types']))
        
        print(f"{status} digital | {movie['title'][:35]:35} | Types: [{types_str}]")
        
        if release_info['has_digital']:
            digital_found += 1
        else:
            no_digital_found += 1
            # Show detailed release info for movies without digital
            print(f"    Releases: {release_info['releases']}")
        
        time.sleep(0.1)
    
    print(f"\\nResults from filtered movies:")
    print(f"  Movies with digital types: {digital_found}")
    print(f"  Movies WITHOUT digital types: {no_digital_found}")
    
    if no_digital_found > 0:
        print(f"\\n🚨 ISSUE: The filter is returning {no_digital_found} movies that don't have digital release types!")
        print("This suggests the filter might be using different criteria or regions.")

def compare_parameters():
    """Compare different parameter combinations"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print("\\n" + "="*60)
    print("TESTING DIFFERENT PARAMETER COMBINATIONS")
    print("="*60)
    
    # Test 1: Just with_release_type=4 (Digital only)
    params1 = {
        'api_key': api_key,
        'region': 'US',
        'with_release_type': '4',  # Digital only
        'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
        'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
        'sort_by': 'popularity.desc',
        'page': 1
    }
    
    response1 = requests.get('https://api.themoviedb.org/3/discover/movie', params=params1)
    movies1 = response1.json().get('results', [])
    print(f"Test 1 - release_type=4 only: {len(movies1)} movies")
    
    # Test 2: Just with_release_type=6 (TV only)  
    params2 = {
        'api_key': api_key,
        'region': 'US',
        'with_release_type': '6',  # TV only
        'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
        'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
        'sort_by': 'popularity.desc',
        'page': 1
    }
    
    response2 = requests.get('https://api.themoviedb.org/3/discover/movie', params=params2)
    movies2 = response2.json().get('results', [])
    print(f"Test 2 - release_type=6 only: {len(movies2)} movies")
    
    # Test 3: with_release_type=4|6 (what we were using)
    params3 = {
        'api_key': api_key,
        'region': 'US', 
        'with_release_type': '4|6',  # Digital OR TV
        'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
        'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
        'sort_by': 'popularity.desc',
        'page': 1
    }
    
    response3 = requests.get('https://api.themoviedb.org/3/discover/movie', params=params3)
    movies3 = response3.json().get('results', [])
    print(f"Test 3 - release_type=4|6: {len(movies3)} movies")
    
    # Test 4: No release_type filter at all
    params4 = {
        'api_key': api_key,
        'region': 'US',
        'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
        'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
        'sort_by': 'popularity.desc',
        'page': 1
    }
    
    response4 = requests.get('https://api.themoviedb.org/3/discover/movie', params=params4)
    movies4 = response4.json().get('results', [])
    print(f"Test 4 - No filter: {len(movies4)} movies")
    
    print(f"\\nExpected: Test 1 + Test 2 should roughly equal Test 3")
    print(f"Actual: {len(movies1)} + {len(movies2)} = {len(movies1) + len(movies2)} vs {len(movies3)}")

def main():
    print("DETAILED TMDB API DIAGNOSTIC")
    print("="*60)
    
    # First analyze what the filter is actually returning
    analyze_filtered_movies()
    
    # Then test different parameter combinations
    compare_parameters()
    
    print("\\n" + "="*60)
    print("CONCLUSIONS")
    print("="*60)
    print("1. If filtered movies don't actually have digital release types,")
    print("   the filter might be using different criteria (e.g., global releases)")
    print("2. If they DO have digital types, then our manual checking logic might be wrong")
    print("3. The 'region=US' parameter might interact with release_type filtering differently")

if __name__ == "__main__":
    main()```

## diagnose_indie_search.py
```python
#!/usr/bin/env python3
"""
Diagnose why we're not finding more indie films
"""

import json
import requests
import time
from datetime import datetime, timedelta

api_key = "99b122ce7fa3e9065d7b7dc6e660772d"

# Load current database
with open('movie_tracking.json', 'r') as f:
    db = json.load(f)
    existing_ids = set(db['movies'].keys())

print("🔍 Diagnosing indie film search...\n")

# Search for A24 films from last 2 years
params = {
    'api_key': api_key,
    'with_companies': '41077',  # A24
    'primary_release_date.gte': '2023-01-01',
    'primary_release_date.lte': '2025-12-31',
    'sort_by': 'release_date.desc'
}

response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
if response.status_code == 200:
    movies = response.json().get('results', [])
    print(f"Found {len(movies)} A24 films from 2023-2025")
    
    in_db = 0
    no_providers = 0
    should_add = []
    
    for movie in movies:
        movie_id = str(movie['id'])
        
        if movie_id in existing_ids:
            in_db += 1
        else:
            # Check providers
            time.sleep(0.2)
            prov_response = requests.get(
                f'https://api.themoviedb.org/3/movie/{movie_id}/watch/providers',
                params={'api_key': api_key}
            )
            
            if prov_response.status_code == 200:
                us_providers = prov_response.json().get('results', {}).get('US', {})
                has_providers = any([
                    us_providers.get('rent'),
                    us_providers.get('buy'),
                    us_providers.get('flatrate')
                ])
                
                if not has_providers:
                    no_providers += 1
                    print(f"  ❌ No providers: {movie['title']} ({movie.get('release_date', 'No date')[:10]})")
                else:
                    should_add.append(movie['title'])
                    print(f"  ✅ Has providers but not in DB: {movie['title']}")
    
    print(f"\nSummary:")
    print(f"  Already in database: {in_db}")
    print(f"  No providers listed: {no_providers}")
    print(f"  Should be added: {len(should_add)}")

# Check for specific known films
print("\n🎬 Checking specific known indie films...")
known_films = [
    "Beau Is Afraid",
    "The Iron Claw", 
    "Priscilla",
    "Dream Scenario",
    "The Whale",
    "Everything Everywhere All at Once",
    "X",
    "Pearl",
    "Men",
    "After Yang"
]

for title in known_films:
    # Search for the film
    search_response = requests.get(
        'https://api.themoviedb.org/3/search/movie',
        params={'api_key': api_key, 'query': title}
    )
    
    if search_response.status_code == 200:
        results = search_response.json().get('results', [])
        if results:
            movie = results[0]
            movie_id = str(movie['id'])
            
            if movie_id in existing_ids:
                print(f"  ✓ {title} - Already in database")
            else:
                print(f"  ✗ {title} - MISSING from database")
```

## enhanced_discovery.py
```python
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
    discovery.test_missing_films()```

## enhanced_movie_tracker.py
```python
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

def main():
    """CLI interface"""
    import sys
    
    tracker = EnhancedMovieTracker()
    
    if len(sys.argv) < 2:
        print("Usage: python enhanced_movie_tracker.py [bootstrap|check-missing|status]")
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

if __name__ == "__main__":
    main()```

## enhanced_rt_collector.py
```python
#!/usr/bin/env python3
"""
Enhanced RT Score Collector using WebFetch
Collects RT scores for movies missing them in the database
"""

import json
import re
import sys
import time
from urllib.parse import quote

# This script is designed to be called from Claude with WebFetch access
# It will output JSON data that can be parsed by the movie tracker

def get_rt_url_candidates(title, year=None):
    """Generate possible RT URLs for a movie"""
    # Clean title for URL
    title_slug = re.sub(r'[^\w\s-]', '', title.lower())
    title_slug = re.sub(r'[-\s]+', '_', title_slug)
    
    candidates = [
        f"https://www.rottentomatoes.com/m/{title_slug}_{year}" if year else None,
        f"https://www.rottentomatoes.com/m/{title_slug}",
        f"https://www.rottentomatoes.com/m/{title_slug.replace('_', '-')}",
    ]
    
    return [url for url in candidates if url]

def load_movies_needing_scores():
    """Load movies from database that need RT scores"""
    try:
        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)
        
        movies_needing_scores = []
        for movie_id, movie in db['movies'].items():
            if not movie.get('rt_score'):
                # Extract year from release date
                year = None
                if movie.get('release_date'):
                    year = movie['release_date'][:4]
                
                movies_needing_scores.append({
                    'id': movie_id,
                    'title': movie['title'],
                    'year': year
                })
        
        return movies_needing_scores
    except Exception as e:
        print(f"Error loading movies: {e}")
        return []

def main():
    """Main function to collect RT scores"""
    movies = load_movies_needing_scores()
    print(f"Found {len(movies)} movies needing RT scores")
    
    # Output the first few movies that need scores for testing
    for movie in movies[:10]:
        title = movie['title']
        year = movie['year']
        print(f"Movie: {title} ({year})")
        
        # Generate URL candidates
        urls = get_rt_url_candidates(title, year)
        print(f"RT URL candidates: {urls}")
        print()

if __name__ == "__main__":
    main()```

## export_for_admin.py
```python
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
    export_movie_data()```

## final_diagnosis.py
```python
#!/usr/bin/env python3
"""
Final diagnostic using the exact same parameters as our original scripts
to prove the API filter issue
"""

import requests
import time
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def get_release_types(movie_id, api_key):
    """Get release types for a movie"""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
    try:
        response = requests.get(url, params={'api_key': api_key})
        data = response.json()
        
        us_types = []
        if 'results' in data:
            for country_data in data['results']:
                if country_data['iso_3166_1'] == 'US':
                    for release in country_data.get('release_dates', []):
                        release_type = release.get('type')
                        if release_type and release_type not in us_types:
                            us_types.append(release_type)
                    break
        
        return us_types
    except Exception:
        return []

def test_original_parameters():
    """Test with the exact parameters from new_release_wall.py"""
    config = load_config()
    api_key = config['tmdb_api_key']
    
    # Use 45 days like our working script
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    
    print("="*60)
    print("FINAL DIAGNOSIS - EXACT ORIGINAL PARAMETERS")
    print("="*60)
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Test the OLD way (with filter) - exactly like new_release_wall.py
    print("\\n1. OLD METHOD - With release_type filter (like new_release_wall.py)")
    print("-" * 50)
    
    old_movies = []
    for page in range(1, 6):  # 5 pages like our test
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            'with_release_type': '2|3|4|6',  # Exactly like the old script
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        old_movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Total movies with filter: {len(old_movies)}")
    
    # Now check how many actually have digital types
    print("\\n  Checking actual release types...")
    actually_digital = []
    false_positives = []
    
    for i, movie in enumerate(old_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(old_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        has_digital = 4 in release_types or 6 in release_types
        
        if has_digital:
            actually_digital.append(movie)
        else:
            false_positives.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies that actually have digital types: {len(actually_digital)}")
    print(f"  False positives (no digital types): {len(false_positives)}")
    
    # Test the NEW way (without filter) - like new_release_wall_balanced.py  
    print("\\n2. NEW METHOD - Without filter, then check types")
    print("-" * 50)
    
    all_movies = []
    for page in range(1, 6):  # 5 pages
        print(f"  Fetching page {page}...")
        
        params = {
            'api_key': api_key,
            'region': 'US',
            # NO release_type filter
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc',
            'page': page
        }
        
        response = requests.get('https://api.themoviedb.org/3/discover/movie', params=params)
        page_movies = response.json().get('results', [])
        
        if not page_movies:
            break
            
        all_movies.extend(page_movies)
        time.sleep(0.2)
    
    print(f"  Total movies without filter: {len(all_movies)}")
    
    # Check release types for each
    print("\\n  Checking release types for each...")
    new_digital = []
    
    for i, movie in enumerate(all_movies):
        if i % 10 == 0 and i > 0:
            print(f"    Checked {i}/{len(all_movies)} movies...")
        
        release_types = get_release_types(movie['id'], api_key)
        has_digital = 4 in release_types or 6 in release_types
        
        if has_digital:
            new_digital.append(movie)
            
        time.sleep(0.1)
    
    print(f"  Movies with digital types: {len(new_digital)}")
    
    # Compare the results
    print("\\n" + "="*60)
    print("FINAL COMPARISON")
    print("="*60)
    
    old_ids = {movie['id'] for movie in actually_digital}
    new_ids = {movie['id'] for movie in new_digital}
    
    only_in_old = old_ids - new_ids
    only_in_new = new_ids - old_ids
    in_both = old_ids & new_ids
    
    print(f"Movies found with OLD method (actually digital): {len(old_ids)}")
    print(f"Movies found with NEW method: {len(new_ids)}")
    print(f"Movies in both: {len(in_both)}")
    print(f"Only in OLD: {len(only_in_old)}")
    print(f"Only in NEW: {len(only_in_new)}")
    
    if len(false_positives) > 0:
        print(f"\\n🚨 API FILTER ISSUE CONFIRMED:")
        print(f"   The filter returned {len(false_positives)} movies without digital release types")
        print(f"   False positive rate: {len(false_positives)/len(old_movies)*100:.1f}%")
        
        print(f"\\n   Examples of false positives:")
        for movie in false_positives[:5]:
            print(f"     • {movie['title']} ({movie.get('release_date', '')[:4]})")
    
    if len(only_in_new) > 0:
        print(f"\\n✅ NEW METHOD FOUND {len(only_in_new)} ADDITIONAL MOVIES:")
        for movie in new_digital:
            if movie['id'] in only_in_new:
                print(f"     • {movie['title']} ({movie.get('release_date', '')[:4]})")
        
        improvement = len(new_ids) / len(old_ids) * 100 - 100 if len(old_ids) > 0 else 0
        print(f"\\n   Improvement: {improvement:.1f}% more movies found")
    
    print(f"\\n🎯 BOTTOM LINE:")
    if len(new_ids) > len(old_ids):
        print(f"   NEW method finds {len(new_ids) - len(old_ids)} more digitally available movies")
        print(f"   This proves the API filter was indeed problematic")
    else:
        print(f"   Both methods find similar numbers of movies")
        print(f"   The API filter works correctly for this dataset")

if __name__ == "__main__":
    test_original_parameters()```

## find_all_indie_films.py
```python
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
```

## fix_rt_scores.py
```python
#!/usr/bin/env python3
"""
Fix RT scores using working OMDb API
"""

import json
import time
from simple_rt_fetcher import get_rt_score_omdb

def fix_rt_scores(limit=10):
    """Fix RT scores using working OMDb API"""
    
    # Load current data
    with open('output/data.json', 'r') as f:
        movies_dict = json.load(f)
    
    print(f"Fixing RT scores using OMDb API for first {limit} movies...")
    
    updated_count = 0
    processed = 0
    
    for movie_id, movie in movies_dict.items():
        if processed >= limit:
            break
            
        title = movie.get('title', '')
        year = movie.get('digital_date', '')[:4] if movie.get('digital_date') else '2024'
        
        processed += 1
        print(f"\n{processed}. Fetching RT score for: {title} ({year})")
        rt_score = get_rt_score_omdb(title, year)
        
        if rt_score:
            movie['rt_score'] = rt_score
            updated_count += 1
            print(f"   ✅ Found: {rt_score}%")
        else:
            print(f"   ❌ Not found")
        
        time.sleep(0.2)  # Rate limiting
    
    # Save updated data
    with open('output/data.json', 'w') as f:
        json.dump(movies_dict, f, indent=2)
    
    print(f"\n✅ Fixed {updated_count} RT scores using OMDb API")
    return updated_count

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    fix_rt_scores(limit)```

## fix_tracking_dates.py
```python
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
```

## generate_from_tracker.py
```python
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
            print(f"  • {movie['title']} - {days_ago} days ago")```

## generate_site.py
```python
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
    generate_site()```

## generate_substack.py
```python
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
```

## hybrid_site_restore.py
```python
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
    hybrid_restore()```

## justwatch_collector.py
```python
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
    main()```

## movie_tracker.py
```python
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
    main()```

## movie_tracker_enhanced.py
```python
#!/usr/bin/env python3
"""
Enhanced Movie Digital Release Tracker
- Tracks all release types (1, 2, 3, 4)
- Uses provider data comparison to detect actual digital availability
- Catches indie films that might not have reliable Type 4 dates
"""

import json
import requests
import yaml
from datetime import datetime, timedelta
import time
import os

class EnhancedMovieTracker:
    def __init__(self, db_file='movie_tracking_enhanced.json'):
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
            'last_provider_check': None,
            'stats': {
                'total_tracked': 0,
                'resolved': 0,
                'still_tracking': 0,
                'provider_detected': 0
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
            'still_tracking': len([m for m in movies.values() if m.get('status') == 'tracking']),
            'provider_detected': len([m for m in movies.values() if m.get('detected_via_providers', False)])
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
        """Get release dates for a movie - ALL types (1, 2, 3, 4)"""
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        try:
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            result = {
                'premiere_date': None,      # Type 1
                'limited_date': None,       # Type 2  
                'theatrical_date': None,    # Type 3
                'digital_date': None,       # Type 4
                'earliest_release': None,   # Earliest of any type
                'has_digital': False,
                'release_types_found': []
            }
            
            # Collect all release dates by type
            all_dates = {1: [], 2: [], 3: [], 4: []}
            
            if 'results' in data:
                for country_data in data['results']:
                    for release in country_data.get('release_dates', []):
                        release_type = release.get('type')
                        date = release.get('release_date', '')[:10]
                        
                        if date and release_type in [1, 2, 3, 4]:
                            all_dates[release_type].append(date)
                            if release_type not in result['release_types_found']:
                                result['release_types_found'].append(release_type)
                
                # Find earliest date for each type
                for release_type, dates in all_dates.items():
                    if dates:
                        earliest = min(dates)
                        if release_type == 1:
                            result['premiere_date'] = earliest
                        elif release_type == 2:
                            result['limited_date'] = earliest
                        elif release_type == 3:
                            result['theatrical_date'] = earliest
                        elif release_type == 4:
                            result['digital_date'] = earliest
                
                # Find overall earliest release
                all_release_dates = [d for dates in all_dates.values() for d in dates]
                if all_release_dates:
                    result['earliest_release'] = min(all_release_dates)
                
                result['has_digital'] = bool(result['digital_date'])
            
            return result
        except Exception as e:
            print(f"Error getting release info for {movie_id}: {e}")
            return None
    
    def get_justwatch_providers(self, movie_id):
        """Get JustWatch provider data from TMDB"""
        try:
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
            response = requests.get(url, params={'api_key': self.api_key})
            data = response.json()
            
            us_data = data.get('results', {}).get('US', {})
            providers = {
                'rent': us_data.get('rent', []),
                'buy': us_data.get('buy', []),
                'flatrate': us_data.get('flatrate', [])
            }
            
            # Check if any digital providers are available
            has_digital_providers = any(providers.values())
            
            return {
                'has_providers': has_digital_providers,
                'providers': providers,
                'provider_count': sum(len(p) for p in providers.values())
            }
        except Exception as e:
            print(f"Error getting providers for {movie_id}: {e}")
            return {'has_providers': False, 'providers': {}, 'provider_count': 0}
    
    def get_omdb_rt_score(self, title, year):
        """Get Rotten Tomatoes score from OMDb API"""
        if not self.omdb_api_key:
            return None
            
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
            print(f"Error getting RT score for {title}: {e}")
        return None
    
    def comprehensive_bootstrap(self, days_back=730):
        """Bootstrap with comprehensive search for ALL release types"""
        print(f"🚀 Comprehensive bootstrap: scanning {days_back} days for ALL release types...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Get movies using multiple discovery methods
        all_movies = []
        
        # Method 1: Primary release date (catches most theatrical)
        print("  🎬 Scanning primary releases...")
        movies_primary = self._discover_movies({
            "sort_by": "primary_release_date.desc",
            "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
            "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
        })
        all_movies.extend(movies_primary)
        
        # Method 2: Release date (catches premieres, festivals)
        print("  🎪 Scanning all releases...")
        movies_release = self._discover_movies({
            "sort_by": "release_date.desc", 
            "release_date.gte": start_date.strftime("%Y-%m-%d"),
            "release_date.lte": end_date.strftime("%Y-%m-%d"),
        })
        all_movies.extend(movies_release)
        
        # Method 3: Popularity (catches trending indie films)
        print("  📈 Scanning popular recent movies...")
        movies_popular = self._discover_movies({
            "sort_by": "popularity.desc",
            "primary_release_date.gte": (end_date - timedelta(days=365)).strftime("%Y-%m-%d"),
        }, max_pages=10)
        all_movies.extend(movies_popular)
        
        # Deduplicate by TMDB ID
        seen_ids = set()
        unique_movies = []
        for movie in all_movies:
            if movie['id'] not in seen_ids:
                seen_ids.add(movie['id'])
                unique_movies.append(movie)
        
        print(f"  📊 Found {len(unique_movies)} unique movies, analyzing releases...")
        
        # Process each movie
        for i, movie in enumerate(unique_movies):
            if i % 25 == 0:
                print(f"    Processed {i}/{len(unique_movies)} movies...")
            
            movie_id = str(movie['id'])
            if movie_id in self.db['movies']:
                continue  # Already tracking
            
            # Get comprehensive release info
            release_info = self.get_release_info(movie['id'])
            if not release_info or not release_info['earliest_release']:
                continue
            
            # Get provider data
            provider_info = self.get_justwatch_providers(movie['id'])
            
            # Get RT score
            year = None
            if release_info['earliest_release']:
                year = release_info['earliest_release'][:4]
            rt_score = self.get_omdb_rt_score(movie['title'], year)
            
            # Determine status
            status = 'resolved' if (release_info['has_digital'] or provider_info['has_providers']) else 'tracking'
            
            # Add to database
            self.db['movies'][movie_id] = {
                'title': movie['title'],
                'tmdb_id': movie['id'],
                'premiere_date': release_info['premiere_date'],
                'limited_date': release_info['limited_date'],
                'theatrical_date': release_info['theatrical_date'],
                'digital_date': release_info['digital_date'],
                'earliest_release': release_info['earliest_release'],
                'release_types_found': release_info['release_types_found'],
                'provider_count': provider_info['provider_count'],
                'has_providers': provider_info['has_providers'],
                'detected_via_providers': provider_info['has_providers'] and not release_info['has_digital'],
                'rt_score': rt_score,
                'status': status,
                'added_to_db': datetime.now().isoformat()[:10],
                'last_checked': datetime.now().isoformat()[:10],
                'last_provider_check': datetime.now().isoformat()[:10]
            }
            
            time.sleep(0.15)  # Rate limiting
        
        self.save_database()
        print(f"✅ Comprehensive bootstrap complete!")
        print(f"  📊 Total movies: {self.db['stats']['total_tracked']}")
        print(f"  🎯 Provider-detected: {self.db['stats']['provider_detected']}")
    
    def _discover_movies(self, base_params, max_pages=50):
        """Helper to discover movies with pagination"""
        movies = []
        page = 1
        
        while page <= max_pages:
            params = base_params.copy()
            params['page'] = page
            params['region'] = 'US'
            
            data = self.tmdb_get("/discover/movie", params)
            page_movies = data.get("results", [])
            
            if not page_movies:
                break
                
            movies.extend(page_movies)
            total_pages = min(data.get("total_pages", 1), max_pages)
            
            if page >= total_pages:
                break
                
            page += 1
            time.sleep(0.2)
        
        return movies
    
    def check_providers_for_tracking_movies(self):
        """Check provider availability for movies still being tracked"""
        tracking_movies = {k: v for k, v in self.db['movies'].items() 
                          if v['status'] == 'tracking'}
        
        if not tracking_movies:
            print("📭 No movies currently being tracked")
            return 0
        
        print(f"🔍 Checking providers for {len(tracking_movies)} tracking movies...")
        
        newly_available = 0
        for movie_id, movie_data in tracking_movies.items():
            provider_info = self.get_justwatch_providers(int(movie_id))
            
            # Update provider data
            movie_data['provider_count'] = provider_info['provider_count']
            movie_data['has_providers'] = provider_info['has_providers']
            movie_data['last_provider_check'] = datetime.now().isoformat()[:10]
            
            # Check if movie went digital via providers
            if provider_info['has_providers'] and not movie_data.get('has_providers_previously', False):
                movie_data['status'] = 'resolved'
                movie_data['detected_via_providers'] = True
                movie_data['digital_detected_date'] = datetime.now().isoformat()[:10]
                newly_available += 1
                
                print(f"  🎯 {movie_data['title']} - Digital via providers! ({provider_info['provider_count']} providers)")
            
            movie_data['has_providers_previously'] = provider_info['has_providers']
            time.sleep(0.1)
        
        self.db['last_provider_check'] = datetime.now().isoformat()
        print(f"✅ Found {newly_available} newly available via providers")
        return newly_available
    
    def add_movie_by_title(self, title, year=None):
        """Manually add a specific movie to tracking (for missing indie films)"""
        print(f"🔍 Searching for: {title}" + (f" ({year})" if year else ""))
        
        # Search TMDB
        params = {'query': title}
        if year:
            params['year'] = year
            
        data = self.tmdb_get("/search/movie", params)
        movies = data.get('results', [])
        
        if not movies:
            print(f"❌ No movies found for '{title}'")
            return False
        
        # Take the first match (or best match by year)
        movie = movies[0]
        if year:
            for m in movies:
                if m.get('release_date', '').startswith(str(year)):
                    movie = m
                    break
        
        movie_id = str(movie['id'])
        
        if movie_id in self.db['movies']:
            print(f"ℹ️  {movie['title']} already being tracked")
            return True
        
        print(f"➕ Adding: {movie['title']} ({movie.get('release_date', 'Unknown date')})")
        
        # Get full details
        release_info = self.get_release_info(movie['id'])
        provider_info = self.get_justwatch_providers(movie['id'])
        
        # Get RT score
        movie_year = None
        if release_info and release_info['earliest_release']:
            movie_year = release_info['earliest_release'][:4]
        rt_score = self.get_omdb_rt_score(movie['title'], movie_year)
        
        # Determine status
        status = 'resolved' if (release_info['has_digital'] or provider_info['has_providers']) else 'tracking'
        
        # Add to database
        self.db['movies'][movie_id] = {
            'title': movie['title'],
            'tmdb_id': movie['id'],
            'premiere_date': release_info['premiere_date'] if release_info else None,
            'limited_date': release_info['limited_date'] if release_info else None,
            'theatrical_date': release_info['theatrical_date'] if release_info else None,
            'digital_date': release_info['digital_date'] if release_info else None,
            'earliest_release': release_info['earliest_release'] if release_info else None,
            'release_types_found': release_info['release_types_found'] if release_info else [],
            'provider_count': provider_info['provider_count'],
            'has_providers': provider_info['has_providers'],
            'detected_via_providers': provider_info['has_providers'] and not (release_info and release_info['has_digital']),
            'rt_score': rt_score,
            'status': status,
            'added_to_db': datetime.now().isoformat()[:10],
            'last_checked': datetime.now().isoformat()[:10],
            'last_provider_check': datetime.now().isoformat()[:10],
            'manually_added': True
        }
        
        provider_status = f" - {provider_info['provider_count']} providers" if provider_info['has_providers'] else " - No providers yet"
        rt_status = f" (RT: {rt_score}%)" if rt_score else ""
        print(f"✅ Added{provider_status}{rt_status}")
        
        self.save_database()
        return True
    
    def daily_update(self):
        """Enhanced daily update: check TMDB dates + provider availability"""
        print("📅 Running enhanced daily update...")
        
        # Add new theatrical releases
        new_movies = self.add_new_releases(days_back=7)
        
        # Check provider availability for tracking movies
        newly_via_providers = self.check_providers_for_tracking_movies()
        
        # Check TMDB digital dates for tracking movies
        newly_via_tmdb = self.check_tmdb_digital_dates()
        
        self.save_database()
        
        print(f"\n📊 Daily Summary:")
        print(f"  New movies added: {new_movies}")
        print(f"  Digital via providers: {newly_via_providers}")
        print(f"  Digital via TMDB: {newly_via_tmdb}")
        print(f"  Still tracking: {self.db['stats']['still_tracking']}")
        print(f"  Provider-detected total: {self.db['stats']['provider_detected']}")
    
    def add_new_releases(self, days_back=7):
        """Add new releases from multiple discovery methods"""
        print(f"➕ Adding new releases from last {days_back} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Multiple discovery methods
        all_movies = []
        
        # Primary releases
        movies_primary = self._discover_movies({
            'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
            'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc'
        }, max_pages=5)
        all_movies.extend(movies_primary)
        
        # All releases
        movies_all = self._discover_movies({
            'release_date.gte': start_date.strftime('%Y-%m-%d'),
            'release_date.lte': end_date.strftime('%Y-%m-%d'),
            'sort_by': 'popularity.desc'
        }, max_pages=5)
        all_movies.extend(movies_all)
        
        # Deduplicate
        seen_ids = set()
        unique_movies = []
        for movie in all_movies:
            if movie['id'] not in seen_ids:
                seen_ids.add(movie['id'])
                unique_movies.append(movie)
        
        new_count = 0
        for movie in unique_movies:
            movie_id = str(movie['id'])
            if movie_id not in self.db['movies']:
                release_info = self.get_release_info(movie['id'])
                if release_info and release_info['earliest_release']:
                    provider_info = self.get_justwatch_providers(movie['id'])
                    
                    # Get RT score
                    year = release_info['earliest_release'][:4]
                    rt_score = self.get_omdb_rt_score(movie['title'], year)
                    
                    status = 'resolved' if (release_info['has_digital'] or provider_info['has_providers']) else 'tracking'
                    
                    self.db['movies'][movie_id] = {
                        'title': movie['title'],
                        'tmdb_id': movie['id'],
                        'premiere_date': release_info['premiere_date'],
                        'limited_date': release_info['limited_date'],
                        'theatrical_date': release_info['theatrical_date'],
                        'digital_date': release_info['digital_date'],
                        'earliest_release': release_info['earliest_release'],
                        'release_types_found': release_info['release_types_found'],
                        'provider_count': provider_info['provider_count'],
                        'has_providers': provider_info['has_providers'],
                        'detected_via_providers': provider_info['has_providers'] and not release_info['has_digital'],
                        'rt_score': rt_score,
                        'status': status,
                        'added_to_db': datetime.now().isoformat()[:10],
                        'last_checked': datetime.now().isoformat()[:10],
                        'last_provider_check': datetime.now().isoformat()[:10]
                    }
                    new_count += 1
                    print(f"  ➕ Added: {movie['title']}")
                
                time.sleep(0.1)
        
        print(f"✅ Added {new_count} new movies")
        return new_count
    
    def check_tmdb_digital_dates(self):
        """Check TMDB digital dates for tracking movies"""
        tracking_movies = {k: v for k, v in self.db['movies'].items() 
                          if v['status'] == 'tracking'}
        
        resolved_count = 0
        for movie_id, movie_data in tracking_movies.items():
            release_info = self.get_release_info(int(movie_id))
            if release_info and release_info['has_digital'] and not movie_data.get('digital_date'):
                # Movie got TMDB digital date!
                movie_data['digital_date'] = release_info['digital_date']
                movie_data['status'] = 'resolved'
                movie_data['last_checked'] = datetime.now().isoformat()[:10]
                resolved_count += 1
                
                print(f"  ✅ {movie_data['title']} - TMDB digital date: {release_info['digital_date']}")
            
            time.sleep(0.1)
        
        return resolved_count
    
    def show_status(self):
        """Show enhanced database status"""
        # Ensure stats exist
        if 'stats' not in self.db:
            self.save_database()  # This will calculate stats
        stats = self.db['stats']
        print(f"\n📊 ENHANCED TRACKING DATABASE STATUS")
        print(f"{'='*50}")
        print(f"Total movies tracked: {stats['total_tracked']}")
        print(f"Resolved (went digital): {stats['resolved']}")
        print(f"  └─ Via provider detection: {stats['provider_detected']}")
        print(f"Still tracking: {stats['still_tracking']}")
        print(f"Last update: {self.db.get('last_update', 'Never')}")
        print(f"Last provider check: {self.db.get('last_provider_check', 'Never')}")
        
        # Show tracking examples
        tracking = {k: v for k, v in self.db['movies'].items() if v.get('status') == 'tracking'}
        if tracking:
            print(f"\nCurrently tracking (sample):")
            for movie_id, movie in list(tracking.items())[:5]:
                earliest = movie.get('earliest_release')
                if earliest:
                    days_since = (datetime.now() - datetime.fromisoformat(earliest)).days
                    types = movie.get('release_types_found', [])
                    type_str = f" (Types: {types})" if types else ""
                    print(f"  • {movie['title']} - {days_since} days since release{type_str}")
        
        # Show provider-detected movies
        provider_detected = {k: v for k, v in self.db['movies'].items() 
                           if v.get('detected_via_providers', False)}
        if provider_detected:
            print(f"\nProvider-detected movies (sample):")
            for movie_id, movie in list(provider_detected.items())[:5]:
                rt_text = f" (RT: {movie.get('rt_score')}%)" if movie.get('rt_score') else ""
                providers = movie.get('provider_count', 0)
                print(f"  🎯 {movie['title']} - {providers} providers{rt_text}")
        
        # Show recently added movies
        recent_added = {k: v for k, v in self.db['movies'].items() 
                       if v.get('manually_added', False)}
        if recent_added:
            print(f"\nManually added movies:")
            for movie_id, movie in recent_added.items():
                status = movie.get('status', 'unknown')
                providers = movie.get('provider_count', 0)
                print(f"  ➕ {movie['title']} - {status} ({providers} providers)")

def main():
    tracker = EnhancedMovieTracker()
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'bootstrap':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 730
            tracker.comprehensive_bootstrap(days)
        elif command == 'daily':
            tracker.daily_update()
        elif command == 'status':
            tracker.show_status()
        elif command == 'add':
            if len(sys.argv) < 3:
                print("Usage: python movie_tracker_enhanced.py add 'Movie Title' [year]")
                return
            title = sys.argv[2]
            year = int(sys.argv[3]) if len(sys.argv) > 3 else None
            tracker.add_movie_by_title(title, year)
        elif command == 'check-providers':
            tracker.check_providers_for_tracking_movies()
            tracker.save_database()
        else:
            print("Usage: python movie_tracker_enhanced.py [bootstrap|daily|status|add|check-providers]")
    else:
        tracker.show_status()

if __name__ == "__main__":
    main()```

## new_release_wall.py
```python
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
    main()```

## new_release_wall_balanced.py
```python
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
```

## new_release_wall_fixed.py
```python
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
        
        # Format data
        movie['poster'] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get('poster_path') else ''
        movie['year'] = movie.get('release_date', '')[:4] if movie.get('release_date') else ''
        
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
    
    # Fetch movies with proper type checking
    movies = scraper.fetch_recent_movies(days=45, max_pages=5)
    
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
```

## new_release_wall_improved.py
```python
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
```

## new_release_wall_smart.py
```python
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
```

## new_release_wall_v2.py
```python
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
            'overview': movie.get('overview', ''),
            'tmdb_url': f"https://www.themoviedb.org/movie/{movie['id']}",
            'tmdb_watch_link': f"https://www.themoviedb.org/movie/{movie['id']}/watch",
            'justwatch_search_link': f"https://www.justwatch.com/us/search?q={movie['title'].replace(' ', '%20')}"
        }
        
        processed.append(movie_data)
    
    return processed

def generate_output(movies, region="US"):
    """Generate HTML and markdown output"""
    # Create output directory
    os.makedirs('output/site', exist_ok=True)
    
    # Generate HTML
    with open('templates/site.html', 'r') as f:
        template = Template(f.read())
    
    html = template.render(
        items=movies,
        site_title="New Release Wall",
        window_label="Last 7 days",
        region=region,
        store_names=[],
        generated_at=dt.now().strftime("%Y-%m-%d %H:%M")
    )
    
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
    generate_output(processed, args.region)
    
    print(f"\nGenerated output for {len(processed)} movies")
    print("View at: http://localhost:8080")

if __name__ == "__main__":
    main()```

## quick_rt_update.py
```python
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
    update_rt_scores(limit)```

## quick_site_update.py
```python
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
    quick_update_site()```

## restore_full_site.py
```python
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
    restore_full_site()```

## rt_score_collector.py
```python
#!/usr/bin/env python3
"""
Rotten Tomatoes Score Collector
Direct web scraping fallback for when OMDb doesn't have RT scores
"""

import json
import re
import requests
from urllib.parse import quote
import time

class RTScoreCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def search_rt_movie(self, title, year=None):
        """Search for movie on RT and return URL if found"""
        try:
            # Try direct URL construction first (most common pattern)
            title_slug = re.sub(r'[^\w\s-]', '', title.lower())
            title_slug = re.sub(r'[-\s]+', '_', title_slug)
            
            if year:
                direct_url = f"https://www.rottentomatoes.com/m/{title_slug}_{year}"
            else:
                direct_url = f"https://www.rottentomatoes.com/m/{title_slug}"
            
            response = self.session.get(direct_url)
            if response.status_code == 200 and 'tomatometer' in response.text.lower():
                return direct_url
                
            # Try without year
            if year:
                alt_url = f"https://www.rottentomatoes.com/m/{title_slug}"
                response = self.session.get(alt_url)
                if response.status_code == 200 and 'tomatometer' in response.text.lower():
                    return alt_url
            
            return None
        except Exception as e:
            print(f"Error searching for {title}: {e}")
            return None
    
    def extract_rt_scores(self, url):
        """Extract RT scores from movie page"""
        try:
            response = self.session.get(url)
            html = response.text
            
            scores = {}
            
            # Extract Tomatometer score
            tomatometer_match = re.search(r'"score":"(\d+)"%.*?"state":"certified-fresh|fresh|rotten"', html)
            if tomatometer_match:
                scores['tomatometer'] = int(tomatometer_match.group(1))
            else:
                # Alternative pattern
                tomatometer_match = re.search(r'tomatometer.*?(\d+)%', html, re.IGNORECASE)
                if tomatometer_match:
                    scores['tomatometer'] = int(tomatometer_match.group(1))
            
            # Extract Audience score  
            audience_match = re.search(r'"audienceScore":"(\d+)"', html)
            if audience_match:
                scores['audience'] = int(audience_match.group(1))
            else:
                # Alternative pattern
                audience_match = re.search(r'audience.*?score.*?(\d+)%', html, re.IGNORECASE)
                if audience_match:
                    scores['audience'] = int(audience_match.group(1))
            
            return scores
            
        except Exception as e:
            print(f"Error extracting scores from {url}: {e}")
            return {}
    
    def get_rt_scores(self, title, year=None):
        """Get RT scores for a movie"""
        print(f"🍅 Searching RT for: {title} ({year})")
        
        url = self.search_rt_movie(title, year)
        if not url:
            print(f"❌ No RT page found for {title}")
            return None
        
        print(f"✓ Found RT page: {url}")
        scores = self.extract_rt_scores(url)
        
        if scores:
            tomatometer = scores.get('tomatometer', 'N/A')
            audience = scores.get('audience', 'N/A')
            print(f"✓ Scores: {tomatometer}% critics, {audience}% audience")
            return scores.get('tomatometer')  # Return tomatometer score
        else:
            print(f"❌ Could not extract scores from page")
            return None

def test_collector():
    """Test the RT collector with known movies"""
    collector = RTScoreCollector()
    
    test_movies = [
        ("Weapons", 2025),
        ("Hostile Takeover", 2025),
        ("The Pickup", 2025)
    ]
    
    for title, year in test_movies:
        score = collector.get_rt_scores(title, year)
        print(f"{title} ({year}): {score}%\n")

if __name__ == "__main__":
    test_collector()```

## rt_score_fetcher.py
```python
#!/usr/bin/env python3
"""
Rotten Tomatoes Score Fetcher
Fetches RT scores by scraping RT search results
"""

import requests
import re
import urllib.parse
import time
from bs4 import BeautifulSoup

def get_rt_score_from_search(title, year=None):
    """Get RT score by searching Rotten Tomatoes"""
    try:
        # Create search query
        search_query = f"{title} {year}" if year else title
        search_url = f"https://www.rottentomatoes.com/search?search={urllib.parse.quote(search_query)}"
        
        # Headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Look for tomatometer score in the HTML
            html_content = response.text
            
            # Multiple patterns to find RT scores
            patterns = [
                r'tomatometer-score["\s>]+(\d+)',
                r'critics-score["\s>]+(\d+)',
                r'data-tomatometer["\s]*=["\s]*(\d+)',
                r'"tomatometer":(\d+)',
                r'score-number["\s>]+(\d+)%',
                r'(\d+)%\s*</span>.*?tomatometer',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                if matches:
                    score = int(matches[0])
                    if 0 <= score <= 100:  # Valid RT score range
                        return score
            
            # If no score found in search results, try to find movie link and follow it
            soup = BeautifulSoup(html_content, 'html.parser')
            movie_links = soup.find_all('a', href=re.compile(r'/m/'))
            
            if movie_links:
                movie_url = 'https://www.rottentomatoes.com' + movie_links[0]['href']
                return get_rt_score_from_movie_page(movie_url, headers)
        
        return None
        
    except Exception as e:
        print(f"Error getting RT score for {title}: {e}")
        return None

def get_rt_score_from_movie_page(movie_url, headers):
    """Get RT score from a specific movie page"""
    try:
        response = requests.get(movie_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html_content = response.text
            
            # Look for score in movie page
            patterns = [
                r'data-tomatometer["\s]*=["\s]*"(\d+)"',
                r'"tomatometer"\s*:\s*(\d+)',
                r'tomatometer-score["\s>]+(\d+)',
                r'critics_score["\s]*:\s*(\d+)',
                r'(\d+)%.*?tomatometer',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                if matches:
                    score = int(matches[0])
                    if 0 <= score <= 100:
                        return score
        
        return None
        
    except Exception as e:
        print(f"Error getting RT score from movie page: {e}")
        return None

def get_rt_score_with_fallbacks(title, year=None):
    """Get RT score with multiple fallback methods"""
    
    # Method 1: Search-based scraping
    score = get_rt_score_from_search(title, year)
    if score is not None:
        return score
    
    # Method 2: Try without year
    if year:
        score = get_rt_score_from_search(title)
        if score is not None:
            return score
    
    # Method 3: Try with simplified title (remove articles, special chars)
    simplified_title = title.lower()
    for article in ['the ', 'a ', 'an ']:
        if simplified_title.startswith(article):
            simplified_title = simplified_title[len(article):]
    
    simplified_title = re.sub(r'[^\w\s]', '', simplified_title).strip()
    if simplified_title != title.lower():
        score = get_rt_score_from_search(simplified_title, year)
        if score is not None:
            return score
    
    return None

def test_rt_fetcher():
    """Test the RT score fetcher with known movies"""
    test_movies = [
        ("Deadpool & Wolverine", 2024),
        ("Inside Out 2", 2024),
        ("The Wild Robot", 2024),
        ("Beetlejuice Beetlejuice", 2024),
        ("Joker: Folie à Deux", 2024)
    ]
    
    print("Testing RT Score Fetcher:")
    print("=" * 40)
    
    for title, year in test_movies:
        print(f"\nFetching score for: {title} ({year})")
        score = get_rt_score_with_fallbacks(title, year)
        if score is not None:
            print(f"✅ {title}: {score}%")
        else:
            print(f"❌ {title}: No score found")
        
        time.sleep(1)  # Rate limiting

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_rt_fetcher()
        else:
            title = sys.argv[1]
            year = int(sys.argv[2]) if len(sys.argv) > 2 else None
            score = get_rt_score_with_fallbacks(title, year)
            if score is not None:
                print(f"{title}: {score}%")
            else:
                print(f"{title}: No RT score found")
    else:
        print("Usage: python rt_score_fetcher.py <title> [year]")
        print("       python rt_score_fetcher.py test")```

## simple_rt_fetcher.py
```python
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
        print("       python simple_rt_fetcher.py test")```

## update_movie_providers.py
```python
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
        print("Example: python update_movie_providers.py 'Ebony'")```

