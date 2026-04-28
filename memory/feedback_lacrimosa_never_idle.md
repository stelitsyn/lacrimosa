---
name: Lacrimosa must never idle when work exists — but must accurately detect idleness
description: Conductor must use 4-signal check (status bar, state workers, heartbeat, cadence) to determine if a specialist is truly idle vs between cycles
type: feedback
---

Lacrimosa must never idle when there's work to do — BUT must accurately distinguish "idle" from "between cycles" or "waiting for agent."

**Why:** Conductor mistakenly re-triggered all 3 specialists that were actually working:
- Discovery: between sense cycles (normal cadence wait)
- Engineering: monitoring a running fix agent
- Content: waiting for background /team-implement agent
`>` at prompt does NOT mean idle — it means the specialist completed its cycle and is waiting for the next /loop or agent notification.

**4-signal state check (ALL required before deciding to re-trigger):**

| Signal | How to check | "Working" if |
|--------|-------------|-------------|
| 1. Status bar agents | `tmux capture-pane` for "local agent" in status bar line | "N local agent" present |
| 2. State workers | Check state for active workers/dispatches | Active workers exist |
| 3. Heartbeat freshness | Check specialist health last_heartbeat | Within max_silence window |
| 4. Cadence timing | Compare last sense/dispatch time vs config cadence | Next cycle not yet overdue |

**Decision matrix:**

| Agents running | Workers in state | Heartbeat fresh | Cadence due | Verdict |
|----------------|--------------|-----------------|-------------|---------|
| Yes | * | * | * | WORKING — do not touch |
| No | Yes | * | * | WAITING for agent completion — do not touch |
| No | No | Yes | No | BETWEEN CYCLES — normal, do not touch |
| No | No | Yes | Yes | OVERDUE — re-trigger |
| No | No | Stale | * | Check pane for crash/error, then re-trigger if needed |

**Only re-trigger when:** No agents + no workers + heartbeat stale or cadence overdue + pane shows idle prompt.
