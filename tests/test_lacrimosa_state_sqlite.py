"""TDD tests for SQLite-backed Lacrimosa StateManager."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.lacrimosa_state_sqlite import StateManager, StateViolation


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


@pytest.fixture
def sm(db_path: Path) -> StateManager:
    return StateManager(db_path)


class TestSchemaCreation:
    def test_creates_state_table(self, sm: StateManager, db_path: Path):
        conn = sqlite3.connect(str(db_path))
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "state" in tables
        assert "specialists" in tables
        assert "learning_events" in tables
        assert "merge_queue" in tables
        assert "review_cycles" in tables

    def test_wal_mode_enabled(self, sm: StateManager, db_path: Path):
        conn = sqlite3.connect(str(db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_busy_timeout_set(self, sm: StateManager):
        timeout = sm._conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout == 30000


class TestReadWrite:
    def test_read_nonexistent_key_returns_none(self, sm: StateManager):
        assert sm.read("nonexistent.key") is None

    def test_read_prefix_empty(self, sm: StateManager):
        assert sm.read_prefix("discovery.*") == {}

    def test_write_and_read_single_key(self, sm: StateManager):
        with sm.transaction("discovery") as w:
            w.set("discovery.signal_queue", [1, 2, 3])
        result = sm.read("discovery.signal_queue")
        assert result == [1, 2, 3]

    def test_write_and_read_prefix(self, sm: StateManager):
        with sm.transaction("discovery") as w:
            w.set("discovery.last_sense", "2026-03-26T10:00:00Z")
            w.set("discovery.signal_count", 42)
        results = sm.read_prefix("discovery.*")
        assert len(results) == 2
        assert results["discovery.last_sense"] == "2026-03-26T10:00:00Z"
        assert results["discovery.signal_count"] == 42

    def test_write_overwrites_existing(self, sm: StateManager):
        with sm.transaction("discovery") as w:
            w.set("discovery.count", 1)
        with sm.transaction("discovery") as w:
            w.set("discovery.count", 2)
        assert sm.read("discovery.count") == 2

    def test_transaction_records_domain(self, sm: StateManager):
        with sm.transaction("engineering") as w:
            w.set("pipeline.workers", {})
        row = sm._conn.execute(
            "SELECT domain, updated_by FROM state WHERE key = ?", ("pipeline.workers",)
        ).fetchone()
        assert row["domain"] == "engineering"
        assert row["updated_by"] == "engineering"


class TestLearningEvents:
    def test_append_learning_event(self, sm: StateManager):
        with sm.transaction("engineering") as w:
            w.append_learning_event(
                {
                    "id": "evt-abc123",
                    "timestamp": "2026-03-26T10:48:00Z",
                    "event_type": "pr_rejected",
                    "issue_id": "TST-445",
                    "context": {"pr": "#850"},
                }
            )
        rows = sm._conn.execute("SELECT * FROM learning_events").fetchall()
        assert len(rows) == 1
        assert rows[0]["source_specialist"] == "engineering"
        assert rows[0]["processed"] == 0


class TestTransactionAtomicity:
    def test_failed_transaction_rolls_back(self, sm: StateManager):
        with sm.transaction("discovery") as w:
            w.set("discovery.before", "value")

        try:
            with sm.transaction("discovery") as w:
                w.set("discovery.during", "should_rollback")
                raise RuntimeError("simulated failure")
        except RuntimeError:
            pass

        assert sm.read("discovery.before") == "value"
        assert sm.read("discovery.during") is None

    def test_heartbeat_updated_on_success(self, sm: StateManager):
        with sm.transaction("discovery") as w:
            w.set("discovery.x", 1)
        health = sm.get_specialist_health()
        assert "discovery" in health
        assert health["discovery"]["last_cycle_result"] == "ok"
        assert health["discovery"]["cycles_completed"] == 1

    def test_error_count_incremented_on_failure(self, sm: StateManager):
        with sm.transaction("discovery") as w:
            w.set("discovery.x", 1)

        try:
            with sm.transaction("discovery") as w:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

        health = sm.get_specialist_health()
        assert health["discovery"]["consecutive_errors"] == 1
        assert health["discovery"]["last_cycle_result"] == "error"

    def test_consecutive_errors_reset_on_success(self, sm: StateManager):
        with sm.transaction("discovery") as w:
            w.set("discovery.x", 1)
        try:
            with sm.transaction("discovery") as w:
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        with sm.transaction("discovery") as w:
            w.set("discovery.x", 2)
        health = sm.get_specialist_health()
        assert health["discovery"]["consecutive_errors"] == 0

    def test_error_handler_sets_heartbeat(self, sm: StateManager):
        """First-ever transaction failure must still set heartbeat to avoid false restart."""
        try:
            with sm.transaction("discovery") as w:
                raise RuntimeError("first cycle fails")
        except RuntimeError:
            pass
        health = sm.get_specialist_health()
        assert health["discovery"]["last_heartbeat"] is not None


class TestMigrationFromJson:
    def test_migrate_flat_keys(self, tmp_path: Path):
        json_path = tmp_path / "state.json"
        json_path.write_text(
            json.dumps(
                {
                    "version": 6,
                    "system_state": "Running",
                    "rate_limits": {"throttle_level": "green"},
                }
            )
        )
        db_path = tmp_path / "state.db"
        from scripts.lacrimosa_state_sqlite import migrate_json_to_sqlite

        migrate_json_to_sqlite(json_path, db_path)
        sm = StateManager(db_path)
        assert sm.read("system_state") == "Running"
        assert sm.read("rate_limits.throttle_level") == "green"

    def test_migrate_nested_discovery(self, tmp_path: Path):
        json_path = tmp_path / "state.json"
        json_path.write_text(
            json.dumps(
                {
                    "version": 6,
                    "discovery": {
                        "last_internal_sense": "2026-03-26T10:00:00Z",
                        "signal_queue": [{"id": "sig-1"}],
                    },
                }
            )
        )
        db_path = tmp_path / "state.db"
        from scripts.lacrimosa_state_sqlite import migrate_json_to_sqlite

        migrate_json_to_sqlite(json_path, db_path)
        sm = StateManager(db_path)
        assert sm.read("discovery.last_internal_sense") == "2026-03-26T10:00:00Z"
        assert sm.read("discovery.signal_queue") == [{"id": "sig-1"}]

    def test_migrate_pipeline_domain_is_engineering(self, tmp_path: Path):
        json_path = tmp_path / "state.json"
        json_path.write_text(
            json.dumps(
                {
                    "version": 6,
                    "pipeline": {"active_workers": {}},
                }
            )
        )
        db_path = tmp_path / "state.db"
        from scripts.lacrimosa_state_sqlite import migrate_json_to_sqlite

        migrate_json_to_sqlite(json_path, db_path)
        sm = StateManager(db_path)
        row = sm._conn.execute(
            "SELECT domain FROM state WHERE key = ?", ("pipeline.active_workers",)
        ).fetchone()
        assert row["domain"] == "engineering"

    def test_migrate_deep_nested_preserved_as_json(self, tmp_path: Path):
        """3-level deep nesting should be stored as JSON blob at level 2."""
        json_path = tmp_path / "state.json"
        json_path.write_text(
            json.dumps(
                {
                    "version": 6,
                    "pipeline": {
                        "active_workers": {"w-abc123": {"status": "running", "issue": "TST-445"}}
                    },
                }
            )
        )
        db_path = tmp_path / "state.db"
        from scripts.lacrimosa_state_sqlite import migrate_json_to_sqlite

        migrate_json_to_sqlite(json_path, db_path)
        sm = StateManager(db_path)
        workers = sm.read("pipeline.active_workers")
        assert workers["w-abc123"]["status"] == "running"
        assert workers["w-abc123"]["issue"] == "TST-445"

    def test_migrate_ceremonies_domain_is_conductor(self, tmp_path: Path):
        json_path = tmp_path / "state.json"
        json_path.write_text(
            json.dumps(
                {
                    "version": 6,
                    "ceremonies": {"standup": {"last_run": None}},
                }
            )
        )
        db_path = tmp_path / "state.db"
        from scripts.lacrimosa_state_sqlite import migrate_json_to_sqlite

        migrate_json_to_sqlite(json_path, db_path)
        sm = StateManager(db_path)
        row = sm._conn.execute(
            "SELECT domain FROM state WHERE key = ?", ("ceremonies.standup",)
        ).fetchone()
        assert row["domain"] == "conductor"


class TestScopedWriteEnforcement:
    def test_rejects_write_outside_domain(self, sm: StateManager):
        sm.set_allowed_prefixes("discovery", ["discovery.*", "learning_events.*"])
        with pytest.raises(StateViolation, match="not allowed"):
            with sm.transaction("discovery") as w:
                w.set("pipeline.workers", {})

    def test_allows_write_within_domain(self, sm: StateManager):
        sm.set_allowed_prefixes("discovery", ["discovery.*", "learning_events.*"])
        with sm.transaction("discovery") as w:
            w.set("discovery.signal_queue", [])
        assert sm.read("discovery.signal_queue") == []

    def test_allows_shared_learning_events(self, sm: StateManager):
        sm.set_allowed_prefixes("engineering", ["pipeline.*", "learning_events.*"])
        with sm.transaction("engineering") as w:
            w.append_learning_event({"id": "e1", "timestamp": "now", "event_type": "test"})

    def test_no_enforcement_without_prefixes(self, sm: StateManager):
        """When no prefixes set, any write is allowed (backward compat)."""
        with sm.transaction("discovery") as w:
            w.set("anything.goes", "value")
        assert sm.read("anything.goes") == "value"
