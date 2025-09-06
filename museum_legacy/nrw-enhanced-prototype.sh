#!/bin/bash
# NRW — bring the prototype to life (renderer + CSS + data) and open it
set -euo pipefail
cd "${REPO:-$PWD}"

mkdir -p assets

# 1) Runtime renderer (reads window.NRW_DATA or assets/data.json)
cat > assets/nrw_render.js <<'JS'
(()=>{function E(s){return(s||'').replace(/[&<>"']/g,m=>({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]))}
function T(html){const t=document.createElement('template');t.innerHTML=html.trim();return t.content}
function norm(raw){let a=[];if(Array.isArray(raw))a=raw;else if(raw&&Array.isArray(raw.movies)){a=raw.movies.map(m=>({title:m.title,date:m.digital_date||m.release_date||"",poster:m.poster||"",overview:m.synopsis||"",dir:(m.crew&&m.crew.director)||"",cast:Array.isArray(m.crew&&m.crew.cast)?m.crew.cast.join(", "):"",trailer:m.links&&m.links.trailer||"",rt_url:m.links&&m.links.rt||"",wiki:m.links&&m.links.wiki||"",runtime:m.metadata&&m.metadata.runtime||"",studio:m.metadata&&m.metadata.studio||"",sale:m.links&&m.links.sale||""}))}
return a.filter(x=>x.title&&x.date)}
function render(items,mountId='app'){const root=document.getElementById(mountId);root.innerHTML='<div class="movie-grid"></div>';const grid=root.querySelector('.movie-grid');items.sort((a,b)=>new Date(b.date)-new Date(a.date));let last='';for(const m of items){const k=(m.date||'').slice(0,10);if(k&&k!==last){const d=new Date(m.date);grid.appendChild(T(`<div class="date-card"><div class="month">${d.toLocaleString('en-US',{month:'short'}).toUpperCase()}</div><div class="day">${String(d.getDate()).padStart(2,'0')}</div><div class="year">${d.getFullYear()}</div></div>`));last=k}
const score=m.rt_score==null?'N/A%':`${m.rt_score}%`;const poster=m.poster||'assets/placeholder.png';const dir=m.dir||m.director||'N/A';const cast=Array.isArray(m.cast)?m.cast.slice(0,3).join(', '):(m.cast||'N/A');grid.appendChild(T(`
<div class="movie-card">
  <div class="movie-card-inner">
    <div class="card-face card-front">
      <img class="movie-poster" src="${poster}" alt="${E(m.title)}">
      <div class="movie-info">
        <div class="front-credits"><strong>Dir:</strong> ${E(dir)}<br><strong>Cast:</strong> ${E(cast)}</div>
      </div>
    </div>
    <div class="card-face card-back" ${m.sale?`data-sale="${m.sale}"`:''}>
      <div class="back-synopsis">${E(m.overview||'')}</div>
      <div class="back-buttons">
        ${m.trailer?`<a class="mini-btn btn-trailer" target="_blank" rel="noopener" href="${m.trailer}">Trailer</a>`:''}
        ${m.rt_url?`<a class="mini-btn btn-rt" target="_blank" rel="noopener" href="${m.rt_url}">RT ${score}</a>`:''}
        ${m.wiki?`<a class="mini-btn btn-wiki" target="_blank" rel="noopener" href="${m.wiki}">Wiki</a>`:''}
      </div>
      <div class="back-meta">${m.runtime?`${m.runtime} min • `:''}${E(m.studio||'')} • ${(m.date||'').slice(0,4)}</div>
    </div>
  </div>
</div>`))}
grid.addEventListener('click',e=>{if(e.target.closest('a'))return;const card=e.target.closest('.movie-card');if(!card)return;const onBack=e.target.closest('.card-back');if(onBack){const sale=onBack.getAttribute('data-sale');if(sale){window.open(sale,'_blank','noopener');return}}card.classList.toggle('flipped')})}
async function load(src){if(window.NRW_DATA)return window.NRW_DATA;const r=await fetch(src,{cache:'no-store'});return r.json()}
window.NRW={async init(o={}){const src=o.src||'assets/data.json';const raw=await load(src).catch(()=>({movies:[]}));const items=norm(raw);render(items,o.mountId||'app')}}
})();
JS

# 2) Minimal CSS for the cards/panel (Safari-safe)
cat > assets/nrw_styles.css <<'CSS'
:root{--card-w:180px}
body{background:#0a0a0a;color:#fff;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Oxygen,Ubuntu,sans-serif}
.header{padding:2rem 1rem 1rem;text-align:center;background:linear-gradient(180deg,#1a1a1a 0%,#0a0a0a 100%)}
.header h1{font-weight:300;letter-spacing:.08em;margin:0}
.header .sub{color:#9a9a9a;font-size:.9rem;margin-top:.3rem}
.movie-grid{display:flex;flex-wrap:wrap;gap:1.2rem;padding:1.5rem;max-width:1400px;margin:0 auto;align-items:flex-start}
.date-card{width:80px;aspect-ratio:2/3;background:linear-gradient(135deg,#1a1a1a 0%,#2a2a2a 100%);border:1px solid #333;border-radius:6px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.date-card .month{font-size:.8rem;color:#bbb;letter-spacing:.1em}
.date-card .day{font-size:1.8rem;font-weight:200;line-height:1}
.date-card .year{font-size:.7rem;color:#777}
.movie-card{width:var(--card-w);aspect-ratio:2/3;perspective:1000px;cursor:pointer}
.movie-card-inner{position:relative;width:100%;height:100%;transform-style:preserve-3d;transition:transform .5s}
.movie-card:hover .movie-card-inner{transform:none} /* no hover-flip */
.movie-card.flipped .movie-card-inner{transform:rotateY(180deg)}
.card-face{position:absolute;width:100%;height:100%;-webkit-backface-visibility:hidden;backface-visibility:hidden;border-radius:6px;overflow:hidden;border:1px solid #222;background:#151515}
.card-front{transform:rotateY(0)}
.card-back{transform:rotateY(180deg);padding:.6rem;display:flex;flex-direction:column;justify-content:space-between}
.movie-poster{width:100%;height:70%;object-fit:cover;display:block}
.movie-info{padding:.35rem .5rem}
.front-credits{font-size:.72rem;color:#cfcfcf}
.front-credits strong{color:#fff}
.back-synopsis{font-size:.78rem;line-height:1.35;max-height:6.4rem;overflow:auto;margin:.25rem 0 .5rem}
.back-buttons{display:flex;gap:.5rem;margin:.2rem 0 .5rem}
.mini-btn{padding:.35rem .55rem;border:1px solid #444;border-radius:.35rem;background:#2a2a2a;color:#fff;text-decoration:none;font-weight:600;font-size:.7rem}
.back-meta{font-size:.72rem;color:#9a9a9a}
@media (hover:none){.movie-card:hover .movie-card-inner{transform:none}}
@media (prefers-reduced-motion:reduce){.movie-card-inner{transition:none}}
CSS

# 3) Provide the data file the renderer expects
if [ -f data.json ]; then cp -f data.json assets/data.json;
elif [ -f current_releases.json ]; then cp -f current_releases.json assets/data.json;
else printf '[]' > assets/data.json; fi

# 4) Serve and open the prototype
if ! lsof -i :5500 >/dev/null 2>&1; then (python3 -m http.server 5500 >/dev/null 2>&1 & echo $! > .nrw_http_pid); fi
open -a Safari "http://localhost:5500/prototype.html"
echo "Prototype ready on http://localhost:5500/prototype.html"