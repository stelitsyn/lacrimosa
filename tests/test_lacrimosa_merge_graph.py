"""TDD tests for merge dependency graph."""

from __future__ import annotations


from scripts.lacrimosa_merge_graph import (
    build_merge_graph,
    check_file_overlap,
    check_file_overlap_enhanced,
    find_orphaned_worktrees,
    get_mergeable,
)


class TestBuildMergeGraph:
    def test_no_overlap_all_ready(self):
        prs = [
            {"pr": 850, "files": ["auth.py", "utils.py"]},
            {"pr": 851, "files": ["models.py", "schema.py"]},
        ]
        graph = build_merge_graph(prs)
        assert all(e["status"] == "ready" for e in graph)
        assert all(e["depends_on"] == [] for e in graph)

    def test_overlap_creates_dependency(self):
        prs = [
            {"pr": 850, "files": ["auth.py", "utils.py"]},
            {"pr": 852, "files": ["utils.py", "routes.py"]},
        ]
        graph = build_merge_graph(prs)
        assert graph[0]["status"] == "ready"
        assert graph[1]["status"] == "blocked"
        assert graph[1]["depends_on"] == [850]

    def test_transitive_dependency(self):
        prs = [
            {"pr": 850, "files": ["a.py"]},
            {"pr": 851, "files": ["a.py", "b.py"]},
            {"pr": 852, "files": ["b.py"]},
        ]
        graph = build_merge_graph(prs)
        assert graph[0]["depends_on"] == []
        assert graph[1]["depends_on"] == [850]
        assert graph[2]["depends_on"] == [851]

    def test_empty_input(self):
        assert build_merge_graph([]) == []

    def test_single_pr(self):
        graph = build_merge_graph([{"pr": 1, "files": ["a.py"]}])
        assert len(graph) == 1
        assert graph[0]["status"] == "ready"


class TestGetMergeable:
    def test_ready_items_returned(self):
        queue = [
            {"pr": 850, "depends_on": [], "status": "ready"},
            {"pr": 851, "depends_on": [850], "status": "blocked"},
        ]
        result = get_mergeable(queue)
        assert len(result) == 1
        assert result[0]["pr"] == 850

    def test_blocked_becomes_mergeable_after_dependency_merged(self):
        queue = [
            {"pr": 850, "depends_on": [], "status": "merged"},
            {"pr": 851, "depends_on": [850], "status": "blocked"},
        ]
        result = get_mergeable(queue)
        assert len(result) == 1
        assert result[0]["pr"] == 851

    def test_multiple_independent_ready(self):
        queue = [
            {"pr": 850, "depends_on": [], "status": "ready"},
            {"pr": 851, "depends_on": [], "status": "ready"},
        ]
        result = get_mergeable(queue)
        assert len(result) == 2

    def test_partial_dependency_not_mergeable(self):
        queue = [
            {"pr": 850, "depends_on": [], "status": "ready"},
            {"pr": 851, "depends_on": [], "status": "merged"},
            {"pr": 852, "depends_on": [850, 851], "status": "blocked"},
        ]
        result = get_mergeable(queue)
        # 852 depends on 850 (not merged) and 851 (merged) — NOT mergeable
        prs = [r["pr"] for r in result]
        assert 852 not in prs
        assert 850 in prs


class TestCheckFileOverlap:
    def test_no_overlap_returns_clear(self):
        result = check_file_overlap(
            new_files=["c.py"],
            active_workers={"w1": {"estimated_files": ["a.py", "b.py"]}},
        )
        assert result[0] == "CLEAR"

    def test_overlap_returns_blocked(self):
        result = check_file_overlap(
            new_files=["a.py", "c.py"],
            active_workers={"w1": {"estimated_files": ["a.py", "b.py"]}},
        )
        assert result[0] == "BLOCKED"
        assert "a.py" in result[1]

    def test_empty_workers_returns_clear(self):
        result = check_file_overlap(new_files=["a.py"], active_workers={})
        assert result[0] == "CLEAR"


class TestCheckFileOverlapEnhanced:
    def test_delay_on_recently_merged_overlap(self):
        result = check_file_overlap_enhanced(
            new_files=["routes.py"],
            active_workers={},
            recently_merged_files=["routes.py", "auth.py"],
        )
        assert result[0] == "DELAY"

    def test_clear_when_no_recent_merge_overlap(self):
        result = check_file_overlap_enhanced(
            new_files=["models.py"],
            active_workers={},
            recently_merged_files=["routes.py"],
        )
        assert result[0] == "CLEAR"

    def test_blocked_takes_priority_over_delay(self):
        result = check_file_overlap_enhanced(
            new_files=["a.py"],
            active_workers={"w1": {"estimated_files": ["a.py"]}},
            recently_merged_files=["a.py"],
        )
        assert result[0] == "BLOCKED"


class TestFindOrphanedWorktrees:
    def test_finds_old_orphans(self):
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        worktrees = [
            {"path": "/tmp/wt1", "branch": "prj-old", "created": old},
        ]
        orphans = find_orphaned_worktrees(worktrees, active_branches=set(), max_age_hours=24)
        assert orphans == ["/tmp/wt1"]

    def test_ignores_active_branches(self):
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        worktrees = [
            {"path": "/tmp/wt1", "branch": "prj-active", "created": old},
        ]
        orphans = find_orphaned_worktrees(
            worktrees, active_branches={"prj-active"}, max_age_hours=24
        )
        assert orphans == []

    def test_ignores_young_worktrees(self):
        from datetime import datetime, timezone

        recent = datetime.now(timezone.utc).isoformat()
        worktrees = [
            {"path": "/tmp/wt1", "branch": "prj-new", "created": recent},
        ]
        orphans = find_orphaned_worktrees(worktrees, active_branches=set(), max_age_hours=24)
        assert orphans == []
