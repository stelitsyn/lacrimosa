"""
TDD tests for Lacrimosa v2 conductor dispatch and worker management.
Tests: worker dispatch subprocess args, security (SEC-C02), completions,
error handling (retry/escalation), state updates after dispatch.
Imports from scripts.lacrimosa_conductor (not yet implemented — tests FAIL).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.lacrimosa_conductor import (
    check_completions,
    dispatch_worker,
    handle_worker_failure,
    record_completion,
    record_dispatch,
)
from scripts.lacrimosa_types import WorkerEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_config() -> dict[str, Any]:
    return {
        "conductor": {"poll_interval_seconds": 60, "worktree_base": "/tmp/lacrimosa"},
        "trust": {
            "tiers": {
                0: {"concurrent_workers": 1, "issues_per_day": 3, "max_files_per_pr": 15},
                1: {"concurrent_workers": 2, "issues_per_day": 5, "max_files_per_pr": 25},
            }
        },
        "workers": {"max_retries": 3, "stall_timeout_minutes": 10, "shutdown_timeout_minutes": 30},
        "lifecycle": {
            "phases": {
                "research": {"max_duration_minutes": 15},
                "implementation": {"max_duration_minutes": 30},
            },
            "routing": {
                "bug_known_fix": {"phases": ["implementation", "review", "verification", "merge"]}
            },
        },
    }


@pytest.fixture
def base_state() -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "version": 3,
        "system_state": "Running",
        "trust_scores": {"Platform": {"tier": 0, "successful_merges": 0}},
        "pipeline": {"active_workers": {}},
        "daily_counters": {today: {"workers_spawned": 0}},
        "issues": {},
        "rate_limits": {"throttle_level": "green"},
    }


def _ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _mock_popen():
    """Create a mock Popen that returns a running process."""
    mock_proc = MagicMock()
    mock_proc.pid = 12345
    mock_proc.poll.return_value = None
    return mock_proc


# ---------------------------------------------------------------------------
# Worker dispatch (D1-AC02, BS-001)
# ---------------------------------------------------------------------------


class TestDispatchWorker:
    @patch("subprocess.Popen")
    def test_returns_worker_entry(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        result = dispatch_worker("TST-99", "implementation", "Fix the bug", base_config)
        assert isinstance(result, WorkerEntry)
        assert result.issue_id == "TST-99"
        assert result.pid == 12345
        assert result.phase == "implementation"

    @patch("subprocess.Popen")
    def test_uses_claude_print_command(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "implementation", "prompt", base_config)
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "claude"
        assert "--print" in cmd

    @patch("subprocess.Popen")
    def test_worktree_contains_issue_id(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "implementation", "prompt", base_config)
        cmd = mock_popen.call_args[0][0]
        wt_idx = cmd.index("--worktree")
        assert "lacrimosa-TST-42" in cmd[wt_idx + 1]

    @patch("subprocess.Popen")
    def test_prompt_passed_via_p_flag(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "implementation", "Fix the broken event", base_config)
        cmd = mock_popen.call_args[0][0]
        p_idx = cmd.index("-p")
        assert "Fix the broken event" in cmd[p_idx + 1]

    @patch("subprocess.Popen")
    def test_detached_from_session_group(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "implementation", "prompt", base_config)
        assert mock_popen.call_args[1].get("start_new_session") is True

    @patch("subprocess.Popen")
    def test_worktree_name_in_entry(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        entry = dispatch_worker("TST-123", "research", "prompt", base_config)
        assert "lacrimosa-TST-123" in entry.worktree_name


# ---------------------------------------------------------------------------
# Security permissions (SEC-C02)
# ---------------------------------------------------------------------------


class TestSecurityPermissions:
    """SEC-C02: only implementation workers get --dangerously-skip-permissions."""

    @patch("subprocess.Popen")
    def test_implementation_gets_dangerous_flag(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "implementation", "prompt", base_config)
        assert "--dangerously-skip-permissions" in mock_popen.call_args[0][0]

    @patch("subprocess.Popen")
    def test_research_no_dangerous_flag(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "research", "prompt", base_config)
        assert "--dangerously-skip-permissions" not in mock_popen.call_args[0][0]

    @patch("subprocess.Popen")
    def test_architecture_no_dangerous_flag(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "architecture", "prompt", base_config)
        assert "--dangerously-skip-permissions" not in mock_popen.call_args[0][0]

    @patch("subprocess.Popen")
    def test_review_no_dangerous_flag(self, mock_popen, base_config):
        mock_popen.return_value = _mock_popen()
        dispatch_worker("TST-42", "review", "prompt", base_config)
        assert "--dangerously-skip-permissions" not in mock_popen.call_args[0][0]


# ---------------------------------------------------------------------------
# Worker completions (check_completions)
# ---------------------------------------------------------------------------


class TestCheckCompletions:
    def test_completed_worker_detected(self, base_state):
        proc = MagicMock(pid=100)
        proc.poll.return_value = 0
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {
                "domain": "Platform",
                "pid": 100,
                "phase": "implementation",
                "started_at": _ago(10),
                "_proc": proc,
            }
        }
        completed = check_completions(base_state)
        assert len(completed) >= 1
        assert any(w["issue_id"] == "TST-50" for w in completed)

    def test_running_worker_not_in_completions(self, base_state):
        proc = MagicMock()
        proc.poll.return_value = None
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {
                "domain": "Platform",
                "pid": 100,
                "phase": "implementation",
                "started_at": _ago(5),
                "_proc": proc,
            }
        }
        assert len(check_completions(base_state)) == 0

    def test_stalled_worker_detected(self, base_state):
        proc = MagicMock()
        proc.poll.return_value = None
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {
                "domain": "Platform",
                "pid": 100,
                "phase": "implementation",
                "started_at": _ago(120),
                "_proc": proc,
            }
        }
        completed = check_completions(base_state, stall_timeout_minutes=10)
        assert len(completed) >= 1
        assert any(w.get("stalled") for w in completed)

    def test_failed_worker_detected(self, base_state):
        proc = MagicMock()
        proc.poll.return_value = 1
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {
                "domain": "Platform",
                "pid": 100,
                "phase": "implementation",
                "started_at": _ago(10),
                "_proc": proc,
            }
        }
        completed = check_completions(base_state)
        assert any(w.get("failed") for w in completed)


# ---------------------------------------------------------------------------
# Error handling: retry and escalation
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_retry_count_incremented(self, base_state):
        base_state["issues"] = {"TST-50": {"retry_count": 0, "state": "Implementation"}}
        updated = handle_worker_failure("TST-50", base_state, max_retries=3)
        assert updated["issues"]["TST-50"]["retry_count"] == 1

    def test_requeued_under_max_retries(self, base_state):
        base_state["issues"] = {"TST-50": {"retry_count": 1, "state": "Implementation"}}
        updated = handle_worker_failure("TST-50", base_state, max_retries=3)
        assert updated["issues"]["TST-50"]["state"] == "RetryQueued"

    def test_escalated_at_max_retries(self, base_state):
        base_state["issues"] = {"TST-50": {"retry_count": 2, "state": "Implementation"}}
        updated = handle_worker_failure("TST-50", base_state, max_retries=3)
        assert updated["issues"]["TST-50"]["state"] == "Escalated"
        assert updated["issues"]["TST-50"]["retry_count"] == 3


# ---------------------------------------------------------------------------
# State updates after dispatch/completion
# ---------------------------------------------------------------------------


class TestStateUpdates:
    def _make_entry(self, issue_id: str = "TST-99") -> WorkerEntry:
        return WorkerEntry(
            issue_id=issue_id,
            pid=12345,
            worktree_name=f"lacrimosa-{issue_id}",
            phase="implementation",
            started_at=datetime.now(timezone.utc).isoformat(),
            domain="Platform",
        )

    def test_dispatch_updates_active_workers(self, base_state):
        updated = record_dispatch(self._make_entry(), base_state)
        assert "TST-99" in updated["pipeline"]["active_workers"]
        assert updated["pipeline"]["active_workers"]["TST-99"]["pid"] == 12345

    def test_dispatch_increments_daily_counter(self, base_state):
        today = datetime.now().strftime("%Y-%m-%d")
        updated = record_dispatch(self._make_entry(), base_state)
        assert updated["daily_counters"][today]["workers_spawned"] == 1

    def test_completion_removes_from_active_workers(self, base_state):
        base_state["pipeline"]["active_workers"] = {
            "TST-50": {"domain": "Platform", "pid": 100}
        }
        updated = record_completion("TST-50", base_state)
        assert "TST-50" not in updated["pipeline"]["active_workers"]
