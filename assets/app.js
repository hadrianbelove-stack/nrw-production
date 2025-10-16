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
                
                html += `<div class="date-divider-card">
                    <div class="date-content">
                        <div class="date-day">${d.toLocaleDateString('en', {weekday: 'short'}).toUpperCase()}</div>
                        <div class="date-number">${d.getDate()}</div>
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

            // Build watch link and button text
            let watchLink = '';
            let watchText = 'PLAY';

            if (movie.providers?.streaming?.length > 0) {
                // Use first streaming provider
                const provider = movie.providers.streaming[0];
                watchLink = `https://www.google.com/search?q=${encodeURIComponent(title + ' watch ' + provider)}`;
                watchText = `PLAY ON ${provider.toUpperCase()}`;
            } else if (movie.providers?.rent?.length > 0) {
                // Use first rental provider
                const provider = movie.providers.rent[0];
                watchLink = `https://www.google.com/search?q=${encodeURIComponent(title + ' rent ' + provider)}`;
                watchText = `RENT ON ${provider.toUpperCase()}`;
            } else if (movie.providers?.buy?.length > 0) {
                // Use first buy provider
                const provider = movie.providers.buy[0];
                watchLink = `https://www.google.com/search?q=${encodeURIComponent(title + ' buy ' + provider)}`;
                watchText = `BUY ON ${provider.toUpperCase()}`;
            } else {
                // Default to Amazon search
                watchLink = `https://www.amazon.com/s?k=${encodeURIComponent(title + ' ' + year)}`;
                watchText = 'PLAY ON AMAZON';
            }

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
                                <a href="${watchLink}" target="_blank" class="watch-btn">${watchText}</a>
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