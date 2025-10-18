#!/usr/bin/env python3
"""
Admin panel for curating movie selections.
Simple Flask app for editing movie data and controlling visibility.
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import json
import os
import subprocess
from datetime import datetime
import yaml

app = Flask(__name__)

from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()

# Load credentials from environment or use defaults (change in production!)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme')

@auth.verify_password
def verify_password(username, password):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return username
    return None

# Configuration
DATA_FILE = 'data.json'  # Root directory - production display data
HIDDEN_FILE = 'admin/hidden_movies.json'  # Admin overrides
FEATURED_FILE = 'admin/featured_movies.json'  # Admin overrides
WATCH_LINK_OVERRIDES_FILE = 'admin/watch_link_overrides.json'

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
        <div style="margin-top: 1rem;">
            <button onclick="regenerateData()"
                    class="action-btn"
                    style="background: #007bff; color: white; padding: 0.6rem 1.2rem; font-size: 0.9rem;"
                    id="regenerate-btn">
                🔄 Regenerate data.json
            </button>
            <span id="regenerate-status" style="margin-left: 1rem; color: #999; font-size: 0.85rem;"></span>
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

                <!-- Watch Links Editor -->
                <div class="watch-links-editor" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #3a3a3a;">
                    <div style="font-size: 0.85rem; color: #999; margin-bottom: 0.5rem; cursor: pointer;"
                         onclick="toggleWatchLinksEditor('{{ movie_id }}')">
                        🔗 Watch Links Override
                        <span id="watch-links-indicator-{{ movie_id }}" style="color: #00d4aa;">
                            {% if movie_id in watch_link_overrides %}({{ watch_link_overrides[movie_id].keys()|length }} override{% if watch_link_overrides[movie_id].keys()|length != 1 %}s{% endif %}){% endif %}
                        </span>
                        <span style="float: right;">▼</span>
                    </div>

                    <div id="watch-links-form-{{ movie_id }}" style="display: none;">
                        <!-- Streaming Override -->
                        <div style="margin-bottom: 0.5rem;">
                            <label style="font-size: 0.75rem; color: #999; display: block; margin-bottom: 0.2rem;">Streaming</label>
                            <input type="text"
                                   id="streaming-service-{{ movie_id }}"
                                   placeholder="Service (e.g., Netflix)"
                                   value="{% if movie_id in watch_link_overrides and 'streaming' in watch_link_overrides[movie_id] %}{{ watch_link_overrides[movie_id]['streaming']['service'] }}{% endif %}"
                                   style="width: 100%; padding: 0.3rem; background: #1a1a1a; border: 1px solid #3a3a3a; color: white; border-radius: 4px; font-size: 0.75rem; margin-bottom: 0.2rem;">
                            <input type="url"
                                   id="streaming-link-{{ movie_id }}"
                                   placeholder="https://www.netflix.com/title/..."
                                   value="{% if movie_id in watch_link_overrides and 'streaming' in watch_link_overrides[movie_id] %}{{ watch_link_overrides[movie_id]['streaming']['link'] }}{% endif %}"
                                   style="width: 100%; padding: 0.3rem; background: #1a1a1a; border: 1px solid #3a3a3a; color: white; border-radius: 4px; font-size: 0.75rem;">
                        </div>

                        <!-- Rent Override -->
                        <div style="margin-bottom: 0.5rem;">
                            <label style="font-size: 0.75rem; color: #999; display: block; margin-bottom: 0.2rem;">Rent</label>
                            <input type="text"
                                   id="rent-service-{{ movie_id }}"
                                   placeholder="Service (e.g., Amazon Video)"
                                   value="{% if movie_id in watch_link_overrides and 'rent' in watch_link_overrides[movie_id] %}{{ watch_link_overrides[movie_id]['rent']['service'] }}{% endif %}"
                                   style="width: 100%; padding: 0.3rem; background: #1a1a1a; border: 1px solid #3a3a3a; color: white; border-radius: 4px; font-size: 0.75rem; margin-bottom: 0.2rem;">
                            <input type="url"
                                   id="rent-link-{{ movie_id }}"
                                   placeholder="https://www.amazon.com/..."
                                   value="{% if movie_id in watch_link_overrides and 'rent' in watch_link_overrides[movie_id] %}{{ watch_link_overrides[movie_id]['rent']['link'] }}{% endif %}"
                                   style="width: 100%; padding: 0.3rem; background: #1a1a1a; border: 1px solid #3a3a3a; color: white; border-radius: 4px; font-size: 0.75rem;">
                        </div>

                        <!-- Buy Override -->
                        <div style="margin-bottom: 0.5rem;">
                            <label style="font-size: 0.75rem; color: #999; display: block; margin-bottom: 0.2rem;">Buy</label>
                            <input type="text"
                                   id="buy-service-{{ movie_id }}"
                                   placeholder="Service (e.g., Apple TV)"
                                   value="{% if movie_id in watch_link_overrides and 'buy' in watch_link_overrides[movie_id] %}{{ watch_link_overrides[movie_id]['buy']['service'] }}{% endif %}"
                                   style="width: 100%; padding: 0.3rem; background: #1a1a1a; border: 1px solid #3a3a3a; color: white; border-radius: 4px; font-size: 0.75rem; margin-bottom: 0.2rem;">
                            <input type="url"
                                   id="buy-link-{{ movie_id }}"
                                   placeholder="https://tv.apple.com/..."
                                   value="{% if movie_id in watch_link_overrides and 'buy' in watch_link_overrides[movie_id] %}{{ watch_link_overrides[movie_id]['buy']['link'] }}{% endif %}"
                                   style="width: 100%; padding: 0.3rem; background: #1a1a1a; border: 1px solid #3a3a3a; color: white; border-radius: 4px; font-size: 0.75rem;">
                        </div>

                        <!-- Save Button -->
                        <button class="action-btn"
                                style="background: #28a745; color: white; font-size: 0.75rem; padding: 0.4rem 0.8rem; width: 100%;"
                                onclick="saveWatchLinks('{{ movie_id }}')">
                            💾 Save Watch Links
                        </button>

                        <!-- Clear Button -->
                        <button class="action-btn"
                                style="background: #dc3545; color: white; font-size: 0.75rem; padding: 0.4rem 0.8rem; width: 100%; margin-top: 0.3rem;"
                                onclick="clearWatchLinks('{{ movie_id }}')">
                            🗑️ Clear All Overrides
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
                    // Update card styling without page reload
                    const card = document.querySelector(`[data-movie-id="${movieId}"]`);
                    if (hide) {
                        card.classList.add('hidden');
                    } else {
                        card.classList.remove('hidden');
                    }

                    // Update button
                    const actionsDiv = card.querySelector('.movie-actions');
                    const hideBtn = actionsDiv.querySelector('.btn-hide, .btn-show');
                    if (hide) {
                        hideBtn.className = 'action-btn btn-show';
                        hideBtn.innerHTML = '👁️ Show';
                        hideBtn.onclick = () => toggleHidden(movieId, false);
                    } else {
                        hideBtn.className = 'action-btn btn-hide';
                        hideBtn.innerHTML = '🚫 Hide';
                        hideBtn.onclick = () => toggleHidden(movieId, true);
                    }

                    // Update stats
                    updateStats();

                    showSuccess(hide ? 'Movie hidden' : 'Movie shown');
                }
            })
            .catch(error => {
                alert('Error: ' + error);
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
                    // Update card styling without page reload
                    const card = document.querySelector(`[data-movie-id="${movieId}"]`);
                    if (feature) {
                        card.classList.add('featured');
                    } else {
                        card.classList.remove('featured');
                    }

                    // Update button
                    const actionsDiv = card.querySelector('.movie-actions');
                    const featureBtn = actionsDiv.querySelector('.btn-feature, .btn-unfeature');
                    if (feature) {
                        featureBtn.className = 'action-btn btn-unfeature';
                        featureBtn.innerHTML = '⭐ Unfeature';
                        featureBtn.onclick = () => toggleFeatured(movieId, false);
                    } else {
                        featureBtn.className = 'action-btn btn-feature';
                        featureBtn.innerHTML = '⭐ Feature';
                        featureBtn.onclick = () => toggleFeatured(movieId, true);
                    }

                    // Update stats
                    updateStats();

                    showSuccess(feature ? 'Movie featured' : 'Movie unfeatured');
                }
            })
            .catch(error => {
                alert('Error: ' + error);
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

        function updateStats() {
            // Recalculate stats from current DOM state
            const allCards = document.querySelectorAll('.movie-card');
            const hiddenCards = document.querySelectorAll('.movie-card.hidden');
            const featuredCards = document.querySelectorAll('.movie-card.featured');

            const total = allCards.length;
            const hidden = hiddenCards.length;
            const visible = total - hidden;
            const featured = featuredCards.length;

            // Update stat displays
            document.getElementById('visible-count').textContent = visible;
            document.getElementById('hidden-count').textContent = hidden;
            document.getElementById('featured-count').textContent = featured;
        }

        function regenerateData() {
            const btn = document.getElementById('regenerate-btn');
            const status = document.getElementById('regenerate-status');

            // Disable button and show loading state
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
            status.textContent = 'Regenerating... (this may take 10-30 seconds)';
            status.style.color = '#ffc107';

            fetch('/regenerate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    status.textContent = '✓ ' + (data.message || 'Regeneration complete!');
                    status.style.color = '#28a745';
                    showSuccess('data.json regenerated successfully');
                } else {
                    status.textContent = '✗ ' + (data.error || 'Regeneration failed');
                    status.style.color = '#dc3545';
                    alert('Regeneration failed: ' + (data.error || 'Unknown error'));
                }

                // Re-enable button
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';

                // Clear status after 5 seconds
                setTimeout(() => {
                    status.textContent = '';
                }, 5000);
            })
            .catch(error => {
                status.textContent = '✗ Error: ' + error;
                status.style.color = '#dc3545';
                alert('Error triggering regeneration: ' + error);

                // Re-enable button
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
            });
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

        function toggleWatchLinksEditor(movieId) {
            const form = document.getElementById(`watch-links-form-${movieId}`);
            const isHidden = form.style.display === 'none';
            form.style.display = isHidden ? 'block' : 'none';
        }

        function validateUrl(url) {
            if (!url || url.trim() === '') {
                return true; // Empty is valid (means "no override")
            }
            try {
                const urlObj = new URL(url);
                return urlObj.protocol === 'http:' || urlObj.protocol === 'https:';
            } catch (e) {
                return false;
            }
        }

        function saveWatchLinks(movieId) {
            // Collect input values
            const streamingService = document.getElementById(`streaming-service-${movieId}`).value.trim();
            const streamingLink = document.getElementById(`streaming-link-${movieId}`).value.trim();
            const rentService = document.getElementById(`rent-service-${movieId}`).value.trim();
            const rentLink = document.getElementById(`rent-link-${movieId}`).value.trim();
            const buyService = document.getElementById(`buy-service-${movieId}`).value.trim();
            const buyLink = document.getElementById(`buy-link-${movieId}`).value.trim();

            // Validate URLs
            if (!validateUrl(streamingLink)) {
                alert('Invalid streaming URL. Must start with http:// or https://');
                return;
            }
            if (!validateUrl(rentLink)) {
                alert('Invalid rent URL. Must start with http:// or https://');
                return;
            }
            if (!validateUrl(buyLink)) {
                alert('Invalid buy URL. Must start with http:// or https://');
                return;
            }

            // Build overrides object (only include non-empty entries)
            const overrides = {};

            if (streamingService && streamingLink) {
                overrides.streaming = {service: streamingService, link: streamingLink};
            }
            if (rentService && rentLink) {
                overrides.rent = {service: rentService, link: rentLink};
            }
            if (buyService && buyLink) {
                overrides.buy = {service: buyService, link: buyLink};
            }

            // Send to server
            fetch('/update-watch-links', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    movie_id: movieId,
                    overrides: overrides
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showSuccess(data.message || 'Watch links saved!');
                    // Update indicator
                    const indicator = document.getElementById(`watch-links-indicator-${movieId}`);
                    const count = Object.keys(overrides).length;
                    if (count > 0) {
                        indicator.textContent = `(${count} override${count !== 1 ? 's' : ''})`;
                    } else {
                        indicator.textContent = '';
                    }
                } else {
                    alert(data.error || 'Failed to save watch links');
                }
            })
            .catch(error => {
                alert('Error saving watch links: ' + error);
            });
        }

        function clearWatchLinks(movieId) {
            if (!confirm('Clear all watch link overrides for this movie?')) {
                return;
            }

            // Clear input fields
            document.getElementById(`streaming-service-${movieId}`).value = '';
            document.getElementById(`streaming-link-${movieId}`).value = '';
            document.getElementById(`rent-service-${movieId}`).value = '';
            document.getElementById(`rent-link-${movieId}`).value = '';
            document.getElementById(`buy-service-${movieId}`).value = '';
            document.getElementById(`buy-link-${movieId}`).value = '';

            // Send empty overrides to server
            fetch('/update-watch-links', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    movie_id: movieId,
                    overrides: {}
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showSuccess('Watch link overrides cleared');
                    // Clear indicator
                    const indicator = document.getElementById(`watch-links-indicator-${movieId}`);
                    indicator.textContent = '';
                } else {
                    alert(data.error || 'Failed to clear watch links');
                }
            })
            .catch(error => {
                alert('Error clearing watch links: ' + error);
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

def load_config():
    """Load configuration from config.yaml"""
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Warning: Could not load config.yaml: {e}")
        return {}

def get_tmdb_api_key():
    """Get TMDB API key from config or environment"""
    # Try environment variable first (12-factor app pattern)
    api_key = os.environ.get('TMDB_API_KEY')
    if api_key:
        return api_key

    # Fall back to config.yaml
    config = load_config()
    api_key = config.get('api', {}).get('tmdb_api_key')
    if api_key:
        return api_key

    # Last resort: print warning
    print("Warning: No TMDB API key found in environment or config.yaml")
    return None

def get_poster_url(tmdb_id):
    """Get poster URL from TMDB ID"""
    if not tmdb_id:
        return None

    api_key = get_tmdb_api_key()
    if not api_key:
        return None

    try:
        import requests
        response = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": api_key},
            timeout=10  # 10 second timeout
        )
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w300{poster_path}"
    except requests.Timeout:
        print(f"Timeout fetching poster for TMDB ID {tmdb_id}")
        return None
    except:
        pass
    return None

def save_json(filepath, data):
    """Save JSON file"""
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
@auth.login_required
def index():
    """Main admin panel"""
    data = load_json(DATA_FILE, {})
    hidden = load_json(HIDDEN_FILE, [])
    featured = load_json(FEATURED_FILE, [])
    watch_link_overrides = load_json(WATCH_LINK_OVERRIDES_FILE, {})

    # Handle different data shapes from data.json
    if data and isinstance(data, dict) and 'movies' in data and isinstance(data['movies'], list):
        movies_list = data['movies']
    elif isinstance(data, list):
        movies_list = data
    else:
        movies_list = []

    # Process all movies and build dict keyed by movie ID
    processed_movies = {}

    for movie in movies_list:
        movie_id = str(movie.get('id'))
        movie_copy = dict(movie)

        # Normalize movie fields expected by template
        # Set rt_url from links.rt if available
        if movie_copy.get('links', {}).get('rt'):
            movie_copy['rt_url'] = movie_copy['links']['rt']

        # Set director from crew.director if available
        if movie_copy.get('crew', {}).get('director'):
            movie_copy['director'] = movie_copy['crew']['director']

        # Build provider_list from providers or watch_links
        providers = set()
        if movie_copy.get('providers'):
            for category in ['streaming', 'rent', 'buy']:
                if category in movie_copy['providers']:
                    providers.update(movie_copy['providers'][category])
        if movie_copy.get('watch_links'):
            for category_data in movie_copy['watch_links'].values():
                if isinstance(category_data, dict) and 'service' in category_data:
                    providers.add(category_data['service'])
        movie_copy['provider_list'] = ', '.join(sorted(providers)) if providers else ''

        # Handle poster URLs
        if movie_copy.get('poster') and not movie_copy.get('poster_url'):
            movie_copy['poster_url'] = movie_copy['poster']

        # Fetch from TMDB only if both poster and poster_url are missing and id exists
        if not movie_copy.get('poster_url') and not movie_copy.get('poster') and movie_copy.get('id'):
            movie_copy['poster_url'] = get_poster_url(movie_copy['id'])

        processed_movies[movie_id] = movie_copy

    # Calculate stats
    total_count = len(movies_list)
    hidden_count = len(hidden)
    visible_count = total_count - hidden_count
    featured_count = len(featured)

    return render_template_string(
        ADMIN_TEMPLATE,
        movies=processed_movies,
        hidden=hidden,
        featured=featured,
        watch_link_overrides=watch_link_overrides,
        visible_count=visible_count,
        hidden_count=hidden_count,
        featured_count=featured_count
    )

@app.route('/toggle-hidden', methods=['POST'])
@auth.login_required
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
@auth.login_required
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
@auth.login_required
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

            # Regenerate data.json from movie_tracking.json
            try:
                result = subprocess.run(
                    ['python3', 'generate_data.py'],
                    capture_output=True,
                    text=True,
                    timeout=60  # 1 minute timeout
                )
                if result.returncode == 0:
                    return jsonify({'success': True, 'message': f'Date updated to {new_date} and data.json regenerated'})
                else:
                    return jsonify({'success': False, 'error': f'Date updated but regeneration failed: {result.stderr}'})
            except subprocess.TimeoutExpired:
                return jsonify({'success': False, 'error': 'Date updated but regeneration timed out'})
            except Exception as e:
                return jsonify({'success': False, 'error': f'Date updated but regeneration failed: {str(e)}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Movie not found'})

@app.route('/update-watch-links', methods=['POST'])
@auth.login_required
def update_watch_links():
    """Update watch link overrides for a movie"""
    data = request.json
    movie_id = data.get('movie_id')
    overrides = data.get('overrides', {})

    if not movie_id:
        return jsonify({'success': False, 'error': 'Movie ID required'})

    # Validate movie_id is numeric (TMDB ID)
    if not str(movie_id).isdigit():
        return jsonify({'success': False, 'error': 'Invalid movie ID: must be numeric TMDB ID'})

    # Load existing overrides
    all_overrides = load_json(WATCH_LINK_OVERRIDES_FILE, {})

    # Validate overrides structure
    validated_overrides = {}
    for category in ['streaming', 'rent', 'buy']:
        if category in overrides:
            override_data = overrides[category]

            # Validate structure
            if not isinstance(override_data, dict):
                return jsonify({'success': False, 'error': f'Invalid {category} override format'})

            if 'service' not in override_data or 'link' not in override_data:
                return jsonify({'success': False, 'error': f'{category} override missing service or link'})

            service = override_data['service'].strip()
            link = override_data['link'].strip()

            # Validate service name
            if not service:
                return jsonify({'success': False, 'error': f'{category} service name cannot be empty'})

            # Validate URL format
            if not link:
                return jsonify({'success': False, 'error': f'{category} link cannot be empty'})

            if not (link.startswith('http://') or link.startswith('https://')):
                return jsonify({'success': False, 'error': f'{category} link must start with http:// or https://'})

            validated_overrides[category] = {
                'service': service,
                'link': link
            }

    # Update or remove movie overrides
    if validated_overrides:
        all_overrides[movie_id] = validated_overrides
        message = f'Watch link overrides saved for {len(validated_overrides)} categor{"y" if len(validated_overrides) == 1 else "ies"}'
    else:
        # Remove movie from overrides if no categories provided
        if movie_id in all_overrides:
            del all_overrides[movie_id]
        message = 'Watch link overrides cleared'

    # Save updated overrides
    try:
        save_json(WATCH_LINK_OVERRIDES_FILE, all_overrides)
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to save: {str(e)}'})

@app.route('/regenerate', methods=['POST'])
@auth.login_required
def regenerate():
    """Manually trigger data.json regeneration"""
    try:
        result = subprocess.run(
            ['python3', 'generate_data.py'],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout (longer than date update)
        )

        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': 'data.json regenerated successfully',
                'output': result.stdout[-500:] if result.stdout else ''  # Last 500 chars
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Regeneration failed with exit code {result.returncode}',
                'stderr': result.stderr[-500:] if result.stderr else ''
            })
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Regeneration timed out after 2 minutes'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to trigger regeneration: {str(e)}'
        })

if __name__ == '__main__':
    print("\n🎬 New Release Wall Admin Panel")
    print("================================")
    print("Starting server at http://localhost:5555")
    print(f"\n🔐 Authentication enabled")
    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Password: {'*' * len(ADMIN_PASSWORD)}")
    if ADMIN_PASSWORD == 'changeme':
        print("\n⚠️  WARNING: Using default password!")
        print("   Set ADMIN_PASSWORD environment variable for production")
    print("\nPress Ctrl+C to stop\n")

    # Ensure admin directory exists
    os.makedirs('admin', exist_ok=True)

    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5555)
