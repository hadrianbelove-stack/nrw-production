#!/bin/bash
# NRW STEP F — runtime renderer + clean page
set -euo pipefail
ROOT="${REPO:-$PWD}"
cd "$ROOT"

mkdir -p assets

# 1) Normalize your current releases JSON → assets/data.json
python3 - <<'PY'
import json, os, sys, datetime
srcs = [p for p in ["current_releases.json","data/current_releases.json"] if os.path.isfile(p)]
if not srcs:
    raise SystemExit("No current_releases.json found")
data = json.load(open(srcs[0], "r", encoding="utf-8"))
# Accept array or {id: movie} map
items = data if isinstance(data, list) else list(data.values())
out = []
for m in items:
    title = m.get("title") or ""
    year  = m.get("year") or ""
    ddate = m.get("digital_date") or m.get("release_date") or ""
    poster_path = m.get("poster_path") or ""
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
    syn = (m.get("overview") or "").strip()
    # Baseline search links (can later be replaced by real URLs/scores)
    q   = (title + " " + str(year)).strip()
    trailer = f"https://www.youtube.com/results?search_query={q.replace(' ','+')}+trailer" if q else ""
    rtUrl   = f"https://www.rottentomatoes.com/search?search={q.replace(' ','%20')}" if q else ""
    wiki    = f"https://en.wikipedia.org/w/index.php?search={q.replace(' ','+')}" if q else ""
    sale    = f"https://www.amazon.com/s?k={q.replace(' ','+')}"
    # Minimal UI record
    out.append({
        "title": title, "year": str(year) if year else "",
        "date": ddate, "poster": poster, "synopsis": syn,
        "dir": "", "cast": "",
        "runtime": m.get("runtime") or "", "studio": "",
        "trailer": trailer, "rtUrl": rtUrl, "rtScore": None,
        "wiki": wiki, "sale": sale
    })
# sort newest first on date if parseable
def key(m):
    try: return datetime.date.fromisoformat(m["date"] or "0001-01-01")
    except: return datetime.date(1,1,1)
out.sort(key=key, reverse=True)
json.dump(out, open("assets/data.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
print("Wrote assets/data.json with", len(out), "records")
PY

# 2) Runtime renderer (flip cards)
cat > assets/nrw_render.js <<'JS'
(function(){
  const $ = (sel,root=document)=>Array.from(root.querySelectorAll(sel));
  const html = String.raw;

  // ---- mount helpers -------------------------------------------------------
  function el(tag, cls){ const e=document.createElement(tag); if(cls) e.className=cls; return e; }
  function esc(s){ return (s||"").replace(/[&<>"']/g, m=>({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[m])); }

  // ---- card templates -------------------------------------------------------
  function dateCard(d){
    const dt = new Date(d);
    const wrap = el("div","date-card");
    wrap.innerHTML = html`
      <div class="month">${dt.toLocaleString('en-US',{month:'short'}).toUpperCase()}</div>
      <div class="day">${String(dt.getDate()).padStart(2,'0')}</div>
      <div class="year">${dt.getFullYear()}</div>`;
    return wrap;
  }

  function card(movie){
    const score = (movie.rtScore==null) ? 'N/A%' : `${movie.rtScore}%`;
    const poster = movie.poster || '/assets/placeholder_poster.svg';
    const root = el("div","movie-card");
    root.innerHTML = html`
      <div class="movie-card-inner">
        <div class="card-face card-front" style="position:relative">
          <img class="movie-poster" loading="lazy" src="${esc(poster)}"
               alt="${esc(movie.title)}"
               onerror="this.onerror=null;this.src='/assets/placeholder_poster.svg'">
          <div class="movie-info">
            <div class="front-credits">
              <div><strong>Dir:</strong> ${esc(movie.dir||'N/A')}</div>
              <div><strong>Cast:</strong> ${esc(movie.cast||'N/A')}</div>
            </div>
          </div>
        </div>
        <div class="card-face card-back" data-sale="${esc(movie.sale||'')}">
          <div class="back-credits">
            <strong>Dir:</strong> ${esc(movie.dir||'N/A')}<br>
            <strong>Cast:</strong> ${esc(movie.cast||'N/A')}
          </div>
          <div class="back-synopsis">${esc(movie.synopsis||'Synopsis not available.')}</div>
          <div class="back-buttons">
            ${movie.trailer ? `<a href="${esc(movie.trailer)}" class="mini-btn btn-trailer" target="_blank" rel="noopener">Trailer</a>` : ''}
            ${movie.rtUrl   ? `<a href="${esc(movie.rtUrl)}"   class="mini-btn btn-rt"      target="_blank" rel="noopener">RT ${score}</a>` : ''}
            ${movie.wiki    ? `<a href="${esc(movie.wiki)}"    class="mini-btn btn-wiki"    target="_blank" rel="noopener">Wiki</a>` : ''}
          </div>
          <div class="back-meta">
            ${movie.runtime ? `${esc(String(movie.runtime))} min • ` : ''}${esc(movie.studio||'')} • ${esc(movie.year||'')}
          </div>
        </div>
      </div>`;
    return root;
  }

  // ---- behavior (flip, accessibility) --------------------------------------
  function wireInteractions(grid){
    grid.addEventListener('click', (e)=>{
      const a = e.target.closest('a');
      if (a) return; // let buttons work
      const c = e.target.closest('.movie-card');
      if (!c) return;
      const onBack = e.target.closest('.card-back');
      if (onBack){
        const sale = onBack.getAttribute('data-sale');
        if (sale) window.open(sale, '_blank', 'noopener');
        else c.classList.toggle('flipped', false);
      } else {
        c.classList.toggle('flipped');
      }
    });
    // keyboard
    grid.addEventListener('keydown', (e)=>{
      const c = e.target.closest && e.target.closest('.movie-card');
      if (!c) return;
      if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); c.classList.toggle('flipped'); }
      if (e.key === 'Escape'){ c.classList.remove('flipped'); }
    });
    // add roles
    $('.movie-card', grid).forEach(c=>{ c.tabIndex=0; c.setAttribute('role','button'); });
  }

  // ---- render pipeline ------------------------------------------------------
  async function main(){
    const grid = document.querySelector('#movie-grid');
    if (!grid) return;
    const res = await fetch('assets/data.json', {cache:'no-store'});
    const movies = await res.json();

    grid.innerHTML = '';
    let last = '';
    for (const m of movies){
      const key = (m.date||'').slice(0,10);
      if (key && key !== last){ grid.appendChild(dateCard(key)); last = key; }
      grid.appendChild(card(m));
    }
    wireInteractions(grid);
  }
  // Minimal CSS tokens injected (avoid touching site.css)
  const style = document.createElement('style');
  style.textContent = `
    :root{ --card-w:180px; }
    .movie-grid{ display:grid; grid-template-columns: repeat(auto-fill, minmax(var(--card-w),1fr)); gap:24px; }
    .movie-card{ width:var(--card-w); perspective:1000px; }
    .movie-card-inner{ position:relative; width:100%; height:320px; transform-style:preserve-3d; transition:transform .5s; }
    .movie-card.flipped .movie-card-inner{ transform:rotateY(180deg); }
    @media (hover:none){ .movie-card:hover .movie-card-inner{ transform:none; } }
    @media (prefers-reduced-motion:reduce){ .movie-card-inner{ transition:none; } }
    .card-face{ position:absolute; inset:0; backface-visibility:hidden; -webkit-backface-visibility:hidden; display:flex; flex-direction:column; }
    .card-back{ transform:rotateY(180deg); padding:8px 10px; }
    .movie-poster{ width:100%; height:70%; object-fit:cover; border-radius:4px 4px 0 0; }
    .front-credits{ font-size:.78rem; color:#cfcfcf; margin-top:.3rem; line-height:1.25; }
    .front-credits strong{ color:#fff; }
    .back-synopsis{ flex:1; overflow:auto; margin:.35rem 0; font-size:.85rem; }
    .back-buttons{ display:flex; gap:.5rem; margin:.25rem 0 .5rem; }
    .mini-btn{ display:inline-block; padding:.4rem .6rem; border:1px solid #444; border-radius:.35rem; text-decoration:none; font-weight:600; font-size:.72rem; background:#2a2a2a; color:#fff; }
    .back-meta{ font-size:.75rem; color:#9a9a9a; }
    .date-card{ width:80px; text-align:center; color:#bbb; }
    .date-card .month{ letter-spacing:.12em; }
    .date-card .day{ font-size:1.9rem; color:#fff; }
  `;
  document.head.appendChild(style);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', main);
  else main();
})();
JS

# 3) Minimal placeholder poster (so missing art doesn't break layout)
cat > assets/placeholder_poster.svg <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="500" height="750">
  <rect width="100%" height="100%" fill="#222"/>
  <text x="50%" y="50%" fill="#666" font-size="28" text-anchor="middle" font-family="Helvetica, Arial">No Poster</text>
</svg>
SVG

# 4) Clean page that mounts the renderer
cat > site.v2.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>New Release Wall — Runtime</title>
  <link rel="preconnect" href="https://image.tmdb.org">
  <style> body{margin:0;background:#0e0e0f;color:#ddd;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
    header{padding:28px 0 8px;text-align:center;letter-spacing:.15em}
    h1{margin:0;font-weight:600}
    main{display:flex;justify-content:center}
    .container{width:min(1200px,96vw);padding:10px 0 60px}
  </style>
</head>
<body>
  <header><h1>NEW RELEASE WALL</h1><div>Runtime demo layout</div></header>
  <main><div class="container"><div id="movie-grid" class="movie-grid"></div></div></main>
  <script src="assets/nrw_render.js" defer></script>
</body>
</html>
HTML

# 5) Start server (if needed) and open the new page
if ! lsof -i :5500 >/dev/null 2>&1; then
  (python3 -m http.server 5500 >/dev/null 2>&1 & echo $! > .nrw_http_pid)
  echo "HTTP server started on :5500"
fi
open -a Safari "http://localhost:5500/site.v2.html"
echo "Done. Page: http://localhost:5500/site.v2.html"