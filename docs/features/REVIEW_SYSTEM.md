# Review System Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-050
**Date:** 2025-10-22
**Maintainer:** Development Team

## Overview

The Review System provides editorial content creation capabilities for the NRW newsletter. It allows curators to write custom reviews that highlight notable releases and provide context beyond automated metadata, distinguishing the newsletter from generic movie aggregators.

## Context

Newsletter generation requires editorial content - custom reviews written by the curator to highlight notable releases and provide context beyond metadata. The review system enables this editorial workflow while integrating seamlessly with the existing admin panel and data pipeline.

## Implementation Architecture

### Review Storage
- **File**: `admin/movie_reviews.json`
- **Schema**: `{movie_id: {review, author, rating, featured_in_newsletter, added_date, last_modified}}`
- **Pattern**: Follows admin override pattern (similar to hidden/featured movies)
- **Location**: Admin directory for easy backup and version control

### Data Schema

```json
{
  "1234567": {
    "review": "A haunting meditation on memory and loss...",
    "author": "Hadrian Belove",
    "rating": 4.5,
    "featured_in_newsletter": true,
    "added_date": "2025-10-22T14:30:00Z",
    "last_modified": "2025-10-22T14:30:00Z"
  }
}
```

**Field Definitions:**
- `review` (string): Editorial review text
- `author` (string): Review author name
- `rating` (float): Rating on 0-5 scale
- `featured_in_newsletter` (boolean): Highlight in newsletter generation
- `added_date` (ISO timestamp): When review was created
- `last_modified` (ISO timestamp): When review was last updated

## Admin Panel Integration

### UI Components
The review system is fully integrated into the admin panel interface:

#### Review Section (Per Movie Card)
- **Review text field**: Large textarea for editorial content
- **Author field**: Text input for reviewer name
- **Rating field**: Number input (0-5 scale) with half-point precision
- **Featured checkbox**: Mark as newsletter highlight
- **Action buttons**: Separate "Save Review" and "Delete Review" buttons

#### Header Statistics
- **Review count**: Shows total number of reviewed movies
- **Filter button**: "Show Only Reviewed Movies" for easy navigation
- **Quick stats**: Integration with other admin metrics

### Backend Routes

#### `/update-review` (POST)
- Creates or updates movie reviews
- Validates input data (rating range, required fields)
- Atomic writes with backup management
- Triggers data.json regeneration after changes

#### `/delete-review` (POST)
- Removes reviews completely
- Atomic deletion with backup
- Triggers data regeneration
- Returns updated review count

### Error Handling
- **Input validation**: Rating bounds checking, required field validation
- **Atomic operations**: Backup before write, restore on failure
- **Graceful degradation**: Missing review file handled gracefully
- **User feedback**: Clear success/error messages via AJAX responses

## Data Integration Pipeline

### Data Generation Integration
- **Initialization**: `generate_data.py` loads reviews at startup
- **Data inclusion**: Reviews included in `data.json` for each movie
- **Availability check**: System works with or without review file
- **Performance**: Reviews loaded once, cached for entire generation run

### Newsletter Integration
- **Content source**: Newsletter generator accesses review data from `data.json`
- **Featured content**: Movies with `featured_in_newsletter: true` highlighted
- **Fallback handling**: Newsletter works without reviews (graceful degradation)
- **Rich content**: Full review text, author, and rating included in output

### Public Site Integration
- **Data availability**: Reviews accessible via `data.json` for frontend display
- **Optional display**: Frontend can show/hide reviews based on UI design
- **Rich metadata**: Reviews provide additional content beyond automated data

## Review Workflow

### Content Creation Process
1. **Curator browses movies** in admin panel
2. **Identifies notable releases** requiring editorial coverage
3. **Writes review** in admin panel review section
4. **Sets rating** and author information
5. **Marks as featured** for newsletter highlighting (optional)
6. **Saves review** (triggers data regeneration)

### Newsletter Publication
1. **Reviews created** throughout week as movies are evaluated
2. **Featured movie selected** via `featured_in_newsletter` flag
3. **Newsletter generated** with `python3 generate_newsletter.py`
4. **Review content** automatically included in appropriate sections
5. **Distribution** to subscribers via preferred channels

### Quality Control
- **Review editing**: Updates trigger data regeneration
- **Review deletion**: Complete removal with backup
- **Batch operations**: Multiple reviews can be managed efficiently
- **Content versioning**: `last_modified` tracks review changes

## File Management

### Files Created
- `admin/movie_reviews.json` - Review storage (new file)

### Files Modified
- `admin.py` - Review CRUD routes and backend logic
- `admin/templates/index.html` - Review UI components
- `admin/static/js/admin.js` - Review JavaScript handlers
- `generate_data.py` - Review data integration and loading

### Backup Strategy
- **Atomic writes**: Backup created before each write operation
- **Error recovery**: Automatic restore on write failure
- **Version control**: File tracked in git for historical preservation
- **Manual backup**: Admin can manually backup review file

## Technical Specifications

### Performance Characteristics
- **Load time**: Reviews loaded once per data generation
- **Memory usage**: Minimal (reviews cached in memory)
- **Write performance**: Atomic operations with backup management
- **Read performance**: Direct dictionary lookup by movie ID

### Data Validation
- **Rating bounds**: 0-5 range with 0.5 increment precision
- **Required fields**: Review text and author required for save
- **Input sanitization**: Basic HTML escape for security
- **JSON validation**: Schema validation on load and save

### Integration Points
- **Admin panel**: Full CRUD interface for review management
- **Data pipeline**: Reviews included in generated display data
- **Newsletter system**: Reviews provide editorial content
- **Frontend ready**: Reviews available for UI display (future)

## Rationale

### Editorial Value Proposition
- **Context provision**: Reviews explain why movies matter beyond ratings
- **Curation signal**: Editorial attention indicates noteworthy releases
- **Personality injection**: Human voice distinguishes from automated feeds
- **Quality assurance**: Manual review ensures content relevance

### Workflow Integration
- **Inline editing**: Reviews written during normal admin workflow
- **Immediate availability**: Changes reflected in next data generation
- **Newsletter readiness**: Editorial content ready for distribution
- **Simple management**: One interface for all admin tasks

### Technical Benefits
- **Data consistency**: Reviews integrated into main data pipeline
- **Performance efficiency**: Single load, multiple usage points
- **Backup safety**: Atomic operations prevent data loss
- **Future extensibility**: Schema supports additional metadata

## Future Enhancements

### Content Features
- **Review categories**: Genre-specific, platform-specific reviews
- **Collaborative reviews**: Multiple author support
- **Review templates**: Structured review formats
- **Media integration**: Screenshots, clips, poster highlights

### Workflow Features
- **Review scheduling**: Publish reviews on specific dates
- **Bulk operations**: Batch import/export of reviews
- **Review reminders**: Notifications for unreviewed notable movies
- **Analytics integration**: Track review engagement and effectiveness

### Distribution Features
- **Social media formatting**: Platform-specific review excerpts
- **Email integration**: Direct review distribution to subscribers
- **API exposure**: Reviews available via external API
- **Content syndication**: Review distribution to partner sites

## Related Features
- **Newsletter Generator** (AMENDMENT-051): Consumes review content for distribution
- **Admin Panel** (AMENDMENT-045): Provides review creation and management interface
- **Data Pipeline**: Integrates reviews into main data generation workflow

## Status
✅ Implemented and documented
✅ Unblocks HIGH-002 (Newsletter Export) in IMPLEMENTATION_ROADMAP.md
✅ Full CRUD operations available in admin panel
✅ Newsletter integration complete