(async function(){
  const res = await fetch('/assets/data.json', {cache:'no-store'});
  const all = await res.json();

  const today = new Date();
  function notFuture(m){
    const d = m.digital_date || m.date_key || m.release_date || "";
    const s = (d||"").toString().slice(0,10);
    const t = s && !isNaN(Date.parse(s)) ? new Date(s) : null;
    return !t || t <= today;
  }

  function provNames(m){
    const prov = m.providers || [];
    const names = [];
    if (Array.isArray(prov)){
      for (const p of prov){
        if (typeof p === 'string') names.push(p);
        else if (p && typeof p === 'object') names.push(p.name || p.provider_name || '');
      }
    } else if (prov && typeof prov === 'object'){
      for (const v of Object.values(prov)){
        if (Array.isArray(v)){
          for (const p of v){
            if (typeof p === 'string') names.push(p);
            else if (p && typeof p === 'object') names.push(p.name || p.provider_name || '');
          }
        }
      }
    }
    return [...new Set(names.filter(Boolean))].sort();
  }

  const withProviders = all.filter(m => (m.has_digital === true) || provNames(m).length>0);
  const movies = withProviders.filter(notFuture);

  const grid = document.querySelector('#cards, .cards, .grid');
  if (!grid) return;

  grid.innerHTML = movies.map(m=>{
    const prov = provNames(m);
    const rt = (m.rt_score ?? '—');
    const poster = m.poster ? (m.poster.startsWith('http') ? m.poster : `https://image.tmdb.org/t/p/w500${m.poster}`) : '';
    return `
      <article class="card">
        <div class="poster">${poster?`<img src="${poster}" alt="${m.title||''}">`:`<div class="ph">🎬</div>`}</div>
        <div class="meta">
          <h3>${m.title||''}</h3>
          <div class="bar">
            <div class="chips">${prov.map(p=>`<span class="chip">${p}</span>`).join('')}</div>
            <span class="chip rt">🍅 ${rt}</span>
          </div>
        </div>
      </article>
    `;
  }).join('');

  const cnt = document.getElementById('count');
  if (cnt) cnt.textContent = movies.length;
})();
