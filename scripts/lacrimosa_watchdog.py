#!/usr/bin/env python3
"""Lacrimosa Watchdog — monitors conductor health and restarts if dead.

Designed to run via macOS launchd every 5 minutes.
Checks if the Lacrimosa conductor process is alive (via PID file or health endpoint).
If dead, restarts the conductor session.

Usage:
    python scripts/lacrimosa_watchdog.py [--dry-run] [--verbose]

launchd runs this automatically via:
    ~/Library/LaunchAgents/<watchdog.bundle_id>.plist
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from scripts import lacrimosa_config

# -- Paths ------------------------------------------------------------------

LACRIMOSA_DIR = Path.home() / ".claude" / "lacrimosa"
STATE_FILE = LACRIMOSA_DIR / "state.json"
PID_FILE = LACRIMOSA_DIR / "conductor.pid"
LOG_FILE = LACRIMOSA_DIR / "watchdog.log"
CONFIG_FILE = LACRIMOSA_DIR / "config.yaml"

# -- Config defaults --------------------------------------------------------

HEALTH_ENDPOINT = "http://localhost:1791/health"
MAX_RESTART_ATTEMPTS = 5
RESTART_COOLDOWN_SECONDS = 60
PROJECT_ROOT = Path(__file__).parent.parent

# Circuit breaker: 3 crashes in 15 minutes → stop (CTO Decision 6, Layer 3)
CIRCUIT_BREAKER_CRASHES = 3
CIRCUIT_BREAKER_WINDOW_SECONDS = 900  # 15 minutes

# State size guard (NFR-12 / CTO Decision 6, Layer 3)
MAX_STATE_FILE_SIZE_BYTES = 1_000_000  # 1 MB

# Discovery freshness thresholds
# 1.5x the cadence: internal_sense every 30 min -> stale at 45 min (2700s)
#                    external_sense every 6 hours -> stale at 9 hours (32400s)
DISCOVERY_INTERNAL_MAX_AGE_SECONDS = 2700
DISCOVERY_EXTERNAL_MAX_AGE_SECONDS = 32400


# -- Logging ----------------------------------------------------------------


def setup_logging(verbose: bool = False) -> logging.Logger:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("lacrimosa-watchdog")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # File handler — always logs
    fh = logging.FileHandler(str(LOG_FILE), mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(fh)

    # Console handler — only when verbose or running interactively
    if verbose or sys.stdout.isatty():
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG if verbose else logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ch)

    return logger


# -- State helpers (delegated to StateManager) ------------------------------

from scripts.lacrimosa_state import StateManager

_state_manager = StateManager()


def read_state() -> dict:
    return _state_manager.read()


def write_state(state: dict) -> None:
    _state_manager.atomic_update(lambda _: state)


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        return pid
    except (ValueError, OSError):
        return None


def is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# -- Health checks ----------------------------------------------------------


def check_health_endpoint() -> bool:
    """Check if the dashboard health endpoint responds."""
    try:
        resp = urlopen(HEALTH_ENDPOINT, timeout=5)
        if resp.status == 200:
            data = json.loads(resp.read())
            return data.get("status") == "healthy"
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        pass
    return False


def check_pid_alive() -> bool:
    """Check if the conductor PID is alive."""
    pid = read_pid()
    if pid is None:
        return False
    return is_process_alive(pid)


def check_state_fresh(max_age_seconds: int = 600) -> bool:
    """Check if state.json was updated recently (within max_age_seconds)."""
    state = read_state()
    last_poll = state.get("last_poll")
    if not last_poll:
        return False
    try:
        last_dt = datetime.fromisoformat(last_poll.replace("Z", "+00:00"))
        age = (datetime.now(tz=timezone.utc) - last_dt).total_seconds()
        return age < max_age_seconds
    except (ValueError, TypeError):
        return False


def check_discovery_fresh(logger: logging.Logger) -> bool:
    """Check if discovery sense timestamps are within acceptable freshness.

    Reads state.json and checks:
    - discovery.last_internal_sense: should be within 45 min (1.5x 30-min cadence)
    - discovery.last_external_sense: should be within 9 hours (1.5x 6-hour cadence)

    Returns True if BOTH are fresh enough, or if the discovery section does not
    exist (backwards compatibility with state v2).
    """
    state = read_state()
    discovery = state.get("discovery")

    if discovery is None:
        # No discovery section — backwards compatible, treat as OK
        return True

    now = datetime.now(tz=timezone.utc)
    fresh = True

    # Check internal sense freshness
    last_internal = discovery.get("last_internal_sense")
    if last_internal:
        try:
            internal_dt = datetime.fromisoformat(last_internal.replace("Z", "+00:00"))
            internal_age = (now - internal_dt).total_seconds()
            if internal_age > DISCOVERY_INTERNAL_MAX_AGE_SECONDS:
                logger.warning(
                    f"Discovery internal_sense is stale: "
                    f"{int(internal_age)}s old (threshold: "
                    f"{DISCOVERY_INTERNAL_MAX_AGE_SECONDS}s)"
                )
                fresh = False
        except (ValueError, TypeError):
            logger.warning("Discovery last_internal_sense has invalid timestamp")
            fresh = False
    else:
        # Field missing within discovery section — could be partial config
        logger.warning("Discovery section exists but last_internal_sense is missing")
        fresh = False

    # Check external sense freshness
    last_external = discovery.get("last_external_sense")
    if last_external:
        try:
            external_dt = datetime.fromisoformat(last_external.replace("Z", "+00:00"))
            external_age = (now - external_dt).total_seconds()
            if external_age > DISCOVERY_EXTERNAL_MAX_AGE_SECONDS:
                logger.warning(
                    f"Discovery external_sense is stale: "
                    f"{int(external_age)}s old (threshold: "
                    f"{DISCOVERY_EXTERNAL_MAX_AGE_SECONDS}s)"
                )
                fresh = False
        except (ValueError, TypeError):
            logger.warning("Discovery last_external_sense has invalid timestamp")
            fresh = False
    else:
        logger.warning("Discovery section exists but last_external_sense is missing")
        fresh = False

    return fresh


def is_conductor_healthy(logger: logging.Logger) -> bool:
    """Run all health checks. Conductor is healthy if PID alive AND state fresh."""
    # Check 1: PID file
    pid_ok = check_pid_alive()
    logger.debug(f"PID check: {'alive' if pid_ok else 'dead/missing'}")

    # Check 2: Health endpoint (dashboard may not be running)
    health_ok = check_health_endpoint()
    logger.debug(f"Health endpoint: {'responsive' if health_ok else 'unresponsive'}")

    # Check 3: State freshness
    state_ok = check_state_fresh()
    logger.debug(f"State freshness: {'fresh' if state_ok else 'stale/missing'}")

    # Check 4: Discovery freshness (warning only — does not affect health)
    discovery_ok = check_discovery_fresh(logger)
    logger.debug(f"Discovery freshness: " f"{'fresh' if discovery_ok else 'stale/not-configured'}")

    # Conductor is healthy if PID is alive AND state is fresh
    # (health endpoint is optional — dashboard may not be running)
    # (discovery staleness is warning-only — does not trigger restart)
    healthy = pid_ok and state_ok
    return healthy


# -- Circuit breaker & safety checks ----------------------------------------


def check_circuit_breaker(logger: logging.Logger) -> bool:
    """Check if crash rate triggers circuit breaker. Returns True if tripped."""
    state = read_state()
    watchdog = state.get("watchdog", {})
    crash_times = watchdog.get("recent_crash_times", [])

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(seconds=CIRCUIT_BREAKER_WINDOW_SECONDS)

    recent = []
    for ts in crash_times:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt >= cutoff:
                recent.append(ts)
        except (ValueError, TypeError):
            pass

    if len(recent) >= CIRCUIT_BREAKER_CRASHES:
        logger.error(
            "Circuit breaker tripped: %d crashes in %d seconds. "
            "Setting system_state='Stopped'. Manual intervention required.",
            len(recent),
            CIRCUIT_BREAKER_WINDOW_SECONDS,
        )
        state["system_state"] = "Stopped"
        state.setdefault("watchdog", {})["circuit_breaker_tripped"] = True
        write_state(state)
        return True
    return False


def record_crash_time() -> None:
    """Record a crash timestamp for circuit breaker tracking."""
    state = read_state()
    watchdog = state.setdefault("watchdog", {})
    crash_times = watchdog.setdefault("recent_crash_times", [])
    crash_times.append(datetime.now(tz=timezone.utc).isoformat())
    # Keep only last 10 entries
    watchdog["recent_crash_times"] = crash_times[-10:]
    write_state(state)


def check_state_size(logger: logging.Logger) -> bool:
    """Check if state.json exceeds size limit. Returns True if oversized."""
    if not STATE_FILE.exists():
        return False
    try:
        size = STATE_FILE.stat().st_size
        if size > MAX_STATE_FILE_SIZE_BYTES:
            logger.warning(
                "state.json is %d bytes (limit: %d). Pausing conductor.",
                size,
                MAX_STATE_FILE_SIZE_BYTES,
            )
            state = read_state()
            state["system_state"] = "Paused"
            write_state(state)
            return True
    except OSError:
        pass
    return False


def check_state_integrity(logger: logging.Logger) -> bool:
    """Check if state.json is valid. Returns False if corrupt."""
    if not STATE_FILE.exists():
        return True
    try:
        data = json.loads(STATE_FILE.read_text())
        if not isinstance(data, dict):
            logger.error("state.json is not a JSON object — corrupt")
            return False
        if "version" not in data:
            logger.error("state.json missing 'version' field — corrupt")
            return False
        return True
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("state.json is corrupt: %s", exc)
        return False


def save_crash_log(logger: logging.Logger) -> None:
    """Save crash log with timestamp for debugging (SEC-M04)."""
    crash_dir = LACRIMOSA_DIR
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    crash_file = crash_dir / f"crash-{timestamp}.log"
    try:
        log_content = LOG_FILE.read_text() if LOG_FILE.exists() else ""
        lines = log_content.splitlines()
        last_50 = "\n".join(lines[-50:]) if lines else "No log content"
        crash_file.write_text(last_50)
        os.chmod(crash_file, 0o600)
        logger.info("Crash log saved to %s", crash_file)
    except OSError as exc:
        logger.warning("Failed to save crash log: %s", exc)


# -- Claude CLI update ------------------------------------------------------


def update_claude_cli(logger: logging.Logger) -> bool:
    """Update Claude Code CLI to the latest version before restarting conductor."""
    logger.info("Checking for Claude Code CLI updates...")
    try:
        proc = subprocess.run(
            ["claude", "update"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode == 0:
            logger.info("Claude CLI update check complete: %s", output or "up to date")
            return True
        else:
            logger.warning(
                "Claude CLI update returned exit %d: stdout=%s stderr=%s",
                proc.returncode, output[-200:], stderr[-200:],
            )
            return False
    except subprocess.TimeoutExpired:
        logger.warning("Claude CLI update timed out after 120s — continuing with current version")
        return False
    except FileNotFoundError:
        logger.error("'claude' CLI not found in PATH — cannot update")
        return False
    except OSError as exc:
        logger.warning("Claude CLI update failed: %s — continuing with current version", exc)
        return False


# -- Restart logic ----------------------------------------------------------


def get_restart_count() -> int:
    """Get number of restarts today from state."""
    state = read_state()
    watchdog_state = state.get("watchdog", {})
    today = datetime.now().strftime("%Y-%m-%d")
    if watchdog_state.get("restart_date") != today:
        return 0
    return watchdog_state.get("restart_count", 0)


def record_restart() -> None:
    """Record a restart attempt in state."""
    state = read_state()
    today = datetime.now().strftime("%Y-%m-%d")
    watchdog = state.get("watchdog", {})

    if watchdog.get("restart_date") != today:
        watchdog["restart_date"] = today
        watchdog["restart_count"] = 1
    else:
        watchdog["restart_count"] = watchdog.get("restart_count", 0) + 1

    watchdog["last_restart"] = datetime.now(tz=timezone.utc).isoformat()
    state["watchdog"] = watchdog
    write_state(state)


def restart_conductor(logger: logging.Logger, dry_run: bool = False) -> bool:
    """Restart the Lacrimosa conductor via Claude Code CLI."""
    restart_count = get_restart_count()
    if restart_count >= MAX_RESTART_ATTEMPTS:
        logger.error(
            f"Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached today. "
            "Manual intervention required."
        )
        return False

    logger.info(f"Restarting conductor (attempt {restart_count + 1}/{MAX_RESTART_ATTEMPTS})")

    if dry_run:
        logger.info("[DRY RUN] Would restart conductor")
        return True

    # Clean up stale PID file
    if PID_FILE.exists():
        pid = read_pid()
        if pid and is_process_alive(pid):
            logger.info(f"Sending SIGTERM to stale conductor PID {pid}")
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(5)
                if is_process_alive(pid):
                    os.kill(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        PID_FILE.unlink(missing_ok=True)

    # Update Claude CLI before starting new conductor
    update_claude_cli(logger)

    # Kill any stale tmux session before creating a new one
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", "lacrimosa-conductor"],
            capture_output=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Start conductor as a long-lived INTERACTIVE Claude session inside tmux.
    # The skill's /loop mechanism keeps the session alive indefinitely.
    # --print mode is one-shot and exits immediately — must NOT be used here.
    try:
        result = subprocess.run(
            [
                "tmux", "new-session",
                "-d",                          # detached
                "-s", "lacrimosa-conductor",    # session name
                "-x", "200", "-y", "50",        # window size
                "claude", "--dangerously-skip-permissions",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=10,
        )

        if result.returncode != 0:
            logger.error(f"tmux new-session failed: {result.stderr.strip()}")
            return False

        # Wait for Claude CLI to fully initialize before sending command.
        # Claude takes ~10s to start (load MCP servers, rules, etc).
        # Poll for the ready indicator (prompt char) before sending keys.
        for attempt in range(12):  # 12 * 2s = 24s max
            time.sleep(2)
            try:
                capture = subprocess.run(
                    ["tmux", "capture-pane", "-t", "lacrimosa-conductor",
                     "-p", "-S", "-5"],
                    capture_output=True, text=True, timeout=5,
                )
                pane_text = capture.stdout if capture.returncode == 0 else ""
                # Claude shows ">" prompt when ready for input
                if "bypass permissions" in pane_text or "❯" in pane_text:
                    logger.info(
                        f"Claude CLI ready after {(attempt + 1) * 2}s"
                    )
                    break
            except (subprocess.TimeoutExpired, OSError):
                pass
        else:
            logger.warning("Claude CLI may not be ready yet — sending command anyway")

        result = subprocess.run(
            [
                "tmux", "send-keys",
                "-t", "lacrimosa-conductor",
                "/lacrimosa start", "Enter",
            ],
            capture_output=True, text=True, timeout=5,
        )

        if result.returncode != 0:
            logger.error(f"tmux send-keys failed: {result.stderr.strip()}")
            return False

        # Record the tmux server PID for tracking
        try:
            pgrep = subprocess.run(
                ["tmux", "display-message", "-t", "lacrimosa-conductor",
                 "-p", "#{pane_pid}"],
                capture_output=True, text=True, timeout=5,
            )
            if pgrep.returncode == 0 and pgrep.stdout.strip():
                PID_FILE.write_text(pgrep.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        record_restart()
        logger.info("Conductor started in tmux session 'lacrimosa-conductor'")
        return True

    except FileNotFoundError:
        logger.error("'tmux' or 'claude' not found in PATH. Cannot restart conductor.")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Timed out starting conductor tmux session.")
        return False
    except Exception as e:
        logger.error(f"Failed to restart conductor: {e}")
        return False


# -- Main -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lacrimosa Watchdog — monitor and restart conductor",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check health without restarting",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logger = setup_logging(verbose=args.verbose)
    logger.info("Watchdog check starting")

    # Check if Lacrimosa is supposed to be running
    state = read_state()
    system_state = state.get("system_state", "Stopped")

    if system_state == "Stopped":
        logger.info("Lacrimosa state is 'Stopped' — nothing to do")
        return

    if system_state == "Stopping":
        logger.info("Lacrimosa state is 'Stopping' — letting it shut down gracefully")
        return

    # Check conductor health
    if is_conductor_healthy(logger):
        logger.info("Conductor is healthy")
        return

    # Check if conductor tmux session is alive — this is the primary health check.
    # If tmux is alive, conductor is running. If tmux is dead, restart regardless
    # of session_mode or state freshness.
    try:
        tmux_result = subprocess.run(
            ["tmux", "has-session", "-t", "lacrimosa-conductor"],
            capture_output=True, timeout=5,
        )
        if tmux_result.returncode == 0:
            logger.info("tmux session 'lacrimosa-conductor' is alive — skipping restart.")
            return
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # tmux session is dead. Distinguish normal exit from crash:
    # - State fresh (<10 min) + no active workers = completed work, exited cleanly
    #   → restart without counting as crash
    # - State stale (>10 min) OR active workers orphaned = crash
    #   → count as crash toward circuit breaker
    state_fresh = check_state_fresh(max_age_seconds=600)
    has_active_workers = bool(
        state.get("pipeline", {}).get("active_workers", {})
    )

    if state_fresh and not has_active_workers:
        logger.info(
            "tmux session ended but state is fresh and no orphaned workers — "
            "normal exit (work completed). Restarting without crash penalty."
        )
        # Don't call record_crash_time() — this is not a crash
    else:
        logger.warning(
            "tmux session 'lacrimosa-conductor' not found — "
            f"state_fresh={state_fresh}, active_workers={has_active_workers}. "
            "Counting as crash."
        )
        # This IS a crash — count it toward circuit breaker
        record_crash_time()
        save_crash_log(logger)

    # Force session_mode to daemon before restart
    state["session_mode"] = "daemon"
    write_state(state)

    # Check for ANY active Claude Code session (interactive or daemon)
    # before spawning a new one — prevents duplicate conductors
    try:
        result = subprocess.run(
            ["pgrep", "-fl", f"claude.*lacrimosa\\|claude.*{lacrimosa_config.get('product.name')}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            active_lines = [
                ln for ln in result.stdout.strip().splitlines()
                if "watchdog" not in ln and "pgrep" not in ln
            ]
            if active_lines:
                logger.info(
                    f"Active Claude session detected ({len(active_lines)} process(es)) "
                    "— skipping restart to avoid duplicate conductor"
                )
                return
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass  # pgrep not available or timed out — continue with normal checks

    # Conductor appears dead — run safety checks before restart
    logger.warning("Conductor appears unhealthy — running safety checks")
    # Note: crash tracking already handled above (normal exit vs crash distinction)

    # Safety: check state integrity (SEC-M04)
    if not check_state_integrity(logger):
        logger.error("State corruption detected — refusing restart. Manual intervention required.")
        state = read_state()
        state["system_state"] = "Stopped"
        write_state(state)
        return

    # Safety: check state size (CTO Decision 6, Layer 3)
    if check_state_size(logger):
        return

    # Safety: circuit breaker (CTO Decision 6, Layer 3)
    if check_circuit_breaker(logger):
        return

    # Cooldown check: don't restart too quickly
    watchdog_state = state.get("watchdog", {})
    last_restart = watchdog_state.get("last_restart")
    if last_restart:
        try:
            last_dt = datetime.fromisoformat(last_restart.replace("Z", "+00:00"))
            elapsed = (datetime.now(tz=timezone.utc) - last_dt).total_seconds()
            if elapsed < RESTART_COOLDOWN_SECONDS:
                logger.info(
                    f"Cooldown active ({int(elapsed)}s < {RESTART_COOLDOWN_SECONDS}s) — skipping"
                )
                return
        except (ValueError, TypeError):
            pass

    logger.info("Safety checks passed — attempting restart")
    success = restart_conductor(logger, dry_run=args.dry_run)
    if success:
        logger.info("Restart initiated successfully")
    else:
        logger.error("Restart failed — manual intervention required")

    logger.info("Watchdog check complete")


if __name__ == "__main__":
    main()
