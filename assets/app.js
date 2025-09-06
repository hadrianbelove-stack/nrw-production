const NRW = {
    async init() {
        try {
            const response = await fetch('data.json');
            const data = await response.json();
            
            if (data.movies && data.movies.length > 0) {
                const today = new Date();
                const filtered = data.movies.filter(m => {
                    if (!m.digital_date) return false;
                    return new Date(m.digital_date) <= today;
                });
                this.renderWall(filtered);
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
            
            // Date marker
            if (date !== lastDate) {
                const d = new Date(date + 'T12:00:00');
                const month = d.toLocaleDateString('en', {month: 'short'}).toUpperCase();
                const day = d.getDate();
                
                html += `<div class="date-marker">
                    <div class="month">${month}</div>
                    <div class="day">${day}</div>
                </div>`;
                
                lastDate = date;
            }
            
            // Movie card
            const title = movie.title || 'Untitled';
            const year = new Date(movie.digital_date).getFullYear();
            
            html += `
            <div class="movie-card">
                <div class="card-inner">
                    <div class="card-front">
                        <img src="${movie.poster || ''}" onerror="this.style.background='#333'">
                        <div class="info">
                            <strong>${title}</strong><br>
                            ${movie.crew?.director || 'Director TBA'}
                        </div>
                    </div>
                    <div class="card-back">
                        <h3>${title}</h3>
                        <div class="synopsis">${movie.synopsis || 'Synopsis coming soon'}</div>
                        <div class="actions">
                            <a href="https://www.amazon.com/s?k=${encodeURIComponent(title + ' ' + year)}" target="_blank">Watch</a>
                            ${movie.links?.trailer ? `<a href="${movie.links.trailer}" target="_blank">Trailer</a>` : ''}
                        </div>
                    </div>
                </div>
            </div>`;
        });
        
        wall.innerHTML = html;
        
        // Click handler for flipping
        wall.addEventListener('click', (e) => {
            if (e.target.tagName === 'A') return;
            const card = e.target.closest('.movie-card');
            if (card) card.classList.toggle('flipped');
        });
    }
};

// Start on page load
document.addEventListener('DOMContentLoaded', () => NRW.init());
