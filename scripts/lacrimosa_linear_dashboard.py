"""Lacrimosa Linear Dashboard — Team visibility via Linear documents + pulse reports.

Renders state.json data into Linear-compatible markdown for:
1. Pinned living document (updated every conductor cycle)
2. Daily project pulse (status update with health indicator)
3. Weekly initiative pulse (strategic summary)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from scripts import lacrimosa_config

logger = logging.getLogger(__name__)

_ISSUE_PREFIX = lacrimosa_config.get("linear.issue_prefix", "")
STATE_FILE = Path.home() / ".claude" / "lacrimosa" / "state.json"


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _time_ago(iso_ts: str | None) -> str:
    if not iso_ts:
        return "never"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        delta = datetime.now(tz=timezone.utc) - dt
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except (ValueError, TypeError):
        return "unknown"


def _count_by_verification(issues: dict) -> tuple[int, int, int]:
    """Returns (verified, unverified, in_progress)."""
    verified = unverified = in_progress = 0
    for issue in issues.values():
        if not isinstance(issue, dict):
            continue
        v = issue.get("verification", {})
        status = v.get("status") if isinstance(v, dict) else None
        if status == "verified":
            verified += 1
        elif status == "unverified":
            unverified += 1
        elif status == "in_progress":
            in_progress += 1
    return verified, unverified, in_progress


def _calculate_health(state: dict) -> str:
    """Calculate health from state: onTrack, atRisk, offTrack."""
    wd = state.get("watchdog", {})
    if wd.get("circuit_breaker_tripped"):
        return "offTrack"

    _, uv, _ = _count_by_verification(state.get("issues", {}))
    if uv > 5:
        return "atRisk"

    # Check for stalled workers
    active = state.get("pipeline", {}).get("active_workers", {})
    if len(active) > 0:
        # Could check output file freshness but we don't have filesystem access
        # in the MCP context — rely on state tracking
        pass

    system_state = state.get("system_state", "")
    if system_state == "Stopped":
        return "atRisk"

    return "onTrack"


# ---------------------------------------------------------------------------
# Layer 1: Pinned Living Document
# ---------------------------------------------------------------------------


def render_live_dashboard(state: dict | None = None) -> str:
    """Render current state as markdown for the pinned Linear document."""
    if state is None:
        state = _read_state()

    now = datetime.now(tz=timezone.utc)
    today = now.strftime("%Y-%m-%d")
    tc = state.get("daily_counters", {}).get(today, {})
    issues = state.get("issues", {})
    active = state.get("pipeline", {}).get("active_workers", {}) or {}
    if not isinstance(active, dict):
        active = {}
    discovery = state.get("discovery", {})
    trust_scores = state.get("trust_scores", {})
    verified, unverified, in_progress = _count_by_verification(issues)
    completed = sum(1 for i in issues.values() if isinstance(i, dict) and i.get("state") == "Completed")

    # Trust summary
    trust_rows = ""
    for proj, ts in trust_scores.items():
        trust_rows += f"| {proj} | Tier {ts.get('tier', 0)} | {ts.get('successful_merges', 0)} | {ts.get('last_revert', 'never')} |\n"

    # Active workers
    worker_rows = ""
    if active:
        for name, w in active.items():
            if not isinstance(w, dict):
                continue
            wissue = w.get('issue', '?')
            w_link = f"[{wissue}](https://linear.app/{lacrimosa_config.get('linear.workspace_slug')}/issue/{wissue})" if str(wissue).startswith(f"{_ISSUE_PREFIX}-") else wissue
            worker_rows += f"| {w_link} | {w.get('phase', '?')} | {name} |\n"
    if not worker_rows:
        worker_rows = "| — | No active workers | — |\n"

    # Recent completions (today)
    today_completed = [
        (iid, i) for iid, i in issues.items()
        if isinstance(i, dict) and i.get("state") == "Completed"
        and (i.get("completed_at") or "").startswith(today)
    ]
    today_completed.sort(key=lambda x: x[1].get("completed_at", ""), reverse=True)
    completion_rows = ""
    for iid, issue in today_completed[:10]:
        pr = issue.get("pr_number", "")
        v_status = issue.get("verification", {}).get("status", "?") if isinstance(issue.get("verification"), dict) else "?"
        completed_at = (issue.get("completed_at") or "")[:16]
        kal_link = f"[{iid}](https://linear.app/{lacrimosa_config.get('linear.workspace_slug')}/issue/{iid})" if iid.startswith(f"{_ISSUE_PREFIX}-") else iid
        _repo_url = lacrimosa_config.get("github.repo_url", "")
        pr_link = f"[#{pr}]({_repo_url}/pull/{pr})" if pr and _repo_url else (f"#{pr}" if pr else "—")
        completion_rows += f"| {kal_link} | {pr_link} | {completed_at} | {v_status} |\n"
    if not completion_rows:
        completion_rows = "| — | No completions today | — | — |\n"

    return f"""# Lacrimosa Conductor — Live Dashboard
*Auto-updated by Lacrimosa engine. Last refresh: {now.strftime('%Y-%m-%d %H:%M UTC')}*

## Engine Status
| Metric | Value |
|--------|-------|
| State | {state.get('system_state', '?')} |
| Active Workers | {len(active)} |
| Today PRs Merged | {tc.get('prs_merged', 0)} |
| Today Workers Spawned | {tc.get('workers_spawned', 0)} |
| Total Completed | {completed} |

## Trust
| Domain | Tier | Merges | Last Revert |
|--------|------|--------|-------------|
{trust_rows}
## Current Work-in-Progress
| Issue | Phase | Worker |
|-------|-------|--------|
{worker_rows}
## Verification Status
| Verified | Unverified | In Progress |
|----------|------------|-------------|
| {verified} | {unverified} | {in_progress} |

## Discovery (last 24h)
- Internal sensors: {_time_ago(discovery.get('last_internal_sense'))}
- External sensors: {_time_ago(discovery.get('last_external_sense'))}
- Strategy analysis: {_time_ago(discovery.get('last_strategy_analysis'))}
- Signals validated today: {discovery.get('signals_validated_today', 0)}

## Recent Completions (today)
| Issue | PR | Completed | Verified |
|-------|----|-----------|----------|
{completion_rows}
"""


# ---------------------------------------------------------------------------
# Layer 2: Daily Project Pulse
# ---------------------------------------------------------------------------


def render_daily_pulse(state: dict | None = None) -> tuple[str, str]:
    """Render daily pulse markdown + health for project status update.

    Returns (body_markdown, health).
    """
    if state is None:
        state = _read_state()

    now = datetime.now(tz=timezone.utc)
    today = now.strftime("%Y-%m-%d")
    tc = state.get("daily_counters", {}).get(today, {})
    issues = state.get("issues", {})
    trust_scores = state.get("trust_scores", {})
    discovery = state.get("discovery", {})
    verified, unverified, _ = _count_by_verification(issues)
    total_issues = len(issues)
    health = _calculate_health(state)

    # Today's completed issues
    today_completed = [
        (iid, i) for iid, i in issues.items()
        if isinstance(i, dict) and i.get("state") == "Completed"
        and (i.get("completed_at") or "").startswith(today)
    ]
    completed_rows = ""
    for iid, issue in sorted(today_completed, key=lambda x: x[1].get("completed_at", "")):
        pr = issue.get("pr_number", "")
        v = issue.get("verification", {})
        v_status = v.get("status", "?") if isinstance(v, dict) else "?"
        kal_link = f"[{iid}](https://linear.app/{lacrimosa_config.get('linear.workspace_slug')}/issue/{iid})" if iid.startswith(f"{_ISSUE_PREFIX}-") else iid
        _repo_url = lacrimosa_config.get("github.repo_url", "")
        pr_link = f"[#{pr}]({_repo_url}/pull/{pr})" if pr and _repo_url else (f"#{pr}" if pr else "")
        completed_rows += f"- **{kal_link}** {pr_link} — {v_status}\n"
    if not completed_rows:
        completed_rows = "- No completions today\n"

    # Trust rows
    trust_rows = ""
    for proj, ts in trust_scores.items():
        trust_rows += f"| {proj} | {ts.get('tier', 0)} | {ts.get('successful_merges', 0)} | {ts.get('last_revert', 'never')} |\n"

    # Learnings
    learnings_path = Path.home() / ".claude" / "lacrimosa" / "learnings.json"
    today_learnings = []
    try:
        all_learnings = json.loads(learnings_path.read_text())
        today_learnings = [
            l for l in all_learnings
            if (l.get("timestamp") or "").startswith(today)
        ]
    except (json.JSONDecodeError, OSError):
        pass

    learning_rows = ""
    for l in today_learnings[:5]:
        learning_rows += f"- {l.get('pattern', '?')[:80]}\n"
    if not learning_rows:
        learning_rows = "- No new learnings today\n"

    body = f"""## Lacrimosa Daily Pulse — {today}

**Engine output:** {tc.get('prs_merged', 0)} PRs merged, {tc.get('workers_spawned', 0)} workers spawned

### Pipeline
| Metric | Value |
|--------|-------|
| Issues completed today | {len(today_completed)} |
| PRs merged | {tc.get('prs_merged', 0)} |
| Verification | {verified}/{total_issues} ({int(verified / max(total_issues, 1) * 100)}%) |

### Discovery
- Signals processed: {tc.get('signals_processed', 0)}
- Signals validated: {tc.get('signals_validated', 0)}
- Issues from discovery: {tc.get('issues_discovered', 0)}

### Trust
| Domain | Tier | Merges | Last Revert |
|--------|------|--------|-------------|
{trust_rows}
### Issues Completed Today
{completed_rows}
### Learnings
{learning_rows}"""

    return body, health


# ---------------------------------------------------------------------------
# Layer 3: Weekly Initiative Pulse
# ---------------------------------------------------------------------------


def render_weekly_pulse(state: dict | None = None) -> tuple[str, str]:
    """Render weekly strategic pulse for initiative status update.

    Returns (body_markdown, health).
    """
    if state is None:
        state = _read_state()

    now = datetime.now(tz=timezone.utc)
    today = now.strftime("%Y-%m-%d")
    issues = state.get("issues", {})
    trust_scores = state.get("trust_scores", {})
    discovery = state.get("discovery", {})
    verified, unverified, _ = _count_by_verification(issues)
    total_issues = len(issues)
    health = _calculate_health(state)

    # Aggregate weekly stats from daily_counters
    counters = state.get("daily_counters", {})
    week_prs = sum(c.get("prs_merged", 0) for c in counters.values())
    week_workers = sum(c.get("workers_spawned", 0) for c in counters.values())
    week_signals = sum(c.get("signals_processed", 0) for c in counters.values())
    completed = sum(1 for i in issues.values() if isinstance(i, dict) and i.get("state") == "Completed")

    # Trust evolution
    trust_rows = ""
    for proj, ts in trust_scores.items():
        trust_rows += f"| {proj} | Tier {ts.get('tier', 0)} | {ts.get('successful_merges', 0)} |\n"

    body = f"""## Lacrimosa Weekly Report — Week of {today}

### Velocity
- **Total PRs merged:** {week_prs}
- **Total workers spawned:** {week_workers}
- **Issues completed:** {completed}

### Quality
- Verification coverage: {verified}/{total_issues} ({int(verified / max(total_issues, 1) * 100)}%)

### Discovery Intelligence
- Signals processed: {week_signals}
- Strategy analysis: {_time_ago(discovery.get('last_strategy_analysis'))}
- Deep research: {_time_ago(discovery.get('last_deep_research'))}

### Trust Evolution
| Domain | Tier | Merges |
|--------|------|--------|
{trust_rows}
### Vision Gaps
{chr(10).join('- ' + g for g in state.get('vision_cache', {}).get('identified_gaps', [])[:5]) or '- None identified'}
"""

    return body, health


# ---------------------------------------------------------------------------
# Orchestrator — called by conductor each cycle
# ---------------------------------------------------------------------------


def update_linear_dashboard(state: dict | None = None) -> None:
    """Update Linear dashboard document + post pulse if due.

    Called by the conductor each cycle. Uses MCP tools via conductor context.
    This function is meant to be called from within a Claude Code session
    that has access to Linear MCP tools.

    For standalone usage, call render_* functions and post manually.
    """
    if state is None:
        state = _read_state()

    dashboard = state.get("linear_dashboard", {})
    doc_id = dashboard.get("document_id")

    # Render current dashboard
    dashboard_md = render_live_dashboard(state)

    # Log what would be posted (actual MCP calls happen in conductor context)
    logger.info(
        "Linear dashboard update: doc_id=%s, content_length=%d",
        doc_id,
        len(dashboard_md),
    )

    # Check if daily pulse is due
    now = datetime.now(tz=timezone.utc)
    last_daily = dashboard.get("last_daily_pulse")
    if last_daily:
        try:
            last_dt = datetime.fromisoformat(last_daily.replace("Z", "+00:00"))
            hours_since = (now - last_dt).total_seconds() / 3600
            daily_due = hours_since >= 20
        except (ValueError, TypeError):
            daily_due = True
    else:
        daily_due = True

    if daily_due:
        pulse_md, health = render_daily_pulse(state)
        logger.info("Daily pulse due: health=%s, content_length=%d", health, len(pulse_md))

    # Check if weekly pulse is due (Friday)
    last_weekly = dashboard.get("last_weekly_pulse")
    is_friday = now.weekday() == 4
    weekly_due = False
    if is_friday:
        if last_weekly:
            try:
                last_dt = datetime.fromisoformat(last_weekly.replace("Z", "+00:00"))
                days_since = (now - last_dt).total_seconds() / 86400
                weekly_due = days_since >= 5
            except (ValueError, TypeError):
                weekly_due = True
        else:
            weekly_due = True

    if weekly_due:
        weekly_md, health = render_weekly_pulse(state)
        logger.info("Weekly pulse due: health=%s, content_length=%d", health, len(weekly_md))

    return {
        "dashboard_md": dashboard_md,
        "doc_id": doc_id,
        "daily_due": daily_due,
        "daily_pulse": render_daily_pulse(state) if daily_due else None,
        "weekly_due": weekly_due,
        "weekly_pulse": render_weekly_pulse(state) if weekly_due else None,
    }


def render_pipeline_dashboard() -> str:
    """Render pipeline-aware dashboard from issue_pipeline table."""
    from scripts.lacrimosa_pipeline import PipelineManager
    from scripts.lacrimosa_state_sqlite import StateManager

    pm = PipelineManager()
    sm = StateManager()

    now = datetime.now(tz=timezone.utc)
    lines = [f"## Lacrimosa Pipeline — {now.strftime('%Y-%m-%d %H:%M UTC')}", ""]

    # Active pipeline
    active = pm.query(states=[
        "Backlog", "Triaged", "Implementing", "ReviewPending",
        "Reviewing", "FixNeeded", "MergeReady", "Merging", "Verifying",
    ])
    lines.append("### Active Pipeline")
    if active:
        lines.append("| Issue | State | Owner | PR | Age | Sentinel? |")
        lines.append("|-------|-------|-------|----|-----|-----------|")
        for row in active:
            age = _time_ago(row["created_at"])
            pr = f"#{row['pr_number']}" if row.get("pr_number") else "—"
            sentinel = "YES" if row.get("sentinel_origin") else ""
            lines.append(
                f"| {row['identifier']} | {row['state']} | "
                f"{row.get('owner') or '—'} | {pr} | {age} | {sentinel} |"
            )
    else:
        lines.append("*No active issues in pipeline.*")

    lines.append("")

    # Specialist health
    health = sm.get_specialist_health()
    lines.append("### Specialist Health")
    lines.append("| Specialist | Last Heartbeat | Status | Errors 24h |")
    lines.append("|-----------|---------------|--------|------------|")
    for name, h in sorted(health.items()):
        hb = _time_ago(h.get("last_heartbeat"))
        status = "healthy" if h.get("consecutive_errors", 0) == 0 else "ERROR"
        errors = h.get("consecutive_errors", 0)
        lines.append(f"| {name} | {hb} | {status} | {errors} |")

    lines.append("")

    # Throttle
    throttle = sm.read("rate_limits.throttle_level") or "unknown"
    five_h = sm.read("rate_limits.five_hour_pct") or 0
    seven_d = sm.read("rate_limits.seven_day_pct") or 0
    lines.append("### Throttle")
    lines.append(f"- Normal: {throttle.upper()} (5h: {five_h}%, 7d: {seven_d}%)")
    sentinel_status = "ACTIVE" if seven_d < 95 else "BLOCKED (95% weekly)"
    lines.append(f"- Sentinel pipeline: {sentinel_status}")

    lines.append("")

    # Recent completions (24h)
    from datetime import timedelta
    since = (now - timedelta(hours=24)).isoformat()
    completed = pm.completed_since(since)
    lines.append("### Recent Completions (24h)")
    if completed:
        lines.append("| Issue | PR | Duration | Sentinel? |")
        lines.append("|-------|----|----------|-----------|")
        for row in completed:
            pr = f"#{row['pr_number']}" if row.get("pr_number") else "—"
            sentinel = "YES" if row.get("sentinel_origin") else ""
            try:
                created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                done = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
                dur = done - created
                dur_str = f"{int(dur.total_seconds() // 3600)}h {int((dur.total_seconds() % 3600) // 60)}m"
            except (ValueError, TypeError):
                dur_str = "—"
            lines.append(f"| {row['identifier']} | {pr} | {dur_str} | {sentinel} |")
    else:
        lines.append("*No completions in last 24h.*")

    return "\n".join(lines)


if __name__ == "__main__":
    # CLI: preview what would be posted
    state = _read_state()
    print("=== LIVE DASHBOARD ===")
    print(render_live_dashboard(state))
    print("\n=== DAILY PULSE ===")
    body, health = render_daily_pulse(state)
    print(f"Health: {health}")
    print(body)
    print("\n=== WEEKLY PULSE ===")
    body, health = render_weekly_pulse(state)
    print(f"Health: {health}")
    print(body)
