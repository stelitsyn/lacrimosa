"""TDD tests for Lacrimosa Linear steering module.

Tests: command parsing, execution, acknowledgment generation,
comment filtering, state mutations for steering commands.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from scripts.lacrimosa_steering import (
    build_acknowledgment,
    execute_command,
    is_steering_comment,
    parse_steering_command,
    should_process_comment,
)
from scripts.lacrimosa_types import SteeringCommand, SteeringCommandType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_state() -> dict[str, Any]:
    return {
        "version": 6,
        "system_state": "Running",
        "issues": {
            "TST-100": {
                "state": "Implementation",
                "retry_count": 0,
                "priority": 3,
            },
            "TST-200": {
                "state": "InReview",
                "retry_count": 0,
                "priority": 2,
            },
        },
        "pipeline": {
            "active_workers": {
                "TST-100": {
                    "pid": 12345,
                    "phase": "implementation",
                    "started_at": "2026-03-25T10:00:00+00:00",
                    "domain": "Platform",
                },
            },
        },
        "steering": {
            "last_poll": None,
            "processed_comment_ids": [],
        },
    }


@pytest.fixture
def sample_comment() -> dict[str, Any]:
    return {
        "id": "comment-uuid-123",
        "body": "@lacrimosa rework this issue — the approach is wrong",
        "user": {"name": "Test Owner"},
        "createdAt": "2026-03-25T14:30:00Z",
        "issue": {"identifier": "TST-100"},
    }


# ---------------------------------------------------------------------------
# SteeringCommandType enum
# ---------------------------------------------------------------------------


class TestSteeringCommandType:
    def test_all_command_types_exist(self) -> None:
        assert SteeringCommandType.REWORK == "rework"
        assert SteeringCommandType.RECONSIDER == "reconsider"
        assert SteeringCommandType.PAUSE == "pause"
        assert SteeringCommandType.RESUME == "resume"
        assert SteeringCommandType.PRIORITIZE == "prioritize"
        assert SteeringCommandType.DEPRIORITIZE == "deprioritize"
        assert SteeringCommandType.CANCEL == "cancel"


# ---------------------------------------------------------------------------
# parse_steering_command
# ---------------------------------------------------------------------------


class TestParseSteeringCommand:
    def test_parse_rework(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa rework this — approach is wrong",
            "TST-100",
            "comment-1",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.REWORK
        assert cmd.issue_id == "TST-100"
        assert cmd.comment_id == "comment-1"

    def test_parse_redo_alias(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa redo this task",
            "TST-100",
            "comment-2",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.REWORK

    def test_parse_reconsider(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa reconsider the architecture",
            "TST-100",
            "comment-3",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.RECONSIDER

    def test_parse_pause(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa pause work on this",
            "TST-100",
            "comment-4",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.PAUSE

    def test_parse_resume(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa resume this",
            "TST-100",
            "comment-5",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.RESUME

    def test_parse_unpause_alias(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa unpause",
            "TST-100",
            "comment-6",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.RESUME

    def test_parse_prioritize(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa prioritize this issue",
            "TST-100",
            "comment-7",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.PRIORITIZE

    def test_parse_urgent_alias(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa urgent",
            "TST-100",
            "comment-8",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.PRIORITIZE

    def test_parse_deprioritize(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa deprioritize this",
            "TST-100",
            "comment-9",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.DEPRIORITIZE

    def test_parse_cancel(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa cancel this work",
            "TST-100",
            "comment-10",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.CANCEL

    def test_parse_no_command_returns_none(self) -> None:
        cmd = parse_steering_command(
            "This is a regular comment with no steering",
            "TST-100",
            "comment-11",
        )
        assert cmd is None

    def test_parse_lacrimosa_without_command_returns_none(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa looks good to me",
            "TST-100",
            "comment-12",
        )
        assert cmd is None

    def test_parse_case_insensitive(self) -> None:
        cmd = parse_steering_command(
            "@LACRIMOSA REWORK this",
            "TST-100",
            "comment-13",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.REWORK

    def test_parse_lacrimosa_in_middle_of_text(self) -> None:
        cmd = parse_steering_command(
            "Hey lacrimosa, please rework this one",
            "TST-100",
            "comment-14",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.REWORK

    def test_parse_extracts_context(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa rework — the API design needs to use REST not GraphQL",
            "TST-100",
            "comment-15",
        )
        assert cmd is not None
        assert cmd.context != ""

    def test_parse_command_with_stop_keyword(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa stop working on this",
            "TST-100",
            "comment-16",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.PAUSE

    def test_parse_hold_alias(self) -> None:
        cmd = parse_steering_command(
            "@lacrimosa hold this issue",
            "TST-100",
            "comment-17",
        )
        assert cmd is not None
        assert cmd.command_type == SteeringCommandType.PAUSE


# ---------------------------------------------------------------------------
# is_steering_comment
# ---------------------------------------------------------------------------


class TestIsSteeringComment:
    def test_at_mention(self) -> None:
        assert is_steering_comment("@lacrimosa rework") is True

    def test_plain_mention(self) -> None:
        assert is_steering_comment("lacrimosa, please rework") is True

    def test_no_mention(self) -> None:
        assert is_steering_comment("just a normal comment") is False

    def test_case_insensitive(self) -> None:
        assert is_steering_comment("@LACRIMOSA pause") is True

    def test_lacrimosa_in_url_is_not_mention(self) -> None:
        assert is_steering_comment("see https://example.com/lacrimosa-docs for info") is False


# ---------------------------------------------------------------------------
# should_process_comment
# ---------------------------------------------------------------------------


class TestShouldProcessComment:
    def test_new_comment_should_process(self) -> None:
        processed: set[str] = set()
        assert should_process_comment("comment-new", processed) is True

    def test_already_processed_comment_skipped(self) -> None:
        processed = {"comment-old"}
        assert should_process_comment("comment-old", processed) is False

    def test_empty_id_skipped(self) -> None:
        assert should_process_comment("", set()) is False


# ---------------------------------------------------------------------------
# execute_command
# ---------------------------------------------------------------------------


class TestExecuteCommand:
    def test_rework_resets_to_implementation(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.REWORK,
            issue_id="TST-100",
            comment_id="c1",
            context="wrong approach",
        )
        new_state, action = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["state"] == "RetryQueued"
        assert "rework" in action.lower() or "retry" in action.lower()

    def test_rework_does_not_mutate_original(self, base_state: dict[str, Any]) -> None:
        original = copy.deepcopy(base_state)
        cmd = SteeringCommand(
            command_type=SteeringCommandType.REWORK,
            issue_id="TST-100",
            comment_id="c1",
            context="",
        )
        execute_command(cmd, base_state)
        assert base_state == original

    def test_reconsider_resets_to_research(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.RECONSIDER,
            issue_id="TST-100",
            comment_id="c2",
            context="need different architecture",
        )
        new_state, action = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["state"] == "Identified"

    def test_pause_sets_paused_state(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.PAUSE,
            issue_id="TST-100",
            comment_id="c3",
            context="",
        )
        new_state, action = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["state"] == "Paused"

    def test_resume_from_paused(self, base_state: dict[str, Any]) -> None:
        state = copy.deepcopy(base_state)
        state["issues"]["TST-100"]["state"] = "Paused"
        state["issues"]["TST-100"]["paused_from"] = "Implementation"
        cmd = SteeringCommand(
            command_type=SteeringCommandType.RESUME,
            issue_id="TST-100",
            comment_id="c4",
            context="",
        )
        new_state, action = execute_command(cmd, state)
        assert new_state["issues"]["TST-100"]["state"] == "Implementation"

    def test_resume_non_paused_is_noop(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.RESUME,
            issue_id="TST-100",
            comment_id="c5",
            context="",
        )
        new_state, action = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["state"] == "Implementation"
        assert "already" in action.lower() or "not paused" in action.lower()

    def test_prioritize_sets_urgent(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.PRIORITIZE,
            issue_id="TST-100",
            comment_id="c6",
            context="",
        )
        new_state, action = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["priority"] == 1

    def test_deprioritize_lowers_priority(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.DEPRIORITIZE,
            issue_id="TST-100",
            comment_id="c7",
            context="",
        )
        new_state, action = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["priority"] == 4

    def test_cancel_marks_cancelled(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.CANCEL,
            issue_id="TST-100",
            comment_id="c8",
            context="",
        )
        new_state, action = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["state"] == "Cancelled"

    def test_cancel_removes_from_active_workers(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.CANCEL,
            issue_id="TST-100",
            comment_id="c9",
            context="",
        )
        new_state, _ = execute_command(cmd, base_state)
        assert "TST-100" not in new_state["pipeline"]["active_workers"]

    def test_unknown_issue_returns_error(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.REWORK,
            issue_id="TST-999",
            comment_id="c10",
            context="",
        )
        new_state, action = execute_command(cmd, base_state)
        assert "not found" in action.lower() or "unknown" in action.lower()
        assert new_state == base_state

    def test_pause_records_paused_from(self, base_state: dict[str, Any]) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.PAUSE,
            issue_id="TST-100",
            comment_id="c11",
            context="",
        )
        new_state, _ = execute_command(cmd, base_state)
        assert new_state["issues"]["TST-100"]["paused_from"] == "Implementation"


# ---------------------------------------------------------------------------
# build_acknowledgment
# ---------------------------------------------------------------------------


class TestBuildAcknowledgment:
    def test_rework_acknowledgment(self) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.REWORK,
            issue_id="TST-100",
            comment_id="c1",
            context="wrong approach",
        )
        msg = build_acknowledgment(cmd, "Issue queued for rework")
        assert "rework" in msg.lower()
        assert "TST-100" in msg
        assert "Lacrimosa" in msg

    def test_cancel_acknowledgment(self) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.CANCEL,
            issue_id="TST-200",
            comment_id="c2",
            context="no longer needed",
        )
        msg = build_acknowledgment(cmd, "Work cancelled")
        assert "cancel" in msg.lower()

    def test_acknowledgment_includes_context_when_present(self) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.RECONSIDER,
            issue_id="TST-100",
            comment_id="c3",
            context="use REST instead of GraphQL",
        )
        msg = build_acknowledgment(cmd, "Sent back to research phase")
        assert "REST" in msg or "context" in msg.lower() or "reconsider" in msg.lower()

    def test_acknowledgment_format_is_markdown(self) -> None:
        cmd = SteeringCommand(
            command_type=SteeringCommandType.PAUSE,
            issue_id="TST-100",
            comment_id="c4",
            context="",
        )
        msg = build_acknowledgment(cmd, "Issue paused")
        assert "**" in msg or "##" in msg


# ---------------------------------------------------------------------------
# State migration v5 → v6
# ---------------------------------------------------------------------------


class TestStateMigration:
    def test_v5_state_gets_steering_section(self) -> None:
        from scripts.lacrimosa_state_json_backup import migrate_state

        v5_state: dict[str, Any] = {
            "version": 5,
            "system_state": "Stopped",
            "session_mode": "interactive",
            "last_poll": None,
            "conductor_pid": None,
            "trust_scores": {},
            "issues": {},
            "daily_counters": {},
            "discovery": {
                "last_internal_sense": None,
                "last_external_sense": None,
                "last_strategy_analysis": None,
                "last_deep_research": None,
            },
            "pipeline": {"active_workers": {}, "implementation_queue": []},
            "rate_limits": {"throttle_level": "green"},
            "vision_cache": {"last_strategy_analysis": None, "identified_gaps": []},
            "ceremonies": {
                "standup": {"last_run": None, "last_output_url": None},
                "sprint": {"current": [], "planned_at": None, "capacity": {}},
                "sprint_planning": {"last_run": None},
                "grooming": {
                    "last_run": None,
                    "last_actions": {
                        "re_scored": 0,
                        "decomposed": 0,
                        "merged": 0,
                        "archived": 0,
                    },
                },
                "retro": {
                    "last_run": None,
                    "last_metrics_snapshot": None,
                    "last_learnings_ids": [],
                },
                "weekly_summary": {"last_run": None, "last_document_url": None},
            },
            "self_monitor": {
                "last_run": None,
                "last_snapshot": None,
                "pending_tune_entries": [],
            },
            "toolchain_monitor": {
                "last_run": None,
                "last_findings_count": 0,
                "known_versions": {},
            },
        }
        migrated = migrate_state(v5_state)
        assert migrated["version"] == 6
        assert "steering" in migrated
        assert migrated["steering"]["last_poll"] is None
        assert migrated["steering"]["processed_comment_ids"] == []

    def test_v6_state_unchanged(self) -> None:
        from scripts.lacrimosa_state_json_backup import migrate_state

        v6_state: dict[str, Any] = {
            "version": 6,
            "steering": {"last_poll": "2026-03-25T10:00:00Z", "processed_comment_ids": ["c1"]},
            "system_state": "Running",
            "daily_counters": {},
            "trust_scores": {},
        }
        migrated = migrate_state(v6_state)
        assert migrated["version"] == 6
        assert migrated["steering"]["processed_comment_ids"] == ["c1"]
