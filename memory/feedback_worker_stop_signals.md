---
name: Workers must respect issue comments as stop signals
description: Implementation workers must read all issue comments before starting work — abort if work is already done, not needed, or superseded
type: feedback
---

Implementation workers MUST read ALL issue tracker comments before starting work. If any comment indicates the work is already done, not needed, a duplicate, or superseded — the worker must abort immediately and report failure with reason "no implementation needed."

**Why:** Workers were continuing to implement features despite comments on the issue saying the work was already completed or no longer needed. This wasted compute and created noise PRs that had to be manually closed.

**How to apply:**
1. **Pre-dispatch gate**: Before dispatching a worker, scan all issue comments for stop signals (phrases like "already done", "not needed", "duplicate of", "superseded by", "closing", "won't fix")
2. **Worker startup**: Workers must read ALL comments on the issue as their first action before writing any code
3. **Abort on stop signal**: If any comment indicates the work is unnecessary, abort immediately with a structured failure reason
4. **Report back**: The conductor must handle abort reports by updating issue state and moving to the next item in the queue, not retrying
