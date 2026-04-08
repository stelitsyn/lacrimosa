"""Lacrimosa pipeline state machine — typed FSM for issue lifecycle.

Each issue lives in exactly one state at any time. Transitions require proof
(evidence keys) and are validated atomically. This is the dedup mechanism:
specialists only query issues in their relevant states.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.lacrimosa_state_sqlite import SCHEMA_SQL

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────


class InvalidTransition(ValueError):
    """Raised when a state transition is not allowed by the FSM."""


class MissingProof(ValueError):
    """Raised when required proof keys are absent for a transition."""


# ── FSM definition ────────────────────────────────────────────────────────────

VALID_STATES: list[str] = [
    "Backlog",
    "Triaged",
    "Implementing",
    "ReviewPending",
    "Reviewing",
    "MergeReady",
    "FixNeeded",
    "Merging",
    "Verifying",
    "Done",
    "Failed",
    "Escalated",
]

VALID_TRANSITIONS: dict[str, list[str]] = {
    "Backlog": ["Triaged"],
    "Triaged": ["Implementing"],
    "Implementing": ["ReviewPending", "Failed"],
    "ReviewPending": ["Reviewing"],
    "Reviewing": ["MergeReady", "FixNeeded", "Escalated"],
    "FixNeeded": ["Implementing"],
    "MergeReady": ["Merging"],
    "Merging": ["Verifying", "Failed"],
    "Verifying": ["Done", "Failed"],
    "Failed": ["Triaged"],
    "Escalated": ["Triaged"],
}

# Keys: (from_state, to_state) -> list of required proof keys.
# Transitions to "Failed" use a wildcard rule (any source).
REQUIRED_PROOF: dict[tuple[str, str], list[str]] = {
    ("Backlog", "Triaged"): ["linear_comment_id", "route_type", "priority_score"],
    ("Triaged", "Implementing"): ["worker_id", "worktree_path"],
    ("Implementing", "ReviewPending"): ["pr_number", "pr_url"],
    ("ReviewPending", "Reviewing"): ["reviewer_agent_id"],
    ("Reviewing", "MergeReady"): ["review_verdict", "linear_comment_id"],
    ("Reviewing", "FixNeeded"): ["issues_list", "linear_comment_id"],
    ("Reviewing", "Escalated"): ["escalation_reason", "linear_comment_id"],
    ("MergeReady", "Merging"): ["rebase_clean", "ci_status"],
    ("Merging", "Verifying"): ["merge_sha", "merged_at"],
    ("Verifying", "Done"): ["verification_result", "linear_status_updated"],
    ("FixNeeded", "Implementing"): ["worker_id", "worktree_path"],
    ("Failed", "Triaged"): ["linear_comment_id", "route_type", "priority_score"],
    ("Escalated", "Triaged"): ["linear_comment_id", "route_type", "priority_score"],
}

# Wildcard proof for any transition to Failed
_FAILED_PROOF: list[str] = ["error_message", "retry_eligible"]

# Terminal states — issues here are "done" (not active)
_TERMINAL_STATES: set[str] = {"Done", "Escalated"}


# ── PipelineManager ──────────────────────────────────────────────────────────


class PipelineManager:
    """Manages issue_pipeline rows with FSM-validated transitions."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".claude" / "lacrimosa" / "state.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None (autocommit) ensures every statement sees the latest
        # WAL writes from other processes — no stale snapshots across specialist sessions.
        self._conn = sqlite3.connect(str(self._db_path), timeout=30, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────

    def insert_issue(
        self,
        identifier: str,
        linear_id: str,
        sentinel_origin: int = 0,
    ) -> dict[str, Any]:
        """Insert a new issue into the pipeline in Backlog state."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO issue_pipeline (identifier, linear_id, sentinel_origin, state, updated_at, created_at)
            VALUES (?, ?, ?, 'Backlog', ?, ?)
            """,
            (identifier, linear_id, sentinel_origin, now, now),
        )
        self._conn.commit()
        return self.get_issue(identifier)  # type: ignore[return-value]

    def get_issue(self, identifier: str) -> dict[str, Any] | None:
        """Return a single issue as a dict, or None if not found."""

        row = self._conn.execute(
            "SELECT * FROM issue_pipeline WHERE identifier = ?",
            (identifier,),
        ).fetchone()
        return dict(row) if row else None

    def query(
        self,
        states: list[str],
        sentinel_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Query issues by state(s). Sentinel issues sort first."""

        placeholders = ",".join("?" for _ in states)
        sql = f"SELECT * FROM issue_pipeline WHERE state IN ({placeholders})"
        params: list[Any] = list(states)

        if sentinel_only:
            sql += " AND sentinel_origin = 1"

        sql += " ORDER BY sentinel_origin DESC, created_at ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Transition ────────────────────────────────────────────────────────

    def transition(
        self,
        identifier: str,
        from_state: str,
        to_state: str,
        owner: str,
        proof: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically transition an issue, validating FSM rules and proof.

        Raises:
            InvalidTransition: if the transition is not allowed or current state mismatch
            MissingProof: if required proof keys are missing
        """
        # 1. Validate transition is in the FSM
        allowed = VALID_TRANSITIONS.get(from_state, [])
        if to_state not in allowed:
            raise InvalidTransition(
                f"Transition {from_state} -> {to_state} is not allowed. "
                f"Valid targets from {from_state}: {allowed}"
            )

        # 2. Validate proof
        self._validate_proof(from_state, to_state, proof)

        # 3. Check current state matches from_state (atomic read-check-write)
        issue = self.get_issue(identifier)
        if issue is None:
            raise InvalidTransition(f"Issue {identifier} not found")
        if issue["state"] != from_state:
            raise InvalidTransition(
                f"Issue {identifier} current state is '{issue['state']}', "
                f"not '{from_state}' as claimed"
            )

        # 4. Apply side effects and build UPDATE
        now = datetime.now(timezone.utc).isoformat()
        updates: dict[str, Any] = {
            "state": to_state,
            "owner": owner,
            "proof": json.dumps(proof),
            "updated_at": now,
        }

        self._apply_side_effects(to_state, proof, updates, issue)

        # 5. Execute atomic UPDATE
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [identifier, from_state]
        affected = self._conn.execute(
            f"UPDATE issue_pipeline SET {set_clause} WHERE identifier = ? AND state = ?",
            values,
        ).rowcount

        if affected == 0:
            raise InvalidTransition(
                f"Concurrent modification: issue {identifier} state changed during transition"
            )

        self._conn.commit()
        logger.info(
            "Pipeline transition: %s %s -> %s (owner=%s)",
            identifier, from_state, to_state, owner,
        )
        return self.get_issue(identifier)  # type: ignore[return-value]

    def _validate_proof(
        self,
        from_state: str,
        to_state: str,
        proof: dict[str, Any],
    ) -> None:
        """Validate that all required proof keys are present."""
        if to_state == "Failed":
            required = _FAILED_PROOF
        else:
            key = (from_state, to_state)
            required = REQUIRED_PROOF.get(key, [])

        missing = [k for k in required if k not in proof]
        if missing:
            raise MissingProof(
                f"Transition {from_state} -> {to_state} missing proof keys: {missing}"
            )

    def _apply_side_effects(
        self,
        to_state: str,
        proof: dict[str, Any],
        updates: dict[str, Any],
        current: dict[str, Any],
    ) -> None:
        """Apply state-specific side effects to the update dict."""
        if to_state == "Implementing":
            updates["worker_id"] = proof.get("worker_id")
            updates["worktree_path"] = proof.get("worktree_path")

        elif to_state == "ReviewPending":
            updates["pr_number"] = proof.get("pr_number")

        elif to_state == "FixNeeded":
            updates["review_feedback"] = json.dumps(proof.get("issues_list", []))
            updates["review_iteration"] = (current.get("review_iteration") or 0) + 1

        elif to_state == "Failed":
            updates["error_count"] = (current.get("error_count") or 0) + 1

        elif to_state == "Reviewing":
            updates["worker_id"] = proof.get("reviewer_agent_id")

    # ── Aggregates ────────────────────────────────────────────────────────

    def active_count(self) -> int:
        """Count issues NOT in terminal states (Done, Escalated)."""

        terminal_placeholders = ",".join("?" for _ in _TERMINAL_STATES)
        row = self._conn.execute(
            f"SELECT COUNT(*) as cnt FROM issue_pipeline WHERE state NOT IN ({terminal_placeholders})",
            list(_TERMINAL_STATES),
        ).fetchone()
        return row["cnt"] if row else 0

    def completed_since(self, since_iso: str) -> list[dict[str, Any]]:
        """Return issues that reached Done state since the given ISO timestamp."""

        rows = self._conn.execute(
            "SELECT * FROM issue_pipeline WHERE state = 'Done' AND updated_at >= ? ORDER BY updated_at ASC",
            (since_iso,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
