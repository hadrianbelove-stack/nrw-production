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

    // Shared config — loaded from assets/shared-config.js
    SERVICE_MAP: NRWConfig.SERVICE_MAP,
    VOD_SERVICE_MAP: NRWConfig.VOD_SERVICE_MAP,
    resolveService: NRWConfig.resolveService.bind(NRWConfig),
    resolveVODService: NRWConfig.resolveVODService.bind(NRWConfig),
    abbreviateCountry: NRWConfig.abbreviateCountry.bind(NRWConfig),

    formatShortDate(dateStr) {
        const [y, m, d] = dateStr.split('-');
        const dt = new Date(y, m - 1, d);
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    },

    getScreeningRibbon(movie) {
        const info = movie.virtual_screening_info || {};
        const name = info.screening_name || 'Virtual Screening';
        const startDate = movie.digital_date;
        const endDate = info.available_end;
        let dateRange = '';
        if (startDate && endDate) {
            dateRange = `Virtual Screening ${this.formatShortDate(startDate)} – ${this.formatShortDate(endDate)}`;
        } else if (endDate) {
            dateRange = `Virtual Screening thru ${this.formatShortDate(endDate)}`;
        } else {
            dateRange = 'Virtual Screening';
        }
        return `<div class="screening-ribbon-top">`
            + `<div class="sr-name">${name}</div>`
            + `<div class="sr-dates">${dateRange}</div>`
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
                return !!m.digital_date;
            });

            // Sort by date descending, staff picks first within each date
            this.sortMovies();

            // Setup event listeners
            this.setupFilters();
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
            this.render();

            // Scroll to top
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
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
            if (filters.size === 0) return true;

            // OR logic: movie must match ANY selected filter
            for (const filter of filters) {
                switch (filter) {
                    case 'big-time':
                        if (movie.categories?.is_big_time || movie.categories?.tier === 'big_time') return true;
                        break;
                    case 'indie':
                        if (movie.categories?.is_indie || movie.categories?.tier === 'indie') return true;
                        break;
                    case 'staff-picks':
                        if (movie.categories?.is_staff_pick || this.staffPicks.includes(movie.id)) return true;
                        break;
                    case 'foreign':
                        if (movie.categories?.is_foreign ||
                            (movie.original_language && movie.original_language !== 'en')) return true;
                        break;
                    case 'series':
                        if (movie.content_type === 'limited_series') return true;
                        break;
                    case 'restorations':
                        if (movie.categories?.is_restoration === true) return true;
                        break;
                    case 'documentary':
                        if (movie.categories?.is_documentary === true) return true;
                        break;
                    case 'virtual-screenings':
                        if (movie.categories?.is_virtual_screening === true) return true;
                        break;
                }
            }
            return false;
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

        movies.forEach(movie => {
            const date = movie.digital_date.substring(0, 10);

            // Add date header when date changes
            if (date !== lastDate) {
                feed.appendChild(this.createDateHeader(date));
                lastDate = date;
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
                        <img class="poster"
                             src="${movie.poster || 'https://via.placeholder.com/300x450?text=No+Poster'}"
                             alt="${movie.title}"
                             loading="lazy">
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
                    <div class="watch-stack">
                        ${watchButton}
                    </div>
                    <div class="buttons-row">
                        ${this.getTrailerButton(movie)}
                        ${this.getWikiButton(movie)}
                    </div>
                    <div class="score-row">
                        ${this.getRTButton(movie)}
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

        // Pre-order: future release date with no watch links yet
        const today = new Date().toISOString().split('T')[0];
        if (movie.digital_date > today) {
            const vodArr = Array.isArray(watchLinks.vod) ? watchLinks.vod
                : (watchLinks.vod?.service ? [watchLinks.vod] : []);
            const hasAnyLink = watchLinks.streaming?.link || vodArr.some(v => v.link);
            if (!hasAnyLink) {
                return '<span class="poster-badge badge-preorder">PRE-ORDER</span>';
            }
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
            badgeClass = 'badge-vod';
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
            const style = resolved ? `background:${resolved.bg};color:${resolved.text}` : 'background:#00d4aa;color:#000';

            return `<a href="${link}" target="_blank" rel="noopener" class="btn-watch-full" style="${style}">${displayName}</a>`;
        }

        // Fall back to VOD — separate Amazon + Apple TV buttons
        const vodEntries = Array.isArray(watchLinks.vod) ? watchLinks.vod
            : (watchLinks.vod?.service ? [watchLinks.vod] : []);
        const vodWithLinks = vodEntries.filter(v => v.link);
        if (vodWithLinks.length > 0) {
            const vodBtns = vodWithLinks.map(vod => {
                const vodType = NRWMobile.resolveVODService(vod.service, vod.link);
                if (!vodType) return '';
                return `<a href="${vod.link}" target="_blank" rel="noopener" class="btn-watch-vod" style="${vodType.style}">${vodType.label}</a>`;
            }).filter(Boolean);
            if (vodBtns.length === 1) return vodBtns[0].replace('btn-watch-vod', 'btn-watch-full');
            return `<div class="vod-row">${vodBtns.join('')}</div>`;
        }

        // Pre-order links (future release — no streaming/VOD links found)
        const preOrderLinks = movie.pre_order_links || {};
        if (preOrderLinks.amazon) {
            return `<a href="${preOrderLinks.amazon}" target="_blank" rel="noopener" class="btn-watch-full" style="background:#ff9900;color:#000">Pre-Order</a>`;
        }
        if (preOrderLinks.apple_tv) {
            return `<a href="${preOrderLinks.apple_tv}" target="_blank" rel="noopener" class="btn-watch-full" style="background:#000;color:#fff">Pre-Order</a>`;
        }

        return '';
    },

    getTrailerButton(movie) {
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        if (!trailerUrl) return '';
        const isMP4 = (() => { try { return new URL(trailerUrl).pathname.endsWith('.mp4'); } catch { return trailerUrl.endsWith('.mp4'); } })();
        if (isMP4) {
            return `<a href="#" onclick="NRWMobile.showTrailer('${movie.id}');return false;" class="btn-equal btn-trailer">Trailer</a>`;
        }
        return `<a href="${trailerUrl}" target="_blank" rel="noopener" class="btn-equal btn-trailer">Trailer</a>`;
    },

    getRTButton(movie) {
        if (!movie.links?.rt) return '';
        const rtText = movie.rt_score ? `RT ${movie.rt_score}` : 'RT';
        return `<a href="${movie.links.rt}" target="_blank" rel="noopener" class="btn-equal btn-rt">${rtText}</a>`;
    },

    getIMDbButton(movie) {
        if (movie.imdb_rating) {
            const imdbUrl = movie.links?.imdb;
            if (imdbUrl) {
                return `<a href="${imdbUrl}" target="_blank" rel="noopener" class="btn-equal btn-imdb">IMDb ${movie.imdb_rating}</a>`;
            }
            return `<span class="btn-equal btn-imdb" style="opacity:0.5">IMDb ${movie.imdb_rating}</span>`;
        }
        return '';
    },

    getScoreBadges(movie) {
        let badges = '';
        if (movie.rt_score && movie.links?.rt) {
            badges += `<a href="${movie.links.rt}" target="_blank" rel="noopener" class="card-score-badge rt">RT ${movie.rt_score}</a>`;
        }
        if (movie.imdb_rating) {
            const imdbUrl = movie.links?.imdb;
            if (imdbUrl) {
                badges += `<a href="${imdbUrl}" target="_blank" rel="noopener" class="card-score-badge imdb">${movie.imdb_rating}</a>`;
            } else {
                badges += `<span class="card-score-badge imdb">${movie.imdb_rating}</span>`;
            }
        }
        return badges ? `<div class="card-score-overlay">${badges}</div>` : '';
    },

    getWikiButton(movie) {
        if (!movie.links?.wikipedia) return '';
        return `<a href="${movie.links.wikipedia}" target="_blank" rel="noopener" class="btn-equal btn-wiki">Wiki</a>`;
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
            </div>
        `;

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        const close = () => { overlay.remove(); document.body.style.overflow = ''; document.removeEventListener('keydown', onKeydown); };
        const onKeydown = e => { if (e.key === 'Escape') close(); };
        document.addEventListener('keydown', onKeydown);

        overlay.querySelector('#trailer-close').addEventListener('click', close);

        // Tap outside the video box (above/below) closes the overlay
        overlay.addEventListener('click', e => {
            if (!overlay.querySelector('#trailer-video-wrap').contains(e.target)) close();
        });

        overlay.querySelector('video').addEventListener('ended', close);

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
