"""
Unit tests for the Lacrimosa v2 discovery loop.

Pure unit tests — no external dependencies, no network, no database.
Tests: signal schema validation, evidence threshold gate, AI scoring composite,
state migration v2->v3, crawl daily cap, borderline routing.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Config constants (extracted from config.yaml)
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "pain-point",
    "feature-gap",
    "error-pattern",
    "churn-signal",
    "competitor-move",
    "quality-issue",
}

VALID_VALIDATION_STATUSES = {"pending", "validated", "archived", "acted"}

VALID_SOURCES = {
    "reddit",
    "ga4",
    "cloud-logging",
    "feedback",
    "competitor",
    "stripe",
    "usage",
}

VALID_SENSORS = {
    "social-listener",
    "funnel-analyzer",
    "competitor-monitor",
    "error-pattern-detector",
    "feedback-analyzer",
    "payment-anomaly-detector",
    "usage-pattern-analyzer",
}

EVIDENCE_THRESHOLDS = {
    "pain-point": {
        "min_mentions": 15,
        "min_sources": 3,
        "within_days": 7,
        "max_sentiment": -0.5,
    },
    "error-pattern": {
        "min_occurrences_24h": 5,
        "or_min_unique_users": 3,
    },
    "feature-gap": {
        "min_competitors": 2,
    },
    "churn-signal": {
        "min_correlated_indicators": 2,
    },
    "quality-issue": {
        "min_occurrences": 3,
        "within_hours": 48,
    },
}

SCORING_MAX_PER_DIMENSION = 2.5
SCORING_DIMENSIONS = ("mission_alignment", "feasibility", "impact", "urgency")
ACT_THRESHOLD = 6.0
BORDERLINE_RANGE = (6.0, 7.0)

EXTERNAL_CRAWL_CAP = 50

AUTONOMOUS_DOMAINS = {"Marketing", "Platform", "Internationalization"}
APPROVAL_REQUIRED_DOMAINS = {"Billing", "Mobile", "Infrastructure"}

REQUIRED_SIGNAL_FIELDS = {
    "id",
    "source",
    "sensor",
    "timestamp",
    "category",
    "raw_content",
    "summary",
    "reach",
    "sentiment",
    "relevance_tags",
    "evidence_links",
    "validation_status",
    "composite_score",
}


# ---------------------------------------------------------------------------
# Pure functions extracted from SKILL.md pseudocode
# ---------------------------------------------------------------------------


def validate_signal(signal: dict[str, Any]) -> list[str]:
    """Validate a signal dict against the schema. Returns list of error strings."""
    errors: list[str] = []

    # Required fields
    missing = REQUIRED_SIGNAL_FIELDS - set(signal.keys())
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")

    # Category
    cat = signal.get("category")
    if cat is not None and cat not in VALID_CATEGORIES:
        errors.append(f"Invalid category: {cat!r}. Must be one of {sorted(VALID_CATEGORIES)}")

    # Sentiment range
    sentiment = signal.get("sentiment")
    if sentiment is not None and not (-1.0 <= sentiment <= 1.0):
        errors.append(f"Sentiment {sentiment} out of range [-1, 1]")

    # Validation status
    vs = signal.get("validation_status")
    if vs is not None and vs not in VALID_VALIDATION_STATUSES:
        errors.append(
            f"Invalid validation_status: {vs!r}. Must be one of {sorted(VALID_VALIDATION_STATUSES)}"
        )

    # composite_score must be None or float/int
    cs = signal.get("composite_score")
    if cs is not None and not isinstance(cs, (int, float)):
        errors.append(f"composite_score must be None or numeric, got {type(cs).__name__}")

    return errors


def passes_evidence_threshold(signal: dict[str, Any], thresholds: dict[str, Any]) -> bool:
    """Gate 1: Check if signal meets minimum evidence requirements."""
    cat = signal["category"]
    if cat == "pain-point":
        return (
            signal.get("reach", 0) >= thresholds.get("min_mentions", 15)
            and len(signal.get("evidence_links", [])) >= thresholds.get("min_sources", 3)
            and signal.get("sentiment", 0) <= thresholds.get("max_sentiment", -0.5)
        )
    elif cat == "error-pattern":
        return signal.get("reach", 0) >= thresholds.get("min_occurrences_24h", 5) or signal.get(
            "unique_users", 0
        ) >= thresholds.get("or_min_unique_users", 3)
    elif cat == "feature-gap":
        return signal.get("competitor_count", 0) >= thresholds.get("min_competitors", 2)
    elif cat == "churn-signal":
        return signal.get("correlated_indicators", 0) >= thresholds.get(
            "min_correlated_indicators", 2
        )
    elif cat == "quality-issue":
        return signal.get("call_count", 0) >= thresholds.get("min_calls", 3)
    return False


def calculate_composite_score(scores: dict[str, float]) -> float:
    """Calculate the composite score from individual dimension scores."""
    return sum(scores.values())


def passes_act_threshold(composite: float) -> bool:
    """Returns True if the composite score meets the act threshold."""
    return composite >= ACT_THRESHOLD


def is_borderline(composite: float) -> bool:
    """Returns True if the score falls in the borderline range [6.0, 7.0]."""
    return BORDERLINE_RANGE[0] <= composite <= BORDERLINE_RANGE[1]


def determine_issue_routing(
    composite: float,
    domain: str,
) -> str:
    """
    Determine how a validated signal should be routed.

    Returns:
        "archived"  — below act threshold
        "backlog"   — borderline score OR approval_required domain
        "action"    — full autonomous action
    """
    if composite < ACT_THRESHOLD:
        return "archived"
    if is_borderline(composite):
        return "backlog"
    if domain in APPROVAL_REQUIRED_DOMAINS:
        return "backlog"
    return "action"


def migrate_state(state: dict[str, Any]) -> dict[str, Any]:
    """Migrate state from v1/v2 to v3. Idempotent — v3 state is returned unchanged."""
    state = copy.deepcopy(state)
    if state.get("version", 1) < 3:
        state["version"] = 3
        state.setdefault("session_mode", "interactive")
        state.setdefault(
            "discovery",
            {
                "last_internal_sense": None,
                "last_external_sense": None,
                "last_strategy_analysis": None,
                "last_deep_research": None,
                "signals_pending_validation": 0,
                "signals_validated_today": 0,
                "signals_archived_today": 0,
                "active_research_sprints": 0,
                "signal_queue": [],
            },
        )
        today = datetime.now().strftime("%Y-%m-%d")
        today_counters = state.setdefault("daily_counters", {}).setdefault(today, {})
        today_counters.setdefault("signals_processed", 0)
        today_counters.setdefault("signals_validated", 0)
        today_counters.setdefault("issues_discovered", 0)
    return state


def can_crawl_externally(daily_counters: dict[str, Any], today: str) -> bool:
    """Check if the external crawl cap allows another crawl today."""
    crawls = daily_counters.get(today, {}).get("external_crawls", 0)
    return crawls < EXTERNAL_CRAWL_CAP


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_signal(**overrides: Any) -> dict[str, Any]:
    """Create a valid signal dict with optional overrides."""
    base = {
        "id": "sig-abc123",
        "source": "reddit",
        "sensor": "social-listener",
        "timestamp": "2026-03-13T10:00:00+00:00",
        "category": "pain-point",
        "raw_content": "This manual process takes hours every week...",
        "summary": "Users frustrated with repetitive manual workflows",
        "reach": 150,
        "sentiment": -0.7,
        "relevance_tags": ["automation", "productivity"],
        "evidence_links": [
            "https://reddit.com/r/productivity/abc",
            "https://reddit.com/r/saas/def",
            "https://reddit.com/r/startups/ghi",
        ],
        "validation_status": "pending",
        "composite_score": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSignalSchema:
    """Test signal schema validation."""

    def test_valid_signal_passes(self):
        signal = _make_signal()
        errors = validate_signal(signal)
        assert errors == []

    def test_missing_required_fields_fails(self):
        signal = {"id": "sig-1", "source": "reddit"}
        errors = validate_signal(signal)
        assert len(errors) >= 1
        assert any("Missing required fields" in e for e in errors)

    def test_missing_single_field_fails(self):
        signal = _make_signal()
        del signal["timestamp"]
        errors = validate_signal(signal)
        assert any("timestamp" in e for e in errors)

    def test_invalid_category_fails(self):
        signal = _make_signal(category="not-a-category")
        errors = validate_signal(signal)
        assert any("Invalid category" in e for e in errors)

    @pytest.mark.parametrize("sentiment", [-1.5, 1.1, 999, -2.0])
    def test_sentiment_out_of_range_fails(self, sentiment: float):
        signal = _make_signal(sentiment=sentiment)
        errors = validate_signal(signal)
        assert any("Sentiment" in e and "out of range" in e for e in errors)

    @pytest.mark.parametrize("sentiment", [-1.0, -0.5, 0.0, 0.5, 1.0])
    def test_sentiment_in_range_passes(self, sentiment: float):
        signal = _make_signal(sentiment=sentiment)
        errors = validate_signal(signal)
        assert not any("Sentiment" in e for e in errors)

    def test_invalid_validation_status_fails(self):
        signal = _make_signal(validation_status="unknown")
        errors = validate_signal(signal)
        assert any("Invalid validation_status" in e for e in errors)

    @pytest.mark.parametrize("status", ["pending", "validated", "archived", "acted"])
    def test_valid_validation_status_passes(self, status: str):
        signal = _make_signal(validation_status=status)
        errors = validate_signal(signal)
        assert not any("validation_status" in e for e in errors)

    def test_composite_score_none_passes(self):
        signal = _make_signal(composite_score=None)
        errors = validate_signal(signal)
        assert not any("composite_score" in e for e in errors)

    def test_composite_score_float_passes(self):
        signal = _make_signal(composite_score=7.5)
        errors = validate_signal(signal)
        assert not any("composite_score" in e for e in errors)

    def test_composite_score_int_passes(self):
        signal = _make_signal(composite_score=8)
        errors = validate_signal(signal)
        assert not any("composite_score" in e for e in errors)

    def test_composite_score_string_fails(self):
        signal = _make_signal(composite_score="high")
        errors = validate_signal(signal)
        assert any("composite_score" in e for e in errors)


class TestEvidenceGate:
    """Test Gate 1: Evidence threshold logic."""

    # ── pain-point ──

    def test_pain_point_passes(self):
        signal = _make_signal(reach=15, sentiment=-0.7)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["pain-point"]) is True

    def test_pain_point_fails_low_reach(self):
        signal = _make_signal(reach=14, sentiment=-0.7)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["pain-point"]) is False

    def test_pain_point_fails_few_sources(self):
        signal = _make_signal(
            reach=20,
            sentiment=-0.7,
            evidence_links=["https://a.com", "https://b.com"],  # only 2
        )
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["pain-point"]) is False

    def test_pain_point_fails_sentiment_not_negative_enough(self):
        signal = _make_signal(reach=20, sentiment=-0.3)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["pain-point"]) is False

    @pytest.mark.parametrize(
        "reach,sources,sentiment,expected",
        [
            (15, 3, -0.5, True),  # exact boundary — all at minimum
            (15, 3, -0.49, False),  # sentiment just above max
            (14, 3, -0.5, False),  # reach just below
            (15, 2, -0.5, False),  # sources just below
        ],
        ids=[
            "exact-boundary-pass",
            "sentiment-just-above",
            "reach-just-below",
            "sources-just-below",
        ],
    )
    def test_pain_point_boundary(self, reach: int, sources: int, sentiment: float, expected: bool):
        signal = _make_signal(
            reach=reach,
            sentiment=sentiment,
            evidence_links=[f"https://link{i}.com" for i in range(sources)],
        )
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["pain-point"]) is expected

    # ── error-pattern ──

    def test_error_pattern_passes_occurrences(self):
        signal = _make_signal(category="error-pattern", reach=5)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["error-pattern"]) is True

    def test_error_pattern_passes_unique_users(self):
        signal = _make_signal(category="error-pattern", reach=0, unique_users=3)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["error-pattern"]) is True

    def test_error_pattern_fails_both_below(self):
        signal = _make_signal(category="error-pattern", reach=4, unique_users=2)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["error-pattern"]) is False

    @pytest.mark.parametrize(
        "reach,unique_users,expected",
        [
            (5, 0, True),  # exact occurrences threshold
            (4, 3, True),  # occurrences below, users at threshold (OR)
            (4, 2, False),  # both below
            (0, 3, True),  # zero occurrences, users at threshold
            (5, 3, True),  # both at threshold
        ],
        ids=["exact-occ", "occ-below-users-at", "both-below", "zero-occ-users-at", "both-at"],
    )
    def test_error_pattern_boundary(self, reach: int, unique_users: int, expected: bool):
        signal = _make_signal(category="error-pattern", reach=reach, unique_users=unique_users)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["error-pattern"]) is expected

    # ── feature-gap ──

    def test_feature_gap_passes(self):
        signal = _make_signal(category="feature-gap", competitor_count=2)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["feature-gap"]) is True

    def test_feature_gap_fails(self):
        signal = _make_signal(category="feature-gap", competitor_count=1)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["feature-gap"]) is False

    @pytest.mark.parametrize(
        "count,expected",
        [(0, False), (1, False), (2, True), (3, True)],
        ids=["zero", "one", "exact-threshold", "above"],
    )
    def test_feature_gap_boundary(self, count: int, expected: bool):
        signal = _make_signal(category="feature-gap", competitor_count=count)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["feature-gap"]) is expected

    # ── churn-signal ──

    def test_churn_signal_passes(self):
        signal = _make_signal(category="churn-signal", correlated_indicators=2)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["churn-signal"]) is True

    def test_churn_signal_fails(self):
        signal = _make_signal(category="churn-signal", correlated_indicators=1)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["churn-signal"]) is False

    # ── quality-issue ──

    def test_quality_issue_passes(self):
        signal = _make_signal(category="quality-issue", occurrence_count=3)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["quality-issue"]) is True

    def test_quality_issue_fails(self):
        signal = _make_signal(category="quality-issue", occurrence_count=2)
        assert passes_evidence_threshold(signal, EVIDENCE_THRESHOLDS["quality-issue"]) is False

    # ── unknown category ──

    def test_unknown_category_returns_false(self):
        signal = _make_signal(category="competitor-move")
        # competitor-move is a valid category but has no threshold config
        assert passes_evidence_threshold(signal, {}) is False


class TestAIScoring:
    """Test composite score calculation and act threshold logic."""

    def test_all_max_scores(self):
        scores = {dim: SCORING_MAX_PER_DIMENSION for dim in SCORING_DIMENSIONS}
        composite = calculate_composite_score(scores)
        assert composite == 10.0

    def test_all_zero_scores(self):
        scores = {dim: 0.0 for dim in SCORING_DIMENSIONS}
        composite = calculate_composite_score(scores)
        assert composite == 0.0

    def test_mixed_scores(self):
        scores = {
            "mission_alignment": 2.0,
            "feasibility": 1.5,
            "impact": 2.5,
            "urgency": 0.5,
        }
        composite = calculate_composite_score(scores)
        assert composite == pytest.approx(6.5)

    def test_score_at_threshold_passes(self):
        assert passes_act_threshold(6.0) is True

    def test_score_above_threshold_passes(self):
        assert passes_act_threshold(8.5) is True

    def test_score_below_threshold_fails(self):
        assert passes_act_threshold(5.9) is False

    @pytest.mark.parametrize(
        "score,expected",
        [
            (5.99, False),
            (6.0, True),
            (6.01, True),
            (10.0, True),
            (0.0, False),
        ],
        ids=["just-below", "exact", "just-above", "max", "zero"],
    )
    def test_act_threshold_boundary(self, score: float, expected: bool):
        assert passes_act_threshold(score) is expected

    def test_borderline_lower_bound(self):
        assert is_borderline(6.0) is True

    def test_borderline_mid(self):
        assert is_borderline(6.5) is True

    def test_borderline_upper_bound(self):
        assert is_borderline(7.0) is True

    def test_below_borderline(self):
        assert is_borderline(5.9) is False

    def test_above_borderline(self):
        assert is_borderline(7.1) is False


class TestStateMigration:
    """Test state migration from v1/v2 to v3."""

    def _make_v2_state(self) -> dict[str, Any]:
        return {
            "version": 2,
            "system_state": "Running",
            "last_poll": "2026-03-12T10:00:00",
            "conductor_pid": 1234,
            "trust_scores": {"Marketing": {"tier": 1, "merged": 6}},
            "issues": {"TST-42": {"status": "In Progress"}},
            "daily_counters": {"2026-03-12": {"issues_completed": 2}},
            "vision_cache": {"last_strategy_analysis": None, "identified_gaps": []},
            "pipeline": {
                "research_queue": [],
                "architecture_queue": [],
                "implementation_queue": [],
                "review_queue": [],
                "blocked": [],
                "active_workers": {},
                "active_teams": [],
            },
        }

    def test_v2_gets_discovery_section(self):
        state = self._make_v2_state()
        migrated = migrate_state(state)
        assert "discovery" in migrated
        assert migrated["discovery"]["signals_pending_validation"] == 0
        assert migrated["discovery"]["signal_queue"] == []

    def test_v2_preserves_existing_data(self):
        state = self._make_v2_state()
        migrated = migrate_state(state)
        assert migrated["trust_scores"] == {"Marketing": {"tier": 1, "merged": 6}}
        assert migrated["issues"] == {"TST-42": {"status": "In Progress"}}
        assert "2026-03-12" in migrated["daily_counters"]
        assert migrated["daily_counters"]["2026-03-12"]["issues_completed"] == 2

    def test_v2_version_bumped(self):
        state = self._make_v2_state()
        migrated = migrate_state(state)
        assert migrated["version"] == 3

    def test_v2_gets_session_mode(self):
        state = self._make_v2_state()
        migrated = migrate_state(state)
        assert migrated["session_mode"] == "interactive"

    def test_v2_existing_session_mode_preserved(self):
        state = self._make_v2_state()
        state["session_mode"] = "daemon"
        migrated = migrate_state(state)
        assert migrated["session_mode"] == "daemon"

    def test_v3_not_modified(self):
        v3_state = {
            "version": 3,
            "session_mode": "daemon",
            "discovery": {
                "last_internal_sense": "2026-03-13T08:00:00",
                "signals_pending_validation": 5,
                "signal_queue": [{"signal_id": "sig-1"}],
            },
            "trust_scores": {},
            "issues": {},
            "daily_counters": {},
        }
        original = copy.deepcopy(v3_state)
        migrated = migrate_state(v3_state)
        assert migrated == original

    def test_v1_migrates_correctly(self):
        v1_state = {
            "version": 1,
            "system_state": "Stopped",
            "trust_scores": {},
            "issues": {},
        }
        migrated = migrate_state(v1_state)
        assert migrated["version"] == 3
        assert "discovery" in migrated
        assert migrated["session_mode"] == "interactive"

    def test_no_version_field_treated_as_v1(self):
        state = {"system_state": "Stopped", "trust_scores": {}}
        migrated = migrate_state(state)
        assert migrated["version"] == 3
        assert "discovery" in migrated

    def test_v2_does_not_mutate_original(self):
        state = self._make_v2_state()
        original = copy.deepcopy(state)
        migrate_state(state)
        assert state == original

    def test_v2_daily_counters_get_discovery_fields(self):
        state = self._make_v2_state()
        migrated = migrate_state(state)
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in migrated["daily_counters"]
        today_counters = migrated["daily_counters"][today]
        assert today_counters["signals_processed"] == 0
        assert today_counters["signals_validated"] == 0
        assert today_counters["issues_discovered"] == 0


class TestCrawlCap:
    """Test external crawl daily cap enforcement."""

    def test_zero_crawls_allowed(self):
        counters = {"2026-03-13": {"external_crawls": 0}}
        assert can_crawl_externally(counters, "2026-03-13") is True

    def test_49_crawls_allowed(self):
        counters = {"2026-03-13": {"external_crawls": 49}}
        assert can_crawl_externally(counters, "2026-03-13") is True

    def test_50_crawls_blocked(self):
        counters = {"2026-03-13": {"external_crawls": 50}}
        assert can_crawl_externally(counters, "2026-03-13") is False

    def test_above_cap_blocked(self):
        counters = {"2026-03-13": {"external_crawls": 100}}
        assert can_crawl_externally(counters, "2026-03-13") is False

    def test_missing_counter_allows(self):
        assert can_crawl_externally({}, "2026-03-13") is True

    @pytest.mark.parametrize(
        "crawls,expected",
        [(0, True), (25, True), (49, True), (50, False), (51, False)],
        ids=["zero", "mid", "just-below", "at-cap", "above-cap"],
    )
    def test_crawl_cap_boundary(self, crawls: int, expected: bool):
        counters = {"2026-03-13": {"external_crawls": crawls}}
        assert can_crawl_externally(counters, "2026-03-13") is expected


class TestBorderlineRouting:
    """Test borderline score routing decisions."""

    def test_below_threshold_archived(self):
        assert determine_issue_routing(5.9, "Platform") == "archived"

    def test_borderline_lower_to_backlog(self):
        assert determine_issue_routing(6.0, "Platform") == "backlog"

    def test_borderline_mid_to_backlog(self):
        assert determine_issue_routing(6.5, "Platform") == "backlog"

    def test_borderline_upper_to_backlog(self):
        assert determine_issue_routing(7.0, "Platform") == "backlog"

    def test_above_borderline_autonomous_domain_full_action(self):
        assert determine_issue_routing(7.1, "Platform") == "action"

    def test_above_borderline_approval_required_to_backlog(self):
        assert determine_issue_routing(7.1, "Billing") == "backlog"

    def test_high_score_approval_required_still_backlog(self):
        assert determine_issue_routing(9.5, "Mobile") == "backlog"

    def test_high_score_autonomous_domain_full_action(self):
        assert determine_issue_routing(9.5, "Marketing") == "action"

    @pytest.mark.parametrize(
        "score,domain,expected",
        [
            (5.9, "Platform", "archived"),
            (6.0, "Platform", "backlog"),
            (7.0, "Platform", "backlog"),
            (7.1, "Platform", "action"),
            (7.1, "Billing", "backlog"),
            (7.1, "Infrastructure", "backlog"),
            (7.1, "Mobile", "backlog"),
            (7.1, "Marketing", "action"),
            (7.1, "Internationalization (i18n)", "action"),
            (10.0, "Platform", "action"),
            (10.0, "Billing", "backlog"),
            (0.0, "Platform", "archived"),
        ],
        ids=[
            "below-autonomous",
            "borderline-lower",
            "borderline-upper",
            "above-autonomous",
            "above-billing",
            "above-infra",
            "above-ios",
            "above-growth",
            "above-i18n",
            "max-autonomous",
            "max-approval-req",
            "zero-autonomous",
        ],
    )
    def test_routing_matrix(self, score: float, domain: str, expected: str):
        assert determine_issue_routing(score, domain) == expected
