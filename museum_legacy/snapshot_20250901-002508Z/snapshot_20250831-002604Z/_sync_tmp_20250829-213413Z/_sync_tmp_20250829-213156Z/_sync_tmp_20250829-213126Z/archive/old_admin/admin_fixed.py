"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
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
