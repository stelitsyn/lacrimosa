"""TDD tests for Lacrimosa self-observability module.
MetaSensor, ReactiveRule, ProactiveRule, AutoTuner, impact, rate limits, edge cases.
Imports FAIL — modules not yet implemented (TDD)."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
import pytest
from scripts.lacrimosa_self_monitor import (
    AutoTuner,
    MetaSensor,
    read_tune_log,
    run_self_monitor,
)
from scripts.lacrimosa_types import (
    AutoTuneEntry,
    MetaSensorSnapshot,
    MAX_TUNE_ENTRIES_PER_CYCLE,
)

_PT = "scripts.lacrimosa_self_monitor.get_trend_data"
_PS = "scripts.lacrimosa_self_monitor.compute_daily_summary"
_UTC = timezone.utc


def _now() -> str:
    return datetime.now(_UTC).isoformat()


def _ago(hours: int) -> str:
    return (datetime.now(_UTC) - timedelta(hours=hours)).isoformat()


def _summary(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tasks_completed": 3,
        "prs_merged": 2,
        "prs_reverted": 0,
        "total_cost_usd": 5.0,
        "average_tokens_per_task": 1000,
        "average_review_iterations": 1.5,
        "bugs_linked_total": 0,
        "average_duration_ms": 60000,
        "revert_rate": 0.0,
        "average_cost_per_task_usd": 1.67,
        "signals_processed": 0,
        "signals_validated": 0,
        "total_input_tokens": 800,
        "total_output_tokens": 200,
    }
    base.update(kw)
    return base


def _q(revert_rate: float = 0.0, avg_ri: float = 1.0, bpt: float = 0.0) -> dict[str, float]:
    return {"revert_rate": revert_rate, "avg_review_iterations": avg_ri, "bugs_per_task": bpt}


def _c(cpm: float = 2.5, tpt: int = 1000, tdc: float = 5.0) -> dict[str, Any]:
    return {"tokens_per_task": tpt, "cost_per_merged_pr": cpm, "total_daily_cost_usd": tdc}


def _snap(**kw: Any) -> MetaSensorSnapshot:
    d: dict[str, Any] = {
        "timestamp": _now(),
        "throughput": {"issues_completed": 3, "prs_merged": 2, "avg_time_to_merge_hours": 1.5},
        "quality": _q(),
        "cost": _c(),
        "discovery": {
            "signals_processed": 10,
            "signals_validated": 7,
            "signal_to_issue_rate": 0.71,
            "false_positive_rate": 0.29,
        },
        "ceremony": {"missed_count": 0, "last_run_ages": {"standup": 3.0}},
        "system": {
            "rate_limit_5h_pct": 30,
            "rate_limit_7d_pct": 20,
            "throttle_level": "green",
            "active_workers": 2,
            "conductor_uptime_hours": 48,
        },
    }
    d.update(kw)
    return MetaSensorSnapshot(**d)


@pytest.fixture
def config() -> dict[str, Any]:
    return {
        "self_monitor": {
            "cadence_hours": 4,
            "reactive_rules": {
                "high_revert_rate": {
                    "metric_path": "quality.revert_rate",
                    "operator": ">",
                    "threshold": 0.10,
                    "window_days": 3,
                    "severity": "high",
                    "action": "Tighten review criteria",
                },
                "ceremony_missed": {
                    "metric_path": "ceremony.missed_count",
                    "operator": ">=",
                    "threshold": 2,
                    "window_days": 1,
                    "severity": "high",
                    "action": "Check conductor health",
                },
            },
            "proactive_rules": {
                "zero_reverts_streak": {
                    "metric_path": "quality.revert_rate",
                    "operator": "==",
                    "threshold": 0.0,
                    "window_days": 7,
                    "action": "Consider trust tier promotion",
                },
                "cost_declining": {
                    "metric_path": "cost.cost_per_merged_pr",
                    "operator": "trend_declining",
                    "window_days": 5,
                    "action": "Log what's working",
                },
            },
            "tracking": {"default_impact_window_hours": 24},
        },
        "ceremonies": {"standup": {"cadence_hours": 4}, "sprint_retro": {"cadence_hours": 24}},
    }


@pytest.fixture
def state() -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "self_monitor": {"last_run": None, "last_snapshot": None, "pending_tune_entries": []},
        "daily_counters": {
            today: {"signals_processed": 10, "signals_validated": 7, "issues_discovered": 5}
        },
        "ceremonies": {"standup": {"last_run": _ago(3)}, "sprint_retro": {"last_run": _ago(20)}},
        "rate_limits": {
            "throttle_level": "green",
            "five_hour": {"used_percentage": 30},
            "seven_day": {"used_percentage": 20},
        },
        "pipeline": {"active_workers": {"w1": {}, "w2": {}}},
    }


class TestMetaSensorCollection:
    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_returns_all_six_categories(self, mock_s, _t, config, state):
        mock_s.return_value = _summary()
        snap = MetaSensor(config, state).collect()
        for cat in ("throughput", "quality", "cost", "discovery", "ceremony", "system"):
            assert hasattr(snap, cat), f"Missing: {cat}"

    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_throughput_values(self, mock_s, _t, config, state):
        mock_s.return_value = _summary(tasks_completed=5, prs_merged=3)
        snap = MetaSensor(config, state).collect()
        assert snap.throughput["issues_completed"] == 5
        assert snap.throughput["prs_merged"] == 3

    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_quality_revert_rate(self, mock_s, _t, config, state):
        mock_s.return_value = _summary(revert_rate=0.2)
        assert MetaSensor(config, state).collect().quality["revert_rate"] == 0.2

    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_cost_per_merged_pr_zero_safe(self, mock_s, _t, config, state):
        mock_s.return_value = _summary(prs_merged=0, total_cost_usd=10.0)
        assert MetaSensor(config, state).collect().cost["cost_per_merged_pr"] == 10.0

    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_discovery_none_when_no_data(self, mock_s, _t, config, state):
        """REQ-SELF-02: false_positive_rate=None when no signals."""
        mock_s.return_value = _summary()
        state["daily_counters"] = {}
        assert MetaSensor(config, state).collect().discovery["false_positive_rate"] is None

    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_ceremony_overdue_counted(self, mock_s, _t, config, state):
        """REQ-SELF-02: standup 10h ago, cadence 4h -> 2+ misses."""
        state["ceremonies"]["standup"]["last_run"] = _ago(10)
        mock_s.return_value = _summary()
        assert MetaSensor(config, state).collect().ceremony["missed_count"] >= 2

    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_system_rate_limit(self, mock_s, _t, config, state):
        state["rate_limits"]["five_hour"]["used_percentage"] = 85
        mock_s.return_value = _summary()
        assert MetaSensor(config, state).collect().system["rate_limit_5h_pct"] == 85


class TestReactiveRules:
    def test_revert_rate_fires_when_all_above(self, config):
        snaps = [_snap(quality=_q(0.12)) for _ in range(3)]
        assert any(
            e.trigger_rule == "high_revert_rate"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_revert_rate_no_fire_below(self, config):
        snaps = [_snap(quality=_q(0.05)) for _ in range(3)]
        assert not any(
            e.trigger_rule == "high_revert_rate"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_revert_rate_window_avg_below_no_fire(self, config):
        """REQ-REACT-01: avg(0.03, 0.05, 0.15) = 0.077 < 0.10."""
        snaps = [_snap(quality=_q(r)) for r in [0.03, 0.05, 0.15]]
        assert not any(
            e.trigger_rule == "high_revert_rate"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_ceremony_missed_fires_at_2(self, config):
        snaps = [_snap(ceremony={"missed_count": 2, "last_run_ages": {"standup": 10.0}})]
        assert any(
            e.trigger_rule == "ceremony_missed"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_ceremony_missed_no_fire_at_1(self, config):
        snaps = [_snap(ceremony={"missed_count": 1, "last_run_ages": {"standup": 5.0}})]
        assert not any(
            e.trigger_rule == "ceremony_missed"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_creates_learning_on_fire(self, config):
        """REQ-REACT-02: reactive rule creates learning."""
        mock_le = MagicMock()
        tuner = AutoTuner(config, mock_le)
        for e in tuner.evaluate([_snap(quality=_q(0.12)) for _ in range(3)]):
            tuner.apply_entry(e)
        assert mock_le.create_learning.called

    def test_cooldown_blocks_refire(self, config):
        """REQ-REACT-03: 24h cooldown prevents immediate re-fire."""
        tuner = AutoTuner(config, MagicMock())
        snaps = [_snap(quality=_q(0.12)) for _ in range(3)]
        for e in tuner.evaluate(snaps):
            tuner.apply_entry(e)
        assert not any(e.trigger_rule == "high_revert_rate" for e in tuner.evaluate(snaps))


class TestProactiveRules:
    def test_zero_reverts_7d_fires(self, config):
        snaps = [_snap(quality=_q(0.0)) for _ in range(7)]
        assert any(
            e.trigger_rule == "zero_reverts_streak"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_zero_reverts_5d_no_fire(self, config):
        snaps = [_snap(quality=_q(0.0)) for _ in range(5)]
        assert not any(
            e.trigger_rule == "zero_reverts_streak"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_cost_declining_monotonic_fires(self, config):
        """REQ-PROACT-01: 5 days monotonically declining."""
        snaps = [_snap(cost=_c(cpm=v)) for v in [5.0, 4.8, 4.5, 4.2, 3.9]]
        assert any(
            e.trigger_rule == "cost_declining"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_cost_not_monotonic_no_fire(self, config):
        snaps = [_snap(cost=_c(cpm=v)) for v in [5.0, 4.8, 5.1, 4.2, 3.9]]
        assert not any(
            e.trigger_rule == "cost_declining"
            for e in AutoTuner(config, MagicMock()).evaluate(snaps)
        )

    def test_proactive_entry_type(self, config):
        snaps = [_snap(quality=_q(0.0)) for _ in range(7)]
        entries = AutoTuner(config, MagicMock()).evaluate(snaps)
        proactive = [e for e in entries if e.trigger_rule == "zero_reverts_streak"]
        assert all(e.change_type == "proactive" for e in proactive)


class TestAutoTuner:
    def test_max_entries_cap(self, config):
        config["self_monitor"]["reactive_rules"]["extra"] = {
            "metric_path": "quality.avg_review_iterations",
            "operator": ">",
            "threshold": 0.1,
            "window_days": 1,
            "severity": "medium",
            "action": "Extra action",
        }
        snaps = [
            _snap(
                quality=_q(0.15, avg_ri=3.0, bpt=0.5),
                ceremony={"missed_count": 5, "last_run_ages": {}},
            )
            for _ in range(3)
        ]
        assert len(AutoTuner(config, MagicMock()).evaluate(snaps)) <= MAX_TUNE_ENTRIES_PER_CYCLE

    def test_entry_has_required_fields(self, config):
        entry = AutoTuner(config, MagicMock()).evaluate(
            [_snap(quality=_q(0.12)) for _ in range(3)]
        )[0]
        assert isinstance(entry, AutoTuneEntry)
        assert entry.id.startswith("tune-")
        assert entry.change_type == "reactive"

    def test_log_append(self, config, tmp_path):
        config["self_monitor"]["tracking"]["log_file"] = str(tmp_path / "tune.jsonl")
        tuner = AutoTuner(config, MagicMock())
        for e in tuner.evaluate([_snap(quality=_q(0.12)) for _ in range(3)]):
            tuner.apply_entry(e)
        assert len(read_tune_log(tmp_path / "tune.jsonl")) >= 1


def _tune_entry(eid: str, lrn_id: str) -> AutoTuneEntry:
    return AutoTuneEntry(
        id=eid,
        timestamp=_ago(25),
        trigger_rule="high_revert_rate",
        change_type="reactive",
        action="Tighten review",
        target_file="config.yaml",
        target_path="quality.revert_rate",
        old_value=0.12,
        new_value=0.08,
        applied_at=_ago(25),
        impact_window_hours=24,
        measured_impact=None,
        reverted=False,
        learning_id=lrn_id,
    )


class TestImpactMeasurement:
    def test_improved_verdict(self, config):
        results = AutoTuner(config, MagicMock()).check_impact(
            [_tune_entry("tune-t1", "lrn-t1")], _snap(quality=_q(0.04))
        )
        assert results[0]["verdict"] == "improved"

    def test_degraded_triggers_revert(self, config):
        """EDGE-02: degraded -> auto-revert + 72h extended cooldown."""
        mock_le = MagicMock()
        AutoTuner(config, mock_le).check_impact(
            [_tune_entry("tune-t2", "lrn-t2")], _snap(quality=_q(0.40))
        )
        mock_le.revert_adjustment.assert_called_once_with("lrn-t2")


class TestRateLimitGating:
    def test_skip_under_red(self, config, state):
        state["rate_limits"]["throttle_level"] = "red"
        assert run_self_monitor(config, state, MagicMock(), MagicMock())["skipped"] is True

    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_runs_under_yellow(self, mock_s, _t, config, state):
        state["rate_limits"]["throttle_level"] = "yellow"
        mock_s.return_value = _summary()
        assert run_self_monitor(config, state, MagicMock(), MagicMock()).get("skipped") is not True


class TestEdgeCases:
    @patch(_PT, return_value=[])
    @patch(_PS)
    def test_empty_first_day(self, mock_s, _t, config, state):
        """EDGE-01: first day, no data."""
        mock_s.return_value = _summary(
            tasks_completed=0, prs_merged=0, total_cost_usd=0.0, revert_rate=0.0
        )
        state["daily_counters"] = {}
        assert MetaSensor(config, state).collect().throughput["issues_completed"] == 0

    def test_empty_snapshots_no_fire(self, config):
        assert AutoTuner(config, MagicMock()).evaluate([]) == []

    def test_conflicting_rules_both_fire(self, config):
        """EDGE-04: two reactive rules fire in same cycle."""
        config["self_monitor"]["reactive_rules"]["cost_spike"] = {
            "metric_path": "cost.tokens_per_task",
            "operator": ">",
            "threshold": 500,
            "window_days": 1,
            "severity": "medium",
            "action": "Investigate prompt bloat",
        }
        snaps = [_snap(quality=_q(0.15), cost=_c(tpt=2000, cpm=5.0, tdc=10.0)) for _ in range(3)]
        triggered = {e.trigger_rule for e in AutoTuner(config, MagicMock()).evaluate(snaps)}
        assert triggered >= {"high_revert_rate", "cost_spike"}
