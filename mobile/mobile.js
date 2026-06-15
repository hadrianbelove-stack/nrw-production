/**
 * NRW Mobile — 3-View Layout
 * View 0: Poster Grid (with date dividers)
 * View 1: Poster Close-up (swipe to navigate)
 * View 2: Bottom Sheet (details, providers, synopsis)
 */

const NRWMobile = {
    // Data
    allMovies: [],
    filteredMovies: [],
    staffPicks: [],

    // UI state
    activeFilters: new Set(),
    slopMode: 'free',
    hideFest: true,
    showPreorders: false,
    showHighlightsOnly: false,
    searchQuery: '',
    currentView: 0,
    currentMovieIndex: 0,
    gridEntries: [],
    displayedCount: 0,
    loadIncrement: 60,
    savedScrollTop: 0,

    // Shared config
    resolveService: NRWConfig.resolveService,
    resolveVODService: NRWConfig.resolveVODService,

    // Wide logos that need CSS invert on dark backgrounds
    INVERT_KEYS: new Set(['apple', 'mubi', 'criterion', 'docuramafilms', 'fandor']),

    // Service brand colors for Gallery Label Frame on grid cards
    STREAMING_FRAME_COLORS: {
        netflix: { color: '#e50914', textColor: '#fff' },
        hulu: { color: '#1ce783', textColor: '#000' },
        max: { color: '#002be7', textColor: '#fff' },
        apple: { color: '#1c1c1e', textColor: '#fff' },
        amazon: { color: '#00a8e0', textColor: '#000' },
        disney: { color: '#113ccf', textColor: '#fff' },
        peacock: { color: '#000000', textColor: '#fff' },
        paramount: { color: '#0064ff', textColor: '#fff' },
        mubi: { color: '#060606', textColor: '#fff' },
        criterion: { color: '#1a1a1a', textColor: '#fff' },
        amc: { color: '#1b6fe0', textColor: '#fff' },
        shudder: { color: '#18b558', textColor: '#fff' },
        tubi: { color: '#fa5100', textColor: '#fff' },
        plex: { color: '#e5a00d', textColor: '#000' },
        starz: { color: '#000000', textColor: '#fff' },
        mgmplus: { color: '#000000', textColor: '#fff' },
    },

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
            text: 'Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces.'
        },
        'restorations': {
            title: 'Reissues',
            text: 'Classic and catalog titles with new digital life. Films that have been restored, remastered, or newly reissued on streaming platforms.'
        },
        'documentary': {
            title: 'Documentary',
            text: 'Non-fiction filmmaking. Documentaries covering real stories, real people, and real events — now available to stream at home.'
        },
        'pre-orders': {
            title: 'Pre-Orders',
            text: 'Coming soon. These movies have confirmed digital release dates and are available to pre-order now.'
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

    // DOM references (populated in init)
    dom: {},

    // ===== INIT =====
    async init() {
        this.dom = {
            gridView: document.getElementById('grid-view'),
            posterView: document.getElementById('poster-view'),
            posterImg: document.getElementById('poster-img'),
            posterCounter: document.getElementById('poster-counter'),
            posterScores: document.getElementById('poster-scores'),
            bottomSheet: document.getElementById('bottom-sheet'),
            sheetContent: document.getElementById('sheet-content'),
            chevronLeft: document.getElementById('chevron-left'),
            chevronRight: document.getElementById('chevron-right'),
            viewDots: document.querySelectorAll('.view-dot'),
            siteHeader: document.getElementById('site-header'),
            filterDesc: document.getElementById('filter-desc'),
        };

        this.updateHeaderHeight();
        window.addEventListener('resize', () => this.updateHeaderHeight());

        try {
            const response = await fetch('../data.json?t=' + Date.now());
            const data = await response.json();

            this.staffPicks = (data.staff_picks || data.featured || []).map(id => String(id));

            this.allMovies = (data.movies || []).filter(m => {
                if (m.hidden) return false;
                if (m._enrichment_status === 'reverted') return false;
                return !!m.digital_date;
            });

            this.sortMovies();
            this.setupFilters();
            this.setupSearch();
            this.setupViewDots();
            this.setupPosterGestures();
            this.setupSheetGestures();
            this.setupKeyboard();

            this.applyFilter();
            this.buildGrid();
            this.setView(0);

        } catch (err) {
            console.error('Failed to load movies:', err);
            this.dom.gridView.innerHTML =
                '<div class="loading"><p>Failed to load movies</p></div>';
        }
    },

    updateHeaderHeight() {
        const h = this.dom.siteHeader.offsetHeight;
        document.documentElement.style.setProperty('--header-height', h + 'px');
        this.updateGridPadding();
    },

    // ===== SORTING =====
    sortMovies() {
        this.allMovies.sort((a, b) => {
            // Pre-orders always sort to the end
            if (a._is_preorder && !b._is_preorder) return 1;
            if (!a._is_preorder && b._is_preorder) return -1;
            if (a._is_preorder && b._is_preorder)
                return (a.digital_date || '').localeCompare(b.digital_date || '');

            // Fest (virtual screening) movies group at the top, under the FEST strip
            const aFest = !!a.filters?.is_virtual_screening;
            const bFest = !!b.filters?.is_virtual_screening;
            if (aFest && !bFest) return -1;
            if (!aFest && bFest) return 1;

            // Virtual screenings: sort by tier (active → upcoming → expired)
            const screeningTier = m => {
                if (!m.filters?.is_virtual_screening) return -1;
                const s = m.virtual_screening_info?.status;
                return s === 'active' ? 0 : s === 'expired' ? 2 : 1;
            };
            const ta = screeningTier(a), tb = screeningTier(b);
            if (ta >= 0 && tb >= 0 && ta !== tb) return ta - tb;

            const dateA = new Date(a.digital_date);
            const dateB = new Date(b.digital_date);
            if (dateB.getTime() !== dateA.getTime()) return dateB - dateA;

            // Same date: staff picks first
            const aStaff = a.filters?.is_staff_pick || this.staffPicks.includes(String(a.id));
            const bStaff = b.filters?.is_staff_pick || this.staffPicks.includes(String(b.id));
            if (aStaff && !bStaff) return -1;
            if (!aStaff && bStaff) return 1;
            return 0;
        });
    },

    // ===== FILTERS =====
    setupFilters() {
        const filtersEl = document.getElementById('filters');
        filtersEl.addEventListener('click', (e) => {
            const pill = e.target.closest('.filter-pill');
            if (!pill) return;

            const filter = pill.dataset.filter;

            if (this.activeFilters.has(filter)) {
                this.activeFilters.delete(filter);
                pill.classList.remove('active');
            } else {
                this.activeFilters.add(filter);
                pill.classList.add('active');
            }

            this.applyFilter();
            this.updateFilterDesc();
            this.buildGrid();
            this.setView(0);
            this.dom.gridView.scrollTop = 0;
        });

        // Slop toggle (3-state: free / all / only)
        const slopToggle = document.getElementById('slop-free-toggle');
        if (slopToggle) {
            const SLOP_STATES = ['free', 'all', 'only'];
            const SLOP_LABELS = { free: 'SLOP FREE', all: 'ALL', only: 'SLOP ONLY' };
            const updateSlopToggle = () => {
                slopToggle.dataset.state = this.slopMode;
                const label = document.getElementById('slop-state-label');
                if (label) label.textContent = SLOP_LABELS[this.slopMode];
            };
            updateSlopToggle();
            slopToggle.addEventListener('click', () => {
                const idx = SLOP_STATES.indexOf(this.slopMode);
                this.slopMode = SLOP_STATES[(idx + 1) % 3];
                updateSlopToggle();
                this.applyFilter();
                this.buildGrid();
                this.setView(0);
                this.dom.gridView.scrollTop = 0;
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
                this.applyFilter();
                this.updateFilterDesc();
                this.buildGrid();
                this.setView(0);
                this.dom.gridView.scrollTop = 0;
            });
        }

        // Fest (virtual screenings) toggle
        const festToggle = document.getElementById('fest-toggle');
        if (festToggle) {
            festToggle.classList.toggle('active', !this.hideFest);
            festToggle.addEventListener('click', () => {
                this.hideFest = !this.hideFest;
                festToggle.classList.toggle('active', !this.hideFest);
                if (!this.hideFest) this.setExclusiveView('fests');
                this.updateFilterDesc();
                this.applyFilter();
                this.buildGrid();
                this.setView(0);
                this.dom.gridView.scrollTop = 0;
            });
        }

        // Pre-order toggle
        const preorderToggle = document.getElementById('preorder-toggle');
        if (preorderToggle) {
            preorderToggle.classList.toggle('active', this.showPreorders);
            preorderToggle.addEventListener('click', () => {
                this.showPreorders = !this.showPreorders;
                preorderToggle.classList.toggle('active', this.showPreorders);
                if (this.showPreorders) this.setExclusiveView('preorders');
                this.updateFilterDesc();
                this.applyFilter();
                this.buildGrid();
                this.setView(0);
                this.dom.gridView.scrollTop = 0;
            });
        }
    },

    // View toggles (Selects / Fests / Pre-Orders) are mutually exclusive.
    // The caller turns its own toggle on; this clears the other two —
    // both the state flag and the button highlight.
    setExclusiveView(winner) {
        const others = {
            selects:   () => { this.showHighlightsOnly = false; document.getElementById('highlights-toggle')?.classList.remove('active'); },
            fests:     () => { this.hideFest = true;            document.getElementById('fest-toggle')?.classList.remove('active'); },
            preorders: () => { this.showPreorders = false;      document.getElementById('preorder-toggle')?.classList.remove('active'); },
        };
        for (const name in others) {
            if (name !== winner) others[name]();
        }
    },

    updateFilterDesc() {
        const desc = this.dom.filterDesc;
        if (!desc) return;

        // Selects description renders in the river (below its banner) — the
        // fixed bar is only for single category filters
        if (!this.showHighlightsOnly && this.activeFilters.size === 1) {
            const key = [...this.activeFilters][0];
            const info = this.FILTER_DESCRIPTIONS[key];
            if (info) {
                desc.innerHTML = '<div class="filter-desc-inner">' + this.esc(info.text) + '</div>';
                desc.classList.add('visible');
                // Adjust grid padding after transition
                setTimeout(() => this.updateGridPadding(), 320);
                return;
            }
        }

        desc.classList.remove('visible');
        setTimeout(() => this.updateGridPadding(), 320);
    },

    updateGridPadding() {
        if (!this.dom.gridView || !this.dom.siteHeader) return;
        const desc = this.dom.filterDesc;
        const descH = desc && desc.classList.contains('visible') ? desc.offsetHeight : 0;
        const headerH = this.dom.siteHeader.offsetHeight;
        this.dom.gridView.style.paddingTop = (headerH + descH) + 'px';
    },

    // ===== SEARCH =====
    setupSearch() {
        const searchInput = document.getElementById('search-input');
        const clearBtn = document.getElementById('search-clear');
        if (!searchInput) return;

        let debounceTimer;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                this.searchQuery = e.target.value.trim().toLowerCase();
                this.applyFilter();
                this.buildGrid();
                if (clearBtn) clearBtn.style.display = this.searchQuery ? 'block' : 'none';
            }, 200);
        });

        if (clearBtn) {
            clearBtn.style.display = 'none';
            clearBtn.addEventListener('click', () => {
                searchInput.value = '';
                this.searchQuery = '';
                this.applyFilter();
                this.buildGrid();
                clearBtn.style.display = 'none';
                searchInput.focus();
            });
        }

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                this.searchQuery = '';
                this.applyFilter();
                this.buildGrid();
                if (clearBtn) clearBtn.style.display = 'none';
                searchInput.blur();
            }
        });
    },

    // ===== FILTER APPLICATION =====
    applyFilter() {
        const filters = this.activeFilters;

        this.filteredMovies = this.allMovies.filter(movie => {
            // Toggles are view modes — an active search bypasses ALL of them
            if (!this.searchQuery) {
                // Pre-order mode is an exclusive view: show ONLY pre-orders, and they
                // bypass slop/category filters (an explicit "show me upcoming" request).
                if (this.showPreorders) return !!movie._is_preorder;

                // Slop mode filter
                const isSlop = movie.is_slop || movie._is_slop_guess;
                if (this.slopMode === 'free' && isSlop) return false;
                if (this.slopMode === 'only' && !isSlop) return false;

                // Highlights mode: only staff picks
                if (this.showHighlightsOnly &&
                    !(movie.filters?.is_staff_pick || movie.featured || this.staffPicks.includes(String(movie.id)))) return false;

                // Hide-fest mode: hide virtual screenings
                if (this.hideFest && movie.filters?.is_virtual_screening) return false;
            }

            // Pre-orders only appear when toggle is ON or search is active
            if (movie._is_preorder && !this.showPreorders && !this.searchQuery) return false;

            // Category filters (OR logic) — bypassed when search is active
            if (filters.size > 0 && !this.searchQuery) {
                let matchesAny = false;
                for (const filter of filters) {
                    switch (filter) {
                        case 'indie':
                            if (movie.filters?.is_indie) matchesAny = true;
                            break;
                        case 'foreign':
                            if (movie.filters?.is_foreign ||
                                (movie.original_language && movie.original_language !== 'en')) matchesAny = true;
                            break;
                        case 'restorations':
                            if (movie.filters?.is_restoration === true) matchesAny = true;
                            break;
                        case 'documentary':
                            if (movie.filters?.is_documentary === true) matchesAny = true;
                            break;
                        case 'horror':
                            if ((movie.genres || []).some(g => g.toLowerCase().includes('horror'))) matchesAny = true;
                            break;
                        case 'action':
                            if ((movie.genres || []).some(g => g.toLowerCase().includes('action'))) matchesAny = true;
                            break;
                        case 'comedy':
                            if ((movie.genres || []).some(g => g.toLowerCase().includes('comedy'))) matchesAny = true;
                            break;
                        case 'family':
                            if ((movie.genres || []).some(g => g.toLowerCase().includes('family'))) matchesAny = true;
                            break;
                        case 'thriller':
                            if ((movie.genres || []).some(g => g.toLowerCase().includes('thriller'))) matchesAny = true;
                            break;
                    }
                    if (matchesAny) break;
                }
                if (!matchesAny) return false;
            }

            // Search filter
            if (this.searchQuery) {
                const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
                const q = norm(this.searchQuery);
                const title = norm(movie.title || '');
                const director = norm(movie.crew?.director || movie.director || '');
                const synopsis = norm(movie.capsule || movie.synopsis || '');
                const genres = norm((movie.genres || []).join(' '));
                const country = norm(movie.country || '');
                const year = String(movie.year || '');
                const cast = norm((movie.crew?.cast || []).join(' '));

                return title.includes(q) || director.includes(q) ||
                       synopsis.includes(q) || genres.includes(q) ||
                       country.includes(q) || year.includes(q) || cast.includes(q);
            }

            return true;
        });
    },

    // ===== GRID (View 0) =====
    buildGrid() {
        this.savedScrollTop = 0;

        // Pre-compute grid entries (date strips + movie items)
        this.gridEntries = [];
        let lastDate = '';
        let preorderStarted = false;
        let festStarted = false;

        if (this.showHighlightsOnly && this.filteredMovies.length > 0) {
            this.gridEntries.push({ type: 'date', dateStr: 'highlights' });
            // Description lives in the river, below the banner — scrolls away naturally
            this.gridEntries.push({ type: 'desc', key: 'staff-picks' });
        }
        if (this.slopMode === 'only' && this.filteredMovies.length > 0) {
            this.gridEntries.push({ type: 'date', dateStr: 'slop' });
        }

        this.filteredMovies.forEach((movie, i) => {
            if (movie._is_preorder) {
                if (!preorderStarted) {
                    preorderStarted = true;
                    this.gridEntries.push({ type: 'date', dateStr: 'pre-order' });
                }
            } else if (movie.filters?.is_virtual_screening) {
                if (!festStarted) {
                    festStarted = true;
                    this.gridEntries.push({ type: 'date', dateStr: 'fest' });
                }
            } else if (!this.showHighlightsOnly) {
                // SELECTS is a single curated section (like FEST / PRE-ORDER) —
                // suppress per-date strips so it shows one "SELECTS · OUR PICKS"
                // header, not redundant date banners around it.
                const date = movie.digital_date.substring(0, 10);
                if (date !== lastDate) {
                    this.gridEntries.push({ type: 'date', dateStr: date });
                    lastDate = date;
                }
            }
            this.gridEntries.push({ type: 'movie', movie, index: i });
        });

        this.displayedCount = 0;
        this.dom.gridView.innerHTML = '';

        if (this.gridEntries.length === 0) {
            this.dom.gridView.innerHTML =
                '<div class="loading"><p>No movies found</p></div>';
            return;
        }

        const grid = document.createElement('div');
        grid.className = 'wall-grid';
        grid.id = 'wall-grid';
        this.dom.gridView.appendChild(grid);

        // Sentinel for lazy loading
        const sentinel = document.createElement('div');
        sentinel.id = 'grid-sentinel';
        sentinel.style.height = '1px';
        this.dom.gridView.appendChild(sentinel);

        this.loadMoreGrid();
        this.setupInfiniteScroll();
    },

    loadMoreGrid() {
        const grid = document.getElementById('wall-grid');
        if (!grid || this.displayedCount >= this.gridEntries.length) return;

        const end = Math.min(this.displayedCount + this.loadIncrement, this.gridEntries.length);
        for (let i = this.displayedCount; i < end; i++) {
            const entry = this.gridEntries[i];
            if (entry.type === 'date') {
                grid.appendChild(this.createDateRowHeader(entry.dateStr));
            } else if (entry.type === 'desc') {
                grid.appendChild(this.createDescRow(entry.key));
            } else {
                grid.appendChild(this.createGridItem(entry.movie, entry.index));
            }
        }
        this.displayedCount = end;
    },

    setupInfiniteScroll() {
        if (this._gridObserver) this._gridObserver.disconnect();
        const sentinel = document.getElementById('grid-sentinel');
        if (!sentinel) return;

        this._gridObserver = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && this.displayedCount < this.gridEntries.length) {
                this.loadMoreGrid();
            }
        }, { rootMargin: '300px', root: this.dom.gridView });
        this._gridObserver.observe(sentinel);
    },

    createDateRowHeader(dateStr) {
        const row = document.createElement('div');
        // Section banners (the view header) render ~2x the date dividers
        const SECTION_TYPES = ['pre-order', 'fest', 'highlights', 'slop'];
        row.className = 'date-row-header' + (SECTION_TYPES.includes(dateStr) ? ' section-banner' : '');

        // Neon sticky banner: colored day + white rest; color follows section / active filter
        let day, rest = '', color = '';
        if (dateStr === 'pre-order') {
            day = 'PRE-ORDER'; rest = 'COMING SOON'; color = '#7c3aed';
        } else if (dateStr === 'fest') {
            day = 'FEST'; rest = 'NOW SCREENING'; color = '#f59e0b';
        } else if (dateStr === 'highlights') {
            day = 'SELECTS'; rest = 'OUR PICKS'; color = '#dc143c';
        } else if (dateStr === 'slop') {
            day = 'SLOP'; rest = 'THE CONTENT RIVER'; color = '#ff9500';  // matches SLOP ONLY toggle orange
        } else {
            const d = new Date(dateStr + 'T12:00:00');
            day = d.toLocaleDateString('en', { weekday: 'short' });
            rest = d.toLocaleDateString('en', { month: 'short' }) + ' ' + d.getDate();
            const singleFilter = this.activeFilters.size === 1 ? [...this.activeFilters][0] : null;
            if (this.showHighlightsOnly) {
                color = '#dc143c';
            } else if (!this.hideFest) {
                color = '#f59e0b';
            } else if (this.slopMode === 'only') {
                color = '#ff9500';
            } else if (singleFilter && this.STRIP_COLORS[singleFilter]) {
                color = this.STRIP_COLORS[singleFilter];
            }
        }

        if (color) row.style.setProperty('--strip-c', color);
        row.innerHTML =
            '<span class="drh-day">' + day + '</span>' +
            (rest ? '<span class="drh-rest">' + rest + '</span>' : '');
        return row;
    },

    createDescRow(key) {
        const row = document.createElement('div');
        row.className = 'grid-desc-row';
        const info = this.FILTER_DESCRIPTIONS[key];
        row.textContent = info ? info.text : '';
        return row;
    },

    createGridItem(movie, index) {
        const isStaffPick = movie.filters?.is_staff_pick || this.staffPicks.includes(String(movie.id));
        const isScreening = movie.filters?.is_virtual_screening;
        const streamingSvc = this.getGridStreamingService(movie);

        const item = document.createElement('div');
        item.className = 'grid-item' + (isScreening ? ' screening-movie' : '');

        // Poster container
        const posterWrap = document.createElement('div');
        posterWrap.className = 'grid-item-poster';

        let badgeTarget; // where position:absolute badges attach

        if (streamingSvc) {
            // Gallery Label Frame: service color background + header strip
            posterWrap.style.cssText = 'background:' + streamingSvc.color + ';display:flex;flex-direction:column;';
            const header = document.createElement('div');
            header.style.cssText = 'flex-shrink:0;height:22px;display:flex;align-items:center;' +
                'justify-content:center;padding:0 3px;overflow:hidden;';
            header.innerHTML = '<span style="color:' + streamingSvc.textColor + ';font-size:0.55rem;' +
                'font-weight:800;letter-spacing:0.06em;white-space:nowrap;">' +
                this.esc(streamingSvc.name.toUpperCase()) + '</span>';
            posterWrap.appendChild(header);
            const imgWrap = document.createElement('div');
            imgWrap.style.cssText = 'flex:1;position:relative;overflow:hidden;';
            if (movie.poster) {
                const img = document.createElement('img');
                img.src = movie.poster;
                img.alt = movie.title || '';
                img.loading = 'lazy';
                img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
                img.onerror = function() { this.style.display = 'none'; };
                imgWrap.appendChild(img);
            }
            posterWrap.appendChild(imgWrap);
            badgeTarget = imgWrap;
        } else if (movie.poster) {
            const img = document.createElement('img');
            img.src = movie.poster;
            img.alt = movie.title || '';
            img.loading = 'lazy';
            img.onerror = function() { this.style.display = 'none'; };
            posterWrap.appendChild(img);
            badgeTarget = posterWrap;
        } else {
            const fallback = document.createElement('div');
            fallback.style.cssText = 'width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#1a1a2e;font-size:0.45rem;color:#888;text-align:center;padding:4px';
            fallback.textContent = movie.display_title || movie.title || '';
            posterWrap.appendChild(fallback);
            badgeTarget = posterWrap;
        }

        if (isScreening) {
            const banner = document.createElement('span');
            banner.className = 'screening-banner';
            banner.textContent = 'Virtual Screening';
            badgeTarget.appendChild(banner);
        }
        if (isStaffPick) {
            const badge = document.createElement('span');
            badge.className = 'staff-pick-badge';
            badge.textContent = 'Select';
            badgeTarget.appendChild(badge);
        }
        if (movie._is_preorder) {
            const badge = document.createElement('span');
            badge.className = 'preorder-badge';
            badge.textContent = 'Pre-Order';
            badgeTarget.appendChild(badge);
        }
        if (movie.filters?.is_restoration) {
            const badge = document.createElement('span');
            badge.style.cssText = 'position:absolute;top:4px;left:4px;background:#4a7c3f;color:#fff;' +
                'font-size:0.32rem;font-weight:700;letter-spacing:0.03em;padding:2px 4px;' +
                'border-radius:2px;text-transform:uppercase;z-index:3;';
            badge.textContent = (movie.reissue_label || 'RESTORED').toUpperCase();
            badgeTarget.appendChild(badge);
        }
        if (movie.rt_score || movie.imdb_rating) {
            const scoreRow = document.createElement('div');
            scoreRow.style.cssText = 'position:absolute;bottom:3px;left:3px;display:flex;gap:2px;z-index:3;';
            if (movie.rt_score) {
                const s = document.createElement('span');
                s.style.cssText = 'background:#b81c20;color:#fff;font-size:0.3rem;font-weight:700;' +
                    'padding:2px 3px;border-radius:2px;line-height:1;';
                s.textContent = movie.rt_score;
                scoreRow.appendChild(s);
            }
            if (movie.imdb_rating) {
                const s = document.createElement('span');
                s.style.cssText = 'background:#f5c518;color:#000;font-size:0.3rem;font-weight:700;' +
                    'padding:2px 3px;border-radius:2px;line-height:1;';
                s.textContent = parseFloat(movie.imdb_rating).toFixed(1);
                scoreRow.appendChild(s);
            }
            badgeTarget.appendChild(scoreRow);
        }

        item.appendChild(posterWrap);

        // Title + meta info
        const info = document.createElement('div');
        info.className = 'grid-item-info';

        const director = movie.crew?.director || movie.director || '';
        const dirWikiUrl = movie.links?.director_wiki;
        const genre = movie.genres?.[0] || '';
        const country = NRWConfig.abbreviateCountry(movie.country) || '';
        const metaParts = [];
        if (director) {
            metaParts.push(dirWikiUrl
                ? `<a href="${dirWikiUrl}" target="_blank" rel="noopener" class="mobile-dir-link">${this.esc(director)}</a>`
                : this.esc(director));
        }
        if (genre) metaParts.push(this.esc(genre));
        if (country) metaParts.push(this.esc(country));
        if (metaParts.length) {
            const meta = document.createElement('div');
            meta.className = 'grid-item-meta';
            meta.innerHTML = metaParts.join(' \u00b7 ');
            info.appendChild(meta);
        }

        item.appendChild(info);

        item.addEventListener('click', () => this.selectMovie(index));
        return item;
    },

    // ===== VIEW TRANSITIONS =====
    setView(view) {
        this.currentView = view;

        // Update dots
        this.dom.viewDots.forEach((d, i) => d.classList.toggle('active', i === view));

        // Grid view
        this.dom.gridView.classList.toggle('hidden', view !== 0);

        // Poster view (visible in view 1 and view 2)
        this.dom.posterView.classList.toggle('hidden', view !== 1 && view !== 2);

        // Bottom sheet
        const sheet = this.dom.bottomSheet;
        sheet.style.transform = '';
        sheet.style.transition = '';
        if (view === 2) {
            sheet.classList.add('visible');
        } else {
            sheet.classList.remove('visible');
        }

        // Chevrons
        const showChevrons = view === 1 || view === 2;
        this.dom.chevronLeft.classList.toggle('visible', showChevrons);
        this.dom.chevronRight.classList.toggle('visible', showChevrons);

        // Body scroll
        document.body.style.overflow = view === 0 ? '' : 'hidden';

        // Restore grid scroll position when returning to grid
        if (view === 0 && this.savedScrollTop > 0) {
            requestAnimationFrame(() => {
                this.dom.gridView.scrollTop = this.savedScrollTop;
            });
        }
    },

    selectMovie(index) {
        this.savedScrollTop = this.dom.gridView.scrollTop;
        this.currentMovieIndex = index;
        const movie = this.filteredMovies[index];
        if (!movie) return;
        this.updatePosterView(movie);
        this.updateSheetContent(movie);
        this.setView(1);
    },

    navigateMovie(dir) {
        const newIndex = this.currentMovieIndex + dir;
        if (newIndex < 0 || newIndex >= this.filteredMovies.length) return;

        // Flash chevron
        const chev = dir < 0 ? this.dom.chevronLeft : this.dom.chevronRight;
        chev.classList.add('flash');
        setTimeout(() => chev.classList.remove('flash'), 200);

        this.currentMovieIndex = newIndex;
        const slideDir = dir > 0 ? 'left' : 'right';
        this.updatePosterView(this.filteredMovies[newIndex], slideDir);
        if (this.currentView === 2) {
            this.updateSheetContent(this.filteredMovies[newIndex], slideDir);
        }
    },

    // ===== POSTER VIEW (View 1) =====
    updatePosterView(movie, direction) {
        const container = document.getElementById('poster-full');

        if (direction) {
            const cls = direction === 'left' ? 'slide-left-enter' : 'slide-right-enter';
            container.classList.add(cls);
            setTimeout(() => container.classList.remove(cls), 250);
        }

        this.dom.posterImg.src = movie.poster || '';
        this.dom.posterImg.alt = this.esc(movie.title || '');

        // Counter
        this.dom.posterCounter.textContent =
            (this.currentMovieIndex + 1) + ' / ' + this.filteredMovies.length;

        // Score badges on poster (RT only)
        let scores = '';
        if (movie.rt_score && movie.links?.rt) {
            scores += '<a href="' + movie.links.rt + '" target="_blank" rel="noopener" class="score-badge rt">' +
                '<img class="score-logo" src="../assets/logos/rt.png" alt="RT"> ' + movie.rt_score + '</a>';
        }
        this.dom.posterScores.innerHTML = scores;

        // Info lines below poster
        const dirName = movie.crew?.director || movie.director || '';
        const genre = movie.genres?.[0] || '';
        const country = NRWConfig.abbreviateCountry(movie.country) || movie.country || '';
        const metaEl = document.getElementById('poster-meta');
        if (metaEl) {
            const line1 = dirName
                ? '<div class="poster-meta-line poster-meta-dir"><span class="poster-meta-label">D:</span> ' + this.esc(dirName) + '</div>'
                : '';
            const line2Parts = [genre, country].filter(Boolean);
            const line2 = line2Parts.length
                ? '<div class="poster-meta-line poster-meta-sub">' + line2Parts.map(p => this.esc(p)).join(' · ') + '</div>'
                : '';
            metaEl.innerHTML = line1 + line2;
        }
    },

    // ===== BOTTOM SHEET (View 2) =====
    updateSheetContent(movie, direction) {
        const content = this.dom.sheetContent;

        if (direction) {
            const cls = direction === 'left' ? 'slide-left-enter' : 'slide-right-enter';
            content.classList.add(cls);
            setTimeout(() => content.classList.remove(cls), 250);
        }

        const isStaffPick = movie.filters?.is_staff_pick || this.staffPicks.includes(String(movie.id));
        const isScreening = movie.filters?.is_virtual_screening;
        const screeningInfo = movie.virtual_screening_info || {};

        // Line 1: Director (label teal, name white)
        const dirName = movie.crew?.director || movie.director || '';
        const dirWikiUrl = movie.links?.director_wiki;
        const dirLine = dirName
            ? '<span class="crew-label">D:</span> ' + (dirWikiUrl
                ? '<a href="' + dirWikiUrl + '" target="_blank" rel="noopener" class="crew-link">' + this.esc(dirName) + '</a>'
                : '<span class="crew-name">' + this.esc(dirName) + '</span>')
            : '';

        // Line 2: Cast (label teal, name white)
        const cast = movie.crew?.cast;
        let castLine = '';
        if (cast?.length) {
            const castWiki = movie.links?.cast_wiki || {};
            const castParts = cast.slice(0, 2).map(name => {
                const url = castWiki[name];
                return url
                    ? '<a href="' + url + '" target="_blank" rel="noopener" class="crew-link">' + this.esc(name) + '</a>'
                    : this.esc(name);
            });
            castLine = '<span class="crew-label">Cast:</span> <span class="crew-name">' + castParts.join(', ') + '</span>';
        }

        // Line 3 (gray): Country • Year • Runtime • Studio
        const detailParts = [];
        if (movie.country) detailParts.push(this.esc(NRWConfig.abbreviateCountry(movie.country) || movie.country));
        if (movie.year) detailParts.push(this.esc(movie.year));
        if (movie.runtime) detailParts.push(this.esc(this.formatRuntime(movie.runtime)));
        if (movie.studio) detailParts.push(this.esc(movie.studio));

        // Inline scores
        let scoresHtml = '';
        const hasScores = movie.rt_score || movie.imdb_rating ||
            (movie.metacritic_score && movie.metacritic_score !== '0');
        if (hasScores) {
            scoresHtml += '<div class="sheet-scores">';
            if (movie.rt_score) {
                scoresHtml += '<div class="sheet-score">' +
                    '<img class="sheet-score-logo" src="../assets/logos/rt.png" alt="RT">' +
                    '<span class="sheet-score-value rt">' + movie.rt_score + '</span></div>';
            }
            if (movie.imdb_rating) {
                scoresHtml += '<div class="sheet-score">' +
                    '<img class="sheet-score-logo" src="../assets/logos/imdb.png" alt="IMDb">' +
                    '<span class="sheet-score-value imdb">' + movie.imdb_rating + '</span></div>';
            }
            if (movie.metacritic_score && movie.metacritic_score !== '0') {
                scoresHtml += '<div class="sheet-score">' +
                    '<img class="sheet-score-logo mc-logo" src="../assets/logos/metacritic.png" alt="MC">' +
                    '<span class="sheet-score-value meta">' + movie.metacritic_score + '</span></div>';
            }
            scoresHtml += '</div>';
        }

        // Virtual screening banner
        let screeningBanner = '';
        if (isScreening && screeningInfo.screening_name) {
            screeningBanner = '<div class="sheet-screening-banner">' +
                this.esc(screeningInfo.screening_name) + '</div>';
        }

        // Build HTML
        let html = screeningBanner;

        // Header row: poster thumb + text
        html += '<div class="sheet-header-row">' +
            '<img class="sheet-thumb" src="' + this.esc(movie.poster || '') + '" alt="' +
            this.esc(movie.title || '') + '" onerror="this.style.display=\'none\'">' +
            '<div class="sheet-header-text">' +
            '<div class="sheet-title">' + this.esc(movie.display_title || movie.title || 'Untitled') +
            (isStaffPick ? ' <span style="color:var(--crimson);font-size:0.7rem">\u2605 SELECT</span>' : '') +
            '</div>' +
            (dirLine ? '<div class="sheet-crew">' + dirLine + '</div>' : '') +
            (castLine ? '<div class="sheet-crew">' + castLine + '</div>' : '') +
            (detailParts.length ? '<div class="sheet-meta"><span>' + detailParts.join(' \u00b7 ') + '</span></div>' : '') +
            (movie.box_office ? '<div class="sheet-meta" style="margin-top:2px"><span style="color:var(--text-muted);font-size:0.72rem">Box office: ' + this.esc(movie.box_office) + '</span></div>' : '') +
            scoresHtml +
            '</div></div>';

        // Trailer button
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        if (trailerUrl) {
            const isMP4 = (() => {
                try { return new URL(trailerUrl).pathname.endsWith('.mp4'); }
                catch { return trailerUrl.endsWith('.mp4'); }
            })();
            if (isMP4) {
                html += '<button class="trailer-btn" onclick="NRWMobile.showTrailer(\'' +
                    movie.id + '\')">\u25B6 Watch Trailer</button>';
            } else {
                html += '<a href="' + trailerUrl + '" target="_blank" rel="noopener" ' +
                    'class="trailer-btn">\u25B6 Watch Trailer</a>';
            }
        }

        // Virtual screening ticket + callout
        if (isScreening) {
            const vodEntries = this.getVODEntries(movie);
            const screeningVod = vodEntries.find(v => {
                const resolved = this.resolveVODService(v.service, v.link);
                return resolved?.key === 'screening';
            });
            if (screeningVod) {
                html += '<a href="' + screeningVod.link + '" target="_blank" rel="noopener" ' +
                    'class="sheet-screening-ticket">\uD83C\uDF9F Buy Ticket</a>';
            }
            let callout = 'Virtual screening via ' + this.esc(screeningInfo.screening_name || 'festival');
            if (screeningInfo.available_end) {
                const [y, m, d] = screeningInfo.available_end.split('-');
                const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                callout += '. Ends ' + months[parseInt(m, 10) - 1] + ' ' + parseInt(d, 10);
            }
            html += '<div class="sheet-screening-callout">' + callout + '</div>';
        }

        // Providers
        const streaming = this.getStreamingProvider(movie);
        const vodList = this.getVODList(movie);

        if (streaming || vodList.length > 0) {
            // Filter out screening VODs (already shown as ticket button above)
            const rentVod = isScreening
                ? vodList.filter(v => v.resolvedKey !== 'screening')
                : vodList;
            if (rentVod.length > 0) {
                html += '<div class="sheet-section-label">Rent/Buy:</div>' +
                    '<div class="sheet-providers">' +
                    rentVod.map(v => this.renderVODPriceCard(v)).join('') + '</div>';
            }
            if (streaming) {
                html += '<div class="sheet-section-label">Stream:</div>' +
                    '<div class="sheet-providers">' + this.renderProviderBadge(streaming) + '</div>';
            }
        } else if (!isScreening) {
            // Pre-order links
            const preOrderLinks = Array.isArray(movie.pre_order_links) ? movie.pre_order_links : [];
            if (preOrderLinks.length > 0) {
                html += '<div class="sheet-section-label">Pre-Order</div>' +
                    '<div class="sheet-providers">';
                preOrderLinks.forEach(pl => {
                    const resolved = this.resolveVODService(pl.service, pl.link);
                    if (resolved && pl.link) {
                        html += this.renderProviderBadge({
                            name: 'Pre-Order',
                            wideLogo: resolved.wideLogo,
                            serviceKey: resolved.key,
                            link: pl.link,
                            resolvedKey: resolved.key
                        });
                    }
                });
                html += '</div>';
                if (movie.digital_date) {
                    html += '<div style="color:var(--text-muted);font-size:0.7rem;margin-top:4px">' +
                        'Available ' + this.formatShortDate(movie.digital_date) + '</div>';
                }
            } else {
                html += '<div class="sheet-section-label">Availability</div>' +
                    '<div class="sheet-synopsis" style="font-style:italic">Coming soon</div>';
            }
        }

        // Pull quotes
        if (movie.pull_quotes?.length) {
            html += '<div class="sheet-section-label">Critics</div>';
            movie.pull_quotes.forEach(q => {
                const badgeClass = q.source === 'letterboxd' ? 'pq-badge-lb' : 'pq-badge-rt';
                const badgeText = q.source === 'letterboxd' ? 'LB' : 'RT';
                const attribution = [q.critic, q.outlet].filter(Boolean).join(', ');
                const quoteInner = '<q class="sheet-pq-text">' + this.esc(q.text || '') + '</q>';
                const quoteEl = q.review_url
                    ? '<a href="' + this.esc(q.review_url) + '" target="_blank" rel="noopener" class="sheet-pq-link">' + quoteInner + '</a>'
                    : quoteInner;
                html += '<div class="sheet-pq">' +
                    '<span class="sheet-pq-badge ' + badgeClass + '">' + badgeText + '</span>' +
                    quoteEl +
                    (attribution ? '<cite class="sheet-pq-cite">' + this.esc(attribution) + '</cite>' : '') +
                    '</div>';
            });
        }

        // Synopsis (renders **bold**/*italic* markdown, bold film titles hyperlinked)
        html += '<div class="sheet-section-label">Synopsis</div>' +
            '<div class="sheet-synopsis">' + this._linkBoldTitles(NRWConfig.renderMarkdown(movie.capsule || movie.synopsis || 'No synopsis available.')) + '</div>';

        html += '<div style="height:50px"></div>';

        content.innerHTML = html;
        content.scrollTop = 0;
    },

    _linkBoldTitles(html) {
        const wikiMap = {};
        (this.allMovies || []).forEach(m => {
            if (m.links?.wikipedia) wikiMap[m.title.toLowerCase()] = m.links.wikipedia;
        });
        return html.replace(/<strong>([^<]+)<\/strong>/g, (match, title) => {
            const known = wikiMap[title.toLowerCase()];
            if (!known) return match;
            return '<strong><a href="' + known + '" target="_blank" rel="noopener">' + title + '</a></strong>';
        });
    },

    // ===== PROVIDER HELPERS =====
    getVODEntries(movie) {
        const wl = movie.watch_links || {};
        const vodArr = Array.isArray(wl.vod) ? wl.vod
            : (wl.vod?.service ? [wl.vod] : []);
        return vodArr.filter(v => v.service);
    },

    getStreamingProvider(movie) {
        const wl = movie.watch_links || {};
        const providers = movie.providers || {};

        const EXCLUDED_STREAMING = ['spectrum on demand'];
        const isExcluded = s => s && EXCLUDED_STREAMING.includes(s.toLowerCase());

        // watch_links.streaming can be array or single object
        let service = null, link = null;
        const streamingWl = wl.streaming;
        if (Array.isArray(streamingWl) && streamingWl.length > 0) {
            const pick = streamingWl.find(s => !isExcluded(s.service));
            if (pick) { service = pick.service; link = pick.link; }
        } else if (streamingWl?.service && !isExcluded(streamingWl.service)) {
            service = streamingWl.service;
            link = streamingWl.link;
        }

        if (!service && providers.streaming?.length > 0) {
            const screeningNames = NRWConfig.VOD_SERVICE_MAP.screening.matches;
            const realStreamers = providers.streaming.filter(p =>
                !p.includes('with Ads') &&
                !screeningNames.some(s => p.toLowerCase().includes(s)) &&
                !isExcluded(p)
            );
            service = realStreamers[0] || null;
        }

        if (!service) return null;

        const resolved = this.resolveService(service);
        return {
            name: resolved?.name || NRWConfig.cleanServiceName(service),
            wideLogo: resolved?.wideLogo,
            serviceKey: resolved?.class,
            link: link || null,
            resolvedKey: resolved?.class
        };
    },

    getGridStreamingService(movie) {
        const wl = movie.watch_links || {};
        const streamingWl = wl.streaming;
        let service = null;
        if (Array.isArray(streamingWl) && streamingWl.length > 0) {
            service = streamingWl[0].service;
        } else if (streamingWl?.service) {
            service = streamingWl.service;
        }
        if (!service) return null;
        const resolved = this.resolveService(service);
        const key = resolved?.class;
        const frame = key && this.STREAMING_FRAME_COLORS[key];
        if (!frame) return null;
        return { key, name: resolved?.name || service, ...frame };
    },

    getVODList(movie) {
        const vodEntries = this.getVODEntries(movie);
        const results = [];

        vodEntries.forEach(v => {
            if (!v.link) return;
            const resolved = this.resolveVODService(v.service, v.link);
            if (!resolved) return;
            results.push({
                name: resolved.label || v.service,
                wideLogo: resolved.wideLogo,
                serviceKey: resolved.key,
                link: v.link,
                resolvedKey: resolved.key,
                isFallback: !!resolved.fallback,
                rentPrice: v.rent_price || null,
                buyPrice: v.buy_price || null
            });
        });

        // Hide fallback services (e.g. Plex) when non-fallback exist
        const hasNonFallback = results.some(r => !r.isFallback);
        return hasNonFallback ? results.filter(r => !r.isFallback) : results;
    },

    renderProviderBadge(provider) {
        // Screening → gold ticket button
        if (provider.resolvedKey === 'screening') {
            return '<a href="' + provider.link + '" target="_blank" rel="noopener" ' +
                'class="provider-pill-text" style="color:#FFD700;border:2px solid #FFD700;' +
                'font-weight:700;text-decoration:none">\uD83C\uDF9F BUY TICKET</a>';
        }

        // Wide logo badge
        if (provider.wideLogo) {
            const invertClass = this.INVERT_KEYS.has(provider.serviceKey) ? ' invert' : '';
            const src = '../assets/logos/' + provider.wideLogo;
            const img = '<img class="provider-pill' + invertClass + '" src="' + src +
                '" alt="' + this.esc(provider.name) + '">';
            if (provider.link) {
                return '<a href="' + provider.link + '" target="_blank" rel="noopener" ' +
                    'style="display:inline-block">' + img + '</a>';
            }
            return img;
        }

        // Text fallback
        const tag = provider.link ? 'a' : 'span';
        const linkAttrs = provider.link
            ? ' href="' + provider.link + '" target="_blank" rel="noopener" style="text-decoration:none"'
            : '';
        return '<' + tag + ' class="provider-pill-text"' + linkAttrs + '>' +
            this.esc(provider.name) + '</' + tag + '>';
    },

    renderVODPriceCard(provider) {
        if (!provider.rentPrice && !provider.buyPrice) return this.renderProviderBadge(provider);
        // V2: logo left, prices stacked right
        const svcKey = provider.serviceKey || '';
        const invertClass = this.INVERT_KEYS.has(svcKey) ? ' invert' : '';
        let logoHtml;
        if (provider.wideLogo) {
            const src = '../assets/logos/' + provider.wideLogo;
            logoHtml = '<img class="vcard-logo-img' + invertClass + '" src="' + src +
                '" alt="' + this.esc(provider.name) + '">';
        } else {
            logoHtml = '<span class="vcard-logo-text">' + this.esc(provider.name) + '</span>';
        }
        let pricesHtml = '';
        if (provider.rentPrice) {
            pricesHtml += '<a href="' + provider.link + '" target="_blank" rel="noopener" ' +
                'class="vcard-price-m rent">Rent ' + this.esc(provider.rentPrice) + '</a>';
        }
        if (provider.buyPrice) {
            pricesHtml += '<a href="' + provider.link + '" target="_blank" rel="noopener" ' +
                'class="vcard-price-m buy">Buy ' + this.esc(provider.buyPrice) + '</a>';
        }
        return '<div class="vcard-m ' + this.esc(svcKey) + '">' +
            '<a href="' + provider.link + '" target="_blank" rel="noopener" class="vcard-logo-m">' + logoHtml + '</a>' +
            '<div class="vcard-prices-m">' + pricesHtml + '</div>' +
            '</div>';
    },

    // ===== GESTURE HANDLERS =====

    setupViewDots() {
        this.dom.viewDots.forEach(dot => {
            dot.addEventListener('click', () => {
                const v = parseInt(dot.dataset.view);
                if (v === 0) {
                    this.setView(0);
                } else if (v === 1) {
                    if (this.currentView === 0 && this.filteredMovies.length > 0) {
                        this.selectMovie(0);
                    } else {
                        this.setView(1);
                    }
                } else if (v === 2) {
                    if (this.currentView === 0 && this.filteredMovies.length > 0) {
                        this.selectMovie(0);
                    }
                    this.setView(2);
                }
            });
        });
    },

    setupPosterGestures() {
        let touchStartX = 0, touchStartY = 0, touchStartTime = 0;

        this.dom.posterView.addEventListener('touchstart', (e) => {
            if (this.currentView !== 1) return;
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = Date.now();
        }, { passive: true });

        this.dom.posterView.addEventListener('touchend', (e) => {
            if (this.currentView !== 1) return;
            const dx = e.changedTouches[0].clientX - touchStartX;
            const dy = e.changedTouches[0].clientY - touchStartY;
            const dt = Date.now() - touchStartTime;
            const absDx = Math.abs(dx);
            const absDy = Math.abs(dy);

            // Tap → open detail sheet
            if (absDx < 15 && absDy < 15 && dt < 300) {
                this.setView(2);
                return;
            }
            if (dt > 500) return;

            // Horizontal swipe → navigate
            if (absDx > absDy && absDx > 50) {
                this.navigateMovie(dx < 0 ? 1 : -1);
            }
            // Swipe down → back to grid
            else if (absDy > absDx && absDy > 50 && dy > 0) {
                this.setView(0);
            }
            // Swipe up → open sheet
            else if (absDy > absDx && absDy > 50 && dy < 0) {
                this.setView(2);
            }
        });

        // Mouse (desktop testing)
        let mouseDown = false, mouseStartX = 0, mouseStartY = 0;
        this.dom.posterView.addEventListener('mousedown', (e) => {
            if (this.currentView !== 1) return;
            mouseDown = true;
            mouseStartX = e.clientX;
            mouseStartY = e.clientY;
        });
        this.dom.posterView.addEventListener('mouseup', (e) => {
            if (!mouseDown || this.currentView !== 1) return;
            mouseDown = false;
            const dx = e.clientX - mouseStartX;
            const dy = e.clientY - mouseStartY;
            if (Math.abs(dx) < 10 && Math.abs(dy) < 10) { this.setView(2); return; }
            if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 40) {
                this.navigateMovie(dx < 0 ? 1 : -1);
            } else if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 40) {
                if (dy > 0) this.setView(0);
                else this.setView(2);
            }
        });
    },

    setupSheetGestures() {
        const sheet = this.dom.bottomSheet;
        const content = this.dom.sheetContent;
        const handle = sheet.querySelector('.sheet-handle');

        // Handle drag to dismiss
        let dragStartY = 0, isDragging = false;

        handle.addEventListener('touchstart', (e) => {
            e.preventDefault();
            isDragging = true;
            dragStartY = e.touches[0].clientY;
            sheet.style.transition = 'none';
        }, { passive: false });

        document.addEventListener('touchmove', (e) => {
            if (!isDragging) return;
            const dy = e.touches[0].clientY - dragStartY;
            if (dy > 0) {
                sheet.style.transform = 'translateY(' + dy + 'px)';
            }
        }, { passive: true });

        document.addEventListener('touchend', (e) => {
            if (!isDragging) return;
            isDragging = false;
            const dy = e.changedTouches[0].clientY - dragStartY;

            sheet.style.transition = '';
            sheet.style.transform = '';
            if (Math.abs(dy) < 10) {
                // Tap on handle → back to grid
                this.setView(0);
            } else if (dy > 100) {
                // Drag dismiss → back to poster
                this.setView(1);
            }
            // else snap back (no action)
        });

        // Content overscroll-to-dismiss
        let contentStartX = 0, contentStartY = 0, contentStartTime = 0;
        let isOverscrolling = false, wasAtTop = false;

        content.addEventListener('touchstart', (e) => {
            contentStartX = e.touches[0].clientX;
            contentStartY = e.touches[0].clientY;
            contentStartTime = Date.now();
            wasAtTop = content.scrollTop <= 1;
            isOverscrolling = false;
        }, { passive: true });

        content.addEventListener('touchmove', (e) => {
            const dy = e.touches[0].clientY - contentStartY;
            const dx = e.touches[0].clientX - contentStartX;

            if (wasAtTop && dy > 10 && Math.abs(dy) > Math.abs(dx) && content.scrollTop <= 1) {
                if (!isOverscrolling) {
                    isOverscrolling = true;
                    sheet.style.transition = 'none';
                    content.style.overflow = 'hidden';
                }
            }

            if (isOverscrolling) {
                e.preventDefault();
                sheet.style.transform = 'translateY(' + (dy * 0.6) + 'px)';
            }
        }, { passive: false });

        content.addEventListener('touchend', (e) => {
            content.style.overflow = '';

            const dx = e.changedTouches[0].clientX - contentStartX;
            const dy = e.changedTouches[0].clientY - contentStartY;
            const dt = Date.now() - contentStartTime;

            if (isOverscrolling) {
                isOverscrolling = false;
                sheet.style.transition = '';
                const velocity = dy / Math.max(dt, 1);

                if (dy > 80 || velocity > 0.6) {
                    sheet.style.transform = '';
                    this.setView(1);
                } else {
                    sheet.style.transform = '';
                }
                return;
            }

            // Horizontal swipe in sheet → navigate movies
            if (dt < 600 && Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
                this.navigateMovie(dx < 0 ? 1 : -1);
                return;
            }

            // Tap on empty content area → back to grid
            if (dt < 300 && Math.abs(dx) < 15 && Math.abs(dy) < 15 && !e.target.closest('a, button')) {
                this.setView(0);
            }
        });
    },

    setupKeyboard() {
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;

            if (e.key === 'ArrowLeft') this.navigateMovie(-1);
            if (e.key === 'ArrowRight') this.navigateMovie(1);
            if (e.key === 'Escape') {
                if (this.currentView === 2) this.setView(1);
                else if (this.currentView === 1) this.setView(0);
            }
            if (e.key === 'Enter' || e.key === ' ') {
                if (e.target.tagName === 'BUTTON') return;
                e.preventDefault();
                if (this.currentView === 0 && this.filteredMovies.length > 0) this.selectMovie(0);
                else if (this.currentView === 1) this.setView(2);
            }
        });
    },

    // ===== TRAILER =====
    showTrailer(movieId) {
        const movie = this.filteredMovies.find(m => String(m.id) === String(movieId));
        if (!movie) return;

        const url = movie.links?.trailer_hosted || movie.links?.trailer;
        if (!url) return;

        const existing = document.getElementById('trailer-overlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'trailer-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.95);' +
            'display:flex;align-items:center;justify-content:center;flex-direction:column';

        const title = this.esc(movie.display_title || movie.title || '');
        const subsUrl = movie.links?.trailer_hosted_subs;
        const trackEl = subsUrl
            ? '<track kind="subtitles" src="' + this.esc(subsUrl) + '" srclang="en" label="English" default>'
            : '';
        overlay.innerHTML =
            '<button style="position:absolute;top:12px;right:16px;background:none;border:none;' +
            'color:white;font-size:2rem;cursor:pointer;z-index:10">&times;</button>' +
            '<video controls autoplay playsinline style="max-width:95%;max-height:70vh;border-radius:8px">' +
            trackEl +
            '<source src="' + this.esc(url) + '" type="video/mp4"></video>' +
            '<div style="color:#888;font-size:0.8rem;margin-top:10px">' + title + '</div>';

        document.body.appendChild(overlay);

        const close = () => overlay.remove();
        overlay.querySelector('button').addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        document.addEventListener('keydown', function onKey(e) {
            if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); }
        });

        // Double-tap left/right on video to seek ±10 seconds
        const video = overlay.querySelector('video');
        if (video) {
            // Auto-advance: when this trailer ends, roll to the next movie's hosted
            // trailer (continuous reel). Only MP4s play in this overlay.
            video.addEventListener('ended', () => {
                const isMp4 = (m) => {
                    const u = m.links?.trailer_hosted;
                    if (!u) return false;
                    try { return new URL(u).pathname.endsWith('.mp4'); }
                    catch { return u.endsWith('.mp4'); }
                };
                const reel = this.filteredMovies.filter(isMp4);
                if (reel.length < 2) return;
                const cur = reel.findIndex(m => String(m.id) === String(movie.id));
                const next = reel[(cur + 1) % reel.length];
                if (next && String(next.id) !== String(movie.id)) this.showTrailer(next.id);
            });

            let lastTap = 0, lastSide = null;
            video.addEventListener('touchend', (e) => {
                e.stopPropagation();
                const now = Date.now();
                const x = e.changedTouches[0].clientX;
                const rect = video.getBoundingClientRect();
                const side = x < rect.left + rect.width / 2 ? 'left' : 'right';
                if (now - lastTap < 300 && side === lastSide) {
                    const delta = side === 'left' ? -10 : 10;
                    video.currentTime = Math.max(0, Math.min(video.duration || 0, video.currentTime + delta));
                    this._mobileSeekFlash(overlay, side, delta);
                    lastTap = 0;
                } else {
                    lastTap = now;
                    lastSide = side;
                }
            });
        }
    },

    _mobileSeekFlash(overlay, side, delta) {
        const existing = overlay.querySelector('.seek-flash');
        if (existing) existing.remove();
        const flash = document.createElement('div');
        flash.className = 'seek-flash';
        flash.textContent = delta < 0 ? '« 10s' : '10s »';
        flash.style.cssText = 'position:absolute;top:50%;transform:translateY(-50%);' +
            (side === 'left' ? 'left:12%' : 'right:12%') + ';' +
            'color:#fff;font-size:1.1rem;font-weight:600;pointer-events:none;' +
            'background:rgba(0,0,0,0.5);padding:8px 14px;border-radius:20px;' +
            'animation:seekFadeOut 0.6s forwards';
        overlay.appendChild(flash);
        setTimeout(() => flash.remove(), 600);
    },

    // ===== HELPERS =====
    esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = String(str);
        return d.innerHTML;
    },

    formatRuntime(min) {
        if (!min) return null;
        const h = Math.floor(min / 60);
        const m = min % 60;
        return h > 0 ? h + 'h ' + m + 'm' : m + 'm';
    },

    formatShortDate(dateStr) {
        const [y, m, d] = dateStr.split('-');
        const dt = new Date(y, m - 1, d);
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    },
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => NRWMobile.init());
