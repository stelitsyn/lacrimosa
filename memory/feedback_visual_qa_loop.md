---
name: visual-qa-feedback-loop
description: All visual changes require autonomous screenshot-based QA loop — agents fix issues themselves and re-verify until clean
type: feedback
---

Any change to visual files (CSS, components, layouts, images, SVGs, themes, copy) MUST go through an autonomous visual QA loop during review. Agents screenshot, analyze, fix, re-screenshot, and loop until clean.

**Why:** Dark theme shipped with unreadable text, white panels on dark background, and faint gradients because the review loop only took full-page screenshot thumbnails. Visual issues are invisible at thumbnail scale. The agent reported "PASS" without zooming into individual components.

**How to apply:**
1. Auto-triggers for any visual file change (CSS, components, layouts, images, themes)
2. Agents take **close-up screenshots** of each component type at native resolution (not just full-page)
3. Agents **analyze** each screenshot for: readability, layout, spacing, theme consistency, regressions
4. Agents **fix issues directly** — they don't just report them
5. After fixing, **re-screenshot and re-analyze** in a loop (max 5 iterations)
6. Report includes contrast ratio table + component screenshots as evidence
7. This applies to ALL visual changes — any CSS, component, layout, image, font, spacing change
