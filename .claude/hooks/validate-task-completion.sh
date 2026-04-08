#!/usr/bin/env bash
# Hook: TaskCompleted — role-aware validation before allowing task completion
#
# Exit codes:
#   0 = validation passed, allow completion
#   2 = validation failed, send feedback and block completion
#
# Roles are split into two tiers:
#   - Implementation roles (backend-dev, frontend-dev, qa, etc.): must pass test/lint checks
#   - Non-implementation roles (architect, ba, cto, designer, etc.): pass without code checks

TEAMMATE="${CLAUDE_TEAMMATE_NAME:-}"
TEAM="${CLAUDE_TEAM_NAME:-}"
TASK_SUBJECT="${CLAUDE_TASK_SUBJECT:-}"

# --- Guard: skip validation outside agent team context ---
if [ -z "$TEAM" ] || [ "$TEAM" = "unknown" ]; then
    exit 0
fi

# --- Determine role tier ---
# Implementation roles: must have tests passing and clean lint
IMPL_ROLES="backend-dev frontend-dev ios-dev qa manual-qa cicd devops infra harness-engineer migration"

IS_IMPL_ROLE=false
for role in $IMPL_ROLES; do
    case "$TEAMMATE" in
        ${role}|${role}-*)
            IS_IMPL_ROLE=true
            break
            ;;
    esac
done

# Non-implementation roles (architect, ba, cto, ceo, designer, marketing,
# seo, legal, finance, security-officer, docs, etc.) pass without code checks.
# Their deliverables are design docs, contracts, and review feedback — not code.
if [ "$IS_IMPL_ROLE" = "false" ]; then
    exit 0
fi

# --- Contract directory check (soft — only block if team uses contracts) ---
CONTRACT_DIR="$HOME/.claude/teams/$TEAM/contract"
if [ -d "$CONTRACT_DIR" ]; then
    # Design-phase agents must have their specific contract file
    declare -A AGENT_CONTRACTS
    AGENT_CONTRACTS[ba]="01-requirements.md"
    AGENT_CONTRACTS[architect]="03-api-contracts.md 05-file-ownership.md 06-naming-conventions.md"
    AGENT_CONTRACTS[db-architect]="04-database-schema.md"
    AGENT_CONTRACTS[security-officer]="07-security-requirements.md"
    AGENT_CONTRACTS[designer]="08-ui-specifications.md"
    AGENT_CONTRACTS[marketing]="09-ui-copy.md"
    AGENT_CONTRACTS[seo]="10-seo-requirements.md"
    AGENT_CONTRACTS[legal]="11-legal-compliance.md"

    REQUIRED_FILES="${AGENT_CONTRACTS[$TEAMMATE]:-}"

    if [ -n "$REQUIRED_FILES" ]; then
        MISSING=""
        for FILE in $REQUIRED_FILES; do
            FILEPATH="$CONTRACT_DIR/$FILE"
            if [ ! -f "$FILEPATH" ]; then
                MISSING="$MISSING $FILE (not found)"
            elif [ ! -s "$FILEPATH" ]; then
                MISSING="$MISSING $FILE (empty)"
            fi
        done

        if [ -n "$MISSING" ]; then
            cat <<EOF
[$TEAMMATE] Task completion blocked: required contract file(s) missing or empty:$MISSING
EOF
            exit 2
        fi
    fi
fi

# --- All checks passed for implementation role ---
# The actual test/lint enforcement is done by the agent itself (TDD workflow)
# and pre-commit hooks. This hook just ensures the role tier is correct.
exit 0
