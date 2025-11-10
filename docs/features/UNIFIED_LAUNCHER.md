# Unified Launcher (Amendment 031)

Menu interface for all NRW services. Run `./launch_all.sh` for options. Replaces individual scripts.

## Overview

The Unified Launcher provides a menu-driven interface per Amendment 031, serving as the single entry point for all NRW services. This eliminates the need for separate terminal commands and provides guided access to admin panel, public site, and utilities.

## Menu Options

### Main Menu Interface

```
┌─────────────────────────────────────────────────────────┐
│           🎬 NRW Unified Launcher                       │
│        Single Entry Point for All Services             │
└─────────────────────────────────────────────────────────┘

1. Launch Admin Panel (background, port 5556)
2. Launch Public Site (foreground, port 3000)
3. Launch All (admin bg + site fg, auto-open browsers)
4. Utilities (health checks, stop services)
0. Exit

Environment overrides: ADMIN_PORT=5556 SITE_PORT=3000
```

### Option 1: Admin Panel
- **Launch:** Admin panel in background on port 5556
- **Authentication:** No auth required for local curation
- **Features:** Direct access to curation interface
- **Health Check:** Automatic verification via `/health` endpoint
- **Auto-open:** Optional browser launch to admin URL

### Option 2: Public Site
- **Launch:** Public site in foreground on port 3000
- **Mode:** Interactive (blocks until Ctrl+C)
- **Features:** View current movie wall
- **Server:** Python3 HTTP server
- **Port Fallback:** Uses 3001 if 3000 occupied

### Option 3: Launch All (Recommended)
- **Admin:** Launched in background with auto-open
- **Site:** Launched in background with auto-open
- **Combined:** Both services with browser launch
- **Process Management:** Single Ctrl+C stops both services
- **Display:** Shows both URLs clearly
- **Monitoring:** Watches for process failures

### Option 4: Utilities
- **Health Check:** Verify admin (`/health`) and site (`/`) endpoints
- **Stop Services:** Kill processes on standard ports using lsof
- **View Logs:** Display recent admin log entries
- **Sub-menu:** Returns to main menu after operations

## Features

### Port Conflict Handling
- **Admin:** 5556 → 5557 fallback if occupied
- **Site:** 3000 → 3001 fallback if occupied
- **Detection:** Uses `lsof` when available
- **Messages:** Clear warnings when fallbacks triggered

### Process Tracking
- **PID Management:** Tracks `ADMIN_PID` and `SITE_PID`
- **Health Monitoring:** Continuous process validation
- **Clean Shutdown:** Proper termination on exit/Ctrl+C
- **Signal Handling:** Responds to INT/TERM for cleanup

### Environment Variable Overrides
```bash
# Custom ports
ADMIN_PORT=5557 ./launch_all.sh
SITE_PORT=8000 ./launch_all.sh

# Combined
ADMIN_PORT=5557 SITE_PORT=8000 ./launch_all.sh
```

### Browser Auto-Open
- **Detection:** Uses `open` command when available (macOS)
- **Launch All:** Opens both admin and site URLs
- **Individual:** Opens respective service URL
- **Fallback:** Shows URLs if auto-open unavailable

### Tool Detection
- **Python:** Prefers `python3`, falls back to `python`
- **Port Checking:** Uses `lsof` when available
- **Error Handling:** Graceful degradation for missing tools
- **Dependencies:** Validates required tools on startup

## Troubleshooting

### Port Issues
```bash
# Check what's using ports
lsof -i :5556
lsof -i :3000

# Force stop services via utilities menu (option 4 → option 2)
```

### Python Not Found
- Script auto-detects `python3` vs `python`
- Use appropriate alias/symlink if neither found
- Ensure Python 3.x is installed and in PATH

### Process Cleanup
- Launcher handles cleanup automatically
- Ctrl+C in 'All' mode stops both services
- Use utilities menu for manual stop if needed

### Browser Auto-Open
- Works with `open` command (macOS primarily)
- Shows URLs when auto-open unavailable
- Manual navigation if browser detection fails

## Daily Workflow Integration

### Recommended Usage
**Option 3 (Launch All)** for development/testing:
- Starts both admin and site services
- Auto-opens browsers for immediate access
- Single Ctrl+C stops everything cleanly
- Ideal for daily curation and preview

### Curation Workflow
1. Launch all services (option 3)
2. Use admin panel for curation (auto-opened)
3. Preview changes on site (auto-opened)
4. Ctrl+C when finished

### Individual Service Access
- **Option 1:** Admin-only for quick edits
- **Option 2:** Site-only for preview/testing
- **Option 4:** Utilities for health checks and cleanup

## Technical Implementation

### Script Structure
- **Tool Detection:** Validates dependencies at startup
- **Menu Loop:** Interactive selection with validation
- **Service Functions:** Modular launch functions per service
- **Process Management:** PID tracking and signal handling
- **Error Handling:** Graceful fallbacks and clear messages

### File Location
```
launch_all.sh          # Root level - primary entry point
docs/features/         # This documentation
```

### Backward Compatibility
Legacy commands still supported:
```bash
python3 admin.py       # Direct admin launch
python3 -m http.server 3000  # Direct site launch
```

## Root Cleanliness Compliance

Per Amendment 032, this launcher:
- **Single Entry Point:** No additional root files created
- **Documentation:** Properly placed in `docs/features/`
- **Port Configuration:** Embedded in script (no separate config files)
- **Clean Interface:** Replaces multiple commands with unified menu

## Amendment 031 Compliance

This implementation fulfills Amendment 031 requirements:
- ✅ Menu-driven interface
- ✅ Single entry point for all services
- ✅ Option 3 "Launch All" for full stack
- ✅ Auto-open browsers in combined mode
- ✅ Process management and clean shutdown
- ✅ Port conflict handling and fallbacks
- ✅ Environment variable support for customization

## Status

✅ **Implemented:** Menu-driven unified launcher
✅ **Documented:** Complete usage and troubleshooting guide
✅ **Tested:** Port handling, process management, cleanup
✅ **Integrated:** Updated README.md and workflow documentation