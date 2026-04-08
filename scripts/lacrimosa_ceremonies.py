"""Lacrimosa v2 ceremonies — autonomous scrum ceremonies.

Schedules and runs standup, sprint planning, backlog grooming,
sprint retro, and weekly summary ceremonies. Integrates with
existing state, metrics, learnings, and Linear posting modules.
"""
from __future__ import annotations

import copy
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts.lacrimosa_state import StateManager
from scripts.lacrimosa_types import CeremonyResult

logger = logging.getLogger(__name__)

_CEREMONY_ORDER = (
    "standup",
    "sprint_planning",
    "backlog_grooming",
    "sprint_retro",
    "weekly_summary",
)
_STATE_KEY = {
    "standup": "standup",
    "sprint_planning": "sprint_planning",
    "backlog_grooming": "grooming",
    "sprint_retro": "retro",
    "weekly_summary": "weekly_summary",
}
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
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


# -- Scheduling helpers -------------------------------------------------------


def is_daily_ceremony_due(
    ceremony_state: dict[str, Any],
    target_time: str,
    now: datetime | None = None,
) -> bool:
    """Check if a daily ceremony is due (past target HH:MM, not yet run today)."""
    now = now or datetime.now(timezone.utc)
    hour, minute = int(target_time[:2]), int(target_time[3:])
    target_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target_dt:
        return False
    last_run = ceremony_state.get("last_run")
    if last_run is None:
        return True
    try:
        return datetime.fromisoformat(last_run) < target_dt
    except (ValueError, TypeError):
        return True


def is_weekly_ceremony_due(
    ceremony_state: dict[str, Any],
    target_day: str,
    target_time: str,
    now: datetime | None = None,
) -> bool:
    """Check if a weekly ceremony is due (correct weekday, past target time)."""
    now = now or datetime.now(timezone.utc)
    if now.weekday() != _WEEKDAYS.get(target_day.lower(), -1):
        return False
    hour, minute = int(target_time[:2]), int(target_time[3:])
    target_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target_dt:
        return False
    last_run = ceremony_state.get("last_run")
    if last_run is None:
        return True
    try:
        return datetime.fromisoformat(last_run) < target_dt
    except (ValueError, TypeError):
        return True


# -- Linear stubs (production: dispatch Claude CLI) ----------------------------


def _post_to_linear(content: str, **kwargs: Any) -> str | None:
    """Post to Linear. Returns URL or None. Mocked in tests."""
    return None


def _query_linear_backlog() -> list[dict[str, Any]]:
    """Query Linear for backlog issues. Mocked in tests."""
    return []


# -- Text similarity -----------------------------------------------------------


def _text_similarity(text1: str, text2: str) -> float:
    """Word overlap coefficient for duplicate detection, filtering stop words."""
    w1 = {w for w in re.findall(r"\w+", text1.lower()) if w not in _ISSUE_STOP and len(w) >= 2}
    w2 = {w for w in re.findall(r"\w+", text2.lower()) if w not in _ISSUE_STOP and len(w) >= 2}
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / min(len(w1), len(w2))


# -- CeremonyScheduler --------------------------------------------------------


class CeremonyScheduler:
    """Schedules and dispatches ceremonies based on config and state."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._cc = config.get("ceremonies", {})

    def is_due(
        self,
        name: str,
        ceremony_state: dict[str, Any],
        now: datetime | None = None,
    ) -> bool:
        """Check if a specific ceremony is due to run."""
        if not self._cc.get("enabled", True):
            return False
        cfg = self._cc.get(name, {})
        if not cfg.get("enabled", True):
            return False
        now = now or datetime.now(timezone.utc)
        if name in ("standup", "backlog_grooming"):
            hours = cfg.get("cadence_hours", 4)
            lr = ceremony_state.get("last_run")
            if lr is None:
                return True
            try:
                return now >= datetime.fromisoformat(lr) + timedelta(hours=hours)
            except (ValueError, TypeError):
                return True
        if name in ("sprint_planning", "sprint_retro"):
            return is_daily_ceremony_due(ceremony_state, cfg.get("time", "08:00"), now)
        if name == "weekly_summary":
            return is_weekly_ceremony_due(
                ceremony_state, cfg.get("day", "friday"), cfg.get("time", "22:30"), now
            )
        return False

    def check_all_due(
        self,
        state: dict[str, Any],
        now: datetime | None = None,
    ) -> list[str]:
        """Return list of ceremony names that are currently due, in order."""
        if not self._cc.get("enabled", True):
            return []
        cers = state.get("ceremonies", {})
        return [
            n for n in _CEREMONY_ORDER if self.is_due(n, cers.get(_STATE_KEY.get(n, n), {}), now)
        ]

    def run(
        self,
        name: str,
        state: dict[str, Any],
        state_manager: StateManager,
    ) -> CeremonyResult:
        """Execute a ceremony and update state atomically."""
        runners = _get_runners()
        try:
            return runners[name](state, self._config, state_manager)
        except Exception as exc:
            return CeremonyResult(
                ceremony=name,
                success=False,
                timestamp=datetime.now(timezone.utc).isoformat(),
                linear_url=None,
                summary=f"{name} failed: {exc}",
                data={},
                error=str(exc),
            )


# -- State helper --------------------------------------------------------------


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


def _get_runners() -> dict[str, Any]:
    """Lazy import to avoid circular dependency."""
    from scripts import lacrimosa_ceremony_runners as r

    return {
        "standup": r.run_standup,
        "sprint_planning": r.run_sprint_planning,
        "backlog_grooming": r.run_backlog_grooming,
        "sprint_retro": r.run_sprint_retro,
        "weekly_summary": r.run_weekly_summary,
    }


# -- Top-level entry point ----------------------------------------------------


def check_and_run_ceremonies(
    state: dict[str, Any],
    config: dict[str, Any],
    state_manager: StateManager,
) -> list[CeremonyResult]:
    """Check all due ceremonies and run them sequentially."""
    scheduler = CeremonyScheduler(config)
    due = scheduler.check_all_due(state)
    results: list[CeremonyResult] = []
    for name in due:
        result = scheduler.run(name, state, state_manager)
        results.append(result)
        if result.success:
            state = state_manager.read()
    return results
