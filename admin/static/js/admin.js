function showSuccess(message = 'Changes saved!') {
    const msg = document.getElementById('success-msg');
    msg.textContent = message;
    msg.style.display = 'block';
    setTimeout(() => {
        msg.style.display = 'none';
    }, 3000);
}

function toggleHidden(movieId, hide) {
    fetch('/toggle-status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({movie_id: movieId, status_type: 'hidden', value: hide})
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
    fetch('/toggle-status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
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

            showSuccess(feature ? 'Movie featured' : 'Movie unfeatured');
        }
    })
    .catch(error => {
        alert('Error: ' + error);
    });
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

    // Update reviewed count
    updateReviewedCount();
}

function updateReviewedCount() {
    // Recalculate reviewed count from current DOM state
    const reviewedCards = document.querySelectorAll('.movie-card[data-has-review="yes"]');
    const reviewedCount = reviewedCards.length;

    // Update reviewed count display
    document.getElementById('reviewed-count').textContent = reviewedCount;
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
            case 'no-trailer':
                card.style.display = card.dataset.hasTrailer === 'no' ? 'block' : 'none';
                break;
            case 'no-poster':
                card.style.display = card.dataset.hasPoster === 'no' ? 'block' : 'none';
                break;
            case 'missing-data':
                card.style.display = card.dataset.missingAny === 'yes' ? 'block' : 'none';
                break;
            case 'reviewed':
                card.style.display = card.dataset.hasReview === 'yes' ? 'block' : 'none';
                break;
        }
    });
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
    const rtLink = document.getElementById(`rt-link-${movieId}`).value;
    const trailerLink = document.getElementById(`trailer-link-${movieId}`).value;
    const director = document.getElementById(`director-${movieId}`).value;
    const country = document.getElementById(`country-${movieId}`).value;
    const synopsis = document.getElementById(`synopsis-${movieId}`).value;
    const posterUrl = document.getElementById(`poster-url-${movieId}`).value;

    // Collect watch links
    const streamingService = document.getElementById(`streaming-service-${movieId}`).value;
    const streamingLink = document.getElementById(`streaming-link-${movieId}`).value;
    const rentService = document.getElementById(`rent-service-${movieId}`).value;
    const rentLink = document.getElementById(`rent-link-${movieId}`).value;
    const buyService = document.getElementById(`buy-service-${movieId}`).value;
    const buyLink = document.getElementById(`buy-link-${movieId}`).value;

    // Build watch links object
    const watchLinks = {};
    if (streamingService && streamingLink) {
        watchLinks.streaming = {service: streamingService, link: streamingLink};
    }
    if (rentService && rentLink) {
        watchLinks.rent = {service: rentService, link: rentLink};
    }
    if (buyService && buyLink) {
        watchLinks.buy = {service: buyService, link: buyLink};
    }

    // Disable button
    btn.disabled = true;
    btn.innerHTML = '⏳ Saving...';

    // Send to server
    fetch('/update-movie-fields', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            movie_id: movieId,
            digital_date: digitalDate || null,
            rt_score: rtScore ? parseInt(rtScore) : null,
            rt_link: rtLink.trim() || null,
            trailer_link: trailerLink.trim() || null,
            director: director.trim() || null,
            country: country.trim() || null,
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

function saveReview(movieId, btn) {
    const originalText = btn.innerHTML;

    // Collect review fields
    const reviewText = document.getElementById(`review-text-${movieId}`).value.trim();
    const author = document.getElementById(`review-author-${movieId}`).value.trim() || 'Admin';
    const rating = document.getElementById(`review-rating-${movieId}`).value;
    const featured = document.getElementById(`review-featured-${movieId}`).checked;

    // Validate review text
    if (!reviewText) {
        alert('Please enter review text before saving.');
        return;
    }

    if (reviewText.length > 5000) {
        alert('Review text is too long (max 5000 characters).');
        return;
    }

    // Validate rating if provided
    if (rating && (parseFloat(rating) < 0 || parseFloat(rating) > 5)) {
        alert('Rating must be between 0 and 5.');
        return;
    }

    // Disable button
    btn.disabled = true;
    btn.innerHTML = '⏳ Saving...';

    // Send to server
    fetch('/update-review', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            movie_id: movieId,
            review_text: reviewText,
            author: author,
            rating: rating ? parseFloat(rating) : null,
            featured_in_newsletter: featured
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            btn.innerHTML = '✅ Saved!';
            btn.style.background = '#28a745';
            showSuccess(data.message || 'Review saved successfully!');

            // Update card data attribute
            const card = document.querySelector(`[data-movie-id="${movieId}"]`);
            card.dataset.hasReview = 'yes';

            // Update textarea background to show it's no longer empty
            document.getElementById(`review-text-${movieId}`).style.background = '#2a2a2a';
            document.getElementById(`review-text-${movieId}`).style.borderColor = '#3a3a3a';

            // Update reviewed count in header
            updateReviewedCount();

            // Reset button after 2 seconds
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
                btn.style.background = '#007bff';
            }, 2000);
        } else {
            btn.innerHTML = '❌ Failed';
            btn.style.background = '#dc3545';
            alert(data.error || 'Failed to save review');

            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
                btn.style.background = '#007bff';
            }, 2000);
        }
    })
    .catch(error => {
        btn.innerHTML = '❌ Error';
        btn.style.background = '#dc3545';
        alert('Error saving review: ' + error);

        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
            btn.style.background = '#007bff';
        }, 2000);
    });
}

function deleteReview(movieId, btn) {
    if (!confirm('Are you sure you want to delete this review?')) {
        return;
    }

    const originalText = btn.innerHTML;

    // Disable button
    btn.disabled = true;
    btn.innerHTML = '⏳ Deleting...';

    // Send to server
    fetch('/delete-review', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({movie_id: movieId})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccess('Review deleted');

            // Clear form fields
            document.getElementById(`review-text-${movieId}`).value = '';
            document.getElementById(`review-author-${movieId}`).value = 'Hadrian Belove';
            document.getElementById(`review-rating-${movieId}`).value = '';
            document.getElementById(`review-featured-${movieId}`).checked = false;

            // Update card data attribute
            const card = document.querySelector(`[data-movie-id="${movieId}"]`);
            card.dataset.hasReview = 'no';

            // Update textarea background to show it's empty
            document.getElementById(`review-text-${movieId}`).style.background = '#1a1a1a';
            document.getElementById(`review-text-${movieId}`).style.borderColor = '#555';

            // Update reviewed count in header
            updateReviewedCount();

            // Hide delete button (will require page reload to show again)
            btn.style.display = 'none';
        } else {
            alert(data.error || 'Failed to delete review');
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    })
    .catch(error => {
        alert('Error deleting review: ' + error);
        btn.innerHTML = originalText;
        btn.disabled = false;
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
        headers: {'Content-Type': 'application/json'},
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