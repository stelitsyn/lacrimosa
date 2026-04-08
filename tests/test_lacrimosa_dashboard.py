"""
TDD tests for Lacrimosa Dashboard — phase_times merging and rendering.

Covers the regression where issues with phases_completed but incomplete
phase_times would show only partial phase details on the dashboard.
"""

from __future__ import annotations

import pytest

from scripts.lacrimosa_dashboard import merge_phase_times, render_dashboard


# ---------------------------------------------------------------------------
# Fixtures — representative issue dicts from state.json
# ---------------------------------------------------------------------------


@pytest.fixture
def good_issue() -> dict:
    """TST-21 style: full phase_times for all phases_completed."""
    return {
        "state": "Completed",
        "lifecycle": "feature_new",
        "phases_completed": [
            "research",
            "implementation",
            "review",
            "review-fix",
            "merge",
        ],
        "priority_score": 6,
        "project": "Platform",
        "pr_number": 778,
        "review_iteration": 2,
        "completed_at": "2026-03-20T16:06:58.652483+00:00",
        "pipeline_entered_at": "2026-03-20T15:36:00.000+00:00",
        "phase_times": {
            "research": {
                "started_at": "2026-03-20T15:36:00+00:00",
                "completed_at": "2026-03-20T15:39:00+00:00",
                "tokens": 101018,
                "cost_usd": 7.44,
            },
            "implementation": {
                "started_at": "2026-03-20T15:40:00+00:00",
                "completed_at": "2026-03-20T15:47:00+00:00",
                "tokens": 73062,
                "cost_usd": 5.38,
            },
            "review": {
                "started_at": "2026-03-20T15:48:00+00:00",
                "completed_at": "2026-03-20T15:53:00+00:00",
                "tokens": 91278,
                "cost_usd": 6.72,
                "findings": 5,
            },
            "review-fix": {
                "started_at": "2026-03-20T15:53:00+00:00",
                "completed_at": "2026-03-20T16:06:00+00:00",
                "tokens": 60165,
                "cost_usd": 4.43,
            },
            "merge": {
                "started_at": "2026-03-20T16:06:00+00:00",
                "completed_at": "2026-03-20T16:06:30+00:00",
            },
        },
    }


@pytest.fixture
def bad_issue_impl_only() -> dict:
    """TST-899 style: phase_times has only implementation, but phases_completed
    lists implementation, review, merge."""
    return {
        "state": "Completed",
        "lifecycle": "bug_known_fix",
        "phases_completed": ["implementation", "review", "merge"],
        "priority_score": 6,
        "project": "Marketing",
        "pr_number": 792,
        "pipeline_entered_at": "2026-03-20T23:07:57.885599+00:00",
        "completed_at": "2026-03-20T23:13:45.048813+00:00",
        "review_iteration": 1,
        "phase_times": {
            "implementation": {
                "started_at": "2026-03-20T23:07:57.885599+00:00",
                "completed_at": "2026-03-20T23:10:31.737097+00:00",
                "tokens": 28645,
                "cost_usd": 0.43,
            },
        },
    }


@pytest.fixture
def bad_issue_research_only() -> dict:
    """TST-13 style: investigation issue, only research phase_times entry."""
    return {
        "state": "Completed",
        "lifecycle": "investigation",
        "phases_completed": ["research"],
        "priority_score": 5,
        "project": "Marketing",
        "completed_at": "2026-03-20T23:02:55.681540+00:00",
        "phase_times": {
            "research": {
                "started_at": "2026-03-20T22:56:35.622119+00:00",
                "completed_at": "2026-03-20T23:02:55.681540+00:00",
                "tokens": 106244,
                "cost_usd": 1.59,
            },
        },
    }


@pytest.fixture
def bad_issue_partial() -> dict:
    """TST-901 style: phase_times has implementation+review+review-fix,
    but phases_completed also has merge (and a review-1-rejected)."""
    return {
        "state": "Completed",
        "lifecycle": "bug_known_fix",
        "phases_completed": [
            "implementation",
            "review-1-rejected",
            "review-fix",
            "merge",
        ],
        "priority_score": 5,
        "project": "Marketing",
        "pr_number": 793,
        "completed_at": "2026-03-21T00:15:47.577975+00:00",
        "phase_times": {
            "implementation": {
                "started_at": "2026-03-20T23:42:28+00:00",
                "completed_at": "2026-03-20T23:47:04.095877+00:00",
                "tokens": 64288,
                "cost_usd": 0.96,
            },
            "review": {
                "started_at": "2026-03-20T23:50:22.192533+00:00",
                "completed_at": "2026-03-20T23:50:22.192533+00:00",
                "findings": 1,
                "verdict": "REQUEST_CHANGES",
            },
            "review-fix": {
                "started_at": "2026-03-20T23:51:00+00:00",
                "completed_at": "2026-03-21T00:15:00.680532+00:00",
                "tokens": 77172,
            },
        },
    }


@pytest.fixture
def issue_no_phase_times() -> dict:
    """Older issue with no phase_times at all — only phases_completed."""
    return {
        "state": "Completed",
        "lifecycle": "feature_with_spec",
        "phases_completed": ["implementation", "review", "merge"],
        "priority_score": 5,
        "project": "Platform",
        "pr_number": 764,
        "completed_at": "2026-03-13T10:52:00.000Z",
    }


@pytest.fixture
def issue_no_phases_completed() -> dict:
    """Edge case: phase_times present but no phases_completed list."""
    return {
        "state": "Completed",
        "lifecycle": "feature_new",
        "pr_number": 100,
        "completed_at": "2026-03-20T10:00:00+00:00",
        "phase_times": {
            "implementation": {
                "started_at": "2026-03-20T09:00:00+00:00",
                "completed_at": "2026-03-20T09:30:00+00:00",
                "tokens": 50000,
                "cost_usd": 3.0,
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests — merge_phase_times
# ---------------------------------------------------------------------------


class TestMergePhaseTimesGoodIssue:
    """When phase_times already covers all phases_completed, return as-is."""

    def test_returns_all_phases(self, good_issue: dict) -> None:
        result = merge_phase_times(good_issue)
        assert set(result.keys()) == {
            "research",
            "implementation",
            "review",
            "review-fix",
            "merge",
        }

    def test_preserves_existing_data(self, good_issue: dict) -> None:
        result = merge_phase_times(good_issue)
        assert result["research"]["tokens"] == 101018
        assert result["implementation"]["cost_usd"] == 5.38
        assert result["review"]["findings"] == 5

    def test_no_synthetic_markers(self, good_issue: dict) -> None:
        """No phase should have the _synthetic marker when data is complete."""
        result = merge_phase_times(good_issue)
        for phase_data in result.values():
            assert "_synthetic" not in phase_data


class TestMergePhaseTimesMissingPhases:
    """When phases_completed has phases not in phase_times, synthesize them."""

    def test_adds_missing_review_and_merge(self, bad_issue_impl_only: dict) -> None:
        result = merge_phase_times(bad_issue_impl_only)
        assert "review" in result
        assert "merge" in result

    def test_synthetic_phases_marked(self, bad_issue_impl_only: dict) -> None:
        result = merge_phase_times(bad_issue_impl_only)
        assert result["review"].get("_synthetic") is True
        assert result["merge"].get("_synthetic") is True

    def test_existing_phase_preserved(self, bad_issue_impl_only: dict) -> None:
        result = merge_phase_times(bad_issue_impl_only)
        assert result["implementation"]["tokens"] == 28645
        assert result["implementation"]["cost_usd"] == 0.43
        assert "_synthetic" not in result["implementation"]

    def test_total_phase_count(self, bad_issue_impl_only: dict) -> None:
        result = merge_phase_times(bad_issue_impl_only)
        assert len(result) == 3  # implementation, review, merge

    def test_partial_missing_merge(self, bad_issue_partial: dict) -> None:
        """TST-901: review-1-rejected in phases_completed should appear,
        merge should be synthesized."""
        result = merge_phase_times(bad_issue_partial)
        assert "merge" in result
        assert result["merge"].get("_synthetic") is True
        # review-1-rejected is in phases_completed but not in phase_times
        assert "review-1-rejected" in result
        assert result["review-1-rejected"].get("_synthetic") is True

    def test_existing_review_not_overwritten(self, bad_issue_partial: dict) -> None:
        result = merge_phase_times(bad_issue_partial)
        # The "review" entry from phase_times should be preserved (not overwritten)
        assert result["review"]["findings"] == 1
        assert "_synthetic" not in result["review"]


class TestMergePhaseTimesNoData:
    """When there are no phase_times at all, synthesize from phases_completed."""

    def test_creates_entries_from_phases_completed(
        self,
        issue_no_phase_times: dict,
    ) -> None:
        result = merge_phase_times(issue_no_phase_times)
        assert set(result.keys()) == {"implementation", "review", "merge"}

    def test_all_are_synthetic(self, issue_no_phase_times: dict) -> None:
        result = merge_phase_times(issue_no_phase_times)
        for phase_data in result.values():
            assert phase_data.get("_synthetic") is True

    def test_empty_when_nothing(self) -> None:
        """If neither phase_times nor phases_completed, return empty dict."""
        result = merge_phase_times({"state": "Completed"})
        assert result == {}


class TestMergePhaseTimesEdgeCases:
    """Edge cases for robustness."""

    def test_no_phases_completed_returns_phase_times(
        self,
        issue_no_phases_completed: dict,
    ) -> None:
        result = merge_phase_times(issue_no_phases_completed)
        assert "implementation" in result
        assert result["implementation"]["tokens"] == 50000

    def test_phase_order_preserved(self, bad_issue_impl_only: dict) -> None:
        """Phases should be in canonical order (research, impl, review, merge)."""
        result = merge_phase_times(bad_issue_impl_only)
        keys = list(result.keys())
        assert keys == ["implementation", "review", "merge"]

    def test_research_only_issue(self, bad_issue_research_only: dict) -> None:
        """TST-13 investigation: only research — should return as-is."""
        result = merge_phase_times(bad_issue_research_only)
        assert len(result) == 1
        assert "research" in result
        assert "_synthetic" not in result["research"]


# ---------------------------------------------------------------------------
# Tests — render_dashboard with merged phase_times
# ---------------------------------------------------------------------------


class TestDashboardRendering:
    """Integration tests: verify the dashboard HTML contains phase details
    for issues that previously showed only compact summaries."""

    @staticmethod
    def _minimal_state(issues: dict) -> dict:
        """Build a minimal state dict sufficient for render_dashboard."""
        return {
            "version": 3,
            "system_state": "Running",
            "last_poll": "2026-03-21T00:00:00+00:00",
            "trust_scores": {},
            "issues": issues,
            "pipeline": {"active_workers": {}},
            "discovery": {},
            "daily_counters": {},
        }

    def test_bad_issue_shows_phase_bar(self, bad_issue_impl_only: dict) -> None:
        """An issue with partial phase_times should still render the full
        phase bar, not the compact summary row."""
        state = self._minimal_state({"TST-899": bad_issue_impl_only})
        html = render_dashboard(state)
        # The compact row has "Completed" as a text span; full row has phase table
        # Check that all three completed phases appear in the output
        assert "Implement" in html
        assert "Review" in html
        assert "Merge" in html

    def test_issue_no_phase_times_shows_phases(
        self,
        issue_no_phase_times: dict,
    ) -> None:
        """An issue with zero phase_times but phases_completed should show
        phase details, not the compact summary."""
        state = self._minimal_state({"TST-7": issue_no_phase_times})
        html = render_dashboard(state)
        assert "Implement" in html
        assert "Review" in html
        assert "Merge" in html

    def test_good_issue_unchanged(self, good_issue: dict) -> None:
        """Issues with full phase_times should render identically."""
        state = self._minimal_state({"TST-21": good_issue})
        html = render_dashboard(state)
        assert "Research" in html
        assert "Implement" in html
        assert "Review" in html
        assert "Fix Findings" in html
        assert "Merge" in html
