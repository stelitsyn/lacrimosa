---
name: browser-qa-via-chrome-devtools
description: Use chrome-devtools MCP for ALL browser QA — full-page screenshots, thorough analysis
type: feedback
---

Use `mcp__chrome-devtools__*` tools for ALL browser QA and browser-required verification/validation operations.

**Why:** chrome-devtools MCP connects to a real Chrome instance with remote debugging. It saves screenshots directly to disk via `filePath`, supports `fullPage=true` for full-page captures, and provides DOM snapshots for content verification. Previous approaches (screencapture/osascript/Playwright) were fragile and only captured the viewport.

**How to apply:**
1. Ensure Chrome is running with `--remote-debugging-port=9222` (use a hook or manual launch)
2. Uses a separate profile to avoid conflicts with normal browsing
3. Load each tool via `ToolSearch("select:mcp__chrome-devtools__<tool>")` before first use
4. **Always use `fullPage=true`** on `take_screenshot` — captures the entire scrollable page, not just viewport
5. **After every screenshot, THOROUGHLY analyze the full page**:
   - Read the screenshot back via `Read(filePath)` — visually inspect top to bottom
   - Use `take_snapshot(pageId)` to get DOM/accessibility tree
   - Verify every expected element from the test plan
   - Check for visual anomalies: overlaps, truncation, broken layouts, wrong colors, missing images
   - Check for state coherence: contradictory banners, wrong CTAs, stale content
   - "It looks fine" is NEVER an acceptable analysis — list specific observations
6. Use for: pre-release QA, Lacrimosa verification, /verify-flows, visual QA loop, any browser validation
