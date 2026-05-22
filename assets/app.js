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
    activeFilters: new Set(),  // Multi-select: Set of active filter IDs
    searchQuery: '',     // Current search query
    displayedCount: CONFIG.moviesPerPage,  // How many movies currently shown
    loadIncrement: CONFIG.moviesPerPage,   // How many to add when clicking "More"

    // Shared config — loaded from assets/shared-config.js
    SERVICE_MAP: NRWConfig.SERVICE_MAP,
    VOD_SERVICE_MAP: NRWConfig.VOD_SERVICE_MAP,
    abbreviateCountry: NRWConfig.abbreviateCountry,

    // Filter descriptions — shown when a single filter is active
    FILTER_DESCRIPTIONS: {
        'studio': {
            title: 'Studio',
            text: 'The wide releases, the studio fare, the main-streamers. Not saying they\'re good, not saying they\'re bad, but these are the movies that have either entered or tried to enter the mainstream conversation. They have budgets, recognizable actors, and large-scale billboard campaigns.'
        },
        'indie': {
            title: 'Indie',
            text: 'The smaller films, the independents, the ones without a billboard campaign. These movies flew under the radar theatrically but are worth knowing about now that they\'re available to stream at home.'
        },
        'staff-picks': {
            title: 'NRW Picks',
            text: 'The ones we\'re vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations.'
        },
        'foreign': {
            title: 'Foreign',
            text: 'Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces. The only thing they have in common is subtitles and the fact that they\'re streaming now.'
        },
        'series': {
            title: 'Miniseries',
            text: 'Not movies — limited series. The kind you can finish in a weekend. Prestige mini-series and limited runs that landed on streaming and deserve the same attention as a good film.'
        },
        'restorations': {
            title: 'Reissues',
            text: 'Classic and catalog titles with new digital life. These are films that have been restored, remastered, or newly reissued on streaming platforms. Old movies, fresh transfers.'
        },
        'documentary': {
            title: 'Documentary',
            text: 'Non-fiction filmmaking. Documentaries covering real stories, real people, and real events — now available to stream at home.'
        },
        'virtual-screenings': {
            title: 'Virtual Screenings',
            text: 'Currently playing at film festivals. These aren\'t streaming yet — they\'re in theaters, at festivals, or doing the circuit. If you\'re near a screening, this is your heads-up.'
        },
        'pre-orders': {
            title: 'Pre-Orders',
            text: 'Coming soon. These movies have confirmed digital release dates and are available to pre-order now on storefronts like Apple TV and Amazon.'
        },
        'exploitation': {
            title: 'Exploitation',
            text: 'The genre stuff. Horror, thrillers, action \u2014 the movies that know exactly what they are and lean all the way in.'
        }
    },

    resolveService: NRWConfig.resolveService,
    resolveVODService: NRWConfig.resolveVODService,

    // Normalize streaming to {service, link} — handles both array and dict formats
    getStreaming(wl) {
        const s = wl?.streaming;
        if (Array.isArray(s) && s.length > 0) return s[0];
        if (s?.service) return s;
        return null;
    },

    // Render a tiny markdown subset (**bold**, *italic*) to safe HTML.
    // HTML is escaped first so synopsis text can never inject markup.
    renderMarkdown(text) {
        const esc = (text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        return esc
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em>$1</em>');
    },


    // Grid navigation state
    gridSelectedId: null,   // movie ID of selected card (string)
    gridNavActive: false,   // true once user presses an arrow key on the wall
    gridAnchorX: null,      // column memory: saved horizontal center for up/down nav

    // Lightbox state
    lightboxMovies: [],  // Movies currently in the lightbox (filtered/displayed)
    lightboxIndex: 0,    // Current index in lightbox
    lbRow: 0,  // Focused row in lightbox grid
    lbCol: 0,  // Focused column in lightbox grid
    trailerLightboxIndex: -1,  // Index in lightboxMovies of the movie whose trailer is playing (-1 = none)
    trailerReelMovies: [],     // Movies in the trailer reel (last 7 days with hosted trailers)
    isTrailerReel: false,      // true when playing the trailer reel (vs individual trailer from lightbox)

    // Convert Letterboxd score (0-5) to star glyphs: "3.8" → "★★★★☆"
    lbStars(score) {
        const n = Math.round(parseFloat(score));
        return '\u2605'.repeat(n) + '\u2606'.repeat(5 - n);
    },

    // Format screening end date: "2026-03-30" → "Mar 30"
    formatShortDate(dateStr) {
        if (!dateStr) return '';
        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const [y, m, d] = dateStr.split('-');
        return `${months[parseInt(m, 10) - 1]} ${parseInt(d, 10)}`;
    },

    async init() {
        try {
            // Load movie data
            const movieResponse = await fetch('data.json?t=' + Date.now());
            const data = await movieResponse.json();

            // Load staff picks (supports both new and legacy field names)
            this.staffPicks = data.staff_picks || data.featured || [];

            // Load YouTube trailers playlist URL
            this.latestPlaylistUrl = data.latest_playlist_url || null;

            if (data.movies && data.movies.length > 0) {
                this.allMovies = data.movies.filter(m => {
                    if (m.hidden) return false;
                    if (m._enrichment_status === 'reverted') return false;
                    return !!m.digital_date;
                });

                this.setupFilterEventListeners();
                this.setupSearchEventListeners();
                this.setupCardFlipHandler();
                this.setupLightboxKeyboardHandler();
                this.setupGridKeyboardHandler();
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
        // Click anywhere on a movie card to open lightbox
        document.getElementById('wall').addEventListener('click', (e) => {
            if (e.target.tagName === 'A') return;
            if (e.target.closest('.movie-info')) return;
            if (e.target.closest('[data-trailer-reel]')) return;

            // Find the movie card — try multiple selectors for robustness
            const container = e.target.closest('.movie-container');
            if (!container) return;

            const expandBtn = container.querySelector('.expand-btn[data-movie-id]');
            if (expandBtn) {
                this.openLightbox(expandBtn.dataset.movieId);
            }
        });
    },

    setupFilterEventListeners() {
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const filter = e.target.dataset.filter;

                // Toggle this filter on/off (multi-select)
                if (this.activeFilters.has(filter)) {
                    this.activeFilters.delete(filter);
                    e.target.classList.remove('active');
                } else {
                    this.activeFilters.add(filter);
                    e.target.classList.add('active');
                }

                this.gridClearSelection();
                this.displayedCount = this.loadIncrement; // Reset when changing filters
                this.applyFilter();
                this.updateFilterDescription();
                this.renderWallWithMore();
            });
        });
    },

    // Show/hide filter description based on active filters
    updateFilterDescription() {
        const el = document.getElementById('filter-description');
        if (!el) return;

        const filters = Array.from(this.activeFilters);
        if (filters.length === 1 && this.FILTER_DESCRIPTIONS[filters[0]]) {
            const desc = this.FILTER_DESCRIPTIONS[filters[0]];
            document.getElementById('filter-description-title').textContent = desc.title;
            document.getElementById('filter-description-text').textContent = desc.text;
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
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
                this.gridClearSelection();
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
            // Pre-orders only appear when the pre-orders filter is active OR search is active
            if (movie._is_preorder && !filters.has('pre-orders') && !query) return false;

            // If no filters selected, show all (except hidden)
            if (filters.size === 0) {
                // No category filter - show all
            } else {
                // Must pass ANY selected filter (OR logic - cumulative)
                let matchesAny = false;
                for (const filter of filters) {
                    switch (filter) {
                        case 'studio':
                            if (movie.categories?.is_studio || movie.categories?.tier === 'studio') matchesAny = true;
                            break;
                        case 'indie':
                            if (movie.categories?.is_indie || movie.categories?.tier === 'indie') matchesAny = true;
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
                        case 'restorations':
                            if (movie.categories?.is_restoration) matchesAny = true;
                            break;
                        case 'documentary':
                            if (movie.categories?.is_documentary) matchesAny = true;
                            break;
                        case 'virtual-screenings':
                            if (movie.categories?.is_virtual_screening) matchesAny = true;
                            break;
                        case 'pre-orders':
                            if (movie._is_preorder) matchesAny = true;
                            break;
                        case 'exploitation':
                            if (movie.categories?.is_exploitation) matchesAny = true;
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
        // Re-apply grid selection if the card is still in the DOM
        if (this.gridSelectedId) {
            const btn = document.querySelector(`#wall .expand-btn[data-movie-id="${CSS.escape(this.gridSelectedId)}"]`);
            if (btn) btn.closest('.movie-container').classList.add('grid-selected');
        }
    },


    renderWall(movies) {
        const wall = document.getElementById('wall');

        // Separate pre-orders from regular movies
        const regularMovies = movies.filter(m => !m._is_preorder);
        const preorderMovies = movies.filter(m => m._is_preorder);

        // Sort regular movies by date descending, then staff picks first within each date
        regularMovies.sort((a, b) => {
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

        // Sort pre-orders by date ascending (nearest release first)
        preorderMovies.sort((a, b) => (a.digital_date || '').localeCompare(b.digital_date || ''));

        // Combine: regular movies first, then pre-orders at the bottom
        const orderedMovies = [...regularMovies, ...preorderMovies];

        let html = '';
        let lastDate = '';
        let isFirstDate = true;
        let preorderSectionStarted = false;

        orderedMovies.forEach(movie => {
            const date = (movie.digital_date || '').substring(0, 10);

            // Pre-order movies: show section header once, no date dividers
            if (movie._is_preorder) {
                if (!preorderSectionStarted) {
                    preorderSectionStarted = true;
                    html += `<div class="date-divider-card">
                        <div class="date-content date-content-preorder">
                            <div class="date-day">PRE-</div>
                            <div class="date-number">ORDER</div>
                        </div>
                    </div>`;
                }
            // Regular movies: date divider when date changes
            } else if (date !== lastDate) {
                // Add NEW TRAILERS button before the first date marker
                if (isFirstDate) {
                    const now = new Date();
                    const weekStart = new Date(now);
                    weekStart.setDate(now.getDate() - now.getDay());
                    const weekEnd = new Date(weekStart);
                    weekEnd.setDate(weekStart.getDate() + 6);
                    const dateRange = weekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' - ' + weekEnd.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    html += `<div class="trailers-card" data-trailer-reel>
                        <div class="trailers-content">
                            <div class="trailers-text">NEW</div>
                            <div class="trailers-text">TRAILERS</div>
                            <div class="trailers-date">${dateRange}</div>
                            <div class="trailers-icon">▶</div>
                        </div>
                    </div>`;
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
            
            const isStaffPick = movie.categories?.is_staff_pick || this.staffPicks.includes(movie.id);
            const staffPickClass = isStaffPick ? ' staff-pick-movie' : '';

            const formatShortDate = NRW.formatShortDate;

            // Streaming service pill badge for card front
            const getStreamingBadge = (movie) => {
                const watchLinks = movie.watch_links || {};
                const providers = movie.providers || {};

                // Pre-order: pipeline sets _is_preorder flag during enrichment
                if (movie._is_preorder) {
                    const poDate = movie.digital_date
                        ? NRW.formatShortDate(movie.digital_date)
                        : 'TBD';
                    return '<div class="streaming-badge badge-preorder"><span class="po-label">PRE-ORDER</span><span class="po-date">' + poDate + '</span></div>';
                }

                // Get streaming service name
                let service = NRW.getStreaming(watchLinks)?.service;
                if (!service && providers.streaming?.length > 0) {
                    const screeningNames = NRWConfig.VOD_SERVICE_MAP.screening.matches;
                    const realStreamers = providers.streaming.filter(p =>
                        !p.includes('with Ads') && !screeningNames.some(s => p.toLowerCase().includes(s))
                    );
                    service = realStreamers[0] || null;
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
            const isScreening = movie.categories?.is_virtual_screening;
            const screeningClass = isScreening ? ' screening-movie' : '';
            const screeningTopBanner = isScreening
                ? '<div class="screening-top-banner">VIRTUAL SCREENING</div>' : '';
            const festivalName = movie.virtual_screening_info?.screening_name;
            const badgeBar = isScreening
                ? `<div class="badge-bar gold">${festivalName || '\u2605 VIRTUAL SCREENING \u2605'}</div>`
                : isStaffPick
                ? '<div class="badge-bar red">\u2605 STAFF PICK \u2605</div>'
                : '';

            // Score badges for card front (bottom-left overlay)
            let cardScoreBadges = '';
            if (movie.rt_score && movie.links?.rt) {
                cardScoreBadges += `<a href="${movie.links.rt}" target="_blank" rel="noopener noreferrer" class="card-score-badge rt"><img src="assets/logos/rt.png" class="score-logo" alt="RT"> ${movie.rt_score}</a>`;
            }
            if (movie.metacritic_score && movie.metacritic_score !== "0" && movie.links?.metacritic) {
                cardScoreBadges += `<a href="${movie.links.metacritic}" target="_blank" rel="noopener noreferrer" class="card-score-badge mc"><img src="assets/logos/metacritic.png" class="score-logo" alt="MC"> ${movie.metacritic_score}</a>`;
            }
            if (movie.imdb_rating) {
                const imdbUrl = movie.links?.imdb;
                if (imdbUrl) {
                    cardScoreBadges += `<a href="${imdbUrl}" target="_blank" rel="noopener noreferrer" class="card-score-badge imdb"><img src="assets/logos/imdb.png" class="score-logo" alt="IMDb"> ${movie.imdb_rating}</a>`;
                } else {
                    cardScoreBadges += `<span class="card-score-badge imdb"><img src="assets/logos/imdb.png" class="score-logo" alt="IMDb"> ${movie.imdb_rating}</span>`;
                }
            }
            if (movie.links?.letterboxd) {
                const lbText = movie.letterboxd_score ? NRW.lbStars(movie.letterboxd_score) : '';
                cardScoreBadges += `<a href="${movie.links.letterboxd}" target="_blank" rel="noopener noreferrer" class="card-score-badge lb"><img src="assets/logos/services/letterboxd-dots.svg" class="score-logo" alt="LB">${lbText ? ' ' + lbText : ''}</a>`;
            }
            const cardScoreHtml = cardScoreBadges ? `<div class="card-score-overlay">${cardScoreBadges}</div>` : '';

            html += `
            <div class="movie-container${staffPickClass}${screeningClass}">
                <div class="movie-card">
                    <div class="card-inner">
                        <div class="card-front">
                            ${screeningTopBanner}
                            ${streamingBadge}
                            ${restorationBadge}
                            <div class="poster-fallback"><span class="poster-fallback-title">${title}</span></div>
                            <img src="${movie.poster || ''}"
                                 onerror="this.style.display='none';"
                                 ${movie.poster ? '' : 'style="display:none"'}>
                            ${cardScoreHtml}
                            <button class="expand-btn" data-movie-id="${movie.id}" aria-label="View fullscreen">&#x26F6;</button>
                        </div>
                    </div>
                </div>
                <div class="movie-info">
                    <div class="movie-title">${movie.display_title || movie.title}</div>
                    <span class="director">${movie.crew?.director || 'Unknown Director'}</span> • <span class="country">${NRW.abbreviateCountry(movie.country) || 'Unknown Country'}</span>
                </div>
                ${badgeBar}
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

    // Trailer architecture: trailers are downloaded via yt-dlp and self-hosted as MP4s on Backblaze B2.
    // trailer_hosted (B2 MP4) is always preferred; trailer (YouTube URL) is fallback only.
    // See docs/features/TRAILER_HOSTING.md
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
        const movies = this.isTrailerReel ? this.trailerReelMovies : this.lightboxMovies;
        const count = movies.length;
        if (count === 0) return -1;
        let idx = fromIndex;
        for (let i = 0; i < count - 1; i++) {
            idx = (idx + direction + count) % count;
            const movie = movies[idx];
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
            video.addEventListener('error', () => {
                loading.style.display = 'none'; error.style.display = '';
                if (this.isTrailerReel) setTimeout(() => this.trailerNav(1), 1500);
            }, { once: true });
            video.addEventListener('ended', () => { if (this.isTrailerReel) this.trailerNav(1); }, { once: true });
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
        const movies = this.isTrailerReel ? this.trailerReelMovies : this.lightboxMovies;
        const movie = movies[nextIdx];
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;

        const titleEl = document.getElementById('trailer-movie-title');
        if (titleEl) titleEl.textContent = movie.display_title || movie.title;

        this.updateTrailerNavVisibility();
        this.loadTrailerVideo(trailerUrl);
        this.updateReelCounter();
    },

    // Show/hide trailer nav arrows based on whether neighbors have trailers
    updateTrailerNavVisibility() {
        const prevBtn = document.getElementById('trailer-nav-prev');
        const nextBtn = document.getElementById('trailer-nav-next');
        if (!prevBtn || !nextBtn) return;

        const movies = this.isTrailerReel ? this.trailerReelMovies : this.lightboxMovies;
        if (this.trailerLightboxIndex < 0 || movies.length === 0) {
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
                        <span class="trailer-reel-counter" id="trailer-reel-counter" style="display:none;"></span>
                        <button class="trailer-close-btn" aria-label="Close trailer">&times;</button>
                    </div>
                    <div class="trailer-nav-wrapper">
                        <button class="trailer-nav prev" id="trailer-nav-prev" aria-label="Previous trailer">&larr;</button>
                        <div class="trailer-video-container" id="trailer-video-container"></div>
                        <button class="trailer-nav next" id="trailer-nav-next" aria-label="Next trailer">&rarr;</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            // Close on backdrop click
            modal.querySelector('.trailer-modal-backdrop').addEventListener('click', () => this.closeTrailer());
            modal.querySelector('.trailer-close-btn').addEventListener('click', () => this.closeTrailer());

            // Nav arrow clicks
            modal.querySelector('#trailer-nav-prev').addEventListener('click', () => this.trailerNav(-1));
            modal.querySelector('#trailer-nav-next').addEventListener('click', () => this.trailerNav(1));

            // Escape handled by setupLightboxKeyboardHandler (capture phase)
        }

        // Determine which movie this trailer belongs to
        const movies = this.isTrailerReel ? this.trailerReelMovies : this.lightboxMovies;
        this.trailerLightboxIndex = movies.findIndex(m => {
            const mUrl = m.links?.trailer_hosted || m.links?.trailer;
            return mUrl === url;
        });

        // Set movie title
        const titleEl = document.getElementById('trailer-movie-title');
        if (titleEl && this.trailerLightboxIndex >= 0) {
            titleEl.textContent = movies[this.trailerLightboxIndex].title;
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

            // Sync lightbox to the movie whose trailer was playing (only when not in reel mode)
            if (!this.isTrailerReel && this.trailerLightboxIndex >= 0) {
                this.lightboxIndex = this.trailerLightboxIndex;
                this.updateLightbox();
            }
            this.trailerLightboxIndex = -1;
            this.isTrailerReel = false;
            this.trailerReelMovies = [];

            // Only restore scrolling if lightbox isn't still open
            const lightbox = document.getElementById('poster-lightbox');
            if (!lightbox || !lightbox.classList.contains('active')) {
                document.body.style.overflow = '';
            }
        }
    },

    // Open trailer reel — plays through hosted trailers from the last 7 days
    openTrailerReel() {
        const cutoff = new Date();
        cutoff.setDate(cutoff.getDate() - 7);

        this.trailerReelMovies = this.allMovies
            .filter(m => {
                if (!m.digital_date) return false;
                if (new Date(m.digital_date) < cutoff) return false;
                return m.links?.trailer_hosted;
            })
            .sort((a, b) => new Date(b.digital_date) - new Date(a.digital_date));

        if (this.trailerReelMovies.length === 0) return;

        this.isTrailerReel = true;
        this.trailerLightboxIndex = 0;

        const movie = this.trailerReelMovies[0];
        this.showTrailer(movie.links.trailer_hosted);
        this.updateReelCounter();
    },

    // Update reel position counter (e.g. "3 of 12") — only visible in reel mode
    updateReelCounter() {
        const counter = document.getElementById('trailer-reel-counter');
        if (!counter) return;
        if (this.isTrailerReel && this.trailerLightboxIndex >= 0) {
            counter.textContent = `${this.trailerLightboxIndex + 1} of ${this.trailerReelMovies.length}`;
            counter.style.display = '';
        } else {
            counter.textContent = '';
            counter.style.display = 'none';
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
            .slice(0, this.displayedCount);

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
        // Scroll back to grid-selected card
        if (this.gridSelectedId) {
            const sel = document.querySelector('#wall .movie-container.grid-selected');
            if (sel) setTimeout(() => sel.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
        }
    },

    // Navigate in lightbox (movie-level)
    // updateLightbox() sets default focus to TRAILER
    lightboxNav(direction) {
        const count = this.lightboxMovies.length;
        this.lightboxIndex = (this.lightboxIndex + direction + count) % count;
        this.updateLightbox();
    },

    // Build 2D grid of focusable elements for lightbox keyboard navigation
    // Rows: [scores] [trailer] [streaming] [vod]
    _getLightboxGrid() {
        const grid = [];
        // Row: score badges (RT, IMDb, MC, Wiki)
        const scores = document.getElementById('lightbox-scores');
        const scoreBadges = scores ? Array.from(scores.querySelectorAll('.score-badge')) : [];
        if (scoreBadges.length > 0) grid.push(scoreBadges);
        // Row: TRAILER button (only if present)
        const btnContainer = document.getElementById('lightbox-buttons');
        const trailerBtn = btnContainer?.querySelector('.lb-trailer-btn');
        if (trailerBtn) grid.push([trailerBtn]);
        // Row: streaming buttons
        const streamRow = btnContainer?.querySelector('.lb-stream-row');
        if (streamRow) {
            const btns = Array.from(streamRow.querySelectorAll('a.stream-btn'));
            if (btns.length > 0) grid.push(btns);
        }
        // Row: VOD buttons
        const vodRow = btnContainer?.querySelector('.lb-vod-row');
        if (vodRow) {
            const btns = Array.from(vodRow.querySelectorAll('a.vod-btn'));
            if (btns.length > 0) grid.push(btns);
        }
        return grid;
    },

    // 2D arrow key nav in lightbox
    // TRAILER row: LEFT → prev movie, RIGHT → next movie
    // Other rows: LEFT/RIGHT cycle within row, UP/DOWN move between rows
    _lightboxGridNav(direction) {
        const grid = this._getLightboxGrid();
        if (grid.length === 0) {
            if (direction === 'left' || direction === 'right') {
                this.lightboxNav(direction === 'right' ? 1 : -1);
            }
            return;
        }
        // Clamp to valid range
        if (this.lbRow >= grid.length) this.lbRow = grid.length - 1;
        if (this.lbCol >= grid[this.lbRow].length) this.lbCol = grid[this.lbRow].length - 1;

        const isTrailerRow = grid[this.lbRow].some(el => el.classList.contains('lb-trailer-btn'));

        switch (direction) {
            case 'left':
                if (isTrailerRow) {
                    this.lightboxNav(-1);  // prev movie
                } else if (this.lbCol > 0) {
                    this.lbCol--;
                    this._updateLightboxGridFocus(grid);
                } else {
                    this.lightboxNav(-1);  // past first button → prev movie
                }
                break;
            case 'right':
                if (isTrailerRow) {
                    this.lightboxNav(1);  // next movie
                } else if (this.lbCol < grid[this.lbRow].length - 1) {
                    this.lbCol++;
                    this._updateLightboxGridFocus(grid);
                } else {
                    this.lightboxNav(1);  // past last button → next movie
                }
                break;
            case 'up':
                if (this.lbRow > 0) {
                    this.lbRow--;
                    this.lbCol = Math.min(this.lbCol, grid[this.lbRow].length - 1);
                    this._updateLightboxGridFocus(grid);
                }
                break;
            case 'down':
                if (this.lbRow < grid.length - 1) {
                    this.lbRow++;
                    this.lbCol = Math.min(this.lbCol, grid[this.lbRow].length - 1);
                    this._updateLightboxGridFocus(grid);
                }
                break;
        }
    },

    // Visually highlight the focused element in the grid
    _updateLightboxGridFocus(grid) {
        if (!grid) grid = this._getLightboxGrid();
        grid.forEach(row => row.forEach(el => el.classList.remove('lb-focused')));
        const el = grid[this.lbRow]?.[this.lbCol];
        if (el) {
            el.classList.add('lb-focused');
            el.scrollIntoView({ block: 'nearest' });
        }
    },

    // Enter/Space activates the focused element
    _lightboxActivateFocused(e) {
        const grid = this._getLightboxGrid();
        const el = grid[this.lbRow]?.[this.lbCol];
        if (!el) return;
        e.preventDefault();
        // Trailer button
        if (el.dataset.trailer) {
            this.showTrailer(el.dataset.trailer);
            return;
        }
        // Links (scores, watch buttons, VOD cards)
        const link = el.tagName === 'A' ? el : el.querySelector('a');
        if (link) link.click();
    },

    // --- Lightbox sub-renderers (extracted from updateLightbox) ---

    _updateLightboxPoster(movie) {
        const posterWrap = document.querySelector('.lightbox-poster-wrap');
        document.getElementById('lightbox-poster').src = movie.poster || '';
        document.getElementById('lightbox-poster').style.display = movie.poster ? '' : 'none';
        document.getElementById('lightbox-poster-fallback').style.display = movie.poster ? 'none' : 'flex';
        document.getElementById('lightbox-poster-fallback-title').textContent = movie.display_title || movie.title;
        document.getElementById('lightbox-score-overlay').innerHTML = '';

        // Clean poster — no trailer overlay
        const oldOverlay = posterWrap.querySelector('.lightbox-trailer-overlay');
        if (oldOverlay) oldOverlay.remove();
        posterWrap.classList.remove('has-trailer');
    },

    _updateLightboxHeader(movie) {
        document.getElementById('lightbox-title').textContent = movie.display_title || movie.title;

        // Release date (with screening date range for virtual screenings)
        const dateEl = document.getElementById('lightbox-date');
        if (dateEl) {
            if (movie.digital_date) {
                const [y, m, d] = movie.digital_date.split('-');
                const dt = new Date(y, m - 1, d);
                let dateText = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                if (movie.categories?.is_virtual_screening && movie.virtual_screening_info?.available_end) {
                    const [ey, em, ed] = movie.virtual_screening_info.available_end.split('-');
                    if (em === m) {
                        dateText += '\u2013' + parseInt(ed, 10);
                    } else {
                        const endDt = new Date(ey, em - 1, ed);
                        dateText += '\u2013' + endDt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    }
                }
                dateEl.textContent = dateText;
            } else {
                dateEl.textContent = '';
            }
        }

        // Staff Pick badge
        const staffPickBadge = document.getElementById('lightbox-staff-pick');
        if (staffPickBadge) {
            staffPickBadge.style.display = movie.categories?.is_staff_pick ? 'inline-block' : 'none';
        }

        // Screening name banner
        const screeningNameEl = document.getElementById('lightbox-screening-name');
        if (screeningNameEl) {
            if (movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name) {
                screeningNameEl.textContent = movie.virtual_screening_info.screening_name;
                screeningNameEl.style.display = 'block';
            } else {
                screeningNameEl.style.display = 'none';
            }
        }
    },

    _updateLightboxSynopsis(movie) {
        // Meta block — 3 lines
        const metaEl = document.getElementById('lightbox-meta');
        metaEl.textContent = '';

        // Line 1: Director
        if (movie.crew?.director) {
            const dirLabel = document.createElement('span');
            dirLabel.className = 'lightbox-crew-label';
            dirLabel.textContent = 'Director: ';
            const dirName = document.createElement('span');
            dirName.className = 'lightbox-crew-name';
            dirName.textContent = movie.crew.director;
            metaEl.appendChild(dirLabel);
            metaEl.appendChild(dirName);
        }

        // Line 2: Cast
        if (movie.crew?.cast?.length) {
            if (metaEl.childNodes.length) metaEl.appendChild(document.createElement('br'));
            const castLabel = document.createElement('span');
            castLabel.className = 'lightbox-crew-label';
            castLabel.textContent = 'Cast: ';
            const castName = document.createElement('span');
            castName.className = 'lightbox-crew-name';
            castName.textContent = movie.crew.cast.slice(0, 3).join(', ');
            metaEl.appendChild(castLabel);
            metaEl.appendChild(castName);
        }

        // Line 3: Country • Year • Runtime • Studio
        const detailParts = [];
        if (movie.country) detailParts.push(movie.country);
        if (movie.year) detailParts.push(movie.year);
        if (movie.runtime) detailParts.push(`${movie.runtime} min`);
        if (movie.studio) detailParts.push(movie.studio);
        if (detailParts.length) {
            if (metaEl.childNodes.length) metaEl.appendChild(document.createElement('br'));
            metaEl.appendChild(document.createTextNode(detailParts.join(' \u2022 ')));
        }

        // Synopsis text (renders **bold**/*italic* markdown)
        const synopsisEl = document.getElementById('lightbox-synopsis');
        synopsisEl.innerHTML = this.renderMarkdown(movie.synopsis || 'Synopsis coming soon.');

        // Screening callout appended to synopsis
        if (movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name) {
            const festName = movie.virtual_screening_info.screening_name;
            const endDate = movie.virtual_screening_info?.available_end;
            const callout = document.createElement('span');
            callout.className = 'screening-callout';
            callout.textContent = endDate
                ? ` Virtual screening available as part of the ${festName}. Ends ${NRW.formatShortDate(endDate)}.`
                : ` Virtual screening available as part of the ${festName}.`;
            synopsisEl.appendChild(callout);
        }
    },

    _updateLightboxScores(movie) {
        const container = document.getElementById('lightbox-scores');
        container.innerHTML = '';

        const makeBadge = (url, cls, text, logoSrc) => {
            const el = url ? document.createElement('a') : document.createElement('span');
            if (url) {
                el.setAttribute('href', url);
                el.setAttribute('target', '_blank');
                el.setAttribute('rel', 'noopener noreferrer');
            }
            el.className = `score-badge ${cls}`;
            if (logoSrc) {
                const img = document.createElement('img');
                img.src = logoSrc;
                img.className = 'score-logo';
                img.alt = '';
                el.appendChild(img);
            }
            el.appendChild(document.createTextNode(text));
            return el;
        };

        if (movie.rt_score && movie.links?.rt) {
            container.appendChild(makeBadge(movie.links.rt, 'rt', movie.rt_score, 'assets/logos/rt.png'));
        }
        if (movie.imdb_rating) {
            container.appendChild(makeBadge(movie.links?.imdb, 'imdb', movie.imdb_rating, 'assets/logos/imdb.png'));
        }
        if (movie.metacritic_score && movie.metacritic_score !== "0" && movie.links?.metacritic) {
            container.appendChild(makeBadge(movie.links.metacritic, 'mc', movie.metacritic_score, 'assets/logos/metacritic.png'));
        }
        if (movie.links?.letterboxd) {
            const lbText = movie.letterboxd_score ? NRW.lbStars(movie.letterboxd_score) : 'LB';
            container.appendChild(makeBadge(movie.links.letterboxd, 'lb', lbText, 'assets/logos/services/letterboxd-dots.svg'));
        }
        if (movie.links?.wikipedia) {
            container.appendChild(makeBadge(movie.links.wikipedia, 'wiki', 'Wiki'));
        }
    },

    _updateLightboxPullQuotes(movie) {
        const pqContainer = document.getElementById('lightbox-pull-quotes');
        pqContainer.innerHTML = '';
        if (movie.pull_quotes && movie.pull_quotes.length > 0) {
            for (const q of movie.pull_quotes) {
                const card = document.createElement('div');
                card.className = 'pq-card';

                const quote = document.createElement('q');
                quote.className = 'pq-text';
                quote.textContent = q.text;

                if (q.review_url) {
                    const link = document.createElement('a');
                    link.href = q.review_url;
                    link.target = '_blank';
                    link.rel = 'noopener';
                    link.className = 'pq-link';
                    link.appendChild(quote);
                    card.appendChild(link);
                } else {
                    card.appendChild(quote);
                }

                const attribution = [q.critic, q.outlet].filter(Boolean).join(', ');
                if (attribution) {
                    const cite = document.createElement('cite');
                    cite.className = 'pq-cite';
                    cite.textContent = attribution;
                    card.appendChild(cite);
                }
                pqContainer.appendChild(card);
            }
            pqContainer.style.display = '';
        } else {
            pqContainer.style.display = 'none';
        }
    },

    _buildLightboxButtons(movie) {
        const container = document.getElementById('lightbox-buttons');
        container.innerHTML = '';
        const watchLinks = movie.watch_links || {};
        const providers = movie.providers || {};

        // === ROW 1: < TRAILER > ===
        const navRow = document.createElement('div');
        navRow.className = 'lb-nav-row';

        // < button
        const prevBtn = document.createElement('button');
        prevBtn.className = 'lb-nav-btn lb-nav-prev';
        prevBtn.textContent = '\u2039';
        prevBtn.setAttribute('aria-label', 'Previous movie');
        navRow.appendChild(prevBtn);

        // TRAILER button (or disabled placeholder when no trailer)
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        const trailerBtn = document.createElement('button');
        trailerBtn.className = 'lb-trailer-btn';
        if (trailerUrl) {
            trailerBtn.dataset.trailer = trailerUrl;
            trailerBtn.textContent = 'TRAILER';
        } else {
            trailerBtn.textContent = 'NO TRAILER';
            trailerBtn.disabled = true;
            trailerBtn.style.opacity = '0.35';
            trailerBtn.style.cursor = 'default';
        }
        navRow.appendChild(trailerBtn);

        // > button
        const nextBtn = document.createElement('button');
        nextBtn.className = 'lb-nav-btn lb-nav-next';
        nextBtn.textContent = '\u203A';
        nextBtn.setAttribute('aria-label', 'Next movie');
        navRow.appendChild(nextBtn);

        container.appendChild(navRow);

        // === STREAM ROW (own row, before VOD) ===
        const lbStreamData = this.getStreaming(watchLinks);
        let streamSvc = lbStreamData?.service;
        let streamLink = lbStreamData?.link;
        if (!streamSvc && providers.streaming?.length) {
            const screeningNames = NRWConfig.VOD_SERVICE_MAP.screening.matches;
            const realStreamers = providers.streaming.filter(p =>
                !p.includes('with Ads') && !screeningNames.some(s => p.toLowerCase().includes(s))
            );
            streamSvc = realStreamers[0] || null;
        }
        if (streamSvc && streamLink) {
            const resolved = this.resolveService(streamSvc);
            const cls = resolved?.class || '';
            const logo = resolved?.wideLogo || null;
            const streamRowEl = document.createElement('div');
            streamRowEl.className = 'lb-stream-row';
            const btn = document.createElement('a');
            btn.className = `stream-btn ${cls}`;
            btn.setAttribute('href', streamLink);
            btn.setAttribute('target', '_blank');
            btn.setAttribute('rel', 'noopener noreferrer');
            if (logo) {
                const img = document.createElement('img');
                img.src = `assets/logos/${logo}`;
                img.alt = resolved?.btnName || streamSvc;
                btn.appendChild(img);
            } else {
                btn.textContent = resolved?.name || streamSvc.toUpperCase();
            }
            streamRowEl.appendChild(btn);
            container.appendChild(streamRowEl);
        }

        // === VOD ROW (own row, after streaming) ===
        const lbVodEntries = Array.isArray(watchLinks.vod) ? watchLinks.vod
            : (watchLinks.vod?.service ? [watchLinks.vod] : []);
        let resolvedVod = [];
        lbVodEntries.forEach(vod => {
            const vodLink = vod.link || vod.url;
            if (vod.service && vodLink) {
                const vodType = this.resolveVODService(vod.service, vodLink);
                if (vodType) resolvedVod.push({ vodType, vodLink, rentPrice: vod.rent_price || null, buyPrice: vod.buy_price || null });
            }
        });
        const hasNonFallback = resolvedVod.some(v => !v.vodType.fallback);
        if (hasNonFallback) resolvedVod = resolvedVod.filter(v => !v.vodType.fallback);

        const vodRowEl = document.createElement('div');
        vodRowEl.className = 'lb-vod-row';
        let hasVod = false;

        resolvedVod.forEach(({ vodType, vodLink, rentPrice, buyPrice }) => {
            const btn = document.createElement('a');
            btn.setAttribute('href', vodLink);
            btn.setAttribute('target', '_blank');
            btn.setAttribute('rel', 'noopener noreferrer');
            btn.className = `vod-btn ${vodType.key}`;

            if (vodType.key === 'screening') {
                btn.className = 'vod-btn screening';
                btn.innerHTML = '<div class="price-half screening-full">Buy Ticket</div>';
            } else {
                const logoHalf = document.createElement('div');
                logoHalf.className = 'logo-half';
                if (vodType.wideLogo) {
                    const img = document.createElement('img');
                    img.src = `assets/logos/${vodType.wideLogo}`;
                    img.alt = vodType.label;
                    logoHalf.appendChild(img);
                } else {
                    logoHalf.textContent = vodType.label;
                }
                btn.appendChild(logoHalf);

                const priceHalf = document.createElement('div');
                priceHalf.className = 'price-half';
                if (rentPrice && buyPrice) {
                    priceHalf.textContent = `Rent ${rentPrice} / Buy ${buyPrice}`;
                } else if (rentPrice) {
                    priceHalf.textContent = `Rent ${rentPrice}`;
                } else if (buyPrice) {
                    priceHalf.textContent = `Buy ${buyPrice}`;
                } else {
                    priceHalf.textContent = vodType.btnLabel || vodType.label;
                }
                btn.appendChild(priceHalf);
            }

            vodRowEl.appendChild(btn);
            hasVod = true;
        });

        // Pre-order links (when no other watch options)
        if (!hasVod) {
            const preOrderLinks = Array.isArray(movie.pre_order_links) ? movie.pre_order_links : [];
            preOrderLinks.forEach(pl => {
                const plLink = pl.link || pl.url;
                if (pl.service && plLink) {
                    const vodType = this.resolveVODService(pl.service, plLink);
                    if (!vodType) return;
                    const btn = document.createElement('a');
                    btn.setAttribute('href', plLink);
                    btn.setAttribute('target', '_blank');
                    btn.setAttribute('rel', 'noopener noreferrer');
                    btn.className = `vod-btn ${vodType.key}`;
                    const logoHalf = document.createElement('div');
                    logoHalf.className = 'logo-half';
                    if (vodType.wideLogo) {
                        const img = document.createElement('img');
                        img.src = `assets/logos/${vodType.wideLogo}`;
                        img.alt = vodType.label;
                        logoHalf.appendChild(img);
                    } else {
                        logoHalf.textContent = vodType.label;
                    }
                    btn.appendChild(logoHalf);
                    const priceHalf = document.createElement('div');
                    priceHalf.className = 'price-half';
                    priceHalf.textContent = 'Pre-Order';
                    btn.appendChild(priceHalf);
                    vodRowEl.appendChild(btn);
                    hasVod = true;
                }
            });
        }

        if (hasVod) container.appendChild(vodRowEl);

        // Pre-order availability date
        if (movie._is_preorder && hasVod) {
            const dateLabel = document.createElement('span');
            dateLabel.className = 'po-available-date';
            dateLabel.textContent = movie.digital_date
                ? `Available ${NRW.formatShortDate(movie.digital_date)}`
                : 'Available TBD';
            container.appendChild(dateLabel);
        }
    },

    // Update lightbox content — delegates to sub-renderers
    // Default focus: TRAILER button (or first available row/col)
    updateLightbox() {
        const movie = this.lightboxMovies[this.lightboxIndex];
        if (!movie) return;

        this._updateLightboxPoster(movie);
        this._updateLightboxHeader(movie);
        this._updateLightboxSynopsis(movie);
        this._updateLightboxScores(movie);
        this._updateLightboxPullQuotes(movie);
        this._buildLightboxButtons(movie);

        // Default focus on TRAILER row, fallback to first row
        const grid = this._getLightboxGrid();
        const trailerRowIdx = grid.findIndex(r => r.some(el => el.classList.contains('lb-trailer-btn')));
        this.lbRow = trailerRowIdx >= 0 ? trailerRowIdx : 0;
        this.lbCol = 0;
        this._updateLightboxGridFocus(grid);
    },

    // Setup lightbox + trailer keyboard navigation
    // Uses capture phase so it fires BEFORE native video controls can consume key events
    setupLightboxKeyboardHandler() {
        document.addEventListener('keydown', (e) => {
            // Handle trailer keyboard when trailer modal is active
            const trailerModal = document.getElementById('trailer-modal');
            if (trailerModal && trailerModal.classList.contains('active')) {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation();
                    this.closeTrailer();
                } else if (e.key === 'ArrowLeft') {
                    this.trailerNav(-1);
                } else if (e.key === 'ArrowRight') {
                    this.trailerNav(1);
                }
                return;
            }

            const lightbox = document.getElementById('poster-lightbox');
            if (!lightbox.classList.contains('active')) return;

            if (e.key === 'Escape') {
                this.closeLightbox();
            } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
                e.preventDefault();
                const dirMap = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
                this._lightboxGridNav(dirMap[e.key]);
            } else if (e.key === 'Enter' || e.key === ' ') {
                this._lightboxActivateFocused(e);
            }
        }, true);  // capture phase — fires before video/iframe controls
    },

    // ---- Grid keyboard navigation (arrow keys on the wall) ----

    // Build a spatial map of movie cards from their DOM positions
    buildGridMap() {
        const wall = document.getElementById('wall');
        const allCards = Array.from(wall.querySelectorAll('.movie-container'));
        if (allCards.length === 0) return { rows: [], cardToPos: new Map(), allCards: [] };

        const rects = allCards.map(el => ({ el, rect: el.getBoundingClientRect() }));

        // Group into rows by top position (10px tolerance)
        const rows = [];
        let currentRow = [rects[0]];
        let currentRowTop = rects[0].rect.top;

        for (let i = 1; i < rects.length; i++) {
            if (Math.abs(rects[i].rect.top - currentRowTop) < 10) {
                currentRow.push(rects[i]);
            } else {
                currentRow.sort((a, b) => a.rect.left - b.rect.left);
                rows.push(currentRow);
                currentRow = [rects[i]];
                currentRowTop = rects[i].rect.top;
            }
        }
        currentRow.sort((a, b) => a.rect.left - b.rect.left);
        rows.push(currentRow);

        const cardToPos = new Map();
        rows.forEach((row, rowIdx) => {
            row.forEach((item, colIdx) => {
                cardToPos.set(item.el, { row: rowIdx, col: colIdx, rect: item.rect });
            });
        });

        return { rows, cardToPos, allCards };
    },

    gridNavigate(direction) {
        const { rows, cardToPos, allCards } = this.buildGridMap();
        if (allCards.length === 0) return;

        // Find current selected element
        let currentEl = this.gridSelectedId
            ? document.querySelector(`#wall .expand-btn[data-movie-id="${CSS.escape(this.gridSelectedId)}"]`)?.closest('.movie-container')
            : null;

        // If nothing selected, select first visible card
        if (!currentEl || !cardToPos.has(currentEl)) {
            this.gridSelect(allCards[0]);
            this.gridAnchorX = null;
            return;
        }

        const pos = cardToPos.get(currentEl);
        let targetEl = null;

        if (direction === 'left') {
            const idx = allCards.indexOf(currentEl);
            if (idx > 0) targetEl = allCards[idx - 1];
        }
        else if (direction === 'right') {
            const idx = allCards.indexOf(currentEl);
            if (idx < allCards.length - 1) targetEl = allCards[idx + 1];
        }
        else if (direction === 'up' || direction === 'down') {
            // Set anchor on first vertical press, keep it for subsequent presses
            const currentCenterX = pos.rect.left + pos.rect.width / 2;
            if (this.gridAnchorX === null) {
                this.gridAnchorX = currentCenterX;
            }

            const rowDelta = direction === 'up' ? -1 : 1;
            let targetRow = pos.row + rowDelta;

            while (targetRow >= 0 && targetRow < rows.length) {
                const row = rows[targetRow];
                let bestDist = Infinity;
                let bestEl = null;
                for (const item of row) {
                    const itemCenterX = item.rect.left + item.rect.width / 2;
                    const dist = Math.abs(itemCenterX - this.gridAnchorX);
                    if (dist < bestDist) {
                        bestDist = dist;
                        bestEl = item.el;
                    }
                }
                if (bestEl) {
                    targetEl = bestEl;
                    break;
                }
                targetRow += rowDelta;
            }
        }

        if (targetEl) {
            // Left/right resets column memory; up/down preserves it
            if (direction === 'left' || direction === 'right') {
                this.gridAnchorX = null;
            }
            this.gridSelect(targetEl);
        }
    },

    gridSelect(containerEl) {
        const prev = document.querySelector('#wall .movie-container.grid-selected');
        if (prev) prev.classList.remove('grid-selected');

        if (containerEl) {
            containerEl.classList.add('grid-selected');
            const expandBtn = containerEl.querySelector('.expand-btn[data-movie-id]');
            this.gridSelectedId = expandBtn ? expandBtn.dataset.movieId : null;
            containerEl.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
        } else {
            this.gridSelectedId = null;
        }
    },

    gridClearSelection() {
        const prev = document.querySelector('#wall .movie-container.grid-selected');
        if (prev) prev.classList.remove('grid-selected');
        this.gridSelectedId = null;
        this.gridNavActive = false;
        this.gridAnchorX = null;
    },

    setupGridKeyboardHandler() {
        document.addEventListener('keydown', (e) => {
            // Don't handle if typing in search
            if (document.activeElement === document.getElementById('search-input')) return;

            // Don't handle if lightbox or trailer modal is open
            const lightbox = document.getElementById('poster-lightbox');
            if (lightbox && lightbox.classList.contains('active')) return;
            const trailerModal = document.getElementById('trailer-modal');
            if (trailerModal && trailerModal.classList.contains('active')) return;

            const arrowKeys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];

            if (arrowKeys.includes(e.key)) {
                e.preventDefault();
                this.gridNavActive = true;
                const dirMap = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
                this.gridNavigate(dirMap[e.key]);
            }
            else if (e.key === 'Enter' && this.gridNavActive && this.gridSelectedId) {
                e.preventDefault();
                this.openLightbox(this.gridSelectedId);
            }
            else if (e.key === 'Escape' && this.gridNavActive) {
                this.gridClearSelection();
            }
        });
    },

    // Delegated click handlers - one listener catches clicks on dynamically created elements
    setupDelegatedClickHandlers() {
        // Handle clicks on #wall (movie cards, expand buttons, trailer links, load more)
        document.getElementById('wall').addEventListener('click', (e) => {
            // Trailer reel card -> open trailer reel
            const reelCard = e.target.closest('[data-trailer-reel]');
            if (reelCard) {
                e.preventDefault();
                this.openTrailerReel();
                return;
            }

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

        // Handle clicks on document body for lightbox/trailer elements
        document.body.addEventListener('click', (e) => {
            // Lightbox nav buttons (< and >)
            if (e.target.closest('.lb-nav-prev')) { this.lightboxNav(-1); return; }
            if (e.target.closest('.lb-nav-next')) { this.lightboxNav(1); return; }
            // Lightbox TRAILER button
            const trailerBtn = e.target.closest('.lb-trailer-btn[data-trailer]');
            if (trailerBtn) { this.showTrailer(trailerBtn.dataset.trailer); return; }
            // Trailer modal backdrop or close button
            if (e.target.closest('.trailer-modal-backdrop') || e.target.closest('.trailer-close-btn')) {
                this.closeTrailer();
            }
        });
    }
};

// Start on page load
document.addEventListener('DOMContentLoaded', () => NRW.init());