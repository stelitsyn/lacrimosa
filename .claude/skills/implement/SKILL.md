---
name: implement
description: |
  Unified implementation workflow with TDD and GitHub tracking. Use for any feature implementation or code change task. Phases: Discovery → TDD → Implementation → Review Loop → Self-Reflection → Verification → Cleanup → Knowledge Preservation. Runs autonomously (RALPH MODE) with max 20 iterations.
---

# Implementation Workflow

> **RALPH MODE**: Run ALL 8 phases autonomously. Max 20 iterations.
> **GitHub issues managed by hook** - no manual `gh` commands.
> **NEVER deploy to prod without user confirmation.**

```
[1+2] → 3 → 4 → 4.05 → [REVIEW-LOOP] → 4.5 → 5 → [5.5+6] → 7 → 8 → DONE
```

---

## PHASE 0: Epic Detection (RUN FIRST — BEFORE Step 0)

> **If the GH issue is an epic, this phase wraps the entire Phase 1-8 flow in a loop.**
> **NOT an epic → Skip directly to Step 0 below.**

### 0.1: Detect Epic

Read the GH issue. Check for epic signals (ANY of these → Epic Mode):
- Label `epic` present
- Title starts with `[EPIC]`
- Body contains "Sub-Issues" or "Proposed Sub-Issues" checklist (3+ items)
- Body references 3+ child issues

**NOT an epic → Skip to Step 0 (existing single-task flow)**
**IS an epic → Continue to 0.2**

### 0.2: Decompose Epic

1. Extract sub-issues from epic body checklist
2. For each sub-issue without a GH issue:
   - Spawn Explore agent to analyze scope (files affected, complexity)
   - Create GH issue with: scope, affected files, acceptance criteria, link to parent epic
3. Build dependency graph from epic's rollout section
4. Order: independent sub-issues first, dependent ones after their blockers

### 0.3: Create Epic Task Tracker

```
TaskCreate("EPIC: GH #NNN — [title]", status="in_progress")
# One task per sub-issue, with dependencies:
TaskCreate("Sub-issue 1: [name]")  # blockedBy: none
TaskCreate("Sub-issue 2: [name]")  # blockedBy: [1] if dependent
TaskCreate("Sub-issue 3: [name]")  # blockedBy: [1] if dependent
...
```

### 0.4: Assess Each Sub-Issue

For each sub-issue, calculate complexity:

| Factor | Points |
|--------|--------|
| Files to modify | +2 each |
| Cross-domain (API+frontend) | +3 |
| Security implications | +2 |
| Database changes | +2 |
| New test files needed | +1 each |

- **Score 8+** → Agent Team (full team lifecycle per sub-issue)
- **Score 3-7** → Subagent-driven-development (implement → review → next)
- **Score 0-2** → Direct implementation

### 0.5: Epic Loop (FULLY AUTONOMOUS)

For each sub-issue (in dependency order):
1. `TaskUpdate(sub-issue task, status="in_progress")`
2. **Dispatch executor** per 0.4 assessment:
   - **Score 8+ → Agent Team**: Spawn a team with its own lifecycle (SPAWN → CONTRACT → FLOW → SHIP → SHUTDOWN). The team does NOT use `/implement` phases — it follows its own continuous flow per `agent-teams-full.md`.
   - **Score 3-7 → Subagent-driven-development**: Dispatch subagents that follow `/implement` Phases 1-8 for this sub-issue.
   - **Score 0-2 → Direct implementation**: Run `/implement` Phases 1-8 directly for this sub-issue.
3. Comment on epic issue: "Sub-issue N complete: [summary]"
4. `TaskUpdate(sub-issue task, status="completed")`
5. **Continue to next sub-issue immediately** (no pause — Dark Factory mode)

**Parallel execution:** If 2+ sub-issues have NO shared dependencies, dispatch their executors in parallel.

After ALL sub-issues complete:
1. Comment on epic: completion summary
2. Close epic issue
3. Run `/completion-check` for entire epic
4. `TaskUpdate(epic task, status="completed")`

### 0.6: Epic Error Handling

- **Sub-issue executor fails 3 times** → Skip sub-issue, create "blocked" GH issue, continue to next independent sub-issue
- **Context window filling** → Epic orchestrator stays lean (delegates ALL implementation to subagents/teams), only tracks progress

---

## STEP 0: Task Setup (MANDATORY FIRST)

**Create tasks for ALL phases immediately:**

```
TaskCreate(subject="Phase 1+2: Discovery", description="KI/Schema search, GitHub context", activeForm="Discovering context")
TaskCreate(subject="Phase 3: TDD", description="Write failing tests FIRST", activeForm="Writing tests")
TaskCreate(subject="Phase 4: Implementation", description="SOLID/DRY code", activeForm="Implementing")
TaskCreate(subject="Phase 4.1: Review Loop", description="Parallel multi-reviewer feedback loop", activeForm="Running review loop")
TaskCreate(subject="Phase 4.5: Self-Reflection", description="PR review mindset", activeForm="Self-reviewing")
TaskCreate(subject="Phase 5: Verification", description="Run all test suites", activeForm="Running tests")
TaskCreate(subject="Phase 5.25: Staging Verification", description="Deploy staging, generate feature-specific test plan, verify with evidence", activeForm="Verifying on staging")
TaskCreate(subject="Phase 5.5+6: Regression + Cleanup", description="Add tests, remove debug", activeForm="Cleaning up")
TaskCreate(subject="Phase 7: Final Verification", description="Full test suite", activeForm="Final verification")
TaskCreate(subject="Phase 8: Knowledge Preservation", description="Update KI, close issue", activeForm="Preserving knowledge")
```

**Set dependencies:**
```
TaskUpdate(taskId="2", addBlockedBy=["1"])  # TDD blocked by Discovery
TaskUpdate(taskId="3", addBlockedBy=["2"])  # Implementation blocked by TDD
TaskUpdate(taskId="4", addBlockedBy=["3"])  # Review Loop blocked by Implementation
TaskUpdate(taskId="5", addBlockedBy=["4"])  # Self-Reflection blocked by Review Loop
# ...etc
```

---

## Subagent Dispatch (PROACTIVE - NO PERMISSION NEEDED)

**Score ≥5 → MUST dispatch IMMEDIATELY.** Calculate before starting:

| Factor | Points |
|--------|--------|
| Files to read | +1 each |
| Files to modify | +2 each |
| Cross-domain (API+frontend) | +3 |
| Security implications | +2 |

**Instant dispatch triggers - SPAWN AUTOMATICALLY:**

| Keywords | Agent | Spawn Command |
|----------|-------|---------------|
| API, endpoint, REST, FastAPI | backend-architect | `Task(subagent_type="backend-architect", ...)` |
| UI, component, React, frontend | frontend-developer | `Task(subagent_type="frontend-developer", ...)` |
| find, explore, investigate | Explore | `Task(subagent_type="Explore", ...)` |
| security, auth, OWASP | security-officer | `Task(subagent_type="security-officer", ...)` |

**Multi-Agent Parallel Pattern:**
```
Feature with API + UI → spawn backend-architect + frontend-developer + Explore (parallel)
```

---

## Phase 1+2: Discovery (Parallel)

**FIRST: Mark task in progress:**
```
TaskUpdate(taskId="1", status="in_progress")
```

**Spawn Explore agent for codebase context:**
```
Task(subagent_type="Explore", prompt="Find all files related to <feature>. Identify patterns, dependencies, and similar implementations.")
```

**KI & Schema (parallel with Explore):**
```
mcp_schema-mcp_schema_search query="<keywords>"
```
Check KI summaries → read artifacts → note patterns and gotchas.

**GitHub:** Hook auto-creates/finds issue. Capture `GITHUB_ISSUE=XXX` in task.md.

**Linear (auto — see `rules/linear-integration.md`):**
1. Search for existing issue: `mcp__linear-server__list_issues(query="<feature>", team="{linear_team}")`
2. If not found → create: `mcp__linear-server__save_issue(title="<title>", team="{linear_team}", project="<matching project>", labels=[<Area>, <Domain>], priority=<from score>, assignee="me", state="In Progress", description="GH #XXX — <context>")`
3. If found → update: `mcp__linear-server__save_issue(id="<id>", state="In Progress", assignee="me")`
4. Capture `LINEAR_ISSUE_ID` for subsequent updates.

**Complete phase:**
```
TaskUpdate(taskId="1", status="completed")
```

**→ Phase 3**

---

## Phase 3: TDD (Tests First)

```
TaskUpdate(taskId="2", status="in_progress")
```

Write tests BEFORE implementation. See [references/tdd.md](references/tdd.md).

```bash
pytest tests/path.py -v --tb=short  # Must FAIL first
```

```
TaskUpdate(taskId="2", status="completed")
```

**→ Phase 4**

---

## Phase 4: Implementation

```
TaskUpdate(taskId="3", status="in_progress")
```

### Option A: Subagents (single-domain or small scope)

**Spawn domain agents based on task type:**
```
# For API work:
Task(subagent_type="backend-architect", prompt="Implement <endpoint> following SOLID/DRY. Max 300 lines/file.")

# For UI work:
Task(subagent_type="frontend-developer", prompt="Implement <component> following React patterns.")

# For both (parallel):
Task(subagent_type="backend-architect", ...) + Task(subagent_type="frontend-developer", ...)
```

### Option B: Agent Team (cross-domain, 5+ files per domain)

**Use when:** Backend + frontend + tests need separate context and coordination.
**Always spawn ALL 16 roles.** Lead = PM. Dedicated agent types for each.

```
# 1. Spawn team
Teammate(operation="spawnTeam", team_name="impl-GH-XXX", description="Implementing <feature>")

# 2. Spawn ALL 16 roles (single message — all in parallel)
Task(team_name="impl-GH-XXX", name="ceo", subagent_type="ceo", prompt="Validate business alignment for <feature>.")
Task(team_name="impl-GH-XXX", name="cto", subagent_type="cto", prompt="Review technical strategy for <feature>.")
Task(team_name="impl-GH-XXX", name="ba", subagent_type="ba", prompt="Gather requirements, acceptance criteria for <feature>.")
Task(team_name="impl-GH-XXX", name="architect", subagent_type="solution-architect", prompt="Design API contracts, file ownership for <feature>.")
Task(team_name="impl-GH-XXX", name="db-architect", subagent_type="backend-architect", prompt="Design DB schema, migrations, indexes for <feature>.")
Task(team_name="impl-GH-XXX", name="backend-dev", subagent_type="backend-developer", prompt="Implement endpoints, services for <feature>. SOLID/DRY.")
Task(team_name="impl-GH-XXX", name="frontend-dev", subagent_type="frontend-developer", prompt="Implement components, UI for <feature>.")
Task(team_name="impl-GH-XXX", name="qa", subagent_type="qa-engineer", prompt="Write automated tests (unit/integration/e2e) for <feature>. TDD first.")
Task(team_name="impl-GH-XXX", name="manual-qa", subagent_type="qa-engineer", prompt="Exploratory testing, UX edge cases, visual verification for <feature>.")
Task(team_name="impl-GH-XXX", name="security-officer", subagent_type="security-officer", prompt="CROSS-CUTTING: Threat model, OWASP review, auth audit at every tier for <feature>.")
Task(team_name="impl-GH-XXX", name="devops", subagent_type="devops-engineer", prompt="Prepare CI/CD, deployment for <feature>.")
Task(team_name="impl-GH-XXX", name="marketing", subagent_type="marketing-specialist", prompt="Define positioning, UI copy for <feature>.")
Task(team_name="impl-GH-XXX", name="seo", subagent_type="seo-specialist", prompt="Optimize SEO, meta tags for <feature>.")
Task(team_name="impl-GH-XXX", name="designer", subagent_type="ui-designer", prompt="Design UI specs, accessibility for <feature>.")
Task(team_name="impl-GH-XXX", name="legal", subagent_type="legal-advisor", prompt="Review compliance, privacy for <feature>.")
Task(team_name="impl-GH-XXX", name="finance", subagent_type="financial-advisor", prompt="Assess costs, pricing for <feature>.")

# 3. Create and assign tasks per auto-sizing (see agent-teams-summary.md + agent-teams-full.md)

# 4. SDLC Kickoff: CEO/CTO approve → BA + Legal + Finance → Architect + Designer + Marketing → Build

# 5. Monitor progress, resolve blockers, cleanup when done
TaskList → wait for completion → Teammate(operation="cleanup")
```

**MANDATORY: Related Code Analysis** - trace callers, callees, shared state, parallel implementations.

Follow SOLID/DRY. Limits: 300 lines/file, 30 lines/function, no GOD-classes.

See [references/code-quality.md](references/code-quality.md) for patterns.

```
TaskUpdate(taskId="3", status="completed")
```

**→ Phase 4.05 (Spec Drift Check)**

---
## Phase 4.05: Spec Drift Check (automatic)

After implementation, check if changed files affect any product spec section:

1. Get changed files: `git diff --name-only HEAD~1`
2. Read `{product_spec_path}` coverage map and match changed files against `code_paths` in section HTML comments
3. If a match is found:
   a. Read `spec/DIRTY_SECTIONS.json`
   b. Add entry for the affected section:
      ```json
      {
        "<section-slug>": {
          "flagged_by": "<LINEAR_ISSUE_ID>",
          "reason": "<one-line description of what changed>",
          "affected_schemas": ["<possibly affected schemas>"],
          "timestamp": "<ISO timestamp>",
          "pending_update": "spec/pending-updates/<date>-<topic>.md"
        }
      }
      ```
   c. Write a pending update file with: what the spec says, what the code now does (file:line evidence), proposed update
   d. Commit the dirty flag and pending update
4. If no match → continue to Phase 4.1

**→ Phase 4.1 (Review Loop)**

---

## Phase 4.1: Review Loop (NEW - Parallel Multi-Reviewer)

```
TaskUpdate(taskId="4", status="in_progress")
```

**Linear:** `mcp__linear-server__save_issue(id=LINEAR_ISSUE_ID, state="In Review")`

### Overview

After implementation, dispatch ALL applicable reviewers in PARALLEL, aggregate feedback, route fixes, and loop until all approve.

```
Implementation complete
        ↓
review-dispatcher: Analyze changed files
        ↓
Parallel dispatch (single message):
  - spec-reviewer (always)
  - code-reviewer (always)
  - security-officer (if auth/input/DB/API)
  - architecture-reviewer (if >100 lines or new classes)
  - design-reviewer (if .tsx/.css files)
        ↓
All reviews complete
        ↓
feedback-aggregator: Categorize issues, make decision
        ↓
    ALL APPROVE → Proceed to Phase 4.5
    ANY ISSUES → Route to implementer → Re-review failed only → Loop
```

### Step 1: Dispatch Review Dispatcher

```
Task(subagent_type="review-dispatcher", prompt="""
Implementation complete for: [task description]

Changed files:
[List of files with line counts]

Commit range: BASE_SHA..HEAD_SHA

Task requirements:
[Original task text]

Analyze which reviewers are needed and dispatch ALL in parallel.
""")
```

### Step 2: Parallel Review Dispatch

The review-dispatcher will dispatch in a SINGLE message:

```
# Always dispatch:
Task(subagent_type="general-purpose", prompt="Spec review...")
Task(subagent_type="superpowers:code-reviewer", prompt="Code review...")

# Conditionally dispatch (based on file patterns):
Task(subagent_type="security-officer", prompt="Security review...")      # if auth/input
Task(subagent_type="architecture-reviewer", prompt="Architecture...")    # if >100 lines
Task(subagent_type="design-reviewer", prompt="Design review...")         # if UI files
```

### Step 3: Feedback Aggregation

```
Task(subagent_type="feedback-aggregator", prompt="""
Reviewer results:

Spec Reviewer: [result]
Code Reviewer: [result]
Security Officer: [result]
Architecture Reviewer: [result]
Design Reviewer: [result]

Iteration: [N] of 5 max

Aggregate findings, categorize by severity, make decision.
""")
```

### Step 4: Handle Decision

**If APPROVE:**
```
TaskUpdate(taskId="4", status="completed")
```
Proceed to Phase 4.5.

**If CONTINUE_WORK:**
1. Route issues to appropriate implementer(s)
2. Implementer(s) fix issues
3. Re-dispatch ONLY failed reviewers (not all)
4. feedback-aggregator again
5. Loop until APPROVE or max iterations (5)

### Iteration Tracking

| Iteration | Max | On Exceed |
|-----------|-----|-----------|
| Normal | 5 | Escalate to human |
| Complex | 7 | Escalate to human |

### Oscillation Detection

If same issue appears 3+ times → ESCALATE:
- Log conflicting requirements
- Request human decision
- Do NOT continue looping

### Completion Criteria (All must be true)

1. **No Discrepancies:** Implementation matches spec exactly
2. **Coherent Solution:** All parts integrate correctly
3. **Bug-Free:** All tests pass, no critical/important issues
4. **Logical Flows:** Handles happy path, errors, edge cases

```
TaskUpdate(taskId="4", status="completed")
```

**→ Phase 4.5**

---

## Phase 4.5: Self-Reflection

```
TaskUpdate(taskId="5", status="in_progress")
```

**Spawn self-reflection-auditor:**
```
Task(subagent_type="self-reflection-auditor", prompt="Review changes for: 1) PR flags 2) Break points 3) Similar patterns missed. Files: <list>")
```

Ask yourself:
1. "If reviewing this PR, what would I flag?"
2. "What's the most likely way this breaks?"
3. "Did I check ALL similar patterns?"

No hacks. No "fix later" TODOs.

```
TaskUpdate(taskId="5", status="completed")
```

**→ Phase 5**

---

## Phase 5: Verification

```
TaskUpdate(taskId="6", status="in_progress")
```

**→ Use `/verification` skill** for test commands and failure handling.

**Spawn parallel-test-runner agents (4 in parallel):**
```
Task(subagent_type="parallel-test-runner", prompt="Run unit tests")
Task(subagent_type="parallel-test-runner", prompt="Run integration tests")
Task(subagent_type="parallel-test-runner", prompt="Run e2e fast tests")
Task(subagent_type="parallel-test-runner", prompt="Run regression tests")
```

```bash
./run_unit_tests.sh && ./run_integration_tests.sh && ./run_e2e_fast_tests.sh
```

**FAIL → Phase 4** (reset task status) **| PASS →**

**If frontend files were touched** (`components/`, `hooks/`, `lib/`, `app/`): invoke `/verify-flows` to verify affected user flows with Playwright (headless, fresh account).

```
TaskUpdate(taskId="6", status="completed")
```
**→ Phase 5.25**

---

## Phase 5.25: Staging Verification (Feature-Specific)

```
TaskUpdate(taskId="6.5", status="in_progress")
```

> [!CRITICAL]
> Every implementation must be verified on staging with a **feature-specific test plan** — not just "deploy and check if it works." The test plan must cover the SPECIFIC feature/bugfix being implemented, with concrete expected outcomes and evidence.

### 1. Build Change Inventory

List exactly what this implementation changed:

```markdown
### Changes in This Implementation
| Type | Description | Key Files | Verification Method |
|------|------------|-----------|-------------------|
| Feature/Bugfix | <what was built/fixed> | <files> | API curl / browser check / unit test |
```

### 2. Generate Feature-Specific Test Plan

Write `output/staging-verify-<ISSUE>/TEST_PLAN.md`:

**For backend changes** (API routes, services, DB):
- Happy path curl against staging endpoint
- Error path (missing auth, invalid input)
- Specific fix verification (if bugfix: reproduce the original error scenario and confirm it's gone)

**For frontend changes** (components, pages, hooks):
- Navigate to affected page on staging
- Verify specific visual elements (not just "page loads")
- Check for console errors
- Take screenshot as evidence

**For coordination/workflow changes:**
- Trigger the specific flow on staging
- Verify the fix addresses the original error (e.g., "resume_graph no longer crashes with msgpack error")

### 3. Deploy to Staging

```bash
./infra/deploy-staging-fresh.sh
```

Wait for health checks to pass on both US and EU.

### 4. Execute Test Plan

**For API tests:** Run curl commands, record status codes and response bodies.

**For browser tests:** Use Chrome MCP or Playwright:
- Navigate to staging URL
- Verify expected elements via `read_page`/`get_page_text`
- Screenshot with macOS `screencapture -l <CGWindowID>`
- Check console for errors

**For unit-test-verified fixes** (backend logic not directly testable via staging API):
- Reference the passing unit test as evidence
- Confirm the deployed code matches (check health endpoint version or recent deploy tag)

### 5. Record Evidence

Every test case gets a verdict (PASS/FAIL/BLOCKED) with evidence:
- API: HTTP status + response body excerpt
- Browser: screenshot file + page content verification
- Unit-verified: test name + pass confirmation

**FAIL → back to Phase 4** (fix the issue, redeploy, re-verify)
**ALL PASS →**

```
TaskUpdate(taskId="6.5", status="completed")
```
**→ Phase 5.5**

---

## Phase 5.5+6: Regression + Cleanup (Parallel)

```
TaskUpdate(taskId="7", status="in_progress")
```

**Spawn agents in parallel:**
```
Task(subagent_type="regression-test-generator", prompt="Generate 15+ regression tests for <feature>. Use BVA methodology.")
Task(subagent_type="debug-cleanup-agent", prompt="Remove DEBUG[ISSUE-XXX] code, verify cleanup.")
```

**Add regression tests** for any bugs fixed (min 15 tests). See `/verification` skill.

**Remove debug code:**
```bash
grep -rn "DEBUG\[ISSUE-" --include="*.py" .
```

```
TaskUpdate(taskId="7", status="completed")
```

**→ Phase 7**

---

## Phase 7: Final Verification

```
TaskUpdate(taskId="8", status="in_progress")
```

**Spawn phase-transition-validator:**
```
Task(subagent_type="phase-transition-validator", prompt="Validate Phase 7 completion: TDD first, no GOD-classes, debug removed, all tests pass, no secrets/PII")
```

Run full test suite. Checklist:
- [ ] Tests written BEFORE implementation
- [ ] No GOD-classes, debug removed
- [ ] All suites pass
- [ ] No secrets/PII

**FAIL → Phase 4** (reset tasks) **| PASS →**
```
TaskUpdate(taskId="8", status="completed")
```
**→ Phase 8**

---

## Phase 8: Knowledge Preservation

```
TaskUpdate(taskId="9", status="in_progress")
```

**Spawn knowledge-engineer agent:**
```
Task(subagent_type="knowledge-engineer", prompt="Update KI artifacts, schemas, and documentation for <feature>")
```

**→ Use `/knowledge-preservation` skill** for schema/KI/doc updates.

**Close issue:**
```
/workflow-complete issue_number=XXX root_cause="..." fix="..." tests="..."
```

**Linear — close issue + comment:**
```
mcp__linear-server__save_issue(id=LINEAR_ISSUE_ID, state="Done")
mcp__linear-server__save_comment(issueId=LINEAR_ISSUE_ID, body="**Completed** — <summary>\n- PR: #XXX\n- Tests: X unit, Y integration, Z regression\n- Files: <key files>")
```
If issue belongs to a milestone, check milestone progress.

```
TaskUpdate(taskId="9", status="completed")
```

---

## MANDATORY: /completion-check

**Before reporting completion**, execute `/completion-check`:
1. Re-read original requirements
2. Compare deliverables
3. Discrepancies → Phase 4
4. All met → notify user
