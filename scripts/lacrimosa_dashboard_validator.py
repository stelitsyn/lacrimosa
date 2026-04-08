"""Lacrimosa Dashboard Validator — continuous data consistency checker.

Runs as part of the conductor cycle. Validates that dashboard data matches
actual state, fixes discrepancies, and logs issues.

Usage:
    PYTHONPATH=. python scripts/lacrimosa_dashboard_validator.py [--fix] [--verbose]
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

LOG_FILE = Path.home() / ".claude" / "lacrimosa" / "dashboard-audit.log"
STATE_FILE = Path.home() / ".claude" / "lacrimosa" / "state.json"
NATIVE_RL_FILE = Path("/tmp/lacrimosa-rl-native.json")
SESSIONS_DIR = Path("/tmp/lacrimosa-sessions")
DASHBOARD_URL = "http://localhost:1791"

logger = logging.getLogger("dashboard-validator")


def setup_logging(verbose: bool = False) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(LOG_FILE), mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if verbose:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ch)


class DashboardValidator:
    """Validates dashboard data consistency and auto-fixes where possible."""

    def __init__(self, fix: bool = True):
        self.fix = fix
        self.issues: list[dict[str, Any]] = []
        self.fixes_applied: list[str] = []

    def run(self) -> dict[str, Any]:
        """Run all validation checks. Returns summary."""
        state = self._read_state()
        if not state:
            return {"error": "Cannot read state.json"}

        self._check_state_schema(state)
        self._check_rate_limits(state)
        self._check_session_tokens(state)
        self._check_metrics_consistency(state)
        self._check_worker_state(state)
        self._check_ceremony_freshness(state)
        self._check_dashboard_responsive()

        if self.fix and self.fixes_applied:
            self._write_state(state)

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "issues_found": len(self.issues),
            "fixes_applied": len(self.fixes_applied),
            "details": self.issues,
            "fixes": self.fixes_applied,
        }

        if self.issues:
            logger.warning(
                "Validation: %d issues found, %d fixed",
                len(self.issues), len(self.fixes_applied),
            )
            for issue in self.issues:
                logger.info("  [%s] %s: %s", issue["severity"], issue["section"], issue["message"])
        else:
            logger.debug("Validation: all checks passed")

        return summary

    def _read_state(self) -> dict | None:
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Cannot read state.json: %s", e)
            return None

    def _write_state(self, state: dict) -> None:
        try:
            STATE_FILE.write_text(json.dumps(state, indent=2))
            logger.info("State.json updated with %d fixes", len(self.fixes_applied))
        except OSError as e:
            logger.error("Cannot write state.json: %s", e)

    def _add_issue(self, section: str, message: str, severity: str = "warning") -> None:
        self.issues.append({"section": section, "message": message, "severity": severity})

    def _check_state_schema(self, state: dict) -> None:
        """Validate state.json has all expected top-level sections and key fields."""
        # Required top-level sections
        required_sections = {
            "version": int,
            "system_state": str,
            "session_mode": str,
            "last_poll": (str, type(None)),
            "discovery": dict,
            "trust_scores": dict,
            "issues": dict,
            "daily_counters": dict,
            "vision_cache": dict,
            "rate_limits": dict,
            "pipeline": dict,
            "metrics_summary": dict,
        }
        for key, expected_type in required_sections.items():
            if key not in state:
                self._add_issue("schema", f"Missing top-level key: '{key}'", severity="error")
                if self.fix:
                    state[key] = {} if expected_type is dict else None
                    self.fixes_applied.append(f"Added missing key: {key}")

        # Required discovery fields
        disc = state.get("discovery", {})
        disc_fields = [
            "last_internal_sense", "last_external_sense", "last_strategy_analysis",
            "last_deep_research", "signals_pending_validation", "signals_validated_today",
            "signals_archived_today", "active_research_sprints", "signal_queue",
        ]
        for f in disc_fields:
            if f not in disc:
                self._add_issue("schema", f"Missing discovery.{f}")
                if self.fix:
                    disc[f] = [] if f == "signal_queue" else 0 if "count" in f or "today" in f or "sprint" in f else None
                    self.fixes_applied.append(f"Added discovery.{f}")

        # Required pipeline fields
        pipeline = state.get("pipeline", {})
        pipe_fields = ["research_queue", "architecture_queue", "implementation_queue",
                        "review_queue", "blocked", "active_workers", "active_teams"]
        for f in pipe_fields:
            if f not in pipeline:
                self._add_issue("schema", f"Missing pipeline.{f}")
                if self.fix:
                    pipeline[f] = {} if f == "active_workers" else []
                    self.fixes_applied.append(f"Added pipeline.{f}")

        # Required metrics_summary fields
        metrics = state.get("metrics_summary", {})
        for period in ("today", "last_7d"):
            if period not in metrics:
                self._add_issue("schema", f"Missing metrics_summary.{period}")
                if self.fix:
                    metrics[period] = {}
                    self.fixes_applied.append(f"Added metrics_summary.{period}")
        today_fields = ["cost_usd", "tasks_completed", "tokens_used", "avg_cost_per_task",
                        "cost_by_model", "cost_by_phase"]
        for f in today_fields:
            if f not in metrics.get("today", {}):
                self._add_issue("schema", f"Missing metrics_summary.today.{f}")
        week_fields = ["cost_usd", "tasks_completed", "revert_rate", "avg_review_iterations",
                        "prs_merged", "prs_reverted", "bugs_linked_total"]
        for f in week_fields:
            if f not in metrics.get("last_7d", {}):
                self._add_issue("schema", f"Missing metrics_summary.last_7d.{f}")

        # Required rate_limits fields
        rl = state.get("rate_limits", {})
        for f in ("five_hour_pct", "seven_day_pct", "throttle_level", "last_updated"):
            if f not in rl:
                self._add_issue("schema", f"Missing rate_limits.{f}")

        # Check version
        if state.get("version") != 3:
            self._add_issue("schema", f"State version is {state.get('version')}, expected 3", severity="error")

        # Today's daily_counters should exist
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in state.get("daily_counters", {}):
            self._add_issue("schema", f"No daily_counters entry for today ({today})")
            if self.fix:
                state.setdefault("daily_counters", {})[today] = {
                    "issues_created": 0, "parent_issues_dispatched": 0,
                    "prs_merged": 0, "workers_spawned": 0,
                    "signals_processed": 0, "signals_validated": 0,
                    "issues_discovered": 0, "teams_spawned": 0,
                }
                self.fixes_applied.append(f"Added daily_counters for {today}")

    def _check_rate_limits(self, state: dict) -> None:
        """Verify rate limits are fresh from native statusline file."""
        if not NATIVE_RL_FILE.exists():
            self._add_issue("rate_limits", "Native RL file missing — no active Claude session?")
            return

        try:
            native = json.loads(NATIVE_RL_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            self._add_issue("rate_limits", "Cannot parse native RL file")
            return

        updated_at = native.get("updated_at", 0)
        if updated_at:
            age_s = (datetime.now(timezone.utc) - datetime.fromtimestamp(updated_at, tz=timezone.utc)).total_seconds()
            if age_s > 120:
                self._add_issue("rate_limits", f"Native RL data is {int(age_s)}s old (>2 min)")

        # Check that state.json rate_limits reflect native data for throttle decisions
        rl = state.get("rate_limits", {})
        native_5h = native.get("five_hour_pct")
        if native_5h is not None and rl.get("five_hour_pct") != native_5h:
            if self.fix:
                rl["five_hour_pct"] = native_5h
                rl["seven_day_pct"] = native.get("seven_day_pct")
                rl["last_updated"] = datetime.now(timezone.utc).isoformat()
                worst = max(native_5h or 0, native.get("seven_day_pct") or 0)
                rl["throttle_level"] = "red" if worst >= 90 else "yellow" if worst >= 50 else "green"
                state["rate_limits"] = rl
                self.fixes_applied.append("Synced rate_limits from native RL file")

    def _check_session_tokens(self, state: dict) -> None:
        """Verify live session token data is available."""
        if not SESSIONS_DIR.exists() or not list(SESSIONS_DIR.glob("*.json")):
            self._add_issue("session_tokens", "No active session files in /tmp/lacrimosa-sessions/")
            return

        total_tokens = 0
        stale_sessions = 0
        for sf in SESSIONS_DIR.glob("*.json"):
            try:
                sd = json.loads(sf.read_text())
                total_tokens += sd.get("session_total_tokens", 0)
                updated = sd.get("updated_at", 0)
                if updated:
                    age = (datetime.now(timezone.utc) - datetime.fromtimestamp(updated, tz=timezone.utc)).total_seconds()
                    if age > 600:
                        stale_sessions += 1
            except (json.JSONDecodeError, OSError):
                pass

        if stale_sessions > 0:
            self._add_issue("session_tokens", f"{stale_sessions} stale session file(s) (>10 min old)")

        if total_tokens == 0:
            self._add_issue("session_tokens", "Total session tokens = 0")

    def _check_metrics_consistency(self, state: dict) -> None:
        """Verify metrics_summary matches issue data."""
        metrics = state.get("metrics_summary", {})
        issues = state.get("issues", {})

        # Count actual completed issues with phase_times
        completed_with_data = [
            i for i in issues.values()
            if i.get("state") == "Completed" and i.get("phase_times")
        ]

        # Check if recent_tasks matches completed issues
        recent = metrics.get("recent_tasks", [])
        if len(completed_with_data) > 0 and len(recent) == 0:
            self._add_issue("metrics", "Completed issues have phase_times but recent_tasks is empty")

        # Verify cost totals
        today_metrics = metrics.get("today", {})
        if today_metrics.get("tasks_completed", 0) > 0:
            reported_cost = today_metrics.get("cost_usd", 0) or 0
            # Cross-check against sum of recent task costs
            task_cost_sum = sum(t.get("cost_usd", 0) or 0 for t in recent[:today_metrics["tasks_completed"]])
            if task_cost_sum > 0 and abs(reported_cost - task_cost_sum) > 1.0:
                self._add_issue(
                    "metrics",
                    f"Today cost ${reported_cost:.2f} != sum of recent tasks ${task_cost_sum:.2f}",
                    severity="error",
                )

    def _check_worker_state(self, state: dict) -> None:
        """Verify active workers match pipeline state."""
        active = state.get("pipeline", {}).get("active_workers", {})
        issues = state.get("issues", {})

        for wid, w in active.items():
            if wid in issues:
                issue_state = issues[wid].get("state", "")
                phase = w.get("phase", "")
                # Check for stale workers (started > 2h ago with no update)
                started = w.get("started_at")
                if started:
                    try:
                        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                        age_h = (datetime.now(timezone.utc) - started_dt).total_seconds() / 3600
                        if age_h > 2:
                            self._add_issue(
                                "workers",
                                f"{wid} in phase '{phase}' for {age_h:.1f}h — may be stalled",
                            )
                    except (ValueError, TypeError):
                        pass

    def _check_ceremony_freshness(self, state: dict) -> None:
        """Check if ceremonies are running on schedule."""
        ceremonies = state.get("ceremonies", {})
        now = datetime.now(timezone.utc)

        checks = {
            "standup": ("standup", 4 * 3600),
            "sprint_planning": ("sprint_planning", 16 * 3600),
            "grooming": ("grooming", 12 * 3600),
        }

        for key, (state_key, max_age_s) in checks.items():
            cer = ceremonies.get(state_key, {})
            last_run = cer.get("last_run")
            if last_run:
                try:
                    lr_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    age = (now - lr_dt).total_seconds()
                    if age > max_age_s * 1.5:
                        self._add_issue(
                            "ceremonies",
                            f"{key} overdue: last run {int(age / 3600)}h ago (max {int(max_age_s / 3600)}h)",
                        )
                except (ValueError, TypeError):
                    pass
            else:
                self._add_issue("ceremonies", f"{key} has never run")

    def _check_dashboard_responsive(self) -> None:
        """Check dashboard responds and verify rendered values match state."""
        try:
            resp = urlopen(DASHBOARD_URL, timeout=5)
            if resp.status != 200:
                self._add_issue("dashboard", f"HTTP {resp.status}", severity="error")
                return
            html = resp.read().decode("utf-8")
            if len(html) < 1000:
                self._add_issue("dashboard", "Response too small — rendering may be broken")
                return
            if "Traceback" in html or "Error" in html[:200]:
                self._add_issue("dashboard", "Dashboard HTML contains error/traceback", severity="error")
                return
            # Run verification against state
            self._verify_dashboard_values(html)
        except (URLError, OSError) as e:
            self._add_issue("dashboard", f"Not responding: {e}", severity="error")

    def _verify_dashboard_values(self, html: str) -> None:
        """Verify dashboard HTML renders correct values from state + native data."""
        import re

        state = self._read_state()
        if not state:
            return

        # 1. Verify system state badge
        sys_state = state.get("system_state", "Stopped")
        if sys_state not in html:
            self._add_issue("verify", f"System state '{sys_state}' not found in dashboard HTML")

        # 2. Verify active worker count matches
        active = state.get("pipeline", {}).get("active_workers", {})
        expected_count = len(active)
        match = re.search(r"Active Workers \((\d+)\)", html)
        if match:
            rendered_count = int(match.group(1))
            if rendered_count != expected_count:
                self._add_issue(
                    "verify",
                    f"Active Workers shows {rendered_count} but state has {expected_count}",
                    severity="error",
                )

        # 3. Verify trust tier values
        for project, data in state.get("trust_scores", {}).items():
            merges = data.get("successful_merges", 0)
            if f">{merges}<" not in html and str(merges) not in html:
                self._add_issue("verify", f"Trust merges for {project} ({merges}) not in HTML")

        # 4. Verify today's cost if set
        today_cost = state.get("metrics_summary", {}).get("today", {}).get("cost_usd")
        if today_cost and today_cost > 0:
            cost_str = f"${today_cost:.2f}"
            if cost_str not in html:
                self._add_issue("verify", f"Today cost {cost_str} not found in dashboard")

        # 5. Verify completed issue IDs appear in recent completions
        completed = [
            iid for iid, i in state.get("issues", {}).items()
            if i.get("state") == "Completed" and i.get("pr_number")
        ]
        for iid in completed[:5]:
            if iid not in html:
                self._add_issue("verify", f"Completed issue {iid} not in dashboard HTML")

        # 6. Verify rate limit values match native file
        if NATIVE_RL_FILE.exists():
            try:
                native = json.loads(NATIVE_RL_FILE.read_text())
                rl_5h = native.get("five_hour_pct")
                if rl_5h is not None:
                    # Dashboard shows rounded integer percentage
                    pct_str = f"{int(rl_5h)}%"
                    if pct_str not in html:
                        self._add_issue(
                            "verify",
                            f"Rate limit 5h shows wrong value (expected {pct_str})",
                        )
            except (json.JSONDecodeError, OSError):
                pass

        # 7. Verify pending issues count
        pending_in_state = sum(
            1 for i in state.get("issues", {}).values()
            if i.get("state") not in ("Completed", "ResearchComplete", "ArchitectureComplete")
            and i.get("state") is not None
        )
        # Subtract active workers (they show in a different section)
        pending_display = pending_in_state - expected_count
        match = re.search(r"Pending Issues \((\d+)\)", html)
        if match:
            rendered_pending = int(match.group(1))
            if abs(rendered_pending - pending_display) > 1:
                self._add_issue(
                    "verify",
                    f"Pending Issues shows {rendered_pending} but expected ~{pending_display}",
                )

        # 8. Verify task pipeline has phase data for completed issues
        issues_with_phases = sum(
            1 for i in state.get("issues", {}).values()
            if i.get("phase_times") and isinstance(i.get("phase_times"), dict)
        )
        if issues_with_phases > 0 and "Task Pipeline" not in html:
            self._add_issue("verify", "Issues have phase_times but Task Pipeline section missing")

        # 9. Verify no "--" data placeholders where real data should exist
        # Count only "--" inside <td> or <div> tags (not CSS variable names like --bg)
        data_dashes = len(re.findall(r">--<", html))
        if today_cost and today_cost > 0 and data_dashes > 3:
            self._add_issue(
                "verify",
                f"Dashboard has {data_dashes} '--' data placeholders despite having real data",
                severity="warning",
            )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Lacrimosa Dashboard Validator")
    parser.add_argument("--fix", action="store_true", default=True, help="Auto-fix issues")
    parser.add_argument("--no-fix", action="store_true", help="Report only, don't fix")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    validator = DashboardValidator(fix=not args.no_fix)
    result = validator.run()

    if args.verbose:
        print(json.dumps(result, indent=2))
    elif result["issues_found"] > 0:
        print(f"Dashboard: {result['issues_found']} issues, {result['fixes_applied']} fixed")
        for issue in result["details"]:
            print(f"  [{issue['severity']}] {issue['section']}: {issue['message']}")
    else:
        print("Dashboard: all checks passed")


if __name__ == "__main__":
    main()
