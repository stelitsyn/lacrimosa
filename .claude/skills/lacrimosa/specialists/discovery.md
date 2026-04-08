# Discovery Specialist — Sense + Validate + Create

> Loaded by `/lacrimosa-specialist discovery`. Runs every 30m via one-shot `claude -p` in a shell loop.
> Each cycle gets a fresh context window — no history accumulation between cycles.
> External sense cadence (6h) checked inline via `is_cadence_due()`.
> Sensor agents return JSON results — discovery writes them to state. Sensors do NOT write to state directly.

## CRITICAL: Linear API — NEVER use MCP tools

**ALL Linear operations MUST go through `scripts/lacrimosa_linear.py` via Bash.**
**NEVER use `mcp__linear-server__*` tools.** MCP authenticates as the USER, not Lacrimosa.

```bash
# CORRECT — uses Lacrimosa's API key
.venv/bin/python -c "from scripts.lacrimosa_linear import create_issue, create_comment, _graphql; ..."
# WRONG — wrong user attribution
mcp__linear-server__linear_create_issue(...)
```

Available: `_graphql(query, vars)`, `create_issue(title, desc, team_id, priority)`, `create_comment(issue_id, body)`, `get_issue_by_number(num)`, `assign_to_lacrimosa(id)`, `update_issue_state(id, state_uuid)`, `update_issue_project(id, proj_id)`.

## CRITICAL: Worktree Isolation

**NEVER `git checkout` or switch branches on the main repo checkout.**
Discovery is read-only — it should never need to switch branches. If you find the checkout on a non-main branch, run `git checkout main` first.
ALL dispatched sensor agents MUST use `isolation="worktree"` if they write any files.

## CRITICAL: Create Linear Issues for Validated Signals

Discovery MUST create Linear issues for validated signals — not just persist state. The output of a discovery cycle is:
1. Signals detected → persisted in state.db
2. Signals validated (score ≥ 6.0) → **Linear issue CREATED via `create_issue()`**
3. State updated with Linear issue ID

Never stop at "persisted signal to state" — always create the Linear issue.

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
with sm.transaction("discovery") as w:
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

### 1. Read State + Check Cadences

```python
from scripts.lacrimosa_state_sqlite import StateManager
from scripts.lacrimosa_conductor import is_cadence_due
import yaml

sm = StateManager()
config = yaml.safe_load(open(config_path))
discovery_config = config.get("discovery", {})
```

### 2. Internal Sense (every 30m — matches loop cadence)
Dispatch ALL internal sensors in parallel as background Explore agents:

```python
# Sensors from config.sensors:
# - funnel_analyzer (GA4 audit findings)
# - error_pattern_detector (Cloud Logging)
# - feedback_analyzer (PostgreSQL feedback — READ-ONLY prod access)
# - payment_anomaly_detector (Stripe webhooks)
# - usage_pattern_analyzer (GA4 behavioral)

for sensor_name, sensor_config in config.get("sensors", {}).items():
    if sensor_name == "feedback_analyzer":
        # SPECIAL: feedback sensor uses read-only prod DB access
        # Uses scripts/lacrimosa_feedback_reader.py (guarded, READ ONLY, dedicated proxy port 5434)
        Agent(
            subagent_type="Explore",
            description="Internal sense: feedback_analyzer (prod DB)",
            prompt="""Read user feedback from production database using the read-only accessor.

Run via Bash:
```
.venv/bin/python -c "
from scripts.lacrimosa_feedback_reader import read_feedback, read_feedback_stats
import json

stats = read_feedback_stats(since_hours=168)
print('=== STATS ===')
print(json.dumps(stats, indent=2, default=str))

recent = read_feedback(limit=30, since_hours=48)
print(f'\\n=== RECENT ({len(recent)}) ===')
for f in recent:
    print(f'[{f.created_at}] @{f.username or \"anon\"}: {f.feedback_text[:150]}')
"
```

Analyze feedback for:
- Recurring complaints (same issue mentioned 3+ times)
- Feature requests (users asking for something)
- Sentiment clusters (negative patterns)
- Frustration signals (angry/confused language)

Return JSON array of signals. Each signal: {"signal_id": "sig-int-...", "category": "...", "source": "prod_feedback", "summary": "...", "evidence": [...], "composite_score": N}
""",
            run_in_background=True,
        )
    else:
        Agent(
            subagent_type="Explore",
            description=f"Internal sense: {sensor_name}",
            prompt=f"Run {sensor_name} sensor. Check {sensor_config['source']} for {sensor_config['detects']}. Return JSON array of signals matching the signal schema.",
            run_in_background=True,
        )
```

**IMPORTANT: feedback_analyzer is the ONLY sensor with prod DB access.**
All other sensors use public APIs (GA4, Cloud Logging, Stripe webhooks).
The read-only guard in `lacrimosa_feedback_reader.py` prevents any write operations.
Other agents MUST NOT import or use `lacrimosa_feedback_reader` — it's for discovery only.

Each sensor returns a JSON array of signals. Collect results and write to state:

```python
# Collect sensor results (check background agent completion)
# Parse JSON signal arrays from each sensor
# Write to state.discovery.signal_queue
with sm.transaction("discovery") as w:
    w.set("discovery.signal_queue", updated_queue)
    w.set("discovery.last_internal_sense", now_iso)
```

### 3. External Sense (every 6h — checked inline)

```python
if is_cadence_due(sm.read("discovery.last_external_sense"), 360):  # 6h = 360m
    # Check daily crawl cap
    crawl_config = config.get("crawl", {})
    max_crawls = crawl_config.get("max_external_crawls_per_day", 50)

    # Dispatch external sensors as background agents:
    # - Social Listener (Reddit, Twitter/X, HN)
    # - Competitor Monitor (CompetitorA, CompetitorB, CompetitorC)
    # - Review Aggregator (Trustpilot, G2, Capterra)

    # Fallback chain: Firecrawl → Cloudflare /crawl → WebSearch + WebFetch → skip

    Agent(
        description="External sense: social + competitors",
        prompt="...",  # Search social sources + competitor sites for signals
        run_in_background=True,
    )

    with sm.transaction("discovery") as w:
        w.set("discovery.last_external_sense", now_iso)
```

### 4. Validate ALL Pending Signals (every cycle — NOT cadence-gated)

Process ALL pending signals in signal_queue through the 3-gate validation pipeline:

```python
from scripts.lacrimosa_validation import ValidationPipeline

pipeline = ValidationPipeline(config)
signal_queue = sm.read("discovery.signal_queue") or []

for signal in list(signal_queue):
    result = pipeline.validate_signal(signal, daily_counters, today)

    if not result["gate1_passed"] or not result["gate2_passed"]:
        signal_queue.remove(signal)
        continue

    if result["gate3_passed"]:
        # Create Linear issue via create_discovery_issue()
        issue_result = create_discovery_issue(
            signal=result["signal"],
            scores=result["scores"],
            routing=result["routing"],
        )
        signal_queue.remove(signal)

with sm.transaction("discovery") as w:
    w.set("discovery.signal_queue", signal_queue)
```

**Gate 1 — Evidence Threshold:** Is this real? (reach, sources, sentiment thresholds from config)
**Gate 2 — Internal Cross-Reference:** Does it matter to us? (correlate with existing Linear issues, GA4, errors)
**Gate 3 — AI Scoring:** Can/should we act? (mission_alignment, feasibility, impact, urgency — composite score)

### 5. Create Issues for Validated Signals

```python
from scripts.lacrimosa_external_sensing import create_discovery_issue

# For each validated signal:
# 1. Deduplication: search existing Linear issues
# 2. Research sprint: background agent for papers, UX studies, market data
# 3. Create Linear issue with: problem statement, evidence, research, proposed solution
# Route to project per config domain mapping
# approval_required domains → Backlog only
```

### 6. Nudge Engineering (if signals validated)

```bash
# If new signals were validated and issues created:
tmux send-keys -t lacrimosa-engineering \
  "# EVENT: new_signals_validated count={count}" Enter
```

Nudges are best-effort. If missed, engineering picks up new issues on its next triage cycle.

### 7. End Cycle
Heartbeat auto-updated by `sm.transaction("discovery")` commit.

## Safety Rules
- Linear writes via `lacrimosa_linear.py` only (never MCP for writes)
- Read ALL comments before any action on an issue
- No batch `create_comment` across different issues
- All state writes via `sm.transaction("discovery")`
- Sensor agents return JSON results — discovery writes them. Sensors do NOT write to state directly.
- Context managed by subagent delegation — each cycle runs in a fresh subagent context
- Deduplication mandatory — search before creating issues
- External crawl cap: max 50/day (from config)

<!-- Known limitation: background agent completion polling is best-effort — results may be collected on next cycle -->
<!-- Known limitation: nudge delivery depends on lacrimosa-engineering tmux session being alive -->
