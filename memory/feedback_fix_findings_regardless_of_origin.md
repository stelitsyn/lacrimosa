# Fix Findings Regardless of Origin

When a task surfaces a quality, security, test, dependency, documentation, or verification finding, do not dismiss it because it is unrelated to the current diff, pre-existing, long-standing, or outside the original scope.

Every finding needs one explicit outcome:

- `FIXED NOW`: preferred when the fix is mechanical, local, low-risk, covered by existing tests, or adjacent to the current change.
- `TRACKED`: acceptable only when the fix is genuinely broad, destructive, product-decision-dependent, cross-service, or otherwise unsafe to bundle. Include owner, acceptance criteria, and deadline.
- `ESCALATED`: use when a human decision is required before action.

Stop-hook and PreToolUse-hook guardrails enforce this rule by detecting phrases such as "pre-existing", "unrelated to this change", "out of scope", "follow-up ticket", and "leaving as-is" when no mitigation marker is present.

The point is not to expand every task endlessly. The point is to prevent easy fixes from becoming permanent background debt.
