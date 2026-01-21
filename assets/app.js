const NRW = {
    allMovies: [],
    filteredMovies: [],
    featuredMovies: [],
    currentFilter: 'all',
    currentPage: 1,
    moviesPerPage: 60,
    
    // Helper function for Wikipedia URLs with safe fallbacks
    wikiUrlFor(movie) {
        const title = movie.title || '';
        const year = movie.year || (movie.digital_date ? new Date(movie.digital_date).getFullYear() : '');
        const stored = movie.links && typeof movie.links.wikipedia === 'string' && movie.links.wikipedia.trim();
        if (stored) return stored;  // trust prebuilt link from generate_data.py
        const q = encodeURIComponent(`${title} ${year} film`.trim());
        return `https://en.wikipedia.org/w/index.php?search=${q}`;  // safe fallback, no broken guesses
    },
    
    async init() {
        try {
            // Parse URL parameters for pagination state
            this.parseUrlParams();

            // Load movie data
            const movieResponse = await fetch('data.json');
            const data = await movieResponse.json();

            // Load filter data (featured list) from data.json
            this.featuredMovies = data.featured || [];

            if (data.movies && data.movies.length > 0) {
                const today = new Date();
                this.allMovies = data.movies.filter(m => {
                    if (!m.digital_date) return false;
                    return new Date(m.digital_date) <= today;
                });

                this.setupFilterEventListeners();
                this.applyFilter();
                this.renderPaginatedWall();
            } else {
                document.getElementById('wall').innerHTML = '<p>No movies in database</p>';
            }
        } catch (err) {
            console.error('Load failed:', err);
            document.getElementById('wall').innerHTML = '<p>Failed to load movies</p>';
        }
    },

    parseUrlParams() {
        const urlParams = new URLSearchParams(window.location.search);
        const page = parseInt(urlParams.get('page'));
        if (page && page > 0) {
            this.currentPage = page;
        }
    },

    updateUrl() {
        const url = new URL(window.location);
        if (this.currentPage > 1) {
            url.searchParams.set('page', this.currentPage);
        } else {
            url.searchParams.delete('page');
        }
        window.history.replaceState({}, '', url);
    },

    setupFilterEventListeners() {
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                // Update active button
                filterButtons.forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');

                // Update filter and re-render
                this.currentFilter = e.target.dataset.filter;
                this.currentPage = 1; // Reset to page 1 when changing filters
                this.applyFilter();
                this.renderPaginatedWall();
            });
        });
    },

    applyFilter() {
        const filter = this.currentFilter;

        this.filteredMovies = this.allMovies.filter(movie => {
            const movieId = movie.id;
            const isFeatured = this.featuredMovies.includes(movieId);

            switch (filter) {
                case 'featured':
                    return isFeatured; // Show only featured movies
                case 'all':
                default:
                    return true; // Show all movies
            }
        });
    },

    renderPaginatedWall() {
        const sortedMovies = [...this.filteredMovies].sort((a, b) => {
            return new Date(b.digital_date) - new Date(a.digital_date);
        });

        const totalPages = Math.ceil(sortedMovies.length / this.moviesPerPage);
        const startIndex = (this.currentPage - 1) * this.moviesPerPage;
        const endIndex = startIndex + this.moviesPerPage;
        const currentPageMovies = sortedMovies.slice(startIndex, endIndex);

        this.renderWall(currentPageMovies);
        this.renderPaginationControls(totalPages);
        this.updateUrl();
    },

    renderPaginationControls(totalPages) {
        const paginationContainer = document.getElementById('pagination');
        const paginationBottomContainer = document.getElementById('pagination-bottom');

        if (totalPages <= 1) {
            if (paginationContainer) paginationContainer.innerHTML = '';
            if (paginationBottomContainer) paginationBottomContainer.innerHTML = '';
            return;
        }

        let html = `
            <div class="pagination-info">
                Showing ${(this.currentPage - 1) * this.moviesPerPage + 1}-${Math.min(this.currentPage * this.moviesPerPage, this.filteredMovies.length)} of ${this.filteredMovies.length} movies
            </div>
            <nav class="pagination-nav" aria-label="Movie pagination">
        `;

        // Previous button
        if (this.currentPage > 1) {
            html += `<button onclick="NRW.goToPage(${this.currentPage - 1})" aria-label="Previous page">&laquo; Previous</button>`;
        }

        // Page numbers (show current and 2 pages on each side)
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, this.currentPage + 2);

        if (startPage > 1) {
            html += `<button onclick="NRW.goToPage(1)">1</button>`;
            if (startPage > 2) html += '<span class="pagination-ellipsis">...</span>';
        }

        for (let i = startPage; i <= endPage; i++) {
            const isActive = i === this.currentPage ? ' active' : '';
            html += `<button onclick="NRW.goToPage(${i})" class="pagination-btn${isActive}" ${isActive ? 'aria-current="page"' : ''}>${i}</button>`;
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) html += '<span class="pagination-ellipsis">...</span>';
            html += `<button onclick="NRW.goToPage(${totalPages})">${totalPages}</button>`;
        }

        // Next button
        if (this.currentPage < totalPages) {
            html += `<button onclick="NRW.goToPage(${this.currentPage + 1})" aria-label="Next page">Next &raquo;</button>`;
        }

        html += '</nav>';

        if (paginationContainer) paginationContainer.innerHTML = html;
        if (paginationBottomContainer) paginationBottomContainer.innerHTML = html;
    },

    goToPage(page) {
        this.currentPage = page;
        this.renderPaginatedWall();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    },


    renderWall(movies) {
        const wall = document.getElementById('wall');

        // Sort by date descending, then featured first within each date
        movies.sort((a, b) => {
            const dateA = new Date(a.digital_date);
            const dateB = new Date(b.digital_date);
            if (dateB.getTime() !== dateA.getTime()) {
                return dateB - dateA;  // Newest first
            }
            // Same date: featured movies first
            const aFeatured = this.featuredMovies.includes(a.id);
            const bFeatured = this.featuredMovies.includes(b.id);
            if (aFeatured && !bFeatured) return -1;
            if (!aFeatured && bFeatured) return 1;
            return 0;
        });

        let html = '';
        let lastDate = '';
        
        movies.forEach(movie => {
            const date = movie.digital_date.substring(0, 10);
            
            // Add inline date divider card when date changes
            if (date !== lastDate) {
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
            if (movie.runtime) {
                bottomMetadata.push(`${movie.runtime} min`);
            }
            const bottomInfo = bottomMetadata.join(' | ');

            // Build platform-based watch buttons (SVOD, Amazon, Apple)
            const buildPlatformButtons = (movie) => {
                const watchLinks = movie.watch_links || {};
                let buttonsHtml = '';

                // 1. SVOD Streaming Button (if available)
                if (watchLinks.streaming?.service && watchLinks.streaming?.link) {
                    const service = watchLinks.streaming.service;
                    const link = watchLinks.streaming.link;

                    // Shorten platform names for display
                    let displayName = service;
                    if (service.toLowerCase().includes('amazon') || service.toLowerCase().includes('prime')) {
                        displayName = 'PRIME';
                    } else if (service.toLowerCase().includes('disney')) {
                        displayName = 'DISNEY+';
                    } else if (service.toLowerCase().includes('hbo') || service.toLowerCase().includes('max')) {
                        displayName = 'MAX';
                    } else if (service.toLowerCase().includes('netflix')) {
                        displayName = 'NETFLIX';
                    } else if (service.toLowerCase().includes('hulu')) {
                        displayName = 'HULU';
                    } else if (service.toLowerCase().includes('peacock')) {
                        displayName = 'PEACOCK';
                    } else {
                        displayName = service.toUpperCase();
                    }

                    // All streaming services use the same style
                    // Use logo images for certain services, text for others
                    if (displayName === 'PRIME') {
                        buttonsHtml += `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on Prime Video"><img src="logos%20and%20images/amazon%20prime.png" alt="Prime Video" class="btn-logo"></a>`;
                    } else if (displayName === 'NETFLIX') {
                        buttonsHtml += `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on Netflix"><img src="logos%20and%20images/netflix%20square%20logo.png" alt="Netflix" class="btn-logo"></a>`;
                    } else {
                        buttonsHtml += `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on ${service}">${displayName}</a>`;
                    }
                }

                // 2. Purchase Buttons (Amazon + Apple)
                let amazonLink = null;
                let appleLink = null;

                // Check for Amazon in VOD
                if (watchLinks.vod?.service?.toLowerCase().includes('amazon') && watchLinks.vod?.link) {
                    amazonLink = watchLinks.vod.link;
                }

                // Check for Apple in VOD
                if (watchLinks.vod?.service?.toLowerCase().includes('apple') && watchLinks.vod?.link) {
                    appleLink = watchLinks.vod.link;
                }

                // Add purchase buttons directly (not in separate wrapper)
                if (amazonLink) {
                    buttonsHtml += `<a href="${amazonLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-purchase" aria-label="Rent/Buy on Amazon"><img src="logos%20and%20images/pngimg.com%20-%20amazon_PNG17.png" alt="Amazon" class="btn-logo"></a>`;
                }

                if (appleLink) {
                    buttonsHtml += `<a href="${appleLink}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-purchase" aria-label="Rent/Buy on Apple TV"><img src="logos%20and%20images/apple%20logo.png" alt="Apple" class="btn-logo"></a>`;
                }

                // If no valid links at all, show disabled placeholder
                if (!buttonsHtml) {
                    buttonsHtml = '<a href="#" class="watch-btn watch-btn-disabled" aria-disabled="true" title="Link not available" tabindex="-1">NOT AVAILABLE</a>';
                }

                // Wrap all buttons in a single container
                return `<div class="watch-buttons">${buttonsHtml}</div>`;
            };

            const platformButtons = buildPlatformButtons(movie);

            // Info links - Only Trailer, RT, Wiki
            let infoLinks = [];

            if (movie.links?.trailer) {
                infoLinks.push(`<a href="${movie.links.trailer}" target="_blank" class="info-btn">Trailer</a>`);
            }

            if (movie.links?.rt) {
                const rtText = movie.rt_score ? `RT ${movie.rt_score}` : 'RT';
                const rtClass = movie.rt_score ? 'info-btn' : 'info-btn info-btn-neutral';
                infoLinks.push(`<a href="${movie.links.rt}" target="_blank" class="${rtClass}">${rtText}</a>`);
            }

            if (movie.links?.wikipedia !== null) {
                infoLinks.push(`<a href="${this.wikiUrlFor(movie)}" target="_blank" class="info-btn">Wiki</a>`);
            }

            const isFeatured = this.featuredMovies.includes(movie.id);
            const featuredClass = isFeatured ? ' featured-movie' : '';
            const featuredBadge = isFeatured ? '<div class="featured-badge">FEATURED</div>' : '';

            html += `
            <div class="movie-container${featuredClass}">
                ${featuredBadge}
                <div class="movie-card">
                    <div class="card-inner">
                        <div class="card-front">
                            <img src="${movie.poster || 'assets/no-poster.jpg'}"
                                 onerror="this.src='assets/no-poster.jpg'; this.onerror=null;">
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
                    <span class="director">${movie.crew?.director || 'Unknown Director'}</span> • <span class="country">${(movie.country === 'United States of America' ? 'USA' : movie.country) || 'Unknown Country'}</span>
                </div>
            </div>`;
        });
        
        wall.innerHTML = html;
        
        // Click handler for flipping
        const newWall = document.getElementById('wall');
        newWall.addEventListener('click', (e) => {
            if (e.target.tagName === 'A') return;
            // Only flip if clicking on the actual card, not the info below
            if (e.target.closest('.movie-info')) return;
            const card = e.target.closest('.movie-card');
            if (card) card.classList.toggle('flipped');
        });
    }
};

// Start on page load
document.addEventListener('DOMContentLoaded', () => NRW.init());

// Mobile swipe navigation
(function() {
    let touchStartX = 0;
    let touchStartY = 0;
    let touchEndX = 0;
    let touchEndY = 0;

    const wall = document.getElementById('wall');
    if (!wall) return;

    wall.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
    }, { passive: true });

    wall.addEventListener('touchend', (e) => {
        touchEndX = e.changedTouches[0].screenX;
        touchEndY = e.changedTouches[0].screenY;
        handleSwipe();
    }, { passive: true });

    function handleSwipe() {
        const deltaX = touchEndX - touchStartX;
        const deltaY = touchEndY - touchStartY;
        const minSwipe = 80; // minimum swipe distance

        // Only handle horizontal swipes (ignore vertical scrolling)
        if (Math.abs(deltaX) < minSwipe || Math.abs(deltaY) > Math.abs(deltaX)) return;

        // Swipe left = next page, swipe right = prev page
        if (deltaX < 0 && NRW.currentPage < Math.ceil(NRW.filteredMovies.length / NRW.moviesPerPage)) {
            NRW.currentPage++;
            NRW.renderPaginatedWall();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } else if (deltaX > 0 && NRW.currentPage > 1) {
            NRW.currentPage--;
            NRW.renderPaginatedWall();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }
})();