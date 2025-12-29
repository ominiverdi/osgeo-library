#!/bin/bash
# OSGeo Library API Server - startup script
#
# Usage:
#   ./servers/start-server.sh           # Run in foreground
#   ./servers/start-server.sh &         # Run in background
#
# For cron @reboot (survives server restarts):
#   crontab -e
#   @reboot ~/github/osgeo-library/servers/start-server.sh >> ~/logs/osgeo-library.log 2>&1
#
# Test:
#   curl http://localhost:8095/health

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${HOME}/logs"

# Create log directory
mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR" || exit 1

echo "[$(date)] Starting OSGeo Library API server..."
echo "  Project: $PROJECT_DIR"
echo "  Port: 8095"

exec "$PROJECT_DIR/.venv/bin/python" -m doclibrary.servers.api
