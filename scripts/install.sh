#!/bin/bash
# ============================================================
# Curator — Install Script (macOS)
# Run this once after cloning the repository.
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$HOME/Library/Application Support/Curator"
PLIST_NAME="com.curator.app.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "📚 Curator — Installation"
echo "========================="
echo ""

# --- 1. Check / install uv ---
if ! command -v uv &> /dev/null; then
    echo "→ Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "  ✓ uv installed"
else
    echo "  ✓ uv already installed ($(uv --version))"
fi

UV_PATH="$(which uv)"

# --- 2. Install Python dependencies ---
echo "→ Installing dependencies..."
cd "$PROJECT_DIR"
uv sync
echo "  ✓ Dependencies installed"

# --- 3. Create data directory ---
mkdir -p "$DATA_DIR/logs"
echo "  ✓ Data directory: $DATA_DIR"

# --- 4. Initialise database ---
echo "→ Initialising database..."
uv run curator init
echo "  ✓ Database ready"

# --- 5. Install LaunchAgent (auto-start at login) ---
echo "→ Setting up auto-start..."

# Create plist from template with correct paths
sed \
    -e "s|__UV_PATH__|$UV_PATH|g" \
    -e "s|__PROJECT_PATH__|$PROJECT_DIR|g" \
    -e "s|__DATA_DIR__|$DATA_DIR|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# Load the agent (unload first if already loaded)
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "  ✓ LaunchAgent installed and started"

# --- 6. Done ---
echo ""
echo "============================================================"
echo "✅ Curator is installed and running!"
echo ""
echo "  🌐 Open:     http://localhost:7745"
echo "  📂 Data:     $DATA_DIR"
echo "  📋 Config:   $DATA_DIR/config.json"
echo "  📜 Logs:     $DATA_DIR/logs/"
echo ""
echo "  CLI:         uv run curator --help"
echo "  Stop:        uv run curator stop"
echo "  Uninstall:   bash scripts/uninstall.sh"
echo ""
echo "  Next steps:"
echo "  1. Open http://localhost:7745 in Safari"
echo "  2. Go to Settings → copy the bookmarklet"
echo "  3. Set up your GitHub username for star imports"
echo "  4. (Optional) Add AI API keys for smart tagging"
echo "============================================================"
