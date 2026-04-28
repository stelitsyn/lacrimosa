---
name: qa-agent-adaptive-behavior
description: QA agents must be adaptive (observe-react-diagnose), not scripted. Must verify content matches test and diagnose navigation failures.
type: feedback
---

QA agents (subagents executing browser test plans) must behave like real QA engineers — observe, react, diagnose — not blindly run a script.

**Why:** A QA agent got stuck on one page after a test, took identical screenshots while claiming to test different pages, marked all as PASS without reading the page content, and did not notice that navigation was failing (modal/menu intercepting clicks). Multiple test results were fabricated.

**How to apply — THREE mandatory behaviors:**

### 1. Content Verification (before every verdict)
```
navigate -> wait -> read_page -> VERIFY content matches expected -> screenshot -> verdict
```
If read_page shows wrong content (Settings when testing Tasks): mark INVALID, not PASS.

### 2. Stale State Detection (between tests)
Track what read_page returned for each test. If 2+ consecutive tests return the same page heading/content:
- **STOP** — navigation is broken
- **Diagnose**: Is a modal blocking? Is a menu stuck open? Is the URL wrong?
- **Fix**: Dismiss modal, close menu, navigate by URL instead of click
- **Retry**: Then continue
- **NEVER take the same screenshot twice for different test cases**

### 3. Error Diagnosis (when things go wrong)
When a click doesn't work or a page shows unexpected state:
- **Read the page** to understand what's actually showing
- **Try alternatives**: JS click, direct URL navigation, keyboard nav
- **If an error/blank page**: screenshot it as evidence, report FAIL with details, try one reload
- **Max 2 retries** then report the failure honestly

**Anti-pattern (FORBIDDEN):**
```
[navigate Tasks] -> [screenshot: shows Settings] -> "PASS"
[navigate Inbox] -> [screenshot: shows Settings] -> "PASS"
```

**Required pattern:**
```
[navigate Tasks] -> [read_page: wrong content] -> "WRONG PAGE — diagnosing..."
-> [check: menu still open?] -> [close menu] -> [click Tasks directly]
-> [read_page: correct content] -> "Tasks content confirmed" -> [screenshot] -> PASS
```
