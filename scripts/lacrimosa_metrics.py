"""Lacrimosa v2 metrics — per-task cost/token recording and daily summaries."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

METRICS_DIR = Path.home() / ".claude" / "lacrimosa" / "metrics"
METRICS_RETENTION_DAYS: int = 30


class ModelUsage(TypedDict, total=False):
    model_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    web_search_requests: int
    web_fetch_requests: int


class TaskMetrics(TypedDict, total=False):
    issue_id: str
    phase: str
    domain: str
    timestamp: str
    worker_type: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    total_tokens: int
    cost_usd: float | None
    duration_ms: int
    duration_api_ms: int
    num_turns: int
    model_usage: dict[str, ModelUsage]
    outcome: str
    pr_number: str | None
    review_iterations: int
    stop_reason: str
    bugs_linked: int
    reverted: bool
    specialist: str
    step: str


class DailySummary(TypedDict, total=False):
    date: str
    total_cost_usd: float
    cost_by_phase: dict[str, float]
    cost_by_domain: dict[str, float]
    cost_by_model: dict[str, float]
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    tasks_completed: int
    tasks_failed: int
    tasks_escalated: int
    phases_completed: dict[str, int]
    prs_merged: int
    prs_reverted: int
    bugs_linked_total: int
    average_review_iterations: float
    revert_rate: float
    average_duration_ms: float
    average_cost_per_task_usd: float
    average_tokens_per_task: float
    signals_processed: int
    signals_validated: int
    scoring_sessions_cost_usd: float
    sensor_sessions_cost_usd: float
    cost_by_specialist: dict[str, float]


def parse_session_output(
    stdout: str,
    issue_id: str,
    phase: str,
    domain: str,
) -> TaskMetrics:
    """Parse claude --print --output-format json output into TaskMetrics."""
    metrics: TaskMetrics = {
        "issue_id": issue_id,
        "phase": phase,
        "domain": domain,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "worker_type": "solo",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "total_tokens": 0,
        "cost_usd": None,
        "duration_ms": 0,
        "duration_api_ms": 0,
        "num_turns": 0,
        "model_usage": {},
        "outcome": "success",
        "pr_number": None,
        "review_iterations": 0,
        "stop_reason": "end_turn",
        "bugs_linked": 0,
        "reverted": False,
    }
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        metrics["outcome"] = "failed"
        return metrics

    usage = data.get("usage", {})
    metrics["input_tokens"] = usage.get("input_tokens", 0)
    metrics["output_tokens"] = usage.get("output_tokens", 0)
    metrics["cache_read_tokens"] = usage.get("cache_read_tokens", 0)
    metrics["cache_creation_tokens"] = usage.get("cache_creation_tokens", 0)
    metrics["total_tokens"] = metrics["input_tokens"] + metrics["output_tokens"]
    metrics["cost_usd"] = data.get("total_cost_usd")
    metrics["duration_ms"] = data.get("duration_ms", 0)
    metrics["duration_api_ms"] = data.get("duration_api_ms", 0)
    metrics["num_turns"] = data.get("num_turns", 0)
    metrics["stop_reason"] = data.get("stop_reason", "end_turn")

    if data.get("is_error"):
        metrics["outcome"] = "failed"

    for model_id, mu in data.get("modelUsage", {}).items():
        metrics["model_usage"][model_id] = {
            "model_id": model_id,
            "input_tokens": mu.get("inputTokens", 0),
            "output_tokens": mu.get("outputTokens", 0),
            "cache_read_tokens": mu.get("cacheReadTokens", 0),
            "cache_creation_tokens": mu.get("cacheCreationTokens", 0),
            "cost_usd": mu.get("costUsd", 0.0),
            "web_search_requests": mu.get("webSearchRequests", 0),
            "web_fetch_requests": mu.get("webFetchRequests", 0),
        }

    result_text = data.get("result", "")
    pr_match = re.search(r"(?:PR|pull request)\s*#?(\d+)", result_text, re.I)
    if pr_match:
        metrics["pr_number"] = f"#{pr_match.group(1)}"

    return metrics


def record_task_metrics(metrics: TaskMetrics, metrics_dir: Path | None = None) -> Path:
    """Write task metrics to date-partitioned directory."""
    base = metrics_dir or METRICS_DIR
    day_dir = base / datetime.now().strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"task-{metrics['issue_id']}-{metrics['phase']}.json"
    path.write_text(json.dumps(metrics, indent=2, default=str))
    os.chmod(path, 0o600)
    return path


def update_bug_linkage(
    issue_id: str,
    bugs_found: int,
    reverted: bool,
    metrics_dir: Path | None = None,
) -> bool:
    """Update a task's metrics file with bug linkage data."""
    base = metrics_dir or METRICS_DIR
    for day_dir in sorted(base.iterdir(), reverse=True) if base.exists() else []:
        if not day_dir.is_dir():
            continue
        for f in day_dir.glob(f"task-{issue_id}-*.json"):
            try:
                data = json.loads(f.read_text())
                data["bugs_linked"] = bugs_found
                data["reverted"] = reverted
                f.write_text(json.dumps(data, indent=2, default=str))
                return True
            except (json.JSONDecodeError, OSError):
                continue
    return False


def compute_daily_summary(
    date: str | None = None,
    metrics_dir: Path | None = None,
) -> DailySummary:
    """Aggregate all task metrics for a date into a summary."""
    base = metrics_dir or METRICS_DIR
    date = date or datetime.now().strftime("%Y-%m-%d")
    day_dir = base / date

    summary: DailySummary = {
        "date": date,
        "total_cost_usd": 0.0,
        "cost_by_phase": {},
        "cost_by_domain": {},
        "cost_by_model": {},
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
        "tasks_completed": 0,
        "tasks_failed": 0,
        "tasks_escalated": 0,
        "phases_completed": {},
        "prs_merged": 0,
        "prs_reverted": 0,
        "bugs_linked_total": 0,
        "average_review_iterations": 0.0,
        "revert_rate": 0.0,
        "average_duration_ms": 0.0,
        "average_cost_per_task_usd": 0.0,
        "average_tokens_per_task": 0.0,
        "signals_processed": 0,
        "signals_validated": 0,
        "scoring_sessions_cost_usd": 0.0,
        "sensor_sessions_cost_usd": 0.0,
        "cost_by_specialist": {},
    }
    if not day_dir.exists():
        return summary

    tasks: list[dict] = []
    for f in day_dir.glob("task-*.json"):
        try:
            tasks.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue

    total_duration = 0
    total_review_iters = 0
    review_count = 0

    for t in tasks:
        cost = t.get("cost_usd") or 0.0
        summary["total_cost_usd"] += cost
        summary["total_input_tokens"] += t.get("input_tokens", 0)
        summary["total_output_tokens"] += t.get("output_tokens", 0)
        summary["total_cache_read_tokens"] += t.get("cache_read_tokens", 0)
        summary["total_cache_creation_tokens"] += t.get("cache_creation_tokens", 0)
        total_duration += t.get("duration_ms", 0)

        phase = t.get("phase", "unknown")
        summary["cost_by_phase"][phase] = summary["cost_by_phase"].get(phase, 0.0) + cost
        domain = t.get("domain", "unknown")
        summary["cost_by_domain"][domain] = summary["cost_by_domain"].get(domain, 0.0) + cost
        specialist = t.get("specialist", "unknown")
        summary["cost_by_specialist"][specialist] = (
            summary["cost_by_specialist"].get(specialist, 0.0) + cost
        )

        for mu in t.get("model_usage", {}).values():
            mid = mu.get("model_id", "unknown")
            summary["cost_by_model"][mid] = summary["cost_by_model"].get(mid, 0.0) + mu.get(
                "cost_usd", 0.0
            )

        outcome = t.get("outcome", "success")
        if outcome == "success":
            summary["tasks_completed"] += 1
        elif outcome == "escalated":
            summary["tasks_escalated"] += 1
        else:
            summary["tasks_failed"] += 1

        summary["phases_completed"][phase] = summary["phases_completed"].get(phase, 0) + 1
        if t.get("pr_number"):
            summary["prs_merged"] += 1
        if t.get("reverted"):
            summary["prs_reverted"] += 1
        summary["bugs_linked_total"] += t.get("bugs_linked", 0)

        ri = t.get("review_iterations", 0)
        if ri > 0:
            total_review_iters += ri
            review_count += 1

    n = len(tasks) or 1
    summary["average_duration_ms"] = total_duration / n
    summary["average_cost_per_task_usd"] = summary["total_cost_usd"] / n
    summary["average_tokens_per_task"] = (
        summary["total_input_tokens"] + summary["total_output_tokens"]
    ) / n
    summary["average_review_iterations"] = (
        total_review_iters / review_count if review_count else 0.0
    )
    merged = summary["prs_merged"] or 1
    summary["revert_rate"] = summary["prs_reverted"] / merged

    summary_path = day_dir / "daily-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    return summary


def get_daily_summary(
    date: str | None = None, metrics_dir: Path | None = None
) -> DailySummary | None:
    """Read cached daily summary. Returns None if not computed yet."""
    base = metrics_dir or METRICS_DIR
    path = base / (date or datetime.now().strftime("%Y-%m-%d")) / "daily-summary.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_trend_data(days: int = 7, metrics_dir: Path | None = None) -> list[DailySummary]:
    """Get daily summaries for last N days."""
    result: list[DailySummary] = []
    for i in range(days):
        s = get_daily_summary(
            (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"), metrics_dir
        )
        if s:
            result.append(s)
    result.reverse()
    return result


def rotate_metrics(metrics_dir: Path | None = None, retention_days: int = 30) -> int:
    """Remove metrics directories older than retention_days."""
    base = metrics_dir or METRICS_DIR
    if not base.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for day_dir in list(base.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            if datetime.strptime(day_dir.name, "%Y-%m-%d") < cutoff:
                shutil.rmtree(day_dir)
                removed += 1
        except ValueError:
            continue
    return removed
