---
name: daily-cap-counts-parent-issues
description: Lacrimosa daily cap counts parent issues, not sub-issues — decomposed work counts as one toward the limit
type: feedback
---

Sub-issues of a decomposed parent count as ONE issue toward the daily cap, not individually.

**Why:** Daily cap was being exceeded because sub-issues were counted separately. The correct behavior: a parent issue decomposed into 4 sub-issues = 1 issue toward the daily cap, not 4.

**How to apply:** When checking daily caps before dispatching, count distinct parent issues (or standalone issues with no parent). All sub-issues sharing a `parent` field count as one. Track via `parent_issues_dispatched` in the daily counters state (managed by `StateManager`).
