const NRW = {
    allMovies: [],
    filteredMovies: [],
    featuredMovies: [],
    latestPlaylistUrl: null,  // YouTube trailers playlist URL
    plexLibrary: {},  // TMDB ID -> Plex URLs mapping (personal, local only)
    currentFilter: 'all',
    displayedCount: 60,  // How many movies currently shown
    loadIncrement: 60,   // How many to add when clicking "More"

    async init() {
        try {
            // Load movie data
            const movieResponse = await fetch('data.json');
            const data = await movieResponse.json();

            // Load filter data (featured list) from data.json
            this.featuredMovies = data.featured || [];

            // Load YouTube trailers playlist URL
            this.latestPlaylistUrl = data.latest_playlist_url || null;

            // Build Plex library from movies that have plex data embedded
            if (data.movies) {
                data.movies.forEach(movie => {
                    if (movie.plex) {
                        this.plexLibrary[String(movie.id)] = movie.plex;
                    }
                });
                if (Object.keys(this.plexLibrary).length > 0) {
                    console.log(`Plex library loaded: ${Object.keys(this.plexLibrary).length} movies`);
                }
            }

            if (data.movies && data.movies.length > 0) {
                const today = new Date();
                this.allMovies = data.movies.filter(m => {
                    if (!m.digital_date) return false;
                    return new Date(m.digital_date) <= today;
                });

                this.setupFilterEventListeners();
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

    setupFilterEventListeners() {
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                // Update active button
                filterButtons.forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');

                // Update filter and re-render
                this.currentFilter = e.target.dataset.filter;
                this.displayedCount = this.loadIncrement; // Reset when changing filters
                this.applyFilter();
                this.renderWallWithMore();
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
                case 'foreign':
                    // Foreign = non-English original language films
                    const lang = movie.original_language;
                    // Include if original_language exists and is not English
                    return lang && lang !== 'en';
                case 'series':
                    // Limited series / miniseries only
                    return movie.content_type === 'limited_series';
                case 'all':
                default:
                    return true; // Show all movies
            }
        });
    },

    renderWallWithMore() {
        const sortedMovies = [...this.filteredMovies].sort((a, b) => {
            return new Date(b.digital_date) - new Date(a.digital_date);
        });

        const moviesToShow = sortedMovies.slice(0, this.displayedCount);
        const hasMore = this.displayedCount < sortedMovies.length;

        this.renderWall(moviesToShow);
        this.renderMoreButton(hasMore, sortedMovies.length);
    },

    renderMoreButton(hasMore, totalCount) {
        const container = document.getElementById('load-more-container');
        if (!container) return;

        if (hasMore) {
            const remaining = totalCount - this.displayedCount;
            container.innerHTML = `
                <button class="load-more-btn" onclick="NRW.loadMore()">
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
        let isFirstDate = true;

        movies.forEach(movie => {
            const date = movie.digital_date.substring(0, 10);

            // Add inline date divider card when date changes
            if (date !== lastDate) {
                // Add NEW TRAILERS button before the first date marker
                if (isFirstDate && this.latestPlaylistUrl) {
                    html += `<a href="${this.latestPlaylistUrl}" target="_blank" rel="noopener noreferrer" class="trailers-card">
                        <div class="trailers-content">
                            <div class="trailers-text">NEW</div>
                            <div class="trailers-text">TRAILERS</div>
                            <div class="trailers-icon">▶</div>
                        </div>
                    </a>`;
                    isFirstDate = false;
                }

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
            // For limited series: show episode count + runtime
            // For movies: just show runtime
            if (movie.content_type === 'limited_series' && movie.episode_count) {
                let seriesInfo = `${movie.episode_count} eps`;
                if (movie.runtime) {
                    seriesInfo += ` • ${movie.runtime} min/ep`;
                }
                bottomMetadata.push(seriesInfo);
            } else if (movie.runtime) {
                bottomMetadata.push(`${movie.runtime} min`);
            }
            const bottomInfo = bottomMetadata.join(' | ');

            // Build platform-based watch buttons (SVOD, Amazon, Apple, Plex)
            const buildPlatformButtons = (movie) => {
                const watchLinks = movie.watch_links || {};
                const providers = movie.providers || {};
                let buttonsHtml = '';

                // Check for Plex availability (personal library)
                const plexInfo = this.plexLibrary[String(movie.id)];
                if (plexInfo && plexInfo.web_url) {
                    buttonsHtml += `<a href="${plexInfo.web_url}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-plex" aria-label="Play on Plex" title="Play on your Plex server"><img src="logos%20and%20images/plex-logo.png" alt="Plex" class="btn-logo" onerror="this.parentElement.innerHTML='PLEX'"></a>`;
                }

                // Helper to get display name for a service
                const getDisplayName = (service) => {
                    const s = service.toLowerCase();
                    if (s.includes('amazon') || s.includes('prime')) return 'PRIME';
                    if (s.includes('disney')) return 'DISNEY+';
                    if (s.includes('hbo') || s.includes('max')) return 'MAX';
                    if (s.includes('netflix')) return 'NETFLIX';
                    if (s.includes('hulu')) return 'HULU';
                    if (s.includes('peacock')) return 'PEACOCK';
                    return service.toUpperCase();
                };

                // Helper to render streaming button (active or disabled)
                const renderStreamButton = (service, link) => {
                    const displayName = getDisplayName(service);
                    if (link) {
                        // Active button with link
                        if (displayName === 'PRIME') {
                            return `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on Prime Video"><img src="logos%20and%20images/amazon%20prime.png" alt="Prime Video" class="btn-logo"></a>`;
                        } else if (displayName === 'NETFLIX') {
                            return `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on Netflix"><img src="logos%20and%20images/netflix%20square%20logo.png" alt="Netflix" class="btn-logo"></a>`;
                        } else {
                            return `<a href="${link}" target="_blank" rel="noopener noreferrer" class="watch-btn watch-btn-stream" aria-label="Watch on ${service}">${displayName}</a>`;
                        }
                    } else {
                        // Disabled button - service known but no link (needs admin correction)
                        if (displayName === 'NETFLIX') {
                            return `<span class="watch-btn watch-btn-stream watch-btn-disabled" aria-disabled="true" title="On Netflix - link pending"><img src="logos%20and%20images/netflix%20square%20logo.png" alt="Netflix" class="btn-logo"></span>`;
                        } else if (displayName === 'PRIME') {
                            return `<span class="watch-btn watch-btn-stream watch-btn-disabled" aria-disabled="true" title="On Prime - link pending"><img src="logos%20and%20images/amazon%20prime.png" alt="Prime Video" class="btn-logo"></span>`;
                        } else {
                            return `<span class="watch-btn watch-btn-stream watch-btn-disabled" aria-disabled="true" title="On ${service} - link pending">${displayName}</span>`;
                        }
                    }
                };

                // 1. SVOD Streaming Button
                // Check watch_links first, then fall back to providers
                let streamingService = watchLinks.streaming?.service;
                let streamingLink = watchLinks.streaming?.link;

                // If no watch_links.streaming but providers.streaming exists, use first provider
                if (!streamingService && providers.streaming?.length > 0) {
                    // Filter out "with Ads" variants to get primary service
                    const primaryProvider = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
                    streamingService = primaryProvider;
                    streamingLink = null; // No link available
                }

                if (streamingService) {
                    buttonsHtml += renderStreamButton(streamingService, streamingLink);
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
                    buttonsHtml = '<span class="watch-btn watch-btn-disabled" aria-disabled="true" title="Link not available">NOT AVAILABLE</span>';
                }

                // Wrap all buttons in a single container
                return `<div class="watch-buttons">${buttonsHtml}</div>`;
            };

            const platformButtons = buildPlatformButtons(movie);

            // Info links - Only Trailer, RT, Wiki
            let infoLinks = [];

            if (movie.links?.trailer) {
                infoLinks.push(`<a href="#" onclick="NRW.showTrailer('${movie.links.trailer}'); return false;" class="info-btn">Trailer</a>`);
            }

            if (movie.links?.rt) {
                const rtText = movie.rt_score ? `RT ${movie.rt_score}` : 'RT';
                const rtClass = movie.rt_score ? 'info-btn' : 'info-btn info-btn-neutral';
                infoLinks.push(`<a href="${movie.links.rt}" target="_blank" class="${rtClass}">${rtText}</a>`);
            }

            if (movie.links?.wikipedia) {
                infoLinks.push(`<a href="${movie.links.wikipedia}" target="_blank" class="info-btn">Wiki</a>`);
            }

            const isFeatured = this.featuredMovies.includes(movie.id);
            const featuredClass = isFeatured ? ' featured-movie' : '';
            const featuredBadge = isFeatured ? '<div class="featured-badge">FEATURED</div>' : '';

            // Streaming service pill badge for card front
            const getStreamingBadge = (movie) => {
                const watchLinks = movie.watch_links || {};
                const providers = movie.providers || {};

                // Get streaming service name
                let service = watchLinks.streaming?.service;
                if (!service && providers.streaming?.length > 0) {
                    service = providers.streaming.find(p => !p.includes('with Ads')) || providers.streaming[0];
                }

                if (!service) return '';

                // Map service to display name and CSS class
                const s = service.toLowerCase();
                let displayName, badgeClass;

                if (s.includes('netflix')) {
                    displayName = 'NETFLIX'; badgeClass = 'badge-netflix';
                } else if (s.includes('disney')) {
                    displayName = 'DISNEY+'; badgeClass = 'badge-disney';
                } else if (s.includes('hbo') || s.includes('max')) {
                    displayName = 'MAX'; badgeClass = 'badge-max';
                } else if (s.includes('amazon') || s.includes('prime')) {
                    displayName = 'PRIME'; badgeClass = 'badge-prime';
                } else if (s.includes('hulu')) {
                    displayName = 'HULU'; badgeClass = 'badge-hulu';
                } else if (s.includes('peacock')) {
                    displayName = 'PEACOCK'; badgeClass = 'badge-peacock';
                } else if (s.includes('mubi')) {
                    displayName = 'MUBI'; badgeClass = 'badge-mubi';
                } else if (s.includes('shudder')) {
                    displayName = 'SHUDDER'; badgeClass = 'badge-shudder';
                } else if (s.includes('criterion')) {
                    displayName = 'CRITERION'; badgeClass = 'badge-criterion';
                } else {
                    displayName = service.toUpperCase().slice(0, 10); badgeClass = 'badge-other';
                }

                return `<div class="streaming-badge ${badgeClass}">${displayName}</div>`;
            };

            const streamingBadge = getStreamingBadge(movie);

            html += `
            <div class="movie-container${featuredClass}">
                ${featuredBadge}
                <div class="movie-card">
                    <div class="card-inner">
                        <div class="card-front">
                            ${streamingBadge}
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

    // Show trailer in embedded modal
    showTrailer(url) {
        const videoId = this.extractYouTubeId(url);

        if (!videoId) {
            // Not a YouTube URL, open in new tab as fallback
            window.open(url, '_blank');
            return;
        }

        // Create modal if it doesn't exist
        let modal = document.getElementById('trailer-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'trailer-modal';
            modal.className = 'trailer-modal';
            modal.innerHTML = `
                <div class="trailer-modal-backdrop" onclick="NRW.closeTrailer()"></div>
                <div class="trailer-modal-content">
                    <button class="trailer-close-btn" onclick="NRW.closeTrailer()" aria-label="Close trailer">&times;</button>
                    <div class="trailer-video-container">
                        <iframe id="trailer-iframe"
                            src=""
                            frameborder="0"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                            allowfullscreen>
                        </iframe>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            // Close on Escape key
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') this.closeTrailer();
            });
        }

        // Set the iframe source with autoplay
        const iframe = document.getElementById('trailer-iframe');
        iframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0`;

        // Show modal
        modal.classList.add('active');
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    },

    // Close trailer modal
    closeTrailer() {
        const modal = document.getElementById('trailer-modal');
        if (modal) {
            modal.classList.remove('active');
            // Stop the video by clearing the src
            const iframe = document.getElementById('trailer-iframe');
            if (iframe) iframe.src = '';
            document.body.style.overflow = ''; // Restore scrolling
        }
    }
};

// Start on page load
document.addEventListener('DOMContentLoaded', () => NRW.init());