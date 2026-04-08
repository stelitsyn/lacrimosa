#!/bin/bash
# Install Lacrimosa macOS LaunchAgents and SwiftBar plugin.
# Usage: ./macos/install-daemons.sh /path/to/your/lacrimosa/project

set -euo pipefail

PROJECT_DIR="${1:?Usage: $0 /path/to/your/lacrimosa/project}"
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)
VENV_DIR="$PROJECT_DIR/.venv"
HOME_DIR="$HOME"

if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    exit 1
fi

echo "Installing Lacrimosa daemons for: $PROJECT_DIR"

# Install LaunchAgents
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

for plist in "$PROJECT_DIR/macos/launchagents/"*.plist; do
    BASENAME=$(basename "$plist")
    DEST="$LAUNCH_AGENTS_DIR/$BASENAME"
    sed -e "s|__LACRIMOSA_PROJECT_DIR__|$PROJECT_DIR|g" \
        -e "s|__LACRIMOSA_VENV__|$VENV_DIR|g" \
        -e "s|__HOME__|$HOME_DIR|g" \
        "$plist" > "$DEST"
    echo "  Installed: $DEST"
    launchctl load "$DEST" 2>/dev/null || true
done

# Install SwiftBar plugin (if SwiftBar is installed)
SWIFTBAR_DIR="$HOME/Library/Application Support/SwiftBar/plugins"
if [ -d "$SWIFTBAR_DIR" ]; then
    SWIFTBAR_SRC="$PROJECT_DIR/macos/swiftbar/lacrimosa.10s.sh"
    SWIFTBAR_DEST="$SWIFTBAR_DIR/lacrimosa.10s.sh"
    sed "s|__LACRIMOSA_PROJECT_DIR__|$PROJECT_DIR|g" "$SWIFTBAR_SRC" > "$SWIFTBAR_DEST"
    chmod +x "$SWIFTBAR_DEST"
    echo "  Installed SwiftBar plugin: $SWIFTBAR_DEST"
else
    echo "  SwiftBar not found — skipping menu bar plugin"
fi

echo "Done. Daemons start at next login, or load manually:"
echo "  launchctl load ~/Library/LaunchAgents/com.lacrimosa.watchdog.plist"
echo "  launchctl load ~/Library/LaunchAgents/com.lacrimosa.dashboard.plist"
