---
name: bugfix
description: |
  Systematic bug investigation and fixing with hypothesis testing and knowledge preservation. Use for any bug fix task. Core workflow: Analysis → Hypotheses (min 3) → Testing → Fix → Verify → Finalize. Emphasizes root cause confirmation before fixing. Auto-detects business-flow bugs and extracts real incident data into sanitized case packs for regression replay.
---

# Bugfix Workflow

Systematic hypothesis-driven debugging. Don't guess—form hypotheses, test them, confirm root cause.

```
Standard:       Analysis → Hypotheses → Testing → Fix → Verify → Regression → Finalize
Business-flow:  [Detection + Analysis(+data)] → Hypotheses → Testing → Fix → CasePack → Verify(+gate) → [BVA + Replay] → Finalize
```

---

## STEP 0: Task Setup (MANDATORY FIRST)

**Create tasks for ALL phases immediately:**

```
TaskCreate(subject="Phase 0.5: Business-Flow Detection", description="Auto-detect if bug is in a business-critical domain", activeForm="Detecting business-flow")
TaskCreate(subject="Phase 1: Analysis", description="Gather context, KI/Schema, GitHub, logs", activeForm="Analyzing bug")
TaskCreate(subject="Phase 2: Hypotheses", description="Form minimum 3 hypotheses", activeForm="Forming hypotheses")
TaskCreate(subject="Phase 3: Testing", description="Test hypotheses one at a time", activeForm="Testing hypotheses")
TaskCreate(subject="Phase 4: Fix", description="Implement fix across all affected locations", activeForm="Implementing fix")
TaskCreate(subject="Phase 4.5: Case Pack Extraction", description="Extract real incident data into sanitized case pack (business-flow only)", activeForm="Extracting case pack")
TaskCreate(subject="Phase 5: Verify", description="Run bug test + all tests + gate validator", activeForm="Verifying fix")
TaskCreate(subject="Phase 5.5A: BVA Regression Tests", description="Add 15+ regression tests via BVA", activeForm="Adding BVA regression tests")
TaskCreate(subject="Phase 5.5B: Replay Tests", description="Generate business-flow replay tests from case pack (business-flow only)", activeForm="Adding replay tests")
TaskCreate(subject="Phase 6: Finalize", description="Remove debug, update KI, close issue", activeForm="Finalizing")
```

**Set dependencies:**
```
# Phase 0.5 is UNBLOCKED (runs parallel with Phase 1)
TaskUpdate(taskId="2", addBlockedBy=["1"])   # Analysis blocked by Detection (to get channel info)
TaskUpdate(taskId="3", addBlockedBy=["2"])   # Hypotheses after Analysis
TaskUpdate(taskId="4", addBlockedBy=["3"])   # Testing after Hypotheses
TaskUpdate(taskId="5", addBlockedBy=["4"])   # Fix after Testing
TaskUpdate(taskId="6", addBlockedBy=["5"])   # Case Pack after Fix
TaskUpdate(taskId="7", addBlockedBy=["5"])   # Verify after Fix (parallel with Case Pack for non-business-flow)
TaskUpdate(taskId="8", addBlockedBy=["7"])   # BVA after Verify
TaskUpdate(taskId="9", addBlockedBy=["6"])   # Replay after Case Pack
TaskUpdate(taskId="10", addBlockedBy=["8"])  # Finalize after BVA
```

**Note:** Phase 4.5, 5.5B only execute when Phase 0.5 detected `is_business_flow == True`. For non-business-flow bugs, mark them `completed` immediately with note "Skipped — not a business-flow bug".

---

## 0.5. Business-Flow Detection (parallel with Phase 1)

```
TaskUpdate(taskId="1", status="in_progress")
```

Auto-detect if the bug falls within business-critical flows (configure per product).

### Detection Signals

| Signal | Weight | How to Check |
|--------|--------|--------------|
| GH issue label `business-flow-bug` | Definitive | `gh issue view <N> --json labels` |
| Affected file paths | High | Files under your product's business-critical service directories |
| Bug description keywords | High | Match against channel keyword sets (below) |
| DB model references | Medium | References to business domain models in stack traces |

### Channel Keyword Sets

Define keyword sets per business channel. Example:

```
CHANNEL_A: <keywords specific to your first business flow>
CHANNEL_B: <keywords specific to your second business flow>
CHANNEL_C: <keywords specific to your third business flow>
```

### Detection Output

```json
{
  "is_business_flow": true,
  "channel": "<channel_name>",
  "confidence": "high",
  "incident_refs_hint": { "incident_id": "...", "tenant_id": "...", "region": "..." },
  "signals": ["gh_label", "file_paths", "keywords"]
}
```

### Decision

- `confidence == high` (or GH label present): activate business-flow path
- `confidence == medium` (2+ signals): activate business-flow path with warning
- `confidence == low` (1 signal) or no match: skip business-flow phases, mark 4.5 and 5.5B as `completed` immediately

```
TaskUpdate(taskId="1", status="completed")
```

---

## 1. Analysis

```
TaskUpdate(taskId="2", status="in_progress")
```

**Spawn Explore agent for codebase context:**
```
Task(subagent_type="Explore", prompt="Find all code related to <bug area>. Identify error handling, state management, similar patterns.")
```

Gather context before forming hypotheses:

- **Schema/KI**: `mcp_schema-mcp_schema_search query="<keywords>"` — check documented gotchas
- **GitHub**: Use `/github-archaeology` for past fixes, regressions, linked PRs
- **Logs**: If production bug, check Cloud Run logs (see [references/debug-harness.md](references/debug-harness.md))

**Linear (auto — see `rules/linear-integration.md`):**
1. Search: `mcp__linear-server__list_issues(query="<bug keywords>", team="{linear_team}")`
2. If not found → create: `mcp__linear-server__save_issue(title="Bug: <title>", team="{linear_team}", project="<matching project>", labels=["Bug", "<Area>", "<Domain>"], priority=<severity>, assignee="me", state="In Progress", description="GH #XXX — <bug description>")`
3. If found → update: `mcp__linear-server__save_issue(id="<id>", state="In Progress", assignee="me")`
4. Capture `LINEAR_ISSUE_ID` for subsequent updates.

### 1b. Production Data Gathering (business-flow only)

**When `is_business_flow == True`**, gather real incident data in parallel with standard analysis.

**Step 1: Get incident identifiers.** Check GH issue body for incident IDs. If not found, **ask user** for the incident identifiers.

**Step 2: Ask user for confirmation** before querying production DB:
> "I need to query production DB for [channel] incident [id]. Proceed?"

**Step 3: Extract raw incident data** (store in `/tmp/incident_raw/{case_id}/`, never commit):

```bash
# Cloud Run logs (adapt service name to your deployment)
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name={cloud_run_service} AND textPayload:\"{incident_id}\"" \
  --limit=200 --format=json --project={gcp_project_id}

# DB queries — adapt table/column names to your schema
# SELECT * FROM {your_table} WHERE id = '{incident_id}';

# GCS artifacts (if applicable)
gsutil ls gs://{GCS_BUCKET}/data/{incident_id}/
```

**Or use the extraction script:**
```bash
python scripts/extract_incident_data.py \
  --channel {channel} \
  --{id_field} {incident_id} \
  --region {region} \
  --output-dir /tmp/incident_raw/{case_id}
```

```
TaskUpdate(taskId="2", status="completed")
```

## 2. Hypotheses

```
TaskUpdate(taskId="3", status="in_progress")
```

Form **minimum 3 hypotheses** before investigating. See [references/hypothesis-testing.md](references/hypothesis-testing.md).

**Create task for each hypothesis:**
```
TaskCreate(subject="H1: <theory>", description="Evidence: ... Counter: ... Test: ...", activeForm="Testing H1")
TaskCreate(subject="H2: <theory>", description="Evidence: ... Counter: ... Test: ...", activeForm="Testing H2")
TaskCreate(subject="H3: <theory>", description="Evidence: ... Counter: ... Test: ...", activeForm="Testing H3")
```

Each hypothesis: Theory → Evidence → Counter-evidence → Test

```markdown
### Hypothesis 1: [Title]
**Theory:** What I believe is happening
**Evidence:** What supports this
**Counter:** What would disprove it
**Test:** How to verify
```

```
TaskUpdate(taskId="3", status="completed")
```

## 3. Testing

```
TaskUpdate(taskId="4", status="in_progress")
```

### Option A: Sequential (simple bugs, 1-2 hypotheses)

Test one hypothesis at a time. Use `DEBUG[ISSUE-XXX]` tagged logging.

**For each hypothesis task, update status as you test:**
```
TaskUpdate(taskId="H1_task_id", status="in_progress")
# Run test
TaskUpdate(taskId="H1_task_id", status="completed", description="CONFIRMED/REFUTED: <reason>")
```

### Option B: Agent Team (complex bugs, 3+ independent hypotheses)

**Use when:** Hypotheses are in different subsystems and can be investigated independently.
**Always spawn ALL 16 roles.** Lead = PM. Dedicated agent types for each.

```
# 1. Spawn team
Teammate(operation="spawnTeam", team_name="debug-GH-XXX", description="Investigating <bug>")

# 2. Spawn ALL 16 roles (single message — all in parallel)
Task(team_name="debug-GH-XXX", name="ceo", subagent_type="ceo", prompt="Assess business impact of <bug>.")
Task(team_name="debug-GH-XXX", name="cto", subagent_type="cto", prompt="Review technical implications of <bug>.")
Task(team_name="debug-GH-XXX", name="ba", subagent_type="ba", prompt="Analyze bug report, define fix acceptance criteria for <bug>.")
Task(team_name="debug-GH-XXX", name="architect", subagent_type="solution-architect", prompt="Analyze impact, review fix approach for <bug>.")
Task(team_name="debug-GH-XXX", name="db-architect", subagent_type="backend-architect", prompt="Analyze DB layer impact, check schema/query issues for <bug>.")
Task(team_name="debug-GH-XXX", name="investigator-A", subagent_type="backend-developer", prompt="Investigate H1+H2 for <bug>. DEBUG[ISSUE-XXX] logging.")
Task(team_name="debug-GH-XXX", name="investigator-B", subagent_type="backend-developer", prompt="Investigate H3+H4 for <bug>. DEBUG[ISSUE-XXX] logging.")
Task(team_name="debug-GH-XXX", name="qa", subagent_type="qa-engineer", prompt="Write regression tests for <bug>. TDD first.")
Task(team_name="debug-GH-XXX", name="manual-qa", subagent_type="qa-engineer", prompt="Exploratory testing around <bug>. Find related edge cases.")
Task(team_name="debug-GH-XXX", name="security-officer", subagent_type="security-officer", prompt="CROSS-CUTTING: Assess if <bug> has security implications. Review fix for vulnerabilities.")
Task(team_name="debug-GH-XXX", name="devops", subagent_type="devops-engineer", prompt="Analyze logs, verify fix in staging for <bug>.")
Task(team_name="debug-GH-XXX", name="marketing", subagent_type="marketing-specialist", prompt="Assess user communication needs for <bug>.")
Task(team_name="debug-GH-XXX", name="seo", subagent_type="seo-specialist", prompt="Check SEO impact of <bug> (broken pages, 404s, etc).")
Task(team_name="debug-GH-XXX", name="designer", subagent_type="ui-designer", prompt="Review UI impact of <bug>, error state design.")
Task(team_name="debug-GH-XXX", name="legal", subagent_type="legal-advisor", prompt="Assess data/compliance impact of <bug>.")
Task(team_name="debug-GH-XXX", name="finance", subagent_type="financial-advisor", prompt="Assess financial impact of <bug> (billing, costs).")

# 3. Assign tasks to ALL 16 members
# 4. SDLC Kickoff: CEO/CTO assess impact → BA + Legal + Security → Investigators + QA + DevOps
# 5. Collect results → cleanup team
```

| Result | Action |
|--------|--------|
| CONFIRMED | → Fix |
| REFUTED | Next hypothesis |
| INCONCLUSIVE | More logging |
| ALL REFUTED | New hypotheses |

```
TaskUpdate(taskId="4", status="completed")
```

## 4. Fix

```
TaskUpdate(taskId="5", status="in_progress")
```

**Spawn codebase-explorer for impact analysis:**
```
Task(subagent_type="codebase-explorer", prompt="Trace entire flow for <bug area>: callers, callees, siblings, shared state. Find ALL locations with same pattern.")
```

**Before fixing, trace the entire flow:**
- Callers, callees, siblings, shared state
- **Search for same pattern elsewhere** — a fix in one place is often not enough

```bash
grep -rn "pattern" --include="*.py" .
```

Fix process:
1. Write failing test first
2. Implement minimal fix across ALL affected locations
3. Bug test should PASS

```
TaskUpdate(taskId="5", status="completed")
```

## 4.5. Case Pack Extraction (business-flow only)

> **Skip this phase** if Phase 0.5 detected `is_business_flow == False`. Mark task as `completed` with note "Skipped".

```
TaskUpdate(taskId="6", status="in_progress")
```

### Step 1: Generate case_id

```
{channel}_{brief_description}_{YYYYMMDD}
# Example: channel_a_edge_case_20260304
```

### Step 2: Create case pack via `business_bugflow.py extract`

```bash
python scripts/business_bugflow.py extract \
  --case-id "{case_id}" \
  --channel "{channel}" \
  --incident-ref "incident_id={incident_id}" \
  --incident-ref "tenant_id={tenant_id}" \
  --incident-ref "region={region}" \
  --sanitized-artifact "event_timeline=artifacts/event_timeline.json" \
  --repro-step "Replay sanitized data through affected code path" \
  --expected-assertion "final_status=success" \
  --redaction-version v1 \
  --risk-level high
```

Or use the all-in-one command:
```bash
python scripts/business_bugflow.py extract-from-production \
  --case-id "{case_id}" \
  --channel "{channel}" \
  --incident-id "{incident_id}" \
  --region "{region}"
```

### Step 3: Sanitize and populate artifacts

Take raw data from `/tmp/incident_raw/{case_id}/` and:
1. Apply `sanitize_payload()` from `scripts/business_bugflow.py`
2. Write sanitized JSON to `tests/fixtures/business_cases/{case_id}/artifacts/`
3. Replace placeholder artifacts with real sanitized data

### Step 4: Validate case pack

```bash
python scripts/business_bugflow.py validate --case-id "{case_id}"
```

### Step 5: PII spot-check

```bash
# Verify no PII leaked into committed artifacts
grep -rE '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' tests/fixtures/business_cases/{case_id}/artifacts/
grep -rE '\+?\d[\d()\-\s]{7,}\d' tests/fixtures/business_cases/{case_id}/artifacts/
```

If PII found → re-sanitize and re-validate.

```
TaskUpdate(taskId="6", status="completed")
```

## 5. Verify

```
TaskUpdate(taskId="7", status="in_progress")
```

**Linear:** `mcp__linear-server__save_issue(id=LINEAR_ISSUE_ID, state="In Review")`
**Linear:** `mcp__linear-server__save_comment(issueId=LINEAR_ISSUE_ID, body="**Root cause confirmed** — <hypothesis>. Fix applied to N files. Running verification...")`

**Spawn parallel-test-runner agents:**
```
Task(subagent_type="parallel-test-runner", prompt="Run bug-specific test: pytest tests/ -k '<bug>' -v")
Task(subagent_type="parallel-test-runner", prompt="Run unit tests")
Task(subagent_type="parallel-test-runner", prompt="Run integration tests")
Task(subagent_type="parallel-test-runner", prompt="Run e2e fast tests")
```

```bash
pytest tests/ -k "<bug>" -v && ./run_all_tests.sh
```

### Gate Validation (business-flow only)

When `is_business_flow == True`, also run:

```bash
python scripts/validate_business_bugflow.py \
  --mode strict \
  --case-id "{case_id}" \
  --force
```

**Business-flow verification checklist:**
- [ ] Case pack manifest validates cleanly
- [ ] All sanitized artifact files exist
- [ ] No PII in committed artifacts
- [ ] Raw artifacts use `secure://` URIs only
- [ ] Gate validator returns `ok: true` in strict mode

Regression found → back to Fix (reset task status).

**If frontend files were touched** (`components/`, `hooks/`, `lib/`, `app/`): invoke `/verify-flows` to verify affected user flows with Playwright (headless, fresh account).

### Staging Verification (Bug-Specific)

> [!CRITICAL]
> Every bugfix must be verified on staging with a **bug-specific verification plan** — not just "tests pass locally." The plan must demonstrate the original error no longer occurs.

**1. Build bug-specific verification plan:**

```markdown
### Verification Plan for {issue_prefix}-XXX
| Check | Method | Expected Result | Evidence |
|-------|--------|-----------------|----------|
| Original error reproduced? | <reproduce steps on staging> | Error no longer occurs | curl/screenshot |
| Fix-specific behavior | <verify the fix works> | <expected new behavior> | curl/screenshot |
| Related flows unbroken | <check adjacent functionality> | No regressions | curl/screenshot |
```

**2. Deploy to staging:** `./infra/deploy-staging-fresh.sh`

**3. Execute verification plan:**
- For API bugs: curl the affected endpoint, confirm error is gone
- For frontend bugs: navigate to affected page, screenshot
- For backend logic bugs: reference passing unit tests + confirm deployed version matches

**4. Record evidence** in `output/staging-verify-<ISSUE>/` — FAIL → back to Fix.

```
TaskUpdate(taskId="7", status="completed")
```

## 5.5A. BVA Regression Tests (MANDATORY)

```
TaskUpdate(taskId="8", status="in_progress")
```

**Spawn regression-test-generator:**
```
Task(subagent_type="regression-test-generator", prompt="Generate 15+ regression tests for bug <ISSUE-XXX> using BVA methodology. Cover: root cause, boundary values, edge cases, state variants, concurrent access, related paths.")
```

Use `/bugfix-extensive-tests` skill for detailed guidance.

```
TaskUpdate(taskId="8", status="completed")
```

## 5.5B. Business-Flow Replay Tests (business-flow only)

> **Skip this phase** if Phase 0.5 detected `is_business_flow == False`. Mark task as `completed` with note "Skipped".
> **Runs in parallel with Phase 5.5A.**

```
TaskUpdate(taskId="9", status="in_progress")
```

### Step 1: Generate test template

```bash
python scripts/business_bugflow.py generate-tests \
  --case-id "{case_id}" \
  --output-dir tests/regression/business_flow/generated \
  --force
```

### Step 2: Enhance generated test

The template from `generate-tests` is a skeleton. Enhance it with:
- Actual function-under-test invocations (not just manifest checks)
- Assertions that exercise the fixed code path with sanitized data
- Proper imports of the system-under-test

### Step 3: Add hand-written replay test

Add a new test function to `tests/regression/business_flow/test_case_replays.py` following the existing pattern:

```python
@pytest.mark.regression
@pytest.mark.unit
def test_{channel}_case_replay_{brief_description}() -> None:
    manifest, case_dir = _load_case("{case_id}")
    # Load relevant sanitized artifacts
    artifact = json.loads(
        (case_dir / manifest["sanitized_artifacts"]["key"]).read_text(encoding="utf-8")
    )
    # Assert expected behavior contract
    assert artifact["expected"]["field"] == expected_value
```

### Step 4: Run replay tests

```bash
pytest tests/regression/business_flow/ -v
pytest -m regression --ignore=tests/e2e --ignore=tests/e2e_fast -q
```

### Step 5: Run gate validator (final check)

```bash
python scripts/validate_business_bugflow.py --mode strict --case-id "{case_id}" --force
```

**Minimum tests for business-flow bugs:** 18+ total (15 BVA + 3 replay: manifest, generated, hand-written)

```
TaskUpdate(taskId="9", status="completed")
```

---

## 5.9. Spec Drift Check (after fix verified)

Check if the fix affects any product spec section:

1. Get changed files: `git diff --name-only HEAD~1`
2. Read `{product_spec_path}` and match changed files against `code_paths` in section HTML comments
3. If match found:
   a. Read and update `spec/DIRTY_SECTIONS.json` with an entry for the affected section
   b. Write pending update to `spec/pending-updates/<date>-<topic>.md`
   c. Commit the dirty flag and pending update
4. If no match → continue

---

## 6. Finalize

```
TaskUpdate(taskId="10", status="in_progress")
```

**Spawn cleanup and knowledge agents in parallel:**
```
Task(subagent_type="debug-cleanup-agent", prompt="Remove DEBUG[ISSUE-XXX] code from all files")
Task(subagent_type="knowledge-engineer", prompt="Update KI artifacts with bug pattern, root cause, and fix")
```

1. Remove debug code: `grep -rn "DEBUG\[ISSUE-" --include="*.py" .`
2. Use `/knowledge-preservation` for schema/KI updates
3. Close issue: `/workflow-complete issue_number=XXX root_cause="..." fix="..." tests="..."`
4. **Linear — close + comment:**
   ```
   mcp__linear-server__save_issue(id=LINEAR_ISSUE_ID, state="Done")
   mcp__linear-server__save_comment(issueId=LINEAR_ISSUE_ID, body="**Fixed** — Root cause: <H#>. Fix: <summary>\n- PR: #XXX\n- Regression tests: N added\n- Files: <key files>")
   ```

### Business-flow finalization (when applicable)

4. Ensure GH issue has `business-flow-bug` label: `gh issue edit <N> --add-label "business-flow-bug"`
5. Update `BUSINESS_FLOW_BUGFIX_FLOW_SCHEMA` if behavior contract changed
6. Set CI env: `BUSINESS_BUGFLOW_CASE_IDS={case_id}` for the PR

```
TaskUpdate(taskId="10", status="completed")
```

---

**Before completion**: Run `/completion-check` to verify fix matches original report.
