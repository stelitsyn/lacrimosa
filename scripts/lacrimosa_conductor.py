"""Lacrimosa v2 conductor — main loop, dispatch, lifecycle FSM, cadence scheduler."""

from __future__ import annotations

import copy
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts import lacrimosa_config
from scripts.lacrimosa_agent_runner import start_agent_prompt
from scripts.lacrimosa_types import (
    HARDCODED_MAX_CONCURRENT_WORKERS,
    HARDCODED_MAX_ISSUES_PER_DAY,
    ThrottleLevel,
    WorkerEntry,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "lacrimosa" / "config.yaml"
REQUIRED_CONFIG_SECTIONS = (
    "conductor",
    "lifecycle",
    "trust",
    "discovery",
    "ceremonies",
    "self_monitor",
)
DANGEROUS_PHASES = frozenset({"implementation"})  # SEC-C02
DIRTY_SECTIONS_PATH = PROJECT_ROOT / "spec" / "DIRTY_SECTIONS.json"


# -- Dirty section checks ---------------------------------------------------


def get_dirty_sections_for_scope(scope_keywords: list[str]) -> list[dict[str, Any]]:
    """Check if any dirty spec sections overlap with the worker's scope.

    Reads ``spec/DIRTY_SECTIONS.json`` and returns entries whose slug or reason
    text contains at least one of the given *scope_keywords*.  Returns an empty
    list when the file is missing, empty, or unparseable.
    """
    if not DIRTY_SECTIONS_PATH.exists():
        return []
    try:
        dirty = json.loads(DIRTY_SECTIONS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if not dirty:
        return []
    matches: list[dict[str, Any]] = []
    for section_slug, info in dirty.items():
        section_text = f"{section_slug} {info.get('reason', '')}".lower()
        if any(kw.lower() in section_text for kw in scope_keywords):
            matches.append({"section": section_slug, **info})
    return matches


def build_dirty_sections_warning(dirty_sections: list[dict[str, Any]]) -> str:
    """Format a list of dirty section matches into a prompt warning block."""
    warning = "\n\n## SPEC DIRTY SECTIONS WARNING\n"
    warning += (
        "The following spec sections have been recently invalidated. "
        "Use CODE as truth, not spec:\n"
    )
    for ds in dirty_sections:
        warning += (
            f"- **{ds['section']}**: "
            f"{ds.get('reason', 'no reason')} "
            f"(flagged by {ds.get('flagged_by', 'unknown')})\n"
        )
        if ds.get("pending_update"):
            warning += f"  Pending update: {ds['pending_update']}\n"
    return warning


# -- Config ------------------------------------------------------------------


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate config before conductor starts. Returns error list."""
    errors: list[str] = []
    for section in REQUIRED_CONFIG_SECTIONS:
        if section not in config:
            errors.append(f"Missing required section: '{section}'")
    t0 = config.get("trust", {}).get("tiers", {}).get(0, {})
    if t0.get("issues_per_day", 0) > 20:
        errors.append(f"T0 daily cap suspiciously high (>20): {t0.get('issues_per_day')}")
    return errors


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load and validate YAML config. Exits on failure."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        logger.error("Config file not found: %s", path)
        sys.exit(1)
    try:
        config = yaml.safe_load(path.read_text())
    except (yaml.YAMLError, OSError) as exc:
        logger.error("Failed to parse config: %s", exc)
        sys.exit(1)
    if not isinstance(config, dict):
        logger.error("Config is not a YAML mapping")
        sys.exit(1)
    errors = validate_config(config)
    if errors:
        for err in errors:
            logger.error("Config validation: %s", err)
        sys.exit(1)
    return config


# -- Rate limits -------------------------------------------------------------


def check_rate_limits(
    config: dict[str, Any],
    rate_limits_data: dict[str, Any],
) -> ThrottleLevel:
    """Determine throttle level from rate limit windows. Worst wins."""
    rl = config.get("rate_limits", {})
    yellow_threshold = rl.get("green_threshold", 50)
    red_threshold = rl.get("red_threshold", 90)
    worst = ThrottleLevel.green
    for window in ("five_hour", "seven_day"):
        pct = rate_limits_data.get(window, {}).get("used_percentage", 0)
        if pct >= red_threshold:
            return ThrottleLevel.red
        if pct >= yellow_threshold and worst == ThrottleLevel.green:
            worst = ThrottleLevel.yellow
    return worst


# -- Cadence scheduling ------------------------------------------------------


def is_cadence_due(last_run_iso: str | None, interval_minutes: int) -> bool:
    """Check if enough time has passed since the last run."""
    if last_run_iso is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last_run_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    return datetime.now(timezone.utc) >= last_dt + timedelta(minutes=interval_minutes)


# -- Lifecycle routing -------------------------------------------------------


def get_lifecycle_phases(routing_type: str, config: dict[str, Any]) -> list[str]:
    """Get the phase list for a lifecycle routing type."""
    entry = config.get("lifecycle", {}).get("routing", {}).get(routing_type)
    if entry is None:
        raise ValueError(f"Unknown lifecycle routing type: {routing_type}")
    return list(entry.get("phases", []))


# -- Dispatch gating ---------------------------------------------------------


def can_dispatch(domain: str, state: dict[str, Any], config: dict[str, Any]) -> bool:
    """Check if a new worker can be dispatched for the given domain."""
    if state.get("rate_limits", {}).get("throttle_level", "green") == "red":
        return False

    trust_data = state.get("trust_scores", {}).get(domain, {})
    tier = trust_data.get("tier", 0)
    tier_config = config.get("trust", {}).get("tiers", {}).get(tier, {})

    max_concurrent = min(tier_config.get("concurrent_workers", 1), HARDCODED_MAX_CONCURRENT_WORKERS)
    active = state.get("pipeline", {}).get("active_workers", {})
    domain_workers = sum(1 for w in active.values() if w.get("domain") == domain)
    if domain_workers >= max_concurrent:
        return False

    max_daily = min(tier_config.get("issues_per_day", 3), HARDCODED_MAX_ISSUES_PER_DAY)
    today = datetime.now().strftime("%Y-%m-%d")
    daily = state.get("daily_counters", {}).get(today, {})
    if daily.get("workers_spawned", 0) >= max_daily:
        return False
    return True


# -- Worker dispatch ---------------------------------------------------------


def dispatch_worker(
    issue_id: str,
    phase: str,
    prompt: str,
    config: dict[str, Any],
    issue_title: str = "",
) -> WorkerEntry:
    """Dispatch a Claude Code worker in a git worktree.

    When *issue_title* is provided, keywords are extracted and checked against
    ``spec/DIRTY_SECTIONS.json``.  Any matching dirty sections are appended to
    the worker prompt so the agent knows to treat code as the source of truth
    rather than stale spec text.
    """
    _ = config.get("conductor", {})  # reserved for future worktree_base

    # -- Inject dirty-section warnings into the worker prompt ----------------
    if issue_title:
        scope_keywords = [w for w in issue_title.lower().split() if len(w) > 3]
        dirty_sections = get_dirty_sections_for_scope(scope_keywords)
        if dirty_sections:
            prompt += build_dirty_sections_warning(dirty_sections)
            logger.info(
                "Injected %d dirty-section warning(s) into prompt for %s",
                len(dirty_sections),
                issue_id,
            )

    worktree_name = f"lacrimosa-{issue_id}"
    proc = start_agent_prompt(
        prompt,
        purpose=f"worker-dispatch-{issue_id}",
        json_mode=True,
        dangerous=phase in DANGEROUS_PHASES,
        cwd=PROJECT_ROOT,
        extra_add_dirs=[PROJECT_ROOT],
        worktree_name=worktree_name,
    )
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("Dispatched worker PID=%d for %s phase=%s", proc.pid, issue_id, phase)
    return WorkerEntry(
        issue_id=issue_id,
        pid=proc.pid,
        worktree_name=worktree_name,
        phase=phase,
        started_at=started_at,
        domain="",
    )


# -- Worker completions ------------------------------------------------------


def check_completions(
    state: dict[str, Any],
    stall_timeout_minutes: int | None = None,
) -> list[dict[str, Any]]:
    """Check active workers for completion, failure, or stall."""
    completed: list[dict[str, Any]] = []
    active = state.get("pipeline", {}).get("active_workers", {})
    now = datetime.now(timezone.utc)

    for issue_id, worker in active.items():
        proc = worker.get("_proc")
        if proc is None:
            continue
        exit_code = proc.poll()
        if exit_code is not None:
            entry: dict[str, Any] = {
                "issue_id": issue_id,
                "exit_code": exit_code,
                "domain": worker.get("domain", ""),
                "phase": worker.get("phase", ""),
            }
            if exit_code != 0:
                entry["failed"] = True
            completed.append(entry)
            continue
        if stall_timeout_minutes is not None:
            started = worker.get("started_at")
            if started:
                try:
                    started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    elapsed = (now - started_dt).total_seconds() / 60.0
                    if elapsed > stall_timeout_minutes:
                        completed.append(
                            {
                                "issue_id": issue_id,
                                "stalled": True,
                                "elapsed_minutes": elapsed,
                                "domain": worker.get("domain", ""),
                                "phase": worker.get("phase", ""),
                            }
                        )
                except (ValueError, TypeError):
                    pass
    return completed


# -- Error handling ----------------------------------------------------------


def handle_worker_failure(
    issue_id: str,
    state: dict[str, Any],
    max_retries: int = 3,
) -> dict[str, Any]:
    """Handle a failed worker — retry or escalate."""
    state = copy.deepcopy(state)
    issue = state.get("issues", {}).get(issue_id, {})
    retry_count = issue.get("retry_count", 0) + 1
    issue["retry_count"] = retry_count
    if retry_count >= max_retries:
        issue["state"] = "Escalated"
        logger.warning("Issue %s escalated after %d retries", issue_id, retry_count)
    else:
        issue["state"] = "RetryQueued"
        logger.info("Issue %s requeued (retry %d/%d)", issue_id, retry_count, max_retries)
    state["issues"][issue_id] = issue
    return state


# -- State updates -----------------------------------------------------------


def record_dispatch(entry: WorkerEntry, state: dict[str, Any]) -> dict[str, Any]:
    """Record a dispatched worker in state."""
    state = copy.deepcopy(state)
    state.setdefault("pipeline", {}).setdefault("active_workers", {})
    state["pipeline"]["active_workers"][entry.issue_id] = {
        "pid": entry.pid,
        "worktree_name": entry.worktree_name,
        "phase": entry.phase,
        "started_at": entry.started_at,
        "domain": entry.domain,
    }
    today = datetime.now().strftime("%Y-%m-%d")
    counters = state.setdefault("daily_counters", {}).setdefault(today, {})
    counters["workers_spawned"] = counters.get("workers_spawned", 0) + 1
    return state


def record_completion(issue_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Remove a completed worker from active_workers."""
    state = copy.deepcopy(state)
    state.get("pipeline", {}).get("active_workers", {}).pop(issue_id, None)
    return state




# -- Verification gates (DO NOT DELETE — tests depend on these) --------------


def determine_verification_gates(
    changed_files: list[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Determine which verification gates apply based on changed files."""
    gates_config = (
        config.get("lifecycle", {})
        .get("phases", {})
        .get("verification", {})
        .get("gates", {})
    )
    gates: list[dict[str, Any]] = []

    # Gate 1: Test suite — always runs
    test_suite = gates_config.get("test_suite", {})
    if test_suite.get("always", True):
        gates.append({
            "name": "test_suite",
            "description": test_suite.get("description", "Run unit + integration tests"),
            "commands": test_suite.get("commands", [
                "./run_unit_tests.sh",
                "./run_integration_tests.sh",
            ]),
        })

    # Gate 2: API staging — when backend files changed
    api_staging = gates_config.get("api_staging", {})
    backend_patterns = ("{source_dir}/", "tests/")
    if any(f.startswith(p) for f in changed_files for p in backend_patterns):
        gates.append({
            "name": "api_staging",
            "description": api_staging.get("description", "Deploy to staging + verify API"),
            "commands": ["./infra/deploy-staging-fresh.sh"],
            "type": "staging_deploy",
        })

    # Gate 3: Browser QA — when frontend files changed
    browser_qa = gates_config.get("browser_qa", {})
    frontend_patterns = tuple(lacrimosa_config.get("verification.frontend_path_patterns"))
    if any(f.startswith(p) for f in changed_files for p in frontend_patterns):
        gates.append({
            "name": "browser_qa",
            "description": browser_qa.get("description", "Browser QA on staging"),
            "type": "browser_qa",
        })

    return gates


def run_verification_gate(
    gate: dict[str, Any],
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Run a single verification gate. Returns result dict."""
    cwd = worktree_path or str(PROJECT_ROOT)
    gate_name = gate["name"]
    commands = gate.get("commands", [])

    results: list[dict[str, Any]] = []
    all_passed = True

    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min per command
            )
            passed = proc.returncode == 0
            results.append({
                "command": cmd,
                "passed": passed,
                "exit_code": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-500:],
                "stderr_tail": (proc.stderr or "")[-500:],
            })
            if not passed:
                all_passed = False
                logger.warning(
                    "Verification gate %s failed: %s (exit %d)",
                    gate_name, cmd, proc.returncode,
                )
                break  # Stop on first failure
        except subprocess.TimeoutExpired:
            results.append({
                "command": cmd,
                "passed": False,
                "exit_code": -1,
                "error": "Timed out after 600s",
            })
            all_passed = False
            break
        except (FileNotFoundError, OSError) as e:
            results.append({
                "command": cmd,
                "passed": False,
                "exit_code": -1,
                "error": str(e),
            })
            all_passed = False
            break

    return {
        "gate": gate_name,
        "passed": all_passed,
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_all_verification_gates(
    issue_id: str,
    changed_files: list[str],
    config: dict[str, Any],
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Run all applicable verification gates for an issue.

    Returns:
        {"passed": bool, "gates": [...], "failed_gate": str|None}
    """
    gates = determine_verification_gates(changed_files, config)
    if not gates:
        logger.info("No verification gates applicable for %s", issue_id)
        return {"passed": True, "gates": [], "failed_gate": None}

    logger.info(
        "Running %d verification gate(s) for %s: %s",
        len(gates), issue_id, [g["name"] for g in gates],
    )

    gate_results = []
    failed_gate = None

    for gate in gates:
        # Skip non-command gates (browser_qa is handled by agent, not subprocess)
        if gate.get("type") in ("browser_qa", "staging_deploy"):
            gate_results.append({
                "gate": gate["name"],
                "passed": True,
                "skipped": True,
                "reason": f"{gate['type']} requires agent dispatch (not subprocess)",
            })
            continue

        result = run_verification_gate(gate, worktree_path)
        gate_results.append(result)

        if not result["passed"]:
            failed_gate = gate["name"]
            logger.warning(
                "Verification failed at gate '%s' for %s — stopping",
                gate["name"], issue_id,
            )
            break

    all_passed = failed_gate is None
    return {
        "passed": all_passed,
        "gates": gate_results,
        "failed_gate": failed_gate,
    }


def transition_after_review(
    issue_id: str,
    state: dict[str, Any],
    config: dict[str, Any],
    changed_files: list[str] | None = None,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Transition an issue from review-passed to verification, then merge-ready.

    This is the conductor's automatic state machine after review approves a PR.
    Runs verification gates and updates state accordingly.
    """
    state = copy.deepcopy(state)
    issue = state.get("issues", {}).get(issue_id, {})

    # Update to verification phase
    issue["state"] = "Verifying"
    worker = state.get("pipeline", {}).get("active_workers", {}).get(issue_id, {})
    worker["phase"] = "verification"
    state["issues"][issue_id] = issue
    logger.info("Issue %s entering verification phase", issue_id)

    if not changed_files:
        changed_files = []

    # Run verification gates
    verification_result = run_all_verification_gates(
        issue_id, changed_files, config, worktree_path,
    )

    issue["verification_result"] = {
        "passed": verification_result["passed"],
        "gates_run": len(verification_result["gates"]),
        "failed_gate": verification_result.get("failed_gate"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if verification_result["passed"]:
        issue["state"] = "Merging"
        phases = issue.get("phases_completed", [])
        if "verification" not in phases:
            phases.append("verification")
        issue["phases_completed"] = phases
        logger.info("Issue %s verification passed — ready to merge", issue_id)
    else:
        issue["state"] = "Implementation"
        worker["phase"] = "implementation"
        logger.warning(
            "Issue %s verification failed at gate '%s' — back to implementation",
            issue_id, verification_result.get("failed_gate"),
        )

    state["issues"][issue_id] = issue
    return state


# -- Specialist Health Check (v3 architecture) --------------------------------


def parse_cadence_to_minutes(cadence: str) -> int:
    """Parse '30m', '6h', '24h' to minutes."""
    if cadence.endswith("m"):
        return int(cadence[:-1])
    if cadence.endswith("h"):
        return int(cadence[:-1]) * 60
    return int(cadence)


def should_restart_specialist(
    last_heartbeat: str | None,
    max_silence_minutes: int,
    consecutive_errors: int,
    max_errors: int = 3,
    restarts_24h: int = 0,
    max_restarts_24h: int = 3,
) -> str | None:
    """Check if a specialist should be restarted. Returns reason or None.

    Priority order: restart_storm > consecutive_errors > no_heartbeat > stale_heartbeat
    """
    if restarts_24h > max_restarts_24h:
        return "restart_storm"

    if consecutive_errors >= max_errors:
        return "consecutive_errors"

    if last_heartbeat is None:
        return "no_heartbeat"

    try:
        hb = datetime.fromisoformat(last_heartbeat.replace("Z", "+00:00"))
        age_minutes = (datetime.now(timezone.utc) - hb).total_seconds() / 60
        if age_minutes > max_silence_minutes:
            return "stale_heartbeat"
    except (ValueError, TypeError):
        return "invalid_heartbeat"

    return None
