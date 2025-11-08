# Unified Launcher Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-052
**Date:** 2025-10-23
**Maintainer:** Development Team

## Overview

The Unified Launcher (`launch_all.sh`) is a menu-driven interface that consolidates launching all NRW tools into a single command. It eliminates the need to remember multiple separate commands and provides streamlined access to the public site, admin panel, and YouTube management tools.

## Context

Previously, users needed to remember three separate commands to launch different NRW tools:
- `./launch_NRW.sh` for the public site
- `python3 admin.py` for the admin panel
- `python3 youtube_playlist_manager.py [args]` for YouTube management

This created friction for daily operations and onboarding new users to the project.

## Solution

Create `launch_all.sh` as unified launcher with menu-driven interface providing:
- Four menu options: (1) Public Site, (2) Admin Panel, (3) YouTube Manager, (4) All Services
- Browser auto-open for web interfaces (site and admin)
- Process management with graceful cleanup on Ctrl+C
- Authentication reminder for admin panel access

## Implementation

### Script Architecture
**File:** `launch_all.sh` (~430 lines)

### Menu Interface
Menu-driven interface with 5 options:
- **Option 1:** Public Site - HTTP server on port 8000/8001, auto-open browser
- **Option 2:** Admin Panel - Flask server on port 5555, auth reminder, auto-open browser
- **Option 3:** YouTube Playlist Manager - Executes `python3 youtube_playlist_manager.py --help` and displays output
- **Option 4:** All Services - Launch site + admin simultaneously, both auto-open
- **Option 5:** Exit - Clean shutdown

### Process Management

#### Global Variables
- `SITE_PID` - Process ID for public site server
- `ADMIN_PID` - Process ID for admin panel server
- `YOUTUBE_PID` - Process ID for YouTube manager (if applicable)

#### Cleanup Function
- Checks if PIDs exist and running with `kill -0`
- Graceful shutdown with `kill $PID` for each service
- Automatic cleanup on script exit or Ctrl+C
- Registered cleanup with `trap` for EXIT, INT, TERM signals

#### Service Lifecycle
- Tracks PIDs for all launched processes
- Cleanup function ensures complete shutdown
- Prevents orphaned processes
- Staggered launches (2-second delay between services)

### Authentication Integration

#### Admin Panel Credentials
- Displays credentials box when launching admin panel (options 2 or 4)
- Shows generic reminder with pointer to `PROJECT_CHARTER.md`
- No in-script credentials (security best practice)
- Security note about changing defaults in production

#### Display Format
Large box display for admin credentials to reduce login friction and ensure visibility.

### Browser Integration

#### Auto-Open Capability
- Detects `open` (macOS) or `xdg-open` (Linux)
- Auto-opens URLs for web interfaces
- Displays URLs if no opener available
- Staggered browser opens for option 4 (site first, admin after 1 second)

#### Error Handling
- Graceful fallback for missing browser opener
- Clear URL display when auto-open unavailable
- No script failure if browser detection fails

### Error Handling and Validation

#### Port Management
- Port availability checking using `lsof`
- Readiness checks include `lsof` if available
- Curl-based HTTP probes as fallback
- Clear error messages for port conflicts

#### Dependency Validation
- python3 and git required
- Graceful fallbacks for missing tools (`lsof`, browser opener)
- Helpful error messages for missing dependencies
- Script continues with reduced functionality when possible

#### Service Readiness
- HTTP probes to verify services are running
- Timeout-based readiness checks
- Clear status messages for user feedback
- Fallback checks when preferred tools unavailable

## Design Decisions

### Menu-Driven vs. Command-Line Flags
- **Menu interface:** More discoverable for new users
- **Reduces cognitive load:** No need to remember flags
- **Interactive experience:** Guides users through options
- **Self-documenting:** All options visible in menu

### Process Management Strategy
- **Track all PIDs:** Ensures complete cleanup
- **Graceful shutdown:** Proper service termination
- **Staggered launches:** Prevents port conflicts and startup races
- **Signal handling:** Robust cleanup on interruption

### YouTube CLI Integration
- **Interactive prompt:** For commands rather than background service
- **Matches CLI nature:** YouTube manager is command-line tool
- **Help display:** Shows available commands to users
- **No background process:** Aligns with tool's design

### Browser Auto-Open Strategy
- **Automatic for web interfaces:** Reduces manual steps
- **Manual for CLI tools:** Appropriate for command-line tools
- **Fallback display:** Shows URLs when auto-open fails
- **User choice:** Can ignore auto-open if preferred

### Authentication Prominence
- **Large box display:** Ensures credentials are visible
- **Reduces login friction:** Easy access to authentication info
- **Security conscious:** Points to external documentation
- **Production awareness:** Reminds about default credential changes

### Backward Compatibility
- **Original scripts unchanged:** `launch_NRW.sh`, `admin.py` remain supported
- **No breaking changes:** Existing workflows continue to work
- **Migration optional:** Users can adopt unified launcher gradually
- **Automation support:** Direct launches still available for scripting

## File Structure

### Files Created
- `launch_all.sh` - Unified launcher script (~430 lines)

### Files Modified
- `README.md` - Updated Quick Start section, added comprehensive Unified Launcher documentation
- `DAILY_CONTEXT.md` - Added launcher to Quick Reference section, updated admin panel instructions
- `PROJECT_CHARTER.md` - This amendment documentation

### Files Unchanged (Backward Compatibility)
- `launch_NRW.sh` - Public site launcher (existing, still supported)
- `admin.py` - Admin panel (existing, still supported)
- `youtube_playlist_manager.py` - YouTube CLI (existing, still supported)

## Usage Patterns

### Primary Command
```bash
./launch_all.sh
```

### Recommended Daily Workflow
Select option 4 (All Services) for comprehensive access:
- Public site for viewing current wall
- Admin panel for curation and management
- Both services ready simultaneously

### YouTube Playlist Management
Select option 3 for interactive CLI:
- Displays available commands
- Guides users through YouTube workflows
- Maintains command-line nature of tool

### Direct Launches (Still Supported)
For automation and scripting:
- `./launch_NRW.sh` - Direct public site launch
- `python3 admin.py` - Direct admin panel launch
- `python3 youtube_playlist_manager.py` - Direct YouTube CLI

## Service Configuration

### Port Assignments
- **Public Site:** 8000 (primary), 8001 (if 8000 busy)
- **Admin Panel:** 5555 (fixed)
- **Port Detection:** Automatic checking and fallback

### Service Dependencies
- **Python 3:** Required for all services
- **Git:** Required for repository operations
- **lsof:** Optional, for port checking
- **Browser opener:** Optional, for auto-open functionality

### Service Integration
- **Staggered startup:** Prevents resource conflicts
- **Readiness probes:** Ensures services are available before proceeding
- **Clean shutdown:** All services terminated properly

## Performance Characteristics

### Startup Time
- **Menu display:** Instant
- **Service launch:** 2-3 seconds per service
- **Browser open:** Additional 1-2 seconds
- **Total time:** 5-10 seconds for all services

### Resource Usage
- **Memory:** Minimal overhead (bash script)
- **CPU:** Brief spikes during service startup
- **Network:** Port binding for HTTP services
- **Disk:** No additional storage requirements

### Scalability
- **Additional services:** Easy to add new menu options
- **Process tracking:** Scales with number of services
- **Cleanup complexity:** Linear with service count
- **Menu size:** Manageable for reasonable number of options

## Maintenance Considerations

### Code Organization
- **Modular functions:** Separate functions for each service type
- **Reusable logic:** Browser detection, port checking shared
- **Clear separation:** Setup, launch, and cleanup phases distinct
- **Error boundaries:** Isolated error handling per function

### Configuration Management
- **Hardcoded ports:** Simple but could be configurable
- **Service paths:** Relative to script directory
- **Command paths:** Uses system PATH for flexibility
- **Feature detection:** Runtime capability checking

### Future Extensibility
- **New services:** Add to menu and process tracking
- **Configuration file:** Could add for advanced options
- **Remote services:** Could support non-local services
- **Service health:** Could add monitoring capabilities

## Related Files

### Implementation Files
- `launch_all.sh` - Unified launcher (new)
- `launch_NRW.sh` - Public site launcher (existing, still supported)
- `admin.py` - Admin panel (existing, still supported)
- `youtube_playlist_manager.py` - YouTube CLI (existing, still supported)

### Documentation Files
- `README.md` - Usage documentation and quick start
- `DAILY_CONTEXT.md` - Quick reference and daily workflow
- `PROJECT_CHARTER.md` - Governance and amendment history

## Rationale

### User Experience Benefits
- **Single entry point:** Eliminates need to remember multiple commands
- **Improved discovery:** Menu interface aids exploration and onboarding
- **Optimized workflow:** Option 4 (All Services) streamlines daily operations
- **Reduced friction:** Authentication reminders and auto-open reduce barriers

### Technical Benefits
- **Process management:** Prevents orphaned processes through proper cleanup
- **Error handling:** Graceful degradation when tools are missing
- **Backward compatibility:** Maintains existing automation and scripting workflows
- **Maintainability:** Centralized launcher simplifies future service additions

### Operational Benefits
- **Training simplification:** New users learn single command
- **Consistency:** Uniform interface across all NRW tools
- **Reliability:** Robust error handling and cleanup procedures
- **Flexibility:** Supports both interactive and automation use cases

## Status
✅ Implemented and documented
✅ Full menu interface with all service options
✅ Process management and cleanup implemented
✅ Browser auto-open and authentication reminders working
✅ Backward compatibility maintained
✅ Documentation updated across relevant files