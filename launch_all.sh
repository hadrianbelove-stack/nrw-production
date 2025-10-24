#!/bin/bash

# NEW RELEASE WALL - Unified Launcher
# Provides a menu-driven interface to launch all NRW tools:
# 1) Public Site (HTTP server on port 8000/8001)
# 2) Admin Panel (Flask server on port 5555)
# 3) YouTube Playlist Manager (CLI tool)
# 4) All Services (site + admin simultaneously)

set -e

# Terminal color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global variables for process tracking
SITE_PID=""
ADMIN_PID=""
YOUTUBE_PID=""

# Browser command detection
BROWSER_CMD=""

# Cleanup function - gracefully shut down all running processes
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down services...${NC}"

    if [[ -n "$SITE_PID" ]] && kill -0 "$SITE_PID" 2>/dev/null; then
        echo -e "${BLUE}   Stopping public site (PID: $SITE_PID)${NC}"
        kill "$SITE_PID" 2>/dev/null || true
        SITE_PID=""
    fi

    if [[ -n "$ADMIN_PID" ]] && kill -0 "$ADMIN_PID" 2>/dev/null; then
        echo -e "${BLUE}   Stopping admin panel (PID: $ADMIN_PID)${NC}"
        kill "$ADMIN_PID" 2>/dev/null || true
        ADMIN_PID=""
    fi

    if [[ -n "$YOUTUBE_PID" ]] && kill -0 "$YOUTUBE_PID" 2>/dev/null; then
        echo -e "${BLUE}   Stopping YouTube manager (PID: $YOUTUBE_PID)${NC}"
        kill "$YOUTUBE_PID" 2>/dev/null || true
        YOUTUBE_PID=""
    fi

    echo -e "${GREEN}✅ All services stopped${NC}"
    exit 0
}

# Register cleanup function for various exit signals
trap cleanup EXIT INT TERM

# Detect available browser command
detect_browser() {
    if command -v open >/dev/null 2>&1; then
        BROWSER_CMD="open"
    elif command -v xdg-open >/dev/null 2>&1; then
        BROWSER_CMD="xdg-open"
    else
        echo -e "${YELLOW}⚠️  No browser opener found. URLs will be displayed for manual opening.${NC}"
        BROWSER_CMD=""
    fi
}

# Open URL in browser if available
open_browser() {
    local url="$1"
    if [[ -n "$BROWSER_CMD" ]]; then
        echo -e "${BLUE}🌐 Opening $url in browser...${NC}"
        "$BROWSER_CMD" "$url" 2>/dev/null &
    else
        echo -e "${YELLOW}🌐 Please open: $url${NC}"
    fi
}

# Check if a port is available
check_port() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        if lsof -Pi ":$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
            return 1  # Port is in use
        else
            return 0  # Port is available
        fi
    else
        echo -e "${YELLOW}⚠️  'lsof' not found. Cannot check if port $port is available.${NC}"
        return 0  # Assume available
    fi
}

# Launch Public Site function
launch_site() {
    local auto_open="${1:-true}"
    echo -e "${GREEN}🎬 Launching Public Site...${NC}"

    # Check ports 8000 and 8001
    local port=8000
    if ! check_port 8000; then
        echo -e "${YELLOW}   Port 8000 is busy, trying 8001...${NC}"
        if ! check_port 8001; then
            echo -e "${RED}❌ Both ports 8000 and 8001 are in use!${NC}"
            echo -e "${YELLOW}   Try stopping other services or choose a different option.${NC}"
            return 1
        fi
        port=8001
    fi

    # Start Python HTTP server
    echo -e "${BLUE}   Starting HTTP server on port $port...${NC}"
    python3 -m http.server "$port" &
    SITE_PID=$!

    # Wait for server to be ready
    echo -e "${BLUE}   Waiting for server to start...${NC}"
    local attempts=0
    local max_attempts=15

    while ! check_port "$port" && [ $attempts -lt $max_attempts ]; do
        sleep 1
        attempts=$((attempts + 1))
    done

    if [ $attempts -eq $max_attempts ]; then
        echo -e "${RED}❌ Server failed to start after $max_attempts seconds${NC}"
        return 1
    fi

    # Open browser if requested
    if [[ "$auto_open" == "true" ]]; then
        sleep 1  # Give server a moment to fully initialize
        open_browser "http://localhost:$port"
    fi

    echo -e "${GREEN}✅ Public Site running at http://localhost:$port${NC}"
    return 0
}

# Launch Admin Panel function
launch_admin() {
    local auto_open="${1:-true}"
    echo -e "${GREEN}🔧 Launching Admin Panel...${NC}"

    # Check if port 5555 is available
    if ! check_port 5555; then
        echo -e "${RED}❌ Port 5555 is in use!${NC}"
        echo -e "${YELLOW}   Stop the conflicting service or choose a different option.${NC}"
        return 1
    fi

    # Display authentication reminder
    echo ""
    echo "┌─────────────────────────────────────────┐"
    echo "│ 🔐 AUTHENTICATION REQUIRED              │"
    echo "│                                         │"
    echo "│ Username: admin                         │"
    echo "│ Password: admin                         │"
    echo "│                                         │"
    echo "│ See PROJECT_CHARTER.md for credentials  │"
    echo "└─────────────────────────────────────────┘"
    echo ""

    # Start admin panel
    echo -e "${BLUE}   Starting Flask server on port 5555...${NC}"
    python3 admin.py &
    ADMIN_PID=$!

    # Wait for Flask to be ready
    echo -e "${BLUE}   Waiting for Flask server to start...${NC}"
    local attempts=0
    local max_attempts=15

    while check_port 5555 && [ $attempts -lt $max_attempts ]; do
        sleep 1
        attempts=$((attempts + 1))
    done

    if [ $attempts -eq $max_attempts ]; then
        echo -e "${RED}❌ Admin panel failed to start after $max_attempts seconds${NC}"
        return 1
    fi

    # Open browser if requested
    if [[ "$auto_open" == "true" ]]; then
        sleep 1  # Give Flask a moment to fully initialize
        open_browser "http://localhost:5555"
    fi

    echo -e "${GREEN}✅ Admin Panel running at http://localhost:5555${NC}"
    return 0
}

# Launch YouTube Playlist Manager function
launch_youtube() {
    echo -e "${GREEN}📺 YouTube Playlist Manager${NC}"
    echo ""
    echo -e "${BLUE}This is a CLI tool, not a web interface.${NC}"
    echo ""
    echo "Common commands:"
    echo "  python3 youtube_playlist_manager.py auth          # First-time setup"
    echo "  python3 youtube_playlist_manager.py test          # Test trailer extraction"
    echo "  python3 youtube_playlist_manager.py weekly        # Create weekly playlist"
    echo "  python3 youtube_playlist_manager.py --help        # Full help"
    echo ""

    read -p "Run a command now? (y/n): " -r run_command
    if [[ $run_command =~ ^[Yy]$ ]]; then
        read -p "Enter command (e.g., 'test' or 'weekly --dry-run'): " -r user_input
        echo ""
        echo -e "${BLUE}Running: python3 youtube_playlist_manager.py $user_input${NC}"
        echo ""

        if python3 youtube_playlist_manager.py $user_input; then
            echo ""
            echo -e "${GREEN}✅ Command completed successfully${NC}"
        else
            echo ""
            echo -e "${RED}❌ Command failed or returned an error${NC}"
        fi
    fi

    echo ""
    echo -e "${BLUE}Press Enter to return to menu...${NC}"
    read -r
}

# Launch All Services function
launch_all() {
    echo -e "${GREEN}🚀 Launching All Services...${NC}"
    echo ""

    # Launch public site (no auto-open yet)
    if ! launch_site false; then
        echo -e "${RED}❌ Failed to launch public site${NC}"
        return 1
    fi

    # Stagger launches
    sleep 2

    # Launch admin panel (no auto-open yet)
    if ! launch_admin false; then
        echo -e "${RED}❌ Failed to launch admin panel${NC}"
        return 1
    fi

    # Display YouTube manager info
    echo ""
    echo -e "${BLUE}📺 YouTube Playlist Manager (CLI tool):${NC}"
    echo "   Use: python3 youtube_playlist_manager.py [command]"
    echo "   Commands: auth, test, weekly, --help"
    echo ""

    # Display summary
    echo "┌─────────────────────────────────────────┐"
    echo "│ ✅ ALL SERVICES RUNNING                 │"
    echo "│                                         │"
    echo "│ 🎬 Public Site: http://localhost:8000   │"
    echo "│ 🔧 Admin Panel: http://localhost:5555   │"
    echo "│ 📺 YouTube: CLI tool (see above)        │"
    echo "│                                         │"
    echo "│ Press Ctrl+C to stop all services       │"
    echo "└─────────────────────────────────────────┘"
    echo ""

    # Open both URLs in browser
    open_browser "http://localhost:8000"
    sleep 1
    open_browser "http://localhost:5555"

    # Wait indefinitely until Ctrl+C
    echo -e "${BLUE}Services are running. Press Ctrl+C to stop all services.${NC}"
    wait
}

# Display main menu
show_menu() {
    clear
    echo "╔═══════════════════════════════════════╗"
    echo "║   NEW RELEASE WALL - Launcher         ║"
    echo "║   Choose a tool to launch             ║"
    echo "╚═══════════════════════════════════════╝"
    echo ""
    echo "1) 🎬 Launch Public Site (port 8000/8001)"
    echo "2) 🔧 Launch Admin Panel (port 5555)"
    echo "3) 📺 YouTube Playlist Manager (CLI)"
    echo "4) 🚀 Launch All Services"
    echo "5) ❌ Exit"
    echo ""

    while true; do
        read -p "Enter your choice [1-5]: " -r choice

        case $choice in
            1)
                echo ""
                if launch_site; then
                    echo ""
                    echo -e "${BLUE}Press Ctrl+C to stop the server and return to menu.${NC}"
                    wait
                fi
                echo ""
                echo -e "${BLUE}Press Enter to return to menu...${NC}"
                read -r
                show_menu
                return
                ;;
            2)
                echo ""
                if launch_admin; then
                    echo ""
                    echo -e "${BLUE}Press Ctrl+C to stop the server and return to menu.${NC}"
                    wait
                fi
                echo ""
                echo -e "${BLUE}Press Enter to return to menu...${NC}"
                read -r
                show_menu
                return
                ;;
            3)
                echo ""
                launch_youtube
                show_menu
                return
                ;;
            4)
                echo ""
                launch_all
                return
                ;;
            5)
                echo ""
                echo -e "${GREEN}👋 Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid choice. Please enter 1-5.${NC}"
                ;;
        esac
    done
}

# Main entry point
main() {
    # Check dependencies
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}❌ python3 is required but not installed.${NC}"
        exit 1
    fi

    if ! command -v git >/dev/null 2>&1; then
        echo -e "${RED}❌ git is required but not installed.${NC}"
        exit 1
    fi

    # Detect browser
    detect_browser

    # Welcome message
    echo -e "${GREEN}🎬 NEW RELEASE WALL - Unified Launcher${NC}"
    echo "======================================"
    echo ""

    # Check if data.json exists (non-fatal warning)
    if [[ ! -f "data.json" ]]; then
        echo -e "${YELLOW}⚠️  Warning: data.json not found. You may need to run data generation first.${NC}"
        echo ""
    fi

    # Start interactive menu
    show_menu
}

# Run main function
main "$@"