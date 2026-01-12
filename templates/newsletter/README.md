# Newsletter Templates

Email-safe HTML and Markdown templates for the New Releases Worth Watching Substack newsletter.

## Template Files Overview

### Main Templates

| File | Description |
|------|-------------|
| `newsletter_base.html` | Base HTML template with empty Featured/Rest sections and Movie Bank |
| `newsletter_base.md` | Markdown version for Substack's native editor |
| `newsletter_full.html` | Complete template with Jinja2 loops for automated generation |
| `newsletter_full.md` | Complete Markdown template with Jinja2 loops |

### Component Templates

| File | Description |
|------|-------------|
| `components/movie_card.html` | Reusable movie card for Featured/Rest sections |
| `components/movie_bank_item.html` | Copy-paste ready movie block with visual markers |
| `components/section_header.html` | Section divider component |

## Newsletter Generation Workflow

### Semi-Automated Workflow (Recommended)

1. **Generate the base newsletter** using `newsletter_base.html`
   - Renders all movies in the Movie Bank section
   - Featured and The Rest sections are empty placeholders

2. **Write your essay** in the Essay section
   - Replace the placeholder with your introduction
   - Use `<p style="...">` tags for paragraphs

3. **Curate your selections**
   - Copy movie cards from the Movie Bank
   - Paste 2-3 standout films into Featured Films
   - Paste remaining films into The Rest

4. **Copy to Substack**
   - In Substack, use "Import from HTML" or paste directly
   - Review formatting and make final adjustments

### Fully Automated Workflow

Use `newsletter_full.html` with pre-sorted movie lists:

```python
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('newsletter/newsletter_full.html')

html = template.render(
    newsletter_title="New Releases Worth Watching",
    date_range="January 6-12, 2025",
    featured_movies=[...],  # Pre-selected featured films
    rest_movies=[...],       # Remaining films
    essay_content="<p>Your essay HTML here...</p>"
)
```

## Editing Guidelines

### Copying Movie Blocks

In `newsletter_base.html`, each movie in the Movie Bank is wrapped with comments:

```html
<!-- MOVIE START: Movie Title -->
<table>...</table>
<!-- MOVIE END -->
```

Copy everything from `MOVIE START` to `MOVIE END` (inclusive) when moving movies.

### Styling Movies for Featured Section

When pasting a movie from the Movie Bank into Featured Films, update the border style:

**Before (Movie Bank style):**
```html
border: 2px dashed #666666;
```

**After (Featured style):**
```html
border: 2px solid #00d4aa;
```

### Adding Your Essay

Replace the essay placeholder with formatted paragraphs:

```html
<p style="margin: 0 0 15px 0; color: #ffffff; font-size: 16px; line-height: 1.6;">
    Your first paragraph here...
</p>
<p style="margin: 0 0 15px 0; color: #ffffff; font-size: 16px; line-height: 1.6;">
    Your second paragraph here...
</p>
```

## Styling Customization

### Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Primary Background | `#1a1a2e` | Main content areas |
| Secondary Background | `#16213e` | Section headers |
| Card Background | `#2a2a3e` | Movie Bank cards |
| Accent | `#00d4aa` | Titles, borders, links |
| Text Primary | `#ffffff` | Main text |
| Text Secondary | `#999999` | Metadata, descriptions |
| Border | `#333333` | Subtle dividers |

### Safe CSS Properties

These properties are safe to use inline for email clients:

- `background-color`
- `color`
- `font-size`
- `font-weight`
- `font-family`
- `padding`
- `margin`
- `border`
- `border-radius`
- `text-align`
- `text-decoration`
- `line-height`
- `width` (px or %)
- `max-width`

### Avoid These Properties

Limited or no support in email clients:

- `box-shadow`
- `transform`
- `backdrop-filter`
- CSS gradients
- `flexbox`
- `grid`
- External stylesheets
- Web fonts

### Button Styles

**Streaming service button (teal):**
```html
style="background-color: #00d4aa; color: #000000; padding: 8px 16px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; font-size: 12px;"
```

**VOD service button (orange):**
```html
style="background-color: #ff8c00; color: #000000; padding: 8px 16px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; font-size: 12px;"
```

## Substack-Specific Tips

### Pasting HTML into Substack

1. In Substack's post editor, click the `+` button
2. Select "Import from HTML"
3. Paste your newsletter HTML
4. Review and adjust formatting as needed

### Image Handling

- Substack will rehost images automatically
- Poster URLs should be direct image links
- Recommended poster width: 200px max

### Mobile Preview

Always preview on mobile before publishing:
- Check that movie cards stack properly
- Verify button tap targets are adequate
- Ensure text remains readable

## Troubleshooting Common Issues

### Images Not Displaying

- Verify poster URLs are direct image links (end in .jpg, .png, etc.)
- Check that URLs are accessible (not behind authentication)
- Use HTTPS URLs only

### Layout Breaking in Outlook

- Ensure all tables have `cellpadding="0" cellspacing="0" border="0"`
- Use `role="presentation"` on layout tables
- Avoid CSS shorthand (use `padding-top` instead of `padding: X X X X`)

### Colors Not Appearing

- Use inline styles, not class-based CSS
- Avoid CSS variables
- Test with Litmus or Email on Acid

### Links Not Working

- Ensure all `<a>` tags have `href` attributes
- Use absolute URLs (include https://)
- Don't use JavaScript in links

## Data Binding Reference

### Movie Object Properties

The templates expect movie objects with these properties:

```python
movie = {
    "title": "Movie Title",
    "year": 2025,
    "director": "Director Name",
    "runtime": 120,
    "country": "US",
    "poster": "https://example.com/poster.jpg",
    "synopsis": "Movie description...",
    "rt_score": 85,
    "rt_url": "https://rottentomatoes.com/...",
    "trailer_url": "https://youtube.com/...",
    "wikipedia_url": "https://wikipedia.org/...",
    "streaming_services": [
        {"name": "Netflix", "url": "https://netflix.com/..."}
    ],
    "vod_services": [
        {"name": "Apple TV", "url": "https://apple.com/..."}
    ]
}
```

### Template Variables

| Variable | Type | Description |
|----------|------|-------------|
| `newsletter_title` | string | Newsletter header title |
| `date_range` | string | e.g., "January 6-12, 2025" |
| `movie_count` | int | Total number of films |
| `essay_content` | string (HTML) | Pre-formatted essay HTML |
| `movies` | list | All movies for Movie Bank |
| `featured_movies` | list | Featured films (full template) |
| `rest_movies` | list | Remaining films (full template) |
