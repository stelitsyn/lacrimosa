"""
TDD tests for the Lacrimosa v2 conductor module.
Tests: config validation, rate limits, cadence scheduling, dispatch gates, lifecycle routing.
Imports from scripts.lacrimosa_conductor (not yet implemented — tests FAIL).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from scripts.lacrimosa_conductor import (
    can_dispatch,
    check_rate_limits,
    is_cadence_due,
    load_config,
    validate_config,
)
from scripts.lacrimosa_types import ThrottleLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_config() -> dict[str, Any]:
    return {
        "conductor": {
            "poll_interval_seconds": 60,
            "worktree_base": "/tmp/lacrimosa",
            "state_file": "~/.claude/lacrimosa/state.json",
        },
        "lifecycle": {
            "phases": {
                "research": {"max_duration_minutes": 15},
                "architecture": {"max_duration_minutes": 10},
                "implementation": {"max_duration_minutes": 30},
                "review": {"merge_criteria": {"max_critical": 0, "max_high": 0, "max_medium": 0}},
            },
            "routing": {
                "investigation": {"phases": ["research"]},
                "bug_known_fix": {"phases": ["implementation", "review", "verification", "merge"]},
                "bug_unknown": {
                    "phases": ["research", "implementation", "review", "verification", "merge"]
                },
                "feature_with_spec": {
                    "phases": ["architecture", "implementation", "review", "verification", "merge"]
                },
                "feature_new": {
                    "phases": [
                        "research",
                        "architecture",
                        "implementation",
                        "review",
                        "verification",
                        "merge",
                    ]
                },
            },
        },
        "trust": {
            "tiers": {
                0: {"concurrent_workers": 1, "issues_per_day": 3, "max_files_per_pr": 15},
                1: {"concurrent_workers": 2, "issues_per_day": 5, "max_files_per_pr": 25},
                2: {"concurrent_workers": 3, "issues_per_day": 10, "max_files_per_pr": 40},
            },
            "cap_counting": "parent_issues",
        },
        "rate_limits": {
            "green_threshold": 50,
            "yellow_threshold": 80,
            "red_threshold": 90,
            "windows": ["five_hour", "seven_day"],
        },
        "discovery": {
            "internal_sense_interval_minutes": 30,
            "external_sense_interval_hours": 6,
            "strategy_analysis_interval_hours": 12,
            "deep_research_interval_hours": 24,
        },
        "workers": {"max_retries": 3, "stall_timeout_minutes": 10},
        "domains": {
            "autonomous": ["Platform", "Marketing"],
            "approval_required": ["Billing", "Mobile"],
        },
        "ceremonies": {
            "enabled": True,
            "standup": {"enabled": True, "cadence_hours": 4},
            "sprint_planning": {"enabled": True, "time": "08:00"},
            "backlog_grooming": {"enabled": True, "cadence_hours": 12},
            "sprint_retro": {"enabled": True, "time": "22:00"},
            "weekly_summary": {"enabled": True, "day": "friday", "time": "22:30"},
        },
        "self_monitor": {
            "cadence_hours": 4,
            "reactive_rules": {},
            "proactive_rules": {},
            "tracking": {"default_impact_window_hours": 24},
        },
    }


@pytest.fixture
def base_state() -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "version": 3,
        "system_state": "Running",
        "session_mode": "interactive",
        "last_poll": datetime.now(timezone.utc).isoformat(),
        "trust_scores": {
            "Platform": {"tier": 0, "successful_merges": 0},
            "Marketing": {"tier": 1, "successful_merges": 6},
        },
        "issues": {},
        "daily_counters": {today: {"workers_spawned": 0, "issues_completed": 0}},
        "discovery": {
            "last_internal_sense": None,
            "last_external_sense": None,
            "last_strategy_analysis": None,
            "last_deep_research": None,
        },
        "pipeline": {"active_workers": {}, "implementation_queue": []},
        "rate_limits": {"throttle_level": "green"},
    }


def _ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


# ---------------------------------------------------------------------------
# Config validation (CTO Decision 6 — Layer 1)
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_valid_config_no_errors(self, base_config):
        assert validate_config(base_config) == []

    def test_missing_conductor_section(self, base_config):
        del base_config["conductor"]
        assert any("conductor" in e.lower() for e in validate_config(base_config))

    def test_missing_lifecycle_section(self, base_config):
        del base_config["lifecycle"]
        assert len(validate_config(base_config)) > 0

    def test_missing_trust_section(self, base_config):
        del base_config["trust"]
        assert len(validate_config(base_config)) > 0

    def test_missing_discovery_section(self, base_config):
        del base_config["discovery"]
        assert len(validate_config(base_config)) > 0

    def test_t0_daily_cap_too_high(self, base_config):
        base_config["trust"]["tiers"][0]["issues_per_day"] = 25
        assert len(validate_config(base_config)) > 0


class TestLoadConfig:
    def test_load_valid_yaml(self, tmp_path, base_config):
        import yaml

        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(base_config))
        assert load_config(p)["conductor"]["poll_interval_seconds"] == 60

    def test_load_invalid_yaml_exits(self, tmp_path):
        (tmp_path / "config.yaml").write_text("{{invalid yaml: [")
        with pytest.raises(SystemExit):
            load_config(tmp_path / "config.yaml")

    def test_load_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            load_config(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# Rate limits (D1-AC07/AC08, BS-005)
# ---------------------------------------------------------------------------


class TestRateLimits:
    def test_green_below_threshold(self, base_config):
        r = {"five_hour": {"used_percentage": 30}, "seven_day": {"used_percentage": 20}}
        assert check_rate_limits(base_config, r) == ThrottleLevel.green

    def test_yellow_at_threshold(self, base_config):
        r = {"five_hour": {"used_percentage": 80}, "seven_day": {"used_percentage": 40}}
        assert check_rate_limits(base_config, r) == ThrottleLevel.yellow

    def test_red_at_threshold(self, base_config):
        r = {"five_hour": {"used_percentage": 90}, "seven_day": {"used_percentage": 40}}
        assert check_rate_limits(base_config, r) == ThrottleLevel.red

    def test_worst_wins_seven_day_yellow(self, base_config):
        r = {"five_hour": {"used_percentage": 30}, "seven_day": {"used_percentage": 82}}
        assert check_rate_limits(base_config, r) == ThrottleLevel.yellow

    def test_worst_wins_seven_day_red(self, base_config):
        r = {"five_hour": {"used_percentage": 30}, "seven_day": {"used_percentage": 92}}
        assert check_rate_limits(base_config, r) == ThrottleLevel.red

    @pytest.mark.parametrize(
        "five_h,seven_d,expected",
        [
            (0, 0, "green"),
            (49, 49, "green"),
            (80, 40, "yellow"),
            (40, 80, "yellow"),
            (89, 89, "yellow"),
            (90, 40, "red"),
            (40, 90, "red"),
            (100, 100, "red"),
        ],
        ids=[
            "zero",
            "below-yellow",
            "5h-yellow",
            "7d-yellow",
            "both-yellow",
            "5h-red",
            "7d-red",
            "both-max",
        ],
    )
    def test_rate_limit_matrix(self, base_config, five_h, seven_d, expected):
        r = {"five_hour": {"used_percentage": five_h}, "seven_day": {"used_percentage": seven_d}}
        assert check_rate_limits(base_config, r).value == expected


# ---------------------------------------------------------------------------
# Dispatch gating (D1-AC03/AC04, BS-001, BS-017)
# ---------------------------------------------------------------------------


class TestCanDispatch:
    def test_allowed_no_active_workers(self, base_config, base_state):
        assert can_dispatch("Platform", base_state, base_config) is True

    def test_blocked_concurrent_limit_t0(self, base_config, base_state):
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {"domain": "Platform", "pid": 111}
        }
        assert can_dispatch("Platform", base_state, base_config) is False

    def test_allowed_concurrent_limit_t1(self, base_config, base_state):
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {"domain": "Marketing", "pid": 111}
        }
        assert can_dispatch("Marketing", base_state, base_config) is True

    def test_blocked_concurrent_limit_t1_full(self, base_config, base_state):
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {"domain": "Marketing", "pid": 111},
            "TST-51": {"domain": "Marketing", "pid": 222},
        }
        assert can_dispatch("Marketing", base_state, base_config) is False

    def test_blocked_daily_cap(self, base_config, base_state):
        today = datetime.now().strftime("%Y-%m-%d")
        base_state["daily_counters"][today]["workers_spawned"] = 3
        assert can_dispatch("Platform", base_state, base_config) is False

    def test_blocked_red_throttle(self, base_config, base_state):
        base_state["rate_limits"]["throttle_level"] = "red"
        assert can_dispatch("Platform", base_state, base_config) is False

    def test_different_domain_doesnt_count(self, base_config, base_state):
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {"domain": "Marketing", "pid": 111}
        }
        assert can_dispatch("Platform", base_state, base_config) is True

    def test_hardcoded_max_concurrent_enforced(self, base_config, base_state):
        base_config["trust"]["tiers"][2]["concurrent_workers"] = 99
        base_state["trust_scores"]["Platform"] = {"tier": 2, "successful_merges": 20}
        for i in range(5):
            base_state["pipeline"]["active_workers"][f"TST-{i}"] = {
                "domain": "Platform",
                "pid": 1000 + i,
            }
        assert can_dispatch("Platform", base_state, base_config) is False

    def test_contraction_blocks_new_dispatch(self, base_config, base_state):
        """BS-017: after contraction to T0, 2 active workers exist but new dispatch blocked."""
        base_state["trust_scores"]["Platform"] = {"tier": 0, "successful_merges": 0}
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {"domain": "Platform", "pid": 111},
            "TST-51": {"domain": "Platform", "pid": 222},
        }
        assert can_dispatch("Platform", base_state, base_config) is False


# ---------------------------------------------------------------------------
# Cadence scheduling (D1-AC05/AC06)
# ---------------------------------------------------------------------------


class TestCadenceScheduling:
    def test_due_when_never_run(self):
        assert is_cadence_due(None, 30) is True

    def test_due_after_interval(self):
        assert is_cadence_due(_ago(35), 30) is True

    def test_not_due_before_interval(self):
        assert is_cadence_due(_ago(20), 30) is False

    def test_due_at_exact_boundary(self):
        assert is_cadence_due(_ago(30), 30) is True

    def test_external_due_after_6h(self):
        assert is_cadence_due(_ago(370), 360) is True

    def test_external_not_due_before_6h(self):
        assert is_cadence_due(_ago(300), 360) is False

    def test_strategy_due_after_12h(self):
        assert is_cadence_due(_ago(730), 720) is True

    def test_deep_research_due_after_24h(self):
        assert is_cadence_due(_ago(1450), 1440) is True


# ---------------------------------------------------------------------------
# Lifecycle routing
# ---------------------------------------------------------------------------


class TestLifecycleRouting:
    def test_bug_known_fix_skips_research(self, base_config):
        from scripts.lacrimosa_conductor import get_lifecycle_phases

        phases = get_lifecycle_phases("bug_known_fix", base_config)
        assert "research" not in phases
        assert "implementation" in phases

    def test_investigation_is_research_only(self, base_config):
        from scripts.lacrimosa_conductor import get_lifecycle_phases

        assert get_lifecycle_phases("investigation", base_config) == ["research"]

    def test_feature_new_includes_all_phases(self, base_config):
        from scripts.lacrimosa_conductor import get_lifecycle_phases

        phases = get_lifecycle_phases("feature_new", base_config)
        assert "research" in phases and "architecture" in phases and "merge" in phases

    def test_feature_with_spec_skips_research(self, base_config):
        from scripts.lacrimosa_conductor import get_lifecycle_phases

        phases = get_lifecycle_phases("feature_with_spec", base_config)
        assert "research" not in phases and "architecture" in phases

    def test_unknown_routing_raises(self, base_config):
        from scripts.lacrimosa_conductor import get_lifecycle_phases

        with pytest.raises(ValueError):
            get_lifecycle_phases("nonexistent_type", base_config)


# ---------------------------------------------------------------------------
# Specialist Health Check (v3 architecture)
# ---------------------------------------------------------------------------

from scripts.lacrimosa_conductor import (
    should_restart_specialist,
    parse_cadence_to_minutes,
)


class TestSpecialistHealthCheck:
    def test_should_restart_when_stale(self):
        from datetime import datetime, timezone, timedelta

        old = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
        assert (
            should_restart_specialist(
                last_heartbeat=old,
                max_silence_minutes=35,
                consecutive_errors=0,
            )
            == "stale_heartbeat"
        )

    def test_should_not_restart_when_fresh(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        assert (
            should_restart_specialist(
                last_heartbeat=now,
                max_silence_minutes=35,
                consecutive_errors=0,
            )
            is None
        )

    def test_should_restart_on_consecutive_errors(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        assert (
            should_restart_specialist(
                last_heartbeat=now,
                max_silence_minutes=35,
                consecutive_errors=3,
            )
            == "consecutive_errors"
        )

    def test_should_restart_on_no_heartbeat(self):
        assert (
            should_restart_specialist(
                last_heartbeat=None,
                max_silence_minutes=35,
                consecutive_errors=0,
            )
            == "no_heartbeat"
        )

    def test_should_disable_on_restart_storm(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        assert (
            should_restart_specialist(
                last_heartbeat=now,
                max_silence_minutes=35,
                consecutive_errors=0,
                restarts_24h=4,
                max_restarts_24h=3,
            )
            == "restart_storm"
        )

    def test_restart_storm_takes_priority(self):
        """Restart storm should be checked before other conditions."""
        assert (
            should_restart_specialist(
                last_heartbeat=None,
                max_silence_minutes=35,
                consecutive_errors=5,
                restarts_24h=4,
                max_restarts_24h=3,
            )
            == "restart_storm"
        )


class TestParseCadence:
    def test_minutes(self):
        assert parse_cadence_to_minutes("30m") == 30

    def test_hours(self):
        assert parse_cadence_to_minutes("6h") == 360

    def test_day(self):
        assert parse_cadence_to_minutes("24h") == 1440

    def test_plain_number_as_minutes(self):
        assert parse_cadence_to_minutes("10") == 10
