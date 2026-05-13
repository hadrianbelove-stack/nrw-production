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

    // Filter descriptions — shown when a single filter is active
    FILTER_DESCRIPTIONS: {
        'studio': {
            title: 'Studio',
            text: 'The wide releases, the studio fare, the main-streamers. Not saying they\'re good, not saying they\'re bad, but these are the movies that have either entered or tried to enter the mainstream conversation.'
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
            text: 'Non-English language films from around the world. Some are massive in their home countries, some are intimate art-house pieces.'
        },
        'series': {
            title: 'Miniseries',
            text: 'Not movies \u2014 limited series. The kind you can finish in a weekend. Prestige mini-series and limited runs that deserve the same attention as a good film.'
        },
        'restorations': {
            title: 'Reissues',
            text: 'Classic and catalog titles with new digital life. Films that have been restored, remastered, or newly reissued on streaming platforms.'
        },
        'documentary': {
            title: 'Documentary',
            text: 'Non-fiction filmmaking. Documentaries covering real stories, real people, and real events \u2014 now available to stream at home.'
        },
        'virtual-screenings': {
            title: 'Virtual Screenings',
            text: 'Currently playing at film festivals. These aren\'t streaming yet \u2014 they\'re in theaters, at festivals, or doing the circuit.'
        },
        'pre-orders': {
            title: 'Pre-Orders',
            text: 'Coming soon. These movies have confirmed digital release dates and are available to pre-order now.'
        },
        'exploitation': {
            title: 'Exploitation',
            text: 'The genre stuff. Horror, thrillers, action \u2014 the movies that know exactly what they are and lean all the way in.'
        }
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

            const dateA = new Date(a.digital_date);
            const dateB = new Date(b.digital_date);
            if (dateB.getTime() !== dateA.getTime()) return dateB - dateA;

            // Same date: staff picks first
            const aStaff = a.categories?.is_staff_pick || this.staffPicks.includes(String(a.id));
            const bStaff = b.categories?.is_staff_pick || this.staffPicks.includes(String(b.id));
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
    },

    updateFilterDesc() {
        const desc = this.dom.filterDesc;
        if (!desc) return;

        // Only show when exactly one filter is active
        if (this.activeFilters.size === 1) {
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
            // Category filters (OR logic)
            if (filters.size > 0) {
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
                        case 'exploitation':
                            if (movie.categories?.is_exploitation) matchesAny = true;
                            break;
                    }
                    if (matchesAny) break;
                }
                if (!matchesAny) return false;
            }

            // Search filter
            if (this.searchQuery) {
                const q = this.searchQuery;
                const title = (movie.title || '').toLowerCase();
                const director = (movie.crew?.director || movie.director || '').toLowerCase();
                const synopsis = (movie.synopsis || '').toLowerCase();
                const genres = (movie.genres || []).join(' ').toLowerCase();
                const country = (movie.country || '').toLowerCase();
                const year = String(movie.year || '');
                const cast = (movie.crew?.cast || []).join(' ').toLowerCase();

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

        // Pre-compute grid entries (date dividers + movie items)
        this.gridEntries = [];
        let lastDate = '';
        let preorderStarted = false;

        this.filteredMovies.forEach((movie, i) => {
            if (movie._is_preorder) {
                if (!preorderStarted) {
                    preorderStarted = true;
                    this.gridEntries.push({ type: 'date', dateStr: 'pre-order' });
                }
            } else {
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
                grid.appendChild(this.createDateDivider(entry.dateStr));
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

    createDateDivider(dateStr) {
        const card = document.createElement('div');
        card.className = 'date-divider-card';

        if (dateStr === 'pre-order') {
            card.innerHTML =
                '<div class="date-bar"><div class="date-day">PRE-ORDER</div></div>' +
                '<div class="date-body">' +
                  '<div class="date-number" style="font-size:1.2rem">SOON</div>' +
                  '<div class="date-chevrons"><span>\u203A</span><span>\u203A</span><span>\u203A</span><span>\u203A</span><span>\u203A</span></div>' +
                '</div>';
            return card;
        }

        const d = new Date(dateStr + 'T12:00:00');
        const weekday = d.toLocaleDateString('en', { weekday: 'short' }).toUpperCase();
        const day = d.getDate();
        const month = d.toLocaleDateString('en', { month: 'short' }).toUpperCase();

        card.innerHTML =
            '<div class="date-bar"><div class="date-day">' + weekday + '</div></div>' +
            '<div class="date-body">' +
              '<div class="date-number">' + day + '</div>' +
              '<div class="date-month">' + month + '</div>' +
              '<div class="date-chevrons"><span>\u203A</span><span>\u203A</span><span>\u203A</span><span>\u203A</span><span>\u203A</span></div>' +
            '</div>';
        return card;
    },

    createGridItem(movie, index) {
        const isStaffPick = movie.categories?.is_staff_pick || this.staffPicks.includes(String(movie.id));
        const isScreening = movie.categories?.is_virtual_screening;

        const item = document.createElement('div');
        item.className = 'grid-item' + (isScreening ? ' screening-movie' : '');

        // Poster container
        const posterWrap = document.createElement('div');
        posterWrap.className = 'grid-item-poster';

        if (movie.poster) {
            const img = document.createElement('img');
            img.src = movie.poster;
            img.alt = movie.title || '';
            img.loading = 'lazy';
            img.onerror = function() { this.style.display = 'none'; };
            posterWrap.appendChild(img);
        } else {
            const fallback = document.createElement('div');
            fallback.style.cssText = 'width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#1a1a2e;font-size:0.45rem;color:#888;text-align:center;padding:4px';
            fallback.textContent = movie.display_title || movie.title || '';
            posterWrap.appendChild(fallback);
        }

        if (isScreening) {
            const banner = document.createElement('span');
            banner.className = 'screening-banner';
            banner.textContent = 'Virtual Screening';
            posterWrap.appendChild(banner);
        }
        if (isStaffPick) {
            const badge = document.createElement('span');
            badge.className = 'staff-pick-badge';
            badge.textContent = 'Staff Pick';
            posterWrap.appendChild(badge);
        }
        if (movie._is_preorder) {
            const badge = document.createElement('span');
            badge.className = 'preorder-badge';
            badge.textContent = 'Pre-Order';
            posterWrap.appendChild(badge);
        }

        item.appendChild(posterWrap);

        // Title + meta info
        const info = document.createElement('div');
        info.className = 'grid-item-info';

        const title = document.createElement('div');
        title.className = 'grid-item-title';
        title.textContent = movie.display_title || movie.title || '';
        info.appendChild(title);

        const director = movie.crew?.director || movie.director || '';
        const country = NRWConfig.abbreviateCountry(movie.country) || '';
        const metaParts = [director, country].filter(Boolean);
        if (metaParts.length) {
            const meta = document.createElement('div');
            meta.className = 'grid-item-meta';
            meta.textContent = metaParts.join(' \u00b7 ');
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

        // Score badges on poster
        let scores = '';
        if (movie.rt_score && movie.links?.rt) {
            scores += '<a href="' + movie.links.rt + '" target="_blank" rel="noopener" class="score-badge rt">' +
                '<img class="score-logo" src="../assets/logos/rt.png" alt="RT"> ' + movie.rt_score + '</a>';
        }
        if (movie.imdb_rating) {
            const href = movie.links?.imdb || '#';
            scores += '<a href="' + href + '" target="_blank" rel="noopener" class="score-badge imdb">' +
                '<img class="score-logo" src="../assets/logos/imdb.png" alt="IMDb"> ' + movie.imdb_rating + '</a>';
        }
        if (movie.metacritic_score && movie.metacritic_score !== '0') {
            const href = movie.links?.metacritic || '#';
            scores += '<a href="' + href + '" target="_blank" rel="noopener" class="score-badge meta">' +
                '<img class="score-logo" src="../assets/logos/metacritic.png" alt="MC"> ' + movie.metacritic_score + '</a>';
        }
        this.dom.posterScores.innerHTML = scores;
    },

    // ===== BOTTOM SHEET (View 2) =====
    updateSheetContent(movie, direction) {
        const content = this.dom.sheetContent;

        if (direction) {
            const cls = direction === 'left' ? 'slide-left-enter' : 'slide-right-enter';
            content.classList.add(cls);
            setTimeout(() => content.classList.remove(cls), 250);
        }

        const isStaffPick = movie.categories?.is_staff_pick || this.staffPicks.includes(String(movie.id));
        const isScreening = movie.categories?.is_virtual_screening;
        const screeningInfo = movie.virtual_screening_info || {};

        // Teal line: D: Director · Country · Year
        const topParts = [];
        if (movie.crew?.director) topParts.push('D: ' + this.esc(movie.crew.director));
        else if (movie.director) topParts.push('D: ' + this.esc(movie.director));
        if (movie.country) topParts.push(this.esc(movie.country));
        if (movie.year) topParts.push(this.esc(movie.year));

        // Gray line: Runtime · Cast · Genre
        let metaParts = '';
        if (movie.runtime) metaParts += '<span>' + this.esc(this.formatRuntime(movie.runtime)) + '</span>';
        const cast = movie.crew?.cast;
        if (cast?.length) metaParts += '<span>' + this.esc(cast.slice(0, 3).join(', ')) + '</span>';
        if (movie.genres?.length) metaParts += '<span>' + this.esc(movie.genres.slice(0, 3).join(', ')) + '</span>';

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
            (isStaffPick ? ' <span style="color:var(--crimson);font-size:0.7rem">\u2605 STAFF PICK</span>' : '') +
            '</div>' +
            '<div class="sheet-date">' + topParts.join(' \u00b7 ') + '</div>' +
            '<div class="sheet-meta">' + metaParts + '</div>' +
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
            if (streaming) {
                html += '<div class="sheet-section-label">Streaming</div>' +
                    '<div class="sheet-providers">' + this.renderProviderBadge(streaming) + '</div>';
            }
            // Filter out screening VODs (already shown as ticket button above)
            const rentVod = isScreening
                ? vodList.filter(v => v.resolvedKey !== 'screening')
                : vodList;
            if (rentVod.length > 0) {
                html += '<div class="sheet-section-label">Rent / Buy</div>' +
                    '<div class="sheet-providers">' +
                    rentVod.map(v => this.renderProviderBadge(v)).join('') + '</div>';
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
                html += '<div class="sheet-pq">' +
                    '<span class="sheet-pq-badge ' + badgeClass + '">' + badgeText + '</span>' +
                    '<q class="sheet-pq-text">' + this.esc(q.text || '') + '</q>' +
                    (attribution ? '<cite class="sheet-pq-cite">' + this.esc(attribution) + '</cite>' : '') +
                    '</div>';
            });
        }

        // Synopsis
        html += '<div class="sheet-section-label">Synopsis</div>' +
            '<div class="sheet-synopsis">' + this.esc(movie.synopsis || 'No synopsis available.') + '</div>';

        html += '<div style="height:50px"></div>';

        content.innerHTML = html;
        content.scrollTop = 0;
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

        // watch_links.streaming can be array or single object
        let service = null, link = null;
        const streamingWl = wl.streaming;
        if (Array.isArray(streamingWl) && streamingWl.length > 0) {
            service = streamingWl[0].service;
            link = streamingWl[0].link;
        } else if (streamingWl?.service) {
            service = streamingWl.service;
            link = streamingWl.link;
        }

        if (!service && providers.streaming?.length > 0) {
            service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
        }

        if (!service) return null;

        const resolved = this.resolveService(service);
        return {
            name: resolved?.name || service,
            wideLogo: resolved?.wideLogo,
            serviceKey: resolved?.class,
            link: link || null,
            resolvedKey: resolved?.class
        };
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
                isFallback: !!resolved.fallback
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

            // Tap → open sheet
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
            if (dy > 100) {
                // Dismiss
                sheet.style.transform = '';
                this.setView(1);
            } else {
                // Snap back
                sheet.style.transform = '';
            }
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
        overlay.innerHTML =
            '<button style="position:absolute;top:12px;right:16px;background:none;border:none;' +
            'color:white;font-size:2rem;cursor:pointer;z-index:10">&times;</button>' +
            '<video controls autoplay playsinline style="max-width:95%;max-height:70vh;border-radius:8px">' +
            '<source src="' + this.esc(url) + '" type="video/mp4"></video>' +
            '<div style="color:#888;font-size:0.8rem;margin-top:10px">' + title + '</div>';

        document.body.appendChild(overlay);

        const close = () => overlay.remove();
        overlay.querySelector('button').addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        document.addEventListener('keydown', function onKey(e) {
            if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); }
        });
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
