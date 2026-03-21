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
        plex:      { class: 'plex',      name: 'PLEX',      btnName: 'Plex',      bg: '#E5A00D', text: '#000',  matches: ['plex'] },
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
            const response = await fetch('../data.json');
            const data = await response.json();

            // Load staff picks
            this.staffPicks = data.staff_picks || data.featured || [];

            // Filter to only show movies with digital_date in the past
            const today = new Date();
            this.allMovies = (data.movies || []).filter(m => {
                if (m.hidden) return false;
                if (!m.digital_date) return false;
                return new Date(m.digital_date) <= today;
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
                        if (movie.categories?.tier === 'big_time') return true;
                        break;
                    case 'niche':
                        if (movie.categories?.tier === 'niche') return true;
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
                    case 'plex':
                        if (movie.plex && movie.plex.deep_link) return true;
                        break;
                    case 'restorations':
                        if (movie.categories?.is_restoration === true) return true;
                        break;
                    case 'documentary':
                        if (movie.categories?.is_documentary === true) return true;
                        break;
                    case 'festivals':
                        if (movie.categories?.is_festival === true) return true;
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

    createFlipCard(movie) {
        const isStaffPick = movie.categories?.is_staff_pick || this.staffPicks.includes(movie.id);

        const card = document.createElement('div');
        card.className = `flip-card${isStaffPick ? ' staff-pick' : ''}`;
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
                        ${movie.categories?.is_festival ? `<div class="festival-ribbon">${(movie.festival_info?.festival_name || 'FESTIVAL SCREENING').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>` : ''}
                        ${isStaffPick ? '<span class="staff-badge">STAFF PICK</span>' : ''}
                    </div>
                </div>
                <div class="flip-back">
                    <div class="back-title-row">
                        <h2 class="back-title">${movie.title || 'Untitled'}</h2>
                        ${movie.year ? `<span class="back-year">(${movie.year})</span>` : ''}
                        ${isStaffPick ? '<span class="back-staff-badge">STAFF PICK</span>' : ''}
                        ${movie.digital_date ? `<span class="back-date">${this.formatShortDate(movie.digital_date)}</span>` : ''}
                    </div>
                    <p class="back-synopsis">${movie.synopsis || 'No synopsis available.'}</p>
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
                        ${this.getWikiButton(movie)}
                    </div>
                </div>
            </div>
        `;

        // Add flip handler
        card.addEventListener('click', (e) => {
            // Don't flip if clicking a button/link
            if (e.target.closest('a, button')) return;
            card.classList.toggle('flipped');
        });

        return card;
    },

    getStreamingBadge(movie) {
        const watchLinks = movie.watch_links || {};
        const providers = movie.providers || {};

        // Get streaming service name
        let service = watchLinks.streaming?.service;
        if (!service && providers.streaming?.length > 0) {
            service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
        }

        if (!service) {
            // Check for VOD (array or single dict)
            const vodArr = Array.isArray(watchLinks.vod) ? watchLinks.vod
                : (watchLinks.vod?.service ? [watchLinks.vod] : []);
            const hasFestivalVod = vodArr.some(v => {
                const s = (v.service || '').toLowerCase();
                const l = v.link || '';
                return s.includes('eventive') || l.includes('eventive.org') || l.includes('festivalplayer') || l.includes('shift72.com');
            });
            if (hasFestivalVod) {
                return '<span class="poster-badge badge-festival">FESTIVAL</span>';
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
                } else if (svc.includes('eventive') || (vod.link && (vod.link.includes('eventive.org') || vod.link.includes('festivalplayer') || vod.link.includes('shift72.com')))) {
                    label = 'Buy Ticket';
                    style = 'background:transparent;color:#FFD700;border:2px solid #FFD700';
                } else {
                    label = vod.service;
                    style = 'background:#ff9500;color:#000';
                }
                return `<a href="${vod.link}" target="_blank" rel="noopener" class="btn-equal btn-watch" style="${style}">${label}</a>`;
            }).join('');
        }

        // Check for Plex
        if (movie.plex?.web_url) {
            return `<a href="${movie.plex.web_url}" target="_blank" rel="noopener" class="btn-equal btn-watch" style="background:#E5A00D;color:#000">Plex</a>`;
        }

        return '<span class="btn-equal btn-watch" style="opacity:0.5">Watch</span>';
    },

    getTrailerButton(movie) {
        const trailerUrl = movie.links?.trailer_hosted || movie.links?.trailer;
        if (trailerUrl) {
            const isMP4 = (() => { try { return new URL(trailerUrl).pathname.endsWith('.mp4'); } catch { return trailerUrl.endsWith('.mp4'); } })();
            if (isMP4) {
                return `<a href="#" onclick="NRWMobile.showTrailer('${trailerUrl}');return false;" class="btn-equal btn-trailer">Trailer</a>`;
            }
            return `<a href="${trailerUrl}" target="_blank" rel="noopener" class="btn-equal btn-trailer">Trailer</a>`;
        }
        return '<span class="btn-equal btn-trailer" style="opacity:0.5">Trailer</span>';
    },

    getRTButton(movie) {
        const rtText = movie.rt_score ? `RT ${movie.rt_score}` : 'RT';
        if (movie.links?.rt) {
            return `<a href="${movie.links.rt}" target="_blank" rel="noopener" class="btn-equal btn-rt">${rtText}</a>`;
        }
        return `<span class="btn-equal btn-rt" style="opacity:0.5">${rtText}</span>`;
    },

    getWikiButton(movie) {
        if (movie.links?.wikipedia) {
            return `<a href="${movie.links.wikipedia}" target="_blank" rel="noopener" class="btn-equal btn-wiki">Wiki</a>`;
        }
        return '<span class="btn-equal btn-wiki" style="opacity:0.5">Wiki</span>';
    },

    // Inline trailer player for self-hosted MP4s
    showTrailer(url) {
        // Remove existing overlay if any
        const existing = document.getElementById('trailer-overlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'trailer-overlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:10000;display:flex;align-items:center;justify-content:center;flex-direction:column;';
        overlay.innerHTML = `
            <button id="trailer-close" style="position:absolute;top:12px;right:16px;background:none;border:none;color:#fff;font-size:32px;cursor:pointer;z-index:1;">&times;</button>
            <video controls autoplay playsinline style="max-width:100%;max-height:85vh;background:#000;">
                <source src="${url}" type="video/mp4">
            </video>
        `;
        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        const close = () => { overlay.remove(); document.body.style.overflow = ''; };
        overlay.querySelector('#trailer-close').addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        overlay.querySelector('video').addEventListener('ended', close);
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => NRWMobile.init());
