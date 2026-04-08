---
name: completion-check
description: Mandatory completion check - Self-review and verification before completing any task. MUST be called before finishing ANY task.
---

# /completion-check - Mandatory Completion Hook

**CRITICAL: This hook MUST be called before finishing ANY task.** It ensures work quality by reviewing against initial requirements and catching discrepancies before completion.

## When to Trigger

This hook is automatically required:

- Before calling `notify_user` to report task completion
- Before ending any implementation, bugfix, or feature workflow
- Before transitioning out of VERIFICATION mode

## Hook Execution Steps

### Step 1: Capture Initial Context

Before ANY work begins, document the original user request:

- Save the exact user question/requirement
- Note any constraints or specific expectations mentioned
- Record the initial state of affected files

### Step 2: Code Revision Checklist

After implementation, systematically verify:

```
[ ] All modified files compile/build without errors
[ ] No unintended side effects in related code
[ ] Code follows project conventions and patterns
[ ] No debug statements, console.logs, or TODOs left behind
[ ] All new functions/methods have proper error handling
[ ] Edge cases are handled appropriately
```

### Step 3: Requirements Alignment Check

Compare completed work against initial request:

1. **Extract Initial Requirements**: Re-read the original user message
2. **List Deliverables**: Enumerate what was actually implemented
3. **Gap Analysis**: Identify any of these discrepancy types:
   - **Missing Features**: Requested functionality not implemented
   - **Partial Implementation**: Features incomplete or lacking edge cases
   - **Scope Creep**: Unasked-for changes that may cause issues
   - **Behavioral Drift**: Implementation doesn't match described behavior
   - **Test Coverage Gap**: Missing tests for critical paths

### Step 4: Decision Gate

**IF discrepancies found:**

```
1. Document each discrepancy clearly:
   - What was requested
   - What was delivered
   - The gap between them

2. Determine severity:
   - CRITICAL: Core functionality missing/broken
   - MAJOR: Significant feature gaps
   - MINOR: Polish/enhancement opportunities

3. For CRITICAL/MAJOR issues:
   - DO NOT proceed to completion
   - Return to the original workflow (e.g., /implement, /bugfix)
   - Pass the discrepancy list as additional context
   - Re-execute with focus on fixing gaps

4. For MINOR issues:
   - Document in walkthrough.md
   - Proceed to completion with note to user
```

**IF no discrepancies (or only MINOR):**

```
1. Proceed to Step 5 (Finalization)
```

### Step 4.5: Staging/Browser Verification (if applicable)

> **Skip this step for**: Agent Team workflows (they have separate QA via `20-manual-qa-instructions.md`), docs-only changes, test-only changes, and CI/config-only changes.

**If the change affects runtime behavior (UI, API, business logic):**

1. **Deploy to staging**: `./infra/deploy-staging.sh`
2. **Verify health**: curl staging US + EU health endpoints
3. **Browser verification** (for UI/frontend changes):
   - Use `mcp__claude-in-chrome__*` tools or Playwright to open staging
   - Login with staging QA account (credentials: `{credentials_file}`)
   - Navigate to the affected flow, verify the fix/feature works
   - Take screenshots as proof
4. **API verification** (for backend changes):
   - curl/httpie against staging endpoints to verify behavior
5. **Generate report**: Create `output/<task-name-YYYYMMDD>/REPORT_WITH_SCREENSHOTS.md`
   - Follow structure from `workflow/staging-verification.md`
   - Include coverage matrix, screenshots, findings with severity
6. **Gate**: If Critical/High findings exist → return to Step 3, do NOT proceed

### Step 5: Create PR with Proofs

Only reach this step when requirements and staging verification are satisfied:

1. Update `task.md` - mark all items as `[x]` completed
2. Create/update `walkthrough.md` with:
   - Summary of changes made
   - Any MINOR discrepancies noted (if applicable)
   - Verification evidence (test results, screenshots)
3. Create PR — link `REPORT_WITH_SCREENSHOTS.md` and screenshots in PR body as proof

### Step 6: PR Review Loop

> **Not applicable to Agent Team workflows** — they have separate review processes.

```
Invoke pr-review-toolkit:review-pr → Fix issues → Re-review → Repeat until clean → Merge
```

1. Invoke `pr-review-toolkit:review-pr` on the PR
2. If issues found:
   - Fix all reported issues in code
   - Commit fixes (new commit, don't amend)
   - Push to the PR branch
   - Re-invoke `pr-review-toolkit:review-pr`
   - Repeat until **zero issues** remain
3. Once review is clean → merge the PR (`gh pr merge --squash`)
4. Call `notify_user` with completion report + PR URL

## Example Usage

```
# Agent completes implementation work...

# Before finishing:
## /completion-check Hook Execution

### Initial Requirements:
"Add timestamp display to chat messages"

### Deliverables Implemented:
- [x] Added timestamp to Message interface
- [x] Created formatTimestamp utility
- [x] Updated MessageBubble component
- [x] Added timestamps to live details view

### Gap Analysis:
- All requested features implemented
- Timestamps display correctly in both chat and transcription
- Format matches project conventions

### Decision: NO DISCREPANCIES - Proceeding to completion
```

## Integration with Other Workflows

The `/completion-check` hook is called at the end of:

- `/implement` - After Phase 7 (Cleanup)
- `/bugfix` - After verification passes
- `/bugfix-extensive-tests` - After test suite generation
- Any ad-hoc implementation task

## Anti-Patterns to Avoid

- Skipping the hook "because the task was simple"
- Marking items complete without actual verification
- Ignoring MAJOR discrepancies to finish faster
- Not re-reading the original user request
- Assuming requirements instead of checking
