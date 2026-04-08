"""Tests for Lacrimosa verification gates — test suite, staging, browser QA."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.lacrimosa_conductor import (
    determine_verification_gates,
    run_all_verification_gates,
    run_verification_gate,
    transition_after_review,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_config() -> dict[str, Any]:
    return {
        "lifecycle": {
            "phases": {
                "verification": {
                    "gates": {
                        "test_suite": {
                            "description": "Run unit + integration tests",
                            "always": True,
                            "commands": ["./run_unit_tests.sh", "./run_integration_tests.sh"],
                        },
                        "api_staging": {
                            "description": "Deploy to staging + verify API",
                            "when": "backend files changed",
                        },
                        "browser_qa": {
                            "description": "Browser QA on staging",
                            "when": "frontend files changed",
                        },
                    }
                }
            }
        }
    }


@pytest.fixture
def base_state() -> dict[str, Any]:
    return {
        "version": 3,
        "issues": {
            "TST-99": {
                "state": "Review",
                "lifecycle": "feature_with_spec",
                "phases_completed": ["implementation", "review"],
                "phases_remaining": ["verification", "merge"],
                "priority_score": 5,
                "project": "Platform",
                "pr_number": 800,
            }
        },
        "pipeline": {
            "active_workers": {
                "TST-99": {
                    "phase": "review",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        },
    }


# ---------------------------------------------------------------------------
# determine_verification_gates
# ---------------------------------------------------------------------------


class TestDetermineVerificationGates:
    def test_test_suite_always_included(self, base_config: dict) -> None:
        gates = determine_verification_gates([], base_config)
        assert len(gates) >= 1
        assert gates[0]["name"] == "test_suite"
        assert "./run_unit_tests.sh" in gates[0]["commands"]
        assert "./run_integration_tests.sh" in gates[0]["commands"]

    def test_backend_files_trigger_api_staging(self, base_config: dict) -> None:
        files = ["src/api/routes/suggestions.py", "tests/test_suggestions.py"]
        gates = determine_verification_gates(files, base_config)
        names = [g["name"] for g in gates]
        assert "test_suite" in names
        assert "api_staging" in names

    def test_frontend_files_trigger_browser_qa(self, base_config: dict) -> None:
        files = ["frontend/components/app/SuggestionCards.tsx"]
        gates = determine_verification_gates(files, base_config)
        names = [g["name"] for g in gates]
        assert "test_suite" in names
        assert "browser_qa" in names

    def test_no_backend_no_frontend_only_test_suite(self, base_config: dict) -> None:
        files = ["scripts/lacrimosa_dashboard.py"]
        gates = determine_verification_gates(files, base_config)
        assert len(gates) == 1
        assert gates[0]["name"] == "test_suite"

    def test_fullstack_change_triggers_all_gates(self, base_config: dict) -> None:
        files = [
            "src/api/routes/foo.py",
            "frontend/components/Bar.tsx",
        ]
        gates = determine_verification_gates(files, base_config)
        names = [g["name"] for g in gates]
        assert "test_suite" in names
        assert "api_staging" in names
        assert "browser_qa" in names

    def test_empty_config_returns_default_test_suite(self) -> None:
        gates = determine_verification_gates([], {})
        assert len(gates) == 1
        assert gates[0]["name"] == "test_suite"


# ---------------------------------------------------------------------------
# run_verification_gate
# ---------------------------------------------------------------------------


class TestRunVerificationGate:
    @patch("scripts.lacrimosa_conductor.subprocess.run")
    def test_passing_gate(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="OK\n", stderr="")
        gate = {"name": "test_suite", "commands": ["./run_unit_tests.sh"]}
        result = run_verification_gate(gate)
        assert result["passed"] is True
        assert result["gate"] == "test_suite"
        assert len(result["results"]) == 1

    @patch("scripts.lacrimosa_conductor.subprocess.run")
    def test_failing_gate(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
        gate = {"name": "test_suite", "commands": ["./run_unit_tests.sh"]}
        result = run_verification_gate(gate)
        assert result["passed"] is False
        assert result["results"][0]["exit_code"] == 1

    @patch("scripts.lacrimosa_conductor.subprocess.run")
    def test_stops_on_first_failure(self, mock_run: MagicMock) -> None:
        """Second command should NOT run if first fails."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAIL")
        gate = {
            "name": "test_suite",
            "commands": ["./run_unit_tests.sh", "./run_integration_tests.sh"],
        }
        result = run_verification_gate(gate)
        assert result["passed"] is False
        assert len(result["results"]) == 1  # Only first ran
        mock_run.assert_called_once()

    @patch("scripts.lacrimosa_conductor.subprocess.run")
    def test_both_commands_pass(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        gate = {
            "name": "test_suite",
            "commands": ["./run_unit_tests.sh", "./run_integration_tests.sh"],
        }
        result = run_verification_gate(gate)
        assert result["passed"] is True
        assert len(result["results"]) == 2
        assert mock_run.call_count == 2

    @patch("scripts.lacrimosa_conductor.subprocess.run")
    def test_timeout_handled(self, mock_run: MagicMock) -> None:
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=600)
        gate = {"name": "test_suite", "commands": ["./slow_test.sh"]}
        result = run_verification_gate(gate)
        assert result["passed"] is False
        assert "Timed out" in result["results"][0].get("error", "")


# ---------------------------------------------------------------------------
# run_all_verification_gates
# ---------------------------------------------------------------------------


class TestRunAllVerificationGates:
    @patch("scripts.lacrimosa_conductor.run_verification_gate")
    def test_all_gates_pass(self, mock_gate: MagicMock, base_config: dict) -> None:
        mock_gate.return_value = {"gate": "test_suite", "passed": True, "results": []}
        result = run_all_verification_gates("TST-99", [], base_config)
        assert result["passed"] is True
        assert result["failed_gate"] is None

    @patch("scripts.lacrimosa_conductor.run_verification_gate")
    def test_gate_failure_stops_chain(self, mock_gate: MagicMock, base_config: dict) -> None:
        mock_gate.return_value = {"gate": "test_suite", "passed": False, "results": []}
        result = run_all_verification_gates("TST-99", [], base_config)
        assert result["passed"] is False
        assert result["failed_gate"] == "test_suite"

    def test_browser_qa_skipped_as_agent_task(self, base_config: dict) -> None:
        """browser_qa and staging_deploy require agent dispatch, not subprocess."""
        files = ["frontend/components/Foo.tsx"]
        with patch("scripts.lacrimosa_conductor.run_verification_gate") as mock_gate:
            mock_gate.return_value = {"gate": "test_suite", "passed": True, "results": []}
            result = run_all_verification_gates("TST-99", files, base_config)
        # browser_qa should be marked skipped, not failed
        browser = [g for g in result["gates"] if g["gate"] == "browser_qa"]
        assert len(browser) == 1
        assert browser[0].get("skipped") is True

    @patch("scripts.lacrimosa_conductor.run_verification_gate")
    def test_no_extra_gates_for_non_matching_files(
        self, mock_gate: MagicMock, base_config: dict
    ) -> None:
        """Only test_suite runs when files don't match backend/frontend patterns."""
        mock_gate.return_value = {"gate": "test_suite", "passed": True, "results": []}
        files = ["README.md"]
        result = run_all_verification_gates("TST-99", files, base_config)
        assert result["passed"] is True
        # Only test_suite should have been called (no staging/browser)
        mock_gate.assert_called_once()


# ---------------------------------------------------------------------------
# transition_after_review
# ---------------------------------------------------------------------------


class TestTransitionAfterReview:
    @patch("scripts.lacrimosa_conductor.run_all_verification_gates")
    def test_verification_passes_transitions_to_merging(
        self,
        mock_verify: MagicMock,
        base_state: dict,
        base_config: dict,
    ) -> None:
        mock_verify.return_value = {
            "passed": True,
            "gates": [{"gate": "test_suite", "passed": True}],
            "failed_gate": None,
        }
        new_state = transition_after_review(
            "TST-99",
            base_state,
            base_config,
            changed_files=["src/foo.py"],
        )
        assert new_state["issues"]["TST-99"]["state"] == "Merging"
        assert "verification" in new_state["issues"]["TST-99"]["phases_completed"]

    @patch("scripts.lacrimosa_conductor.run_all_verification_gates")
    def test_verification_fails_back_to_implementation(
        self,
        mock_verify: MagicMock,
        base_state: dict,
        base_config: dict,
    ) -> None:
        mock_verify.return_value = {
            "passed": False,
            "gates": [{"gate": "test_suite", "passed": False}],
            "failed_gate": "test_suite",
        }
        new_state = transition_after_review(
            "TST-99",
            base_state,
            base_config,
            changed_files=["src/foo.py"],
        )
        assert new_state["issues"]["TST-99"]["state"] == "Implementation"
        assert new_state["issues"]["TST-99"]["verification_result"]["passed"] is False
        assert new_state["issues"]["TST-99"]["verification_result"]["failed_gate"] == "test_suite"

    @patch("scripts.lacrimosa_conductor.run_all_verification_gates")
    def test_verification_result_recorded_in_issue(
        self,
        mock_verify: MagicMock,
        base_state: dict,
        base_config: dict,
    ) -> None:
        mock_verify.return_value = {
            "passed": True,
            "gates": [{"gate": "test_suite", "passed": True}],
            "failed_gate": None,
        }
        new_state = transition_after_review(
            "TST-99",
            base_state,
            base_config,
        )
        vr = new_state["issues"]["TST-99"]["verification_result"]
        assert vr["passed"] is True
        assert vr["gates_run"] == 1
        assert "timestamp" in vr
