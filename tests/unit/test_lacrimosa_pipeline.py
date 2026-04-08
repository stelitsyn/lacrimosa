"""Tests for Lacrimosa pipeline state machine (issue_pipeline table + PipelineManager)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts.lacrimosa_pipeline import (
    PipelineManager,
    InvalidTransition,
    MissingProof,
    VALID_STATES,
    VALID_TRANSITIONS,
    REQUIRED_PROOF,
)


@pytest.fixture
def pm(tmp_path):
    """Create a PipelineManager backed by a temporary SQLite DB."""
    db = tmp_path / "test_pipeline.db"
    return PipelineManager(db_path=db)


# ── Insert tests ──────────────────────────────────────────────────────────────


class TestInsertIssue:
    def test_insert_issue(self, pm: PipelineManager):
        pm.insert_issue("TST-100", "lin_abc123")
        issue = pm.get_issue("TST-100")
        assert issue is not None
        assert issue["identifier"] == "TST-100"
        assert issue["linear_id"] == "lin_abc123"
        assert issue["state"] == "Backlog"
        assert issue["sentinel_origin"] == 0
        assert issue["error_count"] == 0
        assert issue["review_iteration"] == 0
        assert issue["owner"] is None
        assert issue["worker_id"] is None
        assert issue["worktree_path"] is None
        assert issue["pr_number"] is None
        assert issue["review_feedback"] is None
        assert issue["proof"] is None

    def test_insert_sentinel_issue(self, pm: PipelineManager):
        pm.insert_issue("TST-200", "lin_sentinel", sentinel_origin=1)
        issue = pm.get_issue("TST-200")
        assert issue is not None
        assert issue["sentinel_origin"] == 1

    def test_insert_duplicate_raises(self, pm: PipelineManager):
        pm.insert_issue("TST-300", "lin_dup")
        with pytest.raises(Exception):
            pm.insert_issue("TST-300", "lin_dup2")

    def test_get_nonexistent_returns_none(self, pm: PipelineManager):
        assert pm.get_issue("TST-NOPE") is None


# ── Transition tests ──────────────────────────────────────────────────────────


class TestTransitions:
    def test_valid_transition_backlog_to_triaged(self, pm: PipelineManager):
        pm.insert_issue("TST-10", "lin_10")
        pm.transition(
            "TST-10",
            from_state="Backlog",
            to_state="Triaged",
            owner="discovery",
            proof={
                "linear_comment_id": "cmt_1",
                "route_type": "engineering",
                "priority_score": 85,
            },
        )
        issue = pm.get_issue("TST-10")
        assert issue["state"] == "Triaged"
        assert issue["owner"] == "discovery"
        stored_proof = json.loads(issue["proof"])
        assert stored_proof["linear_comment_id"] == "cmt_1"

    def test_invalid_transition_backlog_to_implementing(self, pm: PipelineManager):
        pm.insert_issue("TST-11", "lin_11")
        with pytest.raises(InvalidTransition):
            pm.transition(
                "TST-11",
                from_state="Backlog",
                to_state="Implementing",
                owner="eng",
                proof={"worker_id": "w1", "worktree_path": "/tmp/wt"},
            )

    def test_transition_wrong_current_state(self, pm: PipelineManager):
        pm.insert_issue("TST-12", "lin_12")
        # Issue is in Backlog, but caller claims it's in Triaged
        with pytest.raises(InvalidTransition, match="current state"):
            pm.transition(
                "TST-12",
                from_state="Triaged",
                to_state="Implementing",
                owner="eng",
                proof={"worker_id": "w1", "worktree_path": "/tmp/wt"},
            )

    def test_missing_proof_rejected(self, pm: PipelineManager):
        pm.insert_issue("TST-13", "lin_13")
        # Backlog -> Triaged requires linear_comment_id, route_type, priority_score
        with pytest.raises(MissingProof):
            pm.transition(
                "TST-13",
                from_state="Backlog",
                to_state="Triaged",
                owner="discovery",
                proof={"linear_comment_id": "cmt_1"},  # missing route_type, priority_score
            )

    def test_triaged_to_implementing_requires_worktree(self, pm: PipelineManager):
        pm.insert_issue("TST-14", "lin_14")
        # Move to Triaged first
        pm.transition(
            "TST-14",
            from_state="Backlog",
            to_state="Triaged",
            owner="discovery",
            proof={
                "linear_comment_id": "cmt_1",
                "route_type": "engineering",
                "priority_score": 80,
            },
        )
        # Now attempt Triaged -> Implementing without worktree_path
        with pytest.raises(MissingProof, match="worktree_path"):
            pm.transition(
                "TST-14",
                from_state="Triaged",
                to_state="Implementing",
                owner="eng",
                proof={"worker_id": "w1"},
            )

    def test_transition_to_failed_increments_error_count(self, pm: PipelineManager):
        pm.insert_issue("TST-15", "lin_15")
        # Backlog -> Triaged -> Implementing -> Failed
        pm.transition(
            "TST-15",
            from_state="Backlog",
            to_state="Triaged",
            owner="discovery",
            proof={
                "linear_comment_id": "cmt_1",
                "route_type": "engineering",
                "priority_score": 70,
            },
        )
        pm.transition(
            "TST-15",
            from_state="Triaged",
            to_state="Implementing",
            owner="eng",
            proof={"worker_id": "w1", "worktree_path": "/tmp/wt"},
        )
        pm.transition(
            "TST-15",
            from_state="Implementing",
            to_state="Failed",
            owner="eng",
            proof={"error_message": "build failed", "retry_eligible": True},
        )
        issue = pm.get_issue("TST-15")
        assert issue["state"] == "Failed"
        assert issue["error_count"] == 1

    def test_transition_to_implementing_sets_worker_and_worktree(self, pm: PipelineManager):
        pm.insert_issue("TST-16", "lin_16")
        pm.transition(
            "TST-16",
            from_state="Backlog",
            to_state="Triaged",
            owner="discovery",
            proof={
                "linear_comment_id": "cmt_1",
                "route_type": "engineering",
                "priority_score": 60,
            },
        )
        pm.transition(
            "TST-16",
            from_state="Triaged",
            to_state="Implementing",
            owner="eng",
            proof={"worker_id": "agent-42", "worktree_path": "/tmp/wt-kal16"},
        )
        issue = pm.get_issue("TST-16")
        assert issue["worker_id"] == "agent-42"
        assert issue["worktree_path"] == "/tmp/wt-kal16"

    def test_transition_to_review_pending_sets_pr_number(self, pm: PipelineManager):
        pm.insert_issue("TST-17", "lin_17")
        _advance_to_implementing(pm, "TST-17")
        pm.transition(
            "TST-17",
            from_state="Implementing",
            to_state="ReviewPending",
            owner="eng",
            proof={"pr_number": 42, "pr_url": "https://github.com/org/repo/pull/42"},
        )
        issue = pm.get_issue("TST-17")
        assert issue["pr_number"] == 42

    def test_transition_to_fix_needed_increments_review_iteration(self, pm: PipelineManager):
        pm.insert_issue("TST-18", "lin_18")
        _advance_to_reviewing(pm, "TST-18")
        pm.transition(
            "TST-18",
            from_state="Reviewing",
            to_state="FixNeeded",
            owner="reviewer",
            proof={
                "issues_list": ["fix A", "fix B"],
                "linear_comment_id": "cmt_review",
            },
        )
        issue = pm.get_issue("TST-18")
        assert issue["state"] == "FixNeeded"
        assert issue["review_iteration"] == 1
        feedback = json.loads(issue["review_feedback"])
        assert feedback == ["fix A", "fix B"]

    def test_transition_to_reviewing_sets_reviewer(self, pm: PipelineManager):
        pm.insert_issue("TST-19", "lin_19")
        _advance_to_review_pending(pm, "TST-19")
        pm.transition(
            "TST-19",
            from_state="ReviewPending",
            to_state="Reviewing",
            owner="conductor",
            proof={"reviewer_agent_id": "reviewer-7"},
        )
        issue = pm.get_issue("TST-19")
        assert issue["worker_id"] == "reviewer-7"


# ── Query tests ───────────────────────────────────────────────────────────────


class TestQuery:
    def test_query_by_states(self, pm: PipelineManager):
        pm.insert_issue("TST-A", "lin_a")
        pm.insert_issue("TST-B", "lin_b")
        pm.insert_issue("TST-C", "lin_c")
        # Move TST-B to Triaged
        pm.transition(
            "TST-B",
            from_state="Backlog",
            to_state="Triaged",
            owner="discovery",
            proof={
                "linear_comment_id": "cmt_1",
                "route_type": "engineering",
                "priority_score": 50,
            },
        )
        backlog = pm.query(states=["Backlog"])
        triaged = pm.query(states=["Triaged"])
        assert len(backlog) == 2
        assert len(triaged) == 1
        assert triaged[0]["identifier"] == "TST-B"

    def test_query_sentinel_first(self, pm: PipelineManager):
        pm.insert_issue("TST-REG1", "lin_r1", sentinel_origin=0)
        pm.insert_issue("TST-SENT1", "lin_s1", sentinel_origin=1)
        pm.insert_issue("TST-REG2", "lin_r2", sentinel_origin=0)
        results = pm.query(states=["Backlog"])
        # Sentinel issue should be first
        assert results[0]["identifier"] == "TST-SENT1"

    def test_query_sentinel_only(self, pm: PipelineManager):
        pm.insert_issue("TST-R1", "lin_r1", sentinel_origin=0)
        pm.insert_issue("TST-S1", "lin_s1", sentinel_origin=1)
        results = pm.query(states=["Backlog"], sentinel_only=True)
        assert len(results) == 1
        assert results[0]["identifier"] == "TST-S1"


# ── Active count & completed_since ────────────────────────────────────────────


class TestAggregates:
    def test_active_count(self, pm: PipelineManager):
        pm.insert_issue("TST-X1", "lin_x1")
        pm.insert_issue("TST-X2", "lin_x2")
        assert pm.active_count() == 2
        # Move one to Done via full lifecycle
        _advance_to_done(pm, "TST-X1")
        assert pm.active_count() == 1

    def test_completed_since(self, pm: PipelineManager):
        pm.insert_issue("TST-Y1", "lin_y1")
        before = datetime.now(timezone.utc).isoformat()
        _advance_to_done(pm, "TST-Y1")
        results = pm.completed_since(before)
        assert len(results) == 1
        assert results[0]["identifier"] == "TST-Y1"


# ── Full lifecycle tests ──────────────────────────────────────────────────────


class TestFullLifecycle:
    def test_full_lifecycle(self, pm: PipelineManager):
        """Backlog -> Triaged -> Implementing -> ReviewPending -> Reviewing -> MergeReady -> Merging -> Verifying -> Done."""
        pm.insert_issue("TST-LIFE", "lin_life")
        _advance_to_done(pm, "TST-LIFE")
        issue = pm.get_issue("TST-LIFE")
        assert issue["state"] == "Done"

    def test_review_fix_loop(self, pm: PipelineManager):
        """Reviewing -> FixNeeded -> Implementing -> ReviewPending -> Reviewing (loop)."""
        pm.insert_issue("TST-FIX", "lin_fix")
        _advance_to_reviewing(pm, "TST-FIX")

        # First review: FixNeeded
        pm.transition(
            "TST-FIX",
            from_state="Reviewing",
            to_state="FixNeeded",
            owner="reviewer",
            proof={
                "issues_list": ["missing tests"],
                "linear_comment_id": "cmt_r1",
            },
        )
        issue = pm.get_issue("TST-FIX")
        assert issue["state"] == "FixNeeded"
        assert issue["review_iteration"] == 1

        # Fix: FixNeeded -> Implementing
        pm.transition(
            "TST-FIX",
            from_state="FixNeeded",
            to_state="Implementing",
            owner="eng",
            proof={"worker_id": "agent-fix", "worktree_path": "/tmp/wt-fix"},
        )

        # Re-submit: Implementing -> ReviewPending
        pm.transition(
            "TST-FIX",
            from_state="Implementing",
            to_state="ReviewPending",
            owner="eng",
            proof={"pr_number": 99, "pr_url": "https://github.com/org/repo/pull/99"},
        )

        # Re-review: ReviewPending -> Reviewing
        pm.transition(
            "TST-FIX",
            from_state="ReviewPending",
            to_state="Reviewing",
            owner="conductor",
            proof={"reviewer_agent_id": "reviewer-9"},
        )
        issue = pm.get_issue("TST-FIX")
        assert issue["state"] == "Reviewing"
        # review_iteration should still be 1 (only incremented on FixNeeded)
        assert issue["review_iteration"] == 1


# ── Transition graph completeness ─────────────────────────────────────────────


class TestTransitionGraphCompleteness:
    def test_all_valid_states_have_transitions(self):
        """Every non-terminal state should appear as a key in VALID_TRANSITIONS."""
        terminal = {"Done", "Escalated"}
        for state in VALID_STATES:
            if state not in terminal:
                assert state in VALID_TRANSITIONS, f"{state} missing from VALID_TRANSITIONS"

    def test_all_transition_targets_are_valid_states(self):
        """Every target in VALID_TRANSITIONS must be a valid state."""
        for from_state, targets in VALID_TRANSITIONS.items():
            for to_state in targets:
                assert (
                    to_state in VALID_STATES
                ), f"{to_state} (from {from_state}) not in VALID_STATES"

    def test_required_proof_keys_cover_all_non_failed_transitions(self):
        """Each explicit transition (not *->Failed) should have proof requirements."""
        for from_state, targets in VALID_TRANSITIONS.items():
            for to_state in targets:
                if to_state == "Failed":
                    continue  # wildcard, checked separately
                key = (from_state, to_state)
                assert key in REQUIRED_PROOF, f"Missing REQUIRED_PROOF for {key}"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _advance_to_triaged(pm: PipelineManager, identifier: str) -> None:
    pm.transition(
        identifier,
        from_state="Backlog",
        to_state="Triaged",
        owner="discovery",
        proof={
            "linear_comment_id": "cmt_auto",
            "route_type": "engineering",
            "priority_score": 75,
        },
    )


def _advance_to_implementing(pm: PipelineManager, identifier: str) -> None:
    _advance_to_triaged(pm, identifier)
    pm.transition(
        identifier,
        from_state="Triaged",
        to_state="Implementing",
        owner="eng",
        proof={"worker_id": "agent-1", "worktree_path": "/tmp/wt"},
    )


def _advance_to_review_pending(pm: PipelineManager, identifier: str) -> None:
    _advance_to_implementing(pm, identifier)
    pm.transition(
        identifier,
        from_state="Implementing",
        to_state="ReviewPending",
        owner="eng",
        proof={"pr_number": 1, "pr_url": "https://github.com/org/repo/pull/1"},
    )


def _advance_to_reviewing(pm: PipelineManager, identifier: str) -> None:
    _advance_to_review_pending(pm, identifier)
    pm.transition(
        identifier,
        from_state="ReviewPending",
        to_state="Reviewing",
        owner="conductor",
        proof={"reviewer_agent_id": "reviewer-1"},
    )


def _advance_to_merge_ready(pm: PipelineManager, identifier: str) -> None:
    _advance_to_reviewing(pm, identifier)
    pm.transition(
        identifier,
        from_state="Reviewing",
        to_state="MergeReady",
        owner="reviewer",
        proof={"review_verdict": "approved", "linear_comment_id": "cmt_merge"},
    )


def _advance_to_merging(pm: PipelineManager, identifier: str) -> None:
    _advance_to_merge_ready(pm, identifier)
    pm.transition(
        identifier,
        from_state="MergeReady",
        to_state="Merging",
        owner="conductor",
        proof={"rebase_clean": True, "ci_status": "passed"},
    )


def _advance_to_verifying(pm: PipelineManager, identifier: str) -> None:
    _advance_to_merging(pm, identifier)
    pm.transition(
        identifier,
        from_state="Merging",
        to_state="Verifying",
        owner="conductor",
        proof={"merge_sha": "abc123", "merged_at": "2026-03-26T12:00:00Z"},
    )


def _advance_to_done(pm: PipelineManager, identifier: str) -> None:
    _advance_to_verifying(pm, identifier)
    pm.transition(
        identifier,
        from_state="Verifying",
        to_state="Done",
        owner="conductor",
        proof={
            "verification_result": "staging_verified",
            "linear_status_updated": True,
        },
    )
