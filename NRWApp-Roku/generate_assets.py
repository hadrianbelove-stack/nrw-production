#!/usr/bin/env python3
"""
NRW Roku App Asset Generator
Generates all required PNG icons and splash screens for Option 1 (Text Logo)
"""

from PIL import Image, ImageDraw, ImageFont
import os

# NRW Brand Colors
BACKGROUND = (10, 10, 10)  # #0a0a0a
PRIMARY = (0, 212, 170)     # #00d4aa (teal)
WHITE = (255, 255, 255)

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'images', 'logo')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_font(size, bold=False):
    """Get system font at specified size"""
    # Try common system fonts
    font_options = [
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/SFNSDisplay.ttf',
        '/System/Library/Fonts/SF-Pro-Display-Regular.otf',
        '/Library/Fonts/Arial.ttf',
    ]

    if bold:
        font_options = [
            '/System/Library/Fonts/Helvetica.ttc',
            '/System/Library/Fonts/SFNSDisplay.ttf',
            '/System/Library/Fonts/SF-Pro-Display-Bold.otf',
            '/Library/Fonts/Arial Bold.ttf',
        ]

    for font_path in font_options:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                pass

    # Fallback to default
    return ImageFont.load_default()


def draw_text_centered(draw, text, y, font, color, width):
    """Draw text centered horizontally"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (width - text_width) // 2
    draw.text((x, y), text, font=font, fill=color)
    return bbox[3] - bbox[1]  # Return text height


def create_icon(width, height, filename, is_small=False):
    """Create an icon with NRW branding"""
    img = Image.new('RGBA', (width, height), BACKGROUND)
    draw = ImageDraw.Draw(img)

    # Calculate sizes based on icon dimensions
    if is_small:
        nrw_size = max(24, int(height * 0.28))
        subtitle_size = max(8, int(height * 0.08))
        line_width = int(width * 0.65)
        line_height = 2
        spacing = max(2, int(height * 0.02))
    else:
        nrw_size = max(40, int(height * 0.30))
        subtitle_size = max(12, int(height * 0.065))
        line_width = int(width * 0.62)
        line_height = 3
        spacing = max(4, int(height * 0.02))

    # Get fonts
    nrw_font = get_font(nrw_size, bold=False)
    subtitle_font = get_font(subtitle_size, bold=True)

    # Calculate vertical positioning
    nrw_bbox = draw.textbbox((0, 0), "NRW", font=nrw_font)
    nrw_height = nrw_bbox[3] - nrw_bbox[1]

    subtitle_bbox = draw.textbbox((0, 0), "NEW RELEASE WALL", font=subtitle_font)
    subtitle_height = subtitle_bbox[3] - subtitle_bbox[1]

    total_height = nrw_height + spacing + subtitle_height + spacing + line_height
    start_y = (height - total_height) // 2

    # Draw NRW text (light weight, wide letter spacing simulated)
    nrw_text = "N R W"  # Add spaces for letter-spacing effect
    nrw_bbox = draw.textbbox((0, 0), nrw_text, font=nrw_font)
    nrw_width = nrw_bbox[2] - nrw_bbox[0]
    nrw_x = (width - nrw_width) // 2
    draw.text((nrw_x, start_y), nrw_text, font=nrw_font, fill=WHITE)

    # Draw subtitle
    subtitle_y = start_y + nrw_height + spacing
    subtitle_text = "NEW RELEASE WALL"
    subtitle_bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (width - subtitle_width) // 2
    draw.text((subtitle_x, subtitle_y), subtitle_text, font=subtitle_font, fill=PRIMARY)

    # Draw teal underline
    line_y = subtitle_y + subtitle_height + spacing
    line_x = (width - line_width) // 2
    draw.rectangle([line_x, line_y, line_x + line_width, line_y + line_height], fill=PRIMARY)

    # Save
    output_path = os.path.join(OUTPUT_DIR, filename)
    img.save(output_path, 'PNG')
    print(f"Created: {filename} ({width}x{height})")
    return img


def create_splash(width, height, filename):
    """Create a splash screen"""
    img = Image.new('RGBA', (width, height), BACKGROUND)
    draw = ImageDraw.Draw(img)

    # Larger sizes for splash screen
    nrw_size = int(height * 0.15)
    subtitle_size = int(height * 0.03)
    line_width = int(width * 0.25)
    line_height = 4
    spacing = int(height * 0.015)

    # Get fonts
    nrw_font = get_font(nrw_size, bold=False)
    subtitle_font = get_font(subtitle_size, bold=True)

    # Calculate positioning
    nrw_text = "N R W"
    nrw_bbox = draw.textbbox((0, 0), nrw_text, font=nrw_font)
    nrw_height = nrw_bbox[3] - nrw_bbox[1]
    nrw_width = nrw_bbox[2] - nrw_bbox[0]

    subtitle_text = "NEW RELEASE WALL"
    subtitle_bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
    subtitle_height = subtitle_bbox[3] - subtitle_bbox[1]
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]

    total_height = nrw_height + spacing + subtitle_height + spacing * 2 + line_height
    start_y = (height - total_height) // 2

    # Draw NRW
    nrw_x = (width - nrw_width) // 2
    draw.text((nrw_x, start_y), nrw_text, font=nrw_font, fill=WHITE)

    # Draw subtitle
    subtitle_y = start_y + nrw_height + spacing
    subtitle_x = (width - subtitle_width) // 2
    draw.text((subtitle_x, subtitle_y), subtitle_text, font=subtitle_font, fill=PRIMARY)

    # Draw underline
    line_y = subtitle_y + subtitle_height + spacing * 2
    line_x = (width - line_width) // 2
    draw.rectangle([line_x, line_y, line_x + line_width, line_y + line_height], fill=PRIMARY)

    # Save
    output_path = os.path.join(OUTPUT_DIR, filename)
    img.save(output_path, 'PNG')
    print(f"Created: {filename} ({width}x{height})")
    return img


def create_placeholder():
    """Create a placeholder image for movie posters"""
    img = Image.new('RGBA', (200, 300), (26, 26, 46))  # #1a1a2e
    draw = ImageDraw.Draw(img)

    # Draw film icon placeholder
    font = get_font(14)
    text = "NRW"
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (200 - (bbox[2] - bbox[0])) // 2
    y = (300 - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), text, font=font, fill=(100, 100, 100))

    output_path = os.path.join(os.path.dirname(__file__), 'images', 'icons', 'placeholder.png')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, 'PNG')
    print(f"Created: placeholder.png (200x300)")


def main():
    print("Generating NRW Roku App Assets (Option 1: Text Logo)")
    print("=" * 50)

    # Channel icons
    create_icon(290, 218, 'icon_focus_hd.png')
    create_icon(336, 210, 'icon_focus_fhd.png')
    create_icon(108, 108, 'icon_side_hd.png', is_small=True)
    create_icon(128, 128, 'icon_side_fhd.png', is_small=True)

    # Splash screens
    create_splash(1280, 720, 'splash_hd.png')
    create_splash(1920, 1080, 'splash_fhd.png')

    # Placeholder
    create_placeholder()

    print("=" * 50)
    print("Done! Assets saved to NRWApp-Roku/images/logo/")


if __name__ == '__main__':
    main()
