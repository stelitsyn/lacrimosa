#!/usr/bin/env bash
# Hook: TeammateIdle — nudge idle teammates toward tasks matching their expertise
#
# Exit codes:
#   0 = allow idle (no feedback) — teammate has no actionable tasks
#   2 = send feedback message and keep working — unblocked tasks exist
#
# Fixed: Previously always returned exit 2, causing infinite idle loops
# for teammates with no remaining work. Now checks the task list first.

TEAMMATE="${CLAUDE_TEAMMATE_NAME:-unknown}"
TEAM="${CLAUDE_TEAM_NAME:-unknown}"

# --- Guard: skip if no team context ---
if [ -z "$TEAM" ] || [ "$TEAM" = "unknown" ]; then
    exit 0
fi

# --- Check if teammate has actionable tasks ---
# Look at task files in the team's task directory
TASK_DIR="$HOME/.claude/tasks/$TEAM"
HAS_PENDING_WORK=false

if [ -d "$TASK_DIR" ]; then
    # Check for pending tasks that are unblocked and either unowned or owned by this teammate
    for task_file in "$TASK_DIR"/*.json; do
        [ -f "$task_file" ] || continue
        STATUS=$(python3 -c "import json; d=json.load(open('$task_file')); print(d.get('status',''))" 2>/dev/null)
        OWNER=$(python3 -c "import json; d=json.load(open('$task_file')); print(d.get('owner',''))" 2>/dev/null)
        BLOCKED=$(python3 -c "import json; d=json.load(open('$task_file')); b=d.get('blockedBy',[]); print('yes' if [x for x in b if x] else 'no')" 2>/dev/null)

        # Task is actionable if: pending + unblocked + (unowned or owned by this teammate)
        if [ "$STATUS" = "pending" ] && [ "$BLOCKED" = "no" ]; then
            if [ -z "$OWNER" ] || [ "$OWNER" = "$TEAMMATE" ]; then
                HAS_PENDING_WORK=true
                break
            fi
        fi
        # Also check in_progress tasks owned by this teammate (reminder to continue)
        if [ "$STATUS" = "in_progress" ] && [ "$OWNER" = "$TEAMMATE" ]; then
            HAS_PENDING_WORK=true
            break
        fi
    done
fi

# --- If no actionable tasks, allow idle gracefully ---
if [ "$HAS_PENDING_WORK" = "false" ]; then
    exit 0
fi

# --- Nudge with role-specific guidance ---
case "$TEAMMATE" in
  ba|ba-*)
    FOCUS="requirements, acceptance criteria, behavioral scenarios"
    TIERS="T0 (requirements gathering) and T3 (acceptance testing)"
    ;;
  architect|architect-*)
    FOCUS="API contracts, file ownership, naming conventions"
    TIERS="T1 (design) and T3 (compliance review)"
    ;;
  db-architect|db-architect-*)
    FOCUS="database schema, migrations, indexes"
    TIERS="T1 (schema design) and T3 (DB review)"
    ;;
  backend-dev|backend-dev-*)
    FOCUS="backend implementation, API endpoints, services"
    TIERS="T2 (implementation) and T3 (fix review issues)"
    ;;
  frontend-dev|frontend-dev-*)
    FOCUS="frontend components, pages, UI implementation"
    TIERS="T2 (implementation) and T3 (fix review issues)"
    ;;
  ios-dev|ios-dev-*)
    FOCUS="iOS screens, SwiftUI views, mobile implementation"
    TIERS="T2 (implementation) and T3 (fix review issues)"
    ;;
  qa|qa-*)
    FOCUS="test writing, test execution, bug filing"
    TIERS="T2 (write tests from contracts) and T3 (run tests, file bugs)"
    ;;
  manual-qa)
    FOCUS="exploratory testing, UX edge cases, behavioral scenarios"
    TIERS="T3 (manual testing) and T4 (staging smoke test)"
    ;;
  security-officer|security|security-*)
    FOCUS="threat modeling, OWASP review, vulnerability scanning"
    TIERS="T0 (threat model), T1 (contract review), T3 (code review), T4 (staging verify)"
    ;;
  cto)
    FOCUS="technical strategy, feasibility review, code review"
    TIERS="T0 (feasibility) and T3 (technical review)"
    ;;
  ceo)
    FOCUS="business alignment, go/no-go, final approval"
    TIERS="T0 (business validation) and T4 (ship approval)"
    ;;
  designer|designer-*)
    FOCUS="UI specifications, component design, accessibility"
    TIERS="T1 (UI specs) and T3 (UI review)"
    ;;
  cicd|devops)
    FOCUS="CI/CD pipelines, deploy scripts, staging deployment"
    TIERS="T2 (deploy configs) and T4 (staging deploy + verification)"
    ;;
  infra|infrastructure)
    FOCUS="Terraform, GCP resources, Docker, infrastructure configs"
    TIERS="T2 (infra configs) and T4 (infra verification)"
    ;;
  marketing)
    FOCUS="UI copy, positioning, marketing text"
    TIERS="T1 (write copy) and T3 (verify copy in UI)"
    ;;
  seo)
    FOCUS="meta tags, schema markup, SEO requirements"
    TIERS="T1 (SEO specs) and T3 (SEO validation)"
    ;;
  legal)
    FOCUS="compliance, privacy, data protection"
    TIERS="T0 (compliance requirements) and T3 (compliance verification)"
    ;;
  finance)
    FOCUS="cost analysis, pricing impact, ROI"
    TIERS="T0 (financial assessment)"
    ;;
  harness-engineer)
    FOCUS="scenario generation, coverage matrix, harness testing"
    TIERS="T2 (generate scenarios) and T3 (run harness)"
    ;;
  migration|migration-*)
    FOCUS="Alembic migrations, zero-downtime strategy, rollback plans"
    TIERS="T1 (migration planning) and T2 (migration scripts)"
    ;;
  docs|documentation)
    FOCUS="API docs, README, changelogs, internal comms"
    TIERS="T3 (documentation review and updates)"
    ;;
  *)
    FOCUS="your assigned domain"
    TIERS="pending tiers"
    ;;
esac

cat <<EOF
[$TEAMMATE] You have gone idle but there is pending work. Your expertise: $FOCUS.
Check TaskList for unblocked pending tasks in $TIERS that match your role.
Claim the next task under your responsibility. If all your tasks are blocked, message PM with your status.
EOF

exit 2
