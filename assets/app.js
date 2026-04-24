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
        youtube:   { class: 'youtube',   name: 'YOUTUBE',      badgeName: 'YOUTUBE',   matches: ['youtube'] },
        paramount: { class: 'paramount', name: 'PARAMOUNT+',   badgeName: 'P+',        matches: ['paramount'] },
        kanopy:    { class: 'kanopy',    name: 'KANOPY',       badgeName: 'KANOPY',    matches: ['kanopy'] },
        hoopla:    { class: 'hoopla',    name: 'HOOPLA',       badgeName: 'HOOPLA',    matches: ['hoopla'] },
        roku:      { class: 'roku',      name: 'ROKU CH.',     badgeName: 'ROKU',      matches: ['roku'] },
        pluto:     { class: 'pluto',     name: 'PLUTO TV',     badgeName: 'PLUTO',     matches: ['pluto'] },
        crackle:   { class: 'crackle',   name: 'CRACKLE',      badgeName: 'CRACKLE',   matches: ['crackle'] },
        fawesome:  { class: 'fawesome',  name: 'FAWESOME',     badgeName: 'FAWESOME',  matches: ['fawesome'] },
    },

    // Filter descriptions — shown when a single filter is active
    // User will rewrite all of these; placeholder text for now
    FILTER_DESCRIPTIONS: {
        'big-time': {
            title: 'Big Time Stuff',
            text: 'The wide releases, the studio fare, the main-streamers. Not saying they\'re good, not saying they\'re bad, but these are the movies that have either entered or tried to enter the mainstream conversation. They have budgets, recognizable actors, and large-scale billboard campaigns.'
        },
        'indie': {
            title: 'Indie',
            text: 'The smaller films, the independents, the ones without a billboard campaign. These movies flew under the radar theatrically but are worth knowing about now that they\'re available to stream at home.'
        },
        'staff-picks': {
            title: 'Staff Picks',
            text: 'The ones we\'re vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations.'
        },
        'foreign': {
            title: 'Foreign',
            text: 'Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces. The only thing they have in common is subtitles and the fact that they\'re streaming now.'
        },
        'series': {
            title: 'Limited Series',
            text: 'Not movies — limited series. The kind you can finish in a weekend. Prestige mini-series and limited runs that landed on streaming and deserve the same attention as a good film.'
        },
        'restorations': {
            title: 'Restorations & Reissues',
            text: 'Classic and catalog titles with new digital life. These are films that have been restored, remastered, or newly reissued on streaming platforms. Old movies, fresh transfers.'
        },
        'documentary': {
            title: 'Documentary',
            text: 'Non-fiction filmmaking. Documentaries covering real stories, real people, and real events — now available to stream at home.'
        },
        'virtual-screenings': {
            title: 'Virtual Screenings',
            text: 'Currently playing at film festivals. These aren\'t streaming yet — they\'re in theaters, at festivals, or doing the circuit. If you\'re near a screening, this is your heads-up.'
        }
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
    trailerReelMovies: [],     // Movies in the trailer reel (last 7 days with hosted trailers)
    isTrailerReel: false,      // true when playing the trailer reel (vs individual trailer from lightbox)

    // Format screening end date: "2026-03-30" → "Mar 30"
    formatScreeningDate(dateStr) {
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
                            if (movie.categories?.is_big_time || movie.categories?.tier === 'big_time') matchesAny = true;
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

            // Build platform-based watch buttons (SVOD, Amazon, Apple, YouTube, Plex)
            const buildPlatformButtons = (movie) => {
                const watchLinks = movie.watch_links || {};
                const providers = movie.providers || {};
                let buttonsHtml = '';

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
                        } else if (svc.includes('youtube')) {
                            buttonsHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-youtube" aria-label="Rent/Buy on YouTube">YOUTUBE</a>`;
                        } else if (svc.includes('eventive') || vodLink.includes('eventive.org') || vodLink.includes('festivalplayer') || vodLink.includes('shift72.com')) {
                            buttonsHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-screening" aria-label="Buy Ticket">BUY TICKET</a>`;
                        }
                        // VOD whitelist: only Amazon, Apple, YouTube, and festival tickets
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

            if (movie.imdb_rating) {
                const imdbUrl = movie.links?.imdb;
                if (imdbUrl) {
                    infoLinks.push(`<a href="${imdbUrl}" target="_blank" rel="noopener noreferrer" class="info-btn">IMDb ${movie.imdb_rating}</a>`);
                } else {
                    infoLinks.push(`<span class="info-btn info-btn-neutral">IMDb ${movie.imdb_rating}</span>`);
                }
            }

            if (movie.links?.wikipedia) {
                infoLinks.push(`<a href="${movie.links.wikipedia}" target="_blank" rel="noopener noreferrer" class="info-btn">Wiki</a>`);
            }

            const isStaffPick = movie.categories?.is_staff_pick || this.staffPicks.includes(movie.id);
            const staffPickClass = isStaffPick ? ' staff-pick-movie' : '';

            const formatScreeningDate = NRW.formatScreeningDate;

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
            const isScreening = movie.categories?.is_virtual_screening;
            const screeningClass = isScreening ? ' screening-movie' : '';
            const badgeBar = isScreening
                ? '<div class="badge-bar gold">\u2605 VIRTUAL SCREENING \u2605</div>'
                : isStaffPick
                ? '<div class="badge-bar red">\u2605 STAFF PICK \u2605</div>'
                : '';

            // Score badges for card front (bottom-left overlay)
            let cardScoreBadges = '';
            if (movie.rt_score && movie.links?.rt) {
                cardScoreBadges += `<a href="${movie.links.rt}" target="_blank" rel="noopener noreferrer" class="card-score-badge rt">RT ${movie.rt_score}</a>`;
            }
            if (movie.imdb_rating) {
                const imdbUrl = movie.links?.imdb;
                if (imdbUrl) {
                    cardScoreBadges += `<a href="${imdbUrl}" target="_blank" rel="noopener noreferrer" class="card-score-badge imdb">${movie.imdb_rating}</a>`;
                } else {
                    cardScoreBadges += `<span class="card-score-badge imdb">${movie.imdb_rating}</span>`;
                }
            }
            const cardScoreHtml = cardScoreBadges ? `<div class="card-score-overlay">${cardScoreBadges}</div>` : '';

            html += `
            <div class="movie-container${staffPickClass}${screeningClass}">
                <div class="movie-card">
                    <div class="card-inner">
                        <div class="card-front">
                            ${streamingBadge}
                            ${restorationBadge}
                            <div class="poster-fallback"><span class="poster-fallback-title">${title}</span></div>
                            <img src="${movie.poster || ''}"
                                 onerror="this.style.display='none';"
                                 ${movie.poster ? '' : 'style="display:none"'}>
                            ${cardScoreHtml}
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
        if (titleEl) titleEl.textContent = movie.title;

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

        // Update poster (with fallback for missing posters)
        document.getElementById('lightbox-poster').src = movie.poster || '';
        document.getElementById('lightbox-poster').style.display = movie.poster ? '' : 'none';
        document.getElementById('lightbox-poster-fallback').style.display = movie.poster ? 'none' : 'flex';
        document.getElementById('lightbox-poster-fallback-title').textContent = movie.title;

        // Update title
        document.getElementById('lightbox-title').textContent = movie.title;

        // Update release date
        const dateEl = document.getElementById('lightbox-date');
        if (dateEl) {
            if (movie.digital_date) {
                const [y, m, d] = movie.digital_date.split('-');
                const dt = new Date(y, m - 1, d);
                let dateText = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                // For virtual screenings, show date range (e.g. "Mar 22–26" or "Mar 22–Apr 10")
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

        // Update Staff Pick badge
        const staffPickBadge = document.getElementById('lightbox-staff-pick');
        if (staffPickBadge) {
            if (movie.categories?.is_staff_pick) {
                staffPickBadge.style.display = 'inline-block';
            } else {
                staffPickBadge.style.display = 'none';
            }
        }

        // Update screening name in lightbox
        const screeningNameEl = document.getElementById('lightbox-screening-name');
        if (screeningNameEl) {
            if (movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name) {
                screeningNameEl.textContent = movie.virtual_screening_info.screening_name;
                screeningNameEl.style.display = 'block';
            } else {
                screeningNameEl.style.display = 'none';
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
        const synopsisEl = document.getElementById('lightbox-synopsis');
        synopsisEl.textContent = movie.synopsis || 'Synopsis coming soon.';
        // Append screening availability callout for virtual screenings
        if (movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name) {
            const festName = movie.virtual_screening_info.screening_name;
            const endDate = movie.virtual_screening_info?.available_end;
            const callout = document.createElement('span');
            callout.className = 'screening-callout';
            if (endDate) {
                callout.textContent = ` Virtual screening available as part of the ${festName}. Ends ${NRW.formatScreeningDate(endDate)}.`;
            } else {
                callout.textContent = ` Virtual screening available as part of the ${festName}.`;
            }
            synopsisEl.appendChild(callout);
        }

        // Pull quotes (built via DOM to prevent XSS)
        const pqContainer = document.getElementById('lightbox-pull-quotes');
        pqContainer.innerHTML = '';
        if (movie.pull_quotes && movie.pull_quotes.length > 0) {
            for (const q of movie.pull_quotes) {
                const card = document.createElement('div');
                card.className = 'pq-card';

                const badge = document.createElement('span');
                badge.className = q.source === 'letterboxd' ? 'pq-source pq-lb' : 'pq-source pq-rt';
                badge.textContent = q.source === 'letterboxd' ? 'LB' : 'RT';
                card.appendChild(badge);

                const quote = document.createElement('q');
                quote.className = 'pq-text';
                quote.textContent = q.text;
                card.appendChild(quote);

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

        // Purchase (VOD) buttons — separate Amazon + Apple TV (side-by-side)
        const lbVodEntries = Array.isArray(watchLinks.vod) ? watchLinks.vod
            : (watchLinks.vod?.service ? [watchLinks.vod] : []);

        let vodHtml = '';
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
                } else if (svc.includes('youtube')) {
                    btnClass = 'youtube';
                    label = this.getPurchaseLabel(vod.service);
                } else if (svc.includes('eventive') || vodLink.includes('eventive.org') || vodLink.includes('festivalplayer') || vodLink.includes('shift72.com')) {
                    btnClass = 'screening';
                    label = 'BUY TICKET';
                } else {
                    return; // VOD whitelist: only Amazon, Apple, YouTube, and festival tickets
                }
                vodHtml += `<a href="${vodLink}" target="_blank" rel="noopener noreferrer" class="watch-btn-lb ${btnClass}">${label}</a>`;
            }
        });
        if (vodHtml) watchHtml += `<div class="vod-row">${vodHtml}</div>`;

        let buttonsHtml = '';
        if (watchHtml) buttonsHtml += `<div class="watch-stack">${watchHtml}</div>`;

        // === Score badges on poster overlay ===
        let scoreHtml = '';
        if (movie.links?.rt) {
            const score = movie.rt_score ? ` ${movie.rt_score}` : '';
            scoreHtml += `<a href="${movie.links.rt}" target="_blank" rel="noopener noreferrer" class="lightbox-score-badge rt">RT${score}</a>`;
        }
        if (movie.imdb_rating) {
            const imdbUrl = movie.links?.imdb;
            if (imdbUrl) {
                scoreHtml += `<a href="${imdbUrl}" target="_blank" rel="noopener noreferrer" class="lightbox-score-badge imdb">IMDb ${movie.imdb_rating}</a>`;
            } else {
                scoreHtml += `<span class="lightbox-score-badge imdb">IMDb ${movie.imdb_rating}</span>`;
            }
        }
        document.getElementById('lightbox-score-overlay').innerHTML = scoreHtml;

        // === Info row (horizontal: Trailer, Wiki) ===
        let infoHtml = '';
        const lbTrailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        if (lbTrailerUrl) {
            infoHtml += `<button class="info-btn-lb trailer" data-trailer="${lbTrailerUrl}">Trailer</button>`;
        }
        if (movie.links?.wikipedia) {
            infoHtml += `<a href="${movie.links.wikipedia}" target="_blank" rel="noopener noreferrer" class="info-btn-lb glass">Wiki</a>`;
        }
        if (infoHtml) buttonsHtml += `<div class="info-row">${infoHtml}</div>`;

        document.getElementById('lightbox-buttons').innerHTML = buttonsHtml;
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
            } else if (e.key === 'ArrowLeft') {
                this.lightboxNav(-1);
            } else if (e.key === 'ArrowRight') {
                this.lightboxNav(1);
            }
        }, true);  // capture phase — fires before video/iframe controls
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