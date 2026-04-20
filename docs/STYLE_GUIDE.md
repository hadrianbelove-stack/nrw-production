# NRW Style Guide

This is the authoritative style guide for all NRW visual design. All UI work (newsletters, mockups, apps, web pages) MUST follow these specifications.

**Last Updated:** 2026-02-24

---

## Color Palette

### Core Colors
| Name | Hex | Usage |
|------|-----|-------|
| **Background Dark** | `#0a0a0a` | Gradient start |
| **Background Mid** | `#1a1a2e` | Gradient end, card backgrounds |
| **Primary Accent** | `#00d4aa` | Links, highlights, borders, interactive elements |
| **Primary Accent Hover** | `#00ffbb` | Hover states |
| **Text Primary** | `#ffffff` | Headings, important text |
| **Text Secondary** | `#bbb` | Body text, descriptions |
| **Text Muted** | `#888` | Metadata, timestamps |
| **Border Subtle** | `rgba(255,255,255,0.2)` | Card borders, dividers |

### Category Colors
| Category | Hex | Usage |
|----------|-----|-------|
| **Staff Picks** | `#dc143c` | Crimson - badges, borders, accents |
| **Big Time Stuff** | `#ffffff` | White - default styling |
| **Indie** | `#00d4aa` | Teal - matches primary accent |
| **Documentary** | `#4A90D9` | Blue - informational, non-fiction |
| **Virtual Screenings** | `#FFD700` | Gold - festival/screening accent |
| **The Slop Pile** | `#888888` | Gray - muted, de-emphasized |
| **Restorations** | `#C8A951` | Antique gold - badge pill on poster |

### Service Colors
| Service | Hex |
|---------|-----|
| Netflix | `#E50914` |
| Disney+ | `#113CCF` |
| Max | `#B537F2` |
| Prime Video | `#00A8E1` |
| Hulu | `#1CE783` |
| Peacock | `#000000` |
| Purchase/Rent | `#ff9500` |
| Plex | `#E5A00D` |
| Fawesome | `#5B8DEF` |
| Apple TV | `#aaaaaa` |

### Gray Guidelines
When using grays for secondary UI elements:
- **Prefer lighter grays** - dark grays disappear into dark backgrounds
- Outline buttons: use `#888` to `#aaa` for borders, not `#555` or darker
- Muted text: `#888` minimum, `#666` is too dark
- Apple TV / generic service buttons: `#aaaaaa` (not dark gray)

### Country Display Names
Use shortened forms only for long country names. Keep short names as-is:

| Data Value                  | Displays As |
|-----------------------------|-------------|
| United States of America    | USA         |
| United Kingdom              | UK          |
| South Korea                 | S. Korea    |
| South Africa                | S. Africa   |
| New Zealand                 | N. Zealand  |
| Bosnia and Herzegovina      | Bosnia      |
| Saudi Arabia                | S. Arabia   |

All other countries display as their full name (France, Japan, Canada, etc.)
Case mismatches (e.g. "usa", "SWEDEN") are handled automatically.
For multiple countries, use slashes: `USA / France / Japan`

---

## Typography

### Font Stack
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```
Use system fonts. No custom web fonts.

### Weights & Styles
| Element | Weight | Letter-Spacing | Size |
|---------|--------|----------------|------|
| Main Header (THE NEW RELEASE WALL) | 100 (ultra-light) | 0.3em | 2.5rem |
| Section Headers | 700 (bold) | 0.1-0.15em | 1.1rem |
| Movie Titles | 600-700 | normal | 1-1.25rem |
| Body Text | 400 | normal | 0.9-1rem |
| Metadata/Labels | 400-500 | 0.05em | 0.8-0.9rem |
| Buttons | 700 | 0.1em | 0.75-0.85rem |

### Line Heights
- Body text: `1.6` to `1.7`
- Headings: `1.2` to `1.3`
- Tight (buttons, badges): `1`

---

## Spacing & Layout

### Border Radius
| Element | Radius |
|---------|--------|
| Cards | `15px` |
| Buttons/Pills | `25px` (fully rounded) |
| Small buttons | `6-8px` |
| Badges | `10-12px` |

### Shadows
```css
/* Card shadow */
box-shadow: 0 8px 32px rgba(0,0,0,0.3);

/* Hover glow (accent) */
box-shadow: 0 5px 20px rgba(0,212,170,0.4);

/* Hover glow (crimson for Staff Picks) */
box-shadow: 0 0 20px rgba(220,20,60,0.3);
```

### Standard Spacing
- Card gap: `1-2rem`
- Section padding: `1.5rem` to `2rem`
- Element margins: `0.5rem` to `1rem`

---

## UI Components

### Buttons
```css
/* Primary action button */
background: #00d4aa;
color: #000;
padding: 0.5rem 1rem;
border-radius: 8px;
font-weight: bold;
text-transform: uppercase;

/* Hover */
background: #00ffbb;
transform: translateY(-2px);
box-shadow: 0 5px 20px rgba(0,212,170,0.5);
```

### Filter Pills
```css
background: rgba(255,255,255,0.1);
border: 1px solid rgba(255,255,255,0.2);
border-radius: 25px;
padding: 0.5rem 1rem;

/* Active/Hover */
background: #00d4aa;
border-color: #00d4aa;
```

### Cards
- Dark gradient background
- 15px border radius
- Subtle border `rgba(255,255,255,0.2)`
- Shadow on hover
- Scale up slightly on hover (`transform: scale(1.05)`)

### Navigation Arrows (Movie Detail)
For navigating between movies on detail screens across all platforms:

| Property | Value | Notes |
|----------|-------|-------|
| Character | `‹` / `›` | Unicode chevrons (U+2039, U+203A) |
| Color | `#00d4aa` | Primary accent (teal) |
| Base Opacity | 60% | Visible but not distracting |
| Flash Opacity | 100% | Visual feedback when navigating |
| Position | Vertically centered on left/right edges | |

**Platform-specific sizes:**
| Platform | Size | Notes |
|----------|------|-------|
| tvOS | 80px | 10-foot viewing distance |
| Android TV | 56sp | Material Design scaling |
| Roku | Large system font | ~100px at 1080p |
| iOS Mobile | 40px | Touch device, swipe primary |
| Desktop Web | 1.5rem | Button with background |

**Platform-specific values:**
```css
/* Web (CSS) */
color: #00d4aa;
background: rgba(0, 212, 170, 0.1);

/* React Native (tvOS/iOS) */
color: 'rgba(0, 212, 170, 0.6)'

/* Android (Kotlin/Compose) */
color = Primary.copy(alpha = 0.6f)

/* Roku (BrightScript - RRGGBBAA format) */
color="0x00D4AA99"
```

---

## Dark vs Light Theme

### Main Site / Apps
Always use **dark theme** as specified above.

### Newsletter (Email/Substack)
Use **light theme** for better email compatibility:
- Background: `#fafafa` or `#ffffff`
- Text: `#222222`
- Accent: `#00d4aa` (keep the teal)
- Category colors: Same as above but ensure contrast

---

## Do's and Don'ts

### DO
- Use the exact hex codes specified
- Maintain consistent spacing
- Use system fonts only
- Keep the dark, premium aesthetic
- Use teal `#00d4aa` as the primary accent everywhere

### DON'T
- Add new colors without approval
- Use serif fonts (except for special editorial contexts)
- Use pure black `#000` for backgrounds (use `#0a0a0a`)
- Use pure white `#fff` for large background areas (use gradients)
- Add decorative elements, borders, or effects not in this guide

---

## Examples

### Newsletter Section Header
```html
<div style="color: #dc143c; font-weight: 700; letter-spacing: 3px;
            text-transform: uppercase; border-bottom: 2px solid #dc143c;
            padding-bottom: 8px; margin: 40px 0 20px 0;">
    STAFF PICKS
</div>
```

### Movie Card Meta Line
```html
<div style="font-size: 0.85em; color: #888; margin-bottom: 12px;">
    <strong style="color: #00d4aa;">Director:</strong> Adam Meeks ·
    <strong style="color: #00d4aa;">Country:</strong> USA · 97 min
</div>
```

---

## Changelog

### 2026-04-17 - Added Fawesome Service Color
- Added Fawesome (`#5B8DEF`) to Service Colors table

### 2026-02-24 - Navigation Arrows Standard
- Added Navigation Arrows section for movie detail screens
- Standardized teal color (#00d4aa) at 60% opacity across all platforms
- Documented platform-specific sizes and code values

### 2026-02-03 - Initial Version
- Extracted from main site styles.css
- Established core colors, typography, spacing
- Defined category colors for newsletter sections
