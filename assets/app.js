const NRW = {
    allMovies: [],
    filteredMovies: [],
    staffPicks: [],  // Renamed from featuredMovies
    latestPlaylistUrl: null,  // YouTube trailers playlist URL
    plexLibrary: {},  // TMDB ID -> Plex URLs mapping (personal, local only)
    activeFilters: new Set(),  // Multi-select: Set of active filter IDs
    searchQuery: '',     // Current search query
    displayedCount: 60,  // How many movies currently shown
    loadIncrement: 60,   // How many to add when clicking "More"

    // Lightbox state
    lightboxMovies: [],  // Movies currently in the lightbox (filtered/displayed)
    lightboxIndex: 0,    // Current index in lightbox

    async init() {
        try {
            // Load movie data
            const movieResponse = await fetch('data.json');
            const data = await movieResponse.json();

            // Load staff picks (supports both new and legacy field names)
            this.staffPicks = data.staff_picks || data.featured || [];

            // Load YouTube trailers playlist URL
            this.latestPlaylistUrl = data.latest_playlist_url || null;

            // Build Plex library from movies that have plex data embedded
            if (data.movies) {
                data.movies.forEach(movie => {
                    if (movie.plex) {
                        this.plexLibrary[String(movie.id)] = movie.plex;
                    }
                });
                if (Object.keys(this.plexLibrary).length > 0) {
                    console.log(`Plex library loaded: ${Object.keys(this.plexLibrary).length} movies`);
                }
            }

            if (data.movies && data.movies.length > 0) {
                const today = new Date();
                this.allMovies = data.movies.filter(m => {
                    if (!m.digital_date) return false;
                    return new Date(m.digital_date) <= today;
                });

                this.setupFilterEventListeners();
                this.setupSearchEventListeners();
                this.setupCardFlipHandler();
                this.setupLightboxKeyboardHandler();
                this.applyFilter();
                this.renderWallWithMore();
            } else {
                document.getElementById('wall').innerHTML = '<p>No movies in database</p>';
            }
        } catch (err) {
            console.error('Load failed:', err);
            document.getElementById('wall').innerHTML = '<p>Failed to load movies</p>';
        }
    },

    setupCardFlipHandler() {
        // Add click handler to open lightbox directly (experimental UIX)
        document.getElementById('wall').addEventListener('click', (e) => {
            if (e.target.tagName === 'A') return;
            if (e.target.closest('.movie-info')) return;
            if (e.target.closest('.expand-btn')) return; // Let expand btn handle itself
            const container = e.target.closest('.movie-container');
            if (container) {
                // Find movie ID from the expand button in this container
                const expandBtn = container.querySelector('.expand-btn');
                if (expandBtn) {
                    const onclickAttr = expandBtn.getAttribute('onclick');
                    const match = onclickAttr.match(/openLightbox\('([^']+)'\)/);
                    if (match) {
                        this.openLightbox(match[1]);
                    }
                }
            }
        });
    },

    setupFilterEventListeners() {
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const filter = e.target.dataset.filter;

                if (filter === 'all') {
                    // "All" clears all other filters
                    this.activeFilters.clear();
                    filterButtons.forEach(b => b.classList.remove('active'));
                    e.target.classList.add('active');
                } else {
                    // Toggle this filter on/off (multi-select)
                    if (this.activeFilters.has(filter)) {
                        this.activeFilters.delete(filter);
                        e.target.classList.remove('active');
                    } else {
                        this.activeFilters.add(filter);
                        e.target.classList.add('active');
                    }

                    // Remove "All" active state when other filters are selected
                    const allBtn = document.querySelector('.filter-btn[data-filter="all"]');
                    if (this.activeFilters.size > 0) {
                        allBtn.classList.remove('active');
                    } else {
                        // No filters selected = "All" is active
                        allBtn.classList.add('active');
                    }
                }

                this.displayedCount = this.loadIncrement; // Reset when changing filters
                this.applyFilter();
                this.renderWallWithMore();
            });
        });
    },

    setupSearchEventListeners() {
        const searchInput = document.getElementById('search-input');
        const clearBtn = document.getElementById('search-clear');

        if (!searchInput) return;

        // Debounce search for performance
        let debounceTimer;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                this.searchQuery = e.target.value.trim().toLowerCase();
                this.displayedCount = this.loadIncrement; // Reset pagination
                this.applyFilter();
                this.renderWallWithMore();

                // Show/hide clear button
                if (clearBtn) {
                    clearBtn.style.display = this.searchQuery ? 'block' : 'none';
                }
            }, 200);
        });

        // Clear button
        if (clearBtn) {
            clearBtn.style.display = 'none';
            clearBtn.addEventListener('click', () => {
                searchInput.value = '';
                this.searchQuery = '';
                this.displayedCount = this.loadIncrement;
                this.applyFilter();
                this.renderWallWithMore();
                clearBtn.style.display = 'none';
                searchInput.focus();
            });
        }

        // Allow Escape to clear search
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                this.searchQuery = '';
                this.displayedCount = this.loadIncrement;
                this.applyFilter();
                this.renderWallWithMore();
                if (clearBtn) clearBtn.style.display = 'none';
                searchInput.blur();
            }
        });
    },

    applyFilter() {
        const filters = this.activeFilters;
        const query = this.searchQuery;

        this.filteredMovies = this.allMovies.filter(movie => {
            // If no filters selected, show all (except hidden)
            if (filters.size === 0) {
                // No category filter - show all
            } else {
                // Must pass ALL selected filters (AND logic)
                for (const filter of filters) {
                    switch (filter) {
                        case 'big-time':
                            if (movie.categories?.tier !== 'big_time') return false;
                            break;
                        case 'niche':
                            if (movie.categories?.tier !== 'niche') return false;
                            break;
                        case 'staff-picks':
                            if (!movie.categories?.is_staff_pick) return false;
                            break;
                        case 'foreign':
                            // Support both new categories object and legacy original_language
                            const isForeign = movie.categories?.is_foreign ??
                                (movie.original_language && movie.original_language !== 'en');
                            if (!isForeign) return false;
                            break;
                        case 'series':
                            if (movie.content_type !== 'limited_series') return false;
                            break;
                        case 'plex':
                            // Movies available in personal Plex library
                            if (!movie.plex || !movie.plex.deep_link) return false;
                            break;
                    }
                }
            }

            // Then apply search filter if query exists
            if (query) {
                const title = (movie.title || '').toLowerCase();
                const director = (movie.crew?.director || '').toLowerCase();
                const synopsis = (movie.synopsis || '').toLowerCase();
                const genres = (movie.genres || []).join(' ').toLowerCase();
                const country = (movie.country || '').toLowerCase();
                const year = String(movie.year || '');

                return title.includes(query) ||
                       director.includes(query) ||
                       synopsis.includes(query) ||
                       genres.includes(query) ||
                       country.includes(query) ||
                       year.includes(query);
            }

            return true;
        });
    },

    renderWallWithMore() {
        const sortedMovies = [...this.filteredMovies].sort((a, b) => {
            return new Date(b.digital_date) - new Date(a.digital_date);
        });

        const moviesToShow = sortedMovies.slice(0, this.displayedCount);
        const hasMore = this.displayedCount < sortedMovies.length;

        this.renderWall(moviesToShow);
        this.renderMoreButton(hasMore, sortedMovies.length);
    },

    renderMoreButton(hasMore, totalCount) {
        const container = document.getElementById('load-more-container');
        if (!container) return;

        if (hasMore) {
            const remaining = totalCount - this.displayedCount;
            container.innerHTML = `
                <button class="load-more-btn" onclick="NRW.loadMore()">
                    MORE (${remaining} more)
                </button>
            `;
        } else {
            container.innerHTML = '';
        }
    },

    loadMore() {
        this.displayedCount += this.loadIncrement;
        this.renderWallWithMore();
    },


    renderWall(movies) {
        const wall = document.getElementById('wall');

        // Sort by date descending, then staff picks first within each date
        movies.sort((a, b) => {
            const dateA = new Date(a.digital_date);
            const dateB = new Date(b.digital_date);
            if (dateB.getTime() !== dateA.getTime()) {
                return dateB - dateA;  // Newest first
            }
            // Same date: staff picks first
            const aStaffPick = a.categories?.is_staff_pick || this.staffPicks.includes(a.id);
            const bStaffPick = b.categories?.is_staff_pick || this.staffPicks.includes(b.id);
            if (aStaffPick && !bStaffPick) return -1;
            if (!aStaffPick && bStaffPick) return 1;
            return 0;
        });

        let html = '';
        let lastDate = '';
        let isFirstDate = true;

        movies.forEach(movie => {
            const date = movie.digital_date.substring(0, 10);

            // Add inline date divider card when date changes
            if (date !== lastDate) {
                // Add NEW TRAILERS button before the first date marker
                if (isFirstDate && this.latestPlaylistUrl) {
                    html += `<a href="${this.latestPlaylistUrl}" target="_blank" rel="noopener noreferrer" class="trailers-card">
                        <div class="trailers-content">
                            <div class="trailers-text">THIS WEEK'S</div>
                            <div class="trailers-text">TRAILERS</div>
                            <div class="trailers-icon">▶</div>
                        </div>
                    </a>`;
                    isFirstDate = false;
                }

                const d = new Date(date + 'T12:00:00');

                // Check if this is a bootstrap date for visual indicator
                const isBootstrapDate = movie.bootstrap_date;
                const datePrefix = isBootstrapDate ? '~' : '';
                const dateTitle = isBootstrapDate ? 'Approximate date - may have been available earlier' : '';

                html += `<div class="date-divider-card">
                    <div class="date-content ${isBootstrapDate ? 'date-approximate' : ''}" ${dateTitle ? `title="${dateTitle}"` : ''}>
                        <div class="date-day">${d.toLocaleDateString('en', {weekday: 'short'}).toUpperCase()}</div>
                        <div class="date-number">${datePrefix}${d.getDate()}</div>
                        <div class="date-month">${d.toLocaleDateString('en', {month: 'short'}).toUpperCase()}</div>
                    </div>
                </div>`;

                lastDate = date;
            }
            
            // Movie card
            const title = movie.title || 'Untitled';
            const year = movie.year || new Date(movie.digital_date).getFullYear();
            
            // Build metadata for bottom of card
            let bottomMetadata = [];
            if (movie.genres && movie.genres.length > 0) {
                bottomMetadata.push(movie.genres.slice(0, 2).join(' • '));
            }
            if (movie.studio) {
                bottomMetadata.push(movie.studio);
            }
            // For limited series: show episode count + runtime
            // For movies: just show runtime
            if (movie.content_type === 'limited_series' && movie.episode_count) {
                let seriesInfo = `${movie.episode_count} eps`;
                if (movie.runtime) {
                    seriesInfo += ` • ${movie.runtime} min/ep`;
                }
                bottomMetadata.push(seriesInfo);
            } else if (movie.runtime) {
                bottomMetadata.push(`${movie.runtime} min`);
            }
            const bottomInfo = bottomMetadata.join(' | ');

            // Build platform-based watch buttons (SVOD, Amazon, Apple, Plex)
            const buildPlatformButtons = (movie) => {
                const watchLinks = movie.watch_links || {};
                const providers = movie.providers || {};
                let buttonsHtml = '';

                // Check for Plex availability (personal library)
                const plexInfo = this.plexLibrary[String(movie.id)];
                if (plexInfo && plexInfo.web_url) {
                    buttonsHtml += `<a href="${plexInfo.web_url}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-plex" aria-label="Play on Plex" title="Play on your Plex server"><img src="logos%20and%20images/plex-logo.png" alt="Plex" class="btn-logo" onerror="this.parentElement.innerHTML='PLEX'"></a>`;
                }

                // Helper to get display name for a service
                const getDisplayName = (service) => {
                    const s = service.toLowerCase();
                    if (s.includes('amazon') || s.includes('prime')) return 'PRIME';
                    if (s.includes('disney')) return 'DISNEY+';
                    if (s.includes('hbo') || s.includes('max')) return 'MAX';
                    if (s.includes('netflix')) return 'NETFLIX';
                    if (s.includes('hulu')) return 'HULU';
                    if (s.includes('peacock')) return 'PEACOCK';
                    return service.toUpperCase();
                };

                // Helper to render streaming button (active or disabled)
                const renderStreamButton = (service, link) => {
                    const displayName = getDisplayName(service);
                    if (link) {
                        // Active button with link
                        if (displayName === 'PRIME') {
                            return `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on Prime Video"><img src="logos%20and%20images/amazon%20prime.png" alt="Prime Video" class="btn-logo"></a>`;
                        } else if (displayName === 'NETFLIX') {
                            return `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on Netflix"><img src="logos%20and%20images/netflix%20square%20logo.png" alt="Netflix" class="btn-logo"></a>`;
                        } else {
                            return `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on ${service}">${displayName}</a>`;
                        }
                    } else {
                        // Disabled button - service known but no link (needs admin correction)
                        if (displayName === 'NETFLIX') {
                            return `<span class="watch-btn watch-btn-stream watch-btn-disabled" aria-disabled="true" title="On Netflix - link pending"><img src="logos%20and%20images/netflix%20square%20logo.png" alt="Netflix" class="btn-logo"></span>`;
                        } else if (displayName === 'PRIME') {
                            return `<span class="watch-btn watch-btn-stream watch-btn-disabled" aria-disabled="true" title="On Prime - link pending"><img src="logos%20and%20images/amazon%20prime.png" alt="Prime Video" class="btn-logo"></span>`;
                        } else {
                            return `<span class="watch-btn watch-btn-stream watch-btn-disabled" aria-disabled="true" title="On ${service} - link pending">${displayName}</span>`;
                        }
                    }
                };

                // 1. SVOD Streaming Button
                // Check watch_links first, then fall back to providers
                let streamingService = watchLinks.streaming?.service;
                let streamingLink = watchLinks.streaming?.link;

                // If no watch_links.streaming but providers.streaming exists, use first provider
                if (!streamingService && providers.streaming?.length > 0) {
                    // Filter out "with Ads" variants to get primary service
                    const primaryProvider = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
                    streamingService = primaryProvider;
                    streamingLink = null; // No link available
                }

                if (streamingService) {
                    buttonsHtml += renderStreamButton(streamingService, streamingLink);
                }

                // 2. Purchase Buttons (Amazon + Apple)
                let amazonLink = null;
                let appleLink = null;

                // Check for Amazon in VOD
                if (watchLinks.vod?.service?.toLowerCase().includes('amazon') && watchLinks.vod?.link) {
                    amazonLink = watchLinks.vod.link;
                }

                // Check for Apple in VOD
                if (watchLinks.vod?.service?.toLowerCase().includes('apple') && watchLinks.vod?.link) {
                    appleLink = watchLinks.vod.link;
                }

                // Add purchase buttons directly (not in separate wrapper)
                if (amazonLink) {
                    buttonsHtml += `<a href="${amazonLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-purchase" aria-label="Rent/Buy on Amazon"><img src="logos%20and%20images/pngimg.com%20-%20amazon_PNG17.png" alt="Amazon" class="btn-logo"></a>`;
                }

                if (appleLink) {
                    buttonsHtml += `<a href="${appleLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-purchase" aria-label="Rent/Buy on Apple TV"><img src="logos%20and%20images/apple%20logo.png" alt="Apple" class="btn-logo"></a>`;
                }

                // If no valid links at all, show disabled placeholder
                if (!buttonsHtml) {
                    buttonsHtml = '<span class="watch-btn watch-btn-disabled" aria-disabled="true" title="Link not available">NOT AVAILABLE</span>';
                }

                // Wrap all buttons in a single container
                return `<div class="watch-buttons">${buttonsHtml}</div>`;
            };

            const platformButtons = buildPlatformButtons(movie);

            // Info links - Only Trailer, RT, Wiki
            let infoLinks = [];

            if (movie.links?.trailer) {
                infoLinks.push(`<a href="#" onclick="NRW.showTrailer('${movie.links.trailer}'); return false;" class="info-btn">Trailer</a>`);
            }

            if (movie.links?.rt) {
                const rtText = movie.rt_score ? `RT ${movie.rt_score}` : 'RT';
                const rtClass = movie.rt_score ? 'info-btn' : 'info-btn info-btn-neutral';
                infoLinks.push(`<a href="${movie.links.rt}" target="_blank" rel="noopener noreferrer" class="${rtClass}">${rtText}</a>`);
            }

            if (movie.links?.wikipedia) {
                infoLinks.push(`<a href="${movie.links.wikipedia}" target="_blank" rel="noopener noreferrer" class="info-btn">Wiki</a>`);
            }

            const isStaffPick = movie.categories?.is_staff_pick || this.staffPicks.includes(movie.id);
            const staffPickClass = isStaffPick ? ' staff-pick-movie' : '';
            const staffPickBadge = isStaffPick ? '<div class="staff-pick-badge">STAFF PICK</div>' : '';

            // Streaming service pill badge for card front
            const getStreamingBadge = (movie) => {
                const watchLinks = movie.watch_links || {};
                const providers = movie.providers || {};

                // Get streaming service name
                let service = watchLinks.streaming?.service;
                if (!service && providers.streaming?.length > 0) {
                    service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
                }

                if (!service) return '';

                // Map service to display name and CSS class
                const s = service.toLowerCase();
                let displayName, badgeClass;

                if (s.includes('netflix')) {
                    displayName = 'NETFLIX'; badgeClass = 'badge-netflix';
                } else if (s.includes('disney')) {
                    displayName = 'DISNEY+'; badgeClass = 'badge-disney';
                } else if (s.includes('hbo') || s.includes('max')) {
                    displayName = 'MAX'; badgeClass = 'badge-max';
                } else if (s.includes('amazon') || s.includes('prime')) {
                    displayName = 'PRIME'; badgeClass = 'badge-prime';
                } else if (s.includes('hulu')) {
                    displayName = 'HULU'; badgeClass = 'badge-hulu';
                } else if (s.includes('peacock')) {
                    displayName = 'PEACOCK'; badgeClass = 'badge-peacock';
                } else if (s.includes('mubi')) {
                    displayName = 'MUBI'; badgeClass = 'badge-mubi';
                } else if (s.includes('shudder')) {
                    displayName = 'SHUDDER'; badgeClass = 'badge-shudder';
                } else if (s.includes('criterion')) {
                    displayName = 'CRITERION'; badgeClass = 'badge-criterion';
                } else {
                    displayName = service.toUpperCase().slice(0, 10); badgeClass = 'badge-other';
                }

                return `<div class="streaming-badge ${badgeClass}">${displayName}</div>`;
            };

            const streamingBadge = getStreamingBadge(movie);

            html += `
            <div class="movie-container${staffPickClass}">
                ${staffPickBadge}
                <div class="movie-card">
                    <div class="card-inner">
                        <div class="card-front">
                            ${streamingBadge}
                            <div class="poster-fallback"><span class="poster-fallback-title">${title}</span></div>
                            <img src="${movie.poster || ''}"
                                 onerror="this.style.display='none';"
                                 ${movie.poster ? '' : 'style="display:none"'}>
                            <button class="expand-btn" onclick="event.stopPropagation(); NRW.openLightbox('${movie.id}')" aria-label="View fullscreen">&#x26F6;</button>
                        </div>
                        <div class="card-back">
                            <div class="synopsis">${movie.synopsis || 'Synopsis coming soon'}</div>
                            <div class="actions">
                                ${platformButtons}
                                <div class="info-links">
                                    ${infoLinks.join('')}
                                </div>
                            </div>
                            <div class="bottom-meta">${bottomInfo}</div>
                        </div>
                    </div>
                </div>
                <div class="movie-info">
                    <div class="movie-title">${movie.title}</div>
                    <span class="director">${movie.crew?.director || 'Unknown Director'}</span> • <span class="country">${(movie.country === 'United States of America' ? 'USA' : movie.country) || 'Unknown Country'}</span>
                </div>
            </div>`;
        });
        
        wall.innerHTML = html;
    },

    // Extract YouTube video ID from various URL formats
    extractYouTubeId(url) {
        if (!url) return null;

        // Handle various YouTube URL formats
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
    },

    // Show trailer in embedded modal
    showTrailer(url) {
        const videoId = this.extractYouTubeId(url);

        if (!videoId) {
            // Not a YouTube URL, open in new tab as fallback
            window.open(url, '_blank');
            return;
        }

        // Create modal if it doesn't exist
        let modal = document.getElementById('trailer-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'trailer-modal';
            modal.className = 'trailer-modal';
            modal.innerHTML = `
                <div class="trailer-modal-backdrop" onclick="NRW.closeTrailer()"></div>
                <div class="trailer-modal-content">
                    <button class="trailer-close-btn" onclick="NRW.closeTrailer()" aria-label="Close trailer">&times;</button>
                    <div class="trailer-video-container">
                        <iframe id="trailer-iframe"
                            src=""
                            frameborder="0"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                            allowfullscreen>
                        </iframe>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            // Close on Escape key (only if trailer is showing, stop propagation so lightbox doesn't also close)
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && modal.classList.contains('active')) {
                    e.stopPropagation();
                    this.closeTrailer();
                }
            });
        }

        // Set the iframe source with autoplay
        const iframe = document.getElementById('trailer-iframe');
        iframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0`;

        // Show modal
        modal.classList.add('active');
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    },

    // Close trailer modal
    closeTrailer() {
        const modal = document.getElementById('trailer-modal');
        if (modal) {
            modal.classList.remove('active');
            // Stop the video by clearing the src
            const iframe = document.getElementById('trailer-iframe');
            if (iframe) iframe.src = '';
            document.body.style.overflow = ''; // Restore scrolling
        }
    },

    // ========================================
    // Fullscreen Poster Lightbox
    // ========================================

    // Open lightbox with a specific movie
    openLightbox(movieId) {
        // Build list of currently displayed movies (in order)
        this.lightboxMovies = this.filteredMovies
            .slice(0, this.displayedCount)
            .filter(m => m.poster); // Only movies with posters

        // Find the index of the selected movie
        const index = this.lightboxMovies.findIndex(m => String(m.id) === String(movieId));
        if (index === -1) return;

        this.lightboxIndex = index;
        this.updateLightbox();

        // Show lightbox
        const lightbox = document.getElementById('poster-lightbox');
        lightbox.classList.add('active');
        document.body.style.overflow = 'hidden';
    },

    // Close lightbox
    closeLightbox() {
        const lightbox = document.getElementById('poster-lightbox');
        lightbox.classList.remove('active');
        document.body.style.overflow = '';
    },

    // Navigate in lightbox
    lightboxNav(direction) {
        const count = this.lightboxMovies.length;
        this.lightboxIndex = (this.lightboxIndex + direction + count) % count;
        this.updateLightbox();
    },

    // Update lightbox content
    updateLightbox() {
        const movie = this.lightboxMovies[this.lightboxIndex];
        if (!movie) return;

        // Update poster
        document.getElementById('lightbox-poster').src = movie.poster || '';

        // Update title
        document.getElementById('lightbox-title').textContent = movie.title;

        // Build meta info (now includes studio)
        const metaParts = [];
        if (movie.year) metaParts.push(movie.year);
        if (movie.genres?.length) metaParts.push(movie.genres.slice(0, 2).join(', '));
        if (movie.runtime) metaParts.push(`${movie.runtime} min`);
        if (movie.crew?.director) metaParts.push(`Dir: ${movie.crew.director}`);
        if (movie.studio) metaParts.push(movie.studio);
        document.getElementById('lightbox-meta').textContent = metaParts.join(' • ');

        // Update synopsis
        document.getElementById('lightbox-synopsis').textContent = movie.synopsis || 'Synopsis coming soon.';

        // Build buttons - now includes all card-back actions
        let buttonsHtml = '';
        const watchLinks = movie.watch_links || {};
        const providers = movie.providers || {};

        // Streaming button
        if (watchLinks.streaming?.link) {
            buttonsHtml += `<a href="${watchLinks.streaming.link}" target="_blank" rel="noopener noreferrer" class="lightbox-btn lightbox-btn-primary">Watch on ${watchLinks.streaming.service || 'Streaming'}</a>`;
        } else if (providers.streaming?.length) {
            buttonsHtml += `<span class="lightbox-btn lightbox-btn-primary" style="opacity:0.6;cursor:default">On ${providers.streaming[0]}</span>`;
        }

        // Plex button
        const plexInfo = this.plexLibrary[String(movie.id)];
        if (plexInfo?.web_url) {
            buttonsHtml += `<a href="${plexInfo.web_url}" target="_blank" rel="noopener noreferrer" class="lightbox-btn lightbox-btn-secondary">Play on Plex</a>`;
        }

        // Amazon purchase button
        if (watchLinks.vod?.service?.toLowerCase().includes('amazon') && watchLinks.vod?.link) {
            buttonsHtml += `<a href="${watchLinks.vod.link}" target="_blank" rel="noopener noreferrer" class="lightbox-btn lightbox-btn-secondary">Rent/Buy on Amazon</a>`;
        }

        // Apple purchase button
        if (watchLinks.vod?.service?.toLowerCase().includes('apple') && watchLinks.vod?.link) {
            buttonsHtml += `<a href="${watchLinks.vod.link}" target="_blank" rel="noopener noreferrer" class="lightbox-btn lightbox-btn-secondary">Rent/Buy on Apple TV</a>`;
        }

        // Trailer button
        if (movie.links?.trailer) {
            buttonsHtml += `<button class="lightbox-btn lightbox-btn-secondary" onclick="NRW.showTrailer('${movie.links.trailer}')">Watch Trailer</button>`;
        }

        // Rotten Tomatoes
        if (movie.links?.rt) {
            const rtScore = movie.rt_score ? ` (${movie.rt_score})` : '';
            buttonsHtml += `<a href="${movie.links.rt}" target="_blank" rel="noopener noreferrer" class="lightbox-btn lightbox-btn-secondary">Rotten Tomatoes${rtScore}</a>`;
        }

        // Wikipedia
        if (movie.links?.wikipedia) {
            buttonsHtml += `<a href="${movie.links.wikipedia}" target="_blank" rel="noopener noreferrer" class="lightbox-btn lightbox-btn-secondary">Wikipedia</a>`;
        }

        document.getElementById('lightbox-buttons').innerHTML = buttonsHtml;
    },

    // Setup lightbox keyboard navigation
    setupLightboxKeyboardHandler() {
        document.addEventListener('keydown', (e) => {
            const lightbox = document.getElementById('poster-lightbox');
            if (!lightbox.classList.contains('active')) return;

            if (e.key === 'Escape') {
                this.closeLightbox();
            } else if (e.key === 'ArrowLeft') {
                this.lightboxNav(-1);
            } else if (e.key === 'ArrowRight') {
                this.lightboxNav(1);
            }
        });
    }
};

// Start on page load
document.addEventListener('DOMContentLoaded', () => NRW.init());