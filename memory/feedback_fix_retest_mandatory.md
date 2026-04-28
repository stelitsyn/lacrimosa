---
name: Fix-Retest Mandatory
description: All code fixes during prerelease/bugfix/review require retesting — fixes are untested code
type: feedback
---

Fixes require retest — always. Any code change made during prerelease, bugfix, or review MUST be retested before declaring the fix complete.

**Why:** Fixes were applied without verification during pre-release analysis. Untested fixes can introduce regressions. "Just fixing isn't enough."

**How to apply:**
- After fixing a pre-release finding: run unit tests for changed files + verify on staging
- Retest scope scales: single-file cosmetic fix -> targeted retest; multi-file change -> full regression
- "I fixed it" without evidence is not a fix
