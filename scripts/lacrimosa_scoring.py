"""LLM scoring and response parsing for validation pipeline."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any

import re as _re

from scripts import lacrimosa_config
from lacrimosa_types import SCORING_DIMENSIONS


def _sanitize_for_prompt(text: str) -> str:
    """Sanitize content for LLM prompt inclusion (local copy to avoid circular import)."""
    if not text:
        return text
    result = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    result = _re.sub(
        r"</?(?:system|tool|assistant|human|function_calls|antml)[^>]*>",
        "",
        result,
        flags=_re.IGNORECASE,
    )
    return result[:2000] if len(result) > 2000 else result


logger = logging.getLogger(__name__)

# -- Constants ---------------------------------------------------------------

MAX_SCORING_RETRIES = 2  # Total attempts = 3
SCORING_TIMEOUT_SECONDS = 120


# -- Exceptions --------------------------------------------------------------


class ScoringParseError(ValueError):
    pass


# -- JSON Extraction ----------------------------------------------------------


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Extract JSON object from raw output (may have preamble/fences)."""
    text = raw.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    text_clean = re.sub(r"```(?:json)?\s*", "", text)
    text_clean = re.sub(r"\s*```", "", text_clean).strip()
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    # Extract first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ScoringParseError(f"Could not parse JSON from output: {text[:200]}")


# -- Scoring Response Parsing ------------------------------------------------


def parse_scoring_response(raw_output: str) -> dict[str, Any]:
    """Parse and validate Claude's scoring output."""
    data = _extract_json_object(raw_output)

    scores = data.get("scores", {})
    reasoning = data.get("reasoning", {})
    recommendation = data.get("recommendation", "")

    # Validate all 4 dimensions present
    for dim in SCORING_DIMENSIONS:
        if dim not in scores:
            raise ScoringParseError(f"Missing dimension: {dim}")

    # Validate recommendation
    if recommendation not in {"act", "backlog", "archive"}:
        raise ScoringParseError(
            f"Invalid recommendation: {recommendation!r}",
        )

    # Clamp and round scores
    for dim in SCORING_DIMENSIONS:
        val = float(scores[dim])
        val = max(0.0, min(2.5, val))  # clamp
        val = round(val * 2) / 2  # round to nearest 0.5
        scores[dim] = val

    return {
        "scores": scores,
        "reasoning": reasoning,
        "recommendation": recommendation,
    }


# -- Sensor Response Parsing ------------------------------------------------


def parse_sensor_response(raw_output: str) -> dict[str, Any]:
    """Parse LLM sensor output (feedback or quality-issue)."""
    data = _extract_json_object(raw_output)
    if "signals" not in data:
        raise ScoringParseError("Missing 'signals' key in sensor output")
    if not isinstance(data["signals"], list):
        raise ScoringParseError("'signals' must be a list")
    return data


# -- LLM Scoring ------------------------------------------------------------


_FALLBACK_RESPONSE: dict[str, Any] = {
    "scores": {d: 1.0 for d in SCORING_DIMENSIONS},
    "reasoning": {d: "Fallback — scoring failed" for d in SCORING_DIMENSIONS},
    "recommendation": "archive",
}


def score_signal_via_llm(
    signal: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Score a signal via dispatched Claude session with retry."""
    prompt = _build_scoring_prompt(signal)

    for attempt in range(MAX_SCORING_RETRIES + 1):
        try:
            raw = _dispatch_scoring_session(prompt, attempt)
            return parse_scoring_response(raw)
        except (ScoringParseError, json.JSONDecodeError) as exc:
            logger.warning(
                "Scoring attempt %d failed: %s",
                attempt + 1,
                exc,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Scoring attempt %d timed out", attempt + 1)

    logger.error("All scoring attempts exhausted, using fallback")
    return dict(_FALLBACK_RESPONSE)


def _dispatch_scoring_session(prompt: str, attempt: int) -> str:
    """Dispatch Claude session for scoring."""
    if attempt > 0:
        prompt += (
            "\n\nYour previous response was not valid JSON. " "Respond with ONLY a JSON object."
        )

    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "-p",
        prompt,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=SCORING_TIMEOUT_SECONDS,
    )
    return result.stdout


def _build_scoring_prompt(signal: dict[str, Any]) -> str:
    """Build the scoring prompt for a signal."""
    raw = _sanitize_for_prompt(str(signal.get("raw_content", ""))[:2000])
    _product = lacrimosa_config.get("product.name")
    return (
        f"You are a signal scoring engine for {_product}. "
        "Score this signal across 4 dimensions (0.0 to 2.5 in 0.5 steps).\n"
        f"Category: {signal.get('category')}\n"
        f"Summary: {signal.get('summary')}\n"
        f"Source: {signal.get('source')} via {signal.get('sensor')}\n"
        f"Reach: {signal.get('reach')}\n"
        f"Sentiment: {signal.get('sentiment')}\n"
        f"Tags: {signal.get('relevance_tags')}\n"
        f"Raw content: {raw}\n\n"
        "Dimensions: mission_alignment, feasibility, impact, urgency.\n"
        'Output ONLY JSON: {"scores": {...}, "reasoning": {...}, '
        '"recommendation": "act"|"backlog"|"archive"}'
    )


# -- Deduplication (Gate 2) --------------------------------------------------


def check_deduplication(
    signal: dict[str, Any],
) -> tuple[bool, str | None]:
    """Search Linear+GH for existing similar issues."""
    summary = signal.get("summary", "")
    tags = signal.get("relevance_tags", [])
    query = f"{summary} {' '.join(tags)}"

    cmd = [
        "claude",
        "--print",
        "-p",
        f"Search Linear and GitHub issues for: {query}. "
        "If a matching open issue exists, return its ID (e.g., ISSUE-XX). "
        "If matching issues are Done/Cancelled, treat as novel. "
        'Output ONLY JSON: {{"is_novel": true/false, "existing_issue": "ISSUE-XX" or null}}',
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = _extract_json_object(result.stdout)
        is_novel = data.get("is_novel", True)
        existing = data.get("existing_issue")
        return (is_novel, existing)
    except Exception as exc:
        logger.warning("Dedup check failed: %s — treating as novel", exc)
        return (True, None)
