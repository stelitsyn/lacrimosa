# Content Specialist — SEO Content Creation

> Loaded by `/lacrimosa-specialist content`. Runs every 24h via one-shot `claude -p` in a shell loop.
> GREEN throttle only — completely blocked on YELLOW and RED. SEO content is never urgent.
> Dispatches content work via `/team-implement` — same pipeline as regular engineering.

## CRITICAL: Worktree Isolation (MANDATORY)

**ALL dispatched agents MUST use `isolation="worktree"`.**
The main checkout MUST stay on `main`. Never `git checkout` or create branches on it.
Content specialist agents inherit the current branch — without worktree isolation, they corrupt parallel work.

## CRITICAL: Linear API — NEVER use MCP tools

**ALL Linear operations MUST go through `scripts/lacrimosa_linear.py` via Bash.**
**NEVER use `mcp__linear-server__*` tools.** MCP authenticates as the USER, not Lacrimosa.

```bash
# CORRECT
.venv/bin/python -c "from scripts.lacrimosa_linear import create_comment; create_comment(issue_id, body)"
# WRONG — wrong user attribution
mcp__linear-server__linear_create_comment(...)
```

## StateManager API Reference (EXACT methods — do NOT guess)

```python
from scripts.lacrimosa_state_sqlite import StateManager
sm = StateManager()

# READ
sm.read("key")                  # single value (returns None if missing)
sm.read()                       # full state as nested dict
sm.read_prefix("content_creation.*")  # all keys matching prefix
sm.get_specialist_health()      # all specialist health rows → dict[name, dict]

# WRITE (must use transaction context manager)
with sm.transaction("content") as w:
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

### 1. Throttle Check

```python
from scripts.lacrimosa_state_sqlite import StateManager

sm = StateManager()
throttle = sm.read("rate_limits.throttle_level")

if throttle != "green":
    # Skip entire cycle — content is never urgent
    # Log: "Content cycle skipped — throttle is {throttle}"
    # Heartbeat still updates (cycle ran, just had nothing to do)
    with sm.transaction("content") as w:
        w.set("content_creation.last_skip_reason", f"throttle_{throttle}")
    # End cycle
    return
```

### 2. Query Content Issues from Linear

```python
import yaml
config = yaml.safe_load(open(config_path))
cc_config = config.get("content_creation", {})

# Search Linear for SEO/content issues:
# - Labels containing: SEO, Content, Blog (from cc_config.search_labels)
# - Project: "Marketing" (from cc_config.search_project)
# - State: Backlog or Todo
# - Unassigned or assigned to Lacrimosa
# - Title containing: blog post, landing page, comparison page, content page, seo article
#   (from cc_config.types)

# Use MCP for reads:
# mcp__linear-server__linear_search_issues(query=..., states=["Backlog", "Todo"])
```

### 3. Pick Issues to Dispatch

```python
max_dispatch = cc_config.get("max_per_cycle", 5)

# Sort by priority (highest first)
# Filter: only autonomous domain issues (Marketing)
# Take up to max_dispatch
candidates = sorted(issues, key=lambda i: i["priority"], reverse=True)[:max_dispatch]
```

### 4. Dispatch via /team-implement

```python
for issue in candidates:
    issue_num = issue["identifier"]  # e.g., "{issue_prefix}-445"

    Agent(
        description=f"Content: {issue_num} — {issue['title'][:50]}",
        prompt=f"/team-implement {issue_num}",
        mode="bypassPermissions",
        run_in_background=True,
        isolation="worktree",
    )

    # Update state
    with sm.transaction("content") as w:
        w.set(f"content_creation.dispatched.{issue_num}", {
            "dispatched_at": now_iso,
            "title": issue["title"],
        })

    # Comment on Linear issue (as Lacrimosa)
    from scripts.lacrimosa_linear import create_comment
    create_comment(issue["id"], "**Lacrimosa:** Dispatched for content creation")
```

### 5. Monitor Dispatched Workers & Create PRs

Check active workers and **create PRs for completed work**:

```python
# Read state.content_creation.dispatched
# For each dispatched issue:
#   - If still running: skip
#   - If stalled (>30 min): log warning
#   - If completed WITH PR: log result, update state
#   - If completed WITHOUT PR (branch has commits): CREATE PR (see below)

# Creating PRs for completed worktree branches:
for kal, info in dispatched.items():
    if info.get("status") == "completed" and not info.get("pr"):
        branch = info["branch"]
        # Push branch, create PR
        # git -C <worktree_path> push -u origin <branch>
        # gh pr create --head <branch> --title "{issue_prefix}-XXX: <title>" --body "..."
        # Update state with PR number
```

**Content specialist MUST create PRs** for all completed work that doesn't already have one.
Engineering specialist handles review → merge, but PR creation is content's responsibility.

**PR format:**
- Title: `{issue_prefix}-XXX: <issue title>`
- Body: Summary of changes, files modified, SEO preservation notes
- Labels: `content`, `seo` (if applicable)

### 6. Update Metrics

```python
with sm.transaction("content") as w:
    w.set("content_creation.last_run", now_iso)
    w.set("content_creation.metrics", {
        "issues_dispatched_today": len(candidates),
        "issues_completed_today": completed_count,
        "issues_failed_today": failed_count,
        "last_cycle_duration_ms": duration_ms,
    })
```

### 7. End Cycle

Heartbeat auto-updated by `sm.transaction("content")` commit. 
```bash
```
This clears conversation history between cycles. Cron jobs survive `/clear`.

## What Counts as SEO Content Work

- Blog posts (educational content, comparison pages, how-to guides)
- Landing pages (feature pages, use-case pages, audience pages)
- Programmatic SEO pages (template-based location/keyword pages)
- Content cluster expansion (adding to existing topic clusters)

## Safety Rules

- Linear writes via `lacrimosa_linear.py` only (never MCP for writes)
- All state writes via `sm.transaction("content")`
- GREEN throttle only — skip on YELLOW/RED
- Context managed by loop cadence — no manual clearing needed
- The content dispatch uses the same `/team-implement` pipeline as regular engineering — it gets TDD, review, staging verification, the full workflow
