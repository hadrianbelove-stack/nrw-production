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
    slopMode: 'free',          // 'free' = hide slop, 'all' = show all, 'only' = show only slop
    showFest: false,           // When true, show virtual screening movies
    showPreorders: false,      // When true, show pre-order movies at the top
    showHighlightsOnly: false, // When true, show only staff picks (HIGHLIGHTS toggle)
    searchQuery: '',     // Current search query
    displayedCount: CONFIG.moviesPerPage,  // How many movies currently shown
    loadIncrement: CONFIG.moviesPerPage,   // How many to add when clicking "More"

    // Shared config — loaded from assets/shared-config.js
    SERVICE_MAP: NRWConfig.SERVICE_MAP,
    VOD_SERVICE_MAP: NRWConfig.VOD_SERVICE_MAP,
    abbreviateCountry: NRWConfig.abbreviateCountry,
    lightboxCountry: NRWConfig.lightboxCountry,

    // Filter descriptions — shown when a single filter is active
    FILTER_DESCRIPTIONS: {
        'indie': {
            title: 'Indie',
            text: 'The smaller films, the independents, the ones without a billboard campaign. These movies flew under the radar theatrically but are worth knowing about now that they\'re available to stream at home.'
        },
        'staff-picks': {
            title: 'Selects',
            text: 'The ones we\'re vouching for. Out of everything on the wall, these are the movies we think are genuinely worth your time. Not a popularity contest, just honest recommendations.'
        },
        'foreign': {
            title: 'Foreign',
            text: 'Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces. The only thing they have in common is subtitles and the fact that they\'re streaming now.'
        },
        'restorations': {
            title: 'Reissues',
            text: 'Classic and catalog titles with new digital life. These are films that have been restored, remastered, or newly reissued on streaming platforms. Old movies, fresh transfers.'
        },
        'documentary': {
            title: 'Documentary',
            text: 'Non-fiction filmmaking. Documentaries covering real stories, real people, and real events — now available to stream at home.'
        },
        'horror': {
            title: 'Horror',
            text: 'The stuff that goes bump. Horror films now streaming — from slow-burn dread to full-on splatter.'
        },
        'action': {
            title: 'Action',
            text: 'High-octane, kinetic filmmaking. Action movies now available to watch at home.'
        },
        'comedy': {
            title: 'Comedy',
            text: 'Films that are actually funny. Comedies — broad and subtle — now streaming.'
        },
        'family': {
            title: 'Family',
            text: 'Films for all ages. Family movies now available to watch at home.'
        },
        'thriller': {
            title: 'Thriller',
            text: 'Suspense, dread, and unease. Thrillers now streaming — from psychological slow-burns to pulse-pounding crime.'
        }
    },

    // Date strips adopt the active filter's color when exactly one filter is on
    STRIP_COLORS: {
        'indie': '#00d4aa',
        'horror': '#ff5e57',
        'action': '#ff9500',
        'comedy': '#ffd32a',
        'family': '#2ed573',
        'thriller': '#d63031',
        'foreign': '#e84393',
        'documentary': '#4A90D9',
        'restorations': '#C8A951'
    },

    resolveService: NRWConfig.resolveService,
    resolveVODService: NRWConfig.resolveVODService,
    cleanServiceName: NRWConfig.cleanServiceName,

    // Normalize streaming to {service, link} — handles both array and dict formats
    getStreaming(wl) {
        const s = wl?.streaming;
        if (Array.isArray(s) && s.length > 0) return s[0];
        if (s?.service) return s;
        return null;
    },

    // All free-streaming services as a list (one button each in the lightbox).
    getStreamingList(wl) {
        const s = wl?.streaming;
        if (Array.isArray(s)) return s.filter(x => x && x.service && x.link);
        if (s?.service && s?.link) return [s];
        return [];
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
                this.setupHeaderKeyboardNav();
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
        const btnArray = Array.from(filterButtons);

        filterButtons.forEach(btn => {
            btn.addEventListener('keydown', (e) => {
                if (e.key !== 'Tab') return;
                e.preventDefault();
                const idx = btnArray.indexOf(btn);
                if (!e.shiftKey) {
                    if (idx < btnArray.length - 1) btnArray[idx + 1].focus();
                    else document.getElementById('search-input').focus();
                } else {
                    if (idx > 0) btnArray[idx - 1].focus();
                }
            });

            btn.addEventListener('click', () => {
                const filter = btn.dataset.filter;
                if (!filter) return;

                // One exclusive group: picking a genre clears every other view
                // (other genres + the toggles + slop). Re-clicking the active
                // genre returns to the default wall.
                const wasActive = this.activeFilters.has(filter);
                this.setExclusiveView('genre');
                this.activeFilters.clear();
                document.querySelectorAll('.filter-btn.active').forEach(b => b.classList.remove('active'));
                if (!wasActive) {
                    this.activeFilters.add(filter);
                    btn.classList.add('active');
                }

                this.gridClearSelection();
                this.displayedCount = this.loadIncrement;
                this.applyFilter();
                this.updateFilterDescription();
                this.renderWallWithMore();
            });
        });

        // Slop toggle (3-state: free / all / only) — part of the exclusive view group
        const slopToggle = document.getElementById('slop-free-toggle');
        if (slopToggle) {
            const SLOP_STATES = ['free', 'all', 'only'];
            this.syncSlopToggle();
            slopToggle.addEventListener('click', () => {
                const idx = SLOP_STATES.indexOf(this.slopMode);
                this.slopMode = SLOP_STATES[(idx + 1) % 3];
                this.setExclusiveView('slop');  // clear genres + other toggles
                this.syncSlopToggle();
                this.gridClearSelection();
                this.displayedCount = this.loadIncrement;
                this.updateFilterDescription();
                this.applyFilter();
                this.renderWallWithMore();
            });
        }

        // Highlights toggle — show only staff picks
        const highlightsToggle = document.getElementById('highlights-toggle');
        if (highlightsToggle) {
            highlightsToggle.classList.toggle('active', this.showHighlightsOnly);
            highlightsToggle.addEventListener('click', () => {
                this.showHighlightsOnly = !this.showHighlightsOnly;
                highlightsToggle.classList.toggle('active', this.showHighlightsOnly);
                if (this.showHighlightsOnly) this.setExclusiveView('selects');
                this.displayedCount = this.loadIncrement;
                this.updateFilterDescription();
                this.applyFilter();
                this.renderWallWithMore();
            });
        }

        // Fest (virtual screenings) toggle
        const festToggle = document.getElementById('fest-toggle');
        if (festToggle) {
            festToggle.classList.toggle('active', this.showFest);
            festToggle.addEventListener('click', () => {
                this.showFest = !this.showFest;
                festToggle.classList.toggle('active', this.showFest);
                if (this.showFest) this.setExclusiveView('fests');
                this.displayedCount = this.loadIncrement;
                this.updateFilterDescription();
                this.applyFilter();
                this.renderWallWithMore();
            });
        }

        // Sticky header: expose its height so date strips pin just beneath it
        const updateHeaderOffset = () => {
            const headerEl = document.querySelector('header');
            if (headerEl) {
                document.documentElement.style.setProperty('--header-height', headerEl.offsetHeight + 'px');
            }
        };
        updateHeaderOffset();
        window.addEventListener('resize', updateHeaderOffset);
        // Re-measure once web fonts finish loading — they can change the header's
        // height a beat after first paint, leaving the date strips docked a few px off.
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(updateHeaderOffset);
        }

        // Pre-order toggle
        const preorderToggle = document.getElementById('preorder-toggle');
        if (preorderToggle) {
            preorderToggle.classList.toggle('active', this.showPreorders);
            preorderToggle.addEventListener('click', () => {
                this.showPreorders = !this.showPreorders;
                preorderToggle.classList.toggle('active', this.showPreorders);
                if (this.showPreorders) this.setExclusiveView('preorders');
                this.displayedCount = this.loadIncrement;
                this.updateFilterDescription();
                this.applyFilter();
                this.renderWallWithMore();
            });
        }
    },

    // The whole filter bar is ONE exclusive group: the nine genre chips plus
    // the Selects / Fests / Pre-Orders / Slop views. Selecting any one clears
    // all the others (state flags + button highlights). `winner` names the view
    // being turned on so it isn't cleared; pass a non-matching value to reset all.
    setExclusiveView(winner) {
        if (winner !== 'genre') {
            this.activeFilters.clear();
            document.querySelectorAll('.filter-btn.active').forEach(b => b.classList.remove('active'));
        }
        if (winner !== 'selects')   { this.showHighlightsOnly = false; document.getElementById('highlights-toggle')?.classList.remove('active'); }
        if (winner !== 'fests')     { this.showFest = false;           document.getElementById('fest-toggle')?.classList.remove('active'); }
        if (winner !== 'preorders') { this.showPreorders = false;      document.getElementById('preorder-toggle')?.classList.remove('active'); }
        if (winner !== 'slop')      { this.slopMode = 'free';          this.syncSlopToggle(); }
    },

    // Sync the 3-state slop toggle's data-state + label to this.slopMode.
    syncSlopToggle() {
        const toggle = document.getElementById('slop-free-toggle');
        if (!toggle) return;
        toggle.dataset.state = this.slopMode;
        const label = document.getElementById('slop-state-label');
        const SLOP_LABELS = { free: 'SLOP FREE', all: 'ALL', only: 'SLOP ONLY' };
        if (label) label.textContent = SLOP_LABELS[this.slopMode];
    },

    // Show/hide filter description based on active filters
    updateFilterDescription() {
        const el = document.getElementById('filter-description');
        if (!el) return;
        // Filter description blurbs removed (matches tvOS — no genre/view descriptions).
        el.classList.remove('active');
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

        // Allow Escape to clear search; Tab to enter grid
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                this.searchQuery = '';
                this.displayedCount = this.loadIncrement;
                this.applyFilter();
                this.renderWallWithMore();
                if (clearBtn) clearBtn.style.display = 'none';
                searchInput.blur();
            } else if (e.key === 'Tab' && !e.shiftKey) {
                e.preventDefault();
                searchInput.blur();
                this.gridNavActive = true;
                const { allCards } = this.buildGridMap();
                if (allCards.length > 0) this.gridSelect(allCards[0]);
            } else if (e.key === 'Tab' && e.shiftKey) {
                e.preventDefault();
                const filterBtns = document.querySelectorAll('.filter-btn');
                if (filterBtns.length > 0) filterBtns[filterBtns.length - 1].focus();
            }
        });
    },

    // True if a movie carries a given genre/category tag. Genre views show
    // EVERY film with the tag — slop and fests included — so this is tag-only,
    // with no slop/fest gating.
    movieMatchesGenre(movie, filter) {
        switch (filter) {
            case 'indie':        return !!movie.filters?.is_indie;
            case 'foreign':      return !!(movie.filters?.is_foreign ??
                                     (movie.original_language && movie.original_language !== 'en'));
            case 'restorations': return !!movie.filters?.is_restoration;
            case 'documentary':  return !!movie.filters?.is_documentary;
            case 'horror':
            case 'action':
            case 'comedy':
            case 'family':
            case 'thriller':     return (movie.genres || []).some(g => g.toLowerCase().includes(filter));
            default:             return false;
        }
    },

    matchesSearch(movie, query) {
        const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
        const nq = norm(query);
        return norm(movie.title || '').includes(nq) ||
               norm(movie.crew?.director || '').includes(nq) ||
               norm(movie.capsule || movie.synopsis || '').includes(nq) ||
               norm((movie.genres || []).join(' ')).includes(nq) ||
               norm(movie.country || '').includes(nq) ||
               String(movie.year || '').includes(query);
    },

    applyFilter() {
        const query = this.searchQuery;
        const activeGenre = this.activeFilters.size ? [...this.activeFilters][0] : null;

        this.filteredMovies = this.allMovies.filter(movie => {
            // Search bypasses all view modes
            if (query) return this.matchesSearch(movie, query);

            // The filter bar is one exclusive group; at most one view is active.
            // Each view is a pure tag view (slop + fests included where they match).

            // Pre-orders: their own view; every other view hides upcoming titles
            if (this.showPreorders) return !!movie._is_preorder;
            // Fest view includes upcoming screenings (shown under "Available Soon"),
            // so it must run before the pre-order exclusion below.
            if (this.showFest) return !!movie.filters?.is_virtual_screening;
            if (movie._is_preorder) return false;

            if (this.showHighlightsOnly) return !!(movie.filters?.is_staff_pick || movie.featured);
            // Slop view = slop films on the regular wall; fests live only in the Fests view
            if (this.slopMode === 'only') return !!(movie.is_slop || movie._is_slop_guess) && !movie.filters?.is_virtual_screening;

            // Genre view — every film with that tag, slop + fests included
            if (activeGenre) return this.movieMatchesGenre(movie, activeGenre);

            // Default wall: hide slop (unless slop toggle is on 'all'), hide fests
            if (this.slopMode === 'free' && (movie.is_slop || movie._is_slop_guess)) return false;
            if (movie.filters?.is_virtual_screening) return false;
            return true;
        });
    },

    renderWallWithMore() {
        // Fest view paginates "now" before "soon" so a large festival batch can't
        // push available-now screenings past the page cut (renderWall regroups them).
        const _fToday = new Date().toISOString().slice(0, 10);
        const _fStart = m => (m.virtual_screening_info && m.virtual_screening_info.available_start) || '';
        const sortedMovies = [...this.filteredMovies].sort((a, b) => {
            if (this.showFest) {
                const aNow = !_fStart(a) || _fStart(a) <= _fToday;
                const bNow = !_fStart(b) || _fStart(b) <= _fToday;
                if (aNow !== bNow) return aNow ? -1 : 1;
                return _fStart(a).localeCompare(_fStart(b));
            }
            return new Date(b.digital_date) - new Date(a.digital_date);
        });

        const moviesToShow = sortedMovies.slice(0, this.displayedCount);
        const hasMore = this.displayedCount < sortedMovies.length;

        this.renderWall(moviesToShow);
        this.renderMoreButton(hasMore, sortedMovies.length);

        // After a filter/toggle change (pagination reset to the first page), jump
        // back to the top so the new view starts at its banner, not mid-scroll.
        // "Load more" grows displayedCount so it's skipped; the >0 guard avoids a
        // no-op jump on the initial render or when already at the top.
        if (this.displayedCount === this.loadIncrement && window.scrollY > 0) {
            window.scrollTo({ top: 0 });
        }
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

        // Separate into three buckets: fest, pre-orders, regular
        const festMovies = movies.filter(m => !m._is_preorder && m.filters?.is_virtual_screening);
        const preorderMovies = movies.filter(m => m._is_preorder);
        const regularMovies = movies.filter(m => !m._is_preorder && !m.filters?.is_virtual_screening);

        // Sort regular movies by date descending, then staff picks first within each date
        regularMovies.sort((a, b) => {
            const dateA = new Date(a.digital_date);
            const dateB = new Date(b.digital_date);
            if (dateB.getTime() !== dateA.getTime()) {
                return dateB - dateA;  // Newest first
            }
            // Same date: staff picks first
            const aStaffPick = a.filters?.is_staff_pick || this.staffPicks.includes(a.id);
            const bStaffPick = b.filters?.is_staff_pick || this.staffPicks.includes(b.id);
            if (aStaffPick && !bStaffPick) return -1;
            if (!aStaffPick && bStaffPick) return 1;
            return 0;
        });

        // Sort pre-orders by date ascending (nearest release first)
        preorderMovies.sort((a, b) => (a.digital_date || '').localeCompare(b.digital_date || ''));

        // Sort fest: active (NOW) first by soonest expiry, then upcoming (FUTURE) ascending, then expired
        const today = new Date().toISOString().slice(0, 10);
        const festTier = m => {
            if (m.virtual_screening_info?.status === 'active') return 0;
            if ((m.digital_date || '') > today) return 1;
            return 2;
        };
        festMovies.sort((a, b) => {
            const ta = festTier(a), tb = festTier(b);
            if (ta !== tb) return ta - tb;
            if (ta === 0) {
                // Both active: soonest to expire first
                return (a.virtual_screening_info?.available_end || '').localeCompare(b.virtual_screening_info?.available_end || '');
            }
            if (ta === 1) {
                // Both future: nearest date first
                return (a.digital_date || '').localeCompare(b.digital_date || '');
            }
            // Both expired: most recent first
            return (b.digital_date || '').localeCompare(a.digital_date || '');
        });

        // Virtual-screening view groups by availability (now / soon), not arrival date
        const vsStart = m => (m.virtual_screening_info && m.virtual_screening_info.available_start) || '';
        const vsEnd = m => (m.virtual_screening_info && m.virtual_screening_info.available_end) || '';
        let orderedMovies;
        if (this.showFest) {
            const vsNow = movies.filter(m => { const s = vsStart(m); return !s || s <= today; })
                                .sort((a, b) => (vsEnd(a) || '9999-99-99').localeCompare(vsEnd(b) || '9999-99-99'));
            const vsSoon = movies.filter(m => { const s = vsStart(m); return s && s > today; })
                                 .sort((a, b) => vsStart(a).localeCompare(vsStart(b)));
            orderedMovies = [...vsNow, ...vsSoon];
        } else {
            // Combine: fest at top, then pre-orders, then regular movies
            orderedMovies = [...festMovies, ...preorderMovies, ...regularMovies];
        }

        let html = '';
        let lastDate = '';
        let isFirstDate = true;
        let vsLastSection = '';
        let vsLastStart = '';
        const SHOW_TRAILERS_CARD = false; // Trailers card temporarily disabled — set true to restore

        // Date strips: single active filter recolors them; each view has its own color
        const singleFilter = this.activeFilters.size === 1 ? [...this.activeFilters][0] : null;
        const filterColor = singleFilter ? this.STRIP_COLORS[singleFilter] : null;
        const dateStripColor = this.showHighlightsOnly ? '#dc143c'
            : this.showFest ? '#f59e0b'
            : this.showPreorders ? '#7c3aed'
            : this.slopMode === 'only' ? '#ff9500'
            : (filterColor || 'var(--accent-primary)');
        const stripHtml = (day, rest, color, extraClass = '', titleAttr = '') =>
            `<div class="date-row-header${extraClass}" style="--strip-c:${color}"${titleAttr}><span class="drh-day">${day}</span>${rest ? `<span class="drh-rest">${rest}</span>` : ''}</div>`;

        // Virtual-screening days-left bottom bar: red when ≤3 days left, gold "Until …" when calm,
        // muted "Opens …" for upcoming screenings.
        const vsDaysBar = (movie) => {
            const info = movie.virtual_screening_info || {};
            const start = info.available_start || '';
            const end = info.available_end || '';
            let cls, txt;
            if (start && start > today) { cls = 'soon'; txt = `Opens ${NRW.formatShortDate(start)}`; }
            else if (!end) { cls = 'calm'; txt = 'Screening live'; }
            else {
                const daysLeft = Math.round((new Date(end + 'T12:00:00') - new Date(today + 'T12:00:00')) / 86400000);
                if (daysLeft <= 3) { cls = 'urgent'; txt = daysLeft <= 0 ? 'Last day' : `${daysLeft} day${daysLeft === 1 ? '' : 's'} left`; }
                else { cls = 'calm'; txt = `Until ${NRW.formatShortDate(end)}`; }
            }
            return `<div class="days-row"><span class="days-pill ${cls}">${txt}</span></div>`;
        };

        // View section banner at the very top — one per active view (exclusive).
        // Then every film flows through the normal date strips below, so each view
        // still shows the films grouped by date (the way SLOP already does).
        if (this.showHighlightsOnly) {
            html += stripHtml('SELECTS', 'OF NOTE', '#dc143c', ' section-banner');
        } else if (this.slopMode === 'only') {
            html += stripHtml('SLOP', 'THE CONTENT RIVER', '#ff9500', ' section-banner');
        } else if (this.showPreorders) {
            html += stripHtml('PRE-ORDER', 'COMING SOON', '#7c3aed', ' section-banner');
        }

        orderedMovies.forEach(movie => {
          if (this.showFest) {
            // VS view: "Available Now" / "Available Soon" banners + start-date dividers
            const _s = vsStart(movie);
            const _section = (_s && _s > today) ? 'soon' : 'now';
            if (_section !== vsLastSection) {
                html += _section === 'now'
                    ? stripHtml('AVAILABLE', 'NOW', '#FFD700', ' section-banner')
                    : stripHtml('AVAILABLE', 'SOON', '#b9952e', ' section-banner');
                vsLastSection = _section;
                vsLastStart = '';
            }
            if (_section === 'soon' && _s !== vsLastStart) {
                const _sd = new Date(_s + 'T12:00:00');
                html += stripHtml(_sd.toLocaleDateString('en', { weekday: 'short' }),
                    `${_sd.toLocaleDateString('en', { month: 'short' })} ${_sd.getDate()} · OPENS`, '#b9952e');
                vsLastStart = _s;
            }
          } else {
            const date = (movie.digital_date || '').substring(0, 10);

            // Date strip whenever the date changes — every view groups by date
            if (date !== lastDate) {
                // Add NEW TRAILERS button before the first date marker
                if (isFirstDate && SHOW_TRAILERS_CARD) {
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
                if (date && !isNaN(d.getTime())) {
                    // Bootstrap dates are approximate — mark with ~ and tooltip
                    const isBootstrapDate = movie.bootstrap_date;
                    const datePrefix = isBootstrapDate ? '~' : '';
                    const dateTitle = isBootstrapDate ? ' title="Approximate date - may have been available earlier"' : '';
                    const dayLabel = d.toLocaleDateString('en', {weekday: 'short'});
                    const restLabel = `${datePrefix}${d.toLocaleDateString('en', {month: 'short'})} ${d.getDate()}`;
                    html += stripHtml(dayLabel, restLabel, dateStripColor,
                        isBootstrapDate ? ' date-approximate' : '', dateTitle);
                } else {
                    html += stripHtml('DATE TBD', '', dateStripColor);
                }

                lastDate = date;
            }
          }

            // Movie card
            const title = movie.title || 'Untitled';
            const year = movie.year || new Date(movie.digital_date).getFullYear();
            
            const isStaffPick = movie.filters?.is_staff_pick || this.staffPicks.includes(movie.id);
            const staffPickClass = isStaffPick ? ' staff-pick-movie' : '';

            const formatShortDate = NRW.formatShortDate;

            // Streaming service Gallery Label frame for card front
            const getStreamingBadge = (movie) => {
                const watchLinks = movie.watch_links || {};
                const providers = movie.providers || {};

                // Pre-order: pipeline sets _is_preorder flag during enrichment
                if (movie._is_preorder) {
                    const poDate = movie.digital_date
                        ? NRW.formatShortDate(movie.digital_date)
                        : 'TBD';
                    return {
                        html: '<div class="streaming-badge badge-preorder"><span class="po-label">PRE-ORDER</span><span class="po-date">' + poDate + '</span></div>',
                        isFrame: false
                    };
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

                if (!service) return { html: '', isFrame: false };

                // Map service to display name and CSS class
                const resolved = NRW.resolveService(service);
                let displayName, svcClass;
                if (resolved) {
                    displayName = resolved.badgeName;
                    svcClass = resolved.class;
                } else {
                    displayName = NRW.cleanServiceName(service).toUpperCase().slice(0, 10);
                    svcClass = 'other';
                }

                const textColor = ['hulu', 'prime', 'pluto'].includes(svcClass) ? 'black' : 'white';
                return {
                    html: `<div class="streaming-frame-header" style="color:${textColor}">
                        <div class="streaming-frame-name">${displayName}</div>
                        <div class="streaming-frame-super">NOW STREAMING</div>
                    </div>`,
                    isFrame: true,
                    svcClass
                };
            };

            const { html: streamingBadgeHtml, isFrame: hasStreamingFrame, svcClass: streamingSvcClass } = getStreamingBadge(movie);
            const restorationBadge = movie.reissue_label
                ? `<div class="restoration-badge">${movie.reissue_label.toUpperCase()}</div>`
                : (movie.filters?.is_restoration ? '<div class="restoration-badge">RESTORED</div>' : '');
            const isScreening = movie.filters?.is_virtual_screening;
            const screeningClass = isScreening ? ' screening-movie' : '';
            const festivalName = movie.virtual_screening_info?.screening_name;
            // VS: festival name in a dark band above the poster (poster not cropped)
            const festBand = isScreening
                ? `<div class="fest-above">${festivalName || 'VIRTUAL SCREENING'}</div>`
                : '';
            // VS: days-left bottom bar; Staff Picks keep the red SELECT badge
            const badgeBar = isScreening
                ? vsDaysBar(movie)
                : isStaffPick
                ? '<div class="badge-bar red">\u2605 SELECT \u2605</div>'
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
                ${festBand}
                <div class="movie-card">
                    <div class="card-inner">
                        <div class="card-front${hasStreamingFrame ? ' streaming-frame' : ''}"${hasStreamingFrame ? ` style="background:var(--svc-${streamingSvcClass},#444);padding:0 12px 12px;"` : ''}>
                            ${streamingBadgeHtml}
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
                    <div class="movie-meta"><span class="m-dir">${NRW._directorLink(movie.crew?.director, movie.links?.director_wiki)}</span><span class="m-rest"> · ${movie.genres?.[0] ? movie.genres[0] + ' · ' : ''}${NRW.abbreviateCountry(movie.country) || 'Unknown Country'}</span></div>
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
    loadTrailerVideo(url, movie) {
        const container = document.getElementById('trailer-video-container');
        if (!container) return;

        // Stop any existing video/iframe first
        const existingVideo = container.querySelector('video');
        if (existingVideo) { existingVideo.pause(); existingVideo.src = ''; }
        const existingIframe = container.querySelector('iframe');
        if (existingIframe) { existingIframe.src = ''; }

        if (this.isHostedTrailer(url)) {
            const subsUrl = movie?.links?.trailer_hosted_subs;
            const trackEl = subsUrl
                ? `<track kind="subtitles" src="${subsUrl}" srclang="en" label="English" default>`
                : '';
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
                    ${trackEl}
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
            video.addEventListener('ended', () => this.trailerNav(1), { once: true });
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
        this.loadTrailerVideo(trailerUrl, movie);
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

        // Ensure a navigable list exists even when the trailer was opened straight
        // from the grid (not via the lightbox), so auto-advance + arrows work.
        if (!this.isTrailerReel && (!this.lightboxMovies || this.lightboxMovies.length === 0)) {
            this.lightboxMovies = [...this.filteredMovies]
                .sort((a, b) => new Date(b.digital_date) - new Date(a.digital_date))
                .slice(0, this.displayedCount);
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
        const currentMovie = this.trailerLightboxIndex >= 0 ? movies[this.trailerLightboxIndex] : null;
        this.loadTrailerVideo(url, currentMovie);

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

    _trailerSpeedToast(rate) {
        const existing = document.getElementById('trailer-speed-toast');
        if (existing) existing.remove();
        const toast = document.createElement('div');
        toast.id = 'trailer-speed-toast';
        toast.textContent = rate === 1 ? '1× Speed' : rate + '× Speed';
        toast.style.cssText = 'position:absolute;top:16px;left:50%;transform:translateX(-50%);' +
            'background:rgba(0,0,0,0.7);color:#fff;padding:6px 14px;border-radius:20px;' +
            'font-size:0.9rem;pointer-events:none;z-index:10;transition:opacity 0.3s';
        const modal = document.getElementById('trailer-modal');
        if (modal) modal.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 1200);
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
            if (sel) setTimeout(() => sel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
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

        // Date row: Country \u00b7 Genre \u00b7 Date
        const dateEl = document.getElementById('lightbox-date');
        if (dateEl) {
            const parts = [];
            if (movie.country) parts.push(NRW.lightboxCountry(movie.country) || movie.country);
            if (movie.genres?.[0]) parts.push(movie.genres[0]);
            if (movie.digital_date) {
                const [y, m, d] = movie.digital_date.split('-');
                const dt = new Date(y, m - 1, d);
                let dateText = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                if (movie.filters?.is_virtual_screening && movie.virtual_screening_info?.available_end) {
                    const [ey, em, ed] = movie.virtual_screening_info.available_end.split('-');
                    if (em === m) {
                        dateText += '\u2013' + parseInt(ed, 10);
                    } else {
                        const endDt = new Date(ey, em - 1, ed);
                        dateText += '\u2013' + endDt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    }
                }
                parts.push(dateText);
            }
            dateEl.textContent = parts.join(' \u00b7 ');
        }

        // Staff Pick badge
        const staffPickBadge = document.getElementById('lightbox-staff-pick');
        if (staffPickBadge) {
            staffPickBadge.style.display = movie.filters?.is_staff_pick ? 'inline-block' : 'none';
        }

        // Reissue label pill
        const reissueEl = document.getElementById('lightbox-reissue-label');
        if (reissueEl) {
            const label = movie.reissue_label;
            if (label) {
                reissueEl.textContent = label.toUpperCase();
                reissueEl.style.display = 'inline-block';
            } else {
                reissueEl.style.display = 'none';
            }
        }

        // Screening name banner
        const screeningNameEl = document.getElementById('lightbox-screening-name');
        if (screeningNameEl) {
            if (movie.filters?.is_virtual_screening && movie.virtual_screening_info?.screening_name) {
                screeningNameEl.textContent = movie.virtual_screening_info.screening_name;
                screeningNameEl.style.display = 'block';
            } else {
                screeningNameEl.style.display = 'none';
            }
        }
    },

    _directorLink(name, wikiUrl) {
        if (!name) return 'Unknown Director';
        if (!wikiUrl) return name;
        return `<a href="${wikiUrl}" target="_blank" rel="noopener">${name}</a>`;
    },

    _linkBoldTitles(html) {
        const wikiMap = {};
        (this.movies || []).forEach(m => {
            if (m.links?.wikipedia) wikiMap[m.title.toLowerCase()] = m.links.wikipedia;
        });
        return html.replace(/<strong>([^<]+)<\/strong>/g, (match, title) => {
            const known = wikiMap[title.toLowerCase()];
            if (!known) return match;
            return `<strong><a href="${known}" target="_blank" rel="noopener">${title}</a></strong>`;
        });
    },

    _updateLightboxSynopsis(movie) {
        // Meta block — 3 lines
        const metaEl = document.getElementById('lightbox-meta');
        metaEl.textContent = '';

        // Line 1: Director
        if (movie.crew?.director) {
            const dirLabel = document.createElement('span');
            dirLabel.className = 'lightbox-crew-label';
            dirLabel.textContent = 'Dir: ';
            const dirWikiUrl = movie.links?.director_wiki;
            let dirName;
            if (dirWikiUrl) {
                dirName = document.createElement('a');
                dirName.className = 'lightbox-crew-name lightbox-crew-link';
                dirName.href = dirWikiUrl;
                dirName.target = '_blank';
                dirName.rel = 'noopener';
            } else {
                dirName = document.createElement('span');
                dirName.className = 'lightbox-crew-name';
            }
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
            const castWiki = movie.links?.cast_wiki || {};
            movie.crew.cast.slice(0, 3).forEach((name, i) => {
                if (i > 0) castName.appendChild(document.createTextNode(', '));
                const url = castWiki[name];
                if (url) {
                    const a = document.createElement('a');
                    a.href = url; a.target = '_blank'; a.rel = 'noopener';
                    a.className = 'lightbox-crew-link'; a.textContent = name;
                    castName.appendChild(a);
                } else {
                    castName.appendChild(document.createTextNode(name));
                }
            });
            metaEl.appendChild(castLabel);
            metaEl.appendChild(castName);
        }

        // Synopsis text (renders **bold**/*italic* markdown)
        const synopsisEl = document.getElementById('lightbox-synopsis');
        synopsisEl.innerHTML = NRW._linkBoldTitles(NRWConfig.renderMarkdown(movie.capsule || movie.synopsis || 'Synopsis coming soon.'));

        // Screening callout appended to synopsis
        if (movie.filters?.is_virtual_screening && movie.virtual_screening_info?.screening_name) {
            const festName = movie.virtual_screening_info.screening_name;
            const endDate = movie.virtual_screening_info?.available_end;
            const callout = document.createElement('span');
            callout.className = 'screening-callout';
            callout.textContent = endDate
                ? ` Virtual screening available as part of the ${festName}. Ends ${NRW.formatShortDate(endDate)}.`
                : ` Virtual screening available as part of the ${festName}.`;
            synopsisEl.appendChild(callout);
        }

        // Year • Runtime • Distributor — below synopsis
        const runtimeEl = document.getElementById('lightbox-runtime');
        if (runtimeEl) {
            const runtimeParts = [];
            if (movie.year) runtimeParts.push(movie.year);
            if (movie.runtime) runtimeParts.push(`${movie.runtime} min`);
            if (movie.distributor || movie.studio) runtimeParts.push(movie.distributor || movie.studio);
            if (runtimeParts.length) {
                runtimeEl.textContent = runtimeParts.join(' \u2022 ');
                runtimeEl.style.display = '';
            } else {
                runtimeEl.style.display = 'none';
            }
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
            container.appendChild(makeBadge(movie.links.wikipedia, 'wiki', '', 'assets/logos/wikipedia_PNG40.png'));
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

        // === ROW 1: TRAILER (the < > cycle arrows are appended to the overlay) ===
        const navRow = document.createElement('div');
        navRow.className = 'lb-nav-row';

        // < and > cycle buttons live on the .poster-lightbox OVERLAY, not inside
        // .lightbox-info-wrap \u2014 that panel's backdrop-filter creates a containing
        // block that traps position:fixed and pins the arrows over the capsule.
        // On the overlay (no transform/filter) they pin to the viewport edges as
        // intended. Clicks are handled by delegation on document.body; remove any
        // stale pair first since the overlay isn't rebuilt between opens.
        const overlay = document.getElementById('poster-lightbox');
        overlay.querySelectorAll('.lb-nav-prev, .lb-nav-next').forEach(n => n.remove());

        // < button
        const prevBtn = document.createElement('button');
        prevBtn.className = 'lb-nav-btn lb-nav-prev';
        prevBtn.textContent = '\u2039';
        prevBtn.setAttribute('aria-label', 'Previous movie');
        overlay.appendChild(prevBtn);

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
        overlay.appendChild(nextBtn);

        container.appendChild(navRow);

        // === STREAM ROW (own row, before VOD) — one button per free stream ===
        // Multiple free streams (e.g. Tubi + Fawesome) split the row into equal
        // widths, mirroring the VOD row, so the lightbox footprint stays stable.
        const lbStreamList = this.getStreamingList(watchLinks);
        if (lbStreamList.length) {
            const streamRowEl = document.createElement('div');
            streamRowEl.className = 'lb-stream-row';
            lbStreamList.forEach(({ service: streamSvc, link: streamLink }) => {
                if (!streamSvc || !streamLink) return;
                const resolved = this.resolveService(streamSvc);
                const cls = resolved?.class || '';
                const logo = resolved?.wideLogo || null;
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
            });
            if (streamRowEl.children.length) container.appendChild(streamRowEl);
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
                } else if (e.key === ' ') {
                    e.preventDefault();
                    const vid = document.getElementById('trailer-video');
                    if (vid) vid.paused ? vid.play() : vid.pause();
                } else if (e.key === 'j' || e.key === 'J') {
                    e.preventDefault();
                    const vid = document.getElementById('trailer-video');
                    if (vid) vid.currentTime = Math.max(0, vid.currentTime - 10);
                } else if (e.key === 'l' || e.key === 'L') {
                    e.preventDefault();
                    const vid = document.getElementById('trailer-video');
                    if (vid) {
                        const rates = [1, 2, 4];
                        const next = rates[(rates.indexOf(vid.playbackRate) + 1) % rates.length];
                        vid.playbackRate = next;
                        this._trailerSpeedToast(next);
                    }
                } else if (e.key === 'Tab') {
                    e.preventDefault();
                    const vid = document.getElementById('trailer-video');
                    if (vid) {
                        if (document.fullscreenElement) {
                            document.exitFullscreen();
                        } else {
                            vid.requestFullscreen();
                        }
                    }
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
        } else if (direction === 'up') {
            // Up from the top row hands off to the header toggles — restores the
            // pre-grid-nav ability to escape upward. Lands on the SLOP toggle;
            // Left/Right then walks the toggles/filters, Down drops back in.
            this.gridClearSelection();
            document.getElementById('slop-free-toggle')?.focus();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    },

    gridSelect(containerEl) {
        const prev = document.querySelector('#wall .movie-container.grid-selected');
        if (prev) prev.classList.remove('grid-selected');

        if (containerEl) {
            containerEl.classList.add('grid-selected');
            const expandBtn = containerEl.querySelector('.expand-btn[data-movie-id]');
            this.gridSelectedId = expandBtn ? expandBtn.dataset.movieId : null;
            // 'nearest' (with .movie-container scroll-margin-top) keeps the card clear
            // of the sticky header + date strip. 'center' parked rows under the strip.
            containerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
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

    // Header (toggles + filters + search) keyboard zone. Reached by pressing Up
    // from the top grid row; Down drops back into the wall. The toggles are <div>s,
    // so they're made focusable + Enter/Space-activatable here.
    setupHeaderKeyboardNav() {
        const toggleIds = ['preorder-toggle', 'fest-toggle', 'slop-free-toggle', 'highlights-toggle'];
        toggleIds.forEach(id => {
            const t = document.getElementById(id);
            if (t) { t.setAttribute('tabindex', '0'); t.setAttribute('role', 'button'); }
        });

        // Left/Right traversal order, left to right: toggles, then filters, then search.
        const controls = () => [
            ...toggleIds.map(id => document.getElementById(id)),
            ...Array.from(document.querySelectorAll('.filter-btn')),
            document.getElementById('search-input'),
        ].filter(Boolean);

        document.addEventListener('keydown', (e) => {
            if (!e.target.closest('header')) return;
            const lightbox = document.getElementById('poster-lightbox');
            if (lightbox && lightbox.classList.contains('active')) return;

            const isToggle = e.target.classList.contains('slop-toggle-wrap');
            const onSearch = e.target.id === 'search-input';

            // Enter/Space activates a focused toggle (filters are <button>, native handles those).
            if (isToggle && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                e.target.click();
                return;
            }

            // In the search field, only Down (enter grid) is special — leave typing alone.
            if (onSearch && e.key !== 'ArrowDown') return;

            const list = controls();
            const idx = list.indexOf(e.target);

            if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                e.preventDefault();
                const next = e.key === 'ArrowRight' ? Math.min(idx + 1, list.length - 1) : Math.max(idx - 1, 0);
                list[next]?.focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                document.getElementById('slop-free-toggle')?.focus();  // Up always parks on the SLOP toggle
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                e.target.blur();
                const { allCards } = this.buildGridMap();
                if (allCards.length > 0) {
                    this.gridNavActive = true;
                    this.gridAnchorX = null;
                    this.gridSelect(allCards[0]);
                }
            }
        });
    },

    setupGridKeyboardHandler() {
        document.addEventListener('keydown', (e) => {
            // Don't handle if lightbox or trailer modal is open
            const lightbox = document.getElementById('poster-lightbox');
            if (lightbox && lightbox.classList.contains('active')) return;
            const trailerModal = document.getElementById('trailer-modal');
            if (trailerModal && trailerModal.classList.contains('active')) return;

            const searchInput = document.getElementById('search-input');
            // Use e.target (not activeElement) — activeElement may have already moved by bubbling time
            const onSearch = e.target === searchInput;

            // Tab: nowhere → search → grid (filter buttons handle their own Tab)
            if (e.key === 'Tab' && !onSearch) {
                if (this.gridNavActive && this.gridSelectedId) {
                    if (e.shiftKey) {
                        // Shift+Tab: go to prev card, or back to search if at first card
                        const { allCards } = this.buildGridMap();
                        const currentEl = document.querySelector(`#wall .expand-btn[data-movie-id="${CSS.escape(this.gridSelectedId)}"]`)?.closest('.movie-container');
                        e.preventDefault();
                        if (currentEl && allCards.indexOf(currentEl) === 0) {
                            this.gridClearSelection();
                            searchInput.focus();
                        } else {
                            this.gridNavigate('left');
                        }
                    } else {
                        e.preventDefault();
                        this.gridNavigate('right');
                    }
                } else if (!e.target.closest('.filter-btn')) {
                    // Not in grid, not on a filter: focus search bar
                    e.preventDefault();
                    searchInput.focus();
                }
                return;
            }

            // Don't handle arrow/enter/escape if typing in search
            if (onSearch) return;

            // Header controls (toggles/filters) own their own arrow nav — see
            // setupHeaderKeyboardNav. Leaving them to the grid handler would
            // hijack the arrows and trap focus on a filter button.
            if (e.target.closest('header')) return;

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