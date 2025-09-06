# New Release Wall - Complete Code Documentation

## Project Overview

The New Release Wall is a comprehensive movie tracking and discovery system that monitors theatrical releases and their digital availability. After significant consolidation and enhancement efforts, the project now consists of focused, purpose-built components that work together to provide an automated movie discovery experience.

### Current State (Post-Consolidation)

The project has been streamlined from numerous experimental implementations into a cohesive system with clear responsibilities:

- **Consolidated Architecture**: Multiple RT fetchers, diagnostics tools, and scrapers have been unified into single, comprehensive implementations
- **Enhanced Discovery**: Improved indie and foreign film detection across multiple studios and languages  
- **Modern Admin Panel**: Complete redesign with dark theme, real-time filtering, and date editing capabilities
- **Optimized Performance**: Site generation now uses current releases subset (201 vs 10,818 movies) for faster loading
- **Restored Features**: RT scores properly integrated from main tracking database

### Key Statistics
- **Total Movies Tracked**: 10,818 movies in main database
- **Current Releases**: 201 movies in 60-day window
- **RT Scores Available**: 51 movies with Rotten Tomatoes ratings
- **Active Files**: 25+ Python modules with specific responsibilities

---

## Core System Files

### movie_tracker.py
**Purpose**: Main tracking system - Enhanced movie tracker that captures all release types including premieres, limited theatrical, wide theatrical, and digital releases.

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
```

---

### admin.py
**Purpose**: Modern admin panel with dark theme, real-time filtering, search, and date editing capabilities.

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

---

### rt_fetcher.py
**Purpose**: Consolidated RT Score Fetcher combining OMDb API, web scraping, and audience scores with the best features from all implementations.

```python
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
```

---

### diagnostics.py
**Purpose**: Consolidated diagnostic tool combining all diagnostic functions for TMDB API testing and system verification.

```python
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
```

---

### generate_site.py
**Purpose**: Site generator using VHS-style template with comprehensive movie details from TMDB.

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
    generate_site()
```

---

### generate_from_tracker.py
**Purpose**: Data processor that generates movie lists from the tracking database with provider information.

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
            print(f"  • {movie['title']} - {days_ago} days ago")
```

---

## Utility and Support Files

### adapter.py
**Purpose**: Platform adapter for mapping store names to platform codes for UI display.

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

---

### find_all_indie_films.py
**Purpose**: Comprehensive indie and foreign film finder using multiple search strategies to find films across studios and languages.

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

---

## Additional Utility Files

### concurrent_scraper.py
**Purpose**: Concurrent daily scraper to bypass TMDB API pagination limits by scraping each day individually.

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
    main()
```

---

## Additional Specialized Files

The project also includes several other specialized files for specific tasks:

- **enhanced_discovery.py**: Enhanced discovery system for low-popularity indie films
- **export_for_admin.py**: Exports movie tracking data to admin panel format
- **fix_tracking_dates.py**: Fixes tracking dates using better fallback logic
- **generate_substack.py**: Generates Substack-ready newsletter templates
- **hybrid_site_restore.py**: Hybrid approach using current_releases.json + RT scores
- **justwatch_collector.py**: JustWatch integration for streaming availability
- **convert_tracking_to_vhs.py**: Converts tracking database to VHS site format
- **quick_rt_update.py**: Quick RT score update for testing
- **quick_site_update.py**: Quick site update using existing data
- **restore_full_site.py**: Restores full site with all current releases
- **update_movie_providers.py**: Updates provider data for specific movies
- **new_release_wall.py**: Original balanced movie discovery implementation
- **movie_tracker_basic_backup.py**: Basic movie tracker backup implementation

Each of these files serves specific functions within the ecosystem, handling everything from data transformation to specialized discovery algorithms to administrative tasks.

---

## Project Architecture Summary

The New Release Wall system follows a modular architecture with clear separation of concerns:

1. **Data Collection Layer**: `movie_tracker.py`, `find_all_indie_films.py`, `concurrent_scraper.py`
2. **Data Processing Layer**: `generate_from_tracker.py`, `rt_fetcher.py`, `diagnostics.py`
3. **Presentation Layer**: `generate_site.py`, `admin.py`
4. **Utility Layer**: All remaining support files for specific tasks

The system maintains a comprehensive database of 10,818+ movies with 51 RT scores, providing automated daily updates and a polished user experience through both the public site and admin interface.

### Total Files: 25+ active Python modules
### Total Code Size: ~15,000+ lines of Python code
### Database: 10,818 movies tracked with 51 RT scores available
### Current Active Dataset: 201 movies in 60-day release window

This consolidated system represents the culmination of extensive development and refinement, providing a robust foundation for movie discovery and tracking.