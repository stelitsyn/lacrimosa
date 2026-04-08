"""TDD tests for Lacrimosa toolchain monitor module.
Classification, evaluation, decision routing, source crawling, budget, dedup, errors.
Imports FAIL — modules not yet implemented (TDD)."""

from __future__ import annotations
from typing import Any
from unittest.mock import MagicMock, patch
import pytest
from scripts.lacrimosa_toolchain_monitor import (
    ToolchainMonitor,
    read_findings_log,
    run_toolchain_monitor,
)
from scripts.lacrimosa_types import (
    FindingClassification,
    FindingDecision,
    ToolchainFinding,
)


def _evaluated(
    classification: str = "new_feature",
    relevance: float = 5.0,
    impact: float = 5.0,
    risk: float = 3.0,
    effort: str = "medium",
    **kw: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "classification": classification,
        "title": f"Test: {classification}",
        "summary": "Test summary",
        "content": "Test content",
        "source": "test_source",
        "url": "https://example.com",
        "relevance": relevance,
        "impact": impact,
        "risk": risk,
        "effort": effort,
    }
    base.update(kw)
    return base


@pytest.fixture
def tc_config() -> dict[str, Any]:
    return {
        "toolchain_monitor": {
            "cadence_hours": 6,
            "sources": {
                "anthropic_blog": {"urls": ["https://anthropic.com/news"]},
                "claude_code_releases": {
                    "method": "gh release list -R anthropics/claude-code --limit 5"
                },
                "api_changelog": {"url": "https://docs.anthropic.com/en/api/changelog"},
            },
            "evaluation": {"auto_adopt_threshold": 7, "human_review_risk_threshold": 7},
            "tracking": {"file": "~/.claude/lacrimosa/toolchain_monitor.jsonl"},
        }
    }


@pytest.fixture
def tc_state() -> dict[str, Any]:
    return {"toolchain_monitor": {"last_run": None, "last_findings_count": 0, "known_versions": {}}}


# -- Finding classification (REQ-TOOL-02) -----------------------------------


class TestFindingClassification:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("removes --dangerously-skip-permissions", FindingClassification.BREAKING_CHANGE.value),
            ("new --trust-level flag available", FindingClassification.NEW_FEATURE.value),
            ("output tokens $60/M instead of $75/M", FindingClassification.PRICING_CHANGE.value),
            ("introducing claude-4.5-opus model", FindingClassification.NEW_MODEL.value),
            ("deprecated: legacy prompt format", FindingClassification.DEPRECATION.value),
            ("CVE-2026-1234 critical vulnerability", FindingClassification.SECURITY_ADVISORY.value),
        ],
        ids=["breaking", "feature", "pricing", "model", "deprecation", "security"],
    )
    def test_classification_categories(self, tc_config, text, expected):
        monitor = ToolchainMonitor(tc_config)
        with patch.object(
            monitor,
            "_dispatch_classify",
            return_value={"classification": expected, "title": text, "summary": text},
        ):
            assert (
                monitor._classify({"content": text, "source": "test"})["classification"] == expected
            )


# -- Evaluation scoring (REQ-TOOL-02) ---------------------------------------


class TestEvaluationScoring:
    def test_evaluate_returns_all_dimensions(self, tc_config):
        monitor = ToolchainMonitor(tc_config)
        with patch.object(
            monitor,
            "_dispatch_evaluate",
            return_value={"relevance": 8, "impact": 7, "risk": 3, "effort": "low"},
        ):
            result = monitor._evaluate(
                {
                    "classification": "new_feature",
                    "content": "t",
                    "source": "t",
                    "title": "T",
                    "summary": "S",
                }
            )
        for key in ("relevance", "impact", "risk", "effort"):
            assert key in result

    def test_score_avg_relevance_impact(self, tc_config):
        """avg(8, 6) = 7.0 >= 7 and risk 3 < 7 -> auto_adopt."""
        result = ToolchainMonitor(tc_config)._decide(
            _evaluated(relevance=8.0, impact=6.0, risk=3.0)
        )
        assert result.decision == FindingDecision.AUTO_ADOPT.value

    def test_low_score_archives(self, tc_config):
        """avg(5, 4) = 4.5 < 7 -> archive."""
        result = ToolchainMonitor(tc_config)._decide(_evaluated(relevance=5.0, impact=4.0))
        assert result.decision == FindingDecision.ARCHIVE.value


# -- Decision routing (REQ-TOOL-02) -----------------------------------------


class TestDecisionRouting:
    def test_high_score_low_risk_auto_adopt(self, tc_config):
        result = ToolchainMonitor(tc_config)._decide(
            _evaluated(relevance=8.0, impact=7.0, risk=3.0)
        )
        assert result.decision == FindingDecision.AUTO_ADOPT.value

    def test_high_score_high_risk_human_review(self, tc_config):
        result = ToolchainMonitor(tc_config)._decide(
            _evaluated(relevance=8.0, impact=8.0, risk=8.0)
        )
        assert result.decision == FindingDecision.HUMAN_REVIEW.value

    def test_low_score_archive(self, tc_config):
        result = ToolchainMonitor(tc_config)._decide(
            _evaluated(relevance=3.0, impact=2.0, risk=1.0)
        )
        assert result.decision == FindingDecision.ARCHIVE.value

    def test_breaking_change_always_human_review(self, tc_config):
        """REQ-TOOL-02: breaking_change overrides score threshold."""
        result = ToolchainMonitor(tc_config)._decide(
            _evaluated(
                classification=FindingClassification.BREAKING_CHANGE.value,
                relevance=4.0,
                impact=4.0,
                risk=9.0,
            )
        )
        assert result.decision == FindingDecision.HUMAN_REVIEW.value

    def test_security_advisory_always_human_review(self, tc_config):
        result = ToolchainMonitor(tc_config)._decide(
            _evaluated(
                classification=FindingClassification.SECURITY_ADVISORY.value,
                relevance=9.0,
                impact=9.0,
                risk=1.0,
            )
        )
        assert result.decision == FindingDecision.HUMAN_REVIEW.value

    def test_finding_has_required_fields(self, tc_config):
        result = ToolchainMonitor(tc_config)._decide(
            _evaluated(relevance=8.0, impact=7.0, risk=3.0)
        )
        assert isinstance(result, ToolchainFinding)
        assert result.id.startswith("tcf-")
        assert result.classification == "new_feature"


# -- Source detection (REQ-TOOL-01) ------------------------------------------


class TestSourceDetection:
    @patch("subprocess.run")
    def test_gh_releases_via_subprocess(self, mock_run, tc_config):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="v2.5.0\tClaude Code v2.5\t2026-03-20\tLatest\n"
            "v2.4.0\tClaude Code v2.4\t2026-03-15\t\n",
        )
        monitor = ToolchainMonitor(tc_config)
        src = tc_config["toolchain_monitor"]["sources"]["claude_code_releases"]
        results = monitor._detect_gh_releases(src)
        assert len(results) >= 1 and results[0]["tag"] == "v2.5.0"
        mock_run.assert_called_once()

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_gh_cli_not_found(self, _run, tc_config):
        """EDGE-03: gh CLI missing -> skip gracefully."""
        src = tc_config["toolchain_monitor"]["sources"]["claude_code_releases"]
        assert ToolchainMonitor(tc_config)._detect_gh_releases(src) == []

    @patch("scripts.lacrimosa_toolchain_monitor.crawl_with_fallback")
    def test_url_sources_use_crawl(self, mock_crawl, tc_config):
        mock_crawl.return_value = "New feature announcement"
        budget = MagicMock(remaining=10)
        budget.can_crawl.return_value = True
        src = tc_config["toolchain_monitor"]["sources"]["anthropic_blog"]
        ToolchainMonitor(tc_config)._detect_url_sources("anthropic_blog", src, budget)
        assert mock_crawl.called


# -- Crawl budget sharing (REQ-TOOL-04) -------------------------------------


class TestCrawlBudget:
    @patch("scripts.lacrimosa_toolchain_monitor.crawl_with_fallback")
    def test_budget_exhausted_skips(self, mock_crawl, tc_config):
        budget = MagicMock(remaining=0)
        budget.can_crawl.return_value = False
        src = tc_config["toolchain_monitor"]["sources"]["anthropic_blog"]
        results = ToolchainMonitor(tc_config)._detect_url_sources("anthropic_blog", src, budget)
        assert results == [] and not mock_crawl.called

    @patch("scripts.lacrimosa_toolchain_monitor.crawl_with_fallback")
    def test_budget_consumed_per_crawl(self, mock_crawl, tc_config):
        mock_crawl.return_value = "Content"
        budget = MagicMock(remaining=5)
        budget.can_crawl.return_value = True
        src = tc_config["toolchain_monitor"]["sources"]["anthropic_blog"]
        ToolchainMonitor(tc_config)._detect_url_sources("anthropic_blog", src, budget)
        budget.consume.assert_called()


# -- Deduplication (REQ-TOOL-03) ---------------------------------------------


class TestDeduplication:
    def test_known_finding_skipped(self, tc_config, tc_state):
        tc_state["toolchain_monitor"]["known_versions"] = {
            "claude_code_releases": {"v2.5.0": "2026-03-20T00:00:00Z"}
        }
        monitor = ToolchainMonitor(tc_config)
        monitor._state = tc_state
        assert (
            monitor._is_known(
                {"source": "claude_code_releases", "tag": "v2.5.0", "title": "v2.5", "content": "t"}
            )
            is True
        )

    def test_new_finding_not_skipped(self, tc_config, tc_state):
        monitor = ToolchainMonitor(tc_config)
        monitor._state = tc_state
        assert (
            monitor._is_known(
                {"source": "claude_code_releases", "tag": "v2.6.0", "title": "v2.6", "content": "t"}
            )
            is False
        )


# -- Log persistence (REQ-TOOL-03) ------------------------------------------


class TestLogPersistence:
    def test_finding_persisted_to_jsonl(self, tc_config, tmp_path):
        tc_config["toolchain_monitor"]["tracking"]["file"] = str(tmp_path / "tc.jsonl")
        finding = ToolchainFinding(
            id="tcf-test1",
            source="test",
            url="https://example.com",
            timestamp="2026-03-20T00:00:00Z",
            classification="new_feature",
            title="Test",
            summary="Summary",
            raw_content="Content",
            relevance=8.0,
            impact=7.0,
            risk=3.0,
            effort_estimate="low",
            decision="auto_adopt",
            issue_id=None,
            applied=False,
        )
        ToolchainMonitor(tc_config)._persist(finding)
        log = read_findings_log(tmp_path / "tc.jsonl")
        assert len(log) == 1 and log[0]["id"] == "tcf-test1"

    def test_first_run_creates_log(self, tc_config, tmp_path):
        """REQ-TOOL-03: first run creates the JSONL file."""
        log_path = tmp_path / "tc_new.jsonl"
        tc_config["toolchain_monitor"]["tracking"]["file"] = str(log_path)
        finding = ToolchainFinding(
            id="tcf-new",
            source="test",
            url="https://example.com",
            timestamp="2026-03-20T00:00:00Z",
            classification="new_feature",
            title="New",
            summary="S",
            raw_content="C",
            relevance=5.0,
            impact=5.0,
            risk=2.0,
            effort_estimate="low",
            decision="archive",
            issue_id=None,
            applied=False,
        )
        ToolchainMonitor(tc_config)._persist(finding)
        assert log_path.exists()


# -- Source error handling (EDGE-03) -----------------------------------------


class TestSourceErrors:
    @patch(
        "scripts.lacrimosa_toolchain_monitor.crawl_with_fallback", side_effect=Exception("HTTP 503")
    )
    def test_source_error_skips_gracefully(self, _crawl, tc_config):
        budget = MagicMock(remaining=10)
        budget.can_crawl.return_value = True
        src = tc_config["toolchain_monitor"]["sources"]["anthropic_blog"]
        assert ToolchainMonitor(tc_config)._detect_url_sources("anthropic_blog", src, budget) == []

    @patch(
        "scripts.lacrimosa_toolchain_monitor.crawl_with_fallback",
        side_effect=Exception("All methods failed"),
    )
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_all_sources_fail_zero_findings(self, _sub, _crawl, tc_config, tc_state):
        """EDGE-03: all sources fail -> 0 findings, no crash."""
        assert len(run_toolchain_monitor(tc_config, tc_state, MagicMock())) == 0
