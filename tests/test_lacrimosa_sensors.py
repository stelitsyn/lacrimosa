"""
TDD tests for Lacrimosa v2 internal sensors module.

Tests: sensor output formatting, signal creation, sensor orchestration,
error isolation, SensorResult structure.

These tests import from lacrimosa_sensors and lacrimosa_signals —
modules that DO NOT EXIST yet. Tests must FAIL until implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# --- Imports from modules under test (will fail until implemented) ---
from lacrimosa_signals import create_signal, persist_signal, validate_signal
from lacrimosa_sensors import (
    SensorResult,
    run_all_sensors,
    run_sensor,
    sense_errors,
    sense_funnel,
    sense_payments,
    sense_usage,
)

# --- Constants (must match types module and config) ---

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

# --- Fixtures ---

SENSOR_CONFIG = {
    "sensors": {
        "funnel_analyzer": {
            "source": "ga4",
            "script": "scripts/ga4_audit_to_linear.py",
            "detects": ["broken_events", "high_dropoffs"],
        },
        "error_pattern_detector": {
            "source": "cloud_logging",
            "script": "scripts/analyze_business_flows.py",
            "detects": ["error_spikes", "new_error_patterns"],
        },
        "feedback_analyzer": {
            "source": "postgresql_feedback",
            "module": "assistant.feedback_storage",
            "detects": ["sentiment_clusters", "recurring_complaints"],
        },
        "payment_anomaly_detector": {
            "source": "stripe_webhooks_cloud_logging",
            "detects": ["failed_payments", "churn_signals"],
        },
        "usage_pattern_analyzer": {
            "source": "ga4_behavioral",
            "detects": ["feature_adoption_gaps", "engagement_drops"],
        },
    }
}


# ---------------------------------------------------------------------------
# Test: create_signal factory
# ---------------------------------------------------------------------------


class TestCreateSignal:
    """Test signal factory function from lacrimosa_signals."""

    def test_creates_valid_signal(self):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="High drop-off at step 3",
            summary="50% drop-off in signup funnel step 3",
            reach=120,
            sentiment=-0.6,
            relevance_tags=["funnel", "signup"],
            evidence_links=["https://analytics.google.com/report/1"],
        )
        errors = validate_signal(sig)
        assert errors == [], f"Signal validation failed: {errors}"

    def test_signal_has_required_fields(self):
        sig = create_signal(
            source="feedback",
            sensor="feedback-analyzer",
            category="pain-point",
            raw_content="Users hate hold music",
            summary="Recurring complaint about hold music",
            reach=15,
            sentiment=-0.8,
            relevance_tags=["hold-music"],
            evidence_links=[],
        )
        missing = REQUIRED_SIGNAL_FIELDS - set(sig.keys())
        assert missing == set(), f"Missing fields: {missing}"

    def test_signal_id_starts_with_sig(self):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="x",
            summary="x",
            reach=1,
            sentiment=0.0,
            relevance_tags=[],
            evidence_links=[],
        )
        assert sig["id"].startswith("sig-")

    def test_signal_validation_status_is_pending(self):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="x",
            summary="x",
            reach=1,
            sentiment=0.0,
            relevance_tags=[],
            evidence_links=[],
        )
        assert sig["validation_status"] == "pending"

    def test_signal_composite_score_is_none(self):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="x",
            summary="x",
            reach=1,
            sentiment=0.0,
            relevance_tags=[],
            evidence_links=[],
        )
        assert sig["composite_score"] is None

    def test_signal_timestamp_is_iso8601(self):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="x",
            summary="x",
            reach=1,
            sentiment=0.0,
            relevance_tags=[],
            evidence_links=[],
        )
        from datetime import datetime

        # Should parse without error
        datetime.fromisoformat(sig["timestamp"].replace("Z", "+00:00"))

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match="category"):
            create_signal(
                source="ga4",
                sensor="funnel-analyzer",
                category="not-valid",
                raw_content="x",
                summary="x",
                reach=1,
                sentiment=0.0,
                relevance_tags=[],
                evidence_links=[],
            )

    def test_sentiment_out_of_range_raises(self):
        with pytest.raises(ValueError, match="sentiment"):
            create_signal(
                source="ga4",
                sensor="funnel-analyzer",
                category="error-pattern",
                raw_content="x",
                summary="x",
                reach=1,
                sentiment=-1.5,
                relevance_tags=[],
                evidence_links=[],
            )

    def test_extra_fields_preserved(self):
        sig = create_signal(
            source="cloud-logging",
            sensor="error-pattern-detector",
            category="error-pattern",
            raw_content="TypeError",
            summary="Recurring TypeError",
            reach=7,
            sentiment=-0.5,
            relevance_tags=["error"],
            evidence_links=[],
            unique_users=4,
        )
        assert sig["unique_users"] == 4


# ---------------------------------------------------------------------------
# Test: persist_signal
# ---------------------------------------------------------------------------


class TestPersistSignal:
    """Test signal persistence to filesystem."""

    def test_persist_creates_file(self, tmp_path: Path):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="x",
            summary="x",
            reach=1,
            sentiment=0.0,
            relevance_tags=[],
            evidence_links=[],
        )
        path = persist_signal(sig, signals_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

    def test_persist_file_is_valid_json(self, tmp_path: Path):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="x",
            summary="x",
            reach=1,
            sentiment=0.0,
            relevance_tags=[],
            evidence_links=[],
        )
        path = persist_signal(sig, signals_dir=tmp_path)
        loaded = json.loads(path.read_text())
        assert loaded["id"] == sig["id"]

    def test_persist_creates_date_directory(self, tmp_path: Path):
        sig = create_signal(
            source="ga4",
            sensor="funnel-analyzer",
            category="error-pattern",
            raw_content="x",
            summary="x",
            reach=1,
            sentiment=0.0,
            relevance_tags=[],
            evidence_links=[],
        )
        path = persist_signal(sig, signals_dir=tmp_path)
        # Path should be signals_dir/YYYY-MM-DD/sig-xxx.json
        assert path.parent.name.count("-") == 2  # date format

    def test_persist_rejects_invalid_signal(self, tmp_path: Path):
        bad_signal = {"id": "sig-bad"}  # missing required fields
        with pytest.raises(ValueError):
            persist_signal(bad_signal, signals_dir=tmp_path)


# ---------------------------------------------------------------------------
# Test: SensorResult structure
# ---------------------------------------------------------------------------


class TestSensorResult:
    """Test SensorResult TypedDict contract."""

    def test_successful_result_has_signals(self):
        result: SensorResult = {
            "signals": [{"id": "sig-1"}],
            "errors": [],
            "duration_seconds": 1.5,
        }
        assert len(result["signals"]) == 1
        assert result["errors"] == []

    def test_failed_result_has_errors(self):
        result: SensorResult = {
            "signals": [],
            "errors": ["Connection refused"],
            "duration_seconds": 0.1,
        }
        assert result["signals"] == []
        assert len(result["errors"]) == 1


# ---------------------------------------------------------------------------
# Test: Individual sensor output formatting
# ---------------------------------------------------------------------------


class TestSensorOutputFormat:
    """Test that each sensor function returns signals with correct source/sensor."""

    @patch("subprocess.run")
    def test_funnel_sensor_source_and_sensor(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"event": "signup_step3", "drop_off_pct": 55}]',
        )
        signals = sense_funnel(SENSOR_CONFIG)
        for sig in signals:
            assert sig["source"] == "ga4"
            assert sig["sensor"] == "funnel-analyzer"

    @patch("subprocess.run")
    def test_error_sensor_source_and_sensor(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"error": "TypeError", "count": 7}]',
        )
        signals = sense_errors(SENSOR_CONFIG)
        for sig in signals:
            assert sig["source"] == "cloud-logging"
            assert sig["sensor"] == "error-pattern-detector"

    @patch("subprocess.run")
    def test_payment_sensor_source_and_sensor(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"type": "payment_failed", "count": 10}]',
        )
        signals = sense_payments(SENSOR_CONFIG)
        for sig in signals:
            assert sig["source"] == "stripe"
            assert sig["sensor"] == "payment-anomaly-detector"

    @patch("subprocess.run")
    def test_usage_sensor_source_and_sensor(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"feature": "search", "engagement_drop_pct": 30}]',
        )
        signals = sense_usage(SENSOR_CONFIG)
        for sig in signals:
            assert sig["source"] == "usage"
            assert sig["sensor"] == "usage-pattern-analyzer"


# ---------------------------------------------------------------------------
# Test: run_all_sensors orchestration
# ---------------------------------------------------------------------------


class TestRunAllSensors:
    """Test sensor orchestration — error isolation and result collection."""

    @patch("lacrimosa_sensors.sense_funnel", return_value=[])
    @patch("lacrimosa_sensors.sense_errors", return_value=[])
    @patch("lacrimosa_sensors.sense_feedback", return_value=[])
    @patch("lacrimosa_sensors.sense_payments", return_value=[])
    @patch("lacrimosa_sensors.sense_usage", return_value=[])
    def test_all_sensors_run(self, *mocks):
        results = run_all_sensors(SENSOR_CONFIG)
        assert len(results) == 5

    @patch("lacrimosa_sensors.sense_funnel", side_effect=Exception("GA4 API down"))
    @patch("lacrimosa_sensors.sense_errors", return_value=[])
    @patch("lacrimosa_sensors.sense_feedback", return_value=[])
    @patch("lacrimosa_sensors.sense_payments", return_value=[])
    @patch("lacrimosa_sensors.sense_usage", return_value=[])
    def test_single_sensor_failure_does_not_halt(self, *mocks):
        """D2-AC08: single sensor failure → other sensors continue."""
        results = run_all_sensors(SENSOR_CONFIG)
        assert len(results) == 5
        # The failed sensor should have errors, others should not
        failed = [r for r in results if r["errors"]]
        succeeded = [r for r in results if not r["errors"]]
        assert len(failed) >= 1
        assert len(succeeded) >= 4

    @patch("lacrimosa_sensors.sense_funnel", side_effect=Exception("fail1"))
    @patch("lacrimosa_sensors.sense_errors", side_effect=Exception("fail2"))
    @patch("lacrimosa_sensors.sense_feedback", side_effect=Exception("fail3"))
    @patch("lacrimosa_sensors.sense_payments", side_effect=Exception("fail4"))
    @patch("lacrimosa_sensors.sense_usage", side_effect=Exception("fail5"))
    def test_all_sensors_fail_returns_all_errors(self, *mocks):
        """BS-012: all sensors fail → zero signals, 5 errors, no crash."""
        results = run_all_sensors(SENSOR_CONFIG)
        assert len(results) == 5
        total_signals = sum(len(r["signals"]) for r in results)
        total_errors = sum(len(r["errors"]) for r in results)
        assert total_signals == 0
        assert total_errors == 5

    def test_run_sensor_invalid_name_raises(self):
        with pytest.raises(ValueError):
            run_sensor("nonexistent-sensor", SENSOR_CONFIG)

    @patch("lacrimosa_sensors.sense_funnel")
    def test_each_result_has_duration(self, mock_funnel):
        mock_funnel.return_value = []
        result = run_sensor("funnel_analyzer", SENSOR_CONFIG)
        assert "duration_seconds" in result
        assert isinstance(result["duration_seconds"], float)
        assert result["duration_seconds"] >= 0
