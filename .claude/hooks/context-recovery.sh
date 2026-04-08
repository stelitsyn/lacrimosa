#!/bin/bash
# Context Recovery Hook - Runs on session start/resume
# Provides context continuity for RALPH mode and long-running tasks

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

echo "## Context Recovery"
echo ""

# Check for active task.md
if [ -f "task.md" ]; then
    echo "### Active Task Found"
    echo '```'
    head -50 task.md
    echo '```'
    echo ""
fi

# Check RALPH loop status with lock enforcement
RALPH_FILE=".claude/ralph-loop.local.md"
if [ -f "$RALPH_FILE" ]; then
    # Extract lock status
    LOCKED_BY=$(grep -E "^locked_by:" "$RALPH_FILE" 2>/dev/null | sed 's/locked_by: *//' | tr -d '"' || echo "null")
    IS_ACTIVE=$(grep -E "^active:" "$RALPH_FILE" 2>/dev/null | sed 's/active: *//' || echo "false")

    echo "### RALPH Loop Status"
    echo '```yaml'
    cat "$RALPH_FILE"
    echo '```'
    echo ""

    # Check if loop is locked by another agent
    if [ "$IS_ACTIVE" = "true" ] && [ "$LOCKED_BY" != "null" ] && [ -n "$LOCKED_BY" ]; then
        echo "### ⚠️ RALPH LOOP LOCKED"
        echo ""
        echo "**This loop is currently being worked by another agent session.**"
        echo ""
        echo "- Locked by: \`$LOCKED_BY\`"
        echo "- **DO NOT** work on this loop - another agent owns it"
        echo "- To take over: manually set \`locked_by: null\` in ralph-loop.local.md"
        echo ""
    elif [ "$IS_ACTIVE" = "true" ]; then
        echo "### 🔓 RALPH Loop Available"
        echo ""
        echo "**To claim this loop**, update ralph-loop.local.md:"
        echo '```'
        echo "locked_by: \"$(hostname)-$$\""
        echo "locked_at: \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\""
        echo '```'
        echo ""
    fi
fi

# Recent git activity
echo "### Recent Commits (last 5)"
echo '```'
git log --oneline -5 2>/dev/null || echo "No git history"
echo '```'
echo ""

# Modified files
echo "### Modified Files"
echo '```'
git status --short 2>/dev/null | head -15 || echo "No changes"
echo '```'
echo ""

# Open GitHub issues assigned or created recently
if command -v gh &> /dev/null; then
    echo "### Recent Open Issues"
    echo '```'
    gh issue list --state open --limit 5 2>/dev/null || echo "No issues or gh not authenticated"
    echo '```'
fi

exit 0
