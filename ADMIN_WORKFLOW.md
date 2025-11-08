# Admin Workflow Guide

## Overview

NRW uses a **mandatory pre-publish approval** model where all discovered changes must be reviewed and approved by an admin before reaching the public site. The admin panel serves as a quality gate ensuring only curated content is published.

### Security Reminder ⚠️

**Never use default admin credentials beyond localhost.** Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables for any non-local usage:

```bash
export ADMIN_USERNAME="your-secure-username"
export ADMIN_PASSWORD="your-secure-password"
```

**Core Philosophy**: Mandatory pre-publish approval → Quality-first curation

**Full Review Mode**: Admin runs `python3 admin.py --full-review` to enable approval gate behavior.

## Core Workflow Diagram

```
GitHub Actions (Daily Automation)
    ↓ Discovers new movies via TMDB API
movie_tracking.json (All Movies Database)
    ↓ APPROVAL GATE: Orchestrator waits for admin approval
Admin Panel (http://localhost:5555 --full-review)
    ↓ Admin reviews changes, curates data
    ↓ Click "Approve & Generate"
admin/approval.json (Approval Artifact - ephemeral)
    ↓ Approval validated by orchestrator
data.json (Public Display Data)
    ↓ Only approved content published
Public Site (http://localhost:8001)
```

## Artifact Versioning Policy

**Admin artifacts are ephemeral and not versioned in git:**
- `admin/approval.json` - Approval state (ephemeral)
- `admin/ordering.json` - Movie ordering preferences (ephemeral)
- `admin/hidden_movies.json` - Hidden movie IDs (ephemeral)
- `admin/featured_movies.json` - Featured movie IDs (ephemeral)
- `admin/watch_link_overrides.json` - Watch link overrides (ephemeral)
- `admin/movie_reviews.json` - Custom movie reviews (ephemeral)
- `diary/*.md` - Daily workflow logs (ephemeral)

**Only `data.json` is versioned** as it represents the final published state.

**For CI automation:** Approvals must be created locally before CI runs. Admin artifacts are cleaned up after successful publication to prevent stale state.

**Workflow Steps:**
1. **Discovery**: Orchestrator runs discovery and monitoring phases
2. **Approval Gate**: System waits for mandatory admin approval
3. **Full Review**: Admin runs `admin.py --full-review` to inspect changes
4. **Curation**: Admin hides/features movies, fixes data, adds manual entries
5. **Approval**: Click "Approve & Generate" creates approval artifact
6. **Publication**: Only after approval does system generate data.json

## Admin Panel Features

**For detailed admin panel implementation:** See [docs/features/ADMIN_PANEL_SPEC.md](docs/features/ADMIN_PANEL_SPEC.md)

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
- In full-review mode, changes are saved but not published until approval

### Approve & Generate Button (✅ Approve & Generate)
**Full Review Mode Only** - Main approval control for mandatory gate.

**Functionality:**
- Creates `admin/approval.json` with timestamp and validation metadata
- Authorizes orchestrator to proceed with data.json generation
- Includes curator delta summary (edits, additions, hidden, featured counts)
- Tracks reviewer identity and approval timestamp

**UI Copy**: "Approves curated changes and authorizes generation"

**When to Use:**
- After completing all curation tasks (hiding/featuring/editing)
- When satisfied with movie data quality
- Ready to publish changes to public site

## Daily Curation Routine

### Step-by-Step Workflow

1. **Orchestrator Notification**
   - Daily orchestrator runs discovery and monitoring
   - System pauses at approval gate, waiting for admin
   - Terminal shows: "⏸️ Waiting for admin approval..."

2. **Launch Full Review Mode**
   ```bash
   python3 admin.py --full-review
   ```
   Opens admin interface at `http://localhost:5555` in approval mode

3. **Review Discovered Changes**
   - Examine newly tracked movies and status changes
   - Check data quality and completeness
   - Identify candidates for hiding, featuring, or editing

4. **Manual Movie Addition** (if needed)
   - Use "Add Movie" form for titles missed by discovery
   - Provide TMDB ID, title, and basic metadata
   - System fetches additional details automatically

5. **Hide Unwanted Movies**
   - Click "🚫 Hide" for low-quality releases
   - Use for wrong genre, duplicates, or poor quality
   - Changes saved but not published until approval

6. **Feature Important Releases**
   - Click "⭐ Feature" for high-profile titles
   - Highlights movie on public site
   - Use for awards contenders, popular releases

7. **Fix Missing Data**
   - Click "⚠️ Missing Data" filter
   - Edit incomplete movie information
   - Add missing RT scores, trailers, or descriptions

8. **Editorial Ordering** (optional)
   - Use drag-and-drop to reorder movies
   - Pin important titles to top of display
   - Creates `admin/ordering.json` with ordered IDs

9. **Final Approval**
   - Click "✅ Approve & Generate" button
   - Creates approval artifact with curator metadata
   - Orchestrator resumes and generates final data.json
   - Public site updated with approved changes

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
- **`admin/ordering.json`**: Editorial ordering (pins specific movies to top)
- **`admin/approval.json`**: Approval artifact with timestamp and validation metadata
- **`metrics/daily.jsonl`**: Curator delta logs for audit trail
- **`data.json`**: Public display data (filtered by admin overrides)

### Processing Mechanism
The `apply_admin_overrides()` method in `generate_data.py` handles curation:
- Filters out movies listed in `admin/hidden_movies.json`
- Marks movies in `admin/featured_movies.json` as featured
- Applies editorial ordering from `admin/ordering.json`
- Applies manual data corrections and overrides
- Generates clean `data.json` for public consumption

### Approval Gate Mechanism
The `daily_orchestrator.py` implements mandatory approval:
- Validates `admin/approval.json` timestamp (within 2 hours)
- **Requires** tracking digest for data consistency (ensures `movie_tracking.json` hasn't changed since approval)
- In CI: exits immediately if approval missing or stale
- Locally: polls every 5 seconds until approval received

#### Approval Failure Modes
- **Missing digest**: Approval will fail if `tracking_digest` field is missing or empty
- **Digest mismatch**: Approval will fail if `movie_tracking.json` has been modified since approval was created
- **Missing tracking file**: Admin approval creation will fail if `movie_tracking.json` is not found or unreadable

### Authentication
The admin panel uses HTTP Basic Authentication with default credentials:
- **Default credentials**: `admin` / `changeme`
- **Override**: Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables

**⚠️ SECURITY WARNING: Change default credentials immediately in any shared or deployed environment; set `ADMIN_USERNAME`/`ADMIN_PASSWORD` via environment variables.**

### Default Approval Requirement
All discovered changes require **mandatory admin approval** before reaching the public site. The automation adds discovered movies to `movie_tracking.json`, but they only appear on the public site after admin approval through the full-review workflow.

## FAQ

**Q: Do I need to approve movies before they appear on the site?**
A: Yes, the mandatory approval gate requires admin review before any changes reach the public site. Use `python3 admin.py --full-review` to enable approval mode.

**Q: What happens if I don't approve changes?**
A: The orchestrator will wait indefinitely (locally) or fail (in CI) until approval is provided. No changes reach the public site without explicit approval.

**Q: How do I remove a movie from the public site?**
A: Use the "🚫 Hide" button in the admin panel, then click "✅ Approve & Generate" to authorize the change.

**Q: Can I undo hiding a movie?**
A: Yes, filter by "Hidden" to find the movie, then click "👁️ Show" and approve the change to make it visible again.

**Q: Do I need to regenerate after every change in full-review mode?**
A: No, in full-review mode changes are saved but not published until you click "✅ Approve & Generate".

**Q: How do I find movies that need attention?**
A: Use the "⚠️ Missing Data" filter to identify incomplete movies requiring manual correction.

**Q: What if I need to add a movie that discovery missed?**
A: Use the "Add Movie" form to manually add titles by TMDB ID. The system will fetch metadata automatically.

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