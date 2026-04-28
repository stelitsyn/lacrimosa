---
name: All Lacrimosa dispatched agents must use worktree isolation
description: Never create branches on the main checkout — all Agent() dispatches must use isolation="worktree" to prevent parallel work corruption
type: feedback
---

ALL Lacrimosa dispatched agents (engineering, content, review, fix) MUST use `isolation="worktree"`. The main repo checkout MUST stay on `main` at all times.

**Why:** Engineering created branches directly on the main checkout. Content specialist inherited that branch, corrupting its own work. Both specialists + their agents shared the same `.git/index`, causing lock conflicts, lost changes, and state tracking file corruption when branch swaps changed engine scripts mid-execution.

**How to apply:**

1. **Every Agent() call that writes code** must include `isolation="worktree"`:
   - Dispatch agents (engineering implementation)
   - Review agents (code review)
   - Fix agents (bug fixes)
   - Content dispatch agents
   - Verification agents

2. **Merge operations** must use temp worktrees:
   - `git worktree add /tmp/lacrimosa/merge-{issue} {branch}`
   - Do rebase/merge in worktree, not main checkout
   - Cleanup after: `git worktree remove /tmp/lacrimosa/merge-{issue}`

3. **Main checkout rules**:
   - ALWAYS on `main` branch
   - Read-only operations only (reality check, git log, gh pr list)
   - Never `git checkout`, `git branch -b`, or `git switch`
   - If found on wrong branch, `git checkout main` before any work

4. **State tracking** should live OUTSIDE the repo — not affected by branch swaps. Engine scripts ARE in the repo — branch swaps change the code mid-execution. Worktree isolation prevents this: each agent has its own copy of the scripts.
