# Admin Workflow Guide

## Overview

NRW uses a **"publish first, curate later"** model where movies automatically appear on the public site when discovered by automation. The admin panel is used to refine the display after publication, not to pre-approve content. This approach ensures rapid discovery of new releases while allowing manual curation to maintain quality.

**Core Philosophy**: Movies are **visible by default** → Admin curates post-publication

## Core Workflow Diagram

```
GitHub Actions (Daily Automation)
    ↓ Discovers new movies via TMDB API
movie_tracking.json (All Movies Database)
    ↓ Processed by generate_data.py
data.json (Public Display Data)
    ↓ Movies automatically visible
Public Site (http://localhost:8001)
    ↓ Admin reviews new content
Admin Panel (http://localhost:5555)
    ↓ Hide/Feature/Edit actions
Regenerate data.json
    ↓ Apply curation changes
Updated Public Site
```

**Workflow Steps:**
1. **Discovery**: GitHub Actions automation discovers new movies
2. **Auto-Publication**: Movies added to `movie_tracking.json` and appear on public site
3. **Curation**: Admin uses panel to hide unwanted movies and feature important releases
4. **Regeneration**: Changes applied to `data.json` to update public display

## Admin Panel Features

### Hide Button (🚫 Hide)
Removes movie from public display by adding ID to `admin/hidden_movies.json`.

**Use for:**
- Low-quality direct-to-video releases
- Duplicate entries
- Movies that don't fit site focus
- Adult content or inappropriate material

### Feature Button (⭐ Feature)
Highlights movie on public site by adding ID to `admin/featured_movies.json`.

**Use for:**
- High-profile theatrical releases
- Awards contenders and festival winners
- Popular titles trending on social media
- Editorial picks and recommendations

### Edit Fields
Inline editing of all movie metadata with manual correction tracking.

**Editable Fields:**
- Rotten Tomatoes score and URL
- Trailer URL (YouTube)
- Director and cast information
- Synopsis and plot summary
- Streaming availability (watch links)
- Release dates and ratings

**Save Process:**
- Edit fields directly in the admin interface
- Click "💾 Save All Changes" button
- Changes tracked with admin override flags
- Regenerate `data.json` to apply updates

## Daily Curation Routine

### Step-by-Step Workflow

1. **Morning Sync**
   ```bash
   ./sync_daily_updates.sh
   ```
   Merge automation updates from overnight discovery

2. **Launch Admin Panel**
   ```bash
   python3 admin.py
   ```
   Opens admin interface at `http://localhost:5555`

3. **Review New Movies**
   - Filter by recent dates or use search
   - Check public site to see new additions
   - Identify candidates for hiding or featuring

4. **Hide Unwanted Movies**
   - Click "🚫 Hide" for low-quality releases
   - Use for wrong genre, duplicates, or poor quality
   - Hidden movies removed from public display

5. **Feature Important Releases**
   - Click "⭐ Feature" for high-profile titles
   - Highlights movie on public site
   - Use for awards contenders, popular releases

6. **Fix Missing Data**
   - Click "⚠️ Missing Data" filter
   - Edit incomplete movie information
   - Add missing RT scores, trailers, or descriptions

7. **Apply Changes**
   - Click "🔄 Regenerate data.json"
   - Updates public display with curation changes
   - Verify changes on public site

## Filter Reference

The admin panel provides several filter buttons for efficient curation:

- **All Movies**: Show everything in tracking database
- **⚠️ Missing Data**: Show incomplete movies needing attention
- **Visible**: Show movies currently on public site
- **Hidden**: Show movies removed from public display
- **Featured**: Show highlighted movies
- **📝 Reviewed**: Show movies with custom reviews for newsletter

## Technical Details

### File Structure
- **`movie_tracking.json`**: Master database containing all discovered movies
- **`admin/hidden_movies.json`**: List of movie IDs excluded from public display
- **`admin/featured_movies.json`**: List of movie IDs highlighted on site
- **`data.json`**: Public display data (filtered by admin overrides)

### Processing Mechanism
The `apply_admin_overrides()` method in `generate_data.py` (lines 2197-2228) handles curation:
- Filters out movies listed in `admin/hidden_movies.json`
- Marks movies in `admin/featured_movies.json` as featured
- Applies manual data corrections and overrides
- Generates clean `data.json` for public consumption

### Default Visibility
Movies are **visible by default** unless explicitly hidden. The automation adds all discovered movies to `movie_tracking.json`, and they appear on the public site through the standard generation process. Only movies added to the hidden list are filtered out.

## FAQ

**Q: Do I need to approve movies before they appear on the site?**
A: No, movies are automatically visible when discovered by automation. Use the admin panel to remove unwanted movies after they appear.

**Q: How do I remove a movie from the public site?**
A: Use the "🚫 Hide" button in the admin panel, then click "🔄 Regenerate data.json" to apply the change.

**Q: What happens if I don't curate regularly?**
A: All discovered movies will appear on the public site, which may include low-quality releases or inappropriate content.

**Q: Can I undo hiding a movie?**
A: Yes, filter by "Hidden" to find the movie, then click "👁️ Show" to make it visible again.

**Q: Do I need to regenerate after every change?**
A: Yes, changes to hidden/featured status or metadata require regeneration to update `data.json`.

**Q: How do I find movies that need attention?**
A: Use the "⚠️ Missing Data" filter to identify incomplete movies requiring manual correction.

## Best Practices

### Quality Curation
- Review new movies daily to maintain site quality
- Hide low-budget direct-to-video releases unless notable
- Feature awards contenders, festival winners, and trending titles
- Prioritize theatrical releases over streaming-only content

### Data Management
- Use "⚠️ Missing Data" filter to find incomplete movies
- Fix missing RT scores, trailers, and descriptions
- Correct bootstrap dates (movies with "~" indicator) for high-profile titles
- Add custom reviews for 3-5 movies per week to enhance newsletter content

### Workflow Efficiency
- Batch similar actions (hide multiple low-quality movies together)
- Use filters to focus on specific types of content
- Check both admin panel and public site to verify changes
- Maintain consistent curation standards across all content

### Communication
- Document rationale for featuring specific movies
- Note patterns in hidden content to improve automation
- Coordinate with team on editorial choices and site focus
- Track curation metrics to measure quality improvement

Remember: The goal is **quality over quantity**. It's better to hide questionable content and feature fewer high-quality movies than to let everything through uncurated.