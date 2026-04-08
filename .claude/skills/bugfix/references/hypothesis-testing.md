# Hypothesis Testing Reference

## Hypothesis Structure

Each hypothesis must include:

```markdown
### Hypothesis N: [Title]

**Theory:** What I believe is happening
**Evidence:** Observations supporting this theory
**Counter-evidence:** What would disprove this
**Test:** How to verify/refute
```

## Example Hypotheses

```markdown
### Hypothesis 1: Race condition in session refresh

**Theory:** Two concurrent requests trigger parallel token refresh, causing one to use stale token
**Evidence:** Bug occurs under load, logs show overlapping refresh calls
**Counter-evidence:** Would fail consistently if synchronization issue
**Test:** Add mutex lock around refresh, check if bug persists

### Hypothesis 2: Cache invalidation timing

**Theory:** Cache TTL expires between validation and usage
**Evidence:** Works on first request, fails on subsequent
**Counter-evidence:** Would fail randomly, not consistently after N minutes
**Test:** Extend TTL to 1 hour, monitor for 2 hours

### Hypothesis 3: Null pointer in error path

**Theory:** Error handler assumes non-null response that's null on timeout
**Evidence:** Stack trace shows NullReferenceException in error handler
**Counter-evidence:** Would fail on all errors, not just timeouts
**Test:** Add null check, trigger timeout deliberately
```

## The 5 W's

Every hypothesis must answer:

| Question | Purpose |
|----------|---------|
| **What** fails | Specific symptom/error |
| **Where** in code | File, function, line |
| **When** (conditions) | Trigger conditions, timing |
| **Why** (root cause) | Underlying mechanism |
| **How** to verify | Concrete test to confirm/refute |

## Testing Protocol

1. **Isolate** - Test one hypothesis at a time
2. **Instrument** - Add targeted logging (see debug-harness.md)
3. **Reproduce** - Trigger the bug conditions
4. **Observe** - Collect evidence
5. **Conclude** - CONFIRMED / REFUTED / INCONCLUSIVE

## Decision Matrix

| Evidence | Counter-Evidence | Conclusion |
|----------|------------------|------------|
| Strong | Weak/None | CONFIRMED → Fix |
| Moderate | Moderate | INCONCLUSIVE → More logging |
| Weak/None | Strong | REFUTED → Next hypothesis |
| None | None | Insufficient data → Instrument more |

## Common Bug Patterns

| Pattern | Symptoms | Investigation |
|---------|----------|---------------|
| Race condition | Intermittent, load-dependent | Add mutex, check concurrency |
| Null reference | Random crashes in paths | Trace null propagation |
| Off-by-one | Edge cases fail | Check loop bounds, array indices |
| State corruption | Works then fails | Trace state mutations |
| Resource leak | Degrades over time | Monitor memory/connections |
| Encoding issue | Special chars break | Check encoding at boundaries |

## Anti-Patterns

| Don't | Do Instead |
|-------|------------|
| Jump to conclusions | Form 3+ hypotheses first |
| Fix without understanding | Confirm root cause before fixing |
| Test multiple changes at once | Isolate each hypothesis test |
| Ignore counter-evidence | Weight all evidence fairly |
| Stop at first hypothesis | Test alternatives even if first seems right |
