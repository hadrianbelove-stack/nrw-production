const NRW = {
    allMovies: [],
    
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
            const response = await fetch('data.json');
            const data = await response.json();
            
            if (data.movies && data.movies.length > 0) {
                const today = new Date();
                this.allMovies = data.movies.filter(m => {
                    if (!m.digital_date) return false;
                    return new Date(m.digital_date) <= today;
                });
                
                this.renderWall(this.allMovies);
            } else {
                document.getElementById('wall').innerHTML = '<p>No movies in database</p>';
            }
        } catch (err) {
            console.error('Load failed:', err);
            document.getElementById('wall').innerHTML = '<p>Failed to load movies</p>';
        }
    },


    renderWall(movies) {
        const wall = document.getElementById('wall');
        
        // Sort by date descending
        movies.sort((a, b) => {
            return new Date(b.digital_date) - new Date(a.digital_date);
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
                const buttons = [];

                // 1. Check for SVOD streaming (Netflix, Mubi, Disney+, etc.)
                if (watchLinks.streaming?.service && watchLinks.streaming?.link) {
                    const service = watchLinks.streaming.service;
                    const link = watchLinks.streaming.link;

                    // Shorten platform names for display
                    const displayName = service
                        .replace('Amazon Prime Video', 'PRIME')
                        .replace('Disney Plus', 'DISNEY+')
                        .replace('HBO Max', 'HBO')
                        .toUpperCase();

                    buttons.push({
                        name: displayName,
                        link: link,
                        service: service,
                        class: 'watch-btn-stream'
                    });
                } else if (watchLinks.streaming && !watchLinks.streaming.link) {
                    // Error state for streaming
                    const service = watchLinks.streaming.service || 'STREAM';
                    buttons.push({
                        name: `${service.toUpperCase()} (MISSING)`,
                        link: '#',
                        service: service,
                        class: 'watch-btn-error',
                        disabled: true
                    });
                }

                // 2. Check for Amazon (rent OR buy)
                // Look for Amazon in both rent and buy, prefer rent if both exist
                let amazonLink = null;
                if (watchLinks.rent?.service?.toLowerCase().includes('amazon') && watchLinks.rent?.link) {
                    amazonLink = watchLinks.rent.link;
                } else if (watchLinks.buy?.service?.toLowerCase().includes('amazon') && watchLinks.buy?.link) {
                    amazonLink = watchLinks.buy.link;
                }

                if (amazonLink) {
                    buttons.push({
                        name: 'AMAZON',
                        link: amazonLink,
                        service: 'Amazon',
                        class: 'watch-btn-amazon'
                    });
                }

                // 3. Check for Apple (rent OR buy)
                // Look for Apple in both rent and buy, prefer rent if both exist
                let appleLink = null;
                if (watchLinks.rent?.service?.toLowerCase().includes('apple') && watchLinks.rent?.link) {
                    appleLink = watchLinks.rent.link;
                } else if (watchLinks.buy?.service?.toLowerCase().includes('apple') && watchLinks.buy?.link) {
                    appleLink = watchLinks.buy.link;
                }

                if (appleLink) {
                    buttons.push({
                        name: 'APPLE',
                        link: appleLink,
                        service: 'Apple TV',
                        class: 'watch-btn-apple'
                    });
                }

                // If no buttons at all, show disabled placeholder
                if (buttons.length === 0) {
                    buttons.push({
                        name: 'NOT AVAILABLE',
                        link: '#',
                        service: 'None',
                        class: 'watch-btn-disabled',
                        disabled: true
                    });
                }

                // Render buttons as HTML
                return buttons.map(btn => {
                    if (btn.disabled) {
                        return `<a href="${btn.link}" class="watch-btn ${btn.class}" aria-disabled="true" title="Link not available" tabindex="-1">${btn.name}</a>`;
                    } else {
                        return `<a href="${btn.link}" target="_blank" rel="noopener noreferrer" class="watch-btn ${btn.class}" aria-label="Watch on ${btn.service}">${btn.name}</a>`;
                    }
                }).join('');
            };

            const platformButtons = buildPlatformButtons(movie);

            // Info links - Only Trailer, RT, Wiki
            let infoLinks = [];

            if (movie.links?.trailer) {
                infoLinks.push(`<a href="${movie.links.trailer}" target="_blank" class="info-btn">Trailer</a>`);
            }

            if (movie.links?.rt) {
                const rtText = movie.rt_score ? `RT ${movie.rt_score}` : 'RT';
                infoLinks.push(`<a href="${movie.links.rt}" target="_blank" class="info-btn">${rtText}</a>`);
            }

            if (movie.links?.wikipedia !== null) {
                infoLinks.push(`<a href="${this.wikiUrlFor(movie)}" target="_blank" class="info-btn">Wiki</a>`);
            }

            html += `
            <div class="movie-container">
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
                    <span class="director">${movie.crew?.director || 'Director Unknown'}</span> • <span class="country">${(movie.country === 'United States of America' ? 'USA' : movie.country) || 'Country Unknown'}</span>
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