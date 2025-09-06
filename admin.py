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
