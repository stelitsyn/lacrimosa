# Trust & Learning System

## Trust Learning Loop

Every trust-affecting event triggers analysis + adjustable learning.

### Trigger Events

| Event | Severity | Action |
|-------|----------|--------|
| PR review rejected | Medium | Analyze patterns, propose prompt refinement |
| Review iteration 2+ | Medium | Track first-pass rate |
| PR reverted | Critical | Drop trust tier, create learning issue |
| Worker escalated (3 fails) | High | Root cause analysis |
| Trust promoted | Positive | Log what's working |
| Trust contracted | High | Analyze quality drop |

### Learning Process

1. **Analyze** root cause → generalizable pattern
2. **Post** Linear comment on original issue
3. **Auto-apply** change immediately (file edit)
4. **Create** Linear issue in "In Review" state (not Todo — already applied)
5. **Track** in append-only ledger (`~/.claude/lacrimosa/learnings.json`)
6. **Monitor** for approval/revert via Linear issue status

### Adjustment Types

| Type | Target | Example |
|------|--------|---------|
| prompt_refinement | Agent prompts | "Always check localStorage availability" |
| guardrail_addition | Config safety rules | "Never modify auth without security review" |
| classification_fix | Lifecycle routing | "Issues with 'drop-off' need research first" |
| scope_calibration | Trust tier limits | "Reduce max_files_per_pr at tier 0" |

### Auto-Apply with Revert

Learnings apply immediately. Revert flow:
- Human closes Linear issue as **Done** → learning stays (approved)
- Human closes as **Cancelled** → auto-revert + flag influenced PRs

Ledger entry: `{id, timestamp, event_type, file_changed, old_value, new_value, status, influenced_prs}`

### PR Influence Tracking

When implementation creates a PR, conductor records which learnings were active.
If learning reverted → flagged PRs may need attention.

### Review Rejection Learning

When same pattern appears across 2+ PRs → systemic prompt gap → high severity adjustment.
Single occurrence → monitor only.
