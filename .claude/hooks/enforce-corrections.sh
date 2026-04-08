#!/bin/bash
# enforce-corrections.sh — PreToolUse hook for structurally-enforced corrections
# Reads tool_name and tool_input from stdin, blocks/warns on known anti-patterns.
#
# Hook contract:
#   - Exit 0: allow (no output = allow)
#   - Exit 0 + JSON with permissionDecision "deny": block with reason
#   - Exit 0 + JSON with permissionDecision "ask": prompt user
#   - Exit 2: block (hard error)

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')

# ─── Rule 1: Agent without team_name when "team" is in user prompt ───
# If the user asked for a "team" but Claude is spawning a plain Agent
# without team_name, warn about using TeamCreate instead.
if [ "$TOOL_NAME" = "Agent" ]; then
    TEAM_NAME=$(echo "$INPUT" | jq -r '.tool_input.team_name // ""')
    RUN_BG=$(echo "$INPUT" | jq -r '.tool_input.run_in_background // false')

    # If Agent is called with run_in_background=true and no team_name,
    # this is a background subagent, not a team member — warn
    if [ "$RUN_BG" = "true" ] && [ -z "$TEAM_NAME" ]; then
        # Check if user's recent prompt mentioned "team"
        USER_PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // ""')
        if echo "$USER_PROMPT" | grep -iqE '(agentic team|agent team|spawn.*(team|squad)|real team)'; then
            echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"User asked for an Agent Team but you are spawning a background subagent. Use TeamCreate + Agent with team_name parameter instead of run_in_background=true."}}'
            exit 0
        fi
    fi
fi

# ─── Rule 2: git stash as workaround ───
if [ "$TOOL_NAME" = "Bash" ]; then
    COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
    if echo "$COMMAND" | grep -qE 'git\s+stash'; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: git stash is prohibited — it leads to lost work in multi-session development. For pre-existing test failures: fix root cause if safe, otherwise state they look unrelated and move on. For dirty trees: use .gitignore or fix the root cause."}}'
        exit 0
    fi
fi

# ─── Rule 3: venv activation (shell state does not persist) ───
if [ "$TOOL_NAME" = "Bash" ]; then
    COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
    if echo "$COMMAND" | grep -qE 'source\s+\.venv/bin/activate'; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Shell state does not persist between Bash calls. Use .venv/bin/python directly or ./run_*.sh scripts for tests."}}'
        exit 0
    fi
fi


# ─── Rule 4: MCP Linear write tools in Lacrimosa conductor ───
# Block when running inside lacrimosa-conductor tmux session.
# Normal interactive sessions are unaffected.
if echo "$TOOL_NAME" | grep -qE '^mcp__linear-server__linear_(create_comment|create_issue|create_issues|create_project_with_issues|create_customer_need_from_attachment|bulk_update_issues|delete_issue|delete_issues|delete_comment|update_comment|resolve_comment|unresolve_comment)$'; then
    # Check if current process is inside a tmux session named lacrimosa-conductor
    TMUX_SESSION=""
    if [ -n "$TMUX" ]; then
        TMUX_SESSION=$(tmux display-message -p '#S' 2>/dev/null || true)
    fi
    if [ "$TMUX_SESSION" = "lacrimosa-conductor" ]; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: MCP Linear write tools post as the human operator. Use scripts/lacrimosa_linear.py (create_comment, update_issue_state, create_issue) to post as Lacrimosa. MCP tools are only for READS."}}'
        exit 0
    fi
fi

# No rule matched — allow
exit 0
