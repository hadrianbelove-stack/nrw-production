# Newsletter Generator Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-051
**Date:** 2025-10-22
**Maintainer:** Development Team

## Overview

The Newsletter Generator is a multi-format content creation tool that produces weekly distribution updates for NRW subscribers. It supports multiple output formats for different distribution channels (Substack, email, social media) and integrates with the review system to provide editorial value beyond automated aggregation.

## Context

With the review system in place (AMENDMENT-050), the project needed a newsletter generator to distribute weekly updates to subscribers. The generator must support multiple output formats for different distribution channels while featuring editorial content prominently.

## Implementation

### Script: `generate_newsletter.py`
- Standalone Python script (no external dependencies)
- Reads `data.json` and `admin/movie_reviews.json`
- Filters movies by configurable date range (default 7 days)
- Groups movies by streaming platform (not genre)
- Features reviewed movies prominently

### Output Formats

**Three formats support different distribution channels:**

1. **Markdown** (`newsletter_YYYY-MM-DD.md`): Substack/blog-ready format
2. **HTML** (`newsletter_YYYY-MM-DD.html`): Email-friendly with inline styles
3. **Plain Text** (`newsletter_YYYY-MM-DD.txt`): Simple list for quick sharing

### CLI Interface

```bash
python3 generate_newsletter.py [--days N] [--format FORMAT] [--output-dir DIR]
```

**Parameters:**
- `--days`: Number of days to look back (default 7)
- `--format`: Output format (markdown, html, text, all)
- `--output-dir`: Output directory (default current directory)

## Newsletter Structure

### Section Layout

1. **Hero Review**: Featured movie with full review (first movie with `featured_in_newsletter: true`)
2. **This Week's Highlights**: 3-5 reviewed movies with excerpts
3. **By Platform**: Movies grouped by streaming service (Netflix, Amazon, Apple TV+, Disney+, Hulu, Max, etc.)
4. **Quick List**: Alphabetical reference of all movies with RT scores

### Platform Grouping Logic
- Extracts platforms from movie `providers` object (streaming, rent, buy)
- Normalizes platform names ("Amazon Video" → "Amazon Prime Video")
- Sorts platforms by movie count (most popular first)
- Limits to top 10 movies per platform for readability

### Review Integration
- Loads reviews from `admin/movie_reviews.json`
- Matches reviews to movies by ID
- Prioritizes movies with `featured_in_newsletter: true` for Hero Review
- Includes review text, author, rating in all formats
- Gracefully handles missing reviews (newsletter works without them)

## Error Handling

### Robust Fallbacks
- **Fatal error** if `data.json` missing (can't generate without data)
- **Warning** if `admin/movie_reviews.json` missing (continues without reviews)
- **Skip** movies with malformed dates (logs warning)
- **Use defaults** for missing fields ("Unknown Director", "No synopsis")
- **Helpful message** if no movies in date range

## Design Decisions

### New Script vs. Modifying Existing
Created new `generate_newsletter.py` instead of modifying `substack_newsletter_generator.py` because requirements differ significantly:
- Platform grouping vs. genre organization
- Review integration vs. pure automation
- Multiple formats vs. single output
- Configurable date ranges vs. fixed weekly

### Platform Grouping vs. Genre
- Aligns with user's "where to watch" focus
- Serves streaming-first audience
- More actionable than genre categories
- Matches watch links system structure

### Three Output Formats
- **Markdown**: Substack, blog platforms, GitHub
- **HTML**: Email clients, newsletters, websites
- **Text**: Social media, quick sharing, messaging

### Hero Review Section
- Showcases editorial content prominently
- Incentivizes review writing by curators
- Provides personality beyond automated aggregation
- Distinguishes newsletter from generic movie lists

### No External Dependencies
- Uses only Python standard library
- Easy deployment across environments
- Reduces maintenance burden
- Faster execution (no library imports)

## Workflow Integration

### Content Creation Process
1. **Curator writes reviews** in admin panel (`./launch_all.sh`)
2. **Mark top pick** as "featured in newsletter"
3. **Generate newsletter** with `python3 generate_newsletter.py`
4. **Copy content** to distribution channels:
   - Markdown → Substack editor
   - HTML → Email client
   - Text → Social media platforms
5. **Distribute** to subscribers

### Automation Potential
While currently manual, the workflow could be automated:
- Trigger generation after weekly data updates
- Auto-post to Substack via API
- Send email via mailing service
- Schedule social media posts

## Configuration

### Date Range Flexibility
- **Weekly newsletters**: `--days 7` (default)
- **Monthly roundups**: `--days 30`
- **Custom periods**: `--days N` for any range
- **Specific dates**: Can be extended to support date ranges

### Format Selection
- **Single format**: `--format markdown`
- **All formats**: `--format all` (default)
- **Multiple formats**: Run script multiple times
- **Custom formats**: Easy to add new output types

## Files Created
- `generate_newsletter.py` - Newsletter generator script (~600-800 lines)

## Files Modified
- `README.md` - Added newsletter generation documentation
- `IMPLEMENTATION_ROADMAP.md` - Updated HIGH-002 status to resolved

## Performance

### Script Execution
- **Runtime**: ~1-2 seconds for typical weekly data
- **Memory**: Minimal (loads data.json into memory)
- **Dependencies**: Python standard library only
- **Output size**: ~10-50KB per format

### Content Processing
- **Movie filtering**: Date-based, efficient
- **Platform grouping**: O(n) complexity
- **Review matching**: Dictionary lookup, fast
- **Format generation**: Template-based, scalable

## Quality Assurance

### Content Validation
- Checks for required data availability
- Handles missing reviews gracefully
- Validates date formats and ranges
- Provides helpful error messages

### Output Formatting
- Consistent styling across formats
- Proper escaping for HTML output
- Clean text formatting for readability
- Valid markdown for blog platforms

## Future Enhancements

### Potential Features
- **Email integration**: Direct sending via SMTP
- **Substack API**: Automated posting to blog
- **Template customization**: User-configurable layouts
- **Image integration**: Movie posters in HTML format
- **Social media formatting**: Platform-specific optimizations

### Analytics Integration
- **Open rates**: Email newsletter metrics
- **Click tracking**: Watch link engagement
- **Reader feedback**: Review system integration
- **Content optimization**: Data-driven improvements

## Rationale

### Multi-Format Strategy
- **Flexibility**: Supports different distribution channels without requiring multiple tools
- **Efficiency**: Single script generates all needed formats
- **Consistency**: Same content across all channels
- **Maintenance**: One codebase to update and improve

### Platform-Centric Organization
- **User-focused**: Helps users find movies on their preferred services
- **Actionable**: Direct connection to where movies can be watched
- **Practical**: Aligns with user viewing habits
- **Scalable**: Easy to add new streaming platforms

### Editorial Integration
- **Value proposition**: Provides editorial perspective beyond data aggregation
- **Differentiation**: Distinguishes from automated movie feeds
- **Engagement**: Personal reviews increase reader connection
- **Quality**: Human curation improves content relevance

## Related Features
- **Review System** (AMENDMENT-050): Provides editorial content for newsletters
- **Admin Panel** (AMENDMENT-045): Interface for writing and managing reviews
- **Watch Links System** (AMENDMENT-038): Platform data used for grouping

## Status
✅ Implemented and documented
✅ Completes HIGH-002 (Newsletter Export) in IMPLEMENTATION_ROADMAP.md
✅ Ready for production use