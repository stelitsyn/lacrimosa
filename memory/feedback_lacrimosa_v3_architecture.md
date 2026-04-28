---
name: lacrimosa-v3-architecture
description: Lacrimosa v3 architecture decisions — long-lived tmux conductor, Agent Teams dispatch, mandatory verification, context hygiene
type: feedback
---

Lacrimosa v3 architecture decisions:

1. **Long-lived tmux session, not --print mode.** The conductor runs as `claude` with permissions bypassed inside `tmux new-session -d -s lacrimosa-conductor`. This enables task notifications from background agents, /loop cron cycles, and feedback loops. --print mode loses state and can't receive notifications.

**Why:** --print sessions exit after one pass, losing track of background agents. State wasn't updated, stall detection didn't work, verification was skipped.

**How to apply:** Watchdog spawns tmux session. `/lacrimosa start` sets up /loop for recurring conductor cycles. Background agents dispatch in worktrees with task notifications.

2. **Agent Teams (`/team-implement`) for ALL implementation work.** No bare agent dispatch. Teams have TDD, multi-reviewer QA, staging deploy, browser verification, self-reflection, and knowledge preservation built in.

**Why:** Bare agents skipped verification, browser testing, and staging deployment. Every PR merged without proof.

**How to apply:** Conductor dispatches `Agent(prompt="/team-implement {issue_number}", run_in_background=True)`. Never dispatches raw implementation agents.

3. **Mandatory staging + browser verification.** Implementation prompts include explicit verification requirements. Pre-merge gate checks PR body for verification evidence keywords. Missing evidence = reject and send back.

**Why:** Multiple PRs merged without any staging deployment or browser testing. Autonomous engine must prove correctness.

**How to apply:** `/verify-flows` for frontend, staging deploy + curl for backend. Evidence in PR body.

4. **Context hygiene.** Conductor never reads code or writes code directly. `/clear` between issue lifecycles. State database is source of truth. Agent results processed as summaries only.

**Why:** Long-lived sessions accumulate stale research, diffs, review findings that confuse subsequent work.

**How to apply:** After each issue lifecycle completes: persist state, then /clear. Next cycle reads state fresh.

5. **Persist state after EVERY mutation.** Session can die at any point. State must survive.

**Why:** Conductor completed work (PR merged to main) but state still showed "Identified" — state was never persisted.

**How to apply:** Every state change triggers immediate write to state database with updated last_poll timestamp.

6. **No self-throttling.** Rate limits handled by API. Conductor never idles itself based on usage percentages.

**Why:** Conductor sat idle at 84% usage (yellow threshold) with urgent work waiting. API enforces real limits.

**How to apply:** `throttle_level` always "green" in state. Config thresholds exist for dashboard display only.

7. **Active stall detection via output file polling.** Monitor output file mtime every 60s. >10 min stale = TaskStop + retry.

**Why:** Reviewer agent stalled for 18 min undetected. Passive notification-only model misses stuck agents.

**How to apply:** `monitor_active_workers()` runs FIRST every conductor cycle. Persist agent_task_id and output_file in state.
