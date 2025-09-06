(function(){
  if (window.__NRW_RENDERED__) return; window.__NRW_RENDERED__=true;
  const DATA_URL = 'assets/data.json?cb='+(Date.now());
  const TMDB = 'https://image.tmdb.org/t/p/w500';

  function resolvePoster(m){
    const v = m.poster || m.tmdb_poster || m.poster_path || '';
    if (!v) return '';
    if (typeof v === 'string'){
      if (v.startsWith('http')) return v;
      if (v.startsWith('/')) return TMDB + v;
      if (v.startsWith('t/p/')) return TMDB + '/' + v.replace(/^t\/p\//,'');
      if (v.startsWith('w500/')) return TMDB + '/' + v.replace(/^w500\//,'');
    }
    return v;
  }

  function normProviders(m){
    const prov = m.providers || [];
    if (Array.isArray(prov)) return prov.map(x=> (x.name||x)).filter(Boolean);
    if (prov && typeof prov === 'object'){
      const buckets = ['stream','flatrate','rent','buy'];
      const names = [];
      for (const k of buckets){
        const arr = Array.isArray(prov[k]) ? prov[k] : [];
        for (const it of arr){ names.push(it.name || it); }
      }
      return [...new Set(names)].filter(Boolean);
    }
    return [];
  }

  function notFuture(m){
    const d = m.digital_date || m.date_key || m.release_date || '';
    if (!d) return true;
    const s = String(d).slice(0,10);
    const today = new Date(); today.setHours(0,0,0,0);
    const dt = new Date(s); if (isNaN(dt)) return true;
    return dt <= today;
  }

  function isApproved(m){
    // We're rendering from the approved dataset (186 total),
    // but still enforce: must have providers + not future.
    const hasDigital = !!m.has_digital;
    const providers = normProviders(m);
    return (hasDigital || providers.length>0) && notFuture(m);
  }

  function cardHTML(m){
    const poster = resolvePoster(m) || '';
    const title = String(m.title||'').trim();
    const rt = (m.rt_score==null || m.rt_score==='') ? '—' : `${m.rt_score}%`;
    const providers = normProviders(m);

    return `
    <article class="card">
      <div class="poster-wrap">
        <img class="poster" src="${poster}" alt="${title}" loading="lazy" />
      </div>
      <div class="meta">
        <h3 class="t">${title}</h3>
        <div class="bar">
          <div class="chips">${providers.map(p=>`<span class="chip">${p}</span>`).join('')}</div>
          <span class="chip rt">🍅 ${rt}</span>
        </div>
      </div>
    </article>`;
  }

  async function main(){
    try{
      const r = await fetch(DATA_URL, {cache:'no-store'});
      const data = await r.json();

      const approved = data.filter(isApproved);
      const html = approved.map(cardHTML).join('');

      const targets = [
        document.querySelector('#cards'),
        document.querySelector('.cards'),
        document.querySelector('.grid'),
        document.querySelector('.movie-grid'),
      ].filter(Boolean);

      // ensure one container exists
      let host = targets[0];
      if (!host){
        host = document.createElement('div');
        host.id = 'cards';
        host.className = 'cards grid';
        const anchor = document.querySelector('main') || document.body;
        anchor.appendChild(host);
      }

      // replace content (idempotent)
      host.setAttribute('data-render','approved');
      host.innerHTML = html;

      // update any count elements
      document.querySelectorAll('[data-movie-count]').forEach(el=>{
        el.textContent = String(approved.length);
      });
    }catch(e){
      console.error('NRW render error', e);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', main, {once:true});
  } else {
    main();
  }
})();