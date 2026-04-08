# Debug Harness Reference

## Debug Logging Pattern

Use issue-tagged debug statements for easy cleanup:

```python
# Python
import logging
logger = logging.getLogger(__name__)

# Tag with issue number for easy removal
logger.debug("DEBUG[ISSUE-123] user_id=%s, state=%s", user_id, state)
```

```typescript
// TypeScript
console.log(`DEBUG[ISSUE-123] userId=${userId}, state=${JSON.stringify(state)}`);
```

## Logging Levels

| Level | Use For |
|-------|---------|
| DEBUG | Variable values, flow tracing |
| INFO | Key milestones, state changes |
| WARNING | Unexpected but handled conditions |
| ERROR | Failures requiring attention |

## Strategic Logging Points

Add logging at:

1. **Entry points** - Function inputs
2. **Exit points** - Return values
3. **Branch decisions** - Which path taken
4. **State mutations** - Before/after values
5. **External calls** - Request/response
6. **Error handlers** - Exception details

## Example Debug Harness

```python
def process_order(order_id: str) -> OrderResult:
    logger.debug("DEBUG[ISSUE-456] process_order START order_id=%s", order_id)

    order = get_order(order_id)
    logger.debug("DEBUG[ISSUE-456] order fetched: status=%s, items=%d",
                 order.status, len(order.items))

    if order.status == "pending":
        logger.debug("DEBUG[ISSUE-456] taking pending path")
        result = handle_pending(order)
    else:
        logger.debug("DEBUG[ISSUE-456] taking active path, status=%s", order.status)
        result = handle_active(order)

    logger.debug("DEBUG[ISSUE-456] process_order END result=%s", result)
    return result
```

## Production Log Access

### Cloud Run (GCP)

```bash
# Recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name={cloud_run_service_eu}" \
  --limit=100 --format="table(timestamp,severity,textPayload)"

# Filter by severity
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" --limit=50

# Search for specific pattern
gcloud logging read 'resource.type=cloud_run_revision AND textPayload:"ISSUE-123"' --limit=100
```

### Local Development

```bash
# Follow logs in real-time
tail -f logs/app.log | grep "DEBUG\[ISSUE-"

# Search historical logs
grep -rn "DEBUG\[ISSUE-123\]" logs/
```

## Cleanup

**CRITICAL: Remove all debug code before merging.**

```bash
# Find all debug statements
grep -rn "DEBUG\[ISSUE-" --include="*.py" --include="*.ts" .

# Verify none remain
grep -c "DEBUG\[ISSUE-" --include="*.py" --include="*.ts" -r . && echo "CLEANUP NEEDED" || echo "Clean"
```

## Temporary Test Fixtures

For bugs requiring specific state:

```python
@pytest.fixture
def bug_123_state():
    """
    Reproduces state that triggers ISSUE-123.
    DELETE after bug is fixed.
    """
    # DEBUG[ISSUE-123] Temporary fixture
    return {
        "user_id": "test-user",
        "session_state": "corrupted",
        "timestamp": datetime.now() - timedelta(hours=25)
    }
```

## Checklist Before Phase 6

- [ ] All `DEBUG[ISSUE-XXX]` statements removed
- [ ] No temporary test fixtures remain
- [ ] No hardcoded test values in production code
- [ ] Log levels restored to appropriate production levels
- [ ] No commented-out debug code left behind
