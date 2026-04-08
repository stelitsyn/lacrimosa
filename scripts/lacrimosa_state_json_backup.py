"""Lacrimosa v2 state manager — fcntl.flock advisory locking + atomic writes."""

from __future__ import annotations

import copy
import fcntl
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# -- Constants ---------------------------------------------------------------

DEFAULT_STATE_PATH = Path.home() / ".claude" / "lacrimosa" / "state.json"


def _get_config_module():
    """Return the lacrimosa_config module (see lacrimosa_types for rationale)."""
    import sys

    mod = sys.modules.get("scripts.lacrimosa_config")
    if mod is not None:
        return mod
    import lacrimosa_config as _cfg

    return _cfg


class _LazyFrozenset:
    """Frozenset-like proxy that resolves its value from config on first use."""

    def __init__(self, *config_keys: str) -> None:
        self._config_keys = config_keys
        self._resolved: frozenset[str] | None = None

    def _resolve(self) -> frozenset[str]:
        if self._resolved is None:
            cfg = _get_config_module()
            combined: list[str] = []
            for key in self._config_keys:
                combined.extend(cfg.get(key, []))
            self._resolved = frozenset(combined)
        return self._resolved

    def __contains__(self, item: object) -> bool:
        return item in self._resolve()

    def __iter__(self):  # type: ignore[override]
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __repr__(self) -> str:
        return repr(self._resolve())


VALID_TRUST_DOMAINS = _LazyFrozenset("domains.autonomous", "domains.approval_required")


# -- Exceptions --------------------------------------------------------------


class StateValidationError(ValueError):
    """Raised when atomic_update would write invalid state."""


# -- Pure helpers -------------------------------------------------------------


def _empty_state() -> dict[str, Any]:
    """Return a valid empty v6 state."""
    return {
        "version": 6,
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
        "pipeline": {
            "active_workers": {},
            "implementation_queue": [],
        },
        "rate_limits": {"throttle_level": "green"},
        "vision_cache": {
            "last_strategy_analysis": None,
            "identified_gaps": [],
        },
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
        "steering": {
            "last_poll": None,
            "processed_comment_ids": [],
        },
    }


def migrate_state(state: dict[str, Any]) -> dict[str, Any]:
    """Migrate state from v1/v2/v3/v4 to v5. Pure function — does not write to disk."""
    state = copy.deepcopy(state)

    version = state.get("version", 1)
    if version < 3:
        # v1/v2 → v3
        state["version"] = 3
        state.setdefault("session_mode", "interactive")
        state.setdefault("conductor_pid", None)

        if "discovery" not in state:
            state["discovery"] = {
                "last_internal_sense": None,
                "last_external_sense": None,
                "last_strategy_analysis": None,
                "last_deep_research": None,
            }

        if "pipeline" not in state:
            state["pipeline"] = {
                "active_workers": {},
                "implementation_queue": [],
            }
        else:
            state["pipeline"].setdefault("active_workers", {})
            state["pipeline"].setdefault("implementation_queue", [])

        state.setdefault("rate_limits", {"throttle_level": "green"})
        state.setdefault("trust_scores", {})
        state.setdefault("issues", {})
        state.setdefault("daily_counters", {})
        state.setdefault(
            "vision_cache",
            {
                "last_strategy_analysis": None,
                "identified_gaps": [],
            },
        )

    if state.get("version", 1) < 4:
        # v3 → v4: add ceremonies section
        state["version"] = 4
        state.setdefault(
            "ceremonies",
            {
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
        )

    if state.get("version", 1) < 5:
        # v4 → v5: add self-observability sections
        state["version"] = 5
        state.setdefault(
            "self_monitor",
            {
                "last_run": None,
                "last_snapshot": None,
                "pending_tune_entries": [],
            },
        )
        state.setdefault(
            "toolchain_monitor",
            {
                "last_run": None,
                "last_findings_count": 0,
                "known_versions": {},
            },
        )

    if state.get("version", 1) < 6:
        # v5 → v6: add steering section for Linear command polling
        state["version"] = 6
        state.setdefault(
            "steering",
            {
                "last_poll": None,
                "processed_comment_ids": [],
            },
        )

    return state


def validate_state(state: dict[str, Any]) -> list[str]:
    """Validate state dict. Returns list of errors — empty means valid."""
    errors: list[str] = []

    if "version" not in state:
        errors.append("Missing 'version' field")

    if not isinstance(state.get("daily_counters", {}), dict):
        errors.append("'daily_counters' must be a dict")

    trust = state.get("trust_scores", {})
    if not isinstance(trust, dict):
        errors.append("'trust_scores' must be a dict")

    ceremonies = state.get("ceremonies")
    if ceremonies is not None and not isinstance(ceremonies, dict):
        errors.append("'ceremonies' must be a dict")

    self_mon = state.get("self_monitor")
    if self_mon is not None and not isinstance(self_mon, dict):
        errors.append("'self_monitor' must be a dict")

    tc_mon = state.get("toolchain_monitor")
    if tc_mon is not None and not isinstance(tc_mon, dict):
        errors.append("'toolchain_monitor' must be a dict")

    steering = state.get("steering")
    if steering is not None and not isinstance(steering, dict):
        errors.append("'steering' must be a dict")

    return errors


# -- StateManager class ------------------------------------------------------


class StateManager:
    """Manages Lacrimosa state with atomic writes and advisory locking."""

    def __init__(self, state_path: Path | None = None) -> None:
        self._path = state_path or DEFAULT_STATE_PATH
        self._lock_path = self._path.with_suffix(".lock")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict[str, Any]:
        """Read state without locking — safe for dashboard/watchdog."""
        if not self._path.exists():
            return _empty_state()
        try:
            data = json.loads(self._path.read_text())
            if not isinstance(data, dict):
                logger.warning("State file is not a JSON object, returning empty")
                return _empty_state()
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("State file corrupt or unreadable: %s", exc)
            return _empty_state()

    def atomic_update(
        self,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        """Read, apply updater, validate, write atomically — under flock."""
        backoff = 10.0
        max_backoff = 300.0
        attempts = 3

        for attempt in range(1, attempts + 1):
            try:
                return self._locked_update(updater)
            except BlockingIOError:
                if attempt == attempts:
                    raise IOError(f"Could not acquire state lock after {attempts} attempts")
                logger.warning(
                    "Lock unavailable (attempt %d/%d), retrying in %.0fs",
                    attempt,
                    attempts,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

        raise IOError("Unreachable")  # pragma: no cover

    def migrate(self) -> dict[str, Any]:
        """Migrate state to latest version. Idempotent for v5."""
        return self.atomic_update(migrate_state)

    def _locked_update(
        self,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        with open(self._lock_path, "w") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                state = self._read_raw()
                new_state = updater(state)

                errors = validate_state(new_state)
                if errors:
                    raise StateValidationError(f"State validation failed: {'; '.join(errors)}")

                self._write_raw(new_state)
                return new_state
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def _read_raw(self) -> dict[str, Any]:
        if not self._path.exists():
            return _empty_state()
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            # Try backup
            bak = self._path.with_suffix(".bak")
            if bak.exists():
                try:
                    logger.warning("Primary state corrupt, reading .bak")
                    return json.loads(bak.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
            return _empty_state()

    def _write_raw(self, state: dict[str, Any]) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        content = json.dumps(state, indent=2, default=str)

        tmp_path.write_text(content)
        os.chmod(tmp_path, 0o600)

        # Backup current state
        if self._path.exists():
            bak_path = self._path.with_suffix(".bak")
            try:
                bak_path.write_text(self._path.read_text())
                os.chmod(bak_path, 0o600)
            except OSError:
                pass

        # Atomic rename
        os.rename(tmp_path, self._path)
        logger.debug("State written atomically to %s", self._path)
