"""External sensing: social listener, competitor monitor, review aggregator,
and discovery issue creation for validated signals."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from scripts import lacrimosa_config
try:
    from scripts.lacrimosa_agent_runner import run_agent_prompt
except ImportError:  # pragma: no cover - supports direct script imports
    from lacrimosa_agent_runner import run_agent_prompt

from lacrimosa_signals import create_signal, persist_signal
from lacrimosa_validation import (
    can_crawl_externally,
    sanitize_content,
)

logger = logging.getLogger(__name__)

# -- Types -------------------------------------------------------------------


class ExternalSenseResult(TypedDict):
    signals: list[dict[str, Any]]
    crawls_used: int
    errors: list[str]


@dataclass
class CrawlBudget:
    remaining: int
    used: int

    def can_crawl(self) -> bool:
        return self.remaining > 0

    def consume(self) -> None:
        self.remaining -= 1
        self.used += 1


# -- Public Orchestration ----------------------------------------------------


def run_external_sensing(
    config: dict[str, Any],
    daily_counters: dict[str, Any],
    today: str,
    signals_dir: Path | None = None,
) -> ExternalSenseResult:
    """Run all external sensors with cost cap enforcement."""
    max_crawls = config.get("crawl", {}).get(
        "max_external_crawls_per_day",
        50,
    )
    used_today = daily_counters.get(today, {}).get("external_crawls", 0)

    if not can_crawl_externally(daily_counters, today):
        logger.warning("External crawl cap reached (%d/%d)", used_today, max_crawls)
        return ExternalSenseResult(signals=[], crawls_used=0, errors=[])

    budget = CrawlBudget(remaining=max_crawls - used_today, used=0)
    all_signals: list[dict[str, Any]] = []
    errors: list[str] = []

    subsensors = [
        ("social_listener", social_listener),
        ("competitor_monitor", competitor_monitor),
        ("review_aggregator", review_aggregator),
    ]

    for name, fn in subsensors:
        try:
            signals = fn(config, budget)
            for sig in signals:
                try:
                    persist_signal(sig, signals_dir=signals_dir)
                except Exception as exc:
                    logger.warning("Failed to persist signal: %s", exc)
            all_signals.extend(signals)
        except Exception as exc:
            logger.error("External sensor %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")

    # Update daily counters in place
    today_counters = daily_counters.setdefault(today, {})
    today_counters["external_crawls"] = today_counters.get("external_crawls", 0) + budget.used

    return ExternalSenseResult(
        signals=all_signals,
        crawls_used=budget.used,
        errors=errors,
    )


# -- Discovery Issue Creation ------------------------------------------------

# Project routing for signal tags → Linear project
_TAG_TO_PROJECT: dict[str, str] = {
    "billing": "Billing",
    "stripe": "Billing",
    "payments": "Billing",
    "mobile": "Mobile",
    "swift": "Mobile",
    "seo": "Marketing",
    "marketing": "Marketing",
    "i18n": "Internationalization (i18n)",
    "infra": "Infrastructure",
    "devops": "Infrastructure",
}

_ISSUE_CREATION_TIMEOUT = 60

# Routing → Linear priority and state mapping.
# All validated signals become Linear issues; routing controls visibility.
_ROUTING_TO_LINEAR: dict[str, dict[str, str | int]] = {
    "action": {"priority": 2, "state": "Todo", "label_extra": ""},
    "backlog": {"priority": 3, "state": "Backlog", "label_extra": ""},
    "archived": {"priority": 4, "state": "Backlog", "label_extra": ", Weak Signal"},
}


def create_discovery_issue(
    signal: dict[str, Any],
    scores: dict[str, float],
    daily_counters: dict[str, Any],
    today: str,
    routing: str = "action",
) -> dict[str, Any]:
    """Create a Linear + GitHub issue from a validated signal.

    All signals that pass the 3-gate validation get a Linear issue.
    Routing determines the issue's priority and initial state:
      - action  → Todo, priority 2 (High)
      - backlog → Backlog, priority 3 (Normal)
      - archived → Backlog, priority 4 (Low), labeled "Weak Signal"

    Returns dict with ``created`` (bool), ``linear_issue_id``, ``gh_issue_url``,
    and ``reason`` on skip.
    """
    result: dict[str, Any] = {
        "created": False,
        "linear_issue_id": None,
        "gh_issue_url": None,
        "reason": None,
    }

    linear_params = _ROUTING_TO_LINEAR.get(
        routing, _ROUTING_TO_LINEAR["backlog"],
    )
    priority = linear_params["priority"]
    state = linear_params["state"]
    label_extra = linear_params["label_extra"]

    summary = signal.get("summary", "Unknown signal")
    category = signal.get("category", "unknown")
    composite = sum(scores.values())
    tags = signal.get("relevance_tags", [])
    evidence = signal.get("evidence_links", [])
    raw_excerpt = sanitize_content(str(signal.get("raw_content", ""))[:500])

    # Infer project from tags
    project = lacrimosa_config.get("conductor.default_project")
    for tag in tags:
        mapped = _TAG_TO_PROJECT.get(tag.lower())
        if mapped:
            project = mapped
            break

    # Build evidence section for issue body
    evidence_section = "\n".join(f"- {link}" for link in evidence) if evidence else "None"
    scores_section = "\n".join(
        f"- **{dim}**: {val}" for dim, val in scores.items()
    )

    body = (
        f"## Discovery Signal\n\n"
        f"**Category:** {category}\n"
        f"**Routing:** {routing}\n"
        f"**Composite Score:** {composite:.1f}/10.0\n"
        f"**Reach:** {signal.get('reach', 0)}\n"
        f"**Sentiment:** {signal.get('sentiment', 0)}\n\n"
        f"### Summary\n{summary}\n\n"
        f"### Scores\n{scores_section}\n\n"
        f"### Evidence\n{evidence_section}\n\n"
        f"### Raw Excerpt\n> {raw_excerpt}\n\n"
        f"---\n*Auto-created by Lacrimosa discovery loop*"
    )

    title = f"[Discovery] {summary[:80]}"

    # Dispatch Claude to create the issues (--print only, SEC-C02)
    create_prompt = (
        f"Create a Linear issue and a GitHub issue for this discovery signal.\n\n"
        f"Title: {title}\n"
        f"Project: {project}\n"
        f"Labels: Discovery, {category}{label_extra}\n"
        f"Priority: {priority}\n"
        f"State: {state}\n\n"
        f"Body:\n{body}\n\n"
        f"First search Linear and GitHub for existing issues matching: {summary}\n"
        f"If a matching open issue exists, return its ID instead of creating.\n\n"
        "Output ONLY JSON: "
        '{"created": true/false, "linear_issue_id": "ISSUE-XX" or null, '
        '"gh_issue_url": "https://..." or null, '
        '"reason": "created" or "duplicate: ISSUE-XX"}'
    )

    try:
        proc = run_agent_prompt(
            create_prompt,
            purpose="discovery-issue-creation",
            timeout=_ISSUE_CREATION_TIMEOUT,
        )
        if proc.returncode != 0:
            result["reason"] = f"Agent CLI failed: {proc.stderr[:200]}"
            logger.warning("Discovery issue creation failed: %s", proc.stderr[:200])
            return result

        parsed = _parse_creation_response(proc.stdout)
        result.update(parsed)

        # Increment daily counter on successful creation
        if result.get("created"):
            today_counters = daily_counters.setdefault(today, {})
            today_counters["issues_discovered"] = (
                today_counters.get("issues_discovered", 0) + 1
            )
            logger.info(
                "Created discovery issue: linear=%s gh=%s",
                result.get("linear_issue_id"),
                result.get("gh_issue_url"),
            )

    except subprocess.TimeoutExpired:
        result["reason"] = "Issue creation timed out"
        logger.warning("Discovery issue creation timed out")
    except FileNotFoundError:
        result["reason"] = "Agent CLI not found"
        logger.warning("Agent CLI not found for discovery issue creation")

    return result


def _parse_creation_response(stdout: str) -> dict[str, Any]:
    """Parse JSON response from issue creation Claude session."""
    text = stdout.strip()
    for attempt in [text, _extract_json_from_text(text)]:
        if attempt is None:
            continue
        try:
            data = json.loads(attempt)
            return {
                "created": bool(data.get("created", False)),
                "linear_issue_id": data.get("linear_issue_id"),
                "gh_issue_url": data.get("gh_issue_url"),
                "reason": data.get("reason"),
            }
        except (json.JSONDecodeError, TypeError):
            continue

    return {"created": False, "reason": "Could not parse creation response"}


def _extract_json_from_text(text: str) -> str | None:
    """Extract first JSON object from text."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return None


# -- Social Listener ---------------------------------------------------------


def social_listener(
    config: dict[str, Any],
    crawl_budget: CrawlBudget,
) -> list[dict[str, Any]]:
    """Monitor Reddit/Twitter/HN for relevant discussions."""
    social_config = config.get("crawl", {}).get("social", {})
    sources = social_config.get("sources", {})
    signals: list[dict[str, Any]] = []

    for source_name, source_cfg in sources.items():
        if not crawl_budget.can_crawl():
            break

        keywords = source_cfg.get(
            "keywords",
            source_cfg.get("search_terms", []),
        )
        if not keywords:
            continue

        query = " ".join(keywords[:3])

        crawl_budget.consume()
        content = crawl_with_fallback(
            f"https://{source_name}.com/search?q={query}",
            config,
        )
        if content is None:
            continue

        parsed = _parse_social_content(content, source_name)
        signals.extend(parsed)

    return signals


# -- Competitor Monitor ------------------------------------------------------


def competitor_monitor(
    config: dict[str, Any],
    crawl_budget: CrawlBudget,
) -> list[dict[str, Any]]:
    """Monitor competitor changelogs and pricing pages."""
    targets = config.get("crawl", {}).get("competitors", {}).get("targets", [])
    signals: list[dict[str, Any]] = []
    for target in targets:
        name = target.get("name", "Unknown")
        for url in target.get("urls", []):
            if not crawl_budget.can_crawl():
                break
            crawl_budget.consume()
            content = crawl_with_fallback(url, config)
            if content is None:
                continue
            sanitized = sanitize_content(str(content)[:5000])
            try:
                signals.append(
                    create_signal(
                        source="competitor",
                        sensor="competitor-monitor",
                        category="competitor-move",
                        raw_content=sanitized,
                        summary=f"Update from {name}: {sanitized[:100]}",
                        reach=0,
                        sentiment=0.0,
                        relevance_tags=[name.lower(), "competitor"],
                        evidence_links=[url],
                    )
                )
            except (ValueError, TypeError) as exc:
                logger.warning("Bad competitor signal: %s", exc)
    return signals


# -- Review Aggregator -------------------------------------------------------


def review_aggregator(
    config: dict[str, Any],
    crawl_budget: CrawlBudget,
) -> list[dict[str, Any]]:
    """Monitor review sites (Trustpilot, G2, Capterra)."""
    sources = config.get("crawl", {}).get("competitors", {}).get("review_sources", [])
    signals: list[dict[str, Any]] = []
    for source in sources:
        if not crawl_budget.can_crawl():
            break
        crawl_budget.consume()
        _slug = lacrimosa_config.get("product.slug")
        url = f"https://{source}.com/reviews/{_slug}"
        content = crawl_with_fallback(url, config)
        if content is None:
            continue
        sanitized = sanitize_content(str(content)[:5000])
        try:
            signals.append(
                create_signal(
                    source="competitor",
                    sensor="competitor-monitor",
                    category="competitor-move",
                    raw_content=sanitized,
                    summary=f"Reviews from {source}: {sanitized[:100]}",
                    reach=0,
                    sentiment=0.0,
                    relevance_tags=[source, "reviews"],
                    evidence_links=[url],
                )
            )
        except (ValueError, TypeError) as exc:
            logger.warning("Bad review signal: %s", exc)
    return signals


# -- Fallback Chain ----------------------------------------------------------


def crawl_with_fallback(
    url: str,
    config: dict[str, Any],
) -> str | None:
    """Crawl a URL using the configured fallback chain."""
    chain = config.get("crawl", {}).get(
        "fallback_chain",
        ["firecrawl", "cloudflare_crawl", "web_search_fetch", "skip_and_log"],
    )

    for method in chain:
        if method == "firecrawl":
            result = _crawl_firecrawl(url, config)
        elif method == "cloudflare_crawl":
            result = _crawl_cloudflare(url, config)
        elif method == "web_search_fetch":
            result = _crawl_websearch(url, config)
        elif method == "skip_and_log":
            logger.warning("All crawl methods failed for %s", url)
            return None
        else:
            continue

        if result is not None:
            return result

    return None


# -- Private Crawl Implementations ------------------------------------------


def _crawl_firecrawl(_url: str, _config: dict[str, Any]) -> str | None:
    """Firecrawl deferred per CTO Decision 4."""
    return None


def _crawl_cloudflare(_url: str, _config: dict[str, Any]) -> str | None:
    """Cloudflare /crawl deferred."""
    return None


def _crawl_websearch(url: str, config: dict[str, Any]) -> str | None:
    """Crawl via dispatched Claude session using WebSearch+WebFetch.

    Uses configurable timeout (default 60s for production).
    Falls through to skip_and_log on timeout.
    """
    timeout = config.get("crawl", {}).get("websearch_timeout_seconds", 2)
    try:
        proc = run_agent_prompt(
            f"Fetch the content of this URL: {url}. "
            "Return the main text content as a string. No markdown formatting.",
            purpose="websearch-fetch",
            timeout=timeout,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        pass
    except (FileNotFoundError, OSError):
        pass
    return None


# -- Private Helpers ---------------------------------------------------------


def _parse_social_content(
    content: str,
    source_name: str,
) -> list[dict[str, Any]]:
    """Parse social content (JSON or raw) into signal dicts."""
    try:
        items = json.loads(content)
        if not isinstance(items, list):
            items = [items]
    except (json.JSONDecodeError, TypeError):
        items = [{"title": content[:200], "score": 0}]

    signals: list[dict[str, Any]] = []
    for item in items:
        sanitized = sanitize_content(str(item.get("title", str(item)))[:5000])
        try:
            sig = create_signal(
                source=source_name
                if source_name
                in {
                    "reddit",
                    "twitter",
                    "hackernews",
                }
                else "reddit",
                sensor="social-listener",
                category="pain-point",
                raw_content=sanitized,
                summary=sanitized[:200],
                reach=int(item.get("score", 0)),
                sentiment=float(item.get("sentiment", -0.5)),
                relevance_tags=[source_name],
                evidence_links=[item.get("url", "")],
            )
            signals.append(sig)
        except (ValueError, TypeError) as exc:
            logger.warning("Bad social signal: %s", exc)

    return signals
