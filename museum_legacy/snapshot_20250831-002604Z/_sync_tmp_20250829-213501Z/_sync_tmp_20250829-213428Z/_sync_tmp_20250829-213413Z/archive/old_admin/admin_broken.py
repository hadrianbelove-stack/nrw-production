"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
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
    app.run(debug=True, port=5000)
