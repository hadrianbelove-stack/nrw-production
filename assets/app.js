// Configuration - change these values to adjust behavior
const CONFIG = {
    moviesPerPage: 60,       // How many movies to show initially and add on "More"
    searchDebounceMs: 200    // Milliseconds to wait before searching after typing
};

const NRW = {
    allMovies: [],
    filteredMovies: [],
    staffPicks: [],  // Renamed from featuredMovies
    latestPlaylistUrl: null,  // YouTube trailers playlist URL
    plexLibrary: {},  // TMDB ID -> Plex URLs mapping (personal, local only)
    activeFilters: new Set(),  // Multi-select: Set of active filter IDs
    searchQuery: '',     // Current search query
    displayedCount: CONFIG.moviesPerPage,  // How many movies currently shown
    loadIncrement: CONFIG.moviesPerPage,   // How many to add when clicking "More"

    // Country display names per STYLE_GUIDE.md
    // Only shorten long/formal names; keep short names as-is
    countryAbbrev: {
        'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA',
        'united kingdom': 'UK', 'great britain': 'UK',
        'south korea': 'S. Korea',
        'south africa': 'S. Africa',
        'new zealand': 'N. Zealand',
        'bosnia and herzegovina': 'Bosnia',
        'saudi arabia': 'S. Arabia'
    },

    abbreviateCountry(country) {
        if (!country) return null;
        const shortened = this.countryAbbrev[country.toLowerCase()];
        if (shortened) return shortened;
        // Fix all-caps or all-lowercase entries (e.g. "SWEDEN" → "Sweden")
        if (country !== country[0].toUpperCase() + country.slice(1).toLowerCase()) {
            return country[0].toUpperCase() + country.slice(1).toLowerCase();
        }
        return country;
    },

    // Service config — single source of truth for web
    // Sync with: assets/service-colors.json, assets/styles.css
    SERVICE_MAP: {
        netflix:   { class: 'netflix',   name: 'NETFLIX',      badgeName: 'NETFLIX',   matches: ['netflix'] },
        max:       { class: 'max',       name: 'MAX',          badgeName: 'MAX',       matches: ['max', 'hbo'] },
        disney:    { class: 'disney',    name: 'DISNEY+',      badgeName: 'DISNEY+',   matches: ['disney'] },
        prime:     { class: 'prime',     name: 'PRIME VIDEO',  badgeName: 'PRIME',     matches: ['amazon', 'prime'] },
        hulu:      { class: 'hulu',      name: 'HULU',         badgeName: 'HULU',      matches: ['hulu'] },
        peacock:   { class: 'peacock',   name: 'PEACOCK',      badgeName: 'PEACOCK',   matches: ['peacock'] },
        mubi:      { class: 'mubi',      name: 'MUBI',         badgeName: 'MUBI',      matches: ['mubi'] },
        shudder:   { class: 'shudder',   name: 'SHUDDER',      badgeName: 'SHUDDER',   matches: ['shudder'] },
        criterion: { class: 'criterion', name: 'CRITERION',    badgeName: 'CRITERION', matches: ['criterion'] },
        tubi:      { class: 'tubi',      name: 'TUBI',         badgeName: 'TUBI',      matches: ['tubi'] },
        plex:      { class: 'plex',      name: 'PLEX',         badgeName: 'PLEX',      matches: ['plex'] },
    },

    // Resolve a raw service string (e.g. "Netflix basic with Ads") to its config entry
    resolveService(rawName) {
        if (!rawName) return null;
        const s = rawName.toLowerCase();
        for (const entry of Object.values(this.SERVICE_MAP)) {
            if (entry.matches.some(m => s.includes(m))) return entry;
        }
        return null;
    },

    getPurchaseLabel(service) {
        const s = service.toLowerCase();
        if (s.includes('amazon') || s.includes('prime')) return 'AMAZON';
        if (s.includes('apple') || s.includes('itunes')) return 'APPLE TV';
        return service.toUpperCase();
    },

    // Lightbox state
    lightboxMovies: [],  // Movies currently in the lightbox (filtered/displayed)
    lightboxIndex: 0,    // Current index in lightbox
    trailerLightboxIndex: -1,  // Index in lightboxMovies of the movie whose trailer is playing (-1 = none)

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
                    if (m.hidden) return false;
                    if (!m.digital_date) return false;
                    return new Date(m.digital_date) <= today;
                });

                this.setupFilterEventListeners();
                this.setupSearchEventListeners();
                this.setupCardFlipHandler();
                this.setupLightboxKeyboardHandler();
                this.setupDelegatedClickHandlers();
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
                // Find movie ID from the expand button's data attribute
                const expandBtn = container.querySelector('.expand-btn[data-movie-id]');
                if (expandBtn) {
                    this.openLightbox(expandBtn.dataset.movieId);
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
            }, CONFIG.searchDebounceMs);
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
                // Must pass ANY selected filter (OR logic - cumulative)
                let matchesAny = false;
                for (const filter of filters) {
                    switch (filter) {
                        case 'big-time':
                            if (movie.categories?.tier === 'big_time') matchesAny = true;
                            break;
                        case 'niche':
                            if (movie.categories?.tier === 'niche') matchesAny = true;
                            break;
                        case 'staff-picks':
                            if (movie.categories?.is_staff_pick || movie.featured) matchesAny = true;
                            break;
                        case 'foreign': {
                            const isForeign = movie.categories?.is_foreign ??
                                (movie.original_language && movie.original_language !== 'en');
                            if (isForeign) matchesAny = true;
                            break;
                        }
                        case 'series':
                            if (movie.content_type === 'limited_series') matchesAny = true;
                            break;
                        case 'plex':
                            if (movie.plex && movie.plex.deep_link) matchesAny = true;
                            break;
                        case 'restorations':
                            if (movie.categories?.is_restoration) matchesAny = true;
                            break;
                        case 'festivals':
                            if (movie.categories?.is_festival) matchesAny = true;
                            break;
                    }
                    if (matchesAny) break;
                }
                if (!matchesAny) return false;
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
                <button class="load-more-btn">
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
                    const now = new Date();
                    const weekStart = new Date(now);
                    weekStart.setDate(now.getDate() - now.getDay());
                    const weekEnd = new Date(weekStart);
                    weekEnd.setDate(weekStart.getDate() + 6);
                    const dateRange = weekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' - ' + weekEnd.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    html += `<a href="${this.latestPlaylistUrl}" target="_blank" rel="noopener noreferrer" class="trailers-card">
                        <div class="trailers-content">
                            <div class="trailers-text">NEW</div>
                            <div class="trailers-text">TRAILERS</div>
                            <div class="trailers-date">${dateRange}</div>
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

                // 2. Purchase Buttons (VOD: separate Amazon + Apple TV buttons)
                const vodEntries = Array.isArray(watchLinks.vod) ? watchLinks.vod
                    : (watchLinks.vod?.service ? [watchLinks.vod] : []);

                vodEntries.forEach(vod => {
                    const vodLink = vod.link || vod.url;
                    if (vod.service && vodLink) {
                        const svc = vod.service.toLowerCase();
                        if (svc.includes('amazon') || svc.includes('prime')) {
                            buttonsHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-amazon" aria-label="Rent/Buy on Amazon"><img src="logos%20and%20images/pngimg.com%20-%20amazon_PNG17.png" alt="Amazon" class="btn-logo"></a>`;
                        } else if (svc.includes('apple') || svc.includes('itunes')) {
                            buttonsHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-apple" aria-label="Rent/Buy on Apple TV"><img src="logos%20and%20images/apple%20logo.png" alt="Apple TV" class="btn-logo"></a>`;
                        } else if (svc.includes('eventive') || vodLink.includes('eventive.org') || vodLink.includes('festivalplayer') || vodLink.includes('shift72.com')) {
                            buttonsHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-festival" aria-label="Buy Ticket">BUY TICKET</a>`;
                        } else {
                            buttonsHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-purchase" aria-label="Rent/Buy on ${vod.service}">${vod.service.toUpperCase()}</a>`;
                        }
                    }
                });

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

            const cardTrailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
            if (cardTrailerUrl) {
                infoLinks.push(`<a href="#" data-trailer="${cardTrailerUrl}" class="info-btn">Trailer</a>`);
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
                const resolved = NRW.resolveService(service);
                let displayName, badgeClass;
                if (resolved) {
                    displayName = resolved.badgeName;
                    badgeClass = 'badge-' + resolved.class;
                } else {
                    displayName = service.toUpperCase().slice(0, 10);
                    badgeClass = 'badge-other';
                }

                return `<div class="streaming-badge ${badgeClass}">${displayName}</div>`;
            };

            const streamingBadge = getStreamingBadge(movie);
            const restorationBadge = movie.categories?.is_restoration
                ? '<div class="restoration-badge">RESTORED</div>' : '';
            const festivalRibbon = movie.categories?.is_festival
                ? '<div class="festival-ribbon">FESTIVAL SCREENING</div>' : '';

            html += `
            <div class="movie-container${staffPickClass}">
                ${staffPickBadge}
                <div class="movie-card">
                    <div class="card-inner">
                        <div class="card-front">
                            ${streamingBadge}
                            ${restorationBadge}
                            ${festivalRibbon}
                            <div class="poster-fallback"><span class="poster-fallback-title">${title}</span></div>
                            <img src="${movie.poster || ''}"
                                 onerror="this.style.display='none';"
                                 ${movie.poster ? '' : 'style="display:none"'}>
                            <button class="expand-btn" data-movie-id="${movie.id}" aria-label="View fullscreen">&#x26F6;</button>
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
                    <span class="director">${movie.crew?.director || 'Unknown Director'}</span> • <span class="country">${NRW.abbreviateCountry(movie.country) || 'Unknown Country'}</span>
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

    // Check if URL points to a self-hosted MP4 trailer (resilient to query strings)
    isHostedTrailer(url) {
        if (!url) return false;
        try {
            const pathname = new URL(url).pathname;
            return pathname.endsWith('.mp4') || url.includes('/file/NRW-TRAILERS/');
        } catch {
            return url.endsWith('.mp4') || url.includes('/file/NRW-TRAILERS/');
        }
    },

    // Find next/prev movie index in lightboxMovies that has a trailer
    // direction: +1 (forward) or -1 (backward), wraps around
    // Returns -1 if no other movie with a trailer exists
    findNextTrailerIndex(fromIndex, direction) {
        const count = this.lightboxMovies.length;
        if (count === 0) return -1;
        let idx = fromIndex;
        for (let i = 0; i < count - 1; i++) {
            idx = (idx + direction + count) % count;
            const movie = this.lightboxMovies[idx];
            const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
            if (trailerUrl) return idx;
        }
        return -1;
    },

    // Load a trailer video into the existing trailer modal container
    loadTrailerVideo(url) {
        const container = document.getElementById('trailer-video-container');
        if (!container) return;

        // Stop any existing video/iframe first
        const existingVideo = container.querySelector('video');
        if (existingVideo) { existingVideo.pause(); existingVideo.src = ''; }
        const existingIframe = container.querySelector('iframe');
        if (existingIframe) { existingIframe.src = ''; }

        if (this.isHostedTrailer(url)) {
            container.innerHTML = `
                <div class="trailer-loading" id="trailer-loading">
                    <div class="trailer-spinner"></div>
                    <span>Loading trailer...</span>
                </div>
                <div class="trailer-error" id="trailer-error" style="display:none;">
                    Trailer unavailable
                </div>
                <video id="trailer-video"
                    src="${url}"
                    controls
                    autoplay
                    preload="auto"
                    style="background: #000;">
                    Your browser does not support video playback.
                </video>
            `;
            const video = document.getElementById('trailer-video');
            const loading = document.getElementById('trailer-loading');
            const error = document.getElementById('trailer-error');
            video.addEventListener('canplay', () => { loading.style.display = 'none'; }, { once: true });
            video.addEventListener('error', () => { loading.style.display = 'none'; error.style.display = ''; }, { once: true });
        } else {
            const videoId = this.extractYouTubeId(url);
            if (!videoId) {
                window.open(url, '_blank');
                return;
            }
            container.innerHTML = `
                <iframe id="trailer-iframe"
                    src="https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0"
                    frameborder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                    allowfullscreen>
                </iframe>
            `;
        }
    },

    // Navigate to next/prev trailer within the lightbox movie list
    trailerNav(direction) {
        if (this.trailerLightboxIndex < 0) return;
        const nextIdx = this.findNextTrailerIndex(this.trailerLightboxIndex, direction);
        if (nextIdx < 0) return;

        this.trailerLightboxIndex = nextIdx;
        const movie = this.lightboxMovies[nextIdx];
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;

        const titleEl = document.getElementById('trailer-movie-title');
        if (titleEl) titleEl.textContent = movie.title;

        this.updateTrailerNavVisibility();
        this.loadTrailerVideo(trailerUrl);
    },

    // Show/hide trailer nav arrows based on whether neighbors have trailers
    updateTrailerNavVisibility() {
        const prevBtn = document.getElementById('trailer-nav-prev');
        const nextBtn = document.getElementById('trailer-nav-next');
        if (!prevBtn || !nextBtn) return;

        if (this.trailerLightboxIndex < 0 || this.lightboxMovies.length === 0) {
            prevBtn.style.display = 'none';
            nextBtn.style.display = 'none';
            return;
        }

        prevBtn.style.display = this.findNextTrailerIndex(this.trailerLightboxIndex, -1) >= 0 ? '' : 'none';
        nextBtn.style.display = this.findNextTrailerIndex(this.trailerLightboxIndex, 1) >= 0 ? '' : 'none';
    },

    // Show trailer in embedded modal (supports self-hosted MP4 and YouTube)
    showTrailer(url) {
        // Create modal if it doesn't exist
        let modal = document.getElementById('trailer-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'trailer-modal';
            modal.className = 'trailer-modal';
            modal.innerHTML = `
                <div class="trailer-modal-backdrop"></div>
                <div class="trailer-modal-content">
                    <div class="trailer-header">
                        <span class="trailer-movie-title" id="trailer-movie-title"></span>
                        <button class="trailer-close-btn" aria-label="Close trailer">&times;</button>
                    </div>
                    <div class="trailer-nav-wrapper">
                        <button class="trailer-nav prev" id="trailer-nav-prev" aria-label="Previous trailer">&larr;</button>
                        <div class="trailer-video-container" id="trailer-video-container"></div>
                        <button class="trailer-nav next" id="trailer-nav-next" aria-label="Next trailer">&rarr;</button>
                    </div>
                    <div class="trailer-hint">Arrow keys to navigate trailers &bull; ESC to return</div>
                </div>
            `;
            document.body.appendChild(modal);

            // Close on backdrop click
            modal.querySelector('.trailer-modal-backdrop').addEventListener('click', () => this.closeTrailer());
            modal.querySelector('.trailer-close-btn').addEventListener('click', () => this.closeTrailer());

            // Nav arrow clicks
            modal.querySelector('#trailer-nav-prev').addEventListener('click', () => this.trailerNav(-1));
            modal.querySelector('#trailer-nav-next').addEventListener('click', () => this.trailerNav(1));

            // Close on Escape key (stop propagation so lightbox doesn't also close)
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && modal.classList.contains('active')) {
                    e.stopPropagation();
                    this.closeTrailer();
                }
            });
        }

        // Determine which movie this trailer belongs to
        this.trailerLightboxIndex = this.lightboxMovies.findIndex(m => {
            const mUrl = m.links?.trailer_hosted || m.links?.trailer;
            return mUrl === url;
        });

        // Set movie title
        const titleEl = document.getElementById('trailer-movie-title');
        if (titleEl && this.trailerLightboxIndex >= 0) {
            titleEl.textContent = this.lightboxMovies[this.trailerLightboxIndex].title;
        } else if (titleEl) {
            titleEl.textContent = '';
        }

        this.updateTrailerNavVisibility();
        this.loadTrailerVideo(url);

        // Show modal
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    },

    // Close trailer modal
    closeTrailer() {
        const modal = document.getElementById('trailer-modal');
        if (modal) {
            modal.classList.remove('active');
            const container = document.getElementById('trailer-video-container');
            if (container) {
                const video = container.querySelector('video');
                if (video) { video.pause(); video.src = ''; }
                const iframe = container.querySelector('iframe');
                if (iframe) { iframe.src = ''; }
            }

            // Sync lightbox to the movie whose trailer was playing
            if (this.trailerLightboxIndex >= 0) {
                this.lightboxIndex = this.trailerLightboxIndex;
                this.updateLightbox();
            }
            this.trailerLightboxIndex = -1;

            // Only restore scrolling if lightbox isn't still open
            const lightbox = document.getElementById('poster-lightbox');
            if (!lightbox || !lightbox.classList.contains('active')) {
                document.body.style.overflow = '';
            }
        }
    },

    // ========================================
    // Fullscreen Poster Lightbox
    // ========================================

    // Open lightbox with a specific movie
    openLightbox(movieId) {
        // Build list of currently displayed movies (sorted by date, matching page render order)
        this.lightboxMovies = [...this.filteredMovies]
            .sort((a, b) => new Date(b.digital_date) - new Date(a.digital_date))
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

        // Update release date
        const dateEl = document.getElementById('lightbox-date');
        if (dateEl) {
            if (movie.digital_date) {
                const [y, m, d] = movie.digital_date.split('-');
                const dt = new Date(y, m - 1, d);
                dateEl.textContent = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            } else {
                dateEl.textContent = '';
            }
        }

        // Update Staff Pick badge
        const staffPickBadge = document.getElementById('lightbox-staff-pick');
        if (staffPickBadge) {
            if (movie.categories?.is_staff_pick) {
                staffPickBadge.style.display = 'inline-block';
            } else {
                staffPickBadge.style.display = 'none';
            }
        }

        // Update festival name in lightbox
        const festivalNameEl = document.getElementById('lightbox-festival-name');
        if (festivalNameEl) {
            if (movie.categories?.is_festival && movie.festival_info?.festival_name) {
                festivalNameEl.textContent = movie.festival_info.festival_name;
                festivalNameEl.style.display = 'block';
            } else {
                festivalNameEl.style.display = 'none';
            }
        }

        // Build meta info (now includes studio)
        const metaParts = [];
        if (movie.year) metaParts.push(movie.year);
        if (movie.genres?.length) metaParts.push(movie.genres.slice(0, 2).join(', '));
        if (movie.runtime) metaParts.push(`${movie.runtime} min`);
        if (movie.crew?.director) metaParts.push(`Dir: ${movie.crew.director}`);
        if (movie.country) metaParts.push(this.abbreviateCountry(movie.country));
        if (movie.studio) metaParts.push(movie.studio);
        document.getElementById('lightbox-meta').textContent = metaParts.join(' • ');

        // Update synopsis
        document.getElementById('lightbox-synopsis').textContent = movie.synopsis || 'Synopsis coming soon.';

        // === Watch stack (full-width, stacked, service-colored) ===
        let watchHtml = '';
        const watchLinks = movie.watch_links || {};
        const providers = movie.providers || {};

        // Streaming button
        let streamSvc = watchLinks.streaming?.service;
        let streamLink = watchLinks.streaming?.link;
        if (!streamSvc && providers.streaming?.length) {
            streamSvc = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
        }
        if (streamSvc) {
            const resolved = this.resolveService(streamSvc);
            const cls = resolved?.class || '';
            const name = resolved?.name || streamSvc.toUpperCase();
            if (streamLink) {
                watchHtml += `<a href="${streamLink}" target="_blank" rel="noopener noreferrer" class="watch-btn-lb stream ${cls}">${name}</a>`;
            } else {
                watchHtml += `<span class="watch-btn-lb stream ${cls}" style="opacity:0.6;cursor:default">${name}</span>`;
            }
        }

        // Purchase (VOD) buttons — separate Amazon + Apple TV
        const lbVodEntries = Array.isArray(watchLinks.vod) ? watchLinks.vod
            : (watchLinks.vod?.service ? [watchLinks.vod] : []);

        lbVodEntries.forEach(vod => {
            const vodLink = vod.link || vod.url;
            if (vod.service && vodLink) {
                const svc = vod.service.toLowerCase();
                let btnClass = 'purchase';
                let label;
                if (svc.includes('amazon') || svc.includes('prime')) {
                    btnClass = 'amazon';
                    label = this.getPurchaseLabel(vod.service);
                } else if (svc.includes('apple') || svc.includes('itunes')) {
                    btnClass = 'apple';
                    label = this.getPurchaseLabel(vod.service);
                } else if (svc.includes('eventive') || vodLink.includes('eventive.org') || vodLink.includes('festivalplayer') || vodLink.includes('shift72.com')) {
                    btnClass = 'festival';
                    label = 'BUY TICKET';
                } else {
                    label = this.getPurchaseLabel(vod.service);
                }
                watchHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn-lb ${btnClass}">${label}</a>`;
            }
        });

        // Plex button
        const plexInfo = this.plexLibrary[String(movie.id)];
        if (plexInfo?.web_url) {
            watchHtml += `<a href="${plexInfo.web_url}" target="_blank" rel="noopener noreferrer" class="watch-btn-lb plex">PLEX</a>`;
        }

        let buttonsHtml = '';
        if (watchHtml) buttonsHtml += `<div class="watch-stack">${watchHtml}</div>`;

        // === Info row (horizontal: Trailer, RT, Wiki) ===
        let infoHtml = '';
        const lbTrailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        if (lbTrailerUrl) {
            infoHtml += `<button class="info-btn-lb trailer" data-trailer="${lbTrailerUrl}">Trailer</button>`;
        }
        if (movie.links?.rt) {
            const score = movie.rt_score ? ` ${movie.rt_score}` : '';
            infoHtml += `<a href="${movie.links.rt}" target="_blank" rel="noopener noreferrer" class="info-btn-lb glass">RT${score}</a>`;
        }
        if (movie.links?.wikipedia) {
            infoHtml += `<a href="${movie.links.wikipedia}" target="_blank" rel="noopener noreferrer" class="info-btn-lb glass">Wiki</a>`;
        }
        if (infoHtml) buttonsHtml += `<div class="info-row">${infoHtml}</div>`;

        document.getElementById('lightbox-buttons').innerHTML = buttonsHtml;
    },

    // Setup lightbox keyboard navigation
    setupLightboxKeyboardHandler() {
        document.addEventListener('keydown', (e) => {
            // Handle trailer navigation when trailer modal is active
            const trailerModal = document.getElementById('trailer-modal');
            if (trailerModal && trailerModal.classList.contains('active')) {
                if (e.key === 'ArrowLeft') {
                    this.trailerNav(-1);
                } else if (e.key === 'ArrowRight') {
                    this.trailerNav(1);
                }
                // Escape is handled by showTrailer's own keydown listener
                return;
            }

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
    },

    // Delegated click handlers - one listener catches clicks on dynamically created elements
    setupDelegatedClickHandlers() {
        // Handle clicks on #wall (movie cards, expand buttons, trailer links, load more)
        document.getElementById('wall').addEventListener('click', (e) => {
            // Expand button -> open lightbox
            const expandBtn = e.target.closest('[data-movie-id]');
            if (expandBtn) {
                e.stopPropagation();
                this.openLightbox(expandBtn.dataset.movieId);
                return;
            }

            // Trailer link -> show trailer
            const trailerLink = e.target.closest('[data-trailer]');
            if (trailerLink) {
                e.preventDefault();
                this.showTrailer(trailerLink.dataset.trailer);
                return;
            }
        });

        // Handle clicks on load-more container
        document.getElementById('load-more-container').addEventListener('click', (e) => {
            if (e.target.closest('.load-more-btn')) {
                this.loadMore();
            }
        });

        // Handle clicks on document body for lightbox buttons
        document.body.addEventListener('click', (e) => {
            // Lightbox trailer button
            const lightboxTrailer = e.target.closest('#lightbox-buttons [data-trailer]');
            if (lightboxTrailer) {
                this.showTrailer(lightboxTrailer.dataset.trailer);
                return;
            }

            // Trailer modal backdrop or close button
            if (e.target.closest('.trailer-modal-backdrop') || e.target.closest('.trailer-close-btn')) {
                this.closeTrailer();
            }
        });
    }
};

// Start on page load
document.addEventListener('DOMContentLoaded', () => NRW.init());