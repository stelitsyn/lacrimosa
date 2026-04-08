"""Lacrimosa v3 state manager — SQLite WAL-mode backend."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StateViolation(ValueError):
    """Raised when a specialist writes outside its declared state keys."""


DB_PATH = Path.home() / ".claude" / "lacrimosa" / "state.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    domain      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    updated_by  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS specialists (
    name                TEXT PRIMARY KEY,
    last_heartbeat      TEXT,
    last_cycle_result   TEXT DEFAULT 'ok',
    cycles_completed    INTEGER DEFAULT 0,
    consecutive_errors  INTEGER DEFAULT 0,
    restarts_24h        INTEGER DEFAULT 0,
    metrics             TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS learning_events (
    id                  TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    source_specialist   TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    issue_id            TEXT DEFAULT '',
    context             TEXT DEFAULT '{}',
    processed           INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS merge_queue (
    pr_number       INTEGER PRIMARY KEY,
    issue_id        TEXT,
    files           TEXT NOT NULL,
    depends_on      TEXT DEFAULT '[]',
    status          TEXT DEFAULT 'ready',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_cycles (
    pr_number       INTEGER PRIMARY KEY,
    issue_id        TEXT NOT NULL,
    iteration       INTEGER DEFAULT 1,
    max_iterations  INTEGER DEFAULT 3,
    status          TEXT DEFAULT 'reviewing',
    history         TEXT DEFAULT '[]',
    review_agent_id TEXT,
    fix_agent_id    TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issue_pipeline (
    identifier      TEXT PRIMARY KEY,
    linear_id       TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'Backlog',
    owner           TEXT,
    worker_id       TEXT,
    worktree_path   TEXT,
    pr_number       INTEGER,
    review_iteration INTEGER DEFAULT 0,
    review_feedback TEXT,
    sentinel_origin INTEGER DEFAULT 0,
    proof           TEXT,
    error_count     INTEGER DEFAULT 0,
    updated_at      TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_state ON issue_pipeline(state);
CREATE INDEX IF NOT EXISTS idx_pipeline_sentinel ON issue_pipeline(sentinel_origin)
    WHERE sentinel_origin = 1;
"""


class StateManager:
    """SQLite WAL-mode state manager for Lacrimosa specialists."""

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None (autocommit) ensures every statement sees the latest
        # WAL writes from other processes — no stale snapshots across specialist sessions.
        self._conn = sqlite3.connect(str(self._db_path), timeout=30, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.row_factory = sqlite3.Row
        self._allowed_prefixes: dict[str, list[str]] = {}
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def set_allowed_prefixes(self, domain: str, prefixes: list[str]) -> None:
        """Set write-allowed prefixes for a domain. Prefixes like 'discovery.*' become 'discovery'."""
        self._allowed_prefixes[domain] = [
            p.replace(".*", "").replace("*", "") for p in prefixes
        ]

    @contextmanager
    def transaction(self, domain: str):
        """Scoped write transaction. Atomic, crash-safe, auto-heartbeat."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield ScopedWriter(self._conn, domain, self._allowed_prefixes.get(domain))
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute("""
                INSERT INTO specialists (name, last_heartbeat, last_cycle_result, cycles_completed)
                VALUES (?, ?, 'ok', 1)
                ON CONFLICT(name) DO UPDATE SET
                    last_heartbeat = excluded.last_heartbeat,
                    last_cycle_result = 'ok',
                    cycles_completed = cycles_completed + 1,
                    consecutive_errors = 0
            """, (domain, now))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute("""
                INSERT INTO specialists (name, last_heartbeat, last_cycle_result, consecutive_errors)
                VALUES (?, ?, 'error', 1)
                ON CONFLICT(name) DO UPDATE SET
                    last_heartbeat = excluded.last_heartbeat,
                    consecutive_errors = consecutive_errors + 1,
                    last_cycle_result = 'error'
            """, (domain, now))
            self._conn.commit()
            raise

    def read(self, key: str | None = None) -> Any:
        """Read a single state value, or full state as nested dict if no key given.

        - read("discovery.signal_queue") → returns that key's value
        - read() → returns full state as nested dict (backward compat with old JSON API)
        """

        if key is not None:
            row = self._conn.execute(
                "SELECT value FROM state WHERE key = ?", (key,)
            ).fetchone()
            return json.loads(row["value"]) if row else None

        # No key: reconstruct full state dict from all rows (backward compat)
        # Handles multi-level dot keys: "issues.ISSUE-42.phase" → state["issues"]["ISSUE-42"]["phase"]
        rows = self._conn.execute("SELECT key, value FROM state").fetchall()
        state: dict[str, Any] = {}
        for row in rows:
            k, v = row["key"], json.loads(row["value"])
            parts = k.split(".")
            if len(parts) == 1:
                state[k] = v
            elif len(parts) == 2:
                state.setdefault(parts[0], {})[parts[1]] = v
            else:
                # 3+ parts: nest fully (e.g. issues.ISSUE-42.phase)
                d = state
                for part in parts[:-1]:
                    if part not in d or not isinstance(d[part], dict):
                        d[part] = {}
                    d = d[part]
                d[parts[-1]] = v
        return state

    def atomic_update(self, updater):
        """Backward-compat shim: read full state, apply updater, write back."""
        state = self.read()
        new_state = updater(state)
        now = datetime.now(timezone.utc).isoformat()
        # Write back all top-level keys
        for top_key, value in new_state.items():
            domain = DOMAIN_MAP.get(top_key, "conductor")
            if isinstance(value, dict):
                for sub_key, sub_val in value.items():
                    self._conn.execute(
                        "INSERT OR REPLACE INTO state (key, value, domain, updated_at, updated_by) VALUES (?,?,?,?,?)",
                        (f"{top_key}.{sub_key}", json.dumps(sub_val), domain, now, "compat"),
                    )
            else:
                self._conn.execute(
                    "INSERT OR REPLACE INTO state (key, value, domain, updated_at, updated_by) VALUES (?,?,?,?,?)",
                    (top_key, json.dumps(value), domain, now, "compat"),
                )
        self._conn.commit()
        return new_state

    def migrate(self) -> dict[str, Any]:
        """Backward-compat shim: no-op for SQLite (migration already done)."""
        return self.read()

    def read_prefix(self, prefix: str) -> dict[str, Any]:
        """Read all state keys matching a prefix."""

        pattern = prefix.replace("*", "%")
        rows = self._conn.execute(
            "SELECT key, value FROM state WHERE key LIKE ?", (pattern,)
        ).fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def get_specialist_health(self) -> dict[str, dict]:
        """Read all specialist health rows."""

        rows = self._conn.execute("SELECT * FROM specialists").fetchall()
        return {row["name"]: dict(row) for row in rows}

    def close(self) -> None:
        self._conn.close()

    # ── Aliases for LLM agents that hallucinate method names ──
    # All real methods are defined above, so these class-level assignments work.
    # read() aliases
    get = read
    get_state = read
    get_all_state = read
    read_state = read
    get_value = read
    load = read
    load_state = read
    # get_specialist_health() aliases
    get_all_specialists = get_specialist_health
    get_specialists = get_specialist_health
    list_specialists = get_specialist_health
    specialist_health = get_specialist_health
    # read_prefix() aliases
    get_prefix = read_prefix
    read_all = read_prefix


class ScopedWriter:
    """Write handle scoped to a specialist domain."""

    def __init__(self, conn: sqlite3.Connection, domain: str, allowed_prefixes: list[str] | None = None) -> None:
        self._conn = conn
        self._domain = domain
        self._allowed_prefixes = allowed_prefixes

    def set(self, key: str, value: Any) -> None:
        """Upsert a state key-value pair."""
        if self._allowed_prefixes is not None:
            if not any(key.startswith(p) for p in self._allowed_prefixes):
                raise StateViolation(
                    f"Write to '{key}' not allowed for domain '{self._domain}'. "
                    f"Allowed prefixes: {self._allowed_prefixes}"
                )
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            INSERT INTO state (key, value, domain, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
        """, (key, json.dumps(value), self._domain, now, self._domain))

    def append_learning_event(self, event: dict) -> None:
        """Insert a learning event into the queue."""
        self._conn.execute("""
            INSERT INTO learning_events (id, timestamp, source_specialist, event_type, issue_id, context)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            event["id"], event["timestamp"], self._domain,
            event["event_type"], event.get("issue_id", ""),
            json.dumps(event.get("context", {})),
        ))


# -- Migration: state.json → SQLite ------------------------------------------

DOMAIN_MAP = {
    "discovery": "discovery",
    "pipeline": "engineering",
    "issues": "engineering",
    "trust_scores": "engineering",
    "content_creation": "content",
    "rate_limits": "conductor",
    "ceremonies": "conductor",
    "self_monitor": "conductor",
    "toolchain_monitor": "conductor",
    "steering": "engineering",
    "daily_counters": "conductor",
    "vision_cache": "conductor",
}


def infer_domain(top_key: str) -> str:
    """Map top-level state key to owning specialist."""
    return DOMAIN_MAP.get(top_key, "conductor")


def migrate_json_to_sqlite(json_path: Path, db_path: Path) -> None:
    """One-time migration: read state.json, populate SQLite tables."""
    state = json.loads(Path(json_path).read_text())
    sm = StateManager(db_path)
    now = datetime.now(timezone.utc).isoformat()

    for top_key, value in state.items():
        if top_key == "version":
            sm._conn.execute(
                "INSERT OR REPLACE INTO state (key, value, domain, updated_at, updated_by) VALUES (?,?,?,?,?)",
                (top_key, json.dumps(value), "conductor", now, "migration"),
            )
            continue

        domain = infer_domain(top_key)

        if isinstance(value, dict):
            for sub_key, sub_val in value.items():
                sm._conn.execute(
                    "INSERT OR REPLACE INTO state (key, value, domain, updated_at, updated_by) VALUES (?,?,?,?,?)",
                    (f"{top_key}.{sub_key}", json.dumps(sub_val), domain, now, "migration"),
                )
        else:
            sm._conn.execute(
                "INSERT OR REPLACE INTO state (key, value, domain, updated_at, updated_by) VALUES (?,?,?,?,?)",
                (top_key, json.dumps(value), domain, now, "migration"),
            )

    sm._conn.commit()
    sm.close()
