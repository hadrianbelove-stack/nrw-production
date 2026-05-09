/**
 * NRW Mobile - Option F Flip Cards
 * Fetches data.json and renders movies as flip cards with infinite scroll
 */

// Touch/swipe thresholds
const SWIPE_MIN_DISTANCE = 40;       // Minimum px for a horizontal swipe
const SWIPE_DIRECTION_RATIO = 1.5;   // deltaX must exceed deltaY * this to count as horizontal
const TAP_MAX_DISTANCE = 15;         // Max px movement to still count as a tap (not a drag)
const SWIPE_DEBOUNCE_MS = 400;       // Cooldown after a swipe before another gesture fires
const TAP_DEBOUNCE_MS = 500;         // Cooldown after a tap-flip before click handler fires
const TRAILER_SWIPE_MIN = 50;        // Min px for trailer overlay swipe navigation

const NRWMobile = {
    allMovies: [],
    filteredMovies: [],
    staffPicks: [],
    activeFilters: new Set(),
    displayedCount: 0,
    loadIncrement: 15,
    isLoading: false,
    searchQuery: '',
    isTrailerReel: false,

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
            title: 'Staff Picks',
            text: 'The ones we\'re vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations.'
        },
        'foreign': {
            title: 'Foreign',
            text: 'Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces. The only thing they have in common is subtitles and the fact that they\'re streaming now.'
        },
        'series': {
            title: 'Limited Series',
            text: 'Not movies \u2014 limited series. The kind you can finish in a weekend. Prestige mini-series and limited runs that landed on streaming and deserve the same attention as a good film.'
        },
        'restorations': {
            title: 'Restorations & Reissues',
            text: 'Classic and catalog titles with new digital life. These are films that have been restored, remastered, or newly reissued on streaming platforms. Old movies, fresh transfers.'
        },
        'documentary': {
            title: 'Documentary',
            text: 'Non-fiction filmmaking. Documentaries covering real stories, real people, and real events \u2014 now available to stream at home.'
        },
        'virtual-screenings': {
            title: 'Virtual Screenings',
            text: 'Currently playing at film festivals. These aren\'t streaming yet \u2014 they\'re in theaters, at festivals, or doing the circuit. If you\'re near a screening, this is your heads-up.'
        },
        'pre-orders': {
            title: 'Pre-Orders',
            text: 'Coming soon. These movies have confirmed digital release dates and are available to pre-order now on storefronts like Apple TV and Amazon.'
        }
    },

    // Shared config — loaded from assets/shared-config.js
    SERVICE_MAP: NRWConfig.SERVICE_MAP,
    VOD_SERVICE_MAP: NRWConfig.VOD_SERVICE_MAP,
    resolveService: NRWConfig.resolveService,
    resolveVODService: NRWConfig.resolveVODService,
    abbreviateCountry: NRWConfig.abbreviateCountry,

    formatShortDate(dateStr) {
        const [y, m, d] = dateStr.split('-');
        const dt = new Date(y, m - 1, d);
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    },

    getScreeningRibbon(movie) {
        const info = movie.virtual_screening_info || {};
        const name = info.screening_name;
        return `<div class="screening-ribbon-top">`
            + `<div class="sr-label">VIRTUAL SCREENING</div>`
            + (name ? `<div class="sr-festival">${name}</div>` : '')
            + `</div>`;
    },


    async init() {
        try {
            // Fetch data from parent directory
            const response = await fetch('../data.json?t=' + Date.now());
            const data = await response.json();

            // Load staff picks
            this.staffPicks = data.staff_picks || data.featured || [];

            this.allMovies = (data.movies || []).filter(m => {
                if (m.hidden) return false;
                if (m._enrichment_status === 'reverted') return false;
                return !!m.digital_date;
            });

            // Sort by date descending, staff picks first within each date
            this.sortMovies();

            // Setup event listeners
            this.setupFilters();
            this.setupSearchEventListeners();
            this.setupInfiniteScroll();

            // Initial render
            this.applyFilter();
            this.render();

        } catch (err) {
            console.error('Failed to load movies:', err);
            document.getElementById('movie-feed').innerHTML = `
                <div class="error-state">
                    <h3>Failed to load movies</h3>
                    <p>${err.message}</p>
                </div>
            `;
        }
    },

    sortMovies() {
        this.allMovies.sort((a, b) => {
            // Pre-orders always sort to the end
            if (a._is_preorder && !b._is_preorder) return 1;
            if (!a._is_preorder && b._is_preorder) return -1;
            if (a._is_preorder && b._is_preorder) return (a.digital_date || '').localeCompare(b.digital_date || '');

            const dateA = new Date(a.digital_date);
            const dateB = new Date(b.digital_date);
            if (dateB.getTime() !== dateA.getTime()) {
                return dateB - dateA; // Newest first
            }
            // Same date: staff picks first
            const aStaffPick = a.categories?.is_staff_pick || this.staffPicks.includes(a.id);
            const bStaffPick = b.categories?.is_staff_pick || this.staffPicks.includes(b.id);
            if (aStaffPick && !bStaffPick) return -1;
            if (!aStaffPick && bStaffPick) return 1;
            return 0;
        });
    },

    setupFilters() {
        const filters = document.getElementById('filters');
        filters.addEventListener('click', (e) => {
            const pill = e.target.closest('.filter-pill');
            if (!pill) return;

            const filter = pill.dataset.filter;

            if (filter === 'all') {
                // "All" clears all other filters
                this.activeFilters.clear();
                filters.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
            } else {
                // Toggle this filter on/off (multi-select)
                if (this.activeFilters.has(filter)) {
                    this.activeFilters.delete(filter);
                    pill.classList.remove('active');
                } else {
                    this.activeFilters.add(filter);
                    pill.classList.add('active');
                }

                // Update "All" button state
                const allBtn = filters.querySelector('.filter-pill[data-filter="all"]');
                if (this.activeFilters.size > 0) {
                    allBtn.classList.remove('active');
                } else {
                    allBtn.classList.add('active');
                }
            }

            this.displayedCount = 0;
            this.applyFilter();
            this.updateFilterDescription();
            this.render();

            // Scroll to top
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    },

    setupSearchEventListeners() {
        const searchInput = document.getElementById('search-input');
        const clearBtn = document.getElementById('search-clear');
        if (!searchInput) return;

        let debounceTimer;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                this.searchQuery = e.target.value.trim().toLowerCase();
                this.displayedCount = 0;
                this.applyFilter();
                this.render();
                if (clearBtn) {
                    clearBtn.style.display = this.searchQuery ? 'block' : 'none';
                }
            }, 200);
        });

        if (clearBtn) {
            clearBtn.style.display = 'none';
            clearBtn.addEventListener('click', () => {
                searchInput.value = '';
                this.searchQuery = '';
                this.displayedCount = 0;
                this.applyFilter();
                this.render();
                clearBtn.style.display = 'none';
                searchInput.focus();
            });
        }

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                this.searchQuery = '';
                this.displayedCount = 0;
                this.applyFilter();
                this.render();
                if (clearBtn) clearBtn.style.display = 'none';
                searchInput.blur();
            }
        });
    },

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

    setupInfiniteScroll() {
        const trigger = document.getElementById('load-trigger');
        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && !this.isLoading) {
                this.loadMore();
            }
        }, { rootMargin: '200px' });

        observer.observe(trigger);
    },

    applyFilter() {
        const filters = this.activeFilters;

        this.filteredMovies = this.allMovies.filter(movie => {
            // No filters selected = show all
            if (filters.size === 0) {
                // No category filter — show all
            } else {
                // OR logic: movie must match ANY selected filter
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
                            if (movie.categories?.is_staff_pick || movie.featured || this.staffPicks.includes(String(movie.id))) matchesAny = true;
                            break;
                        case 'foreign':
                            if (movie.categories?.is_foreign ||
                                (movie.original_language && movie.original_language !== 'en')) matchesAny = true;
                            break;
                        case 'series':
                            if (movie.content_type === 'limited_series') matchesAny = true;
                            break;
                        case 'restorations':
                            if (movie.categories?.is_restoration === true) matchesAny = true;
                            break;
                        case 'documentary':
                            if (movie.categories?.is_documentary === true) matchesAny = true;
                            break;
                        case 'virtual-screenings':
                            if (movie.categories?.is_virtual_screening === true) matchesAny = true;
                            break;
                        case 'pre-orders':
                            if (movie._is_preorder === true) matchesAny = true;
                            break;
                    }
                    if (matchesAny) break;
                }
                if (!matchesAny) return false;
            }

            // Then apply search filter if query exists
            if (this.searchQuery) {
                const query = this.searchQuery;
                const title = (movie.title || '').toLowerCase();
                const director = (movie.director || '').toLowerCase();
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

    loadMore() {
        if (this.displayedCount >= this.filteredMovies.length) return;

        this.isLoading = true;
        const start = this.displayedCount;
        const end = Math.min(start + this.loadIncrement, this.filteredMovies.length);
        const moviesToAdd = this.filteredMovies.slice(start, end);

        this.displayedCount = end;
        this.appendMovies(moviesToAdd, start === 0);
        this.isLoading = false;
    },

    render() {
        const feed = document.getElementById('movie-feed');
        feed.innerHTML = '';
        this.displayedCount = 0;
        this.loadMore();

        if (this.filteredMovies.length === 0) {
            feed.innerHTML = `
                <div class="empty-state">
                    <h3>No movies found</h3>
                    <p>Try a different filter</p>
                </div>
            `;
        }
    },

    appendMovies(movies, isFirstBatch) {
        const feed = document.getElementById('movie-feed');
        let lastDate = isFirstBatch ? '' : this.getLastRenderedDate();
        let preorderSectionStarted = false;

        // Add trailer reel card at the top of the first batch
        if (isFirstBatch && !this.searchQuery) {
            const now = new Date();
            const weekStart = new Date(now);
            weekStart.setDate(now.getDate() - now.getDay());
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);
            const dateRange = weekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' \u2013 ' + weekEnd.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

            const reelCard = document.createElement('div');
            reelCard.className = 'trailer-reel-card';
            reelCard.innerHTML = `
                <div class="trailer-reel-title">NEW TRAILERS</div>
                <div class="trailer-reel-date">${dateRange}</div>
                <div class="trailer-reel-icon">&#9654;</div>
            `;
            reelCard.addEventListener('click', () => this.openTrailerReel());
            feed.appendChild(reelCard);
        }

        movies.forEach(movie => {
            // Pre-order movies: show section header once, no date headers
            if (movie._is_preorder) {
                if (!preorderSectionStarted) {
                    preorderSectionStarted = true;
                    const header = document.createElement('div');
                    header.className = 'date-header';
                    header.dataset.date = 'preorder';
                    header.innerHTML = `
                        <div class="date-badge date-badge-preorder">
                            <span class="date-badge-text">PRE-ORDER</span>
                        </div>
                    `;
                    feed.appendChild(header);
                }
            } else {
                const date = movie.digital_date.substring(0, 10);

                // Add date header when date changes
                if (date !== lastDate) {
                    feed.appendChild(this.createDateHeader(date));
                    lastDate = date;
                }
            }

            // Add movie card
            feed.appendChild(this.createFlipCard(movie));
        });
    },

    getLastRenderedDate() {
        const headers = document.querySelectorAll('.date-header');
        if (headers.length === 0) return '';
        const lastHeader = headers[headers.length - 1];
        return lastHeader.dataset.date || '';
    },

    createDateHeader(dateStr) {
        const d = new Date(dateStr + 'T12:00:00');
        const weekday = d.toLocaleDateString('en', { weekday: 'short' }).toUpperCase();
        const month = d.toLocaleDateString('en', { month: 'short' }).toUpperCase();
        const day = d.getDate();

        const header = document.createElement('div');
        header.className = 'date-header';
        header.dataset.date = dateStr;
        header.innerHTML = `
            <div class="date-badge">
                <span class="date-badge-text">${weekday}, ${month} ${day}</span>
            </div>
        `;
        return header;
    },

    navigateCard(card, direction) {
        const allCards = Array.from(document.querySelectorAll('#movie-feed .flip-card'));
        const idx = allCards.indexOf(card);
        const targetIdx = idx + direction;
        if (targetIdx < 0 || targetIdx >= allCards.length) return;
        const targetCard = allCards[targetIdx];
        card.classList.remove('flipped');
        setTimeout(() => {
            targetCard.classList.add('flipped');
            targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 150);
    },

    createFlipCard(movie) {
        const isStaffPick = movie.categories?.is_staff_pick || this.staffPicks.includes(movie.id);

        const card = document.createElement('div');
        card.className = `flip-card${isStaffPick ? ' staff-pick' : ''}${movie.categories?.is_virtual_screening ? ' screening-movie' : ''}`;
        card.dataset.id = movie.id;

        // Get streaming badge info
        const streamingBadge = this.getStreamingBadge(movie);
        const watchButton = this.getWatchButton(movie);

        // Build card HTML
        card.innerHTML = `
            <div class="flip-inner">
                <div class="flip-front">
                    <div class="poster-wrap">
                        <div class="poster-fallback"><span class="poster-fallback-title">${movie.display_title || movie.title || 'Untitled'}</span></div>
                        <img class="poster"
                             src="${movie.poster || ''}"
                             alt="${movie.title}"
                             loading="lazy"
                             ${movie.poster ? '' : 'style="display:none"'}
                             onerror="this.style.display='none';">
                        ${streamingBadge}
                        ${movie.categories?.is_restoration ? '<span class="poster-badge badge-restoration">RESTORED</span>' : ''}
                        ${movie.categories?.is_virtual_screening
                            ? this.getScreeningRibbon(movie)
                            : isStaffPick
                            ? '<div class="badge-bar red">\u2605 STAFF PICK \u2605</div>'
                            : ''}
                        ${this.getScoreBadges(movie)}
                    </div>
                </div>
                <div class="card-caption">
                    <div class="card-caption-title">${movie.display_title || movie.title || 'Untitled'}</div>
                    <div class="card-caption-meta">${movie.crew?.director || ''}${this.abbreviateCountry(movie.country) ? ` \u2022 ${this.abbreviateCountry(movie.country)}` : ''}</div>
                </div>
                <div class="flip-back">
                    <div class="back-content">
                    <div class="back-title-row">
                        <h2 class="back-title">${movie.display_title || movie.title || 'Untitled'}</h2>
                        ${movie.year ? `<span class="back-year">(${movie.year})</span>` : ''}
                        ${isStaffPick ? '<span class="back-staff-badge">STAFF PICK</span>' : ''}
                        ${movie.digital_date ? `<span class="back-date">${this.formatShortDate(movie.digital_date)}</span>` : ''}
                    </div>
                    <p class="back-synopsis">${movie.synopsis || 'No synopsis available.'}</p>
                    ${movie.pull_quotes?.length ? `<div class="back-pull-quotes">${movie.pull_quotes.map(q => '<div class="back-pq"></div>').join('')}</div>` : ''}
                    <p class="back-meta">
                        <strong>Dir:</strong> ${movie.crew?.director || 'Unknown'}
                        ${this.abbreviateCountry(movie.country) ? ` &bull; ${this.abbreviateCountry(movie.country)}` : ''}
                        ${movie.runtime ? ` &bull; ${movie.runtime} min` : ''}
                    </p>
                    <p class="back-meta-secondary">
                        ${movie.genres?.slice(0, 3).join(', ') || ''}
                        ${movie.crew?.cast?.length ? ` &bull; Starring: ${movie.crew.cast.slice(0, 2).join(', ')}` : ''}
                        ${movie.original_language && movie.original_language !== 'en' ? ` &bull; Lang: ${movie.original_language.toUpperCase()}` : ''}
                    </p>
                    ${this.getTrailerButtonFull(movie)}
                    <div class="watch-stack">
                        ${watchButton}
                    </div>
                    <div class="info-row">
                        ${this.getWikiButton(movie)}
                        ${this.getRTButton(movie)}
                        ${this.getMCButton(movie)}
                        ${this.getIMDbButton(movie)}
                    </div>
                    <div class="nav-row">
                        <button class="btn-nav btn-nav-prev" aria-label="Previous">&#8592;</button>
                        <button class="btn-nav btn-nav-next" aria-label="Next">&#8594;</button>
                    </div>
                    </div>
                </div>
            </div>
        `;

        // Populate pull quote text safely (avoid XSS from innerHTML)
        if (movie.pull_quotes?.length) {
            const pqDivs = card.querySelectorAll('.back-pq');
            movie.pull_quotes.forEach((q, i) => {
                if (pqDivs[i]) {
                    const quote = document.createElement('q');
                    quote.textContent = q.text;
                    pqDivs[i].appendChild(quote);
                    if (q.critic || q.outlet) {
                        const cite = document.createElement('cite');
                        cite.textContent = [q.critic, q.outlet].filter(Boolean).join(', ');
                        pqDivs[i].appendChild(cite);
                    }
                }
            });
        }

        // Add screening callout to synopsis
        if (movie.categories?.is_virtual_screening && movie.virtual_screening_info?.screening_name) {
            const synopsisEl = card.querySelector('.back-synopsis');
            if (synopsisEl) {
                const callout = document.createElement('span');
                callout.className = 'screening-callout';
                const festName = movie.virtual_screening_info.screening_name;
                const endDate = movie.virtual_screening_info?.available_end;
                if (endDate) {
                    const [y, m, d] = endDate.split('-');
                    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                    callout.textContent = ` Virtual screening available as part of the ${festName}. Ends ${months[parseInt(m,10)-1]} ${parseInt(d,10)}.`;
                } else {
                    callout.textContent = ` Virtual screening available as part of the ${festName}.`;
                }
                synopsisEl.appendChild(callout);
            }
        }

        // Touch / swipe state — tracked at card level so both front and back work
        let swipeTouchStartX = 0, swipeTouchStartY = 0, justSwiped = false;

        card.addEventListener('touchstart', (e) => {
            swipeTouchStartX = e.touches[0].clientX;
            swipeTouchStartY = e.touches[0].clientY;
        }, { passive: true });

        // Horizontal swipe on the back → navigate prev/next
        const backEl = card.querySelector('.flip-back');
        backEl.addEventListener('touchend', (e) => {
            const deltaX = e.changedTouches[0].clientX - swipeTouchStartX;
            const deltaY = e.changedTouches[0].clientY - swipeTouchStartY;
            if (Math.abs(deltaX) > SWIPE_MIN_DISTANCE && Math.abs(deltaX) > Math.abs(deltaY) * SWIPE_DIRECTION_RATIO) {
                justSwiped = true;
                setTimeout(() => { justSwiped = false; }, SWIPE_DEBOUNCE_MS);
                this.navigateCard(card, deltaX > 0 ? -1 : 1);
            }
        }, { passive: true });

        // Tap-to-flip via touchend — fires instantly, no 300ms iOS delay
        // Uses a flag instead of e.preventDefault() — iOS ignores preventDefault
        // on touchend inside transform-style: preserve-3d contexts
        let touchFlipped = false;
        card.addEventListener('touchend', (e) => {
            if (e.target.closest('a, button')) return;
            const dx = e.changedTouches[0].clientX - swipeTouchStartX;
            const dy = e.changedTouches[0].clientY - swipeTouchStartY;
            if (Math.abs(dx) < TAP_MAX_DISTANCE && Math.abs(dy) < TAP_MAX_DISTANCE) {
                if (justSwiped) return;
                touchFlipped = true;
                setTimeout(() => { touchFlipped = false; }, TAP_DEBOUNCE_MS);
                card.classList.toggle('flipped');
            }
        }, { passive: true });

        // Click fallback for desktop (mouse) users
        card.addEventListener('click', (e) => {
            if (touchFlipped) { touchFlipped = false; return; }
            if (justSwiped) return;
            if (e.target.closest('a, button')) return;
            card.classList.toggle('flipped');
        });

        // Nav arrow buttons
        card.querySelector('.btn-nav-prev').addEventListener('click', () => this.navigateCard(card, -1));
        card.querySelector('.btn-nav-next').addEventListener('click', () => this.navigateCard(card, 1));

        return card;
    },

    getStreamingBadge(movie) {
        const watchLinks = movie.watch_links || {};
        const providers = movie.providers || {};

        // Pre-order: pipeline sets _is_preorder flag during enrichment
        if (movie._is_preorder) {
            const poDate = movie.digital_date ? this.formatShortDate(movie.digital_date) : 'TBD';
            return '<span class="poster-badge badge-preorder"><span class="po-label">PRE-ORDER</span><span class="po-date">' + poDate + '</span></span>';
        }

        // Get streaming service name
        let service = watchLinks.streaming?.service;
        if (!service && providers.streaming?.length > 0) {
            service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
        }

        if (!service) {
            // Check for VOD (array or single dict)
            const vodArr = Array.isArray(watchLinks.vod) ? watchLinks.vod
                : (watchLinks.vod?.service ? [watchLinks.vod] : []);
            const hasScreeningVod = vodArr.some(v => {
                const s = (v.service || '').toLowerCase();
                const l = v.link || '';
                return s.includes('eventive') || l.includes('eventive.org') || l.includes('festivalplayer') || l.includes('shift72.com');
            });
            if (hasScreeningVod) {
                return '<span class="poster-badge badge-screening">VIRTUAL SCREENING</span>';
            }
            if (vodArr.some(v => v.service && v.link) || providers.rental?.length > 0) {
                return '<span class="poster-badge badge-vod">RENT</span>';
            }
            return '';
        }

        // Map service to badge class
        const resolved = this.resolveService(service);
        let displayName, badgeClass;
        if (resolved) {
            displayName = resolved.name;
            badgeClass = 'badge-' + resolved.class;
        } else {
            displayName = service.toUpperCase().substring(0, 10);
            badgeClass = 'badge-other';
        }

        return `<span class="poster-badge ${badgeClass}">${displayName}</span>`;
    },

    getWatchButton(movie) {
        const watchLinks = movie.watch_links || {};
        const providers = movie.providers || {};

        // Check streaming first
        let service = watchLinks.streaming?.service;
        let link = watchLinks.streaming?.link;

        if (!service && providers.streaming?.length > 0) {
            service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
        }

        if (service && link) {
            const resolved = this.resolveService(service);
            const displayName = resolved?.btnName || service;
            const cls = resolved?.class || '';

            return `<a href="${link}" target="_blank" rel="noopener" class="btn-watch-full ${cls}">${displayName}</a>`;
        }

        // Fall back to VOD — separate Amazon + Apple TV buttons
        const vodEntries = Array.isArray(watchLinks.vod) ? watchLinks.vod
            : (watchLinks.vod?.service ? [watchLinks.vod] : []);
        const vodWithLinks = vodEntries.filter(v => v.link);
        if (vodWithLinks.length > 0) {
            // Resolve all VOD, then filter out fallback-only services (e.g. Plex)
            // when non-fallback services are available
            let resolved = vodWithLinks.map(vod => {
                const vodType = NRWMobile.resolveVODService(vod.service, vod.link);
                if (!vodType) return null;
                return { vodType, link: vod.link };
            }).filter(Boolean);
            const hasNonFallback = resolved.some(v => !v.vodType.fallback);
            if (hasNonFallback) resolved = resolved.filter(v => !v.vodType.fallback);
            const vodBtns = resolved.map(({ vodType, link }) =>
                `<a href="${link}" target="_blank" rel="noopener" class="btn-watch-vod ${vodType.key}">${vodType.label}</a>`
            );
            if (vodBtns.length === 1) return vodBtns[0].replace('btn-watch-vod', 'btn-watch-full');
            if (vodBtns.length > 1) return `<div class="vod-row">${vodBtns.join('')}</div>`;
        }

        // Pre-order links (JustWatch buy offers for pre-order movies)
        const preOrderLinks = Array.isArray(movie.pre_order_links) ? movie.pre_order_links : [];
        if (preOrderLinks.length > 0) {
            const poBtns = preOrderLinks.map(pl => {
                const vodType = NRWMobile.resolveVODService(pl.service, pl.link);
                if (!vodType) return '';
                return `<a href="${pl.link}" target="_blank" rel="noopener" class="btn-watch-full ${vodType.key}">Pre-Order</a>`;
            }).filter(Boolean);
            if (poBtns.length > 0) {
                const poDate = movie.digital_date ? this.formatShortDate(movie.digital_date) : 'TBD';
                return `${poBtns[0]}<span class="po-available-date">Available ${poDate}</span>`;
            }
        }

        return '';
    },

    getTrailerButtonFull(movie) {
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        if (!trailerUrl) return '';
        const isMP4 = (() => { try { return new URL(trailerUrl).pathname.endsWith('.mp4'); } catch { return trailerUrl.endsWith('.mp4'); } })();
        if (isMP4) {
            return `<a href="#" onclick="NRWMobile.showTrailer('${movie.id}');return false;" class="btn-full btn-trailer">Trailer</a>`;
        }
        return `<a href="${trailerUrl}" target="_blank" rel="noopener" class="btn-full btn-trailer">Trailer</a>`;
    },

    getRTButton(movie) {
        if (!movie.rt_score || !movie.links?.rt) return '';
        return `<a href="${movie.links.rt}" target="_blank" rel="noopener" class="btn-equal btn-rt"><img src="../assets/logos/rt.png" class="btn-logo" alt="RT"> ${movie.rt_score}</a>`;
    },

    getMCButton(movie) {
        if (!movie.metacritic_score || movie.metacritic_score === "0" || !movie.links?.metacritic) return '';
        return `<a href="${movie.links.metacritic}" target="_blank" rel="noopener" class="btn-equal btn-mc"><img src="../assets/logos/metacritic.png" class="btn-logo" alt="MC"> ${movie.metacritic_score}</a>`;
    },

    getIMDbButton(movie) {
        if (movie.imdb_rating) {
            const imdbUrl = movie.links?.imdb;
            if (imdbUrl) {
                return `<a href="${imdbUrl}" target="_blank" rel="noopener" class="btn-equal btn-imdb"><img src="../assets/logos/imdb.png" class="btn-logo" alt="IMDb"> ${movie.imdb_rating}</a>`;
            }
            return `<span class="btn-equal btn-imdb" style="opacity:0.5"><img src="../assets/logos/imdb.png" class="btn-logo" alt="IMDb"> ${movie.imdb_rating}</span>`;
        }
        return '';
    },

    getScoreBadges(movie) {
        let badges = '';
        if (movie.rt_score && movie.links?.rt) {
            badges += `<a href="${movie.links.rt}" target="_blank" rel="noopener" class="card-score-badge rt"><img src="../assets/logos/rt.png" class="score-logo" alt="RT"> ${movie.rt_score}</a>`;
        }
        if (movie.metacritic_score && movie.metacritic_score !== "0" && movie.links?.metacritic) {
            badges += `<a href="${movie.links.metacritic}" target="_blank" rel="noopener" class="card-score-badge mc"><img src="../assets/logos/metacritic.png" class="score-logo" alt="MC"> ${movie.metacritic_score}</a>`;
        }
        if (movie.imdb_rating) {
            const imdbUrl = movie.links?.imdb;
            if (imdbUrl) {
                badges += `<a href="${imdbUrl}" target="_blank" rel="noopener" class="card-score-badge imdb"><img src="../assets/logos/imdb.png" class="score-logo" alt="IMDb"> ${movie.imdb_rating}</a>`;
            } else {
                badges += `<span class="card-score-badge imdb"><img src="../assets/logos/imdb.png" class="score-logo" alt="IMDb"> ${movie.imdb_rating}</span>`;
            }
        }
        return badges ? `<div class="card-score-overlay">${badges}</div>` : '';
    },

    getWikiButton(movie) {
        if (!movie.links?.wikipedia) return '';
        return `<a href="${movie.links.wikipedia}" target="_blank" rel="noopener" class="btn-equal btn-wiki">Wiki</a>`;
    },

    // Trailer reel — plays through hosted trailers from the last 7 days
    openTrailerReel() {
        const cutoff = new Date();
        cutoff.setDate(cutoff.getDate() - 7);

        const reelMovies = this.allMovies
            .filter(m => {
                if (!m.digital_date) return false;
                if (new Date(m.digital_date) < cutoff) return false;
                return m.links?.trailer_hosted;
            })
            .sort((a, b) => new Date(b.digital_date) - new Date(a.digital_date));

        if (reelMovies.length === 0) return;

        this.isTrailerReel = true;
        this._showTrailerAt(reelMovies, 0);
    },

    // Build swipable trailer list and open at the given movie id
    showTrailer(movieId) {
        const isMP4 = url => { try { return new URL(url).pathname.endsWith('.mp4'); } catch { return url.endsWith('.mp4'); } };
        const trailerMovies = this.filteredMovies.filter(m => {
            const url = m.links?.trailer_hosted || m.links?.trailer;
            return url && isMP4(url);
        });
        const idx = trailerMovies.findIndex(m => String(m.id) === String(movieId));
        if (idx === -1) return;
        this.isTrailerReel = false;
        this._showTrailerAt(trailerMovies, idx);
    },

    _showTrailerAt(trailerMovies, idx) {
        const existing = document.getElementById('trailer-overlay');
        if (existing) existing.remove();

        const movie = trailerMovies[idx];
        const url = movie.links.trailer_hosted || movie.links.trailer;
        const hasPrev = idx > 0;
        const hasNext = idx < trailerMovies.length - 1;

        const overlay = document.createElement('div');
        overlay.id = 'trailer-overlay';
        overlay.className = 'trailer-overlay';

        overlay.innerHTML = `
            <div id="trailer-video-wrap" class="trailer-video-wrap">
                <button id="trailer-close" class="trailer-close-btn">&times;</button>
                ${hasPrev ? '<button id="trailer-prev" class="trailer-nav-btn prev">&#8592;</button>' : ''}
                ${hasNext ? '<button id="trailer-next" class="trailer-nav-btn next">&#8594;</button>' : ''}
                <video controls autoplay playsinline>
                    <source src="${url}" type="video/mp4">
                </video>
                <div class="trailer-video-title">${movie.display_title || movie.title || ''}</div>
                ${trailerMovies.length > 1 ? `<div class="trailer-reel-counter">${idx + 1} of ${trailerMovies.length}</div>` : ''}
            </div>
        `;

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        const close = () => { overlay.remove(); document.body.style.overflow = ''; document.removeEventListener('keydown', onKeydown); this.isTrailerReel = false; };
        const onKeydown = e => { if (e.key === 'Escape') close(); };
        document.addEventListener('keydown', onKeydown);

        overlay.querySelector('#trailer-close').addEventListener('click', close);

        // Tap outside the video box (above/below) closes the overlay
        overlay.addEventListener('click', e => {
            if (!overlay.querySelector('#trailer-video-wrap').contains(e.target)) close();
        });

        // On video end: advance to next in reel mode, close otherwise
        overlay.querySelector('video').addEventListener('ended', () => {
            if (this.isTrailerReel && hasNext) {
                close();
                this._showTrailerAt(trailerMovies, idx + 1);
            } else {
                close();
            }
        });

        if (hasPrev) overlay.querySelector('#trailer-prev').addEventListener('click', () => { close(); this._showTrailerAt(trailerMovies, idx - 1); });
        if (hasNext) overlay.querySelector('#trailer-next').addEventListener('click', () => { close(); this._showTrailerAt(trailerMovies, idx + 1); });

        // Swipe left/right to navigate trailers
        let swipeStartX = 0;
        overlay.addEventListener('touchstart', e => { swipeStartX = e.touches[0].clientX; }, { passive: true });
        overlay.addEventListener('touchend', e => {
            const dx = e.changedTouches[0].clientX - swipeStartX;
            if (Math.abs(dx) > TRAILER_SWIPE_MIN) {
                if (dx > 0 && hasPrev) { close(); this._showTrailerAt(trailerMovies, idx - 1); }
                else if (dx < 0 && hasNext) { close(); this._showTrailerAt(trailerMovies, idx + 1); }
            }
        }, { passive: true });
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => NRWMobile.init());
