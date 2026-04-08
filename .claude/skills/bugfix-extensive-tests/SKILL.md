---
name: bugfix-extensive-tests
description: Comprehensive test suite generation for resolved bugs to prevent recurrence. Creates minimum 15 tests with BVA methodology.
---

# Bug Prevention Test Suite (Phase 5.5)

## RALPH MODE - Phase 5.5 of 6

```
┌────────────────────────────────────────────────────────────────────┐
│ Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → [PHASE 5.5] →   │
│ Analysis  Hypotheses  Testing   Fix       Verify   >>EXTENSIVE<<   │
│                                                                    │
│ → Phase 6 → DONE                                                   │
│   Finalize                                                         │
└────────────────────────────────────────────────────────────────────┘
```

> [!CAUTION]
> **YOU ARE AT PHASE 5.5.** After completing this phase, you MUST continue to Phase 6.
> **Create minimum 15 tests** to ensure this bug never recurs.

---

## Dual-Track Note (Phase 5.5)

> **This skill is Track A (BVA tests).** For business-flow bugs (business-critical), Phase 5.5 runs two tracks in parallel:
> - **Track A (this skill):** BVA boundary-value tests — 15+ tests
> - **Track B (replay tests):** Business-flow replay tests from sanitized case packs — handled by main `/bugfix` skill Phase 5.5B
>
> Both tracks are independent and run simultaneously. This skill does NOT need to produce replay tests — the `/bugfix` skill Phase 5.5B handles that.

---

## Overview

This workflow creates a comprehensive test suite that:

1. Captures the exact bug condition
2. Tests all boundary values around the bug
3. Covers related code paths that could have similar issues
4. Prevents regression through extensive coverage

---

## Step 0: Context Discovery for Test Coverage

> [!NOTE]
> Before creating tests, review context to ensure comprehensive coverage.

### 0.1 Check Previous Conversations

Review conversation summaries for:

- Similar bugs that were fixed before (→ add regression tests)
- Related implementations that may share the same pattern
- Test plans or matrices created for similar issues

### 0.2 Check KI Troubleshooting Artifacts

Review KI summaries for:

- Documented root causes and fixes (apply patterns)
- Known gotchas that should be tested
- Related code paths mentioned in troubleshooting

### 0.3 Check GitHub Issues

```bash
gh issue list --state all --search "<bug_keywords>" --limit 20
```

Look for: related bugs, duplicates, regression patterns.

---

## Step 1: Analyze Bug for Test Generation

### 1.1 Extract Test Parameters

From the confirmed root cause, identify:

| Parameter | Question | Example |
|-----------|----------|---------|
| **Input** | What input triggered the bug? | `session_id = ""` |
| **State** | What system state was required? | `user.is_authenticated = False` |
| **Timing** | Was timing/order relevant? | `called before init` |
| **Boundaries** | What are the limits? | `0 < amount <= 999999` |

### 1.2 Map Code Paths

Identify ALL code paths that:

- Use the same function/method
- Handle similar input types
- Have similar validation logic
- Could fail in the same way

---

## Step 2: Generate Test Matrix

### 2.1 Bug-Specific Test Categories

| Category | Description | Min Tests |
|----------|-------------|-----------|
| **Root Cause** | Exact condition that triggered bug | 1 |
| **Boundary MIN** | Minimum valid value | 1 |
| **Boundary MIN-1** | Just below minimum (invalid) | 1 |
| **Boundary MIN+1** | Just above minimum | 1 |
| **Boundary MAX** | Maximum valid value | 1 |
| **Boundary MAX-1** | Just below maximum | 1 |
| **Boundary MAX+1** | Just above maximum (invalid) | 1 |
| **Null/None** | Null input handling | 1 |
| **Empty** | Empty string/list/dict | 1 |
| **Unicode** | Special characters | 1 |
| **State Variant A** | Different system state | 1 |
| **State Variant B** | Another system state | 1 |
| **Concurrent** | Race condition test | 1 |
| **Related Path 1** | Similar code path | 1 |
| **Related Path 2** | Another similar path | 1 |

**TOTAL MINIMUM: 15 tests**

### 2.2 Test Matrix Template

```markdown
## Bug #XXX Test Matrix

| ID | Category | Input | State | Expected | Priority |
|----|----------|-------|-------|----------|----------|
| BUG-XXX-001 | Root Cause | [exact input] | [exact state] | [error/success] | P0 |
| BUG-XXX-002 | Boundary MIN | [min value] | normal | success | P1 |
| BUG-XXX-003 | Boundary MIN-1 | [min-1] | normal | error | P1 |
| ... | ... | ... | ... | ... | ... |
```

---

## Step 3: Implement Tests

### 3.1 Test File Structure

```
tests/
├── unit/
│   └── test_<component>_bug_xxx.py      # Unit tests for bug
├── integration/
│   └── test_<feature>_bug_xxx.py        # Integration tests
└── e2e_fast/
    └── test_<flow>_bug_xxx.py           # E2E regression tests
```

### 3.2 Test Class Template

```python
"""
Tests to prevent Bug #XXX recurrence.

Root Cause: [one-line description]
Fixed In: [commit/PR reference]
"""
import pytest

class TestBugXXXPrevention:
    """Comprehensive tests for Bug #XXX prevention."""

    # ========== ROOT CAUSE TEST ==========
    def test_exact_bug_condition_returns_error(self):
        """BUG-XXX-001: Exact condition that triggered the bug."""
        # Arrange: [setup exact bug condition]
        # Act: [trigger the operation]
        # Assert: [verify correct behavior now]

    # ========== BOUNDARY VALUE TESTS ==========
    @pytest.mark.parametrize("value,should_succeed", [
        (MIN_VALUE, True),       # BUG-XXX-002: MIN boundary
        (MIN_VALUE - 1, False),  # BUG-XXX-003: Below MIN
        (MIN_VALUE + 1, True),   # BUG-XXX-004: Just above MIN
        (MAX_VALUE - 1, True),   # BUG-XXX-005: Just below MAX
        (MAX_VALUE, True),       # BUG-XXX-006: MAX boundary
        (MAX_VALUE + 1, False),  # BUG-XXX-007: Above MAX
    ])
    def test_boundary_values(self, value, should_succeed):
        """Boundary value tests for bug-related parameter."""
        if should_succeed:
            result = function_under_test(value)
            assert result is not None
        else:
            with pytest.raises(ValidationError):
                function_under_test(value)

    # ========== EDGE CASE TESTS ==========
    def test_null_input_handled(self):
        """BUG-XXX-008: Null/None input should raise ValidationError."""
        with pytest.raises(ValidationError):
            function_under_test(None)

    def test_empty_input_handled(self):
        """BUG-XXX-009: Empty input should raise ValidationError."""
        with pytest.raises(ValidationError):
            function_under_test("")

    def test_unicode_input_handled(self):
        """BUG-XXX-010: Unicode input should be processed correctly."""
        result = function_under_test("test data")
        assert result is not None

    # ========== STATE VARIANT TESTS ==========
    def test_when_user_authenticated(self):
        """BUG-XXX-011: Behavior when user is authenticated."""
        # Test with authenticated state

    def test_when_user_guest(self):
        """BUG-XXX-012: Behavior when user is guest."""
        # Test with guest state

    # ========== CONCURRENCY TESTS ==========
    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """BUG-XXX-013: No race condition under concurrent access."""
        import asyncio
        tasks = [function_under_test(value) for _ in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(r is not None for r in results)

    # ========== RELATED PATH TESTS ==========
    def test_similar_function_a(self):
        """BUG-XXX-014: Similar code path A handles same condition."""
        # Test related function with similar logic

    def test_similar_function_b(self):
        """BUG-XXX-015: Similar code path B handles same condition."""
        # Test another related function
```

### 3.3 Naming Convention

- File: `test_<component>_bug_<issue_number>.py`
- Class: `TestBug<IssueNumber>Prevention`
- Method: `test_<category>_<description>`
- Docstring: Include test ID `BUG-XXX-NNN` for traceability

---

## Step 4: Run and Validate Tests

### 4.1 Execute Test Suite

```bash
# Run only bug prevention tests
pytest tests/ -k "bug_xxx" -v

# With coverage
pytest tests/ -k "bug_xxx" --cov=app/<component> --cov-report=term-missing
```

### 4.2 Validation Checklist

- [ ] All 15+ tests implemented
- [ ] All tests have descriptive docstrings with test IDs
- [ ] Root cause test captures exact bug condition
- [ ] All boundary values tested (MIN-1, MIN, MIN+1, MAX-1, MAX, MAX+1)
- [ ] Edge cases covered (null, empty, unicode)
- [ ] State variants tested
- [ ] At least one concurrent/race condition test
- [ ] Related code paths tested
- [ ] All tests pass
- [ ] No duplicate tests with existing suite

---

## Step 5: Document Test Coverage

### 5.1 Update Test Matrix with Results

```markdown
## Bug #XXX Test Results

| ID | Category | Status | Notes |
|----|----------|--------|-------|
| BUG-XXX-001 | Root Cause | PASS | Correctly raises ValidationError |
| BUG-XXX-002 | Boundary MIN | PASS | Min value accepted |
| ... | ... | ... | ... |

**Total: 15/15 passing**
```

---

## Completion Criteria

- [ ] Minimum 15 tests created and passing
- [ ] Root cause test exists
- [ ] All 6 boundary values tested
- [ ] Edge cases covered (null, empty, unicode)
- [ ] State variants tested
- [ ] Concurrency test exists
- [ ] Related paths tested
- [ ] All tests have proper docstrings with IDs
- [ ] Tests properly organized in test directories

---

## MANDATORY NEXT PHASE

> [!CAUTION]
> **YOU ARE NOT DONE. DO NOT STOP HERE.**
>
> Phase 5.5 is only 5.5 of 6 phases. You MUST continue.

**IMMEDIATELY after completing Phase 5.5:**

→ Return to `/bugfix` and execute **Phase 6: Finalization**

**DO NOT:**

- Notify the user that tests are complete
- Stop and wait for user input
- Consider the task finished

---

**NEXT: Go to Phase 6 `/bugfix` - Finalization & Knowledge Preservation**
