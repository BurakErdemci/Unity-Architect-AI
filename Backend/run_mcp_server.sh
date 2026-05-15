#!/bin/bash
# Antigravity MCP Server launcher
# Venv varsa onu kullanır, yoksa sistem python'ına düşer.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

LOG_FILE="$SCRIPT_DIR/mcp_server.log"
echo "[$(date)] MCP Server başlatılıyor... ANTIGRAVITY_URL=${ANTIGRAVITY_URL}" >> "$LOG_FILE"

cd "$SCRIPT_DIR"
exec "$PYTHON" -m app.unity_ai_mcp.server "$@" 2>> "$LOG_FILE"
