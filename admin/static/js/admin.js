// Pending changes counter
let pendingChangesCount = 0;

function incrementPendingCount() {
    pendingChangesCount++;
    updatePendingBadge();
}

function resetPendingCount() {
    pendingChangesCount = 0;
    updatePendingBadge();
}

function updatePendingBadge() {
    const btn = document.getElementById('regenerate-btn');
    if (!btn) return;

    if (pendingChangesCount > 0) {
        btn.innerHTML = `💾 Save Changes (${pendingChangesCount})`;
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
        btn.classList.remove('saved');
    } else {
        btn.innerHTML = '✓ Saved';
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
        btn.classList.add('saved');
    }
}

function viewSite() {
    // Open the main site in a new tab (served by admin server at /site/)
    window.open('/site/', '_blank');
}

function showSuccess(message = 'Changes saved!') {
    const msg = document.getElementById('success-msg');
    msg.textContent = message;
    msg.style.display = 'block';
    setTimeout(() => {
        msg.style.display = 'none';
    }, 3000);
}

function toggleFeatured(movieId, feature) {
    fetch('/toggle-status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({movie_id: movieId, status_type: 'featured', value: feature})
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

            // Increment pending changes counter
            incrementPendingCount();

            showSuccess(feature ? 'Movie featured' : 'Movie unfeatured');
        }
    })
    .catch(error => {
        alert('Error: ' + error);
    });
}

function removeMovie(movieId, title) {
    if (!confirm(`Remove "${title}" from the New Arrivals Wall?\n\nThis will remove the movie from the site. It can be restored later by setting a new digital date.`)) {
        return;
    }

    fetch('/remove-movie', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ movie_id: movieId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove the card from the DOM
            const card = document.querySelector(`[data-movie-id="${movieId}"]`);
            if (card) {
                card.style.transition = 'opacity 0.3s, transform 0.3s';
                card.style.opacity = '0';
                card.style.transform = 'scale(0.9)';
                setTimeout(() => {
                    card.remove();
                    updateStats();
                }, 300);
            }

            incrementPendingCount();
            showSuccess(data.message || 'Movie removed');
        } else {
            alert(data.error || 'Failed to remove movie');
        }
    })
    .catch(error => {
        alert('Error: ' + error);
    });
}

function updateStats() {
    // Recalculate stats from current DOM state
    const featuredCards = document.querySelectorAll('.movie-card.featured');
    const featured = featuredCards.length;

    // Update stat displays
    document.getElementById('featured-count').textContent = featured;

    // Update issue counts
    updateIssueCounts();
}

function updateIssueCounts() {
    // Count issues by type from current DOM state
    const noTrailerCount = document.querySelectorAll('.movie-card[data-has-trailer="no"]').length;
    const noPosterCount = document.querySelectorAll('.movie-card[data-has-poster="no"]').length;
    const noWatchLinksCount = document.querySelectorAll('.movie-card[data-has-watch-links="no"]').length;
    const missingDataCount = document.querySelectorAll('.movie-card[data-missing-any="yes"]').length;

    // Update issue count displays
    const noTrailerElement = document.getElementById('no-trailer-count');
    const noPosterElement = document.getElementById('no-poster-count');
    const noWatchLinksElement = document.getElementById('no-watch-links-count');
    const missingDataElement = document.getElementById('missing-data-count');

    if (noTrailerElement) noTrailerElement.textContent = noTrailerCount;
    if (noPosterElement) noPosterElement.textContent = noPosterCount;
    if (noWatchLinksElement) noWatchLinksElement.textContent = noWatchLinksCount;
    if (missingDataElement) missingDataElement.textContent = missingDataCount;
}

function regenerateData() {
    const btn = document.getElementById('regenerate-btn');
    const status = document.getElementById('regenerate-status');

    // Disable button and show loading state
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.style.cursor = 'not-allowed';
    status.textContent = 'Saving changes... (this may take 10-30 seconds)';
    status.style.color = '#ffc107';

    fetch('/regenerate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            status.textContent = '✓ ' + (data.message || 'Changes saved!');
            status.style.color = '#28a745';
            showSuccess('Changes saved successfully');

            // Reset pending changes counter
            resetPendingCount();
        } else {
            status.textContent = '✗ ' + (data.error || 'Save failed');
            status.style.color = '#dc3545';
            alert('Save failed: ' + (data.error || 'Unknown error'));
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
        alert('Error saving changes: ' + error);

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
        if (btn.textContent.toLowerCase().includes(filter.replace('-', ' ')) ||
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
            case 'staff-picks':
                card.style.display = card.classList.contains('featured') ? 'block' : 'none';
                break;
            case 'no-trailer':
                card.style.display = card.dataset.hasTrailer === 'no' ? 'block' : 'none';
                break;
            case 'no-poster':
                card.style.display = card.dataset.hasPoster === 'no' ? 'block' : 'none';
                break;
            case 'no-watch-links':
                card.style.display = card.dataset.hasWatchLinks === 'no' ? 'block' : 'none';
                break;
            case 'missing-data':
                card.style.display = card.dataset.missingAny === 'yes' ? 'block' : 'none';
                break;
        }
    });

    // Sort all filters by date (most recent first)
    const grid = document.getElementById('movie-grid');
    const visibleCards = Array.from(cards).filter(card => card.style.display !== 'none');
    visibleCards.sort((a, b) => {
        const dateA = a.dataset.digitalDate || '0000-00-00';
        const dateB = b.dataset.digitalDate || '0000-00-00';
        return dateB.localeCompare(dateA); // Reverse order (most recent first)
    });
    visibleCards.forEach(card => grid.appendChild(card));
}

function searchMovies() {
    const searchBox = document.getElementById('search-box');
    const query = searchBox.value.toLowerCase();
    const cards = document.querySelectorAll('.movie-card');

    cards.forEach(card => {
        const title = card.dataset.title;
        if (title.includes(query)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}



function togglePlaylistForm() {
    const form = document.getElementById('playlist-form');
    const isHidden = form.style.display === 'none';
    form.style.display = isHidden ? 'block' : 'none';
}

function updateDateInputs() {
    const dateType = document.getElementById('playlist-date-type').value;
    const daysContainer = document.getElementById('days-input-container');
    const dateRangeContainer = document.getElementById('date-range-container');

    if (dateType === 'last_x_days') {
        daysContainer.style.display = 'block';
        dateRangeContainer.style.display = 'none';
    } else {
        daysContainer.style.display = 'none';
        dateRangeContainer.style.display = 'block';
    }
}

function saveAllFields(movieId) {
    const btn = event.target;
    const originalText = btn.innerHTML;

    // Collect all field values
    const digitalDate = document.getElementById(`digital-date-${movieId}`).value;
    const rtScore = document.getElementById(`rt-score-${movieId}`).value;
    const director = document.getElementById(`director-${movieId}`).value;
    const country = document.getElementById(`country-${movieId}`).value;
    const year = document.getElementById(`year-${movieId}`).value;
    const runtime = document.getElementById(`runtime-${movieId}`).value;
    const synopsis = document.getElementById(`synopsis-${movieId}`).value;

    // Get links from the universal system (check for existing values in hidden fields)
    const rtLink = document.getElementById(`rt-link-${movieId}`) ?
        document.getElementById(`rt-link-${movieId}`).value : '';
    const trailerLink = document.getElementById(`trailer-link-${movieId}`) ?
        document.getElementById(`trailer-link-${movieId}`).value : '';
    const posterUrl = document.getElementById(`poster-url-${movieId}`) ?
        document.getElementById(`poster-url-${movieId}`).value : '';
    const wikipediaLink = document.getElementById(`wikipedia-link-${movieId}`) ?
        document.getElementById(`wikipedia-link-${movieId}`).value : '';

    // Convert MM/DD date back to full ISO format for backend
    const digitalDateInput = document.getElementById(`digital-date-${movieId}`).value;
    let fullDigitalDate = '';
    if (digitalDateInput && digitalDateInput.includes('/')) {
        const [month, day] = digitalDateInput.split('/');
        const currentYear = new Date().getFullYear();
        fullDigitalDate = `${currentYear}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    }

    // Collect watch links - streaming and VOD separate
    const streamingService = document.getElementById(`streaming-service-${movieId}`) ?
        document.getElementById(`streaming-service-${movieId}`).value : '';
    const streamingLink = document.getElementById(`streaming-link-${movieId}`) ?
        document.getElementById(`streaming-link-${movieId}`).value : '';
    const vodService = document.getElementById(`vod-service-${movieId}`) ?
        document.getElementById(`vod-service-${movieId}`).value : '';
    const vodLink = document.getElementById(`vod-link-${movieId}`) ?
        document.getElementById(`vod-link-${movieId}`).value : '';

    // Build watch links object
    const watchLinks = {};
    if (streamingService && streamingLink) {
        watchLinks.streaming = {service: streamingService, link: streamingLink};
    }
    if (vodService && vodLink) {
        // VOD is a single category (not separate rent/buy anymore)
        watchLinks.vod = {service: vodService, link: vodLink};
    }

    // Disable button
    btn.disabled = true;
    btn.innerHTML = '⏳ Saving...';

    // Send to server
    fetch('/update-movie-fields', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            movie_id: movieId,
            digital_date: fullDigitalDate || null,
            rt_score: rtScore ? parseInt(rtScore) : null,
            rt_link: rtLink.trim() || null,
            trailer_link: trailerLink.trim() || null,
            wikipedia_link: wikipediaLink.trim() || null,
            director: director.trim() || null,
            country: country.trim() || null,
            year: year ? parseInt(year) : null,
            runtime: runtime ? parseInt(runtime) : null,
            synopsis: synopsis.trim() || null,
            poster_url: posterUrl.trim() || null,
            watch_links: Object.keys(watchLinks).length > 0 ? watchLinks : null
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            btn.innerHTML = '✅ Saved!';
            btn.style.background = '#28a745';
            showSuccess(data.message || 'All fields updated successfully!');

            // Increment pending changes counter
            incrementPendingCount();

            // Update field backgrounds to show they're no longer missing
            if (rtScore) document.getElementById(`rt-score-${movieId}`).style.background = '#2a2a2a';
            if (rtLink) document.getElementById(`rt-link-${movieId}`).style.background = '#2a2a2a';
            if (trailerLink) document.getElementById(`trailer-link-${movieId}`).style.background = '#2a2a2a';
            if (director) document.getElementById(`director-${movieId}`).style.background = '#2a2a2a';
            if (country) document.getElementById(`country-${movieId}`).style.background = '#2a2a2a';
            if (posterUrl) document.getElementById(`poster-url-${movieId}`).style.background = '#2a2a2a';

            // Reset button after 2 seconds
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }, 2000);
        } else {
            btn.innerHTML = '❌ Failed';
            btn.style.background = '#dc3545';
            alert(data.error || 'Failed to update fields');

            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.style.background = '#28a745';
                btn.disabled = false;
            }, 2000);
        }
    })
    .catch(error => {
        btn.innerHTML = '❌ Error';
        alert('Error updating fields: ' + error);
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }, 2000);
    });
}

function createYouTubePlaylist() {
    const btn = document.getElementById('create-playlist-btn');
    const status = document.getElementById('playlist-status');
    const result = document.getElementById('playlist-result');

    // Collect form data
    const dateType = document.getElementById('playlist-date-type').value;
    const days = document.getElementById('playlist-days').value;
    const fromDate = document.getElementById('playlist-from-date').value;
    const toDate = document.getElementById('playlist-to-date').value;
    const title = document.getElementById('playlist-title').value.trim();
    const privacy = document.getElementById('playlist-privacy').value;
    const dryRun = document.getElementById('playlist-dry-run').checked;

    // Validate inputs
    if (dateType === 'last_x_days' && (!days || days < 1)) {
        alert('Please enter a valid number of days');
        return;
    }

    if (dateType === 'date_range' && (!fromDate || !toDate)) {
        alert('Please select both from and to dates');
        return;
    }

    if (dateType === 'date_range' && fromDate > toDate) {
        alert('From date must be before to date');
        return;
    }

    // Disable button and show loading state
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.style.cursor = 'not-allowed';
    status.textContent = dryRun ? 'Generating preview...' : 'Creating playlist... (this may take 30-60 seconds)';
    status.style.color = '#ffc107';
    result.style.display = 'none';

    // Build request body
    const requestBody = {
        date_type: dateType,
        privacy: privacy,
        dry_run: dryRun
    };

    if (title) {
        requestBody.title = title;
    }

    if (dateType === 'last_x_days') {
        requestBody.days_back = parseInt(days);
    } else {
        requestBody.from_date = fromDate;
        requestBody.to_date = toDate;
    }

    // Send request
    fetch('/create-youtube-playlist', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            status.textContent = dryRun ? '✓ Preview generated' : '✓ Playlist created successfully!';
            status.style.color = '#28a745';

            // Show result
            result.style.display = 'block';
            let html = `<div style="color: #fff;">`;

            if (data.title) {
                html += `<strong>Title:</strong> ${data.title}<br>`;
            }

            if (data.video_count !== undefined) {
                html += `<strong>Videos:</strong> ${data.video_count}<br>`;
            }

            if (data.date_range) {
                html += `<strong>Date Range:</strong> ${data.date_range}<br>`;
            }

            if (data.playlist_url) {
                html += `<br><a href="${data.playlist_url}" target="_blank" style="color: #66b3ff; text-decoration: underline;">🔗 View Playlist on YouTube</a><br>`;
            }

            if (data.preview_videos && data.preview_videos.length > 0) {
                html += `<br><strong>Preview (first 5 videos):</strong><br>`;
                html += `<ul style="margin: 0.5rem 0; padding-left: 1.5rem; color: #ccc;">`;
                data.preview_videos.forEach(video => {
                    html += `<li style="margin: 0.3rem 0;">${video}</li>`;
                });
                html += `</ul>`;
            }

            if (data.message) {
                html += `<br><em style="color: #999;">${data.message}</em>`;
            }

            html += `</div>`;
            result.innerHTML = html;

            showSuccess(dryRun ? 'Preview generated' : 'Playlist created!');
        } else {
            status.textContent = '✗ ' + (data.error || 'Failed to create playlist');
            status.style.color = '#dc3545';
            result.style.display = 'block';
            result.innerHTML = `<div style="color: #ff6b6b;">${data.error || 'Unknown error'}</div>`;
        }

        // Re-enable button
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
    })
    .catch(error => {
        status.textContent = '✗ Error: ' + error;
        status.style.color = '#dc3545';

        // Re-enable button
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
    });
}

// Editorial Ordering Functions - Always enabled, auto-saves on drop

function saveOrdering() {
    const grid = document.getElementById('movie-grid');
    const orderedIds = Array.from(grid.children).map(card => card.dataset.movieId);

    fetch('/update-ordering', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            ordered_ids: orderedIds
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Mark cards as pinned
            updatePinnedIndicators(orderedIds);

            // Increment pending changes counter
            incrementPendingCount();

            showSuccess('Order updated');
        } else {
            alert('Failed to save ordering: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        alert('Error saving ordering: ' + error);
    });
}

function updatePinnedIndicators(orderedIds) {
    // Remove all pinned indicators
    document.querySelectorAll('.movie-card').forEach(card => {
        card.classList.remove('pinned-order');
    });

    // Add pinned indicators for ordered movies
    orderedIds.forEach(movieId => {
        const card = document.querySelector(`[data-movie-id="${movieId}"]`);
        if (card) {
            card.classList.add('pinned-order');
        }
    });
}

function enableDragAndDrop() {
    const cards = document.querySelectorAll('.movie-card');

    cards.forEach(card => {
        card.addEventListener('dragstart', handleDragStart);
        card.addEventListener('dragend', handleDragEnd);
        card.addEventListener('dragover', handleDragOver);
        card.addEventListener('dragenter', handleDragEnter);
        card.addEventListener('dragleave', handleDragLeave);
        card.addEventListener('drop', handleDrop);
    });
}

let draggedElement = null;

function handleDragStart(e) {
    draggedElement = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', this.outerHTML);
}

function handleDragEnd(e) {
    this.classList.remove('dragging');

    // Clean up all drag-over classes
    document.querySelectorAll('.movie-card').forEach(card => {
        card.classList.remove('drag-over');
    });

    draggedElement = null;
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }

    e.dataTransfer.dropEffect = 'move';
    return false;
}

function handleDragEnter(e) {
    if (this !== draggedElement) {
        this.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    this.classList.remove('drag-over');
}

function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }

    if (draggedElement !== this) {
        // Get the grid and all cards
        const grid = document.getElementById('movie-grid');
        const cards = Array.from(grid.children);
        const draggedIndex = cards.indexOf(draggedElement);
        const targetIndex = cards.indexOf(this);

        // Remove dragged element from its current position
        grid.removeChild(draggedElement);

        // Insert it at the new position
        if (targetIndex < draggedIndex) {
            // Insert before target
            grid.insertBefore(draggedElement, this);
        } else {
            // Insert after target
            if (this.nextSibling) {
                grid.insertBefore(draggedElement, this.nextSibling);
            } else {
                grid.appendChild(draggedElement);
            }
        }

        // Auto-save the new order
        saveOrdering();
    }

    this.classList.remove('drag-over');
    return false;
}

// Add Movie Modal Functions
function showAddMovieModal() {
    const modal = document.getElementById('add-movie-modal');
    modal.style.display = 'flex';

    // Clear search field and results
    document.getElementById('add-movie-search').value = '';
    document.getElementById('tmdb-search-status').textContent = '';
    document.getElementById('tmdb-search-results').innerHTML = '';

    // Focus search field
    setTimeout(() => {
        document.getElementById('add-movie-search').focus();
    }, 100);
}

function hideAddMovieModal() {
    const modal = document.getElementById('add-movie-modal');
    modal.style.display = 'none';

    // Reset to step 1
    document.getElementById('add-movie-step1').style.display = 'block';
    document.getElementById('add-movie-step2').style.display = 'none';
    selectedMovieData = null;
}

function searchTMDB() {
    const query = document.getElementById('add-movie-search').value.trim();
    const status = document.getElementById('tmdb-search-status');
    const results = document.getElementById('tmdb-search-results');
    const btn = document.getElementById('search-tmdb-btn');

    if (!query) {
        status.textContent = 'Enter a movie title to search';
        status.style.color = '#dc3545';
        return;
    }

    if (query.length < 2) {
        status.textContent = 'Enter at least 2 characters';
        status.style.color = '#dc3545';
        return;
    }

    // Show loading state
    btn.disabled = true;
    btn.textContent = '⏳';
    status.textContent = 'Searching...';
    status.style.color = '#ffc107';
    results.innerHTML = '';

    fetch(`/search-tmdb?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            btn.disabled = false;
            btn.textContent = '🔍 Search';

            if (data.success) {
                if (data.results.length === 0) {
                    status.textContent = 'No movies found. Try a different search.';
                    status.style.color = '#ffc107';
                    return;
                }

                status.textContent = `Found ${data.results.length} result${data.results.length > 1 ? 's' : ''} - click to add:`;
                status.style.color = '#28a745';

                // Render results
                results.innerHTML = data.results.map(movie => `
                    <div class="tmdb-result" onclick="addMovieFromSearch(${movie.id}, '${movie.title.replace(/'/g, "\\'")}', '${movie.year || ''}', '${movie.poster_url || ''}')">
                        <div class="tmdb-result-poster">
                            ${movie.poster_url
                                ? `<img src="${movie.poster_url}" alt="${movie.title}">`
                                : '<div class="no-poster-small">No Poster</div>'}
                        </div>
                        <div class="tmdb-result-info">
                            <div class="tmdb-result-title">${movie.title}</div>
                            <div class="tmdb-result-year">${movie.year || 'Year unknown'}</div>
                            ${movie.overview ? `<div class="tmdb-result-overview">${movie.overview}</div>` : ''}
                        </div>
                    </div>
                `).join('');
            } else {
                status.textContent = data.error || 'Search failed';
                status.style.color = '#dc3545';
            }
        })
        .catch(error => {
            btn.disabled = false;
            btn.textContent = '🔍 Search';
            status.textContent = 'Error: ' + error;
            status.style.color = '#dc3545';
        });
}

// Store selected movie info for step 2
let selectedMovieData = null;

// Smart URL-to-service detection
function detectServiceFromUrl() {
    const url = document.getElementById('add-movie-watch-url').value.trim();
    const detected = document.getElementById('detected-service');

    if (!url) {
        detected.textContent = '';
        return null;
    }

    // Map of URL patterns to service names
    const servicePatterns = [
        { pattern: /vimeo\.com/i, service: 'VIMEO', type: 'vod' },
        { pattern: /amazon\.(com|co\.|ca|de|fr|it|es)/i, service: 'AMAZON', type: 'vod' },
        { pattern: /itunes\.apple\.com|tv\.apple\.com/i, service: 'APPLE', type: 'vod' },
        { pattern: /play\.google\.com|youtube\.com\/watch/i, service: 'GOOGLE', type: 'vod' },
        { pattern: /vudu\.com/i, service: 'VUDU', type: 'vod' },
        { pattern: /fandangonow\.com/i, service: 'FANDANGO', type: 'vod' },
        { pattern: /microsoft\.com|xbox\.com/i, service: 'MICROSOFT', type: 'vod' },
        { pattern: /netflix\.com/i, service: 'NETFLIX', type: 'streaming' },
        { pattern: /hulu\.com/i, service: 'HULU', type: 'streaming' },
        { pattern: /disneyplus\.com|disney\+/i, service: 'DISNEY+', type: 'streaming' },
        { pattern: /max\.com|hbomax\.com/i, service: 'MAX', type: 'streaming' },
        { pattern: /peacock/i, service: 'PEACOCK', type: 'streaming' },
        { pattern: /paramountplus\.com/i, service: 'PARAMOUNT+', type: 'streaming' },
        { pattern: /mubi\.com/i, service: 'MUBI', type: 'streaming' },
        { pattern: /criterion/i, service: 'CRITERION', type: 'streaming' },
        { pattern: /kanopy\.com/i, service: 'KANOPY', type: 'streaming' },
        { pattern: /tubi/i, service: 'TUBI', type: 'streaming' },
        { pattern: /pluto/i, service: 'PLUTO', type: 'streaming' },
        { pattern: /shudder/i, service: 'SHUDDER', type: 'streaming' },
    ];

    for (const { pattern, service, type } of servicePatterns) {
        if (pattern.test(url)) {
            detected.innerHTML = `Detected: <strong>${service}</strong> (${type === 'streaming' ? 'Streaming' : 'Rent/Buy'})`;
            detected.style.color = '#28a745';
            return { service, type, url };
        }
    }

    // Unknown service - try to extract domain name
    try {
        const domain = new URL(url).hostname.replace('www.', '').split('.')[0].toUpperCase();
        detected.innerHTML = `Service: <strong>${domain}</strong> (custom)`;
        detected.style.color = '#ffc107';
        return { service: domain, type: 'vod', url };
    } catch {
        detected.textContent = 'Enter a valid URL';
        detected.style.color = '#dc3545';
        return null;
    }
}

function addMovieFromSearch(tmdbId, title, year, posterUrl) {
    // Store selected movie data
    selectedMovieData = { tmdbId, title, year, posterUrl };

    // Hide step 1, show step 2
    document.getElementById('add-movie-step1').style.display = 'none';
    document.getElementById('add-movie-step2').style.display = 'block';

    // Populate selected movie info
    document.getElementById('selected-movie-title').textContent = title;
    document.getElementById('selected-movie-year').textContent = year || 'Year unknown';
    const posterImg = document.getElementById('selected-movie-poster');
    if (posterUrl) {
        posterImg.src = posterUrl;
        posterImg.style.display = 'block';
    } else {
        posterImg.style.display = 'none';
    }

    // Set default date to today
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('add-movie-date').value = today;

    // Clear watch link field
    document.getElementById('add-movie-watch-url').value = '';
    document.getElementById('detected-service').textContent = '';
    document.getElementById('add-movie-status').textContent = '';
}

function goBackToSearch() {
    document.getElementById('add-movie-step2').style.display = 'none';
    document.getElementById('add-movie-step1').style.display = 'block';
    selectedMovieData = null;
}

function confirmAddMovie() {
    if (!selectedMovieData) return;

    const { tmdbId, title } = selectedMovieData;
    const status = document.getElementById('add-movie-status');
    const btn = document.getElementById('confirm-add-btn');

    // Get watch link info
    const watchUrl = document.getElementById('add-movie-watch-url').value.trim();
    const serviceInfo = watchUrl ? detectServiceFromUrl() : null;

    // Show adding state
    status.textContent = `Adding "${title}"...`;
    status.style.color = '#ffc107';
    btn.disabled = true;
    btn.textContent = 'Adding...';

    // Build request body
    const requestBody = { tmdb_id: tmdbId };

    // Add release date if specified
    const releaseDate = document.getElementById('add-movie-date').value;
    if (releaseDate) {
        requestBody.digital_date = releaseDate;
    }

    if (serviceInfo) {
        requestBody.watch_link = {
            service: serviceInfo.service,
            type: serviceInfo.type,
            url: serviceInfo.url
        };
    }

    fetch('/add-movie', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        btn.disabled = false;
        btn.textContent = 'Add Movie';

        if (data.success) {
            status.textContent = `"${title}" added!`;
            status.style.color = '#28a745';

            incrementPendingCount();
            showSuccess(`"${title}" added successfully!`);

            setTimeout(() => {
                hideAddMovieModal();
                window.location.reload();
            }, 1500);
        } else {
            status.textContent = data.error || 'Failed to add movie';
            status.style.color = '#dc3545';
        }
    })
    .catch(error => {
        btn.disabled = false;
        btn.textContent = 'Add Movie';
        status.textContent = 'Error: ' + error;
        status.style.color = '#dc3545';
    });
}

// Close modal when clicking outside content
document.addEventListener('click', function(event) {
    const modal = document.getElementById('add-movie-modal');
    if (event.target === modal) {
        hideAddMovieModal();
    }
});

// Close modal with Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const modal = document.getElementById('add-movie-modal');
        if (modal.style.display === 'flex') {
            hideAddMovieModal();
        }
    }
});

// Character Counter and Validation Functions
function updateCharCounter(textarea, counterId, minLength, maxLength) {
    const counter = document.getElementById(counterId);
    const warning = document.getElementById(counterId.replace('-counter-', '-warning-'));

    if (!counter) return;

    const currentLength = textarea.value.length;
    const fieldType = counterId.includes('synopsis') ? 'synopsis' : 'text';

    // Update counter display
    counter.textContent = `${currentLength}/${maxLength}`;

    // Remove existing classes
    counter.classList.remove('warning', 'error');

    // Check for issues
    const issues = validateText(textarea.value, minLength, maxLength, fieldType);

    if (issues.length > 0) {
        if (currentLength > maxLength * 0.9) {
            counter.classList.add('warning');
        }

        if (issues.some(issue => issue.level === 'error')) {
            counter.classList.add('error');
        }

        // Show warnings
        if (warning) {
            warning.style.display = 'block';
            warning.innerHTML = issues.map(issue => issue.message).join('<br>');
            warning.className = issues.some(issue => issue.level === 'error') ? 'validation-error' : 'validation-warning';
        }
    } else {
        // Hide warnings
        if (warning) {
            warning.style.display = 'none';
        }
    }
}

function validateText(text, minLength, maxLength, fieldType) {
    const issues = [];
    const length = text.length;

    // Length validation
    if (length > 0 && length < minLength) {
        issues.push({
            level: 'warning',
            message: `${fieldType} is quite short (recommended: ${minLength}+ characters)`
        });
    }

    if (length > maxLength * 0.9) {
        issues.push({
            level: 'warning',
            message: `Approaching character limit (${length}/${maxLength})`
        });
    }

    if (length > maxLength) {
        issues.push({
            level: 'error',
            message: `Exceeds character limit! (${length}/${maxLength})`
        });
    }

    // Basic formatting checks
    if (text.includes('<') && text.includes('>')) {
        issues.push({
            level: 'warning',
            message: 'Possible HTML tags detected - these will be displayed as text'
        });
    }

    // Check for excessive line breaks
    const lineBreaks = (text.match(/\n/g) || []).length;
    if (lineBreaks > 10) {
        issues.push({
            level: 'warning',
            message: 'Many line breaks detected - consider condensing'
        });
    }

    return issues;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize pending changes count from server
    fetch('/pending-changes')
        .then(response => response.json())
        .then(data => {
            if (data.has_pending_changes) {
                // Initialize count from server (default to 1 if count not present for backward compatibility)
                pendingChangesCount = data.pending_change_count || 1;
                updatePendingBadge();
            }
        })
        .catch(error => {
            console.error('Failed to fetch pending changes:', error);
        });

    // Initialize Save Changes button state
    updatePendingBadge();

    // Enable drag and drop for ordering (always on)
    enableDragAndDrop();

    // Initialize synopsis counters
    document.querySelectorAll('[id^="synopsis-"]').forEach(textarea => {
        if (textarea.tagName === 'TEXTAREA') {
            const movieId = textarea.id.replace('synopsis-', '');
            const counterId = `synopsis-counter-${movieId}`;
            updateCharCounter(textarea, counterId, 140, 600);
        }
    });
});

// Metadata save function (director, country, runtime)
function saveMetadata(movieId) {
    const saveBtn = document.getElementById(`save-metadata-${movieId}`);
    const director = document.getElementById(`director-${movieId}`).value.trim();
    const country = document.getElementById(`country-${movieId}`).value.trim();
    const runtime = document.getElementById(`runtime-${movieId}`).value.trim();

    // Show saving state
    saveBtn.disabled = true;
    saveBtn.innerHTML = '⏳';

    fetch('/update-movie-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            movie_id: movieId,
            director: director || null,
            country: country || null,
            runtime: runtime ? parseInt(runtime) : null
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update field backgrounds
            const directorInput = document.getElementById(`director-${movieId}`);
            const countryInput = document.getElementById(`country-${movieId}`);

            if (director && director !== 'Unknown') {
                directorInput.classList.remove('missing');
                directorInput.style.background = '#2a2a2a';
            }
            if (country) {
                countryInput.classList.remove('missing');
                countryInput.style.background = '#2a2a2a';
            }

            // Update data attributes for filtering
            const card = document.querySelector(`[data-movie-id="${movieId}"]`);
            if (card) {
                card.dataset.hasDirector = (director && director !== 'Unknown') ? 'yes' : 'no';
                card.dataset.hasCountry = country ? 'yes' : 'no';
                updateMissingAnyAttribute(card);
            }

            incrementPendingCount();
            saveBtn.innerHTML = '✓';
            showSuccess('Metadata saved');
        } else {
            saveBtn.innerHTML = '❌';
            alert(data.error || 'Failed to save');
        }

        setTimeout(() => {
            saveBtn.innerHTML = '💾';
            saveBtn.disabled = false;
        }, 1000);
    })
    .catch(error => {
        saveBtn.innerHTML = '❌';
        alert('Error: ' + error);
        setTimeout(() => {
            saveBtn.innerHTML = '💾';
            saveBtn.disabled = false;
        }, 1000);
    });
}

// Link editing interface
let currentLinkModes = {}; // Track which link type is active for each movie

function setLinkMode(movieId, linkType) {
    // Update current mode
    currentLinkModes[movieId] = linkType;

    // Update button states
    const buttons = document.querySelectorAll(`[onclick*="setLinkMode('${movieId}',"]`);
    buttons.forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    // Get current value for this link type
    let currentValue = '';
    const indicator = document.getElementById(`link-mode-indicator-${movieId}`);
    const input = document.getElementById(`universal-link-${movieId}`);
    const saveBtn = document.getElementById(`save-link-${movieId}`);

    switch(linkType) {
        case 'trailer':
            const trailerField = document.getElementById(`trailer-link-${movieId}`);
            if (trailerField) {
                currentValue = trailerField.value;
            }
            input.placeholder = 'https://www.youtube.com/watch?v=...';
            indicator.textContent = '▶️ Editing trailer link';
            break;
        case 'rt':
            const rtField = document.getElementById(`rt-link-${movieId}`);
            if (rtField) {
                currentValue = rtField.value;
            }
            input.placeholder = 'https://www.rottentomatoes.com/m/...';
            indicator.textContent = '🍅 Editing RT link';
            break;
        case 'poster':
            const posterField = document.getElementById(`poster-url-${movieId}`);
            if (posterField) {
                currentValue = posterField.value;
            }
            input.placeholder = 'https://image.tmdb.org/t/p/w500/...';
            indicator.textContent = '🖼️ Editing poster URL';
            break;
        case 'wikipedia':
            const wikiField = document.getElementById(`wikipedia-link-${movieId}`);
            if (wikiField) {
                currentValue = wikiField.value;
            }
            input.placeholder = 'https://en.wikipedia.org/wiki/...';
            indicator.textContent = '📚 Editing Wikipedia link';
            break;
    }

    // Set current value and enable editing
    input.value = currentValue;
    input.readOnly = false;
    input.style.background = '#2a2a2a';
    saveBtn.disabled = false;
    saveBtn.style.opacity = '1';

    // Focus the input
    input.focus();
}

function saveLinkField(movieId) {
    const linkType = currentLinkModes[movieId];
    if (!linkType) return;

    const input = document.getElementById(`universal-link-${movieId}`);
    const saveBtn = document.getElementById(`save-link-${movieId}`);
    const newValue = input.value.trim();

    // Build the request body based on link type
    const requestBody = { movie_id: movieId };
    switch(linkType) {
        case 'trailer':
            requestBody.trailer_link = newValue || null;
            break;
        case 'rt':
            requestBody.rt_link = newValue || null;
            break;
        case 'poster':
            requestBody.poster_url = newValue || null;
            break;
        case 'wikipedia':
            requestBody.wikipedia_link = newValue || null;
            break;
    }

    // Show saving state
    saveBtn.disabled = true;
    saveBtn.innerHTML = '⏳';

    // POST directly to server
    fetch('/update-movie-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update button color based on whether link exists
            const button = document.querySelector(`[onclick*="setLinkMode('${movieId}', '${linkType}')"]`);
            if (button) {
                button.classList.remove('link-good', 'link-bad');
                button.classList.add(newValue ? 'link-good' : 'link-bad');
            }

            // Update data attributes so Missing Data filter updates
            const card = document.querySelector(`[data-movie-id="${movieId}"]`);
            if (card) {
                if (linkType === 'trailer') {
                    card.dataset.hasTrailer = newValue ? 'yes' : 'no';
                } else if (linkType === 'poster') {
                    card.dataset.hasPoster = newValue ? 'yes' : 'no';
                }
                // Recalculate missing-any
                updateMissingAnyAttribute(card);
            }

            // Increment pending changes counter
            incrementPendingCount();

            // Show success
            saveBtn.innerHTML = '✓';
            showSuccess(data.message || `${linkType} link saved`);
        } else {
            saveBtn.innerHTML = '❌';
            alert(data.error || 'Failed to save');
        }

        // Reset interface after delay
        setTimeout(() => {
            resetLinkInterface(movieId, saveBtn);
        }, 1000);
    })
    .catch(error => {
        saveBtn.innerHTML = '❌';
        alert('Error saving: ' + error);
        setTimeout(() => {
            resetLinkInterface(movieId, saveBtn);
        }, 1000);
    });
}

function resetLinkInterface(movieId, saveBtn) {
    const input = document.getElementById(`universal-link-${movieId}`);
    const indicator = document.getElementById(`link-mode-indicator-${movieId}`);

    input.readOnly = true;
    input.style.background = '#1a1a1a';
    input.value = '';
    input.placeholder = 'Select a button above to edit that link...';

    saveBtn.disabled = true;
    saveBtn.style.opacity = '0.6';
    saveBtn.innerHTML = '💾';

    indicator.textContent = 'Click a button above to edit that link';

    // Remove active state from buttons
    const buttons = document.querySelectorAll(`[onclick*="setLinkMode('${movieId}',"]`);
    buttons.forEach(btn => btn.classList.remove('active'));

    // Clear current mode
    delete currentLinkModes[movieId];
}

function updateMissingAnyAttribute(card) {
    const hasTrailer = card.dataset.hasTrailer === 'yes';
    const hasPoster = card.dataset.hasPoster === 'yes';
    const hasDirector = card.dataset.hasDirector === 'yes';
    const hasCountry = card.dataset.hasCountry === 'yes';

    const missingAny = !hasTrailer || !hasPoster || !hasDirector || !hasCountry;
    card.dataset.missingAny = missingAny ? 'yes' : 'no';

    // Update issue counts
    updateIssueCounts();
}

// Watch service editing interface
let currentWatchModes = {}; // Track which service type is active for each movie

function setWatchService(movieId, serviceType, serviceName) {
    // Update current mode
    currentWatchModes[movieId] = {type: serviceType, service: serviceName};

    // Update button states for this service type
    const buttons = document.querySelectorAll(`[onclick*="setWatchService('${movieId}', '${serviceType}',"]`);
    buttons.forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    // Get current value for this service
    let currentValue = '';
    const input = document.getElementById(`${serviceType}-link-${movieId}`);
    const saveBtn = document.getElementById(`save-${serviceType}-${movieId}`);

    if (serviceName === 'ADD') {
        // Custom service - let user type it in
        currentValue = '';
        input.placeholder = `Enter link for custom ${serviceType} service...`;
    } else {
        // Pre-defined service - load existing link if available
        const existingLinks = getExistingWatchLinks(movieId, serviceType);
        currentValue = existingLinks[serviceName] || '';
        input.placeholder = `Enter ${serviceName} link...`;
    }

    // Set current value and enable editing
    input.value = currentValue;
    input.readOnly = false;
    input.style.background = '#2a2a2a';
    saveBtn.disabled = false;
    saveBtn.style.opacity = '1';

    // Focus the input
    input.focus();
}

function getExistingWatchLinks(movieId, serviceType) {
    // This would ideally get current values from the form fields
    // For now, return empty object - values will be loaded from template
    return {};
}

function saveWatchService(movieId) {
    const watchMode = currentWatchModes[movieId];
    if (!watchMode) return;

    const {type: serviceType, service: serviceName} = watchMode;
    const input = document.getElementById(`${serviceType}-link-${movieId}`);
    const saveBtn = document.getElementById(`save-${serviceType}-${movieId}`);
    const newValue = input.value.trim();

    // Build watch_links object for the request
    const actualServiceName = serviceName === 'ADD' ? 'Custom' : serviceName;
    const watchLinks = {};
    watchLinks[serviceType] = {
        service: actualServiceName,
        link: newValue || null
    };

    const requestBody = {
        movie_id: movieId,
        watch_links: watchLinks
    };

    // Show saving state
    saveBtn.disabled = true;
    saveBtn.innerHTML = '⏳';

    // POST directly to server
    fetch('/update-movie-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update button color based on whether link exists
            const button = document.querySelector(`[onclick*="setWatchService('${movieId}', '${serviceType}', '${serviceName}')"]`);
            if (button && serviceName !== 'ADD') {
                button.classList.remove('link-good', 'link-bad');
                button.classList.add(newValue ? 'link-good' : 'link-bad');
            }

            // Update data attributes so Missing Data filter updates
            const card = document.querySelector(`[data-movie-id="${movieId}"]`);
            if (card) {
                // Check if we now have watch links
                const hasWatchLinks = newValue ? 'yes' : card.dataset.hasWatchLinks;
                card.dataset.hasWatchLinks = hasWatchLinks;
            }

            // Increment pending changes counter
            incrementPendingCount();

            // Show success
            saveBtn.innerHTML = '✓';
            showSuccess(data.message || `${serviceType} link saved`);
        } else {
            saveBtn.innerHTML = '❌';
            alert(data.error || 'Failed to save');
        }

        // Reset interface after delay
        setTimeout(() => {
            resetWatchInterface(movieId, serviceType, saveBtn);
        }, 1000);
    })
    .catch(error => {
        saveBtn.innerHTML = '❌';
        alert('Error saving: ' + error);
        setTimeout(() => {
            resetWatchInterface(movieId, serviceType, saveBtn);
        }, 1000);
    });
}

function resetWatchInterface(movieId, serviceType, saveBtn) {
    const input = document.getElementById(`${serviceType}-link-${movieId}`);

    input.readOnly = true;
    input.style.background = '#1a1a1a';
    input.value = '';
    input.placeholder = 'Select service above to add link...';

    saveBtn.disabled = true;
    saveBtn.style.opacity = '0.6';
    saveBtn.innerHTML = '💾';

    // Remove active state from buttons
    const buttons = document.querySelectorAll(`[onclick*="setWatchService('${movieId}', '${serviceType}',"]`);
    buttons.forEach(btn => btn.classList.remove('active'));

    // Clear current mode
    delete currentWatchModes[movieId];
}

// Health banner - copy details and dismiss
function copyAndDismissHealth() {
    const detailsEl = document.getElementById('health-details');
    const bannerEl = document.getElementById('health-banner');

    if (detailsEl) {
        // Copy to clipboard
        detailsEl.select();
        document.execCommand('copy');

        // Also try modern clipboard API
        if (navigator.clipboard) {
            navigator.clipboard.writeText(detailsEl.value).catch(() => {});
        }
    }

    // Hide banner
    if (bannerEl) {
        bannerEl.style.display = 'none';
    }

    // Set session flag via API
    fetch('/dismiss-health', { method: 'POST' }).catch(() => {});

    // Brief feedback
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '✓ Copied!';
    setTimeout(() => { btn.innerHTML = originalText; }, 1500);
}