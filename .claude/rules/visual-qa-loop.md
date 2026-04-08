# Visual QA Loop (Autonomous)

> **Trigger**: Any change that affects what users see — CSS, components, layouts, images, SVGs, theme files, copy, icons, fonts, spacing, responsive breakpoints.
> **Phase**: Mandatory part of Phase 4.1 (Review Loop) and Phase 5 (Verification).
> **Mode**: Fully autonomous — agents fix issues themselves, re-verify, and loop until clean.

## When This Rule Applies

If `git diff --name-only` touches ANY of:
- Style files: `*.css`, `*.module.css`, `*.scss`, tailwind config, design tokens
- Component files: `*.tsx`, `*.jsx` in `components/`, `app/`
- Assets: `*.svg`, `*.png`, `*.jpg`, `*.ico`, fonts
- Layout files: `layout.tsx`, page files, navigation, header, footer, sidebar
- Theme: `theme.ts`, `ThemeToggle`, `ThemeProvider`, color definitions
- Copy/text: i18n files, content files, hardcoded strings in components

**Simple test**: "Could this change make anything look different?" → Yes → Visual QA Loop required.

## The Loop

```
IMPLEMENT → SCREENSHOT → ANALYZE → ISSUES? → FIX → SCREENSHOT → ANALYZE → LOOP
                                      ↓ no
                                   APPROVE
```

**Max iterations**: 5. If still failing → escalate to user with screenshots of remaining issues.

## Step 1: Screenshot Capture

Use `chrome-devtools` MCP tools for all browser interactions. Do NOT use screencapture, osascript, or Playwright.

**Tool loading**: Each chrome-devtools tool is deferred — load via `ToolSearch("select:mcp__chrome-devtools__<tool>")` before first use.

### A. Full-page screenshots (MANDATORY for every page)
- Use `mcp__chrome-devtools__take_screenshot(pageId, filePath=..., fullPage=true)` — captures the entire scrollable page
- Each affected page, both themes if dark mode exists
- Desktop (1440x900) and mobile (390x844) via `mcp__chrome-devtools__resize_page`
- Always use absolute paths for `filePath`

### B. Close-up component screenshots (detail)
- After full-page capture, scroll to each component via `mcp__chrome-devtools__evaluate_script(pageId, "document.querySelector('<selector>').scrollIntoView({block:'center'})")`
- Take viewport screenshot (without fullPage) to get close-up detail
- Cover EVERY component type that was changed or could be affected

### C. Thorough page analysis (MANDATORY after every screenshot)
After taking each screenshot, you MUST:
1. Read the screenshot back via `Read(filePath)` — visually inspect the full image
2. Use `mcp__chrome-devtools__take_snapshot(pageId)` to get the accessibility tree / DOM content
3. Verify EVERY expected element from the test plan is present and correct
4. Check for visual anomalies: overlapping elements, truncated text, broken layouts, missing images, wrong colors
5. Check for state coherence: contradictory banners, wrong CTAs, stale content
6. Record specific observations — "it looks fine" is never an acceptable analysis

**Both themes**: If dark mode exists, screenshot EVERYTHING in both light and dark.

## Step 2: Visual Analysis

Read each screenshot and check for ALL of these categories:

### Readability
- Text contrast against backgrounds (WCAG AA: 4.5:1 normal, 3:1 large text)
- Text on gradients — check at lightest AND darkest gradient points
- Muted/secondary text (most common failure)
- Text over images or translucent overlays

### Layout & Spacing
- Overflow/clipping (text cut off, elements outside containers)
- Alignment issues (misaligned columns, uneven spacing)
- Missing padding/margins causing elements to touch edges
- Responsive breakage at mobile widths

### Visual Consistency
- Hardcoded colors not adapting to theme (white cards on dark bg, dark text on dark bg)
- Missing dark/light mode overrides for specific components
- Inconsistent border, shadow, or opacity treatment across similar components
- Elements that "disappear" against background

### Components
- Broken icons/SVGs (wrong color, not visible)
- Images with wrong aspect ratio or not loading
- Buttons without visible borders or hover states
- Form inputs that blend into background

### Regression
- Anything that looks different from the last known-good state
- Elements that were fine before the change but broke

## Step 3: Fix

For each issue found:
1. Identify the root cause (CSS variable, hardcoded color, missing override, etc.)
2. Fix it — edit the CSS/component directly
3. Don't batch — fix one category at a time so you can verify each

## Step 4: Re-verify

After fixing:
1. Re-take ONLY the screenshots for affected components
2. Re-analyze those screenshots
3. If still failing → fix and re-screenshot (loop)
4. If passing → move to next issue category

## Step 5: Report

Include in `REPORT_WITH_SCREENSHOTS.md`:

```markdown
## Visual QA

### Contrast Audit
| Component | Text | Background | Ratio | WCAG | Status |
|-----------|------|------------|-------|------|--------|
| ... | ... | ... | ... | ... | PASS |

### Visual Checks
| Check | Status | Notes |
|-------|--------|-------|
| Dark mode panels | PASS | All panels use var(--bg-card) |
| Text on gradients | PASS | Promoted to --text-primary in dark |
| Mobile layout | PASS | No overflow at 390px |
| Theme toggle | PASS | Sun/moon icons visible in both themes |

### Screenshots
![Dark hero](visual-qa/01-dark-hero.png)
![Dark cards](visual-qa/02-dark-cards.png)
...
```

## Dispatch Pattern

During Phase 4.1, when visual files are changed:

```
Task(subagent_type="design-reviewer-v3", prompt="""
Visual QA review for: [task description]

Changed files: [list]

MANDATORY: Follow the Visual QA Loop from ~/.claude/rules/visual-qa-loop.md

Use chrome-devtools MCP for ALL browser interactions (load each tool via ToolSearch first):
- mcp__chrome-devtools__new_page / navigate_page / take_screenshot / take_snapshot / click / fill / evaluate_script

1. Open the page via chrome-devtools MCP (local dev server or staging URL)
2. Take FULL-PAGE screenshots (fullPage=true) of EACH affected page in EACH theme
3. Take close-up viewport screenshots of EACH component type
4. Read each screenshot back (Read tool) and THOROUGHLY analyze: readability, layout, consistency, regressions
5. Use take_snapshot to verify DOM content matches visual expectations
6. Fix any issues found directly (edit CSS/components)
7. Re-screenshot and re-verify in a loop until ALL issues are resolved
8. Generate contrast ratio table for text-on-background combinations
9. Report with screenshots

You are autonomous — fix issues yourself, don't just report them.
Take full-page screenshots FIRST, then zoom into individual components.
After EVERY screenshot, read it back and analyze the ENTIRE visible content.
Max 5 fix iterations before escalating.
""")
```

## Quick Reference

| Tool | Command |
|------|---------|
| Contrast audit script | `.venv/bin/python scripts/contrast_audit.py --url http://localhost:3000 --theme both` |
| Dev server | `cd my-frontend && npm run dev -- -p 3000` |
| Company landing server | `cd static-site && python3 -m http.server 8080` |
| Chrome DevTools screenshot | `mcp__chrome-devtools__take_screenshot(pageId, filePath=..., fullPage=true)` |
| Chrome DevTools DOM read | `mcp__chrome-devtools__take_snapshot(pageId)` |
