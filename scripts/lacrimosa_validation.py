"""Three-gate signal validation pipeline."""

from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

from lacrimosa_types import (
    ACT_THRESHOLD,
    APPROVAL_REQUIRED_DOMAINS,
    BORDERLINE_RANGE,
    EXTERNAL_CRAWL_CAP,
)

logger = logging.getLogger(__name__)

# Re-export scoring functions for backward compatibility
from lacrimosa_scoring import (  # noqa: E402, F401
    ScoringParseError,
    check_deduplication,
    parse_scoring_response,
    parse_sensor_response,
    score_signal_via_llm,
)


# -- TypedDicts --------------------------------------------------------------


class ValidationResult(TypedDict):
    signal: dict[str, Any]
    gate1_passed: bool
    gate2_passed: bool
    gate2_existing_issue: str | None
    gate3_passed: bool
    scores: dict[str, float] | None
    routing: str


# -- Pure Functions (must match test_lacrimosa_discovery.py) -----------------


def passes_evidence_threshold(
    signal: dict[str, Any],
    thresholds: dict[str, Any],
) -> bool:
    """Gate 1: Check if signal meets minimum evidence requirements."""
    cat = signal["category"]
    if cat == "pain-point":
        return (
            signal.get("reach", 0) >= thresholds.get("min_mentions", 15)
            and len(signal.get("evidence_links", [])) >= thresholds.get("min_sources", 3)
            and signal.get("sentiment", 0) <= thresholds.get("max_sentiment", -0.5)
        )
    if cat == "error-pattern":
        return signal.get("reach", 0) >= thresholds.get("min_occurrences_24h", 5) or signal.get(
            "unique_users", 0
        ) >= thresholds.get("or_min_unique_users", 3)
    if cat == "feature-gap":
        return signal.get("competitor_count", 0) >= thresholds.get(
            "min_competitors",
            2,
        )
    if cat == "churn-signal":
        return signal.get("correlated_indicators", 0) >= thresholds.get(
            "min_correlated_indicators",
            2,
        )
    if cat == "quality-issue":
        return signal.get("call_count", 0) >= thresholds.get("min_calls", 3)
    return False


def calculate_composite_score(scores: dict[str, float]) -> float:
    """Calculate composite score from dimension scores."""
    return sum(scores.values())


def passes_act_threshold(composite: float) -> bool:
    """Returns True if composite meets the act threshold."""
    return composite >= ACT_THRESHOLD


def is_borderline(composite: float) -> bool:
    """Returns True if score falls in borderline range [6.0, 7.0]."""
    return BORDERLINE_RANGE[0] <= composite <= BORDERLINE_RANGE[1]


def determine_issue_routing(composite: float, domain: str) -> str:
    """Determine routing: 'archived', 'backlog', or 'action'."""
    if composite < ACT_THRESHOLD:
        return "archived"
    if is_borderline(composite):
        return "backlog"
    if domain in APPROVAL_REQUIRED_DOMAINS:
        return "backlog"
    return "action"


def can_crawl_externally(
    daily_counters: dict[str, Any],
    today: str,
) -> bool:
    """Check if external crawl cap allows another crawl today."""
    crawls = daily_counters.get(today, {}).get("external_crawls", 0)
    return crawls < EXTERNAL_CRAWL_CAP


# -- Content Sanitization (SEC-C01) -----------------------------------------


def sanitize_content(text: str) -> str:
    """Sanitize external content before LLM prompt inclusion."""
    if not text:
        return text
    # Strip control characters (keep newlines and tabs)
    result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Strip dangerous XML-like tags
    result = re.sub(
        r"</?(?:system|tool|assistant|human|function_calls|antml)[^>]*>",
        "",
        result,
        flags=re.IGNORECASE,
    )
    # Truncate to 2000 chars
    if len(result) > 2000:
        result = result[:2000]
    return result


# -- ValidationPipeline Class -----------------------------------------------


class ValidationPipeline:
    """Three-gate validation pipeline orchestrator."""

    def __init__(self, config: dict[str, Any]) -> None:
        val_config = config.get("discovery", {}).get("validation", {})
        self._thresholds = val_config
        self._config = config
        self._domains = config.get("domains", {})

    def validate_signal(
        self,
        signal: dict[str, Any],
        daily_counters: dict[str, Any],
        today: str,
    ) -> ValidationResult:
        """Run signal through all three gates."""
        result: ValidationResult = {
            "signal": signal,
            "gate1_passed": False,
            "gate2_passed": False,
            "gate2_existing_issue": None,
            "gate3_passed": False,
            "scores": None,
            "routing": "archived",
        }

        # Gate 1: Evidence threshold
        cat = signal.get("category", "")
        thresholds = self._thresholds.get(
            cat.replace("-", "_"),
            self._thresholds.get(cat, {}),
        )
        if not passes_evidence_threshold(signal, thresholds):
            return result
        result["gate1_passed"] = True

        # Gate 2: Deduplication
        is_novel, existing_id = check_deduplication(signal)
        if not is_novel:
            result["gate2_passed"] = False
            result["gate2_existing_issue"] = existing_id
            return result
        result["gate2_passed"] = True

        # Gate 3: AI Scoring
        scoring = score_signal_via_llm(signal, self._config)
        scores = scoring["scores"]
        composite = calculate_composite_score(scores)
        signal["composite_score"] = composite
        signal["validation_status"] = "validated"
        result["signal"] = signal
        result["gate3_passed"] = True
        result["scores"] = scores

        # Routing
        domain = self._infer_domain(signal)
        routing = determine_issue_routing(composite, domain)
        result["routing"] = routing

        return result

    def _infer_domain(self, signal: dict[str, Any]) -> str:
        """Infer domain from signal tags."""
        tags = signal.get("relevance_tags", [])
        for tag in tags:
            lower = tag.lower()
            for domain, keywords in self._config.get("project_routing", {}).items():
                if lower in [k.lower() for k in keywords]:
                    return domain
        from lacrimosa_types import _get_config_module

        return _get_config_module().get("conductor.default_project")
