import json, html, datetime as dt
from pathlib import Path

DATA = Path("output/data.json")
OUT  = Path("output/site/index.html")
OUT.parent.mkdir(parents=True, exist_ok=True)

movies = json.load(open(DATA))

today = dt.date.today()
def not_future(d):
    if not d: return True
    s = str(d); s = s[:10]
    try: return dt.date.fromisoformat(s) <= today
    except: return True

def poster_url(m):
    # Prefer absolute poster, else TMDB path, else placeholder
    p = m.get("poster") or m.get("poster_path") or ""
    if p.startswith("http"): return p
    if p.startswith("/"):    return "https://image.tmdb.org/t/p/w500"+p
    return "data:image/svg+xml;utf8," + html.escape(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 900"><rect width="100%" height="100%" fill="#222"/><text x="50%" y="50%" fill="#777" dominant-baseline="middle" text-anchor="middle" font-family="system-ui" font-size="28">{html.escape(m.get("title",""))}</text></svg>'
    )

def prov_count(m):
    prov = m.get("providers") or []
    if isinstance(prov, list): return len(prov)
    if isinstance(prov, dict): return sum(len(v) for v in prov.values() if isinstance(v, list))
    return 0

# filter: has providers AND not in future
items = [m for m in movies if (m.get("has_digital") or prov_count(m)>0) and not_future(m.get("digital_date") or m.get("date_key") or m.get("release_date"))]

cards=[]
for m in items:
    t = html.escape(str(m.get("title","")))
    p = poster_url(m)
    pc = prov_count(m)
    rt = m.get("rt_score")
    rt_badge = f'<span class="rt">🍅 {int(rt)}%</span>' if isinstance(rt,(int,float)) else '<span class="rt muted">🍅 —</span>'
    chips=[]
    prov = m.get("providers") or {}
    if isinstance(prov, dict):
        for k in ("flatrate","stream","buy","rent"):
            for v in prov.get(k,[]) or []:
                name=str(v.get("provider_name") or v.get("name") or k).strip()
                if name: chips.append(f'<span class="chip">{html.escape(name)}</span>')
    elif isinstance(prov, list):
        for v in prov:
            name=str(v.get("provider_name") or v.get("name") or "").strip()
            if name: chips.append(f'<span class="chip">{html.escape(name)}</span>')
    chips_html = ''.join(chips[:6]) + (f'<span class="chip more">+{len(chips)-6}</span>' if len(chips)>6 else "")

    cards.append(f"""
    <article class="card">
      <div class="poster"><img loading="lazy" decoding="async" src="{p}" alt="{t}"/></div>
      <div class="meta">
        <h3>{t}</h3>
        <div class="row">
          <span class="pill">Providers: {pc}</span>
          {rt_badge}
        </div>
        <div class="chips">{chips_html}</div>
      </div>
    </article>
    """)

html_out=f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>New Release Wall — Approved + Provider-active ({len(items)} titles)</title>
<style>
:root {{
  --bg:#0f0f10; --card:#17181a; --muted:#9aa0a6; --line:#2a2d31; --pill:#22262b; --chip:#20242a;
}}
* {{ box-sizing:border-box; }}
body {{ margin:24px; background:var(--bg); color:#e8eaed; font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial, sans-serif; }}
h1 {{ margin:0 0 18px; font-size:28px; font-weight:700; }}
.grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:18px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden; box-shadow: 0 2px 10px rgba(0,0,0,.25); }}
.poster img {{ width:100%; aspect-ratio: 2/3; object-fit: cover; background:#111; display:block; }}
.meta {{ padding:12px 14px 14px; }}
h3 {{ margin:6px 0 8px; font-size:16px; line-height:1.2; }}
.row {{ display:flex; gap:8px; align-items:center; margin-bottom:8px; }}
.pill {{ background:var(--pill); padding:4px 8px; border-radius:999px; font-size:12px; color:var(--muted); border:1px solid var(--line); }}
.rt {{ padding:4px 8px; border-radius:999px; font-size:12px; background:#1f2a1f; color:#e6f4ea; border:1px solid #2c3; }}
.rt.muted {{ background:var(--pill); color:var(--muted); border-color:var(--line); }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
.chip {{ background:var(--chip); border:1px solid var(--line); color:#cfd3d7; padding:3px 8px; border-radius:8px; font-size:12px; }}
.chip.more {{ opacity:.7; }}
.header {{ display:flex; align-items:baseline; justify-content:space-between; margin-bottom:10px; color:var(--muted); }}
small {{ color:var(--muted); }}
a:link,a:visited {{ color:#8ab4f8; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
</style>
</head>
<body>
  <h1>Approved + Provider-active ({len(items)} titles)</h1>
  <div class="grid">
    {''.join(cards)}
  </div>
  <footer style="margin-top:24px;color:var(--muted)"><small>Offline render — no network calls. Uses <code>output/data.json</code>.</small></footer>
</body></html>
"""
OUT.write_text(html_out)
print(f"Rendered {len(items)} cards → {OUT}")
