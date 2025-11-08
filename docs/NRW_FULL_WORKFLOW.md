# NRW Full Workflow Overview (Automated + Manual)

This document provides a high-level overview of the complete NRW workflow, combining both automated data pipeline and manual admin operations.

## 📊 Five-Phase Data Pipeline Summary

### Phase 1: Daily Discovery & Monitoring
**Automated** - Runs daily at 9 AM UTC via GitHub Actions
- Discovers new theatrical releases from TMDB API (past 7 days)
- Monitors ALL tracked movies for digital availability changes
- Updates `movie_tracking.json` with new discoveries and availability transitions
- **Output**: 10-20 new movies discovered, 2-5 transitions to "available" status

### Phase 2: Database Enrichment & Link Resolution
**Automated** - Enrichment-on-transition pattern (only newly available movies)
- Enriches 1-10 movies daily (not all 330+ movies)
- Fetches complete metadata: cast, crew, synopsis, posters, genres
- Resolves links: trailers, Wikipedia, Rotten Tomatoes, watch links
- **Performance**: 99.4% cache efficiency, 30-second runtime

### Phase 3: Quality Assurance & Manual Correction
**Manual** - Admin panel interface (`admin.py` on port 5555)

#### Admin Approval Gate
**Current Behavior**: Publish-first with post-publication curation
- Movies automatically appear on public site when discovered
- Admin curates after publication to maintain quality

**Planned Behavior**: Mandatory admin approval prior to Phase 4 generation
- Pre-approval gate before movies reach public display
- Admin review required before `data.json` generation

**Admin Curation Tasks**:
- Hide low-quality direct-to-video releases
- Feature high-profile theatrical releases and awards contenders
- Fix missing data (RT scores, trailers, descriptions)
- Correct watch links and metadata errors
- Apply manual corrections with `manual_*` flags protection

**Key Admin Artifacts**:
- `admin/hidden_movies.json` - Movies excluded from public display
- `admin/featured_movies.json` - Movies highlighted with special styling
- `admin/watch_link_overrides.json` - Manual watch link corrections
- `manual_*` flags in `movie_tracking.json` - Field-specific corrections

### Phase 4: Display Generation
**Automated** - Incorporates admin curation decisions
- Applies admin filtering (hidden movies removed)
- Applies admin featuring (special highlighting)
- Preserves manual corrections via `manual_*` flags
- Generates clean `data.json` for website consumption

### Phase 5: User Display
**Automated** - Netflix-style movie wall
- Beautiful card layouts with posters and metadata
- Three-button watch UI: STREAM/RENT/BUY
- Infinite scroll backwards through weeks of releases

## 🔄 Daily Workflow Integration

**Morning Automation** (9 AM UTC):
1. Discovery: Find new movies and availability changes
2. Enrichment: Process 1-10 newly available movies only
3. Generation: Create updated `data.json` with latest data
4. Commit: Save changes to `automation-updates` branch

**Admin Review** (User-triggered):
1. Sync automation updates: `./sync_daily_updates.sh`
2. Launch admin panel: `python3 admin.py`
3. Review new movies and apply curation decisions
4. Regenerate data: Click "🔄 Regenerate data.json"

## 📚 Deep Dive Documentation

For detailed technical implementation:
- **[NRW_DATA_WORKFLOW_EXPLAINED.md](../NRW_DATA_WORKFLOW_EXPLAINED.md)** - Complete data pipeline mechanics, scraper architecture, file organization
- **[ADMIN_WORKFLOW.md](../ADMIN_WORKFLOW.md)** - Step-by-step admin panel operations, curation best practices, daily routine

For system architecture and troubleshooting:
- **[SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md)** - Technical reference, performance optimization, common failure modes
- **[PROJECT_CHARTER.md](../PROJECT_CHARTER.md)** - Business requirements, governance, API configuration

## 🎯 Key Benefits

**Automation Benefits**:
- **Speed**: 30-second daily updates vs 75-minute full regeneration
- **Efficiency**: 98% reduction in API calls through smart caching
- **Reliability**: Enrichment-on-transition prevents data corruption cascades
- **Scalability**: Handles 330+ tracked movies with minimal processing

**Manual Curation Benefits**:
- **Quality**: Only vetted, complete movies reach public display
- **Flexibility**: Real-time correction of scraper errors and missing data
- **Editorial Control**: Feature trending releases, hide inappropriate content
- **Data Protection**: Manual corrections preserved from automation overwrites

This combined approach ensures both rapid discovery of new releases and high-quality user experience through careful curation.