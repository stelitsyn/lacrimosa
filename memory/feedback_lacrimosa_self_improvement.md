---
name: Lacrimosa must self-learn and self-improve autonomously
description: Conductor should detect issues, learn from them, and improve its own behavior without requiring human supervision
type: feedback
---

Lacrimosa conductor must actively learn and improve itself. Human supervision should NOT be necessary for operational issues.

**Why:** Lacrimosa was relying on human intervention for: ceremony quality (no-ops), restart decisions (false positives), permission prompt handling, and engine bug fixes. All of these should be self-detected and self-corrected.

**How to apply:**

1. **Self-detect ceremony quality**: After every ceremony, verify the output is non-trivial. If a ceremony produces zero actions (grooming 0 closed, standup empty, retro all-zero), immediately re-run with deeper analysis. Never accept a no-op ceremony.

2. **Self-detect specialist issues**: When a specialist has a stale heartbeat, check tmux pane FIRST. If stuck on permission prompt, auto-approve. If idle, re-trigger. If crashed, restart. Log the issue as a learning event.

3. **Self-detect engine bugs**: When a script crashes (dashboard, linear, state), catch the exception, log it as a learning event, and attempt an auto-fix or graceful degradation. Don't wait for human to notice.

4. **Self-improve prompts**: When a specialist fails 2+ times on the same type of task, create a learning event that refines the specialist's prompt for next dispatch.

5. **Commit fixes immediately**: When the conductor fixes an engine bug (state reader, dashboard, API integration), commit to main within the same cycle via worktree.

6. **Learning event format**: Every self-detected issue should create a learning event in state with:
   - What went wrong
   - Root cause
   - What was done to fix it
   - What should change to prevent recurrence

7. **No human escalation for operational issues**: Only escalate to human for: production deployment approval, billing/monetization changes, and trust tier decisions after reverts. Everything else (bugs, stalls, prompts, ceremonies) should be handled autonomously.
