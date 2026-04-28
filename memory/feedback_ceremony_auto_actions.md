---
name: ALL ceremonies must auto-execute actions
description: Every Lacrimosa ceremony must automatically execute its identified actions — not just analyze and report findings
type: feedback
---

ALL Lacrimosa ceremonies must automatically execute their identified actions, not just analyze and report. Ceremonies are REAL WORK.

**Why:** Ceremonies were running as analysis-only no-ops. Planning didn't dispatch, grooming didn't close/promote/assign, retro didn't create learnings, standup didn't post. Every ceremony must DO the work, not just describe it.

**How to apply:**

**Planning** — must actually:
1. Query Todo issues in autonomous domains
2. Score and rank by priority + config bonuses
3. Check trust tier capacity (concurrent, daily cap)
4. Select top N that fit capacity
5. **Dispatch selected issues to engineering specialist** (or queue for dispatch)
6. Post plan to issue tracker with selected issue IDs

**Backlog Grooming** — must actually:
1. Promote ALL P0 issues from Backlog to Todo (with comment)
2. Close ALL duplicates (with comment linking kept issue)
3. Assign projects to ALL unassigned issues via routing rules
4. Archive truly stale issues (no activity >48h, low priority)
5. Decompose oversized issues into sub-issues
6. Post summary of ALL actions taken

**Retrospective** — must actually:
1. Compute real metrics from state + issue tracker (completed, reverts, review iterations)
2. Compare to previous retro snapshot
3. Create learning events for negative patterns (high revert rate, repeated failures)
4. Post retro with trend analysis

**Standup** — must actually:
1. Query real In Progress / In Review from issue tracker
2. Include today's completed with PR numbers
3. Include planning queue
4. Include grooming action summary
5. Post to issue tracker
