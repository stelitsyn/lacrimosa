# Engineer-Implement Specialist — Dispatch, Monitor, Stall-Detect, Fix Review Feedback

> Loaded by `/lacrimosa-specialist engineer-implement`. Runs every 10m via `/loop 10m`.
> Processes Triaged and FixNeeded issues ONLY. Does not triage, review, merge, or verify.
> Delegates ALL implementation to background workers in isolated worktrees.
> Engineer-Implement is an ORCHESTRATOR — it decides what to dispatch, then delegates the doing.

## CRITICAL: Linear API — NEVER use MCP tools

**ALL Linear operations MUST go through `scripts/lacrimosa_linear.py` via Bash.**
**NEVER use `mcp__linear-server__*` tools.** MCP tools authenticate as the USER (project owner), not as Lacrimosa.

```bash
# CORRECT — uses Lacrimosa's API key
.venv/bin/python -c "from scripts.lacrimosa_linear import create_comment, get_issue_by_number; ..."

# WRONG — uses the project owner's account, wrong attribution
mcp__linear-server__linear_create_comment(...)
```

Available functions in `scripts/lacrimosa_linear`:
- `_graphql(query, variables)` — raw GraphQL for any query
- `create_comment(issue_id, body)` — comment as Lacrimosa
- `create_issue(title, description, team_id, priority)` — create as Lacrimosa
- `get_issue_by_number(num)` — read issue (returns dict with id, identifier, title, description, state, etc.)
- `get_issue_comments(issue_id)` — read all comments on an issue
- `update_issue_state(issue_id, state_uuid)` — change Linear status
- `assign_to_lacrimosa(issue_id)` — assign to Lacrimosa
- `update_profile_status(emoji, label, description)` — update profile

## CRITICAL: Worktree Isolation (MANDATORY)

**NEVER `git checkout`, `git branch`, or `git switch` on the main repo checkout.**
The main checkout (`{project_root}`) MUST stay on `main` at all times.

- ALL dispatched agents MUST use `isolation="worktree"` parameter
- The pipeline FSM REJECTS a Triaged→Implementing transition without `worktree_path` in proof
- Monitoring and validation: read-only operations on main — never switch branches
- If you find the checkout on a non-main branch, run `git checkout main` to fix it before any work

## Pipeline API Reference

```python
from scripts.lacrimosa_pipeline import PipelineManager, InvalidTransition, MissingProof

pm = PipelineManager()

# Query issues in specific states (sentinel issues sort first)
issues = pm.query(states=["Triaged", "FixNeeded"])
implementing = pm.query(states=["Implementing"])

# Get a single issue
issue = pm.get_issue("{issue_prefix}-123")  # returns dict or None
# Keys: identifier, linear_id, state, worker_id, worktree_path, pr_number,
#       review_feedback, review_iteration, error_count, sentinel_origin,
#       proof (JSON string), owner, created_at, updated_at

# Transition an issue (FSM-validated, proof required)
pm.transition(
    identifier="{issue_prefix}-123",
    from_state="Triaged",
    to_state="Implementing",
    owner="engineer-implement",
    proof={"worker_id": "agent-abc123", "worktree_path": "/tmp/lacrimosa/wt-{issue_prefix_lower}-123"},
)

pm.transition(
    identifier="{issue_prefix}-123",
    from_state="Implementing",
    to_state="ReviewPending",
    owner="engineer-implement",
    proof={"pr_number": 456, "pr_url": "https://github.com/..."},
)

pm.transition(
    identifier="{issue_prefix}-123",
    from_state="Implementing",
    to_state="Failed",
    owner="engineer-implement",
    proof={"error_message": "Worker stalled >10 min", "retry_eligible": True},
)

# Re-enter from FixNeeded (same proof as Triaged→Implementing)
pm.transition(
    identifier="{issue_prefix}-123",
    from_state="FixNeeded",
    to_state="Implementing",
    owner="engineer-implement",
    proof={"worker_id": "agent-xyz789", "worktree_path": "/tmp/lacrimosa/wt-{issue_prefix_lower}-123-fix1"},
)
```

**Required proof keys (from FSM):**
- `Triaged → Implementing`: `worker_id`, `worktree_path`
- `FixNeeded → Implementing`: `worker_id`, `worktree_path`
- `Implementing → ReviewPending`: `pr_number`, `pr_url`
- `Implementing → Failed`: `error_message`, `retry_eligible`

## StateManager API Reference

```python
from scripts.lacrimosa_state_sqlite import StateManager
sm = StateManager()

# READ
sm.read("key")                   # single value (returns None if missing)
sm.read()                        # full state as nested dict
sm.read_prefix("engineer.*")    # all keys matching prefix
sm.get_specialist_health()       # all specialist health rows → dict[name, dict]

# WRITE (must use transaction context manager)
with sm.transaction("engineer-implement") as w:
    w.set("key", value)          # upsert a key-value pair
    w.append_learning_event({    # insert learning event
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

# Sentinel issues (sentinel_origin=1) bypass YELLOW — they are human-directed work
# ALL issues (including sentinels) are blocked on RED
if throttle == "red":
    with sm.transaction("engineer-implement") as w:
        w.set("engineer.last_skip_reason", "throttle_red")
    return  # Hard stop — do nothing this cycle

# YELLOW: only dispatch sentinel issues this cycle
yellow_only = (throttle == "yellow")
```

### Step 2: Query Pipeline for Triaged and FixNeeded Issues

```python
from scripts.lacrimosa_pipeline import PipelineManager
pm = PipelineManager()

all_dispatchable = pm.query(states=["Triaged", "FixNeeded"])
# sentinel_origin=1 issues sort first automatically

if yellow_only:
    # Filter to sentinel issues only
    dispatchable = [i for i in all_dispatchable if i["sentinel_origin"] == 1]
else:
    dispatchable = all_dispatchable

print(f"Dispatchable issues: {len(dispatchable)} "
      f"({sum(1 for i in dispatchable if i['sentinel_origin']) } sentinel, "
      f"{sum(1 for i in dispatchable if not i['sentinel_origin'])} regular)")
```

### Step 3: Check Trust Tier Capacity

Read config to determine concurrency limits and per-PR file limits:

```bash
.venv/bin/python -c "
import yaml
with open('{project_root}/.claude/lacrimosa/config.yaml') as f:
    config = yaml.safe_load(f)
trust = config.get('trust_tier', {})
print('max_concurrent_workers:', trust.get('max_concurrent_workers', 3))
print('max_files_per_pr:', trust.get('max_files_per_pr', 20))
"
```

```python
from scripts.lacrimosa_pipeline import PipelineManager
pm = PipelineManager()

# Count currently active (Implementing) workers
active_implementing = pm.query(states=["Implementing"])
active_count = len(active_implementing)

# max_concurrent from config (default 3)
max_concurrent = sm.read("config.trust_tier.max_concurrent_workers") or 3
slots_available = max_concurrent - active_count

if slots_available <= 0:
    print(f"At capacity: {active_count}/{max_concurrent} workers active. Skipping dispatch.")
    # Still run Steps 5+6 to monitor active workers
```

### Step 4: Dispatch Workers for Each Issue (Sentinel First)

For each issue in `dispatchable` (up to `slots_available`):

#### 4a. Read Linear Issue — Description + ALL Comments

```bash
.venv/bin/python -c "
from scripts.lacrimosa_linear import get_issue_by_number, get_issue_comments
import json

issue = get_issue_by_number(123)  # replace with actual number
comments = get_issue_comments(issue['id'])
print(json.dumps({'issue': issue, 'comments': comments}, indent=2, default=str))
"
```

#### 4b. For FixNeeded Issues — Extract Review Feedback

```python
pipeline_row = pm.get_issue(identifier)
review_feedback = json.loads(pipeline_row.get("review_feedback") or "[]")
review_iteration = pipeline_row.get("review_iteration") or 0
# Pass review_feedback as context to worker prompt
```

#### 4c. Pre-Dispatch Validation Gate

Before dispatching, verify ALL conditions. SKIP the issue (do not fail it) if any check fails:

```bash
# Check 1: Linear status is not Done or Cancelled
.venv/bin/python -c "
from scripts.lacrimosa_linear import get_issue_by_number
import json
issue = get_issue_by_number(123)  # replace with actual issue number
state_name = issue.get('state', {}).get('name', '')
print('LINEAR_STATE:', state_name)
print('SKIP:', state_name in ['Done', 'Cancelled', 'Duplicate'])
"

# Check 2: No merged PR exists for this issue
gh pr list --state merged --search "{issue_prefix}-123" --json number,title,mergedAt

# Check 3: No active open PR exists
gh pr list --state open --search "{issue_prefix}-123" --json number,title,url

# Check 4 (CRITICAL): Analyze Linear comments for "no implementation needed" signals
.venv/bin/python -c "
from scripts.lacrimosa_linear import get_issue_by_number, get_issue_comments
import re

issue = get_issue_by_number(123)  # replace with actual issue number
comments = get_issue_comments(issue['id'])

# Scan ALL comments (newest first) for stop signals
STOP_PATTERNS = [
    r'already\s+(done|implemented|fixed|merged|shipped)',
    r'not\s+needed',
    r'no\s+(implementation|work|changes?)\s+(needed|required)',
    r'won.t\s+fix',
    r'duplicate\s+of',
    r'closing\s+(as|this)',
    r'this\s+is\s+(already|no\s+longer)',
    r'do\s+not\s+implement',
    r'skip\s+this',
    r'resolved\s+(by|in|via)',
    r'superseded\s+by',
]

for c in comments:
    body = (c.get('body') or '').lower()
    for pattern in STOP_PATTERNS:
        if re.search(pattern, body):
            author = c.get('user', {}).get('name', 'unknown')
            print(f'STOP_SIGNAL: \"{pattern}\" found in comment by {author}')
            print(f'COMMENT: {body}')
            print('SKIP: True')
            exit(0)

print('SKIP: False')
print('No stop signals in', len(comments), 'comments')
"
```

If Linear is Done/Cancelled → update pipeline to Done/Failed, post Linear comment explaining reconciliation.
If merged PR exists → transition to Done in pipeline, update Linear to Done.
If open PR exists → transition directly to ReviewPending (skip dispatch).
**If stop signal found in comments** → transition to Done/Failed in pipeline, post Linear comment: "Skipped — comment indicates no implementation needed: {signal}".

#### 4d. Dispatch Implementation Worker

For **Triaged** issues (fresh implementation):

```python
import uuid
worker_id = f"worker-{uuid.uuid4().hex[:8]}"
worktree_path = f"/tmp/lacrimosa/wt-{identifier.lower()}-{worker_id[:6]}"
output_file = f"/tmp/lacrimosa/worker-output-{worker_id}.txt"

agent = Agent(
    description=f"Implement {identifier}: {issue_title[:60]}",
    prompt=f"""
You are implementing Linear issue {identifier} for your product.

## Issue Details
Title: {issue_title}
Description:
{issue_description}

## Comments (MUST READ FIRST — may contain stop signals, corrections, or context)
{comments_text}

## Instructions

**STEP 0 (MANDATORY): Read ALL comments above BEFORE doing any work.**
If any comment says the work is already done, not needed, a duplicate, superseded,
or otherwise indicates no implementation is required — STOP IMMEDIATELY.
Write to the output file: `echo "WORKER_FAILED reason=no_implementation_needed: <quote the comment>" > {output_file}`
Do NOT proceed with implementation if comments tell you it's unnecessary.

1. Assign the issue to Lacrimosa:
   from scripts.lacrimosa_linear import assign_to_lacrimosa, get_issue_by_number
   issue = get_issue_by_number({issue_num})
   assign_to_lacrimosa(issue["id"])

2. Run the full implementation workflow:
   /team-implement {issue_num}
   This handles TDD, implementation, tests, and PR creation.

3. After PR is created, write your output to {output_file}:
   echo "WORKER_COMPLETE pr_number=<N> pr_url=<url>" > {output_file}

4. If you cannot complete (blocker, conflict, invalid issue), write:
   echo "WORKER_FAILED reason=<explanation>" > {output_file}

## Constraints
- Max {max_files_per_pr} files changed per PR (from trust tier config)
- You are in an isolated worktree — do NOT touch the main checkout
- All git operations happen in your worktree only
- Write output to {output_file} when done (required for monitoring)
""",
    mode="bypassPermissions",
    run_in_background=True,
    isolation="worktree",
)
```

For **FixNeeded** issues (addressing review feedback):

```python
worker_id = f"worker-fix-{uuid.uuid4().hex[:8]}"
worktree_path = f"/tmp/lacrimosa/wt-{identifier.lower()}-fix{review_iteration}-{worker_id[:6]}"
output_file = f"/tmp/lacrimosa/worker-output-{worker_id}.txt"

agent = Agent(
    description=f"Fix review feedback for {identifier} (iteration {review_iteration + 1})",
    prompt=f"""
You are fixing review feedback for Linear issue {identifier}.

## Issue Details
Title: {issue_title}
Description:
{issue_description}

## All Comments on This Issue (MUST READ FIRST)
{comments_text}

## Review Feedback to Address (iteration {review_iteration})
{json.dumps(review_feedback, indent=2)}

## Instructions

**STEP 0 (MANDATORY): Read ALL comments above BEFORE doing any work.**
If any comment says the work is already done, not needed, a duplicate, superseded,
or otherwise indicates no further work is required — STOP IMMEDIATELY.
Write: `echo "WORKER_FAILED reason=no_work_needed: <quote the comment>" > {output_file}`

1. Checkout the existing PR branch for {identifier} in this worktree
2. Read the review feedback above carefully
3. Fix EVERY issue listed in the feedback
4. Run tests to verify fixes don't break anything: ./run_unit_tests.sh
5. Commit fixes and push to the PR branch
6. Write output to {output_file}:
   echo "WORKER_COMPLETE pr_number=<existing_pr_N> pr_url=<url>" > {output_file}

If a fix is impossible or creates a deeper conflict, write:
   echo "WORKER_FAILED reason=<explanation>" > {output_file}

## Constraints
- You are in an isolated worktree — do NOT touch the main checkout
- Push to the EXISTING PR branch, do not open a new PR
- Address ALL review feedback items, not just the easy ones
""",
    mode="bypassPermissions",
    run_in_background=True,
    isolation="worktree",
)
```

#### 4e. Transition Issue to Implementing

After dispatch (agent object returned — extract worker ID from it):

```python
from scripts.lacrimosa_pipeline import PipelineManager, InvalidTransition, MissingProof
pm = PipelineManager()

try:
    pm.transition(
        identifier=identifier,
        from_state=current_state,   # "Triaged" or "FixNeeded"
        to_state="Implementing",
        owner="engineer-implement",
        proof={
            "worker_id": worker_id,
            "worktree_path": worktree_path,
        },
    )
    # Persist output_file path for monitoring
    with sm.transaction("engineer-implement") as w:
        workers = sm.read("engineer.active_workers") or {}
        workers[identifier] = {
            "worker_id": worker_id,
            "worktree_path": worktree_path,
            "output_file": output_file,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_seen_bytes": 0,
        }
        w.set("engineer.active_workers", workers)
    print(f"Dispatched worker {worker_id} for {identifier} -> Implementing")

except (InvalidTransition, MissingProof) as e:
    print(f"WARN: Failed to transition {identifier}: {e} — skipping")
```

Post a Linear comment confirming dispatch:

```bash
.venv/bin/python -c "
from scripts.lacrimosa_linear import create_comment, get_issue_by_number
issue = get_issue_by_number(123)  # replace
create_comment(issue['id'], '**Implementing** — dispatched worker $WORKER_ID in isolated worktree.')
"
```

### Step 5: Monitor Active Workers

Query pipeline for all Implementing issues and check their output files:

```python
from scripts.lacrimosa_pipeline import PipelineManager
pm = PipelineManager()

implementing = pm.query(states=["Implementing"])
workers = sm.read("engineer.active_workers") or {}
now = datetime.now(timezone.utc)

for issue in implementing:
    identifier = issue["identifier"]
    worker_info = workers.get(identifier)
    if not worker_info:
        # Worker started before this specialist tracked it — use pipeline row
        worker_info = {
            "worker_id": issue.get("worker_id", "unknown"),
            "output_file": f"/tmp/lacrimosa/worker-output-{issue.get('worker_id','unknown')}.txt",
            "started_at": issue.get("updated_at"),
            "last_seen_bytes": 0,
        }

    output_file = worker_info.get("output_file", "")
    started_at_str = worker_info.get("started_at", issue.get("updated_at", ""))
```

Check output file for completion signals:

```bash
# Check if output file exists and read its content
test -f "$OUTPUT_FILE" && cat "$OUTPUT_FILE" || echo "NO_OUTPUT_YET"
```

```python
import os

output_file = worker_info["output_file"]
if os.path.exists(output_file):
    content = open(output_file).read().strip()
    current_bytes = os.path.getsize(output_file)

    if content.startswith("WORKER_COMPLETE"):
        # Parse pr_number and pr_url from output
        # e.g. "WORKER_COMPLETE pr_number=456 pr_url=https://github.com/..."
        parts = dict(p.split("=", 1) for p in content.split()[1:] if "=" in p)
        pr_number = int(parts.get("pr_number", 0))
        pr_url = parts.get("pr_url", "")
        # Handle in Step 7 below
        worker_info["status"] = "complete"
        worker_info["pr_number"] = pr_number
        worker_info["pr_url"] = pr_url

    elif content.startswith("WORKER_FAILED"):
        worker_info["status"] = "failed"
        worker_info["failure_reason"] = content

    else:
        # Still running — update last seen bytes for stall detection
        worker_info["last_seen_bytes"] = current_bytes

else:
    # No output file yet — check elapsed time
    pass
```

### Step 6: Stall Detection

For each Implementing issue, compute elapsed time since last output change:

```python
from datetime import datetime, timezone
import os

for identifier, worker_info in workers.items():
    started_at_str = worker_info.get("started_at", "")
    output_file = worker_info.get("output_file", "")
    status = worker_info.get("status", "running")

    if status in ("complete", "failed"):
        continue  # Already handled

    # Compute minutes since last activity
    if os.path.exists(output_file):
        last_modified = datetime.fromtimestamp(os.path.getmtime(output_file), tz=timezone.utc)
        minutes_stalled = (datetime.now(timezone.utc) - last_modified).total_seconds() / 60
    elif started_at_str:
        started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        minutes_stalled = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
    else:
        continue

    STALL_THRESHOLD_MIN = 10

    if minutes_stalled > STALL_THRESHOLD_MIN:
        print(f"STALL DETECTED: {identifier} worker {worker_info['worker_id']} "
              f"no output for {minutes_stalled:.1f} min — terminating")

        # Get current error count from pipeline
        pipeline_row = pm.get_issue(identifier)
        error_count = (pipeline_row.get("error_count") or 0)
        retry_eligible = error_count < 3  # max 3 retries before escalation

        # Transition to Failed
        try:
            pm.transition(
                identifier=identifier,
                from_state="Implementing",
                to_state="Failed",
                owner="engineer-implement",
                proof={
                    "error_message": f"Worker stalled: no output for {minutes_stalled:.1f} min",
                    "retry_eligible": retry_eligible,
                },
            )
        except Exception as e:
            print(f"WARN: Could not transition {identifier} to Failed: {e}")
            continue

        # Remove from active workers tracking
        workers.pop(identifier, None)

        # Post Linear comment
        from scripts.lacrimosa_linear import create_comment, get_issue_by_number
        issue_data = get_issue_by_number(int(identifier.split("-")[1]))
        if issue_data:
            if retry_eligible:
                create_comment(issue_data["id"],
                    f"**Worker stalled** (no output for {minutes_stalled:.0f} min). "
                    f"Attempt {error_count + 1}/3 — will retry next cycle.")
            else:
                create_comment(issue_data["id"],
                    f"**Escalating** — worker stalled 3 times. Requires human review.")

        # Append learning event
        with sm.transaction("engineer-implement") as w:
            w.append_learning_event({
                "id": f"stall-{identifier}-{datetime.now(timezone.utc).isoformat()}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "worker_stall",
                "issue_id": identifier,
                "context": {
                    "worker_id": worker_info.get("worker_id"),
                    "minutes_stalled": minutes_stalled,
                    "error_count": error_count,
                    "retry_eligible": retry_eligible,
                }
            })
```

### Step 7: Handle Completed Workers → Transition to ReviewPending

For each worker with `status == "complete"`:

```python
for identifier, worker_info in workers.items():
    if worker_info.get("status") != "complete":
        continue

    pr_number = worker_info.get("pr_number")
    pr_url = worker_info.get("pr_url", "")

    # Verify PR actually exists before transitioning
    import subprocess
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "number,url,state"],
        capture_output=True, text=True,
        cwd="{project_root}"
    )

    if result.returncode != 0 or not result.stdout.strip():
        print(f"WARN: Worker for {identifier} claimed PR #{pr_number} but gh pr view failed. "
              f"Keeping in Implementing state — will recheck next cycle.")
        worker_info["status"] = "running"  # Reset to recheck
        continue

    import json as _json
    pr_data = _json.loads(result.stdout)
    if pr_data.get("state") not in ("OPEN", "open"):
        print(f"WARN: PR #{pr_number} for {identifier} is not open (state={pr_data.get('state')})")
        worker_info["status"] = "running"
        continue

    # Transition Implementing → ReviewPending
    try:
        pm.transition(
            identifier=identifier,
            from_state="Implementing",
            to_state="ReviewPending",
            owner="engineer-implement",
            proof={
                "pr_number": pr_number,
                "pr_url": pr_url or pr_data.get("url", ""),
            },
        )
        print(f"Transitioned {identifier} to ReviewPending (PR #{pr_number})")

        # Remove from active workers tracking
        workers.pop(identifier, None)

        # Post Linear comment
        from scripts.lacrimosa_linear import create_comment, get_issue_by_number
        issue_data = get_issue_by_number(int(identifier.split("-")[1]))
        if issue_data:
            create_comment(issue_data["id"],
                f"**PR created** — [#{pr_number}]({pr_url}) ready for review.")

    except Exception as e:
        print(f"ERROR: Could not transition {identifier} to ReviewPending: {e}")
```

### Step 8: Adaptive Work Check

If all slots are full and no workers completed this cycle, check if any Triaged issues were skipped due to capacity. Log for observability:

```python
total_triaged = len(pm.query(states=["Triaged"]))
total_fix_needed = len(pm.query(states=["FixNeeded"]))
total_implementing = len(pm.query(states=["Implementing"]))

with sm.transaction("engineer-implement") as w:
    w.set("engineer.queue_depth", {
        "triaged": total_triaged,
        "fix_needed": total_fix_needed,
        "implementing": total_implementing,
        "slots_available": max(0, max_concurrent - total_implementing),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })
```

If `total_triaged + total_fix_needed > 0` and `slots_available == 0`, this is normal — log it and wait. Do NOT increase concurrency beyond trust tier config.

### Step 9: Update State + End Cycle

```python
with sm.transaction("engineer-implement") as w:
    w.set("engineer.active_workers", workers)  # persist updated worker map
    w.set("engineer.last_cycle", datetime.now(timezone.utc).isoformat())
# Heartbeat auto-updated by transaction commit.
```

End cycle. `/loop 10m` will trigger the next cycle.

## Safety Rules

- **ALL dispatched agents MUST use `isolation="worktree"`** — no exceptions
- **NEVER dispatch foreground (blocking) agents** — all `run_in_background=True`
- **Sentinel issues (`sentinel_origin=1`) bypass YELLOW throttle** — they are human-directed and high-priority; they are still blocked on RED
- **Pipeline transitions ONLY via `pm.transition()`** — never write `issue_pipeline` rows directly via SQL
- **Pre-dispatch validation is mandatory per issue** — skip (don't fail) issues that fail validation
- **Stall threshold is 10 minutes** — terminate and transition to Failed after 10 min no output
- **Max 3 retries before escalation** — track via `error_count` column in pipeline row
- **Verify PR exists via `gh pr view`** before transitioning to ReviewPending — never trust worker output alone
- **Linear writes via `lacrimosa_linear.py` only** — never MCP for writes
- **All state writes via `sm.transaction("engineer-implement")`**
- **Context managed by loop cadence** — no manual clearing needed; `/loop 10m` handles it
- **Read ALL Linear comments before dispatching** — humans post corrections and blockers
- **FixNeeded issues get review_feedback from pipeline row** — always pass it explicitly to fix workers

<!-- Known limitation: if the main specialist process crashes mid-dispatch, the worker continues running
     in its own context. On restart, Step 5 monitoring will detect and handle via stall detection. -->
