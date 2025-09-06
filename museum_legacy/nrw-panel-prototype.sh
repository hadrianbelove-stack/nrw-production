#!/bin/bash
# NRW — bring the prototype up (panel UI) and open it
set -euo pipefail
cd "${REPO:-$PWD}"

# 1) Assets folder and data
mkdir -p assets
# Prefer the data you just uploaded if present
if [ -f data.json ]; then cp -f data.json assets/data.json
elif [ -f current_releases.json ]; then cp -f current_releases.json assets/data.json
else printf '[]' > assets/data.json
fi

# 2) Styles for the panel prototype
cat > assets/nrw_styles.css <<'CSS'
:root{--gap:20px;--card-w:180px;--radius:10px;--fg:#e8e8e8;--bg:#0f0f0f;--panel:#161616;--muted:#a9a9a9}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,Segoe UI,Roboto}
.header{padding:24px 24px 8px;text-align:center}
.header h1{margin:0;font-weight:650;letter-spacing:.08em}
.header .sub{color:var(--muted);font-size:.9rem;margin-top:6px}
.layout{display:grid;grid-template-columns:3fr 2fr;gap:var(--gap);padding:0 24px 32px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--card-w),1fr));gap:var(--gap)}
.card{background:#1a1a1a;border-radius:var(--radius);overflow:hidden;cursor:pointer;box-shadow:0 1px 0 #0007}
.poster{width:100%;aspect-ratio:2/3;object-fit:cover;display:block}
.ctitle{padding:10px 12px;font-weight:600;font-size:.95rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.panel{position:sticky;top:20px;align-self:start;background:var(--panel);border-radius:var(--radius);padding:18px;border:1px solid #242424}
.ptitle{margin:0 0 6px;font-size:1.4rem}
.pmeta{color:var(--muted);font-size:.95rem;margin-bottom:10px}
.psyn{max-height:220px;overflow:auto;line-height:1.45;border-top:1px solid #242424;border-bottom:1px solid #242424;padding:12px 0;margin:10px 0}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.btn{padding:.45rem .7rem;border-radius:.45rem;border:1px solid #3a3a3a;text-decoration:none;color:var(--fg);background:#242424;font-weight:600;font-size:.85rem}
.btn[aria-disabled="true"]{opacity:.45;pointer-events:none}
.pfoot{color:var(--muted);font-size:.95rem;margin-top:8px}
CSS

# 3) Minimal runtime that renders a left grid and a right detail panel
cat > assets/nrw_render.js <<'JS'
/* NRW panel runtime */
window.NRW = (function(){
  const $ = (sel,root=document)=>root.querySelector(sel);
  const $$ = (sel,root=document)=>Array.from(root.querySelectorAll(sel));

  function loadData(opt){
    if (Array.isArray(window.NRW_DATA)) return Promise.resolve(window.NRW_DATA);
    const url = (opt && opt.dataUrl) || 'assets/data.json';
    return fetch(url).then(r=>r.json());
  }

  function card(item, onpick){
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `
      <img class="poster" src="${item.poster||''}" alt="${esc(item.title||'')}" />
      <div class="ctitle">${esc(item.title||'Untitled')}</div>`;
    div.addEventListener('click', ()=>onpick(item));
    return div;
  }

  function renderPanel(el, item){
    const rt = (item.rt_score==null?'N/A':`${item.rt_score}%`);
    el.innerHTML = `
      <h2 class="ptitle">${esc(item.title||'Untitled')}</h2>
      <div class="pmeta"><b>Dir:</b> ${esc(item.director||'N/A')} · <b>Cast:</b> ${esc(item.cast||'N/A')}</div>
      <div class="psyn">${esc(item.overview||item.synopsis||'Synopsis not available.')}</div>
      <div class="btns">
        ${linkBtn('Trailer', item.trailer)}
        ${linkBtn(rt==='N/A'?'RT N/A':'RT '+rt, item.rt_url, rt==='N/A')}
        ${linkBtn('Wiki', item.wiki)}
      </div>
      <div class="pfoot">${fmtRuntime(item.runtime)}${item.studio?` · ${esc(item.studio)}`:''}${item.year?` · ${esc(item.year)}`:''}</div>
    `;
  }

  const linkBtn = (label, href, disable)=>`<a class="btn" ${href?`href="${href}" target="_blank" rel="noopener"`:''} ${disable||!href?`aria-disabled="true"`:''}>${label}</a>`;
  const fmtRuntime = m => m?`${m} min`:'';
  const esc = s => String(s||'').replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[m]));

  function mount(opt){
    const mount = document.getElementById(opt.mountId||'app');
    mount.innerHTML = `
      <div class="layout">
        <div class="grid" id="nrw-grid"></div>
        <div class="panel" id="nrw-panel"><div class="pmeta">Select a movie</div></div>
      </div>`;
    const grid = $('#nrw-grid', mount);
    const panel = $('#nrw-panel', mount);

    loadData(opt).then(items=>{
      // newest first by digital_date or release_date
      items.sort((a,b)=>new Date(b.digital_date||b.release_date||0)-new Date(a.digital_date||a.release_date||0));
      items.forEach((it,i)=>{
        const c = card(it, item=>renderPanel(panel, item));
        grid.appendChild(c);
        if (i===0) renderPanel(panel, it);
      });
    });
  }

  return { init: mount };
})();
JS

# 4) Ensure prototype.html exists (from your upload). If not, create a minimal one.
if [ ! -f prototype.html ]; then
  cat > prototype.html <<'HTML'
<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>New Release Wall — Prototype (Panel UI)</title>
<link rel="stylesheet" href="assets/nrw_styles.css"/>
</head><body>
  <div class="header"><h1>NEW RELEASE WALL</h1><div class="sub">Panel prototype • Data from assets/data.json</div></div>
  <div id="app"></div>
  <script src="assets/nrw_render.js"></script>
  <script>NRW.init({ uiMode:'panel', mountId:'app', dataUrl:'assets/data.json' });</script>
</body></html>
HTML
fi

# 5) Start a local server and open Safari
if ! lsof -i :5500 >/dev/null 2>&1; then (python3 -m http.server 5500 >/dev/null 2>&1 & echo $! > .nrw_http_pid); fi
open -a Safari "http://localhost:5500/prototype.html"
echo "Open: http://localhost:5500/prototype.html"