---
name: pre-release
description: Pre-release verification workflow for your product. Use before creating a release tag to run static analysis, test suites, verify GitHub issues, deploy to staging, and verify all release-pending features in the browser with screenshots.
---

# Pre-Release Verification

Pre-release checks ensuring code quality before creating a release tag. Runs unit, integration, and regression tests by default. E2E fast tests and other OpenAI-dependent tests are **opt-in** — only run if user explicitly requests them.

---

## STEP 0: Task Setup (MANDATORY FIRST)

**Create tasks for ALL verification steps:**

```
TaskCreate(subject="Prerequisites Check", description="Docker, venv, .env loaded", activeForm="Checking prerequisites")
TaskCreate(subject="Context Discovery", description="Review conversations, KI, GitHub issues", activeForm="Discovering context")
TaskCreate(subject="Static Analysis", description="Ruff, mypy, black, SonarQube", activeForm="Running static analysis")
TaskCreate(subject="Security Audit", description="OWASP, dependency CVEs, code security scan", activeForm="Running security audit")
TaskCreate(subject="Unit Tests", description="Run ./run_unit_tests.sh", activeForm="Running unit tests")
TaskCreate(subject="Integration Tests", description="Run ./run_integration_tests.sh", activeForm="Running integration tests")
TaskCreate(subject="Regression Tests", description="Run ./run_regression_tests.sh", activeForm="Running regression tests")
TaskCreate(subject="Git Status Check", description="Verify clean state, up to date", activeForm="Checking git status")
TaskCreate(subject="GitHub Issue Verification", description="Analyze open issues, close implemented ones", activeForm="Verifying issues")
TaskCreate(subject="Schema & Docs Validation", description="Validate schemas/docs consistency", activeForm="Validating schemas and docs")
TaskCreate(subject="10a: Generate Test Plan", description="Analyze release changes, create comprehensive test plan with API + browser + regression + edge case test cases", activeForm="Generating test plan")
TaskCreate(subject="10b: Deploy to Staging", description="Fresh build + deploy + health check", activeForm="Deploying to staging")
TaskCreate(subject="10b.5: Stripe E2E Sandbox Tests", description="Full Stripe sandbox e2e tests against staging — checkout, webhooks, subscriptions, credits, refunds", activeForm="Running Stripe e2e tests")
TaskCreate(subject="10c: Execute Test Plan", description="QA subagent executes every test case on staging with evidence", activeForm="Executing test plan on staging")
TaskCreate(subject="10d: Generate QA Report", description="REPORT_WITH_SCREENSHOTS.md with per-test-case evidence, findings, coverage audit", activeForm="Generating QA report")
```

---

## Prerequisites

```
TaskUpdate(taskId="1", status="in_progress")
```

- Docker Desktop running (required for E2E fast tests)
- Working in active virtual environment
- Environment variables loaded from `.env`

```bash
docker info > /dev/null 2>&1 && echo "✅ Docker running" || echo "❌ Start Docker Desktop"
```

```
TaskUpdate(taskId="1", status="completed")
```

---

## Context Discovery

```
TaskUpdate(taskId="2", status="in_progress")
```

**Spawn Explore agent for codebase context:**
```
Task(subagent_type="Explore", prompt="Find recent changes, unfinished work, known issues in the codebase")
```

Before running tests, review relevant context:

1. **Conversation summaries** - Recent bugfixes, unfinished work, known issues
2. **KI summaries** - Recent troubleshooting updates, new patterns
3. **GitHub issues** (last 7 days):

   ```bash
   gh issue list --state all --search "is:issue updated:>$(date -v-7d +%Y-%m-%d)" --limit 20
   ```

4. **Linear issues** — check In Progress, In Review, and recently Done:

   ```
   mcp__linear-server__list_issues(team="{linear_team}", state="In Progress")
   mcp__linear-server__list_issues(team="{linear_team}", state="In Review")
   mcp__linear-server__list_issues(team="{linear_team}", state="Done", updatedAt="-P7D")
   ```

   If Linear MCP is unavailable, use the API directly:

   ```bash
   curl -s -X POST https://api.linear.app/graphql \
     -H "Authorization: $(grep LINEAR_API_KEY .env | cut -d= -f2)" \
     -H "Content-Type: application/json" \
     -d '{"query":"{ issues(filter: { state: { type: { in: [\"started\", \"completed\"] } }, team: { key: { eq: \"{issue_prefix}\" } }, updatedAt: { gte: \"'$(date -v-7d +%Y-%m-%dT00:00:00Z)'\" } }, first: 30, orderBy: updatedAt) { nodes { identifier title state { name } project { name } priority } } }"}'
   ```

   Verify: all Done Linear issues match merged PRs. Flag any In Progress issues that should block the release.

```
TaskUpdate(taskId="2", status="completed")
```

## Static Analysis

```
TaskUpdate(taskId="3", status="in_progress")
```

> [!IMPORTANT]
> Run static analysis BEFORE tests to catch syntax/style issues early.

**Spawn quality-security-agent:**
```
Task(subagent_type="quality-security-agent", prompt="Run static analysis: ruff check, mypy, black --check. Report violations.")
```

```bash
# Linting with auto-fix
python -m ruff check {source_dir} tests --fix

# Type checking
python -m mypy {source_dir} --ignore-missing-imports

# Formatting check
python -m black --check {source_dir} tests
```

**SonarQube**: Check IDE extension panel for critical/major issues.

```
TaskUpdate(taskId="3", status="completed")
```

---

## Security Audit

```
TaskUpdate(taskId="4", status="in_progress")
```

> [!IMPORTANT]
> Run security scans BEFORE deploying to staging. Critical/High findings BLOCK the release.

**Spawn security-officer-v3 from pr-review-toolkit for deep code review:**
```
Task(subagent_type="security-officer-v3", prompt="Run a full security audit of the product codebase. Focus on OWASP Top 10: injection, broken auth, sensitive data exposure, XXE, broken access control, security misconfig, XSS, insecure deserialization, known vulnerabilities, insufficient logging. Review files changed since the last release tag: git diff --name-only $(git describe --tags --abbrev=0)..HEAD. Blocks on Critical/High findings. Report findings by severity (Critical/High/Medium/Low).")
```

### 1. Python Dependency Vulnerabilities

```bash
# pip-audit for known CVEs in Python dependencies
.venv/bin/pip-audit --require-hashes=false --progress-spinner=off 2>&1 | head -50

# bandit for Python code security (OWASP SAST)
.venv/bin/python -m bandit -r {source_dir} -f txt -ll 2>&1 | tail -30
```

### 2. Frontend Dependency Vulnerabilities

```bash
# npm audit for known CVEs in Node dependencies
cd {frontend_dir} && npm audit --audit-level=moderate 2>&1 | tail -30 && cd ..
```

### 3. CVE Check (Critical Stack Components)

Search for recent CVEs affecting the stack:
- FastAPI, Uvicorn, Starlette
- Next.js, React
- SQLAlchemy, Alembic
- Firebase Admin SDK
- Any dependency with CVSS >= 7.0

### 4. Security Findings Gate

| Severity | Release Action |
|----------|----------------|
| Critical (CVSS >= 9.0) | **BLOCK** — fix immediately before proceeding |
| High (CVSS >= 7.0) | **BLOCK** — fix or document accepted risk with justification |
| Medium (CVSS >= 4.0) | **PROCEED** — create GH issue to track, fix within sprint |
| Low (CVSS < 4.0) | **PROCEED** — log for future cleanup |

```
TaskUpdate(taskId="4", status="completed")
```

---

## Test Suites

**Spawn test runners in parallel (default suites):**
```
Task(subagent_type="parallel-test-runner", prompt="Run unit tests: ./run_unit_tests.sh")
Task(subagent_type="parallel-test-runner", prompt="Run integration tests: ./run_integration_tests.sh")
Task(subagent_type="parallel-test-runner", prompt="Run regression tests: ./run_regression_tests.sh")
```

| Suite | Command | Time | Default |
|-------|---------|------|---------|
| Unit | `./run_unit_tests.sh` | ~30s | Yes |
| Integration | `./run_integration_tests.sh` | ~1min | Yes |
| Regression | `./run_regression_tests.sh` | ~1min | Yes |
| E2E Fast | `./run_e2e_fast_tests.sh` | ~2min | **Opt-in** |

> [!NOTE]
> E2E fast tests and other OpenAI-dependent tests are **opt-in only** — they require real OpenAI API calls and should only run when explicitly requested by the user.

**Mark completed as tests finish:**
```
TaskUpdate(taskId="5", status="completed")  # Unit
TaskUpdate(taskId="6", status="completed")  # Integration
TaskUpdate(taskId="7", status="completed")  # Regression
```

## Git Status

```
TaskUpdate(taskId="8", status="in_progress")
```

```bash
# Check uncommitted changes
git status --porcelain

# Verify branch is up to date
git fetch origin main && git log HEAD..origin/main --oneline
```

```
TaskUpdate(taskId="8", status="completed")
```

---

## GitHub Issue Verification

```
TaskUpdate(taskId="9", status="in_progress")
```

> [!IMPORTANT]
> Analyze open issues in BOTH GitHub and Linear. Close any that have been implemented.

### GitHub Issues

```bash
# List open issues (recent first)
gh issue list --state open --json number,title,labels --limit 50
```

**For each open issue, spawn an Explore agent to verify implementation status:**

```
Task(subagent_type="Explore", prompt="Check if GitHub issue #<NUMBER> '<title>' has been implemented. Search the codebase for the described feature/fix. Report: IMPLEMENTED or NOT_IMPLEMENTED with evidence (file paths, function names).")
```

### Linear Issues

```
mcp__linear-server__list_issues(team="{linear_team}", state="In Progress")
mcp__linear-server__list_issues(team="{linear_team}", state="In Review")
```

**For each open Linear issue, verify implementation status the same way.**

### Decision matrix (applies to both GH and Linear)

| Status | GH Action | Linear Action |
|--------|-----------|---------------|
| **Implemented** | `gh issue close <N> --comment "Verified in v{version}"` | `save_issue(id=..., state="Done")` + comment |
| **Partially implemented** | Leave open, comment progress | `save_comment` noting what's done |
| **Not implemented** | Leave open | Leave in current state |
| **Stale** | Close with comment | `save_issue(id=..., state="Canceled")` |

> [!NOTE]
> This step should NOT block the release. Close what's done, leave the rest open. Only block if a critical bug issue is open and unfixed.

```
TaskUpdate(taskId="9", status="completed")
```

---

## Schema & Documentation Validation

```
TaskUpdate(taskId="10", status="in_progress")
```

> [!IMPORTANT]
> Validates schemas and documentation before release. Run `/docs-schema-validator` or execute manually.

**Spawn docs-schema-validator agent:**
```
Task(subagent_type="Explore", prompt="Validate schemas and docs using docs-schema-validator skill checks")
```

**Quick validation:**
```bash
# Schema index consistency
echo "=== Schema Count ===" && ls schemas/*.md 2>/dev/null | wc -l

# Naming compliance
echo "=== Naming Issues ===" && for f in schemas/*.md; do basename "$f" | grep -qE "^[A-Z_]+\.md$" || echo "Non-compliant: $f"; done

# Stale schemas (>90 days)
echo "=== Stale Schemas ===" && find schemas -maxdepth 1 -name "*.md" -mtime +90 2>/dev/null

# Required docs
echo "=== Required Docs ===" && for doc in CICD_SETUP.md GCP_MULTIREGION_DEPLOYMENT.md; do [ -f "docs/$doc" ] && echo "✓ $doc" || echo "✗ Missing: $doc"; done
```

**MCP Schema tools** (for deeper validation):
- `mcp__schema-mcp__schema_index` - Get parsed index structure
- `mcp__schema-mcp__schema_domains` - List domains with counts
- `mcp__schema-mcp__schema_search` - Search for cross-references

```
TaskUpdate(taskId="10", status="completed")
```

---

## Step 9b: Confirm Pending Spec Updates

1. Check for pending updates: `ls spec/pending-updates/` (ignore .gitkeep)
2. If pending updates exist:
   a. For each pending update file:
      - Read the proposed change
      - Verify it matches current code (may be stale if code changed again)
      - If confirmed: apply to `{product_spec_path}`, update `verified` date, remove entry from `spec/DIRTY_SECTIONS.json`
      - If stale: delete the pending update, remove from `spec/DIRTY_SECTIONS.json`
   b. Update SCHEMA_INDEX.md if any schema trust metadata changed
   c. Commit: `git commit -m "spec: confirm pending updates for release"`
3. If no pending updates → continue

---

## Step 10a: Generate Test Plan

```
TaskUpdate(taskId="11", status="in_progress")
```

> [!IMPORTANT]
> Before deploying or testing anything, create a comprehensive test plan that ensures systematic coverage. The test plan is the contract between planning and execution — the QA subagent in step 10c will execute EVERY test case listed here. This prevents shallow testing where agents just click through pages without verifying what matters.

> [!CRITICAL]
> **The test plan MUST start with a Release Change Inventory** — a structured table of EVERY bug fix and feature in this release (from git log + Linear/GH issues). Then EVERY bug fix and feature MUST have at least one dedicated test case. Generic regression tests are NOT sufficient — if {issue_prefix}-XXX fixed a billing bug, there must be a test case specifically verifying that fix. If {issue_prefix}-YYY added a new integration, there must be test cases for the new endpoints. A test plan without feature/bugfix-specific tests is INCOMPLETE and must be regenerated.

### 0. Build Release Change Inventory (MANDATORY FIRST)

Before writing any test cases, build the complete inventory:

```markdown
## Release Change Inventory

### Bug Fixes
| Issue | Fix Description | Key Files | Verification Method |
|-------|----------------|-----------|-------------------|
| {issue_prefix}-XXX | <what was fixed> | <files> | <unit test / API curl / browser check> |

### New Features
| Issue | Feature Description | Key Files | Verification Method |
|-------|-------------------|-----------|-------------------|
| {issue_prefix}-XXX | <what was added> | <files> | <unit test / API curl / browser check> |
```

**Every row in this inventory MUST map to at least one test case in the plan.** If a bug fix or feature has no test case, add one. The inventory is the source of truth — test cases are derived from it.

### 1. Identify Release-Pending Changes

Build a change inventory from commits since the last release tag:

```bash
# List commits since last tag
git log $(git describe --tags --abbrev=0)..HEAD --oneline --no-merges

# Cross-reference with closed GH issues in this release
gh issue list --state closed --search "is:issue closed:>$(git log -1 --format=%ci $(git describe --tags --abbrev=0) | cut -d' ' -f1)" --limit 30

# Get changed files for impact analysis
git diff --name-only $(git describe --tags --abbrev=0)..HEAD
```

### 2. Map Changes to Test Targets

Load the impact map AND regression UI library:

```bash
cat ~/.claude/skills/verify-flows/references/impact-map.md
cat ~/.claude/skills/verify-flows/references/regression-ui-library.md
```

**For each affected flow, copy the SPECIFIC expected visual elements from the regression
UI library into the test case.** Do NOT write generic "page loads correctly" — include
the exact emoji, text content, selectors, and i18n expectations from the library.

**Multi-language test cases:** For each browser flow, generate at minimum:
- `B-XX-en`: Test in English (set browser Accept-Language via Chrome MCP)
- `B-XX-es`: Test in Spanish
- `B-XX-other`: One non-Latin language (RU or ZH) if the flow is i18n-sensitive

Each language test verifies: all text in correct language, no mixed languages,
emoji render correctly, layout doesn't break with longer/shorter translations.

Classify each changed file:

| Category | Detection Rule | Test Type |
|----------|---------------|-----------|
| API route changed | `{source_dir}/api/routes/*.py` modified | API test (curl on staging) |
| Frontend component changed | `{frontend_dir}/app/**/*.tsx` modified | Browser test (Chrome + screenshot) |
| Shared dependency changed | `lib/`, `hooks/`, `store`, `apiClient` modified | Regression test (all dependent flows) |
| Backend service changed | `{source_dir}/services/*.py` modified | API test (endpoints using that service) |
| Config/infra changed | `Dockerfile`, `cloudbuild`, `next.config` | Health check + smoke test |
| Docs/schemas only | `docs/`, `schemas/`, `*.md` only | Skip (no runtime impact) |

### 3. Check KI for Known Gotchas

```bash
.venv/bin/python schema_cli.py ki list --prefix "gotcha."
```

Include any relevant gotchas as edge case test cases.

### 4. Generate Test Plan Document

Write `output/pre-release-YYYYMMDD/TEST_PLAN.md` with ALL four categories below. Each test case gets a unique ID that the QA subagent will reference when reporting results.

```markdown
# Pre-Release Test Plan

- Date: YYYY-MM-DD
- Version: vX.Y.Z (pending)
- Generated from: N commits since vX.Y.Z-1
- Total test cases: <count>
- Changed files: <count>

---

## Release Change Inventory

### Bug Fixes
| Issue | Fix Description | Key Files | Verification Method |
|-------|----------------|-----------|-------------------|
| {issue_prefix}-XXX | <what was fixed> | <files> | unit test / API curl / browser check |
| ... | ... | ... | ... |

### New Features
| Issue | Feature Description | Key Files | Verification Method |
|-------|-------------------|-----------|-------------------|
| {issue_prefix}-XXX | <what was added> | <files> | unit test / API curl / browser check |
| ... | ... | ... | ... |

> Every row above MUST map to at least one test case below.

---

## Category A: API Endpoint Tests

For EACH changed API route, include at minimum:
- Happy path (valid request → expected status + body shape)
- Auth check (no token → 401)
- Validation (missing/invalid field → 400/422)

| ID | Endpoint | Method | Description | Curl Command | Expected Status | Expected Body Contains |
|----|----------|--------|-------------|-------------|----------------|----------------------|
| API-001 | /v1/health | GET | Health check US | curl -s https://{staging_api_us}/v1/health | 200 | "status" |
| API-002 | /v1/health | GET | Health check EU | curl -s https://{staging_api_eu}/v1/health | 200 | "status" |
| API-003 | /v1/<endpoint> | POST | Happy path | curl -s -X POST ... -d '{...}' | 200/201 | <expected fields> |
| API-004 | /v1/<endpoint> | POST | Missing auth | curl -s -X POST ... (no token) | 401 | "unauthorized" or "Unauthorized" |
| ... | ... | ... | ... | ... | ... | ... |

## Category B: Browser Flow Tests

For EACH affected browser flow (from impact map):

| ID | Flow | URL | Steps to Execute | Expected Visual State | Screenshot Name |
|----|------|-----|-----------------|----------------------|-----------------|
| BROWSER-001 | <flow name> | /app/<page> | 1. Navigate 2. Wait for load 3. Verify <element> | <what should be visible> | browser-001-<flow>.png |
| BROWSER-002 | ... | ... | ... | ... | ... |

**Each browser test MUST specify:**
- Exact URL to navigate to
- Specific elements to check (by data-testid, role, or visible text)
- What the expected visual state looks like — WITH SPECIFIC ELEMENTS from regression-ui-library (not just "page loads")
- **Negative checks**: what should NOT be visible (e.g., "Guest banner absent for authenticated users", "No funnel stage header overlapping nav")
- Layout expectations (no overlaps, no truncation, nav items not wrapping)
- Console error expectation (usually: none)

## Category C: Regression Tests (Minimum 5)

Core flows NOT directly changed that must still work:

| ID | Flow | URL | Steps to Execute | Expected Visual State | Screenshot Name |
|----|------|-----|-----------------|----------------------|-----------------|
| REGR-001 | Auth: Sign in | /app | Enter QA credentials, click Sign In | Dashboard loads, user name visible in header | regr-001-signin.png |
| REGR-002 | Chat: Input | /app (chat tab) | Click chat input, type test message | Chat input accepts text, no JS errors | regr-002-chat-input.png |
| REGR-003 | History tab | /app (history tab) | Click History tab, wait for content | History list or empty state renders | regr-003-history.png |
| REGR-004 | Settings tab | /app (settings tab) | Click Settings tab, wait for content | Settings panels render correctly | regr-004-settings.png |
| REGR-005 | Tab navigation | /app | Click through all tabs sequentially | Each tab loads without error, correct content | regr-005-tabs.png |
| ... | (add more if shared dependencies changed) | ... | ... | ... | ... |

## Category D: Edge Cases & Known Gotchas

| ID | Description | How to Test | Expected Result | Evidence Type |
|----|-------------|-------------|-----------------|---------------|
| EDGE-001 | Console errors on page transitions | Navigate between 3+ pages, check console after each | No uncaught exceptions | Console log dump |
| EDGE-002 | Mobile viewport rendering | Resize browser to 390x844, navigate to /app | No overflow, no clipping, touch targets ≥44px | Screenshot |
| EDGE-003 | <gotcha from KI> | <specific steps> | <expected behavior> | Screenshot or curl |
| ... | ... | ... | ... | ... |
```

### 5. Validate Test Plan Completeness

Before proceeding, verify these minimum coverage rules:

- [ ] Every changed API route has at least 2 test cases (happy path + error)
- [ ] Every affected browser flow has at least 1 test case with specific expected state
- [ ] At least 5 regression test cases for unrelated core flows
- [ ] At least 2 edge case tests
- [ ] Total test cases >= max(10, number_of_changed_files)
- [ ] Every browser/regression test specifies a screenshot filename
- [ ] Every browser test includes "negative checks" (what should NOT be visible — e.g., "Guest banner absent for authenticated users", "No funnel header overlapping nav")
- [ ] Every browser test specifies expected visual elements from regression-ui-library (not just "page loads")
- [ ] Every API test includes the full curl command (copy-paste ready)

```
TaskUpdate(taskId="11", status="completed")
```

---

## Step 10b: Deploy to Staging

```
TaskUpdate(taskId="12", status="in_progress")
```

> [!IMPORTANT]
> Always use `deploy-staging-fresh.sh` — it builds a new Docker image AND deploys. The plain cloudbuild YAML only deploys an existing image without rebuilding.

### 1. Fresh Build + Deploy

```bash
./infra/deploy-staging-fresh.sh
```

Wait for deploy to complete (typically 3-5 minutes).

### 2. Health Check

```bash
# US region
curl -s https://{staging_api_us}/v1/health

# EU region
curl -s https://{staging_api_eu}/v1/health
```

Both must return `200` with `"status"` in the body. If either fails, diagnose before proceeding — do NOT execute the test plan against a broken staging environment.

### 3. Frontend Check

```bash
curl -s -o /dev/null -w "%{http_code}" https://{staging_frontend}/app
```

Must return `200`. If the frontend deploy didn't happen as part of the staging script, deploy it manually:

```bash
cd {frontend_dir} && rm -rf .next out && npm run build && \
  npx wrangler pages deploy out --project-name={frontend_project} --branch=staging --commit-dirty=true
cd ..
```

### 4. Frontend Content Verification (MANDATORY — prevents QA on stale frontend)

> [!CRITICAL]
> The deploy script's frontend section often times out. You MUST verify the frontend actually has the latest code before proceeding to QA. Without this check, the QA subagent will test stale pages and miss bugs or report false 404s.

Pick 2-3 pages that were changed in this release and verify they render on staging:

```bash
# Check a changed landing page (pick from git diff)
curl -s -o /dev/null -w "%{http_code}" https://{staging_frontend}/<changed-page-path>

# Check the app loads
curl -s -o /dev/null -w "%{http_code}" https://{staging_frontend}/app
```

**If any changed page returns 404**: the frontend was NOT deployed. Deploy manually (see step 3 above) and re-verify. Do NOT proceed to QA until the frontend is confirmed current.

**If the frontend build fails**: fix the build error, commit, push, rebuild, and redeploy. Build errors from merged PRs are pre-release blockers.

```
TaskUpdate(taskId="12", status="completed")
```

---

## Step 10b.5: Stripe E2E Sandbox Tests

```
TaskUpdate(taskId="<stripe_task>", status="in_progress")
```

> [!IMPORTANT]
> **MANDATORY when the release touches billing code.** If `git diff --name-only $(git describe --tags --abbrev=0)..HEAD` includes billing-related files (payment services, webhook handlers, subscription routes), this step is required. If no billing code changed, skip to Step 10c.

### Authentication Setup

Get staging auth tokens (required for all authenticated API calls):

```bash
# 1. Get secrets
FIREBASE_KEY=$(gcloud secrets versions access latest --secret="{FIREBASE_WEB_API_KEY}" --project="{gcp_project_id}")
FWDSECRET=$(gcloud secrets versions access latest --secret="{FORWARDING_SECRET_STAGING}" --project="{gcp_project_id}")
STRIPE_KEY=$(gcloud secrets versions access latest --secret="{STRIPE_API_KEY_STAGING}" --project="{gcp_project_id}")

# 2. Get Firebase ID token (QA credentials from {credentials_file})
ID_TOKEN=$(curl -s -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FIREBASE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"<QA_EMAIL>","password":"<QA_PASSWORD>","returnSecureToken":true}' | \
  python3 -c "import json,sys; print(json.load(sys.stdin).get('idToken',''))")

# 3. Exchange for your product JWT
ACCESS_TOKEN=$(curl -s -X POST "https://{staging_api_eu}/v1/auth/token" \
  -H "X-Forwarding-Secret: $FWDSECRET" \
  -H "Content-Type: application/json" \
  -d "{\"id_token\": \"$ID_TOKEN\", \"region\": \"eu\"}" | \
  python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")
```

**Auth headers for all staging API calls:**
- `X-Forwarding-Secret: $FWDSECRET`
- `Authorization: Bearer $ACCESS_TOKEN`

### Stripe Test Scenarios (Execute ALL)

Spawn a dedicated Stripe e2e agent:

```
Task(subagent_type="general-purpose", mode="bypassPermissions", prompt="""
# Stripe E2E Sandbox Tests on Staging

Execute ALL scenarios below against the Stripe sandbox and the product staging API.

## Setup
[Get all secrets as described in the auth setup above]
Staging API EU: https://{staging_api_eu}
Staging API US: https://{staging_api_us}

## Scenarios

### S1: Customer Verification
Verify test account has a Stripe customer:
curl -s https://api.stripe.com/v1/customers -u "$STRIPE_KEY:" -d "email=<QA_EMAIL>" -G --data-urlencode "limit=1"

### S2: List Existing Subscriptions
curl -s "https://api.stripe.com/v1/subscriptions?customer=$CUSTOMER_ID&limit=5" -u "$STRIPE_KEY:"

### S3: Checkout Session Creation
Create a checkout session via staging API:
curl -s -X POST "https://{staging_api_eu}/v1/billing/checkout" \
  -H "X-Forwarding-Secret: $FWDSECRET" -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" -d '{"plan_type":"<PLAN_NAME>","billing_cadence":"monthly"}'

### S4: Webhook Event History
curl -s "https://api.stripe.com/v1/events?limit=5&type=checkout.session.completed" -u "$STRIPE_KEY:"

### S5: Subscription Status via API
curl -s "https://{staging_api_eu}/v1/billing/subscription-status" \
  -H "X-Forwarding-Secret: $FWDSECRET" -H "Authorization: Bearer $ACCESS_TOKEN"
MUST return 200 with plan details and period dates.

### S6: Credit/Usage Balance
curl -s "https://{staging_api_eu}/v1/billing/balance" \
  -H "X-Forwarding-Secret: $FWDSECRET" -H "Authorization: Bearer $ACCESS_TOKEN"
Or check via /v1/stats endpoint.

### S7: Coupon/Promo Code Listing
curl -s "https://api.stripe.com/v1/coupons?limit=5" -u "$STRIPE_KEY:"
curl -s "https://api.stripe.com/v1/promotion_codes?limit=5" -u "$STRIPE_KEY:"

### S8: Invoice Retrieval
curl -s "https://api.stripe.com/v1/invoices?customer=$CUSTOMER_ID&limit=5" -u "$STRIPE_KEY:"

### S9: Price ID Validation
Verify all staging price IDs are valid and active:
for PRICE in PLAN_A PLAN_B PLAN_C; do
  PRICE_ID=$(gcloud secrets versions access latest --secret="{STRIPE_PRICE_ID_STAGING}_$PRICE" --project="{gcp_project_id}")
  curl -s "https://api.stripe.com/v1/prices/$PRICE_ID" -u "$STRIPE_KEY:" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{PRICE}: {d.get(\"unit_amount\",\"?\")} {d.get(\"currency\",\"?\")} active={d.get(\"active\",\"?\")}')"
done

### S10: Webhook Endpoint Configuration
curl -s "https://api.stripe.com/v1/webhook_endpoints?limit=10" -u "$STRIPE_KEY:"
Verify staging endpoint exists with correct event types.

### S11: Subscription Create + Cancel Lifecycle
Create test subscription → verify → cancel → verify canceled:
SUB=$(curl -s https://api.stripe.com/v1/subscriptions -u "$STRIPE_KEY:" \
  -d "customer=$CUSTOMER_ID" -d "items[0][price]=$PLAN_A_PRICE_ID" \
  -d "payment_behavior=default_incomplete" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
curl -s -X DELETE "https://api.stripe.com/v1/subscriptions/$SUB" -u "$STRIPE_KEY:"

### S12: Refund Flow
curl -s "https://api.stripe.com/v1/charges?customer=$CUSTOMER_ID&limit=3" -u "$STRIPE_KEY:"
If charges exist, test partial refund on smallest charge.

## Output
Write results to output/pre-release-YYYYMMDD/STRIPE_E2E_RESULTS.md with:
- Summary table (ID, Scenario, Status, Notes)
- Detailed per-scenario curl responses
- Findings section for any failures
""")
```

### Stripe E2E Gate

| Result | Action |
|--------|--------|
| All PASS | Proceed to Step 10c |
| Any FAIL on S5 (subscription status) | **BLOCK** — user-facing regression |
| Any FAIL on S3 (checkout) | **BLOCK** — checkout is critical path |
| Any FAIL on S9 (price validation) | **BLOCK** — invalid prices break billing |
| Any FAIL on S11 (lifecycle) | **BLOCK** — subscription management broken |
| FAIL on S7/S8/S10/S12 | **PROCEED WITH CAVEATS** — create GH issue |

```
TaskUpdate(taskId="<stripe_task>", status="completed")
```

---

## Step 10c: Execute Test Plan (QA Subagent)

```
TaskUpdate(taskId="13", status="in_progress")
```

> [!IMPORTANT]
> Delegate test plan execution to a QA subagent. The subagent receives the test plan and executes EVERY test case — no skipping, no sampling. Every test case produces evidence (curl response or screenshot). This is the core of the pre-release QA.

### Spawn QA Subagent

```
Task(subagent_type="qa-engineer", prompt="""
# Pre-Release QA: Execute Test Plan on Staging

You are a QA engineer executing a pre-release test plan against the product staging environment. Your job is to execute EVERY test case systematically and record evidence for each one.

## Inputs
- **Test plan**: Read `output/pre-release-YYYYMMDD/TEST_PLAN.md` first — this is your contract
- **Staging API US**: https://{staging_api_us}
- **Staging API EU**: https://{staging_api_eu}
- **Staging frontend**: https://{staging_frontend}/app
- **QA credentials**: Read from `{credentials_file}`

## Execution Rules (NON-NEGOTIABLE)
1. Execute ALL test cases. Do not skip any. Do not sample.
2. Take a SEPARATE screenshot for EVERY browser/regression/visual test case. Not 3 screenshots for 20 tests — one screenshot per test.
3. Record the full curl response for EVERY API test case.
4. If a test is BLOCKED (e.g., requires paid subscription, feature not deployed), mark as BLOCKED with the reason — do not mark as PASS.
5. If you discover something broken NOT in the test plan, add it as an extra finding (EXTRA-001, EXTRA-002, etc.).
6. Do NOT fix any issues — only report them.
7. Save ALL screenshots to `output/pre-release-YYYYMMDD/` using the exact filenames from the test plan.
8. **CRITICAL — VERIFY BEFORE VERDICT**: After EVERY navigation and BEFORE marking any browser test as PASS:
   a. Use `read_page` or `get_page_text` to read the actual page content
   b. Verify the expected elements from the test plan are PRESENT (tab heading, key text, components)
   c. If the page shows content from a DIFFERENT page/tab (e.g., still showing Settings when testing Tasks), mark as **INVALID** — never PASS
   d. For mobile viewport tests: verify no text truncation, no horizontal overflow, touch targets >= 44px
   e. The pattern is: `navigate → wait → read_page → VERIFY content matches expected → screenshot → verdict`
   f. A screenshot alone is NOT evidence of a PASS — the page content must match the test case description
9. **CRITICAL — ADAPTIVE BEHAVIOR**: You are a QA engineer, not a script runner. You MUST react to what you observe:
   a. **If navigation fails** (page shows wrong content): DIAGNOSE why (modal blocking? menu open? wrong URL?), then FIX (dismiss modal, close menu, navigate via URL) and RETRY (max 2 retries)
   b. **If 2+ consecutive tests show the same page**: STOP. The previous action broke navigation. Investigate before continuing.
   c. **If you see an error state** (blank page, spinner stuck, JS error): screenshot the error as evidence, report FAIL with details, try ONE reload before moving on
   d. **If a button/link doesn't respond**: try alternative interaction (JS click via `javascript_tool`, direct URL navigation, keyboard shortcut)
   e. **NEVER take the same screenshot twice and call them different tests** — if read_page returns identical content as the previous test, your navigation failed and you must fix it before proceeding
10. **CRITICAL — VISUAL ANOMALY DETECTION**: After reading page content, actively scan for anomalies. Report as EXTRA findings even if the test case itself passes:
   a. **Contradictory state indicators**: "guest mode" shown for authenticated users, "checking verification" for verified users, loading spinners that never resolve
   b. **Layout/overflow issues**: text wrapping into other elements, overlapping nav items, cropped content, horizontal scrollbars, elements touching viewport edges
   c. **Contrast/readability**: text barely visible against background, status indicators with poor contrast, important info that blends into the background
   d. **Mismatched CTAs**: "Start Free Trial" on a paid landing page, "Sign Up" when user is logged in, wrong pricing shown
   e. **Ghost elements**: empty table rows with visible borders but no content, placeholder text that should have been replaced, [object Object] in UI
   f. **Stale/broken components**: funnel stage headers cluttering pages, referral badges overlapping nav, changelog entries interleaving with unrelated content
   g. **Rule**: A page can functionally PASS (correct content present) but still have visual FINDINGS. Report both. Visual issues are not lesser than functional ones — they are release-blocking if they affect user perception.

## Execution Protocol

### Category A: API Endpoint Tests

For EACH API test case in the plan:

```bash
# Execute the curl command from the test plan, adding timing
curl -s -w "\nHTTP_STATUS:%{http_code}\nTIME:%{time_total}s" \
  -X <METHOD> "<STAGING_URL><PATH>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '<PAYLOAD>'
```

Record: HTTP status code, first 500 chars of response body, response time.
Compare against expected status and expected body from the test plan.
Verdict: PASS if both match, FAIL if either differs.

### Category B + C: Browser & Regression Tests

> **CRITICAL: Use `chrome-devtools` MCP tools for ALL browser interactions.**
> DO NOT use osascript, screencapture, macOS Quartz, or mcp__claude-in-chrome__* tools.
> The chrome-devtools MCP `take_screenshot` saves directly to disk via `filePath`.

**Setup (MANDATORY — do this first, before any browser tests):**

1. Load and list pages: `ToolSearch("select:mcp__chrome-devtools__list_pages")` → `mcp__chrome-devtools__list_pages()`
2. Create a fresh page: `ToolSearch("select:mcp__chrome-devtools__new_page")` → `mcp__chrome-devtools__new_page(url="https://{staging_frontend}/app")`
3. Ensure output directory exists: `Bash("mkdir -p output/pre-release-YYYYMMDD")`

**Tool loading pattern** — each chrome-devtools tool is deferred and must be loaded via ToolSearch before first use:
```
ToolSearch("select:mcp__chrome-devtools__navigate_page")
ToolSearch("select:mcp__chrome-devtools__take_screenshot")
ToolSearch("select:mcp__chrome-devtools__take_snapshot")
ToolSearch("select:mcp__chrome-devtools__click")
ToolSearch("select:mcp__chrome-devtools__fill")
ToolSearch("select:mcp__chrome-devtools__wait_for")
ToolSearch("select:mcp__chrome-devtools__list_console_messages")
ToolSearch("select:mcp__chrome-devtools__evaluate_script")
```

**Login:**
1. Navigate to `/app`: `mcp__chrome-devtools__navigate_page(pageId, "https://{staging_frontend}/app")`
2. Click "Regístrate Gratis" / "Register Free" button: `mcp__chrome-devtools__click(pageId, "button")`
3. Toggle to login mode ("Already have an account? Sign in")
4. Fill email/password: `mcp__chrome-devtools__fill(pageId, "input[type='email']", email)` + `mcp__chrome-devtools__fill(pageId, "input[type='password']", password)`
5. Submit and wait for dashboard: `mcp__chrome-devtools__click(pageId, "button[type='submit']")`
6. Dismiss onboarding wizard / disclaimer modals if they appear

**For EACH browser/regression test case:**
1. `mcp__chrome-devtools__navigate_page(pageId, url)` — navigate
2. `mcp__chrome-devtools__wait_for(pageId, selector, timeout=5000)` — wait for key element
3. Interact: `mcp__chrome-devtools__click`, `mcp__chrome-devtools__fill` as needed
4. `mcp__chrome-devtools__take_snapshot(pageId)` — read page content, **verify expected elements**
5. `mcp__chrome-devtools__take_screenshot(pageId, filePath="/absolute/path/output/pre-release-YYYYMMDD/<test-name>.png")` — save to disk
6. `mcp__chrome-devtools__list_console_messages(pageId)` — check for errors
7. Record verdict (PASS only if snapshot confirms expected content)

**Logout + Relogin (mandatory):**
- Navigate to Settings, click "Cerrar Sesión" / "Log out"
- If button not found, use `evaluate_script` to clear localStorage/sessionStorage/cookies + reload
- Re-login using the same flow above
- Screenshot the dashboard after re-login → proves auth flow works end-to-end

### Category D: Edge Case Tests

Execute per the method specified in each test case (screenshot, curl, console check, etc.).

## Output

Write ALL results to `output/pre-release-YYYYMMDD/TEST_RESULTS.md` with this EXACT structure:

```markdown
# Test Execution Results

- Executed by: QA Subagent
- Date: YYYY-MM-DD HH:MM
- Staging build: <version from health check if available>
- Test plan: TEST_PLAN.md
- Total test cases: <N>
- Execution time: <total minutes>

## Results Summary

| Category | Total | Passed | Failed | Blocked |
|----------|-------|--------|--------|---------|
| A: API Endpoints | | | | |
| B: Browser Flows | | | | |
| C: Regression | | | | |
| D: Edge Cases | | | | |
| **TOTAL** | | | | |

## Category A: API Endpoint Tests — Detailed Results

| ID | Endpoint | Method | Expected Status | Actual Status | Actual Body (first 200 chars) | Time | Verdict |
|----|----------|--------|----------------|---------------|-------------------------------|------|---------|
| API-001 | /v1/health | GET | 200 | 200 | {"status":"ok","region":"us"} | 0.3s | PASS |
| API-002 | ... | ... | ... | ... | ... | ... | ... |

## Category B: Browser Flow Tests — Detailed Results

| ID | Flow | Expected State | Actual State | Screenshot | Console Errors | Verdict |
|----|------|---------------|--------------|------------|----------------|---------|
| BROWSER-001 | <flow> | <from plan> | <what you actually saw> | ![](browser-001-flow.png) | None | PASS |

## Category C: Regression Tests — Detailed Results

| ID | Flow | Expected State | Actual State | Screenshot | Console Errors | Verdict |
|----|------|---------------|--------------|------------|----------------|---------|
| REGR-001 | Sign in | Dashboard loads, user name visible | Dashboard loaded, "{project_owner}" in header | ![](regr-001-signin.png) | None | PASS |

## Category D: Edge Cases — Detailed Results

| ID | Description | Expected | Actual | Evidence | Verdict |
|----|-------------|----------|--------|----------|---------|
| EDGE-001 | Console errors on nav | No uncaught exceptions | 0 errors after 4 transitions | Console dump clean | PASS |

## Failures & Extra Findings

### FAIL: <test-id> — <short title>
- **Expected**: <what should have happened>
- **Actual**: <what actually happened>
- **Evidence**: ![](screenshot.png) or curl response
- **Severity**: Critical / High / Medium / Low
- **Impact**: <what user-facing behavior is affected>

### EXTRA-001: <unexpected finding>
- **Discovered during**: <which test case>
- **Description**: <what was found>
- **Evidence**: ![](extra-001.png)
- **Severity**: Critical / High / Medium / Low
```

## Quality Check Before Finishing
Before marking yourself complete, verify:
- [ ] Every test case from TEST_PLAN.md has a row in TEST_RESULTS.md
- [ ] Every browser/regression test has a screenshot file saved
- [ ] Every API test has recorded the actual HTTP status and body
- [ ] Verdicts are honest — FAIL means FAIL, not "PASS with minor issue"
""")
```

Wait for the QA subagent to complete. It will produce:
- `output/pre-release-YYYYMMDD/TEST_RESULTS.md` — structured results with per-test verdicts
- `output/pre-release-YYYYMMDD/*.png` — one screenshot per browser/regression/visual test case

```
TaskUpdate(taskId="14", status="completed")
```

---

## Step 10c.5: QA Report Validation (Adversarial Review)

```
TaskCreate(subject="10c.5: Validate QA Report", description="Adversarial reviewer verifies QA execution was honest, complete, and coherent", activeForm="Validating QA report")
TaskUpdate(taskId="<new_id>", status="in_progress")
```

> [!IMPORTANT]
> Before generating the final report, an INDEPENDENT reviewer validates the QA execution.
> This catches lazy screenshots, wrong-tab captures, unjustified verdicts, and missing coverage.
> The reviewer has NOT seen the QA execution — it reviews the artifacts cold.

### Spawn QA Reviewer

```
Task(subagent_type="general-purpose", prompt="""
# QA Report Validation — Adversarial Review

Read your review protocol first: Read("{qa_reviewer_config}")

Then validate the QA execution:

## Inputs
- **Test plan**: Read `output/pre-release-YYYYMMDD/TEST_PLAN.md`
- **QA report**: Read `output/pre-release-YYYYMMDD/REPORT_WITH_SCREENSHOTS.md`
- **Screenshots**: `output/pre-release-YYYYMMDD/*.png` — Read each one to visually verify
- **Origin context**: `git log <last-tag>..HEAD --oneline`

## Your job
1. **Completeness audit**: Every test case in the plan has a result in the report
2. **Screenshot coherence**: Read each .png file, verify it matches what the report claims
3. **Verdict coherence**: PASS/FAIL verdicts are supported by the evidence
4. **Acceptance criteria**: Every issue has adequate test coverage
5. **Suspicious patterns**: Duplicate screenshots, blind PASSes, missing evidence

## Output
Write your review to `output/pre-release-YYYYMMDD/QA_REVIEW.md` with:
- Per-screenshot visual verification (what you see vs what report claims)
- Decision: ACCEPT or REJECT with specific objections
- If REJECT: list exactly which tests must be re-executed

Be adversarial. Assume the QA executor was sloppy until proven otherwise.
""")
```

### Handle Review Decision

| Decision | Action |
|----------|--------|
| **ACCEPT** | Proceed to Step 10d (final report + release gate) |
| **ACCEPT WITH NOTES** | Proceed to 10d, include reviewer notes in final report |
| **REJECT** | Feed rejected tests back to QA executor for re-execution (see below) |

**If REJECT — Feedback Loop (max 2 cycles):**

1. Read `QA_REVIEW.md` — extract the specific test IDs that were rejected and WHY
2. Re-spawn the QA executor with ONLY the rejected tests:

```
Task(subagent_type="qa-engineer", prompt="""
# QA Re-Execution — Rejected Tests Only

The QA reviewer REJECTED the following tests. Read the review for details:
Read("output/pre-release-YYYYMMDD/QA_REVIEW.md")

## Reviewer Findings
[paste the specific rejections: which tests, what was wrong, what evidence was missing]

## Your Task
Re-execute ONLY these rejected tests. For each one:
1. Navigate to the CORRECT page via `mcp__chrome-devtools__navigate_page` (reviewer caught wrong-page screenshots)
2. Use ONLY ONE Chrome page (reviewer caught duplicate screenshots from wrong tabs)
3. Use `mcp__chrome-devtools__take_snapshot` to verify page content BEFORE screenshotting
4. Save screenshot via `mcp__chrome-devtools__take_screenshot(pageId, filePath=...)` — always use absolute paths
5. Read back every screenshot to verify it shows the right content
6. Update REPORT_WITH_SCREENSHOTS.md with corrected results for these tests ONLY
   (do not change the results for tests that were ACCEPTED)

## Anti-Patterns the Reviewer Caught (DO NOT REPEAT)
- Duplicate screenshots (same file for different tests) — use ONE page, navigate between tests
- Wrong page in screenshot — verify URL and content via take_snapshot before capturing
- Report claims elements not visible in screenshot — only claim what you can prove
- Using osascript/screencapture instead of chrome-devtools MCP — always use MCP tools
""")
```

3. After re-execution, re-submit to the QA reviewer:

```
Task(prompt="Re-validate the updated QA report. Read QA_REVIEW.md for previous rejection reasons.
Focus ONLY on the previously-rejected tests. Verify the fixes address the specific objections.
Write updated review to QA_REVIEW_v2.md. Decision: ACCEPT or REJECT.")
```

4. If rejected again (cycle 2): escalate to user for manual decision
5. If accepted: proceed to Step 10d

### Step 10d-gate: Release Gate Decision

After QA reviewer accepts the report, make the final release decision based on findings:

| Finding Severity | Release Action |
|-----------------|----------------|
| No findings | **PROCEED** — create release tag |
| Low-severity only | **PROCEED** — document in release notes |
| Medium-severity (non-blocking) | **PROCEED WITH CAVEATS** — create GH issues for each finding |
| High-severity (user-facing regression) | **BLOCK** — return to bugfix. Do NOT release. |
| Critical (data loss, security, auth broken) | **BLOCK** — immediate bugfix, re-run full QA |
| **Visual anomaly** (contradictory state, layout broken, wrong CTA) | **BLOCK** — visual bugs are user-facing regressions |

> **IMPORTANT**: Visual issues ARE release blockers. "Guest mode" shown to a logged-in user, broken nav layout, wrong CTA text — these are all user-facing regressions that degrade trust and conversion. Never classify visual anomalies as "Low" just because the page "functionally loads."

**If BLOCK:**
1. Create GH issues + Linear issues for each blocking finding
2. Return to implementation — fix the issues
3. Run unit/integration tests locally for changed files (catch regressions before deploy)
4. Re-deploy to staging (`./infra/deploy-staging-fresh.sh`)
5. Re-run FULL test plan (not just the failed tests) — fixes can introduce regressions elsewhere
6. Re-submit for QA review

**If PROCEED WITH CAVEATS (medium-severity findings that are fixable):**
1. Fix the medium-severity findings before proceeding
2. Run unit/integration tests locally for changed files
3. Re-deploy to staging
4. **Targeted retest**: Re-run test cases for fixed features + 5 randomly selected regression tests
5. Generate updated `REPORT_WITH_SCREENSHOTS.md` with retest results appended
6. Create GH issues for any findings deferred to next release
7. Proceed to `/release` workflow

> [!IMPORTANT]
> **Fix-then-retest is mandatory.** Never mark a finding as "will fix later" if it can be fixed now.
> Code changes made during prerelease (even trivial fixes) require verification — they are untested
> code entering a release. The retest scope scales with fix scope:
> - Single-file cosmetic fix → targeted retest of that feature + 5 regression tests
> - Multi-file fix → full test plan re-execution
> - No fix needed → proceed as-is

**If PROCEED (all PASS / low-severity only):**
1. Generate final `REPORT_WITH_SCREENSHOTS.md` (already done by QA executor)
2. Create GH issues for any low-severity findings to track
3. Proceed to `/release` workflow

```
TaskUpdate(taskId="<new_id>", status="completed")
```

---

## Step 10d: Generate QA Report

```
TaskUpdate(taskId="14", status="in_progress")
```

> [!IMPORTANT]
> The final report must be detailed enough for the user to visually verify that testing was thorough — not shallow. Every test case must have evidence. The report makes the release gate decision.

### 1. Read Test Results

Read `output/pre-release-YYYYMMDD/TEST_RESULTS.md` and verify all screenshots exist.

### 2. Coverage Audit

Count planned vs executed test cases and verify 1:1 evidence:

| Metric | Planned | Executed | Evidence Items | Gap |
|--------|---------|----------|---------------|-----|
| API test cases | N | — | curl responses | — |
| Browser flow tests | M | — | screenshots | — |
| Regression tests | R | — | screenshots | — |
| Edge case tests | E | — | screenshots/logs | — |
| **Total** | T | — | — | — |

**Coverage < 100%** → MUST flag which test cases are missing evidence and why.
**Coverage < 90%** → BLOCK the release (insufficient evidence).

### 3. Generate Final Report

Create `output/pre-release-YYYYMMDD/REPORT_WITH_SCREENSHOTS.md`:

```markdown
# Pre-Release QA Report

- Date: YYYY-MM-DD
- Version: vX.Y.Z (pending)
- Staging API: https://{staging_api_us}
- Staging Frontend: https://{staging_frontend}/app
- QA Account: <email used>
- Outcome: **PASS** | **PARTIAL PASS** | **FAIL**
- Test Plan: [TEST_PLAN.md](TEST_PLAN.md)
- Test Results: [TEST_RESULTS.md](TEST_RESULTS.md)

## Executive Summary

| Metric | Count |
|--------|-------|
| Total test cases | <N> |
| Passed | <P> |
| Failed | <F> |
| Blocked | <B> |
| Extra findings | <X> |
| Screenshots taken | <S> (expected: <browser + regression + visual edge tests>) |
| **Release recommendation** | **PROCEED** / **BLOCK** / **PROCEED WITH CAVEATS** |

## Coverage Audit

| Category | Planned | Executed | With Evidence | Coverage |
|----------|---------|----------|--------------|----------|
| A: API Endpoints | N | N | N | 100% |
| B: Browser Flows | M | M | M | 100% |
| C: Regression | R | R | R | 100% |
| D: Edge Cases | E | E | E | 100% |
| **Total** | **T** | **T** | **T** | **100%** |

## Results by Category

### A: API Endpoint Tests

| ID | Endpoint | Method | Status | Response Time | Notes |
|----|----------|--------|--------|--------------|-------|
| API-001 | GET /v1/health (US) | GET | PASS | 0.3s | |
| API-002 | GET /v1/health (EU) | GET | PASS | 0.4s | |
| ... | ... | ... | ... | ... | ... |

### B: Browser Flow Tests

| ID | Flow | Status | Screenshot | Notes |
|----|------|--------|------------|-------|
| BROWSER-001 | <flow> | PASS | ![](browser-001-flow.png) | Elements verified |
| ... | ... | ... | ... | ... |

### C: Regression Tests

| ID | Flow | Status | Screenshot | Notes |
|----|------|--------|------------|-------|
| REGR-001 | Sign in | PASS | ![](regr-001-signin.png) | Dashboard loaded |
| REGR-002 | Chat input | PASS | ![](regr-002-chat-input.png) | Input accepts text |
| REGR-003 | History tab | PASS | ![](regr-003-history.png) | List rendered |
| REGR-004 | Settings tab | PASS | ![](regr-004-settings.png) | Panels visible |
| REGR-005 | Tab navigation | PASS | ![](regr-005-tabs.png) | All tabs load |

### D: Edge Cases

| ID | Description | Status | Evidence | Notes |
|----|-------------|--------|----------|-------|
| EDGE-001 | Console errors on nav | PASS | Console clean | 0 errors |
| ... | ... | ... | ... | ... |

## Findings (if any)

### F1: <title> (Severity: Critical/High/Medium/Low)
- **Test Case**: <test-id that found this>
- **Expected**: <what should have happened>
- **Actual**: <what actually happened>
- **Evidence**: ![](finding-f1.png)
- **GH Issue**: #XX (created for severity >= Medium)

## Residual Risk

<Test cases that were BLOCKED and why. Known limitations. Untestable items.>
```

### 4. Release Gate Decision

| Condition | Decision |
|-----------|----------|
| All test cases PASS | **PROCEED** with release |
| All PASS except Low-severity findings | **PROCEED** (document findings in release notes) |
| Any Medium-severity finding | **PROCEED WITH CAVEATS** (create GH issues for each) |
| Any High or Critical finding | **BLOCK** release until fixed |
| Coverage < 90% | **BLOCK** release (insufficient testing evidence) |

> [!NOTE]
> If release is BLOCKED or findings are fixed during prerelease: fix → local tests → redeploy staging → re-execute test plan (10c). The test plan from 10a can be reused. **Any code change during prerelease, no matter how small, requires retest before release.** Untested fixes are untested code.

```
TaskUpdate(taskId="15", status="completed")
```

---

## Pre-Release Checklist

**Run TaskList to verify all tasks completed:**
```
TaskList()  # All 15 tasks should show status="completed"
```

- [ ] All tests pass (unit, integration, regression)
- [ ] Security audit passed (pip-audit, npm audit, bandit, security-officer agent)
- [ ] No Critical/High CVEs in dependencies
- [ ] No linting/type errors
- [ ] Code properly formatted
- [ ] All changes committed
- [ ] Branch up to date with main
- [ ] All related GitHub issues verified and closed
- [ ] Schema index consistent (no orphans/missing)
- [ ] Documentation up to date
- [ ] **Test plan generated** (`TEST_PLAN.md`) with API + browser + regression + edge case categories
- [ ] **Staging deployed** and health-checked (US + EU + frontend)
- [ ] **Test plan fully executed** by QA subagent — every test case has evidence
- [ ] **QA report generated** (`REPORT_WITH_SCREENSHOTS.md`) with per-test-case results
- [ ] Coverage audit: screenshot count matches browser test case count (1:1)
- [ ] Coverage audit: every API test has recorded actual status + body
- [ ] No Critical/High findings blocking release
- [ ] `TEST_PLAN.md` exists in `output/pre-release-YYYYMMDD/`
- [ ] `TEST_RESULTS.md` exists in `output/pre-release-YYYYMMDD/`
- [ ] `REPORT_WITH_SCREENSHOTS.md` exists with inline screenshots

---

## Step 10e: Generate Automated Tests from QA Verdicts

> After QA review accepts the report, convert automatable QA findings into permanent
> automated tests. This ensures manual QA findings become part of the CI pipeline.

```
TaskCreate(subject="10e: Auto-generate tests from QA verdicts", description="Convert automatable QA verdicts into automated unit/integration tests", activeForm="Generating automated tests from QA")
```

Read all verdict files (or extract from REPORT_WITH_SCREENSHOTS.md) and identify tests
where the QA agent flagged `automatable: true` with `automation_benefit: high|medium`.

```
Task(subagent_type="qa-engineer", prompt="""
Read the QA report: output/pre-release-YYYYMMDD/REPORT_WITH_SCREENSHOTS.md

For each test where the QA agent noted an automation suggestion:
1. Create the automated test in the appropriate file:
   - Emoji/visual checks → {frontend_dir}/__tests__/ui-integrity/emoji-rendering.test.ts
   - i18n checks → {frontend_dir}/__tests__/ui-integrity/i18n-completeness.test.ts
   - Logic checks → {frontend_dir}/__tests__/ui-integrity/component-logic.test.ts
   - API checks → tests/integration/test_<feature>.py
2. Run the test to verify it passes (for PASS verdicts) or fails (for FAIL verdicts)
3. For FAIL verdicts: the automated test should ALSO fail — confirming it catches the same bug
4. Report which tests were created and their pass/fail status

This locks in QA findings as permanent regression tests.
""")
```

**Once complete** → proceed to `/release` workflow.
