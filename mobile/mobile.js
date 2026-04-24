/**
 * NRW Mobile - Option F Flip Cards
 * Fetches data.json and renders movies as flip cards with infinite scroll
 */

const NRWMobile = {
    allMovies: [],
    filteredMovies: [],
    staffPicks: [],
    activeFilters: new Set(),
    displayedCount: 0,
    loadIncrement: 15,
    isLoading: false,

    // Service config — single source of truth for mobile web
    // Sync with: assets/service-colors.json, mobile/mobile.css
    SERVICE_MAP: {
        netflix:   { class: 'netflix',   name: 'NETFLIX',   btnName: 'Netflix',   bg: '#E50914', text: '#fff',  matches: ['netflix'] },
        max:       { class: 'max',       name: 'MAX',       btnName: 'Max',       bg: '#B537F2', text: '#fff',  matches: ['max', 'hbo'] },
        disney:    { class: 'disney',    name: 'DISNEY+',   btnName: 'Disney+',   bg: '#113CCF', text: '#fff',  matches: ['disney'] },
        prime:     { class: 'prime',     name: 'PRIME',     btnName: 'Prime',     bg: '#00A8E1', text: '#fff',  matches: ['amazon', 'prime'] },
        hulu:      { class: 'hulu',      name: 'HULU',      btnName: 'Hulu',      bg: '#1CE783', text: '#000',  matches: ['hulu'] },
        peacock:   { class: 'peacock',   name: 'PEACOCK',   btnName: 'Peacock',   bg: '#000',    text: '#fff',  matches: ['peacock'] },
        mubi:      { class: 'mubi',      name: 'MUBI',      btnName: 'MUBI',      bg: '#DA2128', text: '#fff',  matches: ['mubi'] },
        shudder:   { class: 'shudder',   name: 'SHUDDER',   btnName: 'Shudder',   bg: '#8B0000', text: '#fff',  matches: ['shudder'] },
        criterion: { class: 'criterion', name: 'CRITERION', btnName: 'Criterion', bg: '#000',    text: '#fff',  matches: ['criterion'] },
        tubi:      { class: 'tubi',      name: 'TUBI',      btnName: 'Tubi',      bg: '#FA382F', text: '#fff',  matches: ['tubi'] },
        youtube:   { class: 'youtube',   name: 'YOUTUBE',   btnName: 'YouTube',   bg: '#FF0000', text: '#fff',  matches: ['youtube'] },
        paramount: { class: 'paramount', name: 'P+',        btnName: 'Paramount+',bg: '#0064FF', text: '#fff',  matches: ['paramount'] },
        kanopy:    { class: 'kanopy',    name: 'KANOPY',    btnName: 'Kanopy',    bg: '#1B7A43', text: '#fff',  matches: ['kanopy'] },
        hoopla:    { class: 'hoopla',    name: 'HOOPLA',    btnName: 'Hoopla',    bg: '#FC4F08', text: '#fff',  matches: ['hoopla'] },
        roku:      { class: 'roku',      name: 'ROKU',      btnName: 'Roku Ch.',  bg: '#6C3A97', text: '#fff',  matches: ['roku'] },
        pluto:     { class: 'pluto',     name: 'PLUTO',     btnName: 'Pluto TV',  bg: '#00B4E4', text: '#fff',  matches: ['pluto'] },
        crackle:   { class: 'crackle',   name: 'CRACKLE',   btnName: 'Crackle',   bg: '#FF6600', text: '#fff',  matches: ['crackle'] },
        fawesome:  { class: 'fawesome',  name: 'FAWESOME',  btnName: 'Fawesome',  bg: '#5B8DEF', text: '#fff',  matches: ['fawesome'] },
    },

    resolveService(rawName) {
        if (!rawName) return null;
        const s = rawName.toLowerCase();
        for (const entry of Object.values(this.SERVICE_MAP)) {
            if (entry.matches.some(m => s.includes(m))) return entry;
        }
        return null;
    },

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

    formatShortDate(dateStr) {
        const [y, m, d] = dateStr.split('-');
        const dt = new Date(y, m - 1, d);
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    },

    abbreviateCountry(country) {
        if (!country) return null;
        const shortened = this.countryAbbrev[country.toLowerCase()];
        if (shortened) return shortened;
        if (country !== country[0].toUpperCase() + country.slice(1).toLowerCase()) {
            return country[0].toUpperCase() + country.slice(1).toLowerCase();
        }
        return country;
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
                            ? '<div class="badge-bar gold">\u2605 VIRTUAL SCREENING \u2605</div>'
                            : isStaffPick
                            ? '<div class="badge-bar red">\u2605 STAFF PICK \u2605</div>'
                            : ''}
                        ${this.getScoreBadges(movie)}
                    </div>
                </div>
                <div class="flip-back">
                    <div class="back-content">
                    <div class="back-title-row">
                        <h2 class="back-title">${movie.title || 'Untitled'}</h2>
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
                    <div class="buttons-row">
                        ${this.getTrailerButton(movie)}
                        ${watchButton}
                    </div>
                    <div class="buttons-row">
                        ${this.getRTButton(movie)}
                        ${this.getIMDbButton(movie)}
                        ${this.getWikiButton(movie)}
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
            if (Math.abs(deltaX) > 40 && Math.abs(deltaX) > Math.abs(deltaY) * 1.5) {
                justSwiped = true;
                setTimeout(() => { justSwiped = false; }, 400);
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
            if (Math.abs(dx) < 15 && Math.abs(dy) < 15) {
                if (justSwiped) return;
                touchFlipped = true;
                setTimeout(() => { touchFlipped = false; }, 500);
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

            return `<a href="${link}" target="_blank" rel="noopener" class="btn-equal btn-watch" style="${style}">${displayName}</a>`;
        }

        // Fall back to VOD — separate Amazon + Apple TV buttons
        const vodEntries = Array.isArray(watchLinks.vod) ? watchLinks.vod
            : (watchLinks.vod?.service ? [watchLinks.vod] : []);
        const vodWithLinks = vodEntries.filter(v => v.link);
        if (vodWithLinks.length > 0) {
            return vodWithLinks.map(vod => {
                const svc = vod.service.toLowerCase();
                let label, style;
                if (svc.includes('amazon') || svc.includes('prime')) {
                    label = 'Amazon';
                    style = 'background:#ff9900;color:#000';
                } else if (svc.includes('apple') || svc.includes('itunes')) {
                    label = 'Apple TV';
                    style = 'background:#000;color:#fff';
                } else if (svc.includes('youtube')) {
                    label = 'YouTube';
                    style = 'background:#FF0000;color:#fff';
                } else if (svc.includes('eventive') || (vod.link && (vod.link.includes('eventive.org') || vod.link.includes('festivalplayer') || vod.link.includes('shift72.com')))) {
                    label = 'Buy Ticket';
                    style = 'background:transparent;color:#FFD700;border:2px solid #FFD700';
                } else {
                    return ''; // VOD whitelist: only Amazon, Apple, YouTube, and festival tickets
                }
                return `<a href="${vod.link}" target="_blank" rel="noopener" class="btn-equal btn-watch" style="${style}">${label}</a>`;
            }).join('');
        }

        // Pre-order links (future release — no streaming/VOD links found)
        const preOrderLinks = movie.pre_order_links || {};
        if (preOrderLinks.amazon) {
            return `<a href="${preOrderLinks.amazon}" target="_blank" rel="noopener" class="btn-equal btn-watch" style="background:#ff9900;color:#000">Pre-Order</a>`;
        }
        if (preOrderLinks.apple_tv) {
            return `<a href="${preOrderLinks.apple_tv}" target="_blank" rel="noopener" class="btn-equal btn-watch" style="background:#000;color:#fff">Pre-Order</a>`;
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
                return `<a href="${imdbUrl}" target="_blank" rel="noopener" class="btn-equal btn-rt">IMDb ${movie.imdb_rating}</a>`;
            }
            return `<span class="btn-equal btn-rt" style="opacity:0.5">IMDb ${movie.imdb_rating}</span>`;
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
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:10000;display:flex;align-items:center;justify-content:center;';

        overlay.innerHTML = `
            <div id="trailer-video-wrap" style="position:relative;max-width:calc(100% - 60px);">
                <button id="trailer-close" style="position:absolute;top:-14px;right:-14px;background:rgba(0,0,0,0.8);border:1px solid rgba(255,255,255,0.3);color:#fff;font-size:18px;line-height:1;width:30px;height:30px;border-radius:50%;cursor:pointer;z-index:1;display:flex;align-items:center;justify-content:center;">&times;</button>
                ${hasPrev ? `<button id="trailer-prev" style="position:absolute;left:-28px;top:50%;transform:translateY(-50%);background:none;border:none;color:rgba(255,255,255,0.6);font-size:32px;cursor:pointer;padding:8px;line-height:1;">&#8592;</button>` : ''}
                ${hasNext ? `<button id="trailer-next" style="position:absolute;right:-28px;top:50%;transform:translateY(-50%);background:none;border:none;color:rgba(255,255,255,0.6);font-size:32px;cursor:pointer;padding:8px;line-height:1;">&#8594;</button>` : ''}
                <video controls autoplay playsinline style="display:block;width:100%;background:#000;">
                    <source src="${url}" type="video/mp4">
                </video>
                <div style="text-align:center;color:#888;font-size:12px;letter-spacing:0.05em;padding-top:8px;">${movie.title || ''}</div>
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
            if (Math.abs(dx) > 50) {
                if (dx > 0 && hasPrev) { close(); this._showTrailerAt(trailerMovies, idx - 1); }
                else if (dx < 0 && hasNext) { close(); this._showTrailerAt(trailerMovies, idx + 1); }
            }
        }, { passive: true });
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => NRWMobile.init());
