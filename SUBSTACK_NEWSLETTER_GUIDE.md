# Substack Newsletter Generator Guide

Generate beautiful, ready-to-publish newsletters for Substack using your movie data.

## Quick Start

```bash
# Generate this week's newsletter
python3 substack_newsletter_generator.py weekly --output this_week.html

# Open in browser to preview
open this_week.html

# Copy/paste HTML into Substack editor
```

---

## Features

Your newsletter automatically includes:

### 🏆 **Top Picks Section**
- Top 5 highest-rated movies this week
- Full synopsis, RT scores, trailer & review links
- Beautiful numbered badges

### 💎 **Hidden Gems**
- Well-reviewed but under-the-radar releases (80-89% RT)
- Great for discovery

### 📁 **By Genre Sections**
- Movies organized by genre (Drama, Thriller, Comedy, Horror, etc.)
- Top 5 per genre shown
- Compact cards with ratings

### 📋 **Complete Alphabetical List**
- All movies listed for reference
- Two-column layout
- RT scores included

---

## Newsletter Styles

### **Weekly Newsletter**
- Covers last 7 days of releases
- Perfect for regular subscribers
- ~60 movies per week typically

```bash
python3 substack_newsletter_generator.py weekly --output weekly.html
```

### **Monthly Newsletter** *(Coming Soon)*
- Full month roundup
- Best of the month highlights
- More comprehensive coverage

---

## How to Publish on Substack

### Method 1: Copy/Paste HTML (Easiest)

1. **Generate newsletter:**
   ```bash
   python3 substack_newsletter_generator.py weekly --output newsletter.html
   ```

2. **Open in browser:**
   ```bash
   open newsletter.html
   ```

3. **Copy all content** (Cmd+A, Cmd+C)

4. **Go to Substack:**
   - Click "New post"
   - Click "..." menu → "HTML"
   - Paste your HTML
   - Add subject line
   - Click "Publish"

### Method 2: Email HTML Directly

1. **Generate newsletter HTML**

2. **In Substack editor:**
   - Switch to HTML mode
   - Paste the HTML from `newsletter.html`
   - Preview to check formatting
   - Publish!

---

## Customization

### Change Color Scheme

Edit `substack_newsletter_generator.py`:

```python
# Line ~142: Header color
"border-top: 3px solid #ff6b6b;"  # Change #ff6b6b to your brand color

# Line ~168: Top Picks section
"color: #ff6b6b;"  # Change accent color

# Line ~331: Watch Trailer button
"background: #ff6b6b;"  # Button color
```

### Adjust Top Picks Count

```python
# Line ~56
top_picks = self._get_top_picks(movies, count=5)  # Change 5 to desired number
```

### Modify Hidden Gems Criteria

```python
# Line ~97-98
if 80 <= rt_int < 90:  # Change range (e.g., 75-85)
```

---

## Newsletter Sections Explained

### **Header**
- Big, bold title "New Release Wall"
- Date range (e.g., "October 14 - October 17, 2025")
- Clean, professional typography

### **Top Picks** (Featured cards)
- Numbered 1-5
- Full synopsis
- Large, colorful RT badges:
  - 🍅 Green (90%+)
  - 🍅 Orange (60-89%)
  - 🍅 Red (below 60%)
- Trailer and review buttons

### **Hidden Gems** (Yellow highlight box)
- Movies rated 80-89%
- Compact format
- Great for discovery
- "Well-reviewed but under-the-radar" subtitle

### **By Genre** (Organized sections)
- Drama, Thriller, Comedy, Horror, etc.
- Top 5 movies per genre
- Shows total count if more available
- Compact cards with key info

### **Complete List** (Reference)
- All movies alphabetically
- Two-column layout
- RT scores inline
- Quick scan format

### **Footer**
- Generation date
- Link back to newreleasewall.com
- Professional sign-off

---

## Sample Newsletter Preview

```
🎬 New Release Wall
October 14 - October 17, 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This Week's New Releases
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

61 movies hit digital platforms this week. Here are our top picks,
hidden gems, and the full lineup organized by genre.

🏆 TOP PICKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

① 🍅 100% Nanticoke
Directed by John Smith
[Full synopsis...]
▶️ Watch Trailer  🍅 Read Reviews

② 🍅 100% Madharaasi
Directed by A. R. Murugadoss • 168 min • Action, Romance, Thriller
[Full synopsis...]
▶️ Watch Trailer  🍅 Read Reviews

... (3 more top picks)

💎 HIDDEN GEMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Well-reviewed but under-the-radar releases worth your time

🍅 88% The Long Walk
Dir. Francis Lawrence • 101 min • Horror, Thriller
[Synopsis...]
▶️ Trailer  🍅 Reviews

... (2 more gems)

📁 BY GENRE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DRAMA
  🍅 100% Nanticoke
  🍅 97% The Lost Princess
  ... (3 more drama)
  ...plus 16 more drama releases

THRILLER
  🍅 88% The Long Walk
  🍅 79% Night of the Reaper
  ... (3 more thriller)

... (2 more genres)

📋 COMPLETE ALPHABETICAL LIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A Woman with No Filter          Haunted Harmony Mysteries
Everybody Loves Me When I'm Dead Inside Furioza
...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generated October 18, 2025 from New Release Wall
All movies released digitally this week • RT scores where available
```

---

## Technical Details

### File Structure
- **Input:** `data.json` (your movie database)
- **Output:** HTML file (ready for Substack)
- **Styling:** Inline CSS (email-safe)

### HTML Compatibility
- ✅ Substack editor
- ✅ Gmail/email clients
- ✅ Mobile responsive (max-width: 600px)
- ✅ Inline styles (no external CSS)

### Data Requirements
Newsletter pulls from your `data.json`:
- Movie titles, directors, synopses
- RT scores (for badges and sorting)
- Genres (for organization)
- Runtime, release dates
- Trailer and review links

### Performance
- Generates in ~1 second
- File size: ~50-100KB typical
- Works with 60+ movies per week

---

## Automation Ideas

### Weekly Automation
```yaml
# .github/workflows/newsletter.yml
name: Generate Weekly Newsletter

on:
  schedule:
    - cron: '0 14 * * 1'  # Monday 7 AM PDT

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Generate newsletter
        run: python3 substack_newsletter_generator.py weekly --output newsletter.html
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: newsletter
          path: newsletter.html
```

Then download and publish manually.

### Email Alert
Add to your automation:
```bash
# Send yourself the newsletter
mail -s "NRW Newsletter Ready" you@email.com < newsletter.html
```

---

## FAQ

**Q: Can I edit the newsletter after generating?**
A: Yes! The HTML is standard and editable in any text editor or Substack's editor.

**Q: What if a movie doesn't have an RT score?**
A: It still appears in genre sections and complete list, just without the colored badge.

**Q: Can I use this for other platforms (Medium, WordPress, etc.)?**
A: Yes! The HTML works anywhere that accepts HTML/rich text.

**Q: How do I change the title from "New Release Wall"?**
A: Edit line ~144 in `substack_newsletter_generator.py`:
```python
<h1 ...>🎬 Your Custom Title</h1>
```

**Q: Can I add my own sections?**
A: Yes! Add methods to the class and call them in `generate_weekly_newsletter()`.

**Q: Does this cost anything?**
A: No! It's completely free and uses your existing `data.json`.

---

## Examples

### Add "New This Week" Stats Box

```python
def _generate_stats_box(self, movies):
    total = len(movies)
    with_rt = len([m for m in movies if m.get('rt_score')])
    avg_rt = sum([self._safe_int_score(m.get('rt_score'))
                  for m in movies if m.get('rt_score')]) / with_rt if with_rt else 0

    return f"""
    <div style="background: #e8f5e9; padding: 20px; margin: 20px 0; border-radius: 8px;">
        <strong>This Week's Stats:</strong><br>
        📊 {total} total releases<br>
        🍅 {with_rt} with RT scores<br>
        📈 {avg_rt:.0f}% average rating
    </div>
"""
```

### Add Genre Icons

```python
GENRE_ICONS = {
    'Horror': '👻',
    'Comedy': '😂',
    'Drama': '🎭',
    'Thriller': '🔪',
    'Romance': '❤️',
    # ...
}
```

---

## Support

Questions? Check the script:
```bash
python3 substack_newsletter_generator.py --help
```

Or review the code - it's well-commented and easy to modify!

---

**Happy newsletter creating!** 📧✨
