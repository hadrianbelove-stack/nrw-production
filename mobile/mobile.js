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
    slopMode: 'all',  // 'all' = SLOP FILTER (show everything, resting), 'free' = hide slop, 'only' = show only slop
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

    STRIP_COLORS: NRWConfig.STRIP_COLORS,

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
            sheetBtnbar: document.getElementById('sheet-btnbar'),
            chevronLeft: document.getElementById('chevron-left'),
            chevronRight: document.getElementById('chevron-right'),
            viewDots: document.querySelectorAll('.view-btn'),
            posterDetailsLip: document.getElementById('poster-details-lip'),
            siteHeader: document.getElementById('site-header'),
            filterDesc: document.getElementById('filter-desc'),
        };

        this.updateHeaderHeight();
        window.addEventListener('resize', () => this.updateHeaderHeight());

        try {
            // No cache-buster: rely on ETag + max-age=600 (audit #5)
            const response = await fetch('../data.json');
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
            this.setupHistory();

            this.applyFilter();
            this.buildGrid();
            this.setView(0);
            this.handleDeepLink();

        } catch (err) {
            console.error('Failed to load movies:', err);
            this.dom.gridView.innerHTML =
                '<div class="loading"><p>Failed to load movies</p></div>';
        }
    },

    updateHeaderHeight() {
        const h = this.dom.siteHeader.offsetHeight;
        document.documentElement.style.setProperty('--header-height', h + 'px');
        // Detail sheet rises to just below the slogan (covers the filter
        // controls, which are inert behind it anyway)
        const slogan = this.dom.siteHeader.querySelector('.site-slogan');
        const sheetTop = slogan ? (slogan.offsetTop + slogan.offsetHeight + 2) : h;
        document.documentElement.style.setProperty('--sheet-top', sheetTop + 'px');
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

            // Virtual screenings: Available Now first (soonest to leave), then upcoming (soonest to open)
            if (aFest && bFest) {
                const t = new Date().toISOString().slice(0, 10);
                const sA = a.virtual_screening_info?.available_start || '';
                const sB = b.virtual_screening_info?.available_start || '';
                const nowA = !sA || sA <= t, nowB = !sB || sB <= t;
                if (nowA !== nowB) return nowA ? -1 : 1;
                if (nowA) return (a.virtual_screening_info?.available_end || '9999-99-99').localeCompare(b.virtual_screening_info?.available_end || '9999-99-99');
                return sA.localeCompare(sB);
            }

            const dateA = new Date(a.digital_date);
            const dateB = new Date(b.digital_date);
            if (dateB.getTime() !== dateA.getTime()) return dateB - dateA;

            // Same date: staff picks first
            const aStaff = NRWConfig.isStaffPick(a, this.staffPicks);
            const bStaff = NRWConfig.isStaffPick(b, this.staffPicks);
            if (aStaff && !bStaff) return -1;
            if (!aStaff && bStaff) return 1;
            return 0;
        });
    },

    // ===== FILTERS =====
    setupFilters() {
        // GENRE control opens a bottom sheet of genre chips. The chips are
        // .filter-pill elements driving the same single-select genre logic; this
        // only manages the sheet UI + the quiet GENRE control's label/highlight.
        const genreControl = document.getElementById('genre-control');
        const genreBackdrop = document.getElementById('genre-backdrop');
        const genreSheet = document.getElementById('genre-sheet');
        const closeSheet = () => genreBackdrop?.classList.remove('open');
        genreControl?.addEventListener('click', () => genreBackdrop?.classList.add('open'));
        genreBackdrop?.addEventListener('click', (e) => { if (e.target === genreBackdrop) closeSheet(); });
        document.getElementById('genre-sheet-done')?.addEventListener('click', closeSheet);
        document.getElementById('genre-sheet-clear')?.addEventListener('click', () => {
            const active = genreSheet?.querySelector('.filter-pill.active');
            if (active) active.click();   // clears via the same handler below
        });
        genreSheet?.addEventListener('click', (e) => {
            const pill = e.target.closest('.filter-pill');
            if (!pill) return;

            const filter = pill.dataset.filter;

            // One exclusive group: picking a genre clears the toggles + other
            // genres (single-select). Re-tapping the active genre clears it.
            const wasActive = this.activeFilters.has(filter);
            this.setExclusiveView('genre');
            this.activeFilters.clear();
            genreSheet.querySelectorAll('.filter-pill.active').forEach(p => p.classList.remove('active'));
            if (!wasActive) {
                this.activeFilters.add(filter);
                pill.classList.add('active');
            }
            this.syncGenreControl();

            this.applyFilter();
            this.updateFilterDesc();
            this.buildGrid();
            this.setView(0);
            this.dom.gridView.scrollTop = 0;
            closeSheet();
        });

        // Slop toggle (3-state: free / all / only)
        const slopToggle = document.getElementById('slop-free-toggle');
        if (slopToggle) {
            const SLOP_STATES = ['all', 'free', 'only'];  // SLOP FILTER (rest) → SLOP-FREE → SLOP ONLY → back
            const SLOP_LABELS = { free: 'SLOP-FREE', all: 'SLOP FILTER', only: 'SLOP ONLY' };
            const updateSlopToggle = () => {
                slopToggle.dataset.state = this.slopMode;
                const label = document.getElementById('slop-state-label');
                if (label) label.textContent = SLOP_LABELS[this.slopMode];
            };
            updateSlopToggle();
            slopToggle.addEventListener('click', () => {
                const idx = SLOP_STATES.indexOf(this.slopMode);
                this.slopMode = SLOP_STATES[(idx + 1) % 3];
                this.setExclusiveView('slop'); // clear genres + other toggles
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

    // Reflect the active genre (if any) on the quiet GENRE control: highlight it
    // and show the chosen genre's name, else reset to "GENRE".
    syncGenreControl() {
        const control = document.getElementById('genre-control');
        if (!control) return;
        const active = document.querySelector('#genre-sheet .filter-pill.active');
        control.classList.toggle('has-active', !!active);
        const text = control.querySelector('.genre-text');
        if (text) text.textContent = active ? active.textContent.toUpperCase() : 'GENRE';
    },

    // View toggles (Selects / Fests / Pre-Orders) are mutually exclusive.
    // The caller turns its own toggle on; this clears the other two —
    // both the state flag and the button highlight.
    setExclusiveView(winner) {
        // Picking a toggle clears genre filters (one filter OR one toggle at a time).
        if (winner !== 'genre') {
            this.activeFilters.clear();
            document.querySelectorAll('#genre-sheet .filter-pill.active').forEach(p => p.classList.remove('active'));
            this.syncGenreControl();
        }
        const others = {
            selects:   () => { this.showHighlightsOnly = false; document.getElementById('highlights-toggle')?.classList.remove('active'); },
            fests:     () => { this.hideFest = true;            document.getElementById('fest-toggle')?.classList.remove('active'); },
            preorders: () => { this.showPreorders = false;      document.getElementById('preorder-toggle')?.classList.remove('active'); },
            slop:      () => {
                this.slopMode = 'all';
                const st = document.getElementById('slop-free-toggle');
                if (st) st.dataset.state = 'all';
                const lbl = document.getElementById('slop-state-label');
                if (lbl) lbl.textContent = 'SLOP FILTER';
            },
        };
        for (const name in others) {
            if (name !== winner) others[name]();
        }
    },

    updateFilterDesc() {
        const desc = this.dom.filterDesc;
        if (!desc) return;
        // Filter description blurbs removed (matches tvOS — no genre/view descriptions).
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
                if (!NRWConfig.matchesSlopMode(movie, this.slopMode)) return false;

                // Highlights mode: only staff picks
                if (this.showHighlightsOnly && !NRWConfig.isStaffPick(movie, this.staffPicks)) return false;

                // Hide-fest mode: hide virtual screenings
                if (this.hideFest && movie.filters?.is_virtual_screening) return false;
            }

            // Pre-orders only appear when toggle is ON or search is active —
            // the Fest view also surfaces upcoming screenings (Available Soon).
            if (movie._is_preorder && !this.showPreorders && !this.searchQuery
                && !(!this.hideFest && movie.filters?.is_virtual_screening)) return false;

            // Category filters (OR logic) — bypassed when search is active.
            // Tag tests live in shared-config.js (single source of truth with desktop).
            if (filters.size > 0 && !this.searchQuery) {
                if (![...filters].some(f => NRWConfig.movieMatchesGenre(movie, f))) return false;
            }

            // Search filter — shared with desktop
            if (this.searchQuery) {
                return NRWConfig.matchesSearch(movie, this.searchQuery);
            }

            return true;
        });
    },

    // ===== GRID (View 0) =====
    // Packed mode (audit F5/F6): a genre filter or the PRE-ORDER view spread a
    // handful of films across many days, so per-date banners read as 80–90%
    // chrome/void. In these views we drop ALL date section headers and pack the
    // posters into one continuous 3-col grid, each cell carrying a small muted
    // date instead. Default / SELECTS / FESTS / search are unchanged.
    isPackedMode() {
        return (!this.searchQuery && (this.activeFilters.size > 0 || this.showPreorders));
    },

    buildGrid() {
        this.savedScrollTop = 0;

        // Pre-compute grid entries (date strips + movie items)
        this.gridEntries = [];
        let lastDate = '';
        let preorderStarted = false;
        let festNowStarted = false;
        let festSoonStarted = false;
        let lastFestStart = '';
        const festToday = new Date().toISOString().slice(0, 10);
        const packed = this.isPackedMode();

        if (!packed && this.showHighlightsOnly && this.filteredMovies.length > 0) {
            this.gridEntries.push({ type: 'date', dateStr: 'highlights' });
            // No description blurb — the "SELECTS · FILMS OF NOTE" banner says enough
        }
        if (!packed && this.slopMode === 'only' && this.filteredMovies.length > 0) {
            this.gridEntries.push({ type: 'date', dateStr: 'slop' });
        }

        this.filteredMovies.forEach((movie, i) => {
            // Packed mode: no headers at all — the per-cell muted date carries the
            // date info. Just append the movie with its cell date.
            if (packed) {
                const cellDate = (movie.digital_date || '').substring(0, 10);
                this.gridEntries.push({ type: 'movie', movie, index: i, cellDate });
                return;
            }
            if (movie.filters?.is_virtual_screening) {
                // Virtual screenings group into Available Now / Available Soon (not by arrival date)
                const start = movie.virtual_screening_info?.available_start || '';
                const isNow = !start || start <= festToday;
                if (isNow) {
                    if (!festNowStarted) {
                        festNowStarted = true;
                        this.gridEntries.push({ type: 'date', dateStr: 'fest-now' });
                    }
                } else {
                    if (!festSoonStarted) {
                        festSoonStarted = true;
                        this.gridEntries.push({ type: 'date', dateStr: 'fest-soon' });
                    }
                    if (start !== lastFestStart) {
                        this.gridEntries.push({ type: 'date', dateStr: 'fest-open:' + start });
                        lastFestStart = start;
                    }
                }
            } else if (movie._is_preorder) {
                if (!preorderStarted) {
                    preorderStarted = true;
                    this.gridEntries.push({ type: 'date', dateStr: 'pre-order' });
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
            } else {
                grid.appendChild(this.createGridItem(entry.movie, entry.index, entry.cellDate));
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
        const SECTION_TYPES = ['pre-order', 'fest', 'fest-now', 'fest-soon', 'highlights', 'slop'];
        row.className = 'date-row-header' + (SECTION_TYPES.includes(dateStr) ? ' section-banner' : '');

        // Neon sticky banner: colored day + white rest; color follows section / active filter
        let day, rest = '', color = '';
        if (dateStr === 'pre-order') {
            day = 'PRE-ORDER'; rest = 'COMING SOON'; color = '#7c3aed';
        } else if (dateStr === 'fest' || dateStr === 'fest-now') {
            day = 'FESTS'; rest = 'AVAILABLE NOW'; color = '#FFD700';
        } else if (dateStr === 'fest-soon') {
            day = 'FESTS'; rest = 'COMING SOON'; color = '#b9952e';
        } else if (dateStr.startsWith('fest-open:')) {
            const fd = new Date(dateStr.slice(10) + 'T12:00:00');
            day = fd.toLocaleDateString('en', { weekday: 'short' });
            rest = fd.toLocaleDateString('en', { month: 'short' }) + ' ' + fd.getDate() + ' · OPENS';
            color = '#b9952e';
        } else if (dateStr === 'highlights') {
            day = 'SELECTS'; rest = 'OF NOTE'; color = '#00d4aa';
        } else if (dateStr === 'slop') {
            day = 'SLOP'; rest = 'THE CONTENT RIVER'; color = '#ff9500';  // matches SLOP ONLY toggle orange
        } else {
            const d = new Date(dateStr + 'T12:00:00');
            day = d.toLocaleDateString('en', { weekday: 'short' });
            rest = d.toLocaleDateString('en', { month: 'short' }) + ' ' + d.getDate();
            const singleFilter = this.activeFilters.size === 1 ? [...this.activeFilters][0] : null;
            if (this.showHighlightsOnly) {
                color = '#00d4aa';
            } else if (!this.hideFest) {
                color = '#FFD700';
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

    createGridItem(movie, index, cellDate) {
        const isStaffPick = NRWConfig.isStaffPick(movie, this.staffPicks);
        const isScreening = movie.filters?.is_virtual_screening;
        const streamingSvc = this.getGridStreamingService(movie);

        const item = document.createElement('div');
        item.className = 'grid-item' + (isScreening ? ' screening-movie' : '') + (isStaffPick ? ' staff-pick-movie' : '');
        item.dataset.index = index;   // filteredMovies index — used to open the first on-screen movie

        // VS: festival name band above the poster (dark, gold text — matches desktop)
        if (isScreening && movie.virtual_screening_info?.screening_name) {
            const band = document.createElement('div');
            band.className = 'screening-fest-band';
            band.textContent = movie.virtual_screening_info.screening_name;
            item.appendChild(band);
        }

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
                img.src = this.posterAt(movie.poster, 'w342');
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
            img.src = this.posterAt(movie.poster, 'w342');
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

        if (isStaffPick) {
            const badge = document.createElement('span');
            badge.className = 'staff-pick-badge';
            badge.textContent = '★ NRW SELECT ★';
            item.appendChild(badge);
        }
        if (movie._is_preorder) {
            const badge = document.createElement('span');
            badge.className = 'preorder-badge';
            badge.textContent = 'Pre-Order';
            badgeTarget.appendChild(badge);
        }
        if (movie.filters?.is_restoration) {
            const badge = document.createElement('span');
            badge.className = 'restoration-badge';
            badge.textContent = (movie.reissue_label || 'RESTORATION').toUpperCase();
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

        // Caption (STYLE_GUIDE "Wall Grid & Poster Captions"): 2 lines.
        //  Line 1 = white bold title, ONE line, ellipsis.
        //  Line 2 = teal Director \u00b7 Genre \u00b7 Nation. Director ellipsizes while the
        //           pinned " \u00b7 Genre \u00b7 Nation" suffix (flex-shrink:0) is never lost.
        // Packed mode (genre/pre-order views) prepends a small muted date to line 2.
        const info = document.createElement('div');
        info.className = 'grid-item-info';

        // Line 1: title
        const titleEl = document.createElement('div');
        titleEl.className = 'grid-item-title';
        titleEl.textContent = movie.display_title || movie.title || '';
        info.appendChild(titleEl);

        // Line 2: teal meta with pinned suffix (+ optional muted packed date)
        const director = movie.crew?.director || movie.director || '';
        const dirWikiUrl = movie.links?.director_wiki;
        const genre = movie.genres?.[0] || '';
        const country = NRWConfig.abbreviateCountry(movie.country) || '';

        const dateLabel = cellDate ? this.shortDate(cellDate) : '';
        const dirHtml = director
            ? (dirWikiUrl
                ? `<a href="${dirWikiUrl}" target="_blank" rel="noopener" class="mobile-dir-link grid-meta-dir">${this.esc(director)}</a>`
                : `<span class="grid-meta-dir">${this.esc(director)}</span>`)
            : '';
        const pinnedParts = [];
        if (genre) pinnedParts.push(this.esc(genre));
        if (country) pinnedParts.push(this.esc(country));
        const pinnedHtml = pinnedParts.length
            ? `<span class="grid-meta-pin">${(dirHtml ? ' \u00b7 ' : '') + pinnedParts.join(' \u00b7 ')}</span>`
            : '';

        if (dateLabel || dirHtml || pinnedHtml) {
            const meta = document.createElement('div');
            meta.className = 'grid-item-meta';
            const dateHtml = dateLabel
                ? `<span class="grid-meta-date">${this.esc(dateLabel)}${(dirHtml || pinnedHtml) ? ' \u00b7 ' : ''}</span>`
                : '';
            meta.innerHTML = dateHtml + dirHtml + pinnedHtml;
            info.appendChild(meta);
        }

        item.appendChild(info);

        // VS: hollow days-left pill below the caption
        if (isScreening) {
            const pill = this.vsDaysPill(movie);
            const pillRow = document.createElement('div');
            pillRow.className = 'days-row';
            pillRow.innerHTML = '<span class="days-pill ' + pill.cls + '">' + this.esc(pill.txt) + '</span>';
            item.appendChild(pillRow);
        }

        item.addEventListener('click', () => this.selectMovie(index));
        return item;
    },

    // Virtual-screening days-left pill: red ≤3 days, gold "Until <date>", gray "Opens <date>"
    vsDaysPill(movie) {
        const info = movie.virtual_screening_info || {};
        const start = info.available_start || '';
        const end = info.available_end || '';
        const today = new Date().toISOString().slice(0, 10);
        const fmt = iso => {
            const d = new Date(iso + 'T12:00:00');
            return d.toLocaleDateString('en', { month: 'short' }) + ' ' + d.getDate();
        };
        if (start && start > today) return { cls: 'soon', txt: 'Opens ' + fmt(start) };
        if (!end) return { cls: 'calm', txt: 'Screening live' };
        const daysLeft = Math.round((new Date(end + 'T12:00:00') - new Date(today + 'T12:00:00')) / 86400000);
        if (daysLeft <= 3) return { cls: 'urgent', txt: daysLeft <= 0 ? 'Last day' : daysLeft + (daysLeft === 1 ? ' day left' : ' days left') };
        return { cls: 'calm', txt: 'Until ' + fmt(end) };
    },

    // ===== VIEW TRANSITIONS =====
    // History model (audit F42/F45): the browser history stack mirrors the view
    // depth so the iOS swipe-back gesture / Android back button step DOWN through
    // sheet → poster → grid instead of leaving the site. Depth 0 = grid (base
    // entry), 1 = poster, 2 = sheet.
    //
    // setView() is the smart router:
    //   • going UP   → do the DOM work + pushState for each new level
    //   • going DOWN → history.go(delta); popstate is the ONLY path that lowers a
    //                  view (so a swipe-back and a UI dismiss share one code path)
    //   • same level → plain DOM (movie navigation)
    // _applyView() is the raw DOM transition, called by both setView (up) and the
    // popstate handler (down). _histDepth tracks how many nrwView entries we own.
    setupHistory() {
        this._histDepth = 0;
        // A reload can revive a stale {nrwView} entry while our depth counter
        // resets — neutralize it so Back doesn't re-open a view for a movie
        // index that no longer matches.
        if (history.state && typeof history.state.nrwView === 'number') {
            history.replaceState(null, '', location.href);
        }
        window.addEventListener('popstate', () => {
            // A trailer overlay owns its own history entry + popstate handler; let
            // it consume this pop (it's still in the DOM here — removed on a timer).
            if (document.getElementById('trailer-overlay')) return;
            const target = (history.state && typeof history.state.nrwView === 'number')
                ? history.state.nrwView : 0;
            this._histDepth = target;
            if (target === 0) this._stripDeepLink();
            this._applyView(target);
        });
    },

    // Drop a stale ?m= deep-link param once the movie is dismissed (audit F45),
    // without adding a history entry.
    _stripDeepLink() {
        const url = new URL(location.href);
        if (!url.searchParams.has('m')) return;
        url.searchParams.delete('m');  // only m — other params survive
        history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    },

    setView(view) {
        const depth = this._histDepth || 0;
        if (view > depth) {
            // Going up: apply DOM, then record one history entry per new level.
            this._applyView(view);
            for (let d = depth + 1; d <= view; d++) {
                history.pushState({ nrwView: d }, '');
            }
            this._histDepth = view;
        } else if (view < depth) {
            // Going down: let history drive it (popstate does the DOM + strip).
            history.go(view - depth);
        } else {
            // Same level (e.g. reselecting) — plain DOM.
            this._applyView(view);
        }
    },

    _applyView(view) {
        this.currentView = view;

        // Update dots
        this.dom.viewDots.forEach((d, i) => d.classList.toggle('active', i === view));

        // Grid view
        this.dom.gridView.classList.toggle('hidden', view !== 0);

        // Poster view (visible in view 1 and view 2)
        this.dom.posterView.classList.toggle('hidden', view !== 1 && view !== 2);
        // Hide the "⌃ DETAILS" lip once the sheet is up (view 2)
        this.dom.posterView.classList.toggle('sheet-open', view === 2);

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

    // The filteredMovies index of the first grid card currently in the viewport
    // (below the fixed header). Falls back to 0 if none is found (e.g. empty grid).
    firstVisibleGridIndex() {
        const headerH = this.dom.siteHeader ? this.dom.siteHeader.getBoundingClientRect().bottom : 0;
        const items = this.dom.gridView.querySelectorAll('.grid-item');
        for (const el of items) {
            const r = el.getBoundingClientRect();
            // First card whose bottom edge clears the header — i.e. it's on screen.
            if (r.bottom > headerH && r.top < window.innerHeight) {
                const idx = parseInt(el.dataset.index, 10);
                if (!isNaN(idx)) return idx;
            }
        }
        return 0;
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

    // On load, open the poster view for a movie if the URL carries ?m=<id>
    // (from a shared link). Always opens, even if the movie is filtered out.
    handleDeepLink() {
        const id = new URLSearchParams(location.search).get('m');
        if (!id) return;
        let idx = this.filteredMovies.findIndex(m => String(m.id) === String(id));
        if (idx === -1) {
            // Filtered out (slop-hidden / fest / pre-order). Surface just THIS one movie
            // without changing the wall's filter mode (mirrors desktop). The injected
            // movie is transient — the next applyFilter() rebuild drops it.
            const target = this.allMovies.find(m => String(m.id) === String(id));
            if (!target) return;
            this.filteredMovies = [target, ...this.filteredMovies];
            this.buildGrid();
            idx = 0;
        }
        if (idx !== -1) {
            // selectMovie() already enters the poster view (pushes the view-1
            // history entry on top of the deep-linked base entry); one back()
            // returns to the grid and strips ?m=.
            this.selectMovie(idx);
        }
    },

    // The shareable per-movie URL — the OG stub page that yields a rich preview.
    // Mobile lives in /mobile/, so the stub is one level up at ../m/<id>.html.
    _shareUrlFor(id) {
        return new URL('../m/' + encodeURIComponent(id) + '.html', location.href).href;
    },

    // Share the movie currently shown in the poster/sheet view.
    shareCurrent() {
        this.shareMovie(this.filteredMovies[this.currentMovieIndex]);
    },

    shareMovie(movie) {
        if (!movie) return;
        const url = this._shareUrlFor(String(movie.id));
        const title = movie.display_title || movie.title || 'The New Release Wall';
        const text = `${title}${movie.year ? ' (' + movie.year + ')' : ''} — on The New Release Wall`;
        if (navigator.share) {
            navigator.share({ title, text, url }).catch(() => {});
        } else if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(url)
                .then(() => this._showToast('Link copied'))
                .catch(() => this._showToast(url));
        } else {
            window.prompt('Copy this link:', url);
        }
    },

    _showToast(msg) {
        const existing = document.getElementById('nrw-toast');
        if (existing) existing.remove();
        const toast = document.createElement('div');
        toast.id = 'nrw-toast';
        toast.className = 'nrw-toast';
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 1600);
    },

    // Inline share glyph (reused by the sheet button + poster-view icon)
    SHARE_SVG: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>',

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

        // Full-screen close-up gets the sharp w780 rendition (audit #5)
        this.dom.posterImg.src = this.posterAt(movie.poster, 'w780') || '';
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
        const btnbar = this.dom.sheetBtnbar;

        if (direction) {
            const cls = direction === 'left' ? 'slide-left-enter' : 'slide-right-enter';
            content.classList.add(cls);
            setTimeout(() => content.classList.remove(cls), 250);
        }

        const isStaffPick = NRWConfig.isStaffPick(movie, this.staffPicks);
        const isScreening = movie.filters?.is_virtual_screening;
        const screeningInfo = movie.virtual_screening_info || {};

        // ---- LOCKED HERO: poster + fixed-height info box ----
        // Line 1: Director (label teal, name = wiki link, one line)
        const dirName = movie.crew?.director || movie.director || '';
        const dirWikiUrl = movie.links?.director_wiki;
        const dirLine = dirName
            ? '<div class="hero-crew"><span class="crew-label">Dir:</span> ' + (dirWikiUrl
                ? '<a href="' + dirWikiUrl + '" target="_blank" rel="noopener" class="crew-link">' + this.esc(dirName) + '</a>'
                : '<span class="crew-name">' + this.esc(dirName) + '</span>') + '</div>'
            : '';

        // Line 2: Cast (label teal, names = wiki links, one line)
        const cast = movie.crew?.cast;
        let castLine = '';
        if (cast?.length) {
            const castWiki = movie.links?.cast_wiki || {};
            const castParts = cast.map(name => {
                const url = castWiki[name];
                return url
                    ? '<a href="' + url + '" target="_blank" rel="noopener" class="crew-link">' + this.esc(name) + '</a>'
                    : this.esc(name);
            });
            castLine = '<div class="hero-crew hero-cast"><span class="crew-label">Cast:</span> ' +
                '<span class="crew-name">' + castParts.join(', ') + '</span></div>';
        }

        // Teal line under the title (mirrors desktop): Country · Genre · Date
        const genreParts = [];
        if (movie.country) genreParts.push(this.esc(NRWConfig.abbreviateCountry(movie.country) || movie.country));
        if (movie.genres?.[0]) genreParts.push(this.esc(movie.genres[0]));
        if (movie.digital_date) {
            const [gy, gm, gd] = movie.digital_date.split('-');
            const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
            genreParts.push(months[parseInt(gm, 10) - 1] + ' ' + parseInt(gd, 10));
        }

        // Gray detail line — now BELOW the synopsis (mirrors desktop's runtime line)
        const detailParts = [];
        if (movie.year) detailParts.push(this.esc(movie.year));
        if (movie.runtime) detailParts.push(this.esc(this.formatRuntime(movie.runtime)));
        if (movie.studio && movie.studio !== 'Unknown') detailParts.push(this.esc(movie.studio));

        // Score badges (pinned to bottom of the box, tappable)
        let scoresHtml = '';
        const hasScores = movie.links?.wikipedia || movie.rt_score || movie.imdb_rating ||
            (movie.metacritic_score && movie.metacritic_score !== '0') || movie.letterboxd_score;
        if (hasScores) {
            const scoreEl = (link, inner) => link
                ? '<a class="sheet-score" href="' + link + '" target="_blank" rel="noopener">' + inner + '</a>'
                : '<div class="sheet-score">' + inner + '</div>';
            scoresHtml += '<div class="sheet-scores">';
            if (movie.links?.wikipedia) {
                scoresHtml += scoreEl(movie.links.wikipedia,
                    '<img class="sheet-score-logo wiki-logo" src="../assets/logos/wikipedia_PNG40.png" alt="Wikipedia">');
            }
            if (movie.rt_score) {
                scoresHtml += scoreEl(movie.links?.rt,
                    '<img class="sheet-score-logo" src="../assets/logos/rt.png" alt="RT">' +
                    '<span class="sheet-score-value rt">' + movie.rt_score + '</span>');
            }
            if (movie.imdb_rating) {
                scoresHtml += scoreEl(movie.links?.imdb,
                    '<img class="sheet-score-logo" src="../assets/logos/imdb.png" alt="IMDb">' +
                    '<span class="sheet-score-value imdb">' + movie.imdb_rating + '</span>');
            }
            if (movie.metacritic_score && movie.metacritic_score !== '0') {
                scoresHtml += scoreEl(movie.links?.metacritic,
                    '<img class="sheet-score-logo mc-logo" src="../assets/logos/metacritic.png" alt="MC">' +
                    '<span class="sheet-score-value meta">' + movie.metacritic_score + '</span>');
            }
            if (movie.letterboxd_score) {
                scoresHtml += scoreEl(movie.links?.letterboxd,
                    '<img class="sheet-score-logo" src="../assets/logos/services/letterboxd-dots.svg" alt="Letterboxd">' +
                    '<span class="sheet-score-value lb">' + movie.letterboxd_score + '</span>');
            }
            scoresHtml += '</div>';
        }

        // Build scrolling content: locked hero. Title row = title + NRW SELECT
        // badge horizontally aligned (desktop pattern — no badge, no hole);
        // teal Country·Genre·Date line under it; scores pinned at the bottom.
        let html = '<div class="sheet-hero">' +
            '<img class="sheet-hero-poster" src="' + this.esc(movie.poster || '') + '" alt="' +
            this.esc(movie.title || '') + '" onerror="this.style.visibility=\'hidden\'">' +
            '<div class="sheet-hero-text">' +
            '<div class="sheet-hero-titlerow">' +
            '<div class="sheet-hero-title">' + this.esc(movie.display_title || movie.title || 'Untitled') + '</div>' +
            (isStaffPick ? '<span class="sheet-select-badge">★ NRW SELECT ★</span>' : '') +
            '</div>' +
            (genreParts.length ? '<div class="hero-genre">' + genreParts.join(' · ') + '</div>' : '') +
            dirLine + castLine +
            scoresHtml +
            '</div></div>';

        // Pull quotes — teal debadged (no RT/LB badge), still tappable
        if (movie.pull_quotes?.length) {
            html += '<div class="sheet-pq-wrap">';
            movie.pull_quotes.forEach(q => {
                const attribution = [q.critic, q.outlet].filter(Boolean).join(', ');
                const quoteInner = '<q class="sheet-pq-text">' + this.esc(q.text || '') + '</q>' +
                    (attribution ? '<cite class="sheet-pq-cite">' + this.esc(attribution) + '</cite>' : '');
                html += '<div class="sheet-pq">' + (q.review_url
                    ? '<a href="' + this.esc(q.review_url) + '" target="_blank" rel="noopener" class="sheet-pq-link">' + quoteInner + '</a>'
                    : quoteInner) + '</div>';
            });
            html += '</div>';
        }

        // Synopsis (no label; renders **bold**/*italic*, bold film titles hyperlinked)
        html += '<div class="sheet-synopsis">' +
            this._linkBoldTitles(NRWConfig.renderMarkdown(movie.capsule || movie.synopsis || 'No synopsis available.')) +
            '</div>';

        // Virtual screening — quiet gold-italic note at the END of the capsule
        if (isScreening) {
            let note = 'Virtual screening via <span class="vs-fest">' +
                this.esc(screeningInfo.screening_name || 'festival') + '</span>';
            if (screeningInfo.available_end) {
                const [, m, d] = screeningInfo.available_end.split('-');
                const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                note += ' · through ' + months[parseInt(m, 10) - 1] + ' ' + parseInt(d, 10);
            }
            html += '<div class="sheet-vs-note">' + note + '.</div>';
        }

        // Year • Runtime • Studio — quiet closing line (desktop pattern)
        if (detailParts.length) {
            html += '<div class="sheet-detail-line">' + detailParts.join(' • ') + '</div>';
        }

        content.innerHTML = html;
        content.scrollTop = 0;
        this._updateSheetScrollHint();

        // ---- FIXED BOTTOM BUTTON BAR ----
        let bar = '';

        // Trailer: hosted mp4 -> in-app player, else open YouTube link
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        if (trailerUrl) {
            const isMP4 = (() => {
                try { return new URL(trailerUrl).pathname.endsWith('.mp4'); }
                catch { return trailerUrl.endsWith('.mp4'); }
            })();
            bar += isMP4
                ? '<button class="btn-trailer" onclick="NRWMobile.showTrailer(\'' + movie.id + '\')">TRAILER</button>'
                : '<a class="btn-trailer" href="' + trailerUrl + '" target="_blank" rel="noopener">TRAILER</a>';
        }

        // Watch buttons: VOD mini-cards on ONE row (logo on top, Rent/Buy under)
        // + streaming badges (full-width via CSS)
        const streamingList = this.getStreamingProviders(movie);
        const vodList = this.getVODList(movie);
        const rentVod = isScreening
            ? vodList.filter(v => v.resolvedKey !== 'screening')
            : vodList;
        if (rentVod.length) {
            bar += '<div class="vod-row">' +
                rentVod.map(v => this.renderVODMiniCard(v)).join('') +
                '</div>';
        }
        streamingList.forEach(s => { bar += this.renderStreamButton(s); });

        // Pre-order fallback (no other watch links)
        if (!rentVod.length && !streamingList.length && !isScreening) {
            const preOrderLinks = Array.isArray(movie.pre_order_links) ? movie.pre_order_links : [];
            preOrderLinks.forEach(pl => {
                const resolved = this.resolveVODService(pl.service, pl.link);
                if (resolved && pl.link) {
                    bar += this.renderProviderBadge({
                        name: 'Pre-Order',
                        wideLogo: resolved.wideLogo,
                        serviceKey: resolved.key,
                        link: pl.link,
                        resolvedKey: resolved.key
                    });
                }
            });
        }

        // Gold "Buy Tickets" button for virtual screenings
        if (isScreening) {
            const screeningVod = this.getVODEntries(movie).find(v => {
                const resolved = this.resolveVODService(v.service, v.link);
                return resolved?.key === 'screening';
            });
            if (screeningVod?.link) {
                bar += '<a class="btn-tickets" href="' + screeningVod.link +
                    '" target="_blank" rel="noopener">Buy Tickets</a>';
            }
        }

        // Share (teal outline)
        bar += '<button class="btn-share" onclick="NRWMobile.shareCurrent()">' +
            this.SHARE_SVG + '<span>Share</span></button>';

        btnbar.innerHTML = bar;
        btnbar.scrollTop = 0;
    },

    // "MORE ⌄" pill: visible only while the sheet content has unscrolled
    // overflow, so it's obvious the synopsis continues.
    _updateSheetScrollHint() {
        const content = this.dom.sheetContent;
        const pill = document.getElementById('sheet-more-pill');
        if (!content || !pill) return;
        const fade = document.getElementById('sheet-scroll-fade');
        const update = () => {
            const overflow = content.scrollHeight - content.clientHeight;
            const nearEnd = content.scrollTop >= overflow - 20;
            const show = overflow > 12 && !nearEnd;
            // Sit just above the button bar, whose height varies per movie
            const bar = this.dom.sheetBtnbar;
            if (bar) {
                pill.style.bottom = (bar.offsetHeight + 8) + 'px';
                if (fade) fade.style.bottom = bar.offsetHeight + 'px';
            }
            pill.classList.toggle('visible', show);
            if (fade) fade.classList.toggle('visible', show);
        };
        if (!content._scrollHintBound) {
            content._scrollHintBound = true;
            content.addEventListener('scroll', update, { passive: true });
        }
        requestAnimationFrame(update);
        setTimeout(update, 350); // sheet slide-in + reflow settle
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

    // All free-streaming providers (one badge each). Falls back to the single
    // provider-name resolver when watch_links has no linked streaming entries.
    getStreamingProviders(movie) {
        const wl = movie.watch_links || {};
        const EXCLUDED_STREAMING = ['spectrum on demand'];
        const isExcluded = s => s && EXCLUDED_STREAMING.includes(s.toLowerCase());
        const streamingWl = wl.streaming;
        let raw = [];
        if (Array.isArray(streamingWl)) {
            raw = streamingWl.filter(s => s && s.service && s.link && !isExcluded(s.service));
        } else if (streamingWl?.service && streamingWl?.link && !isExcluded(streamingWl.service)) {
            raw = [streamingWl];
        }
        if (raw.length) {
            return raw.map(s => {
                const resolved = this.resolveService(s.service);
                return {
                    name: resolved?.name || NRWConfig.cleanServiceName(s.service),
                    wideLogo: resolved?.wideLogo,
                    serviceKey: resolved?.class,
                    link: s.link,
                    resolvedKey: resolved?.class
                };
            });
        }
        // Fallback: provider-name-only (no link) — preserve single-badge behavior
        const single = this.getStreamingProvider(movie);
        return single ? [single] : [];
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

    // Streaming button for the bottom bar — brand-colored fill + service name,
    // matching the desktop/mockup .btn-stream (no oversized wide-logo images).
    STREAM_COLORS: {
        netflix:'#E50914', max:'#B537F2', disney:'#113CCF', prime:'#00A8E1', amazon:'#00A8E1',
        hulu:'#1CE783', paramount:'#0064FF', youtube:'#FF0000', hoopla:'#FC4F08',
        fandango:'#FF6600', apple:'#333333', appletv:'#333333', peacock:'#111111', tubi:'#FA382F',
        pluto:'#00B4E4', plex:'#1a1a1a', mubi:'#DA2128', shudder:'#8B0000', criterion:'#000000',
        kanopy:'#1B7A43', crackle:'#FF6600', roku:'#6C3A97', amc:'#1B6FE0'
    },

    renderStreamButton(provider) {
        const key = (provider.serviceKey || provider.resolvedKey || '').toLowerCase();
        const bg = this.STREAM_COLORS[key] || '#2a2a3a';
        const text = (bg === '#1CE783') ? '#000' : '#fff';
        const label = this.esc((provider.name || key).toUpperCase());
        const style = 'background:' + bg + ';color:' + text;
        return provider.link
            ? '<a class="btn-stream" style="' + style + '" href="' + provider.link +
                '" target="_blank" rel="noopener">' + label + '</a>'
            : '<div class="btn-stream" style="' + style + '">' + label + '</div>';
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

    // Compact VOD card for the one-row bottom bar (density redesign):
    // service logo on top, Rent/Buy price cells side by side beneath.
    renderVODMiniCard(provider) {
        if (!provider.rentPrice && !provider.buyPrice) return this.renderProviderBadge(provider);
        const svcKey = provider.serviceKey || '';
        const invertClass = this.INVERT_KEYS.has(svcKey) ? ' invert' : '';
        let logoHtml;
        if (provider.wideLogo) {
            const src = '../assets/logos/' + provider.wideLogo;
            logoHtml = '<img class="vmini-logo-img' + invertClass + '" src="' + src +
                '" alt="' + this.esc(provider.name) + '">';
        } else {
            logoHtml = '<span class="vmini-logo-text">' + this.esc(provider.name) + '</span>';
        }
        let pricesHtml = '';
        if (provider.rentPrice) {
            pricesHtml += '<a href="' + provider.link + '" target="_blank" rel="noopener" ' +
                'class="vmini-price rent">Rent ' + this.esc(provider.rentPrice) + '</a>';
        }
        if (provider.buyPrice) {
            pricesHtml += '<a href="' + provider.link + '" target="_blank" rel="noopener" ' +
                'class="vmini-price buy">Buy ' + this.esc(provider.buyPrice) + '</a>';
        }
        return '<div class="vmini ' + this.esc(svcKey) + '">' +
            '<a href="' + provider.link + '" target="_blank" rel="noopener" class="vmini-logo">' + logoHtml + '</a>' +
            '<div class="vmini-prices">' + pricesHtml + '</div>' +
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
                        // From the grid, open the first movie currently on screen
                        // (selectMovie routes through setView(1) so history stays consistent).
                        this.selectMovie(this.firstVisibleGridIndex());
                    } else {
                        this.setView(1);
                    }
                } else if (v === 2) {
                    if (this.currentView === 0 && this.filteredMovies.length > 0) {
                        this.selectMovie(this.firstVisibleGridIndex());
                    }
                    this.setView(2);
                }
            });
        });

        // "⌃ DETAILS" lip on the poster view → open the sheet (same path as swipe-up).
        if (this.dom.posterDetailsLip) {
            this.dom.posterDetailsLip.addEventListener('click', (e) => {
                e.stopPropagation();
                this.setView(2);
            });
        }
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
                // Tap on handle → step down one level to the poster (matches drag).
                this.setView(1);
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

        // Rebuild-safe teardown: reel nav re-enters showTrailer with the overlay
        // already up — swap overlay + listeners without touching history.
        const existing = document.getElementById('trailer-overlay');
        const wasOpen = !!existing;
        if (existing) existing.remove();
        if (this._trailerOrient) { this._trailerOrient(); this._trailerOrient = null; }
        if (this._trailerKey) { document.removeEventListener('keydown', this._trailerKey); this._trailerKey = null; }
        if (this._trailerPop) { window.removeEventListener('popstate', this._trailerPop); this._trailerPop = null; }

        // Reel: hosted-MP4 movies currently RENDERED on the wall (the same
        // "displayed" scope as desktop's reel), in wall order — not the whole
        // filtered list. Computed early: the chrome bar needs the counter.
        const isMp4 = (m) => { const u = m.links?.trailer_hosted; if (!u) return false; try { return new URL(u).pathname.endsWith('.mp4'); } catch { return u.endsWith('.mp4'); } };
        const reel = this.gridEntries.slice(0, this.displayedCount)
            .filter(e => e.type === 'movie')
            .map(e => e.movie)
            .filter(isMp4);
        const reelIdx = reel.findIndex(m => String(m.id) === String(movie.id));

        const overlay = document.createElement('div');
        overlay.id = 'trailer-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.95);' +
            'display:flex;align-items:center;justify-content:center;flex-direction:column;' +
            'opacity:0;transition:opacity 180ms ease';

        const title = this.esc(movie.display_title || movie.title || '');
        const counterEl = (reel.length > 1 && reelIdx >= 0)
            ? '<span class="trailer-chrome-counter">' + (reelIdx + 1) + ' / ' + reel.length + '</span>'
            : '';
        const subsUrl = movie.links?.trailer_hosted_subs;
        const trackEl = subsUrl
            ? '<track kind="subtitles" src="' + this.esc(subsUrl) + '" srclang="en" label="English" default>'
            : '';
        // crossorigin only when subtitles exist: the <track> needs a CORS fetch
        // from B2, but crossorigin also flips the poster to CORS mode, which can
        // fail against Chrome's no-cors-cached copy of the same TMDB image.
        overlay.innerHTML =
            '<div class="trailer-chrome"><span class="trailer-chrome-title">' + title + '</span>' + counterEl + '</div>' +
            '<button style="position:absolute;top:12px;right:16px;background:none;border:none;' +
            'color:white;font-size:2rem;cursor:pointer;z-index:10">&times;</button>' +
            '<div class="trailer-buf-spinner" style="display:none"></div>' +
            '<video controls autoplay playsinline' + (subsUrl ? ' crossorigin="anonymous"' : '') +
            ' poster="' + this.esc(movie.poster || '') + '"' +
            ' src="' + this.esc(url) + '"' +
            ' style="max-width:95%;max-height:70vh;border-radius:8px">' +
            trackEl +
            '</video>';

        document.body.appendChild(overlay);
        if (wasOpen) overlay.style.opacity = '1'; // instant swap on reel nav
        else requestAnimationFrame(() => { overlay.style.opacity = '1'; }); // fade on first open

        // One history entry per trailer session, so the iOS swipe-back / Android
        // back button closes the trailer instead of leaving the site. Non-pop
        // close paths consume the entry via history.back().
        if (!wasOpen) history.pushState({ nrwTrailer: true }, '');

        // close(fromPop): tears down ALL listeners first (incl. popstate, so the
        // compensating history.back() can't double-close), then fades out.
        const close = (fromPop) => {
            if (this._trailerPop) { window.removeEventListener('popstate', this._trailerPop); this._trailerPop = null; }
            if (this._trailerKey) { document.removeEventListener('keydown', this._trailerKey); this._trailerKey = null; }
            if (this._trailerOrient) { this._trailerOrient(); this._trailerOrient = null; }
            overlay.style.opacity = '0';
            setTimeout(() => overlay.remove(), 200);
            if (!fromPop) history.back();
        };
        this._trailerPop = () => close(true);
        window.addEventListener('popstate', this._trailerPop);
        this._trailerKey = (e) => { if (e.key === 'Escape') close(); };
        document.addEventListener('keydown', this._trailerKey);

        overlay.querySelector('button').addEventListener('click', () => close());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

        // Reel navigation: manual prev/next through movies that have an MP4 trailer.
        const goTo = (dir) => {
            if (reel.length < 2) return;
            const n = reel[(reelIdx + dir + reel.length) % reel.length];
            if (n && String(n.id) !== String(movie.id)) this.showTrailer(n.id);
        };
        // Tappable < > cue arrows (swipe affordance + manual nav). Only with a reel.
        if (reel.length >= 2) {
            [['trailer-cue-prev', '‹', 'Previous trailer', -1],
             ['trailer-cue-next', '›', 'Next trailer', 1]].forEach(([cls, glyph, label, dir]) => {
                const btn = document.createElement('button');
                btn.className = 'trailer-cue ' + cls;
                btn.textContent = glyph;
                btn.setAttribute('aria-label', label);
                btn.addEventListener('click', (e) => { e.stopPropagation(); goTo(dir); });
                overlay.appendChild(btn);
            });
        }

        // Swipe anywhere in the overlay → prev/next trailer. Capture phase so it
        // beats the video's native controls/seek; only a clear horizontal drag
        // navigates — taps fall through (close, seek, controls).
        let swStartX = null, swStartY = null;
        overlay.addEventListener('touchstart', (e) => {
            const t = e.touches[0]; swStartX = t.clientX; swStartY = t.clientY;
        }, { capture: true, passive: true });
        overlay.addEventListener('touchend', (e) => {
            if (swStartX === null) return;
            const t = e.changedTouches[0];
            const dx = t.clientX - swStartX, dy = t.clientY - swStartY;
            swStartX = null;
            if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) { e.stopPropagation(); goTo(dx < 0 ? 1 : -1); }
        }, { capture: true });

        // Double-tap left/right to seek ±10s
        const video = overlay.querySelector('video');
        if (video) {
            // Rotate to landscape → fullscreen the video. Listen to the matchMedia
            // CHANGE event (fires with the correct orientation, unlike a bare
            // orientationchange + immediate matchMedia read, which can be stale).
            const mql = window.matchMedia('(orientation: landscape)');
            const onOrient = (e) => {
                const landscape = (e && typeof e.matches === 'boolean') ? e.matches : mql.matches;
                if (!landscape || !document.getElementById('trailer-overlay')) return;
                try {
                    const p = video.requestFullscreen ? video.requestFullscreen()
                        : (video.webkitEnterFullscreen && video.webkitEnterFullscreen());
                    if (p && p.catch) p.catch(() => {});
                } catch (_) {}
            };
            if (mql.addEventListener) mql.addEventListener('change', onOrient);
            else mql.addListener(onOrient); // older Safari
            this._trailerOrient = () => {
                if (mql.removeEventListener) mql.removeEventListener('change', onOrient);
                else mql.removeListener(onOrient);
            };

            // Buffering spinner — visible while the network catches up
            const spinner = overlay.querySelector('.trailer-buf-spinner');
            const showSpin = () => { spinner.style.display = ''; };
            const hideSpin = () => { spinner.style.display = 'none'; };
            video.addEventListener('waiting', showSpin);
            video.addEventListener('playing', hideSpin);
            video.addEventListener('canplay', hideSpin);

            // iOS may reject autoplay-with-sound on auto-advance (the rebuilt
            // overlay loses the tap gesture) — degrade to poster + native play.
            const p = video.play();
            if (p && p.catch) p.catch(() => hideSpin());

            // Broken/missing file: toast, then skip (or close if solo trailer).
            // isConnected guards: events from an already-swapped/closed overlay
            // must not fire toasts or navigation.
            video.addEventListener('error', () => {
                if (!overlay.isConnected) return;
                hideSpin();
                this._showToast('Trailer unavailable');
                setTimeout(() => {
                    if (!overlay.isConnected) return;
                    if (reel.length > 1) goTo(1); else close();
                }, 1200);
            }, { once: true });

            // Auto-advance with an up-next cue; a solo trailer closes instead of
            // stalling on the ended frame (goTo no-ops when reel < 2).
            video.addEventListener('ended', () => {
                if (!overlay.isConnected) return;
                if (reel.length > 1) {
                    const nxt = reel[(reelIdx + 1) % reel.length];
                    if (nxt) this._showToast('Next: ' + (nxt.display_title || nxt.title));
                    goTo(1);
                } else {
                    close();
                }
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
    // TMDB poster at a different rendition size (audit #5): w342 for the 3-col
    // grid (46% lighter than w500, still retina-sharp at ~126px cells), w780
    // for the full-screen close-up. Non-TMDB URLs pass through untouched.
    posterAt(url, size) {
        return url && url.includes('/w500/') ? url.replace('/w500/', '/' + size + '/') : url;
    },

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

    // Compact "Mon D" date for the packed-view per-cell muted date label.
    shortDate(iso) {
        if (!iso) return '';
        const d = new Date(iso + 'T12:00:00');
        if (isNaN(d)) return '';
        return d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
    },
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => NRWMobile.init());
