# Display Templates — Status, Trust, Discover, Learnings, Dashboard, Specialist Health

## `/lacrimosa status`

Read `state.json` and display:

```markdown
## Lacrimosa Status

**State:** Running | Paused | Stopped
**Mode:** interactive | daemon
**Uptime:** HH:MM:SS

### Discovery Loop
| Sensor | Last Run | Status |
|--------|----------|--------|
| Internal Sense | {time_ago} | {ok/overdue} |
| External Sense | {time_ago} | {ok/overdue} |
| Strategy Analysis | {time_ago} | {ok/overdue} |
| Deep Research | {time_ago} | {ok/overdue} |

**Signals:** {processed} processed, {validated} validated, {archived} archived today
**Signal Queue:** {queue_count} pending design

### Engineering Loop
**Trust:** {domain}: Tier {N} ({merges} merges)

#### Active Workers ({count})
| Issue | Phase | Elapsed | Attempt |
|-------|-------|---------|---------|

#### Pending ({count})
| Issue | Priority | Domain |
|-------|----------|--------|

#### Recent Completions (24h)
| Issue | PR | Merged | Duration |
|-------|----|---------| ---------|

### Specialist Health
| Specialist | Status | Session | Last Cycle | Cycles | Errors (consecutive) |
|------------|--------|---------|------------|--------|---------------------|

Read from SQLite: `SELECT * FROM specialists` via `StateManager.get_specialist_health()`.

For each specialist:
1. Check `tmux has-session -t {session_name}` — Session: alive/dead
2. Compute heartbeat age from `last_heartbeat`
3. Status: OK (fresh heartbeat) | STALE (heartbeat > max_silence) | DEAD (tmux session gone) | ERROR (consecutive_errors >= 3) | DISABLED (restarts_24h > 3)
4. Format: `| Discovery | OK | alive | 2m ago | 47 | 0 |`

### Daily Counters
- Signals: {processed} processed, {validated} validated
- Issues dispatched: {dispatched}/{cap}
- PRs merged: {merged}
```

## `/lacrimosa trust`

```markdown
## Trust Scores

| Project | Tier | Merges | Last Revert | Concurrent | Daily Cap |
|---------|------|--------|-------------|------------|-----------|

### Tier Requirements
- Tier 0 → 1: 5 merges, no reverts in 48h
- Tier 1 → 2: 15 merges total
```

## `/lacrimosa discover`

```markdown
## Discovery Signals

### Signal Queue ({count} pending design)
| Signal | Category | Source | Score | Summary |

### Recently Validated (7 days)
| Signal | Category | Score | Action | Issue |

### Recently Archived (7 days)
| Signal | Category | Reason | Source |

### Sensor Activity
- Internal: {count} signals from {sensors} sensors
- External: {count} signals from {sources} sources
- Conversion rate: {rate}%
```

## `/lacrimosa learnings`

Read `~/.claude/lacrimosa/learnings.json`:

```markdown
## Lacrimosa Learnings

### Discovery Learnings
| Date | Signal Type | Adjustment | Reason |

### Engineering Learnings
| Date | Pattern | Improvement | Evidence |

### Calibration Stats
- Signal-to-outcome rate: {rate}%
- First-pass review rate: {rate}%
- Threshold adjustments (30 days): {count}
```

## `/lacrimosa dashboard`

```bash
.venv/bin/python scripts/lacrimosa_dashboard.py --port 1791 &
echo "Dashboard running at http://localhost:1791"
```

## `/lacrimosa stop`

1. Set `system_state = "Stopping"`
2. Wait for active workers (timeout: 30 min)
3. If timeout → terminate
4. Set `system_state = "Stopped"`, write state

## `/lacrimosa pause` / `/lacrimosa resume`

**Pause:** `system_state = "Paused"`, active workers finish, no new dispatch.
**Resume:** `system_state = "Running"`, normal dispatch resumes.

## `/lacrimosa sense`

Force immediate sense cycle (bypass cadence timers):
1. Run all internal sensors
2. Run all external sensors
3. Validate new signals
4. Report: {processed} signals, {validated} validated, {archived} archived
