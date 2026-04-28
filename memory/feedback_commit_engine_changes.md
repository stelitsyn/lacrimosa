---
name: Commit Lacrimosa engine changes to main immediately
description: Infrastructure/engine fixes must be committed to main right away to survive parallel agent branch work
type: feedback
---

Any changes to Lacrimosa engine files (scripts/lacrimosa_*.py, state schema, conductor logic) must be committed to main immediately — not left as uncommitted changes.

**Why:** Parallel agents work on feature branches. Uncommitted changes on those branches get lost when agents do git checkout/reset. Engine fixes are cross-cutting infrastructure, not feature-specific.

**How to apply:**
1. After fixing any engine file, commit to main within the same cycle
2. If currently on a feature branch: use `git worktree add /tmp/lacrimosa-main-commit main`, copy files, commit, push, remove worktree
3. Never leave engine fixes as unstaged changes — they WILL be lost
4. Same applies to: conductor config, ceremony logic, dashboard code
