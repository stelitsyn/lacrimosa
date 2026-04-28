"""Linear intake system for bug reports and support emails.

Receives incoming reports, classifies them via LLM, deduplicates against
existing Linear/GitHub issues, and auto-creates Linear issues with proper
severity, domain, project, and label routing.

Part of Lacrimosa auto-triage pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from scripts import lacrimosa_config
from scripts.lacrimosa_agent_runner import run_agent_prompt

logger = logging.getLogger(__name__)

# -- Constants ---------------------------------------------------------------

CLASSIFICATION_TIMEOUT_SECONDS = 120
DEDUP_TIMEOUT_SECONDS = 60
ISSUE_CREATION_TIMEOUT_SECONDS = 60
MAX_CLASSIFICATION_RETRIES = 2  # Total attempts = 3

VALID_CATEGORIES = frozenset({
    "bug",
    "feature_request",
    "question",
    "complaint",
    "praise",
})

VALID_SEVERITIES = frozenset({
    "critical",
    "high",
    "medium",
    "low",
})

# Categories that should NOT result in issue creation
NON_ACTIONABLE_CATEGORIES = frozenset({
    "praise",
    "question",
})

SEVERITY_PRIORITY_MAP: dict[str, int] = {
    "critical": 1,  # Urgent
    "high": 2,
    "medium": 3,  # Normal
    "low": 4,
}

# Domain → Linear project routing (inverted from config's project→keywords format)
# Lazy-loaded to avoid import-time config access (config not yet loaded in tests).
_domain_project_map: dict[str, str] | None = None


def _get_domain_project_map() -> dict[str, str]:
    global _domain_project_map
    if _domain_project_map is None:
        routing = lacrimosa_config.get("project_routing")
        _domain_project_map = {
            keyword: project
            for project, keywords in routing.items()
            for keyword in keywords
        }
    return _domain_project_map

# Domain → keywords for classification guidance
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "communication": ["message", "notification", "alert", "webhook", "realtime"],
    "billing": ["billing", "payment", "invoice", "subscription", "credit", "charge", "stripe", "plan", "pricing"],
    "mobile": ["mobile", "android", "ios", "swift", "app store", "apple", "testflight"],
    "infra": ["server", "deploy", "docker", "cloud run", "cloudflare", "ci/cd", "latency", "timeout", "502", "503"],
    "email": ["email", "inbox", "send", "receive", "smtp", "resend"],
    "marketing": ["seo", "landing page", "conversion", "campaign", "referral"],
    "i18n": ["translation", "language", "locale", "multilingual", "i18n"],
    "platform": ["app", "dashboard", "settings", "account", "profile", "login", "auth"],
    "search": ["search", "lookup", "find", "google", "maps", "places"],
    "coordination": ["task", "goal", "schedule", "calendar", "reminder", "coordination"],
    "onboarding": ["onboarding", "signup", "welcome", "tutorial", "first time"],
}

# Domain → area label for Linear
DOMAIN_AREA_LABEL: dict[str, str] = {
    "communication": "Communication",
    "billing": "Billing",
    "mobile": "Mobile",
    "infra": "DevOps",
    "email": "Email",
    "marketing": "SEO",
    "i18n": "Internationalization",
    "platform": "Backend",
    "search": "Search",
    "coordination": "Coordination",
    "onboarding": "Onboarding",
}

# Category → type label for Linear
CATEGORY_TYPE_LABEL: dict[str, str] = {
    "bug": "Bug",
    "feature_request": "Feature Request",
    "complaint": "Bug",
    "question": "Documentation",
    "praise": "Feedback",
}


# -- Enums -------------------------------------------------------------------


class IntakeSource(StrEnum):
    BUG_REPORT = "bug_report"
    SUPPORT_EMAIL = "support_email"


# -- Dataclasses -------------------------------------------------------------


@dataclass
class IntakeReport:
    """A raw intake report from bug report or support email."""

    id: str
    source: IntakeSource
    subject: str
    body: str
    sender: str
    received_at: str


@dataclass
class TriageClassification:
    """Result of LLM-based triage classification."""

    severity: str
    category: str
    domain: str
    summary: str
    confidence: float
    reproduction_steps: list[str] = field(default_factory=list)
    affected_area: str = ""


@dataclass
class IntakeResult:
    """Full result of the intake pipeline."""

    report: IntakeReport
    classified: bool
    classification: TriageClassification
    is_novel: bool
    duplicate_of: str | None
    issue_created: bool
    linear_issue_id: str | None
    gh_issue_url: str | None
    reason: str | None


# -- Report Creation ---------------------------------------------------------


def create_intake_report(
    source: str,
    subject: str,
    body: str,
    sender: str,
    received_at: str,
) -> IntakeReport:
    """Create an IntakeReport from raw input data.

    Validates required fields and source type.
    """
    valid_sources = {s.value for s in IntakeSource}
    if source not in valid_sources:
        raise ValueError(
            f"Invalid intake source: {source!r}. Must be one of {sorted(valid_sources)}"
        )
    if not subject or not subject.strip():
        raise ValueError("subject must not be empty")
    if not body or not body.strip():
        raise ValueError("body must not be empty")

    return IntakeReport(
        id=f"intake-{uuid.uuid4().hex[:12]}",
        source=IntakeSource(source),
        subject=subject.strip(),
        body=body.strip(),
        sender=sender.strip(),
        received_at=received_at,
    )


# -- Classification Parsing --------------------------------------------------


def parse_classification_response(raw_output: str) -> TriageClassification:
    """Parse and validate LLM classification output into TriageClassification."""
    data = _extract_json_object(raw_output)

    # Validate required fields
    if "severity" not in data:
        raise ValueError("Missing required field: severity")
    if "category" not in data:
        raise ValueError("Missing required field: category")
    if "domain" not in data:
        raise ValueError("Missing required field: domain")

    severity = str(data["severity"]).lower().strip()
    category = str(data["category"]).lower().strip()
    domain = str(data["domain"]).lower().strip()

    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity: {severity!r}. Must be one of {sorted(VALID_SEVERITIES)}"
        )

    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category: {category!r}. Must be one of {sorted(VALID_CATEGORIES)}"
        )

    # Clamp confidence
    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    raw_steps = data.get("reproduction_steps", [])
    if not isinstance(raw_steps, list):
        raw_steps = [str(raw_steps)] if raw_steps else []

    return TriageClassification(
        severity=severity,
        category=category,
        domain=domain,
        summary=str(data.get("summary", "")),
        confidence=confidence,
        reproduction_steps=raw_steps,
        affected_area=str(data.get("affected_area", "")),
    )


# -- Project & Label Routing -------------------------------------------------


def route_to_project(domain: str) -> str:
    """Map domain to Linear project name."""
    return _get_domain_project_map().get(domain.lower(), lacrimosa_config.get("conductor.default_project"))


def route_to_labels(classification: TriageClassification) -> list[str]:
    """Generate Linear labels from classification."""
    labels: list[str] = []

    # Area label from domain
    area = DOMAIN_AREA_LABEL.get(classification.domain)
    if area:
        labels.append(area)

    # Type label from category
    type_label = CATEGORY_TYPE_LABEL.get(classification.category)
    if type_label:
        labels.append(type_label)

    # Add "Intake" label for traceability
    labels.append("Intake")

    return labels


def determine_priority(severity: str) -> int:
    """Map severity string to Linear priority integer (1=Urgent, 4=Low)."""
    return SEVERITY_PRIORITY_MAP.get(severity.lower(), 3)


# -- LLM Classification ------------------------------------------------------


def classify_report(report: IntakeReport) -> TriageClassification:
    """Classify an intake report using LLM.

    Retries on parse failures. Falls back to a safe default on total failure.
    """
    for attempt in range(MAX_CLASSIFICATION_RETRIES + 1):
        try:
            raw = _dispatch_classification_session(report, attempt)
            return parse_classification_response(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "Classification attempt %d failed: %s",
                attempt + 1,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "Classification attempt %d error: %s",
                attempt + 1,
                exc,
            )

    logger.error("All classification attempts exhausted, using fallback")
    return TriageClassification(
        severity="medium",
        category="bug",
        domain="platform",
        summary=report.subject,
        confidence=0.0,
    )


def _dispatch_classification_session(
    report: IntakeReport,
    attempt: int,
) -> str:
    """Dispatch Claude session for intake classification."""
    prompt = _build_classification_prompt(report)

    if attempt > 0:
        prompt += (
            "\n\nYour previous response was not valid JSON. "
            "Respond with ONLY a JSON object."
        )

    result = run_agent_prompt(
        prompt,
        purpose="intake-classification",
        timeout=CLASSIFICATION_TIMEOUT_SECONDS,
    )
    return result.stdout


def _build_classification_prompt(report: IntakeReport) -> str:
    """Build the classification prompt for an intake report."""
    sanitized_body = _sanitize_for_prompt(report.body)
    sanitized_subject = _sanitize_for_prompt(report.subject)

    _product = lacrimosa_config.get("product.name")
    _desc = lacrimosa_config.get("product.description")
    return (
        f"You are a support triage engine for {_product}, {_desc}. "
        "Classify this incoming report.\n\n"
        f"Source: {report.source.value}\n"
        f"Subject: {sanitized_subject}\n"
        f"Body: {sanitized_body}\n"
        f"Sender: {report.sender}\n\n"
        "Classify into:\n"
        "- severity: critical | high | medium | low\n"
        "- category: bug | feature_request | question | complaint | praise\n"
        "- domain: one of: communication, billing, mobile, infra, email, "
        "marketing, i18n, platform, search, coordination, onboarding\n"
        "- summary: one-line summary of the issue\n"
        "- reproduction_steps: list of steps (if bug)\n"
        "- affected_area: specific subsystem\n"
        "- confidence: 0.0 to 1.0\n\n"
        'Output ONLY JSON: {"severity": "...", "category": "...", '
        '"domain": "...", "summary": "...", "reproduction_steps": [...], '
        '"affected_area": "...", "confidence": 0.XX}'
    )


# -- Deduplication -----------------------------------------------------------


def check_intake_deduplication(
    summary: str,
    tags: list[str],
) -> tuple[bool, str | None]:
    """Check if a similar issue already exists in Linear/GitHub."""
    try:
        raw = _dispatch_dedup_session(summary, tags)
        data = _extract_json_object(raw)
        is_novel = data.get("is_novel", True)
        existing = data.get("existing_issue")
        return (bool(is_novel), existing)
    except Exception as exc:
        logger.warning("Intake dedup check failed: %s — treating as novel", exc)
        return (True, None)


def _dispatch_dedup_session(summary: str, tags: list[str]) -> str:
    """Dispatch Claude session for deduplication check."""
    query = f"{summary} {' '.join(tags)}"
    sanitized_query = _sanitize_for_prompt(query)

    prompt = (
        f"Search Linear and GitHub issues for: {sanitized_query}. "
        "If a matching open issue exists, return its ID (e.g., ISSUE-XX). "
        "If matching issues are Done/Cancelled, treat as novel. "
        'Output ONLY JSON: {{"is_novel": true/false, "existing_issue": "ISSUE-XX" or null}}'
    )

    result = run_agent_prompt(
        prompt,
        purpose="intake-deduplication",
        timeout=DEDUP_TIMEOUT_SECONDS,
    )
    return result.stdout


# -- Linear Issue Creation ---------------------------------------------------


def create_linear_issue_from_intake(
    report: IntakeReport,
    classification: TriageClassification,
) -> dict[str, Any]:
    """Create a Linear issue from classified intake report.

    Returns dict with created (bool), linear_issue_id, gh_issue_url, reason.
    """
    result: dict[str, Any] = {
        "created": False,
        "linear_issue_id": None,
        "gh_issue_url": None,
        "reason": None,
    }

    project = route_to_project(classification.domain)
    labels = route_to_labels(classification)
    priority = determine_priority(classification.severity)

    # Build issue body
    repro = ""
    if classification.reproduction_steps:
        steps = "\n".join(
            f"{i + 1}. {step}"
            for i, step in enumerate(classification.reproduction_steps)
        )
        repro = f"\n\n### Reproduction Steps\n{steps}"

    sanitized_subject = _sanitize_for_prompt(report.subject)

    body = (
        f"## Intake Report\n\n"
        f"**Source:** {report.source.value}\n"
        f"**Sender:** {report.sender}\n"
        f"**Received:** {report.received_at}\n"
        f"**Severity:** {classification.severity}\n"
        f"**Category:** {classification.category}\n"
        f"**Domain:** {classification.domain}\n"
        f"**Confidence:** {classification.confidence:.0%}\n\n"
        f"### Summary\n{classification.summary}\n"
        f"{repro}\n\n"
        f"### Original Report\n"
        f"**Subject:** {sanitized_subject}\n\n"
        f"> {_sanitize_for_prompt(report.body)}\n\n"
        f"---\n*Auto-created by Lacrimosa intake triage*"
    )

    title_prefix = "[Bug]" if classification.category == "bug" else f"[{classification.category.replace('_', ' ').title()}]"
    title = f"{title_prefix} {_sanitize_for_prompt(classification.summary)}"

    create_prompt = (
        f"Create a Linear issue and a GitHub issue.\n\n"
        f"Title: {title}\n"
        f"Project: {project}\n"
        f"Labels: {', '.join(labels)}\n"
        f"Priority: {priority}\n\n"
        f"Body:\n{body}\n\n"
        f"First search Linear and GitHub for existing issues matching: {classification.summary}\n"
        f"If a matching open issue exists, return its ID instead of creating.\n\n"
        "Output ONLY JSON: "
        '{"created": true/false, "linear_issue_id": "ISSUE-XX" or null, '
        '"gh_issue_url": "https://..." or null, '
        '"reason": "created" or "duplicate: ISSUE-XX"}'
    )

    try:
        raw = _dispatch_issue_creation_session(create_prompt)
        parsed = _parse_creation_response(raw)
        result.update(parsed)
    except subprocess.TimeoutExpired:
        result["reason"] = "Issue creation timed out"
        logger.warning("Intake issue creation timed out")
    except FileNotFoundError:
        result["reason"] = "Agent CLI not found"
        logger.warning("Agent CLI not found for intake issue creation")
    except Exception as exc:
        result["reason"] = f"Issue creation failed: {exc}"
        logger.warning("Intake issue creation failed: %s", exc)

    return result


def _dispatch_issue_creation_session(prompt: str) -> str:
    """Dispatch Claude session for issue creation."""
    result = run_agent_prompt(
        prompt,
        purpose="intake-issue-creation",
        timeout=ISSUE_CREATION_TIMEOUT_SECONDS,
        dangerous=True,
    )
    return result.stdout


def _parse_creation_response(stdout: str) -> dict[str, Any]:
    """Parse JSON response from issue creation session."""
    try:
        data = _extract_json_object(stdout)
        return {
            "created": bool(data.get("created", False)),
            "linear_issue_id": data.get("linear_issue_id"),
            "gh_issue_url": data.get("gh_issue_url"),
            "reason": data.get("reason"),
        }
    except (ValueError, json.JSONDecodeError):
        return {"created": False, "reason": "Could not parse creation response"}


# -- Full Pipeline -----------------------------------------------------------


def process_intake(raw_report: dict[str, Any]) -> IntakeResult:
    """Process a single intake report through the full pipeline.

    Steps:
    1. Parse raw report into IntakeReport
    2. Classify via LLM (severity, category, domain)
    3. Skip issue creation for non-actionable categories (praise, question)
    4. Deduplicate against existing issues
    5. Create Linear + GitHub issues if novel and actionable

    Returns IntakeResult with full pipeline state.
    """
    # Step 1: Parse
    try:
        report = create_intake_report(
            source=raw_report["source"],
            subject=raw_report["subject"],
            body=raw_report["body"],
            sender=raw_report.get("sender", ""),
            received_at=raw_report["received_at"],
        )
    except KeyError as exc:
        raise ValueError(f"Missing required field in raw_report: {exc}") from exc

    # Step 2: Classify
    classification = classify_report(report)

    # Step 3: Check if actionable
    if classification.category in NON_ACTIONABLE_CATEGORIES:
        return IntakeResult(
            report=report,
            classified=True,
            classification=classification,
            is_novel=True,
            duplicate_of=None,
            issue_created=False,
            linear_issue_id=None,
            gh_issue_url=None,
            reason=f"Non-actionable category: {classification.category}",
        )

    # Step 4: Dedup
    tags = [classification.domain]
    if classification.affected_area:
        tags.append(classification.affected_area)
    is_novel, existing_id = check_intake_deduplication(
        classification.summary,
        tags,
    )

    if not is_novel:
        return IntakeResult(
            report=report,
            classified=True,
            classification=classification,
            is_novel=False,
            duplicate_of=existing_id,
            issue_created=False,
            linear_issue_id=None,
            gh_issue_url=None,
            reason=f"Duplicate of {existing_id}",
        )

    # Step 5: Create issue
    creation = create_linear_issue_from_intake(report, classification)

    return IntakeResult(
        report=report,
        classified=True,
        classification=classification,
        is_novel=True,
        duplicate_of=None,
        issue_created=creation.get("created", False),
        linear_issue_id=creation.get("linear_issue_id"),
        gh_issue_url=creation.get("gh_issue_url"),
        reason=creation.get("reason"),
    )


# -- Utilities ---------------------------------------------------------------


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

    raise ValueError(f"Could not parse JSON from output: {text[:200]}")



def _sanitize_for_prompt(text: str) -> str:
    """Sanitize content for LLM prompt inclusion."""
    if not text:
        return text
    result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    result = re.sub(
        r"</?(?:system|tool|assistant|human|function_calls|antml)[^>]*>",
        "",
        result,
        flags=re.IGNORECASE,
    )
    return result
