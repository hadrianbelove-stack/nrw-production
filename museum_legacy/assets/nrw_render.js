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
