---
name: verify-flows
description: "Verify user flows and UI/UX in the product webapp — locally (Playwright headless preferred) or on staging (Chrome browser fallback). Use when: (1) `/verify-flows` is invoked, (2) after implementing UI/frontend changes via /implement or /bugfix, (3) during /pre-release staging browser verification step, (4) when user asks to check/test/verify flows, UI, or UX. Creates a fresh test account (like a real new user), walks through all directly and indirectly touched flows, takes screenshots, and produces REPORT_WITH_SCREENSHOTS.md."
---

# Verify Flows

Verify the webapp user flows with a fresh account. Prefers Playwright headless; falls back to Chrome browser automation when headless can't handle the flow.

---

## Step 1: Discover Affected Flows via Schema CLI

Use schema CLI to understand what flows exist and which are affected by current changes.

```bash
# 1. Get changed files
git diff --name-only HEAD~5  # or main, or last tag

# 2. Discover flow schemas from the Web Portal domain
.venv/bin/python schema_cli.py schema index --domain "Web Portal"

# 3. Read relevant schemas for flow details (auth, dashboard, billing, etc.)
.venv/bin/python schema_cli.py schema read YOUR_AUTH_SCHEMA.md
.venv/bin/python schema_cli.py schema read YOUR_DASHBOARD_SCHEMA.md
.venv/bin/python schema_cli.py schema read YOUR_BILLING_SCHEMA.md

# 4. For non-web-portal flows, search by domain
.venv/bin/python schema_cli.py schema index --domain "Features"
.venv/bin/python schema_cli.py schema index --domain "Core Features"

# 5. Check code map for entry points
.venv/bin/python schema_cli.py ki list --prefix "code."
```

Then load `references/impact-map.md` to map changed files → affected flows (direct + indirect).

**Rules:**
- **Direct touch**: Changed file listed in impact map → flow MUST be verified
- **Indirect touch**: Shared dependency changed (store, api client, useAuth, TabBar, styles) → verify ALL flows using that dependency
- **Minimum**: Always verify Tab Navigation + the primary flow under test
- If invoked standalone (`/verify-flows`), ask user which flows or default to all core flows

---

## Step 2: Choose Environment

```
Is this a /pre-release or staging-mandatory context?
├─ Yes → STAGING (deploy first, then verify)
└─ No → LOCAL preferred
    ├─ Can Playwright handle the flow? (no OAuth popups, no complex 3rd-party JS)
    │   ├─ Yes → LOCAL with Playwright (headless)
    │   └─ No → STAGING with Chrome browser automation
    └─ Is the backend needed for the flow?
        ├─ Yes → Start local backend too, or use STAGING
        └─ No → LOCAL frontend-only
```

| Situation | Use |
|-----------|-----|
| Local dev, standard flows | Playwright headless |
| OAuth popup (Google/Apple sign-in) | Chrome browser |
| Complex modals with 3rd-party JS | Chrome browser |
| Staging verification (pre-release) | Chrome browser |
| Email signup + onboarding | Playwright headless |
| Call polling / real-time updates | Playwright with `wait_for_selector` |

### Local Setup

```bash
cd {frontend_dir} && npm run dev  # http://localhost:3000
```

### Staging Setup

```bash
./infra/deploy-staging-fresh.sh
cd {frontend_dir} && rm -rf .next out && npm run build && \
  npx wrangler pages deploy out --project-name={frontend_project} --branch=staging --commit-dirty=true
cd ..
curl -s https://{staging_api_us}/v1/health
```

---

## Step 3: Get or Create Test Account

Check for an existing account first. Only create a new one if none exists.

```
Credentials file: {credentials_file}
├─ File exists AND has valid account for this environment?
│   ├─ Yes → Sign in with existing credentials (skip signup + onboarding)
│   └─ No  → Create fresh account (full new-user journey: signup → onboarding → first task)
```

### Using existing account

Read credentials from `{credentials_file}` and sign in:

```python
page.goto(f"{base_url}/app")
page.wait_for_load_state("networkidle")
page.fill('input[type="email"]', email)
page.fill('input[type="password"]', password)
page.get_by_role("button", name="Sign In").click()
```

### Creating a fresh account (only when no credentials exist)

```python
import secrets, json, os
from datetime import datetime

email = f"testuser{secrets.token_hex(4)}@example.com"
password = f"TestPass{secrets.token_hex(4)}!"

# ... signup flow ...
page.get_by_role("button", name="Sign Up").click()

# Save credentials for reuse
creds_path = "{credentials_file}"
creds = json.loads(open(creds_path).read()) if os.path.exists(creds_path) else {"staging_webapp_accounts": []}
creds["staging_webapp_accounts"].append({
    "label": f"verify_flows_{datetime.now():%Y%m%d}",
    "email": email,
    "password": password,
    "provider": "email_password",
    "created_at": datetime.now().isoformat(),
    "purpose": "verify-flows skill"
})
open(creds_path, "w").write(json.dumps(creds, indent=2))
```

### Chrome browser (staging fallback — chrome-devtools MCP)

Use `chrome-devtools` MCP tools (load each via `ToolSearch("select:mcp__chrome-devtools__<tool>")` first):

```
mcp__chrome-devtools__new_page(url="https://{staging_frontend}/app")
# fill for email/password, click for buttons
# take_screenshot with fullPage=true for full-page captures
# take_snapshot to read DOM content for thorough analysis
```

**Screenshot rule**: Always use `fullPage=true` to capture the entire scrollable page.
After every screenshot, read it back (`Read(filePath)`) and thoroughly analyze the full content —
verify every expected element, check for visual anomalies, state coherence, and layout issues.

---

## Step 4: Walk Through Flows

For each flow in scope, use schema-discovered verification steps. Use `webapp-testing` skill's `scripts/with_server.py` if dev server isn't running:

```bash
python /path/to/webapp-testing/scripts/with_server.py \
  --server "cd {frontend_dir} && npm run dev" --port 3000 \
  -- python verify_script.py
```

**Per-flow Playwright pattern:**

```python
page.goto(f"{base_url}/app")
page.wait_for_load_state("networkidle")
page.click('[data-testid="..."]')  # or text=, role=, CSS selectors
page.screenshot(path=f"output/verify-flows/{nn}-{flow_name}.png", full_page=True)
assert page.locator('[data-testid="welcome-step"]').is_visible()
```

**Chrome browser pattern (fallback — preferred for Firebase auth flows):**

> **Important**: Chrome MCP `computer(action="screenshot")` is **in-memory only** — it does NOT save files to disk.
> Use macOS `screencapture -l <CGWindowID>` to save PNGs. See `~/.claude/reference/workflow/browser-screenshot-protocol.md`.

```
mcp__claude-in-chrome__navigate(tabId, url)
mcp__claude-in-chrome__computer(action="wait", duration=3)
mcp__claude-in-chrome__read_page(tabId)
# Save screenshot to disk via screencapture (NOT computer(action="screenshot"))
Bash: screencapture -l <CHROME_WINDOW_ID> output/verify-flows-YYYYMMDD/<name>.png
mcp__claude-in-chrome__read_console_messages(tabId, pattern="error|Error")
```

### Console Error Check

**Playwright:**
```python
errors = []
page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
```

**Chrome:** `mcp__claude-in-chrome__read_console_messages(tabId, pattern="error|Error|ERR")`

### Screenshot Naming

```
output/verify-flows-YYYYMMDD/
  01-signup/
    01-signup-form.png
    02-signup-complete.png
  02-onboarding/
    01-welcome-step.png
    ...
  03-chat/
    01-chat-input.png
  REPORT_WITH_SCREENSHOTS.md
```

---

## Step 5: Generate Report

Create `output/verify-flows-YYYYMMDD/REPORT_WITH_SCREENSHOTS.md`:

```markdown
# Flow Verification Report

- Date: YYYY-MM-DD
- Environment: local (localhost:3000) | staging ({staging_frontend})
- Account: <test email used>
- Trigger: /verify-flows | post-implement | pre-release
- Outcome: PASS | PARTIAL PASS | FAIL

## Coverage Matrix

| # | Flow | Status | Screenshot | Notes |
|---|------|--------|------------|-------|
| 1 | Auth: Signup | PASS | ![](01-signup/01-signup-form.png) | New account created |

## Findings

### F1: <title> (Severity: Critical/High/Medium/Low)
- Description: ...
- Screenshot: ![](path.png)
- GH Issue: #XX (if created)

## Console Errors
None | <list>

## Residual Risk
<flows not verifiable or known limitations>
```

---

## Integration with Other Workflows

### After /implement or /bugfix (auto-trigger)

When implementation touches frontend files (`components/`, `hooks/`, `lib/`, `app/`):
1. Auto-trigger after tests pass (Phase 5)
2. Run locally with Playwright against dev server
3. Verify directly + indirectly touched flows
4. Report included in PR body

### During /pre-release (mandatory)

1. Environment: staging (mandatory)
2. Scope: all release-pending features/fixes
3. Fresh account + existing account (regression)
4. Report is the pre-release `REPORT_WITH_SCREENSHOTS.md`

### Standalone: `/verify-flows [scope]`

```
/verify-flows              → all core flows, local
/verify-flows onboarding   → onboarding flows only
/verify-flows staging      → all core flows, staging
/verify-flows auth chat    → auth + chat flows
```

## References

- **[references/impact-map.md](references/impact-map.md)** — File→flow mapping with selectors for impact analysis
- **Schema CLI** — `schema_cli.py schema index --domain "Web Portal"` for flow discovery
- **Schema CLI** — `schema_cli.py schema read <SCHEMA_NAME>` for detailed flow specs
