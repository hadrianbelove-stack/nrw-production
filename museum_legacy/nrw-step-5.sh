#!/bin/bash
# NRW STEP 5 — runtime baseline
set -euo pipefail
cd "${REPO:-$PWD}"

# 1. Folders
mkdir -p assets scripts docs

# 2. Data → runtime format
# Uses your current_releases.json as the data contract for now
# (renderer reads /assets/data.json)
if [ -f current_releases.json ]; then
  cp -f current_releases.json assets/data.json
else
  printf '[]' > assets/data.json
fi

# 3. Renderer → assets
# Your renderer already expects /assets/data.json and renders into #cards/.cards/.grid
# and sets #count (if present).
# (If render_approved.js is missing, we stub an empty module.)
if [ -f render_approved.js ]; then
  cp -f render_approved.js assets/nrw_render.js
else
  cat > assets/nrw_render.js <<'JS'
(async function(){ const res=await fetch('/assets/data.json'); const all=await res.json(); const grid=document.querySelector('#cards,.cards,.grid'); if(!grid) return; grid.innerHTML=all.map(m=>`<article class="card"><div class="poster"><div class="ph">🎬</div></div><div class="meta"><h3>${m.title||''}</h3></div></article>`).join(''); const c=document.getElementById('count'); if(c) c.textContent=all.length; })();
JS
fi

# 4. Minimal runtime page (no flip yet; stable grid)
cat > index.runtime.html <<'HTML'
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>New Release Wall — Runtime</title>
<style>
  :root{--gap:16px;--card-w:180px;}
  *{box-sizing:border-box} body{margin:0;background:#0a0a0a;color:#e6e6e6;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  header{padding:24px 24px 8px;display:flex;justify-content:space-between;align-items:flex-end}
  h1{letter-spacing:.2em;font-weight:600;margin:0;font-size:20px;opacity:.9}
  .meta-line{opacity:.6;font-size:12px}
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--card-w),1fr));gap:var(--gap);padding:16px 24px 48px;align-items:start}
  .card{background:#151515;border-radius:12px;overflow:hidden;border:1px solid #222}
  .poster{aspect-ratio:2/3;background:#111;display:flex;align-items:center;justify-content:center}
  .poster img{width:100%;height:100%;object-fit:cover;display:block}
  .ph{font-size:48px;color:#333}
  .meta{padding:10px;border-top:1px solid #222}
  .meta h3{margin:0 0 6px 0;font-size:14px;line-height:1.2}
  .bar{display:flex;justify-content:space-between;align-items:center;gap:8px}
  .chips{display:flex;gap:6px;flex-wrap:wrap}
  .chip{font-size:11px;padding:2px 6px;border-radius:999px;background:#222;border:1px solid #333;opacity:.9}
  .chip.rt{background:#262018}
</style>
</head><body>
<header>
  <div>
    <h1>NEW RELEASE WALL</h1>
    <div class="meta-line">Runtime prototype · <span id="count">0</span> titles</div>
  </div>
</header>
<div id="cards" class="cards"></div>
<script src="assets/nrw_render.js" defer></script>
</body></html>
HTML

# 5. Serve + open
if ! lsof -i :5500 >/dev/null 2>&1; then
  (python3 -m http.server 5500 >/dev/null 2>&1 & echo $! > .nrw_http_pid)
  echo "HTTP: started :5500"
fi
open -a Safari "http://localhost:5500/index.runtime.html"
echo "Runtime baseline ready."