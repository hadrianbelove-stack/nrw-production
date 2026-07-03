#!/usr/bin/env python3
"""Generate tvOS assets for NRW app — "The Wall" design (approved Jul 2026).

App icon is a layered tvOS imagestack:
  Back   = dark diagonal gradient + soft teal glow
  Middle = abstract wall of poster-shaped cards (one teal accent) + legibility shade
  Front  = NRW wordmark, Helvetica Neue Thin, white->teal gradient (site masthead match)

Top shelf = same wall motif behind "THE NEW RELEASE WALL" + slogan.

Run it, then copy tvos-assets/ outputs into
ios/Assets.xcassets/Brand Assets.brandassets/ (filenames match the catalog).
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import os

SCRIPT_DIR = Path(__file__).resolve().parent
output_dir = str(SCRIPT_DIR / "tvos-assets")
os.makedirs(output_dir, exist_ok=True)

# NRW Brand Colors
TEAL = (0, 212, 170)        # #00d4aa - primary accent
DARK_BG = (10, 10, 12)      # darkest
DARK_BLUE = (26, 26, 46)    # #1a1a2e - dark with hint of blue
WHITE = (255, 255, 255)

HELVETICA_NEUE = "/System/Library/Fonts/HelveticaNeue.ttc"
THIN, LIGHT = 12, 7  # face indices in the .ttc

SLOGAN = "What came out, every day."

# Muted cinematic poster palette (deterministic — no RNG, output is reproducible)
PALETTE = [
    (43, 58, 85), (92, 46, 46), (74, 68, 88), (52, 80, 63), (107, 85, 55),
    (51, 56, 68), (85, 58, 92), (39, 75, 82), (96, 70, 50), (60, 44, 66),
    (46, 66, 96), (100, 52, 60), (58, 72, 58), (70, 60, 90), (88, 78, 48),
    (40, 52, 60), (78, 48, 78), (48, 84, 88), (90, 60, 40), (54, 48, 80),
]


def get_font(size, idx=THIN):
    try:
        return ImageFont.truetype(HELVETICA_NEUE, size, index=idx)
    except Exception:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)


def tracked_mask(text, fnt, tracking):
    """Render letterspaced text as an L-mode mask, tightly cropped."""
    widths = [fnt.getlength(c) for c in text]
    asc, desc = fnt.getmetrics()
    w = int(sum(widths) + tracking * (len(text) - 1)) + 40
    img = Image.new("L", (w, asc + desc + 40), 0)
    d = ImageDraw.Draw(img)
    x = 20.0
    for c, wd in zip(text, widths):
        d.text((x, 20), c, font=fnt, fill=255)
        x += wd + tracking
    return img.crop(img.getbbox())


def gradient_text(mask, c1=WHITE, c2=TEAL):
    """Fill a text mask with the site wordmark's 45deg white->teal gradient."""
    w, h = mask.size
    xx, yy = np.meshgrid(np.arange(w), np.arange(h))
    t = (xx + (h - yy)) / float(w + h)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for i in range(3):
        arr[..., i] = (c1[i] * (1 - t) + c2[i] * t).astype(np.uint8)
    arr[..., 3] = np.array(mask)
    return Image.fromarray(arr)


def diag_gradient(size, c1=DARK_BG, c2=DARK_BLUE):
    w, h = size
    xx, yy = np.meshgrid(np.arange(w), np.arange(h))
    t = (xx + yy) / float(w + h)
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for i in range(3):
        arr[..., i] = (c1[i] * (1 - t) + c2[i] * t).astype(np.uint8)
    return Image.fromarray(arr)


def teal_glow(base, center, radius, strength):
    """Soft teal radial glow blended onto an RGB image."""
    glow = Image.new("L", base.size, 0)
    d = ImageDraw.Draw(glow)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=strength)
    glow = glow.filter(ImageFilter.GaussianBlur(radius / 2.2))
    overlay = Image.new("RGB", base.size, TEAL)
    return Image.composite(overlay, base, glow)


def poster_wall(size, card_w, gap, dim, accent_idx):
    """Abstract wall of poster-shaped cards on transparent RGBA."""
    w, h = size
    card_w, gap = int(card_w), int(gap)
    card_h = int(card_w * 1.5)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cols = w // (card_w + gap) + 2
    rows = h // (card_h + gap) + 2
    k = 0
    for r in range(rows):
        off = (card_w + gap) // 2 if r % 2 else 0
        for c in range(cols):
            x = c * (card_w + gap) - off - gap
            y = r * (card_h + gap) - gap // 2
            col = tuple(int(v * dim) for v in PALETTE[k % len(PALETTE)])
            rad = max(6, card_w // 12)
            if k == accent_idx:
                d.rounded_rectangle([x, y, x + card_w, y + card_h], rad, fill=TEAL + (235,))
            else:
                d.rounded_rectangle([x, y, x + card_w, y + card_h], rad, fill=col + (255,))
                # subtle two-tone to suggest artwork
                top = tuple(min(255, int(v * 1.35)) for v in col)
                d.rounded_rectangle([x, y, x + card_w, y + int(card_h * 0.45)], rad, fill=top + (90,))
            k += 1
    return img


# ============================================
# APP ICON LAYERS — design tuned at 800x480 (@2x), scaled by width
# ============================================

def icon_back(size):
    s = size[0] / 800.0
    return teal_glow(diag_gradient(size), (int(400 * s), int(560 * s)), int(420 * s), 26)


def icon_middle(size):
    s = size[0] / 800.0
    layer = poster_wall(size, 92 * s, 16 * s, dim=0.95, accent_idx=20)
    shade = Image.new("RGBA", size, (0, 0, 0, 70))  # legibility shade travels with the wall
    layer.alpha_composite(shade)
    return layer


def icon_front(size):
    s = size[0] / 800.0
    fnt = get_font(int(200 * s), THIN)
    txt = gradient_text(tracked_mask("NRW", fnt, 200 * s * 0.18))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.alpha_composite(txt, ((size[0] - txt.size[0]) // 2,
                                (size[1] - txt.size[1]) // 2 - int(8 * s)))
    return layer


def icon_flat(size):
    comp = icon_back(size).convert("RGBA")
    comp.alpha_composite(icon_middle(size))
    comp.alpha_composite(icon_front(size))
    return comp.convert("RGB")


# ============================================
# TOP SHELF — design tuned at 2320x720 (wide @1x), scaled by width
# ============================================

def top_shelf(size, safe_frac=0.86):
    """safe_frac = max wordmark width as a fraction of image width.

    The WIDE shelf (2320/4640) is wider than the 1920 screen — the extra
    ~200px per side are parallax bleed and get cropped on the home screen,
    so its text must fit the visible center (pass ~0.70), not the full image.
    """
    s = size[0] / 2320.0
    comp = diag_gradient(size).convert("RGBA")
    comp.alpha_composite(poster_wall(size, 150 * s, 26 * s, dim=0.9, accent_idx=42))
    # center vignette so the wordmark owns the middle
    w, h = size
    v = Image.new("L", size, 0)
    ImageDraw.Draw(v).ellipse([w * 0.15, -h * 0.2, w * 0.85, h * 1.2], fill=135)
    v = v.filter(ImageFilter.GaussianBlur(150 * s))
    comp = Image.composite(Image.new("RGBA", size, (5, 5, 8, 255)), comp, v).convert("RGBA")

    wm = tracked_mask("THE NEW RELEASE WALL", get_font(int(170 * s), THIN), 170 * s * 0.14)
    if wm.size[0] > w * safe_frac:
        sc = w * safe_frac / wm.size[0]
        wm = wm.resize((int(wm.size[0] * sc), int(wm.size[1] * sc)), Image.LANCZOS)
    txt = gradient_text(wm)
    tx, ty = (w - txt.size[0]) // 2, int(h * 0.30)
    comp.alpha_composite(txt, (tx, ty))

    sm = tracked_mask(SLOGAN, get_font(int(58 * s), LIGHT), 58 * s * 0.06)
    st = Image.new("RGBA", sm.size, (235, 240, 240, 255))
    st.putalpha(sm)
    comp.alpha_composite(st, ((w - sm.size[0]) // 2, ty + txt.size[1] + int(52 * s)))
    return comp.convert("RGB")


def save(img, name):
    img.save(f"{output_dir}/{name}")
    print(f"  Created {name} ({img.size[0]}x{img.size[1]})")


print("Generating tvOS assets — 'The Wall' design...")

# App icon: render @2x, downscale for @1x
back2x, mid2x, front2x = icon_back((800, 480)), icon_middle((800, 480)), icon_front((800, 480))
save(back2x, "AppIcon-Back-2x.png")
save(mid2x, "AppIcon-Middle-2x.png")
save(front2x, "AppIcon-Front-2x.png")
save(back2x.resize((400, 240), Image.LANCZOS), "AppIcon-Back-1x.png")
save(mid2x.resize((400, 240), Image.LANCZOS), "AppIcon-Middle-1x.png")
save(front2x.resize((400, 240), Image.LANCZOS), "AppIcon-Front-1x.png")

# Combined flattened versions (reference / "All" slot)
save(icon_flat((800, 480)), "AppIcon-All-2x.png")
save(icon_flat((800, 480)).resize((400, 240), Image.LANCZOS), "AppIcon-All-1x.png")

# App Store icon stack (1280x768, single scale — same 5:3 aspect)
save(icon_back((1280, 768)), "AppIcon-AppStore-Back.png")
save(icon_middle((1280, 768)), "AppIcon-AppStore-Middle.png")
save(icon_front((1280, 768)), "AppIcon-AppStore-Front.png")

# Top shelf wide: render @2x (4640x1440), downscale for @1x
# 0.70 keeps the wordmark inside the visible 1920 center + focus-parallax slide
wide2x = top_shelf((4640, 1440), safe_frac=0.70)
save(wide2x, "TopShelf-Wide-2x.png")
save(wide2x.resize((2320, 720), Image.LANCZOS), "TopShelf-Wide-1x.png")

# Top shelf regular: 1920x720 @1x / 3840x1440 @2x (refit, not cropped)
reg2x = top_shelf((3840, 1440))
save(reg2x, "TopShelf-2x.png")
save(reg2x.resize((1920, 720), Image.LANCZOS), "TopShelf-1x.png")

print(f"\n✓ All assets saved to: {output_dir}")
print("\nNext: copy into ios/Assets.xcassets/Brand Assets.brandassets/ (filenames match)")
