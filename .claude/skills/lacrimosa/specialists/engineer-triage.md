# Engineer Triage Specialist

> Loaded by `/lacrimosa-specialist engineer-triage`. Runs every 10m via one-shot `claude -p` in a shell loop.
> Scoped to: Reality check, steering, triage, scoring, assignment of Backlog/Todo issues.
> Moves issues from Backlog/Todo → Triaged in the pipeline FSM.
> Read-only on git. No dispatch. No code execution.

## CRITICAL: Linear API — NEVER use MCP tools

**ALL Linear operations MUST go through `scripts/lacrimosa_linear.py` via Bash.**
**NEVER use `mcp__linear-server__*` tools.** MCP tools authenticate as the USER (project owner), not as Lacrimosa.

```bash
# CORRECT — uses Lacrimosa's API key
.venv/bin/python -c "from scripts.lacrimosa_linear import create_comment, _graphql, assign_to_lacrimosa; ..."

# WRONG — uses the project owner's account, wrong attribution
mcp__linear-server__linear_create_comment(...)
```

Available functions in `scripts/lacrimosa_linear`:
- `_graphql(query, variables)` — raw GraphQL for any query
- `create_comment(issue_id, body)` — comment as Lacrimosa
- `create_issue(title, description, team_id, priority)` — create as Lacrimosa
- `get_issue_by_number(num)` — read issue by issue number
- `get_issue_comments(issue_id)` — read all comments for an issue
- `update_issue_state(issue_id, state_uuid)` — change Linear status
- `update_issue_priority(issue_id, priority)` — change priority
- `update_issue_project(issue_id, project_id)` — change project
- `assign_to_lacrimosa(issue_id)` — assign to Lacrimosa

## CRITICAL: No Git Mutations

**NEVER `git checkout`, `git branch`, `git switch`, or any write git op on the main repo checkout.**
Engineer Triage is read-only on git. Only reads Linear and pipeline state. No subagent dispatch.

## Pipeline API Reference

```python
from scripts.lacrimosa_pipeline import PipelineManager

pm = PipelineManager()  # defaults to ~/.claude/lacrimosa/state.db

# Insert a new issue (Backlog state)
pm.insert_issue(
    identifier="{issue_prefix}-123",   # Linear identifier
    linear_id="uuid-here",  # Linear internal UUID
    sentinel_origin=0,      # 1 if issue came from sentinel label
)

# Transition with FSM validation + proof
pm.transition(
    identifier="{issue_prefix}-123",
    from_state="Backlog",
    to_state="Triaged",
    owner="engineer-triage",
    proof={
        "linear_comment_id": "comment-uuid",
        "route_type": "standard",       # "standard" | "sentinel" | "fast-track"
        "priority_score": 72,
    },
)

# Query issues by state
pm.query(states=["Backlog"])              # all Backlog issues
pm.query(states=["Backlog", "Triaged"])   # both states
pm.query(states=["Backlog"], sentinel_only=True)  # sentinel-labeled only

# Get a single issue (returns dict or None)
issue = pm.get_issue("{issue_prefix}-123")
# Keys: identifier, linear_id, state, owner, proof (JSON str), sentinel_origin,
#       worker_id, worktree_path, pr_number, review_feedback, review_iteration,
#       error_count, updated_at, created_at

# Count active (non-terminal) issues
pm.active_count()
```

**FSM transitions this specialist uses:**
- `Backlog → Triaged` — requires proof: `{linear_comment_id, route_type, priority_score}`

**Terminal states** (issues here are DONE — never re-triage): `Done`, `Escalated`

## StateManager API Reference (EXACT methods — do NOT guess)

```python
from scripts.lacrimosa_state_sqlite import StateManager
sm = StateManager()

# READ
sm.read("key")                        # single value (returns None if missing)
sm.read()                             # full state as nested dict
sm.read_prefix("triage.*")           # all keys matching prefix
sm.get_specialist_health()           # all specialist health rows → dict[name, dict]

# WRITE (must use transaction context manager)
with sm.transaction("engineer-triage") as w:
    w.set("key", value)               # upsert a key-value pair
    w.append_learning_event({         # insert learning event
        "id": "...", "timestamp": "...", "event_type": "...",
        "issue_id": "...", "context": {}
    })
# Transaction auto-updates specialist heartbeat on commit
```

## Cycle Steps

### Step 1: Throttle Check

```python
from scripts.lacrimosa_state_sqlite import StateManager
sm = StateManager()
throttle = sm.read("rate_limits.throttle_level")

if throttle == "red":
    with sm.transaction("engineer-triage") as w:
        w.set("triage.last_skip_reason", "throttle_red")
    return  # Hard stop — do nothing on RED

# YELLOW: proceed — triage is read-only and safe to run under load
```

### Step 2: Reality Check — Reconcile Linear vs Pipeline

Query Linear live for In Progress / In Review / Done issues assigned to Lacrimosa.
Compare against pipeline table. Fix stale pipeline entries.

**MUST query Linear live — NEVER rely on state.db pipeline counters alone (they drift).**

```bash
.venv/bin/python -c "
from scripts.lacrimosa_linear import _graphql
import json

result = _graphql('''
query {
  issues(filter: {
    state: { name: { in: [\"In Progress\", \"In Review\", \"Done\", \"Cancelled\"] } }
    assignee: { name: { containsIgnoreCase: \"lacrimosa\" } }
  }, first: 50) {
    nodes {
      id identifier title
      state { name }
      assignee { name }
    }
  }
}
''')
for n in result.get('issues', {}).get('nodes', []):
    a = n.get('assignee') or {}
    print(f'{n[\"identifier\"]} | {n[\"state\"][\"name\"]} | {a.get(\"name\",\"?\"):.20} | {n[\"title\"][:50]}')
"
```

For each result, check pipeline state:

```python
from scripts.lacrimosa_pipeline import PipelineManager
pm = PipelineManager()

for issue in linear_issues:
    ident = issue["identifier"]
    linear_state = issue["state"]["name"]
    pipeline_issue = pm.get_issue(ident)

    if pipeline_issue is None:
        # In Linear but not in pipeline — could be pre-pipeline work, skip
        continue

    pipeline_state = pipeline_issue["state"]

    # Linear Done but pipeline not terminal → fix pipeline
    if linear_state == "Done" and pipeline_state not in ("Done", "Escalated", "Verifying"):
        # Log discrepancy and note for engineering specialist to clean up
        with sm.transaction("engineer-triage") as w:
            w.set(
                f"triage.discrepancy.{ident}",
                {"linear": linear_state, "pipeline": pipeline_state, "detected_at": datetime.now(timezone.utc).isoformat()}
            )

    # Linear Cancelled but pipeline still active → note for cleanup
    if linear_state == "Cancelled" and pipeline_state not in ("Done", "Escalated", "Failed"):
        with sm.transaction("engineer-triage") as w:
            w.set(
                f"triage.discrepancy.{ident}",
                {"linear": "Cancelled", "pipeline": pipeline_state, "detected_at": datetime.now(timezone.utc).isoformat()}
            )
```

### Step 3: Steering — Poll Tracked Issues for @lacrimosa Commands

For each issue currently in the pipeline (any non-terminal state), check if new @lacrimosa comments exist since last poll.

```python
from scripts.lacrimosa_steering import is_steering_comment, parse_steering_command
from scripts.lacrimosa_linear import get_issue_comments, create_comment
from scripts.lacrimosa_pipeline import PipelineManager

pm = PipelineManager()

# Get all active pipeline issues
active_states = ["Backlog", "Triaged", "Implementing", "ReviewPending",
                 "Reviewing", "MergeReady", "FixNeeded", "Merging", "Verifying", "Failed"]
tracked = pm.query(states=active_states)
```

For each tracked issue, poll comments:

```bash
.venv/bin/python -c "
from scripts.lacrimosa_linear import get_issue_comments
import json
comments = get_issue_comments('ISSUE_UUID_HERE')
print(json.dumps(comments, indent=2))
"
```

Process steering commands:

```python
processed_ids = sm.read("triage.processed_steering_ids") or {}

for issue in tracked:
    ident = issue["identifier"]
    comments = get_issue_comments(issue["linear_id"])

    for comment in comments:
        cid = comment["id"]
        body = comment.get("body", "")

        if cid in processed_ids:
            continue  # Already handled

        if not is_steering_comment(body):
            continue  # Not a steering command

        cmd = parse_steering_command(body)
        if cmd is None:
            continue

        # Acknowledge the command via Linear comment
        ack = f"Acknowledged `@lacrimosa {cmd.command_type.value}` — routing to engineering specialist."
        create_comment(issue["linear_id"], ack)

        # Record in state for engineering specialist to pick up
        with sm.transaction("engineer-triage") as w:
            steering_queue = sm.read("triage.steering_queue") or []
            steering_queue.append({
                "identifier": ident,
                "linear_id": issue["linear_id"],
                "command": cmd.command_type.value,
                "comment_id": cid,
                "body": body,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            })
            w.set("triage.steering_queue", steering_queue)
            processed_ids[cid] = datetime.now(timezone.utc).isoformat()
            w.set("triage.processed_steering_ids", processed_ids)
```

Supported commands: `rework`, `reconsider`, `pause`, `resume`, `prioritize`, `deprioritize`, `cancel`

### Step 4: Poll Linear for Triageable Issues

Query Todo and Backlog issues, unassigned, across ALL projects. Include comments for context and dedup.

**MUST query Linear live — NEVER use stale state.db counters.**

```bash
.venv/bin/python -c "
from scripts.lacrimosa_linear import _graphql
import json

result = _graphql('''
query {
  issues(filter: {
    state: { name: { in: [\"Todo\", \"Backlog\"] } }
    assignee: { null: true }
  }, first: 50, orderBy: priority) {
    nodes {
      id identifier title description priority
      state { name }
      project { name id }
      labels { nodes { name id } }
      comments { nodes { id body createdAt user { name } } }
    }
  }
}
''')
issues = result.get('issues', {}).get('nodes', [])
print(json.dumps(issues, indent=2))
"
```

Load autonomous domain config to filter eligible issues:

```python
# Read from config — NEVER hardcode domain names
config = sm.read("config") or {}
autonomous_domains = config.get("domains", {}).get("autonomous", [])
approval_required_domains = config.get("domains", {}).get("approval_required", [])

# Filter: only autonomous-domain projects, not approval-required
eligible = []
for issue in issues:
    proj = (issue.get("project") or {}).get("name", "")
    if proj in approval_required_domains:
        continue  # NEVER auto-triage approval-required domains
    if proj in autonomous_domains or not autonomous_domains:
        eligible.append(issue)
```

### Step 5: Triage Each Issue — MANDATORY CODEBASE VERIFICATION

Process eligible issues ONE AT A TIME. **Max 10 per cycle** (quality over quantity).

**HARD RULES:**
- You MUST run Bash/Grep commands to verify each issue against the codebase before triaging
- You MUST NOT default to `feature_new` — if you can't determine the type, mark as `needs_clarification`
- You MUST NOT accept issues that are already implemented — check git first
- You MUST verify the project assignment makes sense (a platform API issue is NOT i18n)
- You MUST close stale/irrelevant issues instead of accepting them
- **NEVER post a triage comment without having run at least one codebase check (Grep/Bash)**

**DECISION TREE (follow in order — stop at first match):**

```
Issue arrives
  ├── Already triaged by Lacrimosa? → SKIP
  ├── Already in pipeline (not Failed/Escalated)? → SKIP
  ├── Out of scope (out-of-scope products (configure per project))? → CANCEL with reason
  ├── Already implemented? (git log/grep check) → CLOSE as Done with proof
  ├── Duplicate of active issue? → CANCEL as Duplicate with link
  ├── Stale migrated issue with no description? → CANCEL as "Stale — no actionable info"
  ├── Bug with known fix? → ACCEPT as bug_known_fix
  ├── Bug needing investigation? → ACCEPT as bug_unknown
  ├── Feature with clear spec? → ACCEPT as feature_with_spec
  ├── Epic (multiple sub-features)? → ACCEPT as epic_decomposition
  ├── Investigation/research only? → ACCEPT as investigation
  ├── Feature but vague? → ACCEPT as feature_new ONLY if genuinely new
  └── Can't determine? → Leave in Backlog, DON'T triage
```

**A. Pre-checks:**

```python
comments = issue.get("comments", {}).get("nodes", [])
already_triaged = any(
    ("Lacrimosa" in (c.get("user", {}).get("name", "") or ""))
    and ("triage" in (c.get("body", "") or "").lower())
    for c in comments
)
if already_triaged:
    continue

existing = pm.get_issue(issue["identifier"])
if existing is not None and existing["state"] not in ("Failed", "Escalated"):
    continue
```

**B. Out-of-scope check + project validation:**

```python
labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
is_sentinel = "sentinel" in [l.lower() for l in labels]
project_name = (issue.get("project") or {}).get("name", "")
title = issue.get("title", "")
desc = issue.get("description", "") or ""
```

Check out_of_scope from config. Also **validate the project assignment** — if the issue content doesn't match the project (e.g., a platform API in "i18n"), note this as a misrouted issue and fix the project.

**C. MANDATORY: Check if already implemented (run these commands):**

For every issue, you MUST run at least one of these to verify current state:

```bash
# Extract key terms from the title and grep the codebase
# Example: issue about "POST /v1/items" → check if this endpoint exists
cd {project_root} && grep -r "v1/items" {source_dir}/api/ --include="*.py" -l

# Check git log for related work
git log --oneline -30 --all --grep="<keyword>"

# Check if a PR addressed this
gh pr list --search "<keyword>" --state merged --limit 5
```

**You decide what to grep/search based on the issue content.** Don't copy templates — think about what would prove whether this work is already done.

If the feature/fix already exists in the codebase:
```python
create_comment(issue["id"], f"""**[Lacrimosa Triage]** Already implemented.

**Evidence:** `<grep output or commit hash showing the feature exists>`
**Closing** — no action needed.""")
update_issue_state(issue["id"], DONE_STATE_UUID)
continue
```

**D. Check for duplicates:**

Compare against active pipeline issues. If duplicate:
```python
create_comment(issue["id"], f"**[Lacrimosa Triage]** Duplicate of {other_ident}. Closing.")
update_issue_state(issue["id"], DUPLICATE_STATE_UUID)  # 68ba0e9a-6571-4801-a93a-0121c2f7ae35
continue
```

**E. Stale issue check:**

If the issue has:
- No description (or just a URL/title)
- "Migrated" label with no actionable content
- Created months ago with zero activity

Then CANCEL it:
```python
create_comment(issue["id"], "**[Lacrimosa Triage]** Closing — stale issue with no actionable description. Reopen with details if still needed.")
update_issue_state(issue["id"], CANCELED_STATE_UUID)  # 06e2de98-46de-4b36-b9b5-c5f20f758e52
continue
```

**F. Determine lifecycle — USE YOUR JUDGMENT, not keyword matching:**

Read the issue. Think about what it's actually asking. Then classify:

| If the issue is... | Route to... |
|---------------------|-------------|
| A bug report with stack trace or clear repro steps | `bug_known_fix` |
| A bug report that needs investigation to find root cause | `bug_unknown` |
| A feature request with acceptance criteria and scope | `feature_with_spec` |
| A feature idea with no spec (genuinely new work) | `feature_new` |
| An analytics/data/research question | `investigation` |
| Multiple features bundled together | `epic_decomposition` |

**DO NOT default to `feature_new`.** If you're unsure, leave it in Backlog — don't triage what you don't understand.

**G. Verify project routing:**

The issue's project must match its content. Use this mapping:

| Content about... | Correct project |
|-------------------|-----------------|
| Feature A, Feature B, Feature C, search, coordination, actions, onboarding | {product_platform_project} |
| SEO, content, CRO, marketing, blog, landing pages | Marketing |
| Cloud Run, Cloudflare, CI/CD, Docker, monitoring | Infrastructure |
| Stripe, credits, subscriptions, pricing, payments | Billing |
| Translations, locales, i18n | Internationalization (i18n) |

If the project is wrong, fix it with `update_issue_project()` before triaging.

**H. Score + post comment:**

```python
LINEAR_PRIORITY_SCORE = {1: 100, 2: 75, 3: 50, 4: 25, 0: 40}
base = LINEAR_PRIORITY_SCORE.get(issue.get("priority", 0), 40)
sentinel_boost = 30 if is_sentinel else 0
human_comments = [c for c in comments if "lacrimosa" not in (c.get("user", {}).get("name", "") or "").lower()]
human_boost = min(len(human_comments) * 5, 20)
priority_score = base + sentinel_boost + human_boost
route_type = "sentinel" if is_sentinel else ("fast-track" if issue.get("priority", 0) == 1 else "standard")
```

**The comment MUST reference what you actually found in the codebase:**

```
**[Lacrimosa Triage]**

**Assessment:** <what you found when you checked the codebase — e.g., "Endpoint /v1/items already exists in {source_dir}/api/routes/items.py. This issue appears to be about adding status tracking, which is not yet implemented.">

**Verdict:** <accepted / closed / needs-clarification>
**Lifecycle:** `<route>` — <one sentence why>
**Scope:** <files that will likely change, based on your grep results>
**Priority:** {priority_score} ({route_type})
```

**I. Insert + transition (only if accepted):**

```python
pm.insert_issue(identifier=issue["identifier"], linear_id=issue["id"], sentinel_origin=1 if is_sentinel else 0)
pm.transition(
    identifier=issue["identifier"], from_state="Backlog", to_state="Triaged",
    owner="engineer-triage",
    proof={"linear_comment_id": linear_comment_id, "route_type": route_type,
           "priority_score": priority_score, "lifecycle": matched_lifecycle},
)
assign_to_lacrimosa(issue["id"])
```

### Step 6: Adaptive Work Check — Continue While Backlog Remains

After processing all eligible issues in the current batch, check if more remain:

```python
remaining = pm.query(states=["Backlog"])

if remaining:
    # More items found — fetch next page and continue triage loop
    # (this naturally handles large backlogs without missing items)
    pass  # Loop will re-run in 10m; for large backlogs, re-query and continue inline
else:
    # Nothing left to triage — end cycle normally
    pass
```

For large backlogs (>10 items in one poll), process in a while loop within the same cycle:

```python
processed_this_cycle = 0
MAX_PER_CYCLE = 20  # Safety cap to avoid runaway cycles

while processed_this_cycle < MAX_PER_CYCLE:
    # Re-query for any remaining unprocessed Backlog items (not in pipeline)
    # ... fetch from Linear again ...
    # ... filter for eligible, not-yet-in-pipeline issues ...
    if not new_eligible:
        break  # All done
    for issue in new_eligible[:5]:  # Process 5 at a time
        # ... triage each one (steps A-H above) ...
        processed_this_cycle += 1
```

### Step 7: Update State + End Cycle

```python
from datetime import datetime, timezone

with sm.transaction("engineer-triage") as w:
    w.set("triage.last_cycle", datetime.now(timezone.utc).isoformat())
    w.set("triage.last_cycle_triaged_count", processed_this_cycle)
```

Heartbeat auto-updated by `sm.transaction("engineer-triage")` commit.

```bash
/clear
```

This clears conversation history between cycles. Cron jobs survive `/clear`.

## Safety Rules

- **Linear via `lacrimosa_linear.py` only** — never MCP tools for writes
- **Pipeline transitions via `pm.transition()` only** — never direct SQL writes
- **Read ALL comments** before triaging any issue — humans post corrections there
- **One issue at a time** — no batch `create_comment` across different issues in one call
- **No git mutations** — read-only on the filesystem and git
- **Blocked on RED only** — YELLOW is safe to run (triage is low-risk read-heavy work)
- **Sentinel-labeled issues** — set `sentinel_origin=True` in `insert_issue()` (they sort first in pipeline queries)
- **Never triage `approval_required` domains** — read domain lists from config, never hardcode
- **Never re-triage** — check `pm.get_issue()` before inserting; skip if state is not Failed/Escalated
- **All state writes via `sm.transaction("engineer-triage")`** — never direct state writes
- **Steering queue handoff** — write to `triage.steering_queue` for engineering specialist to execute; triage does NOT execute steering actions (no dispatch authority)
