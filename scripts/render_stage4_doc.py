#!/usr/bin/env python3
"""Render the /curate Stage 4 walkthrough doc — every queued film's full
presentation (capsule variants, factoid primer, suggested links, pull quotes)
assembled from overnight caches into one self-contained HTML page.

No LLM, no network: pure cache + data.json reads, <1s. Run at session start so
the doc always reflects the current queue (films drained by parallel windows
disappear). Chat then walks the films one at a time with short pointers.

This script is the single source of truth for the Stage-4 presentation;
.claude/commands/capsule.md Step 2 stays the template for standalone /capsule
and cache-miss fallbacks — a change to one should touch both.

Usage:
  render_stage4_doc.py [--window N] [--out PATH]
      Writes cache/stage4_doc.html and prints the queue summary.
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curate_list import capsule_queue, _services, _trailer  # noqa: E402
from get_quotes import _find_entry, _ordered_quotes, SPOILER_PREFIX, LB_MAX  # noqa: E402

CAPSULE_CACHE = "cache/capsule_cache.json"
QUOTES_CACHE = "cache/pull_quotes_combined.json"
OUT_DEFAULT = "cache/stage4_doc.html"

# Matches VARIANT_ANGLES order in gemini_scraper/capsule.py and the labels in
# .claude/commands/capsule.md Step 2.
VARIANT_LABELS = ["premise", "detail", "reception"]

CSS = """
body { font-family: -apple-system, 'Helvetica Neue', sans-serif; margin: 0;
       background: #14181c; color: #e3e6e8; line-height: 1.55; }
.wrap { max-width: 860px; margin: 0 auto; padding: 28px 24px 80px; }
h1 { font-size: 22px; letter-spacing: .04em; border-bottom: 2px solid #2ec4b6;
     padding-bottom: 10px; }
.index { background: #1c2228; border-radius: 10px; padding: 14px 20px; }
.index a { color: #2ec4b6; text-decoration: none; }
.index li { margin: 4px 0; }
.film { border-top: 1px solid #2a3138; margin-top: 44px; padding-top: 24px; }
.film h2 { font-size: 19px; margin: 0 0 2px; }
.meta { color: #9aa4ad; font-style: italic; margin: 2px 0 4px; font-size: 14px; }
.kw { color: #7f8a93; font-size: 13px; margin-bottom: 10px; }
.badge { display: inline-block; background: #5a3e00; color: #ffc857;
         border-radius: 4px; padding: 0 7px; margin-left: 6px; font-size: 12px;
         font-style: normal; }
.linksrow { font-size: 13px; margin-bottom: 14px; }
.linksrow a { color: #2ec4b6; text-decoration: none; margin-right: 14px; }
.variant { background: #1c2228; border-radius: 10px; padding: 14px 18px;
           margin: 10px 0; }
.variant .vnum { color: #2ec4b6; font-weight: 700; }
.variant .wc { color: #7f8a93; font-size: 12.5px; font-style: italic; }
h3 { font-size: 13px; letter-spacing: .1em; color: #9aa4ad;
     text-transform: uppercase; margin: 22px 0 8px; }
.primer li { margin: 7px 0; font-size: 14.5px; }
.slinks li { margin: 5px 0; }
.slinks a { color: #2ec4b6; }
.slinks .desc { color: #9aa4ad; font-style: italic; }
.quote { margin: 12px 0; font-size: 14.5px; }
.quote .qnum { color: #2ec4b6; font-weight: 700; }
.quote .attr { color: #9aa4ad; font-size: 13.5px; }
.outlet { color: #e3e6e8; font-weight: 700; margin: 16px 0 2px; font-size: 14px; }
.warn { background: #3a2b12; color: #ffc857; border-radius: 8px;
        padding: 8px 14px; margin: 10px 0; font-size: 14px; }
.note { color: #7f8a93; font-size: 13px; font-style: italic; }
"""


def md_to_html(text):
    """Minimal markdown → HTML for capsule/quote text: bold, italics, escapes."""
    out = html.escape(text or "")
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\*(.+?)\*", r"<em>\1</em>", out)
    return out


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")


def _cache_entry(cache, title, year):
    """Exact key first, then scan by stored title/year (same spirit as the
    quote cache's _find_entry)."""
    key = f"{title}_{year}"
    if key in cache:
        return cache[key]
    tl = (title or "").lower()
    for e in cache.values():
        if isinstance(e, dict) and str(e.get("title", "")).lower() == tl \
                and str(e.get("year", "")) == str(year):
            return e
    return None


def film_header(n, total, m):
    title = m.get("title", "?")
    year = m.get("year", "?")
    crew = m.get("crew") or {}
    director = crew.get("director") if isinstance(crew, dict) else None
    genres = ", ".join((m.get("genres") or [])[:2])
    runtime = m.get("runtime")
    country = m.get("country") or ""
    platforms = ", ".join(_services(m))
    meta_bits = [b for b in [
        f"directed by {director}" if director else None,
        genres or None,
        f"{runtime} min" if runtime else None,
        country or None,
        platforms or None,
    ] if b]

    badges = []
    if m.get("is_slop"):
        badges.append("SLOP")
    if (m.get("filters") or {}).get("is_virtual_screening"):
        badges.append("VIRTUAL SCREENING")
    if (m.get("digital_date") or "") > str(date.today()):
        badges.append("PREORDER")
    kw = " · ".join((m.get("keywords") or [])[:6])

    L = m.get("links") or {}
    links = []
    if L.get("wikipedia"):
        links.append(f'<a href="{html.escape(L["wikipedia"])}">Wikipedia</a>')
    trailer = _trailer(m)
    if trailer:
        links.append(f'<a href="{html.escape(trailer)}">▶ Trailer</a>')
    if L.get("rt"):
        rt = m.get("rt_score")
        links.append(f'<a href="{html.escape(L["rt"])}">RT {rt or "--"}</a>')
    if L.get("imdb"):
        links.append(f'<a href="{html.escape(L["imdb"])}">IMDb {m.get("imdb_rating") or "--"}</a>')

    h = [f'<section class="film" id="{slug(title)}">']
    h.append(f"<h2>#{n} of {total} — {html.escape(str(title))} ({year})</h2>")
    badge_html = "".join(f'<span class="badge">{b}</span>' for b in badges)
    if meta_bits:
        h.append(f'<div class="meta">{html.escape(" | ".join(meta_bits))}{badge_html}</div>')
    elif badge_html:
        h.append(f'<div class="meta">{badge_html}</div>')
    if kw:
        h.append(f'<div class="kw">{html.escape(kw)}</div>')
    if links:
        h.append(f'<div class="linksrow">{" ".join(links)}</div>')
    return "\n".join(h)


def variants_html(entry):
    if not entry or not entry.get("capsules"):
        return ('<div class="warn">⚠ no cached variants — this film arrived '
                "after the nightly run; capsules will generate live in chat</div>")
    out = []
    for i, cap in enumerate(entry["capsules"], 1):
        label = VARIANT_LABELS[(i - 1) % len(VARIANT_LABELS)]
        wc = len((cap or "").split())
        out.append(
            f'<div class="variant"><span class="vnum">{i}.</span> '
            f"{md_to_html(cap)} "
            f'<span class="wc">({wc} words — {label})</span></div>'
        )
    return "\n".join(out)


def primer_html(entry):
    primer = (entry or {}).get("factoid_primer") or ""
    if not primer:
        return ""
    items = [l.lstrip("• ").strip() for l in primer.split("\n") if l.strip()]
    lis = "\n".join(f"<li>{md_to_html(b)}</li>" for b in items)
    return f"<h3>Factoid primer</h3>\n<ul class=\"primer\">{lis}</ul>"


def slinks_html(entry):
    if entry is None:
        return ""
    if "suggested_links" not in entry:
        return ('<h3>Suggested links</h3><div class="warn">⚠ links not cached '
                "(pre-upgrade cache entry) — chat will search live for this film</div>")
    links = entry.get("suggested_links") or []
    if not links:
        return '<h3>Suggested links</h3><div class="note">none found</div>'
    lis = []
    for i, l in enumerate(links, 1):
        desc = f' — <span class="desc">{html.escape(l.get("wiki_description") or "")}</span>' \
            if l.get("wiki_description") else ""
        lis.append(f'<li>{i}. <a href="{html.escape(l.get("url", ""))}">'
                   f'{html.escape(l.get("name", "?"))}</a>{desc}</li>')
    return "<h3>Suggested links</h3>\n<ul class=\"slinks\">" + "\n".join(lis) + "</ul>"


def quotes_html(qcache, title, year):
    """Numbered exactly like get_quotes.py display/--select (same
    _ordered_quotes) — the number in the doc is the number the save writes."""
    try:
        key = _find_entry(qcache, title, year)
    except SystemExit:  # ambiguous-title guard in _find_entry
        key = None
    if key is None:
        return '<h3>Pull quotes</h3><div class="warn">⚠ no quotes in cache — skip or add --custom</div>'
    items, lb_hidden = _ordered_quotes(qcache[key])
    if not items:
        return '<h3>Pull quotes</h3><div class="warn">⚠ cache entry holds 0 quotes — treat as missing</div>'
    out = ["<h3>Pull quotes</h3>"]
    prev_group = None
    for n, (group, q) in enumerate(items, 1):
        if group != prev_group:
            out.append(f'<div class="outlet">{html.escape(group)}</div>')
            prev_group = group
        if group == "Letterboxd":
            attr = f"— @{(q.get('critic') or '?').lstrip('@')}"
        else:
            attr = f"— {q.get('critic') or '?'}, {q.get('outlet') or group}"
        if q.get("selected"):
            attr += "   ✓ selected"
        text = (q.get("text") or "").strip()
        if text.startswith(SPOILER_PREFIX):
            url = q.get("review_url") or ""
            body = f'<span class="attr">{html.escape(attr)}</span> → <a href="{html.escape(url)}">read review</a>'
        else:
            body = (f'<em>"{md_to_html(text)}"</em><br>'
                    f'<span class="attr">{html.escape(attr)}</span>')
        out.append(f'<div class="quote"><span class="qnum">{n}.</span> {body}</div>')
    if lb_hidden:
        out.append(f'<div class="note">({lb_hidden} more Letterboxd quote(s) in cache '
                   f"not shown — cap is {LB_MAX})</div>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args()

    queue = capsule_queue(args.window)
    ccache = json.load(open(CAPSULE_CACHE)) if os.path.exists(CAPSULE_CACHE) else {}
    qcache = json.load(open(QUOTES_CACHE)) if os.path.exists(QUOTES_CACHE) else {}

    total = len(queue)
    if total == 0:
        print("Stage 4: nothing needs capsules or quotes in the window — no doc written.")
        return

    idx, sections = [], []
    for n, (m, needs) in enumerate(queue, 1):
        title, year = m.get("title", "?"), m.get("year", "?")
        entry = _cache_entry(ccache, title, year)
        flags = []
        if not (entry and entry.get("capsules")):
            flags.append("⚠ no cached variants")
        idx.append(f'<li><a href="#{slug(title)}">#{n} — {html.escape(str(title))} '
                   f"({year})</a> <span class=\"note\">{'+'.join(needs)}"
                   f"{(' · ' + ' '.join(flags)) if flags else ''}</span></li>")
        parts = [film_header(n, total, m)]
        if "capsule" in needs:
            parts.append(variants_html(entry))
            parts.append(primer_html(entry))
            parts.append(slinks_html(entry))
        else:
            parts.append('<div class="note">capsule already approved — quotes only</div>')
        if "quotes" in needs:
            parts.append(quotes_html(qcache, title, year))
        else:
            parts.append('<div class="note">quotes already handled</div>')
        parts.append("</section>")
        sections.append("\n".join(p for p in parts if p))

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>NRW Stage 4 — {total} film(s) · {date.today()}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>STAGE 4 — {total} film(s) to curate · {date.today()}</h1>
<div class="index"><ol>{''.join(idx)}</ol></div>
{''.join(sections)}
</div></body></html>"""

    with open(args.out, "w") as f:
        f.write(doc)
    print(f"Wrote {args.out} — {total} film(s):")
    for n, (m, needs) in enumerate(queue, 1):
        print(f"  #{n}  {m.get('title')} ({m.get('year')}) — {'+'.join(needs)}")


if __name__ == "__main__":
    main()
