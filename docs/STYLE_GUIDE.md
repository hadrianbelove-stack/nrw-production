# NRW Style Guide

This is the authoritative style guide for all NRW visual design. All UI work (newsletters, mockups, apps, web pages) MUST follow these specifications.

**Last Updated:** 2026-02-03

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
| **Niche Notables** | `#00d4aa` | Teal - matches primary accent |
| **The Slop Pile** | `#888888` | Gray - muted, de-emphasized |

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

### 2026-02-03 - Initial Version
- Extracted from main site styles.css
- Established core colors, typography, spacing
- Defined category colors for newsletter sections
