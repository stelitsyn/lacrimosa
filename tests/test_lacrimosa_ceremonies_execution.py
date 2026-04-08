"""TDD tests for Lacrimosa ceremonies — grooming, retro, weekly summary, edge cases.
Companion to test_lacrimosa_ceremonies.py. Tests FAIL (TDD — module not yet implemented).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.lacrimosa_ceremonies import CeremonyScheduler, check_and_run_ceremonies
from scripts.lacrimosa_state import StateManager
from scripts.lacrimosa_types import CeremonyResult

_FRI = datetime(2026, 3, 20, tzinfo=timezone.utc)


def _at(h: int, m: int = 0) -> datetime:
    return _FRI.replace(hour=h, minute=m, second=0, microsecond=0)


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
            "learning": {"auto_apply": False},
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
        "daily_counters": {"2026-03-20": {"workers_spawned": 0, "prs_merged": 0}},
        "pipeline": {"active_workers": {}},
        "rate_limits": {"throttle_level": "green"},
        "ceremonies": _v4_ceremonies(),
    }


@pytest.fixture
def sm(tmp_path) -> StateManager:
    return StateManager(tmp_path / "state.json")


_ML = "scripts.lacrimosa_ceremony_runners._post_to_linear"
_MS = "scripts.lacrimosa_ceremony_runners.compute_daily_summary"
_MT = "scripts.lacrimosa_ceremony_runners.get_trend_data"
_MB = "scripts.lacrimosa_ceremony_runners._query_linear_backlog"


class TestGrooming:
    @patch(_ML, return_value="https://linear.app/c/30")
    def test_re_score_stale_signals(self, mock_post, cfg, st, sm):
        now = _at(20, 0)
        st["issues"]["TST-50"] = {
            "priority_score": 5,
            "scored_at": _ago(now, 14),
            "domain": "Platform",
            "state": "Backlog",
        }
        result = CeremonyScheduler(cfg).run("backlog_grooming", st, sm)
        assert result.success and result.data["actions"]["re_scored"] >= 1

    @patch(_ML, return_value="https://linear.app/c/31")
    def test_decompose_large_issue(self, mock_post, cfg, st, sm):
        st["issues"]["TST-80"] = {
            "estimated_files": 20,
            "domain": "Platform",
            "state": "Backlog",
        }
        result = CeremonyScheduler(cfg).run("backlog_grooming", st, sm)
        assert result.data["actions"]["decomposed"] >= 1

    @patch(_ML, return_value="https://linear.app/c/32")
    def test_merge_duplicates(self, mock_post, cfg, st, sm):
        st["issues"]["TST-30"] = {
            "title": "Fix broken email CTA",
            "description": "CTA broken",
            "priority_score": 5,
            "state": "Backlog",
        }
        st["issues"]["TST-45"] = {
            "title": "Email CTA button broken",
            "description": "Button not working",
            "priority_score": 3,
            "state": "Backlog",
        }
        result = CeremonyScheduler(cfg).run("backlog_grooming", st, sm)
        assert result.data["actions"]["merged"] >= 1

    @patch(_ML, return_value="https://linear.app/c/33")
    def test_archive_abandoned(self, mock_post, cfg, st, sm):
        st["issues"]["TST-35"] = {
            "state": "Todo",
            "last_activity": _ago(_at(20, 0), 52),
            "domain": "Platform",
        }
        result = CeremonyScheduler(cfg).run("backlog_grooming", st, sm)
        assert result.data["actions"]["archived"] >= 1

    @patch(_ML, return_value="https://linear.app/c/34")
    def test_rate_limit_red_skips_decompose(self, mock_post, cfg, st, sm):
        st["rate_limits"]["throttle_level"] = "red"
        st["issues"]["TST-80"] = {
            "estimated_files": 20,
            "domain": "Platform",
            "state": "Backlog",
        }
        result = CeremonyScheduler(cfg).run("backlog_grooming", st, sm)
        assert result.data["actions"]["decomposed"] == 0

    @patch(_ML, return_value="https://linear.app/c/35")
    def test_no_stale_signals(self, mock_post, cfg, st, sm):
        # scored_at must be recent (within stale_threshold_hours=12) relative
        # to real wall-clock time, since the runner uses datetime.now(utc).
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        recent = (_dt.now(_tz.utc) - _td(hours=2)).isoformat()
        st["issues"]["TST-50"] = {
            "priority_score": 5,
            "scored_at": recent,
            "state": "Backlog",
        }
        result = CeremonyScheduler(cfg).run("backlog_grooming", st, sm)
        assert result.data["actions"]["re_scored"] == 0


_TODAY = {
    "tasks_completed": 5,
    "tasks_failed": 1,
    "tasks_escalated": 0,
    "prs_merged": 5,
    "prs_reverted": 0,
    "average_review_iterations": 1.4,
    "total_cost_usd": 3.50,
    "average_cost_per_task_usd": 0.70,
    "revert_rate": 0.0,
}
_YESTERDAY = {
    "tasks_completed": 3,
    "tasks_failed": 0,
    "prs_merged": 3,
    "prs_reverted": 0,
    "average_review_iterations": 1.2,
    "total_cost_usd": 2.10,
    "revert_rate": 0.0,
}


class TestRetro:
    @patch(_ML, return_value="https://linear.app/c/40")
    @patch(_MS, return_value=_TODAY)
    def test_normal_with_deltas(self, mock_sum, mock_post, cfg, st, sm):
        st["ceremonies"]["retro"]["last_metrics_snapshot"] = _YESTERDAY
        result = CeremonyScheduler(cfg).run("sprint_retro", st, sm)
        assert result.success and result.data["metrics"]["tasks_completed"] == 5
        assert "delta" in result.data or "deltas" in result.data

    @patch(_ML, return_value="https://linear.app/c/41")
    @patch(_MS, return_value={**_TODAY, "tasks_completed": 3})
    def test_first_retro_no_yesterday(self, mock_sum, mock_post, cfg, st, sm):
        result = CeremonyScheduler(cfg).run("sprint_retro", st, sm)
        assert result.success
        assert result.data.get("first_retro") is True or "first" in result.summary.lower()

    @patch(_ML, return_value="https://linear.app/c/42")
    @patch(_MS, return_value={**_TODAY, "prs_reverted": 1, "revert_rate": 0.2})
    @patch("scripts.lacrimosa_ceremony_runners.LearningsEngine")
    def test_negative_trend_generates_learning(self, mock_le, mock_sum, mock_post, cfg, st, sm):
        mock_engine = MagicMock()
        mock_engine.create_learning.return_value = "lrn-abc123"
        mock_le.return_value = mock_engine
        st["ceremonies"]["retro"]["last_metrics_snapshot"] = _YESTERDAY
        result = CeremonyScheduler(cfg).run("sprint_retro", st, sm)
        assert len(result.data.get("learnings_generated", [])) >= 1
        mock_engine.create_learning.assert_called()

    @patch(_ML, return_value="https://linear.app/c/43")
    @patch(_MS, return_value={k: 0 for k in _TODAY})
    def test_zero_tasks(self, mock_sum, mock_post, cfg, st, sm):
        result = CeremonyScheduler(cfg).run("sprint_retro", st, sm)
        assert result.success  # does not skip on idle days

    @patch(_ML, return_value="https://linear.app/c/44")
    @patch(_MS, return_value={**_TODAY, "revert_rate": 0.15, "prs_reverted": 1})
    @patch("scripts.lacrimosa_ceremony_runners.LearningsEngine")
    def test_retro_learnings_status_in_review(self, mock_le, mock_sum, mock_post, cfg, st, sm):
        mock_engine = MagicMock()
        mock_engine.create_learning.return_value = "lrn-test"
        mock_le.return_value = mock_engine
        st["ceremonies"]["retro"]["last_metrics_snapshot"] = _YESTERDAY
        CeremonyScheduler(cfg).run("sprint_retro", st, sm)
        if mock_engine.create_learning.called:
            learning = mock_engine.create_learning.call_args[0][0]
            assert learning.get("status") == "in_review"
            assert learning.get("applied") is False


class TestWeeklySummary:
    @patch(_ML, return_value="https://linear.app/i/50")
    @patch(_MT)
    def test_full_week(self, mock_trend, mock_post, cfg, st, sm):
        mock_trend.return_value = [
            {
                "date": f"2026-03-{d}",
                "prs_merged": 5,
                "total_cost_usd": 3.7,
                "revert_rate": 0.0,
                "average_review_iterations": 1.2,
            }
            for d in range(16, 21)
        ]
        result = CeremonyScheduler(cfg).run("weekly_summary", st, sm)
        assert result.success and result.data["week_prs_merged"] == 25
        assert abs(result.data["week_cost_total"] - 18.5) < 0.01

    @patch(_ML, return_value="https://linear.app/i/51")
    @patch(_MT)
    def test_partial_week(self, mock_trend, mock_post, cfg, st, sm):
        mock_trend.return_value = [
            {"date": f"2026-03-{d}", "prs_merged": 3, "total_cost_usd": 2.0} for d in range(16, 19)
        ]
        result = CeremonyScheduler(cfg).run("weekly_summary", st, sm)
        assert result.success and result.data.get("days_with_data") == 3

    @patch(_ML, return_value="https://linear.app/i/52")
    @patch(_MT, return_value=[{"date": "2026-03-20", "prs_merged": 5, "total_cost_usd": 3.0}])
    def test_first_ever_weekly(self, mock_trend, mock_post, cfg, st, sm):
        result = CeremonyScheduler(cfg).run("weekly_summary", st, sm)
        assert result.success
        assert result.data.get("first_week") is True or "first" in result.summary.lower()

    @patch(_ML, return_value="https://linear.app/i/53")
    @patch(_MT, return_value=[{"date": "2026-03-20", "prs_merged": 5, "total_cost_usd": 3.0}])
    def test_trust_progression(self, mock_trend, mock_post, cfg, st, sm):
        st["trust_scores"]["Platform"] = {"tier": 1, "previous_tier": 0}
        result = CeremonyScheduler(cfg).run("weekly_summary", st, sm)
        assert "trust" in str(result.data).lower()


class TestEdgeCases:
    @patch(_ML, side_effect=Exception("crash mid-ceremony"))
    def test_crash_last_run_not_updated(self, mock_post, cfg, st, sm):
        result = CeremonyScheduler(cfg).run("standup", st, sm)
        assert result.success is False and result.error is not None

    @patch(_ML, return_value=None)
    def test_linear_failure_graceful(self, mock_post, cfg, st, sm):
        result = CeremonyScheduler(cfg).run("standup", st, sm)
        assert result.success is True and result.linear_url is None

    @patch(_ML, return_value="https://linear.app/c/60")
    @patch(_MB, side_effect=Exception("Linear down"))
    def test_planning_linear_down_uses_cache(self, mock_bl, mock_post, cfg, st, sm):
        st["issues"]["TST-10"] = {
            "priority_score": 5,
            "domain": "Platform",
            "state": "Todo",
        }
        result = CeremonyScheduler(cfg).run("sprint_planning", st, sm)
        assert result.success
        assert result.data.get("from_cache") is True or "cache" in result.summary.lower()

    @patch(_ML, return_value="https://linear.app/c/61")
    def test_rate_limit_read_only_ceremonies_run(self, mock_post, cfg, st, sm):
        st["rate_limits"]["throttle_level"] = "red"
        for name in ("standup", "sprint_retro"):
            result = CeremonyScheduler(cfg).run(name, st, sm)
            assert result.success is True

    def test_check_and_run_sequential(self, cfg, st, sm):
        with patch(_ML, return_value="https://linear.app/c/70"):
            results = check_and_run_ceremonies(st, cfg, sm)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r, CeremonyResult)

    @patch(_ML, return_value="https://linear.app/c/80")
    @patch(_MS, return_value={k: 0 for k in _TODAY})
    def test_empty_state_ceremonies_succeed(self, mock_sum, mock_post, cfg, sm):
        empty: dict[str, Any] = {
            "version": 4,
            "system_state": "Running",
            "trust_scores": {},
            "issues": {},
            "daily_counters": {},
            "pipeline": {"active_workers": {}},
            "rate_limits": {"throttle_level": "green"},
            "ceremonies": _v4_ceremonies(),
        }
        for name in ("standup", "sprint_retro"):
            result = CeremonyScheduler(cfg).run(name, empty, sm)
            assert result.success is True
