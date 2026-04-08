"""
TDD tests for Lacrimosa Linear intake system.

Tests: intake report parsing, LLM-based classification/triage,
severity/domain/project routing, Linear issue creation, deduplication,
and end-to-end intake pipeline.

Covers TST-929: Integrate Linear intake for bug reports & support emails.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from lacrimosa_intake import (
    IntakeResult,
    IntakeSource,
    TriageClassification,
    classify_report,
    create_intake_report,
    parse_classification_response,
    route_to_project,
    route_to_labels,
    determine_priority,
    process_intake,
    check_intake_deduplication,
    create_linear_issue_from_intake,
    DOMAIN_KEYWORDS,
    SEVERITY_PRIORITY_MAP,
)


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def bug_report_raw() -> dict[str, Any]:
    return {
        "source": "bug_report",
        "subject": "Task fails after 30 seconds on mobile",
        "body": (
            "When I start a task using the app on mobile, it consistently "
            "fails after approximately 30 seconds. This happens on both WiFi and "
            "cellular. I've tried reinstalling the app. Device: Pixel 8 Pro."
        ),
        "sender": "user@example.com",
        "received_at": "2026-03-22T10:00:00Z",
    }


@pytest.fixture
def support_email_raw() -> dict[str, Any]:
    return {
        "source": "support_email",
        "subject": "Can't update billing information",
        "body": (
            "I'm trying to update my credit card on file but the settings page "
            "shows a spinner and never loads. I need to update before my next "
            "billing cycle on April 1st."
        ),
        "sender": "customer@company.com",
        "received_at": "2026-03-22T11:30:00Z",
    }


@pytest.fixture
def feature_request_raw() -> dict[str, Any]:
    return {
        "source": "support_email",
        "subject": "Request: Slack integration",
        "body": (
            "It would be great if TestProduct could also send notifications via Slack. "
            "Many of my team members prefer Slack over email."
        ),
        "sender": "feedback@example.com",
        "received_at": "2026-03-22T12:00:00Z",
    }


@pytest.fixture
def classification_response_bug() -> dict[str, Any]:
    return {
        "severity": "high",
        "category": "bug",
        "domain": "platform",
        "summary": "Mobile tasks fail after 30 seconds on Pixel 8 Pro",
        "reproduction_steps": [
            "Open app on mobile",
            "Start a task",
            "Wait 30 seconds",
            "Task fails",
        ],
        "affected_area": "task_execution",
        "confidence": 0.92,
    }


@pytest.fixture
def classification_response_billing() -> dict[str, Any]:
    return {
        "severity": "medium",
        "category": "bug",
        "domain": "billing",
        "summary": "Settings page spinner when updating billing info",
        "reproduction_steps": [
            "Navigate to settings",
            "Click update billing",
            "Page shows spinner indefinitely",
        ],
        "affected_area": "billing_settings",
        "confidence": 0.88,
    }


@pytest.fixture
def classification_response_feature() -> dict[str, Any]:
    return {
        "severity": "low",
        "category": "feature_request",
        "domain": "platform",
        "summary": "User requests Slack notification integration",
        "reproduction_steps": [],
        "affected_area": "integrations",
        "confidence": 0.95,
    }


# ---------------------------------------------------------------------------
# Test: IntakeReport creation
# ---------------------------------------------------------------------------


class TestCreateIntakeReport:
    """Test creating IntakeReport from raw data."""

    def test_creates_report_with_required_fields(self, bug_report_raw):
        report = create_intake_report(**bug_report_raw)
        assert report.source == IntakeSource.BUG_REPORT
        assert report.subject == bug_report_raw["subject"]
        assert report.body == bug_report_raw["body"]
        assert report.sender == bug_report_raw["sender"]
        assert report.received_at == bug_report_raw["received_at"]
        assert report.id.startswith("intake-")

    def test_creates_report_from_support_email(self, support_email_raw):
        report = create_intake_report(**support_email_raw)
        assert report.source == IntakeSource.SUPPORT_EMAIL

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="Invalid intake source"):
            create_intake_report(
                source="invalid_source",
                subject="Test",
                body="Test body",
                sender="test@test.com",
                received_at="2026-03-22T10:00:00Z",
            )

    def test_empty_body_raises(self):
        with pytest.raises(ValueError, match="body"):
            create_intake_report(
                source="bug_report",
                subject="Test",
                body="",
                sender="test@test.com",
                received_at="2026-03-22T10:00:00Z",
            )

    def test_empty_subject_raises(self):
        with pytest.raises(ValueError, match="subject"):
            create_intake_report(
                source="bug_report",
                subject="",
                body="Some body text",
                sender="test@test.com",
                received_at="2026-03-22T10:00:00Z",
            )

    def test_report_id_is_unique(self, bug_report_raw):
        r1 = create_intake_report(**bug_report_raw)
        r2 = create_intake_report(**bug_report_raw)
        assert r1.id != r2.id


# ---------------------------------------------------------------------------
# Test: parse_classification_response
# ---------------------------------------------------------------------------


class TestParseClassificationResponse:
    """Test parsing LLM classification output into TriageClassification."""

    def test_parses_valid_json(self, classification_response_bug):
        raw = json.dumps(classification_response_bug)
        result = parse_classification_response(raw)
        assert isinstance(result, TriageClassification)
        assert result.severity == "high"
        assert result.category == "bug"
        assert result.domain == "platform"
        assert result.confidence >= 0.0

    def test_parses_json_in_markdown_fences(self, classification_response_bug):
        raw = f"```json\n{json.dumps(classification_response_bug)}\n```"
        result = parse_classification_response(raw)
        assert result.severity == "high"

    def test_parses_json_with_preamble(self, classification_response_bug):
        raw = f"Here is my analysis:\n{json.dumps(classification_response_bug)}"
        result = parse_classification_response(raw)
        assert result.category == "bug"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="[Pp]arse|JSON"):
            parse_classification_response("this is not json at all")

    def test_missing_severity_raises(self, classification_response_bug):
        del classification_response_bug["severity"]
        raw = json.dumps(classification_response_bug)
        with pytest.raises(ValueError, match="severity"):
            parse_classification_response(raw)

    def test_missing_category_raises(self, classification_response_bug):
        del classification_response_bug["category"]
        raw = json.dumps(classification_response_bug)
        with pytest.raises(ValueError, match="category"):
            parse_classification_response(raw)

    def test_missing_domain_raises(self, classification_response_bug):
        del classification_response_bug["domain"]
        raw = json.dumps(classification_response_bug)
        with pytest.raises(ValueError, match="domain"):
            parse_classification_response(raw)

    def test_invalid_severity_normalized(self):
        raw = json.dumps(
            {
                "severity": "CRITICAL",
                "category": "bug",
                "domain": "infra",
                "summary": "Server down",
                "confidence": 0.99,
            }
        )
        result = parse_classification_response(raw)
        assert result.severity == "critical"

    def test_valid_categories(self):
        for cat in ("bug", "feature_request", "question", "complaint", "praise"):
            raw = json.dumps(
                {
                    "severity": "low",
                    "category": cat,
                    "domain": "platform",
                    "summary": "Test",
                    "confidence": 0.5,
                }
            )
            result = parse_classification_response(raw)
            assert result.category == cat

    def test_invalid_category_raises(self):
        raw = json.dumps(
            {
                "severity": "low",
                "category": "unknown_cat",
                "domain": "platform",
                "summary": "Test",
                "confidence": 0.5,
            }
        )
        with pytest.raises(ValueError, match="category"):
            parse_classification_response(raw)

    def test_invalid_severity_raises(self):
        raw = json.dumps(
            {
                "severity": "extreme",
                "category": "bug",
                "domain": "platform",
                "summary": "Test",
                "confidence": 0.5,
            }
        )
        with pytest.raises(ValueError, match="severity"):
            parse_classification_response(raw)

    def test_reproduction_steps_non_list_coerced(self):
        raw = json.dumps(
            {
                "severity": "low",
                "category": "bug",
                "domain": "platform",
                "summary": "Test",
                "confidence": 0.5,
                "reproduction_steps": "Open the app and click submit",
            }
        )
        result = parse_classification_response(raw)
        assert isinstance(result.reproduction_steps, list)
        assert len(result.reproduction_steps) == 1
        assert result.reproduction_steps[0] == "Open the app and click submit"

    def test_reproduction_steps_none_coerced_to_empty_list(self):
        raw = json.dumps(
            {
                "severity": "low",
                "category": "bug",
                "domain": "platform",
                "summary": "Test",
                "confidence": 0.5,
                "reproduction_steps": None,
            }
        )
        result = parse_classification_response(raw)
        assert isinstance(result.reproduction_steps, list)
        assert len(result.reproduction_steps) == 0

    def test_confidence_clamped(self):
        raw = json.dumps(
            {
                "severity": "low",
                "category": "bug",
                "domain": "platform",
                "summary": "Test",
                "confidence": 1.5,
            }
        )
        result = parse_classification_response(raw)
        assert result.confidence <= 1.0

    def test_missing_confidence_defaults(self, classification_response_bug):
        del classification_response_bug["confidence"]
        raw = json.dumps(classification_response_bug)
        result = parse_classification_response(raw)
        assert result.confidence == 0.5  # default


# ---------------------------------------------------------------------------
# Test: route_to_project
# ---------------------------------------------------------------------------


class TestRouteToProject:
    """Test domain → Linear project routing."""

    def test_feature_domain_routes_to_platform(self):
        assert route_to_project("feature") == "Platform"

    def test_billing_domain_routes_to_billing(self):
        assert route_to_project("billing") == "Billing"

    def test_mobile_domain_routes_to_mobile(self):
        assert route_to_project("mobile") == "Mobile"

    def test_infra_domain_routes_to_infra(self):
        assert route_to_project("infra") == "Infrastructure"

    def test_marketing_domain_routes_to_growth(self):
        assert route_to_project("marketing") == "Marketing"

    def test_i18n_domain_routes_to_i18n(self):
        # i18n is not in the test config project_routing, falls back to default_project
        assert route_to_project("i18n") == "Platform"

    def test_unknown_domain_defaults_to_platform(self):
        assert route_to_project("unknown_thing") == "Platform"

    def test_platform_domain_routes_to_platform(self):
        assert route_to_project("platform") == "Platform"


# ---------------------------------------------------------------------------
# Test: route_to_labels
# ---------------------------------------------------------------------------


class TestRouteToLabels:
    """Test classification → Linear label routing."""

    def test_bug_in_platform_gets_area_and_domain_labels(self):
        classification = TriageClassification(
            severity="high",
            category="bug",
            domain="platform",
            summary="Task fails",
            confidence=0.9,
        )
        labels = route_to_labels(classification)
        assert "Platform" in labels
        assert "Bug" in labels

    def test_feature_request_gets_type_label(self):
        classification = TriageClassification(
            severity="low",
            category="feature_request",
            domain="platform",
            summary="Add Slack integration",
            confidence=0.9,
        )
        labels = route_to_labels(classification)
        assert "Feature Request" in labels

    def test_billing_bug_gets_billing_label(self):
        classification = TriageClassification(
            severity="medium",
            category="bug",
            domain="billing",
            summary="Billing page broken",
            confidence=0.88,
        )
        labels = route_to_labels(classification)
        assert "Billing" in labels
        assert "Bug" in labels


# ---------------------------------------------------------------------------
# Test: determine_priority
# ---------------------------------------------------------------------------


class TestDeterminePriority:
    """Test severity → Linear priority mapping."""

    def test_critical_maps_to_urgent(self):
        assert determine_priority("critical") == 1

    def test_high_maps_to_high(self):
        assert determine_priority("high") == 2

    def test_medium_maps_to_normal(self):
        assert determine_priority("medium") == 3

    def test_low_maps_to_low(self):
        assert determine_priority("low") == 4

    def test_unknown_defaults_to_normal(self):
        assert determine_priority("unknown") == 3


# ---------------------------------------------------------------------------
# Test: classify_report (LLM classification)
# ---------------------------------------------------------------------------


class TestClassifyReport:
    """Test LLM-based report classification."""

    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_returns_triage_classification(
        self, mock_dispatch, bug_report_raw, classification_response_bug
    ):
        mock_dispatch.return_value = json.dumps(classification_response_bug)
        report = create_intake_report(**bug_report_raw)
        result = classify_report(report)
        assert isinstance(result, TriageClassification)
        assert result.severity == "high"
        assert result.category == "bug"
        assert result.domain == "platform"

    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_retries_on_parse_failure(self, mock_dispatch, bug_report_raw):
        mock_dispatch.side_effect = [
            "not json",  # first attempt fails
            json.dumps(
                {
                    "severity": "high",
                    "category": "bug",
                    "domain": "platform",
                    "summary": "Task fails",
                    "confidence": 0.9,
                }
            ),
        ]
        report = create_intake_report(**bug_report_raw)
        result = classify_report(report)
        assert result.severity == "high"
        assert mock_dispatch.call_count == 2

    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_returns_fallback_on_all_failures(self, mock_dispatch, bug_report_raw):
        mock_dispatch.side_effect = ValueError("LLM failed")
        report = create_intake_report(**bug_report_raw)
        result = classify_report(report)
        assert result.severity == "medium"
        assert result.category == "bug"
        assert result.domain == "platform"
        assert result.confidence == 0.0

    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_support_email_classified(
        self, mock_dispatch, support_email_raw, classification_response_billing
    ):
        mock_dispatch.return_value = json.dumps(classification_response_billing)
        report = create_intake_report(**support_email_raw)
        result = classify_report(report)
        assert result.domain == "billing"

    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_feature_request_classified(
        self, mock_dispatch, feature_request_raw, classification_response_feature
    ):
        mock_dispatch.return_value = json.dumps(classification_response_feature)
        report = create_intake_report(**feature_request_raw)
        result = classify_report(report)
        assert result.category == "feature_request"


# ---------------------------------------------------------------------------
# Test: check_intake_deduplication
# ---------------------------------------------------------------------------


class TestCheckIntakeDeduplication:
    """Test deduplication of intake reports against existing Linear issues."""

    @patch("lacrimosa_intake._dispatch_dedup_session")
    def test_novel_report_returns_true(self, mock_dispatch):
        mock_dispatch.return_value = json.dumps(
            {
                "is_novel": True,
                "existing_issue": None,
            }
        )
        is_novel, existing = check_intake_deduplication("Task fails on mobile", ["platform", "mobile"])
        assert is_novel is True
        assert existing is None

    @patch("lacrimosa_intake._dispatch_dedup_session")
    def test_duplicate_report_returns_false(self, mock_dispatch):
        mock_dispatch.return_value = json.dumps(
            {
                "is_novel": False,
                "existing_issue": "TST-500",
            }
        )
        is_novel, existing = check_intake_deduplication("Task fails on mobile", ["platform", "mobile"])
        assert is_novel is False
        assert existing == "TST-500"

    @patch("lacrimosa_intake._dispatch_dedup_session")
    def test_dedup_failure_treats_as_novel(self, mock_dispatch):
        mock_dispatch.side_effect = Exception("Connection error")
        is_novel, existing = check_intake_deduplication("Something broke", ["platform"])
        assert is_novel is True
        assert existing is None


# ---------------------------------------------------------------------------
# Test: create_linear_issue_from_intake
# ---------------------------------------------------------------------------


class TestCreateLinearIssueFromIntake:
    """Test Linear issue creation from classified intake."""

    @patch("lacrimosa_intake._dispatch_issue_creation_session")
    def test_creates_issue_successfully(self, mock_dispatch, bug_report_raw):
        mock_dispatch.return_value = json.dumps(
            {
                "created": True,
                "linear_issue_id": "TST-950",
                "gh_issue_url": "https://github.com/org/repo/issues/850",
            }
        )
        report = create_intake_report(**bug_report_raw)
        classification = TriageClassification(
            severity="high",
            category="bug",
            domain="platform",
            summary="Mobile tasks fail after 30s",
            confidence=0.92,
        )
        result = create_linear_issue_from_intake(report, classification)
        assert result["created"] is True
        assert result["linear_issue_id"] == "TST-950"

    @patch("lacrimosa_intake._dispatch_issue_creation_session")
    def test_creation_failure_returns_not_created(self, mock_dispatch, bug_report_raw):
        mock_dispatch.side_effect = Exception("CLI not found")
        report = create_intake_report(**bug_report_raw)
        classification = TriageClassification(
            severity="high",
            category="bug",
            domain="platform",
            summary="iOS calls drop",
            confidence=0.92,
        )
        result = create_linear_issue_from_intake(report, classification)
        assert result["created"] is False
        assert result["reason"] is not None


# ---------------------------------------------------------------------------
# Test: process_intake (end-to-end pipeline)
# ---------------------------------------------------------------------------


class TestProcessIntake:
    """Test the full intake pipeline: parse → classify → dedup → create."""

    @patch("lacrimosa_intake._dispatch_issue_creation_session")
    @patch("lacrimosa_intake._dispatch_dedup_session")
    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_full_pipeline_bug_report(
        self,
        mock_classify,
        mock_dedup,
        mock_create,
        bug_report_raw,
        classification_response_bug,
    ):
        mock_classify.return_value = json.dumps(classification_response_bug)
        mock_dedup.return_value = json.dumps(
            {
                "is_novel": True,
                "existing_issue": None,
            }
        )
        mock_create.return_value = json.dumps(
            {
                "created": True,
                "linear_issue_id": "TST-951",
                "gh_issue_url": "https://github.com/org/repo/issues/851",
            }
        )

        result = process_intake(bug_report_raw)
        assert isinstance(result, IntakeResult)
        assert result.classified is True
        assert result.is_novel is True
        assert result.issue_created is True
        assert result.linear_issue_id == "TST-951"

    @patch("lacrimosa_intake._dispatch_dedup_session")
    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_pipeline_skips_duplicate(
        self,
        mock_classify,
        mock_dedup,
        bug_report_raw,
        classification_response_bug,
    ):
        mock_classify.return_value = json.dumps(classification_response_bug)
        mock_dedup.return_value = json.dumps(
            {
                "is_novel": False,
                "existing_issue": "TST-500",
            }
        )

        result = process_intake(bug_report_raw)
        assert result.is_novel is False
        assert result.issue_created is False
        assert result.duplicate_of == "TST-500"

    @patch("lacrimosa_intake._dispatch_issue_creation_session")
    @patch("lacrimosa_intake._dispatch_dedup_session")
    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_pipeline_feature_request(
        self,
        mock_classify,
        mock_dedup,
        mock_create,
        feature_request_raw,
        classification_response_feature,
    ):
        mock_classify.return_value = json.dumps(classification_response_feature)
        mock_dedup.return_value = json.dumps(
            {
                "is_novel": True,
                "existing_issue": None,
            }
        )
        mock_create.return_value = json.dumps(
            {
                "created": True,
                "linear_issue_id": "TST-952",
                "gh_issue_url": None,
            }
        )

        result = process_intake(feature_request_raw)
        assert result.classification.category == "feature_request"
        assert result.issue_created is True

    @patch("lacrimosa_intake._dispatch_issue_creation_session")
    @patch("lacrimosa_intake._dispatch_dedup_session")
    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_pipeline_classification_failure_still_returns_result(
        self,
        mock_classify,
        mock_dedup,
        mock_create,
        bug_report_raw,
    ):
        mock_classify.side_effect = Exception("LLM unavailable")
        mock_dedup.return_value = json.dumps(
            {
                "is_novel": True,
                "existing_issue": None,
            }
        )
        mock_create.return_value = json.dumps(
            {
                "created": True,
                "linear_issue_id": "TST-999",
                "gh_issue_url": None,
            }
        )
        result = process_intake(bug_report_raw)
        assert result.classified is True  # fallback classification used
        assert result.classification.confidence == 0.0

    @patch("lacrimosa_intake._dispatch_issue_creation_session")
    @patch("lacrimosa_intake._dispatch_dedup_session")
    @patch("lacrimosa_intake._dispatch_classification_session")
    def test_pipeline_praise_category_skips_issue_creation(
        self,
        mock_classify,
        mock_dedup,
        mock_create,
    ):
        mock_classify.return_value = json.dumps(
            {
                "severity": "low",
                "category": "praise",
                "domain": "platform",
                "summary": "Love the app!",
                "confidence": 0.95,
            }
        )

        result = process_intake(
            {
                "source": "support_email",
                "subject": "Love TestProduct!",
                "body": "Just wanted to say I love the app. Keep up the great work!",
                "sender": "happy@user.com",
                "received_at": "2026-03-22T14:00:00Z",
            }
        )
        assert result.classification.category == "praise"
        assert result.issue_created is False
        mock_create.assert_not_called()

    def test_pipeline_missing_required_field_raises(self):
        with pytest.raises(ValueError, match="Missing required field"):
            process_intake(
                {
                    "source": "bug_report",
                    "subject": "Missing body field",
                    "sender": "test@test.com",
                    "received_at": "2026-03-22T14:00:00Z",
                }
            )

    def test_pipeline_sender_defaults_to_empty(self):
        """sender is optional in raw_report; defaults to empty string."""
        raw = {
            "source": "bug_report",
            "subject": "No sender",
            "body": "Some body text",
            "received_at": "2026-03-22T14:00:00Z",
        }
        with patch("lacrimosa_intake._dispatch_classification_session") as mock_cls:
            mock_cls.return_value = json.dumps(
                {
                    "severity": "low",
                    "category": "praise",
                    "domain": "platform",
                    "summary": "Test",
                    "confidence": 0.5,
                }
            )
            result = process_intake(raw)
            assert result.report.sender == ""


# ---------------------------------------------------------------------------
# Test: DOMAIN_KEYWORDS mapping
# ---------------------------------------------------------------------------


class TestDomainKeywords:
    """Test that domain keyword mappings are comprehensive."""

    def test_communication_keywords_exist(self):
        assert "communication" in DOMAIN_KEYWORDS
        assert len(DOMAIN_KEYWORDS["communication"]) > 0

    def test_billing_keywords_exist(self):
        assert "billing" in DOMAIN_KEYWORDS
        assert len(DOMAIN_KEYWORDS["billing"]) > 0

    def test_ios_keywords_exist(self):
        assert "ios" in DOMAIN_KEYWORDS
        assert len(DOMAIN_KEYWORDS["ios"]) > 0

    def test_infra_keywords_exist(self):
        assert "infra" in DOMAIN_KEYWORDS
        assert len(DOMAIN_KEYWORDS["infra"]) > 0


# ---------------------------------------------------------------------------
# Test: SEVERITY_PRIORITY_MAP
# ---------------------------------------------------------------------------


class TestSeverityPriorityMap:
    """Test severity to priority mapping completeness."""

    def test_all_severities_mapped(self):
        for sev in ("critical", "high", "medium", "low"):
            assert sev in SEVERITY_PRIORITY_MAP

    def test_priorities_are_1_to_4(self):
        for priority in SEVERITY_PRIORITY_MAP.values():
            assert 1 <= priority <= 4
