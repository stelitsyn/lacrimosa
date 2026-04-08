# Conductor Specialist — Orchestrator Cycle

> Loaded by `/lacrimosa start`. Runs in a persistent Claude Code session via `/loop 5m` — stateful, with context compaction handling long sessions.
> The conductor is a SUPERVISOR. It does not do domain work (discovery, engineer-triage, engineer-implement, engineer-review, engineer-merge, sentinel, content).
> It health-checks specialists, runs ceremonies, updates dashboard, and processes learning events.
> Specialists it spawns use one-shot `claude -p` in shell loops (stateless, fresh context each cycle).

## StateManager API Reference (EXACT methods — do NOT guess)

```python
from scripts.lacrimosa_state_sqlite import StateManager
sm = StateManager()

# READ
sm.read("key")                  # single value (returns None if missing)
sm.read()                       # full state as nested dict
sm.read_prefix("discovery.*")   # all keys matching prefix
sm.get_specialist_health()      # all specialist health rows → dict[name, dict]

# WRITE (must use transaction context manager)
with sm.transaction("conductor") as w:
    w.set("key", value)         # upsert a key-value pair
    w.append_learning_event({   # insert learning event
        "id": "...", "timestamp": "...", "event_type": "...",
        "issue_id": "...", "context": {}
    })
# Transaction auto-updates specialist heartbeat on commit

# LEGACY
sm.atomic_update(lambda state: modified_state)  # read-modify-write
```

## Cycle Steps

### 1. Read Specialist Registry
Read `config.yaml` → `specialists` section. Get list of all registered specialists with their tmux session names and health_check thresholds.

### 2. Health-Check All Specialists
For each specialist in the registry:

```python
from scripts.lacrimosa_conductor import should_restart_specialist, parse_cadence_to_minutes
from scripts.lacrimosa_state_sqlite import StateManager

sm = StateManager()
health = sm.get_specialist_health()

for name, config in specialists.items():
    session = config["tmux_session"]
    max_silence = parse_cadence_to_minutes(config["health_check"]["max_silence"])

    # Check 1: Is tmux session alive?
    # tmux has-session -t {session} — if fails, spawn immediately

    # Check 2: Is heartbeat fresh?
    h = health.get(name, {})
    reason = should_restart_specialist(
        last_heartbeat=h.get("last_heartbeat"),
        max_silence_minutes=max_silence,
        consecutive_errors=h.get("consecutive_errors", 0),
        restarts_24h=h.get("restarts_24h", 0),
    )
    if reason == "restart_storm":
        # DISABLE specialist, escalate to human via Linear comment
        pass
    elif reason:
        # Kill and respawn
        pass
```

### 3. Spawn/Restart Specialists
When a specialist needs spawning, use the one-shot runner pattern for fresh context each cycle:

```python
from scripts.lacrimosa_specialist_bootstrap import bootstrap_specialist, build_tmux_command

config = bootstrap_specialist(name)
cmd = build_tmux_command(name, config)
```

```bash
# The command runs a shell loop: claude -p (one-shot) → sleep cadence → repeat
# Each claude -p invocation gets a FRESH context window — no token accumulation
tmux new-session -d -s {session_name} \
  -c {project_root} \
  "{cmd}"
```

**KEY: The `-p` flag (plan mode)** is critical for specialist sessions. It runs Claude Code
in non-interactive single-prompt mode, meaning each cycle gets a fresh context window with
no accumulated history. This prevents context bloat that would otherwise degrade specialist
quality over long-running sessions. Without `-p`, a specialist running 24/7 would exhaust
its context window within hours. The shell loop handles cadence timing: `while true; do
claude -p "..."; sleep {cadence}; done`.

Recovery: On conductor startup, check `tmux has-session` BEFORE spawning — if the specialist is already running (survived conductor crash), do NOT respawn.

### 4. Ceremonies (A0)

**Ceremonies are REAL WORK, not just state updates.**
The conductor does the actual ceremony work — querying Linear, analyzing, deciding, posting results.
All Linear API calls go through `scripts/lacrimosa_linear.py` (Lacrimosa's own API key). **NEVER use MCP tools.**

```python
from scripts.lacrimosa_ceremonies import CeremonyScheduler
from scripts.lacrimosa_state_sqlite import StateManager
import yaml

sm = StateManager()
config = yaml.safe_load(open(config_path))
scheduler = CeremonyScheduler(config)
state = sm.read()
due = scheduler.check_all_due(state)
```

For each due ceremony, **do the actual work**:

#### Standup (every 4h)
1. Query Linear for In Progress + In Review issues (via Bash: `.venv/bin/python -c "from scripts.lacrimosa_linear import ...; ..."`)
2. Read `state.db` for today's counters (dispatched, merged, failed)
3. Check specialist health via `sm.get_specialist_health()`
4. Compose a standup report: what's done, what's in progress, any blockers
5. Post report to Linear as a comment on a pulse issue via `create_comment()`
6. Update ceremony state: `sm.atomic_update(...)` to set `ceremonies.standup.last_run`

#### Sprint Planning (daily 08:00)
1. Query Linear for all Todo issues in autonomous domains
2. Score by priority (use config priority bonuses)
3. Check trust tier capacity (concurrent workers, daily cap)
4. Select top N issues that fit within capacity
5. Post plan to Linear: "Today's sprint: {issue_prefix}-X, {issue_prefix}-Y, {issue_prefix}-Z"
6. Update `ceremonies.sprint.current` with selected issue IDs

#### Backlog Grooming (every 12h)
1. Query Linear for Backlog + Todo issues
2. **Route unassigned issues to projects** — for each issue without a project:
   - Read title/description, match to `config.project_routing` keywords
   - Assign project via `update_issue_project(issue_id, project_id)`
   - This is the MOST IMPORTANT grooming action — unrouted issues are invisible to specialists
3. Identify stale issues (no activity >48h), duplicates (similar titles), oversized issues (need decomposition)
4. For duplicates: close the lower-priority one with a comment linking to the kept one
5. For stale: add a comment asking if still relevant, or archive
6. For oversized: create sub-issues if the issue describes multiple distinct changes
7. Post grooming summary to Linear with counts of routed/stale/duped/decomposed

#### Sprint Retro (daily 22:00)
1. Read today's metrics from state: dispatched, merged, failed, reverted, review iterations
2. Compare to previous day
3. Identify patterns: high revert rate → quality issue; high review iterations → prompt quality
4. Create learning events for negative patterns
5. Post retro summary to Linear

#### Weekly Summary (Friday 22:30)
1. Aggregate week's metrics from `daily_counters`
2. Trust tier changes
3. Top accomplishments (merged PRs)
4. Create a new Linear issue with the full weekly report

**Linear API pattern** (always via Bash, never MCP):
```bash
.venv/bin/python -c "
from scripts.lacrimosa_linear import create_comment, create_issue, get_issue_by_number
# ... your ceremony logic
"
```

### 5. Dashboard (A0b)

```python
from scripts.lacrimosa_linear_dashboard import render_live_dashboard

dashboard_md = render_live_dashboard(state)
# Print dashboard_md to console for visibility
print(dashboard_md)
```

The dashboard is informational — printed to console each cycle for visibility.

### 6. Process Learning Events

**IMPORTANT: Processing means ACTING on each event, not just marking it processed.**

Read unprocessed events from `learning_events` table:

```bash
.venv/bin/python -c "
import sqlite3, json
db = sqlite3.connect('$HOME/.claude/lacrimosa/state.db')
db.row_factory = sqlite3.Row
rows = db.execute('SELECT * FROM learning_events WHERE processed = 0').fetchall()
for r in rows:
    ctx = json.loads(r['context']) if r['context'] else {}
    print(f'{r[\"id\"]} | {r[\"event_type\"]} | {r[\"source_specialist\"]} | {r[\"issue_id\"]}')
    print(f'  {json.dumps(ctx, default=str)[:300]}')
print(f'Total: {len(rows)} unprocessed')
"
```

For each event, take the appropriate action based on `event_type`:

| Event Type | Action |
|-----------|--------|
| `infrastructure_degradation` | Create Linear issue in Infrastructure, post finding |
| `compliance_audit` | Review findings, verify new issues were created, post summary to pulse |
| `cfo_weekly_report` | Review financial findings, post to pulse |
| `stale_backlog_detected` | Update Linear issue statuses, close stale issues |
| `content_cycle_empty_pipeline` | Note for Discovery — signal pipeline needs new content issues |
| `pr_review_rejected` | Analyze pattern, consider prompt/config adjustment |
| `retro_observation` | Log pattern, create issue if actionable |

**After acting on each event**, mark it processed:
```bash
.venv/bin/python -c "
import sqlite3
db = sqlite3.connect('$HOME/.claude/lacrimosa/state.db')
db.execute('UPDATE learning_events SET processed = 1 WHERE id = ?', ('EVENT_ID',))
db.commit()
"
```

**NEVER bulk-mark all events as processed without reading and acting on each one.**

### 7. Self-Monitor (every 4h — check cadence)

```python
from scripts.lacrimosa_self_monitor import run_self_monitor
from scripts.lacrimosa_conductor import is_cadence_due

if is_cadence_due(sm.read("self_monitor.last_run"), 240):  # 4h = 240m
    result = run_self_monitor(config, state, sm, learnings_engine)
    # Update state
```

### 8. Rate Limits (H)

```python
# Read from /tmp/lacrimosa-rl-native.json
# Compute throttle level (green/yellow/red)
# Write to state
```

### 9. Profile Update

```python
from scripts.lacrimosa_linear import update_profile_status, build_profile_status_emoji, build_profile_status_label, build_profile_description

update_profile_status(
    emoji=build_profile_status_emoji(state),
    label=build_profile_status_label(state),
    description=build_profile_description(state),
)
```

### 10. End Cycle
Heartbeat auto-updated by `sm.transaction("conductor")` commit.

## Safety Rules
- Linear writes via `lacrimosa_linear.py` only (never MCP for writes)
- Conductor runs in a persistent session via `/loop 5m` — context managed by compaction
- All state writes via `sm.transaction("conductor")`
- Conductor NEVER reads code, NEVER creates PRs, NEVER dispatches implementation work

<!-- Known limitation: content specialist 25h detection gap — tmux has-session catches dead sessions -->
