#!/usr/bin/env python3
"""Lacrimosa Dashboard — local HTTP server for real-time system visibility.

Reads ~/.claude/lacrimosa/state.json and serves an HTML dashboard showing:
- Trust scores per domain with tier visualization
- Active workers with phase, elapsed time
- Recent completions (last 24h) with merge status
- Pending issues awaiting dispatch or approval
- Vision analysis summary
- Discovery stats, sensor health, and signal queue
- Token costs, quality scores, and bug/revert tracking
- System controls (pause/resume via POST)

Usage:
    python scripts/lacrimosa_dashboard.py [--port 1791]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from scripts import lacrimosa_config

# -- Paths ------------------------------------------------------------------

LACRIMOSA_DIR = Path.home() / ".claude" / "lacrimosa"
STATE_FILE = LACRIMOSA_DIR / "state.json"
CONFIG_FILE = LACRIMOSA_DIR / "config.yaml"

# -- Trust tier config ------------------------------------------------------

TRUST_TIERS = {
    0: {"concurrent_workers": 1, "issues_per_day": 3, "max_files_per_pr": 15},
    1: {"concurrent_workers": 2, "issues_per_day": 5, "max_files_per_pr": 25},
    2: {"concurrent_workers": 3, "issues_per_day": 10, "max_files_per_pr": 40},
}


# -- State helpers (delegated to StateManager) ------------------------------

from scripts.lacrimosa_state import StateManager

_state_manager = StateManager()


def read_state() -> dict:
    return _state_manager.read()


def write_state(state: dict) -> None:
    _state_manager.atomic_update(lambda _: state)


def elapsed_str(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "--:--:--"
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        delta = datetime.now(tz=timezone.utc) - dt
        total_s = max(0, int(delta.total_seconds()))
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except (ValueError, TypeError):
        return "--:--:--"


def time_ago(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "never"
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        delta = datetime.now(tz=timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except (ValueError, TypeError):
        return "unknown"


def time_ago_ts(unix_ts: int | float | None) -> str:
    """Format a unix timestamp as 'in Xh Ym' (future) or 'Xh ago'."""
    if not unix_ts or unix_ts <= 0:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        delta = dt - datetime.now(tz=timezone.utc)
        secs = int(delta.total_seconds())
        if secs > 0:
            h, rem = divmod(secs, 3600)
            m = rem // 60
            return f"in {h}h{m}m" if h else f"in {m}m"
        secs = abs(secs)
        if secs < 3600:
            return f"{secs // 60}m ago"
        return f"{secs // 3600}h ago"
    except (ValueError, TypeError, OSError):
        return "unknown"


# -- Phase-times merging ----------------------------------------------------

# Canonical ordering of pipeline phases.  When synthesizing missing entries
# from ``phases_completed``, this list determines the display order so that
# the phase bar always reads left-to-right in a logical sequence.
_CANONICAL_PHASE_ORDER: list[str] = [
    "research",
    "architecture",
    "implementation",
    "review",
    "review-1-rejected",
    "review-fix",
    "review-2",
    "verification",
    "merge",
]


def merge_phase_times(issue: dict) -> dict:
    """Build a complete ``phase_times`` dict for *issue*.

    The conductor records phase timing data in ``phase_times`` and the list of
    completed phases in ``phases_completed``.  In some sessions the conductor
    only recorded timing for the worker-owned phase (e.g. implementation) but
    not for phases it handled itself (review, merge).  This helper merges both
    sources so every completed phase has an entry.

    Phases present in ``phases_completed`` but absent from ``phase_times`` get
    a **synthetic** placeholder: ``{"_synthetic": True}``.  The rendering code
    can detect this marker to display a "completed (no timing data)" badge
    instead of leaving the phase invisible.

    Returns a *new* ``dict`` — the original issue is never mutated.
    """
    pt: dict = issue.get("phase_times") or {}
    if not isinstance(pt, dict):
        pt = {}
    # Copy so we never mutate the caller's dict
    merged = dict(pt)

    phases_completed: list[str] = issue.get("phases_completed") or []
    for phase in phases_completed:
        if phase not in merged:
            merged[phase] = {"_synthetic": True}

    # Sort into canonical order; unknown phases go to the end.
    order_map = {p: i for i, p in enumerate(_CANONICAL_PHASE_ORDER)}
    sorted_merged: dict = dict(
        sorted(merged.items(), key=lambda kv: order_map.get(kv[0], 999))
    )
    return sorted_merged


# -- Rate limit helpers -----------------------------------------------------


def _rl_color(pct: float | None) -> str:
    """Return CSS color for a rate limit percentage."""
    if pct is None:
        return "var(--muted)"
    if pct >= 90:
        return "var(--red)"
    if pct >= 80:
        return "var(--yellow)"
    return "var(--green)"


def _rl_css_class(pct: float | None) -> str:
    """Return CSS class for rate limit bar fill."""
    if pct is None:
        return ""
    if pct >= 90:
        return "rl-red"
    if pct >= 80:
        return "rl-yellow"
    return "rl-green"


def _throttle_color(level: str) -> str:
    """Return badge background color for throttle level."""
    return {"green": "#22c55e", "yellow": "#f59e0b", "red": "#ef4444"}.get(level, "#6b7280")


def _revert_rate_color(rate: float) -> str:
    """Return CSS color for revert rate badge."""
    if rate >= 0.15:
        return "var(--red)"
    if rate >= 0.05:
        return "var(--yellow)"
    return "var(--green)"


def _cost_str(usd: float | None) -> str:
    """Format a USD cost value for display."""
    if usd is None:
        return "--"
    if usd < 0.01:
        return "<$0.01"
    return f"${usd:.2f}"


def _pct_str(val: float | None) -> str:
    """Format a percentage value for display."""
    if val is None:
        return "--"
    return f"{val * 100:.1f}%"


# -- HTML template ----------------------------------------------------------


def render_dashboard(state: dict) -> str:
    system_state = state.get("system_state", "Stopped")
    last_poll = state.get("last_poll")
    trust_scores = state.get("trust_scores", {})
    issues = state.get("issues", {})
    # v3 state: workers under pipeline.active_workers; v2 fallback: top-level workers
    pipeline = state.get("pipeline", {})
    workers = pipeline.get("active_workers", state.get("workers", {}))
    daily = state.get("daily_counters", {})
    vision = state.get("vision_cache", {})
    discovery = state.get("discovery", {})

    ceremonies = state.get("ceremonies", {})
    self_monitor = state.get("self_monitor", {})
    toolchain_mon = state.get("toolchain_monitor", {})

    today = datetime.now().strftime("%Y-%m-%d")
    today_counters = daily.get(today, {})

    # Discovery counters (from daily_counters or discovery section)
    signals_discovered = today_counters.get(
        "signals_processed",
        discovery.get("signals_validated_today", 0),
    )
    signals_validated = today_counters.get("signals_validated", 0)
    issues_discovered = today_counters.get("issues_discovered", 0)
    active_research_sprints = discovery.get("active_research_sprints", 0)

    # State badge
    state_colors = {
        "Running": "#22c55e",
        "Paused": "#f59e0b",
        "Stopped": "#ef4444",
        "Stopping": "#f59e0b",
    }
    state_color = state_colors.get(system_state, "#6b7280")

    # Trust scores table
    trust_rows = ""
    for project, data in sorted(trust_scores.items()):
        tier = data.get("tier", 0)
        merges = data.get("successful_merges", 0)
        last_revert = data.get("last_revert")
        tier_config = TRUST_TIERS.get(tier, TRUST_TIERS[0])
        tier_bar = "".join(
            f'<span class="tier-dot {"active" if i <= tier else ""}">' f"T{i}</span>"
            for i in range(3)
        )
        trust_rows += f"""
        <tr>
            <td>{_esc(project)}</td>
            <td>{tier_bar}</td>
            <td>{merges}</td>
            <td>{time_ago(last_revert) if last_revert else 'never'}</td>
            <td>{tier_config['concurrent_workers']}</td>
            <td>{tier_config['issues_per_day']}</td>
        </tr>"""

    # Active workers table (v3: keyed by issue ID with phase/attempt fields)
    _state_labels = {
        "implementation": "Implementing",
        "review": "In Review",
        "review-fix": "Fixing Review Findings",
        "research": "Researching",
        "architecture": "Designing",
        "merge": "Merging",
        "verification": "Verifying on Staging",
        "Running": "Running",
        "Dispatched": "Starting Up",
        "InReview": "In Review",
        "Verifying": "Verifying",
        "RetryQueued": "Waiting to Retry",
        "Blocked": "Blocked",
        "Completed": "Done",
        "Escalated": "Needs Human Help",
        "Failed": "Failed",
    }
    active_workers = dict(workers)
    worker_rows = ""
    for wid, w in sorted(active_workers.items()):
        raw_state = w.get("state") or w.get("phase", "Unknown")
        display_state = _state_labels.get(raw_state, raw_state.replace("_", " ").title())
        worker_rows += f"""
        <tr>
            <td>{_issue_link(w.get('issue_id', wid))}</td>
            <td>{_esc(display_state)}</td>
            <td>{elapsed_str(w.get('started_at'))}</td>
            <td>{w.get('attempt', 1)}/3</td>
        </tr>"""
    if not worker_rows:
        worker_rows = '<tr><td colspan="4" class="empty">No active workers</td></tr>'

    # Pending issues (includes blocked, ready, queued — anything not completed/active)
    _terminal = {"Completed", "ResearchComplete", "ArchitectureComplete"}
    _active_ids = set(active_workers.keys())
    pending_issues = {
        iid: i
        for iid, i in issues.items()
        if i.get("state") not in _terminal and iid not in _active_ids
    }
    pending_rows = ""
    for iid, issue in sorted(
        pending_issues.items(),
        key=lambda x: x[1].get("priority", 99),
    ):
        pending_rows += f"""
        <tr>
            <td>{_issue_link(iid)}</td>
            <td>{issue.get('priority', '-')}</td>
            <td>{_esc(issue.get('project', '-'))}</td>
            <td>{_state_labels.get(issue.get('state', '-'), issue.get('state', '-'))}</td>
        </tr>"""
    if not pending_rows:
        pending_rows = '<tr><td colspan="4" class="empty">No pending issues</td></tr>'

    # Recent completions (last 24h)
    completed_issues = {iid: i for iid, i in issues.items() if i.get("state") == "Completed"}
    completion_rows = ""
    for iid, issue in sorted(
        completed_issues.items(),
        key=lambda x: x[1].get("completed_at", ""),
        reverse=True,
    )[:20]:
        completion_rows += f"""
        <tr>
            <td>{_issue_link(iid)}</td>
            <td>{_pr_link(issue.get('pr_number')) or '-'}</td>
            <td>{time_ago(issue.get('completed_at'))}</td>
        </tr>"""
    if not completion_rows:
        completion_rows = '<tr><td colspan="3" class="empty">No completions yet</td></tr>'

    # Vision summary
    last_analysis = vision.get("last_strategy_analysis")
    gaps = vision.get("identified_gaps", [])
    gap_list = ""
    for gap in gaps[:10]:
        if isinstance(gap, str):
            gap_list += f"<li>{_esc(gap)}</li>"
        elif isinstance(gap, dict):
            gap_list += f"<li>{_esc(gap.get('title', str(gap)))}</li>"
    if not gap_list:
        gap_list = "<li class='empty'>No gaps identified</li>"

    # Rate limits — read from native Claude Code statusline output (real-time)
    rl_native_path = Path("/tmp/lacrimosa-rl-native.json")
    rl = {}
    if rl_native_path.exists():
        try:
            rl = json.loads(rl_native_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    # Fall back to state.json if native file not available
    if not rl:
        rl = state.get("rate_limits", {})
    rl_5h = rl.get("five_hour_pct")
    rl_7d = rl.get("seven_day_pct")
    # Compute throttle from actual values
    if rl_5h is not None or rl_7d is not None:
        worst = max(rl_5h or 0, rl_7d or 0)
        rl_throttle = "red" if worst >= 90 else "yellow" if worst >= 50 else "green"
    else:
        rl_throttle = state.get("rate_limits", {}).get("throttle_level", "unknown")
    rl_updated_ts = rl.get("updated_at")
    rl_updated = (
        datetime.fromtimestamp(rl_updated_ts, tz=timezone.utc).isoformat()
        if rl_updated_ts and rl_updated_ts > 0
        else rl.get("last_updated")
    )
    # EMA velocity (from statusline native data)
    rl_ema_5h = rl.get("ema_5h", 0)  # milli-%/hour
    rl_ema_7d = rl.get("ema_7d", 0)  # milli-%/day
    # Reset times
    rl_5h_resets = rl.get("five_hour_resets_at", 0)
    rl_7d_resets = rl.get("seven_day_resets_at", 0)
    # Live session tokens + cost — aggregate all active sessions from /tmp/lacrimosa-sessions/
    _pricing = {"opus": (15.0, 75.0), "sonnet": (3.0, 15.0), "haiku": (0.25, 1.25)}
    _sessions_dir = Path("/tmp/lacrimosa-sessions")
    live_sessions: list[dict] = []
    live_input_tokens = live_output_tokens = live_total_tokens = 0
    live_cost_usd = 0.0
    live_context_pct = None
    if _sessions_dir.exists():
        for sf in _sessions_dir.glob("*.json"):
            try:
                sd = json.loads(sf.read_text())
                live_sessions.append(sd)
                s_in = sd.get("session_input_tokens", 0)
                s_out = sd.get("session_output_tokens", 0)
                live_input_tokens += s_in
                live_output_tokens += s_out
                live_total_tokens += sd.get("session_total_tokens", 0)
                # Cost per session based on its model
                _mk = "opus"
                s_model = sd.get("model", "")
                for k in _pricing:
                    if k in s_model.lower():
                        _mk = k
                        break
                _ip, _op = _pricing[_mk]
                live_cost_usd += (s_in * _ip + s_out * _op) / 1_000_000
                if sd.get("context_used_pct") is not None:
                    live_context_pct = sd["context_used_pct"]  # show last updated
            except (json.JSONDecodeError, OSError):
                pass
    _mk = "mixed" if len({s.get("model", "") for s in live_sessions}) > 1 else (
        live_sessions[0].get("model", "opus") if live_sessions else "opus"
    )
    live_session_count = len(live_sessions)

    # Supplement: compute costs from state.json daily_counters + phase_times
    # This catches costs from issues where phase_times were recorded
    _state_total_cost = 0.0
    _state_total_tokens = 0
    _state_tasks_with_cost = 0
    for _iid, _iss in issues.items():
        _pt = _iss.get("phase_times")
        if isinstance(_pt, dict):
            for _p in _pt.values():
                _c = _p.get("cost_usd", 0) or 0
                _t = _p.get("tokens", 0) or 0
                _state_total_cost += _c
                _state_total_tokens += _t
            if any((_p.get("cost_usd", 0) or 0) > 0 for _p in _pt.values()):
                _state_tasks_with_cost += 1

    # Use whichever source has more data
    if _state_total_cost > live_cost_usd:
        live_cost_usd = _state_total_cost
        live_total_tokens = max(live_total_tokens, _state_total_tokens)
    # Merge task count
    if _state_tasks_with_cost > 0 and live_session_count == 0:
        live_session_count = _state_tasks_with_cost

    # Signal queue
    signal_queue = discovery.get("signal_queue", [])
    signal_rows = ""
    for sig in signal_queue:
        signal_rows += f"""
        <tr>
            <td><code>{_esc(str(sig.get('signal_id', '-')))}</code></td>
            <td>{_esc(str(sig.get('category', '-')))}</td>
            <td>{_esc(str(sig.get('source', '-')))}</td>
            <td>{sig.get('composite_score', 0)}</td>
        </tr>"""
    if not signal_rows:
        signal_rows = '<tr><td colspan="4" class="empty">No signals in queue</td></tr>'

    # Sensor health timestamps
    last_internal_sense = discovery.get("last_internal_sense")
    last_external_sense = discovery.get("last_external_sense")
    last_strategy = discovery.get("last_strategy_analysis")
    last_deep_research = discovery.get("last_deep_research")

    # Ceremony health
    ceremony_names = {
        "standup": "Standup (4h)",
        "sprint_planning": "Sprint Planning (08:00)",
        "grooming": "Backlog Grooming (12h)",
        "retro": "Sprint Retro (22:00)",
        "weekly_summary": "Weekly Summary (Fri)",
    }
    ceremony_cadences = {
        "standup": 4, "sprint_planning": 16, "grooming": 12,
        "retro": 24, "weekly_summary": 168,
    }
    ceremony_rows = ""
    ceremony_missed_count = 0
    now_utc = datetime.now(tz=timezone.utc)
    for key, label in ceremony_names.items():
        cer = ceremonies.get(key, {})
        lr = cer.get("last_run")
        cadence_h = ceremony_cadences.get(key, 24)
        overdue = False
        if lr:
            try:
                lr_dt = datetime.fromisoformat(lr.replace("Z", "+00:00"))
                age_h = (now_utc - lr_dt).total_seconds() / 3600
                overdue = age_h > cadence_h * 1.5
            except (ValueError, TypeError):
                overdue = True
        else:
            overdue = True
        if overdue:
            ceremony_missed_count += 1
        style = 'color:#ef4444;font-weight:600' if overdue else ''
        suffix = ' OVERDUE' if overdue else ''
        ceremony_rows += f"""
        <tr>
            <td>{label}</td>
            <td style="{style}">{time_ago(lr)}{suffix}</td>
        </tr>"""
    if not ceremony_rows:
        ceremony_rows = '<tr><td colspan="2" class="empty">No ceremony data</td></tr>'

    # Self-monitor snapshot (fallback to metrics_summary when self-monitor hasn't run)
    sm_last = self_monitor.get("last_run")
    sm_snap = self_monitor.get("last_snapshot") or {}
    sm_quality = sm_snap.get("quality", {}) if isinstance(sm_snap, dict) else {}
    sm_cost = sm_snap.get("cost", {}) if isinstance(sm_snap, dict) else {}
    sm_ceremony = sm_snap.get("ceremony", {}) if isinstance(sm_snap, dict) else {}
    sm_ceremony["missed_count"] = ceremony_missed_count  # Override with live calculation
    sm_pending = self_monitor.get("pending_tune_entries", [])

    # Fallback: populate sm_quality from metrics_summary.last_7d if self-monitor never ran
    if not sm_quality:
        _m7d = state.get("metrics_summary", {}).get("last_7d", {})
        if _m7d:
            sm_quality = {
                "revert_rate": _m7d.get("revert_rate"),
                "avg_review_iterations": _m7d.get("avg_review_iterations"),
            }
    if not sm_cost:
        _mt = state.get("metrics_summary", {}).get("today", {})
        if _mt and _mt.get("avg_cost_per_task") is not None:
            sm_cost = {"total_daily_cost_usd": _mt.get("avg_cost_per_task")}

    # Toolchain monitor
    tc_last = toolchain_mon.get("last_run")
    tc_count = toolchain_mon.get("last_findings_count", 0)

    # Metrics summary (from conductor's per-cycle update)
    metrics = state.get("metrics_summary", {})
    m_today = metrics.get("today", {})
    m_7d = metrics.get("last_7d", {})

    # Today metrics — always prefer live-computed values over stale metrics_summary
    today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    _tc_today = state.get("daily_counters", {}).get(today_str, {})

    # Task count: PRs merged is the authoritative count
    today_tasks = _tc_today.get("prs_merged", 0) or m_today.get("tasks_completed", 0)

    # Cost: use live_cost_usd (from phase_times + session data), fall back to metrics_summary
    today_cost = live_cost_usd if live_cost_usd > 0 else m_today.get("cost_usd")

    # Tokens: use live total, fall back to metrics_summary
    today_tokens = live_total_tokens if live_total_tokens > 0 else m_today.get("tokens_used", 0)

    # Avg cost per task
    avg_cost_task = (today_cost / max(today_tasks, 1)) if today_cost and today_tasks else m_today.get("avg_cost_per_task")

    # Compute 7d stats from state.json instead of stale metrics_summary
    _now_utc = datetime.now(tz=timezone.utc)
    _7d_cutoff = (_now_utc - timedelta(days=7)).strftime("%Y-%m-%d")
    _7d_cost = 0.0
    _7d_tasks = 0
    for _d, _dc in state.get("daily_counters", {}).items():
        if _d >= _7d_cutoff:
            _7d_tasks += _dc.get("prs_merged", 0)
    for _iid, _iss in issues.items():
        _pt = _iss.get("phase_times")
        if not isinstance(_pt, dict):
            continue
        _cdate = (_iss.get("completed_at") or _iss.get("merged_at") or "")[:10]
        if _cdate and _cdate >= _7d_cutoff:
            _7d_cost += sum((_p.get("cost_usd", 0) or 0) for _p in _pt.values())
    week_cost = _7d_cost if _7d_cost > 0 else (m_7d.get("cost_usd") or today_cost)
    week_tasks = _7d_tasks if _7d_tasks > 0 else (m_7d.get("tasks_completed", 0) or today_tasks)
    week_revert_rate = m_7d.get("revert_rate")
    week_avg_review = m_7d.get("avg_review_iterations")

    # Model mix breakdown
    model_mix = m_today.get("cost_by_model", {})
    model_mix_rows = ""
    for model_id, cost in sorted(model_mix.items(), key=lambda x: x[1], reverse=True):
        short_name = model_id.split("[")[0] if "[" in model_id else model_id
        model_mix_rows += f"""
        <tr>
            <td><code>{_esc(short_name)}</code></td>
            <td style="text-align:right;">{_cost_str(cost)}</td>
        </tr>"""
    if not model_mix_rows:
        model_mix_rows = '<tr><td colspan="2" class="empty">No model data</td></tr>'

    # Cost by phase breakdown
    phase_costs = m_today.get("cost_by_phase", {})
    phase_cost_rows = ""
    for phase, cost in sorted(phase_costs.items(), key=lambda x: x[1], reverse=True):
        phase_cost_rows += f"""
        <tr>
            <td>{_esc(phase)}</td>
            <td style="text-align:right;">{_cost_str(cost)}</td>
        </tr>"""
    if not phase_cost_rows:
        phase_cost_rows = '<tr><td colspan="2" class="empty">No phase data</td></tr>'

    # Recent task costs (from per-issue metrics in state)
    recent_tasks = metrics.get("recent_tasks", [])
    task_cost_rows = ""
    for task in recent_tasks[:10]:
        t_issue = task.get("issue_id", "-")
        t_phase = task.get("phase", "-")
        t_cost = task.get("cost_usd")
        t_tokens = task.get("total_tokens", 0)
        t_outcome = task.get("outcome", "-")
        outcome_color = (
            "var(--green)"
            if t_outcome == "success"
            else "var(--red)"
            if t_outcome == "failed"
            else "var(--muted)"
        )
        task_cost_rows += f"""
        <tr>
            <td><code>{_esc(t_issue)}</code></td>
            <td>{_esc(t_phase)}</td>
            <td style="text-align:right;">{_cost_str(t_cost)}</td>
            <td style="text-align:right;">{t_tokens:,}</td>
            <td style="color:{outcome_color};">{_esc(t_outcome)}</td>
        </tr>"""
    if not task_cost_rows:
        task_cost_rows = '<tr><td colspan="5" class="empty">No task metrics yet</td></tr>'

    # 7-day trend data — compute from state.json issues + daily_counters
    # (metrics files are not reliably written, so derive from state directly)
    from collections import defaultdict as _defaultdict
    _trend_by_date: dict[str, dict] = _defaultdict(lambda: {"cost": 0.0, "tasks": 0})
    for _iid, _iss in issues.items():
        _pt = _iss.get("phase_times")
        if not isinstance(_pt, dict):
            continue
        _icost = sum((_p.get("cost_usd", 0) or 0) for _p in _pt.values())
        # Determine completion date
        _idate = (_iss.get("completed_at") or _iss.get("merged_at") or "")[:10]
        if not _idate:
            # Fallback: earliest phase timestamp
            _ts_list = [
                _p.get("started_at") or _p.get("completed_at") or ""
                for _p in _pt.values()
            ]
            _ts_list = [t for t in _ts_list if t]
            _idate = min(_ts_list)[:10] if _ts_list else ""
        if _idate:
            _trend_by_date[_idate]["cost"] += _icost
            _trend_by_date[_idate]["tasks"] += 1
    # Supplement task counts from daily_counters (catches tasks without cost data)
    for _d, _dc in state.get("daily_counters", {}).items():
        _merged = _dc.get("prs_merged", 0)
        if _merged > _trend_by_date[_d]["tasks"]:
            _trend_by_date[_d]["tasks"] = _merged

    # Build 7-day trend bars
    trend_bars = ""
    _trend_costs = []
    for _i in range(6, -1, -1):
        _d = (_now_utc - timedelta(days=_i)).strftime("%Y-%m-%d")
        _entry = _trend_by_date.get(_d, {"cost": 0.0, "tasks": 0})
        _trend_costs.append((_d, _entry["cost"], _entry["tasks"]))
    _max_cost = max((c for _, c, _ in _trend_costs), default=1) or 1
    for _d, _cost, _tasks in _trend_costs:
        _d_short = _d[-5:]
        _bar_pct = min(100, (_cost / _max_cost) * 100) if _max_cost > 0 else 0
        trend_bars += f"""
        <div style="display:flex;align-items:center;gap:0.5rem;margin:0.2rem 0;">
          <span style="font-size:0.75rem;color:var(--muted);width:3rem;">{_d_short}</span>
          <div class="rl-bar" style="flex:1;">
            <div class="rl-fill rl-green" style="width:{_bar_pct:.0f}%;"></div>
          </div>
          <span style="font-size:0.75rem;width:4rem;text-align:right;">{_cost_str(_cost)}</span>
          <span style="font-size:0.7rem;color:var(--muted);width:2rem;">{_tasks}t</span>
        </div>"""
    if not trend_bars:
        trend_bars = '<div class="empty" style="padding:0.5rem;">No trend data</div>'

    # Bug/revert tracking
    bugs_total = m_7d.get("bugs_linked_total", 0)
    reverts_total = m_7d.get("prs_reverted", 0)
    merges_total = m_7d.get("prs_merged", 0)

    # Task pipeline detail — per-phase breakdown for each issue
    _phase_labels = {
        "research": "Research", "architecture": "Design",
        "implementation": "Implement", "review": "Review",
        "review-1-rejected": "Review (Rejected)", "review-fix": "Fix Findings",
        "review-2": "Re-Review", "verification": "Verify", "merge": "Merge",
    }
    _phase_colors = {
        "research": "#8b5cf6", "architecture": "#6366f1",
        "implementation": "#38bdf8", "review": "#f59e0b",
        "review-1-rejected": "#ef4444", "review-fix": "#fb923c",
        "review-2": "#f59e0b", "verification": "#22d3ee", "merge": "#22c55e",
    }
    pipeline_rows = ""
    # Show ALL completed/active issues, sorted by most recent first.
    # Use merge_phase_times() so issues with phases_completed but
    # incomplete phase_times still show all their completed phases.
    all_pipeline_issues = [
        (iid, i) for iid, i in issues.items()
        if i.get("state") in ("Completed", "Implementation", "Review", "Merging", "Verifying")
    ]
    all_pipeline_issues.sort(
        key=lambda x: x[1].get("completed_at", x[1].get("pipeline_entered_at", "")),
        reverse=True,
    )
    for iid, issue in all_pipeline_issues[:20]:
        pt = merge_phase_times(issue)
        pr_num = issue.get("pr_number", "")
        issue_state = issue.get("state", "")
        verif = issue.get("verification", {})
        v_status = verif.get("status", "unknown") if isinstance(verif, dict) else "unknown"
        _v_colors = {"verified": "var(--green)", "unverified": "var(--red)", "partial": "var(--yellow)", "in_progress": "var(--accent)"}
        v_color = _v_colors.get(v_status, "var(--muted)")
        desc = issue.get("description", issue.get("lifecycle", iid))

        # Issues without any phase info get a compact summary row
        if not pt:
            pipeline_rows += f"""
            <div style="background:var(--surface);border-radius:6px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;display:flex;justify-content:space-between;align-items:center;">
              <div>
                <strong>{_issue_link(iid)}</strong>
                <span style="color:var(--muted);font-size:0.8rem;margin-left:0.5rem;">{_esc(str(desc)[:60])}</span>
              </div>
              <div style="font-size:0.8rem;">
                {_pr_link(pr_num)}
                <span style="color:var(--muted);margin-left:0.5rem;">{issue_state}</span>
                <a href="/api/report/{iid}" target="_blank" style="text-decoration:none;margin-left:0.5rem;">
                  <span style="color:{v_color};">●</span>
                  <span style="font-size:0.7rem;color:{v_color};">{v_status}</span>
                </a>
              </div>
            </div>"""
            continue

        total_cost = sum(p.get("cost_usd", 0) or 0 for p in pt.values())
        total_tokens = sum(p.get("tokens", 0) or 0 for p in pt.values())
        total_findings = sum(p.get("findings", 0) or 0 for p in pt.values())
        rev_iters = issue.get("review_iteration", 1)
        desc = issue.get("description", iid)
        # Phase bar segments — include synthetic phases so every completed
        # phase is visible in the bar, even without timing data.
        phase_segments = ""
        all_durations: list[tuple[str, float, bool]] = []
        for pname, pdata in pt.items():
            s = pdata.get("started_at")
            e = pdata.get("completed_at")
            is_synthetic = pdata.get("_synthetic", False)
            if s and e and not is_synthetic:
                try:
                    ds = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    de = datetime.fromisoformat(e.replace("Z", "+00:00"))
                    dur_m = max(1, (de - ds).total_seconds() / 60)
                    all_durations.append((pname, dur_m, False))
                except (ValueError, TypeError):
                    all_durations.append((pname, 1, True))
            else:
                # Synthetic or missing timestamps — give a minimal placeholder
                all_durations.append((pname, 1, is_synthetic))
        # Bar proportions use all durations; display total excludes synthetic
        total_dur_bar = sum(d for _, d, _ in all_durations) or 1
        total_dur = sum(d for _, d, syn in all_durations if not syn) or sum(d for _, d, _ in all_durations) or 1
        for pname, dur_m, is_syn in all_durations:
            pct = (dur_m / total_dur_bar) * 100
            color = _phase_colors.get(pname, "#6b7280")
            label = _phase_labels.get(pname, pname)
            opacity = "0.45" if is_syn else "1"
            title_suffix = " (no timing data)" if is_syn else f": {dur_m:.0f}m"
            phase_segments += (
                f'<div title="{label}{title_suffix}" '
                f'style="width:{pct:.1f}%;background:{color};height:100%;'
                f'opacity:{opacity};display:inline-block;"></div>'
            )
        # Phase detail rows
        phase_detail = ""
        for pname, pdata in pt.items():
            label = _phase_labels.get(pname, pname)
            color = _phase_colors.get(pname, "#6b7280")
            s = pdata.get("started_at")
            e = pdata.get("completed_at")
            dur_str = "--"
            if s and e:
                try:
                    ds = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    de = datetime.fromisoformat(e.replace("Z", "+00:00"))
                    dur_s = int((de - ds).total_seconds())
                    dur_str = f"{dur_s // 60}m {dur_s % 60}s"
                except (ValueError, TypeError):
                    pass
            p_tokens = pdata.get("tokens", 0) or 0
            # Merge phase has no cost tracking — treat as $0 instead of null
            p_cost = pdata.get("cost_usd", 0 if pname == "merge" else None)
            p_findings = pdata.get("findings", 0) or 0
            p_detail = pdata.get("findings_detail", "")
            findings_html = (
                f'<span style="color:var(--yellow);">{p_findings} issues</span>'
                f'<span style="font-size:0.7rem;color:var(--muted);"> ({_esc(p_detail)})</span>'
                if p_findings > 0 else
                '<span style="color:var(--green);">clean</span>'
                if pname in ("review", "review-2") else ""
            )
            phase_detail += f"""
            <tr>
              <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:4px;"></span>{label}</td>
              <td>{dur_str}</td>
              <td style="text-align:right;">{p_tokens:,}</td>
              <td style="text-align:right;">{_cost_str(p_cost)}</td>
              <td>{findings_html}</td>
            </tr>"""

        pipeline_rows += f"""
        <div style="background:var(--surface);border-radius:6px;padding:0.8rem;margin-bottom:0.6rem;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
            <div>
              <strong>{_issue_link(iid)}</strong>
              <span style="color:var(--muted);font-size:0.8rem;margin-left:0.5rem;">{_esc(str(desc)[:80])}</span>
            </div>
            <div style="font-size:0.8rem;">
              {_pr_link(pr_num)}
              <span style="color:var(--muted);margin-left:0.5rem;">{rev_iters} review round{"s" if rev_iters != 1 else ""}</span>
              <span style="color:var(--accent);margin-left:0.5rem;">{_cost_str(total_cost)}</span>
              <span style="color:var(--muted);margin-left:0.5rem;">{total_tokens:,} tokens</span>
              <a href="/api/report/{iid}" target="_blank" style="text-decoration:none;margin-left:0.5rem;" title="Verification report">
                <span style="color:{v_color};">●</span>
                <span style="font-size:0.7rem;color:{v_color};">{v_status}</span>
              </a>
            </div>
          </div>
          <div style="background:var(--border);border-radius:3px;height:8px;overflow:hidden;margin-bottom:0.5rem;display:flex;">
            {phase_segments}
          </div>
          <table style="font-size:0.8rem;">
            <tr><th>Phase</th><th>Duration</th><th style="text-align:right;">Tokens</th><th style="text-align:right;">Cost</th><th>Findings</th></tr>
            {phase_detail}
            <tr style="font-weight:bold;border-top:1px solid var(--border);">
              <td>Total</td>
              <td>{total_dur:.0f}m</td>
              <td style="text-align:right;">{total_tokens:,}</td>
              <td style="text-align:right;">{_cost_str(total_cost)}</td>
              <td>{total_findings} total</td>
            </tr>
          </table>
        </div>"""
    if not pipeline_rows:
        pipeline_rows = '<div class="empty" style="padding:1rem;">No task pipeline data yet. Phase timing is recorded as tasks complete.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lacrimosa Dashboard</title>
<meta http-equiv="refresh" content="5">
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
    --green: #22c55e; --yellow: #f59e0b; --red: #ef4444;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'SF Mono', 'Fira Code', monospace;
    background: var(--bg); color: var(--text);
    padding: 1.5rem; line-height: 1.5;
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.5rem; }}
  h2 {{
    font-size: 1rem; color: var(--accent);
    margin: 1.5rem 0 0.5rem; border-bottom: 1px solid var(--border);
    padding-bottom: 0.3rem;
  }}
  .header {{
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: 1rem; flex-wrap: wrap;
  }}
  .badge {{
    display: inline-block; padding: 0.2rem 0.8rem;
    border-radius: 4px; font-size: 0.85rem; font-weight: 600;
    color: #000;
  }}
  .stat {{
    background: var(--surface); padding: 0.4rem 0.8rem;
    border-radius: 4px; font-size: 0.85rem;
  }}
  .stat .label {{ color: var(--muted); }}
  table {{
    width: 100%; border-collapse: collapse;
    background: var(--surface); border-radius: 6px;
    overflow: hidden; margin-bottom: 0.5rem;
  }}
  th {{ text-align: left; padding: 0.5rem 0.8rem;
       background: var(--border); color: var(--accent);
       font-size: 0.8rem; text-transform: uppercase; }}
  td {{ padding: 0.4rem 0.8rem; border-top: 1px solid var(--border);
       font-size: 0.85rem; }}
  tr:hover {{ background: rgba(56, 189, 248, 0.05); }}
  code {{ color: var(--accent); }}
  .empty {{ color: var(--muted); font-style: italic; text-align: center; }}
  .tier-dot {{
    display: inline-block; padding: 0.1rem 0.4rem; margin: 0 0.15rem;
    border-radius: 3px; font-size: 0.7rem;
    background: var(--border); color: var(--muted);
  }}
  .tier-dot.active {{
    background: var(--green); color: #000; font-weight: 600;
  }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .controls {{
    display: flex; gap: 0.5rem; margin-top: 0.5rem;
  }}
  .controls button {{
    padding: 0.3rem 1rem; border-radius: 4px; border: 1px solid var(--border);
    background: var(--surface); color: var(--text); cursor: pointer;
    font-family: inherit; font-size: 0.85rem;
  }}
  .controls button:hover {{ background: var(--border); }}
  ul {{ list-style: disc; padding-left: 1.5rem; }}
  li {{ font-size: 0.85rem; margin: 0.2rem 0; }}
  .rl-bar {{
    height: 8px; border-radius: 4px; background: var(--border);
    overflow: hidden; margin-top: 4px;
  }}
  .rl-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
  .rl-green {{ background: var(--green); }}
  .rl-yellow {{ background: var(--yellow); }}
  .rl-red {{ background: var(--red); }}
  .rl-card {{
    background: var(--surface); padding: 0.6rem 1rem;
    border-radius: 6px; flex: 1; min-width: 140px;
  }}
  .rl-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; }}
  .rl-value {{ font-size: 1.2rem; font-weight: 600; }}
  .throttle-badge {{
    display: inline-block; padding: 0.15rem 0.6rem;
    border-radius: 3px; font-size: 0.75rem; font-weight: 600; color: #000;
  }}
  .metric-cards {{
    display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.5rem;
  }}
  .metric-card {{
    background: var(--surface); padding: 0.6rem 1rem;
    border-radius: 6px; flex: 1; min-width: 120px;
  }}
  .metric-card .mc-label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; }}
  .metric-card .mc-value {{ font-size: 1.3rem; font-weight: 600; }}
  .metric-card .mc-sub {{ font-size: 0.7rem; color: var(--muted); margin-top: 2px; }}
</style>
</head>
<body>

<div class="header">
  <h1>Lacrimosa</h1>
  <span class="badge" style="background: {state_color};">{system_state}</span>
  <span class="stat"><span class="label">Last poll:</span> {time_ago(last_poll)}</span>
  <span class="stat"><span class="label">Workers:</span> {len(active_workers)}</span>
  <span class="stat"><span class="label">Today:</span> {signals_validated} discovered, {today_counters.get('issues_created', 0)} created, {today_counters.get('prs_merged', 0)} merged</span>
</div>

<div class="controls">
  <button onclick="fetch('/api/pause', {{method:'POST'}}).then(()=>location.reload())">Pause</button>
  <button onclick="fetch('/api/resume', {{method:'POST'}}).then(()=>location.reload())">Resume</button>
  <button onclick="location.reload()">Refresh</button>
</div>

<h2>Rate Limits <span style="font-size:0.7rem;font-weight:normal;color:var(--muted);">(native from Claude Code statusline)</span></h2>
<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:0.5rem;">
  <div class="rl-card">
    <div class="rl-label">5-hour window</div>
    <div class="rl-value" style="color:{_rl_color(rl_5h)};">{f'{rl_5h:.0f}%' if rl_5h is not None else '--'}</div>
    <div class="rl-bar"><div class="rl-fill {_rl_css_class(rl_5h)}" style="width:{rl_5h or 0}%;"></div></div>
    <div style="font-size:0.7rem;color:var(--muted);margin-top:2px;">{f'{rl_ema_5h/1000:.1f}%/h burn' if rl_ema_5h and rl_ema_5h > 0 else ''}{f' · resets {time_ago_ts(rl_5h_resets)}' if rl_5h_resets and rl_5h_resets > 0 else ''}</div>
  </div>
  <div class="rl-card">
    <div class="rl-label">7-day window</div>
    <div class="rl-value" style="color:{_rl_color(rl_7d)};">{f'{rl_7d:.0f}%' if rl_7d is not None else '--'}</div>
    <div class="rl-bar"><div class="rl-fill {_rl_css_class(rl_7d)}" style="width:{rl_7d or 0}%;"></div></div>
    <div style="font-size:0.7rem;color:var(--muted);margin-top:2px;">{f'{rl_ema_7d/1000:.1f}%/d burn' if rl_ema_7d and rl_ema_7d > 0 else ''}{f' · resets {time_ago_ts(rl_7d_resets)}' if rl_7d_resets and rl_7d_resets > 0 else ''}</div>
  </div>
  <div class="rl-card">
    <div class="rl-label">Throttle</div>
    <div><span class="throttle-badge" style="background:{_throttle_color(rl_throttle)};">{rl_throttle.upper()}</span></div>
    <div style="font-size:0.75rem;color:var(--muted);margin-top:4px;">Updated {time_ago(rl_updated)}</div>
  </div>
</div>

<h2>Trust Scores</h2>
<table>
  <tr><th>Project</th><th>Tier</th><th>Merges</th><th>Last Revert</th><th>Concurrent</th><th>Daily Cap</th></tr>
  {trust_rows if trust_rows else '<tr><td colspan="6" class="empty">No trust data yet</td></tr>'}
</table>

<div class="grid">
  <div>
    <h2>Active Workers ({len(active_workers)})</h2>
    <table>
      <tr><th>Issue</th><th>State</th><th>Elapsed</th><th>Attempt</th></tr>
      {worker_rows}
    </table>
  </div>
  <div>
    <h2>Pending Issues ({len(pending_issues)})</h2>
    <table>
      <tr><th>Issue</th><th>Priority</th><th>Project</th><th>State</th></tr>
      {pending_rows}
    </table>
  </div>
</div>

<div class="grid">
  <div>
    <h2>Recent Completions</h2>
    <table>
      <tr><th>Issue</th><th>PR</th><th>Completed</th></tr>
      {completion_rows}
    </table>
  </div>
  <div>
    <h2>Vision Analysis</h2>
    <p style="font-size:0.85rem;color:var(--muted);">Last analysis: {time_ago(last_analysis)}</p>
    <ul>{gap_list}</ul>
  </div>
</div>

<div class="grid">
  <div>
    <h2>Discovery</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Signals discovered today</td><td>{signals_discovered}</td></tr>
      <tr><td>Signals validated today</td><td>{signals_validated}</td></tr>
      <tr><td>Issues from discovery today</td><td>{issues_discovered}</td></tr>
      <tr><td>Active research sprints</td><td>{active_research_sprints}</td></tr>
    </table>
  </div>
  <div>
    <h2>Sensor Health</h2>
    <table>
      <tr><th>Sensor</th><th>Last Run</th></tr>
      <tr><td>Internal sense</td><td>{time_ago(last_internal_sense)}</td></tr>
      <tr><td>External sense</td><td>{time_ago(last_external_sense)}</td></tr>
      <tr><td>Strategy analysis</td><td>{time_ago(last_strategy)}</td></tr>
      <tr><td>Deep research</td><td>{time_ago(last_deep_research)}</td></tr>
    </table>
  </div>
</div>

<h2>Ceremony Health</h2>
<table>
  <tr><th>Ceremony</th><th>Last Run</th></tr>
  {ceremony_rows}
</table>

<div class="grid">
  <div>
    <h2>Self-Monitor</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Last run</td><td>{time_ago(sm_last)}</td></tr>
      <tr><td>Revert rate</td><td style="color:{_revert_rate_color(sm_quality.get('revert_rate', 0))};">{_pct_str(sm_quality.get('revert_rate'))}</td></tr>
      <tr><td>Avg review iters</td><td>{f"{sm_quality.get('avg_review_iterations', 0):.1f}" if sm_quality else '--'}</td></tr>
      <tr><td>Cost/task</td><td>{_cost_str(sm_cost.get('total_daily_cost_usd'))}</td></tr>
      <tr><td>Ceremony misses</td><td>{sm_ceremony.get('missed_count', 0)}</td></tr>
      <tr><td>Pending tune entries</td><td>{len(sm_pending)}</td></tr>
    </table>
  </div>
  <div>
    <h2>Toolchain Monitor</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Last run</td><td>{time_ago(tc_last)}</td></tr>
      <tr><td>Findings (last run)</td><td>{tc_count}</td></tr>
    </table>
  </div>
</div>

<h2>Signal Queue ({len(signal_queue)})</h2>
<table>
  <tr><th>Signal ID</th><th>Category</th><th>Source</th><th>Score</th></tr>
  {signal_rows}
</table>

<h2>Token Costs</h2>
<div class="metric-cards">
  <div class="metric-card">
    <div class="mc-label">Live{f' ({live_session_count} sessions)' if live_session_count > 1 else ''}</div>
    <div class="mc-value" style="color:var(--accent);">${live_cost_usd:.2f}</div>
    <div class="mc-sub">{live_total_tokens:,} tokens ({_mk}){f' &middot; ctx: {live_context_pct}%' if live_context_pct else ''}</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">Today</div>
    <div class="mc-value" style="color:var(--accent);">{_cost_str(today_cost)}</div>
    <div class="mc-sub">{today_tasks} tasks &middot; {today_tokens:,} tokens</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">7-Day Total</div>
    <div class="mc-value">{_cost_str(week_cost)}</div>
    <div class="mc-sub">{week_tasks} tasks</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">Avg / Task</div>
    <div class="mc-value">{_cost_str(avg_cost_task)}</div>
    <div class="mc-sub">today&rsquo;s average</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">Revert Rate</div>
    <div class="mc-value" style="color:{_revert_rate_color(week_revert_rate or 0)};">{_pct_str(week_revert_rate)}</div>
    <div class="mc-sub">7-day &middot; {reverts_total}/{merges_total} PRs</div>
  </div>
</div>

<div class="grid">
  <div>
    <h2>Quality &amp; Bugs (7d)</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Revert rate</td><td style="color:{_revert_rate_color(week_revert_rate or 0)};">{_pct_str(week_revert_rate)}</td></tr>
      <tr><td>Avg review iterations</td><td>{f'{week_avg_review:.1f}' if week_avg_review is not None else '--'}</td></tr>
      <tr><td>Bugs linked to PRs</td><td>{bugs_total}</td></tr>
      <tr><td>PRs reverted</td><td>{reverts_total}</td></tr>
      <tr><td>PRs merged</td><td>{merges_total}</td></tr>
    </table>
  </div>
  <div>
    <h2>Model Mix (Today)</h2>
    <table>
      <tr><th>Model</th><th style="text-align:right;">Cost</th></tr>
      {model_mix_rows}
    </table>
  </div>
</div>

<div class="grid">
  <div>
    <h2>Cost by Phase (Today)</h2>
    <table>
      <tr><th>Phase</th><th style="text-align:right;">Cost</th></tr>
      {phase_cost_rows}
    </table>
  </div>
  <div>
    <h2>7-Day Cost Trend</h2>
    <div style="background:var(--surface);border-radius:6px;padding:0.6rem 1rem;">
      {trend_bars}
    </div>
  </div>
</div>

<h2>Task Pipeline (Recent)</h2>
{pipeline_rows}

</body>
</html>"""


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _linear_base() -> str:
    return f"https://linear.app/{lacrimosa_config.get('linear.workspace_slug')}/issue"


def _issue_link(issue_id: str) -> str:
    """Render an issue ID as a clickable link to Linear."""
    eid = _esc(str(issue_id))
    prefix = lacrimosa_config.get("linear.issue_prefix", "")
    if prefix and eid.startswith(f"{prefix}-"):
        return f'<a href="{_linear_base()}/{eid}" target="_blank" style="color:var(--accent);text-decoration:none;"><code>{eid}</code></a>'
    return f"<code>{eid}</code>"


def _pr_link(pr_num: int | str | None) -> str:
    """Render a PR number as a clickable link to GitHub."""
    if not pr_num:
        return ""
    gh_base = lacrimosa_config.get("github.repo_url", "")
    if not gh_base:
        return f"PR #{_esc(str(pr_num))}"
    return f'<a href="{gh_base}/pull/{pr_num}" target="_blank" style="color:var(--accent);text-decoration:none;">PR #{_esc(str(pr_num))}</a>'


# -- HTTP Handler -----------------------------------------------------------


class LacrimosaDashboardHandler(SimpleHTTPRequestHandler):
    """Custom handler for Lacrimosa dashboard."""

    def log_message(self, format: str, *args) -> None:
        """Suppress default access logs."""
        pass

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/dashboard":
            self._serve_dashboard()
        elif self.path == "/health":
            self._serve_health()
        elif self.path == "/api/state":
            self._serve_json(read_state())
        elif self.path == "/api/metrics":
            self._serve_metrics()
        elif self.path.startswith("/api/report/"):
            self._serve_report(self.path[len("/api/report/"):])
        elif self.path.startswith("/screenshots/"):
            self._serve_screenshot(self.path[len("/screenshots/"):])
        else:
            self.send_error(404)

    def _serve_screenshot(self, filename: str) -> None:
        """Serve screenshot images from output/verification/ or output/visual-qa/."""
        from urllib.parse import unquote
        import mimetypes
        filename = unquote(filename).replace("..", "").lstrip("/")
        project_root = Path(__file__).parent.parent
        search_dirs = [
            project_root / "output" / "verification" / "screenshots",
            project_root / "output" / "verification",
            project_root / "output" / "visual-qa",
            project_root / "output",
        ]
        for d in search_dirs:
            fp = d / filename
            if fp.exists() and fp.is_file():
                mime = mimetypes.guess_type(str(fp))[0] or "image/png"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(fp.read_bytes())
                return
        self.send_error(404)

    def _serve_report(self, issue_id: str) -> None:
        """Serve verification report for an issue."""
        import glob, re
        from urllib.parse import unquote
        import html as html_mod

        issue_id = unquote(issue_id).strip("/")
        project_root = Path(__file__).parent.parent

        # Search for report files — ONLY issue-specific matches
        # Step 1: file with issue_id in name
        issue_pattern = str(project_root / "output" / "verification" / f"*{issue_id}*")
        report_content = report_name = None
        for match in sorted(glob.glob(issue_pattern), reverse=True):
            if match.endswith(".md"):
                try:
                    report_content = Path(match).read_text(encoding="utf-8")
                    report_name = Path(match).name
                    break
                except OSError:
                    continue

        # Step 2: check state.json report_path (may point to a batch report)
        if not report_content:
            state_tmp = read_state()
            _iss = state_tmp.get("issues", {}).get(issue_id, {})
            rp = (_iss.get("verification") or {}).get("report_path", "")
            pr_num = str(_iss.get("pr_number", ""))
            lifecycle = _iss.get("lifecycle", "")
            if rp:
                rp_full = Path(rp) if Path(rp).is_absolute() else project_root / rp
                if rp_full.is_file():
                    try:
                        batch_content = rp_full.read_text(encoding="utf-8")
                        report_name = rp_full.name
                    except OSError:
                        batch_content = None

                    # Extract ONLY lines mentioning this issue or its PR
                    if batch_content:
                        lines = batch_content.split("\n")
                        relevant = []
                        for i, line in enumerate(lines):
                            if issue_id in line or (pr_num and (f"#{pr_num}" in line or f"| {pr_num} " in line)):
                                start = max(0, i - 3)
                                end = min(len(lines), i + 10)
                                relevant.extend(lines[start:end])
                                relevant.append("")

                        if relevant:
                            report_content = f"# Verification: {issue_id} (PR #{pr_num})\n\n**Type:** {lifecycle}\n**Source:** {report_name}\n\n---\n\n" + "\n".join(relevant)
                        else:
                            # Batch report exists but doesn't mention this issue — don't show it
                            report_content = None

        # Check state for verification note
        state = read_state()
        issue = state.get("issues", {}).get(issue_id, {})
        verif = issue.get("verification", {}) if isinstance(issue.get("verification"), dict) else {}
        v_status = verif.get("status", "unknown")
        v_note = verif.get("note", "")

        if not report_content and not v_note:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"""<html><body style="background:#0f172a;color:#e2e8f0;font-family:sans-serif;padding:2rem;">
            <h2>No verification report for {_esc(issue_id)}</h2>
            <p>Status: {_esc(v_status)}</p><a href="/" style="color:#3b82f6;">← Dashboard</a>
            </body></html>""".encode())
            return

        if not report_content and v_note:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"""<html><head><meta charset="utf-8"><style>body{{background:#0f172a;color:#e2e8f0;font-family:sans-serif;padding:2rem;max-width:600px;margin:0 auto;}}</style></head><body>
            <a href="/" style="color:#3b82f6;font-size:0.8rem;">← Dashboard</a>
            <h2>Verification: {_esc(issue_id)}</h2>
            <p><strong>Status:</strong> {_esc(v_status)}</p>
            <p><strong>Note:</strong> {_esc(v_note)}</p>
            </body></html>""".encode())
            return

        # Extract images BEFORE escaping, replace with placeholders
        report_content = report_content or ""
        _images: list[str] = []
        def _capture_md_img(m):
            tag = f'<img src="/screenshots/{m.group(2).split("/")[-1]}" alt="{html_mod.escape(m.group(1))}" style="max-width:100%;border-radius:8px;margin:0.5rem 0;">'
            _images.append(tag)
            return f"__IMG_{len(_images)-1}__"
        report_content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _capture_md_img, report_content)
        # Also capture bare .png references
        def _capture_bare_png(m):
            tag = f'<img src="/screenshots/{html_mod.escape(m.group(1))}" alt="{html_mod.escape(m.group(1))}" style="max-width:300px;border-radius:4px;">'
            _images.append(tag)
            return f"__IMG_{len(_images)-1}__"
        report_content = re.sub(r'(?<!\/)(\b[\w-]+\.png\b)', _capture_bare_png, report_content)
        # Escape HTML (placeholders are safe text)
        safe = html_mod.escape(report_content)
        # Restore image placeholders
        for i, tag in enumerate(_images):
            safe = safe.replace(f"__IMG_{i}__", tag)
        # Markdown → HTML conversion
        # Code blocks (before other transforms)
        safe = re.sub(r'```(\w*)\n(.*?)```', r'<pre style="background:#1e293b;padding:1rem;border-radius:6px;overflow-x:auto;font-size:0.85rem;"><code>\2</code></pre>', safe, flags=re.DOTALL)
        # Headers
        safe = re.sub(r'^### (.+)$', r'<h3>\1</h3>', safe, flags=re.MULTILINE)
        safe = re.sub(r'^## (.+)$', r'<h2>\1</h2>', safe, flags=re.MULTILINE)
        safe = re.sub(r'^# (.+)$', r'<h1>\1</h1>', safe, flags=re.MULTILINE)
        # Bold and italic
        safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
        safe = re.sub(r'\*(.+?)\*', r'<em>\1</em>', safe)
        # Inline code
        safe = re.sub(r'`([^`]+)`', r'<code style="background:#334155;padding:2px 6px;border-radius:3px;">\1</code>', safe)
        # Horizontal rules
        safe = re.sub(r'^---+$', r'<hr style="border-color:#334155;margin:1rem 0;">', safe, flags=re.MULTILINE)
        # Tables: convert markdown tables to HTML
        _table_lines: list[str] = []
        _out_lines: list[str] = []
        def _flush_table():
            if not _table_lines:
                return
            rows = [r.strip().strip('|').split('|') for r in _table_lines]
            html_t = '<table style="border-collapse:collapse;width:100%;margin:0.5rem 0;font-size:0.85rem;">'
            for ri, row in enumerate(rows):
                if ri == 1 and all(c.strip().replace('-','') == '' for c in row):
                    continue  # Skip separator row
                tag = 'th' if ri == 0 else 'td'
                style = 'style="border:1px solid #334155;padding:6px 10px;text-align:left;"'
                html_t += '<tr>' + ''.join(f'<{tag} {style}>{c.strip()}</{tag}>' for c in row) + '</tr>'
            html_t += '</table>'
            _out_lines.append(html_t)
            _table_lines.clear()
        for line in safe.split('\n'):
            if line.strip().startswith('|') and '|' in line.strip()[1:]:
                _table_lines.append(line)
            else:
                _flush_table()
                _out_lines.append(line)
        _flush_table()
        safe = '\n'.join(_out_lines)
        # Newlines (but not inside tables/pre)
        safe = safe.replace('\n', '<br>\n')

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"""<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Report: {_esc(issue_id)}</title>
        <style>body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,sans-serif;padding:1rem 2rem;max-width:900px;margin:0 auto;line-height:1.6;}}
        h1,h2,h3{{color:#f8fafc;}} a{{color:#3b82f6;}} img{{display:block;margin:0.5rem 0;}}</style>
        </head><body>
        <a href="/" style="font-size:0.8rem;">← Dashboard</a>
        <h1>Verification: {_esc(issue_id)}</h1>
        <p style="color:#94a3b8;font-size:0.8rem;">File: {_esc(report_name or 'inline')}</p>
        <hr style="border-color:#334155;">
        {safe}
        </body></html>""".encode())

    def do_POST(self) -> None:
        if self.path == "/api/pause":
            self._update_system_state("Paused")
        elif self.path == "/api/resume":
            self._update_system_state("Running")
        else:
            self.send_error(404)

    def _serve_dashboard(self) -> None:
        state = read_state()
        html = render_dashboard(state)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_health(self) -> None:
        state = read_state()
        rl = state.get("rate_limits", {})
        health = {
            "status": "healthy",
            "system_state": state.get("system_state", "Unknown"),
            "last_poll": state.get("last_poll"),
            "active_workers": sum(
                1
                for w in state.get("workers", {}).values()
                if w.get("state") in ("Running", "Verifying", "InReview")
            ),
            "rate_limits": {
                "five_hour_pct": rl.get("five_hour_pct"),
                "seven_day_pct": rl.get("seven_day_pct"),
                "throttle_level": rl.get("throttle_level", "unknown"),
            },
            "self_monitor": {
                "last_run": state.get("self_monitor", {}).get("last_run"),
            },
            "toolchain_monitor": {
                "last_run": state.get("toolchain_monitor", {}).get("last_run"),
            },
        }
        self._serve_json(health)

    def _serve_metrics(self) -> None:
        state = read_state()
        self._serve_json(state.get("metrics_summary", {}))

    def _serve_json(self, data: dict) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _update_system_state(self, new_state: str) -> None:
        state = read_state()
        state["system_state"] = new_state
        write_state(state)
        self._serve_json({"ok": True, "system_state": new_state})


# -- Main -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Lacrimosa Dashboard HTTP Server")
    parser.add_argument("--port", type=int, default=1791, help="Port to listen on")
    parser.add_argument("--bind", default="127.0.0.1", help="Address to bind to")
    args = parser.parse_args()

    from http.server import ThreadingHTTPServer
    import socket

    class NoDNSServer(ThreadingHTTPServer):
        address_family = socket.AF_INET
        allow_reuse_address = True
        def server_bind(self):
            self.server_name = "lacrimosa-dashboard"
            self.server_port = self.server_address[1]
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(self.server_address)

    server = NoDNSServer((args.bind, args.port), LacrimosaDashboardHandler)
    print(f"Lacrimosa Dashboard running at http://{args.bind}:{args.port}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard")
        server.shutdown()


if __name__ == "__main__":
    main()
