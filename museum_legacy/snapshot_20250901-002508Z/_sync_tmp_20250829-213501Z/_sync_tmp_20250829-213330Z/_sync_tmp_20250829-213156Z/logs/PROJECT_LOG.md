
## [$(date '+%Y-%m-%d %H:%M')] Offline Mode + Template Rebind
- Locked server_port: 3001; offline true; fetch_tmdb/rt/trailers false
- Created cache dirs/files: .cache/{rt,tmdb,trailers}
- Built assets/data.json from output/data.json (no network)
- Added templates/partials/card.j2 and assets/site.css
- Rendered index.offline.html without network calls
- Next: swap renderer to main index.html after visual confirmation
