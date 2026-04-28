---
name: Visual anomalies are release blockers
description: QA agents must detect and report visual anomalies (contradictory state, layout issues, wrong CTAs) as release blockers
type: feedback
---

Visual bugs are release blockers — not lesser than functional bugs.

**Why:** A pre-release passed QA with "guest mode" shown for logged-in users, broken nav layout, wrong CTA text, and funnel header clutter. The QA agent only checked "is the element present?" rather than "does this look correct?" The adversarial reviewer checked "does screenshot match report?" rather than "does screenshot show a problem?"

**How to apply:**
- Pre-release QA must include VISUAL ANOMALY DETECTION — scanning for contradictory state, layout issues, contrast problems, wrong CTAs, ghost elements, and stale components
- QA reviewer must check "State Coherence" — contradictory banners, stale verification, wrong CTAs, overlapping UI
- Release gate must classify visual anomalies as release blockers
- A page can functionally PASS but still have visual FINDINGS that block release
