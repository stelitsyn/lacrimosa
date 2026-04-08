---
name: workflow-complete
description: Signal workflow completion and close GitHub issue with structured summary
---

# Workflow Complete

Triggers the `github-issue-manager` hook to close the associated GitHub issue with a structured resolution summary.

## When to Use

Called automatically at the end of `/implement` or `/bugfix` workflows (Phase 8) after all verification passes.

## Required Arguments

Pass these as skill args:

```
/workflow-complete issue_number=123 root_cause="..." fix="..." tests="..."
```

| Argument | Description |
|----------|-------------|
| `issue_number` | GitHub issue number (from `GITHUB_ISSUE` in task.md header) |
| `root_cause` | Brief description of root cause (for bugfix) or "Feature implementation" |
| `fix` | Summary of the fix/implementation changes |
| `tests` | List of tests added (e.g., "15 unit tests, 3 integration tests") |

## Example

```
/workflow-complete issue_number=421 root_cause="Missing null check in auth handler" fix="Added null validation and early return" tests="5 unit tests for edge cases"
```

## What Happens

1. Hook receives the skill invocation
2. Constructs structured close comment:
   - Root cause
   - Fix description
   - Tests added
3. Closes the GitHub issue with `gh issue close`

## Integration

The `/implement` and `/bugfix` skills should call this at Phase 8:

```markdown
## Phase 8: Knowledge Preservation

After all verifications pass:
1. Update schemas if behavior changed
2. Update KI artifacts
3. **Call `/workflow-complete`** with issue summary
```
