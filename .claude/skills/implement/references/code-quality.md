# Code Quality Reference

## Limits

| Metric | Limit |
|--------|-------|
| Lines per file | 300 max |
| Lines per function | 30 max |
| Methods per class | 15 max (GOD-class threshold) |
| Parameters per function | 5 max |
| Nesting depth | 3 max |

## SOLID Principles

### Single Responsibility
One class = one reason to change. If describing a class requires "and", split it.

### Open/Closed
Open for extension, closed for modification. Use interfaces/protocols.

### Liskov Substitution
Subtypes must be substitutable for base types without breaking behavior.

### Interface Segregation
Many specific interfaces > one general interface. Clients shouldn't depend on unused methods.

### Dependency Inversion
Depend on abstractions, not concretions. Inject dependencies.

## DRY (Don't Repeat Yourself)

**Rule of Three:** Duplicate once = OK. Duplicate twice = extract.

```python
# BAD: Repeated validation
def create_user(email): validate_email(email); ...
def update_user(email): validate_email(email); ...
def invite_user(email): validate_email(email); ...

# GOOD: Decorator or base class
@validate_input(email=validate_email)
def create_user(email): ...
```

## Related Code Analysis (MANDATORY)

Before implementing ANY change, trace:

1. **Callers** - Who calls this code?
2. **Callees** - What does this code call?
3. **Siblings** - Similar patterns in same module?
4. **Shared state** - Global/class state accessed?
5. **Parallel implementations** - Same bug elsewhere?

```bash
# Find callers
grep -rn "function_name(" --include="*.py" .

# Find similar patterns
grep -rn "pattern_to_find" --include="*.py" .
```

## Type Hints

```python
def process_user(
    user_id: str,
    options: dict[str, Any] | None = None
) -> UserResponse:
    """Process user with given options."""
```

## Error Handling

```python
# Specific exceptions
class UserNotFoundError(Exception): pass
class ValidationError(Exception): pass

# Handle at boundaries
try:
    result = service.process(data)
except ValidationError as e:
    return {"error": str(e)}, 400
except UserNotFoundError:
    return {"error": "User not found"}, 404
```

## Docstrings

```python
def calculate_price(
    items: list[Item],
    discount: float = 0.0
) -> Decimal:
    """
    Calculate total price with optional discount.

    Args:
        items: List of items to price
        discount: Discount percentage (0.0-1.0)

    Returns:
        Total price after discount

    Raises:
        ValueError: If discount is outside valid range
    """
```

## Anti-Patterns to Avoid

| Anti-Pattern | Fix |
|--------------|-----|
| GOD-class | Split by responsibility |
| Long method | Extract helper functions |
| Deep nesting | Early returns, guard clauses |
| Magic numbers | Named constants |
| Boolean parameters | Separate methods or enums |
| Comments explaining "what" | Self-documenting names |

## Refactoring Triggers

Refactor when:
- [ ] Class > 300 lines
- [ ] Function > 30 lines
- [ ] Same code appears 3+ times
- [ ] Function has 6+ parameters
- [ ] Nesting > 3 levels
- [ ] Class name includes "And" or "Manager"
