#!/bin/bash
# block-linear-mcp-writes.sh — Block MCP Linear write tools in Lacrimosa sessions.
# Lacrimosa specialists must use scripts/lacrimosa_linear.py (posts as Lacrimosa).
# MCP tools authenticate as the human operator — wrong attribution.

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')

# Only check Linear MCP write tools
case "$TOOL_NAME" in
    mcp__linear-server__linear_create_*|\
    mcp__linear-server__linear_update_*|\
    mcp__linear-server__linear_delete_*|\
    mcp__linear-server__linear_bulk_*|\
    mcp__linear-server__linear_resolve_*|\
    mcp__linear-server__linear_unresolve_*)
        ;;
    *)
        # Not a Linear write tool — allow
        exit 0
        ;;
esac

# Check if we're in a Lacrimosa tmux session
TMUX_SESSION=""
if [ -n "$TMUX" ]; then
    TMUX_SESSION=$(tmux display-message -p '#S' 2>/dev/null || echo "")
fi

if echo "$TMUX_SESSION" | grep -q '^lacrimosa-'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: Use scripts/lacrimosa_linear.py for Linear writes — MCP tools post as the human operator, not Lacrimosa.\n\nUse: .venv/bin/python -c \"from scripts.lacrimosa_linear import create_comment, create_issue, update_issue_state, assign_to_lacrimosa; ...\"\n\nAvailable: _graphql(), create_comment(), create_issue(), update_issue_state(), update_issue_priority(), update_issue_project(), assign_to_lacrimosa(), get_issue_by_number(), get_issue_comments()"}}'
    exit 0
fi

# Not in a Lacrimosa session — allow (user's own sessions can use MCP)
exit 0
