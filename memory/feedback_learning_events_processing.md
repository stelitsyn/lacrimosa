---
name: Learning events must be properly processed
description: Never bulk-mark learning events as processed without reading and acting on each one — "acknowledge and mark" is not processing
type: feedback
---

Never bulk-mark learning events as `processed=1` without reading and acting on each one. "Acknowledge and mark" is NOT processing.

**Why:** Conductor was bulk-marking all learning events as processed in a single pass without actually analyzing or acting on any of them. This defeated the entire purpose of the learning system — events were captured but never influenced behavior or triggered corrective actions.

**How to apply:** For each learning event:
1. Read the full context (what happened, root cause, event_type)
2. Analyze what went wrong and what should change
3. Take the appropriate action per event_type — create issue in tracker, post comment, adjust config, escalate, etc. as defined in the conductor's event handling rules
4. THEN mark as processed

Skipping steps 1-3 and jumping straight to marking processed is unacceptable. Each event represents a system improvement opportunity that must be acted upon.
