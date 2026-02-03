#!/usr/bin/env python3
"""Generate tvOS assets for NRW app - Teal/Cyan color scheme"""

from PIL import Image, ImageDraw, ImageFont
import os

# Create output directory
output_dir = "/Users/hadrianbelove/Downloads/nrw-production/NRWApp-tvOS/tvos-assets"
os.makedirs(output_dir, exist_ok=True)

# NRW Brand Colors
TEAL = (0, 212, 170)        # #00d4aa - primary accent
DARK_BG = (10, 10, 10)      # #0a0a0a - darkest
DARK_BLUE = (26, 26, 46)    # #1a1a2e - dark with hint of blue
WHITE = (255, 255, 255)
GRAY = (120, 120, 120)

def create_gradient(size, color1, color2, direction='diagonal'):
    """Create a gradient image"""
    img = Image.new('RGB', size)
    w, h = size

    for y in range(h):
        for x in range(w):
            if direction == 'diagonal':
                ratio = (x + y) / (w + h)
            elif direction == 'vertical':
                ratio = y / h
            else:  # horizontal
                ratio = x / w

            r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
            g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
            b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
            img.putpixel((x, y), (r, g, b))

    return img

def draw_text_centered(draw, text, y, font, fill, width):
    """Draw centered text"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (width - text_width) // 2
    draw.text((x, y), text, font=font, fill=fill)

def get_font(size):
    """Try to load a nice font, fall back to default"""
    font_paths = [
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()

print("Generating tvOS assets with NRW teal color scheme...")

# ============================================
# APP ICON - Minimal with teal accent
# ============================================

icon_sizes = {
    '1x': (400, 240),
    '2x': (800, 480),
}

for scale, size in icon_sizes.items():
    w, h = size

    # BACK LAYER - dark gradient
    back = create_gradient(size, DARK_BG, DARK_BLUE, 'diagonal')
    back.save(f"{output_dir}/AppIcon-Back-{scale}.png")
    print(f"  Created AppIcon-Back-{scale}.png ({w}x{h})")

    # FRONT LAYER - text on transparent
    front = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(front)

    main_font_size = int(72 * w / 400)
    sub_font_size = int(18 * w / 400)

    main_font = get_font(main_font_size)
    sub_font = get_font(sub_font_size)

    # NRW in white
    draw_text_centered(draw, "NRW", int(h * 0.35), main_font, WHITE + (255,), w)
    # Subtitle in teal
    draw_text_centered(draw, "NEW RELEASE WALL", int(h * 0.60), sub_font, TEAL + (255,), w)

    front.save(f"{output_dir}/AppIcon-Front-{scale}.png")
    print(f"  Created AppIcon-Front-{scale}.png ({w}x{h})")

    # MIDDLE LAYER - empty/transparent
    middle = Image.new('RGBA', size, (0, 0, 0, 0))
    middle.save(f"{output_dir}/AppIcon-Middle-{scale}.png")
    print(f"  Created AppIcon-Middle-{scale}.png ({w}x{h})")

# Combined version for "All" slot
for scale, size in icon_sizes.items():
    w, h = size
    combined = create_gradient(size, DARK_BG, DARK_BLUE, 'diagonal')
    draw = ImageDraw.Draw(combined)

    main_font_size = int(72 * w / 400)
    sub_font_size = int(18 * w / 400)
    main_font = get_font(main_font_size)
    sub_font = get_font(sub_font_size)

    draw_text_centered(draw, "NRW", int(h * 0.35), main_font, WHITE, w)
    draw_text_centered(draw, "NEW RELEASE WALL", int(h * 0.60), sub_font, TEAL, w)

    combined.save(f"{output_dir}/AppIcon-All-{scale}.png")
    print(f"  Created AppIcon-All-{scale}.png ({w}x{h})")


# ============================================
# TOP SHELF IMAGE WIDE
# ============================================

shelf_sizes = {
    '1x': (1920, 720),
    '2x': (3840, 1440),
}

for scale, size in shelf_sizes.items():
    w, h = size

    # Dark gradient background
    img = create_gradient(size, DARK_BG, DARK_BLUE, 'vertical')
    draw = ImageDraw.Draw(img)

    # Add subtle teal glow at bottom center
    for y in range(h // 2, h):
        for x in range(w // 4, 3 * w // 4):
            # Distance from bottom center
            cx, cy = w // 2, h
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            max_dist = ((w // 4) ** 2 + (h // 2) ** 2) ** 0.5

            if dist < max_dist:
                intensity = (1 - dist / max_dist) * 0.15
                orig = img.getpixel((x, y))
                new_r = int(min(255, orig[0] + TEAL[0] * intensity))
                new_g = int(min(255, orig[1] + TEAL[1] * intensity))
                new_b = int(min(255, orig[2] + TEAL[2] * intensity))
                img.putpixel((x, y), (new_r, new_g, new_b))

    draw = ImageDraw.Draw(img)

    title_size = int(140 * w / 1920)
    subtitle_size = int(42 * w / 1920)

    title_font = get_font(title_size)
    subtitle_font = get_font(subtitle_size)

    # Main title in white
    draw_text_centered(draw, "NEW RELEASE WALL", int(h * 0.40), title_font, WHITE, w)
    # Subtitle in teal
    draw_text_centered(draw, "Track movies from theater to streaming", int(h * 0.58), subtitle_font, TEAL, w)

    img.save(f"{output_dir}/TopShelf-Wide-{scale}.png")
    print(f"  Created TopShelf-Wide-{scale}.png ({w}x{h})")


# ============================================
# TOP SHELF IMAGE (regular)
# ============================================

for scale, size in shelf_sizes.items():
    w, h = size
    img = create_gradient(size, DARK_BG, DARK_BLUE, 'vertical')
    draw = ImageDraw.Draw(img)

    title_size = int(120 * w / 1920)
    title_font = get_font(title_size)

    draw_text_centered(draw, "NEW RELEASE WALL", int(h * 0.45), title_font, WHITE, w)

    img.save(f"{output_dir}/TopShelf-{scale}.png")
    print(f"  Created TopShelf-{scale}.png ({w}x{h})")

print(f"\n✓ All assets saved to: {output_dir}")
print("\nNext: Drag these PNG files into Xcode's Asset Catalog slots")
