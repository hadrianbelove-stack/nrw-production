#!/usr/bin/env python3
"""
Generate the site-level hero share image: assets/share-card.png.

This is the og:image for the ROOT url on both desktop and mobile (see the <meta>
tags in index.html / mobile/index.html). A poster-wall collage under a brand
masthead — wordmark "THE NEW RELEASE WALL" + the tagline "What came out, every
day." — centered on a dark band.

Reproducible replacement for the old hand-made card, which had the retired second
slogan line baked into the pixels. Reuses the brand
palette + font/poster helpers from generate_share_pages.py so the treatment matches
the per-movie cards.

Run:  python3 scripts/generate_hero_card.py
"""
import os
import sys
import json

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_share_pages import (  # reuse — do not reinvent
    ROOT, DATA_JSON, get_font, fetch_poster, is_visible,
    BG, TEAL, WHITE,
)

OUT = os.path.join(ROOT, "assets", "share-card.png")
CARD_W, CARD_H = 1200, 630
WORDMARK = "THE NEW RELEASE WALL"
SLOGAN = "What came out, every day."   # single tagline (older second line retired)
COLS = 9                                # poster strips across the collage
DARK = (8, 8, 10)


def load_posters(limit):
    """Newest visible movies with a poster; returns a list of PIL Images."""
    with open(DATA_JSON, encoding="utf-8") as f:
        data = json.load(f)
    movies = [m for m in data.get("movies", []) if is_visible(m) and m.get("poster")]
    movies.sort(key=lambda m: m.get("digital_date", ""), reverse=True)
    out = []
    for m in movies:
        img = fetch_poster(m.get("poster"))
        if img is not None:
            out.append(img)
        if len(out) >= limit:
            break
    return out


def build_collage(posters):
    """Tile full-height, center-cropped poster strips across the canvas."""
    canvas = Image.new("RGB", (CARD_W, CARD_H), BG)
    strip_w = CARD_W // COLS + 1
    x = i = 0
    while x < CARD_W:
        p = posters[i % len(posters)]
        scale = CARD_H / p.height
        w = max(1, int(round(p.width * scale)))
        p2 = p.resize((w, CARD_H))
        left = max(0, (w - strip_w) // 2)
        canvas.paste(p2.crop((left, 0, left + strip_w, CARD_H)), (x, 0))
        x += strip_w
        i += 1
    return canvas


def darken_bottom(canvas):
    """Fade the collage into a solid dark band at the bottom so text is legible."""
    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    band_top = CARD_H - 175            # solid dark band that holds the text
    grad_top = int(CARD_H * 0.38)      # gradient blends collage -> band
    for y in range(CARD_H):
        if y >= band_top:
            a = 240
        elif y >= grad_top:
            a = int(30 + (240 - 30) * ((y - grad_top) / (band_top - grad_top)))
        else:
            a = int(30 * (y / grad_top))   # faint top vignette
        od.line([(0, y), (CARD_W, y)], fill=(*DARK, a))
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def draw_centered_tracked(draw, cx, y, text, font, fill, tracking):
    """Centered text with per-character letter-spacing (PIL has no tracking)."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill, anchor="lm")
        x += w + tracking


def main():
    posters = load_posters(limit=COLS + 4)
    if not posters:
        print("No posters available; aborting (share-card.png unchanged).", file=sys.stderr)
        return 1

    canvas = darken_bottom(build_collage(posters))
    draw = ImageDraw.Draw(canvas)
    cx = CARD_W // 2

    draw_centered_tracked(draw, cx, CARD_H - 112, WORDMARK,
                          get_font("black", 54), TEAL, tracking=12)
    draw.text((cx, CARD_H - 56), SLOGAN,
              font=get_font("regular", 34), fill=WHITE, anchor="mm")

    canvas.save(OUT, "PNG")
    print(f"Wrote {OUT} ({CARD_W}x{CARD_H}) from {len(posters)} posters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
