#!/usr/bin/env python3
"""
Generate per-movie share assets for the NRW web site.

For every visible movie in data.json this writes two things:
  1. assets/cards/<id>.png  — a branded 1200x630 Open Graph card (poster + title + scores)
  2. m/<id>.html            — a tiny stub page whose ONLY job is to carry that movie's
                              OG/Twitter meta (so iMessage/Twitter/Slack show the card) and
                              then JS-redirect a real browser to ../?m=<id>.

Why a stub page at all: the site is a static SPA. Social crawlers do not run JavaScript,
so they can never see anything app.js / mobile.js render. The only way to get a per-movie
link preview is a real HTML file with per-movie <meta> tags. The crawler reads the meta and
stops; a human's browser runs the <script> and lands on the wall with the movie open.

These outputs are intentionally gitignored. They are regenerated fresh in the publish
workflow before the Pages artifact is uploaded, so nothing binary churns the git history.
Run locally any time to preview:  python3 scripts/generate_share_pages.py --limit 5
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JSON = os.path.join(ROOT, "data.json")
CARDS_DIR = os.path.join(ROOT, "assets", "cards")
STUBS_DIR = os.path.join(ROOT, "m")

# Public base URL — OG tags MUST be absolute (crawlers fetch them out of context).
SITE_BASE = "https://hadrianbelove-stack.github.io/nrw-production/"

# Brand palette (matches the rest of NRW)
BG = (10, 10, 10)          # #0a0a0a
TEAL = (0, 212, 170)       # #00d4aa
WHITE = (245, 245, 245)
MUTED = (150, 150, 150)
POSTER_BG = (26, 26, 46)   # placeholder fill when a movie has no poster

CARD_W, CARD_H = 1200, 630

# Lato lives in the Roku app; fall back to system fonts so this runs anywhere (incl. CI).
_FONT_CANDIDATES = {
    "black": [
        os.path.join(ROOT, "NRWApp-Roku", "fonts", "Lato-Black.ttf"),
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "bold": [
        os.path.join(ROOT, "NRWApp-Roku", "fonts", "Lato-Bold.ttf"),
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "regular": [
        os.path.join(ROOT, "NRWApp-Roku", "fonts", "Lato-Regular.ttf"),
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
}


def get_font(weight, size):
    for path in _FONT_CANDIDATES[weight]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def is_visible(m):
    return (
        not m.get("hidden")
        and m.get("_enrichment_status") != "reverted"
        and bool(m.get("digital_date"))
    )


def fetch_poster(url, timeout=15):
    """Download a poster; return a PIL Image or None on any failure."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NRW-share-card/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            from io import BytesIO
            return Image.open(BytesIO(resp.read())).convert("RGB")
    except Exception as e:
        print(f"  ! poster fetch failed ({e})", file=sys.stderr)
        return None


def wrap_lines(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_title(draw, text, max_w, max_lines=3):
    """Pick the largest size whose wrap fits in max_lines; ellipsize if it still overflows."""
    for size in (66, 58, 50, 44, 38):
        font = get_font("black", size)
        lines = wrap_lines(draw, text, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
    font = get_font("black", 38)
    lines = wrap_lines(draw, text, font, max_w)[:max_lines]
    if lines:
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return font, lines


def make_card(m, out_path):
    img = Image.new("RGB", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)

    margin = 48
    poster_h = CARD_H - 2 * margin
    poster_w = round(poster_h * 2 / 3)  # 2:3 poster aspect

    # Poster (or placeholder)
    poster = fetch_poster(m.get("poster"))
    px, py = margin, margin
    if poster is not None:
        poster = poster.resize((poster_w, poster_h))
        img.paste(poster, (px, py))
    else:
        draw.rectangle([px, py, px + poster_w, py + poster_h], fill=POSTER_BG)
        ph_font = get_font("black", 48)
        draw.text((px + poster_w / 2, py + poster_h / 2), "NRW",
                  font=ph_font, fill=MUTED, anchor="mm")
    draw.rectangle([px, py, px + poster_w, py + poster_h], outline=(60, 60, 60), width=2)

    tx = px + poster_w + 56
    tw = CARD_W - 56 - tx
    y = margin

    # Wordmark
    wm_font = get_font("bold", 26)
    draw.text((tx, y), "THE NEW RELEASE WALL", font=wm_font, fill=TEAL)
    y += 52

    # Title — drop a trailing non-Latin parenthetical (bilingual original title) so
    # the card doesn't render CJK as tofu boxes; Lato (and CI fonts) lack those glyphs.
    title = (m.get("display_title") or m.get("title") or "Untitled").strip()
    stripped = re.sub(r"\s*\([^)]*[^\x00-\x7f][^)]*\)\s*$", "", title).strip()
    if stripped:
        title = stripped
    title_font, title_lines = fit_title(draw, title, tw)
    line_h = title_font.size + 8
    for line in title_lines:
        draw.text((tx, y), line, font=title_font, fill=WHITE)
        y += line_h
    y += 8

    # Year + director
    meta_font = get_font("regular", 30)
    bits = []
    if m.get("year"):
        bits.append(str(m["year"]))
    director = (m.get("crew") or {}).get("director")
    if director and director.strip().lower() != "unknown":
        bits.append(f"Dir. {director}")
    if bits:
        draw.text((tx, y), "  •  ".join(bits), font=meta_font, fill=MUTED)
        y += 44

    # Scores
    score_font = get_font("bold", 34)
    tokens = []
    if m.get("rt_score"):
        tokens.append(f"RT {m['rt_score']}")
    if m.get("imdb_rating"):
        tokens.append(f"IMDb {m['imdb_rating']}")
    if m.get("metacritic_score"):
        tokens.append(f"MC {m['metacritic_score']}")
    if tokens:
        draw.text((tx, y + 6), "    ".join(tokens), font=score_font, fill=TEAL)

    # Slogan pinned to the bottom of the text column
    slogan_font = get_font("regular", 24)
    draw.text((tx, CARD_H - margin - 24), "Bringing back browsing.",
              font=slogan_font, fill=MUTED)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG")


def share_description(m, limit=180):
    text = m.get("capsule") or m.get("synopsis") or ""
    text = text.replace("//", " ").replace("\n", " ")
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


STUB_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_disp} — The New Release Wall</title>
<link rel="icon" href="../favicon.png">
<meta property="og:type" content="video.movie">
<meta property="og:site_name" content="The New Release Wall">
<meta property="og:title" content="{title_attr}">
<meta property="og:description" content="{desc_attr}">
<meta property="og:url" content="{base}m/{id}.html">
<meta property="og:image" content="{base}assets/cards/{id}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_attr}">
<meta name="twitter:description" content="{desc_attr}">
<meta name="twitter:image" content="{base}assets/cards/{id}.png">
<script>location.replace('../?m={id}');</script>
</head>
<body style="background:#0a0a0a;color:#f5f5f5;font-family:system-ui,Arial,sans-serif;text-align:center;padding:48px">
<p><a href="../?m={id}" style="color:#00d4aa;text-decoration:none">Opening {title_disp} on The New Release Wall →</a></p>
<noscript><p><a href="../?m={id}" style="color:#00d4aa">View {title_disp} →</a></p></noscript>
</body>
</html>
"""


def make_stub(m, out_path):
    mid = str(m["id"])
    title = (m.get("display_title") or m.get("title") or "Untitled").strip()
    year = m.get("year")
    title_disp = f"{title} ({year})" if year else title
    desc = share_description(m)
    htmlc = STUB_TEMPLATE.format(
        id=mid,
        base=SITE_BASE,
        title_disp=html.escape(title_disp),
        title_attr=html.escape(title_disp, quote=True),
        desc_attr=html.escape(desc, quote=True),
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(htmlc)


def main():
    ap = argparse.ArgumentParser(description="Generate per-movie share cards + OG stub pages")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N movies (testing)")
    ap.add_argument("--skip-cards", action="store_true", help="write stubs only (skip image generation)")
    args = ap.parse_args()

    with open(DATA_JSON, encoding="utf-8") as f:
        data = json.load(f)

    movies = [m for m in data.get("movies", []) if is_visible(m) and m.get("id") is not None]
    if args.limit:
        movies = movies[: args.limit]

    os.makedirs(CARDS_DIR, exist_ok=True)
    os.makedirs(STUBS_DIR, exist_ok=True)

    cards = stubs = errors = 0
    for i, m in enumerate(movies, 1):
        mid = str(m["id"])
        try:
            make_stub(m, os.path.join(STUBS_DIR, f"{mid}.html"))
            stubs += 1
            if not args.skip_cards:
                make_card(m, os.path.join(CARDS_DIR, f"{mid}.png"))
                cards += 1
        except Exception as e:
            errors += 1
            print(f"  ! {mid}: {e}", file=sys.stderr)
        if i % 50 == 0:
            print(f"  …{i}/{len(movies)}")

    print(f"Done: {stubs} stubs, {cards} cards, {errors} errors → m/, assets/cards/")
    return 1 if errors and stubs == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
