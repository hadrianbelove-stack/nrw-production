/**
 * NRW Mobile - Option F Flip Cards
 * Fetches data.json and renders movies as flip cards with infinite scroll
 */

const NRWMobile = {
    allMovies: [],
    filteredMovies: [],
    staffPicks: [],
    activeFilter: 'all',
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

            // Update active state
            filters.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');

            // Apply filter
            this.activeFilter = pill.dataset.filter;
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
        const filter = this.activeFilter;

        this.filteredMovies = this.allMovies.filter(movie => {
            if (filter === 'all') return true;

            switch (filter) {
                case 'big-time':
                    return movie.categories?.tier === 'big_time';
                case 'niche':
                    return movie.categories?.tier === 'niche';
                case 'staff-picks':
                    return movie.categories?.is_staff_pick || this.staffPicks.includes(movie.id);
                case 'foreign':
                    return movie.categories?.is_foreign ||
                           (movie.original_language && movie.original_language !== 'en');
                case 'plex':
                    return movie.plex && movie.plex.deep_link;
                case 'restorations':
                    return movie.categories?.is_restoration === true;
                default:
                    return true;
            }
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
            if (vodArr.some(v => v.service) || providers.rental?.length > 0) {
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
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => NRWMobile.init());
