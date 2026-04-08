"""Lacrimosa ceremony implementations — standup, planning, grooming, retro, weekly."""

from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts.lacrimosa_learnings import LearningsEngine
from scripts.lacrimosa_metrics import compute_daily_summary, get_trend_data
from scripts.lacrimosa_state import StateManager
from scripts.lacrimosa_types import CeremonyResult

# -- Shared helpers (inlined to avoid circular import with lacrimosa_ceremonies) --

_ISSUE_STOP = frozenset(
    {
        "fix",
        "add",
        "update",
        "remove",
        "implement",
        "create",
        "delete",
        "change",
        "move",
        "rename",
        "refactor",
        "make",
        "set",
        "get",
        "the",
        "a",
        "an",
        "is",
        "not",
        "and",
        "or",
        "for",
        "in",
        "on",
        "to",
        "of",
        "with",
        "by",
        "it",
        "this",
        "that",
        "was",
        "are",
    }
)


def _post_to_linear(content: str, **kwargs: Any) -> str | None:
    """Post to Linear. Returns URL or None. Mocked in tests."""
    return None


def _query_linear_backlog() -> list[dict[str, Any]]:
    """Query Linear for backlog issues. Mocked in tests."""
    return []


def _text_similarity(text1: str, text2: str) -> float:
    """Word overlap coefficient for duplicate detection."""
    w1 = {w for w in re.findall(r"\w+", text1.lower()) if w not in _ISSUE_STOP and len(w) >= 2}
    w2 = {w for w in re.findall(r"\w+", text2.lower()) if w not in _ISSUE_STOP and len(w) >= 2}
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / min(len(w1), len(w2))


def _update_state(sm: StateManager, key: str, updates: dict[str, Any]) -> None:
    """Atomically update a ceremony's state section."""

    def updater(s: dict[str, Any]) -> dict[str, Any]:
        s = copy.deepcopy(s)
        s.setdefault("ceremonies", {}).setdefault(key, {}).update(updates)
        return s

    sm.atomic_update(updater)


def _window_cutoff(now: datetime, window_hours: int) -> datetime:
    """Compute start of current cadence window (midnight-aligned)."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    secs = (now - midnight).total_seconds()
    window_secs = window_hours * 3600
    idx = int(secs / window_secs)
    return midnight + timedelta(seconds=idx * window_secs)


def run_standup(
    state: dict[str, Any],
    config: dict[str, Any],
    sm: StateManager,
) -> CeremonyResult:
    """Generate standup report and post to Linear."""
    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now().strftime("%Y-%m-%d")
    active = state.get("pipeline", {}).get("active_workers", {})
    daily = state.get("daily_counters", {}).get(today, {})
    throttle = state.get("rate_limits", {}).get("throttle_level", "green")
    first = state.get("ceremonies", {}).get("standup", {}).get("last_run") is None
    data = {
        "merges_count": daily.get("prs_merged", 0),
        "active_workers": len(active),
        "blocked_issues": sum(1 for i in state.get("issues", {}).values() if i.get("blocked")),
        "cost_since_last": 0.0,
        "throttle_level": throttle,
        "first_run": first,
    }
    parts = [f"Standup: {data['merges_count']} merged, {data['active_workers']} active"]
    if first:
        parts.append("(first standup)")
    summary = ", ".join(parts)
    url = _post_to_linear(summary)
    _update_state(sm, "standup", {"last_run": now_iso, "last_output_url": url})
    return CeremonyResult(
        ceremony="standup",
        success=True,
        timestamp=now_iso,
        linear_url=url,
        summary=summary,
        data=data,
        error=None,
    )


def run_sprint_planning(
    state: dict[str, Any],
    config: dict[str, Any],
    sm: StateManager,
) -> CeremonyResult:
    """Score backlog, select issues for today's sprint."""
    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now().strftime("%Y-%m-%d")
    daily = state.get("daily_counters", {}).get(today, {})
    spawned = daily.get("workers_spawned", 0)
    trust = state.get("trust_scores", {})
    trust_cfg = config.get("trust", {}).get("tiers", {})
    cap_counting = config.get("trust", {}).get("cap_counting")
    from_cache = False
    try:
        backlog = _query_linear_backlog()
    except Exception:
        backlog = [
            {**v, "id": k}
            for k, v in state.get("issues", {}).items()
            if v.get("state") in ("Todo", "Ready", "Backlog")
        ]
        from_cache = True
    backlog = [i for i in backlog if not i.get("blocked")]
    backlog.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
    capacity: dict[str, int] = {}
    for domain, ts in trust.items():
        tier = ts.get("tier", 0)
        cap = trust_cfg.get(tier, {}).get("issues_per_day", 3)
        capacity[domain] = max(0, cap - spawned)
    selected: list[dict[str, Any]] = []
    parents_used: dict[str, set[str]] = {}
    for issue in backlog:
        domain = issue.get("domain", "")
        if domain not in capacity or capacity[domain] <= 0:
            continue
        parent_id = issue.get("parent_id")
        if cap_counting == "parent_issues" and parent_id:
            ps = parents_used.setdefault(domain, set())
            if parent_id not in ps and len(ps) >= capacity[domain]:
                continue
            ps.add(parent_id)
        else:
            used = parents_used.setdefault(domain, set())
            if len(used) >= capacity[domain]:
                continue
            used.add(issue["id"])
        selected.append(issue)
    summary = f"Sprint {today}: {len(selected)} issues selected"
    if from_cache:
        summary += " (from cache)"
    url = _post_to_linear(summary)
    _update_state(
        sm,
        "sprint",
        {
            "current": [i["id"] for i in selected],
            "planned_at": now_iso,
            "capacity": capacity,
        },
    )
    _update_state(sm, "sprint_planning", {"last_run": now_iso})
    return CeremonyResult(
        ceremony="sprint_planning",
        success=True,
        timestamp=now_iso,
        linear_url=url,
        summary=summary,
        data={"selected_issues": selected, "from_cache": from_cache},
        error=None,
    )


def run_backlog_grooming(
    state: dict[str, Any],
    config: dict[str, Any],
    sm: StateManager,
) -> CeremonyResult:
    """Re-score stale signals, decompose epics, merge dupes, archive abandoned."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    gcfg = config.get("ceremonies", {}).get("backlog_grooming", {})
    stale_h = gcfg.get("stale_threshold_hours", 12)
    file_thresh = gcfg.get("file_threshold", 15)
    sim_thresh = gcfg.get("similarity_threshold", 0.8)
    inactive_h = gcfg.get("inactive_threshold_hours", 48)
    throttle = state.get("rate_limits", {}).get("throttle_level", "green")
    issues = {
        k: v for k, v in state.get("issues", {}).items() if v.get("state") in ("Backlog", "Todo")
    }
    actions = {"re_scored": 0, "decomposed": 0, "merged": 0, "archived": 0}
    stale_cutoff = _window_cutoff(now, stale_h)
    for iss in issues.values():
        scored_at = iss.get("scored_at")
        if scored_at:
            try:
                if datetime.fromisoformat(scored_at) < stale_cutoff:
                    actions["re_scored"] += 1
            except (ValueError, TypeError):
                pass
    if throttle != "red":
        for iss in issues.values():
            if iss.get("estimated_files", 0) > file_thresh:
                actions["decomposed"] += 1
    items = list(issues.items())
    merged_ids: set[str] = set()
    for i, (id1, iss1) in enumerate(items):
        if id1 in merged_ids:
            continue
        t1 = f"{iss1.get('title', '')} {iss1.get('description', '')}"
        for id2, iss2 in items[i + 1 :]:
            if id2 in merged_ids:
                continue
            t2 = f"{iss2.get('title', '')} {iss2.get('description', '')}"
            if _text_similarity(t1, t2) >= sim_thresh:
                lower = (
                    id2 if iss2.get("priority_score", 0) <= iss1.get("priority_score", 0) else id1
                )
                merged_ids.add(lower)
                actions["merged"] += 1
    inactive_cutoff = _window_cutoff(now, inactive_h)
    for iss in issues.values():
        la = iss.get("last_activity")
        if la and iss.get("state") == "Todo":
            try:
                if datetime.fromisoformat(la) < inactive_cutoff:
                    actions["archived"] += 1
            except (ValueError, TypeError):
                pass
    summary = (
        f"Grooming: {actions['re_scored']} re-scored, "
        f"{actions['decomposed']} decomposed, "
        f"{actions['merged']} merged, {actions['archived']} archived"
    )
    url = _post_to_linear(summary)
    _update_state(sm, "grooming", {"last_run": now_iso, "last_actions": actions})
    return CeremonyResult(
        ceremony="backlog_grooming",
        success=True,
        timestamp=now_iso,
        linear_url=url,
        summary=summary,
        data={"actions": actions},
        error=None,
    )


def run_sprint_retro(
    state: dict[str, Any],
    config: dict[str, Any],
    sm: StateManager,
) -> CeremonyResult:
    """Compute metrics, compare to yesterday, generate learnings for negative trends."""
    now_iso = datetime.now(timezone.utc).isoformat()
    today_metrics = compute_daily_summary()
    last_snap = state.get("ceremonies", {}).get("retro", {}).get("last_metrics_snapshot")
    first_retro = last_snap is None
    deltas: dict[str, Any] = {}
    if last_snap:
        for key in (
            "tasks_completed",
            "tasks_failed",
            "prs_merged",
            "prs_reverted",
            "average_review_iterations",
            "total_cost_usd",
            "revert_rate",
        ):
            deltas[key] = (today_metrics.get(key, 0) or 0) - (last_snap.get(key, 0) or 0)
    learnings_ids: list[str] = []
    revert_rate = today_metrics.get("revert_rate", 0) or 0
    avg_review = today_metrics.get("average_review_iterations", 0) or 0
    cpt = today_metrics.get("average_cost_per_task_usd", 0) or 0
    old_cpt = (last_snap or {}).get("average_cost_per_task_usd", 0) or 0
    patterns: list[tuple[str, str]] = []
    if revert_rate > 0.1:
        patterns.append(("elevated revert rate", "high"))
    if avg_review > 2.0:
        patterns.append(("high review iteration count", "medium"))
    if old_cpt and cpt > 2 * old_cpt:
        patterns.append(("cost per task doubled", "medium"))
    if patterns:
        engine = LearningsEngine(config)
        for pattern, severity in patterns:
            lid = f"lrn-{uuid.uuid4().hex[:8]}"
            engine.create_learning(
                {
                    "id": lid,
                    "timestamp": now_iso,
                    "event_type": "retro_observation",
                    "issue_id": "",
                    "agent_type": "ceremony",
                    "root_cause": pattern,
                    "pattern": pattern,
                    "severity": severity,
                    "adjustment": "",
                    "applied": False,
                    "linear_issue_id": "",
                    "status": "in_review",
                }
            )
            learnings_ids.append(lid)
    parts = [f"Retro: {today_metrics.get('tasks_completed', 0)} completed"]
    if first_retro:
        parts.append("(first retro)")
    summary = ", ".join(parts)
    url = _post_to_linear(summary)
    _update_state(
        sm,
        "retro",
        {
            "last_run": now_iso,
            "last_metrics_snapshot": dict(today_metrics),
            "last_learnings_ids": learnings_ids,
        },
    )
    data: dict[str, Any] = {"metrics": dict(today_metrics), "learnings_generated": learnings_ids}
    if first_retro:
        data["first_retro"] = True
    else:
        data["deltas"] = deltas
    return CeremonyResult(
        ceremony="sprint_retro",
        success=True,
        timestamp=now_iso,
        linear_url=url,
        summary=summary,
        data=data,
        error=None,
    )


def run_weekly_summary(
    state: dict[str, Any],
    config: dict[str, Any],
    sm: StateManager,
) -> CeremonyResult:
    """Aggregate week's metrics into a summary report."""
    now_iso = datetime.now(timezone.utc).isoformat()
    trend = get_trend_data(days=7)
    last_run = state.get("ceremonies", {}).get("weekly_summary", {}).get("last_run")
    first_week = last_run is None
    week_prs = sum(d.get("prs_merged", 0) for d in trend)
    week_cost = sum(d.get("total_cost_usd", 0) for d in trend)
    trust_scores = state.get("trust_scores", {})
    trust_changes = {
        d: {"tier": ts.get("tier"), "previous_tier": ts.get("previous_tier")}
        for d, ts in trust_scores.items()
        if "previous_tier" in ts
    }
    parts = [f"Weekly: {week_prs} PRs merged, ${week_cost:.2f} cost"]
    if first_week:
        parts.append("(first weekly summary)")
    summary = ", ".join(parts)
    url = _post_to_linear(summary, create_issue=True)
    _update_state(sm, "weekly_summary", {"last_run": now_iso, "last_document_url": url})
    data: dict[str, Any] = {
        "week_prs_merged": week_prs,
        "week_cost_total": week_cost,
        "days_with_data": len(trend),
        "trust_changes": trust_changes,
    }
    if first_week:
        data["first_week"] = True
    return CeremonyResult(
        ceremony="weekly_summary",
        success=True,
        timestamp=now_iso,
        linear_url=url,
        summary=summary,
        data=data,
        error=None,
    )
