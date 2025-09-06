# curator_admin.py
from flask import Flask, request, jsonify, render_template_string, send_from_directory
import json, os, datetime as dt

APP = Flask(__name__)

SRC = "current_releases.json"
CUR = "curated_selections.json"

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return default

def save_json(path, obj):
    with open(path, "w") as f: json.dump(obj, f, indent=2)

def parse_date(s):
    try: return dt.datetime.fromisoformat(s[:10])
    except: return None

HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>NRW Admin</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#0a0a0a; --fg:#e6e6e6; --muted:#9aa0a6; --accent:#c62828; --ok:#2e7d32; --warn:#ef6c00; }
  body { margin:0; background:var(--bg); color:var(--fg); font:14px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
  header { position:sticky; top:0; background:#111; padding:10px 12px; border-bottom:1px solid #222; display:flex; gap:8px; align-items:center; z-index:10; flex-wrap:wrap; }
  input, select, button { background:#161616; color:var(--fg); border:1px solid #333; border-radius:8px; padding:8px 10px; }
  button.primary { background:var(--ok); border-color:#204c22; }
  button.warn { background:var(--warn); border-color:#6b3a00; }
  button.accent { background:var(--accent); border-color:#5c1010; }
  .grid { display:grid; grid-template-columns: repeat(auto-fill, 160px); gap:14px; padding:14px; max-width:1400px; margin:0 auto; }
  .card { background:#111; border:1px solid #222; border-radius:14px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.4); }
  .poster { width:100%; height:240px; background:#1b1b1b center/cover no-repeat; }
  .meta { padding:8px; display:flex; flex-direction:column; gap:6px; }
  .title { font-weight:600; line-height:1.2; }
  .muted { color:var(--muted); font-size:12px; }
  .row { display:flex; gap:6px; flex-wrap:wrap; }
  .pill { padding:2px 6px; border:1px solid #333; border-radius:999px; font-size:11px; }
  .actions { display:flex; gap:6px; flex-wrap:wrap; }
  .sel { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); }
  footer { padding:10px 14px; color:var(--muted); border-top:1px solid #222; }
</style>
</head>
<body>
<header>
  <strong>NRW Admin</strong>
  <input id="q" placeholder="Search title…" oninput="applyFilters()" />
  <select id="status" onchange="applyFilters()">
    <option value="">All</option>
    <option value="unreviewed">Unreviewed</option>
    <option value="approve">Approved</option>
    <option value="feature">Featured</option>
    <option value="reject">Rejected</option>
    <option value="maybe">Maybe</option>
  </select>
  <select id="provider" onchange="applyFilters()">
    <option value="">Any provider</option>
    <option>Apple TV</option><option>YouTube</option><option>Amazon Prime Video</option>
    <option>Google Play Movies</option><option>Vudu</option><option>Max</option><option>MUBI</option>
    <option>Hulu</option><option>Disney Plus</option><option>Criterion Channel</option>
  </select>
  <select id="days" onchange="applyFilters()">
    <option value="14">Last 14 days</option>
    <option value="30">Last 30 days</option>
    <option value="60" selected>Last 60 days</option>
    <option value="90">Last 90 days</option>
  </select>
  <button onclick="batch('approve')" class="primary">Approve selected</button>
  <button onclick="batch('feature')" class="warn">Feature selected</button>
  <button onclick="batch('reject')" class="accent">Reject selected</button>
  <label class="sel"><input type="checkbox" id="selectAll" onchange="toggleAll(this)"> Select all</label>
  <span id="count" class="muted"></span>
</header>

<div id="grid" class="grid"></div>

<footer>
  <span id="foot"></span>
</footer>

<script>
let items = [];
let choices = {};
let filtered = [];
function fmtDate(s){ if(!s) return ''; return s.slice(0,10); }
function hasProvider(m, p){
  const pv = (m.providers||{}); const all = [...(pv.rent||[]), ...(pv.buy||[]), ...(pv.flatrate||[])];
  return all.map(String).some(x => x.toLowerCase().includes(p.toLowerCase()));
}
function statusOf(id){ return choices[id] || 'unreviewed'; }

async function loadData(){
  const a = await fetch('/api/items'); items = await a.json();
  const b = await fetch('/api/curations'); choices = await b.json();
  applyFilters();
}

function applyFilters(){
  const q = document.getElementById('q').value.trim().toLowerCase();
  const st = document.getElementById('status').value;
  const pv = document.getElementById('provider').value;
  const days = parseInt(document.getElementById('days').value || '60', 10);
  const cutoff = new Date(Date.now() - days*24*3600*1000);
  filtered = items.filter(m=>{
    const t = (m.title||'').toLowerCase();
    if(q && !t.includes(q)) return false;
    const d = new Date((m.digital_date||'').slice(0,10));
    if(isFinite(cutoff) && d && d < cutoff) return false;
    if(pv && !hasProvider(m, pv)) return false;
    if(st && statusOf(String(m.id)) !== st) return false;
    return true;
  }).sort((a,b)=>{
    const sa = statusOf(String(a.id))==='feature'?0:1;
    const sb = statusOf(String(b.id))==='feature'?0:1;
    const da = Date.parse(a.digital_date||'1970-01-01');
    const db = Date.parse(b.digital_date||'1970-01-01');
    return sa - sb || db - da;
  });
  render();
}

function posterUrl(m){
  if(m.poster_path){ return 'https://image.tmdb.org/t/p/w342' + m.poster_path; }
  return '';
}

function render(){
  const grid = document.getElementById('grid');
  const cnt = document.getElementById('count');
  grid.innerHTML = '';
  cnt.textContent = filtered.length + ' shown';
  for(const m of filtered){
    const id = String(m.id);
    const st = statusOf(id);
    const pv = (m.providers||{});
    const prov = [...(pv.rent||[]), ...(pv.buy||[]), ...(pv.flatrate||[])].slice(0,3).join(', ');
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `
      <div class="poster" style="background-image:url('${posterUrl(m)}')"></div>
      <div class="meta">
        <div class="title">${m.title||'(untitled)'}</div>
        <div class="muted">${fmtDate(m.digital_date)} • ${m.year||''}</div>
        <div class="row">
          <span class="pill">${st}</span>
          ${prov ? `<span class="pill">${prov}</span>`:''}
        </div>
        <div class="actions">
          <button onclick="act('${id}','approve')" class="primary">✓ Approve</button>
          <button onclick="act('${id}','feature')" class="warn">⭐ Feature</button>
          <button onclick="act('${id}','maybe')">🔄 Maybe</button>
          <button onclick="act('${id}','reject')" class="accent">✗ Reject</button>
          <label class="sel"><input type="checkbox" class="rowchk" data-id="${id}"></label>
        </div>
      </div>`;
    grid.appendChild(div);
  }
  document.getElementById('foot').textContent = 'Total items: ' + items.length;
}

function toggleAll(box){
  document.querySelectorAll('.rowchk').forEach(cb => cb.checked = box.checked);
}

async function act(id, action){
  const r = await fetch('/curate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id, action})});
  const d = await r.json();
  if(d.ok){ choices[id]=action; applyFilters(); }
}

async function batch(action){
  const ids = Array.from(document.querySelectorAll('.rowchk:checked')).map(cb => cb.dataset.id);
  for(const id of ids){ await act(id, action); }
  document.getElementById('selectAll').checked = false;
}

loadData();
</script>
</body>
</html>
"""

@APP.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp

@APP.get("/")
def index():
    return render_template_string(HTML)

@APP.get("/api/items")
def api_items():
    return jsonify(load_json(SRC, []))

@APP.get("/api/curations")
def api_curations():
    return jsonify(load_json(CUR, {}))

@APP.post("/curate")
def curate():
    body = request.get_json(force=True, silent=True) or {}
    movie_id = str(body.get("id") or "")
    action = (body.get("action") or "").lower()
    if not movie_id or action not in {"approve","reject","feature","maybe"}:
        return jsonify({"error":"bad request"}), 400
    cur = load_json(CUR, {})
    cur[movie_id] = action
    save_json(CUR, cur)
    return jsonify({"ok": True, "id": movie_id, "action": action})

import datetime as _dt

def _load_items():
    # same source as admin grid
    try:
        return json.load(open("current_releases.json"))
    except:
        return []

def _load_tracker():
    # tries enhanced then legacy
    for p in ("movie_tracking_enhanced.json","movie_tracking.json"):
        if os.path.exists(p):
            with open(p) as f: return json.load(f), p
    return ([], None)

def _as_list(db):
    if isinstance(db, dict) and "movies" in db: return db["movies"]
    if isinstance(db, list): return db
    return []

def _to_date(s):
    try: return _dt.date.fromisoformat((s or "")[:10])
    except: return None

@APP.get("/api/status")
def api_status():
    items = _load_items()
    db, src = _load_tracker()
    movies = _as_list(db)
    today = _dt.date.today()
    zombies = []
    unresolved = 0
    # allow ?days= to tune threshold (default 180)
    try:
        thresh = int(request.args.get("days", "180"))
    except:
        thresh = 180
    resolved = 0
    for m in movies:
        dig = (m.get("digital") or {}).get("date") or (m.get("state") or {}).get("digital_since") or m.get("digital_date")
        if dig:
            resolved += 1
            continue
        # unresolved: use theatrical or first-seen as anchor
        thea = m.get("release_date") or (m.get("theatrical") or {}).get("date")
        d = _to_date(thea)
        if d is None:
            unresolved += 1
            continue
        age = (today - d).days
        if age >= thresh:
            zombies.append({
                "id": m.get("id"),
                "title": m.get("title") or m.get("name"),
                "age_days": age,
                "release_date": thea
            })
        else:
            unresolved += 1
    zombies.sort(key=lambda x: -x["age_days"])
    return jsonify({
        "tracker_source": src,
        "tracked_total": len(movies),
        "resolved": resolved,
        "unresolved_recent": unresolved,
        "zombies_180d": len(zombies),
        "items_current_window": len(items),
        "sample_zombies": zombies[:50],
    })

_INSPECT_HTML = r"""
<!doctype html><meta charset="utf-8"><title>NRW Inspector</title>
<style>body{background:#0a0a0a;color:#e6e6e6;font:14px system-ui;margin:0}
h1,h2{margin:12px 16px} .wrap{padding:12px 16px}
table{border-collapse:collapse;width:100%;max-width:1200px;margin:0 16px 24px}
th,td{border:1px solid #222;padding:8px} th{background:#121212}
.bad{color:#ef5350} .muted{color:#9aa0a6} a{color:#90caf9}
</style>
<h1>NRW Database Inspector</h1>
<div class="wrap" id="stats" class="muted">Loading…</div>
<h2>Zombies ≥ 180 days (top 50)</h2>
<table id="z"><thead><tr><th>Title</th><th>Days</th><th>Theatrical</th><th>Actions</th></tr></thead><tbody></tbody></table>
<script>
async function run(){
  const s = await (await fetch('/api/status')).json();
  document.getElementById('stats').innerHTML =
    `<div>Tracker: <b>${s.tracker_source||'n/a'}</b></div>
     <div>Tracked total: <b>${s.tracked_total}</b></div>
     <div>Resolved (has digital): <b>${s.resolved}</b></div>
     <div>Unresolved recent (&lt;180d): <b>${s.unresolved_recent}</b></div>
     <div>Current-window items: <b>${s.items_current_window}</b></div>
     <div>Zombies ≥180d: <b class="bad">${s.zombies_180d}</b></div>`;
  const tb = document.querySelector('#z tbody');
  tb.innerHTML = '';
  for(const m of s.sample_zombies){
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${m.title||'(untitled)'} (${m.id})</td>
                    <td>${m.age_days}</td>
                    <td class="muted">${(m.release_date||'').slice(0,10)}</td>
                    <td>
                      <button onclick="approve(${JSON.stringify(m.id)})">Approve anyway</button>
                      <button onclick="maybe(${JSON.stringify(m.id)})">Maybe later</button>
                    </td>`;
    tb.appendChild(tr);
  }
}
async function approve(id){
  await fetch('/curate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action:'approve'})});
  alert('Approved '+id+' (no providers yet)'); 
}
async function maybe(id){
  await fetch('/curate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action:'maybe'})});
  alert('Marked maybe '+id);
}
run();
</script>
"""

@APP.get("/inspect")
def inspect():
    return _INSPECT_HTML

if __name__ == "__main__":
    APP.run(host="127.0.0.1", port=5100, debug=False)