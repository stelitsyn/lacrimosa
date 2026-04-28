---
name: Specialist restart requires multi-signal verification
description: Never restart a specialist based on heartbeat alone — check tmux session, claude process, and pane activity before deciding
type: feedback
---

Never restart a specialist based solely on stale heartbeat. A specialist can have a stale heartbeat while actively working (e.g. stuck on permission prompt, long-running tool call, waiting for API response).

**Why:** Engineering specialist was actively running (claude process alive, "Running..." in pane, stuck on `.git/index.lock` permission prompt) but had a stale heartbeat. Restarting would have killed in-flight work and caused git lock issues.

**How to apply:** Before restarting any specialist, check ALL of these signals in order:

1. `tmux has-session -t {session}` — is the tmux session alive?
2. Check pane PID children: `pgrep -P {pane_pid}` — is a claude process running?
3. `tmux capture-pane -t {session} -p | tail -10` — is there recent activity? Look for:
   - "Running..." = actively executing a tool call, DO NOT restart
   - Permission prompt = stuck but alive, nudge or approve instead
   - Idle prompt with no /loop = needs re-trigger, not restart
   - Error messages = investigate before restart

**Restart decision matrix:**

| tmux alive | claude running | pane active | Action |
|------------|---------------|-------------|--------|
| No | -- | -- | Respawn tmux session + specialist |
| Yes | No | Idle prompt | Re-send `/lacrimosa-specialist {name}` |
| Yes | Yes | "Running..." | HEALTHY — do nothing |
| Yes | Yes | Permission prompt | Approve or nudge — do not restart |
| Yes | Yes | Error output | Investigate error, then decide |
| Yes | No | Error/crash | Kill session, respawn |

**Permission prompt handling:**
- Claude Code's `.git/` and `~/.claude/` sensitive file protection fires even with permissions bypassed
- Deploy a PreToolUse hook to auto-approve writes to known safe paths
- Existing sessions need restart to pick up hook changes — new sessions get it automatically
- Fallback: if a specialist is still stuck, send `Down Enter` via tmux (option 2: "always allow")
