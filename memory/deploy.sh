#!/usr/bin/env bash
# Deploy Lacrimosa memory files to Claude Code's per-project memory directory.
# Run from the Lacrimosa repo root: ./memory/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Claude Code encodes project paths by replacing all / with -
# The leading / becomes a leading -, so the result starts with -
# Example: /home/user/projects/lacrimosa -> -home-user-projects-lacrimosa
ENCODED_PATH=$(echo "$REPO_ROOT" | sed 's|/|-|g')

MEMORY_TARGET="$HOME/.claude/projects/${ENCODED_PATH}/memory"

echo "Lacrimosa Memory Deploy"
echo "======================="
echo ""
echo "Repo root:    $REPO_ROOT"
echo "Encoded path: $ENCODED_PATH"
echo "Target:       $MEMORY_TARGET"
echo ""

# Create target directory
mkdir -p "$MEMORY_TARGET"

# Count files to copy
COPIED=0
SKIPPED=0

for src in "$SCRIPT_DIR"/*.md; do
    filename=$(basename "$src")

    # Skip deploy artifacts
    if [[ "$filename" == "DEPLOY.md" ]]; then
        ((SKIPPED++)) || true
        continue
    fi

    dest="$MEMORY_TARGET/$filename"

    # Check if target exists and is identical
    if [[ -f "$dest" ]] && diff -q "$src" "$dest" > /dev/null 2>&1; then
        echo "  [skip] $filename (identical)"
        ((SKIPPED++)) || true
        continue
    fi

    cp "$src" "$dest"
    echo "  [copy] $filename"
    ((COPIED++)) || true
done

echo ""
echo "Done: $COPIED copied, $SKIPPED skipped"
echo ""

if [[ $COPIED -gt 0 ]]; then
    echo "Memory files deployed. They will be available in your next Claude Code session."
    echo "To verify: ls $MEMORY_TARGET/"
else
    echo "All memory files were already up to date."
fi
