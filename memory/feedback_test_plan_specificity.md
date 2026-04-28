---
name: Test plans must cover specific features and bugs
description: Pre-release test plans must start with a Release Change Inventory and have dedicated test cases for every bug fix and feature
type: feedback
---

Pre-release test plans MUST start with a Release Change Inventory (bug fixes + features table derived from git log) and every entry must map to at least one specific test case. Generic regression tests are NOT sufficient.

**Why:** A test plan had zero test cases for the actual bugs fixed or features added — only generic "page loads" and "health check" tests. Specific changes need specific verification.

**How to apply:** When generating any test plan (pre-release, staging verification, QA):
1. FIRST: build inventory from `git log <last-tag>..HEAD` + issue tracker
2. THEN: create specific test cases for each inventory item (e.g., "verify unique coupon created per user" not just "payments work")
3. LAST: add generic regression tests on top
