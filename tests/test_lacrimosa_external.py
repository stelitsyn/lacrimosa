"""
TDD tests for Lacrimosa v2 external sensing module.

Tests: crawl budget, fallback chain, social listener output,
competitor monitor output, review aggregator, cost cap enforcement.

These tests import from lacrimosa_external_sensing — a module that
DOES NOT EXIST yet. Tests must FAIL until implementation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

# --- Imports from modules under test (will fail until implemented) ---
from lacrimosa_external_sensing import (
    CrawlBudget,
    ExternalSenseResult,
    competitor_monitor,
    crawl_with_fallback,
    run_external_sensing,
    social_listener,
)

# --- Constants ---

VALID_SOURCES = {
    "reddit",
    "ga4",
    "cloud-logging",
    "feedback",
    "competitor",
    "stripe",
    "usage",
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

EXTERNAL_CONFIG = {
    "crawl": {
        "max_external_crawls_per_day": 50,
        "crawl_api_key_secret": "CRAWL_SERVICE_API_KEY",
        "fallback_chain": ["primary_crawl", "cloudflare_crawl", "web_search_fetch", "skip_and_log"],
        "social": {
            "sources": {
                "reddit": {
                    "subreddits": ["productivity", "saas", "startups"],
                    "keywords": ["AI assistant", "productivity"],
                },
                "twitter": {"search_terms": ["AI productivity"]},
                "hackernews": {"keywords": ["AI automation"]},
                "forums": {"urls": []},
            },
            "cadence": "6h",
        },
        "competitors": {
            "targets": [
                {"name": "CompetitorA", "urls": ["https://competitor-a.example.com/changelog"]},
                {"name": "CompetitorB", "urls": ["https://competitor-b.example.com"]},
                {"name": "CompetitorC", "urls": ["https://competitor-c.example.com/changelog"]},
            ],
            "review_sources": ["trustpilot", "g2", "capterra"],
            "cadence": "6h",
        },
    },
}


# ---------------------------------------------------------------------------
# Test: CrawlBudget
# ---------------------------------------------------------------------------


class TestCrawlBudget:
    """Test CrawlBudget dataclass for tracking crawl consumption."""

    def test_initial_state(self):
        budget = CrawlBudget(remaining=50, used=0)
        assert budget.remaining == 50
        assert budget.used == 0

    def test_can_crawl_when_budget_available(self):
        budget = CrawlBudget(remaining=10, used=40)
        assert budget.can_crawl() is True

    def test_cannot_crawl_when_exhausted(self):
        budget = CrawlBudget(remaining=0, used=50)
        assert budget.can_crawl() is False

    def test_consume_decrements_remaining(self):
        budget = CrawlBudget(remaining=10, used=40)
        budget.consume()
        assert budget.remaining == 9
        assert budget.used == 41

    def test_consume_at_zero_raises_or_blocks(self):
        budget = CrawlBudget(remaining=0, used=50)
        assert budget.can_crawl() is False

    @pytest.mark.parametrize(
        "remaining,expected",
        [(0, False), (1, True), (50, True)],
        ids=["exhausted", "one-left", "fresh"],
    )
    def test_can_crawl_boundary(self, remaining: int, expected: bool):
        budget = CrawlBudget(remaining=remaining, used=50 - remaining)
        assert budget.can_crawl() is expected


# ---------------------------------------------------------------------------
# Test: crawl_with_fallback
# ---------------------------------------------------------------------------


class TestCrawlWithFallback:
    """Test fallback chain: firecrawl → cloudflare → websearch → skip."""

    @patch("lacrimosa_external_sensing._crawl_firecrawl", return_value=None)
    @patch("lacrimosa_external_sensing._crawl_cloudflare", return_value=None)
    @patch("lacrimosa_external_sensing._crawl_websearch", return_value="Reddit post content")
    def test_falls_through_to_websearch(self, mock_ws, mock_cf, mock_fc):
        """D4-AC03: Firecrawl fails → Cloudflare fails → WebSearch succeeds."""
        result = crawl_with_fallback("https://reddit.com/r/test", EXTERNAL_CONFIG)
        assert result == "Reddit post content"
        mock_fc.assert_called_once()
        mock_cf.assert_called_once()
        mock_ws.assert_called_once()

    @patch("lacrimosa_external_sensing._crawl_firecrawl", return_value="Content from Firecrawl")
    def test_firecrawl_success_stops_chain(self, mock_fc):
        result = crawl_with_fallback("https://reddit.com/r/test", EXTERNAL_CONFIG)
        assert result == "Content from Firecrawl"

    @patch("lacrimosa_external_sensing._crawl_firecrawl", return_value=None)
    @patch("lacrimosa_external_sensing._crawl_cloudflare", return_value=None)
    @patch("lacrimosa_external_sensing._crawl_websearch", return_value=None)
    def test_all_fallbacks_fail_returns_none(self, *mocks):
        """D4-AC06: all crawlers fail → returns None, no crash."""
        result = crawl_with_fallback("https://reddit.com/r/test", EXTERNAL_CONFIG)
        assert result is None


# ---------------------------------------------------------------------------
# Test: social_listener output
# ---------------------------------------------------------------------------


class TestSocialListener:
    """Test social listener signal output format."""

    @patch("lacrimosa_external_sensing.crawl_with_fallback")
    def test_signals_have_correct_source(self, mock_crawl):
        mock_crawl.return_value = '[{"title": "I hate manual workflows", "score": 50}]'
        budget = CrawlBudget(remaining=50, used=0)
        signals = social_listener(EXTERNAL_CONFIG, budget)
        for sig in signals:
            assert sig["source"] in {"reddit", "twitter", "hackernews"}
            assert sig["sensor"] == "social-listener"

    @patch("lacrimosa_external_sensing.crawl_with_fallback")
    def test_signals_have_required_fields(self, mock_crawl):
        mock_crawl.return_value = '[{"title": "AI task automation tool", "score": 30}]'
        budget = CrawlBudget(remaining=50, used=0)
        signals = social_listener(EXTERNAL_CONFIG, budget)
        for sig in signals:
            missing = REQUIRED_SIGNAL_FIELDS - set(sig.keys())
            assert missing == set(), f"Missing: {missing}"

    @patch("lacrimosa_external_sensing.crawl_with_fallback", return_value=None)
    def test_crawl_failure_returns_empty(self, mock_crawl):
        budget = CrawlBudget(remaining=50, used=0)
        signals = social_listener(EXTERNAL_CONFIG, budget)
        assert signals == []


# ---------------------------------------------------------------------------
# Test: competitor_monitor output
# ---------------------------------------------------------------------------


class TestCompetitorMonitor:
    """Test competitor monitor signal output format."""

    @patch("lacrimosa_external_sensing.crawl_with_fallback")
    def test_signals_have_competitor_source(self, mock_crawl):
        mock_crawl.return_value = "Competitor X now supports automated workflow scheduling"
        budget = CrawlBudget(remaining=50, used=0)
        signals = competitor_monitor(EXTERNAL_CONFIG, budget)
        for sig in signals:
            assert sig["source"] == "competitor"
            assert sig["sensor"] == "competitor-monitor"

    @patch("lacrimosa_external_sensing.crawl_with_fallback")
    def test_each_competitor_url_crawled(self, mock_crawl):
        mock_crawl.return_value = "No changes"
        budget = CrawlBudget(remaining=50, used=0)
        competitor_monitor(EXTERNAL_CONFIG, budget)
        # 3 competitors × their URLs
        expected_urls = [
            "https://competitor-a.example.com/changelog",
            "https://competitor-b.example.com",
            "https://competitor-c.example.com/changelog",
        ]
        crawled_urls = [call.args[0] for call in mock_crawl.call_args_list]
        for url in expected_urls:
            assert url in crawled_urls


# ---------------------------------------------------------------------------
# Test: run_external_sensing orchestration
# ---------------------------------------------------------------------------


class TestRunExternalSensing:
    """Test external sensing orchestration with cost cap."""

    @patch("lacrimosa_external_sensing.social_listener", return_value=[])
    @patch("lacrimosa_external_sensing.competitor_monitor", return_value=[])
    @patch("lacrimosa_external_sensing.review_aggregator", return_value=[])
    def test_all_subsensors_called(self, mock_rev, mock_comp, mock_soc):
        counters: dict[str, Any] = {"2026-03-20": {"external_crawls": 0}}
        run_external_sensing(EXTERNAL_CONFIG, counters, "2026-03-20")
        mock_soc.assert_called_once()
        mock_comp.assert_called_once()
        mock_rev.assert_called_once()

    @patch("lacrimosa_external_sensing.social_listener", return_value=[])
    @patch("lacrimosa_external_sensing.competitor_monitor", return_value=[])
    @patch("lacrimosa_external_sensing.review_aggregator", return_value=[])
    def test_result_structure(self, *mocks):
        counters: dict[str, Any] = {"2026-03-20": {"external_crawls": 0}}
        result = run_external_sensing(EXTERNAL_CONFIG, counters, "2026-03-20")
        assert "signals" in result
        assert "crawls_used" in result
        assert "errors" in result

    def test_crawl_cap_prevents_sensing(self):
        """D4-AC04: 50 crawls today → skip remaining sources."""
        counters: dict[str, Any] = {"2026-03-20": {"external_crawls": 50}}
        result = run_external_sensing(EXTERNAL_CONFIG, counters, "2026-03-20")
        assert result["signals"] == []
        assert result["crawls_used"] == 0

    @patch("lacrimosa_external_sensing.social_listener", side_effect=Exception("fail"))
    @patch("lacrimosa_external_sensing.competitor_monitor", return_value=[])
    @patch("lacrimosa_external_sensing.review_aggregator", return_value=[])
    def test_single_subsensor_failure_does_not_halt(self, mock_rev, mock_comp, mock_soc):
        """Single external sensor failure → others continue."""
        counters: dict[str, Any] = {"2026-03-20": {"external_crawls": 0}}
        result = run_external_sensing(EXTERNAL_CONFIG, counters, "2026-03-20")
        assert len(result["errors"]) >= 1
        mock_comp.assert_called_once()
        mock_rev.assert_called_once()

    @pytest.mark.parametrize(
        "crawls_used,expected_can_sense",
        [(0, True), (25, True), (49, True), (50, False), (100, False)],
        ids=["fresh", "mid", "one-left", "at-cap", "over-cap"],
    )
    def test_crawl_cap_boundary(self, crawls_used: int, expected_can_sense: bool):
        """D4-AC04 boundary values for crawl cap."""
        counters: dict[str, Any] = {"2026-03-20": {"external_crawls": crawls_used}}
        result = run_external_sensing(EXTERNAL_CONFIG, counters, "2026-03-20")
        if not expected_can_sense:
            assert result["crawls_used"] == 0


# ---------------------------------------------------------------------------
# Test: ExternalSenseResult structure
# ---------------------------------------------------------------------------


class TestExternalSenseResult:
    """Test ExternalSenseResult TypedDict contract."""

    def test_result_with_signals(self):
        result: ExternalSenseResult = {
            "signals": [{"id": "sig-ext1"}],
            "crawls_used": 5,
            "errors": [],
        }
        assert len(result["signals"]) == 1
        assert result["crawls_used"] == 5

    def test_result_with_errors(self):
        result: ExternalSenseResult = {
            "signals": [],
            "crawls_used": 0,
            "errors": ["Firecrawl 503", "Cloudflare timeout"],
        }
        assert result["signals"] == []
        assert len(result["errors"]) == 2
