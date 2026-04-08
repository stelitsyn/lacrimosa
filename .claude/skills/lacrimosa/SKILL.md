---
name: lacrimosa
description: |
  Autonomous intelligence + engineering engine for your product. Specialist architecture:
  Conductor (health-checks, ceremonies, dashboard, rate limits) orchestrates 7 specialists:
  Discovery (SENSE → VALIDATE → issue creation), Engineer-Triage (reality check, triage, scoring),
  Engineer-Implement (dispatch workers, monitor), Engineer-Review (PR review, verdicts),
  Engineer-Merge (merge queue, rebase), Sentinel (production monitoring, alerting),
  Content (SEO content creation). Each runs in its own tmux session with independent context.
  All loops self-improve via learnings. Production deploy is the only human gate.
  Subcommands: start, stop, status, pause, resume, trust, sense, discover, learnings, dashboard.
---

# Lacrimosa — Autonomous Intelligence & Engineering Engine

> **Specialist architecture: conductor + discovery + engineer-triage + engineer-implement + engineer-review + engineer-merge + sentinel + content — 24/7.**
> Each specialist runs in its own tmux session. State shared via SQLite (WAL mode). Human gate: production deployment only.

## Module Index

| Module | Contents | Load When |
|--------|----------|-----------|
| `specialists/conductor.md` | Health-check specialists, ceremonies, dashboard, rate limits, learning events | `/lacrimosa start` |
| `specialists/discovery.md` | SENSE + VALIDATE: sensors, signal validation, issue creation | `/lacrimosa-specialist discovery` |
| `specialists/engineer-triage.md` | Reality check, steering, triage, scoring | `/lacrimosa-specialist engineer-triage` |
| `specialists/engineer-implement.md` | Dispatch workers, monitor, fix review feedback | `/lacrimosa-specialist engineer-implement` |
| `specialists/engineer-review.md` | PR review only, verdict posting | `/lacrimosa-specialist engineer-review` |
| `specialists/engineer-merge.md` | Merge queue, rebase, verification | `/lacrimosa-specialist engineer-merge` |
| `specialists/sentinel.md` | Production monitoring, fast alerting, issue creation | `/lacrimosa-specialist sentinel` |
| `specialists/content.md` | SEO content creation: query issues, dispatch via /team-implement | `/lacrimosa-specialist content` |
| `display.md` | Output templates for status/trust/discover/learnings/dashboard + stop/pause/resume/sense | Light subcommands |
| `trust-learning.md` | Trust events, learning process, auto-apply/revert, PR influence tracking | On trust-affecting events |

---

## Subcommand Routing

| Input | Action | Module |
|-------|--------|--------|
| `/lacrimosa` or `/lacrimosa start` | Start conductor + spawn specialists | Read: specialists/conductor.md |
| `/lacrimosa-specialist {name}` | Start a specialist session | Read config → Read: specialists/{name}.md |
| `/lacrimosa stop` | Graceful shutdown | Read: display |
| `/lacrimosa status` | Show state + counters | Read: display |
| `/lacrimosa pause` / `resume` | Pause/resume dispatch | Read: display |
| `/lacrimosa trust` | Trust scores per domain | Read: display |
| `/lacrimosa sense` | Immediate sense cycle | Read: display + specialists/discovery.md |
| `/lacrimosa discover` | Pending/validated signals | Read: display |
| `/lacrimosa learnings` | Discovery + engineering pipeline learnings | Read: display |
| `/lacrimosa dashboard` | Start dashboard HTTP server | Read: display |

**For light subcommands (status/trust/discover/learnings/dashboard/stop/pause/resume):**
Only `Read("~/.claude/skills/lacrimosa/display.md")` — do NOT load specialist modules.

---

## STEP 0: Load State

```python
STATE_FILE = Path.home() / ".claude" / "lacrimosa" / "state.db"
CONFIG_FILE = Path.home() / ".claude" / "lacrimosa" / "config.yaml"
```

**State: SQLite database** at `~/.claude/lacrimosa/state.db` (WAL mode)

Tables: `state` (key-value), `specialists` (health), `learning_events` (queue), `merge_queue` (dependency graph), `review_cycles` (feedback loop)

Access via `scripts.lacrimosa_state_sqlite.StateManager`.

---

## `/lacrimosa start` — Conductor Loop

### Step 1: Initialize

1. Open `state.db` via `StateManager` — restore or initialize
2. Read `config.yaml` — domain guardrails, concurrency limits, trust tiers, discovery cadences
3. Set `system_state = "Running"`, record PID
4. **Preserve `session_mode`** — do NOT override if already `"daemon"` (watchdog sets this)
5. Write state immediately

### Step 2: Load Modules

```python
# Load conductor specialist (the only module the conductor session needs)
Read("~/.claude/skills/lacrimosa/specialists/conductor.md")
```

### Step 3: Execution Model

```
Watchdog (launchd) → tmux "lacrimosa-conductor" → claude --dangerously-skip-permissions
  ├── /lacrimosa start → reads specialists/conductor.md, runs first cycle
  ├── /loop 5m conductor-cycle → fires every 5 min
  ├── Spawns specialist tmux sessions (discovery, engineer-triage, engineer-implement, engineer-review, engineer-merge, sentinel, content, clo, cfo, coo)
  ├── Health-checks specialists every cycle
  └── Watchdog checks conductor health every 5 min
```

**PERSIST STATE RULE:** After EVERY state mutation, write to state.db immediately via StateManager.

**SPECIALIST CONTEXT: `-p` flag (plan mode)** — Specialists that use `claude -p` in a shell
loop get a fresh context window each cycle, preventing context bloat. This is the key
architectural pattern that allows Lacrimosa to run 24/7 without degradation. See
`specialists/conductor.md` for the spawn pattern.

### Step 4: Setup /loop

```python
run_conductor_cycle()  # First cycle immediately

Skill("/loop", args="5m Execute one conductor cycle. "
      "Health-check all specialist tmux sessions. "
      "Run overdue ceremonies. Process learning events. "
      "Update rate limits + persist state.")
```

### Context Hygiene — MANDATORY

1. **Context managed by loop cadence.** State persists in state.db. `/clear` is deferred — do not attempt it. Context compaction handles long sessions.
2. **NEVER run `git checkout`, `git pull`, or any git commands.** Conductor doesn't touch git. Implementation happens in specialist worktrees.
3. **All implementation in SPECIALIST SESSIONS.** Conductor never reads/writes code.
4. **Minimize inline processing.** Agent results: "PASS/FAIL" → update state → move on.
5. **state.db is source of truth**, not conversation context.

**Context budget per cycle:** <15KB (state ~2KB, Linear queries ~5KB, decisions ~1KB, results ~2KB each).

### Conductor Cycle

Each cycle runs the conductor's lightweight loop from `specialists/conductor.md`:

```
1: Health-check all specialist tmux sessions (discovery, engineer-triage, engineer-implement, engineer-review, engineer-merge, sentinel, content, clo, cfo, coo)
2: Restart any dead/stalled specialists
3: Overdue ceremonies (sprint planning, standup, grooming, retro, weekly)
4: Update Linear dashboard document
5: Process learning events queue from state.db
6: Update rate limits
7: Persist state
```

Domain work (discovery, triage, dispatch, review, merge, content) runs in specialist sessions.

---

## Safety Rules

### Linear API
0b. **NEVER batch multiple `create_comment` calls for different issues in one response** — the LLM cross-wires issueIds between parallel tool calls. Process one issue at a time: lookup → read → analyze → comment → next. Self-check: comment body must mention the same {issue_prefix}-XXX as the target issueId.

### Engineering
1. NEVER deploy to production — only merge to main
2. NEVER modify `approval_required` domain issues beyond creating as Backlog
3. NEVER exceed trust tier limits (concurrent, daily cap, files/PR)
4. Reality check before dispatch — verify Linear + git + GitHub every cycle
5. Pre-dispatch gate per issue — skip if already done/merged/has-open-PR
6. Stall detection: 10 min no output → terminate
7. Human escalation: 3 retries → escalate
8. Trust decay: PR reverted → -1 tier

### Discovery
9. All validated signals → Linear issue (no daily cap; routing determines priority/state)
10. Deduplication mandatory — search before create
11. Borderline scores (6.0-7.0) → Backlog regardless of domain
12. External sources must be public
13. External crawl cap: max 50/day
14. Evidence chain required: signal → validation → research

## Error Handling

| Scenario | Action |
|----------|--------|
| Worker crashes/stalls | Retry with backoff (max 3) → escalate |
| PR review fails 3x | Escalate to human |
| Git conflict on merge | Rebase, retry once |
| Staging deploy fails | Auto-deploy recovery, retry once |
| Linear API down | Skip updates, retry next cycle |
| Daily cap reached | Stop dispatching, monitor active |
| Conductor crash | Watchdog restarts, state from state.db |
| Firecrawl unavailable | Fallback: Cloudflare → WebSearch → skip |
| Sensor/research fails | Log, skip, continue others |

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│  WATCHDOG (launchd) → checks conductor health every 5m                     │
├────────────────────────────────────────────────────────────────────────────┤
│  CONDUCTOR (tmux: lacrimosa-conductor)                                      │
│    Health-check specialists, ceremonies, dashboard,                         │
│    rate limits, learning events, state.db (WAL)                             │
├──────────┬────────────┬──────────────┬─────────────┬───────────┬───────────┤
│ DISCOVERY│  ENG-TRIAGE│ ENG-IMPLEMENT│  ENG-REVIEW │ ENG-MERGE │  SENTINEL │
│ (tmux)   │  (tmux)    │  (tmux)      │  (tmux)     │  (tmux)   │  (tmux)   │
│ SENSE →  │  Reality   │  Dispatch    │  PR review  │  Merge    │  Monitor  │
│ VALIDATE │  check →   │  workers →   │  verdicts → │  queue →  │  prod →   │
│ → Create │  Triage →  │  Monitor →   │  post to    │  rebase → │  alert →  │
│   issues │  Score →   │  Fix review  │  Linear     │  verify   │  create   │
│          │  Steer     │  feedback    │             │           │  issues   │
├──────────┴────────────┴──────────────┴─────────────┴───────────┴───────────┤
│  CONTENT (tmux) │ Query SEO → Dispatch → /team-implement                    │
├────────────────────────────────────────────────────────────────────────────┤
│  state.db (shared WAL) │ Tables: state, specialists, learning_ev,           │
│                         │         merge_queue, review_cycles                │
├────────────────────────────────────────────────────────────────────────────┤
│  TRUST + LEARNING: Auto-apply learnings, revert on fail                     │
│  INFRA: Dashboard (:1791)                                                   │
└────────────────────────────────────────────────────────────────────────────┘
```
