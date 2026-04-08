#!/bin/bash
# security-review-precommit.sh — Block git commits without security review.
# Scans staged changes for common security issues before allowing commit.

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Only intercept git commit commands
[ "$TOOL_NAME" = "Bash" ] || exit 0
echo "$COMMAND" | grep -q "git commit" || exit 0

# Check staged diff for common security issues
STAGED=$(git diff --cached --diff-filter=ACMR 2>/dev/null || true)
[ -z "$STAGED" ] && exit 0

ISSUES=""

# Check for hardcoded secrets patterns
if echo "$STAGED" | grep -qiE '(password|secret|api_key|token)\s*=\s*["\x27][^"\x27]{8,}'; then
    ISSUES="$ISSUES\n- Possible hardcoded secret detected"
fi

# Check for private keys
if echo "$STAGED" | grep -q 'PRIVATE KEY'; then
    ISSUES="$ISSUES\n- Private key detected in staged changes"
fi

# Check for .env files being committed
STAGED_FILES=$(git diff --cached --name-only 2>/dev/null || true)
if echo "$STAGED_FILES" | grep -qE '\.env$|\.env\.local$|credentials\.json$'; then
    ISSUES="$ISSUES\n- Sensitive file (.env/credentials) being committed"
fi

if [ -n "$ISSUES" ]; then
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"Security review found potential issues:$ISSUES\n\nReview and confirm to proceed.\"}}"
    exit 0
fi

exit 0
