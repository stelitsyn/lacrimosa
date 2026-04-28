"""Internal sensor orchestrator and 6 sensor implementations."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TypedDict

from scripts import lacrimosa_config
from scripts.lacrimosa_agent_runner import run_agent_prompt
from scripts.lacrimosa_signals import create_signal, persist_signal

logger = logging.getLogger(__name__)

# -- Types -------------------------------------------------------------------


class SensorResult(TypedDict):
    signals: list[dict[str, Any]]
    errors: list[str]
    duration_seconds: float


# -- Sensor Registry ---------------------------------------------------------

SENSOR_FUNCTIONS: dict[str, str] = {
    "funnel_analyzer": "sense_funnel",
    "error_pattern_detector": "sense_errors",
    "feedback_analyzer": "sense_feedback",
    "payment_anomaly_detector": "sense_payments",
    "usage_pattern_analyzer": "sense_usage",
}


# -- Public Orchestration ----------------------------------------------------


def run_all_sensors(
    config: dict[str, Any],
    signals_dir: Path | None = None,
) -> list[SensorResult]:
    """Run all 6 internal sensors. Single failure does not halt cycle."""
    results: list[SensorResult] = []
    for sensor_name in SENSOR_FUNCTIONS:
        result = run_sensor(sensor_name, config, signals_dir)
        results.append(result)
    return results


def run_sensor(
    sensor_name: str,
    config: dict[str, Any],
    signals_dir: Path | None = None,
) -> SensorResult:
    """Run a named sensor and return its SensorResult."""
    if sensor_name not in SENSOR_FUNCTIONS:
        raise ValueError(f"Unknown sensor: {sensor_name!r}")

    fn_name = SENSOR_FUNCTIONS[sensor_name]
    fn = globals()[fn_name]
    start = time.monotonic()

    try:
        signals = fn(config)
        for sig in signals:
            try:
                persist_signal(sig, signals_dir=signals_dir)
            except Exception as exc:
                logger.warning("Failed to persist signal: %s", exc)
        elapsed = time.monotonic() - start
        return SensorResult(
            signals=signals,
            errors=[],
            duration_seconds=elapsed,
        )
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.error("Sensor %s failed: %s", sensor_name, exc)
        return SensorResult(
            signals=[],
            errors=[str(exc)],
            duration_seconds=elapsed,
        )


# -- Data Fetchers -----------------------------------------------------------


# -- Individual Sensors ------------------------------------------------------


def sense_funnel(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze GA4 funnel data via existing script."""
    script = (
        config.get("sensors", {})
        .get(
            "funnel_analyzer",
            {},
        )
        .get("script", "scripts/ga4_audit_to_linear.py")
    )

    # Run with --format json (outputs findings as JSON array to stdout).
    result = subprocess.run(
        [sys.executable, script, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        logger.warning("Funnel script failed: %s", result.stderr)
        return []

    return _parse_script_output(
        result.stdout,
        source="ga4",
        sensor="funnel-analyzer",
        category="error-pattern",
    )


def sense_errors(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect error patterns via existing script."""
    script = (
        config.get("sensors", {})
        .get(
            "error_pattern_detector",
            {},
        )
        .get("script", "scripts/analyze_business_flows.py")
    )

    result = subprocess.run(
        [sys.executable, script, "--output", "json"],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        logger.warning("Error script failed: %s", result.stderr)
        return []

    return _parse_script_output(
        result.stdout,
        source="cloud-logging",
        sensor="error-pattern-detector",
        category="error-pattern",
    )


def sense_feedback(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze user feedback via dispatched Claude session (LLM)."""
    _product = lacrimosa_config.get("product.name")
    prompt = (
        f"Analyze recent user feedback for {_product}. "
        "Identify recurring complaints (3+ users), sentiment clusters, "
        "and feature requests. Output ONLY a JSON array of signals, each with: "
        'category ("pain-point"|"feature-gap"|"quality-issue"), '
        "summary, reach (int), sentiment (-1.0 to 1.0), "
        "relevance_tags (list), raw_content (representative quotes)."
    )
    return _dispatch_llm_sensor(
        prompt,
        source="feedback",
        sensor="feedback-analyzer",
    )


def sense_payments(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect payment anomalies via Cloud Logging scan.

    Uses analyze_business_flows.py --channel payment to scan Cloud Run logs
    for Stripe webhook failures, failed payments, and churn signals.
    """
    script = (
        config.get("sensors", {})
        .get("payment_anomaly_detector", {})
        .get("script", "scripts/analyze_business_flows.py")
    )

    result = subprocess.run(
        [
            sys.executable, script,
            "--channel", "payment",
            "--lookback-hours", "24",
            "--output", "json",
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        logger.warning("Payment script failed: %s", result.stderr)
        return []

    return _parse_script_output(
        result.stdout,
        source="stripe",
        sensor="payment-anomaly-detector",
        category="churn-signal",
    )


def sense_usage(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect usage pattern anomalies via dispatched Claude session (LLM).

    Analyzes GA4 behavioral data and goal completion patterns to detect
    feature adoption gaps, engagement drops, and power user patterns.
    """
    _product = lacrimosa_config.get("product.name")
    prompt = (
        "Analyze recent GA4 behavioral data and goal completion patterns "
        f"for {_product}. Look for:\n"
        "1. Feature adoption gaps (features available but underused)\n"
        "2. Engagement drops (declining session duration, fewer return visits)\n"
        "3. Power user patterns (features heavily used by a small cohort "
        "that could benefit broader audience)\n"
        "4. Conversion funnel leaks (users dropping off before completing "
        "key goals like making a call or setting up a task)\n\n"
        "Only report patterns with clear evidence across 5+ users. "
        "Output ONLY a JSON array of signals, each with: "
        'category ("feature-gap"), summary, reach (int), '
        "sentiment (-1.0 to 1.0), relevance_tags (list), "
        "raw_content (representative data points), "
        "competitor_count (int, how many competitors offer this feature)."
    )
    return _dispatch_llm_sensor(
        prompt,
        source="usage",
        sensor="usage-pattern-analyzer",
        default_category="feature-gap",
    )


# -- Private Helpers ---------------------------------------------------------


def _parse_script_output(
    stdout: str,
    source: str,
    sensor: str,
    category: str,
) -> list[dict[str, Any]]:
    """Parse JSON array from script output into signal dicts.

    Handles mixed output (human-readable + JSON) by extracting the first
    JSON array found in stdout.
    """
    raw = stdout.strip()
    items = None

    # Try direct parse first
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Extract JSON array from mixed output
        extracted = _extract_json(raw)
        if extracted:
            try:
                items = json.loads(extracted)
            except (json.JSONDecodeError, ValueError):
                pass

    if items is None:
        logger.warning("Could not parse script output as JSON for %s", sensor)
        return []

    # If the output is a wrapper object (e.g. analyze_business_flows.py),
    # extract the inner array from known keys.
    if isinstance(items, dict):
        for key in ("anomalies", "findings", "signals", "items", "results"):
            if key in items and isinstance(items[key], list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        items = [items]

    signals: list[dict[str, Any]] = []
    for item in items:
        summary = item.get("summary", item.get("event", str(item)))
        raw = item.get("raw_content", json.dumps(item))
        try:
            sig = create_signal(
                source=source,
                sensor=sensor,
                category=category,
                raw_content=str(raw)[:5000],
                summary=str(summary)[:500],
                reach=int(item.get("reach", item.get("count", 1))),
                sentiment=float(item.get("sentiment", -0.5)),
                relevance_tags=item.get("relevance_tags", []),
                evidence_links=item.get("evidence_links", []),
            )
            signals.append(sig)
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping malformed item: %s", exc)
    return signals


def _dispatch_llm_sensor(
    prompt: str,
    source: str,
    sensor: str,
    default_category: str = "quality-issue",
) -> list[dict[str, Any]]:
    """Dispatch Claude session for LLM-based sensor analysis.

    SEC-C02: Sensors use --print only (NO --dangerously-skip-permissions).
    """
    try:
        result = run_agent_prompt(
            prompt,
            purpose=f"sensor-{sensor}",
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.warning("LLM sensor %s timed out", sensor)
        return []
    except FileNotFoundError:
        logger.warning("Agent CLI not found for sensor %s", sensor)
        return []

    if result.returncode != 0:
        logger.warning("LLM sensor %s failed: %s", sensor, result.stderr)
        return []

    return _parse_llm_output(result.stdout, source, sensor, default_category)


def _parse_llm_output(
    stdout: str,
    source: str,
    sensor: str,
    default_category: str = "quality-issue",
) -> list[dict[str, Any]]:
    """Parse LLM JSON output into signal dicts.

    Each item may specify its own ``category``; falls back to
    *default_category* when the item omits one.
    """
    raw = stdout.strip()
    # Try direct parse, then extract JSON array
    for attempt_text in [raw, _extract_json(raw)]:
        if attempt_text is None:
            continue
        try:
            data = json.loads(attempt_text)
            items = data if isinstance(data, list) else data.get("signals", [])
            signals: list[dict[str, Any]] = []
            for item in items:
                item_category = item.get("category", default_category)
                summary = item.get("summary", item.get("event", str(item)))
                raw_content = item.get("raw_content", json.dumps(item))
                try:
                    sig = create_signal(
                        source=source,
                        sensor=sensor,
                        category=item_category,
                        raw_content=str(raw_content)[:5000],
                        summary=str(summary)[:500],
                        reach=int(item.get("reach", item.get("count", 1))),
                        sentiment=float(item.get("sentiment", -0.5)),
                        relevance_tags=item.get("relevance_tags", []),
                        evidence_links=item.get("evidence_links", []),
                    )
                    signals.append(sig)
                except (ValueError, TypeError) as exc:
                    logger.warning("Skipping malformed LLM item: %s", exc)
            return signals
        except (json.JSONDecodeError, TypeError):
            continue

    logger.warning("Could not parse LLM output for %s", sensor)
    return []


def _extract_json(text: str) -> str | None:
    """Extract first JSON array or object from text.

    Looks for '[{' or '{"' patterns to avoid false positives like '[HIGH]'.
    Falls back to simple '['/'{' if structured patterns not found.
    """
    # Prefer structured starts: [{ for arrays, {" for objects
    for start_pat, end_char in [("[{", "]"), ('{"', "}")]:
        start = text.find(start_pat)
        end = text.rfind(end_char)
        if start != -1 and end > start:
            return text[start : end + 1]

    # Fallback to simple delimiters
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, ValueError):
                continue
    return None
