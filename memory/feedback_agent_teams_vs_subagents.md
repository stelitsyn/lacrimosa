---
name: agent-teams-vs-subagents
description: When user asks for "agentic team" or "agent team", use TeamCreate (real teams) not background subagents
type: feedback
---

When user says "spawn agentic team", "agentic team", "agent team", or "real team" — ALWAYS use TeamCreate + shared task list + Agent with team_name parameter. NEVER use multiple background subagents (Agent with run_in_background=true) as a substitute for a coordinated team.

**Exception:** A single Agent dispatched with `run_in_background=True` that internally creates a real team (e.g., via `/team-implement`) is acceptable — the team coordination happens inside that agent. The prohibition is against using multiple isolated background subagents as a replacement for `TeamCreate`.

**Why:** Background subagents are isolated workers — no peer communication, no shared task list, no team coordination. Agent Teams (via TeamCreate) provide shared TaskList, SendMessage peer-to-peer communication, proper team lifecycle with shutdown, and structured quality gates. Background subagents were spawned instead of a real team, resulting in uncoordinated work.

**How to apply:** When the context calls for "team" or "agentic team":
1. Use `TeamCreate` to create the team
2. Use `TaskCreate` to build a shared task list with `addBlockedBy` dependencies
3. Spawn teammates with `Agent` tool using `team_name` parameter (NOT `run_in_background`)
4. Teammates coordinate via `SendMessage` and shared `TaskList`
5. PM (spawning agent) monitors progress and spawns additional teammates as dependencies resolve
