"""Merge dependency graph for parallel PR safety."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_merge_graph(prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build dependency graph from file overlap.

    Each PR dict must have 'pr' (int) and 'files' (list[str]).
    Returns list with added 'depends_on' and 'status' fields.
    """
    queue: list[dict[str, Any]] = []
    for pr_info in prs:
        pr_files = set(pr_info["files"])
        depends_on: list[int] = []
        for other in queue:
            if pr_files & set(other["files"]):
                depends_on.append(other["pr"])
        queue.append({
            "pr": pr_info["pr"],
            "files": pr_info["files"],
            "depends_on": depends_on,
            "status": "ready" if not depends_on else "blocked",
        })
    return queue


def get_mergeable(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return PRs whose dependencies are all merged."""
    merged = {e["pr"] for e in queue if e["status"] == "merged"}
    return [
        e for e in queue
        if e["status"] == "ready"
        or (e["status"] == "blocked" and set(e["depends_on"]).issubset(merged))
    ]


def check_file_overlap(
    new_files: list[str],
    active_workers: dict[str, dict[str, Any]],
) -> tuple[str, str | None]:
    """Check if new files overlap with active workers."""
    new_set = set(new_files)
    for wk_id, wk in active_workers.items():
        overlap = new_set & set(wk.get("estimated_files", []))
        if overlap:
            return ("BLOCKED", f"File overlap with {wk_id}: {overlap}")
    return ("CLEAR", None)


def check_file_overlap_enhanced(
    new_files: list[str],
    active_workers: dict[str, dict[str, Any]],
    recently_merged_files: list[str] | None = None,
) -> tuple[str, str | None]:
    """Check file overlap against active workers AND recent merges."""
    new_set = set(new_files)
    for wk_id, wk in active_workers.items():
        overlap = new_set & set(wk.get("estimated_files", []))
        if overlap:
            return ("BLOCKED", f"File overlap with {wk_id}: {overlap}")
    if recently_merged_files:
        overlap = new_set & set(recently_merged_files)
        if overlap:
            return ("DELAY", f"Files recently merged, wait for rebase: {overlap}")
    return ("CLEAR", None)


def find_orphaned_worktrees(
    worktree_list: list[dict[str, str]],
    active_branches: set[str],
    max_age_hours: int = 24,
) -> list[str]:
    """Return worktree paths that have no active worker and exceed max age."""
    now = datetime.now(timezone.utc)
    orphans: list[str] = []
    for wt in worktree_list:
        if wt.get("branch") not in active_branches:
            created = wt.get("created")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_hours = (now - dt).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        orphans.append(wt["path"])
                except (ValueError, TypeError):
                    pass
    return orphans
