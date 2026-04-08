"""Lacrimosa self-observability — meta-sensor + auto-tuning.

MetaSensor collects 6 metric categories from existing modules.
AutoTuner evaluates reactive/proactive rules and tracks changes.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.lacrimosa_metrics import compute_daily_summary, get_trend_data
from scripts.lacrimosa_types import (
    AutoTuneEntry,
    MetaSensorSnapshot,
    ProactiveRule,
    ReactiveRule,
    DEFAULT_IMPACT_WINDOW_HOURS,
    MAX_TUNE_ENTRIES_PER_CYCLE,
)

logger = logging.getLogger(__name__)
_UTC = timezone.utc
AUTO_TUNE_LOG = Path.home() / ".claude" / "lacrimosa" / "auto_tune_log.jsonl"


class MetaSensor:
    """Collects Lacrimosa's own performance metrics into a snapshot."""

    def __init__(self, config: dict[str, Any], state: dict[str, Any]) -> None:
        self._config = config
        self._state = state

    def collect(self) -> MetaSensorSnapshot:
        summary = compute_daily_summary()
        trend = get_trend_data(days=7)
        return MetaSensorSnapshot(
            timestamp=datetime.now(_UTC).isoformat(),
            throughput=self._throughput(summary, trend),
            quality=self._quality(summary),
            cost=self._cost(summary),
            discovery=self._discovery(),
            ceremony=self._ceremony(),
            system=self._system(),
            specialists=self._specialists(),
        )

    def _throughput(self, s: dict, trend: list) -> dict[str, float]:
        avg_ttm = 0.0
        if trend:
            durations = [t.get("average_duration_ms", 0) for t in trend]
            avg_ttm = (sum(durations) / len(durations)) / 3_600_000
        return {
            "issues_completed": s.get("tasks_completed", 0),
            "prs_merged": s.get("prs_merged", 0),
            "avg_time_to_merge_hours": avg_ttm,
        }

    def _quality(self, s: dict) -> dict[str, float]:
        tc = max(s.get("tasks_completed", 0), 1)
        return {
            "revert_rate": s.get("revert_rate", 0.0),
            "avg_review_iterations": s.get("average_review_iterations", 0.0),
            "bugs_per_task": s.get("bugs_linked_total", 0) / tc,
        }

    def _cost(self, s: dict) -> dict[str, Any]:
        pm = max(s.get("prs_merged", 0), 1)
        return {
            "tokens_per_task": s.get("average_tokens_per_task", 0),
            "cost_per_merged_pr": s.get("total_cost_usd", 0.0) / pm,
            "total_daily_cost_usd": s.get("total_cost_usd", 0.0),
        }

    def _discovery(self) -> dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        counters = self._state.get("daily_counters", {}).get(today, {})
        sp = counters.get("signals_processed", 0)
        sv = counters.get("signals_validated", 0)
        if sp == 0 and sv == 0:
            return {
                "signals_processed": 0,
                "signals_validated": 0,
                "signal_to_issue_rate": None,
                "false_positive_rate": None,
            }
        issued = counters.get("issues_discovered", 0)
        sir = issued / max(sv, 1)
        return {
            "signals_processed": sp,
            "signals_validated": sv,
            "signal_to_issue_rate": sir,
            "false_positive_rate": max(0.0, min(1.0, 1.0 - sir)),
        }

    def _ceremony(self) -> dict[str, Any]:
        ceremonies = self._state.get("ceremonies", {})
        cfg = self._config.get("ceremonies", {})
        now = datetime.now(_UTC)
        missed = 0
        ages: dict[str, float] = {}
        for name, data in ceremonies.items():
            lr = data.get("last_run")
            cadence_h = cfg.get(name, {}).get("cadence_hours")
            if lr and cadence_h:
                try:
                    dt = datetime.fromisoformat(lr.replace("Z", "+00:00"))
                    hours_since = (now - dt).total_seconds() / 3600
                    ages[name] = hours_since
                    missed += int(hours_since / cadence_h)
                except (ValueError, TypeError):
                    pass
        return {"missed_count": missed, "last_run_ages": ages}

    def _specialists(self) -> dict[str, dict]:
        """Read specialist health from state."""
        specs = self._state.get("specialists", {})
        if isinstance(specs, dict):
            return {
                name: {
                    "cycles_completed": data.get("cycles_completed", 0),
                    "consecutive_errors": data.get("consecutive_errors", 0),
                    "restarts_24h": data.get("restarts_24h", 0),
                }
                for name, data in specs.items()
                if isinstance(data, dict)
            }
        return {}

    def _system(self) -> dict[str, Any]:
        rl = self._state.get("rate_limits", {})
        return {
            "rate_limit_5h_pct": rl.get("five_hour", {}).get("used_percentage", 0),
            "rate_limit_7d_pct": rl.get("seven_day", {}).get("used_percentage", 0),
            "throttle_level": rl.get("throttle_level", "green"),
            "active_workers": len(self._state.get("pipeline", {}).get("active_workers", {})),
            "conductor_uptime_hours": 0,
        }


class AutoTuner:
    """Evaluates reactive/proactive rules and tracks auto-tune changes."""

    def __init__(self, config: dict[str, Any], learnings_engine: Any) -> None:
        self._learnings = learnings_engine
        self._cooldowns: dict[str, datetime] = {}
        sm = config.get("self_monitor", {})
        self._reactive = self._load_rules(sm.get("reactive_rules", {}), True)
        self._proactive = self._load_rules(sm.get("proactive_rules", {}), False)
        tracking = sm.get("tracking", {})
        self._log_path = Path(tracking.get("log_file", str(AUTO_TUNE_LOG))).expanduser()
        self._impact_hours = tracking.get(
            "default_impact_window_hours", DEFAULT_IMPACT_WINDOW_HOURS
        )

    def evaluate(self, snapshots: list[MetaSensorSnapshot]) -> list[AutoTuneEntry]:
        if not snapshots:
            return []
        entries: list[AutoTuneEntry] = []
        for rule in self._reactive:
            if not self._in_cooldown(rule.name) and self._fires(rule, snapshots):
                entries.append(self._create_entry(rule, "reactive", snapshots))
        for rule in self._proactive:
            if not self._in_cooldown(rule.name) and self._fires(rule, snapshots):
                entries.append(self._create_entry(rule, "proactive", snapshots))
        return entries[:MAX_TUNE_ENTRIES_PER_CYCLE]

    def apply_entry(self, entry: AutoTuneEntry) -> bool:
        self._learnings.create_learning(
            {
                "id": entry.learning_id or f"lrn-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(_UTC).isoformat(),
                "event_type": "auto_tune_applied",
                "issue_id": "",
                "agent_type": "self_monitor",
                "root_cause": f"Rule {entry.trigger_rule} fired",
                "pattern": entry.action,
                "severity": "medium",
                "adjustment": {
                    "type": "threshold_adjustment",
                    "target_file": entry.target_file,
                    "target_path": entry.target_path,
                    "old_value": entry.old_value,
                    "new_value": entry.new_value,
                    "description": entry.action,
                },
                "applied": True,
                "linear_issue_id": "",
                "status": "in_review",
            }
        )
        self._cooldowns[entry.trigger_rule] = datetime.now(_UTC)
        self._append_log(entry)
        return True

    def check_impact(
        self,
        entries: list[AutoTuneEntry],
        snapshot: MetaSensorSnapshot,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for entry in entries:
            current = self._get_metric(snapshot, entry.target_path)
            old = entry.old_value
            if current is not None and old is not None:
                delta = current - old
                if delta > 0:
                    verdict = "degraded"
                    if entry.learning_id:
                        self._learnings.revert_adjustment(entry.learning_id)
                elif delta < 0:
                    verdict = "improved"
                else:
                    verdict = "no_change"
            else:
                delta, verdict = None, "no_change"
            results.append({"entry_id": entry.id, "verdict": verdict, "delta": delta})
        return results

    # -- Rule evaluation -----------------------------------------------------

    def _fires(
        self, rule: ReactiveRule | ProactiveRule, snapshots: list[MetaSensorSnapshot]
    ) -> bool:
        if len(snapshots) < rule.window_days:
            return False
        window = snapshots[-rule.window_days :]
        values = [self._get_metric(s, rule.metric_path) for s in window]
        values = [v for v in values if v is not None]
        if not values or len(values) < rule.window_days:
            return False
        if rule.operator == "trend_declining":
            return all(values[i] > values[i + 1] for i in range(len(values) - 1))
        if rule.operator == "==":
            return all(v == rule.threshold for v in values)
        avg = sum(values) / len(values)
        return {
            ">": avg > rule.threshold,
            "<": avg < rule.threshold,
            ">=": avg >= rule.threshold,
            "<=": avg <= rule.threshold,
        }.get(rule.operator, False)

    def _get_metric(self, snap: MetaSensorSnapshot, path: str) -> float | None:
        parts = path.split(".")
        current: Any = getattr(snap, parts[0], None)
        for part in parts[1:]:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current if isinstance(current, (int, float)) else None

    def _create_entry(
        self,
        rule: ReactiveRule | ProactiveRule,
        change_type: str,
        snapshots: list[MetaSensorSnapshot],
    ) -> AutoTuneEntry:
        return AutoTuneEntry(
            id=f"tune-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(_UTC).isoformat(),
            trigger_rule=rule.name,
            change_type=change_type,
            action=rule.action,
            target_file="",
            target_path=rule.metric_path,
            old_value=self._get_metric(snapshots[-1], rule.metric_path),
            new_value=None,
            applied_at=None,
            impact_window_hours=self._impact_hours,
            measured_impact=None,
            reverted=False,
            learning_id=None,
        )

    def _in_cooldown(self, rule_name: str) -> bool:
        last = self._cooldowns.get(rule_name)
        if last is None:
            return False
        return (datetime.now(_UTC) - last).total_seconds() < 86400

    def _append_log(self, entry: AutoTuneEntry) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as f:
            f.write(json.dumps(asdict(entry), default=str) + "\n")

    @staticmethod
    def _load_rules(raw: dict[str, Any], reactive: bool) -> list:
        rules: list = []
        for name, cfg in raw.items():
            if reactive:
                rules.append(
                    ReactiveRule(
                        name=name,
                        metric_path=cfg["metric_path"],
                        operator=cfg["operator"],
                        threshold=cfg.get("threshold", 0),
                        window_days=cfg.get("window_days", 1),
                        action=cfg.get("action", ""),
                        severity=cfg.get("severity", "medium"),
                        adjustment=cfg.get("adjustment"),
                    )
                )
            else:
                rules.append(
                    ProactiveRule(
                        name=name,
                        metric_path=cfg["metric_path"],
                        operator=cfg["operator"],
                        threshold=cfg.get("threshold", 0),
                        window_days=cfg.get("window_days", 1),
                        action=cfg.get("action", ""),
                        adjustment=cfg.get("adjustment"),
                    )
                )
        return rules


# -- Top-level entry points --------------------------------------------------


def run_self_monitor(
    config: dict[str, Any],
    state: dict[str, Any],
    state_manager: Any,
    learnings_engine: Any,
) -> dict[str, Any]:
    """Run self-observability cycle. Conductor calls this on 4h cadence."""
    if state.get("rate_limits", {}).get("throttle_level") == "red":
        return {"skipped": True, "reason": "rate_limit_red"}
    snapshot = MetaSensor(config, state).collect()
    tuner = AutoTuner(config, learnings_engine)
    entries = tuner.evaluate([snapshot])
    for entry in entries:
        tuner.apply_entry(entry)
    pending = state.get("self_monitor", {}).get("pending_tune_entries", [])
    impact = tuner.check_impact(pending, snapshot) if pending else []
    return {"snapshot": snapshot, "triggered_entries": entries, "impact_results": impact}


def read_tune_log(path: Path | None = None) -> list[dict[str, Any]]:
    """Read auto-tune log entries from JSONL file."""
    p = path or AUTO_TUNE_LOG
    if not p.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
