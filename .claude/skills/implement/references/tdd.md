# TDD Reference

## Core Principle

**Tests FIRST, implementation SECOND.** No exceptions.

## Test Categories

| Category | Count | Purpose |
|----------|-------|---------|
| Happy path | 5-10 | Normal operation |
| Edge cases | 5-10 | Boundaries, limits |
| Error cases | 5-10 | Invalid inputs, failures |
| Integration | 3-5 | Component interactions |

**Target: 25+ tests per feature.**

## Test Naming

```python
def test_<action>_<scenario>_<expected_result>():
    """
    Given: <preconditions>
    When: <action>
    Then: <expected outcome>
    """
```

Examples:
```python
def test_create_user_with_valid_email_returns_user_id():
def test_create_user_with_duplicate_email_raises_conflict():
def test_create_user_with_empty_name_raises_validation_error():
```

## Red-Green-Refactor

1. **RED**: Write failing test
2. **GREEN**: Minimal code to pass
3. **REFACTOR**: Clean up, maintain passing

## Verification Before Implementation

```bash
pytest tests/path.py -v --tb=short
```

**Tests MUST fail** before implementation. Verify failures are for expected reasons (missing functionality), not:
- Import errors
- Syntax errors
- Missing fixtures

## Test Structure (AAA Pattern)

```python
def test_example():
    # Arrange - set up preconditions
    user = create_test_user()

    # Act - perform the action
    result = service.process(user)

    # Assert - verify outcome
    assert result.status == "success"
```

## Fixtures

```python
@pytest.fixture
def test_user():
    return User(id="test-123", email="test@example.com")

@pytest.fixture
def mock_database(mocker):
    return mocker.patch("app.db.session")
```

## Parameterized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("valid@email.com", True),
    ("invalid", False),
    ("", False),
    ("@nodomain", False),
])
def test_email_validation(input, expected):
    assert validate_email(input) == expected
```

## Markers

```python
@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.regression
@pytest.mark.slow
```

## Common Gotchas

| Issue | Solution |
|-------|----------|
| Tests pass in isolation, fail together | Check fixture isolation, shared state |
| Flaky tests | Remove timing dependencies, use mocks |
| Import errors in tests | Verify mock patch paths match imports |
| Tests too slow | Use mocks, avoid real I/O |
