// ============================================
// Pending changes counter
// ============================================
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
        btn.textContent = `Save Changes (${pendingChangesCount})`;
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
        btn.classList.add('pending-changes');
    } else {
        btn.textContent = 'Saved';
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
        btn.classList.remove('pending-changes');
    }
}

function viewSite() {
    window.open('/site/', '_blank');
}

function showSuccess(message = 'Changes saved!') {
    const msg = document.getElementById('success-msg');
    msg.textContent = message;
    msg.style.display = 'block';
    setTimeout(() => { msg.style.display = 'none'; }, 3000);
}

// ============================================
// Row expand/collapse
// ============================================
function toggleRow(row) {
    const panel = row.nextElementSibling;
    if (!panel || !panel.classList.contains('ep')) return;

    const wasOpen = panel.classList.contains('open');

    // Close all panels
    document.querySelectorAll('.ep.open').forEach(p => p.classList.remove('open'));
    document.querySelectorAll('.movie-row.expanded').forEach(r => r.classList.remove('expanded'));

    if (!wasOpen) {
        panel.classList.add('open');
        row.classList.add('expanded');

        // Load pull quotes if not yet loaded
        const movieId = row.dataset.movieId;
        loadQuotes(movieId);
    }
}

// ============================================
// Unified category toggling
// ============================================
function toggleCategory(movieId, statusType, value) {
    fetch('/toggle-status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ movie_id: movieId, status_type: statusType, value: value })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Find the button that was clicked and toggle its .on class
            const row = document.querySelector(`.movie-row[data-movie-id="${movieId}"]`);
            if (!row) return;

            const btns = row.querySelectorAll('.cat-btn');
            btns.forEach(btn => {
                const title = btn.getAttribute('title');
                const typeMap = {
                    'Staff Pick': 'featured',
                    'Big Time': 'big_time',
                    'Indie': 'indie',
                    'Foreign': 'foreign',
                    'Series': 'series',
                    'Restoration': 'restoration',
                    'Virtual Screening': 'virtual_screening',
                    'Documentary': 'documentary'
                };
                if (typeMap[title] === statusType) {
                    if (value) {
                        btn.classList.add('on');
                        // Update onclick to toggle off next time
                        btn.setAttribute('onclick', `toggleCategory('${movieId}', '${statusType}', false)`);
                    } else {
                        btn.classList.remove('on');
                        btn.setAttribute('onclick', `toggleCategory('${movieId}', '${statusType}', true)`);
                    }
                }
            });

            // Update pick styling on row
            if (statusType === 'featured') {
                if (value) {
                    row.classList.add('pick');
                    row.dataset.isPick = 'yes';
                } else {
                    row.classList.remove('pick');
                    row.dataset.isPick = 'no';
                }
                updateStats();
            }

            incrementPendingCount();
            showSuccess(`${statusType.replace('_', ' ')} ${value ? 'enabled' : 'disabled'}`);
        } else {
            alert(data.error || 'Failed to toggle');
        }
    })
    .catch(error => {
        alert('Error: ' + error);
    });
}

// ============================================
// Pull quotes AJAX loading
// ============================================
const loadedQuotes = {};

function loadQuotes(movieId) {
    if (loadedQuotes[movieId]) return; // Already loaded

    const container = document.getElementById(`quotes-list-${movieId}`);
    if (!container) return;

    fetch(`/api/pull-quotes/${movieId}`)
        .then(response => response.json())
        .then(data => {
            loadedQuotes[movieId] = true;

            if (!data.quotes || data.quotes.length === 0) {
                container.innerHTML = '<div class="quote-empty">No quotes yet</div>';
                return;
            }

            const countEl = document.getElementById(`quote-count-${movieId}`);
            if (countEl) {
                const selected = data.quotes.filter(q => q.selected).length;
                countEl.textContent = `${selected} selected / ${data.quotes.length} total`;
            }

            container.innerHTML = data.quotes.map((q, i) => `
                <div class="quote-item ${q.selected ? 'selected' : ''}"
                     onclick="toggleQuote('${data.cache_key}', '${q.pool}', ${q.index}, this)">
                    <span class="q-check">${q.selected ? '&#10003;' : ''}</span>
                    <div>
                        <div class="quote-text">"${escapeHtml(q.text)}"</div>
                        <div class="quote-src">- ${escapeHtml(q.source)}</div>
                    </div>
                </div>
            `).join('');
        })
        .catch(error => {
            container.innerHTML = '<div class="quote-empty">Failed to load quotes</div>';
            console.error('Error loading quotes:', error);
        });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function toggleQuote(cacheKey, source, index, el) {
    fetch('/pull-quotes/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cache_key: cacheKey, source: source, index: index })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            el.classList.toggle('selected');
            const check = el.querySelector('.q-check');
            if (check) {
                check.innerHTML = el.classList.contains('selected') ? '&#10003;' : '';
            }
        }
    })
    .catch(error => console.error('Error toggling quote:', error));
}

function addQuote(movieId) {
    const input = document.getElementById(`quote-add-${movieId}`);
    if (!input || !input.value.trim()) return;

    // Get movie title/year from the row for cache_key construction
    // For now, navigate to the quotes page for adding
    window.open(`/pull-quotes/${movieId}`, '_blank');
}

// ============================================
// Remove movie
// ============================================
function removeMovie(movieId, title) {
    if (!confirm(`Remove "${title}" from the New Arrivals Wall?\n\nThis will remove the movie from the site.`)) {
        return;
    }

    fetch('/remove-movie', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ movie_id: movieId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove both the row and its expanded panel
            const row = document.querySelector(`.movie-row[data-movie-id="${movieId}"]`);
            const panel = document.querySelector(`.ep[data-movie-id="${movieId}"]`);
            if (row) {
                row.style.transition = 'opacity 0.3s';
                row.style.opacity = '0';
                setTimeout(() => row.remove(), 300);
            }
            if (panel) {
                panel.style.transition = 'opacity 0.3s';
                panel.style.opacity = '0';
                setTimeout(() => panel.remove(), 300);
            }
            incrementPendingCount();
            showSuccess(data.message || 'Movie removed');
        } else {
            alert(data.error || 'Failed to remove movie');
        }
    })
    .catch(error => { alert('Error: ' + error); });
}

// ============================================
// Stats
// ============================================
function updateStats() {
    const picks = document.querySelectorAll('.movie-row[data-is-pick="yes"]');
    const el = document.getElementById('featured-count');
    if (el) el.textContent = picks.length;

    const missing = document.querySelectorAll('.movie-row[data-missing-any="yes"]');
    const missingEl = document.getElementById('missing-data-count');
    if (missingEl) missingEl.textContent = missing.length;
}

// ============================================
// Filter & Search
// ============================================
function filterMovies(filter, event) {
    const rows = document.querySelectorAll('.movie-row');
    const dateHeaders = document.querySelectorAll('.date-header');
    const buttons = document.querySelectorAll('.filter-btn');

    // Update active button
    buttons.forEach(btn => btn.classList.remove('active'));
    const activeBtn = event ? event.target : null;
    if (activeBtn) activeBtn.classList.add('active');

    // Show/hide rows
    rows.forEach(row => {
        let show = true;
        switch (filter) {
            case 'all':
                show = true;
                break;
            case 'staff-picks':
                show = row.dataset.isPick === 'yes';
                break;
            case 'restorations':
                // Check if REST button is .on
                const restBtn = row.querySelector('.cat-btn[title="Restoration"]');
                show = restBtn && restBtn.classList.contains('on');
                break;
            case 'missing-data':
                show = row.dataset.missingAny === 'yes';
                break;
        }
        row.style.display = show ? '' : 'none';
        // Also hide the panel
        const panel = row.nextElementSibling;
        if (panel && panel.classList.contains('ep')) {
            panel.style.display = show ? '' : 'none';
            if (!show) panel.classList.remove('open');
        }
    });

    // Show/hide date headers based on whether they have visible children
    dateHeaders.forEach(header => {
        let hasVisible = false;
        let sibling = header.nextElementSibling;
        while (sibling && !sibling.classList.contains('date-header')) {
            if (sibling.classList.contains('movie-row') && sibling.style.display !== 'none') {
                hasVisible = true;
                break;
            }
            sibling = sibling.nextElementSibling;
        }
        header.style.display = hasVisible ? '' : 'none';
    });
}

function searchMovies() {
    const query = document.getElementById('search-box').value.toLowerCase();
    const rows = document.querySelectorAll('.movie-row');
    const dateHeaders = document.querySelectorAll('.date-header');

    rows.forEach(row => {
        const title = row.dataset.title || '';
        const show = !query || title.includes(query);
        row.style.display = show ? '' : 'none';
        const panel = row.nextElementSibling;
        if (panel && panel.classList.contains('ep')) {
            if (!show) {
                panel.style.display = 'none';
                panel.classList.remove('open');
            } else {
                panel.style.display = '';
            }
        }
    });

    // Show/hide date headers
    dateHeaders.forEach(header => {
        let hasVisible = false;
        let sibling = header.nextElementSibling;
        while (sibling && !sibling.classList.contains('date-header')) {
            if (sibling.classList.contains('movie-row') && sibling.style.display !== 'none') {
                hasVisible = true;
                break;
            }
            sibling = sibling.nextElementSibling;
        }
        header.style.display = hasVisible ? '' : 'none';
    });
}

// ============================================
// Regenerate (Save Changes)
// ============================================
function regenerateData() {
    const btn = document.getElementById('regenerate-btn');
    const status = document.getElementById('regenerate-status');

    btn.disabled = true;
    btn.style.opacity = '0.5';
    status.textContent = 'Saving changes... (10-30 seconds)';
    status.style.color = '#ffc107';

    fetch('/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            status.textContent = (data.message || 'Changes saved!');
            status.style.color = '#28a745';
            showSuccess('Changes saved successfully');
            resetPendingCount();
        } else {
            status.textContent = (data.error || 'Save failed');
            status.style.color = '#dc3545';
            alert('Save failed: ' + (data.error || 'Unknown error'));
        }
        btn.disabled = false;
        btn.style.opacity = '1';
        setTimeout(() => { status.textContent = ''; }, 5000);
    })
    .catch(error => {
        status.textContent = 'Error: ' + error;
        status.style.color = '#dc3545';
        btn.disabled = false;
        btn.style.opacity = '1';
    });
}

// ============================================
// Drag & Drop
// ============================================
let draggedElement = null;

function enableDragAndDrop() {
    const rows = document.querySelectorAll('.movie-row');
    rows.forEach(row => {
        row.addEventListener('dragstart', handleDragStart);
        row.addEventListener('dragend', handleDragEnd);
        row.addEventListener('dragover', handleDragOver);
        row.addEventListener('dragenter', handleDragEnter);
        row.addEventListener('dragleave', handleDragLeave);
        row.addEventListener('drop', handleDrop);
    });
}

function handleDragStart(e) {
    draggedElement = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.dataset.movieId);
}

function handleDragEnd(e) {
    this.classList.remove('dragging');
    document.querySelectorAll('.movie-row.drag-over').forEach(r => r.classList.remove('drag-over'));
    draggedElement = null;
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
}

function handleDragEnter(e) {
    if (this !== draggedElement && this.classList.contains('movie-row')) {
        this.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    this.classList.remove('drag-over');
}

function handleDrop(e) {
    e.stopPropagation();
    if (!draggedElement || draggedElement === this) return;

    const list = document.getElementById('movie-list');
    const draggedPanel = draggedElement.nextElementSibling;

    // Move the row + its panel before or after the target
    if (this.classList.contains('movie-row')) {
        // Insert before the target row
        list.insertBefore(draggedElement, this);
        if (draggedPanel && draggedPanel.classList.contains('ep')) {
            list.insertBefore(draggedPanel, this);
        }
    }

    this.classList.remove('drag-over');
    saveOrdering();
}

function saveOrdering() {
    const rows = document.querySelectorAll('.movie-row');
    const orderedIds = Array.from(rows).map(row => row.dataset.movieId);

    fetch('/update-ordering', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ordered_ids: orderedIds })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            incrementPendingCount();
            showSuccess('Order updated');
        } else {
            alert('Failed to save ordering: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => { alert('Error saving ordering: ' + error); });
}

// ============================================
// Metadata save
// ============================================
function saveMetadata(movieId) {
    const director = document.getElementById(`director-${movieId}`).value.trim();
    const country = document.getElementById(`country-${movieId}`).value.trim();
    const runtime = document.getElementById(`runtime-${movieId}`).value.trim();

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
            // Update field styles
            const dirInput = document.getElementById(`director-${movieId}`);
            const ccInput = document.getElementById(`country-${movieId}`);
            if (director && director !== 'Unknown') dirInput.classList.remove('miss');
            if (country) ccInput.classList.remove('miss');

            // Update row display
            const row = document.querySelector(`.movie-row[data-movie-id="${movieId}"]`);
            if (row) {
                const dirCell = row.querySelector('.r-dir');
                if (dirCell) {
                    dirCell.textContent = director || '\u2014';
                    dirCell.classList.toggle('bad', !director || director === 'Unknown');
                }
                const ccCell = row.querySelector('.r-cc');
                if (ccCell) ccCell.textContent = country || '\u2014';
                const minCell = row.querySelector('.r-min');
                if (minCell) minCell.textContent = runtime || '\u2014';
            }

            incrementPendingCount();
            showSuccess('Metadata saved');
        } else {
            alert(data.error || 'Failed to save');
        }
    })
    .catch(error => { alert('Error: ' + error); });
}

// ============================================
// Link editing
// ============================================
let currentLinkModes = {};

function setLinkMode(movieId, linkType) {
    currentLinkModes[movieId] = linkType;

    const input = document.getElementById(`universal-link-${movieId}`);
    const saveBtn = document.getElementById(`save-link-${movieId}`);
    const indicator = document.getElementById(`link-mode-indicator-${movieId}`);

    const placeholders = {
        trailer: 'https://www.youtube.com/watch?v=...',
        rt: 'https://www.rottentomatoes.com/m/...',
        poster: 'https://image.tmdb.org/t/p/w500/...',
        wikipedia: 'https://en.wikipedia.org/wiki/...'
    };

    const labels = {
        trailer: 'Editing trailer link',
        rt: 'Editing RT link',
        poster: 'Editing poster URL',
        wikipedia: 'Editing Wikipedia link'
    };

    input.value = '';
    input.readOnly = false;
    input.placeholder = placeholders[linkType] || '';
    indicator.textContent = labels[linkType] || '';
    saveBtn.disabled = false;
    saveBtn.style.opacity = '1';
    input.focus();

    // Highlight active button
    const panel = document.querySelector(`.ep[data-movie-id="${movieId}"]`);
    if (panel) {
        panel.querySelectorAll('.lb').forEach(btn => btn.classList.remove('active'));
    }
}

function saveLinkField(movieId) {
    const linkType = currentLinkModes[movieId];
    if (!linkType) return;

    const input = document.getElementById(`universal-link-${movieId}`);
    const saveBtn = document.getElementById(`save-link-${movieId}`);
    const newValue = input.value.trim();

    const requestBody = { movie_id: movieId };
    switch (linkType) {
        case 'trailer': requestBody.trailer_link = newValue || null; break;
        case 'rt': requestBody.rt_link = newValue || null; break;
        case 'poster': requestBody.poster_url = newValue || null; break;
        case 'wikipedia': requestBody.wikipedia_link = newValue || null; break;
    }

    saveBtn.disabled = true;

    fetch('/update-movie-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update link button color in expanded panel
            const panel = document.querySelector(`.ep[data-movie-id="${movieId}"]`);
            if (panel) {
                const linkBtns = panel.querySelectorAll('.lb');
                const typeIndex = { trailer: 0, rt: 1, poster: 2, wikipedia: 3 };
                const idx = typeIndex[linkType];
                if (idx !== undefined && linkBtns[idx]) {
                    linkBtns[idx].classList.remove('g', 'r');
                    linkBtns[idx].classList.add(newValue ? 'g' : 'r');
                }
            }

            // Update quick links in row
            const row = document.querySelector(`.movie-row[data-movie-id="${movieId}"]`);
            if (row && (linkType === 'wikipedia' || linkType === 'rt')) {
                const qls = row.querySelectorAll('.ql');
                const qlIndex = { wikipedia: 0, rt: 2 };
                const qi = qlIndex[linkType];
                if (qi !== undefined && qls[qi]) {
                    if (newValue) {
                        qls[qi].classList.remove('dead');
                        qls[qi].href = newValue;
                        qls[qi].target = '_blank';
                    } else {
                        qls[qi].classList.add('dead');
                        qls[qi].removeAttribute('href');
                    }
                }
            }

            incrementPendingCount();
            showSuccess(`${linkType} link saved`);
        } else {
            alert(data.error || 'Failed to save');
        }

        // Reset
        setTimeout(() => {
            input.readOnly = true;
            input.value = '';
            input.placeholder = 'Select a link button to edit...';
            saveBtn.disabled = true;
            saveBtn.style.opacity = '0.6';
            const indicator = document.getElementById(`link-mode-indicator-${movieId}`);
            if (indicator) indicator.textContent = 'Click a button to edit that link';
            delete currentLinkModes[movieId];
        }, 800);
    })
    .catch(error => {
        alert('Error: ' + error);
        saveBtn.disabled = false;
    });
}

// ============================================
// Watch service editing
// ============================================
let currentWatchModes = {};

function setWatchService(movieId, serviceType, serviceName) {
    currentWatchModes[movieId] = { type: serviceType, service: serviceName };

    const input = document.getElementById(`streaming-link-${movieId}`);
    const saveBtn = document.getElementById(`save-streaming-${movieId}`);

    if (serviceName === 'ADD') {
        input.placeholder = `Enter link for custom ${serviceType} service...`;
    } else {
        input.placeholder = `Enter ${serviceName} link...`;
    }

    input.value = '';
    input.readOnly = false;
    saveBtn.disabled = false;
    saveBtn.style.opacity = '1';
    input.focus();

    // Store service name for save
    if (serviceType === 'streaming') {
        document.getElementById(`streaming-service-${movieId}`).value = serviceName;
    } else {
        document.getElementById(`vod-service-${movieId}`).value = serviceName;
    }
}

function saveWatchService(movieId, serviceType) {
    const watchMode = currentWatchModes[movieId];
    if (!watchMode) return;

    const input = document.getElementById(`streaming-link-${movieId}`);
    const saveBtn = document.getElementById(`save-streaming-${movieId}`);
    const newValue = input.value.trim();
    const svcType = watchMode.type;
    const svcName = watchMode.service === 'ADD' ? 'Custom' : watchMode.service;

    const watchLinks = {};
    watchLinks[svcType] = { service: svcName, link: newValue || null };

    saveBtn.disabled = true;

    fetch('/update-movie-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ movie_id: movieId, watch_links: watchLinks })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            incrementPendingCount();
            showSuccess(`${svcType} link saved`);
        } else {
            alert(data.error || 'Failed to save');
        }
        // Reset
        setTimeout(() => {
            input.readOnly = true;
            input.value = '';
            input.placeholder = 'Select service to add link...';
            saveBtn.disabled = true;
            saveBtn.style.opacity = '0.6';
            delete currentWatchModes[movieId];
        }, 800);
    })
    .catch(error => {
        alert('Error: ' + error);
        saveBtn.disabled = false;
    });
}

// ============================================
// Character counter
// ============================================
function updateCharCounter(textarea, counterId, minLength, maxLength) {
    const counter = document.getElementById(counterId);
    if (!counter) return;
    const len = textarea.value.length;
    counter.textContent = `${len}/${maxLength}`;
    counter.classList.remove('warning', 'error');
    if (len > maxLength * 0.9) counter.classList.add('warning');
    if (len > maxLength) counter.classList.add('error');
}

// ============================================
// Trailer player
// ============================================
function isHostedTrailer(url) {
    if (!url) return false;
    try { return new URL(url).pathname.endsWith('.mp4') || url.includes('/file/NRW-TRAILERS/'); }
    catch { return url.endsWith('.mp4') || url.includes('/file/NRW-TRAILERS/'); }
}

function extractYouTubeId(url) {
    if (!url) return null;
    const patterns = [
        /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\?\/]+)/,
        /youtube\.com\/v\/([^&\?\/]+)/,
        /youtube\.com\/shorts\/([^&\?\/]+)/
    ];
    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) return match[1];
    }
    return null;
}

// Trailer navigation state
let trailerList = [];
let currentTrailerIndex = -1;

function buildTrailerList() {
    trailerList = [];
    document.querySelectorAll('.movie-row[data-movie-id]').forEach(row => {
        const pst = row.querySelector('[data-trailer-url]');
        if (!pst) return;
        const url = pst.dataset.trailerUrl;
        const title = pst.dataset.trailerTitle || '';
        const movieId = row.dataset.movieId;
        if (url && movieId) {
            trailerList.push({ movieId, title, url });
        }
    });
}

function openTrailer(movieId, el) {
    const url = el.dataset.trailerUrl;
    const title = el.dataset.trailerTitle || '';
    buildTrailerList();
    currentTrailerIndex = trailerList.findIndex(t => t.movieId === movieId);
    playTrailer(url, title);
    updateAdminTrailerNav();
}

function playTrailer(url, title) {
    const modal = document.getElementById('admin-trailer-modal');
    const container = document.getElementById('admin-trailer-video');
    const titleEl = document.getElementById('admin-trailer-title');
    if (!modal || !container) return;

    titleEl.textContent = title || '';

    if (isHostedTrailer(url)) {
        container.innerHTML = `<video src="${url}" controls autoplay preload="auto"></video>`;
    } else {
        const videoId = extractYouTubeId(url);
        if (!videoId) return;
        container.innerHTML = `<iframe src="https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0" frameborder="0" allow="accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture" allowfullscreen></iframe>`;
    }

    modal.style.display = 'flex';
}

function adminTrailerNav(direction) {
    if (currentTrailerIndex < 0 || trailerList.length === 0) return;
    const nextIdx = currentTrailerIndex + direction;
    if (nextIdx < 0 || nextIdx >= trailerList.length) return;
    currentTrailerIndex = nextIdx;
    const t = trailerList[nextIdx];
    // Stop current video/iframe before loading next
    const container = document.getElementById('admin-trailer-video');
    const video = container?.querySelector('video');
    if (video) { video.pause(); video.src = ''; }
    const iframe = container?.querySelector('iframe');
    if (iframe) { iframe.src = ''; }
    playTrailer(t.url, t.title);
    updateAdminTrailerNav();
}

function updateAdminTrailerNav() {
    const prevBtn = document.getElementById('admin-trailer-prev');
    const nextBtn = document.getElementById('admin-trailer-next');
    if (prevBtn) prevBtn.style.display = currentTrailerIndex > 0 ? '' : 'none';
    if (nextBtn) nextBtn.style.display = currentTrailerIndex < trailerList.length - 1 ? '' : 'none';
}

function closeAdminTrailer() {
    const modal = document.getElementById('admin-trailer-modal');
    const container = document.getElementById('admin-trailer-video');
    if (!modal) return;
    const video = container?.querySelector('video');
    if (video) { video.pause(); video.src = ''; }
    const iframe = container?.querySelector('iframe');
    if (iframe) { iframe.src = ''; }
    modal.style.display = 'none';
    if (container) container.innerHTML = '';
    currentTrailerIndex = -1;
}

// Image overlay
function showImg(url) {
    document.getElementById('img-preview').src = url;
    document.getElementById('imgoverlay').classList.add('open');
}
function closeImg() {
    document.getElementById('imgoverlay').classList.remove('open');
}

// ============================================
// Health banner
// ============================================
function copyAndDismissHealth() {
    const detailsEl = document.getElementById('health-details');
    const bannerEl = document.getElementById('health-banner');
    if (detailsEl && navigator.clipboard) {
        navigator.clipboard.writeText(detailsEl.value).catch(() => {});
    }
    if (bannerEl) bannerEl.style.display = 'none';
    fetch('/dismiss-health', { method: 'POST' }).catch(() => {});
}

// ============================================
// Playlist form
// ============================================
function togglePlaylistForm() {
    const form = document.getElementById('playlist-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

function updateDateInputs() {
    const dateType = document.getElementById('playlist-date-type').value;
    document.getElementById('days-input-container').style.display = dateType === 'last_x_days' ? 'block' : 'none';
    document.getElementById('date-range-container').style.display = dateType === 'date_range' ? 'block' : 'none';
}

function createYouTubePlaylist() {
    const btn = document.getElementById('create-playlist-btn');
    const status = document.getElementById('playlist-status');
    const result = document.getElementById('playlist-result');
    const dateType = document.getElementById('playlist-date-type').value;
    const dryRun = document.getElementById('playlist-dry-run').checked;

    const requestBody = {
        date_type: dateType,
        privacy: document.getElementById('playlist-privacy').value,
        dry_run: dryRun
    };

    const title = document.getElementById('playlist-title').value.trim();
    if (title) requestBody.title = title;

    if (dateType === 'last_x_days') {
        requestBody.days_back = parseInt(document.getElementById('playlist-days').value);
    } else {
        requestBody.from_date = document.getElementById('playlist-from-date').value;
        requestBody.to_date = document.getElementById('playlist-to-date').value;
    }

    btn.disabled = true;
    status.textContent = dryRun ? 'Generating preview...' : 'Creating playlist...';
    status.style.color = '#ffc107';
    result.style.display = 'none';

    fetch('/create-youtube-playlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        btn.disabled = false;
        if (data.success) {
            status.textContent = dryRun ? 'Preview generated' : 'Playlist created!';
            status.style.color = '#28a745';
            result.style.display = 'block';
            let html = '<div style="color:#fff;">';
            if (data.title) html += `<strong>Title:</strong> ${data.title}<br>`;
            if (data.video_count !== undefined) html += `<strong>Videos:</strong> ${data.video_count}<br>`;
            if (data.playlist_url) html += `<br><a href="${data.playlist_url}" target="_blank" style="color:#66b3ff;">View Playlist</a><br>`;
            html += '</div>';
            result.innerHTML = html;
        } else {
            status.textContent = data.error || 'Failed';
            status.style.color = '#dc3545';
        }
    })
    .catch(error => {
        btn.disabled = false;
        status.textContent = 'Error: ' + error;
        status.style.color = '#dc3545';
    });
}

// ============================================
// Add Movie modal
// ============================================
let selectedMovieData = null;

function showAddMovieModal() {
    document.getElementById('add-movie-modal').style.display = 'flex';
    document.getElementById('add-movie-search').value = '';
    document.getElementById('tmdb-search-status').textContent = '';
    document.getElementById('tmdb-search-results').innerHTML = '';
    setTimeout(() => document.getElementById('add-movie-search').focus(), 100);
}

function hideAddMovieModal() {
    document.getElementById('add-movie-modal').style.display = 'none';
    document.getElementById('add-movie-step1').style.display = 'block';
    document.getElementById('add-movie-step2').style.display = 'none';
    selectedMovieData = null;
}

function searchTMDB() {
    const query = document.getElementById('add-movie-search').value.trim();
    const status = document.getElementById('tmdb-search-status');
    const results = document.getElementById('tmdb-search-results');
    const btn = document.getElementById('search-tmdb-btn');

    if (!query || query.length < 2) {
        status.textContent = 'Enter at least 2 characters';
        status.style.color = '#dc3545';
        return;
    }

    btn.disabled = true;
    status.textContent = 'Searching...';
    status.style.color = '#ffc107';
    results.innerHTML = '';

    fetch(`/search-tmdb?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            btn.disabled = false;
            if (data.success && data.results.length > 0) {
                status.textContent = `Found ${data.results.length} results:`;
                status.style.color = '#28a745';
                results.innerHTML = data.results.map(movie => `
                    <div class="tmdb-result" onclick="addMovieFromSearch(${movie.id}, '${movie.title.replace(/'/g, "\\'")}', '${movie.year || ''}', '${movie.poster_url || ''}')">
                        <div class="tmdb-result-poster">
                            ${movie.poster_url ? `<img src="${movie.poster_url}" alt="">` : '<div class="no-poster-small">No Poster</div>'}
                        </div>
                        <div class="tmdb-result-info">
                            <div class="tmdb-result-title">${movie.title}</div>
                            <div class="tmdb-result-year">${movie.year || ''}</div>
                            ${movie.overview ? `<div class="tmdb-result-overview">${movie.overview}</div>` : ''}
                        </div>
                    </div>
                `).join('');
            } else {
                status.textContent = data.results?.length === 0 ? 'No movies found.' : (data.error || 'Search failed');
                status.style.color = '#ffc107';
            }
        })
        .catch(error => {
            btn.disabled = false;
            status.textContent = 'Error: ' + error;
            status.style.color = '#dc3545';
        });
}

function detectServiceFromUrl() {
    const url = document.getElementById('add-movie-watch-url').value.trim();
    const detected = document.getElementById('detected-service');
    if (!url) { detected.textContent = ''; return null; }

    const patterns = [
        { pattern: /vimeo\.com/i, service: 'VIMEO', type: 'vod' },
        { pattern: /amazon\./i, service: 'AMAZON', type: 'vod' },
        { pattern: /itunes\.apple\.com|tv\.apple\.com/i, service: 'APPLE', type: 'vod' },
        { pattern: /vudu\.com/i, service: 'VUDU', type: 'vod' },
        { pattern: /netflix\.com/i, service: 'NETFLIX', type: 'streaming' },
        { pattern: /mubi\.com/i, service: 'MUBI', type: 'streaming' },
        { pattern: /disneyplus\.com/i, service: 'DISNEY+', type: 'streaming' },
        { pattern: /max\.com|hbomax\.com/i, service: 'MAX', type: 'streaming' },
    ];

    for (const { pattern, service, type } of patterns) {
        if (pattern.test(url)) {
            detected.innerHTML = `Detected: <strong>${service}</strong> (${type})`;
            detected.style.color = '#28a745';
            return { service, type, url };
        }
    }

    try {
        const domain = new URL(url).hostname.replace('www.', '').split('.')[0].toUpperCase();
        detected.innerHTML = `Service: <strong>${domain}</strong>`;
        detected.style.color = '#ffc107';
        return { service: domain, type: 'vod', url };
    } catch {
        detected.textContent = 'Enter a valid URL';
        detected.style.color = '#dc3545';
        return null;
    }
}

function addMovieFromSearch(tmdbId, title, year, posterUrl) {
    selectedMovieData = { tmdbId, title, year, posterUrl };
    document.getElementById('add-movie-step1').style.display = 'none';
    document.getElementById('add-movie-step2').style.display = 'block';
    document.getElementById('selected-movie-title').textContent = title;
    document.getElementById('selected-movie-year').textContent = year || '';
    const posterImg = document.getElementById('selected-movie-poster');
    posterImg.src = posterUrl || '';
    posterImg.style.display = posterUrl ? 'block' : 'none';
    document.getElementById('add-movie-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('add-movie-watch-url').value = '';
    document.getElementById('detected-service').textContent = '';
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
    const watchUrl = document.getElementById('add-movie-watch-url').value.trim();
    const serviceInfo = watchUrl ? detectServiceFromUrl() : null;

    status.textContent = `Adding "${title}"...`;
    status.style.color = '#ffc107';
    btn.disabled = true;

    const requestBody = { tmdb_id: tmdbId };
    const releaseDate = document.getElementById('add-movie-date').value;
    if (releaseDate) requestBody.digital_date = releaseDate;
    if (serviceInfo) requestBody.watch_link = { service: serviceInfo.service, type: serviceInfo.type, url: serviceInfo.url };

    fetch('/add-movie', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        btn.disabled = false;
        if (data.success) {
            status.textContent = `"${title}" added!`;
            status.style.color = '#28a745';
            incrementPendingCount();
            setTimeout(() => { hideAddMovieModal(); window.location.reload(); }, 1500);
        } else {
            status.textContent = data.error || 'Failed';
            status.style.color = '#dc3545';
        }
    })
    .catch(error => {
        btn.disabled = false;
        status.textContent = 'Error: ' + error;
        status.style.color = '#dc3545';
    });
}

// ============================================
// Keyboard shortcuts & global events
// ============================================
document.addEventListener('keydown', function(e) {
    // Trailer modal: arrow keys navigate, Escape closes
    const trailerModal = document.getElementById('admin-trailer-modal');
    if (trailerModal && trailerModal.style.display !== 'none') {
        if (e.key === 'ArrowLeft') { adminTrailerNav(-1); return; }
        if (e.key === 'ArrowRight') { adminTrailerNav(1); return; }
    }

    if (e.key === 'Escape') {
        if (trailerModal && trailerModal.style.display !== 'none') {
            closeAdminTrailer();
            return;
        }
        // Close image overlay
        const imgOverlay = document.getElementById('imgoverlay');
        if (imgOverlay && imgOverlay.classList.contains('open')) {
            closeImg();
            return;
        }
        // Close add movie modal
        const addModal = document.getElementById('add-movie-modal');
        if (addModal && addModal.style.display === 'flex') {
            hideAddMovieModal();
            return;
        }
        // Close any expanded panel
        document.querySelectorAll('.ep.open').forEach(p => p.classList.remove('open'));
        document.querySelectorAll('.movie-row.expanded').forEach(r => r.classList.remove('expanded'));
    }
});

// Close add movie modal by clicking outside
document.addEventListener('click', function(e) {
    const modal = document.getElementById('add-movie-modal');
    if (e.target === modal) hideAddMovieModal();
});

// ============================================
// Initialize
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    // Check pending changes
    fetch('/pending-changes')
        .then(response => response.json())
        .then(data => {
            if (data.has_pending_changes) {
                pendingChangesCount = data.pending_change_count || 1;
                updatePendingBadge();
            }
        })
        .catch(() => {});

    updatePendingBadge();
    enableDragAndDrop();
});
