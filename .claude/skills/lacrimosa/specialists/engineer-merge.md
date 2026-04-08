# Engineer-Merge — Merge Queue + Post-Merge Verification

> Loaded by `/lacrimosa-specialist engineer-merge`. Runs every 10m via `/loop 10m`.
> Owns the final stretch: MergeReady → Merging → Verifying → Done.
> Engineering hands off here; engineer-merge owns everything from rebase to Linear Done.

## CRITICAL: Linear API — NEVER use MCP tools

**ALL Linear operations MUST go through `scripts/lacrimosa_linear.py` via Bash.**
**NEVER use `mcp__linear-server__*` tools.** MCP authenticates as the USER, not Lacrimosa.

```bash
# CORRECT — uses Lacrimosa's API key
.venv/bin/python -c "from scripts.lacrimosa_linear import create_comment, create_issue, _graphql; ..."
# WRONG — wrong user attribution
mcp__linear-server__linear_create_issue(...)
```

Available: `_graphql(query, vars)`, `create_issue(title, desc, team_id, priority)`, `create_comment(issue_id, body)`, `get_issue_by_number(num)`, `assign_to_lacrimosa(id)`, `update_issue_state(id, state_uuid)`, `update_issue_project(id, proj_id)`.

## CRITICAL: Merge Operations in WORKTREE — Never Touch Main Checkout

**NEVER `git checkout`, `git branch`, or `git switch` on the main repo checkout.**
`{project_root}` MUST stay on `main` at all times.
Multiple specialists share this checkout — any branch switch corrupts parallel work.

**ALL merge operations use a temp worktree:**
```bash
# Create worktree on the PR branch
git -C {project_root} worktree add /tmp/lacrimosa/merge-{issue} {pr_branch}

# All rebase/push ops run inside the worktree — NEVER in the main checkout
cd /tmp/lacrimosa/merge-{issue} && git rebase origin/main

# Remove after merge
git -C {project_root} worktree remove /tmp/lacrimosa/merge-{issue} --force
```

## Pipeline API Reference

```python
from scripts.lacrimosa_pipeline import PipelineManager
pm = PipelineManager()

# Query issues in one or more pipeline states
issues = pm.query(states=["MergeReady"])
issues = pm.query(states=["Verifying"])

# Get a single issue by identifier (e.g. "{issue_prefix}-42")
issue = pm.get_issue("{issue_prefix}-42")
# Returns: {identifier, linear_id, state, pr_number, worker_id, worktree_path,
#           sentinel_origin, proof, error_count, review_iteration, ...}

# FSM-validated transition (raises InvalidTransition or MissingProof on violation)
pm.transition(
    identifier="{issue_prefix}-42",
    from_state="MergeReady",
    to_state="Merging",
    owner="engineer-merge",
    proof={"rebase_clean": True, "ci_status": "success"},
)

# Proof keys required per transition (enforced by the FSM):
# MergeReady  → Merging:    rebase_clean, ci_status
# Merging     → Verifying:  merge_sha, merged_at
# Merging     → Failed:     error_message, retry_eligible
# Verifying   → Done:       verification_result, linear_status_updated
# Verifying   → Failed:     error_message, retry_eligible
```

## StateManager API Reference

```python
from scripts.lacrimosa_state_sqlite import StateManager
sm = StateManager()

# READ
sm.read("key")                      # single value (returns None if missing)
sm.read()                           # full state as nested dict
sm.read_prefix("merge.*")           # all keys matching prefix
sm.get_specialist_health()          # all specialist health rows

# WRITE (must use transaction context manager)
with sm.transaction("engineer-merge") as w:
    w.set("key", value)             # upsert a key-value pair
    w.append_learning_event({       # insert learning event
        "id": "...", "timestamp": "...", "event_type": "...",
        "issue_id": "...", "context": {}
    })
# Transaction auto-updates specialist heartbeat on commit
```

## Cycle Steps

### Step 1: Throttle Check (Sentinel Bypass)

```python
from scripts.lacrimosa_state_sqlite import StateManager
from scripts.lacrimosa_pipeline import PipelineManager
sm = StateManager()
pm = PipelineManager()

throttle = sm.read("rate_limits.throttle_level")

# Sentinel issues always merge — they bypass throttle
sentinel_ready = pm.query(states=["MergeReady"], sentinel_only=True)
if throttle == "red" and not sentinel_ready:
    with sm.transaction("engineer-merge") as w:
        w.set("merge.last_skip_reason", "throttle_red")
    # End cycle — skip all non-sentinel work
    exit()
```

### Step 2: Query Pipeline for MergeReady Issues

```python
merge_ready = pm.query(states=["MergeReady"])
# Each item: {identifier, linear_id, state, pr_number, ...}
# pr_number is the GitHub PR number stored during ReviewPending → MergeReady transition
```

If no `merge_ready` issues and no `Verifying` issues → end cycle early.

### Step 3: Build Merge Dependency Graph

```python
import subprocess, json
from scripts.lacrimosa_merge_graph import build_merge_graph, get_mergeable

# Enrich each issue with the list of files changed in its PR
pr_data = []
for issue in merge_ready:
    pr_num = issue["pr_number"]
    if not pr_num:
        continue
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_num), "--json", "files,headRefName,number"],
        capture_output=True, text=True,
        cwd="{project_root}",
    )
    pr_json = json.loads(result.stdout)
    files = [f["path"] for f in pr_json.get("files", [])]
    pr_data.append({
        "identifier": issue["identifier"],
        "pr": pr_num,
        "branch": pr_json.get("headRefName", ""),
        "files": files,
    })

# Build graph: independent PRs → "ready", overlapping → "blocked"
graph = build_merge_graph(pr_data)
# Returns: [{pr, files, depends_on, status}, ...]

# Enrich graph entries with identifier for later lookups
id_by_pr = {d["pr"]: d["identifier"] for d in pr_data}

# Get PRs that are safe to merge this cycle (no unmerged dependencies)
mergeable = get_mergeable(graph)
# Cap at 3 per cycle to avoid flooding CI
mergeable = mergeable[:3]
```

### Step 4: Merge Each Eligible PR

For each PR in `mergeable` (up to 3):

#### 4a. Create Temp Worktree

```bash
ISSUE={issue_prefix}-42
BRANCH={issue_prefix_lower}-42-add-feature
WORKTREE=/tmp/lacrimosa/merge-{issue_prefix}-42

# Fetch latest remote refs first
git -C {project_root} fetch origin

# Create worktree checked out to the PR branch
git -C {project_root} worktree add $WORKTREE $BRANCH
```

#### 4b. Rebase onto Origin/Main

```bash
cd $WORKTREE && git rebase origin/main
# Exit code 0 = clean rebase
# Non-zero = conflicts
```

#### 4c. Handle Rebase Outcome

**If rebase conflicts (non-zero exit):**
```bash
# Abort cleanly
cd $WORKTREE && git rebase --abort

# Close the PR with a conflict note
gh pr close $PR_NUM --comment "Auto-merge aborted: rebase conflict with main. Re-dispatching." \
    --repo {github_org}/{github_repo}

# Remove worktree
git -C {project_root} worktree remove $WORKTREE --force
```

```python
# Transition to Failed
pm.transition(
    identifier=issue["identifier"],
    from_state="MergeReady",
    to_state="Failed",
    owner="engineer-merge",
    proof={
        "error_message": "Rebase conflict with main — re-dispatch required",
        "retry_eligible": True,
    },
)

# Post Linear comment
from scripts.lacrimosa_linear import create_comment
create_comment(issue["linear_id"], "**Merge failed**: rebase conflict with `main`. PR closed. Re-dispatching.")
```

Skip to next PR in the loop.

**If rebase clean (exit 0):**
```bash
# Push rebased branch — force-with-lease is safe (we own the worktree)
cd $WORKTREE && git push --force-with-lease
```

#### 4d. Wait for CI

```python
import subprocess, time, json

MAX_WAIT_SECONDS = 600  # 10 minutes
POLL_INTERVAL = 30
elapsed = 0
ci_status = None

while elapsed < MAX_WAIT_SECONDS:
    result = subprocess.run(
        ["gh", "pr", "checks", str(pr_num), "--json", "name,status,conclusion"],
        capture_output=True, text=True,
        cwd="{project_root}",
    )
    checks = json.loads(result.stdout) if result.returncode == 0 else []
    pending = [c for c in checks if c["status"] in ("queued", "in_progress")]
    failed  = [c for c in checks if c["conclusion"] in ("failure", "cancelled", "timed_out")]
    passed  = [c for c in checks if c["conclusion"] == "success"]

    if failed:
        ci_status = "failure"
        break
    if not pending and passed:
        ci_status = "success"
        break

    time.sleep(POLL_INTERVAL)
    elapsed += POLL_INTERVAL
else:
    ci_status = "timeout"
```

**If CI failed or timed out:**
```python
pm.transition(
    identifier=issue["identifier"],
    from_state="MergeReady",
    to_state="Failed",
    owner="engineer-merge",
    proof={
        "error_message": f"CI {ci_status} after rebase — re-dispatch required",
        "retry_eligible": True,
    },
)
from scripts.lacrimosa_linear import create_comment
create_comment(issue["linear_id"], f"**Merge failed**: CI status `{ci_status}` after rebase. Re-dispatching.")
# Remove worktree
import subprocess
subprocess.run(
    ["git", "worktree", "remove", worktree_path, "--force"],
    cwd="{project_root}",
)
```

Skip to next PR.

#### 4e. Transition MergeReady → Merging

```python
# CI is green — claim the merge slot
pm.transition(
    identifier=issue["identifier"],
    from_state="MergeReady",
    to_state="Merging",
    owner="engineer-merge",
    proof={
        "rebase_clean": True,
        "ci_status": "success",
    },
)
```

#### 4f. Squash Merge

```bash
gh pr merge $PR_NUM --squash --delete-branch --repo {github_org}/{github_repo}
```

Capture the merge SHA:
```bash
# Get the merge commit SHA from the PR after merge
gh pr view $PR_NUM --json mergeCommit --jq '.mergeCommit.oid'
```

```python
import subprocess, json
from datetime import datetime, timezone

result = subprocess.run(
    ["gh", "pr", "view", str(pr_num), "--json", "mergeCommit,mergedAt"],
    capture_output=True, text=True,
    cwd="{project_root}",
)
pr_info = json.loads(result.stdout)
merge_sha = pr_info.get("mergeCommit", {}).get("oid", "unknown")
merged_at = pr_info.get("mergedAt") or datetime.now(timezone.utc).isoformat()
```

#### 4g. Transition Merging → Verifying

```python
pm.transition(
    identifier=issue["identifier"],
    from_state="Merging",
    to_state="Verifying",
    owner="engineer-merge",
    proof={
        "merge_sha": merge_sha,
        "merged_at": merged_at,
    },
)
```

#### 4h. Cleanup Worktree

```bash
git -C {project_root} worktree remove $WORKTREE --force
```

```python
# Mark this PR as merged in the graph for subsequent dependency resolution
for entry in graph:
    if entry["pr"] == pr_num:
        entry["status"] = "merged"
        break
```

#### 4i. Nudge COO

```bash
tmux send-keys -t lacrimosa-coo "PR #$PR_NUM merged for $IDENTIFIER ($MERGE_SHA)" Enter
```

### Step 5: Verify Merged Issues (Verifying State)

```python
verifying = pm.query(states=["Verifying"])
```

For each issue in `verifying`:

#### 5a. Determine if Staging Verification is Needed

```python
import subprocess, json

result = subprocess.run(
    ["gh", "pr", "view", str(issue["pr_number"]), "--json", "files"],
    capture_output=True, text=True,
    cwd="{project_root}",
)
pr_files = [f["path"] for f in json.loads(result.stdout).get("files", [])]

# Docs/config only → auto-verify (no staging needed)
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css"}
SKIP_DIRS = {"docs/", ".claude/", "scripts/lacrimosa"}

needs_staging = any(
    any(f.endswith(ext) for ext in CODE_EXTENSIONS)
    and not any(f.startswith(skip) for skip in SKIP_DIRS)
    for f in pr_files
)
```

#### 5b-i. Auto-Verify (Docs/Config Only)

```python
if not needs_staging:
    verification_result = "auto-verified: docs/config only — no runtime impact"
    linear_comment = "Merged. Verification skipped (docs/config only — no runtime impact)."
```

#### 5b-ii. Staging Verification (Code Changes)

Dispatch a verification subagent:

```python
from anthropic import Agent

Agent(
    description=f"Staging verify {issue_prefix}-{issue_num} post-merge",
    prompt=f"""
    Issue {issue_prefix}-{issue_num} was just merged (SHA: {merge_sha}).

    Run post-merge staging verification:
    1. Deploy staging: ./infra/deploy-staging-fresh.sh
    2. Identify the feature/fix from the PR description (pr #{pr_num})
    3. Verify it works on staging — positive (happy path) AND negative (error path) tests
    4. Use chrome-devtools MCP for any UI verification (load tools via ToolSearch first)
    5. Return: VERIFIED with evidence | REJECTED with specific failures

    Verification scope from PR files: {pr_files}
    """,
    mode="bypassPermissions",
    run_in_background=True,
    isolation="worktree",
)
# Store agent output path in state for polling next cycle
```

Poll the verification agent next cycle. When complete:

```python
# verification_result = agent output ("VERIFIED ..." or "REJECTED ...")
```

**If REJECTED:**
```python
pm.transition(
    identifier=issue["identifier"],
    from_state="Verifying",
    to_state="Failed",
    owner="engineer-merge",
    proof={
        "error_message": f"Staging verification failed: {rejection_reason}",
        "retry_eligible": False,  # Needs human review — regression
    },
)
from scripts.lacrimosa_linear import create_comment
create_comment(issue["linear_id"],
    f"**Staging verification FAILED** after merge.\n\n"
    f"Failures: {rejection_reason}\n\n"
    f"Merge SHA: `{merge_sha}` — this is live on main. Human review required."
)
# Escalate to human via tmux
import subprocess
subprocess.run(
    ["tmux", "send-keys", "-t", "lacrimosa-coo",
     f"ALERT: post-merge verification failed for {issue['identifier']} ({merge_sha})", "Enter"]
)
continue
```

#### 5c. Transition Verifying → Done

```python
# Update Linear status to Done first
from scripts.lacrimosa_linear import get_issue_by_number, update_issue_state

linear_issue = get_issue_by_number(int(issue["identifier"].replace("{issue_prefix}-", "")))

# Get Done state UUID
done_query = '''
query {
  workflowStates(filter: { name: { eq: "Done" } }) {
    nodes { id name team { name } }
  }
}
'''
states_result = _graphql(done_query)
done_states = states_result.get("workflowStates", {}).get("nodes", [])
if done_states:
    update_issue_state(linear_issue["id"], done_states[0]["id"])

pm.transition(
    identifier=issue["identifier"],
    from_state="Verifying",
    to_state="Done",
    owner="engineer-merge",
    proof={
        "verification_result": verification_result,
        "linear_status_updated": True,
    },
)
```

#### 5d. Post Completion Comment

```python
from scripts.lacrimosa_linear import create_comment

create_comment(
    linear_issue["id"],
    f"**Done** ✓\n\n"
    f"Merged: `{merge_sha}`\n"
    f"Verification: {verification_result}\n\n"
    f"Cycle complete."
)
```

### Step 6: Nudge COO on Completions

For each issue transitioned to Done this cycle:
```bash
tmux send-keys -t lacrimosa-coo "{issue_prefix}-$NUM Done — verified and closed ($MERGE_SHA)" Enter
```

### Step 7: Update State + End Cycle

```python
from datetime import datetime, timezone

with sm.transaction("engineer-merge") as w:
    w.set("merge.last_cycle", datetime.now(timezone.utc).isoformat())
    w.set("merge.merges_this_cycle", len(merged_this_cycle))
    w.set("merge.verified_this_cycle", len(verified_this_cycle))
```

Heartbeat auto-updated by transaction commit.
```bash
```
This clears conversation history between cycles. Cron jobs survive `/clear`.

## Safety Rules

- Merge ops in worktree ONLY — never touch `{project_root}` branch state
- NEVER `git checkout`, `git branch`, or `git switch` on the main repo checkout
- Up to 3 merges per cycle — do not exceed; CI queue overflow causes flakiness
- Always cleanup worktree after merge, even on failure (`--force` flag handles stuck states)
- Sentinel issues bypass RED throttle — they always merge
- Linear writes via `lacrimosa_linear.py` only (never MCP for writes)
- All state writes via `sm.transaction("engineer-merge")`
- CI timeout (10m) → Failed, not indefinite wait
- Post-merge verification failure → Failed + human alert (never silently pass a regression)
- Read ALL existing comments before posting on an issue — avoid duplicate completion comments
- Context managed by loop cadence — no manual clearing needed
