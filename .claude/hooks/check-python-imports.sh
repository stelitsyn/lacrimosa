#!/bin/bash
# check-python-imports.sh — Auto-fix missing imports after Python file edits.
# Runs autoimport (if available) then ruff F821 to catch undefined names.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // ""')

# Only check Python files
case "$FILE_PATH" in
    *.py) ;;
    *) exit 0 ;;
esac

# Skip if file doesn't exist (deleted)
[ -f "$FILE_PATH" ] || exit 0

# Try autoimport if available
if command -v autoimport &>/dev/null; then
    autoimport "$FILE_PATH" 2>/dev/null || true
fi

# Check for undefined names with ruff
if command -v ruff &>/dev/null; then
    ERRORS=$(ruff check --select F821 --no-fix "$FILE_PATH" 2>/dev/null || true)
    if [ -n "$ERRORS" ]; then
        echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"message\":\"Warning: Undefined names found:\\n$ERRORS\"}}"
    fi
fi

exit 0
