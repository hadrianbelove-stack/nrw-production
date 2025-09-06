import json, html, re
from pathlib import Path

root = Path(__file__).parent
data_p = root/"output/data.json"
tpl_p  = root/"_design/site_base.html"
outdir = root/"output/site"
outdir.mkdir(parents=True, exist_ok=True)
out_p  = outdir/"index.html"

# 1) load data
data = json.load(open(data_p)) if data_p.exists() else []
movies = [m for m in data if m.get("has_digital")]

# 2) build cards (poster, title, providers, RT)
def prov_names(p):
    if isinstance(p, dict):
        names = []
        for bucket in ("stream","flatrate","buy","rent"):
            for it in (p.get(bucket) or []):
                name = it.get("provider_name") or it.get("name")
                if name: names.append(name)
        return sorted(set(names))
    if isinstance(p, list):
        return sorted(set([(x.get("provider_name") or x.get("name") or "").strip() for x in p if isinstance(x, dict)]))
    return []

cards_html = []
for m in movies:
    title = html.escape(str(m.get("title","")))
    poster = m.get("poster") or m.get("poster_path") or ""
    if poster and not poster.startswith("http"):
        # fallback TMDB path if only a path was stored
        poster = f"https://image.tmdb.org/t/p/w500{poster}"
    rt = m.get("rt_score")
    rtbadge = f"🍅 {rt}%" if isinstance(rt,(int,float)) else "🍅 —"
    providers = prov_names(m.get("providers") or [])
    chips = "".join(f'<span class="chip">{html.escape(x)}</span>' for x in providers[:8])

    cards_html.append(f"""
      <article class="card">
        <div class="poster-wrap"><img src="{poster}" alt="{title}" loading="lazy"/></div>
        <h3 class="title">{title}</h3>
        <div class="meta">
          <span class="rt">{rtbadge}</span>
        </div>
        <div class="providers">{chips}</div>
      </article>
    """.strip())

cards = "\n".join(cards_html)

# 3) load template and inject
tpl = open(tpl_p, encoding="utf-8").read()

# Ensure the header says The New Release Wall
tpl = re.sub(r"(<h1[^>]*>)(.*?)(</h1>)", r"\1The New Release Wall\3", tpl, flags=re.I|re.S)

# Insert cards at a marker if present, else before </main> else before </body>
for marker in ("<!-- CARDS -->","<!-- {{CARDS}} -->","{{CARDS}}"):
    if marker in tpl:
        tpl = tpl.replace(marker, cards)
        break
else:
    if "</main>" in tpl:
        tpl = tpl.replace("</main>", cards + "\n</main>")
    else:
        tpl = tpl.replace("</body>", cards + "\n</body>")

# Minimal CSS safety net if template lacks card styles
if "class=\"card\"" not in tpl or "chip" not in tpl:
    css = """
    <style>
      :root{--bg:#0c0c0f;--panel:#151518;--ink:#eaeaea;--muted:#a1a1aa;--ring:#2a2a2f;}
      body{background:var(--bg);color:var(--ink);font-family:system-ui, -apple-system, Segoe UI, Roboto, sans-serif;margin:0}
      .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;padding:20px}
      .card{background:var(--panel);border:1px solid var(--ring);border-radius:14px;overflow:hidden}
      .poster-wrap{aspect-ratio:2/3;background:#222}
      .poster-wrap img{width:100%;height:100%;object-fit:cover;display:block}
      .title{font-size:16px;margin:10px 12px 0}
      .meta{display:flex;gap:8px;align-items:center;margin:6px 12px;color:var(--muted)}
      .providers{display:flex;flex-wrap:wrap;gap:6px;margin:8px 12px 12px}
      .chip{border:1px solid var(--ring);padding:2px 8px;border-radius:999px;font-size:12px}
      header h1{margin:0;padding:16px 20px;font-size:22px}
      main .grid{padding-top:0}
    </style>
    """
    tpl = tpl.replace("</head>", css + "\n</head>")

# Ensure there is a grid wrapper; if template already has it, we don't add another
if "class=\"grid\"" not in tpl:
    tpl = tpl.replace("<main>", "<main>\n<div class=\"grid\">", 1)
    tpl = tpl.replace("</main>", "</div>\n</main>", 1)

open(out_p, "w", encoding="utf-8").write(tpl)
print(f"Rendered {len(movies)} cards → {out_p}")
