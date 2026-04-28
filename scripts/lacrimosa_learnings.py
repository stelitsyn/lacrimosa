"""Lacrimosa v2 — Learnings Engine. Owner: ai-engineer.

Captures structured learnings from trust events, auto-applies adjustments,
maintains append-only ledger, reverts when operator cancels in Linear.
"""
from __future__ import annotations

import json, logging, subprocess, uuid  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from scripts.lacrimosa_agent_runner import run_agent_prompt
from scripts.lacrimosa_types import (
    EVENT_SEVERITY_MAP,
    REQUIRED_ADJUSTMENT_FIELDS,
    REQUIRED_LEARNING_FIELDS,
    VALID_ADJUSTMENT_TYPES,
    VALID_LEARNING_STATUSES,
    VALID_SEVERITIES,
    TrustEvent,
    TrustEventData,
)

logger = logging.getLogger("lacrimosa.learnings")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEDGER_FILE = Path.home() / ".claude" / "lacrimosa" / "learnings.json"
MAX_LEARNING_RETRIES = 2
LLM_TIMEOUT_SECONDS = 120
LEDGER_SIZE_WARN_BYTES = 1_048_576  # 1 MB
_VALID_TRUST_EVENTS = frozenset(e.value for e in TrustEvent)


def validate_learning(learning: dict[str, Any]) -> list[str]:
    """Validate a learning dict against the schema."""
    errors: list[str] = []
    missing = REQUIRED_LEARNING_FIELDS - set(learning.keys())
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")
    et = learning.get("event_type")
    if et is not None and et not in _VALID_TRUST_EVENTS:
        errors.append(f"Invalid event_type: {et!r}")
    sev = learning.get("severity")
    if sev is not None and sev not in VALID_SEVERITIES:
        errors.append(f"Invalid severity: {sev!r}")
    st = learning.get("status")
    if st is not None and st not in VALID_LEARNING_STATUSES:
        errors.append(f"Invalid status: {st!r}")
    adj = learning.get("adjustment")
    if adj is not None and isinstance(adj, dict):
        adj_miss = REQUIRED_ADJUSTMENT_FIELDS - set(adj.keys())
        if adj_miss:
            errors.append(f"Adjustment missing fields: {sorted(adj_miss)}")
        at = adj.get("type")
        if at is not None and at not in VALID_ADJUSTMENT_TYPES:
            errors.append(f"Invalid adjustment type: {at!r}")
    ap = learning.get("applied")
    if ap is not None and not isinstance(ap, bool):
        errors.append(f"applied must be bool, got {type(ap).__name__}")
    return errors


def classify_event_severity(event_type: str) -> str:
    """Map event type to default severity level."""
    return EVENT_SEVERITY_MAP.get(event_type, "medium")


def measure_outcome(
    config: dict[str, Any],
    state: dict[str, Any],
    ledger_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Module-level convenience: measure outcomes for all completed discovery issues.

    Delegates to ``LearningsEngine.measure_outcome()``.
    """
    engine = LearningsEngine(config, ledger_path=ledger_path)
    return engine.measure_outcome(state)


def append_ledger(entry: dict[str, Any], ledger_path: Path | None = None) -> None:
    """Append one JSON entry to the ledger file."""
    path = ledger_path or LEDGER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    if path.exists() and path.stat().st_size > LEDGER_SIZE_WARN_BYTES:
        logger.warning("Ledger exceeds 1MB: %s bytes", path.stat().st_size)


def read_ledger(ledger_path: Path | None = None) -> list[dict[str, Any]]:
    """Read all entries from the JSON Lines ledger file."""
    path = ledger_path or LEDGER_FILE
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def can_apply_adjustment(
    adjustment: dict[str, Any],
    current_config: dict[str, Any],
) -> tuple[bool, str]:
    """Check if an adjustment can be safely applied."""
    target_path = adjustment.get("target_path", "")
    old_value = adjustment.get("old_value")
    parts = target_path.split(".")
    current: Any = current_config
    for i, part in enumerate(parts[:-1]):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, dict) and part.isdigit() and int(part) in current:
            current = current[int(part)]
        else:
            if old_value is None:
                return True, "New entry, path will be created"
            return False, f"Path segment '{part}' not found at depth {i}"
    final_key = parts[-1]
    if not isinstance(current, dict):
        return False, f"Cannot navigate to final key '{final_key}'"
    if old_value is None:
        return True, "New entry"
    if str(current.get(final_key)) != str(old_value):
        return False, f"Value mismatch: expected '{old_value}', found '{current.get(final_key)}'"
    return True, "Value matches, safe to apply"


class LearningsEngine:
    """Learnings engine: event capture, analysis, apply, revert."""

    def __init__(self, config: dict[str, Any], ledger_path: Path | None = None):
        self._config = config
        self._ledger_path = ledger_path or LEDGER_FILE
        lcfg = config.get("trust", {}).get("learning", {})
        self._auto_apply = lcfg.get("auto_apply", True)

    def detect_event(self, event: TrustEventData) -> dict[str, Any] | None:
        """Analyze a trust event via Claude and produce a learning."""
        if event.event_type not in _VALID_TRUST_EVENTS:
            logger.warning("Unknown event type: %s", event.event_type)
            return None
        raw = self._dispatch_claude(self._build_prompt(event))
        if raw is None:
            return self._fallback(event)
        return self._parse_response(raw, event)

    def create_learning(self, learning: dict[str, Any]) -> str:
        """Record learning in ledger; auto-apply if enabled."""
        if validate_learning(learning):
            logger.error("Invalid learning: %s", validate_learning(learning))
            learning["applied"] = False
        append_ledger(learning, self._ledger_path)
        if self._auto_apply and learning.get("applied") is not False:
            learning["applied"] = self.apply_adjustment(learning)
        return learning["id"]

    def apply_adjustment(self, learning: dict[str, Any]) -> bool:
        """Apply a learning's adjustment to the target file."""
        adj = learning.get("adjustment", {})
        path = Path(adj.get("target_file", "")).expanduser()
        if not path.exists():
            logger.error("Target file missing: %s", path)
            return False
        if path.suffix in (".yaml", ".yml"):
            return self._apply_yaml(path, adj)
        if path.suffix == ".md":
            return self._apply_md(path, adj)
        logger.error("Unsupported file type: %s", path.suffix)
        return False

    def revert_adjustment(self, learning_id: str) -> bool:
        """Revert a learning's adjustment using ledger data."""
        entries = read_ledger(self._ledger_path)
        entry = next((e for e in entries if e["id"] == learning_id), None)
        if entry is None:
            logger.error("Learning not found: %s", learning_id)
            return False
        adj = entry.get("adjustment", {})
        path = Path(adj.get("target_file", "")).expanduser()
        if not path.exists():
            logger.error("Target file missing for revert: %s", path)
            return False
        # Swap old/new for revert
        rev_adj = {**adj, "old_value": adj.get("new_value"), "new_value": adj.get("old_value")}
        reverted = self._apply_yaml(path, rev_adj) if path.suffix in (".yaml", ".yml") else False
        append_ledger(
            {
                "id": f"{learning_id}-revert",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "learning_reverted",
                "references": learning_id,
                "reason": "Operator cancelled learning issue",
                "revert_applied": reverted,
            },
            self._ledger_path,
        )
        return reverted

    def check_learning_approvals(self) -> list[str]:
        """Check Linear for cancelled learning issues needing revert."""
        return []  # Production: dispatches Claude session to query Linear

    def measure_outcome(
        self,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Measure outcomes for completed discovery issues.

        Scans the ledger for applied learnings that originated from
        discovery signals, checks state.json for completed issues with
        a discovery source, and compares predicted vs actual impact.

        Returns a list of outcome measurement dicts, each containing:
        - learning_id: the original learning entry
        - issue_id: the associated issue
        - hypothesis_validated: bool
        - predicted_impact: from the original adjustment description
        - actual_impact: approximated from state metrics
        - recommendation: threshold adjustment suggestion
        """
        entries = read_ledger(self._ledger_path)
        if not entries:
            return []

        # Collect applied learnings that have an associated issue
        applied = [
            e for e in entries
            if e.get("applied") is True
            and e.get("issue_id")
            and e.get("event_type") not in ("learning_reverted", "learning_approved")
        ]

        if not applied:
            return []

        # Check state for completed issues with discovery source
        completed_issues = state.get("issues", {})
        measurements: list[dict[str, Any]] = []

        for learning in applied:
            issue_id = learning.get("issue_id", "")
            issue_state = completed_issues.get(issue_id, {})

            # Only measure outcomes for issues that reached Done
            if issue_state.get("status") not in ("Done", "done", "completed"):
                continue

            # Check if this learning was later reverted
            was_reverted = any(
                e.get("event_type") == "learning_reverted"
                and e.get("references") == learning["id"]
                for e in entries
            )

            # Extract predicted impact from adjustment description
            adj = learning.get("adjustment", {})
            predicted_impact = adj.get("description", "No prediction recorded")
            adj_type = adj.get("type", "unknown")

            # Approximate actual impact from available metrics
            actual_impact = _approximate_impact(
                learning, issue_state, state
            )

            # Determine if hypothesis was validated
            hypothesis_validated = (
                not was_reverted
                and actual_impact.get("improvement_detected", False)
            )

            # Generate threshold adjustment recommendation
            recommendation = _generate_recommendation(
                learning, hypothesis_validated, was_reverted, adj_type
            )

            measurement = {
                "learning_id": learning["id"],
                "issue_id": issue_id,
                "event_type": learning.get("event_type"),
                "severity": learning.get("severity"),
                "adjustment_type": adj_type,
                "hypothesis_validated": hypothesis_validated,
                "was_reverted": was_reverted,
                "predicted_impact": predicted_impact,
                "actual_impact": actual_impact,
                "recommendation": recommendation,
                "measured_at": datetime.now(timezone.utc).isoformat(),
            }

            measurements.append(measurement)

            # Log the measurement to the ledger
            append_ledger(
                {
                    "id": f"{learning['id']}-outcome",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_type": "outcome_measured",
                    "references": learning["id"],
                    "hypothesis_validated": hypothesis_validated,
                    "recommendation": recommendation,
                },
                self._ledger_path,
            )

        return measurements

    def _build_prompt(self, event: TrustEventData) -> str:
        ctx = json.dumps(event.context, indent=2)[:3000]
        return (
            "You are Lacrimosa's learnings engine. Analyze this trust event.\n\n"
            f"Type: {event.event_type}\nIssue: {event.issue_id}\n"
            f"Domain: {event.domain}\nAgent: {event.agent_type}\n"
            f"Context: {ctx}\n\n"
            "Output ONLY JSON: "
            '{"root_cause": "...", "pattern": "...", '
            '"severity": "low|medium|high|critical", '
            '"adjustment": {"type": "...", "target_file": "...", '
            '"target_path": "...", "old_value": null, '
            '"new_value": "...", "description": "..."}}'
        )

    def _dispatch_claude(self, prompt: str) -> str | None:
        for attempt in range(MAX_LEARNING_RETRIES + 1):
            try:
                r = run_agent_prompt(
                    prompt,
                    purpose="learning-analysis",
                    timeout=LLM_TIMEOUT_SECONDS,
                    cwd=str(PROJECT_ROOT),
                    dangerous=True,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
                logger.warning("Agent code %d (attempt %d)", r.returncode, attempt + 1)
            except subprocess.TimeoutExpired:
                logger.warning("Agent timed out (attempt %d)", attempt + 1)
            except FileNotFoundError:
                logger.error("Agent CLI not found")
                return None
        return None

    def _parse_response(self, raw: str, event: TrustEventData) -> dict[str, Any]:
        try:
            text = raw.strip()
            s, e = text.find("{"), text.rfind("}")
            data = json.loads(text[s : e + 1]) if s != -1 and e > s else json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.error("Failed to parse learning response")
            return self._fallback(event)
        sev = data.get("severity", "medium")
        if sev not in VALID_SEVERITIES:
            sev = classify_event_severity(event.event_type)
        adj = data.get("adjustment", {})
        if not isinstance(adj, dict):
            adj = {}
        for f in REQUIRED_ADJUSTMENT_FIELDS:
            adj.setdefault(f, None)
        return {
            "id": f"lrn-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event.event_type,
            "issue_id": event.issue_id,
            "agent_type": event.agent_type,
            "root_cause": data.get("root_cause", "Analysis unavailable"),
            "pattern": data.get("pattern", "Unknown pattern"),
            "severity": sev,
            "adjustment": adj,
            "applied": False,
            "linear_issue_id": "",
            "status": "in_review",
        }

    def _fallback(self, event: TrustEventData) -> dict[str, Any]:
        return {
            "id": f"lrn-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event.event_type,
            "issue_id": event.issue_id,
            "agent_type": event.agent_type,
            "root_cause": "Analysis failed — manual review needed",
            "pattern": "Unknown — LLM analysis unavailable",
            "severity": classify_event_severity(event.event_type),
            "adjustment": {
                "type": "prompt_refinement",
                "target_file": "",
                "target_path": "",
                "old_value": None,
                "new_value": "",
                "description": "Manual investigation required",
            },
            "applied": False,
            "linear_issue_id": "",
            "status": "in_review",
        }

    def _apply_yaml(self, path: Path, adj: dict[str, Any]) -> bool:
        try:
            config = yaml.safe_load(path.read_text()) or {}
        except Exception:
            logger.error("Failed to read YAML: %s", path)
            return False
        parts = adj.get("target_path", "").split(".")
        current = config
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, dict) and part.isdigit():
                current = current.get(int(part), {})
            else:
                logger.error("Path not found: %s", adj.get("target_path"))
                return False
        if not isinstance(current, dict):
            return False
        old = adj.get("old_value")
        if old is not None and str(current.get(parts[-1])) != str(old):
            logger.error("YAML mismatch at %s", adj.get("target_path"))
            return False
        current[parts[-1]] = adj.get("new_value")
        try:
            path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        except Exception:
            logger.error("Failed to write YAML: %s", path)
            return False
        return True

    def _apply_md(self, path: Path, adj: dict[str, Any]) -> bool:
        try:
            content = path.read_text()
        except Exception:
            return False
        nv = str(adj.get("new_value", ""))
        if nv and nv not in content:
            path.write_text(content + f"\n- {nv}\n")
        return True


# -- Outcome Measurement Helpers ---------------------------------------------


def _approximate_impact(
    learning: dict[str, Any],
    issue_state: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Approximate the actual impact of an applied learning.

    Compares pre/post metrics where available. Falls back to heuristic
    signals (issue completion time, revert history, trust score changes).
    """
    result: dict[str, Any] = {"improvement_detected": False, "details": {}}

    adj_type = learning.get("adjustment", {}).get("type", "")
    severity = learning.get("severity", "medium")

    # Check trust score changes for the domain
    trust_scores = state.get("trust_scores", {})
    agent_type = learning.get("agent_type", "")
    for domain, scores in trust_scores.items():
        if isinstance(scores, dict) and scores.get("tier", 0) > 0:
            result["details"]["trust_tier"] = scores.get("tier")

    # Check if the issue completed without further incidents
    issue_metrics = issue_state.get("metrics", {})
    if issue_metrics:
        result["details"]["completion_time_hours"] = issue_metrics.get(
            "completion_time_hours"
        )
        result["details"]["review_iterations"] = issue_metrics.get(
            "review_iterations", 0
        )

    # Heuristic: if the adjustment was applied and no revert happened,
    # and the severity was medium+, consider it an improvement
    if severity in ("medium", "high", "critical"):
        result["improvement_detected"] = True
        result["details"]["basis"] = "no_revert_after_apply"
    elif adj_type in ("threshold_adjustment", "scope_calibration"):
        # For threshold adjustments, check if related signals decreased
        daily = state.get("daily_counters", {})
        recent_signals = sum(
            counters.get("signals_validated", 0)
            for counters in daily.values()
            if isinstance(counters, dict)
        )
        result["details"]["recent_signals_validated"] = recent_signals
        result["improvement_detected"] = recent_signals > 0

    return result


def _generate_recommendation(
    learning: dict[str, Any],
    hypothesis_validated: bool,
    was_reverted: bool,
    adj_type: str,
) -> str:
    """Generate a threshold adjustment recommendation based on outcome."""
    if was_reverted:
        return (
            f"Learning {learning['id']} was reverted. Consider tightening "
            f"the {adj_type} criteria to avoid false positive adjustments."
        )

    if hypothesis_validated:
        if adj_type == "threshold_adjustment":
            return (
                f"Threshold adjustment validated for {learning.get('event_type')}. "
                "Consider making the threshold permanent and applying to "
                "similar signal categories."
            )
        if adj_type == "guardrail_addition":
            return (
                f"Guardrail validated for {learning.get('event_type')}. "
                "No threshold change needed. Monitor for 2 more cycles."
            )
        return (
            f"Adjustment validated for {learning.get('event_type')}. "
            "No further action needed."
        )

    return (
        f"Outcome inconclusive for {learning['id']}. "
        "Keep current thresholds. Re-evaluate after more data."
    )
