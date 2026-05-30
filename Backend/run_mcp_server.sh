#!/bin/bash
# Antigravity MCP Server launcher
# Venv varsa onu kullanır, yoksa sistem python'ına düşer.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LOG_FILE="$SCRIPT_DIR/mcp_server.log"
echo "[$(date)] MCP Server başlatılıyor... ANTIGRAVITY_URL=${ANTIGRAVITY_URL}" >> "$LOG_FILE"

cd "$SCRIPT_DIR"

# Paketlenmiş build: yanında donmuş 'backend' binary'si varsa onu kullan (venv/python yok).
if [ -x "$SCRIPT_DIR/backend" ]; then
    exec "$SCRIPT_DIR/backend" mcp-server "$@" 2>> "$LOG_FILE"
fi

# Dev: venv python, yoksa sistem python3
if [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

export PYTHONPATH="$SCRIPT_DIR/app${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m app.unity_ai_mcp.server "$@" 2>> "$LOG_FILE"
