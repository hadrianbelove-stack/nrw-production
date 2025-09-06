#!/bin/bash
set -euo pipefail
pkill -f "http\.server" 2>/dev/null || true
pkill -f "curator_admin\.py" 2>/dev/null || true
echo "Stopped http.server and curator_admin if running"
