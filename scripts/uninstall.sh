#!/bin/bash
# ============================================================
# Curator — Uninstall Script (macOS)
# Cleanly removes Curator from your system.
# ============================================================

set -e

PLIST_NAME="com.curator.app.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"
DATA_DIR="$HOME/Library/Application Support/Curator"

echo "📚 Curator — Uninstall"
echo "======================"
echo ""

# --- 1. Stop the service ---
echo "→ Stopping Curator service..."
if [ -f "$PLIST_DST" ]; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    rm -f "$PLIST_DST"
    echo "  ✓ LaunchAgent removed"
else
    echo "  ℹ LaunchAgent not found (already removed?)"
fi

# --- 2. Kill any running process ---
PID_FILE="$DATA_DIR/curator.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    kill "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "  ✓ Process stopped (PID $PID)"
fi

# --- 3. Ask about data ---
echo ""
echo "Your data is stored at:"
echo "  $DATA_DIR"
echo ""
echo "This includes your database, config, and logs."
read -p "Delete all data? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_DIR"
    echo "  ✓ Data directory removed"
else
    echo "  ℹ Data preserved at $DATA_DIR"
fi

# --- 4. Note about project files ---
echo ""
echo "============================================================"
echo "✅ Curator has been uninstalled."
echo ""
echo "  The project source code is still at the cloned location."
echo "  To remove it, delete the project directory manually."
echo ""
echo "  If you used 'uv sync', the virtual environment is inside"
echo "  the project directory (.venv/) and will be removed with it."
echo "============================================================"
