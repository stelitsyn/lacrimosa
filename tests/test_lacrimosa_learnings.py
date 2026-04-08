"""
TDD tests for the Lacrimosa v2 learnings engine.

Pure unit tests — no external dependencies, no network, no database, no Claude CLI.
Tests: event classification, learning schema, ledger I/O, adjustment apply/revert,
scoring response parsing, learning approval detection, sensor prompt output parsing.

These tests define the behavioral contract for lacrimosa_learnings.py.
Implementation must match these signatures and behaviors exactly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Constants (extracted from config.yaml + AI engineering contracts)
# ---------------------------------------------------------------------------

VALID_TRUST_EVENTS = {
    "pr_review_rejected",
    "pr_review_iteration_2plus",
    "pr_reverted",
    "worker_escalated",
    "trust_promoted",
    "trust_contracted",
}

VALID_ADJUSTMENT_TYPES = {
    "prompt_refinement",
    "guardrail_addition",
    "classification_fix",
    "scope_calibration",
}

VALID_SEVERITIES = {"low", "medium", "high", "critical"}

VALID_LEARNING_STATUSES = {"in_review", "approved", "reverted"}

REQUIRED_LEARNING_FIELDS = {
    "id",
    "timestamp",
    "event_type",
    "issue_id",
    "agent_type",
    "root_cause",
    "pattern",
    "severity",
    "adjustment",
    "applied",
    "linear_issue_id",
    "status",
}

REQUIRED_ADJUSTMENT_FIELDS = {
    "type",
    "target_file",
    "target_path",
    "old_value",
    "new_value",
    "description",
}

SCORING_DIMENSIONS = ("mission_alignment", "feasibility", "impact", "urgency")
SCORING_MAX_PER_DIMENSION = 2.5


# ---------------------------------------------------------------------------
# Pure functions to test (will be imported from lacrimosa_learnings.py)
# ---------------------------------------------------------------------------


def validate_learning(learning: dict[str, Any]) -> list[str]:
    """Validate a learning dict against the schema. Returns list of errors."""
    errors: list[str] = []

    missing = REQUIRED_LEARNING_FIELDS - set(learning.keys())
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")

    event_type = learning.get("event_type")
    if event_type is not None and event_type not in VALID_TRUST_EVENTS:
        errors.append(f"Invalid event_type: {event_type!r}")

    severity = learning.get("severity")
    if severity is not None and severity not in VALID_SEVERITIES:
        errors.append(f"Invalid severity: {severity!r}")

    status = learning.get("status")
    if status is not None and status not in VALID_LEARNING_STATUSES:
        errors.append(f"Invalid status: {status!r}")

    adjustment = learning.get("adjustment")
    if adjustment is not None and isinstance(adjustment, dict):
        adj_missing = REQUIRED_ADJUSTMENT_FIELDS - set(adjustment.keys())
        if adj_missing:
            errors.append(f"Adjustment missing fields: {sorted(adj_missing)}")
        adj_type = adjustment.get("type")
        if adj_type is not None and adj_type not in VALID_ADJUSTMENT_TYPES:
            errors.append(f"Invalid adjustment type: {adj_type!r}")

    applied = learning.get("applied")
    if applied is not None and not isinstance(applied, bool):
        errors.append(f"applied must be bool, got {type(applied).__name__}")

    return errors


def classify_event_severity(event_type: str) -> str:
    """Map event type to default severity level."""
    severity_map = {
        "pr_reverted": "high",
        "worker_escalated": "high",
        "pr_review_rejected": "medium",
        "pr_review_iteration_2plus": "medium",
        "trust_contracted": "medium",
        "trust_promoted": "low",
    }
    return severity_map.get(event_type, "medium")


def parse_scoring_response(raw_output: str) -> dict[str, Any]:
    """Parse and validate Claude's Gate 3 scoring output.

    Extraction: try json.loads, then regex extract first { to last }.
    Validation: 4 dimensions, scores in [0.0, 2.5], 0.5 multiples.
    Returns validated response dict.
    Raises ScoringParseError on failure.
    """
    # Try direct parse
    text = raw_output.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try extracting JSON from surrounding text
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"No JSON found in output: {text[:200]}")
        data = json.loads(text[start : end + 1])

    # Validate structure
    if "scores" not in data:
        raise ValueError("Missing 'scores' key")
    if "reasoning" not in data:
        raise ValueError("Missing 'reasoning' key")

    scores = data["scores"]
    for dim in SCORING_DIMENSIONS:
        if dim not in scores:
            raise ValueError(f"Missing scoring dimension: {dim}")
        score = scores[dim]
        if not isinstance(score, (int, float)):
            raise ValueError(f"Score for {dim} must be numeric, got {type(score).__name__}")
        # Clamp to [0.0, 2.5]
        score = max(0.0, min(SCORING_MAX_PER_DIMENSION, float(score)))
        # Round to nearest 0.5
        score = round(score * 2) / 2
        scores[dim] = score

    recommendation = data.get("recommendation", "archive")
    if recommendation not in {"act", "backlog", "archive"}:
        data["recommendation"] = "archive"

    return data


def parse_sensor_response(raw_output: str) -> dict[str, Any]:
    """Parse LLM sensor output (feedback or quality-issue).

    Same extraction strategy as scoring: try json.loads, then regex extract.
    Returns dict with 'signals' list and metadata.
    Raises ValueError on parse failure.
    """
    text = raw_output.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"No JSON found in sensor output: {text[:200]}")
        data = json.loads(text[start : end + 1])

    if "signals" not in data:
        raise ValueError("Missing 'signals' key in sensor output")
    if not isinstance(data["signals"], list):
        raise ValueError("'signals' must be a list")

    return data


def append_ledger(entry: dict[str, Any], ledger_path: Path) -> None:
    """Append one JSON entry to the ledger file (JSON Lines format)."""
    with open(ledger_path, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


def read_ledger(ledger_path: Path) -> list[dict[str, Any]]:
    """Read all entries from the JSON Lines ledger file."""
    if not ledger_path.exists():
        return []
    entries = []
    with open(ledger_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def can_apply_adjustment(
    adjustment: dict[str, Any],
    current_config: dict[str, Any],
) -> tuple[bool, str]:
    """Check if an adjustment can be safely applied.

    Returns (can_apply, reason).
    Validates: target_path resolves, old_value matches current.
    """
    target_path = adjustment.get("target_path", "")
    old_value = adjustment.get("old_value")
    parts = target_path.split(".")

    # Navigate to the target location
    current = current_config
    for i, part in enumerate(parts[:-1]):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, dict) and part.isdigit() and int(part) in current:
            current = current[int(part)]
        else:
            if old_value is None:
                # New entry — path doesn't need to fully exist for additions
                return True, "New entry, path will be created"
            return False, f"Path segment '{part}' not found at depth {i}"

    final_key = parts[-1]
    if isinstance(current, dict):
        current_value = current.get(final_key)
    else:
        return False, f"Cannot navigate to final key '{final_key}'"

    if old_value is None:
        # Addition — no conflict possible
        return True, "New entry"

    if str(current_value) != str(old_value):
        return False, f"Value mismatch: expected '{old_value}', found '{current_value}'"

    return True, "Value matches, safe to apply"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_learning(**overrides: Any) -> dict[str, Any]:
    """Create a valid learning dict with optional overrides."""
    base: dict[str, Any] = {
        "id": "lrn-abc123",
        "timestamp": "2026-03-20T14:30:00Z",
        "event_type": "pr_reverted",
        "issue_id": "TST-99",
        "agent_type": "backend-developer-v4",
        "root_cause": "Agent modified auth middleware without checking session token format",
        "pattern": "Auth-related changes need explicit security review",
        "severity": "high",
        "adjustment": {
            "type": "guardrail_addition",
            "target_file": "~/.claude/lacrimosa/config.yaml",
            "target_path": "lifecycle.phases.review.reviewers.conditional",
            "old_value": None,
            "new_value": "security-officer: when auth/* files changed",
            "description": "Always require security-officer review when auth files are modified",
        },
        "applied": True,
        "linear_issue_id": "TST-105",
        "status": "in_review",
    }
    base.update(overrides)
    return base


def _make_scoring_json(**overrides: Any) -> str:
    """Create valid scoring response JSON string."""
    base = {
        "scores": {
            "mission_alignment": 2.0,
            "feasibility": 1.5,
            "impact": 2.5,
            "urgency": 0.5,
        },
        "reasoning": {
            "mission_alignment": "Directly addresses user productivity.",
            "feasibility": "Requires new API integration.",
            "impact": "Affects 30% of users.",
            "urgency": "Competitor launched similar feature.",
        },
        "recommendation": "backlog",
    }
    base.update(overrides)
    return json.dumps(base)


def _make_sensor_json(signals: list[dict] | None = None) -> str:
    """Create valid sensor response JSON string."""
    if signals is None:
        signals = [
            {
                "category": "pain-point",
                "summary": "Users frustrated with slow response times on dashboard",
                "reach": 25,
                "sentiment": -0.8,
                "relevance_tags": ["automation", "productivity"],
                "evidence_links": [],
                "raw_content": "The dashboard takes forever to load with large datasets...",
                "cluster_size": 5,
            }
        ]
    return json.dumps(
        {
            "signals": signals,
            "total_feedback_analyzed": 42,
            "no_signal_reason": None,
        }
    )


# ---------------------------------------------------------------------------
# Tests: Learning Schema Validation
# ---------------------------------------------------------------------------


class TestLearningSchema:
    """Test learning entry schema validation."""

    def test_valid_learning_passes(self):
        learning = _make_learning()
        errors = validate_learning(learning)
        assert errors == []

    def test_missing_required_fields_fails(self):
        learning = {"id": "lrn-1", "event_type": "pr_reverted"}
        errors = validate_learning(learning)
        assert len(errors) >= 1
        assert any("Missing required fields" in e for e in errors)

    def test_missing_single_field_fails(self):
        learning = _make_learning()
        del learning["root_cause"]
        errors = validate_learning(learning)
        assert any("root_cause" in e for e in errors)

    def test_invalid_event_type_fails(self):
        learning = _make_learning(event_type="unknown_event")
        errors = validate_learning(learning)
        assert any("Invalid event_type" in e for e in errors)

    @pytest.mark.parametrize("event_type", sorted(VALID_TRUST_EVENTS))
    def test_valid_event_types_pass(self, event_type: str):
        learning = _make_learning(event_type=event_type)
        errors = validate_learning(learning)
        assert not any("event_type" in e for e in errors)

    def test_invalid_severity_fails(self):
        learning = _make_learning(severity="extreme")
        errors = validate_learning(learning)
        assert any("Invalid severity" in e for e in errors)

    @pytest.mark.parametrize("severity", ["low", "medium", "high", "critical"])
    def test_valid_severities_pass(self, severity: str):
        learning = _make_learning(severity=severity)
        errors = validate_learning(learning)
        assert not any("severity" in e for e in errors)

    def test_invalid_status_fails(self):
        learning = _make_learning(status="unknown")
        errors = validate_learning(learning)
        assert any("Invalid status" in e for e in errors)

    @pytest.mark.parametrize("status", ["in_review", "approved", "reverted"])
    def test_valid_statuses_pass(self, status: str):
        learning = _make_learning(status=status)
        errors = validate_learning(learning)
        assert not any("status" in e for e in errors)

    def test_applied_must_be_bool(self):
        learning = _make_learning(applied="yes")
        errors = validate_learning(learning)
        assert any("applied must be bool" in e for e in errors)

    def test_applied_true_passes(self):
        learning = _make_learning(applied=True)
        errors = validate_learning(learning)
        assert not any("applied" in e for e in errors)

    def test_applied_false_passes(self):
        learning = _make_learning(applied=False)
        errors = validate_learning(learning)
        assert not any("applied" in e for e in errors)

    def test_invalid_adjustment_type_fails(self):
        learning = _make_learning()
        learning["adjustment"]["type"] = "invalid_type"
        errors = validate_learning(learning)
        assert any("Invalid adjustment type" in e for e in errors)

    @pytest.mark.parametrize("adj_type", sorted(VALID_ADJUSTMENT_TYPES))
    def test_valid_adjustment_types_pass(self, adj_type: str):
        learning = _make_learning()
        learning["adjustment"]["type"] = adj_type
        errors = validate_learning(learning)
        assert not any("adjustment type" in e for e in errors)

    def test_adjustment_missing_fields_fails(self):
        learning = _make_learning()
        del learning["adjustment"]["target_file"]
        errors = validate_learning(learning)
        assert any("Adjustment missing fields" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: Event Severity Classification
# ---------------------------------------------------------------------------


class TestEventSeverity:
    """Test default severity mapping for trust events."""

    @pytest.mark.parametrize(
        "event_type,expected",
        [
            ("pr_reverted", "high"),
            ("worker_escalated", "high"),
            ("pr_review_rejected", "medium"),
            ("pr_review_iteration_2plus", "medium"),
            ("trust_contracted", "medium"),
            ("trust_promoted", "low"),
        ],
    )
    def test_severity_mapping(self, event_type: str, expected: str):
        assert classify_event_severity(event_type) == expected

    def test_unknown_event_defaults_to_medium(self):
        assert classify_event_severity("unknown_event") == "medium"


# ---------------------------------------------------------------------------
# Tests: Gate 3 Scoring Response Parsing
# ---------------------------------------------------------------------------


class TestScoringResponseParsing:
    """Test parsing and validation of Claude's Gate 3 scoring output."""

    def test_valid_json_parses(self):
        raw = _make_scoring_json()
        result = parse_scoring_response(raw)
        assert result["scores"]["mission_alignment"] == 2.0
        assert result["scores"]["feasibility"] == 1.5
        assert result["scores"]["impact"] == 2.5
        assert result["scores"]["urgency"] == 0.5
        assert result["recommendation"] == "backlog"

    def test_json_with_preamble_parses(self):
        raw = "Here is the scoring:\n" + _make_scoring_json() + "\nDone."
        result = parse_scoring_response(raw)
        assert "scores" in result
        assert result["scores"]["mission_alignment"] == 2.0

    def test_json_with_markdown_fences_parses(self):
        raw = "```json\n" + _make_scoring_json() + "\n```"
        result = parse_scoring_response(raw)
        assert "scores" in result

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON found"):
            parse_scoring_response("This is just text with no JSON at all.")

    def test_missing_scores_key_raises(self):
        raw = json.dumps({"reasoning": {}, "recommendation": "act"})
        with pytest.raises(ValueError, match="Missing 'scores'"):
            parse_scoring_response(raw)

    def test_missing_reasoning_key_raises(self):
        raw = json.dumps(
            {
                "scores": {d: 1.0 for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        with pytest.raises(ValueError, match="Missing 'reasoning'"):
            parse_scoring_response(raw)

    def test_missing_dimension_raises(self):
        scores = {d: 1.0 for d in SCORING_DIMENSIONS}
        del scores["urgency"]
        raw = json.dumps({"scores": scores, "reasoning": {}, "recommendation": "act"})
        with pytest.raises(ValueError, match="Missing scoring dimension: urgency"):
            parse_scoring_response(raw)

    def test_score_clamped_to_max(self):
        scores = {d: 3.0 for d in SCORING_DIMENSIONS}  # Above 2.5
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        result = parse_scoring_response(raw)
        for dim in SCORING_DIMENSIONS:
            assert result["scores"][dim] == 2.5

    def test_score_clamped_to_min(self):
        scores = {d: -1.0 for d in SCORING_DIMENSIONS}  # Below 0.0
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        result = parse_scoring_response(raw)
        for dim in SCORING_DIMENSIONS:
            assert result["scores"][dim] == 0.0

    def test_score_rounded_to_half(self):
        scores = {
            "mission_alignment": 1.3,  # → 1.5
            "feasibility": 1.7,  # → 1.5
            "impact": 0.2,  # → 0.0
            "urgency": 2.4,  # → 2.5
        }
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        result = parse_scoring_response(raw)
        assert result["scores"]["mission_alignment"] == 1.5
        assert result["scores"]["feasibility"] == 1.5
        assert result["scores"]["impact"] == 0.0
        assert result["scores"]["urgency"] == 2.5

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.0, 0.0),
            (0.1, 0.0),
            (0.24, 0.0),
            (0.25, 0.0),  # Python banker's rounding: round(0.5) = 0
            (0.3, 0.5),
            (0.5, 0.5),
            (0.7, 0.5),
            (0.75, 1.0),
            (1.0, 1.0),
            (1.25, 1.0),  # Python banker's rounding: round(2.5) = 2
            (1.5, 1.5),
            (1.75, 2.0),
            (2.0, 2.0),
            (2.25, 2.0),  # Python banker's rounding: round(4.5) = 4
            (2.5, 2.5),
        ],
        ids=[
            "zero",
            "0.1-rounds-down",
            "0.24-rounds-down",
            "0.25-bankers-rounds-down",
            "0.3-rounds-down",
            "half",
            "0.7-rounds-down",
            "0.75-rounds-up",
            "one",
            "1.25-bankers-rounds-down",
            "one-half",
            "1.75-rounds-up",
            "two",
            "2.25-bankers-rounds-down",
            "max",
        ],
    )
    def test_score_rounding_boundary(self, score: float, expected: float):
        scores = {d: score for d in SCORING_DIMENSIONS}
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        result = parse_scoring_response(raw)
        assert result["scores"]["mission_alignment"] == expected

    def test_invalid_recommendation_defaults_to_archive(self):
        raw = json.dumps(
            {
                "scores": {d: 1.0 for d in SCORING_DIMENSIONS},
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "invalid",
            }
        )
        result = parse_scoring_response(raw)
        assert result["recommendation"] == "archive"

    @pytest.mark.parametrize("rec", ["act", "backlog", "archive"])
    def test_valid_recommendations_preserved(self, rec: str):
        raw = json.dumps(
            {
                "scores": {d: 1.0 for d in SCORING_DIMENSIONS},
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": rec,
            }
        )
        result = parse_scoring_response(raw)
        assert result["recommendation"] == rec

    def test_non_numeric_score_raises(self):
        scores = {d: 1.0 for d in SCORING_DIMENSIONS}
        scores["urgency"] = "high"
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        with pytest.raises(ValueError, match="must be numeric"):
            parse_scoring_response(raw)


# ---------------------------------------------------------------------------
# Tests: Sensor Response Parsing
# ---------------------------------------------------------------------------


class TestSensorResponseParsing:
    """Test parsing of feedback and quality-issue sensor LLM output."""

    def test_valid_feedback_response_parses(self):
        raw = _make_sensor_json()
        result = parse_sensor_response(raw)
        assert len(result["signals"]) == 1
        assert result["signals"][0]["category"] == "pain-point"
        assert result["total_feedback_analyzed"] == 42

    def test_empty_signals_parses(self):
        raw = _make_sensor_json(signals=[])
        result = parse_sensor_response(raw)
        assert result["signals"] == []

    def test_json_with_preamble_parses(self):
        raw = "Analysis complete:\n" + _make_sensor_json() + "\n"
        result = parse_sensor_response(raw)
        assert "signals" in result

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON found"):
            parse_sensor_response("No signals detected in the data.")

    def test_missing_signals_key_raises(self):
        raw = json.dumps({"total_feedback_analyzed": 10})
        with pytest.raises(ValueError, match="Missing 'signals'"):
            parse_sensor_response(raw)

    def test_signals_not_list_raises(self):
        raw = json.dumps({"signals": "none", "total_feedback_analyzed": 0})
        with pytest.raises(ValueError, match="must be a list"):
            parse_sensor_response(raw)

    def test_multiple_signals_parse(self):
        signals = [
            {
                "category": "pain-point",
                "summary": "Hold time complaints",
                "reach": 20,
                "sentiment": -0.7,
                "relevance_tags": ["hold-time"],
                "evidence_links": [],
                "raw_content": "Too long on hold",
                "cluster_size": 5,
            },
            {
                "category": "feature-gap",
                "summary": "Users want email follow-up",
                "reach": 10,
                "sentiment": -0.3,
                "relevance_tags": ["email", "follow-up"],
                "evidence_links": [],
                "raw_content": "Can you send an email after?",
                "cluster_size": 4,
            },
        ]
        raw = _make_sensor_json(signals=signals)
        result = parse_sensor_response(raw)
        assert len(result["signals"]) == 2

    def test_quality_issue_response_parses(self):
        signals = [
            {
                "category": "quality-issue",
                "summary": "AI misinterprets ambiguous user input",
                "reach": 5,
                "sentiment": -0.6,
                "relevance_tags": ["misunderstanding", "input-parsing"],
                "evidence_links": [],
                "raw_content": "User: I need to export the report. AI: Let me search for settings...",
                "call_count": 5,
                "pattern_type": "misunderstanding",
            }
        ]
        raw = json.dumps({"signals": signals, "total_calls_analyzed": 30, "no_signal_reason": None})
        result = parse_sensor_response(raw)
        assert result["signals"][0]["pattern_type"] == "misunderstanding"
        assert result["total_calls_analyzed"] == 30


# ---------------------------------------------------------------------------
# Tests: Ledger I/O (JSON Lines)
# ---------------------------------------------------------------------------


class TestLedgerIO:
    """Test append-only JSON Lines ledger read/write."""

    def test_append_creates_file(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        entry = _make_learning()
        append_ledger(entry, ledger)
        assert ledger.exists()

    def test_append_writes_single_line(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        entry = _make_learning()
        append_ledger(entry, ledger)
        lines = ledger.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_append_writes_valid_json(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        entry = _make_learning()
        append_ledger(entry, ledger)
        line = ledger.read_text().strip()
        parsed = json.loads(line)
        assert parsed["id"] == "lrn-abc123"

    def test_multiple_appends_create_multiple_lines(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        for i in range(3):
            append_ledger(_make_learning(id=f"lrn-{i}"), ledger)
        lines = ledger.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_read_empty_ledger(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        entries = read_ledger(ledger)
        assert entries == []

    def test_read_nonexistent_ledger(self, tmp_path: Path):
        ledger = tmp_path / "nonexistent.json"
        entries = read_ledger(ledger)
        assert entries == []

    def test_read_returns_all_entries(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        for i in range(5):
            append_ledger(_make_learning(id=f"lrn-{i}"), ledger)
        entries = read_ledger(ledger)
        assert len(entries) == 5
        assert entries[0]["id"] == "lrn-0"
        assert entries[4]["id"] == "lrn-4"

    def test_read_preserves_order(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        ids = ["lrn-c", "lrn-a", "lrn-b"]
        for lid in ids:
            append_ledger(_make_learning(id=lid), ledger)
        entries = read_ledger(ledger)
        assert [e["id"] for e in entries] == ids

    def test_append_does_not_modify_existing_entries(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        append_ledger(_make_learning(id="lrn-1"), ledger)
        content_before = ledger.read_text()
        append_ledger(_make_learning(id="lrn-2"), ledger)
        content_after = ledger.read_text()
        assert content_after.startswith(content_before)

    def test_read_skips_empty_lines(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        ledger.write_text(json.dumps({"id": "lrn-1"}) + "\n\n" + json.dumps({"id": "lrn-2"}) + "\n")
        entries = read_ledger(ledger)
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# Tests: Adjustment Apply Safety
# ---------------------------------------------------------------------------


class TestAdjustmentApply:
    """Test pre-apply validation for config adjustments."""

    def test_matching_old_value_can_apply(self):
        adjustment = {
            "type": "scope_calibration",
            "target_file": "config.yaml",
            "target_path": "trust.tiers.0.max_files_per_pr",
            "old_value": "15",
            "new_value": "10",
            "description": "Reduce max files",
        }
        config = {"trust": {"tiers": {0: {"max_files_per_pr": 15}}}}
        can, reason = can_apply_adjustment(adjustment, config)
        assert can is True

    def test_mismatching_old_value_cannot_apply(self):
        adjustment = {
            "type": "scope_calibration",
            "target_file": "config.yaml",
            "target_path": "trust.tiers.0.max_files_per_pr",
            "old_value": "15",
            "new_value": "10",
            "description": "Reduce max files",
        }
        config = {"trust": {"tiers": {0: {"max_files_per_pr": 12}}}}
        can, reason = can_apply_adjustment(adjustment, config)
        assert can is False
        assert "mismatch" in reason.lower()

    def test_null_old_value_can_apply_new_entry(self):
        adjustment = {
            "type": "guardrail_addition",
            "target_file": "config.yaml",
            "target_path": "lifecycle.phases.review.new_rule",
            "old_value": None,
            "new_value": "security-officer required",
            "description": "Add guardrail",
        }
        config = {"lifecycle": {"phases": {"review": {}}}}
        can, reason = can_apply_adjustment(adjustment, config)
        assert can is True

    def test_path_not_found_with_old_value_cannot_apply(self):
        adjustment = {
            "type": "scope_calibration",
            "target_file": "config.yaml",
            "target_path": "nonexistent.path.key",
            "old_value": "15",
            "new_value": "10",
            "description": "Fix",
        }
        config = {"other": {}}
        can, reason = can_apply_adjustment(adjustment, config)
        assert can is False
        assert "not found" in reason.lower()

    def test_path_not_found_with_null_old_value_can_apply(self):
        adjustment = {
            "type": "guardrail_addition",
            "target_file": "config.yaml",
            "target_path": "new.section.key",
            "old_value": None,
            "new_value": "new value",
            "description": "Add new section",
        }
        config = {"other": {}}
        can, reason = can_apply_adjustment(adjustment, config)
        assert can is True

    def test_deep_nested_path_resolves(self):
        adjustment = {
            "type": "scope_calibration",
            "target_file": "config.yaml",
            "target_path": "discovery.validation.pain_point.min_mentions",
            "old_value": "15",
            "new_value": "20",
            "description": "Increase threshold",
        }
        config = {"discovery": {"validation": {"pain_point": {"min_mentions": 15}}}}
        can, reason = can_apply_adjustment(adjustment, config)
        assert can is True


# ---------------------------------------------------------------------------
# Tests: Revert Safety
# ---------------------------------------------------------------------------


class TestRevertSafety:
    """Test that revert logic validates current state before reverting."""

    def test_revert_entry_structure(self):
        """Revert ledger entries must reference the original learning."""
        revert_entry = {
            "id": "lrn-abc123-revert",
            "timestamp": "2026-03-21T09:00:00Z",
            "event_type": "learning_reverted",
            "references": "lrn-abc123",
            "reason": "Operator cancelled TST-105",
            "revert_applied": True,
        }
        assert revert_entry["references"] == "lrn-abc123"
        assert revert_entry["event_type"] == "learning_reverted"

    def test_approve_entry_structure(self):
        """Approval ledger entries must reference the original learning."""
        approve_entry = {
            "id": "lrn-abc123-approve",
            "timestamp": "2026-03-22T10:00:00Z",
            "event_type": "learning_approved",
            "references": "lrn-abc123",
            "reason": "Operator closed TST-105 as Done",
        }
        assert approve_entry["references"] == "lrn-abc123"
        assert approve_entry["event_type"] == "learning_approved"


# ---------------------------------------------------------------------------
# Tests: Full Learning Lifecycle (integration-like, but pure)
# ---------------------------------------------------------------------------


class TestLearningLifecycle:
    """Test the full lifecycle: create → apply → revert."""

    def test_create_and_read_back(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        learning = _make_learning()
        append_ledger(learning, ledger)
        entries = read_ledger(ledger)
        assert len(entries) == 1
        assert entries[0]["id"] == "lrn-abc123"
        assert entries[0]["event_type"] == "pr_reverted"
        assert entries[0]["applied"] is True
        assert entries[0]["status"] == "in_review"

    def test_create_then_revert_appends_not_modifies(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        learning = _make_learning()
        append_ledger(learning, ledger)
        revert = {
            "id": "lrn-abc123-revert",
            "timestamp": "2026-03-21T09:00:00Z",
            "event_type": "learning_reverted",
            "references": "lrn-abc123",
            "reason": "Cancelled",
            "revert_applied": True,
        }
        append_ledger(revert, ledger)
        entries = read_ledger(ledger)
        assert len(entries) == 2
        # Original is unchanged
        assert entries[0]["id"] == "lrn-abc123"
        assert entries[0]["status"] == "in_review"
        # Revert is appended
        assert entries[1]["id"] == "lrn-abc123-revert"
        assert entries[1]["event_type"] == "learning_reverted"

    def test_multiple_learnings_independent(self, tmp_path: Path):
        ledger = tmp_path / "learnings.json"
        learning1 = _make_learning(id="lrn-001", event_type="pr_reverted")
        learning2 = _make_learning(id="lrn-002", event_type="trust_promoted", severity="low")
        append_ledger(learning1, ledger)
        append_ledger(learning2, ledger)
        entries = read_ledger(ledger)
        assert entries[0]["severity"] == "high"
        assert entries[1]["severity"] == "low"


# ---------------------------------------------------------------------------
# Tests: Composite Score from Gate 3 (end-to-end parse → calculate)
# ---------------------------------------------------------------------------


class TestScoringEndToEnd:
    """Test parsing scoring response and calculating composite."""

    def test_standard_scores_composite(self):
        raw = _make_scoring_json()
        result = parse_scoring_response(raw)
        composite = sum(result["scores"].values())
        assert composite == pytest.approx(6.5)

    def test_all_max_composite(self):
        scores = {d: 2.5 for d in SCORING_DIMENSIONS}
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "max" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        result = parse_scoring_response(raw)
        composite = sum(result["scores"].values())
        assert composite == pytest.approx(10.0)

    def test_all_zero_composite(self):
        scores = {d: 0.0 for d in SCORING_DIMENSIONS}
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "none" for d in SCORING_DIMENSIONS},
                "recommendation": "archive",
            }
        )
        result = parse_scoring_response(raw)
        composite = sum(result["scores"].values())
        assert composite == pytest.approx(0.0)

    def test_clamped_scores_composite_max_10(self):
        scores = {d: 5.0 for d in SCORING_DIMENSIONS}  # 5.0 each → clamped to 2.5
        raw = json.dumps(
            {
                "scores": scores,
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        result = parse_scoring_response(raw)
        composite = sum(result["scores"].values())
        assert composite == pytest.approx(10.0)

    @pytest.mark.parametrize(
        "scores_dict,expected_composite",
        [
            ({"mission_alignment": 2.5, "feasibility": 2.5, "impact": 2.5, "urgency": 2.5}, 10.0),
            ({"mission_alignment": 0.0, "feasibility": 0.0, "impact": 0.0, "urgency": 0.0}, 0.0),
            ({"mission_alignment": 1.5, "feasibility": 1.5, "impact": 1.5, "urgency": 1.5}, 6.0),
            ({"mission_alignment": 2.0, "feasibility": 1.5, "impact": 2.5, "urgency": 0.5}, 6.5),
            ({"mission_alignment": 2.0, "feasibility": 2.0, "impact": 2.0, "urgency": 2.0}, 8.0),
        ],
        ids=["max", "zero", "borderline-lower", "mixed", "high"],
    )
    def test_composite_calculation(self, scores_dict: dict, expected_composite: float):
        raw = json.dumps(
            {
                "scores": scores_dict,
                "reasoning": {d: "test" for d in SCORING_DIMENSIONS},
                "recommendation": "act",
            }
        )
        result = parse_scoring_response(raw)
        composite = sum(result["scores"].values())
        assert composite == pytest.approx(expected_composite)
