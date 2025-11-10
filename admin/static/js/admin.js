
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
        headers: {
            'Content-Type': 'application/json'
        },
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

            // Immediately refresh pending changes status
            checkPendingChanges();
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

// Draft management functions
let drafts = [];

function fetchDrafts() {
    fetch('/drafts')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            drafts = data.drafts || [];
            renderDraftsList(drafts);
        } else {
            console.error('Failed to fetch drafts:', data.error);
        }
    })
    .catch(error => {
        console.error('Error fetching drafts:', error);
    });
}

function renderDraftsList(drafts) {
    const container = document.getElementById('drafts-list');
    if (!container) return;

    if (drafts.length === 0) {
        container.innerHTML = '<div class="draft-empty">No drafts available</div>';
        return;
    }

    // Sort by creation date, newest first
    const sortedDrafts = drafts.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    container.innerHTML = sortedDrafts.map(draft => `
        <div class="draft-item" data-draft-id="${draft.id}">
            <div class="draft-header">
                <h4>Draft ${draft.id}</h4>
                <span class="draft-date">${new Date(draft.createdAt).toLocaleDateString()}</span>
            </div>
            <div class="draft-stats">
                <span>${draft.movieIds?.length || 0} movies</span>
                ${draft.lastModified ? `<span>Modified: ${new Date(draft.lastModified).toLocaleDateString()}</span>` : ''}
            </div>
            <div class="draft-actions">
                <button class="action-btn btn-small" onclick="editDraftTitles('${draft.id}')">✏️ Edit Titles</button>
                <button class="action-btn btn-small success" onclick="publishDraft('${draft.id}')">🚀 Publish</button>
            </div>
            <div class="draft-titles-editor" id="titles-editor-${draft.id}" style="display: none;">
                <h5>Edit Movie Titles</h5>
                <div class="titles-list" id="titles-list-${draft.id}"></div>
                <div class="editor-actions">
                    <button class="action-btn btn-small" onclick="saveDraftTitles('${draft.id}')">💾 Save</button>
                    <button class="action-btn btn-small" onclick="cancelEditTitles('${draft.id}')">❌ Cancel</button>
                </div>
            </div>
        </div>
    `).join('');
}

function editDraftTitles(draftId) {
    const draft = drafts.find(d => d.id === draftId);
    if (!draft) return;

    const editor = document.getElementById(`titles-editor-${draftId}`);
    const titlesList = document.getElementById(`titles-list-${draftId}`);

    if (!editor || !titlesList) return;

    // Render title inputs
    const titlesHtml = (draft.movieIds || []).map((movieId, index) => {
        const title = (draft.titles && draft.titles[index]) || '';
        return `
            <div class="title-input-row">
                <span class="movie-id">Movie ${movieId}:</span>
                <input type="text"
                       class="title-input"
                       id="title-${draftId}-${index}"
                       value="${title}"
                       placeholder="Enter movie title">
            </div>
        `;
    }).join('');

    titlesList.innerHTML = titlesHtml;
    editor.style.display = 'block';
}

function saveDraftTitles(draftId) {
    const draft = drafts.find(d => d.id === draftId);
    if (!draft) return;

    // Collect updated titles
    const updatedTitles = [];
    (draft.movieIds || []).forEach((movieId, index) => {
        const input = document.getElementById(`title-${draftId}-${index}`);
        if (input) {
            updatedTitles.push(input.value.trim());
        }
    });

    fetch(`/drafts/${draftId}`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ titles: updatedTitles })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccess('Draft titles updated successfully');
            cancelEditTitles(draftId);
            fetchDrafts(); // Refresh the list
        } else {
            alert('Failed to update titles: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        alert('Error updating titles: ' + error);
    });
}

function cancelEditTitles(draftId) {
    const editor = document.getElementById(`titles-editor-${draftId}`);
    if (editor) {
        editor.style.display = 'none';
    }
}

function publishDraft(draftId) {
    if (!confirm(`Are you sure you want to publish draft ${draftId}? This will update the live site.`)) {
        return;
    }

    fetch(`/drafts/${draftId}/publish`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccess(`Draft ${draftId} published successfully!`);
            fetchDrafts(); // Refresh the list (published draft should be removed)
        } else {
            alert('Failed to publish draft: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        alert('Error publishing draft: ' + error);
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
    const year = document.getElementById(`year-${movieId}`).value;
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
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            movie_id: movieId,
            digital_date: digitalDate || null,
            rt_score: rtScore ? parseInt(rtScore) : null,
            rt_link: rtLink.trim() || null,
            trailer_link: trailerLink.trim() || null,
            director: director.trim() || null,
            country: country.trim() || null,
            year: year ? parseInt(year) : null,
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

// Editorial Ordering Functions
let orderingMode = false;
let originalOrder = [];

function toggleOrderingMode() {
    const grid = document.getElementById('movie-grid');
    const editBtn = document.getElementById('edit-order-btn');
    const saveBtn = document.getElementById('save-order-btn');
    const cancelBtn = document.getElementById('cancel-order-btn');

    orderingMode = !orderingMode;

    if (orderingMode) {
        // Enter ordering mode
        grid.classList.add('ordering-mode');
        editBtn.style.display = 'none';
        saveBtn.style.display = 'inline-block';
        cancelBtn.style.display = 'inline-block';

        // Show drag handles
        document.querySelectorAll('.drag-handle').forEach(handle => {
            handle.style.display = 'block';
        });

        // Store original order
        originalOrder = Array.from(grid.children).map(card => card.dataset.movieId);

        // Enable drag and drop
        enableDragAndDrop();

        showSuccess('Drag and drop movies to reorder them. Click "Save Order" when done.');
    } else {
        // Exit ordering mode
        exitOrderingMode();
    }
}

function exitOrderingMode() {
    const grid = document.getElementById('movie-grid');
    const editBtn = document.getElementById('edit-order-btn');
    const saveBtn = document.getElementById('save-order-btn');
    const cancelBtn = document.getElementById('cancel-order-btn');

    orderingMode = false;
    grid.classList.remove('ordering-mode');
    editBtn.style.display = 'inline-block';
    saveBtn.style.display = 'none';
    cancelBtn.style.display = 'none';

    // Hide drag handles
    document.querySelectorAll('.drag-handle').forEach(handle => {
        handle.style.display = 'none';
    });

    // Disable drag and drop
    disableDragAndDrop();

    // Clear any drag-related classes
    document.querySelectorAll('.movie-card').forEach(card => {
        card.classList.remove('dragging', 'drag-over');
        card.draggable = false;
    });
}

function cancelOrdering() {
    // Restore original order
    const grid = document.getElementById('movie-grid');
    const cards = Array.from(grid.children);

    // Sort cards by original order
    cards.sort((a, b) => {
        const aIndex = originalOrder.indexOf(a.dataset.movieId);
        const bIndex = originalOrder.indexOf(b.dataset.movieId);
        return aIndex - bIndex;
    });

    // Re-append in original order
    cards.forEach(card => grid.appendChild(card));

    exitOrderingMode();
    showSuccess('Ordering cancelled - original order restored');
}

function saveOrdering() {
    const grid = document.getElementById('movie-grid');
    const orderedIds = Array.from(grid.children).map(card => card.dataset.movieId);

    const saveBtn = document.getElementById('save-order-btn');
    const originalText = saveBtn.textContent;

    // Disable button
    saveBtn.disabled = true;
    saveBtn.textContent = '⏳ Saving...';

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

            exitOrderingMode();
            showSuccess(data.message || `Editorial ordering saved with ${data.ordered_count || orderedIds.length} movies`);
        } else {
            saveBtn.textContent = '❌ Failed';
            alert('Failed to save ordering: ' + (data.error || 'Unknown error'));

            setTimeout(() => {
                saveBtn.textContent = originalText;
                saveBtn.disabled = false;
            }, 2000);
        }
    })
    .catch(error => {
        saveBtn.textContent = '❌ Error';
        alert('Error saving ordering: ' + error);

        setTimeout(() => {
            saveBtn.textContent = originalText;
            saveBtn.disabled = false;
        }, 2000);
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
        card.draggable = true;

        card.addEventListener('dragstart', handleDragStart);
        card.addEventListener('dragend', handleDragEnd);
        card.addEventListener('dragover', handleDragOver);
        card.addEventListener('dragenter', handleDragEnter);
        card.addEventListener('dragleave', handleDragLeave);
        card.addEventListener('drop', handleDrop);
    });
}

function disableDragAndDrop() {
    const cards = document.querySelectorAll('.movie-card');

    cards.forEach(card => {
        card.draggable = false;

        card.removeEventListener('dragstart', handleDragStart);
        card.removeEventListener('dragend', handleDragEnd);
        card.removeEventListener('dragover', handleDragOver);
        card.removeEventListener('dragenter', handleDragEnter);
        card.removeEventListener('dragleave', handleDragLeave);
        card.removeEventListener('drop', handleDrop);
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
    }

    this.classList.remove('drag-over');
    return false;
}

// Add Movie Modal Functions
function showAddMovieModal() {
    const modal = document.getElementById('add-movie-modal');
    modal.style.display = 'flex';

    // Clear form fields
    document.getElementById('add-tmdb-id').value = '';
    document.getElementById('add-title').value = '';
    document.getElementById('add-digital-date').value = '';
    document.getElementById('add-synopsis').value = '';
    document.getElementById('add-poster-url').value = '';
    document.getElementById('add-movie-status').textContent = '';

    // Focus TMDB ID field
    setTimeout(() => {
        document.getElementById('add-tmdb-id').focus();
    }, 100);
}

function hideAddMovieModal() {
    const modal = document.getElementById('add-movie-modal');
    modal.style.display = 'none';
}

function addMovie() {
    const tmdbId = document.getElementById('add-tmdb-id').value.trim();
    const title = document.getElementById('add-title').value.trim();
    const digitalDate = document.getElementById('add-digital-date').value.trim();
    const synopsis = document.getElementById('add-synopsis').value.trim();
    const posterUrl = document.getElementById('add-poster-url').value.trim();

    const btn = document.getElementById('add-movie-btn');
    const status = document.getElementById('add-movie-status');

    // Validation
    if (!tmdbId) {
        status.textContent = 'TMDB ID is required';
        status.style.color = '#dc3545';
        return;
    }

    if (!title) {
        status.textContent = 'Movie title is required';
        status.style.color = '#dc3545';
        return;
    }

    // Validate TMDB ID is numeric
    if (!/^\d+$/.test(tmdbId)) {
        status.textContent = 'TMDB ID must be numeric';
        status.style.color = '#dc3545';
        return;
    }

    // Disable button
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Adding...';
    status.textContent = 'Adding movie...';
    status.style.color = '#ffc107';

    // Build request data
    const requestData = {
        tmdb_id: tmdbId,
        title: title
    };

    if (digitalDate) {
        requestData.digital_date = digitalDate;
    }

    if (synopsis) {
        requestData.synopsis = synopsis;
    }

    if (posterUrl) {
        requestData.poster_url = posterUrl;
    }

    // Send to server
    fetch('/add-movie', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            status.textContent = '✅ ' + (data.message || 'Movie added successfully!');
            status.style.color = '#28a745';

            // Show success and close modal after delay
            showSuccess(data.message || 'Movie added successfully!');

            setTimeout(() => {
                hideAddMovieModal();

                // Reload page to show new movie
                window.location.reload();
            }, 2000);
        } else {
            status.textContent = '❌ ' + (data.error || 'Failed to add movie');
            status.style.color = '#dc3545';

            // Re-enable button
            btn.disabled = false;
            btn.textContent = originalText;
        }
    })
    .catch(error => {
        status.textContent = '❌ Error: ' + error;
        status.style.color = '#dc3545';

        // Re-enable button
        btn.disabled = false;
        btn.textContent = originalText;
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

// Initialize character counters on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize synopsis counters
    document.querySelectorAll('[id^="synopsis-"]').forEach(textarea => {
        if (textarea.tagName === 'TEXTAREA') {
            const movieId = textarea.id.replace('synopsis-', '');
            const counterId = `synopsis-counter-${movieId}`;
            updateCharCounter(textarea, counterId, 140, 600);
        }
    });

    // Load delta summary
    if (document.getElementById('delta-sidebar')) {
        refreshDeltaSummary();
    }

    // Fetch and render drafts if drafts section exists
    if (document.getElementById('drafts-list')) {
        fetchDrafts();
    }

    // Check for pending changes and poll every 5 seconds
    checkPendingChanges();
    setInterval(checkPendingChanges, 5000);
});

// Pending Changes Functions
function checkPendingChanges() {
    fetch('/pending-changes')
        .then(response => response.json())
        .then(data => {
            const btn = document.getElementById('regenerate-btn');
            if (!btn) return;

            if (data.has_pending_changes) {
                // Highlight button when changes are pending
                btn.classList.add('pending-changes');
                btn.style.animation = 'pulse 2s infinite';
                btn.title = 'You have unsaved changes. Click to save.';
            } else {
                // Normal state when no changes
                btn.classList.remove('pending-changes');
                btn.style.animation = '';
                btn.title = 'Rebuild data.json from tracking database';
            }
        })
        .catch(error => {
            console.error('Error checking pending changes:', error);
        });
}

// Delta Summary Functions
function refreshDeltaSummary() {
    const loading = document.getElementById('delta-loading');
    const content = document.getElementById('delta-content');

    if (!loading || !content) return;

    // Show loading state
    loading.style.display = 'block';
    content.style.display = 'none';

    fetch('/delta-summary')
    .then(response => response.json())
    .then(data => {
        if (data.success && data.delta) {
            updateDeltaDisplay(data.delta);
            loading.style.display = 'none';
            content.style.display = 'block';
        } else {
            loading.textContent = 'Error loading summary: ' + (data.error || 'Unknown error');
            loading.style.color = '#dc3545';
        }
    })
    .catch(error => {
        loading.textContent = 'Error: ' + error;
        loading.style.color = '#dc3545';
    });
}

function updateDeltaDisplay(delta) {
    // Update main stats
    const newFilmsElement = document.getElementById('delta-new-films');
    const editsElement = document.getElementById('delta-edits');
    const additionsElement = document.getElementById('delta-additions');

    if (newFilmsElement) newFilmsElement.textContent = delta.new_films_released || 0;
    if (editsElement) editsElement.textContent = delta.edits || 0;
    if (additionsElement) additionsElement.textContent = delta.additions || 0;

    // Update status changes
    const hiddenElement = document.getElementById('delta-hidden');
    const featuredElement = document.getElementById('delta-featured');
    const orderedElement = document.getElementById('delta-ordered');

    if (hiddenElement) hiddenElement.textContent = delta.hidden || 0;
    if (featuredElement) featuredElement.textContent = delta.featured || 0;
    if (orderedElement) orderedElement.textContent = delta.ordered || 0;

    // Update issues
    const issues = delta.issues || {};
    const missingRtElement = document.getElementById('delta-missing-rt');
    const missingTrailerElement = document.getElementById('delta-missing-trailer');
    const missingStreamElement = document.getElementById('delta-missing-stream');
    const missingRentElement = document.getElementById('delta-missing-rent');
    const missingBuyElement = document.getElementById('delta-missing-buy');

    if (missingRtElement) missingRtElement.textContent = issues.missing_rt || 0;
    if (missingTrailerElement) missingTrailerElement.textContent = issues.missing_trailer || 0;
    if (missingStreamElement) missingStreamElement.textContent = issues.missing_stream_link || 0;
    if (missingRentElement) missingRentElement.textContent = issues.missing_rent_link || 0;
    if (missingBuyElement) missingBuyElement.textContent = issues.missing_buy_link || 0;
}

// Override updateStats to also refresh delta summary when changes happen
const originalUpdateStatsWithDelta = updateStats;
updateStats = function() {
    originalUpdateStatsWithDelta.call(this);

    // Refresh delta summary if it exists (with debouncing)
    if (document.getElementById('delta-sidebar')) {
        clearTimeout(window.deltaRefreshTimeout);
        window.deltaRefreshTimeout = setTimeout(refreshDeltaSummary, 1000);
    }
};