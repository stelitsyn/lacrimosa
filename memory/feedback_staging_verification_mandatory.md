---
name: staging-verification-mandatory
description: Deploy to staging and verify in browser after ALL feature implementations, not just when asked
type: feedback
---

After implementing features, ALWAYS deploy to staging and verify workflows in the browser before considering the work complete.

**Why:** Staging verification should be a standard part of every feature implementation workflow, not something that requires a separate explicit request. Skipping verification means bugs reach the user's review.

**How to apply:** After completing any feature implementation (especially backend/frontend coordination changes), automatically:
1. Deploy to staging (using your project's staging deploy script)
2. Open staging in browser and test the affected workflows
3. Take screenshots of key state transitions
4. Include verification results in the completion report

This applies to all workflows — `/implement`, `/bugfix`, agent teams, and direct implementation. Treat it as a mandatory post-implementation gate, same as running tests.
