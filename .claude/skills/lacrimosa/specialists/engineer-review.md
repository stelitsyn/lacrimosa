# Engineer Review Specialist — PR Review Only

> Loaded by `/lacrimosa-specialist engineer-review`. Runs every 10m via `/loop 10m`.
> **READ-ONLY REVIEWER.** This specialist invokes the review skill, posts verdicts, and
> transitions pipeline states. It NEVER writes code, NEVER modifies files, NEVER creates branches.
> Blocked on RED throttle only. GREEN and YELLOW: operate normally.

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
- `get_issue_by_number(num)` — read issue by {issue_prefix}-N number
- `get_issue_comments(issue_id)` — read all comments on an issue
- `update_issue_state(issue_id, state_uuid)` — change Linear status
- `assign_to_lacrimosa(issue_id)` — assign to Lacrimosa

## CRITICAL: No Git Mutations, No Code Writing

**NEVER `git checkout`, `git branch`, `git switch`, `git commit`, `git push` on ANY repo.**
**NEVER write, edit, or create source files.** This specialist is review-only.

If the review finds issues, those issues go into `FixNeeded` in the pipeline and are
addressed by a fix subagent dispatched by the Engineering specialist — not by this specialist.

- All dispatched subagents MUST use `isolation="worktree"` parameter
- No file writes, no code changes, no test runs that produce artifacts
- Read-only: `gh pr view`, `gh pr list`, Linear reads, state reads

## Pipeline API Reference

```python
from scripts.lacrimosa_pipeline import PipelineManager

pm = PipelineManager()

# Query issues in specific states — sentinel (human-created) issues sort first
issues = pm.query(states=["ReviewPending"])
issues = pm.query(states=["ReviewPending", "Reviewing"])

# Get a single issue by identifier (e.g. "{issue_prefix}-42")
issue = pm.get_issue("{issue_prefix}-42")
# Returns dict with fields: identifier, linear_id, state, pr_number, pr_url,
#   review_iteration, review_feedback, worker_id, worktree_path, owner,
#   proof (JSON string), sentinel_origin, created_at, updated_at
# Returns None if not found.

# Transition FSM state — raises InvalidTransition or MissingProof on failure
pm.transition(
    identifier="{issue_prefix}-42",
    from_state="ReviewPending",
    to_state="Reviewing",
    owner="engineer-review",
    proof={"reviewer_agent_id": "agent-abc123"},
)
```

**Valid review-domain transitions and required proof keys:**

| From → To | Required proof keys |
|-----------|---------------------|
| `ReviewPending` → `Reviewing` | `reviewer_agent_id` |
| `Reviewing` → `MergeReady` | `review_verdict`, `linear_comment_id` |
| `Reviewing` → `FixNeeded` | `issues_list` (non-empty list), `linear_comment_id` |
| `Reviewing` → `Escalated` | `escalation_reason`, `linear_comment_id` |

## StateManager API Reference

```python
from scripts.lacrimosa_state_sqlite import StateManager
sm = StateManager()

# READ
sm.read("key")                    # single value (returns None if missing)
sm.read()                         # full state as nested dict
sm.read_prefix("review.*")        # all keys matching prefix

# WRITE (must use transaction context manager)
with sm.transaction("engineer-review") as w:
    w.set("key", value)           # upsert a key-value pair
    w.append_learning_event({     # insert learning event
        "id": "...", "timestamp": "...", "event_type": "...",
        "issue_id": "...", "context": {}
    })
# Transaction auto-updates specialist heartbeat on commit

# Review cycles table (direct SQLite — via StateManager connection is not exposed)
# Use PipelineManager for all pipeline state. Use StateManager for kv/learning.
```

## Cycle Steps

### Step 1: Throttle Check — Sentinel Bypass

```python
from scripts.lacrimosa_state_sqlite import StateManager
from scripts.lacrimosa_pipeline import PipelineManager

sm = StateManager()
pm = PipelineManager()

throttle = sm.read("rate_limits.throttle_level")

# Sentinel (human-escalated) issues bypass throttle entirely
sentinel_issues = pm.query(states=["ReviewPending"], sentinel_only=True)
if throttle == "red" and not sentinel_issues:
    with sm.transaction("engineer-review") as w:
        w.set("engineer_review.last_skip_reason", "throttle_red")
    # End cycle — no work when RED and no sentinel issues
    return
```

### Step 2: Query Pipeline for ReviewPending Issues

```python
# Get all issues awaiting review (sentinel issues sort first)
pending = pm.query(states=["ReviewPending"])

if not pending:
    # No work — update heartbeat and end cycle
    with sm.transaction("engineer-review") as w:
        w.set("engineer_review.last_cycle_result", "no_pending")
    return

# Process ONE issue per cycle to avoid review queue pile-up
# Sentinel issues already sort first via query() — pick the head
issue = pending[0]
```

### Step 3: Process Each Issue

For each issue (process one at a time — see Safety Rules):

#### 3a. Read the PR

```bash
# Get PR metadata including changed files, additions, deletions
gh pr view {pr_number} --json number,title,body,state,files,additions,deletions,commits,headRefName,baseRefName,url
```

```python
import subprocess, json

pr_number = issue["pr_number"]
result = subprocess.run(
    ["gh", "pr", "view", str(pr_number),
     "--json", "number,title,body,state,files,additions,deletions,commits,headRefName,baseRefName,url"],
    capture_output=True, text=True, cwd="{project_root}"
)
pr_data = json.loads(result.stdout)
```

#### 3b. Read Linear Issue for Acceptance Criteria

```python
from scripts.lacrimosa_linear import get_issue_by_number, get_issue_comments

# Extract issue number from identifier (e.g. "{issue_prefix}-42" → 42)
issue_num = int(issue["identifier"].split("-")[1])
linear_issue = get_issue_by_number(issue_num)

# Read ALL comments — acceptance criteria may be in comments, not just description
comments = get_issue_comments(linear_issue["id"])
```

Acceptance criteria are typically in `linear_issue["description"]` plus any comments
authored by the project owner. Extract them to pass context to the review subagent.

#### 3c. Read Previous Review Comments (if re-review)

```python
review_iteration = issue.get("review_iteration") or 0

if review_iteration > 0:
    # Re-review: fetch previous review findings from Linear comments
    # These were posted by this specialist in the prior iteration
    prior_feedback_raw = issue.get("review_feedback") or "[]"
    try:
        prior_issues = json.loads(prior_feedback_raw)
    except Exception:
        prior_issues = []
    # Pass prior_issues to the review subagent so it can verify fixes
```

#### 3d. Transition ReviewPending → Reviewing

Generate a unique agent ID for this review job, then transition:

```python
import uuid
from datetime import datetime, timezone

reviewer_agent_id = f"review-{issue['identifier']}-iter{review_iteration + 1}-{uuid.uuid4().hex[:8]}"

pm.transition(
    identifier=issue["identifier"],
    from_state="ReviewPending",
    to_state="Reviewing",
    owner="engineer-review",
    proof={"reviewer_agent_id": reviewer_agent_id},
)
```

#### 3e. Invoke the Review Skill via Subagent

Delegate to a subagent — review can be slow (multi-reviewer plugin) and must not block the loop:

```python
Agent(
    description=f"Review PR #{pr_number} for {issue['identifier']} (iteration {review_iteration + 1})",
    prompt=f"""
You are a review subagent. Your ONLY job is to review PR #{pr_number} and return a verdict.
Do NOT write code. Do NOT modify files. Do NOT commit or push anything.

## Context
- Issue: {issue['identifier']}
- PR URL: {pr_data.get('url', '')}
- PR title: {pr_data.get('title', '')}
- Files changed: {len(pr_data.get('files', []))} files, +{pr_data.get('additions', 0)}/-{pr_data.get('deletions', 0)} lines
- Review iteration: {review_iteration + 1}
- Acceptance criteria from Linear:
{linear_issue.get('description', '(none)')}

{'## Prior Review Issues (verify these are fixed)' + chr(10) + json.dumps(prior_issues, indent=2) if review_iteration > 0 else ''}

## Instructions
1. Read the PR diff:
   gh pr diff {pr_number} --repo {github_org}/{github_repo}

2. If iteration > 0: verify each issue from the prior review list is addressed in the new commits.
   Check commit messages and diff for evidence of each fix.

3. Invoke the multi-agent review skill:
   Skill(skill="pr-review-toolkit:review-pr", args="{pr_number}")

4. Parse the skill output. Determine final verdict:
   - APPROVED: all reviewers pass, no blocking issues
   - CHANGES_REQUESTED: one or more reviewers found blocking issues

5. Return a JSON result (write to stdout):
{{
  "verdict": "APPROVED" | "CHANGES_REQUESTED",
  "issues": [  // empty if APPROVED
    {{
      "severity": "critical|high|medium|low",
      "reviewer": "code-reviewer|architecture-reviewer|security-officer|design-reviewer|silent-failure-hunter",
      "file": "path/to/file.py or null",
      "line": 42 or null,
      "description": "Specific description of the problem",
      "suggestion": "Specific fix suggestion"
    }}
  ],
  "summary": "One-sentence summary of the review verdict"
}}

Output ONLY the JSON — no prose before or after.
""",
    mode="bypassPermissions",
    run_in_background=False,  # Wait for result — review must complete before pipeline transition
    isolation="worktree",
)
```

#### 3f. Parse Verdict

```python
import json as json_lib

# Parse the subagent's JSON output
try:
    review_result = json_lib.loads(subagent_output.strip())
    verdict = review_result.get("verdict")  # "APPROVED" or "CHANGES_REQUESTED"
    issues_list = review_result.get("issues", [])
    summary = review_result.get("summary", "")
except Exception as e:
    # Malformed output — escalate
    verdict = None
    issues_list = []
    summary = f"Review subagent returned unparseable output: {e}"
```

#### 3g. If APPROVED — Post Comment + Transition → MergeReady

```python
if verdict == "APPROVED":
    # Post Linear comment with approval verdict
    comment_body = f"""**Review APPROVED** (iteration {review_iteration + 1})

PR #{pr_number} passed all review checks.

{summary}

Reviewers: code-reviewer, architecture-reviewer, security-officer, design-reviewer, silent-failure-hunter
"""
    from scripts.lacrimosa_linear import create_comment
    comment = create_comment(linear_issue["id"], comment_body)
    linear_comment_id = comment.get("id", "")

    # Transition Reviewing → MergeReady
    pm.transition(
        identifier=issue["identifier"],
        from_state="Reviewing",
        to_state="MergeReady",
        owner="engineer-review",
        proof={
            "review_verdict": "APPROVED",
            "linear_comment_id": linear_comment_id,
        },
    )

    # Persist cycle result
    with sm.transaction("engineer-review") as w:
        w.set("engineer_review.last_approved", issue["identifier"])
        w.set("engineer_review.last_cycle_result", f"approved:{issue['identifier']}")
```

#### 3h. If CHANGES_REQUESTED — Post Comment + Transition → FixNeeded

```python
elif verdict == "CHANGES_REQUESTED":
    # CRITICAL: issues_list MUST be non-empty with specific findings — never vague
    if not issues_list:
        # Subagent said CHANGES_REQUESTED but gave no issues — treat as malformed, escalate
        verdict = None  # Fall through to escalation below
    else:
        # Format findings as readable Linear comment
        findings_md = "\n".join(
            f"- **[{i['severity'].upper()}]** {i.get('reviewer','')} — "
            f"`{i.get('file','') or 'general'}{'#L' + str(i['line']) if i.get('line') else ''}`: "
            f"{i['description']}"
            + (f"\n  Suggestion: {i['suggestion']}" if i.get('suggestion') else "")
            for i in issues_list
        )
        comment_body = f"""**Review CHANGES_REQUESTED** (iteration {review_iteration + 1})

PR #{pr_number} requires changes before merge.

{summary}

### Findings ({len(issues_list)} issue(s)):
{findings_md}
"""
        from scripts.lacrimosa_linear import create_comment
        comment = create_comment(linear_issue["id"], comment_body)
        linear_comment_id = comment.get("id", "")

        # Transition Reviewing → FixNeeded
        pm.transition(
            identifier=issue["identifier"],
            from_state="Reviewing",
            to_state="FixNeeded",
            owner="engineer-review",
            proof={
                "issues_list": issues_list,  # Must be non-empty list of specific findings
                "linear_comment_id": linear_comment_id,
            },
        )

        # Persist learning event for 2+ iteration reviews
        if review_iteration >= 1:
            with sm.transaction("engineer-review") as w:
                w.append_learning_event({
                    "id": f"review-iter-{issue['identifier']}-{review_iteration + 1}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_type": "pr_review_iteration_2plus",
                    "issue_id": issue["identifier"],
                    "context": {
                        "pr_number": pr_number,
                        "iteration": review_iteration + 1,
                        "issues_count": len(issues_list),
                    }
                })
```

#### 3i. Escalation — if verdict is None or review_iteration >= max_iterations

```python
# Read max_iterations from config (default 3)
import yaml
with open("{project_root}/.claude/lacrimosa/config.yaml") as f:
    config = yaml.safe_load(f)
max_iterations = config.get("review", {}).get("max_iterations", 3)

# Escalate if: unparseable verdict, empty issues_list on CHANGES_REQUESTED, or too many iterations
should_escalate = (
    verdict is None
    or review_iteration >= max_iterations
)

if should_escalate:
    escalation_reason = (
        f"Review iteration limit reached ({review_iteration + 1}/{max_iterations})"
        if review_iteration >= max_iterations
        else f"Review subagent returned invalid verdict: {summary or 'no output'}"
    )

    comment_body = f"""**Review ESCALATED** — Human Review Required

PR #{pr_number} for {issue['identifier']} requires human attention.

**Reason:** {escalation_reason}

 please review this PR directly.

PR: {pr_data.get('url', f'https://github.com/{github_org}/{github_repo}/pull/{pr_number}')}
"""
    from scripts.lacrimosa_linear import create_comment
    comment = create_comment(linear_issue["id"], comment_body)
    linear_comment_id = comment.get("id", "")

    pm.transition(
        identifier=issue["identifier"],
        from_state="Reviewing",
        to_state="Escalated",
        owner="engineer-review",
        proof={
            "escalation_reason": escalation_reason,
            "linear_comment_id": linear_comment_id,
        },
    )

    with sm.transaction("engineer-review") as w:
        w.append_learning_event({
            "id": f"escalation-{issue['identifier']}-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "pr_review_escalated",
            "issue_id": issue["identifier"],
            "context": {
                "pr_number": pr_number,
                "iteration": review_iteration + 1,
                "reason": escalation_reason,
            }
        })
```

### Step 4: Adaptive Work Check

After processing the primary issue, check for additional quick wins:

```python
# Check if any other ReviewPending issues exist
remaining = pm.query(states=["ReviewPending"])
if remaining:
    # Do NOT process more — one review per cycle to avoid context bloat.
    # Log that work remains and let the next cycle pick it up.
    with sm.transaction("engineer-review") as w:
        w.set("engineer_review.queue_depth", len(remaining))
```

### Step 5: Update State + End Cycle

```python
from datetime import datetime, timezone

with sm.transaction("engineer-review") as w:
    w.set("engineer_review.last_cycle", datetime.now(timezone.utc).isoformat())
# Heartbeat auto-updated by transaction commit.
```

```bash
/clear
```
This clears conversation history between cycles. Cron jobs survive `/clear`.

## Safety Rules

1. **NEVER writes code.** This specialist invokes `pr-review-toolkit:review-pr` and posts verdicts.
   It does not fix code, does not run tests, does not commit anything.

2. **FixNeeded proof MUST contain a non-empty `issues_list` with specific findings.**
   Each entry must include `severity`, `description`, and at minimum one of `file` or `reviewer`.
   Vague entries like `{"description": "some issues found"}` are forbidden — escalate instead.

3. **Escalate at `max_iterations`** (read from `config.review.max_iterations`, default 3).
   Do not continue the review loop beyond this limit. Post `` mention in the
   Linear comment so the human sees it.

4. **One PR per cycle.** Process `pending[0]` only. The loop cadence (10m) provides
   natural throughput — never rush to process multiple PRs in one cycle as review context bloat
   causes quality degradation.

5. **All Linear writes via `lacrimosa_linear.py`** — never MCP tools.

6. **All state writes via `sm.transaction("engineer-review")`** — never direct SQLite.

7. **Sentinel bypass on RED.** Human-escalated issues (`sentinel_origin=1`) bypass the RED
   throttle. All other issues pause when throttle is RED.

8. **Never transition a stale state.** `pm.transition()` raises `InvalidTransition` if the
   current state does not match `from_state`. Catch this and log — do not retry blindly.

```python
from scripts.lacrimosa_pipeline import InvalidTransition, MissingProof
try:
    pm.transition(...)
except InvalidTransition as e:
    # State was already moved by another specialist (race) — skip silently
    pass
except MissingProof as e:
    # Bug in proof construction — log and escalate
    with sm.transaction("engineer-review") as w:
        w.set("engineer_review.last_error", str(e))
```
