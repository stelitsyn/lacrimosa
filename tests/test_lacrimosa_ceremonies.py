"""TDD tests for Lacrimosa ceremonies — scheduling, standup, planning, state migration.
Imports from scripts.lacrimosa_ceremonies (not yet implemented — tests FAIL).
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest

from scripts.lacrimosa_ceremonies import (
    CeremonyScheduler,
    is_daily_ceremony_due,
    is_weekly_ceremony_due,
)
from scripts.lacrimosa_state import StateManager
from scripts.lacrimosa_state_json_backup import migrate_state

_FRI = datetime(2026, 3, 20, tzinfo=timezone.utc)  # a Friday
_THU = datetime(2026, 3, 19, tzinfo=timezone.utc)


def _at(h: int, m: int = 0, base: datetime = _FRI) -> datetime:
    return base.replace(hour=h, minute=m, second=0, microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _ago(now: datetime, hours: float) -> str:
    return _iso(now - timedelta(hours=hours))


def _v4_ceremonies() -> dict[str, Any]:
    return {
        "standup": {"last_run": None, "last_output_url": None},
        "sprint": {"current": [], "planned_at": None, "capacity": {}},
        "sprint_planning": {"last_run": None},
        "grooming": {
            "last_run": None,
            "last_actions": {"re_scored": 0, "decomposed": 0, "merged": 0, "archived": 0},
        },
        "retro": {"last_run": None, "last_metrics_snapshot": None, "last_learnings_ids": []},
        "weekly_summary": {"last_run": None, "last_document_url": None},
    }


@pytest.fixture
def cfg() -> dict[str, Any]:
    return {
        "conductor": {},
        "lifecycle": {"routing": {}},
        "trust": {
            "tiers": {0: {"issues_per_day": 3}, 1: {"issues_per_day": 5}},
            "cap_counting": "parent_issues",
        },
        "rate_limits": {"green_threshold": 50, "red_threshold": 90},
        "discovery": {},
        "ceremonies": {
            "enabled": True,
            "standup": {"enabled": True, "cadence_hours": 4},
            "sprint_planning": {"enabled": True, "time": "08:00"},
            "backlog_grooming": {
                "enabled": True,
                "cadence_hours": 12,
                "stale_threshold_hours": 12,
                "file_threshold": 15,
                "similarity_threshold": 0.8,
                "inactive_threshold_hours": 48,
            },
            "sprint_retro": {"enabled": True, "time": "22:00"},
            "weekly_summary": {"enabled": True, "day": "friday", "time": "22:30"},
        },
    }


@pytest.fixture
def st() -> dict[str, Any]:
    return {
        "version": 4,
        "system_state": "Running",
        "trust_scores": {"Platform": {"tier": 0}, "Marketing": {"tier": 1}},
        "issues": {},
        "daily_counters": {_TODAY: {"workers_spawned": 0, "prs_merged": 0}},
        "pipeline": {"active_workers": {}},
        "rate_limits": {"throttle_level": "green"},
        "ceremonies": _v4_ceremonies(),
    }


@pytest.fixture
def sm(tmp_path) -> StateManager:
    return StateManager(tmp_path / "state.json")


class TestIsDailyCeremonyDue:
    def test_due_past_target_never_run(self):
        assert is_daily_ceremony_due({"last_run": None}, "08:00", now=_at(8, 1)) is True

    def test_due_past_target_ran_yesterday(self):
        yesterday = _iso(_at(8, 0, base=_THU))
        assert is_daily_ceremony_due({"last_run": yesterday}, "08:00", now=_at(8, 1)) is True

    def test_not_due_before_target(self):
        assert is_daily_ceremony_due({"last_run": None}, "08:00", now=_at(7, 59)) is False

    def test_not_due_already_ran_today(self):
        assert (
            is_daily_ceremony_due({"last_run": _iso(_at(8, 5))}, "08:00", now=_at(12, 0)) is False
        )

    def test_due_exactly_at_target(self):
        assert is_daily_ceremony_due({"last_run": None}, "08:00", now=_at(8, 0)) is True

    def test_one_second_before_not_due(self):
        almost = _at(7, 59).replace(second=59)
        assert is_daily_ceremony_due({"last_run": None}, "08:00", now=almost) is False


class TestIsWeeklyCeremonyDue:
    def test_due_correct_day_past_time(self):
        assert (
            is_weekly_ceremony_due({"last_run": None}, "friday", "22:30", now=_at(22, 31)) is True
        )

    def test_not_due_wrong_day(self):
        assert (
            is_weekly_ceremony_due(
                {"last_run": None}, "friday", "22:30", now=_at(22, 31, base=_THU)
            )
            is False
        )

    def test_not_due_before_time_correct_day(self):
        assert (
            is_weekly_ceremony_due({"last_run": None}, "friday", "22:30", now=_at(22, 29)) is False
        )

    def test_not_due_already_ran_this_week(self):
        assert (
            is_weekly_ceremony_due(
                {"last_run": _iso(_at(22, 35))}, "friday", "22:30", now=_at(23, 0)
            )
            is False
        )

    def test_due_first_ever(self):
        assert (
            is_weekly_ceremony_due({"last_run": None}, "friday", "22:30", now=_at(22, 30)) is True
        )

    def test_due_ran_last_week(self):
        last_fri = _iso(_at(22, 35, base=datetime(2026, 3, 13, tzinfo=timezone.utc)))
        assert (
            is_weekly_ceremony_due({"last_run": last_fri}, "friday", "22:30", now=_at(22, 31))
            is True
        )


class TestCeremonySchedulerIsDue:
    def test_standup_due_after_4h(self, cfg, st):
        now = _at(12, 1)
        st["ceremonies"]["standup"]["last_run"] = _ago(now, 4.1)
        assert (
            CeremonyScheduler(cfg).is_due("standup", st["ceremonies"]["standup"], now=now) is True
        )

    def test_standup_not_due_before_4h(self, cfg, st):
        now = _at(12, 0)
        st["ceremonies"]["standup"]["last_run"] = _ago(now, 3.9)
        assert (
            CeremonyScheduler(cfg).is_due("standup", st["ceremonies"]["standup"], now=now) is False
        )

    def test_standup_due_never_run(self, cfg, st):
        assert (
            CeremonyScheduler(cfg).is_due("standup", st["ceremonies"]["standup"], now=_at(12, 0))
            is True
        )

    def test_grooming_due_after_12h(self, cfg, st):
        now = _at(20, 0)
        st["ceremonies"]["grooming"]["last_run"] = _ago(now, 12.1)
        assert (
            CeremonyScheduler(cfg).is_due("backlog_grooming", st["ceremonies"]["grooming"], now=now)
            is True
        )

    def test_daily_planning(self, cfg, st):
        assert (
            CeremonyScheduler(cfg).is_due(
                "sprint_planning", st["ceremonies"]["sprint_planning"], now=_at(8, 1)
            )
            is True
        )

    def test_weekly_summary(self, cfg, st):
        assert (
            CeremonyScheduler(cfg).is_due(
                "weekly_summary", st["ceremonies"]["weekly_summary"], now=_at(22, 31)
            )
            is True
        )

    def test_disabled_ceremony(self, cfg, st):
        cfg["ceremonies"]["standup"]["enabled"] = False
        assert (
            CeremonyScheduler(cfg).is_due("standup", st["ceremonies"]["standup"], now=_at(12, 0))
            is False
        )

    def test_master_switch_off(self, cfg, st):
        cfg["ceremonies"]["enabled"] = False
        assert (
            CeremonyScheduler(cfg).is_due("standup", st["ceremonies"]["standup"], now=_at(12, 0))
            is False
        )


class TestCheckAllDue:
    def test_multiple_due_correct_order(self, cfg, st):
        due = CeremonyScheduler(cfg).check_all_due(st, now=_at(22, 31))
        assert "standup" in due and "sprint_retro" in due and "weekly_summary" in due
        idx = {n: due.index(n) for n in ("standup", "sprint_retro", "weekly_summary")}
        assert idx["standup"] < idx["sprint_retro"] < idx["weekly_summary"]

    def test_none_due(self, cfg, st):
        now = _at(7, 0)
        for key in st["ceremonies"]:
            sub = st["ceremonies"][key]
            if isinstance(sub, dict) and "last_run" in sub:
                sub["last_run"] = _iso(now - timedelta(minutes=5))
        assert CeremonyScheduler(cfg).check_all_due(st, now=now) == []

    def test_master_disabled(self, cfg, st):
        cfg["ceremonies"]["enabled"] = False
        assert CeremonyScheduler(cfg).check_all_due(st, now=_at(22, 31)) == []


_ML = "scripts.lacrimosa_ceremony_runners._post_to_linear"
_MB = "scripts.lacrimosa_ceremony_runners._query_linear_backlog"
_TODAY = datetime.now().strftime("%Y-%m-%d")


class TestStandup:
    @patch(_ML, return_value="https://linear.app/c/1")
    def test_normal(self, mock_post, cfg, st, sm):
        st["ceremonies"]["standup"]["last_run"] = _iso(_at(8, 0))
        st["pipeline"]["active_workers"] = {"TST-64": {"domain": "Platform"}}
        st["daily_counters"][_TODAY]["prs_merged"] = 3
        result = CeremonyScheduler(cfg).run("standup", st, sm)
        assert result.success and result.data["merges_count"] == 3
        assert result.data["active_workers"] == 1
        assert "blocked_issues" in result.data and "cost_since_last" in result.data
        mock_post.assert_called_once()

    @patch(_ML, return_value="https://linear.app/c/2")
    def test_first_ever(self, mock_post, cfg, st, sm):
        result = CeremonyScheduler(cfg).run("standup", st, sm)
        assert result.success
        assert result.data.get("first_run") is True or "first" in result.summary.lower()

    @patch(_ML, return_value="https://linear.app/c/3")
    def test_zero_activity(self, mock_post, cfg, st, sm):
        st["ceremonies"]["standup"]["last_run"] = _ago(_at(12, 0), 4.5)
        result = CeremonyScheduler(cfg).run("standup", st, sm)
        assert result.data["merges_count"] == 0 and result.data["active_workers"] == 0

    @patch(_ML, return_value="https://linear.app/c/4")
    def test_rate_limit_red(self, mock_post, cfg, st, sm):
        st["rate_limits"]["throttle_level"] = "red"
        result = CeremonyScheduler(cfg).run("standup", st, sm)
        assert result.success and result.data["throttle_level"] == "red"


class TestSprintPlanning:
    @patch(_ML, return_value="https://linear.app/c/10")
    @patch(_MB)
    def test_selects_by_priority(self, mock_bl, mock_post, cfg, st, sm):
        mock_bl.return_value = [
            {"id": "TST-70", "priority_score": 7, "domain": "Marketing", "state": "Todo"},
            {"id": "TST-64", "priority_score": 4, "domain": "Platform", "state": "Todo"},
            {
                "id": "TST-21",
                "priority_score": 4,
                "domain": "Platform",
                "state": "Todo",
                "blocked": True,
            },
        ]
        result = CeremonyScheduler(cfg).run("sprint_planning", st, sm)
        ids = [i["id"] for i in result.data["selected_issues"]]
        assert "TST-70" in ids and "TST-64" in ids and "TST-21" not in ids

    @patch(_ML, return_value="https://linear.app/c/11")
    @patch(_MB)
    def test_respects_daily_cap(self, mock_bl, mock_post, cfg, st, sm):
        st["daily_counters"][_TODAY]["workers_spawned"] = 3
        mock_bl.return_value = [
            {"id": "TST-10", "priority_score": 8, "domain": "Platform", "state": "Todo"},
        ]
        result = CeremonyScheduler(cfg).run("sprint_planning", st, sm)
        platform = [
            i for i in result.data["selected_issues"] if i.get("domain") == "Platform"
        ]
        assert platform == []

    @patch(_ML, return_value="https://linear.app/c/12")
    @patch(_MB, return_value=[])
    def test_empty_backlog(self, mock_bl, mock_post, cfg, st, sm):
        result = CeremonyScheduler(cfg).run("sprint_planning", st, sm)
        assert result.success and result.data["selected_issues"] == []

    @patch(_ML, return_value="https://linear.app/c/13")
    @patch(_MB)
    def test_parent_issue_cap_counting(self, mock_bl, mock_post, cfg, st, sm):
        mock_bl.return_value = [
            {
                "id": f"TST-6{i}",
                "priority_score": 5,
                "domain": "Platform",
                "state": "Todo",
                "parent_id": "TST-22",
            }
            for i in range(1, 5)
        ]
        result = CeremonyScheduler(cfg).run("sprint_planning", st, sm)
        assert len(result.data["selected_issues"]) == 4  # all 4 count as 1 toward cap

    @patch(_ML, return_value="https://linear.app/c/14")
    @patch(_MB)
    def test_first_ever_sprint(self, mock_bl, mock_post, cfg, st, sm):
        st["daily_counters"] = {}  # no counters at all
        mock_bl.return_value = [
            {"id": "TST-50", "priority_score": 5, "domain": "Platform", "state": "Todo"},
        ]
        result = CeremonyScheduler(cfg).run("sprint_planning", st, sm)
        assert result.success and len(result.data["selected_issues"]) >= 1


class TestStateMigrationV4:
    def test_v3_gains_ceremonies(self):
        v3 = {
            "version": 3,
            "daily_counters": {},
            "trust_scores": {},
            "issues": {},
            "pipeline": {"active_workers": {}},
            "rate_limits": {"throttle_level": "green"},
        }
        v4 = migrate_state(v3)
        assert v4["version"] == 6 and "ceremonies" in v4
        assert v4["ceremonies"]["standup"]["last_run"] is None
        assert v4["ceremonies"]["sprint"]["current"] == []
        assert "self_monitor" in v4
        assert "toolchain_monitor" in v4
        assert "steering" in v4

    def test_v4_idempotent(self):
        v4 = {
            "version": 4,
            "daily_counters": {},
            "trust_scores": {},
            "ceremonies": _v4_ceremonies(),
        }
        result = migrate_state(v4)
        assert result["ceremonies"] == v4["ceremonies"]
        assert result["version"] == 6

    def test_preserves_existing_ceremony_data(self):
        v3 = {
            "version": 3,
            "daily_counters": {},
            "trust_scores": {},
            "ceremonies": {"standup": {"last_run": "2026-03-20T08:00:00+00:00"}},
        }
        v4 = migrate_state(v3)
        assert v4["ceremonies"]["standup"]["last_run"] == "2026-03-20T08:00:00+00:00"

    def test_pure_no_mutation(self):
        v3 = {"version": 3, "daily_counters": {}, "trust_scores": {}}
        original = copy.deepcopy(v3)
        migrate_state(v3)
        assert v3 == original
